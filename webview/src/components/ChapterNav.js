import React from 'react';

export default function ChapterNav({ chapters, chapterIdx, onChange, coverage }) {
  return (
    <div id="chapter-nav">
      <button disabled={chapterIdx === 0} onClick={() => onChange(chapterIdx - 1)}>&larr;</button>
      <select value={chapterIdx} onChange={(e) => onChange(parseInt(e.target.value, 10))}>
        {chapters.map((ch, i) => (
          <option key={ch.number} value={i}>Chapter {ch.number}</option>
        ))}
      </select>
      <button
        disabled={chapterIdx >= chapters.length - 1}
        onClick={() => onChange(chapterIdx + 1)}
      >&rarr;</button>
      <span className="cov">{coverage}</span>
    </div>
  );
}
