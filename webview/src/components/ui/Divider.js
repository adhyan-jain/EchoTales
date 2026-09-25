import React from 'react';

/* A fine rule -- the primary structural device in this system, used instead
   of card boundaries or shadows to separate sections. */
export default function Divider({ label, className = '' }) {
  if (!label) return <hr className={`border-border ${className}`} />;
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{label}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  );
}
