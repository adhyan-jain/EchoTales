import React from 'react';

/* A surface, not a "card" in the SaaS sense: hairline border, no drop
   shadow, sharp corners. Composition (rules, spacing) carries hierarchy
   instead of nested elevation. */
export function Card({ className = '', children, ...props }) {
  return (
    <div className={`bg-surface border border-border rounded-sm ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ className = '', children }) {
  return <div className={`px-5 pt-4 pb-3 border-b border-border ${className}`}>{children}</div>;
}

export function CardBody({ className = '', children }) {
  return <div className={`p-5 ${className}`}>{children}</div>;
}
