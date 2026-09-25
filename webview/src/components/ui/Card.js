import React from 'react';

/* Base surface: hairline border on a slightly lifted panel, generous
   radius (cinematic redesign, 2026-09-26). Depth comes from DepthCard's
   shadow steps, not from nesting cards inside cards. */
export function Card({ className = '', children, ...props }) {
  return (
    <div className={`bg-surface border border-border rounded-2xl ${className}`} {...props}>
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
