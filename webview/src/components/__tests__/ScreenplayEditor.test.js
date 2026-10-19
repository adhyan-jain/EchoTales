import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    getScreenplayEpisode: jest.fn(),
    saveScreenplayEpisode: jest.fn(),
    compileScreenplay: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import ScreenplayEditor from '../ScreenplayEditor';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

function renderEditor(props) {
  return render(
    <ToastProvider>
      <ScreenplayEditor {...props} />
    </ToastProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ScreenplayEditor', () => {
  const mockEpisode = {
    episode_id: 'ep1',
    novel_id: 'hound',
    title: 'Episode 1: The Walking Stick',
    chapter_range: [1.0, 1.0],
    scenes: [
      {
        scene_id: 'sc1',
        scene_index: 1,
        location_id: 'loc:study',
        time_of_day: 'day',
        shots: [
          {
            shot_index: 0,
            scene_id: 'sc1',
            location_id: 'loc:study',
            shot_size: 'medium',
            camera_move: 'static',
            duration_s: 3.5,
            action: 'Holmes examines the walking stick.',
            render_tier: '2.5d',
            dialogue: [
              {
                speaker_id: 'char:holmes',
                text: 'Well, Watson, what do you make of it?',
                emotion: 'curious',
                intensity: 1,
              },
            ],
          },
          {
            shot_index: 1,
            scene_id: 'sc1',
            location_id: 'loc:study',
            shot_size: 'close',
            camera_move: 'slow_push_in',
            duration_s: 7.2, // Still hold > 6s violation warning!
            action: 'Watson ponders.',
            render_tier: '2.5d',
            dialogue: [],
          },
        ],
      },
    ],
  };

  test('renders episode shots and flags still hold > 6s', async () => {
    api.getScreenplayEpisode.mockResolvedValueOnce(mockEpisode);

    renderEditor({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByTestId('screenplay-editor')).toBeInTheDocument();
      expect(screen.getByText('Episode 1: The Walking Stick')).toBeInTheDocument();
      expect(screen.getByText('Shot #1')).toBeInTheDocument();
      expect(screen.getByText('Shot #2')).toBeInTheDocument();
    });

    // Check hold warning badge on Shot #2
    expect(screen.getByText(/Still hold > 6s/i)).toBeInTheDocument();
  });

  test('edits shot action and saves screenplay', async () => {
    api.getScreenplayEpisode.mockResolvedValueOnce(mockEpisode);
    api.saveScreenplayEpisode.mockResolvedValueOnce({ saved: true });

    renderEditor({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByDisplayValue('Holmes examines the walking stick.')).toBeInTheDocument();
    });

    const actionInput = screen.getByDisplayValue('Holmes examines the walking stick.');
    fireEvent.change(actionInput, { target: { value: 'Holmes holds up the magnifying glass.' } });

    expect(screen.getByDisplayValue('Holmes holds up the magnifying glass.')).toBeInTheDocument();

    const saveBtn = screen.getByText('Save Changes');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(api.saveScreenplayEpisode).toHaveBeenCalledWith(
        'hound',
        'ep1',
        expect.objectContaining({
          scenes: expect.arrayContaining([
            expect.objectContaining({
              shots: expect.arrayContaining([
                expect.objectContaining({
                  action: 'Holmes holds up the magnifying glass.',
                }),
              ]),
            }),
          ]),
        })
      );
    });
  });

  test('triggers re-compilation of screenplay', async () => {
    api.getScreenplayEpisode.mockResolvedValueOnce(mockEpisode);
    api.compileScreenplay.mockResolvedValueOnce({
      ...mockEpisode,
      title: 'Episode 1: Recompiled',
    });

    renderEditor({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByText('Episode 1: The Walking Stick')).toBeInTheDocument();
    });

    const compileBtn = screen.getByText('Re-compile Screenplay');
    fireEvent.click(compileBtn);

    await waitFor(() => {
      expect(api.compileScreenplay).toHaveBeenCalledWith('hound', 'ep1', {
        chapters: [1.0, 1.0],
      });
      expect(screen.getByText('Episode 1: Recompiled')).toBeInTheDocument();
    });
  });
});
