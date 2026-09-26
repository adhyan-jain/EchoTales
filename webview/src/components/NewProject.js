import { useState, useMemo } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import Label from './ui/Label';
import Divider from './ui/Divider';
import { Card, CardBody } from './ui/Card';
import ManuscriptProgress from './ui/ManuscriptProgress';
import { describeError } from '../lib/errors';

// Each option states its processing model in one sentence rather than a
// feature-comparison grid -- per brief, this is meant to read as a
// considered choice ("what kind of thing is this"), not a pricing table.
const CONTENT_TYPES = [
  {
    value: 'novel',
    label: 'Novel',
    sentence: 'Resolve the cast. Understand the chapters. Build the world.',
  },
  {
    value: 'short_story',
    label: 'Short story',
    sentence: 'A smaller cast. The same transformation.',
  },
  {
    value: 'general_text',
    label: 'General text',
    sentence: 'One voice. One continuous narration.',
  },
  {
    value: 'roleplay',
    label: 'Roleplay',
    sentence: 'Dialogue-first storytelling.',
    comingSoon: true,
  },
];

// Placeholder rows for the "what ingestion progress will look like" preview
// below the disabled upload control -- every chapter PENDING, nothing live.
// See ManuscriptProgress.js: it renders honestly (no fake ticking) when fed
// this, which is exactly what an unstarted ingestion actually looks like.
const PREVIEW_CHAPTERS = [1, 2, 3, 4, 5].map((number) => ({ number, status: 'pending' }));

// Lowercase, punctuation/whitespace to hyphens, strip anything left that
// isn't alphanumeric-or-hyphen, and collapse/trim stray hyphens -- mirrors
// what a human would type by hand as an id, so the form doesn't need a
// separate id field at all.
function slugify(title) {
  return title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// Section 7.2: registers a new project via POST /api/projects. Section
// 7.2's original gap -- no upload/ingestion route existed at all -- is
// closed by the Product Orchestration track (`POST .../source`,
// `POST .../ingest`); this form now uploads the picked EPUB (if any)
// right after creating the project, and reports the real result rather
// than a placeholder. Ingestion itself still runs as its own explicit
// step (triggered from Project home / ManuscriptProgress), not
// automatically on upload -- uploading and ingesting are different jobs
// with different failure modes, and conflating them would hide which one
// actually failed.
export default function NewProject({ onCreated }) {
  const [title, setTitle] = useState('');
  const [contentType, setContentType] = useState('novel');
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [busy, setBusy] = useState(false);

  const id = useMemo(() => slugify(title), [title]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (busy || !title.trim() || !id) return;
    setError(null);
    setUploadError(null);
    setBusy(true);
    try {
      const result = await api.createProject(id, title.trim(), contentType);
      if (file) {
        try {
          await api.uploadSource(id, file);
        } catch (err) {
          // The project itself was created successfully -- an upload
          // failure is reported alongside it, not swallowed into a
          // generic "could not create project" error that would be
          // misleading (the project *was* created).
          setUploadError(describeError(err, 'Could not upload the source file.'));
        }
      }
      onCreated(result);
    } catch (err) {
      setError(describeError(err, 'Could not create project'));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 font-sans text-text">
      <div className="mb-8">
        <div className="font-mono text-xs uppercase tracking-widest text-muted">
          EchoTales &middot; New production
        </div>
        <h1 className="mt-2 font-display text-3xl text-text">Open a new project file</h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-10">
        <section>
          <Divider label="Content type" className="mb-4" />
          <div className="space-y-2">
            {CONTENT_TYPES.map((t) => {
              const selected = contentType === t.value;
              return (
                <button
                  type="button"
                  key={t.value}
                  disabled={t.comingSoon}
                  onClick={() => setContentType(t.value)}
                  aria-pressed={selected}
                  className={
                    'block w-full rounded-sm border px-5 py-4 text-left transition-colors ' +
                    (t.comingSoon
                      ? 'cursor-not-allowed border-border/60 opacity-50'
                      : selected
                      ? 'border-accent bg-surface'
                      : 'border-border bg-surface hover:border-accent/60')
                  }
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-display text-lg text-text">{t.label}</span>
                    {t.comingSoon ? (
                      <Label tone="neutral">Coming soon</Label>
                    ) : selected ? (
                      <Label tone="accent">Selected</Label>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-muted">{t.sentence}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section>
          <Divider label="Title" className="mb-4" />
          <div className="space-y-1.5">
            <Input
              id="np-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Reverend Insanity"
              autoFocus
            />
            <div className="font-mono text-xs text-muted">
              id: <span className="text-text">{id || '—'}</span>
            </div>
          </div>
        </section>

        <section>
          <Divider label="Source text" className="mb-4" />
          <Card>
            <CardBody className="space-y-4">
              <div className="flex items-center gap-3">
                <input
                  type="file"
                  aria-label="EPUB source file"
                  accept=".epub"
                  onChange={(e) => setFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
                  className="block flex-1 cursor-pointer text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border file:border-border file:bg-transparent file:px-3 file:py-1.5 file:font-sans file:text-sm file:text-text"
                />
              </div>
              <p className="text-sm text-muted">
                EPUB only (per this project's own "italics carry inner-monologue
                signal" rule -- a PDF would lose that). Uploading here does not
                ingest the text yet -- ingestion is a separate step, triggered from
                Project home once the file is attached, so a reviewer can see the
                upload and the ingest result as two distinct outcomes.
              </p>
              {file && (
                <div className="font-mono text-xs text-text">Selected: {file.name}</div>
              )}
              <div>
                <div className="mb-2 font-mono text-xs uppercase tracking-wider text-muted">
                  Once ingestion runs (preview)
                </div>
                <ManuscriptProgress chapters={PREVIEW_CHAPTERS} />
              </div>
            </CardBody>
          </Card>
        </section>

        {error && (
          <div className="rounded-sm border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {error}
          </div>
        )}
        {uploadError && (
          <div className="rounded-sm border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
            Project created, but the upload failed: {uploadError}. You can retry it from Project home.
          </div>
        )}

        <div className="flex items-center gap-4">
          <Button type="submit" disabled={busy || !title.trim()}>
            {busy ? 'Creating…' : 'Create project'}
          </Button>
          <p className="text-sm text-muted">
            This only registers the project. Source text is ingested separately, from Project home
            (or via the CLI).
          </p>
        </div>
      </form>
    </div>
  );
}
