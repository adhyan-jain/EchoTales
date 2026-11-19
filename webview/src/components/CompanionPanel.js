import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import JobFailure from './ui/JobFailure';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { waitForJob } from '../lib/jobs';

/* The spoiler-safe companion: who is who, as a reader who has finished chapter N knows it. It is built on the server
   from the graph filtered to chapter N, so a later chapter is not in the page at all. */
export default function CompanionPanel({ novelId, project }) {
  const push = useToast();
  const [list, setList] = useState(null);
  const [through, setThrough] = useState('1');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState(null);
  const [loadError, setLoadError] = useState('');
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  const load = useCallback(() => {
    return api
      .listCompanions(novelId)
      .then((r) => {
        if (gone.current) return;
        setList((r && r.companions) || []);
        setLoadError('');
      })
      .catch((err) => {
        if (!gone.current) setLoadError(describeError(err, 'Could not load the companions.'));
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const n = Number(through);
  const valid = through.trim() !== '' && Number.isFinite(n) && n > 0;
  const total = project && project.chapter_count;

  const build = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const queued = await api.triggerStage(novelId, 'companion', { through: n });
      const done = await waitForJob(novelId, queued.job_id, { cancelled: () => gone.current });
      if (gone.current) return;
      if (done && done.status === 'SUCCEEDED') push(`Companion through chapter ${n} built.`, 'success');
      else setFailure({ summary: done && done.error_summary });
      await load();
    } catch (err) {
      push(describeError(err, 'Could not queue the companion.'), 'danger');
    } finally {
      if (!gone.current) setBusy(false);
    }
  };

  return (
    <section aria-label="Reader companion" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Reader companion</h2>
      <p className="mt-1 text-sm text-muted">
        A page of characters, relationships and a timeline for someone partway through the book. It contains only what
        the book has told them by the chapter you choose.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="companion-through">
            Last chapter you have finished
          </label>
          <Input
            id="companion-through"
            type="number"
            min="1"
            max={total || undefined}
            step="1"
            value={through}
            onChange={(e) => setThrough(e.target.value)}
          />
        </div>
        <Button variant="secondary" disabled={!valid || busy} onClick={build}>
          {busy ? 'Building…' : `Build companion through chapter ${valid ? n : '…'}`}
        </Button>
      </div>
      {loadError && (
        <div role="alert" className="mt-4 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}
      {failure && <JobFailure kind="companion" summary={failure.summary} />}
      <ul className="mt-4 space-y-2">
        {list && list.length === 0 && !loadError && <li className="text-sm text-muted">No companion built yet.</li>}
        {(list || []).map((c) => (
          <li key={c.through}>
            <a
              href={api.companionUrl(novelId, c.through)}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-accent underline underline-offset-4"
            >
              Open the companion through chapter {c.through}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
