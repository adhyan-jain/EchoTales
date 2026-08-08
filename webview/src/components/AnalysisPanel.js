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
export default function AnalysisPanel({ summary, onApply, applyResult, applying, onClose }) {
  const pending = summary.pending_actionable ?? summary.pending;
  return (
    <div className="analysis-panel">
      <div className="analysis-header">
        <b>Corrections</b>
        <button className="close" onClick={onClose}>&times;</button>
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
          <button disabled={pending === 0 || applying} onClick={onApply}>
            {applying ? 'Applying…' : `Apply ${pending} pending correction(s) to the graph`}
          </button>
          <p className="muted small">
            Rebinds mentions/speakers in the SQLite store and logs an event per
            change. Does not change how the resolver decides anything on the
            next run -- see HANDOFF §6 for why not. Flags are never applied;
            remove one from the list once you've dealt with it.
          </p>
        </>
      )}
      {applyResult && (
        <div className="apply-result">
          <b>Applied {applyResult.count} correction(s):</b>
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
