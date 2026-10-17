import React, { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Divider from './ui/Divider';
import DepthCard from './ui/DepthCard';
import { CardBody } from './ui/Card';
import Label from './ui/Label';
import { EmptyState, LoadingState } from './ui/EmptyState';
import { describeError, isNetworkError } from '../lib/errors';
import JobFailure from './ui/JobFailure';

/* Production-desk overview, not a KPI dashboard (plan Section 9): what
   state this project is in and what to do next. Wires the real
   `GET /api/projects` listing (Product Orchestration track) -- source
   uploaded / ingested / last job -- rather than fabricating progress. */
export default function ProjectHome({ novelId, onNewProject, hideHeader = false, onChanged }) {
  const [status, setStatus] = useState('loading');
  const [projects, setProjects] = useState([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [unreachable, setUnreachable] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  // `quiet` is the poll: it refreshes this card only. The parent's project list (`onChanged`) is told once, when the
  // job ends, not on every tick -- two list requests per tick before.
  const load = useCallback((quiet = false) => {
    setStatus((prev) => (prev === 'ready' ? 'ready' : 'loading'));
    api
      .listProjects()
      .then((list) => {
        setProjects(list || []);
        setStatus('ready');
        if (onChanged && quiet !== true) onChanged();
      })
      .catch((err) => {
        setUnreachable(isNetworkError(err));
        setErrorMessage(describeError(err, 'Failed to load projects.'));
        setStatus('error');
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const current = projects.find((p) => p.id === novelId);

  // `load` runs once right after a job is queued, when it is still PENDING, and nothing refreshed it afterwards:
  // after "Start ingestion" the page said "Not yet" and PENDING until a reload (found in the 2026-10-18 browser
  // pass). Poll while this project's last job is in flight, like the Studio does; it stops itself when the job ends.
  const pollRef = useRef(null);
  const lastStatus = current && current.last_job ? current.last_job.status : null;
  const wasInFlight = useRef(false);
  useEffect(() => {
    clearInterval(pollRef.current);
    const inFlight = lastStatus === 'PENDING' || lastStatus === 'RUNNING';
    if (inFlight) {
      // Capped at five minutes: a job left RUNNING by a server restart is not polled forever.
      let ticks = 0;
      pollRef.current = setInterval(() => {
        ticks += 1;
        if (ticks > 150) clearInterval(pollRef.current);
        else load(true);
      }, 2000);
    } else if (wasInFlight.current && onChanged) {
      onChanged();
    }
    wasInFlight.current = inFlight;
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastStatus, load]);

  const startIngest = () => {
    setIngesting(true);
    api
      .triggerStage(novelId, 'ingest')
      .then(load)
      .catch((err) => setErrorMessage(describeError(err, 'Could not start ingestion.')))
      .finally(() => setIngesting(false));
  };

  return (
    <div className={hideHeader ? '' : 'mx-auto max-w-3xl px-6 py-10'}>
      {!hideHeader && (
      <header className="flex items-start justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Production desk</div>
          <h1 className="mt-2 font-display text-4xl text-text">Project</h1>
        </div>
        <Button variant="secondary" size="sm" onClick={onNewProject}>
          + New project
        </Button>
      </header>
      )}

      {status === 'loading' && <LoadingState label="Loading project status" />}

      {status === 'error' && (
        <div className="mt-8 border-l-2 border-danger pl-4 font-sans text-sm text-danger">
          {errorMessage}
          {unreachable && (
            <>
              {' '}Start it with <code className="font-mono">uv run echotales webview-server --source …</code>.
            </>
          )}
        </div>
      )}

      {status === 'ready' && !current && (
        <div className="mt-8">
          <EmptyState
            title="No lifecycle data for this project"
            description="This project isn’t set up for pipeline runs on this server, so there is no ingestion status to show."
          />
        </div>
      )}

      {status === 'ready' && current && (
        <div className="mt-6">
          <Divider label="Status" className="mb-4" />
          <DepthCard interactive={false}>
            <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Content type" value={current.content_type} />
              <Stat
                label="Source"
                value={current.source_uploaded ? 'Uploaded' : 'Not uploaded'}
                tone={current.source_uploaded ? 'success' : 'neutral'}
              />
              <Stat
                label="Ingested"
                value={current.ingested ? `${current.chapter_count} chapters` : 'Not yet'}
                tone={current.ingested ? 'success' : 'neutral'}
              />
              <Stat label="Jobs run" value={String(current.job_count)} />
            </CardBody>
          </DepthCard>

          {current.source_uploaded && !current.ingested && (
            <div className="mt-4 flex items-center justify-between gap-3 border border-border px-4 py-3">
              <p className="text-sm text-muted">Source is uploaded but not ingested yet.</p>
              <Button size="sm" disabled={ingesting} onClick={startIngest}>
                {ingesting ? 'Starting…' : 'Start ingestion'}
              </Button>
            </div>
          )}

          {current.last_job && (
            <div className="mt-6">
              <Divider label="Last job" className="mb-4" />
              <DepthCard interactive={false}>
                <CardBody className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-mono text-sm text-text">{current.last_job.kind}</div>
                    {current.last_job.status === 'FAILED' && (
                      <JobFailure kind={current.last_job.kind} summary={current.last_job.error_summary} />
                    )}
                  </div>
                  <Label tone={current.last_job.status === 'FAILED' ? 'danger' : 'neutral'}>
                    {current.last_job.status}
                  </Label>
                </CardBody>
              </DepthCard>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, tone = 'neutral' }) {
  const toneClass = { success: 'text-success', danger: 'text-danger', neutral: 'text-text' }[tone];
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className={`mt-1 font-display text-lg ${toneClass}`}>{value}</div>
    </div>
  );
}
