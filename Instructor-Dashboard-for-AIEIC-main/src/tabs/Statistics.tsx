const gradeDistribution = [
  { label: '90–100 (A)', count: 8, maxCount: 35 },
  { label: '80–89 (B)', count: 12, maxCount: 35 },
  { label: '70–79 (C)', count: 9, maxCount: 35 },
  { label: '60–69 (D)', count: 4, maxCount: 35 },
  { label: 'Below 60', count: 2, maxCount: 35 },
];

const aiStats = [
  { label: 'Total prompts', value: '195' },
  { label: 'Avg per student', value: '16.3' },
  { label: 'Progressive hints given', value: '87' },
  { label: 'Direct answers blocked', value: '14' },
  { label: 'Escalations to instructor', value: '3' },
  { label: 'Avg completion time', value: '47 min' },
];

const perStudent = [
  { name: 'Alex M', score: 92, prompts: 12, hints: 4, status: 'On Track' },
  { name: 'Bella K', score: 88, prompts: 9, hints: 3, status: 'On Track' },
  { name: 'Carlos R', score: 45, prompts: 31, hints: 9, status: 'Flagged' },
  { name: 'Dana W', score: 85, prompts: 15, hints: 5, status: 'On Track' },
  { name: 'Ethan L', score: 62, prompts: 22, hints: 8, status: 'Needs Help' },
  { name: 'Fiona S', score: 79, prompts: 10, hints: 5, status: 'On Track' },
  { name: 'Jake N', score: 71, prompts: 20, hints: 7, status: 'On Track' },
  { name: 'Nina Q', score: 48, prompts: 28, hints: 7, status: 'Flagged' },
];

function statusColor(status: string) {
  if (status === 'On Track') return 'var(--color-on-track)';
  if (status === 'Needs Help') return 'var(--color-needs-help)';
  if (status === 'Flagged') return 'var(--color-flagged)';
  return 'var(--color-text-muted)';
}

export default function Statistics() {
  return (
    <div className="content-card">
      <div className="content-header">
        <div className="content-title">
          <h2>Lab 4 Statistics</h2>
          <p>Full overview — grading, AI assistance, per-student breakdown</p>
        </div>
      </div>
      <hr className="content-divider" />

      {/* Summary cards */}
      <div className="stats-cards">
        <div className="stat-card">
          <div className="stat-card-label">Class Average</div>
          <div className="stat-card-value">78.4%</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Submissions</div>
          <div className="stat-card-value">35 / 35</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Auto-graded</div>
          <div className="stat-card-value">30</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Needs Review</div>
          <div className="stat-card-value">3</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">Flagged</div>
          <div className="stat-card-value">2</div>
        </div>
      </div>

      <div className="stats-columns">
        {/* Left column */}
        <div>
          <div className="stats-section-title">Grade Distribution</div>
          {gradeDistribution.map(row => (
            <div key={row.label} className="grade-bar-row">
              <div className="grade-bar-label">{row.label}</div>
              <div className="grade-bar-track">
                <div
                  className="grade-bar-fill"
                  style={{ width: `${(row.count / row.maxCount) * 100}%` }}
                />
              </div>
              <div className="grade-bar-count">{row.count}</div>
            </div>
          ))}

          <div className="stats-section-title" style={{ marginTop: 28 }}>AI Assistance</div>
          {aiStats.map(row => (
            <div key={row.label} className="ai-stat-row">
              <span style={{ color: 'var(--color-text-dark)' }}>{row.label}</span>
              <span className="ai-stat-value">{row.value}</span>
            </div>
          ))}
        </div>

        {/* Right column */}
        <div>
          <div className="stats-section-title">Per-Student Breakdown</div>
          <table className="ps-table">
            <thead>
              <tr>
                <th>Student</th>
                <th>Score</th>
                <th>Prompts</th>
                <th>Hints</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {perStudent.map(row => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td style={{ fontWeight: 600 }}>{row.score}</td>
                  <td>{row.prompts}</td>
                  <td>{row.hints}</td>
                  <td style={{ color: statusColor(row.status), fontWeight: 500, fontSize: 12 }}>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
