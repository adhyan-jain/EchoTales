import React from 'react';

/* TRAIT -> SOURCE -> QUOTE, made structurally visible rather than hidden in
   a tooltip -- per the brief, evidence is a first-class object, closer to a
   scholarly annotation than an "AI explanation" callout. */
export default function EvidenceBlock({ trait, source, quote }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <div className="text-sm font-semibold text-accent">{trait}</div>
      {source && <div className="mt-0.5 font-mono text-xs text-muted">{source}</div>}
      {quote && (
        <blockquote className="mt-2 border-l-2 border-accent/40 pl-3 text-base italic leading-relaxed text-text">
          &ldquo;{quote}&rdquo;
        </blockquote>
      )}
    </div>
  );
}
