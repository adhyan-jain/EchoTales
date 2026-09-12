import React from 'react';

/* TRAIT -> SOURCE -> QUOTE, made structurally visible rather than hidden in
   a tooltip -- per the brief, evidence is a first-class object, closer to a
   scholarly annotation than an "AI explanation" callout. */
export default function EvidenceBlock({ trait, source, quote }) {
  return (
    <div className="border-l-2 border-border pl-4 py-1">
      <div className="font-mono text-xs uppercase tracking-wider text-accent">{trait}</div>
      {source && <div className="mt-0.5 font-mono text-xs text-muted">{source}</div>}
      {quote && (
        <blockquote className="mt-1.5 font-display italic text-lg leading-snug text-text">
          &ldquo;{quote}&rdquo;
        </blockquote>
      )}
    </div>
  );
}
