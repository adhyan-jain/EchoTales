import React from 'react';
import DepthCard from './DepthCard';
import Label from './Label';

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

export default function MediaArtifact({ item }) {
  const { chapter, version } = parsePathMeta(item.path);
  const filename = (item.path || '').split('/').pop();
  return (
    <DepthCard className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-text">{filename}</div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-muted">
            {chapter && <span>ch{chapter}</span>}
            {version && <span>v{version}</span>}
            {item.size != null && <span>{formatBytes(item.size)}</span>}
            {item.mtime && <span>{new Date(item.mtime * 1000).toLocaleDateString()}</span>}
          </div>
        </div>
        <Label tone="neutral">on disk</Label>
      </div>
    </DepthCard>
  );
}
