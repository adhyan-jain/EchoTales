import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    characters: jest.fn(),
    reviewLines: jest.fn(),
    reassignSpeaker: jest.fn(),
    characterTimeline: jest.fn(),
    getBible: jest.fn(),
    lockBible: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import BibleReview from '../BibleReview';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const renderIt = () =>
  render(
    <ToastProvider>
      <BibleReview novelId="orv" />
    </ToastProvider>
  );

const bible = (current, locks = []) => ({
  current: { digest: 'd', pipeline_version: 'p1', stale_reason: null, dirty: false, changed_chapters: [], locked_version: null, ...current },
  locks,
});

beforeEach(() => {
  jest.clearAllMocks();
  api.characters.mockResolvedValue({ characters: [{ self_id: 'orv:self:1', label: 'Dokja' }] });
});

describe('BibleReview', () => {
  test('queue renders and reassigning calls reassignSpeaker then refetches', async () => {
    api.reviewLines.mockResolvedValue({
      total: 1,
      items: [{ span_id: 's1', chapter: 3, block_index: 7, text: 'Hello there', speaker_id: null, speaker_label: null, method: 'llm', confidence: 0.3, reason: 'role_slot', affected: 12 }],
    });
    api.reassignSpeaker.mockResolvedValue({});
    renderIt();
    expect(await screen.findByText(/affects 12 lines/)).toBeInTheDocument();
    expect(screen.getByText('role slot')).toBeInTheDocument();
    expect(screen.getByText('unnamed')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Change speaker'));
    fireEvent.click(await screen.findByText('Dokja'));
    await waitFor(() => expect(api.reassignSpeaker).toHaveBeenCalledWith('orv', 's1', 3, 'orv:self:1'));
    await waitFor(() => expect(api.reviewLines).toHaveBeenCalledTimes(2));
  });

  test('timeline shows story-vs-learned difference', async () => {
    api.reviewLines.mockResolvedValue({ total: 0, items: [] });
    api.characterTimeline.mockResolvedValue({
      self_id: 'orv:self:1',
      label: 'Dokja',
      personas: [{ persona_id: 'p1', from_chapter: 1, to_chapter: null }],
      looks: [{ persona_id: 'p1', key: 'hair', value: 'black', from_chapter: 2, evidence: 'his black hair', confidence: 0.9, asserted_by: 'llm' }],
      identities: [{ alias: 'Reader King', alias_type: 'TRANSFERABLE_TITLE', story_from: 1, story_to: null, learned_chapter: 6, evidence: 'the king' }],
    });
    renderIt();
    fireEvent.click(screen.getByText('Character timeline'));
    await waitFor(() => expect(api.characters).toHaveBeenCalled());
    fireEvent.change(await screen.findByLabelText('Character'), { target: { value: 'orv:self:1' } });
    expect(await screen.findByText('held since ch 1, learned ch 6')).toBeInTheDocument();
    expect(api.characterTimeline).toHaveBeenCalledWith('orv', 'orv:self:1');
    expect(screen.getByText('hair')).toBeInTheDocument();
  });

  test('lock is disabled when stale and shows the reason', async () => {
    api.reviewLines.mockResolvedValue({ total: 0, items: [] });
    api.getBible.mockResolvedValue(bible({ stale_reason: 'Resolver changed since build' }));
    renderIt();
    fireEvent.click(screen.getByText('Lock'));
    expect(await screen.findByText('Resolver changed since build')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Lock canon v1/ })).toBeDisabled();
  });

  test('lock calls lockBible with the note when not stale', async () => {
    api.reviewLines.mockResolvedValue({ total: 0, items: [] });
    api.getBible.mockResolvedValue(bible({}, [{ version: 1, created_at: 't', note: 'first', pipeline_version: 'p1', counts: { lines: 1, attributes: 2, aliases: 3, entities: 4 } }]));
    api.lockBible.mockResolvedValue({ version: 2, changed_chapters: [3] });
    renderIt();
    fireEvent.click(screen.getByText('Lock'));
    const btn = await screen.findByRole('button', { name: /Lock canon v2/ });
    expect(btn).toBeEnabled();
    fireEvent.change(screen.getByLabelText('Lock note'), { target: { value: 'after review' } });
    fireEvent.click(btn);
    await waitFor(() => expect(api.lockBible).toHaveBeenCalledWith('orv', 'after review'));
  });

  test('a failed first load is an error with a retry, not "Nothing to check"', async () => {
    api.reviewLines.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500 })).mockResolvedValue({ total: 0, items: [] });
    renderIt();
    expect(await screen.findAllByText(/server hit a problem/i)).not.toHaveLength(0);
    expect(screen.queryByText(/Nothing to check/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/Nothing to check/)).toBeInTheDocument();
  });

  test('an older, slower response cannot overwrite the newest one', async () => {
    let resolveSlow;
    const item = (id) => ({ span_id: id, chapter: 1, block_index: 1, text: id, speaker_label: null, method: 'llm', confidence: 0.3, reason: 'unnamed', affected: 1 });
    api.reviewLines
      .mockResolvedValueOnce({ total: 0, items: [] }) // initial, chapter all
      .mockImplementationOnce(() => new Promise((r) => { resolveSlow = r; })) // chapter 1: slow
      .mockResolvedValueOnce({ total: 1, items: [item('fast-line')] }); // chapter 12: fast
    renderIt();
    await waitFor(() => expect(api.reviewLines).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText('Chapter'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Chapter'), { target: { value: '12' } });
    expect(await screen.findByText('fast-line')).toBeInTheDocument();
    resolveSlow({ total: 1, items: [item('slow-line')] });
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText('slow-line')).not.toBeInTheDocument();
    expect(screen.getByText('fast-line')).toBeInTheDocument();
  });

  test('the lock panel shows an error with retry instead of Loading forever', async () => {
    api.reviewLines.mockResolvedValue({ total: 0, items: [] });
    api.getBible.mockRejectedValueOnce(Object.assign(new Error('x'), { status: 500 })).mockResolvedValue(bible({}));
    renderIt();
    fireEvent.click(screen.getByText('Lock'));
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/Not locked yet/)).toBeInTheDocument();
  });

  test('a failed character fetch is reported', async () => {
    api.reviewLines.mockResolvedValue({ total: 0, items: [] });
    api.characters.mockRejectedValue(Object.assign(new Error('x'), { status: 0 }));
    renderIt();
    expect(await screen.findByText(/speaker choices will be incomplete|reach the EchoTales server/i)).toBeInTheDocument();
  });
});
