// A production build is normally served by the backend itself
// (`echotales webview-server --static-dir webview/build`), so it talks to its
// own origin. `npm start` runs on :3000 and needs the backend's :8787.
// REACT_APP_API_BASE overrides both (e.g. a build hosted elsewhere).
const API_BASE =
  process.env.REACT_APP_API_BASE ?? (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8787');

// Every id segment is encoded. Ids now arrive from the browser URL
// (/p/:projectId, /characters/:selfId) rather than only from a server-populated
// <select>, so a hand-edited URL must not be able to inject `/` or `?` into
// a backend path. Entity ids contain ':' (e.g. "novel:self:4768..."), which
// encodes to %3A and is decoded by the server's router.
const enc = encodeURIComponent;

// sessionStorage (not localStorage) so the token clears when the tab closes --
// every route but /api/auth/status and /api/auth/login requires it once the
// server has auth_required: true.
const AUTH_TOKEN_KEY = 'echotales_auth_token';

function getAuthToken() {
  try {
    return sessionStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

function setAuthToken(token) {
  try {
    sessionStorage.setItem(AUTH_TOKEN_KEY, token);
  } catch {
    // sessionStorage unavailable (e.g. private mode edge cases) -- requests
    // just go out unauthenticated and the server will 401.
  }
}

function clearAuthToken() {
  try {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // no-op -- see getAuthToken/setAuthToken.
  }
}

/**
 * An API failure with enough structure for the UI to say something useful.
 * `status` is the HTTP status (0 for a network failure); `serverMessage` is
 * what the backend put in `{error}`. Before this, request() threw a bare
 * Error carrying the server's raw text, so a 500 with a Python traceback was
 * shown to users verbatim, and every failure was indistinguishable from
 * "server down" (2026-09-26 failure-state QA). `describeError` in
 * lib/errors.js turns this into user-facing copy.
 */
export class ApiError extends Error {
  constructor(status, serverMessage) {
    super(serverMessage || (status ? `HTTP ${status}` : 'Network error'));
    this.name = 'ApiError';
    this.status = status;
    this.statusCode = status;
    this.serverMessage = serverMessage || '';
  }
}

async function request(path, options) {
  const token = getAuthToken();
  const opts = { ...options };
  if (token) {
    opts.headers = { ...(options && options.headers), Authorization: `Bearer ${token}` };
  }
  // A server that accepts the connection but never answers used to leave
  // every page on "Loading..." indefinitely (failure-state QA, 2026-09-26).
  // 30 s covers the largest payload (a 9.6 MB novel); a file upload gets 5 min.
  const timeoutMs = options && options.body instanceof FormData ? 300000 : 30000;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  opts.signal = controller.signal;
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, opts);
  } catch {
    throw new ApiError(0, '');
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    if (res.status === 401) {
      // Token is gone/expired/wrong -- clear it so the app can detect "log
      // in again" rather than keep retrying a dead token on every request.
      clearAuthToken();
    }
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.error);
  }
  return res.json();
}

