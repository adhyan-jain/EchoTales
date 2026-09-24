import React from 'react';

/* The "page" wrapper around ScriptView's existing `#script` column --
   paper/ink layered background and a registration-mark corner tick, laid
   over the proven `.line`/`.dialogue` grid rather than replacing it (plan
   Section 4: "do not sacrifice text readability for aesthetics"). Pure
   CSS depth (shadow + border), no transforms on the reading column itself
   so scrolling/selection never feels like it's moving in 3D. */
export default function ManuscriptSurface({ chapterLabel, children }) {
  return (
    <div className="relative mx-auto max-w-[860px] px-4 pb-16 pt-6">
      <div className="relative bg-surface shadow-depth-2">
        {/* Registration-mark corner ticks -- a manuscript/print-production
            detail, not decoration for its own sake. */}
        <span className="pointer-events-none absolute left-2 top-2 h-3 w-3 border-l border-t border-accent/40" aria-hidden="true" />
        <span className="pointer-events-none absolute right-2 top-2 h-3 w-3 border-r border-t border-accent/40" aria-hidden="true" />
        {chapterLabel && (
          <div className="border-b border-border px-6 py-3 font-mono text-xs uppercase tracking-widest text-muted">
            {chapterLabel}
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
