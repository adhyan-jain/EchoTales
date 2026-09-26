import React from 'react';

// `as` lets a page whose only content is this state supply its own <h1>.
export function EmptyState({ title, description, action, as: Heading = 'div' }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface/40 px-6 py-14 text-center">
      <Heading className="font-display text-lg font-semibold text-text">{title}</Heading>
      {description && <div className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = 'Loading' }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-muted" role="status">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
      {label}&hellip;
    </div>
  );
}
