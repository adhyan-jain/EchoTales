import React from 'react';

/* Replaces the generic colored pill badge. A bracketed mono tag reads as an
   archival classification stamp ([ PRINCIPAL ]) rather than an "AI SaaS
   status chip" -- no fill, no rounding, color carried by text only. */
const TONES = {
  neutral: 'text-muted',
  accent: 'text-accent',
  success: 'text-success',
  warning: 'text-warning',
  danger: 'text-danger',
};

export default function Label({ tone = 'neutral', className = '', children }) {
  return (
    <span className={`font-mono text-xs uppercase tracking-wider ${TONES[tone]} ${className}`}>
      [&nbsp;{children}&nbsp;]
    </span>
  );
}
