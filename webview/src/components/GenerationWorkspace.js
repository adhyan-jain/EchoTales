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
   default, otherwise the engines the server enables for ECHOTALES_COMPUTE and
   the provider variables -- `pipeline/compute.py`, `/api/compute`) and watching
   its real status. A finished or failed job raises a browser notification (when
   the person allowed them), so a render that takes minutes can be left alone. Per-beat render *preview* needs a `beat_id`/`cast_self_ids`
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
// What each engine is called. Which of them are offered, and why one is disabled, comes from the server
// (`/api/compute`, pipeline/compute.py): the compute mode and the provider variables decide, not this list.
const ENGINE_LABELS = {
  stub: 'Placeholder (stub, no model)',
  noobai: 'NoobAI XL (local GPU)',
  illustrious: 'Illustrious (local GPU)',
  sdxl: 'SDXL (local GPU)',
  runpod: 'RunPod (cloud)',
  gemini: 'Gemini (cloud)',
  openrouter: 'OpenRouter (cloud)',
};

const MODE_NOTES = {
  'local-low': 'Laptop-safe: one model at a time, a memory check before a render, and previews by default.',
  'local-high': 'Workstation: full chapters and no extra guards.',
  cloud: 'Cloud: the models run on RunPod, so nothing is loaded on this machine.',
};

function minutes(seconds) {
  if (seconds == null) return null;
  const m = Math.max(1, Math.round(seconds / 60));
  return m >= 90 ? `about ${(m / 60).toFixed(1)} hours` : `about ${m} min`;
}

export default function GenerationWorkspace({ novelId, hideHeader = false }) {
  const [engine, setEngine] = useState('stub');
  const [tier, setTier] = useState(null);
  const [compute, setCompute] = useState(null);
  const [chapters, setChapters] = useState([]);
  const [selected, setSelected] = useState('');
  const [jobs, setJobs] = useState([]);
  const [jobsError, setJobsError] = useState(null);
  const [chaptersError, setChaptersError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const push = useToast();
  const pollRef = useRef(null);

  // Asked on mount and whenever the engine picker is opened, not polled: it decides which engines can be chosen and
  // the server re-checks memory and the GPU when the job is queued.
  const loadCompute = useCallback(() => {
    api
      .compute()
      .then(setCompute)
      .catch(() => setCompute({ mode: 'local-low', engines: ['stub'], refusals: {}, scenes: {}, gpu: { available: false } }));
  }, []);
  useEffect(() => {
    loadCompute();
  }, [loadCompute]);

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

  // Tell the person when a render they queued ends: it can take many minutes, and they should not have to watch.
  const wasInFlight = useRef(new Set());
  useEffect(() => {
    const nowInFlight = new Set(jobs.filter((j) => j.status === 'PENDING' || j.status === 'RUNNING').map((j) => j.job_id));
    jobs.forEach((j) => {
      if (wasInFlight.current.has(j.job_id) && !nowInFlight.has(j.job_id)) {
        const ok = j.status === 'SUCCEEDED';
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
          try {
            new Notification(ok ? 'Render finished' : 'Render stopped', { body: `${novelId}: ${j.status.toLowerCase()}` });
          } catch (e) {
            /* a notification that cannot be shown is not worth failing the page */
          }
        }
      }
    });
    wasInFlight.current = nowInFlight;
  }, [jobs, novelId]);

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

  const activeTier = tier || (compute && compute.default_tier) || 'full';
  const scenes = compute && compute.scenes ? compute.scenes[activeTier] : null;
  const perImage = compute && compute.seconds_per_panel ? compute.seconds_per_panel[engine] : null;
  const eta =
    scenes && perImage != null && compute.images_per_scene ? minutes(perImage * compute.images_per_scene * scenes) : null;

  const handleGenerate = () => {
    if (!selected) return;
    setSubmitting(true);
    api
      .renderGenerate(novelId, { chapters: [Number(selected)], engine, tier: activeTier })
      .then(() => {
        if (engine !== 'stub' && typeof Notification !== 'undefined' && Notification.permission === 'default') {
          Notification.requestPermission();
        }
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
                onFocus={loadCompute}
                onChange={(e) => setEngine(e.target.value)}
                className="h-10 rounded-xl border border-border bg-transparent px-3 font-sans text-text"
              >
                {(compute ? compute.engines : ['stub']).map((e) => {
                  const refusal = compute && compute.refusals ? compute.refusals[e] : null;
                  return (
                    <option key={e} value={e} disabled={!!refusal} title={refusal || undefined}>
                      {ENGINE_LABELS[e] || e}
                    </option>
                  );
                })}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="gen-tier">
                Scope
              </label>
              <select
                id="gen-tier"
                value={activeTier}
                onChange={(e) => setTier(e.target.value)}
                className="h-10 rounded-xl border border-border bg-transparent px-3 font-sans text-text"
              >
                <option value="preview">Preview ({compute && compute.scenes ? compute.scenes.preview : 3} scenes)</option>
                <option value="full">Full chapter ({compute && compute.scenes ? compute.scenes.full : 70} scenes)</option>
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
            ? 'The placeholder engine produces test panels and loads no model.'
            : 'A real engine generates every image of the scope you chose. Each render is kept as its own version.'}{' '}
          {eta && engine !== 'stub' && <span data-testid="eta">Roughly {eta} on this machine (images only). </span>}
          {compute && MODE_NOTES[compute.mode]}{' '}
          {compute && compute.llm_missing && compute.llm_missing.length > 0 &&
            `The ${compute.llm_provider} language model still needs ${compute.llm_missing.join(', ')}. `}
          {compute && engine !== 'stub' && compute.refusals && compute.refusals[engine] && `${compute.refusals[engine]}. `}
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
