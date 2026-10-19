import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// The Read page must not name a character before the book does. The book here
// mirrors packages/pipeline/tests/test_reader_cast.py: "the masked guest" is
// revealed as Arthur Vane in chapter 3, and the whole-volume payload already
// labels him (and his dialogue) "Arthur Vane" in chapter 1.
jest.mock('../api', () => ({
  api: {
    hasToken: jest.fn(),
    authStatus: jest.fn(),
    listProjects: jest.fn(),
    listOutput: jest.fn(),
    novel: jest.fn(),
    corrections: jest.fn(),
    characters: jest.fn(),
    readerCast: jest.fn(),
    outputFileUrl: jest.fn(),
    reassignSpeaker: jest.fn(),
  },
  SPAN_TYPES: ['DIALOGUE', 'NARRATION_ACTION'],
}));

// eslint-disable-next-line import/first
import { api } from '../api';
// eslint-disable-next-line import/first
import { routes } from '../router';
// eslint-disable-next-line import/first
import { ToastProvider } from '../components/ui/Toast';
// eslint-disable-next-line import/first
import { readerChapter } from '../pages/project/Read';

const GUEST_WHOLE = { id: 'g', label: 'Arthur Vane', count: 3, colour: '#8b70ff', aliases: ['Arthur Vane', 'The masked guest'], first_chapter: 1, last_chapter: 3 };
const CORIN_WHOLE = { id: 'c', label: 'Corin', count: 1, colour: '#22aa88', aliases: ['Corin'], first_chapter: 3, last_chapter: 3 };
const GUEST_AT_1 = { ...GUEST_WHOLE, label: 'The masked guest', aliases: ['The masked guest'], count: 1, last_chapter: 1 };

const CH1 = {
  number: 1,
  spans: [
    {
      span_id: 's1', type: 'NARRATION_ACTION', text: 'The masked guest bowed.',
      marks: [{ s: 0, e: 16, id: 'g', label: 'Arthur Vane', surface: 'The masked guest', resolved: true, conf: 0.9, colour: '#8b70ff' }],
    },
    { span_id: 's2', type: 'DIALOGUE', text: '"Good evening."', marks: [], speaker: 'Arthur Vane', speaker_id: 'g', method: 'CONTEXTUAL_LLM' },
    { span_id: 's3', type: 'DIALOGUE', text: '"Who asks?"', marks: [], speaker: 'Corin', speaker_id: 'c', method: 'CONTEXTUAL_LLM' },
    { span_id: 's4', type: 'DIALOGUE', text: '"Hush."', marks: [], speaker: 'Voice A', speaker_id: 'anon:A', anonymous_speaker: true },
  ],
};
const CH2 = { number: 2, spans: [{ span_id: 's5', type: 'NARRATION_ACTION', text: 'The next morning.', marks: [] }] };
const NOVEL = {
  novel_id: 'toy',
  label: 'Toy Novel',
  stats: { chapters: 2 },
  entities: [GUEST_WHOLE, CORIN_WHOLE],
  chapters: [CH1, CH2],
};

