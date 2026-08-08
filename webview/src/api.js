const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:8787';

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
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

  reassignSpeaker: (novelId, spanId, chapter, target) =>
    postCorrection(novelId, 'reassign_speaker', {
      span_id: spanId,
      chapter,
      speaker_id: typeof target === 'string' ? target : null,
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
// for (§ user request: "every line... option to change it to NON DIEGETIC
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
