import type { AgentName } from '../api/agents';

interface AgentCard {
  name: AgentName;
  description: string;
  color: string;
  bg: string;
  primaryMetric: { value: number | string; label: string };
  secondaryMetric: { value: number | string; label: string };
  currentFocus: string;
}

const AGENTS: AgentCard[] = [
  {
    name: 'Lab Companion',
    description: 'Answers student questions with progressive hints. Blocks requests for direct answers.',
    color: 'var(--color-primary)',
    bg: 'var(--bg-blue-light)',
    primaryMetric: { value: 87, label: 'hints given' },
    secondaryMetric: { value: 14, label: 'direct answers blocked' },
    currentFocus: 'Carlos R reached hint limit · Ethan L stuck at hint 3',
  },
  {
    name: 'Participant',
    description: 'Tracks each student\'s prompts and pacing so the AI can tailor its responses.',
    color: 'var(--color-on-track)',
    bg: 'var(--bg-green-light)',
    primaryMetric: { value: 35, label: 'students tracked' },
    secondaryMetric: { value: 2, label: 'pacing alerts' },
    currentFocus: 'Carlos R 28 min behind · George T very low activity',
  },
  {
    name: 'Integrity',
    description: 'Enforces AI usage policies, detects similarity between submissions, and escalates violations.',
    color: 'var(--color-flagged)',
    bg: '#fdf0e4',
    primaryMetric: { value: 2, label: 'flags raised' },
    secondaryMetric: { value: 3, label: 'sessions escalated' },
    currentFocus: 'Carlos R + Nina Q flagged — 87% prompt similarity',
  },
  {
    name: 'Curriculum Designer',
    description: 'Generates lab materials and tracks class-wide misconceptions to improve future content.',
    color: 'var(--color-curriculum)',
    bg: 'var(--bg-purple-light)',
    primaryMetric: { value: 4, label: 'misconceptions noted' },
    secondaryMetric: { value: 2, label: 'recommendations queued' },
    currentFocus: 'Pointer semantics gap across 3 students · Lab 5 prep flagged',
  },
];

interface FeedEvent {
  time: string;
  agent: AgentName;
  studentName?: string;
  action: string;
  detail?: string;
  requiresAction: boolean;
  severity: 'info' | 'warning' | 'critical';
}

const FEED_EVENTS: FeedEvent[] = [
  {
    time: '2:47 PM', agent: 'Integrity', studentName: 'Carlos R & Nina Q',
    action: 'Similarity flag raised — 87% prompt match between Carlos R and Nina Q',
    detail: 'Requires instructor review before final grades are released.',
    requiresAction: true, severity: 'critical',
  },
  {
    time: '2:31 PM', agent: 'Lab Companion', studentName: 'Carlos R',
    action: 'Hint limit reached — all 5 scaffolded hints exhausted',
    detail: 'Student has not progressed. Consider a direct check-in.',
    requiresAction: true, severity: 'warning',
  },
  {
    time: '2:15 PM', agent: 'Participant', studentName: 'Carlos R',
    action: 'Pacing alert — 28 minutes behind expected lab completion time',
    requiresAction: false, severity: 'warning',
  },
  {
    time: '2:10 PM', agent: 'Lab Companion', studentName: 'Alex M',
    action: 'Student unblocked after hint 2 — progressing normally',
    requiresAction: false, severity: 'info',
  },
  {
    time: '2:05 PM', agent: 'Curriculum Designer', studentName: 'Ethan L',
    action: 'Misconception logged — pointer swap (temp variable pattern)',
    detail: 'Added to Lab 5 curriculum review queue.',
    requiresAction: false, severity: 'info',
  },
  {
    time: '1:58 PM', agent: 'Lab Companion', studentName: 'Carlos R',
    action: 'Direct answer request blocked — "Just give me the full insert function"',
    requiresAction: false, severity: 'warning',
  },
  {
    time: '1:55 PM', agent: 'Curriculum Designer', studentName: 'Nina Q',
    action: 'Misconception logged — insertion pointer off-by-one error',
    requiresAction: false, severity: 'info',
  },
  {
    time: '1:42 PM', agent: 'Curriculum Designer', studentName: 'Carlos R',
    action: 'Misconception logged — pointer vs. value semantics confusion',
    requiresAction: false, severity: 'info',
  },
  {
    time: '1:30 PM', agent: 'Participant', studentName: 'George T',
    action: 'Low activity alert — 2 prompts in 30 minutes, no task progress',
    detail: 'Student may need environment help or a direct check-in.',
    requiresAction: true, severity: 'warning',
  },
];

