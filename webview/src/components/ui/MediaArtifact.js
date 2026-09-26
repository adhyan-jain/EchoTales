import React from 'react';
import DepthCard from './DepthCard';
import Label from './Label';
import { fileUrl, thumbUrl } from '../../lib/media';

// `GET /api/novels/<id>/output` is a pure filesystem walk
// (`webview_server.py::_list_output`) -- it returns `{path, size, mtime}`
// per file, nothing richer (no duration/backend/render-state metadata
// exists server-side). Chapter/version are real, though: `pipeline/paths.py`
// writes every artifact under `<kind>/ch<N>/v<M>/...`, so parsing them out
// of the path is reading a real, documented convention, not guessing.
function parsePathMeta(path) {
  const m = /ch([\d.]+)\/v(\d+)/.exec(path || '');
  return { chapter: m ? m[1] : null, version: m ? m[2] : null };
}

function formatBytes(n) {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export const VIDEO_RE = /\.(mp4|webm|mov)$/i;
export const AUDIO_RE = /\.(wav|mp3|ogg|flac|m4a)$/i;
export const IMAGE_RE = /\.(png|jpe?g|webp)$/i;

/**
 * One rendered file, with a way to actually look at or listen to it. The
 * library used to list bare filenames marked "on disk": no player, no
 * preview -- for the video, audio and panels the product exists to make
 * (2026-09-26 QA). `preload="none"` keeps a 262 MB chapter video from
 * downloading until someone presses play.
 */
export default function MediaArtifact({ item, novelId, compact = false }) {
  const { chapter, version } = parsePathMeta(item.path);
  const filename = (item.path || '').split('/').pop();
  const src = novelId ? fileUrl(novelId, item.path) : null;

  return (
    <DepthCard className="overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="overflow-hidden text-ellipsis whitespace-nowrap font-mono text-sm text-text">{filename}</div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-muted">
              {chapter && <span>ch{chapter}</span>}
              {version && <span>v{version}</span>}
              {item.size != null && <span>{formatBytes(item.size)}</span>}
              {item.mtime && <span>{new Date(item.mtime * 1000).toLocaleDateString()}</span>}
            </div>
          </div>
          {src && (
            <a
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-muted hover:border-accent/60 hover:text-text"
              aria-label={`Open ${filename} in a new tab`}
            >
              Open
            </a>
          )}
          {!src && <Label tone="neutral">on disk</Label>}
        </div>
        {src && VIDEO_RE.test(item.path) && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video controls preload="none" className={`mt-3 w-full rounded-xl bg-black ${compact ? 'max-h-56' : 'max-h-[420px]'}`}>
            <source src={src} />
            Your browser can’t play this video.
          </video>
        )}
        {src && AUDIO_RE.test(item.path) && (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <audio controls preload="none" className="mt-3 w-full" src={src}>
            Your browser can’t play this audio.
          </audio>
        )}
        {src && IMAGE_RE.test(item.path) && (
          <a href={src} target="_blank" rel="noopener noreferrer" className="mt-3 block overflow-hidden rounded-xl bg-surface2">
            <img
              src={thumbUrl(novelId, item.path, 480)}
              alt={`Panel ${filename}`}
              loading="lazy"
              className="max-h-72 w-full object-contain"
            />
          </a>
        )}
      </div>
    </DepthCard>
  );
}
