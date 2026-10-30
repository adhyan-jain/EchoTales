import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { CircleCheck, CircleDashed, Download } from 'lucide-react';
import { api } from '../api';
import Button from './ui/Button';
import JobStatusBadge from './ui/JobStatusBadge';
import JobFailure from './ui/JobFailure';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { fileUrl } from '../lib/media';

/* The guided path from an uploaded EPUB to an audiobook: build the book, review the lines the pipeline was unsure
   about, lock the canon, voice it, bind the M4B. Every state shown here is read from the server (jobs, bible lock,
   review queue, output files); nothing is inferred from what this page did earlier, so a reload or a second tab shows
   the same truth. Voicing with a real engine is refused by the server until the canon is locked, so the steps are in
   the order the server enforces. */

const inFlight = (job) => job && (job.status === 'PENDING' || job.status === 'RUNNING');
const latest = (jobs, kind) => (jobs || []).filter((j) => j.kind === kind).sort((a, b) => (b.created_at || 0) - (a.created_at || 0))[0] || null;

export default function AudiobookPanel({ novelId, project }) {
  const [jobs, setJobs] = useState([]);
  const [bible, setBible] = useState(null);
  const [queue, setQueue] = useState(null);
  const [output, setOutput] = useState(null);
  const [engine, setEngine] = useState('chatterbox');
  const [busy, setBusy] = useState('');
  const push = useToast();
  const timer = useRef(null);

  const refresh = useCallback(() => {
    if (!novelId) return;
    api.listJobs(novelId).then((j) => setJobs(j || [])).catch(() => {});
    api.getBible(novelId).then(setBible).catch(() => setBible(null));
    api.reviewLines(novelId, { limit: 1 }).then(setQueue).catch(() => setQueue(null));
    api.listOutput(novelId).then(setOutput).catch(() => setOutput({ kinds: {} }));
  }, [novelId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll only while something is running, so an idle page costs the server nothing.
  useEffect(() => {
    clearInterval(timer.current);
    if (jobs.some(inFlight)) timer.current = setInterval(refresh, 2500);
    return () => clearInterval(timer.current);
  }, [jobs, refresh]);

  const start = (kind, params, label) => {
    setBusy(kind);
    api
      .triggerStage(novelId, kind, params)
      .then(() => {
        push(`${label} queued.`, 'success');
        refresh();
      })
      .catch((err) => push(describeError(err, `Could not queue: ${label.toLowerCase()}.`), 'danger'))
      .finally(() => setBusy(''));
  };

  const lock = () => {
    setBusy('lock');
    api
      .lockBible(novelId)
      .then(() => {
        push('Canon locked.', 'success');
        refresh();
      })
      .catch((err) => push(describeError(err, 'Could not lock the canon.'), 'danger'))
      .finally(() => setBusy(''));
  };

  const built = project ? project.ingested : false;
  const buildJob = latest(jobs, 'pipeline');
  const voiceJob = latest(jobs, 'voice');
  const exportJob = latest(jobs, 'export_m4b');
  const current = bible && bible.current;
  const locked = !!(current && current.locked_version != null && !current.dirty);
  const waiting = queue ? queue.total : null;
  const audioFiles = (output && output.kinds && output.kinds.audio) || [];
  const book = audioFiles.filter((f) => /\.m4b$/i.test(f.path)).sort((a, b) => (b.mtime || 0) - (a.mtime || 0))[0];
  const voiced = voiceJob && voiceJob.status === 'SUCCEEDED';
  const anyRunning = jobs.some(inFlight);

  return (
    <section aria-label="Audiobook" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Make the audiobook</h2>
      <p className="mt-1 text-sm text-muted">
        Five steps, in the order the server requires them. Each shows its real state.
      </p>
      <ol className="mt-5 space-y-3">
        <StepRow
          n={1}
          done={built}
          title="Build the book"
          note={built ? `${project.chapter_count} chapters read and the cast resolved.` : 'Reads every chapter, finds the characters and who speaks each line.'}
          job={buildJob}
          action={
            <Button size="sm" disabled={!project || !project.source_uploaded || anyRunning || busy === 'pipeline'} onClick={() => start('pipeline', {}, 'Build')}>
              {built ? 'Rebuild' : 'Build'}
            </Button>
          }
        />
        <StepRow
          n={2}
          done={built && waiting === 0}
          title="Review uncertain lines"
          note={waiting == null ? 'Checking the queue…' : waiting === 0 ? 'Nothing left to review.' : `${waiting} lines have no confirmed speaker. Unreviewed lines are voiced as an unnamed speaker.`}
          action={
            <Link to="../review" className="inline-flex h-9 items-center rounded-xl border border-border px-3 text-sm font-semibold text-text hover:border-accent/60">
              Open review
            </Link>
          }
        />
        <StepRow
          n={3}
          done={locked}
          title="Lock the canon"
          note={
            locked
              ? `Locked as version ${current.locked_version}.`
              : current && current.stale_reason
                ? `Cannot lock yet: ${current.stale_reason}`
                : current && current.locked_version != null
                  ? 'Edits since the last lock. Lock again to voice them.'
                  : 'Freezes the reviewed cast so the voice and images are made from a fixed version.'
          }
          action={
            <Button size="sm" disabled={!built || locked || anyRunning || busy === 'lock' || !!(current && current.stale_reason)} onClick={lock}>
              Lock
            </Button>
          }
        />
        <StepRow
          n={4}
          done={!!voiced}
          title="Voice every line"
          note="One voice per character, the narrator for narration. Uses the GPU; the placeholder engine writes silent files and cannot make an audiobook."
          job={voiceJob}
          action={
            <span className="flex items-center gap-2">
              <select
                aria-label="Voice engine"
                value={engine}
                onChange={(e) => setEngine(e.target.value)}
                className="h-9 rounded-xl border border-border bg-transparent px-2 text-sm text-text"
              >
                <option value="chatterbox">Chatterbox (speech)</option>
                <option value="stub">Placeholder (silent)</option>
              </select>
              <Button size="sm" disabled={!built || (engine !== 'stub' && !locked) || anyRunning || busy === 'voice'} onClick={() => start('voice', { engine }, 'Voicing')}>
                Voice
              </Button>
            </span>
          }
        />
        <StepRow
          n={5}
          done={!!book}
          title="Bind the audiobook"
          note={book ? 'Ready. One file, with a marker for every chapter.' : 'Joins the chapters into one M4B with chapter markers.'}
          job={exportJob}
          action={
            book ? (
              <a
                href={fileUrl(novelId, book.path)}
                download
                className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-primary px-3 text-sm font-semibold text-white hover:bg-primary-2"
              >
                <Download className="h-4 w-4" aria-hidden="true" /> Download
              </a>
            ) : (
              <Button size="sm" disabled={!voiced || anyRunning || busy === 'export_m4b'} onClick={() => start('export_m4b', {}, 'Export')}>
                Make M4B
              </Button>
            )
          }
        />
      </ol>
    </section>
  );
}

function StepRow({ n, done, title, note, job, action }) {
  const Icon = done ? CircleCheck : CircleDashed;
  return (
    <li className={`rounded-2xl border px-4 py-3 ${done ? 'border-success/30 bg-success/5' : 'border-border'}`}>
      <div className="flex flex-wrap items-center gap-3">
        <Icon className={`h-5 w-5 shrink-0 ${done ? 'text-success' : 'text-muted'}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">
            {n}. {title} {job ? <JobStatusBadge status={job.status} /> : null}
          </div>
          <div className="text-xs text-muted">{note}</div>
        </div>
        {action}
      </div>
      {job && job.status === 'FAILED' && <JobFailure kind={job.kind} summary={job.error_summary} />}
    </li>
  );
}
