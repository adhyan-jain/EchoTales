import { useState, useMemo } from 'react';
import { api } from '../api';

const CONTENT_TYPES = [
  { value: 'novel', label: 'Novel' },
  { value: 'short_story', label: 'Short Story' },
  { value: 'general_text', label: 'General Text' },
  { value: 'roleplay', label: 'Roleplay' },
];

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

// Section 7.2: registers a new project via POST /api/projects. This does NOT
// run text ingestion -- that stays a separate manual CLI step until this UI
// grows that scope, and the form says so explicitly (see help text below).
export default function NewProject({ onCreated }) {
  const [title, setTitle] = useState('');
  const [contentType, setContentType] = useState('novel');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const id = useMemo(() => slugify(title), [title]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (busy || !title.trim() || !id) return;
    setError(null);
    setBusy(true);
    try {
      const result = await api.createProject(id, title.trim(), contentType);
      onCreated(result);
    } catch (err) {
      setError(err.message || 'Could not create project');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="new-project-card" onSubmit={handleSubmit}>
      <h2>New project</h2>

      <label htmlFor="np-title">Title</label>
      <input
        id="np-title"
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="e.g. Reverend Insanity"
        autoFocus
      />
      <div className="new-project-id">
        id: <code>{id || '—'}</code>
      </div>

      <label htmlFor="np-type">Content type</label>
      <select id="np-type" value={contentType} onChange={(e) => setContentType(e.target.value)}>
        {CONTENT_TYPES.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>

      {error && <div className="new-project-error">{error}</div>}

      <button type="submit" className="btn-primary" disabled={busy || !title.trim()}>
        {busy ? 'Creating...' : 'Create project'}
      </button>
      <p className="new-project-note">
        This only registers the project. Ingest the source text separately via the
        CLI before this project has any content to review.
      </p>
    </form>
  );
}
