import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Divider from './ui/Divider';
import DepthCard from './ui/DepthCard';
import { CardBody } from './ui/Card';
import Label from './ui/Label';
import { EmptyState, LoadingState } from './ui/EmptyState';

/* Production-desk overview, not a KPI dashboard (plan Section 9): what
   state this project is in and what to do next. Wires the real
   `GET /api/projects` listing (Product Orchestration track) -- source
   uploaded / ingested / last job -- rather than fabricating progress. */
export default function ProjectHome({ novelId, onNewProject }) {
  const [status, setStatus] = useState('loading');
  const [projects, setProjects] = useState([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [ingesting, setIngesting] = useState(false);

  const load = useCallback(() => {
    setStatus((prev) => (prev === 'ready' ? 'ready' : 'loading'));
    api
      .listProjects()
      .then((list) => {
        setProjects(list || []);
        setStatus('ready');
      })
      .catch((err) => {
        setErrorMessage((err && err.message) || 'Failed to load projects.');
        setStatus('error');
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const current = projects.find((p) => p.id === novelId);

  const startIngest = () => {
    setIngesting(true);
    api
      .triggerStage(novelId, 'ingest')
      .then(load)
      .catch((err) => setErrorMessage((err && err.message) || 'Could not start ingestion.'))
      .finally(() => setIngesting(false));
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <header className="flex items-start justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-muted">Production desk</div>
          <h1 className="mt-2 font-display text-4xl text-text">Project</h1>
        </div>
        <Button variant="secondary" size="sm" onClick={onNewProject}>
          + New project
        </Button>
      </header>

      {status === 'loading' && <LoadingState label="Loading project status" />}

      {status === 'error' && (
        <div className="mt-8 border-l-2 border-danger pl-4 font-sans text-sm text-danger">
          Couldn&rsquo;t reach the orchestration backend: {errorMessage}. Start it with{' '}
          <code className="font-mono">uv run echotales webview-server --source ...</code>.
        </div>
      )}

      {status === 'ready' && !current && (
        <div className="mt-8">
          <EmptyState
            title="No lifecycle data for this project"
            description="This project isn't tracked by the orchestration backend yet -- it may be a static export, or was registered outside this server."
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
                    {current.last_job.error_summary && (
                      <div className="mt-1 text-sm text-danger">{current.last_job.error_summary}</div>
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
      <div className="font-mono text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-1 font-display text-lg ${toneClass}`}>{value}</div>
    </div>
  );
}
