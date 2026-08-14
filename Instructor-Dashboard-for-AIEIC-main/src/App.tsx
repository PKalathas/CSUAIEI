import { useState } from 'react';
import './index.css';
import MaterialPreview from './tabs/MaterialPreview';
import LabQuizPreview from './tabs/LabQuizPreview';
import StudentActivity from './tabs/StudentActivity';
import GradedSubmissions from './tabs/GradedSubmissions';
import Statistics from './tabs/Statistics';
import AgentCollaboration from './tabs/AgentCollaboration';
import UploadMaterialModal from './components/UploadMaterialModal';
import UploadAgentModal from './components/UploadAgentModal';
import StudentDetailModal from './components/StudentDetailModal';
import LoginPage from './components/LoginPage';

type Tab = 'tasks' | 'quiz' | 'activity' | 'grades' | 'stats' | 'agents';

const tabs: { id: Tab; label: string }[] = [
  { id: 'tasks', label: 'Lab Tasks Preview' },
  { id: 'quiz', label: 'Lab Quiz Preview' },
  { id: 'activity', label: 'Student Activity' },
  { id: 'grades', label: 'Graded Submissions' },
  { id: 'stats', label: 'Statistics' },
  { id: 'agents', label: 'AI Overview' },
];

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('tasks');
  const [showUploadMaterial, setShowUploadMaterial] = useState(false);
  const [showUploadAgent, setShowUploadAgent] = useState(false);
  const [selectedStudent, setSelectedStudent] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  function renderContent() {
    switch (activeTab) {
      case 'tasks': return <MaterialPreview />;
      case 'quiz': return <LabQuizPreview />;
      case 'activity': return <StudentActivity onSelectStudent={setSelectedStudent} />;
      case 'grades': return <GradedSubmissions onSelectStudent={setSelectedStudent} />;
      case 'stats': return <Statistics />;
      case 'agents': return <AgentCollaboration />;
    }
  }

  if (!isAuthenticated) {
    return <LoginPage onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <>
    <div className="dashboard">
      {/* Header */}
      <header className="header">
        <button className="sidebar-toggle" onClick={() => setSidebarOpen(o => !o)} title="Toggle sidebar">
          <span className="sidebar-toggle-bar" />
          <span className="sidebar-toggle-bar" />
          <span className="sidebar-toggle-bar" />
        </button>
        <div className="header-left">
          <h1>Instructor Panel</h1>
          <p>CSC 101 — Lab 4: Linked Lists</p>
        </div>
        <div className="status-pill">● Lab in session</div>
      </header>

      {/* Body */}
      <div className="body">
        {/* Left Panel */}
        <aside className={`left-panel${sidebarOpen ? '' : ' left-panel--collapsed'}`}>
          <div className="panel-section-label">Lab Material</div>

          <div className="uploaded-file">
            <div className="file-name">Lab4_specification.pdf</div>
            <div className="file-meta">Uploaded · 2.3 MB</div>
          </div>

          <button className="panel-btn panel-btn-ghost" onClick={() => setShowUploadMaterial(true)}>Upload Material</button>
          <button className="panel-btn panel-btn-ghost" onClick={() => setShowUploadAgent(true)}>Customize Tutor Behavior</button>
        </aside>

        {/* Main */}
        <main className="main">
          {/* Tab Bar */}
          <div className="tab-bar">
            {tabs.map(tab => (
              <button
                key={tab.id}
                className={`tab-btn${activeTab === tab.id ? ' active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="content-scroll">
            {renderContent()}
          </div>
        </main>
      </div>
    </div>

    {showUploadMaterial && <UploadMaterialModal onClose={() => setShowUploadMaterial(false)} />}
    {showUploadAgent && <UploadAgentModal onClose={() => setShowUploadAgent(false)} />}
    {selectedStudent && (
      <StudentDetailModal
        studentName={selectedStudent}
        onClose={() => setSelectedStudent(null)}
        onViewSubmission={() => { setSelectedStudent(null); setActiveTab('grades'); }}
      />
    )}
    </>
  );
}