const AGENT_COLORS: Record<AgentName, string> = {
  'Lab Companion': 'var(--color-primary)',
  'Participant': 'var(--color-on-track)',
  'Integrity': 'var(--color-flagged)',
  'Curriculum Designer': 'var(--color-curriculum)',
};

const AGENT_BG: Record<AgentName, string> = {
  'Lab Companion': 'var(--bg-blue-light)',
  'Participant': 'var(--bg-green-light)',
  'Integrity': '#fdf0e4',
  'Curriculum Designer': 'var(--bg-purple-light)',
};

const needsAction = FEED_EVENTS.filter(e => e.requiresAction).length;

export default function AgentCollaboration() {
  return (
    <div className="content-card">
      <div className="content-header">
        <div className="content-title">
          <h2>AI Overview</h2>
          <p>4 AI agents active · {needsAction} items need your attention</p>
        </div>
      </div>
      <hr className="content-divider" />

      {/* Agent Status Cards */}
      <div className="agent-status-grid">
        {AGENTS.map(agent => (
          <div key={agent.name} className="agent-status-card" style={{ borderTopColor: AGENT_COLORS[agent.name] }}>
            <div className="agent-status-card-header">
              <span className="agent-status-name" style={{ color: AGENT_COLORS[agent.name] }}>{agent.name}</span>
              <span className="agent-status-active-dot" style={{ background: AGENT_COLORS[agent.name] }} />
            </div>
            <div className="agent-status-role">{agent.description}</div>
            <div className="agent-status-metrics">
              <div className="agent-metric">
                <span className="agent-metric-value" style={{ color: agent.name === 'Integrity' && Number(agent.primaryMetric.value) > 0 ? 'var(--color-needs-help)' : 'inherit' }}>
                  {agent.primaryMetric.value}
                </span>
                <span className="agent-metric-label">{agent.primaryMetric.label}</span>
              </div>
              <div className="agent-metric">
                <span className="agent-metric-value">{agent.secondaryMetric.value}</span>
                <span className="agent-metric-label">{agent.secondaryMetric.label}</span>
              </div>
            </div>
            <div className="agent-status-focus">{agent.currentFocus}</div>
          </div>
        ))}
      </div>

      {/* Activity Feed */}
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 28, marginBottom: 16 }}>
        <div className="detail-section-title" style={{ margin: 0 }}>Activity Log</div>
        {needsAction > 0 && (
          <span style={{ fontSize: 11, color: 'var(--color-needs-help)', fontWeight: 600 }}>
            {needsAction} item{needsAction > 1 ? 's' : ''} need your attention
          </span>
        )}
      </div>
      <div className="collab-feed">
        {FEED_EVENTS.map((event, i) => (
          <div key={i} className={`feed-item feed-item--${event.severity}`}>
            <div className="feed-item-left">
              <div className="feed-time">{event.time}</div>
            </div>
            <div className="feed-item-body">
              <div className="feed-item-agents">
                <span className="agent-badge" style={{ background: AGENT_BG[event.agent], color: AGENT_COLORS[event.agent] }}>
                  {event.agent}
                </span>
                {event.studentName && (
                  <span className="feed-student-name">{event.studentName}</span>
                )}
                {event.requiresAction && (
                  <span className="feed-action-required">Needs review</span>
                )}
              </div>
              <div className="feed-desc">{event.action}</div>
              {event.detail && <div className="feed-detail">{event.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
