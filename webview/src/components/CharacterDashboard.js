import React, { useEffect, useState, useCallback } from 'react';
import { api } from '../api';

/**
 * Per-character review dashboard: voice casting, reference-image selection,
 * and -- the reason this component exists -- the evidence trail behind every
 * trait a persona was assigned. A reviewer overriding a trait/voice/image
 * needs to see *why* the pipeline picked what it picked, not just the
 * current value, or the override is a guess instead of a correction.
 */
export default function CharacterDashboard({ novelId }) {
  const [status, setStatus] = useState('loading'); // 'loading' | 'ready' | 'error' | 'not_found'
  const [characters, setCharacters] = useState([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [search, setSearch] = useState('');
  const [pendingAction, setPendingAction] = useState(null); // selfId currently mid-request, for disabling controls
  const [voiceDrafts, setVoiceDrafts] = useState({}); // selfId -> in-progress text input value

  const load = useCallback(() => {
    if (!novelId) return;
    setStatus((prev) => (prev === 'ready' ? 'ready' : 'loading'));
    api
      .characters(novelId)
      .then((data) => {
        setCharacters((data && data.characters) || []);
        setStatus('ready');
      })
      .catch((err) => {
        // A fresh project with no personas/audio generated yet 404s -- that's
        // an expected, honest empty state, not a crash.
        if (err && (err.status === 404 || err.statusCode === 404)) {
          setCharacters([]);
          setStatus('not_found');
          return;
        }
        setErrorMessage((err && err.message) || 'Failed to load characters.');
        setStatus('error');
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  const withPending = (selfId, fn) => {
    setPendingAction(selfId);
    fn().finally(() => setPendingAction(null));
  };

  const handleSetVoice = (selfId) => {
    const speakerId = (voiceDrafts[selfId] || '').trim();
    if (!speakerId) return;
    withPending(selfId, () =>
      api
        .setVoice(novelId, selfId, speakerId, 'manual override via dashboard')
        .then(() => {
          setVoiceDrafts((prev) => ({ ...prev, [selfId]: '' }));
          load();
        })
    );
  };

  const handleSelectReference = (selfId, candidateId) => {
    withPending(selfId, () =>
      api
        .selectReference(novelId, selfId, candidateId, 'selected via dashboard')
        .then(() => load())
    );
  };

  const q = search.toLowerCase();
  const filtered = characters.filter((c) => (c.label || '').toLowerCase().includes(q));

  return (
    <div className="char-dashboard">
      <div className="char-dashboard-search">
        <input
          type="search"
          placeholder="Filter characters…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {status === 'loading' && (
        <div className="char-dashboard-state">Loading characters&hellip;</div>
      )}

      {status === 'error' && (
        <div className="char-dashboard-state char-dashboard-state-error">
          Couldn&rsquo;t load characters: {errorMessage}
        </div>
      )}

      {status === 'not_found' && (
        <div className="char-dashboard-state char-dashboard-state-empty">
          No character data yet for this novel -- personas/voices haven&rsquo;t
          been generated for this project.
        </div>
      )}

      {status === 'ready' && characters.length === 0 && (
        <div className="char-dashboard-state char-dashboard-state-empty">
          No characters found for this novel yet.
        </div>
      )}

      {status === 'ready' && characters.length > 0 && filtered.length === 0 && (
        <div className="char-dashboard-state char-dashboard-state-empty">
          No characters match &ldquo;{search}&rdquo;.
        </div>
      )}

      {status === 'ready' && filtered.length > 0 && (
        <div className="char-card-list">
          {filtered.map((c) => (
            <CharacterCard
              key={c.self_id}
              character={c}
              busy={pendingAction === c.self_id}
              voiceDraft={voiceDrafts[c.self_id] || ''}
              onVoiceDraftChange={(v) =>
                setVoiceDrafts((prev) => ({ ...prev, [c.self_id]: v }))
              }
              onSetVoice={() => handleSetVoice(c.self_id)}
              onSelectReference={(candidateId) =>
                handleSelectReference(c.self_id, candidateId)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CharacterCard({
  character,
  busy,
  voiceDraft,
  onVoiceDraftChange,
  onSetVoice,
  onSelectReference,
}) {
  const { label, prominence, voice, traits = [], reference_images: refs = [] } = character;

  return (
    <div className="char-card">
      <div className="char-card-header">
        <h3 className="char-card-name">{label}</h3>
        {prominence && (
          <span className={`prominence-badge prominence-${prominence.toLowerCase()}`}>
            {prominence}
          </span>
        )}
      </div>

      <section className="char-card-section char-voice-section">
        <h4 className="char-section-title">Voice</h4>
        {voice ? (
          <div className="char-voice-current">
            <span className="voice-label">
              {voice.speaker_label || voice.speaker_id || voice.voice}
              {voice.speaker_id && voice.speaker_label ? ` (${voice.speaker_id})` : ''}
            </span>
            {voice.overridden && <span className="overridden-tag">manually overridden</span>}
            {voice.sample_audio_path ? (
              <audio className="voice-sample" controls src={voice.sample_audio_path}>
                Your browser does not support audio playback.
              </audio>
            ) : null}
          </div>
        ) : (
          <div className="char-empty-note">No voice assigned yet</div>
        )}
        <div className="voice-override">
          <input
            type="text"
            className="voice-override-input"
            placeholder="speaker id (e.g. p227)"
            value={voiceDraft}
            disabled={busy}
            onChange={(e) => onVoiceDraftChange(e.target.value)}
          />
          <button
            type="button"
            className="btn-gradient"
            disabled={busy || !voiceDraft.trim()}
            onClick={onSetVoice}
          >
            Set voice
          </button>
        </div>
      </section>

      <section className="char-card-section char-refs-section">
        <h4 className="char-section-title">Reference images</h4>
        {refs.length === 0 ? (
          <div className="char-empty-note">No reference images found yet</div>
        ) : (
          <div className="ref-gallery">
            {refs.map((r) => (
              <button
                type="button"
                key={r.id}
                className={`ref-thumb${r.selected ? ' ref-thumb-selected' : ''}`}
                disabled={busy || r.selected}
                title={r.title || ''}
                onClick={() => onSelectReference(r.id)}
              >
                <img
                  src={r.thumbnail_url || r.source_url}
                  alt={r.title || label}
                  loading="lazy"
                />
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="char-card-section char-evidence-section">
        <h4 className="char-section-title">Traits &amp; evidence</h4>
        {traits.length === 0 ? (
          <div className="char-empty-note">No traits recorded yet</div>
        ) : (
          <ul className="trait-list">
            {traits.map((t, i) => (
              <li className="trait-row" key={`${t.key}-${i}`}>
                <div className="trait-headline">
                  <span className="trait-key">{t.key}</span>: <span className="trait-value">{t.value}</span>
                </div>
                {t.evidence && <blockquote className="trait-evidence">&ldquo;{t.evidence}&rdquo;</blockquote>}
                <div className="trait-meta">
                  {typeof t.confidence === 'number' && (
                    <span className="trait-confidence">
                      {Math.round(t.confidence * 100)}% confidence
                    </span>
                  )}
                  {t.provenance && <span className="trait-provenance">{t.provenance}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
