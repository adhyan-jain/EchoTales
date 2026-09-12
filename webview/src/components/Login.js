import { useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';

// Section 7.2: gate the whole review UI behind a password when the server
// reports auth_required: true (see api.js::authStatus). This component only
// knows how to log in -- whether to show it at all, and what to render once
// onLoggedIn fires, is the integrating App.js's call.
//
// Deliberately the one screen with no design investment beyond correct
// tokens (per brief): this is a single shared server password, not a
// per-user account system, so there's nothing here to dress up -- a name,
// a field, a button.
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
    // [grid-column:1/-1] [grid-row:1/-1]: #root is a 2-column CSS grid
    // (index.css); without spanning both tracks explicitly this div is
    // auto-placed into the 300px sidebar column and pins the card to the
    // top-left instead of centering it in the viewport.
    <div className="flex min-h-screen w-full items-center justify-center bg-bg font-sans [grid-column:1/-1] [grid-row:1/-1]">
      <form
        className="w-full max-w-[320px] space-y-4 border border-border bg-surface p-8 rounded-sm"
        onSubmit={handleSubmit}
      >
        <div>
          <h1 className="font-display text-xl text-text">EchoTales Review</h1>
          <p className="mt-1 text-sm text-muted">This review tool is password-protected.</p>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="login-password" className="block text-sm text-muted">
            Password
          </label>
          <Input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            autoComplete="current-password"
          />
        </div>

        {error && (
          <div className="rounded-sm border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}

        <Button type="submit" disabled={busy || !password} className="w-full">
          {busy ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </div>
  );
}
