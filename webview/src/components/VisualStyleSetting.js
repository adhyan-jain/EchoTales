import React, { useState } from 'react';
import { api } from '../api';
import { describeError } from '../lib/errors';
import { useToast } from './ui/Toast';

/**
 * The genre panels and reference sheets are drawn in (persona/genre.py).
 * Every unlisted project used to be drawn as a Chinese cultivation novel,
 * and Omniscient Reader's Viewpoint got hanfu reference sheets in modern
 * Seoul; the genre is now a project setting, proposed from the book's own
 * words when nobody has chosen one. "Detected" is that proposal, so the
 * empty choice is never a silent default.
 */
export default function VisualStyleSetting({ novelId, project, onChanged }) {
  const push = useToast();
  const [saving, setSaving] = useState(false);
  if (!project || !project.genres) return null;

  const labelOf = (id) => (project.genres.find((g) => g.id === id) || {}).label || id;
  const value = project.visual_genre || '';

  const onChange = async (e) => {
    const genre = e.target.value || null;
    setSaving(true);
    try {
      await api.setGenre(novelId, genre);
      push(genre ? `Visual style set to ${labelOf(genre)}.` : 'Visual style follows the detected genre.', 'success');
      onChanged && onChanged();
    } catch (err) {
      push(describeError(err, 'Could not change the visual style.'), 'danger');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-3xl border border-border bg-surface p-6">
      <h2 className="font-display text-lg font-bold tracking-tight">Visual style</h2>
      <p className="mt-1 text-sm text-muted">
        The genre panels and reference sheets are drawn in. New renders use it; earlier versions are kept.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.14em] text-muted" htmlFor="visual-genre">
            Genre
          </label>
          <select
            id="visual-genre"
            value={value}
            disabled={saving}
            onChange={onChange}
            className="h-10 rounded-xl border border-border bg-transparent px-3 font-sans text-text"
          >
            <option value="">Detected from the text ({labelOf(project.detected_genre)})</option>
            {project.genres.map((g) => (
              <option key={g.id} value={g.id}>
                {g.label}
              </option>
            ))}
          </select>
        </div>
        <p className="text-sm text-muted" data-testid="effective-genre">
          Rendering as <span className="text-text">{labelOf(project.effective_genre)}</span>
        </p>
      </div>
    </section>
  );
}
