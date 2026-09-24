import React from 'react';

/* One persona/body-state marker on a `TimelineRail` -- label, narrative
   range, and an optional transition note. Kept separate from
   `TimelineRail` so a future chapter-timeline view can reuse the marker
   shape without the rail's layout (plan Section 2/6). */
export default function StateNode({ label, range, detail, active }) {
  return (
    <div className="flex min-w-[9rem] flex-col items-start gap-1">
      <div
        className={
          'h-2.5 w-2.5 rounded-full border ' +
          (active ? 'border-accent bg-accent' : 'border-border bg-surface2')
        }
        aria-hidden="true"
      />
      <div className="font-display text-lg text-text">{label}</div>
      {range && <div className="font-mono text-xs text-muted">{range}</div>}
      {detail && <div className="text-sm text-muted">{detail}</div>}
    </div>
  );
}
