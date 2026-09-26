import React from 'react';

const PROMINENCE_LABEL = {
  PRINCIPAL: 'Principal',
  RECURRING: 'Recurring',
  INCIDENTAL: 'Incidental',
};

/* One character as a ruled row in the cast list. It was a bordered card with
   a lettered tile; a hundred of those in a grid read as a template, and the
   tile carried no information the name did not. */
export default function CharacterRow({ index, name, prominence, onClick, children }) {
  const principal = prominence === 'PRINCIPAL';
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex w-full items-center gap-3 border-b border-border/70 py-3 text-left transition-colors hover:border-accent/60"
    >
      <span className="w-9 shrink-0 font-mono text-xs tabular-nums text-muted">{String(index).padStart(3, '0')}</span>
      <span className="min-w-0 flex-1">
        <span className="block overflow-hidden text-ellipsis whitespace-nowrap font-display text-xl text-text group-hover:text-accent">
          {name}
        </span>
        <span className={`text-xs ${principal ? 'font-medium text-accent' : 'text-muted'}`}>
          {PROMINENCE_LABEL[prominence] || prominence}
        </span>
      </span>
      {children}
    </button>
  );
}
