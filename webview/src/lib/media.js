import { api } from '../api';

const IMAGE_RE = /\.(png|jpe?g|webp)$/i;

// Stub-engine placeholder panels are small flat images; real renders from
// the local diffusion engines are several hundred KB. Below this size a
// "panel" is almost certainly a placeholder and would make the landing and
// overview imagery look broken, so it is skipped.
const MIN_REAL_PANEL_BYTES = 60 * 1024;

/**
 * The newest real panel images for a project, as file paths.
 *
 * The output directory holds every version ever rendered (ch1 alone has
 * 40+ version folders, many of them documented failures in VERSIONS.md), so
 * "all panels" would surface old defects. Newest-first by mtime is the best
 * available proxy for "current", since each version supersedes the last.
 * Crowd cuts are skipped: out of context they read as noise.
 */
export function pickPanels(output, limit = 12) {
  const panels = (output && output.kinds && output.kinds.panels) || [];
  return panels
    .filter((p) => IMAGE_RE.test(p.path) && !/crowd/i.test(p.path) && (p.size || 0) >= MIN_REAL_PANEL_BYTES)
    .sort((a, b) => (b.mtime || 0) - (a.mtime || 0))
    .slice(0, limit)
    .map((p) => p.path);
}

/** Reference sheets (one per character body), newest first. */
export function pickReferenceSheets(output, limit = 8) {
  const refs = (output && output.kinds && output.kinds.references) || [];
  return refs
    .filter((p) => IMAGE_RE.test(p.path))
    .sort((a, b) => (b.mtime || 0) - (a.mtime || 0))
    .slice(0, limit)
    .map((p) => p.path);
}

export function fileUrl(novelId, path) {
  return api.outputFileUrl(novelId, path);
}

/**
 * A server-resized WebP of a panel (`?w=` on the output-file route; widths
 * 320/480/960 only). Cards and tiles use this: full-size panels are up to
 * 1.4 MB each, and the landing page alone pulled ~23 MB of them to fill
 * 480px tiles (measured 2026-09-26). The full file stays available via
 * `fileUrl` for when one is actually opened.
 */
export function thumbUrl(novelId, path, width = 480) {
  return `${fileUrl(novelId, path)}&w=${width}`;
}

export function countKind(output, kind, re = null) {
  const items = (output && output.kinds && output.kinds[kind]) || [];
  return re ? items.filter((i) => re.test(i.path)).length : items.length;
}
