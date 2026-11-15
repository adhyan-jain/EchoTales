import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    listReviewItems: jest.fn(),
    decideReviewItem: jest.fn(),
    reopenReviewItem: jest.fn(),
    corrections: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import NamesToCheck from '../NamesToCheck';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const ENTITIES = [{ id: 't:self:9', label: 'Other Person' }];
const ID = 'resolve_deferred:orv:m1:abc';

const item = (over = {}) => ({
  id: ID,
  chapter: 4,
  kind: 'resolve_deferred',
  message: "'Angelica' (2 mention(s)) left unlinked: p=0.409 in deferred band",
  resolved: false,
  resolution: null,
  decision_state: 'open',
  candidates: [
    { role: 'group', surfaces: ['Angelica'], mention_ids: ['m1', 'm2'], reason_kind: 'tie_margin', excerpt: 'Angelica smiled at him.' },
    { role: 'candidate', target_id: 't:self:1', label: 'Madam Angelica', probability: 0.409, retrieval_score: 0.5 },
    { role: 'candidate', target_id: 't:self:2', label: 'Angel', probability: 0.2, retrieval_score: 0.3 },
  ],
  ...over,
});

const decided = (resolution, state = 'decided_pending_apply') => item({ resolved: true, resolution, decision_state: state });
const listing = (...items) => ({ items, total: items.length, open: items.filter((i) => i.decision_state === 'open').length });

const renderIt = () =>
  render(
    <ToastProvider>
      <NamesToCheck novelId="orv" entities={ENTITIES} />
    </ToastProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  api.corrections.mockResolvedValue({ summary: { pending: 0, pending_actionable: 0 }, items: [] });
});

describe('NamesToCheck', () => {
  test('lists the item with count, reason, excerpt and candidate percentages', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    renderIt();
    expect(await screen.findByText('Angelica')).toBeInTheDocument();
    expect(screen.getByText('1 name to check')).toBeInTheDocument();
    expect(screen.getByText('2 mentions')).toBeInTheDocument();
    expect(screen.getByText('Two characters fit about equally.')).toBeInTheDocument();
    expect(screen.getByText(/Angelica smiled at him/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Madam Angelica · 41%' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Angel · 20%' })).toBeInTheDocument();
    expect(api.listReviewItems).toHaveBeenCalledWith('orv', { kind: 'resolve_deferred' });
  });

  test('clicking a candidate posts a link and shows the pending state and count', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    api.decideReviewItem.mockResolvedValue({
      item: decided('human:link:t:self:1'),
      correction_ids: ['c1', 'c2'],
      summary: { pending: 2, pending_actionable: 2 },
    });
    renderIt();
    fireEvent.click(await screen.findByRole('button', { name: 'Madam Angelica · 41%' }));
    await waitFor(() => expect(api.decideReviewItem).toHaveBeenCalledWith('orv', ID, { action: 'link', target_id: 't:self:1' }));
    expect(await screen.findByText('Linked to Madam Angelica, pending Apply')).toBeInTheDocument();
    expect(screen.getByText(/2 corrections waiting for Apply/)).toBeInTheDocument();
    expect(screen.getByText('0 names to check')).toBeInTheDocument();
  });

  test('New character posts the edited name', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    api.decideReviewItem.mockResolvedValue({
      item: decided('human:new:Angelica Vale'),
      correction_ids: ['c1'],
      summary: { pending: 1, pending_actionable: 1 },
    });
    renderIt();
    const input = await screen.findByLabelText('Name for a new character from Angelica');
    expect(input).toHaveValue('Angelica');
    fireEvent.change(input, { target: { value: 'Angelica Vale' } });
    fireEvent.click(screen.getByRole('button', { name: 'New character' }));
    await waitFor(() => expect(api.decideReviewItem).toHaveBeenCalledWith('orv', ID, { action: 'new', label: 'Angelica Vale' }));
    expect(await screen.findByText('New character "Angelica Vale", pending Apply')).toBeInTheDocument();
  });

  test('Not a character posts a dismiss', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    api.decideReviewItem.mockResolvedValue({
      item: decided('human:dismiss', 'dismissed'),
      correction_ids: [],
      summary: { pending: 0, pending_actionable: 0 },
    });
    renderIt();
    fireEvent.click(await screen.findByRole('button', { name: 'Not a character' }));
    await waitFor(() => expect(api.decideReviewItem).toHaveBeenCalledWith('orv', ID, { action: 'dismiss' }));
    expect(await screen.findByText('Marked as not a character')).toBeInTheDocument();
  });

  test('Undo calls reopen and the row is decidable again', async () => {
    api.listReviewItems.mockResolvedValue(listing(decided('human:link:t:self:1')));
    api.reopenReviewItem.mockResolvedValue({ item: item(), removed: ['c1', 'c2'], summary: { pending: 0, pending_actionable: 0 } });
    renderIt();
    fireEvent.click(await screen.findByRole('button', { name: 'Undo the decision for Angelica' }));
    await waitFor(() => expect(api.reopenReviewItem).toHaveBeenCalledWith('orv', ID));
    expect(await screen.findByRole('button', { name: 'Madam Angelica · 41%' })).toBeInTheDocument();
  });

  test('an applied decision has no Undo', async () => {
    api.listReviewItems.mockResolvedValue(listing(decided('human:link:t:self:1', 'applied')));
    renderIt();
    expect(await screen.findByText('Linked to Madam Angelica')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Undo/ })).not.toBeInTheDocument();
  });

  test('a failed load shows an error with retry, not "No names to check"', async () => {
    api.listReviewItems.mockRejectedValueOnce(new Error('boom'));
    renderIt();
    expect(await screen.findByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByText('No names to check.')).not.toBeInTheDocument();
    api.listReviewItems.mockResolvedValueOnce(listing(item()));
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Angelica')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  test('an empty queue says so', async () => {
    api.listReviewItems.mockResolvedValue(listing());
    renderIt();
    expect(await screen.findByText('No names to check.')).toBeInTheDocument();
  });

  test('a double click posts once', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    let finish;
    api.decideReviewItem.mockReturnValue(new Promise((r) => (finish = r)));
    renderIt();
    const btn = await screen.findByRole('button', { name: 'Madam Angelica · 41%' });
    fireEvent.click(btn);
    fireEvent.click(btn);
    fireEvent.click(screen.getByRole('button', { name: 'Not a character' }));
    expect(api.decideReviewItem).toHaveBeenCalledTimes(1);
    finish({ item: decided('human:link:t:self:1'), summary: { pending: 2, pending_actionable: 2 } });
    await screen.findByText('Linked to Madam Angelica, pending Apply');
  });

  test('a failed decision keeps the row open and decidable', async () => {
    api.listReviewItems.mockResolvedValue(listing(item()));
    api.decideReviewItem.mockRejectedValue(new Error('nope'));
    renderIt();
    fireEvent.click(await screen.findByRole('button', { name: 'Angel · 20%' }));
    await waitFor(() => expect(api.decideReviewItem).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', { name: 'Angel · 20%' })).toBeEnabled());
  });
});
