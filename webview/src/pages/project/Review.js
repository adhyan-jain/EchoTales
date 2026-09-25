import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ClipboardCheck, PencilLine } from 'lucide-react';
import { api } from '../../api';
import AnalysisPanel from '../../components/AnalysisPanel';
import ChapterNav from '../../components/ChapterNav';
import EntityPicker from '../../components/EntityPicker';
import EntitySidebar from '../../components/EntitySidebar';
import ScriptView from '../../components/ScriptView';
import Tooltip from '../../components/Tooltip';
import { CenterMessage } from '../../components/app/Chrome';
import { useToast } from '../../components/ui/Toast';
import { useProject } from '../../lib/ProjectContext';

const pct = (x) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '—');

/**
 * The reviewer desk: every correction action the old `?review` screen had
 * (reassign mention/speaker, create mention, merge entities, merge lines,
 * retype a line, flag, apply), moved onto its own page so reading and
 * correcting are no longer one crowded screen.
 *
 * A correction is never fed back into the resolver as input (HANDOFF
 * Section 6): it redirects this payload's display immediately and, on
 * Apply, patches this run's stored bindings. The static-JSON mode the old
 * App.js carried is gone -- every page of the new app reads the live server.
 */
export default function Review() {
  const { novelId, novel, error, refetch } = useProject();
  const push = useToast();
  const [params, setParams] = useSearchParams();
  const [editMode, setEditMode] = useState(true);
  const [focusId, setFocusId] = useState(null);
  const [search, setSearch] = useState('');
  const [tip, setTip] = useState({ visible: false, x: 0, y: 0, text: '' });
  const [mergeSourceId, setMergeSourceId] = useState(null);
  const [picker, setPicker] = useState(null);
  const [showPanel, setShowPanel] = useState(false);
  const [summary, setSummary] = useState({ total: 0, applied: 0, pending: 0, pending_actionable: 0, flags_open: 0, by_type: {} });
  const [applyResult, setApplyResult] = useState(null);
  const [applying, setApplying] = useState(false);

  const chapters = useMemo(() => (novel ? novel.chapters : []), [novel]);
  const idx = useMemo(() => {
    const ch = params.get('ch');
    const i = ch ? chapters.findIndex((c) => String(Number(c.number)) === ch) : 0;
    return i >= 0 ? i : 0;
  }, [chapters, params]);
  const chapter = chapters[idx];

  const fail = useCallback((e) => push((e && e.message) || 'That change could not be saved.', 'danger'), [push]);

  const refreshSummary = useCallback(() => {
    api.corrections(novelId).then((r) => setSummary(r.summary)).catch(() => {});
  }, [novelId]);
  useEffect(() => {
    refreshSummary();
  }, [refreshSummary]);

  const after = useCallback(() => {
    setPicker(null);
    refetch();
    refreshSummary();
  }, [refetch, refreshSummary]);

  const goTo = useCallback(
    (i) => {
      const c = chapters[i];
      if (!c) return;
      const next = new URLSearchParams(params);
      next.set('ch', String(Number(c.number)));
      setParams(next);
      window.scrollTo({ top: 0 });
    },
    [chapters, params, setParams]
  );

  // -- picker ---------------------------------------------------------------
  const onMentionClick = useCallback((mark, e) => {
    setPicker({ kind: 'mention', mentionId: mark.mention_id, anchor: { x: e.clientX, y: e.clientY } });
  }, []);
  const onSpeakerClick = useCallback((span, e, chapterNumber) => {
    setPicker({ kind: 'speaker', spanId: span.span_id, chapter: chapterNumber, anchor: { x: e.clientX, y: e.clientY } });
  }, []);
  const onCreateMention = useCallback(
    (span, e, chapterNumber) => {
      const selected = window.getSelection() ? window.getSelection().toString().trim() : '';
      const text = selected || window.prompt('Enter mention text from this line:');
      if (!text) return;
      const start = span.text.indexOf(text);
      if (start === -1) {
        push(`“${text}” is not in this line.`, 'danger');
        return;
      }
      if (span.text.indexOf(text, start + 1) !== -1) {
        push(`“${text}” appears more than once in this line. Select the exact text instead of typing it.`, 'danger');
        return;
      }
      setPicker({
        kind: 'create_mention',
        spanId: span.span_id,
        chapter: chapterNumber,
        localStart: start,
        localEnd: start + text.length,
        text,
        anchor: { x: e.clientX, y: e.clientY },
      });
    },
    [push]
  );

  const applyTarget = useCallback(
    (target) => {
      if (!picker) return;
      const call =
        picker.kind === 'create_mention'
          ? api.createMention(novelId, picker.spanId, picker.chapter, picker.localStart, picker.localEnd, picker.text, target)
          : picker.kind === 'mention'
          ? api.reassignMention(novelId, picker.mentionId, target)
          : api.reassignSpeaker(novelId, picker.spanId, picker.chapter, target);
      call.then(after).catch(fail);
    },
    [picker, novelId, after, fail]
  );

  // -- line + entity actions ------------------------------------------------
  const onFlagLine = useCallback(
    (span, chapterNumber) => {
      const note = window.prompt('Note for this flag (what looks wrong?)');
      if (note === null) return;
      api.flag(novelId, { spanId: span.span_id, chapter: chapterNumber, note, source: 'human' }).then(after).catch(fail);
    },
    [novelId, after, fail]
  );
  const onMergeLines = useCallback(
    (primary, absorbed, chapterNumber) => {
      api
        .mergeLines(novelId, primary, absorbed, chapterNumber)
        .then(() => {
          refreshSummary();
          push('Line merge queued. It shows in the text after you apply corrections.', 'success');
        })
        .catch(fail);
    },
    [novelId, refreshSummary, push, fail]
  );
  const onRetype = useCallback(
    (span, newType, chapterNumber) => {
      api.reassignSpanType(novelId, span.span_id, chapterNumber, newType).then(after).catch(fail);
    },
    [novelId, after, fail]
  );
  const onConfirmMerge = useCallback(
    (targetId) => {
      if (!mergeSourceId) return;
      api
        .mergeEntities(novelId, mergeSourceId, targetId)
        .then(() => {
          setMergeSourceId(null);
          after();
        })
        .catch(fail);
    },
    [novelId, mergeSourceId, after, fail]
  );
  const onApply = useCallback(() => {
    setApplying(true);
    api
      .applyCorrections(novelId)
      .then((result) => {
        setApplyResult(result);
        refetch();
        refreshSummary();
      })
      .catch(fail)
      .finally(() => setApplying(false));
  }, [novelId, refetch, refreshSummary, fail]);

  const onMarkHover = useCallback((e, text) => setTip({ visible: true, x: e.clientX, y: e.clientY, text }), []);
  const onMarkMove = useCallback((e) => setTip((p) => (p.visible ? { ...p, x: e.clientX, y: e.clientY } : p)), []);
  const onMarkLeave = useCallback(() => setTip((p) => ({ ...p, visible: false })), []);

  const coverage = useMemo(() => {
    if (!chapter) return '';
    let total = 0;
    let attributed = 0;
    chapter.spans.forEach((sp) => {
      if (sp.type === 'DIALOGUE') {
        total += 1;
        if (sp.speaker) attributed += 1;
      }
    });
    return total ? `${attributed}/${total} dialogue lines attributed` : 'no dialogue';
  }, [chapter]);

  if (error) return <CenterMessage title="Couldn’t load this project">{error}</CenterMessage>;
  if (!novel) return <CenterMessage>Loading the book…</CenterMessage>;

  const s = novel.stats || {};
  const pending = summary.pending_actionable ?? summary.pending;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 sm:px-6">
        <div className="mr-auto flex items-center gap-2">
          <ClipboardCheck className="h-5 w-5 text-accent" aria-hidden="true" />
          <h1 className="font-display text-lg font-bold tracking-tight">Review desk</h1>
        </div>
        <div className="hidden items-center gap-4 text-xs text-muted md:flex">
          <span>
            <b className="font-semibold tabular-nums text-text">{pct(s.resolution_rate)}</b> mentions linked
          </span>
          <span className={s.attribution_rate < 0.6 ? 'text-warning' : ''}>
            <b className="font-semibold tabular-nums">{pct(s.attribution_rate)}</b> dialogue attributed
          </span>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-border px-3 py-1.5 text-sm">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[rgb(var(--c-primary))]"
            checked={editMode}
            onChange={(e) => {
              setEditMode(e.target.checked);
              setMergeSourceId(null);
            }}
          />
          <PencilLine className="h-4 w-4 text-muted" aria-hidden="true" /> Editing
        </label>
        <button
          type="button"
          onClick={() => setShowPanel((v) => !v)}
          aria-expanded={showPanel}
          className="inline-flex h-9 items-center gap-2 rounded-xl bg-primary px-3.5 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-primary-2"
        >
          Corrections
          <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs tabular-nums">{pending}</span>
          {summary.flags_open > 0 && <span className="text-xs text-white/80">· {summary.flags_open} flags</span>}
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1">
          <ChapterNav chapters={chapters} chapterIdx={idx} onChange={goTo} coverage={coverage} />
          <ScriptView
            chapter={chapter}
            focusId={focusId}
            onMarkHover={onMarkHover}
            onMarkMove={onMarkMove}
            onMarkLeave={onMarkLeave}
            editMode={editMode}
            onMentionClick={onMentionClick}
            onSpeakerClick={onSpeakerClick}
            onFlagLine={onFlagLine}
            onMergeLines={onMergeLines}
            onRetype={onRetype}
            onCreateMention={onCreateMention}
          />
        </div>
        <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-l border-border bg-surface lg:block" aria-label="Entities">
          <EntitySidebar
            entities={novel.entities}
            search={search}
            onSearchChange={setSearch}
            focusId={focusId}
            onToggleFocus={(id) => setFocusId((prev) => (prev === id ? null : id))}
            editMode={editMode}
            mergeSourceId={mergeSourceId}
            onStartMerge={setMergeSourceId}
            onConfirmMerge={onConfirmMerge}
            onCancelMerge={() => setMergeSourceId(null)}
          />
        </aside>
      </div>

      <Tooltip tip={tip} />
      {picker && (
        <EntityPicker
          entities={novel.entities}
          anchor={picker.anchor}
          onSelect={applyTarget}
          onCreateNew={(label) => applyTarget({ new_label: label })}
          onClear={picker.kind === 'create_mention' ? undefined : () => applyTarget(null)}
          onAnonSlot={
            picker.kind === 'speaker'
              ? (slot) => api.reassignSpeaker(novelId, picker.spanId, picker.chapter, { anon_slot: slot }).then(after).catch(fail)
              : undefined
          }
          onCancel={() => setPicker(null)}
        />
      )}
      {showPanel && (
        <AnalysisPanel summary={summary} onApply={onApply} applyResult={applyResult} applying={applying} onClose={() => setShowPanel(false)} />
      )}
    </div>
  );
}
