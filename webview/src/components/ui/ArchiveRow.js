import React from 'react';
import Label from './Label';

/* Generalized archival-index row -- an index number, a display-serif
   title, a classification label, and optional trailing metadata,
   separated by a rule rather than a bordered box (same reasoning as
   `CharacterRow`, which this generalizes: plan Section 2 asks for one
   reusable row shape across the character archive and the output
   library's chapter list rather than two near-duplicate components). */
export default function ArchiveRow({ index, title, subtitle, tone = 'neutral', meta, onClick, children }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      onClick={onClick}
      className={
        'group block w-full border-b border-border py-5 text-left transition-colors ' +
        (onClick ? 'hover:bg-surface2 cursor-pointer' : '')
      }
    >
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-baseline gap-4 min-w-0">
          {index != null && (
            <span className="font-mono text-xs text-muted">{String(index).padStart(3, '0')}</span>
          )}
          <span className="truncate font-display text-2xl text-text group-hover:text-accent">
            {title}
          </span>
        </div>
        {subtitle && <Label tone={tone}>{subtitle}</Label>}
      </div>
      {meta && (
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted">{meta}</div>
      )}
      {children}
    </Tag>
  );
}
