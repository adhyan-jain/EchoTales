import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import RunEstimate from '../ui/RunEstimate';

test('a book not yet ingested says the time is unknown instead of showing zeros', () => {
  render(
    <RunEstimate
      estimate={{ known: false, chapters: null, seconds: null, stages: [{ stage: 'render', seconds: null, basis: 'unknown' }] }}
    />
  );
  expect(screen.getByText(/unknown until the book is ingested/i)).toBeInTheDocument();
  expect(screen.queryByText(/under 1 min/i)).not.toBeInTheDocument();
});

test('a known estimate still lists each stage and the total', () => {
  render(
    <RunEstimate
      estimate={{ known: true, chapters: 2, seconds: 120, measured: false, stages: [{ stage: 'render', seconds: 120, basis: 'estimate' }] }}
    />
  );
  expect(screen.getByText('render')).toBeInTheDocument();
  expect(screen.getByText(/for 2 chapters/)).toBeInTheDocument();
});
