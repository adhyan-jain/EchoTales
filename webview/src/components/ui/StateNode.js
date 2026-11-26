import React from 'react';
import Button from './Button';
import Label from './Label';

/* One persona/body-state marker on a `TimelineRail` -- label, narrative
   range, approval state, and an optional transition note. */
export default function StateNode({ label, range, detail, active, approved, onSelect, onApprove }) {
  return (
    <div
      className={
        'flex min-w-[11rem] flex-col items-start gap-1.5 p-2 rounded-lg border transition-colors cursor-pointer ' +
        (active ? 'border-accent bg-surface2/80 shadow-sm' : 'border-border bg-surface hover:bg-surface2/50')
      }
      onClick={onSelect}
    >
      <div className="flex items-center justify-between w-full">
        <div
          className={
            'h-2.5 w-2.5 rounded-full border ' +
            (active ? 'border-accent bg-accent' : 'border-border bg-surface2')
          }
          aria-hidden="true"
        />
        {approved ? (
          <Label tone="success">Approved</Label>
        ) : onApprove ? (
          <Button
            size="xs"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              onApprove();
            }}
          >
            Approve
          </Button>
        ) : (
          <Label tone="neutral">Unapproved</Label>
        )}
      </div>
      <div className="font-display text-base font-medium text-text">{label}</div>
      {range && <div className="font-mono text-xs text-muted">{range}</div>}
      {detail && <div className="text-xs text-muted line-clamp-2">{detail}</div>}
    </div>
  );
}

