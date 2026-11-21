import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    getEpisodeCost: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import CostMeterWidget from '../CostMeterWidget';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

function renderWidget(props) {
  return render(
    <ToastProvider>
      <CostMeterWidget {...props} />
    </ToastProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('CostMeterWidget', () => {
  test('renders pre-render cost estimate and breakdown', async () => {
    api.getEpisodeCost.mockResolvedValueOnce({
      novel_id: 'hound',
      episode_id: 'ep1',
      tier: 'path1',
      cost_per_finished_minute_usd: 0.28,
      total_cost_usd: 0.56,
      episode_duration_s: 120.0,
      num_shots: 24,
      breakdown: {
        llm_adaptation: 0.007,
        keyframe_diffusion: 0.288,
        voice_synthesis: 0.096,
        video_generation: 0.036,
      },
    });

    renderWidget({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByTestId('cost-meter-widget')).toBeInTheDocument();
      expect(screen.getByTestId('cost-per-minute')).toHaveTextContent('$0.28');
      expect(screen.getByTestId('total-cost')).toHaveTextContent('$0.56');
    });

    expect(screen.getByText('Within Budget')).toBeInTheDocument();
    expect(screen.getByText('$0.2880')).toBeInTheDocument(); // keyframe_diffusion row
  });

  test('tolerates a response with missing fields instead of crashing', async () => {
    // 2026-11 walkthrough: the old field names made .toFixed run on undefined and took the whole Studio down.
    api.getEpisodeCost.mockResolvedValueOnce({ tier: 'path1' });
    renderWidget({ novelId: 'hound', episodeId: 'ep1' });
    await waitFor(() => expect(screen.getByTestId('total-cost')).toHaveTextContent('$0.00'));
    expect(screen.getByTestId('cost-per-minute')).toHaveTextContent('$0.00');
  });

  test('switches tier between Path 1 and Path 2', async () => {
    api.getEpisodeCost
      .mockResolvedValueOnce({
        novel_id: 'hound',
        episode_id: 'ep1',
        tier: 'path1',
        cost_per_finished_minute_usd: 0.28,
        total_cost_usd: 0.56,
        episode_duration_s: 120.0,
        num_shots: 24,
        breakdown: {},
      })
      .mockResolvedValueOnce({
        novel_id: 'hound',
        episode_id: 'ep1',
        tier: 'path2',
        cost_per_finished_minute_usd: 0.64,
        total_cost_usd: 1.28,
        episode_duration_s: 120.0,
        num_shots: 24,
        breakdown: {},
      });

    const onTierChange = jest.fn();
    renderWidget({ novelId: 'hound', episodeId: 'ep1', onTierChange });

    await waitFor(() => {
      expect(screen.getByTestId('cost-per-minute')).toHaveTextContent('$0.28');
    });

    const path2Btn = screen.getByText('Path 2: Wan 2.2 Video');
    fireEvent.click(path2Btn);

    await waitFor(() => {
      expect(api.getEpisodeCost).toHaveBeenCalledWith('hound', 'ep1', 'path2');
      expect(onTierChange).toHaveBeenCalledWith('path2');
      expect(screen.getByTestId('cost-per-minute')).toHaveTextContent('$0.64');
    });
  });

  test('displays warning alert when cost exceeds limit', async () => {
    api.getEpisodeCost.mockResolvedValueOnce({
      novel_id: 'hound',
      episode_id: 'ep1',
      tier: 'path1',
      cost_per_finished_minute_usd: 0.85, // Exceeds $0.50 target
      total_cost_usd: 1.70,
      episode_duration_s: 120.0,
      num_shots: 50,
      breakdown: {},
    });

    renderWidget({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByText('Over Budget')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });

  test('says so when the estimate is for an assumed episode, not a saved screenplay', async () => {
    api.getEpisodeCost.mockResolvedValueOnce({
      episode_id: 'ep1', tier: 'path1', cost_per_finished_minute_usd: 0.2, total_cost_usd: 0.1,
      episode_duration_s: 42, num_shots: 12, breakdown: {}, assumed_episode: true,
    });
    renderWidget({ novelId: 'hound', episodeId: 'ep1' });
    expect(await screen.findByTestId('cost-assumed')).toBeInTheDocument();
  });
});