function mount(path) {
  api.hasToken.mockReturnValue(false);
  api.authStatus.mockResolvedValue({ auth_required: false });
  api.listProjects.mockResolvedValue([{ id: 'toy', title: 'Toy Novel', ingested: true, chapter_count: 1 }]);
  api.listOutput.mockResolvedValue({ kinds: {} });
  api.novel.mockResolvedValue(NOVEL);
  api.corrections.mockResolvedValue({ summary: { total: 0, applied: 0, pending: 0, pending_actionable: 0, flags_open: 0, by_type: {} } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  );
  return router;
}

test('the reader names only who the reader has met, in the list, the marks and the speaker column', async () => {
  api.readerCast.mockResolvedValue({ entities: [GUEST_AT_1] });
  mount('/p/toy/read/1');
  expect(await screen.findByRole('button', { name: /^The masked guest, 1 mentions/ })).toBeInTheDocument();
  expect(screen.queryByText('Arthur Vane')).not.toBeInTheDocument();
  expect(screen.queryByText('Corin')).not.toBeInTheDocument();
  expect(screen.getByText('unnamed speaker')).toBeInTheDocument(); // Corin speaks before anyone names him
  expect(screen.getByText('Voice A')).toBeInTheDocument(); // an anonymous slot names no one
  fireEvent.mouseEnter(screen.getByText('The masked guest', { selector: 'mark' }));
  expect(await screen.findByText(/The masked guest\s+·\s+conf/)).toBeInTheDocument(); // the hover tooltip
  expect(screen.queryByText(/Arthur Vane/)).not.toBeInTheDocument();
});

test('the cast failing to load offers a retry instead of falling back to the whole-book cast', async () => {
  api.readerCast.mockRejectedValueOnce(Object.assign(new Error('HTTP 500'), { status: 500 }));
  api.readerCast.mockResolvedValueOnce({ entities: [GUEST_AT_1] });
  mount('/p/toy/read/1');
  fireEvent.click(await screen.findByRole('button', { name: /try again/i }));
  expect(await screen.findByRole('button', { name: /^The masked guest, 1 mentions/ })).toBeInTheDocument();
  expect(screen.queryByText('Arthur Vane')).not.toBeInTheDocument();
  await waitFor(() => expect(api.readerCast).toHaveBeenCalledTimes(2));
});

test('a shared link focusing a character not met yet does not name them', async () => {
  api.readerCast.mockResolvedValue({ entities: [GUEST_AT_1] });
  mount('/p/toy/read/1?focus=c');
  expect(await screen.findByText('a character not met yet')).toBeInTheDocument();
  expect(screen.queryByText('Corin')).not.toBeInTheDocument();
});

test('readerChapter: while the cast loads, marks show the printed text and speakers an ellipsis', () => {
  const out = readerChapter(CH1, null);
  expect(out.spans[0].marks[0].label).toBe('The masked guest');
  expect(out.spans[1].speaker).toBe('…');
  expect(out.spans[3].speaker).toBe('Voice A');
  expect(CH1.spans[0].marks[0].label).toBe('Arthur Vane'); // the payload is not mutated
});

test('no focus chip until the chapter cast has loaded, so a met character is never shown as unmet', async () => {
  let release;
  api.readerCast.mockReturnValue(new Promise((resolve) => { release = resolve; }));
  mount('/p/toy/read/1?focus=g');
  await screen.findByText('Good evening.', { exact: false });
  expect(screen.queryByText('a character not met yet')).not.toBeInTheDocument();
  release({ entities: [GUEST_AT_1] });
  expect(await screen.findByRole('button', { name: /^Stop highlighting The masked guest/ })).toBeInTheDocument();
});

test('turning the page keeps the cast list up while the next chapter loads', async () => {
  window.scrollTo = jest.fn(); // jsdom does not implement it; the page turn scrolls to the top
  let release;
  api.readerCast.mockResolvedValueOnce({ entities: [GUEST_AT_1] });
  mount('/p/toy/read/1');
  expect(await screen.findByRole('button', { name: /^The masked guest, 1 mentions/ })).toBeInTheDocument();
  api.readerCast.mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));
  fireEvent.click(screen.getByRole('button', { name: /next chapter/i }));
  await waitFor(() => expect(api.readerCast).toHaveBeenCalledWith('toy', 2));
  expect(screen.getByRole('button', { name: /^The masked guest, 1 mentions/ })).toBeInTheDocument();
  expect(screen.queryByText('Loading the cast…')).not.toBeInTheDocument();
  release({ entities: [GUEST_WHOLE, CORIN_WHOLE] });
  expect(await screen.findByRole('button', { name: /^Corin, 1 mentions/ })).toBeInTheDocument();
});

test('clicking a dialogue speaker in the reader opens EntityPicker and allows reassigning speaker', async () => {
  api.readerCast.mockResolvedValue({ entities: [GUEST_AT_1] });
  api.reassignSpeaker.mockResolvedValue({ id: 'corr-1' });
  mount('/p/toy/read/1');
  const speakerBtn = await screen.findByRole('button', { name: /Reassign speaker The masked guest/i });
  expect(speakerBtn).toBeInTheDocument();
  fireEvent.click(speakerBtn);
  expect(await screen.findByRole('dialog', { name: /Choose a character/i })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/Search or type a new name/i)).toBeInTheDocument();
});
