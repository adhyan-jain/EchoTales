import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import EntityPicker from './EntityPicker';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { Lock, AlertTriangle } from 'lucide-react';

const REASONS = {
  unnamed: { label: 'unnamed', tone: 'danger' },
  role_slot: { label: 'role slot', tone: 'warning' },
  model_guess: { label: 'model guess', tone: 'accent' },
  low_confidence: { label: 'low confidence', tone: 'neutral' },
};

const cardCls = 'rounded-2xl border border-border bg-surface p-4';

function truncate(text, n = 160) {
  const t = text || '';
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
}

/* (a) The ranked queue. role_slot / unnamed rows are the first-class cases:
   one fix there repairs `affected` lines at once, which is why the server
   sorts by it. */
function LinesToCheck({ novelId, entities }) {
  const push = useToast();
  const [chapter, setChapter] = useState('');
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [picking, setPicking] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.reviewLines(novelId, { chapter: chapter || undefined }));
    } catch (err) {
      push(describeError(err, 'Failed to load lines to check.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, chapter, push]);

  useEffect(() => {
    load();
  }, [load]);

  const assign = async (item, target) => {
    setPicking(null);
    try {
      await api.reassignSpeaker(novelId, item.span_id, item.chapter, target);
      push('Speaker updated.', 'success');
      await load();
    } catch (err) {
      push(describeError(err, 'Could not reassign the speaker.'), 'danger');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted" htmlFor="bible-chapter">Chapter</label>
        <input
          id="bible-chapter"
          type="number"
          min="1"
          value={chapter}
          placeholder="all"
          onChange={(e) => setChapter(e.target.value)}
          className="h-10 w-24 rounded-xl border border-border bg-surface px-3 text-sm text-text"
        />
        <span className="text-sm text-muted">{data.total} line{data.total === 1 ? '' : 's'} to check</span>
      </div>
      {!loading && data.items.length === 0 && (
        <p className={cardCls + ' text-sm text-muted'}>Nothing to check{chapter ? ` in chapter ${chapter}` : ''}.</p>
      )}
      <ul className="space-y-3">
        {data.items.map((it) => {
          const r = REASONS[it.reason] || REASONS.low_confidence;
          return (
            <li key={it.span_id} className={cardCls} data-testid="review-line">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                <span>Ch {it.chapter} · block {it.block_index}</span>
                <Badge tone={r.tone}>{r.label}</Badge>
                <span>affects {it.affected} line{it.affected === 1 ? '' : 's'}</span>
                <span>{Math.round(it.confidence * 100)}% sure ({it.method})</span>
              </div>
              {/* it.text already carries the book's own quote marks; wrapping it showed doubled quotes */}
              <p className="mt-2 text-sm text-text">{truncate(it.text)}</p>
              <div className="mt-3 flex items-center gap-3">
                <span className="text-sm text-muted">
                  Speaker: <span className="font-medium text-text">{it.speaker_label || 'unnamed'}</span>
                </span>
                <Button variant="secondary" size="sm" onClick={() => setPicking(it)}>
                  Change speaker
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      {picking && (
        <EntityPicker
          entities={entities}
          onCancel={() => setPicking(null)}
          onSelect={(id) => assign(picking, id)}
          onCreateNew={(label) => assign(picking, { new_label: label })}
          onAnonSlot={(n) => assign(picking, { anon_slot: n })}
        />
      )}
    </div>
  );
}

/* A chapter ruler: the bar is the span the thing was true in the story, the
   dot is the chapter the reader learned it. story_from < learned_chapter is
   the whole point (a title held before the holder's name is revealed). */
function Ruler({ from, to, learned, max }) {
  const pct = (c) => `${Math.min(100, Math.max(0, ((c - 1) / Math.max(1, max - 1)) * 100))}%`;
  const end = to == null ? max : to;
  return (
    <div className="relative my-2 h-2 rounded-full bg-surface2" aria-hidden="true">
      <div
        className="absolute h-2 rounded-full bg-primary/60"
        style={{ left: pct(from), width: `calc(${pct(end)} - ${pct(from)})`, minWidth: 6 }}
      />
      <div className="absolute -top-1 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-accent bg-bg" style={{ left: pct(learned) }} />
    </div>
  );
}

function heldText(i) {
  const held = i.story_to == null ? `held since ch ${i.story_from}` : `held ch ${i.story_from}-${i.story_to}`;
  return `${held}, learned ch ${i.learned_chapter}`;
}

function TimelineView({ tl }) {
  const [open, setOpen] = useState(null);
  const looksByKey = useMemo(() => {
    const m = {};
    (tl.looks || []).forEach((l) => {
      (m[l.key] = m[l.key] || []).push(l);
    });
    Object.values(m).forEach((arr) => arr.sort((a, b) => a.from_chapter - b.from_chapter));
    return m;
  }, [tl]);
  const max = Math.max(
    2,
    ...(tl.looks || []).map((l) => l.from_chapter),
    ...(tl.identities || []).flatMap((i) => [i.story_from, i.story_to || 0, i.learned_chapter]),
    ...(tl.personas || []).flatMap((p) => [p.from_chapter, p.to_chapter || 0])
  );

  return (
    <div className="space-y-6">
      <section className={cardCls}>
        <h3 className="font-display text-base font-bold">Names and titles</h3>
        {(tl.identities || []).length === 0 && <p className="mt-2 text-sm text-muted">None recorded.</p>}
        <ul className="mt-2 space-y-3">
          {(tl.identities || []).map((i, n) => (
            <li key={`${i.alias}-${n}`} data-testid="identity">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-text">{i.alias}</span>
                <Badge>{String(i.alias_type).toLowerCase().replace(/_/g, ' ')}</Badge>
                <span className="text-muted">{heldText(i)}</span>
              </div>
              <Ruler from={i.story_from} to={i.story_to} learned={i.learned_chapter} max={max} />
              {i.evidence && <p className="text-xs italic text-muted">&ldquo;{truncate(i.evidence, 200)}&rdquo;</p>}
            </li>
          ))}
        </ul>
      </section>
      <section className={cardCls}>
        <h3 className="font-display text-base font-bold">Look by chapter</h3>
        {Object.keys(looksByKey).length === 0 && <p className="mt-2 text-sm text-muted">No look attributes recorded.</p>}
        <div className="mt-2 space-y-3">
          {Object.entries(looksByKey).map(([key, versions]) => (
            <div key={key}>
              <div className="text-sm font-medium text-text">{key}</div>
              <ol className="mt-1 flex flex-wrap gap-2">
                {versions.map((v, n) => {
                  const id = `${key}-${n}`;
                  return (
                    <li key={id}>
                      <button
                        type="button"
                        title={v.evidence}
                        aria-expanded={open === id}
                        onClick={() => setOpen(open === id ? null : id)}
                        className="rounded-xl border border-border bg-surface2 px-3 py-1.5 text-left text-sm hover:border-accent/60"
                      >
                        <span className="text-xs text-muted">ch {v.from_chapter}</span> {v.value}
                      </button>
                      {open === id && (
                        <p className="mt-1 max-w-xs text-xs italic text-muted">
                          &ldquo;{v.evidence}&rdquo; ({Math.round(v.confidence * 100)}%, {v.asserted_by})
                        </p>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
        </div>
      </section>
      <section className={cardCls}>
        <h3 className="font-display text-base font-bold">Personas</h3>
        <ul className="mt-2 space-y-1 text-sm text-muted">
          {(tl.personas || []).map((p) => (
            <li key={p.persona_id}>
              <span className="font-mono text-xs text-text">{p.persona_id}</span> ch {p.from_chapter}
              {p.to_chapter == null ? ' onward' : `-${p.to_chapter}`}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/* (b) */
function CharacterTimeline({ novelId, characters }) {
  const push = useToast();
  const [selfId, setSelfId] = useState('');
  const [tl, setTl] = useState(null);

  useEffect(() => {
    if (!selfId) return;
    let live = true;
    api
      .characterTimeline(novelId, selfId)
      .then((d) => live && setTl(d))
      .catch((err) => push(describeError(err, 'Failed to load the timeline.'), 'danger'));
    return () => {
      live = false;
    };
  }, [novelId, selfId, push]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <label htmlFor="bible-char" className="text-sm text-muted">Character</label>
        <select
          id="bible-char"
          value={selfId}
          onChange={(e) => {
            setTl(null);
            setSelfId(e.target.value);
          }}
          className="h-10 rounded-xl border border-border bg-surface px-3 text-sm text-text"
        >
          <option value="">Choose a character</option>
          {characters.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
      </div>
      {tl && <TimelineView tl={tl} />}
    </div>
  );
}

/* (c) */
function LockPanel({ novelId }) {
  const push = useToast();
  const [bible, setBible] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setBible(await api.getBible(novelId));
    } catch (err) {
      push(describeError(err, 'Failed to load the canon state.'), 'danger');
    }
  }, [novelId, push]);

  useEffect(() => {
    load();
  }, [load]);

  if (!bible) return <p className="text-sm text-muted">Loading…</p>;
  const { current, locks } = bible;
  const stale = !!current.stale_reason;
  const next = Math.max(0, ...locks.map((l) => l.version)) + 1;

  const lock = async () => {
    setBusy(true);
    try {
      const rec = await api.lockBible(novelId, note.trim() || undefined);
      const n = (rec.changed_chapters || []).length;
      push(`Locked canon v${rec.version}${n ? ` (${n} chapter${n === 1 ? '' : 's'} changed)` : ''}.`, 'success');
      setNote('');
      await load();
    } catch (err) {
      push(describeError(err, 'Could not lock the canon.'), 'danger');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className={cardCls}>
        <div className="flex flex-wrap items-center gap-2">
          {stale ? <Badge tone="danger">stale</Badge> : current.dirty ? <Badge tone="warning">changed since last lock</Badge> : <Badge tone="success">clean</Badge>}
          <span className="text-sm text-muted">
            {current.locked_version ? `Locked at v${current.locked_version}` : 'Not locked yet'} · pipeline {current.pipeline_version}
          </span>
        </div>
        {stale && (
          <p className="mt-3 flex items-start gap-2 text-sm text-danger" role="alert">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> {current.stale_reason}
          </p>
        )}
        {(current.changed_chapters || []).length > 0 && (
          <p className="mt-3 text-sm text-muted">
            Changed since the last lock: chapter{current.changed_chapters.length === 1 ? '' : 's'} {current.changed_chapters.join(', ')}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            aria-label="Lock note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            className="h-10 min-w-[16rem] flex-1 rounded-xl border border-border bg-surface px-3 text-sm text-text"
          />
          <Button onClick={lock} disabled={stale || busy}>
            <Lock className="h-4 w-4" aria-hidden="true" /> Lock canon v{next}
          </Button>
        </div>
      </div>
      <ul className="space-y-2">
        {locks.map((l) => (
          <li key={l.version} className={cardCls + ' text-sm'} data-testid="bible-lock">
            <span className="font-medium text-text">v{l.version}</span>{' '}
            <span className="text-muted">{l.created_at} · {l.note || 'no note'}</span>
            <div className="mt-1 text-xs text-muted">
              {l.counts.lines} lines · {l.counts.attributes} attributes · {l.counts.aliases} aliases · {l.counts.entities} entities
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const SUBTABS = [
  { key: 'lines', label: 'Lines to check' },
  { key: 'timeline', label: 'Character timeline' },
  { key: 'lock', label: 'Lock' },
];

export default function BibleReview({ novelId }) {
  const [sub, setSub] = useState('lines');
  const [characters, setCharacters] = useState([]);

  useEffect(() => {
    let live = true;
    api
      .characters(novelId)
      .then((d) => {
        if (!live) return;
        setCharacters(
          ((d && d.characters) || []).map((c) => {
            const id = c.self_id || c.id;
            return { id, label: c.label || c.canonical_label || c.name || id, count: c.count };
          })
        );
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [novelId]);

  return (
    <div data-testid="bible-review" className="space-y-6">
      <div role="group" aria-label="Canon review view" className="inline-flex flex-wrap gap-1 rounded-2xl border border-border bg-surface p-1">
        {SUBTABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            aria-pressed={sub === key}
            onClick={() => setSub(key)}
            className={
              'rounded-xl px-4 py-2 text-sm font-medium transition-colors ' +
              (sub === key ? 'bg-primary text-white shadow-glow' : 'text-muted hover:text-text')
            }
          >
            {label}
          </button>
        ))}
      </div>
      {sub === 'lines' && <LinesToCheck novelId={novelId} entities={characters} />}
      {sub === 'timeline' && <CharacterTimeline novelId={novelId} characters={characters} />}
      {sub === 'lock' && <LockPanel novelId={novelId} />}
    </div>
  );
}
