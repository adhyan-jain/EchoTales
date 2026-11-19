import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';

jest.mock('../../api', () => ({
  api: {
    characters: jest.fn(),
    listTurnarounds: jest.fn(),
    approveTurnaround: jest.fn(),
    rejectTurnaround: jest.fn(),
    generateTurnaround: jest.fn(),
    generateIdentitySheet: jest.fn(),
    listLocationPlates: jest.fn(),
    approveLocationPlate: jest.fn(),
    rejectLocationPlate: jest.fn(),
    generateLocationPlate: jest.fn(),
    listReviewItems: jest.fn(),
    resolveReviewItem: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../../api';
// eslint-disable-next-line import/first
import AssetStudio from '../AssetStudio';
// eslint-disable-next-line import/first
import { ToastProvider } from '../ui/Toast';

function renderStudio(props) {
  return render(
    <ToastProvider>
      <AssetStudio {...props} />
    </ToastProvider>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('AssetStudio', () => {
  test('renders characters and approves turnaround candidate', async () => {
    api.characters.mockResolvedValueOnce({
      characters: [{ id: 'char:holmes', canonical_label: 'Sherlock Holmes' }],
    });
    api.listTurnarounds.mockResolvedValueOnce([
      { id: 'cand_turnaround_1', is_approved: false },
    ]);
    api.approveTurnaround.mockResolvedValueOnce({ id: 'cand_turnaround_1', action: 'approve' });

    renderStudio({ novelId: 'hound' });

    await waitFor(() => {
      expect(screen.getByTestId('asset-studio')).toBeInTheDocument();
      expect(screen.getByText('cand_turnaround_1')).toBeInTheDocument();
      expect(screen.getByText('Pending Approval')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('Approve');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.approveTurnaround).toHaveBeenCalledWith('hound', 'char:holmes', 'cand_turnaround_1');
    });
  });

  test('shows the locked description of a sheet and says approving locks it', async () => {
    api.characters.mockResolvedValueOnce({ characters: [{ id: 'char:holmes', canonical_label: 'Sherlock Holmes' }] });
    api.listTurnarounds.mockResolvedValueOnce([
      { id: 'sheet_1', is_approved: false, locked_description: 'Fang Yuan is a man with long black hair, wearing a deep green robe.' },
    ]);
    renderStudio({ novelId: 'hound' });
    await waitFor(() => {
      expect(screen.getByTestId('locked-description')).toHaveTextContent('Approve to lock for every panel');
      expect(screen.getByTestId('locked-description')).toHaveTextContent('long black hair');
    });
  });

  test('switches to location plates and approves master plate', async () => {
    api.characters.mockResolvedValueOnce({ characters: [] });
    api.listTurnarounds.mockResolvedValueOnce([]);
    api.listLocationPlates.mockResolvedValueOnce([
      { id: 'cand_plate_1', is_approved: false },
    ]);
    api.approveLocationPlate.mockResolvedValueOnce({ id: 'cand_plate_1', action: 'approve' });

    renderStudio({ novelId: 'hound' });

    const locTab = screen.getByText('Location Plates');
    fireEvent.click(locTab);

    await waitFor(() => {
      expect(screen.getByText('cand_plate_1')).toBeInTheDocument();
    });

    const approveBtn = screen.getByText('Approve');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(api.approveLocationPlate).toHaveBeenCalledWith('hound', 'loc:study', 'cand_plate_1');
    });
  });

  test('switches to review queue and resolves ambiguous item', async () => {
    api.characters.mockResolvedValueOnce({ characters: [] });
    api.listTurnarounds.mockResolvedValueOnce([]);
    api.listReviewItems.mockResolvedValueOnce({
      items: [{ id: 'rev_1', chapter: 1.0, kind: 'Ambiguous Merge', message: 'Mortimer vs Doctor', resolved: false }],
      total: 1,
      open: 1,
    });
    api.resolveReviewItem.mockResolvedValueOnce({ id: 'rev_1', resolved: true });

    renderStudio({ novelId: 'hound' });

    const revTab = screen.getByText('Bible Review Queue');
    fireEvent.click(revTab);

    await waitFor(() => {
      expect(screen.getByText('Mortimer vs Doctor')).toBeInTheDocument();
    });

    const resolveBtn = screen.getByText('Resolve Contradiction');
    fireEvent.click(resolveBtn);

    await waitFor(() => {
      expect(api.resolveReviewItem).toHaveBeenCalledWith('hound', 'rev_1', 'RESOLVED_MANUAL');
    });
  });

  test('review items show candidate labels, never [object Object]', async () => {
    api.characters.mockResolvedValueOnce({ characters: [] });
    api.listTurnarounds.mockResolvedValueOnce([]);
    api.listReviewItems.mockResolvedValueOnce({
      items: [
        {
          id: 'rd_1',
          chapter: 2.0,
          kind: 'resolve_deferred',
          message: "'Angelica' left unlinked",
          resolved: false,
          candidates: [
            { role: 'group', surfaces: ['Angelica'], mention_ids: ['m1'] },
            { role: 'candidate', target_id: 't:self:1', label: 'Madam Angelica', probability: 0.41 },
            { role: 'candidate', target_id: 't:self:2', label: 'Angel', probability: 0.2 },
          ],
        },
      ],
      total: 1,
      open: 1,
    });

    renderStudio({ novelId: 'hound' });
    fireEvent.click(screen.getByText('Bible Review Queue'));

    expect(await screen.findByText('Candidates: Madam Angelica, Angel')).toBeInTheDocument();
    expect(screen.queryByText(/object Object/)).not.toBeInTheDocument();
    // A plain resolve links nothing, so the unlinked-name kind points at the Canon tab instead.
    expect(screen.queryByText('Resolve Contradiction')).not.toBeInTheDocument();
  });
});
