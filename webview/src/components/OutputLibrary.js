import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import Divider from './ui/Divider';
import MediaArtifact from './ui/MediaArtifact';
import { EmptyState, LoadingState } from './ui/EmptyState';

// Real backend kinds only (`webview_server.py::_OUTPUT_KINDS`) -- "Reels"
// is deliberately not one of them: `render/reels.py` is unwired planning
// logic with no ffmpeg call (docs/STATUS.md), so there is no reels kind to
// list, ever, today. Shown as a fourth tab that always reads "not
// produced yet" rather than silently omitted, so the format exists in the
// product's shape per the plan's "look like the future production
// workstation" instruction -- honestly, not as a fake populated tab.
const FORMATS = [
  { key: 'video', label: 'Video' },
  { key: 'audio', label: 'Audio' },
  { key: 'reels', label: 'Reels' },
  { key: 'panels', label: 'Panels' },
];

export default function OutputLibrary({ novelId }) {
  const [status, setStatus] = useState('loading');
  const [output, setOutput] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [format, setFormat] = useState('video');

  const load = useCallback(() => {
    if (!novelId) return;
    setStatus((prev) => (prev === 'ready' ? 'ready' : 'loading'));
    api
      .listOutput(novelId)
      .then((data) => {
        setOutput(data);
        setStatus('ready');
      })
      .catch((err) => {
        if (err && (err.status === 404 || err.statusCode === 404)) {
          setOutput({ kinds: {} });
          setStatus('ready');
          return;
        }
        setErrorMessage((err && err.message) || 'Failed to load the output library.');
        setStatus('error');
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const items = format === 'reels' ? [] : ((output && output.kinds && output.kinds[format]) || []);
  const latest = ((output && output.kinds && output.kinds.video) || [])
    .slice()
    .sort((a, b) => (b.mtime || 0) - (a.mtime || 0))[0];

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header className="border-b border-border pb-6">
        <div className="font-mono text-xs uppercase tracking-widest text-muted">{novelId}</div>
        <h1 className="mt-2 font-display text-4xl text-text">Output library</h1>
      </header>

      {status === 'loading' && <LoadingState label="Reading output directory" />}

      {status === 'error' && (
        <div className="mt-8 border-l-2 border-danger pl-4 font-sans text-sm text-danger">
          Couldn&rsquo;t load the output library: {errorMessage}
        </div>
      )}

      {status === 'ready' && (
        <>
          {latest && (
            <div className="mt-8">
              <Divider label="Latest render" className="mb-4" />
              <MediaArtifact item={latest} />
            </div>
          )}

          <div className="mt-8">
            <Divider label="Browse" className="mb-4" />
            <div className="flex gap-1 border-b border-border pb-3">
              {FORMATS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setFormat(f.key)}
                  aria-pressed={format === f.key}
                  className={
                    'rounded-sm px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors ' +
                    (format === f.key
                      ? 'border border-accent text-accent'
                      : 'border border-transparent text-muted hover:text-text')
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="mt-4">
              {format === 'reels' ? (
                <EmptyState
                  title="Reels not produced yet"
                  description="The reels engine (render/reels.py) is planning logic only -- it has no ffmpeg call yet, so no reel file can exist here."
                />
              ) : items.length === 0 ? (
                <EmptyState title={`No ${format} yet`} description="Nothing has been rendered to this format for this project." />
              ) : (
                <div className="space-y-3">
                  {items.map((item) => (
                    <MediaArtifact key={item.path} item={item} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
