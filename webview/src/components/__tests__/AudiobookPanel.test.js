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
  (overrides.reject || []).forEach((name) => api[name].mockRejectedValueOnce(new Error('down')));
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

  test('a failed jobs read does not re-enable the action buttons, and says so', async () => {
    mount({ reject: ['listJobs'], bible: { current: { locked_version: 2, dirty: false, stale_reason: null } }, queue: { total: 0, items: [] } });
    expect(await screen.findByText(/Could not check whether a job is running/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Rebuild' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Voice' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Lock' })).toBeDisabled();
  });

  test('a failed review-lines read is not "Checking the queue…" forever', async () => {
    mount({ reject: ['reviewLines'] });
    expect(await screen.findByText('Could not check the queue.')).toBeInTheDocument();
    expect(screen.queryByText('Checking the queue…')).not.toBeInTheDocument();
  });

  test('a failed bible read is unknown, not "not locked" with Lock enabled', async () => {
    mount({ reject: ['getBible'] });
    expect(await screen.findByText('Could not read the canon state.')).toBeInTheDocument();
    expect(screen.queryByText(/Freezes the reviewed cast/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Lock' })).toBeDisabled();
  });

  test('Check again re-reads and clears the warning once the server answers', async () => {
    mount({ reject: ['listJobs'] });
    fireEvent.click(await screen.findByRole('button', { name: 'Check again' }));
    await waitFor(() => expect(screen.queryByText(/Could not check/i)).not.toBeInTheDocument());
  });

  test('a failed job shows why', async () => {
    mount({ jobs: [{ job_id: 'p', kind: 'pipeline', status: 'FAILED', created_at: 1, error_summary: 'ollama is not running' }] });
    expect(await screen.findByText(/ollama is not running/i)).toBeInTheDocument();
  });

  test('an interrupted job shows why, so the user knows to run it again', async () => {
    mount({ jobs: [{ job_id: 'i', kind: 'pipeline', status: 'INTERRUPTED', created_at: 1, error_summary: 'server restarted while queued' }] });
    expect(await screen.findByText(/server restarted while queued/i)).toBeInTheDocument();
  });

  const estimate = {
    chapters: 3, seconds: 5400, cost_usd: 0, measured: false,
    stages: [
      { stage: '0 ingest', seconds: 60, seconds_per_chapter: 20, basis: 'measured' },
      { stage: '6b reader', seconds: 5340, seconds_per_chapter: 1780, basis: 'estimate' },
    ],
  };

  test('a running build shows its estimate per stage, labelled measured or estimate, with the total', async () => {
    mount({ jobs: [{ job_id: 'p', kind: 'pipeline', status: 'RUNNING', created_at: 1, estimate }] });
    const box = await screen.findByLabelText('Run estimate');
    expect(box).toHaveTextContent('0 ingest');
    expect(box).toHaveTextContent('1 min');
    expect(box).toHaveTextContent('measured');
    expect(box).toHaveTextContent('6b reader');
    expect(box).toHaveTextContent('89 min');
    expect(box).toHaveTextContent('estimate');
    expect(box).toHaveTextContent(/Total about 90 min for 3 chapters/);
    expect(box).toHaveTextContent(/includes estimates/);
  });

  test('a finished build no longer shows the estimate', async () => {
    mount({ jobs: [{ job_id: 'p', kind: 'pipeline', status: 'SUCCEEDED', created_at: 1, estimate }] });
    await screen.findByText('SUCCEEDED');
    expect(screen.queryByLabelText('Run estimate')).not.toBeInTheDocument();
  });

  test('a cancelled job shows no failure text', async () => {
    mount({ jobs: [{ job_id: 'c', kind: 'pipeline', status: 'CANCELLED', created_at: 1, error_summary: 'withdrawn by user' }] });
    expect(await screen.findByText('CANCELLED')).toBeInTheDocument();
    expect(screen.queryByText(/withdrawn by user/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/did not finish/i)).not.toBeInTheDocument();
  });
});

describe('AudiobookPanel video step', () => {
  const voicedJobs = [{ job_id: 'v', kind: 'voice', status: 'SUCCEEDED', created_at: 2 }];
  const locked = { current: { locked_version: 1, dirty: false, stale_reason: null } };

  test('Make video is off until the book is voiced', async () => {
    mount();
    expect(await screen.findByRole('button', { name: 'Make video' })).toBeDisabled();
  });

  test('starts a video job with the chapters, engine and prune choice', async () => {
    mount({ jobs: voicedJobs, bible: locked });
    fireEvent.change(await screen.findByLabelText('Video chapters'), { target: { value: '1, 2' } });
    fireEvent.change(screen.getByLabelText('Video engine'), { target: { value: 'stills' } });
    fireEvent.click(screen.getByLabelText(/Cut narration the picture shows/i));
    const button = screen.getByRole('button', { name: 'Make video' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() =>
      expect(api.triggerStage).toHaveBeenCalledWith('b', 'video', { chapters: [1, 2], engine: 'stills', prune_visual_narration: true })
    );
  });

  test('the animated engine cannot be combined with pruning', async () => {
    mount({ jobs: voicedJobs, bible: locked });
    fireEvent.change(await screen.findByLabelText('Video engine'), { target: { value: 'ltx-local' } });
    expect(screen.getByLabelText(/Cut narration the picture shows/i)).toBeDisabled();
  });

  test('a refused video job shows the server message, not a bare failure', async () => {
    mount({
      jobs: [...voicedJobs, { job_id: 'm', kind: 'video', status: 'FAILED', created_at: 3, error_summary: 'no panel version of chapter 1; render it first' }],
      bible: locked,
    });
    expect(await screen.findByText(/Could not make the video: no panel version of chapter 1/i)).toBeInTheDocument();
  });

  test('a finished video is playable and downloadable', async () => {
    mount({
      jobs: voicedJobs,
      bible: locked,
      output: { kinds: { audio: [], video: [{ path: 'video/ch1/v1_x/chapter.mp4', mtime: 5, size: 10 }] } },
    });
    const player = await screen.findByLabelText('Latest chapter video');
    expect(player).toHaveAttribute('src', expect.stringContaining('chapter.mp4'));
  });
});

describe('AudiobookPanel M4B, pages and episode steps', () => {
  const voicedJobs = [{ job_id: 'v', kind: 'voice', status: 'SUCCEEDED', created_at: 2 }];
  const locked = { current: { locked_version: 1, dirty: false, stale_reason: null } };
  const panels = { kinds: { audio: [], panels: [{ path: 'panels/ch1/v1/p.png', mtime: 1, size: 1 }] } };

  test('Make M4B is off with a hint while the audio is the silent stub', async () => {
    mount({ jobs: voicedJobs, bible: locked, project: { ...project, audio_engine: 'stub' } });
    expect(await screen.findByRole('button', { name: 'Make M4B' })).toBeDisabled();
    expect(screen.getByText(/voice it with chatterbox first/i)).toBeInTheDocument();
  });

  test('Make M4B stays on for real audio', async () => {
    mount({ jobs: voicedJobs, bible: locked, project: { ...project, audio_engine: 'chatterbox' } });
    const button = await screen.findByRole('button', { name: 'Make M4B' });
    await waitFor(() => expect(button).toBeEnabled());
  });

  test('Make pages sends the chosen format and the CBZ and PDF exports', async () => {
    mount({ output: panels });
    fireEvent.change(await screen.findByLabelText('Page format'), { target: { value: 'webtoon' } });
    const button = screen.getByRole('button', { name: 'Make pages' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() =>
      expect(api.triggerStage).toHaveBeenCalledWith('b', 'pages', { chapters: [1], format: 'webtoon', export: 'png,cbz,pdf' })
    );
  });

  test('Make pages is off until there are panels, and finished pages are downloadable', async () => {
    mount();
    expect(await screen.findByRole('button', { name: 'Make pages' })).toBeDisabled();
  });

  test('the finished CBZ and PDF are linked', async () => {
    mount({
      output: { kinds: { audio: [], panels: [], pages: [
        { path: 'pages/ch1/v1_x/ch1.cbz', mtime: 5, size: 1 },
        { path: 'pages/ch1/v1_x/ch1.pdf', mtime: 5, size: 1 },
        { path: 'pages/ch1/v1_x/page_01.png', mtime: 5, size: 1 },
      ] } },
    });
    expect(await screen.findByRole('link', { name: /Pages \(CBZ\)/ })).toHaveAttribute('href', expect.stringContaining('ch1.cbz'));
    expect(screen.getByRole('link', { name: /Pages \(PDF\)/ })).toHaveAttribute('href', expect.stringContaining('ch1.pdf'));
  });

  test('Make episode starts an episode job and needs the voiced book', async () => {
    mount();
    expect(await screen.findByRole('button', { name: 'Make episode' })).toBeDisabled();
  });

  test('Make episode sends the chapters', async () => {
    mount({ jobs: voicedJobs, bible: locked });
    const button = await screen.findByRole('button', { name: 'Make episode' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(api.triggerStage).toHaveBeenCalledWith('b', 'episode', { chapters: [1] }));
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
