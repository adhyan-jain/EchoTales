import React, { useState, useEffect, useCallback, useMemo } from 'react';
import EntitySidebar from './components/EntitySidebar';
import ChapterNav from './components/ChapterNav';
import ScriptView from './components/ScriptView';
import Tooltip from './components/Tooltip';
import AnalysisPanel from './components/AnalysisPanel';
import EntityPicker from './components/EntityPicker';
import Login from './components/Login';
import NewProject from './components/NewProject';
import CharacterDashboard from './components/CharacterDashboard';
import GenerationWorkspace from './components/GenerationWorkspace';
import OutputLibrary from './components/OutputLibrary';
import ProjectHome from './components/ProjectHome';
import TimelineRail from './components/ui/TimelineRail';
import Label from './components/ui/Label';
import InspectorSection from './components/ui/InspectorSection';
import { getStoredTheme, applyTheme } from './theme';
import { api } from './api';

// Left-rail navigation. Every item is always shown (never hidden for being
// "not implemented yet") -- each screen is responsible for its own honest
// empty/error state when the data it needs isn't there, the same pattern
// CharacterDashboard already uses for a 404/500 from the live backend.
const NAV_ITEMS = [
  { key: 'script', label: 'Script' },
  { key: 'characters', label: 'Characters' },
  { key: 'state', label: 'State' },
  { key: 'generation', label: 'Generation' },
  { key: 'outputs', label: 'Outputs' },
  { key: 'project', label: 'Project' },
];

const DATA_BASE = process.env.PUBLIC_URL + '/data';

function pct(x) {
  return Math.round(x * 100) + '%';
}

/**
 * EchoTales coref/attribution viewer.
 *
 * Two data modes, one component tree:
 *
 * - **Static** (default): fetches the pre-built JSON export, same as the
 *   dependency-free HTML build in packages/pipeline/.../webview.py. Read-only.
 * - **Live edit**: fetches from `webview_server.py` instead, which serves the
 *   same shape of payload but overlays any pending corrections and accepts
 *   new ones. Requires `uv run echotales webview-server` running separately --
 *   this component degrades to a clear error if it isn't.
 *
 * A correction is never fed back into the resolver as input (HANDOFF Section 6 rules
 * that out explicitly -- a resolver graded against its own answer key isn't
 * measuring anything). What a correction *does*: (1) redirects this payload's
 * display immediately, so the fix is visible before anything is "applied";
 * (2) optionally patches the live SQLite store's mention bindings, which is a
 * one-time fix to this run's output, not a change to how future runs decide.
 */
