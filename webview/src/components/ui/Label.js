import React from 'react';

/* Small status chip. Was a bracketed mono stamp ([ PRINCIPAL ]) in the
   archive direction; a tinted pill reads faster in the cinematic one. */
const TONES = {
  neutral: 'text-muted bg-surface2 border-border',
  accent: 'text-accent bg-accent/10 border-accent/30',
  success: 'text-success bg-success/10 border-success/30',
  warning: 'text-warning bg-warning/10 border-warning/30',
  danger: 'text-danger bg-danger/10 border-danger/30',
};

export default function Label({ tone = 'neutral', className = '', children }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}>
      {children}
    </span>
  );
}
