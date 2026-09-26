import React from 'react';

/**
 * Why a job failed, for a person. `error_summary` is the raw exception text
 * (`jobs.py` stores `str(exc)`), so the plain-language line comes first and
 * the technical text sits behind a disclosure, truncated -- a failed render
 * used to show only a red FAILED badge, and the project overview printed the
 * exception as-is (failure-state QA, 2026-09-26).
 */
export default function JobFailure({ summary, kind = 'job' }) {
  return (
    <div className="mt-2 text-sm">
      <p className="text-danger">
        This {kind} did not finish. It may have left partial output; you can queue it again.
      </p>
      {summary && (
        <details className="mt-1 text-muted">
          <summary className="cursor-pointer select-none text-xs underline decoration-border underline-offset-4">
            Technical detail
          </summary>
          <code className="mt-1 block max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface2 p-2 font-mono text-xs">
            {String(summary).slice(0, 400)}
          </code>
        </details>
      )}
    </div>
  );
}
