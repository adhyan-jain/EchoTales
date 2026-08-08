import React from 'react';
import { SPAN_TYPES } from '../api';

/**
 * One span, rendered with its mentions as inline <mark> elements.
 *
 * Offsets in `marks` are local to `span.text` already (computed server-side
 * in `webview.py`), so this only has to slice and interleave -- no coordinate
 * translation happens in the browser.
 */
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
}) {
  const isDialogue = span.type === 'DIALOGUE';
  // Whose thought this is matters as much as who's speaking -- the pipeline
  // already resolves it (`speakers/attribution.py::pov_holder`, logged as
  // POV_INFERRED) but the viewer used to only ever show the speaker column
  // for DIALOGUE, so a reader had no way to tell whose head a paragraph of
  // inner monologue was inside without cross-referencing chapter POV by hand.
  const isInnerMonologue = span.type === 'INNER_MONOLOGUE';
  const speakerEditable = editMode && (isDialogue || isInnerMonologue);
  const relevant =
    !focusId ||
    span.marks.some((m) => m.id === focusId) ||
    span.speaker_id === focusId;
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
      focusId && m.id !== focusId ? 'dim' : '',
      focusId && m.id === focusId ? 'focus' : '',
      editMode ? 'editable' : '',
    ]
      .filter(Boolean)
      .join(' ');
    const tip =
      `${m.label}${m.resolved ? '' : '  (unresolved)'}  ·  conf ${m.conf}` +
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
      >
        {span.text.slice(m.s, m.e)}
        {m.flags && m.flags.length > 0 && <span className="flag-badge">&#9873;</span>}
      </mark>
    );
    pos = m.e;
  });
  if (pos < span.text.length) parts.push(span.text.slice(pos));

  const hasFlags = span.flags && span.flags.length > 0;

  return (
    <div className={rowClass}>
      <div
        className={
          'speaker' +
          (isDialogue && !span.speaker ? ' missing' : '') +
          (span.anonymous_speaker ? ' anonymous' : '') +
          (speakerEditable ? ' editable' : '')
        }
        style={span.anonymous_speaker && span.speaker_colour ? { color: span.speaker_colour } : undefined}
        onClick={speakerEditable ? (e) => onSpeakerClick(span, e) : undefined}
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
              {span.anonymous_speaker ? 'anonymous' : span.speaker ? span.method : ''}
            </span>
          </>
        )}
        {isInnerMonologue && span.speaker && (
          <>
            <span className="thinking">{span.speaker}</span>
            <span className="method">thinking</span>
          </>
        )}
      </div>
      <div className="body">
        {editMode ? (
          <select
            className="tag-select"
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
            <button onClick={() => onFlagLine(span)}>flag</button>
            {canMergeUp && <button onClick={onMergeUp}>merge&nbsp;&uarr;</button>}
          </span>
        )}
      </div>
    </div>
  );
}
