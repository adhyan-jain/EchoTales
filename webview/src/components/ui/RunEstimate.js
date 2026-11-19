import React from 'react';
import Badge from './Badge';

// Seconds as a person reads a wait: minutes up to two hours, hours after.
export function formatDuration(seconds) {
  const s = Number(seconds) || 0;
  if (s < 60) return 'under 1 min';
  if (s < 7200) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

/* What a long build is expected to cost in time, per stage, taken from `long_series.estimate_run` (the pipeline job's
   `estimate`). A stage is "measured" only when this project has timed it before; the rest are unmeasured defaults and
   say "estimate", so the total never reads as a promise it cannot keep. */
export default function RunEstimate({ estimate }) {
  if (!estimate || !Array.isArray(estimate.stages) || estimate.stages.length === 0) return null;
  return (
    <div aria-label="Run estimate" className="mt-3 rounded-xl border border-border px-3 py-2 text-xs text-muted">
      <ul className="space-y-1">
        {estimate.stages.map((row) => (
          <li key={row.stage} className="flex items-center justify-between gap-3">
            <span className="text-text">{row.stage}</span>
            <span className="flex items-center gap-2">
              {formatDuration(row.seconds)}
              <Badge tone={row.basis === 'measured' ? 'success' : 'neutral'}>{row.basis}</Badge>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-2 border-t border-border pt-2">
        Total about {formatDuration(estimate.seconds)} for {estimate.chapters} chapter{estimate.chapters === 1 ? '' : 's'}
        {estimate.measured ? '.' : ', includes estimates.'}
      </div>
    </div>
  );
}
