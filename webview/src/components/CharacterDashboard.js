import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Input from './ui/Input';
import Label from './ui/Label';
import Divider from './ui/Divider';
import { Card, CardBody } from './ui/Card';
import EvidenceBlock from './ui/EvidenceBlock';
import CharacterRow from './ui/CharacterRow';
import AudioPlayer from './ui/AudioPlayer';
import DossierHeader from './ui/DossierHeader';
import TimelineRail from './ui/TimelineRail';
import { EmptyState, LoadingState } from './ui/EmptyState';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';

const PROMINENCE_LABEL = {
  PRINCIPAL: 'Principal Character',
  RECURRING: 'Recurring Character',
  INCIDENTAL: 'Incidental',
};

/**
 * Cast archive: a manifest of every resolved character, drilling into a
 * production-desk view per character -- voice casting, reference-image
 * selection, and -- the reason this component exists -- the evidence trail
 * behind every trait a persona was assigned. A reviewer overriding a
 * trait/voice/image needs to see *why* the pipeline picked what it picked,
 * not just the current value, or the override is a guess instead of a
 * correction.
 */
// `selectedId`/`onSelect` are optional: the routed Characters page passes
// them so the open dossier lives in the URL (/characters/:selfId) and the back
// button returns to the grid. Without them the component keeps its own
// selection state, as it always has.
export default function CharacterDashboard({ novelId, readOnly = false, selectedId: controlledId, onSelect }) {
  const [status, setStatus] = useState('loading'); // 'loading' | 'ready' | 'error' | 'not_found'
  const [characters, setCharacters] = useState([]);
  const [errorMessage, setErrorMessage] = useState('');
  const [search, setSearch] = useState('');
  const [ownSelectedId, setOwnSelectedId] = useState(null);
  const selectedId = controlledId !== undefined ? controlledId : ownSelectedId;
  const setSelectedId = onSelect || setOwnSelectedId;
  const [showIncidental, setShowIncidental] = useState(false);
  const [pendingAction, setPendingAction] = useState(null); // selfId currently mid-request, for disabling controls
  const push = useToast();

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
        setErrorMessage(describeError(err, 'Failed to load characters.'));
        setStatus('error');
      });
  }, [novelId]);

  useEffect(() => {
    load();
  }, [load]);

  // The drilled-in character is a live reference into `characters`, not a
  // frozen snapshot -- a voice/reference override calls `load()`, and if the
  // reader stays on the detail view it must reflect the refreshed row, not
  // the pre-override one.
  const selected = useMemo(
    () => characters.find((c) => c.self_id === selectedId) || null,
    [characters, selectedId]
  );

  const withPending = (selfId, fn) => {
    setPendingAction(selfId);
    return fn().finally(() => setPendingAction(null));
  };

  const handleSetVoice = (selfId, speakerId) => {
    if (!speakerId.trim()) return Promise.resolve();
    return withPending(selfId, () =>
      api
        .setVoice(novelId, selfId, speakerId.trim(), 'manual override via dashboard')
        .then(() => {
          push('Voice updated.', 'success');
          load();
        })
        .catch((err) => {
          push(describeError(err, 'Could not update voice.'), 'danger');
          throw err;
        })
    );
  };

  const handleSelectReference = (selfId, candidateId) => {
    return withPending(selfId, () =>
      api
        .selectReference(novelId, selfId, candidateId, 'selected via dashboard')
        .then(() => {
          push('Reference image updated.', 'success');
          load();
        })
        .catch((err) => {
          push(describeError(err, 'Could not update reference image.'), 'danger');
          throw err;
        })
    );
  };

  // Enqueues a real `refimg_search` job (Product Orchestration track) --
  // the search itself runs async server-side, so this only confirms the
  // job was queued; the new candidates show up on the next `load()` a
  // reviewer triggers (there's no push channel to auto-refresh on job
  // completion).
  const handleSearchReferences = (selfId) => {
    return withPending(selfId, () =>
      api
        .searchReferences(novelId, selfId)
        .then(() => {
          push('Reference search queued. Refresh this page in a moment to see new candidates.', 'success');
        })
        .catch((err) => {
          push(describeError(err, 'Could not queue reference search.'), 'danger');
          throw err;
        })
    );
  };

  const q = search.toLowerCase();
  const filtered = characters.filter((c) => (c.label || '').toLowerCase().includes(q));
  const mainCast = filtered.filter((c) => c.prominence !== 'INCIDENTAL');
  const incidentalCast = filtered.filter((c) => c.prominence === 'INCIDENTAL');
  // Numbering runs across the whole manifest (main cast first, then
  // incidental) so a row's index is stable regardless of whether the
  // incidental group is expanded -- a real ordinal, not a per-group one.
  const indexOf = new Map(filtered.map((c, i) => [c.self_id, i + 1]));

  // A shared or stale link to a character this project does not have (or no
  // longer has, after a merge) gets a clear dead end rather than the grid
  // silently replacing the page the user asked for.
  if (controlledId && status === 'ready' && !selected) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-8">
        <EmptyState
          as="h1"
          title="Character not found"
          description="This link points to a character this book doesn't have. It may have been merged into another character during review."
          action={
            <Button variant="secondary" onClick={() => setSelectedId(null)}>
              Back to all characters
            </Button>
          }
        />
      </div>
    );
  }

  if (selected) {
    return (
      <CharacterDetail
        character={selected}
        busy={pendingAction === selected.self_id}
        readOnly={readOnly}
        onBack={() => setSelectedId(null)}
        onSetVoice={readOnly ? undefined : (speakerId) => handleSetVoice(selected.self_id, speakerId)}
        onSelectReference={readOnly ? undefined : (candidateId) => handleSelectReference(selected.self_id, candidateId)}
        onSearchReferences={readOnly ? undefined : () => handleSearchReferences(selected.self_id)}
      />
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4 pb-8">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-accent">Characters</div>
          <h1 className="mt-1.5 font-display text-3xl font-bold tracking-tight text-text sm:text-4xl">Cast</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted">
            Everyone the book resolved, with the voice, reference look and evidence behind each one.
          </p>
        </div>
        <div className="w-full sm:w-72">
          <Input
            type="search"
            aria-label="Filter characters"
            placeholder="Filter characters…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </header>

      {status === 'loading' && <LoadingState label="Loading cast" />}

      {status === 'error' && (
        <div className="mt-8 border-l-2 border-danger pl-4 font-sans text-sm text-danger">
          Couldn&rsquo;t load characters: {errorMessage}
        </div>
      )}

      {status === 'not_found' && (
        <div className="mt-8">
          <EmptyState
            title="No character data yet"
            description="Personas and voices haven't been generated for this project yet."
          />
        </div>
      )}

      {status === 'ready' && characters.length === 0 && (
        <div className="mt-8">
          <EmptyState title="No characters found" description="This novel has no resolved cast yet." />
        </div>
      )}

      {status === 'ready' && characters.length > 0 && filtered.length === 0 && (
        <div className="mt-8">
          <EmptyState title="No matches" description={`No characters match "${search}".`} />
        </div>
      )}

      {status === 'ready' && filtered.length > 0 && (
        <div className="mt-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {mainCast.map((c) => (
              <CharacterRow
                key={c.self_id}
                index={indexOf.get(c.self_id)}
                name={c.label}
                prominence={c.prominence}
                onClick={() => setSelectedId(c.self_id)}
              />
            ))}
          </div>

          {incidentalCast.length > 0 && (
            <div className="mt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowIncidental((v) => !v)}
              >
                {showIncidental
                  ? 'Hide incidental characters'
                  : `Show ${incidentalCast.length} incidental character${incidentalCast.length === 1 ? '' : 's'}`}
              </Button>
              {showIncidental && (
                <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {incidentalCast.map((c) => (
                    <CharacterRow
                      key={c.self_id}
                      index={indexOf.get(c.self_id)}
                      name={c.label}
                      prominence={c.prominence}
                      onClick={() => setSelectedId(c.self_id)}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CharacterDetail({ character, busy, readOnly, onBack, onSetVoice, onSelectReference, onSearchReferences }) {
  const { label, prominence, voice, traits = [], reference_images: refs = [] } = character;
  const [voiceFormOpen, setVoiceFormOpen] = useState(false);
  const [voiceDraft, setVoiceDraft] = useState('');

  const submitVoice = () => {
    onSetVoice(voiceDraft).then(() => {
      setVoiceDraft('');
      setVoiceFormOpen(false);
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-8">
      <Button variant="ghost" size="sm" onClick={onBack}>
        &larr; Back to cast
      </Button>

      <div className="mt-6">
        <DossierHeader
          eyebrow="Character dossier"
          title={label}
          tone={prominence === 'PRINCIPAL' ? 'accent' : 'neutral'}
          badge={prominence ? PROMINENCE_LABEL[prominence] || prominence : null}
        />
      </div>

      <Divider label="Reference & voice" className="mb-6 mt-10" />
      <div className="grid gap-8 md:grid-cols-2">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">
              Reference images
            </div>
            {onSearchReferences && (
              <Button variant="ghost" size="sm" disabled={busy} onClick={onSearchReferences}>
                Search for more
              </Button>
            )}
          </div>
          {refs.length === 0 ? (
            <EmptyState title="No reference images yet" />
          ) : (
            <div className="space-y-4">
              {refs.map((r) => (
                <Card key={r.id}>
                  <div className="aspect-[3/4] w-full overflow-hidden bg-surface2">
                    <img
                      src={r.thumbnail_url || r.source_url}
                      alt={r.title || label}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  </div>
                  <CardBody className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      {r.selected ? (
                        <Label tone="success">Selected</Label>
                      ) : (
                        <span className="font-mono text-xs text-muted truncate block">
                          {r.title || 'Candidate'}
                        </span>
                      )}
                      {r.user_uploaded && (
                        <span className="mt-1 block font-mono text-xs text-muted">User uploaded</span>
                      )}
                    </div>
                    {!readOnly && (
                      <div className="flex shrink-0 gap-2">
                        {!r.selected && (
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={busy}
                            onClick={() => onSelectReference(r.id)}
                          >
                            Replace
                          </Button>
                        )}
                        <span title="Image-to-image editing isn't wired up in the backend yet.">
                          <Button variant="ghost" size="sm" disabled>
                            Edit reference
                          </Button>
                        </span>
                      </div>
                    )}
                  </CardBody>
                </Card>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted mb-3">Voice</div>
          <Card>
            <CardBody>
              {voice ? (
                <div>
                  <AudioPlayer
                    label={voice.speaker_label || voice.speaker_id || voice.voice}
                    duration={voice.speaker_id && voice.speaker_id !== voice.speaker_label ? voice.speaker_id : ''}
                    src={voice.sample_audio_path}
                  />
                  {voice.overridden && (
                    <div className="mt-3">
                      <Label tone="warning">Manually overridden</Label>
                    </div>
                  )}
                </div>
              ) : (
                <div className="font-sans text-sm text-muted">No voice assigned yet.</div>
              )}

              {!readOnly && (
                <>
                  <Divider className="my-4" />
                  {voiceFormOpen ? (
                    <div className="flex items-center gap-2">
                      <Input
                        placeholder="speaker id (e.g. p227)"
                        value={voiceDraft}
                        disabled={busy}
                        onChange={(e) => setVoiceDraft(e.target.value)}
                        autoFocus
                      />
                      <Button size="sm" disabled={busy || !voiceDraft.trim()} onClick={submitVoice}>
                        Save
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => {
                          setVoiceFormOpen(false);
                          setVoiceDraft('');
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <Button variant="secondary" size="sm" disabled={busy} onClick={() => setVoiceFormOpen(true)}>
                      Replace voice
                    </Button>
                  )}
                </>
              )}
            </CardBody>
          </Card>
        </div>
      </div>

      <Divider label="Traits & evidence" className="mb-6 mt-10" />
      {traits.length === 0 ? (
        <EmptyState title="No traits recorded yet" />
      ) : (
        <div className="space-y-6">
          {traits.map((t, i) => {
            const confidence =
              typeof t.confidence === 'number' ? `${Math.round(t.confidence * 100)}% confidence` : null;
            const source = [t.provenance, confidence].filter(Boolean).join(' · ');
            return (
              <EvidenceBlock
                key={`${t.key}-${i}`}
                trait={`${t.key}: ${t.value}`}
                source={source || null}
                quote={t.evidence}
              />
            );
          })}
        </div>
      )}

      <Divider label="State history" className="mb-6 mt-10" />
      {/* No `epochs` field exists on this payload (`build_character_dashboard`,
          webview.py, confirmed by reading it) -- TimelineRail renders its own
          honest "not yet available" state rather than this component
          fabricating a single-persona timeline from the current snapshot. */}
      <TimelineRail epochs={character.epochs} />
    </div>
  );
}
