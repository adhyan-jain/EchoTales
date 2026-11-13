import React from 'react';
import Badge from './Badge';

// Mirrors `JobStatus` (packages/core/src/echotales/core/lifecycle.py) -- the
// real values a `Job` row can carry, never a fabricated "queued" state the
// backend doesn't itself have.
const TONE_BY_STATUS = {
  PENDING: 'neutral',
  RUNNING: 'accent',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  PARTIAL: 'warning',
  CANCELLED: 'neutral',
  // Interrupted work is re-run, not debugged, so it is a warning rather than a danger.
  INTERRUPTED: 'warning',
};

// Only these two end states carry a reason worth showing (`error_summary`).
// A cancelled job was withdrawn on purpose, so it has none to show.
export const jobEndedBadly = (status) => status === 'FAILED' || status === 'INTERRUPTED';

export default function JobStatusBadge({ status }) {
  return <Badge tone={TONE_BY_STATUS[status] || 'neutral'}>{status || 'UNKNOWN'}</Badge>;
}
