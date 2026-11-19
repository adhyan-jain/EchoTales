import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    listComic: jest.fn(),
    uploadComic: jest.fn(),
    triggerStage: jest.fn(),
    getJob: jest.fn(),
    outputFileUrl: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import ComicPanel from '../ComicPanel';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const mount = () =>
  render(
    <ToastProvider>
      <ComicPanel novelId="pc" />
    </ToastProvider>
  );

beforeEach(() => {
  jest.clearAllMocks();
  api.outputFileUrl.mockImplementation((id, path) => `/api/novels/${id}/output/file?path=${path}`);
  api.listComic.mockResolvedValue({ sources: [], videos: [] });
  api.triggerStage.mockResolvedValue({ job_id: 'j1', kind: 'comic', status: 'PENDING' });
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'SUCCEEDED' });
});

test('an empty project says so and offers the upload', async () => {
  mount();
  expect(await screen.findByText(/No comic uploaded to this project yet/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Upload comic' })).toBeDisabled();
});

test('uploading sends the file, then lists the stored comic; a refusal is shown', async () => {
  mount();
  await screen.findByText(/No comic uploaded/i);
  const file = new File(['x'], 'ep1.cbz');
  api.uploadComic.mockResolvedValue({ name: 'ep1', pages: 2, kind: 'images' });
  api.listComic.mockResolvedValue({ sources: [{ name: 'ep1', pages: 2, kind: 'images' }], videos: [] });
  fireEvent.change(screen.getByLabelText('Comic file'), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload comic' }));
  await waitFor(() => expect(api.uploadComic).toHaveBeenCalledWith('pc', file));
  expect(await screen.findByText('ep1')).toBeInTheDocument();
  expect(screen.getByText('2 pages')).toBeInTheDocument();

  api.uploadComic.mockRejectedValue(Object.assign(new Error('x'), { status: 400, serverMessage: 'unsafe path in the archive' }));
  fireEvent.change(screen.getByLabelText('Comic file'), { target: { files: [new File(['y'], 'bad.cbz')] } });
  fireEvent.click(screen.getByRole('button', { name: 'Upload comic' }));
  expect(await screen.findByText('unsafe path in the archive')).toBeInTheDocument();
});

test('Build queues the comic job for that source and then links the built video', async () => {
  api.listComic.mockResolvedValueOnce({ sources: [{ name: 'ep1', pages: 2, kind: 'images' }], videos: [] });
  api.listComic.mockResolvedValue({
    sources: [{ name: 'ep1', pages: 2, kind: 'images' }],
    videos: [{ path: 'video/ch1/v2_lama/episode.mp4', version: 'v2_lama' }],
  });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Build ep1' }));
  await waitFor(() =>
    expect(api.triggerStage).toHaveBeenCalledWith('pc', 'comic', { stage: 'build', source: 'ep1' })
  );
  const link = await screen.findByRole('link', { name: 'v2_lama' });
  expect(link).toHaveAttribute('href', '/api/novels/pc/output/file?path=video/ch1/v2_lama/episode.mp4');
});

test('a failed build is reported, not shown as built', async () => {
  api.listComic.mockResolvedValue({ sources: [{ name: 'ep1', pages: 2, kind: 'images' }], videos: [] });
  api.getJob.mockResolvedValue({ job_id: 'j1', status: 'FAILED', error_summary: 'OCR engine unavailable' });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Build ep1' }));
  expect(await screen.findByText(/OCR engine unavailable/)).toBeInTheDocument();
});
