import React from 'react';
import Badge from './Badge';

// Mirrors `StageStatus` (packages/core/.../models.py) -- the real values a
// `Job` row can carry, never a fabricated "queued" state the backend
// doesn't itself have.
const TONE_BY_STATUS = {
  PENDING: 'neutral',
  RUNNING: 'accent',
  SUCCEEDED: 'success',
  FAILED: 'danger',
  PARTIAL: 'warning',
};

export default function JobStatusBadge({ status }) {
  return <Badge tone={TONE_BY_STATUS[status] || 'neutral'}>{status || 'UNKNOWN'}</Badge>;
}
