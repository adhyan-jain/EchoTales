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
      total_estimated_usd: 0.56,
      episode_duration_s: 120.0,
      num_shots: 24,
      breakdown: {
        llm_screenplay_tokens: 3500,
        llm_screenplay_cost_usd: 0.007,
        image_generation_count: 24,
        image_generation_cost_usd: 0.288,
        audio_seconds: 120.0,
        voice_synthesis_cost_usd: 0.096,
        video_render_seconds: 120.0,
        video_render_cost_usd: 0.036,
      },
    });

    renderWidget({ novelId: 'hound', episodeId: 'ep1' });

    await waitFor(() => {
      expect(screen.getByTestId('cost-meter-widget')).toBeInTheDocument();
      expect(screen.getByTestId('cost-per-minute')).toHaveTextContent('$0.28');
      expect(screen.getByTestId('total-cost')).toHaveTextContent('$0.56');
    });

    expect(screen.getByText('Within Budget')).toBeInTheDocument();
  });

  test('switches tier between Path 1 and Path 2', async () => {
    api.getEpisodeCost
      .mockResolvedValueOnce({
        novel_id: 'hound',
        episode_id: 'ep1',
        tier: 'path1',
        cost_per_finished_minute_usd: 0.28,
        total_estimated_usd: 0.56,
        episode_duration_s: 120.0,
        num_shots: 24,
        breakdown: {},
      })
      .mockResolvedValueOnce({
        novel_id: 'hound',
        episode_id: 'ep1',
        tier: 'path2',
        cost_per_finished_minute_usd: 0.64,
        total_estimated_usd: 1.28,
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
      total_estimated_usd: 1.70,
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
});
