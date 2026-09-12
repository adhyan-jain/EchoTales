import React, { useRef, useState } from 'react';

/* A fixed bar pattern (not random-per-render) reads as a waveform without
   pulling in a real decode/analysis library -- adequate for a cast-listing
   preview; a real per-clip waveform is a later, backend-fed upgrade. */
const BARS = [3, 7, 5, 9, 4, 8, 6, 10, 5, 7, 3, 9, 6, 4, 8, 5, 7, 3, 6, 9, 4, 8, 5, 7];

export default function AudioPlayer({ label, duration, src }) {
  const [playing, setPlaying] = useState(false);
  const ref = useRef(null);

  const toggle = () => {
    if (!ref.current) return;
    if (playing) ref.current.pause();
    else ref.current.play();
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={toggle}
        aria-label={playing ? 'Pause' : 'Play'}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-border text-text hover:border-accent hover:text-accent"
      >
        {playing ? (
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><rect width="3" height="12" /><rect x="6" width="3" height="12" /></svg>
        ) : (
          <svg width="10" height="12" viewBox="0 0 10 12" fill="currentColor"><path d="M0 0L10 6L0 12Z" /></svg>
        )}
      </button>
      <div className="flex h-9 flex-1 items-end gap-[2px]">
        {BARS.map((h, i) => (
          <div key={i} className="w-1 bg-border" style={{ height: `${h * 3.2}px` }} />
        ))}
      </div>
      <div className="shrink-0 font-mono text-xs text-muted">{label} &middot; {duration}</div>
      {src && (
        <audio ref={ref} src={src} onEnded={() => setPlaying(false)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} />
      )}
    </div>
  );
}
