import React from 'react';

const TONES = {
  neutral: 'bg-surface2 text-muted border-border',
  accent: 'bg-accent/15 text-accent border-accent/30',
  success: 'bg-success/15 text-success border-success/30',
  warning: 'bg-warning/15 text-warning border-warning/30',
  danger: 'bg-danger/15 text-danger border-danger/30',
};

export default function Badge({ tone = 'neutral', className = '', children }) {
  return (
    <span
      className={
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ' +
        `${TONES[tone]} ${className}`
      }
    >
      {children}
    </span>
  );
}
