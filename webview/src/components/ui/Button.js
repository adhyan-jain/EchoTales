import React from 'react';

/* Sentence case, sans -- the brief asks for mono on metadata/evidence/system
   state, not on controls; a button is an action a person takes, and reads
   better as "Approve sample" than "APPROVE SAMPLE". Rectangular, no
   gradient/glow -- a production-desk control, not a SaaS CTA. */
const VARIANTS = {
  primary: 'bg-accent text-bg hover:bg-accent-2',
  secondary: 'border border-border text-text hover:border-accent hover:text-accent',
  ghost: 'text-muted hover:text-text underline decoration-border underline-offset-4 hover:decoration-accent',
  danger: 'border border-danger text-danger hover:bg-danger hover:text-bg',
};

const SIZES = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-base',
  lg: 'h-12 px-6 text-lg',
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
        'inline-flex items-center justify-center gap-2 rounded-sm font-sans font-medium ' +
        'transition-colors duration-150 disabled:opacity-40 disabled:pointer-events-none ' +
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg ' +
        `${VARIANTS[variant]} ${SIZES[size]} ${className}`
      }
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}
