// All API calls go through the Orchestrator — never to individual agents directly.
// See INTERFACE_CONTRACT.md for the full endpoint reference.
//
// Set VITE_ORCHESTRATOR_URL=http://localhost:8000 in .env (copy from .env.example).

const BASE = import.meta.env.VITE_ORCHESTRATOR_URL ?? '';
const LAB_ID = import.meta.env.VITE_LAB_ID ?? 'lab4';

// ── Shared types (mirrors INTERFACE_CONTRACT.md shared schemas) ─────────────

export type StudentStatus = 'on_track' | 'needs_help' | 'flagged' | 'inactive';

export type AgentName = 'Lab Companion' | 'Participant' | 'Integrity' | 'Curriculum Designer';

export interface DashboardPayload {
  lab: {
    lab_id: string;
    title: string;
    phase: 'pre_lab' | 'during_lab' | 'post_lab';
    students_enrolled: number;
  };
  activity: {
    needs_help: StudentActivityRow[];
    flagged: StudentActivityRow[];
    on_track: StudentActivityRow[];
    inactive?: StudentActivityRow[];
  };
  grades: {
    submissions_total: number;
    auto_graded: number;
    needs_review: number;
    flagged: number;
    rows: GradeRow[];
  };
  stats: {
    class_average: number;
    grade_distribution: Record<string, number>;
    ai_assistance: Record<string, string | number>;
    per_student: PerStudentStat[];
  };
}

export interface StudentActivityRow {
  student_id: string;
  total_questions: number;
  last_message: string;
  top_topic: string;
  status: StudentStatus;
}

export interface GradeRow {
  submission_id: string;
  student_id: string;
  automated_score: number;
  final_score: number | null;
  status: 'completed' | 'needs_review' | 'flagged';
  feedback_summary: string;
}

export interface PerStudentStat {
  student_id: string;
  score: number;
  question_count: number;
  hint_count: number;
  status: StudentStatus;
}

// Per-student integrity analytics — from GET /analytics/lab/{lab_id} via Orchestrator
export interface StudentIntegrityData {
  student_id: string;
  question_count: number;
  violation_count: number;
  status: 'ON_TRACK' | 'FLAGGED' | 'NEEDS_HELP';
  classification_breakdown: Record<string, number>;
}

// ── API helpers ──────────────────────────────────────────────────────────────

async function get<T>(path: string): Promise<T | null> {
  if (!BASE) return null;
  try {
    const res = await fetch(`${BASE}${path}`);
    if (!res.ok) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}

// ── Dashboard ────────────────────────────────────────────────────────────────

export async function fetchDashboard(tab?: 'material' | 'activity' | 'grades' | 'stats'): Promise<DashboardPayload | null> {
  const query = tab ? `?tab=${tab}` : '';
  return get<DashboardPayload>(`/orchestrator/instructor/dashboard/${LAB_ID}${query}`);
}

// ── Student Activity (polls every 10s per contract — v0.1) ──────────────────

export async function fetchActivityTab() {
  const data = await fetchDashboard('activity');
  return data?.activity ?? null;
}

// ── Integrity analytics (feeds per-student integrity data) ──────────────────

export interface IntegrityAnalytics {
  lab_id: string;
  question_stats: {
    total_questions: number;
    avg_questions_per_student: number;
    direct_solution_attempts: number;
    escalated_session_count: number;
  };
  per_student: StudentIntegrityData[];
}

export async function fetchIntegrityAnalytics(): Promise<IntegrityAnalytics | null> {
  return get<IntegrityAnalytics>(`/orchestrator/integrity/analytics/lab/${LAB_ID}`);
}

// ── Submission detail ────────────────────────────────────────────────────────

export async function fetchSubmission(submissionId: string) {
  return get(`/orchestrator/instructor/submission/${submissionId}`);
}

// ── Grading actions ──────────────────────────────────────────────────────────

export async function triggerGradeBatch(): Promise<{ submissions_queued: number } | null> {
  if (!BASE) return null;
  try {
    const res = await fetch(`${BASE}/orchestrator/instructor/grade-batch?lab_id=${LAB_ID}`, { method: 'POST' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
