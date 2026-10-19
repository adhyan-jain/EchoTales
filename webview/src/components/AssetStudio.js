import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { User, MapPin, Check, X, RefreshCw, AlertTriangle } from 'lucide-react';

export default function AssetStudio({ novelId }) {
  const push = useToast();
  const [subTab, setSubTab] = useState('characters'); // 'characters' | 'locations' | 'review_items'
  const [characters, setCharacters] = useState([]);
  const [selectedCharId, setSelectedCharId] = useState(null);
  const [turnarounds, setTurnarounds] = useState([]);
  const [locations] = useState([
    { id: 'loc:study', label: 'Victorian Study / Baker Street' },
    { id: 'loc:moor', label: 'Dartmoor Moorlands' },
    { id: 'loc:hall', label: 'Baskerville Hall' },
  ]);
  const [selectedLocId, setSelectedLocId] = useState('loc:study');
  const [locationPlates, setLocationPlates] = useState([]);
  const [reviewItems, setReviewItems] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load cast characters
  const loadCharacters = useCallback(async () => {
    try {
      const data = await api.characters(novelId);
      const raw = (data && data.characters) || [];
      const list = raw.map((c) => ({
        ...c,
        id: c.self_id || c.id,
        label: c.label || c.canonical_label || c.name || c.self_id || c.id,
        canonical_label: c.canonical_label || c.label || c.name || c.self_id || c.id,
      }));
      setCharacters(list);
      if (list.length > 0 && !selectedCharId) {
        setSelectedCharId(list[0].id);
      }
    } catch {
      // Fallback cast
      const fallback = [
        { id: 'char:holmes', canonical_label: 'Sherlock Holmes', label: 'Sherlock Holmes' },
        { id: 'char:watson', canonical_label: 'Dr. John Watson', label: 'Dr. John Watson' },
        { id: 'char:mortimer', canonical_label: 'Dr. James Mortimer', label: 'Dr. James Mortimer' },
      ];
      setCharacters(fallback);
      if (!selectedCharId) setSelectedCharId(fallback[0].id);
    }
  }, [novelId, selectedCharId]);

  // Load turnarounds for selected character
  const loadTurnarounds = useCallback(async (selfId) => {
    if (!selfId) return;
    setLoading(true);
    try {
      const list = await api.listTurnarounds(novelId, selfId);
      setTurnarounds(list || []);
    } catch (err) {
      push(describeError(err, 'Failed to load character turnarounds.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, push]);

  // Load location plates
  const loadLocationPlates = useCallback(async (locId) => {
    if (!locId) return;
    setLoading(true);
    try {
      const list = await api.listLocationPlates(novelId, locId);
      setLocationPlates(list || []);
    } catch (err) {
      push(describeError(err, 'Failed to load location master plates.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, push]);

  // Load review items
  const loadReviewItems = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api.listReviewItems(novelId);
      setReviewItems(items || []);
    } catch (err) {
      push(describeError(err, 'Failed to load review items.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, push]);

  useEffect(() => {
    loadCharacters();
  }, [loadCharacters]);

  useEffect(() => {
    if (subTab === 'characters' && selectedCharId) {
      loadTurnarounds(selectedCharId);
    } else if (subTab === 'locations' && selectedLocId) {
      loadLocationPlates(selectedLocId);
    } else if (subTab === 'review_items') {
      loadReviewItems();
    }
  }, [subTab, selectedCharId, selectedLocId, loadTurnarounds, loadLocationPlates, loadReviewItems]);

  const handleApproveTurnaround = async (candidateId) => {
    try {
      await api.approveTurnaround(novelId, selectedCharId, candidateId);
      push('Turnaround approved and locked for keyframe rendering.', 'success');
      loadTurnarounds(selectedCharId);
    } catch (err) {
      push(describeError(err, 'Failed to approve turnaround.'), 'danger');
    }
  };

  const handleRejectTurnaround = async (candidateId) => {
    try {
      await api.rejectTurnaround(novelId, selectedCharId, candidateId);
      push('Turnaround rejected.', 'neutral');
      loadTurnarounds(selectedCharId);
    } catch (err) {
      push(describeError(err, 'Failed to reject turnaround.'), 'danger');
    }
  };

  const handleGenerateTurnaround = async () => {
    setLoading(true);
    try {
      await api.generateTurnaround(novelId, selectedCharId);
      push('New 3-view turnaround generated.', 'success');
      loadTurnarounds(selectedCharId);
    } catch (err) {
      push(describeError(err, 'Failed to generate turnaround.'), 'danger');
    } finally {
      setLoading(false);
    }
  };

  const handleApproveLocation = async (plateId) => {
    try {
      await api.approveLocationPlate(novelId, selectedLocId, plateId);
      push('Location master plate approved.', 'success');
      loadLocationPlates(selectedLocId);
    } catch (err) {
      push(describeError(err, 'Failed to approve plate.'), 'danger');
    }
  };

  const handleRejectLocation = async (plateId) => {
    try {
      await api.rejectLocationPlate(novelId, selectedLocId, plateId);
      push('Location plate rejected.', 'neutral');
      loadLocationPlates(selectedLocId);
    } catch (err) {
      push(describeError(err, 'Failed to reject plate.'), 'danger');
    }
  };

  const handleGenerateLocation = async () => {
    setLoading(true);
    try {
      await api.generateLocationPlate(novelId, selectedLocId);
      push('New location master plate generated.', 'success');
      loadLocationPlates(selectedLocId);
    } catch (err) {
      push(describeError(err, 'Failed to generate location plate.'), 'danger');
    } finally {
      setLoading(false);
    }
  };

  const handleResolveReviewItem = async (itemId) => {
    try {
      await api.resolveReviewItem(novelId, itemId, 'RESOLVED_MANUAL');
      push('Review item resolved.', 'success');
      loadReviewItems();
    } catch (err) {
      push(describeError(err, 'Failed to resolve review item.'), 'danger');
    }
  };

  return (
    <section className="space-y-6" data-testid="asset-studio">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="font-display text-xl font-bold tracking-tight">Asset Studio</h2>
          <p className="mt-1 text-sm text-muted">
            Approved character turnarounds, expression sheets, and master location plates.
          </p>
        </div>

        <div role="group" aria-label="Asset studio views" className="inline-flex rounded-2xl border border-border bg-surface p-1">
          <button
            type="button"
            aria-pressed={subTab === 'characters'}
            onClick={() => setSubTab('characters')}
            className={
              'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ' +
              (subTab === 'characters' ? 'bg-primary text-white shadow-glow' : 'text-muted hover:text-text')
            }
          >
            <User className="h-4 w-4" aria-hidden="true" /> Character Turnarounds
          </button>
          <button
            type="button"
            aria-pressed={subTab === 'locations'}
            onClick={() => setSubTab('locations')}
            className={
              'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ' +
              (subTab === 'locations' ? 'bg-primary text-white shadow-glow' : 'text-muted hover:text-text')
            }
          >
            <MapPin className="h-4 w-4" aria-hidden="true" /> Location Plates
          </button>
          <button
            type="button"
            aria-pressed={subTab === 'review_items'}
            onClick={() => setSubTab('review_items')}
            className={
              'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ' +
              (subTab === 'review_items' ? 'bg-primary text-white shadow-glow' : 'text-muted hover:text-text')
            }
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" /> Bible Review Queue
            {reviewItems.filter((i) => !i.resolved).length > 0 && (
              <Badge tone="warning">{reviewItems.filter((i) => !i.resolved).length}</Badge>
            )}
          </button>
        </div>
      </div>

      {subTab === 'characters' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          <div className="rounded-3xl border border-border bg-surface p-4 lg:col-span-1">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Characters</h3>
            <div className="space-y-1">
              {characters.map((c) => {
                const charId = c.self_id || c.id;
                const charLabel = c.label || c.canonical_label || c.name || charId;
                const isSelected = selectedCharId === charId;
                return (
                  <button
                    key={charId}
                    type="button"
                    onClick={() => setSelectedCharId(charId)}
                    className={
                      'flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors ' +
                      (isSelected ? 'bg-primary/10 text-primary font-semibold' : 'text-muted hover:bg-surface2 hover:text-text')
                    }
                  >
                    <span>{charLabel}</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-4 border-t border-border pt-4">
              <Button variant="secondary" size="sm" className="w-full" onClick={handleGenerateTurnaround} disabled={loading}>
                <RefreshCw className={'h-3.5 w-3.5 ' + (loading ? 'animate-spin' : '')} /> Generate New Sheet
              </Button>
            </div>
          </div>

          <div className="rounded-3xl border border-border bg-surface p-6 lg:col-span-3">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h3 className="font-display text-base font-bold text-text">
                  Turnarounds &amp; Expressions for {
                    (() => {
                      const sel = characters.find((c) => (c.self_id || c.id) === selectedCharId);
                      return sel ? (sel.label || sel.canonical_label || sel.name || sel.self_id || sel.id) : (selectedCharId || 'Character');
                    })()
                  }
                </h3>
                <p className="text-xs text-muted">3-View Turnaround (Front, Side, Back) &bull; 7 Expression Set</p>
              </div>
            </div>

            <div className="mt-6">
              {turnarounds.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-12 text-center">
                  <User className="h-10 w-10 text-muted/60" />
                  <p className="mt-3 text-sm font-medium text-text">No reference turnarounds generated yet</p>
                  <p className="mt-1 text-xs text-muted">Generate a 3-view turnaround with Qwen-Image-Edit Multiple Angles LoRA.</p>
                  <Button variant="primary" size="sm" className="mt-4" onClick={handleGenerateTurnaround} disabled={loading}>
                    Generate Turnaround
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {turnarounds.map((cand) => (
                    <div key={cand.id} className="overflow-hidden rounded-2xl border border-border bg-surface2 p-4">
                      <div className="flex items-center justify-between pb-3">
                        <span className="font-mono text-xs text-muted">{cand.id}</span>
                        <Badge tone={cand.is_approved ? 'success' : 'neutral'}>
                          {cand.is_approved ? 'Approved' : 'Pending Approval'}
                        </Badge>
                      </div>
                      <div className="relative flex h-48 items-center justify-center rounded-xl bg-bg/80 overflow-hidden border border-border/40">
                        {cand.image_url ? (
                          <img
                            src={cand.image_url}
                            alt={cand.title || `Turnaround ${cand.id}`}
                            className="h-full w-full object-cover transition-transform duration-300 hover:scale-105"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                              if (e.currentTarget.nextSibling) {
                                e.currentTarget.nextSibling.style.display = 'flex';
                              }
                            }}
                          />
                        ) : null}
                        <div
                          className={
                            'flex h-full w-full flex-col items-center justify-center p-3 text-center ' +
                            (cand.image_url ? 'hidden' : '')
                          }
                        >
                          <span className="font-mono text-xs text-muted">{cand.title || '3-View Turnaround + 7 Expressions'}</span>
                          <span className="mt-1 text-[11px] text-muted/70">Qwen-Image Angles LoRA</span>
                        </div>
                      </div>
                      <div className="mt-4 flex gap-2">
                        <Button
                          variant={cand.is_approved ? 'secondary' : 'primary'}
                          size="sm"
                          className="flex-1"
                          onClick={() => handleApproveTurnaround(cand.id)}
                        >
                          <Check className="h-3.5 w-3.5" /> Approve
                        </Button>
                        <Button variant="danger" size="sm" onClick={() => handleRejectTurnaround(cand.id)}>
                          <X className="h-3.5 w-3.5" /> Reject
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {subTab === 'locations' && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          <div className="rounded-3xl border border-border bg-surface p-4 lg:col-span-1">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">Master Locations</h3>
            <div className="space-y-1">
              {locations.map((loc) => (
                <button
                  key={loc.id}
                  type="button"
                  onClick={() => setSelectedLocId(loc.id)}
                  className={
                    'flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors ' +
                    (selectedLocId === loc.id ? 'bg-primary/10 text-primary font-semibold' : 'text-muted hover:bg-surface2 hover:text-text')
                  }
                >
                  <span>{loc.label}</span>
                </button>
              ))}
            </div>
            <div className="mt-4 border-t border-border pt-4">
              <Button variant="secondary" size="sm" className="w-full" onClick={handleGenerateLocation} disabled={loading}>
                <RefreshCw className={'h-3.5 w-3.5 ' + (loading ? 'animate-spin' : '')} /> Generate Plate
              </Button>
            </div>
          </div>

          <div className="rounded-3xl border border-border bg-surface p-6 lg:col-span-3">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h3 className="font-display text-base font-bold text-text">
                  Master Plates for {locations.find((l) => l.id === selectedLocId)?.label || selectedLocId}
                </h3>
                <p className="text-xs text-muted">Wide establishing plate, angles, and day/night variants</p>
              </div>
            </div>

            <div className="mt-6">
              {locationPlates.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-12 text-center">
                  <MapPin className="h-10 w-10 text-muted/60" />
                  <p className="mt-3 text-sm font-medium text-text">No location master plates generated yet</p>
                  <p className="mt-1 text-xs text-muted">Generate a master plate for background consistency across shots.</p>
                  <Button variant="primary" size="sm" className="mt-4" onClick={handleGenerateLocation} disabled={loading}>
                    Generate Master Plate
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {locationPlates.map((plate) => (
                    <div key={plate.id} className="overflow-hidden rounded-2xl border border-border bg-surface2 p-4">
                      <div className="flex items-center justify-between pb-3">
                        <span className="font-mono text-xs text-muted">{plate.id}</span>
                        <Badge tone={plate.is_approved ? 'success' : 'neutral'}>
                          {plate.is_approved ? 'Approved' : 'Pending Approval'}
                        </Badge>
                      </div>
                      <div className="relative flex h-48 items-center justify-center rounded-xl bg-bg/80 overflow-hidden border border-border/40">
                        {plate.image_url ? (
                          <img
                            src={plate.image_url}
                            alt={plate.title || `Master Plate ${plate.id}`}
                            className="h-full w-full object-cover transition-transform duration-300 hover:scale-105"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                              if (e.currentTarget.nextSibling) {
                                e.currentTarget.nextSibling.style.display = 'flex';
                              }
                            }}
                          />
                        ) : null}
                        <div
                          className={
                            'flex h-full w-full flex-col items-center justify-center p-3 text-center ' +
                            (plate.image_url ? 'hidden' : '')
                          }
                        >
                          <span className="font-mono text-xs text-muted">{plate.title || 'Master Plate Variant'}</span>
                          <span className="mt-1 text-[11px] text-muted/70">Establishing Background</span>
                        </div>
                      </div>
                      <div className="mt-4 flex gap-2">
                        <Button
                          variant={plate.is_approved ? 'secondary' : 'primary'}
                          size="sm"
                          className="flex-1"
                          onClick={() => handleApproveLocation(plate.id)}
                        >
                          <Check className="h-3.5 w-3.5" /> Approve
                        </Button>
                        <Button variant="danger" size="sm" onClick={() => handleRejectLocation(plate.id)}>
                          <X className="h-3.5 w-3.5" /> Reject
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {subTab === 'review_items' && (
        <div className="rounded-3xl border border-border bg-surface p-6">
          <div className="flex items-center justify-between border-b border-border pb-4">
            <div>
              <h3 className="font-display text-base font-bold text-text">Story Bible Review Queue</h3>
              <p className="text-xs text-muted">
                Ambiguous entity merges, alias contradictions, and trait mutations detected across chapters.
              </p>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {reviewItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center text-muted">
                <Check className="h-8 w-8 text-success" />
                <p className="mt-2 text-sm font-medium text-text">Review Queue Clean</p>
                <p className="text-xs text-muted">Zero unresolved entity or alias contradictions in the story bible.</p>
              </div>
            ) : (
              reviewItems.map((item) => (
                <div key={item.id} className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-surface2 p-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge tone={item.resolved ? 'success' : 'warning'}>
                        {item.kind || 'Ambiguous Merge'}
                      </Badge>
                      <span className="text-xs font-semibold text-text">Chapter {item.chapter}</span>
                    </div>
                    <p className="mt-2 text-sm text-text">{item.message}</p>
                    {item.candidates && item.candidates.length > 0 && (
                      <p className="mt-1 text-xs text-muted">Candidates: {item.candidates.join(', ')}</p>
                    )}
                  </div>

                  {!item.resolved && (
                    <Button variant="secondary" size="sm" onClick={() => handleResolveReviewItem(item.id)}>
                      Resolve Contradiction
                    </Button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  );
}
