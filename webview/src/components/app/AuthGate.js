import React, { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { api, UNAUTHORIZED_EVENT } from '../../api';
import Login from '../Login';
import { describeError } from '../../lib/errors';
import { CenterMessage } from './Chrome';

/**
 * Guards every app route (dashboard and project workspace); the landing
 * page stays public. `checked` separates "status not known yet" from "known
 * open" so the login screen never flashes for a frame while the request is
 * in flight -- the same reason the old App.js carried an `authChecked` flag.
 * An unreachable server is reported as such, not as a login failure.
 */
export default function AuthGate() {
  const [checked, setChecked] = useState(false);
  const [required, setRequired] = useState(false);
  const [unreachable, setUnreachable] = useState(null);
  const [authed, setAuthed] = useState(api.hasToken());

  useEffect(() => {
    api
      .authStatus()
      .then((r) => {
        setRequired(!!r.auth_required);
        setUnreachable(null);
      })
      .catch((e) => setUnreachable(describeError(e, 'The server did not respond as expected.')))
      .finally(() => setChecked(true));
  }, []);

  // A 401 mid-session (expired token) returns to the sign-in screen.
  useEffect(() => {
    const onUnauthorized = () => setAuthed(false);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  if (!checked) return <main><CenterMessage>Connecting to the EchoTales server…</CenterMessage></main>;
  if (unreachable) {
    return (
      <main>
      <CenterMessage title="Can’t reach the EchoTales server">
        <p>{unreachable}</p>
        <p className="mt-2">
          Start it with <code className="rounded bg-surface2 px-1.5 py-0.5 font-mono text-xs">uv run echotales webview-server --source …</code> and reload.
        </p>
      </CenterMessage>
      </main>
    );
  }
  if (required && !authed) {
    return <Login title="Sign in to EchoTales" description="Your projects are on this server." onLoggedIn={() => setAuthed(true)} />;
  }
  return <Outlet />;
}
