import React from 'react';

export default function ChapterNav({ chapters, chapterIdx, onChange, coverage }) {
  return (
    <div id="chapter-nav">
      <button type="button" aria-label="Previous chapter" disabled={chapterIdx === 0} onClick={() => onChange(chapterIdx - 1)}>&larr;</button>
      <select aria-label="Chapter" value={chapterIdx} onChange={(e) => onChange(parseInt(e.target.value, 10))}>
        {chapters.map((ch, i) => (
          <option key={ch.number} value={i}>Chapter {ch.number}</option>
        ))}
      </select>
      <button
        type="button"
        aria-label="Next chapter"
        disabled={chapterIdx >= chapters.length - 1}
        onClick={() => onChange(chapterIdx + 1)}
      >&rarr;</button>
      <span className="cov">{coverage}</span>
    </div>
  );
}
