import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: { listCompanions: jest.fn(), triggerStage: jest.fn(), getJob: jest.fn(), companionUrl: jest.fn() },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import CompanionPanel from '../CompanionPanel';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const mount = () =>
  render(
    <ToastProvider>
      <CompanionPanel novelId="b" project={{ id: 'b', ingested: true, chapter_count: 12 }} />
    </ToastProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  api.listCompanions.mockResolvedValue({ companions: [] });
  api.triggerStage.mockResolvedValue({ job_id: 'j1', status: 'PENDING' });
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'SUCCEEDED' });
  api.companionUrl.mockImplementation((novelId, through) => `/api/novels/${novelId}/companion/through_${through}/index.html`);
});

test('building queues a companion job through the chapter typed, and the built page then gets a link', async () => {
  mount();
  await screen.findByText(/No companion built yet/i);
  fireEvent.change(screen.getByLabelText('Last chapter you have finished'), { target: { value: '7' } });
  api.listCompanions.mockResolvedValue({ companions: [{ through: 7, built_at: 5 }] });
  fireEvent.click(screen.getByRole('button', { name: 'Build companion through chapter 7' }));
  await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'companion', { through: 7 }));
  const link = await screen.findByRole('link', { name: /Open the companion through chapter 7/ });
  expect(link).toHaveAttribute('href', '/api/novels/b/companion/through_7/index.html');
  expect(link).toHaveAttribute('target', '_blank');
});

test('a chapter that is not a positive number cannot be built', async () => {
  mount();
  await screen.findByText(/No companion built yet/i);
  const input = screen.getByLabelText('Last chapter you have finished');
  fireEvent.change(input, { target: { value: '0' } });
  expect(screen.getByRole('button', { name: /Build companion/ })).toBeDisabled();
  fireEvent.change(input, { target: { value: '' } });
  expect(screen.getByRole('button', { name: /Build companion/ })).toBeDisabled();
});

test('already built companions are listed with a link each', async () => {
  api.listCompanions.mockResolvedValue({ companions: [{ through: 3, built_at: 1 }, { through: 9, built_at: 2 }] });
  mount();
  expect(await screen.findByRole('link', { name: /through chapter 3/ })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /through chapter 9/ })).toBeInTheDocument();
});

test('a failed build says so and shows the reason', async () => {
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'FAILED', error_summary: 'chapter 7 is not in this book' });
  mount();
  await screen.findByText(/No companion built yet/i);
  fireEvent.click(screen.getByRole('button', { name: /Build companion/ }));
  expect(await screen.findByText(/chapter 7 is not in this book/)).toBeInTheDocument();
});
