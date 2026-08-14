type SubmissionStatus = 'Graded' | 'Flagged ⚠' | 'Needs Review';

interface Submission {
  student: string;
  score: number;
  status: SubmissionStatus;
  feedback: string;
}

const submissions: Submission[] = [
  { student: 'Alex M', score: 92, status: 'Graded', feedback: 'Well-structured logic. Minor edge case missed on traversal.' },
  { student: 'Bella K', score: 88, status: 'Graded', feedback: 'Good pointer management. Review head-node deletion.' },
  { student: 'Carlos R', score: 45, status: 'Flagged ⚠', feedback: '87% similarity + excessive AI usage. Pending review.' },
  { student: 'Dana W', score: 85, status: 'Graded', feedback: 'Solid work. Deletion edge case handled correctly.' },
  { student: 'Ethan L', score: 62, status: 'Graded', feedback: 'Task 1 complete. Task 2 incomplete — pointer logic missing.' },
  { student: 'Fiona S', score: 79, status: 'Graded', feedback: 'Memory management correct. Minor style issues.' },
  { student: 'Jake N', score: 71, status: 'Needs Review', feedback: 'Partial completion. Needs manual review for task 3.' },
  { student: 'Nina Q', score: 48, status: 'Flagged ⚠', feedback: '87% similarity with Carlos R. Pending review.' },
];

function statusBadge(status: SubmissionStatus) {
  if (status === 'Graded') return <span className="badge badge-graded">Graded</span>;
  if (status === 'Flagged ⚠') return <span className="badge badge-flagged">Flagged ⚠</span>;
  return <span className="badge badge-review">Needs Review</span>;
}

export default function GradedSubmissions({ onSelectStudent }: { onSelectStudent: (name: string) => void }) {
  return (
    <div className="content-card">
      <div className="content-header">
        <div className="content-title">
          <h2>Graded Submissions — Lab 4</h2>
          <p>35 submissions · 30 auto-graded · 3 pending review</p>
        </div>
        <div className="content-actions">
          <button className="btn-outline">Download All (CSV)</button>
          <button className="btn-primary">Grade Submissions</button>
        </div>
      </div>
      <hr className="content-divider" />

      <table className="submissions-table">
        <thead>
          <tr>
            <th>Student</th>
            <th>Score</th>
            <th>Status</th>
            <th>AI Feedback</th>
            <th style={{ textAlign: 'right' }}>Download</th>
          </tr>
        </thead>
        <tbody>
          {submissions.map(row => (
            <tr key={row.student} className="submission-row-clickable" onClick={() => onSelectStudent(row.student)}>
              <td style={{ fontWeight: 500 }}>{row.student}</td>
              <td style={{ fontWeight: 600 }}>{row.score}</td>
              <td>{statusBadge(row.status)}</td>
              <td style={{ color: 'var(--color-text-muted)', fontSize: 12 }}>{row.feedback}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="download-link">Download</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
