import React from 'react';
import { Card } from './Card';

/* A `Card` with a layered-shadow hover lift -- the CSS-only "2.5D" surface
   used by archive rows, output tiles, and generation previews (plan
   Section 2). `.depth-hover`'s transition is itself gated behind
   `prefers-reduced-motion`/a 1280px floor (index.css), so this component
   never needs its own motion check -- the base `shadow-depth-1` state is
   fully legible with zero animation. */
export default function DepthCard({ className = '', interactive = true, children, ...props }) {
  return (
    <Card
      className={
        `shadow-depth-1 ${interactive ? 'depth-hover hover:shadow-depth-2' : ''} ${className}`
      }
      {...props}
    >
      {children}
    </Card>
  );
}
