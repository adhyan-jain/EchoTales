import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import JobFailure from './ui/JobFailure';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { waitForJob } from '../lib/jobs';

const sum = (counts) => Object.values(counts || {}).reduce((a, b) => a + Number(b || 0), 0);
const kb = (bytes) => (bytes < 1024 ? `${bytes} B` : `${Math.round(bytes / 1024)} KB`);

/* Adaptation packs (roadmap M4): the cast, descriptions, voices, direction and corrections of this book as one file
   that carries no book text. Importing applies only what matches this copy of the book's chapters and reports the
   rest, so the counts below are the whole answer to "what did that do". */
export default function PacksPanel({ novelId }) {
  const push = useToast();
  const [packs, setPacks] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [file, setFile] = useState(null);
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState('');
  const [failure, setFailure] = useState(null);
  const gone = useRef(false);

  useEffect(() => () => { gone.current = true; }, []);

  const load = useCallback(() => {
    return api
      .listPacks(novelId)
      .then((r) => {
        if (gone.current) return;
        setPacks((r && r.packs) || []);
        setLoadError('');
      })
      .catch((err) => {
        if (!gone.current) setLoadError(describeError(err, 'Could not load the packs.'));
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (kind, params, label, key) => {
    setBusy(key);
    setFailure(null);
    try {
      const queued = await api.triggerStage(novelId, kind, params);
      const done = await waitForJob(novelId, queued.job_id, { cancelled: () => gone.current });
      if (gone.current) return;
      if (done && done.status === 'SUCCEEDED') {
        push(`${label} finished.`, 'success');
      } else {
        setFailure({ kind, summary: done && done.error_summary });
      }
      await load();
    } catch (err) {
      push(describeError(err, `Could not queue: ${label.toLowerCase()}.`), 'danger');
    } finally {
      if (!gone.current) setBusy('');
    }
  };

  const upload = async () => {
    if (!file) return;
    setBusy('upload');
    try {
      await api.uploadPack(novelId, file);
      push('Pack uploaded.', 'success');
      setFile(null);
      setFileKey((k) => k + 1);
      await load();
    } catch (err) {
      push(describeError(err, 'Could not upload that pack.'), 'danger');
    } finally {
      setBusy('');
    }
  };

  const exportName = name.trim();

  return (
    <section aria-label="Adaptation packs" className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Adaptation packs</h2>
      <p className="mt-1 text-sm text-muted">
        Share this book’s cast, descriptions, voices and corrections as one file. A pack carries none of the book’s
        text, and importing only applies what matches your copy of the chapters.
      </p>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-[12rem] flex-1">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pack-name">
            Pack name
          </label>
          <Input id="pack-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={novelId} />
        </div>
        <Button
          variant="secondary"
          disabled={!!busy}
          onClick={() => run('pack_export', exportName ? { name: exportName } : {}, 'Export', 'export')}
        >
          {busy === 'export' ? 'Exporting…' : 'Export pack'}
        </Button>
      </div>

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="pack-file">
            Pack file
          </label>
          <input
            key={fileKey}
            id="pack-file"
            type="file"
            accept=".etpack"
            onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
            className="block cursor-pointer text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border file:border-border file:bg-transparent file:px-3 file:py-1.5 file:font-sans file:text-sm file:text-text"
          />
        </div>
        <Button variant="secondary" disabled={!file || !!busy} onClick={upload}>
          {busy === 'upload' ? 'Uploading…' : 'Upload pack'}
        </Button>
      </div>

      {loadError && (
        <div role="alert" className="mt-4 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {loadError}
        </div>
      )}
      {failure && <JobFailure kind={failure.kind} summary={failure.summary} />}

      <ul className="mt-5 space-y-3">
        {packs && packs.length === 0 && !loadError && (
          <li className="text-sm text-muted">No packs in this project yet. Export one, or upload a pack someone shared.</li>
        )}
        {(packs || []).map((p) => (
          <li key={p.name} className="rounded-2xl border border-border px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="font-mono text-sm text-text">{p.name}</span>
                <span className="ml-2 text-xs text-muted">{kb(p.bytes)}</span>
              </div>
              <Button
                size="sm"
                disabled={!!busy}
                aria-label={`Import ${p.name}`}
                onClick={() => run('pack_import', { name: p.name }, 'Import', `import:${p.name}`)}
              >
                {busy === `import:${p.name}` ? 'Importing…' : 'Import'}
              </Button>
            </div>
            {p.report && <ImportReport name={p.name} report={p.report} />}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ImportReport({ name, report }) {
  const applied = sum(report.applied);
  const skipped = report.skipped || [];
  return (
    <div aria-label={`Import report for ${name}`} className="mt-3 text-sm">
      <p className="text-text">
        Applied {applied}
        {Object.keys(report.applied || {}).length > 0 && (
          <span className="text-muted"> ({Object.entries(report.applied).map(([k, v]) => `${k} ${v}`).join(', ')})</span>
        )}
        . Skipped {skipped.length}.
      </p>
      {skipped.length > 0 && (
        <details className="mt-1 text-muted">
          <summary className="cursor-pointer select-none text-xs underline decoration-border underline-offset-4">
            Why items were skipped
          </summary>
          <ul className="mt-1 space-y-0.5 text-xs">
            {skipped.slice(0, 50).map((s, i) => (
              <li key={i}>
                {s.kind}
                {s.what ? ` ${s.what}` : ''}
                {s.chapter != null ? ` (chapter ${s.chapter})` : ''}: {s.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
