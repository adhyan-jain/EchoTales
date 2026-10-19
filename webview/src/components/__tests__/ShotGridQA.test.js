import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    listShotCandidates: jest.fn(),
    rerollShotCandidates: jest.fn(),
    lockShotCandidate: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import ShotGridQA from '../ShotGridQA';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

function renderQA(props) {
  return render(
    <ToastProvider>
      <ShotGridQA {...props} />
    </ToastProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ShotGridQA', () => {
  const mockCandidates = [
    {
      id: 'cand_ep1_0_0',
      shot_index: 0,
      seed: 42,
      selected: true,
      qa_report: {
        face_match: { score: 0.94, passed: true },
        bg_match: { score: 0.88, passed: true },
        vlm_checklist: { score: 0.92, passed: true },
        artifact_filter: { score: 0.98, passed: true },
        passed: true,
      },
    },
    {
      id: 'cand_ep1_0_1',
      shot_index: 0,
      seed: 59,
      selected: false,
      qa_report: {
        face_match: { score: 0.89, passed: true },
        bg_match: { score: 0.84, passed: true },
        vlm_checklist: { score: 0.86, passed: true },
        artifact_filter: { score: 0.96, passed: true },
        passed: true,
      },
    },
    {
      id: 'cand_ep1_0_2',
      shot_index: 0,
      seed: 76,
      selected: false,
      qa_report: {
        face_match: { score: 0.79, passed: false }, // Failed face match
        bg_match: { score: 0.80, passed: true },
        vlm_checklist: { score: 0.80, passed: false },
        artifact_filter: { score: 0.94, passed: true },
        passed: false,
      },
    },
    {
      id: 'cand_ep1_0_3',
      shot_index: 0,
      seed: 93,
      selected: false,
      qa_report: {
        face_match: { score: 0.74, passed: false },
        bg_match: { score: 0.76, passed: true },
        vlm_checklist: { score: 0.75, passed: false },
        artifact_filter: { score: 0.92, passed: true },
        passed: false,
      },
    },
  ];

  test('renders 4 keyframe candidates and displays 4-check scores', async () => {
    api.listShotCandidates.mockResolvedValueOnce(mockCandidates);

    renderQA({ novelId: 'hound', episodeId: 'ep1', shotIndex: 0 });

    await waitFor(() => {
      expect(screen.getByTestId('shot-grid-qa')).toBeInTheDocument();
      expect(screen.getByText('Candidate #1')).toBeInTheDocument();
      expect(screen.getByText('Candidate #2')).toBeInTheDocument();
      expect(screen.getByText('Candidate #3')).toBeInTheDocument();
      expect(screen.getByText('Candidate #4')).toBeInTheDocument();
    });

    expect(screen.getByText('94%')).toBeInTheDocument(); // Face score
    expect(screen.getByText('88%')).toBeInTheDocument(); // BG score
    expect(screen.getByText('Locked Reference')).toBeInTheDocument();
  });

  test('locks another candidate', async () => {
    api.listShotCandidates.mockResolvedValueOnce(mockCandidates);
    api.lockShotCandidate.mockResolvedValueOnce({ locked: true, candidate_id: 'cand_ep1_0_1' });

    renderQA({ novelId: 'hound', episodeId: 'ep1', shotIndex: 0 });

    await waitFor(() => {
      expect(screen.getByText('Candidate #2')).toBeInTheDocument();
    });

    const selectButtons = screen.getAllByText('Select & Lock');
    fireEvent.click(selectButtons[0]); // Candidate 2

    await waitFor(() => {
      expect(api.lockShotCandidate).toHaveBeenCalledWith('hound', 'ep1', 0, 'cand_ep1_0_1');
    });
  });

  test('re-rolls 4 candidates through QA gate', async () => {
    api.listShotCandidates.mockResolvedValueOnce(mockCandidates);
    api.rerollShotCandidates.mockResolvedValueOnce({
      rerolled: true,
      candidates: [
        {
          id: 'cand_ep1_0_0_rerolled',
          shot_index: 0,
          seed: 142,
          selected: true,
          qa_report: {
            face_match: { score: 0.96, passed: true },
            bg_match: { score: 0.92, passed: true },
            vlm_checklist: { score: 0.95, passed: true },
            artifact_filter: { score: 0.99, passed: true },
            passed: true,
          },
        },
      ],
    });

    renderQA({ novelId: 'hound', episodeId: 'ep1', shotIndex: 0 });

    await waitFor(() => {
      expect(screen.getByText('Candidate #1')).toBeInTheDocument();
    });

    const rerollBtn = screen.getByText('Re-roll 4 Candidates');
    fireEvent.click(rerollBtn);

    await waitFor(() => {
      expect(api.rerollShotCandidates).toHaveBeenCalledWith('hound', 'ep1', 0, expect.any(Object));
      expect(screen.getByText('96%')).toBeInTheDocument();
    });
  });
});
