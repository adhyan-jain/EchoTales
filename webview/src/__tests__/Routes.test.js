import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// The reading surface and the reviewer desk must stay different pages, not
// one screen with a mode flag (this pinned Viewer vs App before the
// 2026-09-26 routed redesign; it now pins /read vs /review). Old query-param
// bookmarks must still land somewhere sensible.
//
// CRA's jest config sets `resetMocks: true`, so implementations are set in
// each test with `.mockResolvedValue`, not inside the factory.
jest.mock('../api', () => ({
  api: {
    hasToken: jest.fn(),
    authStatus: jest.fn(),
    listProjects: jest.fn(),
    listOutput: jest.fn(),
    novel: jest.fn(),
    corrections: jest.fn(),
    characters: jest.fn(),
    outputFileUrl: jest.fn(),
  },
  SPAN_TYPES: ['DIALOGUE', 'NARRATION_ACTION'],
}));

// eslint-disable-next-line import/first
import { api } from '../api';
// eslint-disable-next-line import/first
import { routes } from '../router';
// eslint-disable-next-line import/first
import { ToastProvider } from '../components/ui/Toast';

const NOVEL = {
  novel_id: 'toy',
  label: 'Toy Novel',
  stats: { chapters: 2, resolution_rate: 1, attribution_rate: 0.5 },
  entities: [{ id: 'e1', label: 'Hero', count: 3, colour: '#8b70ff', aliases: ['Hero'], first_chapter: 1, last_chapter: 2 }],
  chapters: [
    { number: 1, spans: [{ span_id: 's1', type: 'NARRATION_ACTION', text: 'Hero walked.', marks: [] }] },
    { number: 2, spans: [{ span_id: 's2', type: 'NARRATION_ACTION', text: 'Chapter two text.', marks: [] }] },
  ],
};

function mount(path) {
  api.hasToken.mockReturnValue(false);
  api.authStatus.mockResolvedValue({ auth_required: false });
  api.listProjects.mockResolvedValue([{ id: 'toy', title: 'Toy Novel', ingested: true, chapter_count: 2 }]);
  api.listOutput.mockResolvedValue({ kinds: {} });
  api.novel.mockResolvedValue(NOVEL);
  api.characters.mockResolvedValue({
    characters: [{ self_id: 'e1', label: 'Hero', prominence: 'PRINCIPAL', traits: [], reference_images: [] }],
  });
  api.corrections.mockResolvedValue({ summary: { total: 0, applied: 0, pending: 0, pending_actionable: 0, flags_open: 0, by_type: {} } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  );
  return router;
}

test('the reader shows the chapter from the URL and has no editing chrome', async () => {
  mount('/p/toy/read/2');
  expect(await screen.findByText('Chapter two text.')).toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: /editing/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /corrections/i })).not.toBeInTheDocument();
});

test('the review desk is its own page with the editing switch and corrections queue', async () => {
  mount('/p/toy/review');
  expect(await screen.findByRole('heading', { name: /review desk/i })).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /editing/i })).toBeChecked();
  expect(screen.getByRole('button', { name: /corrections/i })).toBeInTheDocument();
});

test('an old ?review bookmark redirects into the app', async () => {
  const router = mount('/?review');
  expect(await screen.findByRole('heading', { name: /your projects/i })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/projects');
});

test('the project sidebar separates reading pages from tools', async () => {
  mount('/p/toy');
  const nav = await screen.findAllByRole('navigation', { name: 'Project' });
  expect(nav[0]).toHaveTextContent(/Overview.*Read.*Characters.*Studio.*Tools.*Review.*Settings/);
});

test('an old ?gallery bookmark opens the design gallery', async () => {
  const router = mount('/?gallery');
  await screen.findAllByRole('heading');
  expect(router.state.location.pathname).toBe('/design');
});

test('old /cast links redirect to /characters, keeping the character', async () => {
  const router = mount('/p/toy/cast/e1');
  expect(await screen.findByRole('heading', { name: 'Hero' })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe('/p/toy/characters/e1');
});

test('a link to a character the book does not have says so', async () => {
  mount('/p/toy/characters/nobody');
  expect(await screen.findByText(/character not found/i)).toBeInTheDocument();
});

test('a link to a chapter the book does not have says so instead of showing chapter 1', async () => {
  mount('/p/toy/read/99');
  expect(await screen.findByText(/chapter 99 isn’t in this book/i)).toBeInTheDocument();
  expect(screen.queryByText('Hero walked.')).not.toBeInTheDocument();
});

test('an unknown route shows a not-found page', async () => {
  mount('/definitely/not/a/page');
  expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
});
