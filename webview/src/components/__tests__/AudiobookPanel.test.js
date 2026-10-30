import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    listJobs: jest.fn(),
    getBible: jest.fn(),
    reviewLines: jest.fn(),
    listOutput: jest.fn(),
    triggerStage: jest.fn(),
    lockBible: jest.fn(),
    renderGenerate: jest.fn(),
    compute: jest.fn(),
    chapters: jest.fn(),
    outputFileUrl: jest.fn((novelId, path) => `/api/novels/${novelId}/output/file?path=${path}`),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import AudiobookPanel from '../AudiobookPanel';
// eslint-disable-next-line import/first
import GenerationWorkspace from '../GenerationWorkspace';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

const project = { id: 'b', source_uploaded: true, ingested: true, chapter_count: 3 };

function mount(overrides = {}) {
  api.listJobs.mockResolvedValue(overrides.jobs || []);
  api.getBible.mockResolvedValue(overrides.bible || { current: { locked_version: null, dirty: true, stale_reason: null } });
  api.reviewLines.mockResolvedValue(overrides.queue || { total: 4, items: [] });
  api.listOutput.mockResolvedValue(overrides.output || { kinds: { audio: [] } });
  api.triggerStage.mockResolvedValue({ job_id: 'x' });
  api.lockBible.mockResolvedValue({});
  // CRA's jest config resets mock implementations between tests, so this is set here and not in the factory.
  api.outputFileUrl.mockImplementation((novelId, path) => `/api/novels/${novelId}/output/file?path=${path}`);
  return render(
    <MemoryRouter>
      <ToastProvider>
        <AudiobookPanel novelId="b" project={overrides.project || project} />
      </ToastProvider>
    </MemoryRouter>
  );
}

beforeEach(() => jest.clearAllMocks());

describe('AudiobookPanel', () => {
  test('voicing with a real engine is not offered until the canon is locked', async () => {
    mount();
    expect(await screen.findByText(/4 lines have no confirmed speaker/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voice' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Make M4B' })).toBeDisabled();
  });

  test('once locked, voicing starts a voice job with the chosen engine', async () => {
    mount({ bible: { current: { locked_version: 2, dirty: false, stale_reason: null } }, queue: { total: 0, items: [] } });
    expect(await screen.findByText(/Locked as version 2/i)).toBeInTheDocument();
    const voice = screen.getByRole('button', { name: 'Voice' });
    await waitFor(() => expect(voice).toBeEnabled());
    fireEvent.click(voice);
    await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'voice', { engine: 'chatterbox' }));
  });

  test('the first step starts the whole pipeline job', async () => {
    mount({ project: { id: 'b', source_uploaded: true, ingested: false, chapter_count: 0 } });
    fireEvent.click(await screen.findByRole('button', { name: 'Build' }));
    await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'pipeline', {}));
  });

  test('a stale build explains itself instead of offering to lock', async () => {
    mount({ bible: { current: { locked_version: null, dirty: true, stale_reason: 'built by older code' } } });
    expect(await screen.findByText(/Cannot lock yet: built by older code/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lock' })).toBeDisabled();
  });

  test('a finished audiobook is offered as a download', async () => {
    mount({
      jobs: [{ job_id: 'v', kind: 'voice', status: 'SUCCEEDED', created_at: 2 }],
      bible: { current: { locked_version: 1, dirty: false, stale_reason: null } },
      output: { kinds: { audio: [{ path: 'audio/b.m4b', mtime: 5, size: 10 }] } },
    });
    expect(await screen.findByRole('link', { name: /Download/i })).toHaveAttribute('href', expect.stringContaining('b.m4b'));
  });

  test('a failed job shows why', async () => {
    mount({ jobs: [{ job_id: 'p', kind: 'pipeline', status: 'FAILED', created_at: 1, error_summary: 'ollama is not running' }] });
    expect(await screen.findByText(/ollama is not running/i)).toBeInTheDocument();
  });
});

describe('GenerationWorkspace detail option', () => {
  test('the chosen detail level is sent with the render request', async () => {
    api.compute.mockResolvedValue({
      mode: 'local-low', engines: ['stub'], refusals: {}, scenes: { preview: 3, full: 70 }, default_tier: 'preview',
      densities: { beat: { images_per_scene: 3.3, measured: true }, dense: { images_per_scene: 13.2, measured: false } },
      gpu: { available: false },
    });
    api.chapters.mockResolvedValue([{ number: 1 }]);
    api.listJobs.mockResolvedValue([]);
    api.renderGenerate.mockResolvedValue({ job_id: 'r' });
    render(
      <ToastProvider>
        <GenerationWorkspace novelId="b" hideHeader />
      </ToastProvider>
    );
    fireEvent.change(await screen.findByLabelText('Detail'), { target: { value: 'dense' } });
    await waitFor(() => expect(screen.getByRole('button', { name: /Generate panels/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /Generate panels/i }));
    await waitFor(() =>
      expect(api.renderGenerate).toHaveBeenCalledWith('b', expect.objectContaining({ density: 'dense', engine: 'stub' }))
    );
  });
});
