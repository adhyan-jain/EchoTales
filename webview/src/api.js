const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8787';

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

async function request(path, options) {
  const token = getAuthToken();
  const opts = { ...options };
  if (token) {
    opts.headers = { ...(options && options.headers), Authorization: `Bearer ${token}` };
  }
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    if (res.status === 401) {
      // Token is gone/expired/wrong -- clear it so the app can detect "log
      // in again" rather than keep retrying a dead token on every request.
      clearAuthToken();
    }
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

function postCorrection(novelId, type, payload) {
  return request(`/api/novels/${novelId}/corrections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, payload }),
  });
}

export const api = {
  base: API_BASE,
  manifest: () => request('/api/manifest'),
  novel: (id) => request(`/api/novels/${id}`),
  corrections: (id) => request(`/api/novels/${id}/corrections`),

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

  characters: (novelId) => request(`/api/novels/${novelId}/characters`),

  setVoice: (novelId, selfId, speakerId, note) =>
    request(`/api/novels/${novelId}/characters/${selfId}/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ speaker_id: speakerId, note }),
    }),

  selectReference: (novelId, selfId, candidateId, note) =>
    request(`/api/novels/${novelId}/characters/${selfId}/reference`, {
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
    request(`/api/novels/${novelId}/corrections/${correctionId}`, { method: 'DELETE' }),
  applyCorrections: (novelId) => request(`/api/novels/${novelId}/apply`, { method: 'POST' }),
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
