import React from 'react';

/* Sentence-case sans labels; primary is the one violet fill on a page so
   the main action is unmistakable (cinematic redesign, 2026-09-26). */
const VARIANTS = {
  primary: 'bg-primary text-white shadow-glow hover:bg-primary-2',
  secondary: 'border border-border bg-surface text-text hover:border-accent/60 hover:bg-surface2',
  ghost: 'text-muted hover:bg-surface2 hover:text-text',
  danger: 'border border-danger/50 text-danger hover:bg-danger/10',
  white: 'bg-white text-black hover:bg-white/90',
};

const SIZES = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-base',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  disabled,
  children,
  ...props
}) {
  return (
    <button
      className={
        'inline-flex items-center justify-center gap-2 rounded-xl font-sans font-medium ' +
        'transition-[background-color,border-color,color,box-shadow] duration-150 disabled:opacity-40 disabled:pointer-events-none ' +
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ' +
        `${VARIANTS[variant]} ${SIZES[size]} ${className}`
      }
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}