export default function App() {
  const [editMode, setEditMode] = useState(false);
  const [manifest, setManifest] = useState([]);
  const [novels, setNovels] = useState({}); // id -> payload, refetched whenever stale
  const [novelId, setNovelId] = useState(null);
  const [chapterIdx, setChapterIdx] = useState(0);
  const [focusId, setFocusId] = useState(null);
  const [search, setSearch] = useState('');
  const [tip, setTip] = useState({ visible: false, x: 0, y: 0, text: '' });
  const [loadError, setLoadError] = useState(null);
  const [mergeSourceId, setMergeSourceId] = useState(null);
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [correctionsSummary, setCorrectionsSummary] = useState({
    total: 0, applied: 0, pending: 0, pending_actionable: 0, flags_open: 0, by_type: {},
  });
  const [applyResult, setApplyResult] = useState(null);
  const [applying, setApplying] = useState(false);
  // { kind: 'mention'|'speaker', anchor: {x,y}, mentionId? | spanId?+chapter }
  const [picker, setPicker] = useState(null);

  // Section 7.2: auth gate + view switcher. `authChecked` distinguishes "we
  // don't know yet" from "known open" so the app doesn't flash the login
  // screen for a frame while the status request is in flight. Auth only
  // ever applies in live-edit mode -- the static build has no server to
  // authenticate against at all.
  const [authChecked, setAuthChecked] = useState(false);
  const [authRequired, setAuthRequired] = useState(false);
  const [authed, setAuthed] = useState(api.hasToken());
  // 'script' | 'characters' | 'state' | 'generation' | 'outputs' | 'project' | 'new-project'
  const [view, setView] = useState('script');
  const [theme, setTheme] = useState(() => getStoredTheme() || 'dark');

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!editMode) {
      setAuthChecked(true);
      return;
    }
    api
      .authStatus()
      .then((r) => setAuthRequired(!!r.auth_required))
      .catch(() => setAuthRequired(false))
      .finally(() => setAuthChecked(true));
  }, [editMode]);

  // Manifest: static file, or the backend's live list. Held off in edit
  // mode until the login gate (if any) clears, so a 401 from an unauthed
  // request never masquerades as "can't reach the edit backend."
  useEffect(() => {
    if (editMode && (!authChecked || (authRequired && !authed))) return;
    setLoadError(null);
    const load = editMode
      ? api.manifest()
      : fetch(`${DATA_BASE}/manifest.json`).then((r) => {
          if (!r.ok) throw new Error(`manifest.json: HTTP ${r.status}`);
          return r.json();
        });
    load
      .then((m) => {
        setManifest(m);
        if (m.length && !m.some((x) => x.id === novelId)) setNovelId(m[0].id);
      })
      .catch((e) =>
        setLoadError(
          editMode
            ? `Can't reach the edit backend (${e.message}). Start it with: ` +
              `uv run echotales webview-server --source ...`
            : e.message
        )
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editMode, authChecked, authRequired, authed]);

  const refetchNovel = useCallback(
    (id) => {
      if (!id) return;
      const load = editMode
        ? api.novel(id)
        : fetch(`${DATA_BASE}/${id}.json`).then((r) => {
            if (!r.ok) throw new Error(`${id}.json: HTTP ${r.status}`);
            return r.json();
          });
      load
        .then((payload) => {
          setNovels((prev) => ({ ...prev, [id]: payload }));
          // A stale `novelId` from before a mode switch can 404 briefly
          // (the manifest hasn't swapped `novelId` to a valid one yet) --
          // once *any* fetch since succeeds, that transient error is over.
          setLoadError(null);
        })
        .catch((e) => setLoadError(e.message));
    },
    [editMode]
  );

  useEffect(() => {
    if (!novelId) return;
    refetchNovel(novelId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [novelId, editMode]);

  const refreshCorrections = useCallback(() => {
    if (!editMode || !novelId) return;
    api.corrections(novelId).then((r) => setCorrectionsSummary(r.summary)).catch(() => {});
  }, [editMode, novelId]);

  useEffect(() => {
    refreshCorrections();
  }, [refreshCorrections]);

  const novel = novels[novelId];

  // A live-edit manifest refresh (`refetchNovel`) can report fewer chapters
  // than before for the currently-selected novel -- e.g. a re-ingest/resolve
  // rerun rebuilding the chapter table -- without going through
  // `handleSelectNovel`'s reset. Left unclamped, `novel.chapters[chapterIdx]`
  // silently returns `undefined` and crashed ScriptView with "Cannot read
  // properties of undefined (reading 'spans')".
  useEffect(() => {
    if (!novel) return;
    if (chapterIdx >= novel.chapters.length) {
      setChapterIdx(Math.max(0, novel.chapters.length - 1));
    }
  }, [novel, chapterIdx]);

  const handleSelectNovel = useCallback((id) => {
    setNovelId(id);
    setChapterIdx(0);
    setFocusId(null);
    setSearch('');
    setMergeSourceId(null);
    setApplyResult(null);
  }, []);

  const handleToggleFocus = useCallback((entId) => {
    setFocusId((prev) => (prev === entId ? null : entId));
  }, []);

  const handleStartMerge = useCallback((entId) => setMergeSourceId(entId), []);
  const handleCancelMerge = useCallback(() => setMergeSourceId(null), []);
  const handleConfirmMerge = useCallback(
    (targetId) => {
      if (!novelId || !mergeSourceId) return;
      api
        .mergeEntities(novelId, mergeSourceId, targetId)
        .then(() => {
          setMergeSourceId(null);
          refetchNovel(novelId);
          refreshCorrections();
        })
        .catch((e) => setLoadError(e.message));
    },
    [novelId, mergeSourceId, refetchNovel, refreshCorrections]
  );

  const handleApply = useCallback(() => {
    if (!novelId) return;
    setApplying(true);
    api
      .applyCorrections(novelId)
      .then((result) => {
        setApplyResult(result);
        refetchNovel(novelId);
        refreshCorrections();
      })
      .catch((e) => setLoadError(e.message))
      .finally(() => setApplying(false));
  }, [novelId, refetchNovel, refreshCorrections]);

  // -- mention / speaker / flag / merge-lines -----------------------------

  const handleMentionClick = useCallback((mark, e) => {
    setPicker({
      kind: 'mention',
      mentionId: mark.mention_id,
      currentLabel: mark.label,
      anchor: { x: e.clientX, y: e.clientY },
    });
  }, []);

  const handleSpeakerClick = useCallback((span, e, chapterNumber) => {
    // `chapterNumber` comes from `ScriptView`, which is already rendering
    // that exact chapter -- deriving it here instead from `novel`/`chapterIdx`
    // state risks a stale closure (this callback's memoised deps not
    // including `novel` means it can keep referencing an old, possibly
    // `undefined`, snapshot from before the first fetch completed).
    setPicker({
      kind: 'speaker',
      spanId: span.span_id,
      chapter: chapterNumber,
      currentLabel: span.speaker,
      anchor: { x: e.clientX, y: e.clientY },
    });
  }, []);

  const closePicker = useCallback(() => setPicker(null), []);

  const afterCorrection = useCallback(() => {
    setPicker(null);
    refetchNovel(novelId);
    refreshCorrections();
  }, [novelId, refetchNovel, refreshCorrections]);

  const handlePickerSelect = useCallback(
    (entityId) => {
      if (!picker || !novelId) return;
      const call =
        picker.kind === 'create_mention'
          ? api.createMention(
              novelId,
              picker.spanId,
              picker.chapter,
              picker.localStart,
              picker.localEnd,
              picker.text,
              entityId
            )
          : picker.kind === 'mention'
          ? api.reassignMention(novelId, picker.mentionId, entityId)
          : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, entityId);
      call.then(afterCorrection).catch((e) => setLoadError(e.message));
    },
    [picker, novelId, afterCorrection]
  );

  const handlePickerCreate = useCallback(
    (label) => {
      if (!picker || !novelId) return;
      const target = { new_label: label };
      const call =
        picker.kind === 'create_mention'
          ? api.createMention(
              novelId,
              picker.spanId,
              picker.chapter,
              picker.localStart,
              picker.localEnd,
              picker.text,
              target
            )
          : picker.kind === 'mention'
          ? api.reassignMention(novelId, picker.mentionId, target)
          : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, target);
      call.then(afterCorrection).catch((e) => setLoadError(e.message));
    },
    [picker, novelId, afterCorrection]
  );

  const handleCreateMentionPrompt = useCallback(
    (span, e, chapterNumber) => {
      const selectedText = window.getSelection() ? window.getSelection().toString().trim() : '';
      const textToUse = selectedText || window.prompt('Enter mention text from this line:');
      if (!textToUse) return;

      const localStart = span.text.indexOf(textToUse);
      if (localStart === -1) {
        window.alert(`Text "${textToUse}" not found in line.`);
        return;
      }
      if (span.text.indexOf(textToUse, localStart + 1) !== -1) {
        window.alert(
          `"${textToUse}" appears more than once in this line -- please select the exact text instead of typing it, so the correct occurrence can be located.`
        );
        return;
      }
      const start = localStart;
      const end = start + textToUse.length;

      setPicker({
        kind: 'create_mention',
        spanId: span.span_id,
        chapter: chapterNumber,
        localStart: start,
        localEnd: end,
        text: textToUse,
        anchor: { x: e.clientX, y: e.clientY },
      });
    },
    []
  );

  const handlePickerClear = useCallback(() => {
    if (!picker || !novelId || picker.kind === 'create_mention') return;
    const call =
      picker.kind === 'mention'
        ? api.reassignMention(novelId, picker.mentionId, null)
        : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, null);
    call.then(afterCorrection).catch((e) => setLoadError(e.message));
  }, [picker, novelId, afterCorrection]);

  // Speaker-only: put a line into a numbered "Unknown Speaker N" voice slot
  // instead of a real character -- including putting it back after an
  // accidental clear-to-unattributed, which was previously a dead end.
  const handlePickerAnonSlot = useCallback(
    (slot) => {
      if (!picker || !novelId || picker.kind !== 'speaker') return;
      api
        .reassignSpeaker(novelId, picker.spanId, picker.chapter, { anon_slot: slot })
        .then(afterCorrection)
        .catch((e) => setLoadError(e.message));
    },
    [picker, novelId, afterCorrection]
  );

  const handleFlagLine = useCallback(
    (span, chapterNumber) => {
      if (!novelId) return;
      const note = window.prompt('Note for this flag (what looks wrong?)');
      if (note === null) return; // cancelled
      api
        .flag(novelId, {
          spanId: span.span_id,
          chapter: chapterNumber,
          note,
          source: 'human',
        })
        .then(afterCorrection)
        .catch((e) => setLoadError(e.message));
    },
    [novelId, afterCorrection]
  );

  const handleMergeLines = useCallback(
    (primarySpanId, absorbedSpanId, chapter) => {
      if (!novelId) return;
      api
        .mergeLines(novelId, primarySpanId, absorbedSpanId, chapter)
        .then(() => {
          setPicker(null);
          refreshCorrections();
          window.alert(
            'Merge queued. It will show in the text after you Apply -- unlike other edits, ' +
              'this one has no live preview.'
          );
        })
        .catch((e) => setLoadError(e.message));
    },
    [novelId, refreshCorrections]
  );

  const handleRetype = useCallback(
    (span, newType, chapterNumber) => {
      if (!novelId) return;
      // `chapterNumber` is threaded through explicitly from ScriptView's
      // wrapper -- same "don't re-derive from possibly-stale state"
      // reasoning as handleSpeakerClick above.
      api
        .reassignSpanType(novelId, span.span_id, chapterNumber, newType)
        .then(afterCorrection)
        .catch((e) => setLoadError(e.message));
    },
    [novelId, afterCorrection]
  );

  const onMarkHover = useCallback((e, text) => {
    setTip({ visible: true, x: e.clientX, y: e.clientY, text });
  }, []);
  const onMarkMove = useCallback((e) => {
    setTip((prev) => (prev.visible ? { ...prev, x: e.clientX, y: e.clientY } : prev));
  }, []);
  const onMarkLeave = useCallback(() => {
    setTip((prev) => ({ ...prev, visible: false }));
  }, []);

  const chapter = novel ? novel.chapters[chapterIdx] : null;

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
    return total ? `${attributed}/${total} dialogue lines attributed` : 'no dialogue';
  }, [chapter]);

  if (editMode && authChecked && authRequired && !authed) {
    return <Login onLoggedIn={() => setAuthed(true)} />;
  }

  if (loadError) {
    return (
      <div id="empty">
        {loadError}
        <br />
        <button onClick={() => setEditMode(false)} style={{ marginTop: '1rem' }}>
          Back to the static build
        </button>
      </div>
    );
  }

  if (editMode && !authChecked) {
    return <div id="empty">Checking authentication…</div>;
  }

  if (!manifest.length || !novel) {
    return <div id="empty">Loading…</div>;
  }

  const s = novel.stats;

  return (
    <>
      <header>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[0.65rem] uppercase tracking-widest text-muted">EchoTales</span>
          <h1 className="font-display text-xl text-text">
            {(manifest.find((m) => m.id === novelId) || {}).label || novelId}
          </h1>
        </div>
        <select
          id="novel-select"
          aria-label="Novel"
          value={novelId}
          onChange={(e) => handleSelectNovel(e.target.value)}
          className="h-8 rounded-sm border border-border bg-bg px-2 font-sans text-sm text-text"
        >
          {manifest.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
        <Label tone="neutral" id="novel-sub">{novel.chapters.length} chapters loaded</Label>
        <label className="edit-toggle flex items-center gap-2 font-sans text-sm text-text">
          <input
            type="checkbox"
            checked={editMode}
            onChange={(e) => {
              setEditMode(e.target.checked);
              setMergeSourceId(null);
            }}
          />
          Live edit
        </label>
        {editMode && (
          <button
            type="button"
            onClick={() => setShowAnalysis((v) => !v)}
            className="h-8 rounded-sm border border-border px-3 font-sans text-sm text-text hover:border-accent hover:text-accent"
          >
            Corrections ({correctionsSummary.pending_actionable ?? correctionsSummary.pending} pending
            {correctionsSummary.flags_open > 0 ? `, ${correctionsSummary.flags_open} flags` : ''})
          </button>
        )}
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'paper' : 'ink'} theme`}
          className="ml-auto h-8 rounded-sm border border-border px-3 font-mono text-xs uppercase tracking-wider text-muted hover:border-accent hover:text-accent"
        >
          {theme === 'dark' ? 'Ink' : 'Paper'}
        </button>
        <a
          href="/"
          className="font-mono text-xs uppercase tracking-wider text-muted underline decoration-border underline-offset-4 hover:text-accent hover:decoration-accent"
        >
          &larr; Back to viewer
        </a>
        <div className="stats-strip" id="stats-strip">
          <div><b>{s.chapters}</b> chapters</div>
          <div><b>{s.mentions.toLocaleString()}</b> mentions</div>
          <div><b>{pct(s.resolution_rate)}</b> resolved</div>
          <div><b>{s.entities}</b> entities</div>
          <div className={s.singleton_rate > 0.4 ? 'warn' : ''}>
            <b>{pct(s.singleton_rate)}</b> seen once
          </div>
          <div className={s.attribution_rate < 0.6 ? 'warn' : ''}>
            <b>{pct(s.attribution_rate)}</b> dialogue attributed
          </div>
          {s.dialogue_anonymous > 0 && (
            <div title="Distinct voice slot, no known identity">
              <b>{s.dialogue_anonymous.toLocaleString()}</b> anonymous
            </div>
          )}
        </div>
      </header>

      <nav className="rail" aria-label="Sections">
        {NAV_ITEMS.map((item) => (
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

      <main>
        {view === 'script' && (
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
              editMode={editMode}
              onMentionClick={handleMentionClick}
              onSpeakerClick={handleSpeakerClick}
              onFlagLine={handleFlagLine}
              onMergeLines={handleMergeLines}
              onRetype={handleRetype}
              onCreateMention={handleCreateMentionPrompt}
            />
          </>
        )}
        {view === 'characters' && <CharacterDashboard novelId={novelId} />}
        {view === 'state' && (
          <div className="mx-auto max-w-3xl px-6 py-10">
            <header className="border-b border-border pb-6">
              <div className="font-mono text-xs uppercase tracking-widest text-muted">{novelId}</div>
              <h1 className="mt-2 font-display text-4xl text-text">State &amp; timeline</h1>
              <p className="mt-2 max-w-xl text-sm text-muted">
                A character's body/persona history over story time -- Self ≠ persona is one of
                EchoTales' central concepts. Open a character in the Cast archive to see its
                timeline once the backend exposes epoch data.
              </p>
            </header>
            <div className="mt-8">
              <TimelineRail epochs={null} />
            </div>
          </div>
        )}
        {view === 'generation' && <GenerationWorkspace novelId={novelId} />}
        {view === 'outputs' && <OutputLibrary novelId={novelId} />}
        {view === 'project' && (
          <ProjectHome
            novelId={novelId}
            onNewProject={() => setView('new-project')}
          />
        )}
        {view === 'new-project' && (
          <NewProject
            onCreated={(created) => {
              api.manifest().then(setManifest);
              handleSelectNovel(created.id);
              setView('project');
            }}
          />
        )}
      </main>

      <aside className="inspector">
        {view === 'script' && (
          <EntitySidebar
            entities={novel.entities}
            search={search}
            onSearchChange={setSearch}
            focusId={focusId}
            onToggleFocus={handleToggleFocus}
            editMode={editMode}
            mergeSourceId={mergeSourceId}
            onStartMerge={handleStartMerge}
            onConfirmMerge={handleConfirmMerge}
            onCancelMerge={handleCancelMerge}
          />
        )}
        {view !== 'script' && (
          <InspectorSection title="Inspector">
            <p className="text-sm text-muted">
              No contextual detail for this screen yet.
            </p>
          </InspectorSection>
        )}
      </aside>

      <Tooltip tip={tip} />

      {picker && (
        <EntityPicker
          entities={novel.entities}
          anchor={picker.anchor}
          onSelect={handlePickerSelect}
          onCreateNew={handlePickerCreate}
          onClear={picker.kind === 'create_mention' ? undefined : handlePickerClear}
          onAnonSlot={picker.kind === 'speaker' ? handlePickerAnonSlot : undefined}
          onCancel={closePicker}
        />
      )}

      {editMode && showAnalysis && (
        <AnalysisPanel
          summary={correctionsSummary}
          onApply={handleApply}
          applyResult={applyResult}
          applying={applying}
          onClose={() => setShowAnalysis(false)}
        />
      )}
    </>
  );
}