function postCorrection(novelId, type, payload) {
  return request(`/api/novels/${enc(novelId)}/corrections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, payload }),
  });
}

export const api = {
  base: API_BASE,
  manifest: () => request('/api/manifest'),
  novel: (id) => request(`/api/novels/${enc(id)}`),
  // Chapter numbers/titles only -- the full novel payload is ~9.4 MB.
  chapters: (id) => request(`/api/novels/${enc(id)}/chapters`),
  corrections: (id) => request(`/api/novels/${enc(id)}/corrections`),

  authStatus: () => request('/api/auth/status'),

  // Stores the returned token into sessionStorage on success (in addition to
  // returning it), so callers don't have to remember to do it themselves.
  login: (password) =>
    request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }).then((result) => {
      if (result && result.token) {
        setAuthToken(result.token);
      }
      return result;
    }),

  logout: () => {
    clearAuthToken();
  },

  // Optimistic only -- a stale/expired token still reads true here and
  // simply 401s (clearing itself) on the first real request. Used by
  // App.js to decide whether to skip the login screen on load.
  hasToken: () => !!getAuthToken(),

  createProject: (id, title, contentType) =>
    request('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, title, content_type: contentType }),
    }),

  characters: (novelId) => request(`/api/novels/${enc(novelId)}/characters`),

  setVoice: (novelId, selfId, speakerId, note) =>
    request(`/api/novels/${enc(novelId)}/characters/${enc(selfId)}/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speaker_id: speakerId, note }),
    }),

  selectReference: (novelId, selfId, candidateId, note) =>
    request(`/api/novels/${enc(novelId)}/characters/${enc(selfId)}/reference`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate_id: candidateId, note }),
    }),

  mergeEntities: (novelId, fromId, intoId) =>
    postCorrection(novelId, 'merge_entities', { from_id: fromId, into_id: intoId }),

  // `target` is either an existing entity id, or { new_label: "..." } to
  // found a character that isn't in the list yet -- same shape for both
  // mentions and speakers, so the caller doesn't need two code paths.
  reassignMention: (novelId, mentionId, target) =>
    postCorrection(novelId, 'reassign_mention', {
      mention_id: mentionId,
      target_id: typeof target === 'string' ? target : null,
      new_label: target && target.new_label ? target.new_label : null,
    }),

  // `target` also accepts { anon_slot: 1..4 } -- a distinct voice slot with
  // no identity, same id scheme the pipeline's own anonymous-slot pass uses
  // (speakers/runner.py::_assign_anonymous_slots), so it renders as "Unknown
  // Speaker N" and gets that slot's colour. Lets a reviewer put a line back
  // into a numbered slot instead of only being able to clear it to bare
  // "unattributed" -- including undoing an accidental clear.
  reassignSpeaker: (novelId, spanId, chapter, target) =>
    postCorrection(novelId, 'reassign_speaker', {
      span_id: spanId,
      chapter,
      speaker_id: typeof target === 'string' ? target : null,
      new_label: target && target.new_label ? target.new_label : null,
      anon_slot: target && target.anon_slot ? target.anon_slot : null,
    }),

  // For text the detector never proposed as a mention at all ("old bastard
  // Fang" referring to Fang Yuan) -- `localStart`/`localEnd` are offsets into
  // `span.text`, the same coordinate space `marks[].s`/`.e` already use, so
  // the browser sends exactly what the user selected with no translation.
  createMention: (novelId, spanId, chapter, localStart, localEnd, text, target) =>
    postCorrection(novelId, 'create_mention', {
      span_id: spanId,
      chapter,
      local_start: localStart,
      local_end: localEnd,
      text,
      target_id: typeof target === 'string' ? target : null,
      new_label: target && target.new_label ? target.new_label : null,
    }),

  mergeLines: (novelId, primarySpanId, absorbedSpanId, chapter) =>
    postCorrection(novelId, 'merge_lines', {
      primary_span_id: primarySpanId,
      absorbed_span_id: absorbedSpanId,
      chapter,
    }),

  flag: (novelId, { spanId, mentionId, chapter, note, source }) =>
    postCorrection(novelId, 'flag', {
      span_id: spanId || null,
      mention_id: mentionId || null,
      chapter,
      note,
      source: source || 'human',
    }),

  reassignSpanType: (novelId, spanId, chapter, newType) =>
    postCorrection(novelId, 'reassign_span_type', { span_id: spanId, chapter, new_type: newType }),

  undoCorrection: (novelId, correctionId) =>
    request(`/api/novels/${enc(novelId)}/corrections/${enc(correctionId)}`, { method: 'DELETE' }),
  applyCorrections: (novelId) => request(`/api/novels/${enc(novelId)}/apply`, { method: 'POST' }),

  // -- Product Orchestration track (project lifecycle, jobs, reference
  // search, render preview/generate, output library) -- these wrap real,
  // already-shipped `webview_server.py` routes; see that module's own
  // docstring for the full route list.

  listProjects: () => request('/api/projects'),
  deleteProject: (novelId) => request(`/api/projects/${enc(novelId)}`, { method: 'DELETE' }),

  uploadSource: (novelId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/api/projects/${enc(novelId)}/source`, { method: 'POST', body: form });
  },

  // `kind` is one of ingest/resolve/appearance/persona/render/voice/
  // refimg_search/reference_gen (`jobs.py::JOB_KINDS`) -- one trigger
  // route per stage, all shaped the same.
  triggerStage: (novelId, kind, params = {}) =>
    request(`/api/projects/${enc(novelId)}/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),

  listJobs: (novelId) => request(`/api/projects/${enc(novelId)}/jobs`),
  getJob: (novelId, jobId) => request(`/api/projects/${enc(novelId)}/jobs/${enc(jobId)}`),

  listReferenceCandidates: (novelId, selfId) =>
    request(`/api/novels/${enc(novelId)}/characters/${enc(selfId)}/reference/candidates`),

  searchReferences: (novelId, selfId) =>
    request(`/api/novels/${enc(novelId)}/characters/${enc(selfId)}/reference/search`, { method: 'POST' }),

  uploadReference: (novelId, selfId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/api/novels/${enc(novelId)}/characters/${enc(selfId)}/reference/upload`, {
      method: 'POST',
      body: form,
    });
  },

  renderPreview: (novelId, params) =>
    request(`/api/novels/${enc(novelId)}/render/preview?${new URLSearchParams(params)}`),

  renderGenerate: (novelId, body) =>
    request(`/api/novels/${enc(novelId)}/render/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  referenceGenerate: (novelId, body = {}) =>
    request(`/api/novels/${enc(novelId)}/reference/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  listOutput: (novelId) => request(`/api/novels/${enc(novelId)}/output`),
  outputFileUrl: (novelId, path) =>
    `${API_BASE}/api/novels/${enc(novelId)}/output/file?path=${encodeURIComponent(path)}`,
};

// Mirrors `SpanType` in packages/core/.../enums.py. NON_DIEGETIC and the
// narration types are listed first -- the two retype targets actually asked
// for (Section user request: "every line... option to change it to NON DIEGETIC
// and narrator").
export const SPAN_TYPES = [
  'NON_DIEGETIC',
  'NARRATION_ACTION',
  'NARRATION_DESCRIPTION',
  'NARRATION_EXPOSITION',
  'DIALOGUE',
  'INNER_MONOLOGUE',
  'CROWD_REACTION',
  'SYSTEM_WINDOW',
];
