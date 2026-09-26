import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

// Review's flag and add-mention actions used window.prompt/alert until the
// 2026-09-26 QA pass; the first in-app replacement then silently dropped an
// empty flag and toasted mention errors after the dialog had closed. These
// pin the replacement's behaviour: no native dialogs, a labelled field that
// takes focus, inline validation that keeps the dialog open, Escape to
// cancel with focus returned to the trigger, and the right API call on a
// valid submit.
jest.mock('../api', () => ({
  api: {
    hasToken: jest.fn(),
    authStatus: jest.fn(),
    listProjects: jest.fn(),
    listOutput: jest.fn(),
    novel: jest.fn(),
    corrections: jest.fn(),
    flag: jest.fn(),
    createMention: jest.fn(),
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

const LINE = 'The old man said Hero should leave.';
const NOVEL = {
  novel_id: 'toy',
  label: 'Toy',
  stats: {},
  entities: [{ id: 'e1', label: 'Hero', count: 2, colour: '#8b70ff', aliases: ['Hero'], first_chapter: 1, last_chapter: 1 }],
  chapters: [{ number: 1, spans: [{ span_id: 's1', type: 'NARRATION_ACTION', text: LINE, marks: [] }] }],
};

let promptSpy;
let alertSpy;

beforeEach(() => {
  api.hasToken.mockReturnValue(false);
  api.authStatus.mockResolvedValue({ auth_required: false });
  api.listProjects.mockResolvedValue([{ id: 'toy', title: 'Toy', ingested: true, chapter_count: 1 }]);
  api.listOutput.mockResolvedValue({ kinds: {} });
  api.novel.mockResolvedValue(NOVEL);
  api.corrections.mockResolvedValue({ summary: { total: 0, applied: 0, pending: 0, pending_actionable: 0, flags_open: 0, by_type: {} } });
  api.flag.mockResolvedValue({});
  promptSpy = jest.spyOn(window, 'prompt').mockImplementation(() => null);
  alertSpy = jest.spyOn(window, 'alert').mockImplementation(() => {});
});

afterEach(() => {
  expect(promptSpy).not.toHaveBeenCalled();
  expect(alertSpy).not.toHaveBeenCalled();
  promptSpy.mockRestore();
  alertSpy.mockRestore();
});

async function openReview() {
  render(
    <ToastProvider>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: ['/p/toy/review'] })} />
    </ToastProvider>
  );
  await screen.findByRole('heading', { name: /review desk/i });
}

test('flag: labelled field takes focus, empty note is rejected in place, valid note is sent', async () => {
  await openReview();
  const trigger = screen.getByRole('button', { name: /^flag this line:/i });
  trigger.focus();
  fireEvent.click(trigger);

  const field = await screen.findByRole('textbox', { name: /what looks wrong/i });
  expect(field).toHaveFocus();
  expect(screen.getByRole('dialog', { name: /flag this line/i })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Flag line' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/add a short note/i);
  expect(field).toHaveAttribute('aria-invalid', 'true');
  expect(api.flag).not.toHaveBeenCalled();

  fireEvent.change(field, { target: { value: 'speaker should be Hero' } });
  fireEvent.click(screen.getByRole('button', { name: 'Flag line' }));
  await waitFor(() =>
    expect(api.flag).toHaveBeenCalledWith('toy', expect.objectContaining({ spanId: 's1', note: 'speaker should be Hero' }))
  );
});

test('Escape cancels the dialog and returns focus to the button that opened it', async () => {
  await openReview();
  const trigger = screen.getByRole('button', { name: /^flag this line:/i });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByRole('textbox', { name: /what looks wrong/i });

  fireEvent.keyDown(window, { key: 'Escape' });
  await waitFor(() => expect(screen.queryByRole('dialog', { name: /flag this line/i })).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
});

test('add mention: text not in the line is explained inline; valid text opens the character picker', async () => {
  await openReview();
  fireEvent.click(screen.getByRole('button', { name: /add a mention in this line/i }));
  const field = await screen.findByRole('textbox', { name: /words in this line/i });
  expect(screen.getByText(LINE, { selector: 'p' })).toBeInTheDocument(); // the line is shown for context

  fireEvent.change(field, { target: { value: 'Nobody' } });
  fireEvent.click(screen.getByRole('button', { name: 'Choose character' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/is not in this line/i);

  fireEvent.change(field, { target: { value: 'The old man' } });
  fireEvent.click(screen.getByRole('button', { name: 'Choose character' }));
  expect(await screen.findByRole('dialog', { name: /choose a character/i })).toBeInTheDocument();
  expect(api.createMention).not.toHaveBeenCalled(); // nothing is sent until a character is chosen
});
