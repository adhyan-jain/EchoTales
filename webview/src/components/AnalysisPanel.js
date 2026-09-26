import React from 'react';

/**
 * The second half of the feedback loop. A correction on its own is inert --
 * this is where it becomes visible as something to act on: how many are
 * pending, what they touch, and a button to actually patch the graph.
 *
 * Deliberately does not claim the pipeline "learned" anything. It didn't --
 * see the App-level docstring for why corrections are never fed back as
 * resolver input. This panel is the honest version: a log of human review,
 * and a one-click way to apply it to *this* run's output.
 *
 * `flag` corrections are excluded from "pending" here on purpose -- they
 * have no store-side effect, so sweeping them into Apply would silently mark
 * a note as dealt with the moment you fix something unrelated. They stay
 * open until removed (the same undo affordance that already exists).
 */
// Plain-language line for a queued correction. Ids are shortened to the part
// a reviewer recognises (line 3 of chapter 5), not the full `novel:5:3:0`.
function shortId(id) {
  const parts = String(id || '').split(':');
  return parts.length >= 3 ? parts.slice(1).join(':') : String(id || '');
}
function describePending(c) {
  const p = c.payload || {};
  switch (c.type) {
    case 'merge_lines':
      return `Merge line ${shortId(p.absorbed_span_id)} into ${shortId(p.primary_span_id)}`;
    case 'merge_entities':
      return 'Merge one character into another';
    case 'reassign_mention':
      return p.target_id || p.new_label ? `Change who a mention refers to (${shortId(p.mention_id)})` : `Unlink a mention (${shortId(p.mention_id)})`;
    case 'reassign_speaker':
      return p.anon_slot ? `Set line ${shortId(p.span_id)} to Unknown Speaker ${p.anon_slot}` : `Change the speaker of line ${shortId(p.span_id)}`;
    case 'reassign_span_type':
      return `Change line ${shortId(p.span_id)} to ${String(p.new_type || '').replace(/_/g, ' ').toLowerCase()}`;
    case 'create_mention':
      return `Add a mention “${p.text || ''}” in line ${shortId(p.span_id)}`;
    case 'flag':
      return `Flag on line ${shortId(p.span_id || p.mention_id)}${p.note ? `: ${p.note}` : ''}`;
    default:
      return c.type;
  }
}

export default function AnalysisPanel({ summary, items = [], failedIds = new Set(), onUndo, undoing, onApply, applyResult, applying, onClose }) {
  const pending = summary.pending_actionable ?? summary.pending;
  const waiting = items.filter((c) => !c.applied);
  // `failedIds`: corrections the last Apply attempted that are still unapplied,
  // i.e. they errored and would fail again. Named so they can be undone.
  return (
    <div className="analysis-panel">
      <div className="analysis-header">
        <b>Corrections</b>
        <button type="button" className="close" aria-label="Close corrections" onClick={onClose}>&times;</button>
      </div>
      {summary.total === 0 ? (
        <p className="muted">
          No corrections yet. In edit mode: click a highlighted mention or a
          speaker name to reassign it, an entity's ⇄ icon to merge it, or
          "flag" on a line to note it for later.
        </p>
      ) : (
        <>
          <p>
            <b>{summary.total}</b> logged &middot; <b>{pending}</b> pending &middot;{' '}
            <b>{summary.applied}</b> applied
            {summary.flags_open > 0 && <> &middot; <b>{summary.flags_open}</b> open flags</>}
          </p>
          <ul className="by-type">
            {Object.entries(summary.by_type).map(([type, count]) => (
              <li key={type}>{type}: {count}</li>
            ))}
          </ul>
          {waiting.length > 0 && (
            <>
              <h3 className="waiting-title">Waiting to apply</h3>
              <ul className="waiting-list">
                {waiting.map((c) => (
                  <li key={c.id} className={failedIds.has(c.id) ? 'failed' : ''}>
                    <span>
                      {describePending(c)}
                      {failedIds.has(c.id) && <em> — did not apply last time</em>}
                    </span>
                    <button
                      type="button"
                      className="undo"
                      disabled={undoing === c.id}
                      onClick={() => onUndo(c.id)}
                      aria-label={`Undo: ${describePending(c)}`}
                    >
                      Undo
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <button disabled={pending === 0 || applying} onClick={onApply}>
            {applying ? 'Applying…' : `Apply ${pending} pending correction${pending === 1 ? '' : 's'}`}
          </button>
          <p className="muted small">
            Applying writes your corrections into this book’s stored results. It does not change how the pipeline
            decides on its next run, so re-processing the book from scratch will not remember them. Flags are notes
            only and are never applied; undo one once you have dealt with it.
          </p>
        </>
      )}
      {applyResult && (
        <div className="apply-result">
          <b>
            {applyResult.applied.filter((x) => !x.error).length} applied
            {applyResult.applied.some((x) => x.error) && `, ${applyResult.applied.filter((x) => x.error).length} could not be applied`}:
          </b>
          <ul>
            {applyResult.applied.map((r, i) => (
              <li key={i}>{describeResult(r)}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function describeResult(r) {
  if (r.error) return `${r.type}: error -- ${r.error}`;
  switch (r.type) {
    case 'merge_entities':
      return `merged ${r.from_id} → ${r.into_id} (${r.mentions_rebound} mentions rebound)`;
    case 'reassign_mention':
      return `mention ${r.mention_id}: ${r.old_target_id || 'unresolved'} → ${r.new_target_id || 'unresolved'}`;
    case 'reassign_speaker':
      return `speaker on ${r.span_id}: ${r.old_speaker_id || 'none'} → ${r.new_speaker_id || 'none'}`;
    case 'merge_lines':
      return `merged line ${r.absorbed_span_id} into ${r.primary_span_id}`;
    case 'reassign_span_type':
      return `${r.span_id}: ${r.old_type} → ${r.new_type}`;
    default:
      return `${r.type}: done`;
  }
}
