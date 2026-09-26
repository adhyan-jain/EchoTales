import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import AnalysisPanel from '../AnalysisPanel';

// A correction that fails on Apply (a line merge across blocks) is never
// marked applied, so it stayed queued and failed on every Apply with no way
// to remove it -- reported by a reviewer, 2026-09-26.

const SUMMARY = { total: 3, applied: 1, pending: 2, pending_actionable: 1, flags_open: 1, by_type: { merge_lines: 1 } };
const ITEMS = [
  { id: 'a', type: 'reassign_mention', applied: true, payload: { mention_id: 'n:1:m0', target_id: 'x' } },
  { id: 'b', type: 'merge_lines', applied: false, payload: { primary_span_id: 'n:2:7:0', absorbed_span_id: 'n:2:8:0' } },
  { id: 'c', type: 'flag', applied: false, payload: { span_id: 'n:2:1:0', note: 'check speaker' } },
];

test('lists only what is waiting, in plain language, each with an Undo', () => {
  render(<AnalysisPanel summary={SUMMARY} items={ITEMS} onUndo={jest.fn()} onApply={jest.fn()} onClose={jest.fn()} />);
  expect(screen.getByText(/merge line 2:8:0 into 2:7:0/i)).toBeInTheDocument();
  expect(screen.getByText(/flag on line 2:1:0: check speaker/i)).toBeInTheDocument();
  expect(screen.queryByText(/unlink a mention/i)).not.toBeInTheDocument(); // already applied
  expect(screen.getAllByRole('button', { name: /^Undo:/ })).toHaveLength(2);
});

test('Undo removes exactly that correction', () => {
  const onUndo = jest.fn();
  render(<AnalysisPanel summary={SUMMARY} items={ITEMS} onUndo={onUndo} onApply={jest.fn()} onClose={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /undo: merge line/i }));
  expect(onUndo).toHaveBeenCalledWith('b');
});

test('an item that failed on the last Apply is called out, and the heading counts failures honestly', () => {
  const applyResult = { count: 0, applied: [{ type: 'merge_lines', error: 'spans are not in the same block' }] };
  render(
    <AnalysisPanel summary={SUMMARY} items={ITEMS} failedIds={new Set(['b'])} applyResult={applyResult} onUndo={jest.fn()} onApply={jest.fn()} onClose={jest.fn()} />
  );
  expect(screen.getAllByText(/did not apply last time/i)).toHaveLength(1); // only item b, not the flag
  expect(screen.getByText(/0 applied, 1 could not be applied/i)).toBeInTheDocument();
});
