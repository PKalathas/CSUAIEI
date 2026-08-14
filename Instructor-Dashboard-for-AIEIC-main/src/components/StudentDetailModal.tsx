import type { AgentName } from '../api/agents';

interface AgentSnapshot {
  status: string;
  keyMetric: string;
  detail: string;
  reasoning: string;
  flagged: boolean;
}

interface InterventionEntry {
  time: string;
  agent: AgentName | 'Instructor';
  type: string;
  description: string;
  severity: 'info' | 'warning' | 'critical';
}

interface StudentDetailData {
  score?: number;
  agents: Record<AgentName, AgentSnapshot>;
  interventions: InterventionEntry[];
}

const STUDENT_DETAILS: Record<string, StudentDetailData> = {
  'Carlos R': {
    score: 45,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 5 / 5',
        keyMetric: '31 prompts · 4 blocked',
        detail: 'All scaffolded hints exhausted. Repeated direct-answer seeking on insertion and deletion tasks.',
        reasoning: 'Student has reached the hint ceiling across 3 separate task attempts. Pattern of "give me the answer" phrasing in 6 of last 10 prompts indicates conceptual overload, not surface confusion.',
        flagged: true,
      },
      'Participant': {
        status: 'Pacing: 28 min behind',
        keyMetric: '73 min session · Engagement 42/100',
        detail: 'Significantly behind expected 47-min lab time. Engagement score declining since minute 45.',
        reasoning: 'Engagement drop correlates with hint exhaustion event at 2:31 PM. Student may have disengaged after realizing hints would not provide direct answers.',
        flagged: true,
      },
      'Integrity': {
        status: '⚠ Similarity Flag',
        keyMetric: '87% match with Nina Q',
        detail: '14 matched prompt pairs across both sessions. 6 direct-answer-seeking attempts logged.',
        reasoning: 'Cross-student similarity exceeds the 70% threshold across semantically equivalent prompts. Temporal overlap in submission timing adds weight to collaboration concern. Recommended for instructor review before grading.',
        flagged: true,
      },
      'Curriculum Designer': {
        status: '2 misconceptions logged',
        keyMetric: '1 / 4 topics complete',
        detail: 'Conceptual gaps in pointer semantics and head-node edge cases identified across 5 prompts.',
        reasoning: 'Pointer vs value confusion is a foundational gap affecting all downstream tasks. Recommend supplemental material on pointer fundamentals before Lab 5.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:47 PM', agent: 'Integrity', type: 'Similarity Flag', description: '87% prompt similarity with Nina Q detected across 14 matched pairs. Flag sent to instructor queue.', severity: 'critical' },
      { time: '2:31 PM', agent: 'Lab Companion', type: 'Hint Cap Reached', description: 'Student reached maximum hint level (5/5) on insertion task. All scaffolded hints exhausted. Escalation sent to instructor.', severity: 'warning' },
      { time: '2:15 PM', agent: 'Participant', type: 'Pacing Alert', description: 'Student 28 min behind expected lab pace. Engagement score dropped below 50/100 threshold.', severity: 'warning' },
      { time: '1:58 PM', agent: 'Lab Companion', type: 'Direct Answer Blocked', description: '"Just give me the full insert function" classified as direct-answer seeking. Redirected to Hint 4.', severity: 'info' },
      { time: '1:42 PM', agent: 'Curriculum Designer', type: 'Misconception Logged', description: 'Repeated confusion about pointer vs value semantics across 3 prompts. Added to curriculum review queue.', severity: 'info' },
    ],
  },
  'Nina Q': {
    score: 48,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 3 / 5',
        keyMetric: '28 prompts · 2 blocked',
        detail: 'Progressing through hints at moderate pace. 2 direct-answer-seeking attempts redirected.',
        reasoning: 'Prompt patterns show student partially understands concepts but is attempting to shortcut verification steps. Hint progression is consistent with surface-level understanding.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: 20 min behind',
        keyMetric: '67 min session · Engagement 58/100',
        detail: 'Moderate engagement. Pacing behind expected time by about 20 minutes.',
        reasoning: 'Engagement score has been stable around 58, suggesting steady but slow progress. No disengagement events logged.',
        flagged: false,
      },
      'Integrity': {
        status: '⚠ Similarity Flag',
        keyMetric: '87% match with Carlos R',
        detail: '14 matched prompt pairs with Carlos R across shared session window.',
        reasoning: 'Same 87% similarity score as Carlos R. The direction of similarity (who copied whom) is ambiguous from prompt data alone. Both students flagged pending instructor review.',
        flagged: true,
      },
      'Curriculum Designer': {
        status: '1 misconception logged',
        keyMetric: '2 / 4 topics complete',
        detail: 'Insertion logic misconception identified. Traversal and basic structure completed correctly.',
        reasoning: 'Insertion error pattern matches a common misunderstanding of the "off-by-one" pointer advance. This is fixable with a single targeted explanation.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:47 PM', agent: 'Integrity', type: 'Similarity Flag', description: '87% prompt similarity with Carlos R detected. Flag sent to instructor queue alongside Carlos R flag.', severity: 'critical' },
      { time: '2:20 PM', agent: 'Lab Companion', type: 'Direct Answer Blocked', description: '"Can you just write the delete function for me?" redirected to Hint 2.', severity: 'info' },
      { time: '1:55 PM', agent: 'Curriculum Designer', type: 'Misconception Logged', description: 'Repeated off-by-one error in insertion pointer advance. Logged for curriculum review.', severity: 'info' },
    ],
  },
  'Ethan L': {
    score: 62,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 3 / 5',
        keyMetric: '22 prompts · 0 blocked',
        detail: 'Reached Hint 3 on pointer swap task. Genuinely stuck — not attempting to game the system.',
        reasoning: 'Unlike flagged students, prompt phrasing shows authentic confusion rather than answer-seeking. Student is asking "why" questions. Consider instructor check-in.',
        flagged: true,
      },
      'Participant': {
        status: 'Pacing: 5 min behind',
        keyMetric: '52 min session · Engagement 71/100',
        detail: 'Slightly behind schedule but engagement is healthy. Actively working through problems.',
        reasoning: 'Engagement score above 70 suggests student is putting in genuine effort. Pacing delay is likely due to the stuck point on pointer swap.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'No integrity concerns detected. Prompt patterns are independent and question-focused.',
        reasoning: 'Prompt diversity score is high — student is asking varied, contextual questions indicating original work.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '1 misconception logged',
        keyMetric: '2 / 4 topics complete',
        detail: 'Pointer swap (temp variable pattern) identified as knowledge gap.',
        reasoning: 'This is a classic misconception at this stage. A targeted explanation of the three-step swap pattern would likely unblock the student quickly.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:40 PM', agent: 'Lab Companion', type: 'Escalation Candidate', description: 'Student stuck at Hint 3 for 15+ minutes without progress. Marked as instructor escalation candidate.', severity: 'warning' },
      { time: '2:22 PM', agent: 'Curriculum Designer', type: 'Misconception Logged', description: 'Pointer swap temp-variable confusion detected across 4 prompts. Logged for curriculum review.', severity: 'info' },
      { time: '2:05 PM', agent: 'Lab Companion', type: 'Hint 3 Delivered', description: 'Scaffolded hint on pointer swap step-by-step pattern delivered. Student acknowledged but still stuck.', severity: 'info' },
    ],
  },
  'Alex M': {
    score: 92,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 2 / 5',
        keyMetric: '12 prompts · 0 blocked',
        detail: 'On track. Using hints as intended for guided discovery, not answer-seeking.',
        reasoning: 'Prompt quality is high — student is asking conceptual questions and verifying understanding. No intervention needed.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: on track',
        keyMetric: '38 min session · Engagement 84/100',
        detail: 'Within expected 47-min window. Consistent engagement throughout session.',
        reasoning: 'Steady engagement with no drops. Student is progressing efficiently.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'All prompts independent. No integrity concerns.',
        reasoning: 'Prompt patterns are highly varied and context-specific. No similarity concerns.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '3 / 4 topics complete',
        keyMetric: '0 misconceptions',
        detail: 'Insertion, traversal, and basic deletion completed correctly. Edge cases in progress.',
        reasoning: 'Student shows strong conceptual grasp. Remaining topic (edge cases) is within expected progress for this point in the lab.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:10 PM', agent: 'Lab Companion', type: 'Hint 2 Delivered', description: 'Scaffolded hint on insertion at position N delivered. Student acknowledged and moved forward.', severity: 'info' },
    ],
  },
  'Bella K': {
    score: 88,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 1 / 5',
        keyMetric: '9 prompts · 0 blocked',
        detail: 'Minimal hint usage. Primarily asking design-level questions.',
        reasoning: 'Student is demonstrating design thinking which indicates strong conceptual engagement. Well ahead of peers.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: on track',
        keyMetric: '41 min session · Engagement 88/100',
        detail: 'Strong engagement. On schedule.',
        reasoning: 'Top-quartile engagement score. Student is actively exploring the problem space.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'All prompts independent.',
        reasoning: 'No integrity concerns. Prompt diversity is high.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '4 / 4 topics complete',
        keyMetric: '0 misconceptions',
        detail: 'All lab topics completed. Student submitted early.',
        reasoning: 'No curriculum gaps detected. Student may benefit from extension challenges.',
        flagged: false,
      },
    },
    interventions: [],
  },
  'Dana W': {
    score: 85,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 2 / 5',
        keyMetric: '15 prompts · 0 blocked',
        detail: 'Working through deletion edge cases with guided hints.',
        reasoning: 'Student is methodically debugging the head-deletion case. Hint 2 was sufficient to get them unstuck.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: on track',
        keyMetric: '44 min session · Engagement 79/100',
        detail: 'On pace. Consistent effort throughout.',
        reasoning: 'No engagement drops. Student is progressing steadily.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'All prompts independent.',
        reasoning: 'No integrity concerns.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '3 / 4 topics complete',
        keyMetric: '0 misconceptions',
        detail: 'Deletion edge case is the remaining topic. On track to finish.',
        reasoning: 'Student is close to completing all topics. No intervention needed.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:18 PM', agent: 'Lab Companion', type: 'Hint 2 Delivered', description: 'Hint on head-node deletion special case delivered. Student unblocked.', severity: 'info' },
    ],
  },
  'Fiona S': {
    score: 79,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 2 / 5',
        keyMetric: '10 prompts · 0 blocked',
        detail: 'Memory management focus. Asking good questions about freeing nodes.',
        reasoning: 'Student is thinking carefully about memory safety — a positive indicator. Minor style issues noted in grading but conceptual understanding is solid.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: on track',
        keyMetric: '39 min session · Engagement 76/100',
        detail: 'On pace with healthy engagement.',
        reasoning: 'No concerns. Student is progressing at a good pace.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'All prompts independent.',
        reasoning: 'No integrity concerns.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '3 / 4 topics complete',
        keyMetric: '0 misconceptions',
        detail: 'Memory management topic in progress. On track.',
        reasoning: 'Student is asking exactly the right questions about memory. Likely to complete without intervention.',
        flagged: false,
      },
    },
    interventions: [],
  },
  'Jake N': {
    score: 71,
    agents: {
      'Lab Companion': {
        status: 'Hint Level 3 / 5',
        keyMetric: '20 prompts · 0 blocked',
        detail: 'On track per hint pace benchmarks despite high prompt count.',
        reasoning: 'Higher prompt count is within normal range for this task complexity. Hint progression is healthy — student is not stuck at any single level.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: on track',
        keyMetric: '46 min session · Engagement 68/100',
        detail: 'Just within expected time window. Engagement slightly below average but stable.',
        reasoning: 'Engagement score of 68 is below class average but not alarming. Student may benefit from a short check-in.',
        flagged: false,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'All prompts independent.',
        reasoning: 'No integrity concerns.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '2 / 4 topics complete',
        keyMetric: '0 misconceptions',
        detail: 'Two topics remaining. Needs review on task 3.',
        reasoning: 'Partial completion of task 3 is noted. Manual review recommended to determine if conceptual gap exists.',
        flagged: false,
      },
    },
    interventions: [
      { time: '2:35 PM', agent: 'Lab Companion', type: 'Hint 3 Delivered', description: 'Hint 3 delivered on task 3 logic. Student acknowledged but progress is slow.', severity: 'info' },
    ],
  },
  'George T': {
    agents: {
      'Lab Companion': {
        status: 'Hint Level 0 / 5',
        keyMetric: '2 prompts · 0 blocked',
        detail: 'Minimal engagement. Only basic environment setup questions asked.',
        reasoning: 'Extremely low prompt activity. Student may be confused about the lab environment or may not have started the lab tasks yet.',
        flagged: false,
      },
      'Participant': {
        status: 'Pacing: 40 min behind',
        keyMetric: '15 min session · Engagement 22/100',
        detail: 'Very low activity. Has not meaningfully started the lab.',
        reasoning: 'Engagement score of 22 is the lowest in the class. Combined with only 2 prompts in 15 minutes, this student needs proactive instructor outreach.',
        flagged: true,
      },
      'Integrity': {
        status: 'No flags',
        keyMetric: '0 similarity concerns',
        detail: 'No prompts to analyze for similarity.',
        reasoning: 'Insufficient prompt data for analysis.',
        flagged: false,
      },
      'Curriculum Designer': {
        status: '0 / 4 topics complete',
        keyMetric: 'Not started',
        detail: 'No lab task progress detected.',
        reasoning: 'Student has not begun any lab tasks. Immediate instructor check-in recommended.',
        flagged: true,
      },
    },
    interventions: [
      { time: '2:50 PM', agent: 'Participant', type: 'Low Activity Alert', description: 'Student has been active for 15 minutes with only 2 prompts and no task progress. Flagged for monitoring.', severity: 'warning' },
    ],
  },
};

