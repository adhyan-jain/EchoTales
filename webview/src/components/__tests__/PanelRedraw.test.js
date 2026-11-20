import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    listPanels: jest.fn(),
    redrawPanel: jest.fn(),
    choosePanelCandidate: jest.fn(),
    // The real helper adds the session token; the test marks that it was used.
    mediaUrl: jest.fn((u) => `${u}&access_token=T`),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import PanelRedraw from '../PanelRedraw';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const listing = (chosen = 'original') => ({
  version: 'v1_stub',
  panels: [
    {
      panel_id: 't:1:0',
      panel_seq: 0,
      chosen,
      direction: '',
      candidates: [
        { id: 'original', round: 0, direction: '', path: 'panels/ch1/v1_stub/a.png' },
        { id: 'r1c0', round: 1, direction: 'closer', path: 'panels/ch1/v1_stub/regen/0/r1c0.png' },
      ],
    },
  ],
});

const renderIt = (props = {}) =>
  render(
    <ToastProvider>
      <PanelRedraw novelId="t" chapter="1" engine="stub" jobs={[]} {...props} />
    </ToastProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  api.mediaUrl.mockImplementation((u) => `${u}&access_token=T`);
});

test('shows each panel and its candidates, with pictures loaded through mediaUrl', async () => {
  api.listPanels.mockResolvedValue(listing());
  renderIt();
  expect(await screen.findByText('Panel 0')).toBeInTheDocument();
  const img = screen.getByAltText('Candidate r1c0 of panel 0');
  expect(img.getAttribute('src')).toContain('access_token=T');
  expect(img.getAttribute('src')).toContain('regen%2F0%2Fr1c0.png');
  expect(screen.getByText('Original')).toBeInTheDocument();
});

test('Redraw queues a render job for that panel with the edited direction', async () => {
  api.listPanels.mockResolvedValue(listing());
  api.redrawPanel.mockResolvedValue({ job_id: 'j1' });
  const onQueued = jest.fn();
  renderIt({ onQueued });
  fireEvent.change(await screen.findByLabelText('Direction for the redraw'), { target: { value: ' she looks up ' } });
  fireEvent.click(screen.getByRole('button', { name: 'Redraw panel 0' }));
  await waitFor(() => expect(api.redrawPanel).toHaveBeenCalled());
  expect(api.redrawPanel).toHaveBeenCalledWith('t', {
    chapter: 1,
    panel_id: 't:1:0',
    version: 'v1_stub',
    engine: 'stub',
    direction: 'she looks up',
  });
  await waitFor(() => expect(onQueued).toHaveBeenCalled());
});

test('Use this saves the pick and reloads the panel', async () => {
  api.listPanels.mockResolvedValueOnce(listing()).mockResolvedValueOnce(listing('r1c0'));
  api.choosePanelCandidate.mockResolvedValue({});
  renderIt();
  fireEvent.click(await screen.findByRole('button', { name: /Use this r1c0 for panel 0/ }));
  await waitFor(() =>
    expect(api.choosePanelCandidate).toHaveBeenCalledWith('t', {
      chapter: 1,
      panel_id: 't:1:0',
      candidate_id: 'r1c0',
      version: 'v1_stub',
    })
  );
  expect(await screen.findByText('Using r1c0')).toBeInTheDocument();
});

test('says why there is nothing to redraw when the chapter has no render', async () => {
  api.listPanels.mockRejectedValue(new Error('chapter 1 has no rendered panels with a plan; render it first'));
  renderIt();
  expect(await screen.findByText('No panels to work on yet')).toBeInTheDocument();
});

test('reloads when a job finishes so new candidates appear', async () => {
  api.listPanels.mockResolvedValue(listing());
  const { rerender } = renderIt({ jobs: [{ job_id: 'j1', status: 'RUNNING' }] });
  await screen.findByText('Panel 0');
  rerender(
    <ToastProvider>
      <PanelRedraw novelId="t" chapter="1" engine="stub" jobs={[{ job_id: 'j1', status: 'SUCCEEDED' }]} />
    </ToastProvider>
  );
  await waitFor(() => expect(api.listPanels).toHaveBeenCalledTimes(2));
});
