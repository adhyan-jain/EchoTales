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

  // Focus goes into the picker on open and back to whatever opened it (the
  // mention or speaker) on close, so a keyboard reviewer keeps their place in
  // the script instead of landing on <body> after every edit.
  useEffect(() => {
    const opener = document.activeElement;
    inputRef.current?.focus();
    return () => {
      if (opener && opener !== document.body && document.contains(opener)) opener.focus();
    };
  }, []);

  const q = query.trim().toLowerCase();
  const filtered = q ? entities.filter((e) => e.label.toLowerCase().includes(q)) : entities;
  const exactMatch = entities.some((e) => e.label.toLowerCase() === q);

  const style = anchor
    ? { position: 'fixed', left: Math.min(anchor.x, window.innerWidth - 320), top: Math.min(anchor.y, window.innerHeight - 360) }
    : {};

  // Rows are real <button>s so the picker works from the keyboard: the input
  // takes focus on open, ArrowDown moves into the list, Escape closes from
  // anywhere. Clickable <li>s were mouse-only (web-design-guidelines audit,
  // 2026-09-26), which locked keyboard reviewers out of every edit action.
  const listRef = useRef(null);
  const moveFocus = (e) => {
    if (e.key === 'Escape') {
      onCancel();
      return;
    }
    if (e.key === 'Tab') {
      // Keep Tab inside the picker while it is open: the backdrop covers the
      // page, so tabbing into the script behind it would be invisible.
      const stops = [inputRef.current, ...(listRef.current?.querySelectorAll('button[data-row]') || [])];
      const first = stops[0];
      const last = stops[stops.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
      return;
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const rows = Array.from(listRef.current?.querySelectorAll('button[data-row]') || []);
    if (!rows.length) return;
    e.preventDefault();
    const i = rows.indexOf(document.activeElement);
    const next = e.key === 'ArrowDown' ? Math.min(i + 1, rows.length - 1) : i - 1;
    (next < 0 ? inputRef.current : rows[next])?.focus();
  };

  return (
    <div className="picker-backdrop" onClick={onCancel}>
      <div
        className="entity-picker"
        style={style}
        role="dialog"
        aria-modal="true"
        aria-label="Choose a character"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={moveFocus}
      >
        <input
          ref={inputRef}
          type="text"
          aria-label="Search or type a new name"
          autoComplete="off"
          spellCheck={false}
          placeholder="Search or type a new name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && query.trim() && !exactMatch) onCreateNew(query.trim());
          }}
        />
        <ul ref={listRef}>
          {onClear && (
            <li>
              <button type="button" data-row className="picker-row clear-row" onClick={onClear}>
                <span aria-hidden="true">&empty;</span> Unassign / mark unresolved
              </button>
            </li>
          )}
          {onAnonSlot && (
            <li className="anon-slot-row">
              <span className="anon-slot-label">Unknown speaker:</span>
              {Array.from({ length: MAX_ANON_SLOTS }, (_, i) => i + 1).map((n) => (
                <button
                  key={n}
                  type="button"
                  data-row
                  className="anon-slot-btn"
                  onClick={() => onAnonSlot(n)}
                  aria-label={`Unknown speaker ${n}`}
                  title={`Give this line "Unknown Speaker ${n}"'s voice slot`}
                >
                  {n}
                </button>
              ))}
            </li>
          )}
          {query.trim() && !exactMatch && (
            <li>
              <button type="button" data-row className="picker-row create-row" onClick={() => onCreateNew(query.trim())}>
                + Create new character &ldquo;{query.trim()}&rdquo;
              </button>
            </li>
          )}
          {filtered.slice(0, 60).map((ent) => (
            <li key={ent.id}>
              <button type="button" data-row className="picker-row" onClick={() => onSelect(ent.id)}>
                <span className="swatch" style={{ background: ent.colour }} aria-hidden="true" />
                <span className="picker-label">{ent.label}</span>
                <span className="count">{ent.count}</span>
              </button>
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
