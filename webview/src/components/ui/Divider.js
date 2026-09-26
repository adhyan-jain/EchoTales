import React from 'react';

/* A fine rule -- the primary structural device in this system, used instead
   of card boundaries or shadows to separate sections. A labelled divider is a
   section heading set in the display serif with the rule beneath it (it was an
   uppercase tracked label with a trailing line, one of the template tells). */
export default function Divider({ label, className = '' }) {
  if (!label) return <hr className={`border-border ${className}`} />;
  return (
    <div className={`border-b border-border pb-2 ${className}`}>
      <span className="font-display text-2xl font-medium text-text">{label}</span>
    </div>
  );
}
