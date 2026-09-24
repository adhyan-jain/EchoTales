import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Regression test for the split this session made: `Viewer` (end-user
// product surface) and `App` (reviewer/production-desk tool) must stay
// genuinely different screens, not the same component with a flag. This
// pins down the concrete, checkable difference -- no "Live edit" checkbox,
// no stats strip, only the three reader-facing nav items -- so a future
// change can't silently re-merge them back into one screen.

// CRA's default jest config sets `resetMocks: true` -- any implementation
// baked into a `jest.fn(() => ...)` inside this factory gets wiped before
// the test body runs, so implementations are set with `.mockResolvedValue`
// in the test itself instead (same pattern `ProductScreens.test.js` uses).
jest.mock('../api', () => ({
  api: {
    hasToken: jest.fn(),
    authStatus: jest.fn(),
    manifest: jest.fn(),
    novel: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../api';
// eslint-disable-next-line import/first
import Viewer from '../Viewer';

test('Viewer has no reviewer chrome -- no Live edit toggle, only Read/Cast/Library nav', async () => {
  api.hasToken.mockReturnValue(false);
  api.authStatus.mockResolvedValue({ auth_required: false });
  api.manifest.mockResolvedValue([{ id: 'toy', label: 'Toy Novel', content_type: 'novel' }]);
  api.novel.mockResolvedValue({
    novel_id: 'toy',
    entities: [],
    chapters: [{ number: 1, title: 'First', spans: [] }],
    stats: {},
  });

  render(<Viewer />);

  await waitFor(() => expect(screen.getByRole('button', { name: 'Read' })).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Cast' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Library' })).toBeInTheDocument();

  // The reviewer-only affordances must not exist here at all.
  expect(screen.queryByText(/live edit/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/corrections/i)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Script' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Generation' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Project' })).not.toBeInTheDocument();

  // The link to the reviewer tool is present but distinct from being it.
  expect(screen.getByRole('link', { name: /reviewer tools/i })).toHaveAttribute('href', '?review');
});
