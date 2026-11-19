import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: { listPacks: jest.fn(), uploadPack: jest.fn(), triggerStage: jest.fn(), getJob: jest.fn() },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import PacksPanel from '../PacksPanel';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const mount = () =>
  render(
    <ToastProvider>
      <PacksPanel novelId="b" />
    </ToastProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  api.listPacks.mockResolvedValue({ packs: [] });
  api.triggerStage.mockResolvedValue({ job_id: 'j1', kind: 'pack_export', status: 'PENDING' });
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'SUCCEEDED' });
});

test('lists the packs in the project folder by name', async () => {
  api.listPacks.mockResolvedValue({ packs: [{ name: 'mine.etpack', bytes: 2048, report: null }] });
  mount();
  expect(await screen.findByText('mine.etpack')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Import mine.etpack' })).toBeEnabled();
});

test('an empty folder says so and still offers export', async () => {
  mount();
  expect(await screen.findByText(/No packs in this project yet/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Export pack' })).toBeEnabled();
});

test('Export pack queues a pack_export job with the chosen name, then reloads the list', async () => {
  mount();
  await screen.findByText(/No packs in this project yet/i);
  fireEvent.change(screen.getByLabelText('Pack name'), { target: { value: 'my-cast' } });
  api.listPacks.mockResolvedValue({ packs: [{ name: 'my-cast.etpack', bytes: 10, report: null }] });
  fireEvent.click(screen.getByRole('button', { name: 'Export pack' }));
  await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'pack_export', { name: 'my-cast' }));
  expect(await screen.findByText('my-cast.etpack')).toBeInTheDocument();
});

test('Import queues pack_import for that pack and shows applied and skipped counts when it ends', async () => {
  api.listPacks.mockResolvedValueOnce({ packs: [{ name: 'mine.etpack', bytes: 2048, report: null }] });
  // Every read after the first one (the reload once the job ends) carries the report the server wrote.
  api.listPacks.mockResolvedValue({
    packs: [
      {
        name: 'mine.etpack',
        bytes: 2048,
        report: {
          applied: { cast: 3, appearance: 2 },
          skipped: [{ kind: 'cast', reason: 'chapter text differs or is missing here', chapter: 2, what: 'Mira' }],
        },
      },
    ],
  });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Import mine.etpack' }));
  await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'pack_import', { name: 'mine.etpack' }));
  const report = await screen.findByLabelText('Import report for mine.etpack');
  expect(report).toHaveTextContent('Applied 5');
  expect(report).toHaveTextContent('Skipped 1');
  expect(report).toHaveTextContent('chapter text differs or is missing here');
});

test('a failed import job is reported, not shown as applied', async () => {
  api.listPacks.mockResolvedValue({ packs: [{ name: 'mine.etpack', bytes: 1, report: null }] });
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'FAILED', error_summary: 'not a readable pack' });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Import mine.etpack' }));
  expect(await screen.findByText(/not a readable pack/)).toBeInTheDocument();
});

test('uploading a pack sends the file and refreshes the list; a refusal is shown', async () => {
  mount();
  await screen.findByText(/No packs in this project yet/i);
  const file = new File(['x'], 'theirs.etpack');
  api.uploadPack.mockResolvedValue({ name: 'theirs.etpack', bytes: 1 });
  api.listPacks.mockResolvedValue({ packs: [{ name: 'theirs.etpack', bytes: 1, report: null }] });
  fireEvent.change(screen.getByLabelText('Pack file'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload pack' }));
  await waitFor(() => expect(api.uploadPack).toHaveBeenCalledWith('b', file));
  expect(await screen.findByText('theirs.etpack')).toBeInTheDocument();

  api.uploadPack.mockRejectedValue(Object.assign(new Error('x'), { status: 400, serverMessage: 'not a readable .etpack file' }));
  fireEvent.change(screen.getByLabelText('Pack file'), { target: { files: [new File(['y'], 'bad.etpack')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload pack' }));
  expect(await screen.findByText('not a readable .etpack file')).toBeInTheDocument();
});
