import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ClipboardCheck, PencilLine, Users, X } from 'lucide-react';
import { api } from '../../api';
import AnalysisPanel from '../../components/AnalysisPanel';
import ChapterNav from '../../components/ChapterNav';
import EntityPicker from '../../components/EntityPicker';
import EntitySidebar from '../../components/EntitySidebar';
import ScriptView from '../../components/ScriptView';
import Tooltip from '../../components/Tooltip';
import { CenterMessage, ProjectProblem } from '../../components/app/Chrome';
import { useToast } from '../../components/ui/Toast';
import { useNovelData } from '../../lib/ProjectContext';
import PromptModal from '../../components/ui/PromptModal';
import { describeError } from '../../lib/errors';


const pct = (x) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '—');


// A new mention needs exact offsets, so the text must occur in the line
// exactly once. Returned as a message rather than toasted, so the dialog
// can show it next to the field and stay open for a retry.
function mentionProblem(text, span) {
  if (!text) return 'Type the words from this line that name the character.';
  const start = span.text.indexOf(text);
  if (start === -1) return `“${text}” is not in this line. Copy it exactly, including capitals.`;
  if (span.text.indexOf(text, start + 1) !== -1) {
    return `“${text}” appears more than once in this line. Select the exact words in the text instead, then press + Mention.`;
  }
  return null;
}

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
  const { novelId, novel, error, errorStatus, refetch } = useNovelData();
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
  const [items, setItems] = useState([]);
  const [undoing, setUndoing] = useState(null);
  const [failedIds, setFailedIds] = useState(() => new Set());
  const [showEntities, setShowEntities] = useState(false);

  const chapters = useMemo(() => (novel ? novel.chapters : []), [novel]);
  const idx = useMemo(() => {
    const ch = params.get('ch');
    const i = ch ? chapters.findIndex((c) => String(Number(c.number)) === ch) : 0;
    return i >= 0 ? i : 0;
  }, [chapters, params]);
  const chapter = chapters[idx];
  // Highest "Unknown Speaker N" already used in this chapter. Slot numbers
  // restart at 1 in every chapter (the slot id carries the chapter), so the
  // picker offers 1..max(4, this) plus a New button for the next number.
  const usedAnonSlots = useMemo(() => {
    let max = 0;
    ((chapter && chapter.spans) || []).forEach((sp) => {
      const m = /^Unknown Speaker (\d+)$/.exec(sp.speaker || '');
      if (m) max = Math.max(max, Number(m[1]));
    });
    return max;
  }, [chapter]);

  const fail = useCallback((e) => push(describeError(e, 'That change could not be saved.'), 'danger'), [push]);

  const refreshSummary = useCallback(() => {
    return api
      .corrections(novelId)
      .then((r) => {
        setSummary(r.summary);
        setItems(r.items || []);
        return r;
      })
      .catch(() => null);
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
  const [promptModal, setPromptModal] = useState(null);

  const processCreateMentionText = useCallback(
    (text, span, chapterNumber, anchor) => {
      const problem = mentionProblem(text, span);
      if (problem) {
        push(problem, 'danger');
        return;
      }
      const start = span.text.indexOf(text);
      setPicker({
        kind: 'create_mention',
        spanId: span.span_id,
        chapter: chapterNumber,
        localStart: start,
        localEnd: start + text.length,
        text,
        anchor,
      });
    },
    [push]
  );

  const onCreateMention = useCallback(
    (span, e, chapterNumber) => {
      const selected = window.getSelection() ? window.getSelection().toString().trim() : '';
      const anchor = { x: e.clientX, y: e.clientY };
      if (selected) {
        processCreateMentionText(selected, span, chapterNumber, anchor);
      } else {
        setPromptModal({
          title: 'Add a missed mention',
          label: 'Words in this line that refer to a character',
          description: span.text,
          placeholder: 'e.g. the old man…',
          submitLabel: 'Choose character',
          validate: (text) => mentionProblem(text, span),
          onSubmit: (text) => {
            setPromptModal(null);
            processCreateMentionText(text, span, chapterNumber, anchor);
          },
        });
      }
    },
    [processCreateMentionText]
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
      // The server's preview overlay has no case for new mentions (nor for
      // line merges): they appear only after Apply. Without saying so, the
      // edit looked lost -- the QA run on 2026-09-26 saw the correction
      // logged but no highlight in the line.
      const queuedOnly = picker.kind === 'create_mention';
      call
        .then(() => {
          if (queuedOnly) push('Mention queued. It shows in the text after you apply corrections.', 'success');
          after();
        })
        .catch(fail);
    },
    [picker, novelId, after, fail, push]
  );

  // -- line + entity actions ------------------------------------------------
  const onFlagLine = useCallback(
    (span, chapterNumber) => {
      setPromptModal({
        title: 'Flag this line',
        label: 'What looks wrong?',
        description: span.text,
        placeholder: 'e.g. the speaker should be Fang Zheng…',
        submitLabel: 'Flag line',
        multiline: true,
        validate: (note) => (note ? null : 'Add a short note so whoever reviews the flag knows what to check.'),
        onSubmit: (note) => {
          setPromptModal(null);
          api.flag(novelId, { spanId: span.span_id, chapter: chapterNumber, note, source: 'human' }).then(after).catch(fail);
        },
      });
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
    // A correction that errors on Apply is never written and stays unapplied,
    // so it would fail again on every Apply. Remember which ones were
    // attempted; those still unapplied afterwards are exactly the failures,
    // and the panel names them so they can be undone.
    const attempted = new Set(items.filter((c) => !c.applied && c.type !== 'flag').map((c) => c.id));
    api
      .applyCorrections(novelId)
      .then((result) => {
        setApplyResult(result);
        refetch();
        return refreshSummary();
      })
      .then((fresh) => {
        setFailedIds(new Set(((fresh && fresh.items) || []).filter((c) => attempted.has(c.id) && !c.applied).map((c) => c.id)));
      })
      .catch(fail)
      .finally(() => setApplying(false));
  }, [novelId, items, refetch, refreshSummary, fail]);

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

  if (error) return <ProjectProblem error={error} status={errorStatus} onRetry={refetch} />;
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
          onClick={() => setShowEntities(true)}
          className="inline-flex h-9 items-center gap-2 rounded-xl border border-border px-3 text-sm lg:hidden"
        >
          <Users className="h-4 w-4 text-muted" aria-hidden="true" /> Entities
        </button>
        <button
          type="button"
          onClick={() => setShowPanel((v) => !v)}
          aria-expanded={showPanel}
          className="inline-flex h-9 items-center gap-2 rounded-xl bg-primary px-3.5 text-sm font-semibold text-white shadow-glow transition-colors hover:bg-primary-2"
        >
          Corrections
          <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs tabular-nums">{pending}</span>
          {summary.flags_open > 0 && <span className="text-xs text-white">· {summary.flags_open} flags</span>}
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

      {/* Below lg the entity rail is hidden, and with it the only way to
          merge two entities; the same sidebar opens in a drawer instead. */}
      {showEntities && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Entities">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowEntities(false)} aria-hidden="true" />
          <div className="absolute inset-y-0 right-0 flex w-[min(20rem,90vw)] flex-col overscroll-contain border-l border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="font-display font-bold">Entities</span>
              <button
                type="button"
                autoFocus
                onClick={() => setShowEntities(false)}
                aria-label="Close entities"
                className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:text-text"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <EntitySidebar
                entities={novel.entities}
                search={search}
                onSearchChange={setSearch}
                focusId={focusId}
                onToggleFocus={(id) => setFocusId((prev) => (prev === id ? null : id))}
                editMode={editMode}
                mergeSourceId={mergeSourceId}
                onStartMerge={setMergeSourceId}
                onConfirmMerge={(id) => {
                  onConfirmMerge(id);
                  setShowEntities(false);
                }}
                onCancelMerge={() => setMergeSourceId(null)}
              />
            </div>
          </div>
        </div>
      )}
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
          usedAnonSlots={usedAnonSlots}
          onCancel={() => setPicker(null)}
        />
      )}
      {showPanel && (
        <AnalysisPanel
          summary={summary}
          items={items}
          failedIds={failedIds}
          undoing={undoing}
          onUndo={(id) => {
            setUndoing(id);
            api
              .undoCorrection(novelId, id)
              .then(() => {
                refetch();
                refreshSummary();
              })
              .catch(fail)
              .finally(() => setUndoing(null));
          }}
          onApply={onApply}
          applyResult={applyResult}
          applying={applying}
          onClose={() => setShowPanel(false)}
        />
      )}
      {promptModal && (
        <PromptModal
          open={true}
          title={promptModal.title}
          label={promptModal.label}
          description={promptModal.description}
          placeholder={promptModal.placeholder}
          submitLabel={promptModal.submitLabel}
          multiline={promptModal.multiline}
          validate={promptModal.validate}
          onSubmit={promptModal.onSubmit}
          onClose={() => setPromptModal(null)}
        />
      )}
    </div>
  );
}