const AGENT_COLORS: Record<AgentName | 'Instructor', string> = {
  'Lab Companion': 'var(--color-primary)',
  'Participant': 'var(--color-on-track)',
  'Integrity': 'var(--color-flagged)',
  'Curriculum Designer': 'var(--color-curriculum)',
  'Instructor': 'var(--color-text-muted)',
};

const AGENT_BG: Record<AgentName | 'Instructor', string> = {
  'Lab Companion': 'var(--bg-blue-light)',
  'Participant': 'var(--bg-green-light)',
  'Integrity': '#fdf0e4',
  'Curriculum Designer': 'var(--bg-purple-light)',
  'Instructor': 'var(--bg-light)',
};

const AGENT_ORDER: AgentName[] = ['Lab Companion', 'Participant', 'Integrity', 'Curriculum Designer'];

interface Props {
  studentName: string;
  onClose: () => void;
  onViewSubmission: () => void;
}

export default function StudentDetailModal({ studentName, onClose, onViewSubmission }: Props) {
  const data = STUDENT_DETAILS[studentName];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-wide" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <div className="modal-title">{studentName}</div>
            <div className="modal-subtitle" style={{ marginBottom: 0 }}>
              Student Detail View · Agent Attribution &amp; Intervention History
            </div>
          </div>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {!data ? (
          <div style={{ padding: '32px 0', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13 }}>
            No detailed data available for this student yet.
          </div>
        ) : (
          <>
            {/* Agent Snapshot Grid */}
            <div className="agent-snap-grid">
              {AGENT_ORDER.map(agent => {
                const snap = data.agents[agent];
                return (
                  <div
                    key={agent}
                    className="agent-snap-card"
                    style={{ borderColor: snap.flagged ? AGENT_COLORS[agent] : 'var(--color-border)' }}
                  >
                    <div
                      className="agent-snap-header"
                      style={{ background: AGENT_BG[agent], borderBottomColor: snap.flagged ? AGENT_COLORS[agent] : 'var(--color-border)' }}
                    >
                      <span className="agent-snap-name" style={{ color: AGENT_COLORS[agent] }}>{agent}</span>
                      {snap.flagged && <span className="agent-snap-flag">⚠</span>}
                    </div>
                    <div className="agent-snap-body">
                      <div className="agent-snap-status">{snap.status}</div>
                      <div className="agent-snap-metric">{snap.keyMetric}</div>
                      <div className="agent-snap-detail">{snap.detail}</div>
                      <div className="agent-snap-reasoning">{snap.reasoning}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Intervention Timeline */}
            <div className="detail-section-title">Intervention History</div>
            {data.interventions.length === 0 ? (
              <div className="no-interventions">No interventions logged — student is progressing normally.</div>
            ) : (
              <div className="intervention-timeline">
                {data.interventions.map((entry, i) => (
                  <div key={i} className="timeline-item">
                    <div className="timeline-left">
                      <div
                        className={`timeline-dot severity-${entry.severity}`}
                        style={{ background: AGENT_COLORS[entry.agent] }}
                      />
                      {i < data.interventions.length - 1 && <div className="timeline-line" />}
                    </div>
                    <div className="timeline-content">
                      <div className="timeline-meta">
                        <span className="timeline-time">{entry.time}</span>
                        <span
                          className="agent-badge"
                          style={{ background: AGENT_BG[entry.agent], color: AGENT_COLORS[entry.agent] }}
                        >
                          {entry.agent}
                        </span>
                        <span className="timeline-type">{entry.type}</span>
                      </div>
                      <div className="timeline-desc">{entry.description}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Footer Actions */}
            <div className="modal-footer">
              {data.score !== undefined && (
                <span style={{ fontSize: 12, color: 'var(--color-text-muted)', marginRight: 'auto', alignSelf: 'center' }}>
                  Score: <strong style={{ color: 'var(--color-text-dark)' }}>{data.score}</strong>
                </span>
              )}
              <button className="btn-outline" onClick={onClose}>Close</button>
              <button className="btn-primary" onClick={onViewSubmission}>View Submission →</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
