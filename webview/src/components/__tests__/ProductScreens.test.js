import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

  test('a fresh project not tracked by the backend degrades honestly', async () => {
    api.listProjects.mockResolvedValueOnce([]);
    render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);
    expect(await screen.findByText(/No lifecycle data/i)).toBeInTheDocument();
  });

  test('a real backend error is shown, not swallowed', async () => {
    api.listProjects.mockRejectedValueOnce(new Error('HTTP 500'));
    render(<ProjectHome novelId="toy" onNewProject={jest.fn()} />);
    expect(await screen.findByText(/HTTP 500/)).toBeInTheDocument();
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

  test('lists real output files and shows the honest reels state', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: 'Reels' }));
    expect(await screen.findByText(/Reels not produced yet/i)).toBeInTheDocument();
  });

  test('empty output degrades to an honest empty state, not a crash', async () => {
    api.listOutput.mockResolvedValueOnce({ novel_id: 'toy', kinds: {} });
    render(<OutputLibrary novelId="toy" />);
    expect(await screen.findByText(/No video yet/i)).toBeInTheDocument();
  });
});

describe('GenerationWorkspace', () => {
  // Regression test for a real bug found in manual verification: this
  // component used to take `chapters` as a prop from App.js's `novels`
  // cache, which goes stale the moment an ingest job finishes elsewhere
  // (nothing refetches it) -- the chapter picker was silently empty and
  // "Generate panels" stayed permanently disabled. It now fetches its own
  // chapter list via the light `api.chapters` route, matching every other new screen.
  beforeEach(() => {
    api.chapters.mockResolvedValue([{ number: 1 }, { number: 2 }]);
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
      expect(api.renderGenerate).toHaveBeenCalledWith('toy', { chapters: [1], engine: 'stub' })
    );
    await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  });

  test('renders honest not-yet-available states for preview and QA', async () => {
    api.listJobs.mockResolvedValue([]);
    withToast(<GenerationWorkspace novelId="toy" />);
    expect((await screen.findAllByText(/not yet available/i)).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(api.listJobs).toHaveBeenCalled());
  });
});
