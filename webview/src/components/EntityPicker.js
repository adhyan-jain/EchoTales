import React, { useState, useRef, useEffect } from 'react';

/**
 * The one picker every edit action shares: reassign a mention, reassign a
 * speaker, or found either on a brand-new character. Search-filtered list of
 * existing entities, a "create new" row that appears the moment the typed
 * text doesn't match one exactly, and a clear/unassign option -- so "this
 * mention is wrong" and "this character doesn't exist yet" are the same
 * gesture, not two different UIs to learn.
 */
// Matches `_MAX_ANON_SLOTS` in speakers/runner.py -- a chapter with more
// simultaneous unnamed voices than this is one confused scene, not a dozen
// distinct background speakers, so the picker doesn't offer more than the
// pipeline itself would ever assign.
const MAX_ANON_SLOTS = 4;

export default function EntityPicker({
  entities,
  anchor,
  onSelect,
  onCreateNew,
  onClear,
  onAnonSlot,
  onCancel,
}) {
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = q ? entities.filter((e) => e.label.toLowerCase().includes(q)) : entities;
  const exactMatch = entities.some((e) => e.label.toLowerCase() === q);

  const style = anchor
    ? { position: 'fixed', left: Math.min(anchor.x, window.innerWidth - 320), top: Math.min(anchor.y, window.innerHeight - 360) }
    : {};

  return (
    <div className="picker-backdrop" onClick={onCancel}>
      <div className="entity-picker" style={style} onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          type="text"
          placeholder="Search or type a new name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onCancel();
            if (e.key === 'Enter' && query.trim() && !exactMatch) onCreateNew(query.trim());
          }}
        />
        <ul>
          {onClear && (
            <li className="clear-row" onClick={onClear}>
              &empty; Unassign / mark unresolved
            </li>
          )}
          {onAnonSlot && (
            <li className="anon-slot-row">
              <span className="anon-slot-label">Unknown speaker:</span>
              {Array.from({ length: MAX_ANON_SLOTS }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  className="anon-slot-btn"
                  onClick={() => onAnonSlot(n)}
                  title={`Give this line "Unknown Speaker ${n}"'s voice slot`}
                >
                  {n}
                </button>
              ))}
            </li>
          )}
          {query.trim() && !exactMatch && (
            <li className="create-row" onClick={() => onCreateNew(query.trim())}>
              + Create new character &ldquo;{query.trim()}&rdquo;
            </li>
          )}
          {filtered.slice(0, 60).map((ent) => (
            <li key={ent.id} onClick={() => onSelect(ent.id)}>
              <span className="swatch" style={{ background: ent.colour }} />
              {ent.label}
              <span className="count">{ent.count}</span>
            </li>
          ))}
          {filtered.length === 0 && !query.trim() && (
            <li className="hint">Type to search or create a character.</li>
          )}
        </ul>
      </div>
    </div>
  );
}
