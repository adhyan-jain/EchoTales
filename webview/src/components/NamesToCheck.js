import React, { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import EntityPicker from './EntityPicker';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';

const cardCls = 'rounded-2xl border border-border bg-surface p-4';
const errorCls = 'rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger';

// Plain-language form of the resolver's `reason_kind`; anything else falls back to the item's own sentence.
const REASON_TEXT = {
  tie_margin: 'Two characters fit about equally.',
  below_link_above_new: 'Not sure enough to link, not different enough to be new.',
};

const groupOf = (item) => (item.candidates || []).find((c) => c && c.role === 'group') || {};
const candidatesOf = (item) => (item.candidates || []).filter((c) => c && c.role === 'candidate');
const longest = (list) => (list || []).reduce((a, b) => (b.length > a.length ? b : a), '');

// What the reviewer decided, in words; `labelOf` turns a character id into a name.
function stateText(item, labelOf) {
  const r = item.resolution || '';
  const pending = item.decision_state === 'decided_pending_apply';
  const tail = pending ? ', pending Apply' : '';
  if (r.startsWith('human:link:')) return `Linked to ${labelOf(r.slice('human:link:'.length))}${tail}`;
  if (r.startsWith('human:new:')) return `New character "${r.slice('human:new:'.length)}"${tail}`;
  if (item.decision_state === 'dismissed') return 'Marked as not a character';
  if (item.decision_state === 'auto_closed') return 'Linked automatically on a later run';
  return '';
}

function NameRow({ item, entities, busy, onDecide, onReopen }) {
  const group = groupOf(item);
  const surfaces = group.surfaces || [];
  const cands = candidatesOf(item);
  const [name, setName] = useState(longest(surfaces));
  const [picking, setPicking] = useState(false);
  const open = item.decision_state === 'open';
  const labelOf = (id) => (cands.find((c) => c.target_id === id) || entities.find((e) => e.id === id) || {}).label || id;
  const nMentions = (group.mention_ids || []).length;
  const reason = REASON_TEXT[group.reason_kind] || item.message;
  const subject = surfaces.join(', ') || 'this name';

  return (
    <li className={cardCls} data-testid="name-to-check">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="text-sm font-medium text-text">{subject}</span>
        <span>{nMentions} mention{nMentions === 1 ? '' : 's'}</span>
        <span>Ch {item.chapter}</span>
      </div>
      {group.excerpt && <p className="mt-2 text-sm italic text-muted">&ldquo;{group.excerpt}&rdquo;</p>}
      <p className="mt-2 text-sm text-text">{reason}</p>
      {open ? (
        <div className="mt-3 space-y-3">
          <div role="group" aria-label={`Link ${subject} to`} className="flex flex-wrap gap-2">
              {cands.map((c) => (
                <Button
                  key={c.target_id}
                  variant="secondary"
                  size="sm"
                  disabled={busy}
                  onClick={() => onDecide(item, { action: 'link', target_id: c.target_id })}
                >
                  {c.label} · {Math.round(c.probability * 100)}%
                </Button>
              ))}
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => setPicking(true)}>
                Another character
              </Button>
            </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label={`Name for a new character from ${subject}`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-8 min-w-[12rem] rounded-xl border border-border bg-surface px-3 text-sm text-text"
            />
            <Button variant="secondary" size="sm" disabled={busy || !name.trim()} onClick={() => onDecide(item, { action: 'new', label: name.trim() })}>
              New character
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => onDecide(item, { action: 'dismiss' })}>
              Not a character
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Badge tone={item.decision_state === 'applied' ? 'success' : 'accent'}>
            <span aria-live="polite">{stateText(item, labelOf)}</span>
          </Badge>
          {(item.decision_state === 'decided_pending_apply' || item.decision_state === 'dismissed') && (
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => onReopen(item)} aria-label={`Undo the decision for ${subject}`}>
              Undo
            </Button>
          )}
        </div>
      )}
      {picking && (
        <EntityPicker
          entities={entities}
          onCancel={() => setPicking(false)}
          onSelect={(id) => {
            setPicking(false);
            onDecide(item, { action: 'link', target_id: id });
          }}
          onCreateNew={(label) => {
            setPicking(false);
            onDecide(item, { action: 'new', label });
          }}
        />
      )}
    </li>
  );
}

export default function NamesToCheck({ novelId, entities }) {
  const push = useToast();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [pending, setPending] = useState(null);
  const [busyId, setBusyId] = useState(null);
  // State updates land after the click handler returns, so two quick clicks would both see busy === false.
  const inflight = useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [res, corr] = await Promise.all([
        api.listReviewItems(novelId, { kind: 'resolve_deferred' }),
        api.corrections(novelId).catch(() => null),
      ]);
      setItems((res && res.items) || []);
      setPending(corr && corr.summary ? corr.summary.pending_actionable ?? corr.summary.pending : null);
      setLoadError('');
    } catch (err) {
      const message = describeError(err, 'Failed to load the names to check.');
      setLoadError(message);
      push(message, 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, push]);

  useEffect(() => {
    load();
  }, [load]);

  const replace = (body) => {
    setItems((prev) => prev.map((i) => (i.id === body.item.id ? body.item : i)));
    if (body.summary) setPending(body.summary.pending_actionable ?? body.summary.pending);
  };

  const run = async (item, call, success, failure) => {
    if (inflight.current) return;
    inflight.current = true;
    setBusyId(item.id);
    try {
      replace(await call());
      push(success, 'success');
    } catch (err) {
      push(describeError(err, failure), 'danger');
    } finally {
      inflight.current = false;
      setBusyId(null);
    }
  };

  const decide = (item, decision) =>
    run(item, () => api.decideReviewItem(novelId, item.id, decision), 'Decision saved. Apply it from the Review desk.', 'Could not save that decision.');
  const reopen = (item) => run(item, () => api.reopenReviewItem(novelId, item.id), 'Decision undone.', 'Could not undo that decision.');

  const open = items.filter((i) => i.decision_state === 'open').length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
        {!loadError && <span>{open} name{open === 1 ? '' : 's'} to check</span>}
        {!loadError && pending != null && (
          <span>· {pending} correction{pending === 1 ? '' : 's'} waiting for Apply</span>
        )}
      </div>
      {loadError && (
        <div role="alert" className={errorCls + ' flex flex-wrap items-center justify-between gap-3'}>
          <span>{loadError}</span>
          <Button variant="secondary" size="sm" onClick={load}>
            Try again
          </Button>
        </div>
      )}
      {!loadError && !loading && items.length === 0 && <p className={cardCls + ' text-sm text-muted'}>No names to check.</p>}
      <ul className="space-y-3">
        {(loadError ? [] : items).map((item) => (
          <NameRow
            key={item.id}
            item={item}
            entities={entities}
            busy={busyId !== null}
            onDecide={decide}
            onReopen={reopen}
          />
        ))}
      </ul>
    </div>
  );
}
