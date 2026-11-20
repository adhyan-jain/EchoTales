import React from 'react';
import { SPAN_TYPES } from '../api';
import { DELIVERY_EMOTIONS } from '../lib/delivery';

/**
 * One span, rendered with its mentions as inline <mark> elements.
 *
 * Offsets in `marks` are local to `span.text` already (computed server-side
 * in `webview.py`), so this only has to slice and interleave -- no coordinate
 * translation happens in the browser.
 */
// Edit targets stay inline <mark>/<div> elements (a <button> would break the
// running text's line flow), so they get role="button" plus Enter/Space. The
// picker is anchored at the pointer (`clientX/Y`), which a key event does not
// carry, so a keyboard activation anchors at the element's own corner instead.
function keyActivate(handler) {
  return (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    e.stopPropagation();
    const r = e.currentTarget.getBoundingClientRect();
    handler({ clientX: r.left, clientY: r.bottom, currentTarget: e.currentTarget });
  };
}

export default function ScriptLine({
  span,
  focusId,
  onMarkHover,
  onMarkMove,
  onMarkLeave,
  editMode,
  onMentionClick,
  onSpeakerClick,
  onFlagLine,
  onMergeUp,
  canMergeUp,
  onRetype,
  onCreateMention,
  onSetDelivery,
}) {
  const isDialogue = span.type === 'DIALOGUE';
  // Whose thought this is matters as much as who's speaking -- the pipeline
  // already resolves it (`speakers/attribution.py::pov_holder`, logged as
  // POV_INFERRED) but the viewer used to only ever show the speaker column
  // for DIALOGUE, so a reader had no way to tell whose head a paragraph of
  // inner monologue was inside without cross-referencing chapter POV by hand.
  const isInnerMonologue = span.type === 'INNER_MONOLOGUE';
  const speakerEditable = (editMode || Boolean(onSpeakerClick)) && (isDialogue || isInnerMonologue);
  // `speaker_id` is the attributed surface ("Zhou Mingrui"), never an entity
  // id, so comparing it with the focused id never matched a speaker's lines;
  // `speaker_entity_id` is the server's join of that surface to the entity.
  const relevant =
    !focusId ||
    span.marks.some((m) => m.id === focusId) ||
    (span.speaker_entity_id || span.speaker_id) === focusId;
  const rowClass = ['line', isDialogue ? 'dialogue' : '', focusId && !relevant ? 'dim' : '']
    .filter(Boolean)
    .join(' ');

  const marks = [...span.marks].sort((a, b) => a.s - b.s);
  const parts = [];
  let pos = 0;
  marks.forEach((m, i) => {
    if (m.s < pos || m.e > span.text.length) return; // malformed offset, skip defensively
    if (m.s > pos) parts.push(span.text.slice(pos, m.s));
    const cls = [
      'mark',
      !m.resolved ? 'unresolved' : '',
      m.is_person === false ? 'not-person' : '',
      focusId && m.id !== focusId ? 'dim' : '',
      focusId && m.id === focusId ? 'focus' : '',
      editMode ? 'editable' : '',
    ]
      .filter(Boolean)
      .join(' ');
    const tip =
      `${m.label}${m.resolved ? '' : '  (unresolved)'}` +
      (m.is_person === false ? '  (not a person -- place/item/org)' : '') +
      `  ·  conf ${m.conf}` +
      (m.flags && m.flags.length ? `  ⚑ ${m.flags.length}` : '');
    parts.push(
      <mark
        key={i}
        className={cls.replace('mark', '').trim()}
        style={{ '--mk': m.colour }}
        onMouseEnter={(e) => onMarkHover(e, tip)}
        onMouseMove={onMarkMove}
        onMouseLeave={onMarkLeave}
        onClick={editMode ? (e) => { e.stopPropagation(); onMentionClick(m, e); } : undefined}
        {...(editMode && {
          role: 'button',
          tabIndex: 0,
          'aria-label': `Reassign mention ${span.text.slice(m.s, m.e)}`,
          'aria-haspopup': 'dialog',
          onKeyDown: keyActivate((e) => onMentionClick(m, e)),
        })}
      >
        {span.text.slice(m.s, m.e)}
        {m.flags && m.flags.length > 0 && <span className="flag-badge">&#9873;</span>}
      </mark>
    );
    pos = m.e;
  });
  if (pos < span.text.length) parts.push(span.text.slice(pos));

  const hasFlags = span.flags && span.flags.length > 0;
  // Three identical "Flag" buttons per screen say nothing to a screen reader.
  const lineHint = `${(span.text || '').slice(0, 40).trim()}${(span.text || '').length > 40 ? '…' : ''}`;

  return (
    <div className={rowClass}>
      <div
        className={
          'speaker' +
          (isDialogue && !span.speaker ? ' missing' : '') +
          (span.anonymous_speaker ? ' anonymous' : '') +
          (speakerEditable ? ' editable' : '')
        }
        style={span.anonymous_speaker && span.speaker_colour ? { '--sp': span.speaker_colour } : undefined}
        onClick={speakerEditable ? (e) => onSpeakerClick(span, e) : undefined}
        {...(speakerEditable && {
          role: 'button',
          tabIndex: 0,
          'aria-haspopup': 'dialog',
          onKeyDown: keyActivate((e) => onSpeakerClick(span, e)),
        })}
        title={
          speakerEditable
            ? span.anonymous_speaker
              ? 'A distinct voice slot, not a known character -- click to name them if you know who this is'
              : 'Click to reassign the speaker'
            : undefined
        }
      >
        {isDialogue && (
          <>
            {span.speaker || 'unattributed'}
            <span className="method">
              {/* The attribution method (e.g. CONTEXTUAL_LLM) is evidence a
                  reviewer weighs; for a reader it is noise, so the reader
                  (editMode off) shows only whether the voice is anonymous. */}
              {span.anonymous_speaker ? 'anonymous' : span.speaker && editMode ? span.method : ''}
            </span>
          </>
        )}
        {isInnerMonologue && span.speaker && (
          <>
            <span className="thinking">{span.speaker}</span>
            <span className="method">thinking</span>
          </>
        )}
        {/* Not an aria-label: the name must contain the visible text (speaker and method), 2026-11 audit. */}
        {speakerEditable && <span className="sr-only">, {span.speaker ? 'reassign speaker' : 'assign a speaker'}</span>}
      </div>
      <div className="body">
        {editMode ? (
          <select
            className="tag-select"
            aria-label="Line type"
            value={span.type}
            title="Reclassify this line -- e.g. mark it NON_DIEGETIC to drop it from audio and panels"
            onChange={(e) => onRetype(span, e.target.value)}
          >
            {SPAN_TYPES.map((t) => (
              <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
            ))}
          </select>
        ) : (
          <span className="tag">{span.type.replace(/_/g, ' ')}</span>
        )}
        {parts}
        {hasFlags && (
          <span className="flag-badge" title={span.flags.map((f) => f.note).join('; ')}>
            &#9873; {span.flags.length}
          </span>
        )}
        {editMode && (
          <span className="line-actions">
            {onCreateMention && (
              <button
                type="button"
                title="Create a mention for text in this line that detector missed"
                onClick={(e) => onCreateMention(span, e)}
              >
                <span aria-hidden="true">+ </span>Mention<span className="sr-only"> in this line: {lineHint}</span>
              </button>
            )}
            {onSetDelivery && (isDialogue || isInnerMonologue) && (
              <DeliveryControl span={span} onSetDelivery={onSetDelivery} />
            )}
            <button type="button" aria-label={`Flag this line: ${lineHint}`} onClick={() => onFlagLine(span)}>Flag</button>
            {canMergeUp && (
              <button type="button" onClick={onMergeUp}>
                Merge<span aria-hidden="true">&nbsp;&uarr;</span><span className="sr-only"> this line into the one above: {lineHint}</span>
              </button>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

// How this line will be voiced. "Not set" is the delivery pass's own guess (or neutral); picking an emotion makes it the
// reviewer's, which the delivery pass never rewrites. Intensity is meaningless without an emotion, so it waits for one.
function DeliveryControl({ span, onSetDelivery }) {
  const current = span.delivery || null;
  const emotion = current ? current.emotion : '';
  const intensity = current ? current.intensity : 2;
  return (
    <span className="delivery-control">
      <select
        className="tag-select"
        aria-label="Line emotion"
        title="How this line is performed when the book is voiced"
        value={emotion}
        onChange={(e) => e.target.value && onSetDelivery(span, e.target.value, intensity)}
      >
        <option value="">Not set (the reader’s guess)</option>
        {DELIVERY_EMOTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <select
        className="tag-select"
        aria-label="Line intensity"
        title="1 is restrained, 3 is full"
        value={String(intensity)}
        disabled={!emotion}
        onChange={(e) => onSetDelivery(span, emotion, Number(e.target.value))}
      >
        {[1, 2, 3].map((n) => (
          <option key={n} value={n}>{n}</option>
        ))}
      </select>
      {current && current.pending && <span className="method">Not applied yet</span>}
    </span>
  );
}
