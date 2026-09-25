import React from 'react';
import Label from './Label';

/* Detail-view header -- name, kind badge, metadata strip. Reused by
   `CharacterDashboard`'s dossier view and available for a future
   chapter-detail view (plan Section 2/5). */
export default function DossierHeader({ eyebrow, title, tone = 'neutral', badge, meta }) {
  return (
    <div className="flex flex-wrap items-baseline gap-4 border-b border-border pb-6">
      <div className="w-full">
        {eyebrow && (
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{eyebrow}</div>
        )}
        <div className="mt-1 flex flex-wrap items-baseline gap-4">
          <h1 className="font-display text-5xl font-bold tracking-tight text-text">{title}</h1>
          {badge && <Label tone={tone}>{badge}</Label>}
        </div>
      </div>
      {meta && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-muted">{meta}</div>
      )}
    </div>
  );
}
