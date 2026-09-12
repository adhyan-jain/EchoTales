import React from 'react';

export default function Input({ className = '', ...props }) {
  return (
    <input
      className={
        'h-10 w-full rounded-sm border border-border bg-transparent px-3 font-sans text-base text-text ' +
        'placeholder:text-muted outline-none transition-colors ' +
        'focus:border-accent ' +
        className
      }
      {...props}
    />
  );
}
