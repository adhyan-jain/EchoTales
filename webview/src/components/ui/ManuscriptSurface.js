import React from 'react';

/* The "page" wrapper around ScriptView's `#script` column: one rounded
   panel laid over the proven `.line`/`.dialogue` grid rather than replacing
   it (plan Section 4: "do not sacrifice text readability for aesthetics").
   No transforms on the reading column, so scrolling and selection never
   feel like they move. */
export default function ManuscriptSurface({ chapterLabel, children }) {
  return (
    <div className="relative mx-auto max-w-[860px] px-4 pb-16 pt-6">
      <div className="relative overflow-hidden rounded-3xl border border-border bg-surface">
        {chapterLabel && (
          <div className="border-b border-border px-6 py-4 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
            {chapterLabel}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
