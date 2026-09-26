import React from 'react';

/* The "page" wrapper around ScriptView's `#script` column: the page laid over the proven `.line`/`.dialogue` grid rather than replacing
   it (plan Section 4: "do not sacrifice text readability for aesthetics").
   No transforms on the reading column, so scrolling and selection never
   feel like they move. */
export default function ManuscriptSurface({ chapterLabel, children }) {
  return (
    <div className="relative mx-auto max-w-[860px] px-4 pb-16 pt-8">
      {chapterLabel && (
        <div className="mb-2 flex items-center gap-4 border-b border-border pb-4">
          <span className="font-display text-3xl font-medium tracking-tight text-text">{chapterLabel}</span>
        </div>
      )}
      {children}
    </div>
  );
}
