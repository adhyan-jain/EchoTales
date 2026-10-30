import React from 'react';
import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

// Product Orchestration track UI: the three new screens this session added
// (ProjectHome, OutputLibrary, GenerationWorkspace) plus TimelineRail's
// honest "not yet available" state -- covering empty/real/error rendering
// the same way Section7Smoke.test.js already does for CharacterDashboard.

jest.mock('../../api', () => ({
  api: {
    listProjects: jest.fn(),
    listOutput: jest.fn(),
    listJobs: jest.fn(),
    renderGenerate: jest.fn(),
    compute: jest.fn(),
    novel: jest.fn(),
    chapters: jest.fn(),
    outputFileUrl: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import ProjectHome from '../ProjectHome';
// eslint-disable-next-line import/first
import OutputLibrary from '../OutputLibrary';
// eslint-disable-next-line import/first
import GenerationWorkspace from '../GenerationWorkspace';
// eslint-disable-next-line import/first
import TimelineRail from '../ui/TimelineRail';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

function withToast(node) {
  return render(<ToastProvider>{node}</ToastProvider>);
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('TimelineRail', () => {
  test('renders the honest not-yet-available state when there is no epoch data', () => {
    render(<TimelineRail epochs={null} />);
    expect(screen.getByText(/not yet available/i)).toBeInTheDocument();
  });

  test('renders real nodes when epoch data is provided', () => {
    render(
      <TimelineRail
        epochs={[
          { id: 'e1', persona_label: 'Body A', range: 'ch1-40' },
          { id: 'e2', persona_label: 'Body B', range: 'ch41-' },
        ]}
      />
    );
    expect(screen.getByText('Body A')).toBeInTheDocument();
    expect(screen.getByText('Body B')).toBeInTheDocument();
  });
});

describe('ProjectHome', () => {
  test('shows real status fields for the current project', async () => {
    api.listProjects.mockResolvedValueOnce([
      {
        id: 'toy',
        content_type: 'novel',
        source_uploaded: true,
        ingested: true,
        chapter_count: 3,
        job_count: 2,
        last_job: { kind: 'ingest', status: 'SUCCEEDED', error_summary: '' },
      },
    ]);
    render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);

    expect(await screen.findByText('3 chapters')).toBeInTheDocument();
    expect(screen.getByText('ingest')).toBeInTheDocument();
  });

  test('follows a queued job to its end instead of freezing on PENDING', async () => {
    jest.useFakeTimers();
    try {
      const base = { id: 'toy', content_type: 'novel', source_uploaded: true, job_count: 1 };
      api.listProjects
        .mockResolvedValueOnce([{ ...base, ingested: false, chapter_count: 0, last_job: { kind: 'ingest', status: 'PENDING', error_summary: '' } }])
        .mockResolvedValue([{ ...base, ingested: true, chapter_count: 3, last_job: { kind: 'ingest', status: 'SUCCEEDED', error_summary: '' } }]);
      render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);
      expect(await screen.findByText('Not yet')).toBeInTheDocument();
      await act(async () => {
        jest.advanceTimersByTime(2100);
      });
      expect(await screen.findByText('3 chapters')).toBeInTheDocument();
      const calls = api.listProjects.mock.calls.length;
      await act(async () => {
        jest.advanceTimersByTime(7000);
      });
      expect(api.listProjects.mock.calls.length).toBe(calls); // finished: it stops polling
    } finally {
      jest.useRealTimers();
    }
  });

  test('a fresh project not tracked by the backend degrades honestly', async () => {
    api.listProjects.mockResolvedValueOnce([]);
    render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);
    expect(await screen.findByText(/No lifecycle data/i)).toBeInTheDocument();
  });

  test('a real backend error is shown, not swallowed', async () => {
    api.listProjects.mockRejectedValueOnce(Object.assign(new Error('HTTP 500'), { status: 500 }));
    render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);
    expect(await screen.findByText(/server hit a problem/i)).toBeInTheDocument();
  });
});

describe('OutputLibrary', () => {
  beforeEach(() => {
    api.outputFileUrl.mockImplementation((id, path) => `http://api/${id}/output/file?path=${encodeURIComponent(path)}`);
  });

  test('a video gets a player that does not download until played', async () => {
    api.listOutput.mockResolvedValueOnce({ kinds: { video: [{ path: 'video/ch1/v1/out.mp4', size: 262 * 1048576, mtime: 1 }] } });
    const { container } = render(<OutputLibrary novelId="toy" />);
    await screen.findAllByText('out.mp4');
    // <video> has no ARIA role to query by; the element itself is what is under test.
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    const video = container.querySelector('video');
    expect(video).toHaveAttribute('preload', 'none');
    // eslint-disable-next-line testing-library/no-node-access
    expect(video.querySelector('source')).toHaveAttribute('src', expect.stringContaining('out.mp4'));
    expect(screen.getAllByRole('link', { name: /open out\.mp4/i })[0]).toHaveAttribute('target', '_blank');
  });

  test('manifests and notes are not listed as media, and panels are thumbnails from newest', async () => {
    api.listOutput.mockResolvedValueOnce({
      kinds: {
        video: [],
        panels: [
          { path: 'panels/ch1/manifest_v35.jsonl', size: 1, mtime: 9 },
          { path: 'panels/ch1/VERSIONS.md', size: 1, mtime: 9 },
          { path: 'panels/ch1/old.png', size: 100000, mtime: 1 },
          { path: 'panels/ch1/new.png', size: 100000, mtime: 5 },
        ],
      },
    });
    render(<OutputLibrary novelId="toy" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Panels' }));
    const imgs = await screen.findAllByRole('img');
    expect(imgs.map((i) => i.getAttribute('alt'))).toEqual(['Panel new.png', 'Panel old.png']);
    expect(imgs[0]).toHaveAttribute('src', expect.stringContaining('w=320'));
    expect(screen.queryByText(/manifest_v35/)).not.toBeInTheDocument();
    expect(screen.getByText('Showing 2 of 2')).toBeInTheDocument();
  });

  test('a long list is paged instead of rendered all at once', async () => {
    const audio = Array.from({ length: 60 }, (_, i) => ({ path: `audio/ch1/v1/clip${i}.wav`, size: 10, mtime: i }));
    api.listOutput.mockResolvedValueOnce({ kinds: { video: [], audio } });
    render(<OutputLibrary novelId="toy" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Audio' }));
    expect(await screen.findByText('Showing 24 of 60')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }));
    expect(screen.getByText('Showing 48 of 60')).toBeInTheDocument();
  });

  test('lists real output files and has no dead-end reels tab', async () => {
    api.listOutput.mockResolvedValueOnce({
      novel_id: 'toy',
      kinds: {
        video: [{ path: 'video/ch1/v1/out.mp4', size: 1024, mtime: 1700000000 }],
        audio: [],
        panels: [],
        references: [],
      },
    });
    render(<OutputLibrary novelId="toy" />);

    // Appears twice by design -- the "Latest render" hero and the "Browse"
    // list both surface the same real file.
    expect((await screen.findAllByText('out.mp4')).length).toBeGreaterThanOrEqual(1);

    // No dead-end "Reels" tab: chapter videos are already vertical.
    expect(screen.queryByRole('button', { name: 'Reels' })).not.toBeInTheDocument();
  });

  test('empty output degrades to an honest empty state, not a crash', async () => {
    api.listOutput.mockResolvedValueOnce({ novel_id: 'toy', kinds: {} });
    render(<OutputLibrary novelId="toy" />);
    expect(await screen.findByText(/No video yet/i)).toBeInTheDocument();
  });
});

const COMPUTE_STUB_ONLY = {
  mode: 'local-low', llm_provider: 'ollama', image_provider: 'local', default_tier: 'preview',
  scenes: { preview: 3, full: 70 }, images_per_scene: 3.3, engines: ['stub'], refusals: { stub: null },
  seconds_per_panel: { stub: 0.3 }, llm_missing: [], gpu: { available: false },
};
const COMPUTE_LOCAL_LOW = {
  ...COMPUTE_STUB_ONLY, engines: ['stub', 'noobai', 'illustrious', 'sdxl'],
  refusals: { stub: null, noobai: null, illustrious: null, sdxl: null },
  seconds_per_panel: { stub: 0.3, noobai: 45, illustrious: 45, sdxl: 45 },
};

describe('GenerationWorkspace', () => {
  // Regression test for a real bug found in manual verification: this
  // component used to take `chapters` as a prop from App.js's `novels`
  // cache, which goes stale the moment an ingest job finishes elsewhere
  // (nothing refetches it) -- the chapter picker was silently empty and
  // "Generate panels" stayed permanently disabled. It now fetches its own
  // chapter list via the light `api.chapters` route, matching every other new screen.
  beforeEach(() => {
    api.chapters.mockResolvedValue([{ number: 1 }, { number: 2 }]);
    api.compute.mockResolvedValue(COMPUTE_STUB_ONLY);
  });

  test('fetches its own chapter list rather than trusting a stale prop', async () => {
    api.listJobs.mockResolvedValue([]);
    withToast(<GenerationWorkspace novelId="toy" />);

    await waitFor(() => expect(api.chapters).toHaveBeenCalledWith('toy'));
    expect(api.novel).not.toHaveBeenCalled(); // the full ~9 MB payload is not needed for a chapter picker
    expect(await screen.findByRole('option', { name: 'Chapter 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /generate panels/i })).not.toBeDisabled();
  });

  test('queues a real stub-engine render job and shows its status', async () => {
    api.listJobs.mockResolvedValue([]);
    api.renderGenerate.mockResolvedValueOnce({ job_id: 'toy:render:abc', kind: 'render', status: 'PENDING' });

    withToast(<GenerationWorkspace novelId="toy" />);

    await screen.findByRole('option', { name: 'Chapter 1' });
    fireEvent.click(screen.getByRole('button', { name: /generate panels/i }));

    await waitFor(() =>
      expect(api.renderGenerate).toHaveBeenCalledWith('toy', { chapters: [1], engine: 'stub', tier: 'preview', density: 'beat' })
    );
    await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  });

  test('offers the engines the server enables and sends the chosen engine and scope', async () => {
    api.listJobs.mockResolvedValue([]);
    api.compute.mockResolvedValue(COMPUTE_LOCAL_LOW);
    withToast(<GenerationWorkspace novelId="toy" />);
    await screen.findByRole('option', { name: 'Chapter 1' });
    await waitFor(() => expect(screen.getByRole('option', { name: /NoobAI XL/ })).not.toBeDisabled());
    expect(screen.getByLabelText('Scope')).toHaveValue('preview'); // local-low defaults to a preview
    fireEvent.change(screen.getByLabelText('Engine'), { target: { value: 'noobai' } });
    // 3 scenes x 3.3 images x 45 s = about 7 minutes
    await waitFor(() => expect(screen.getByTestId('eta')).toHaveTextContent(/about 7 min/));
    api.renderGenerate.mockResolvedValueOnce({ job_id: 'toy:render:n', kind: 'render', status: 'PENDING' });
    fireEvent.click(screen.getByRole('button', { name: /generate panels/i }));
    await waitFor(() =>
      expect(api.renderGenerate).toHaveBeenCalledWith('toy', { chapters: [1], engine: 'noobai', tier: 'preview', density: 'beat' })
    );
  });

  test('a refused engine is disabled and the reason is shown', async () => {
    api.listJobs.mockResolvedValue([]);
    api.compute.mockResolvedValue({
      ...COMPUTE_LOCAL_LOW,
      refusals: { stub: null, noobai: 'the GPU is busy (NVIDIA RTX: 5200 of 8188 MiB in use); stop what is using it' },
    });
    withToast(<GenerationWorkspace novelId="toy" />);
    await screen.findByRole('option', { name: 'Chapter 1' });
    fireEvent.change(screen.getByLabelText('Engine'), { target: { value: 'stub' } });
    await waitFor(() => expect(screen.getByRole('option', { name: /NoobAI XL/ })).toBeDisabled());
    expect(screen.getByRole('option', { name: /Placeholder/ })).not.toBeDisabled();
  });

  test('cloud mode offers the hosted engine and no local ones', async () => {
    api.listJobs.mockResolvedValue([]);
    api.compute.mockResolvedValue({
      ...COMPUTE_STUB_ONLY, mode: 'cloud', default_tier: 'full', engines: ['stub', 'runpod'],
      refusals: { stub: null, runpod: null }, scenes: { preview: 3, full: 70 },
      llm_provider: 'runpod', llm_missing: ['ECHOTALES_RUNPOD_API_KEY'],
    });
    withToast(<GenerationWorkspace novelId="toy" />);
    await screen.findByRole('option', { name: 'Chapter 1' });
    expect(await screen.findByRole('option', { name: /RunPod \(cloud\)/ })).not.toBeDisabled();
    expect(screen.queryByRole('option', { name: /NoobAI/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Scope')).toHaveValue('full');
    expect(screen.getByTestId('engine-note')).toHaveTextContent(/still needs ECHOTALES_RUNPOD_API_KEY/);
  });

  test('renders honest not-yet-available states for preview and QA', async () => {
    api.listJobs.mockResolvedValue([]);
    withToast(<GenerationWorkspace novelId="toy" />);
    expect((await screen.findAllByText(/not yet available/i)).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  });
});
