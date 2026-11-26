import React from 'react';
import StateNode from './StateNode';
import { EmptyState } from './EmptyState';

/* Horizontal story-time state rail -- one of EchoTales' distinctive concepts,
   visualizing character body epochs across story intervals with per-epoch review. */
export default function TimelineRail({ epochs, selectedId, onSelect, onApprove }) {
  if (!epochs || epochs.length === 0) {
    return (
      <EmptyState
        title="State history not yet available"
        description="This view shows a character's body/persona timeline when the backend exposes epoch data. Today it only tracks the current state, not the history behind it."
      />
    );
  }
  return (
    <div className="relative flex items-start gap-6 overflow-x-auto border-t border-border pt-6 pb-2">
      <div className="pointer-events-none absolute left-0 right-0 top-[1.3rem] h-px bg-border" />
      {epochs.map((epoch, i) => (
        <StateNode
          key={epoch.id || i}
          label={epoch.persona_label}
          range={epoch.range}
          detail={epoch.transition}
          active={selectedId ? selectedId === epoch.id : i === epochs.length - 1}
          approved={epoch.approved}
          onSelect={() => onSelect && onSelect(epoch.id)}
          onApprove={onApprove ? () => onApprove(epoch.persona_id || epoch.id) : null}
        />
      ))}
    </div>
  );
}

