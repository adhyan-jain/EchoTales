import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import Divider from './ui/Divider';
import MediaArtifact, { AUDIO_RE, IMAGE_RE, VIDEO_RE } from './ui/MediaArtifact';
import { thumbUrl, fileUrl } from '../lib/media';
import { EmptyState, LoadingState } from './ui/EmptyState';
import { describeError } from '../lib/errors';

// Real backend kinds only (`webview_server.py::_OUTPUT_KINDS`). There used
// to be a fourth "Reels" tab that could only ever say "not produced yet":
// chapter videos are already vertical (1080x1920, verified with ffprobe on a
// real render), so a separate empty tab was a dead end (removed 2026-09-26).
const FORMATS = [
  { key: 'video', label: 'Video' },
  { key: 'audio', label: 'Audio' },
  { key: 'panels', label: 'Panels' },
];

const PAGE = 24;

export default function OutputLibrary({ novelId, hideHeader = false }) {
  const [status, setStatus] = useState('loading');
  const [output, setOutput] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [format, setFormat] = useState('video');
  const [visible, setVisible] = useState(PAGE);

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
        setErrorMessage(describeError(err, 'Failed to load the output library.'));
        setStatus('error');
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  // Only files a person can watch, hear or look at, newest first. The raw
  // listing is a filesystem walk: it includes manifests (.jsonl), notes (.md)
  // and, for panels, over a thousand files across every version ever rendered
  // -- all of which used to be rendered at once as bare filenames.
  const MEDIA_RE = { video: VIDEO_RE, audio: AUDIO_RE, panels: IMAGE_RE };
  const listOf = (kind) =>
    ((output && output.kinds && output.kinds[kind]) || [])
      .filter((i) => (MEDIA_RE[kind] ? MEDIA_RE[kind].test(i.path) : true))
      .sort((a, b) => (b.mtime || 0) - (a.mtime || 0));
  const items = listOf(format);
  const latest = listOf('video')[0];
  const shown = items.slice(0, visible);

  return (
    <div className={hideHeader ? '' : 'mx-auto max-w-4xl px-6 py-10'}>
      {!hideHeader && (
      <header className="border-b border-border pb-6">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">{novelId}</div>
        <h1 className="mt-2 font-display text-4xl text-text">Output library</h1>
      </header>
      )}

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
              <MediaArtifact item={latest} novelId={novelId} />
            </div>
          )}

          <div className="mt-8">
            <Divider label="Browse" className="mb-4" />
            <div className="flex gap-1 border-b border-border pb-3">
              {FORMATS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => {
                    setFormat(f.key);
                    setVisible(PAGE);
                  }}
                  aria-pressed={format === f.key}
                  className={
                    'rounded-xl border px-3.5 py-1.5 text-sm font-medium transition-colors ' +
                    (format === f.key
                      ? 'border-accent/40 bg-primary/15 text-text'
                      : 'border-transparent text-muted hover:bg-surface2 hover:text-text')
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="mt-4">
              {items.length === 0 ? (
                <EmptyState title={`No ${format} yet`} description="Nothing has been rendered to this format for this project." />
              ) : (
                <>
                  {format === 'panels' ? (
                    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                      {shown.map((item) => (
                        <li key={item.path}>
                          <a
                            href={fileUrl(novelId, item.path)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="group block overflow-hidden rounded-xl border border-border bg-surface2"
                            aria-label={`Open ${item.path.split('/').pop()} full size`}
                          >
                            <img
                              src={thumbUrl(novelId, item.path, 320)}
                              alt={`Panel ${item.path.split('/').pop()}`}
                              loading="lazy"
                              className="aspect-[3/4] w-full object-cover transition-transform duration-300 group-hover:scale-105"
                            />
                          </a>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div className="space-y-3">
                      {shown.map((item) => (
                        <MediaArtifact key={item.path} item={item} novelId={novelId} compact />
                      ))}
                    </div>
                  )}
                  <div className="mt-4 flex items-center justify-between gap-3 text-sm text-muted">
                    <span>
                      Showing {shown.length} of {items.length}
                    </span>
                    {shown.length < items.length && (
                      <button
                        type="button"
                        onClick={() => setVisible((v) => v + PAGE)}
                        className="rounded-xl border border-border px-4 py-2 font-medium text-text hover:border-accent/60"
                      >
                        Show more
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
