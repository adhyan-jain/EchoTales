import React from 'react';

export default function Input({ className = '', ...props }) {
  return (
    <input
      className={
        'h-10 w-full rounded-xl border border-border bg-surface px-3 font-sans text-sm text-text ' +
        'placeholder:text-muted outline-none transition-colors ' +
        'focus:border-accent focus-visible:ring-1 focus-visible:ring-accent ' +
        className
      }
      {...props}
    />
  );
}
