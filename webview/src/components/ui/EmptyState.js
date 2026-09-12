import React from 'react';

export function EmptyState({ title, description, action }) {
  return (
    <div className="border border-dashed border-border py-16 text-center">
      <div className="font-display text-xl text-text">{title}</div>
      {description && <div className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = 'Loading' }) {
  return (
    <div className="flex items-center gap-2 py-10 font-mono text-xs uppercase tracking-wider text-muted">
      <span className="inline-block h-1.5 w-1.5 animate-pulse bg-accent" />
      {label}&hellip;
    </div>
  );
}
