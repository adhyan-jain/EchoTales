import React from 'react';
import ScriptLine from './ScriptLine';

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
}) {
  return (
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
            canMergeUp={editMode && !!prev && !!prev.span_id && !!span.span_id}
            onMergeUp={() => onMergeLines(prev.span_id, span.span_id, chapter.number)}
            onRetype={(s, newType) => onRetype(s, newType, chapter.number)}
          />
        );
      })}
    </div>
  );
}
