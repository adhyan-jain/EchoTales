import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import { EmptyState } from './ui/EmptyState';
import JobStatusBadge from './ui/JobStatusBadge';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';

/* Per panel of a chapter's newest render: the picture in use, a direction box and a Redraw button (a render job with
   `panel_id`; the original is never overwritten), and every candidate with "Use this". The pick is what pages and
   videos use afterwards (`render/regen.py`). Pictures go through `api.mediaUrl` so a password-protected server serves
   them. */
const picture = (novelId, path) =>
  api.mediaUrl(`/api/novels/${encodeURIComponent(novelId)}/output/file?path=${encodeURIComponent(path)}`);

function PanelCard({ novelId, panel, busy, onRedraw, onUse }) {
  const [direction, setDirection] = useState(panel.direction || '');
  const current = panel.candidates.find((c) => c.id === panel.chosen) || panel.candidates[0];
  const inputId = `redraw-direction-${panel.panel_seq}`;
  return (
    <div className="rounded-2xl border border-border bg-surface p-4" data-testid={`panel-${panel.panel_seq}`}>
      <div className="flex flex-wrap items-start gap-4">
        <img
          src={picture(novelId, current.path)}
          alt={`Panel ${panel.panel_seq}, in use: ${current.id}`}
          className="h-40 w-40 rounded-xl border border-border object-cover"
        />
        <div className="min-w-[14rem] flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-text">Panel {panel.panel_seq}</span>
            <Badge tone="neutral">{current.id === 'original' ? 'Original' : `Using ${current.id}`}</Badge>
          </div>
          <label htmlFor={inputId} className="mt-3 mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted">
            Direction for the redraw
          </label>
          <textarea
            id={inputId}
            rows={2}
            maxLength={400}
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            placeholder="What should change? Leave empty to draw again with the same direction."
            className="w-full rounded-xl border border-border bg-surface px-3 py-2 font-sans text-sm text-text outline-none placeholder:text-muted focus:border-accent focus-visible:ring-1 focus-visible:ring-accent"
          />
          <div className="mt-2">
            <Button size="sm" disabled={busy} onClick={() => onRedraw(panel, direction)}>
              Redraw panel {panel.panel_seq}
            </Button>
          </div>
        </div>
      </div>
      {panel.candidates.length > 1 && (
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label={`Candidates for panel ${panel.panel_seq}`}>
          {panel.candidates.map((c) => (
            <li key={c.id} className="rounded-xl border border-border bg-surface2 p-2">
              <img
                src={picture(novelId, c.path)}
                alt={`Candidate ${c.id} of panel ${panel.panel_seq}`}
                className="aspect-square w-full rounded-lg object-cover"
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-muted">{c.id}</span>
                {c.id === panel.chosen ? (
                  <Badge tone="success">In use</Badge>
                ) : (
                  <Button variant="secondary" size="sm" onClick={() => onUse(panel, c.id)}>
                    Use this
                    <span className="sr-only"> {c.id} for panel {panel.panel_seq}</span>
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PanelRedraw({ novelId, chapter, engine = 'stub', jobs = [], onQueued }) {
  const push = useToast();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const lastReload = useRef('');

  const load = useCallback(() => {
    if (!novelId || chapter === '' || chapter == null) return;
    api
      .listPanels(novelId, chapter)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((err) => {
        setData(null);
        setError(describeError(err, 'Could not load this chapter’s panels.'));
      });
  }, [novelId, chapter]);

  // Reload when the chapter changes, and again whenever a job's status changes (a finished redraw has new candidates).
  const signature = jobs.map((j) => `${j.job_id}:${j.status}`).join('|');
  useEffect(() => {
    if (lastReload.current === `${chapter}|${signature}`) return;
    lastReload.current = `${chapter}|${signature}`;
    load();
  }, [chapter, signature, load]);

  const redraw = (panel, direction) => {
    setBusy(true);
    api
      .redrawPanel(novelId, {
        chapter: Number(chapter),
        panel_id: panel.panel_id,
        version: data.version,
        engine,
        ...(direction.trim() ? { direction: direction.trim() } : {}),
      })
      .then(() => {
        push(`Redraw of panel ${panel.panel_seq} queued.`, 'success');
        if (onQueued) onQueued();
      })
      .catch((err) => push(describeError(err, 'Could not queue the redraw.'), 'danger'))
      .finally(() => setBusy(false));
  };

  const use = (panel, candidateId) =>
    api
      .choosePanelCandidate(novelId, {
        chapter: Number(chapter),
        panel_id: panel.panel_id,
        candidate_id: candidateId,
        version: data.version,
      })
      .then(() => {
        push(`Panel ${panel.panel_seq} now uses ${candidateId}.`, 'success');
        load();
      })
      .catch((err) => push(describeError(err, 'Could not save the choice.'), 'danger'));

  const latest = jobs[0];
  return (
    <section aria-label="Panels and redraws">
      {latest && (
        <p className="mb-3 flex items-center gap-2 text-sm text-muted">
          Latest render job <span className="font-mono text-text">{latest.job_id}</span>
          <JobStatusBadge status={latest.status} />
        </p>
      )}
      {error && <EmptyState title="No panels to work on yet" description={error} />}
      {!error && data && data.panels.length === 0 && (
        <EmptyState title="No panels in this render" description="Render the chapter first." />
      )}
      {!error && !data && <p className="text-sm text-muted">Loading panels…</p>}
      {data && data.panels.length > 0 && (
        <>
          <p className="mb-3 text-sm text-muted">
            Render {data.version}. A redraw adds candidates beside the original; nothing is overwritten.
          </p>
          <div className="space-y-4">
            {data.panels.map((p) => (
              <PanelCard key={p.panel_id} novelId={novelId} panel={p} busy={busy} onRedraw={redraw} onUse={use} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}
