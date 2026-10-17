import React, { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Divider from './ui/Divider';
import DepthCard from './ui/DepthCard';
import { CardBody } from './ui/Card';
import InspectorSection from './ui/InspectorSection';
import JobStatusBadge from './ui/JobStatusBadge';
import JobFailure from './ui/JobFailure';
import { EmptyState } from './ui/EmptyState';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';

/* The production workstation for panel generation (plan Section 7) --
   deliberately scoped to what the backend actually supports today:
   triggering a real `render` job (`POST .../render/generate`; the stub by
   default, a local image engine when the server reports its GPU free --
   `jobs.py::ALLOWED_HTTP_ENGINES`, `pipeline/gpu.py`) and watching its real
   status. Per-beat render *preview* needs a `beat_id`/`cast_self_ids`
   the webview payload has no way to discover today (no "list beats for a
   chapter" route exists) -- rather than build a form that can never
   submit correctly, that panel is an honest "not yet available" state.
   Regeneration/QA have no backend route at all and are the same.

   Chapters are fetched here directly (`api.chapters`, the light
   numbers-and-titles route), not read from a shared cache: right after a
   real ingest job finishes elsewhere (Settings) a cached novel payload
   stays stale at "0 chapters," which once left this screen's chapter
   picker permanently empty and "Generate panels" permanently disabled.
   The full ~9 MB novel payload is deliberately not used for this. */
// Local engines the server accepts over HTTP (paid ones stay CLI-only).
const REAL_ENGINES = [
  { id: 'noobai', label: 'NoobAI XL (local GPU)' },
  { id: 'illustrious', label: 'Illustrious (local GPU)' },
  { id: 'sdxl', label: 'SDXL (local GPU)' },
];

export default function GenerationWorkspace({ novelId, hideHeader = false }) {
  const [engine, setEngine] = useState('stub');
  const [gpu, setGpu] = useState(null);
  const [chapters, setChapters] = useState([]);
  const [selected, setSelected] = useState('');
  const [jobs, setJobs] = useState([]);
  const [jobsError, setJobsError] = useState(null);
  const [chaptersError, setChaptersError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const push = useToast();
  const pollRef = useRef(null);

  // Asked on mount and whenever the engine picker is opened, not polled: it only decides whether a real engine can
  // be chosen, and the server re-checks when the job is queued.
  const loadGpu = useCallback(() => {
    api
      .gpu()
      .then(setGpu)
      .catch(() => setGpu({ available: false, free: false }));
  }, []);
  useEffect(() => {
    loadGpu();
  }, [loadGpu]);

  useEffect(() => {
    if (!novelId) return;
    api
      .chapters(novelId)
      .then((list) => {
        const ch = list || [];
        setChapters(ch);
        setChaptersError(null);
        setSelected((prev) => (prev && ch.some((c) => c.number === Number(prev)) ? prev : ch[0] ? ch[0].number : ''));
      })
      .catch((err) => {
        // Not silent: an empty chapter list with a disabled Generate button
        // and no explanation looked like a broken page.
        setChapters([]);
        setChaptersError(describeError(err, 'Could not load this book’s chapters.'));
      });
  }, [novelId]);

  const loadJobs = useCallback(() => {
    if (!novelId) return;
    api
      .listJobs(novelId)
      .then((list) => {
        setJobs((list || []).filter((j) => j.kind === 'render'));
        setJobsError(null);
      })
      .catch((err) => setJobsError(describeError(err, 'Could not load jobs.')));
  }, [novelId]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  // Poll while any render job is still in flight -- stops itself once
  // nothing is PENDING/RUNNING, so this doesn't hammer the server forever
  // after a job finishes.
  useEffect(() => {
    const inFlight = jobs.some((j) => j.status === 'PENDING' || j.status === 'RUNNING');
    clearInterval(pollRef.current);
    if (inFlight) {
      pollRef.current = setInterval(loadJobs, 2000);
    }
    return () => clearInterval(pollRef.current);
  }, [jobs, loadJobs]);

  const handleGenerate = () => {
    if (!selected) return;
    setSubmitting(true);
    api
      .renderGenerate(novelId, { chapters: [Number(selected)], engine })
      .then(() => {
        push(`Render job queued (${engine === 'stub' ? 'stub engine' : engine}).`, 'success');
        loadJobs();
      })
      .catch((err) => push(describeError(err, 'Could not queue render.'), 'danger'))
      .finally(() => setSubmitting(false));
  };

  return (
    <div className={hideHeader ? '' : 'mx-auto max-w-4xl px-6 py-10'}>
      {!hideHeader && (
      <header className="border-b border-border pb-6">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{novelId}</div>
        <h1 className="mt-2 font-display text-4xl text-text">Generation</h1>
      </header>
      )}

      <div className="mt-8">
        <Divider label="Render a chapter" className="mb-4" />
        <DepthCard interactive={false}>
          <CardBody className="flex flex-wrap items-end gap-4">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="gen-chapter">
                Chapter
              </label>
              <select
                id="gen-chapter"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="h-10 rounded-xl border border-border bg-transparent px-3 font-sans text-text"
              >
                {chapters.map((c) => (
                  <option key={c.number} value={c.number}>
                    Chapter {c.number}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="gen-engine">
                Engine
              </label>
              <select
                id="gen-engine"
                value={engine}
                onFocus={loadGpu}
                onChange={(e) => setEngine(e.target.value)}
                className="h-10 rounded-xl border border-border bg-transparent px-3 font-sans text-text"
              >
                <option value="stub">Placeholder (stub, no GPU)</option>
                {REAL_ENGINES.map((e) => (
                  <option key={e.id} value={e.id} disabled={!(gpu && gpu.available && gpu.free)}>
                    {e.label}
                  </option>
                ))}
              </select>
            </div>
            <Button size="md" disabled={submitting || !selected} onClick={handleGenerate}>
              {submitting ? 'Queuing…' : 'Generate panels'}
            </Button>
          </CardBody>
        </DepthCard>
        {chaptersError && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {chaptersError}
          </p>
        )}
        <p className="mt-2 text-sm text-muted" data-testid="engine-note">
          {engine === 'stub'
            ? 'The placeholder engine produces test panels and uses no GPU.'
            : 'A real engine loads an image model onto the GPU and takes minutes per chapter. Each render is kept as its own version.'}{' '}
          {gpu && !gpu.available && 'No NVIDIA GPU was found on the server, so only the placeholder engine can run here. '}
          {gpu && gpu.available && !gpu.free && `The GPU is busy (${gpu.used_mb} of ${gpu.total_mb} MiB in use), so real engines are unavailable until it is free. `}
          Paid engines run from the command line.
        </p>
      </div>

      <div className="mt-8">
        <Divider label="Job status" className="mb-4" />
        {jobsError && <div className="text-sm text-danger">{jobsError}</div>}
        {!jobsError && jobs.length === 0 && (
          <EmptyState title="No render jobs yet" description="Queue one above to see it here." />
        )}
        {jobs.length > 0 && (
          <div className="space-y-2">
            {jobs.map((j) => (
              <div key={j.job_id} className="border-b border-border py-2">
                <div className="flex items-center justify-between">
                  <div className="font-mono text-sm text-text">{j.job_id}</div>
                  <JobStatusBadge status={j.status} />
                </div>
                {j.status === 'FAILED' && <JobFailure kind="render" summary={j.error_summary} />}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <InspectorSection title="Render preview" defaultOpen>
          <EmptyState
            title="Not yet available"
            description="Previewing a single panel isn’t available in this screen yet."
          />
        </InspectorSection>
        <InspectorSection title="QA &amp; regeneration" defaultOpen>
          <EmptyState
            title="Not yet available"
            description="Quality checks and re-rendering a single panel aren’t available yet."
          />
        </InspectorSection>
      </div>
    </div>
  );
}
