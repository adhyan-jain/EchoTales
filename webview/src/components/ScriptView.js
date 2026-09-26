import React from 'react';
import ScriptLine from './ScriptLine';
import { EmptyState } from './ui/EmptyState';
import ManuscriptSurface from './ui/ManuscriptSurface';

// Span ids are `<novel>:<chapter>:<block>:<index>`. The backend only merges
// spans within one block ("spans are not in the same block"), but Merge ↑
// used to be offered between any two adjacent lines, so the merge failed
// only later, at Apply (QA run, 2026-09-26).
function sameBlock(prev, span) {
  if (!prev || !prev.span_id || !span.span_id) return false;
  const block = (id) => id.split(':').slice(0, -1).join(':');
  return block(prev.span_id) === block(span.span_id);
}

export default function ScriptView({
  chapter,
  focusId,
  onMarkHover,
  onMarkMove,
  onMarkLeave,
  editMode,
  onMentionClick,
  onSpeakerClick,
  onFlagLine,
  onMergeLines,
  onRetype,
  onCreateMention,
}) {
  // `chapter` can be undefined for a beat after a manifest refresh --
  // the Read and Review pages derive it from the URL's chapter, and a fresh/updated
  // manifest can report fewer chapters than the index still selected from
  // before the refresh, which threw "Cannot read properties of undefined
  // (reading 'spans')" here instead of rendering an honest empty state.
  if (!chapter) {
    return (
      <div id="script">
        <EmptyState title="No chapter selected" description="Pick a chapter, or wait for the manifest to finish loading." />
      </div>
    );
  }
  return (
    <ManuscriptSurface chapterLabel={`Chapter ${String(chapter.number).padStart(2, '0')}${chapter.title ? ` · ${chapter.title}` : ''}`}>
    <div id="script">
      {chapter.spans.map((span, i) => {
        const prev = i > 0 ? chapter.spans[i - 1] : null;
        return (
          <ScriptLine
            key={span.span_id || i}
            span={span}
            focusId={focusId}
            onMarkHover={onMarkHover}
            onMarkMove={onMarkMove}
            onMarkLeave={onMarkLeave}
            editMode={editMode}
            onMentionClick={onMentionClick}
            onSpeakerClick={(s, e) => onSpeakerClick(s, e, chapter.number)}
            onFlagLine={(s) => onFlagLine(s, chapter.number)}
            canMergeUp={editMode && sameBlock(prev, span)}
            onMergeUp={() => onMergeLines(prev.span_id, span.span_id, chapter.number)}
            onRetype={(s, newType) => onRetype(s, newType, chapter.number)}
            onCreateMention={onCreateMention ? (s, e) => onCreateMention(s, e, chapter.number) : undefined}
          />
        );
      })}
    </div>
    </ManuscriptSurface>
  );
}
