import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { api } from '../../api';
import ChapterNav from '../../components/ChapterNav';
import EntitySidebar from '../../components/EntitySidebar';
import ScriptView from '../../components/ScriptView';
import Tooltip from '../../components/Tooltip';
import { CenterMessage, ProjectProblem } from '../../components/app/Chrome';
import { useNovelData } from '../../lib/ProjectContext';

/**
 * The chapter as a reader at that chapter knows its cast. The whole-volume
 * payload labels every mark and speaker with the final canonical name, so a
 * reader on chapter 2 hovering "the masked guest" read the name the book
 * reveals later (tests/test_reader_cast.py builds exactly that book). A mark
 * or speaker takes its label from the reader cast; anything the cast does not
 * know falls back to what is printed on the page, never to the volume's label.
 */
export function readerChapter(chapter, castById) {
  if (!chapter) return chapter;
  return {
    ...chapter,
    spans: chapter.spans.map((s) => {
      const marks = s.marks.map((m) => {
        const known = m.id && castById ? castById.get(m.id) : null;
        return { ...m, label: known ? known.label : m.surface || s.text.slice(m.s, m.e) };
      });
      if (!s.speaker || s.anonymous_speaker) return { ...s, marks };
      const speakerId = s.speaker_entity_id || s.speaker_id;
      const known = speakerId && castById ? castById.get(speakerId) : null;
      // `castById` is null while the cast loads: an ellipsis, not "unattributed",
      // which would claim the line has no speaker.
      return { ...s, marks, speaker: known ? known.label : castById ? 'unnamed speaker' : '…' };
    }),
  };
}

/**
 * Read-only reader. The chapter lives in the path (/read/12) and a focused
 * character in the query (?focus=<id>), so a reading position and a filter
 * can be bookmarked or shared -- the old viewer kept both in component
 * state, lost on every reload. Edit affordances are deliberately absent;
 * they live on the Review page. Names, aliases and the cast list come from
 * the reader cast at this chapter (`api.readerCast`), not the whole volume,
 * so the page does not spoil a later reveal; the Review page keeps the
 * whole-volume view a reviewer needs.
 */
export default function Read() {
  const { novel, novelId, error, errorStatus, refetch } = useNovelData();
  const { chapter: chapterParam } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [tip, setTip] = useState({ visible: false, x: 0, y: 0, text: '' });
  const focusId = params.get('focus');

  const chapters = useMemo(() => (novel ? novel.chapters : []), [novel]);
  // -1 = the URL names a chapter this book does not have. It used to fall
  // back to chapter 1 silently, so a mistyped or stale shared link showed
  // the wrong text with no hint anything was off.
  const idx = useMemo(() => {
    if (chapterParam == null) return 0;
    return chapters.findIndex((c) => String(Number(c.number)) === chapterParam);
  }, [chapters, chapterParam]);
  const chapter = idx >= 0 ? chapters[idx] : null;
  const chapterNumber = chapter ? Number(chapter.number) : null;

  // Keyed by chapter, so a stale response for the chapter just left is never
  // shown against the one just opened.
  const [cast, setCast] = useState({ chapter: null, entities: null, error: null });
  const [castAttempt, setCastAttempt] = useState(0);
  useEffect(() => {
    if (!novelId || chapterNumber == null) return undefined;
    let live = true;
    api
      .readerCast(novelId, chapterNumber)
      .then((r) => live && setCast({ chapter: chapterNumber, entities: r.entities, error: null }))
      .catch((e) => live && setCast({ chapter: chapterNumber, entities: null, error: e }));
    return () => {
      live = false;
    };
  }, [novelId, chapterNumber, castAttempt]);
  const current = cast.chapter === chapterNumber ? cast : { entities: null, error: null };
  const castById = useMemo(
    () => (current.entities ? new Map(current.entities.map((e) => [e.id, e])) : null),
    [current.entities]
  );
  const shownChapter = useMemo(() => readerChapter(chapter, castById), [chapter, castById]);

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

  if (error) return <ProjectProblem error={error} status={errorStatus} onRetry={refetch} />;
  if (!novel) return <CenterMessage>Loading the book…</CenterMessage>;

  if (!chapters.length) {
    return (
      <CenterMessage title="No chapters yet">
        <p>This project has no ingested text.</p>
        <Link to={`/p/${encodeURIComponent(novelId)}/settings`} className="mt-3 inline-block text-accent hover:underline">
          Go to settings to ingest a source
        </Link>
      </CenterMessage>
    );
  }

  if (idx < 0) {
    const first = chapters[0];
    return (
      <CenterMessage title={`Chapter ${chapterParam} isn’t in this book`}>
        <p>This book has {chapters.length} chapters.</p>
        {first && (
          <Link to={`../${Number(first.number)}`} relative="path" className="mt-3 inline-block text-accent hover:underline">
            Go to chapter {Number(first.number)}
          </Link>
        )}
      </CenterMessage>
    );
  }

  // A shared link can focus a character the reader has not met yet; naming
  // them in the chip would be the spoiler this page avoids.
  const focused = focusId
    ? (castById && castById.get(focusId)) || { id: focusId, label: 'a character not met yet', colour: 'transparent' }
    : null;

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden">
      <div className="h-full min-w-0 flex-1 overflow-y-auto overscroll-contain">
        {/* The visible chapter label lives in ManuscriptSurface; screen
            readers still need one page heading (route sweep, 2026-09-26). */}
        <h1 className="sr-only">
          Chapter {Number(chapter.number)}{focusId ? ' (highlighting a character)' : ''}
        </h1>
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
          chapter={shownChapter}
          focusId={focusId}
          onMarkHover={onMarkHover}
          onMarkMove={onMarkMove}
          onMarkLeave={onMarkLeave}
          editMode={false}
        />
      </div>

      <aside className="sticky top-0 hidden h-full w-72 shrink-0 border-l border-border bg-surface xl:block" aria-label="Cast so far">
        {current.error ? (
          <div className="p-4 text-sm text-muted" role="alert">
            <p>The cast for this chapter didn’t load.</p>
            <button type="button" onClick={() => setCastAttempt((n) => n + 1)} className="mt-2 text-accent hover:underline">
              Try again
            </button>
          </div>
        ) : current.entities ? (
          <EntitySidebar
            entities={current.entities}
            search={search}
            onSearchChange={setSearch}
            focusId={focusId}
            onToggleFocus={toggleFocus}
            editMode={false}
            mergeSourceId={null}
          />
        ) : (
          <p className="p-4 text-sm text-muted" role="status">Loading the cast…</p>
        )}
      </aside>
      <Tooltip tip={tip} />
    </div>
  );
}
