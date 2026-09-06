import { useState } from 'react';
import { api } from '../api';

// Section 7.2: gate the whole review UI behind a password when the server
// reports auth_required: true (see api.js::authStatus). This component only
// knows how to log in -- whether to show it at all, and what to render once
// onLoggedIn fires, is the integrating App.js's call.
export default function Login({ onLoggedIn }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await api.login(password);
      onLoggedIn();
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>EchoTales Review</h1>
        <p className="login-explainer">This review tool is password-protected.</p>
        <label htmlFor="login-password">Password</label>
        <input
          id="login-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          autoComplete="current-password"
        />
        {error && <div className="login-error">{error}</div>}
        <button type="submit" className="btn-primary" disabled={busy || !password}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
