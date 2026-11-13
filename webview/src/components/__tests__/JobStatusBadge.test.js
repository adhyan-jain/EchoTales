import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import JobStatusBadge, { jobEndedBadly } from '../ui/JobStatusBadge';

describe('JobStatusBadge', () => {
  test('a cancelled job reads as neutral, not as a defect', () => {
    render(<JobStatusBadge status="CANCELLED" />);
    expect(screen.getByText('CANCELLED')).toHaveClass('bg-surface2', 'text-muted');
    expect(screen.getByText('CANCELLED')).not.toHaveClass('text-danger');
  });

  test('an interrupted job reads as a warning, the same tone as partial', () => {
    render(<JobStatusBadge status="INTERRUPTED" />);
    expect(screen.getByText('INTERRUPTED')).toHaveClass('bg-warning/15', 'text-warning');
    expect(screen.getByText('INTERRUPTED')).not.toHaveClass('text-danger');
  });

  test('only FAILED and INTERRUPTED show a failure reason', () => {
    expect(jobEndedBadly('FAILED')).toBe(true);
    expect(jobEndedBadly('INTERRUPTED')).toBe(true);
    expect(jobEndedBadly('CANCELLED')).toBe(false);
    expect(jobEndedBadly('SUCCEEDED')).toBe(false);
    expect(jobEndedBadly(undefined)).toBe(false);
  });
});
