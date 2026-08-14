import { useState } from 'react';

interface Props {
  onLogin: () => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onLogin();
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-brand-logo">AI</div>
          <div>
            <div className="login-brand-title">AIEIC Instructor Panel</div>
            <div className="login-brand-sub">AI-Enhanced Instructional Co-pilot</div>
          </div>
        </div>

        <div className="modal-tab-switch" style={{ marginBottom: 24 }}>
          <button
            className={`modal-tab${mode === 'signin' ? ' modal-tab-active' : ''}`}
            onClick={() => setMode('signin')}
          >
            Sign In
          </button>
          <button
            className={`modal-tab${mode === 'signup' ? ' modal-tab-active' : ''}`}
            onClick={() => setMode('signup')}
          >
            Sign Up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          {mode === 'signup' && (
            <div className="login-field">
              <label className="login-label">Full Name</label>
              <input
                className="login-input"
                type="text"
                placeholder="e.g. Prof. Kurfess"
                value={name}
                onChange={e => setName(e.target.value)}
                required
              />
            </div>
          )}

          <div className="login-field">
            <label className="login-label">Email</label>
            <input
              className="login-input"
              type="email"
              placeholder="instructor@university.edu"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="login-field">
            <label className="login-label">Password</label>
            <input
              className="login-input"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn-primary login-submit">
            {mode === 'signin' ? 'Sign In' : 'Create Account'}
          </button>
        </form>

        {mode === 'signin' && (
          <p className="login-footer">
            Don't have an account?{' '}
            <button className="login-link" onClick={() => setMode('signup')}>Sign up</button>
          </p>
        )}
        {mode === 'signup' && (
          <p className="login-footer">
            Already have an account?{' '}
            <button className="login-link" onClick={() => setMode('signin')}>Sign in</button>
          </p>
        )}
      </div>
    </div>
  );
}
