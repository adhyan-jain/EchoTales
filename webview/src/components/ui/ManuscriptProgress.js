import React from 'react';

/* Ingestion, staged as "reading the manuscript" rather than a percentage
   bar -- per the brief, this is meant to feel alive, and it degrades
   honestly: a chapter with no status yet renders PENDING, not a fake tick. */
const STATUS_LABEL = {
  found: 'FOUND',
  processing: 'PROCESSING',
  pending: 'PENDING',
};

export default function ManuscriptProgress({ chapters, stats }) {
  return (
    <div className="font-mono text-sm">
      <div className="mb-3 text-xs uppercase tracking-wider text-muted">Reading manuscript</div>
      <div className="space-y-1">
        {chapters.map((c) => (
          <div key={c.number} className="flex items-center gap-2 text-text">
            <span>Chapter {String(c.number).padStart(2, '0')}</span>
            <span className="flex-1 border-b border-dotted border-border" />
            <span
              className={
                c.status === 'processing'
                  ? 'animate-pulse text-accent'
                  : c.status === 'found'
                  ? 'text-muted'
                  : 'text-muted/50'
              }
            >
              {STATUS_LABEL[c.status] || STATUS_LABEL.pending}
            </span>
          </div>
        ))}
      </div>
      {stats && (
        <>
          <div className="my-3 h-px bg-border" />
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted">
            {stats.words != null && <span>{stats.words.toLocaleString()} words</span>}
            {stats.chapters != null && <span>{stats.chapters} chapters</span>}
            {stats.entities != null && <span>{stats.entities} entities detected</span>}
          </div>
        </>
      )}
    </div>
  );
}
