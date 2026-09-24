import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Login from './components/Login';
import ScriptView from './components/ScriptView';
import ChapterNav from './components/ChapterNav';
import CharacterDashboard from './components/CharacterDashboard';
import OutputLibrary from './components/OutputLibrary';
import Tooltip from './components/Tooltip';
import { getStoredTheme, applyTheme } from './theme';
import { api } from './api';

/**
 * The end-user product surface -- genuinely separate from `App.js`, not the
 * same screen with a mode switch. `App.js` is a production-desk tool: it
 * exists to let whoever runs the pipeline correct mistakes (mention/speaker
 * reassignment, merges, voice/reference overrides, job triggers, project
 * creation) and carries the chrome that job requires -- a "Live edit"
 * toggle, a corrections queue, raw job ids, an entity-merge sidebar. None
 * of that is a reader's problem; a reader wants three things: read the
 * chapter, browse who's in it, watch/listen to what's been generated.
 *
 * So this component reuses the same underlying pieces where they're
 * already correct read-only building blocks (`ScriptView`/`ChapterNav`
 * render nothing but plain text when `editMode` is false; `OutputLibrary`
 * was already consumption-only) and switches off the edit affordances
 * where a shared component has them (`CharacterDashboard`'s new
 * `readOnly` prop). It does not reuse `App.js`'s shell, header, or grid --
 * that shell *is* the reviewer identity (stats strip, Live edit checkbox,
 * Corrections button), and copying it here would recreate exactly the
 * "one screen for both" problem this file exists to fix.
 */
export default function Viewer() {
  const [manifest, setManifest] = useState([]);
  const [novelId, setNovelId] = useState(null);
  const [novel, setNovel] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [chapterIdx, setChapterIdx] = useState(0);
  const [focusId, setFocusId] = useState(null);
  const [tip, setTip] = useState({ visible: false, x: 0, y: 0, text: '' });
  const [view, setView] = useState('read'); // 'read' | 'cast' | 'library'
  const [theme, setTheme] = useState(() => getStoredTheme() || 'dark');

  const [authChecked, setAuthChecked] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [authed, setAuthed] = useState(api.hasToken());

  useEffect(() => {
    api
      .authStatus()
      .then((r) => setAuthRequired(!!r.auth_required))
      .catch(() => setAuthRequired(false))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!authChecked || (authRequired && !authed)) return;
    api
      .manifest()
      .then((m) => {
        setManifest(m);
        if (m.length && !m.some((x) => x.id === novelId)) setNovelId(m[0].id);
      })
      .catch((e) => setLoadError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authChecked, authRequired, authed]);

  useEffect(() => {
    if (!novelId) return;
    api
      .novel(novelId)
      .then((payload) => {
        setNovel(payload);
        setLoadError(null);
      })
      .catch((e) => setLoadError(e.message));
  }, [novelId]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      return next;
    });
  }, []);

  const handleSelectNovel = useCallback((id) => {
    setNovelId(id);
    setChapterIdx(0);
    setFocusId(null);
  }, []);

  const onMarkHover = useCallback((e, text) => setTip({ visible: true, x: e.clientX, y: e.clientY, text }), []);
  const onMarkMove = useCallback(
    (e) => setTip((prev) => (prev.visible ? { ...prev, x: e.clientX, y: e.clientY } : prev)),
    []
  );
  const onMarkLeave = useCallback(() => setTip((prev) => ({ ...prev, visible: false })), []);

  const chapter = novel ? novel.chapters[Math.min(chapterIdx, novel.chapters.length - 1)] : null;
  const chapterCoverage = useMemo(() => {
    if (!chapter) return '';
    let total = 0;
    let attributed = 0;
    chapter.spans.forEach((s) => {
      if (s.type === 'DIALOGUE') {
        total++;
        if (s.speaker) attributed++;
      }
    });
    return total ? `${attributed}/${total} lines voiced` : '';
  }, [chapter]);

  if (!authChecked) {
    return <div className="flex min-h-screen items-center justify-center bg-bg font-sans text-muted">Loading…</div>;
  }
  if (authRequired && !authed) {
    return (
      <Login
        title="EchoTales"
        description="Sign in to browse this novel."
        onLoggedIn={() => setAuthed(true)}
      />
    );
  }
  if (loadError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2 bg-bg px-6 text-center font-sans text-text">
        <p>Can&rsquo;t reach the local EchoTales server ({loadError}).</p>
        <p className="text-sm text-muted">
          Start it with: <code className="font-mono">uv run echotales webview-server --source ...</code>
        </p>
      </div>
    );
  }
  if (!manifest.length || !novel) {
    return <div className="flex min-h-screen items-center justify-center bg-bg font-sans text-muted">Loading…</div>;
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text">
      <header className="flex items-center gap-4 border-b border-border bg-surface px-4 py-3">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">EchoTales</span>
          <h1 className="font-display text-xl text-text">
            {(manifest.find((m) => m.id === novelId) || {}).label || novelId}
          </h1>
        </div>
        <select
          value={novelId}
          onChange={(e) => handleSelectNovel(e.target.value)}
          className="h-8 rounded-sm border border-border bg-bg px-2 font-sans text-sm text-text"
        >
          {manifest.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'paper' : 'ink'} theme`}
          className="h-8 rounded-sm border border-border px-3 font-mono text-xs uppercase tracking-wider text-muted hover:border-accent hover:text-accent"
        >
          {theme === 'dark' ? 'Ink' : 'Paper'}
        </button>
        <a
          href="?review"
          className="ml-auto font-mono text-xs uppercase tracking-wider text-muted underline decoration-border underline-offset-4 hover:text-accent hover:decoration-accent"
        >
          Reviewer tools &rarr;
        </a>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <nav className="w-[200px] shrink-0 border-r border-border bg-surface py-2" aria-label="Sections">
          {[
            { key: 'read', label: 'Read' },
            { key: 'cast', label: 'Cast' },
            { key: 'library', label: 'Library' },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              className={`rail-nav-item${view === item.key ? ' active' : ''}`}
              aria-current={view === item.key ? 'page' : undefined}
              onClick={() => setView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="flex-1 overflow-y-auto">
          {view === 'read' && (
            <>
              <ChapterNav
                chapters={novel.chapters}
                chapterIdx={chapterIdx}
                onChange={setChapterIdx}
                coverage={chapterCoverage}
              />
              <ScriptView
                chapter={chapter}
                focusId={focusId}
                onMarkHover={onMarkHover}
                onMarkMove={onMarkMove}
                onMarkLeave={onMarkLeave}
                editMode={false}
              />
            </>
          )}
          {view === 'cast' && <CharacterDashboard novelId={novelId} readOnly />}
          {view === 'library' && <OutputLibrary novelId={novelId} />}
        </main>
      </div>

      <Tooltip tip={tip} />
    </div>
  );
}
