import React from 'react';
import Label from './Label';

const PROMINENCE_LABEL = {
  PRINCIPAL: 'Principal Character',
  RECURRING: 'Recurring Character',
  INCIDENTAL: 'Incidental',
};

/* One character as a card in the cast grid (cinematic redesign,
   2026-09-26; it was a ruled list row). Principal characters get the accent
   gradient monogram so the leads stand out at a glance in a 90-person cast. */
export default function CharacterRow({ index, name, prominence, onClick, children }) {
  const principal = prominence === 'PRINCIPAL';
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        'group relative flex w-full items-center gap-4 overflow-hidden rounded-2xl border bg-surface p-4 text-left transition-[border-color,background-color] ' +
        (principal ? 'border-accent/30 hover:border-accent/70' : 'border-border hover:border-accent/50')
      }
    >
      <span
        className={
          'flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl font-display text-lg font-bold ' +
          (principal ? 'bg-accent-gradient text-black' : 'bg-surface2 text-text')
        }
        aria-hidden="true"
      >
        {(name || '?').slice(0, 1)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block overflow-hidden text-ellipsis whitespace-nowrap font-display text-lg font-semibold text-text group-hover:text-accent">
          {name}
        </span>
        <span className="mt-1 flex items-center gap-2">
          <Label tone={principal ? 'accent' : 'neutral'}>{PROMINENCE_LABEL[prominence] || prominence}</Label>
          <span className="font-mono text-xs text-muted">#{String(index).padStart(3, '0')}</span>
        </span>
      </span>
      {children}
    </button>
  );
}
