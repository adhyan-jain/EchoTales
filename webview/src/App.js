import React, { useState, useEffect, useCallback, useMemo } from 'react';
import EntitySidebar from './components/EntitySidebar';
import ChapterNav from './components/ChapterNav';
import ScriptView from './components/ScriptView';
import Tooltip from './components/Tooltip';
import AnalysisPanel from './components/AnalysisPanel';
import EntityPicker from './components/EntityPicker';
import { api } from './api';

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
 * A correction is never fed back into the resolver as input (HANDOFF §6 rules
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

  // Manifest: static file, or the backend's live list.
  useEffect(() => {
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
  }, [editMode]);

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
        picker.kind === 'mention'
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
        picker.kind === 'mention'
          ? api.reassignMention(novelId, picker.mentionId, target)
          : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, target);
      call.then(afterCorrection).catch((e) => setLoadError(e.message));
    },
    [picker, novelId, afterCorrection]
  );

  const handlePickerClear = useCallback(() => {
    if (!picker || !novelId) return;
    const call =
      picker.kind === 'mention'
        ? api.reassignMention(novelId, picker.mentionId, null)
        : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, null);
    call.then(afterCorrection).catch((e) => setLoadError(e.message));
  }, [picker, novelId, afterCorrection]);

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

  if (!manifest.length || !novel) {
    return <div id="empty">Loading…</div>;
  }

  const s = novel.stats;

  return (
    <>
      <header>
        <h1>EchoTales viewer</h1>
        <select
          id="novel-select"
          value={novelId}
          onChange={(e) => handleSelectNovel(e.target.value)}
        >
          {manifest.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </select>
        <span className="sub" id="novel-sub">{novel.chapters.length} chapters loaded</span>
        <label className="edit-toggle">
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
          <button onClick={() => setShowAnalysis((v) => !v)}>
            Corrections ({correctionsSummary.pending_actionable ?? correctionsSummary.pending} pending
            {correctionsSummary.flags_open > 0 ? `, ${correctionsSummary.flags_open} flags` : ''})
          </button>
        )}
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

      <main>
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
        />
      </main>

      <Tooltip tip={tip} />

      {picker && (
        <EntityPicker
          entities={novel.entities}
          anchor={picker.anchor}
          onSelect={handlePickerSelect}
          onCreateNew={handlePickerCreate}
          onClear={handlePickerClear}
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
