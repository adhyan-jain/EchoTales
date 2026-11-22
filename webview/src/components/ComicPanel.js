import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import JobFailure from './ui/JobFailure';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { waitForJob } from '../lib/jobs';

/* Comic to motion comic (roadmap M2): upload a .cbz, a .zip of page images or a .pdf, then queue the `comic` job. The
   server reads the pages by the uploaded name, never a path, and lists the built videos by the paths the output route
   already serves, so the link below is the same media route the output library uses. */
export default function ComicPanel({ novelId }) {
  const push = useToast();
  const [listing, setListing] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState(null);
  const [link, setLink] = useState('');
  const [rights, setRights] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  const load = useCallback(() => {
    return api
      .listComic(novelId)
      .then((r) => {
        if (gone.current) return;
        setListing({ sources: (r && r.sources) || [], videos: (r && r.videos) || [] });
        setLoadError('');
      })
      .catch((err) => {
        if (!gone.current) setLoadError(describeError(err, 'Could not load the comic sources.'));
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async () => {
    if (!file) return;
    setBusy('upload');
    try {
      const stored = await api.uploadComic(novelId, file);
      push(`Uploaded ${stored && stored.name ? stored.name : 'comic'}.`, 'success');
      setFile(null);
      setFileKey((k) => k + 1);
      await load();
    } catch (err) {
      push(describeError(err, 'Could not upload that comic.'), 'danger');
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const fetchLink = async () => {
    const url = link.trim();
    if (!url) return;
    setBusy('fetch');
    setFetchError('');
    try {
      const queued = await api.fetchComicLink(novelId, url, rights);
      const done = await waitForJob(novelId, queued.job_id, { cancelled: () => gone.current });
      if (gone.current) return;
      if (done && done.status === 'SUCCEEDED') {
        push('Pages downloaded. Build the motion comic from the list below.', 'success');
        setLink('');
        await load();
      } else {
        setFetchError(
          (done && done.error_summary) || 'The download did not finish. Check the link and try again.'
        );
      }
    } catch (err) {
      setFetchError(describeError(err, 'Could not start the download.'));
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const build = async (name) => {
    setBusy(`build:${name}`);
    setFailure(null);
    try {
      const queued = await api.triggerStage(novelId, 'comic', { stage: 'build', source: name });
      const done = await waitForJob(novelId, queued.job_id, { cancelled: () => gone.current });
      if (gone.current) return;
      if (done && done.status === 'SUCCEEDED') {
        push('Motion comic built.', 'success');
      } else {
        setFailure({ kind: 'comic', summary: done && done.error_summary });
      }
      await load();
    } catch (err) {
      push(describeError(err, 'Could not queue the comic build.'), 'danger');
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const sources = (listing && listing.sources) || [];
  const videos = (listing && listing.videos) || [];

  return (
    <section aria-label="Comic" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Comic</h2>
      <p className="mt-1 text-sm text-muted">
        Turn a comic or manga you own into a voiced motion comic. Upload a .cbz, a .zip of page images or a .pdf, then
        build it; the original lettering stays as a subtitle track.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="comic-file">
            Comic file
          </label>
          <input
            key={fileKey}
            id="comic-file"
            type="file"
            accept=".cbz,.zip,.pdf"
            onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
            className="block cursor-pointer text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border file:border-border file:bg-transparent file:px-3 file:py-1.5 file:font-sans file:text-sm file:text-text"
          />
        </div>
        <Button variant="secondary" disabled={!file || !!busy} onClick={upload}>
          {busy === 'upload' ? 'Uploading…' : 'Upload comic'}
        </Button>
      </div>

      <div className="mt-5">
        <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="comic-link">
          Paste a chapter link
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Input
            id="comic-link"
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            placeholder="https://example.com/comic/chapter-1"
            className="min-w-0 flex-1"
          />
          <Button variant="secondary" disabled={!link.trim() || !!busy} onClick={fetchLink}>
            {busy === 'fetch' ? 'Downloading…' : 'Download pages'}
          </Button>
        </div>
        <label className="mt-2 flex cursor-pointer items-start gap-2 text-sm text-text">
          <input type="checkbox" className="mt-1" checked={rights} onChange={(e) => setRights(e.target.checked)} />
          <span>I have the right to use this content.</span>
        </label>
        <p className="mt-1 text-xs text-muted">
          You are responsible for having the right to use anything you download. Pages that need a login or are
          protected are not downloaded.
        </p>
        {fetchError && (
          <div role="alert" className="mt-3 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {fetchError}
          </div>
        )}
      </div>

      {loadError && (
        <div role="alert" className="mt-4 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}
      {failure && <JobFailure kind={failure.kind} summary={failure.summary} />}

      <ul className="mt-5 space-y-3">
        {listing && sources.length === 0 && !loadError && (
          <li className="text-sm text-muted">No comic uploaded to this project yet.</li>
        )}
        {sources.map((s) => (
          <li key={s.name} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border px-4 py-3">
            <div>
              <span className="font-mono text-sm text-text">{s.name}</span>
              <span className="ml-2 text-xs text-muted">{s.kind === 'pdf' ? 'PDF' : `${s.pages} pages`}</span>
            </div>
            <Button size="sm" disabled={!!busy} aria-label={`Build ${s.name}`} onClick={() => build(s.name)}>
              {busy === `build:${s.name}` ? 'Building…' : 'Build motion comic'}
            </Button>
          </li>
        ))}
      </ul>

      {videos.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Built videos</h3>
          <ul className="mt-2 space-y-1">
            {videos.map((v) => (
              <li key={v.path}>
                <a
                  href={api.outputFileUrl(novelId, v.path)}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-sm text-text underline decoration-border underline-offset-4"
                >
                  {v.version}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
