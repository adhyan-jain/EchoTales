import React from 'react';
import Label from './Label';

const PROMINENCE_LABEL = {
  PRINCIPAL: 'Principal Character',
  RECURRING: 'Recurring Character',
  INCIDENTAL: 'Incidental',
};

/* A cast-list row, not a card -- index number, display-serif name, and a
   mono classification, separated by a single rule rather than a bordered
   box. Rows compose into a manifest; boxes would compose into a grid. */
export default function CharacterRow({ index, name, prominence, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className="group block w-full border-b border-border py-5 text-left transition-colors hover:bg-surface2"
    >
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-baseline gap-4">
          <span className="font-mono text-xs text-muted">{String(index).padStart(3, '0')}</span>
          <span className="font-display text-2xl text-text group-hover:text-accent">{name}</span>
        </div>
        <Label tone={prominence === 'PRINCIPAL' ? 'accent' : 'neutral'}>
          {PROMINENCE_LABEL[prominence] || prominence}
        </Label>
      </div>
      {children}
    </button>
  );
}
