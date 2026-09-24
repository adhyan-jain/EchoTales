import React from 'react';
import StateNode from './StateNode';
import { EmptyState } from './EmptyState';

/* Horizontal story-time state rail (plan Section 6) -- one of EchoTales'
   distinctive concepts, given real visual weight here. `epochs` is
   expected to be `BodyEpoch`-shaped data (persona label, narrative
   range, transition note) once the webview payload exposes it.
   `build_character_dashboard` (packages/pipeline/.../webview.py) does
   not return that today -- confirmed by reading its payload shape -- so
   this renders the honest "not yet available" state whenever `epochs` is
   empty/undefined, rather than fabricating a single-persona timeline
   from the current snapshot. Never invent an epoch. */
export default function TimelineRail({ epochs }) {
  if (!epochs || epochs.length === 0) {
    return (
      <EmptyState
        title="State history not yet available"
        description="This view shows a character's body/persona timeline when the backend exposes epoch data. Today it only tracks the current state, not the history behind it."
      />
    );
  }
  return (
    <div className="relative flex items-start gap-6 overflow-x-auto border-t border-border pt-6">
      <div className="pointer-events-none absolute left-0 right-0 top-[1.3rem] h-px bg-border" />
      {epochs.map((epoch, i) => (
        <StateNode
          key={epoch.id || i}
          label={epoch.persona_label}
          range={epoch.range}
          detail={epoch.transition}
          active={i === epochs.length - 1}
        />
      ))}
    </div>
  );
}
