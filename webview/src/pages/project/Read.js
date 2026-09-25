import React, { useCallback, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import ChapterNav from '../../components/ChapterNav';
import EntitySidebar from '../../components/EntitySidebar';
import ScriptView from '../../components/ScriptView';
import Tooltip from '../../components/Tooltip';
import { CenterMessage } from '../../components/app/Chrome';
import { useProject } from '../../lib/ProjectContext';

/**
 * Read-only reader. The chapter lives in the path (/read/12) and a focused
 * character in the query (?focus=<id>), so a reading position and a filter
 * can be bookmarked or shared -- the old viewer kept both in component
 * state, lost on every reload. Edit affordances are deliberately absent;
 * they live on the Review page.
 */
export default function Read() {
  const { novel, error } = useProject();
  const { chapter: chapterParam } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [tip, setTip] = useState({ visible: false, x: 0, y: 0, text: '' });
  const focusId = params.get('focus');

  const chapters = useMemo(() => (novel ? novel.chapters : []), [novel]);
  const idx = useMemo(() => {
    if (!chapters.length || chapterParam == null) return 0;
    const i = chapters.findIndex((c) => String(Number(c.number)) === chapterParam);
    return i >= 0 ? i : 0;
  }, [chapters, chapterParam]);
  const chapter = chapters[idx];

  const goTo = useCallback(
    (i) => {
      const c = chapters[i];
      if (!c) return;
      const qs = params.toString();
      const base = chapterParam == null ? '.' : '..';
      navigate(`${base}/${Number(c.number)}${qs ? `?${qs}` : ''}`, { relative: 'path' });
      window.scrollTo({ top: 0 });
    },
    [chapters, chapterParam, navigate, params]
  );

  const toggleFocus = useCallback(
    (id) => {
      const next = new URLSearchParams(params);
      if (next.get('focus') === id) next.delete('focus');
      else next.set('focus', id);
      setParams(next, { replace: true });
    },
    [params, setParams]
  );

  const coverage = useMemo(() => {
    if (!chapter) return '';
    let total = 0;
    let attributed = 0;
    chapter.spans.forEach((s) => {
      if (s.type === 'DIALOGUE') {
        total += 1;
        if (s.speaker) attributed += 1;
      }
    });
    return total ? `${attributed}/${total} lines voiced` : '';
  }, [chapter]);

  const onMarkHover = useCallback((e, text) => setTip({ visible: true, x: e.clientX, y: e.clientY, text }), []);
  const onMarkMove = useCallback((e) => setTip((p) => (p.visible ? { ...p, x: e.clientX, y: e.clientY } : p)), []);
  const onMarkLeave = useCallback(() => setTip((p) => ({ ...p, visible: false })), []);

  if (error) return <CenterMessage title="Couldn’t load this book">{error}</CenterMessage>;
  if (!novel) return <CenterMessage>Loading the book…</CenterMessage>;

  const focused = focusId ? novel.entities.find((e) => e.id === focusId) : null;

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-w-0 flex-1">
        <ChapterNav chapters={chapters} chapterIdx={idx} onChange={goTo} coverage={coverage} />
        {focused && (
          <div className="mx-auto mt-4 flex max-w-[760px] items-center gap-2 px-6 text-sm">
            <span className="text-muted">Highlighting</span>
            <span className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-accent/10 px-3 py-1 font-medium">
              <span className="h-2 w-2 rounded-full" style={{ background: focused.colour }} aria-hidden="true" />
              {focused.label}
              <button
                type="button"
                onClick={() => toggleFocus(focused.id)}
                aria-label={`Stop highlighting ${focused.label}`}
                className="text-muted hover:text-text"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          </div>
        )}
        <ScriptView
          chapter={chapter}
          focusId={focusId}
          onMarkHover={onMarkHover}
          onMarkMove={onMarkMove}
          onMarkLeave={onMarkLeave}
          editMode={false}
        />
      </div>

      <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-l border-border bg-surface xl:block" aria-label="Cast in this book">
        <EntitySidebar
          entities={novel.entities}
          search={search}
          onSearchChange={setSearch}
          focusId={focusId}
          onToggleFocus={toggleFocus}
          editMode={false}
          mergeSourceId={null}
        />
      </aside>
      <Tooltip tip={tip} />
    </div>
  );
}
