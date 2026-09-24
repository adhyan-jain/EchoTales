import React from 'react';

/* A collapsible labeled section for the shell's right inspector rail and
   the generation workspace's metadata panel (plan Section 2/3). Plain
   <details>/<summary> -- native keyboard/AT support, no JS state needed. */
export default function InspectorSection({ title, defaultOpen = true, children }) {
  return (
    <details className="border-b border-border px-4 py-3" open={defaultOpen}>
      <summary className="cursor-pointer select-none font-mono text-xs uppercase tracking-wider text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent">
        {title}
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}
