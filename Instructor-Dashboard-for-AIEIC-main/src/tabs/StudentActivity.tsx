type StudentStatus = 'needs-help' | 'flagged' | 'on-track' | 'low';

interface Student {
  name: string;
  prompts: number;
  detail: string;
  status: StudentStatus;
}

interface Props {
  onSelectStudent: (name: string) => void;
}

const students: Student[] = [
  { name: 'Carlos R', prompts: 31, detail: 'Last: "Just give me the full insert function" · Top topic: Everything', status: 'needs-help' },
  { name: 'Ethan L', prompts: 22, detail: 'Last: "I still don\'t get pointer swap" · Reached hint level 3, still stuck', status: 'needs-help' },
  { name: 'Nina Q', prompts: 28, detail: '28 prompts · 87% prompt similarity with Carlos R · Possible collaboration flag', status: 'flagged' },
  { name: 'Alex M', prompts: 12, detail: 'Last: "How do I insert at position 3?" · Top topic: Insertion', status: 'on-track' },
  { name: 'Bella K', prompts: 9, detail: 'Last: "Should I use a dummy head node?" · Top topic: Design', status: 'on-track' },
  { name: 'Dana W', prompts: 15, detail: 'Last: "Why does delete fail for head?" · Top topic: Deletion', status: 'on-track' },
  { name: 'Fiona S', prompts: 10, detail: 'Last: "Do I need to free this node?" · Top topic: Memory', status: 'on-track' },
  { name: 'Jake N', prompts: 20, detail: 'Last: "Hint 3 didn\'t help, still stuck" · On track per hint pace', status: 'on-track' },
  { name: 'George T', prompts: 2, detail: 'Last: "How do I compile?" · Low activity, monitor', status: 'low' },
];

const statusMeta: Record<StudentStatus, { label: string; labelClass: string; accentClass: string }> = {
  'needs-help': { label: 'Needs Help', labelClass: 'status-label-needs-help', accentClass: 'accent-needs-help' },
  'flagged': { label: 'Flagged', labelClass: 'status-label-flagged', accentClass: 'accent-flagged' },
  'on-track': { label: 'On Track', labelClass: 'status-label-on-track', accentClass: 'accent-on-track' },
  'low': { label: 'Low Activity', labelClass: 'status-label-low', accentClass: 'accent-low' },
};

const groups: StudentStatus[] = ['needs-help', 'flagged', 'on-track', 'low'];

export default function StudentActivity({ onSelectStudent }: Props) {
  return (
    <div className="content-card">
      <div className="content-header">
        <div className="content-title">
          <h2>Live Student Activity</h2>
          <p>35 students enrolled · Lab in session</p>
        </div>
      </div>
      <hr className="content-divider" />

      {groups.map(status => {
        const group = students.filter(s => s.status === status);
        if (group.length === 0) return null;
        const meta = statusMeta[status];
        return (
          <div key={status} style={{ marginBottom: 20 }}>
            <div className={`status-group-label ${meta.labelClass}`}>
              {meta.label} ({group.length})
            </div>
            <div className="students-grid">
              {group.map(student => (
                <div
                  key={student.name}
                  className="student-card student-card-clickable"
                  onClick={() => onSelectStudent(student.name)}
                >
                  <div className={`student-card-accent ${meta.accentClass}`} />
                  <div className="student-card-body">
                    <div className="student-name">{student.name}</div>
                    <div className="student-detail">{student.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
