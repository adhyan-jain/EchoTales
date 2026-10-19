import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { Clapperboard, Video, MessageSquare, Clock, AlertTriangle, RefreshCw, Save } from 'lucide-react';

const SHOT_SIZES = ['establishing', 'wide', 'medium', 'close', 'extreme_close', 'reaction', 'insert'];
const CAMERA_MOVES = ['static', 'slow_push_in', 'pull_out', 'pan_left', 'pan_right', 'tilt_up', 'tilt_down', 'rack_focus', 'impact_shake'];

export default function ScreenplayEditor({ novelId, episodeId = 'ep1', onSelectShot }) {
  const push = useToast();
  const [episode, setEpisode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [selectedShotIdx, setSelectedShotIdx] = useState(0);

  const loadEpisode = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getScreenplayEpisode(novelId, episodeId);
      setEpisode(data);
    } catch (err) {
      push(describeError(err, 'Failed to load screenplay episode.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, episodeId, push]);

  useEffect(() => {
    loadEpisode();
  }, [loadEpisode]);

  const handleSave = async () => {
    if (!episode) return;
    setSaving(true);
    try {
      await api.saveScreenplayEpisode(novelId, episode.episode_id || episodeId, episode);
      push('Screenplay episode saved.', 'success');
    } catch (err) {
      push(describeError(err, 'Failed to save screenplay episode.'), 'danger');
    } finally {
      setSaving(false);
    }
  };

  const handleCompile = async () => {
    setLoading(true);
    try {
      const compiled = await api.compileScreenplay(novelId, episodeId, {
        chapters: episode ? episode.chapter_range || [1.0] : [1.0],
      });
      setEpisode(compiled);
      push('Screenplay compiled from novel chapter text.', 'success');
    } catch (err) {
      push(describeError(err, 'Failed to compile screenplay.'), 'danger');
    } finally {
      setLoading(false);
    }
  };

  const updateShot = (sceneIndex, shotIndex, updates) => {
    if (!episode) return;
    const newScenes = [...episode.scenes];
    const targetScene = { ...newScenes[sceneIndex] };
    const newShots = [...targetScene.shots];
    newShots[shotIndex] = { ...newShots[shotIndex], ...updates };
    targetScene.shots = newShots;
    newScenes[sceneIndex] = targetScene;
    setEpisode({ ...episode, scenes: newScenes });
  };

  if (loading && !episode) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted" data-testid="screenplay-loading">
        Loading episode screenplay...
      </div>
    );
  }

  if (!episode) return null;

  const allShots = (episode.scenes || []).flatMap((sc, scIdx) =>
    (sc.shots || []).map((sh, shIdx) => ({ ...sh, sceneIndex: scIdx, shotIdxInScene: shIdx }))
  );

  return (
    <section className="space-y-6" data-testid="screenplay-editor">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Clapperboard className="h-5 w-5 text-accent" />
            <h2 className="font-display text-lg font-bold tracking-tight">
              {episode.title || `Episode ${episodeId}`}
            </h2>
          </div>
          <p className="mt-1 text-sm text-muted">
            Chapter range: {episode.chapter_range?.join(' – ') || '1.0'} &bull; {allShots.length} shots &bull; Rule-governed pacing
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={handleCompile} disabled={loading || saving}>
            <RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')} /> Re-compile Screenplay
          </Button>
          <Button variant="primary" size="sm" onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4" /> Save Changes
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        {(episode.scenes || []).map((scene, scIdx) => (
          <div key={scene.scene_id || scIdx} className="rounded-3xl border border-border bg-surface p-6 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
              <div className="flex items-center gap-3">
                <span className="font-display text-sm font-bold text-accent">
                  SCENE {scIdx + 1}: {scene.scene_id}
                </span>
                <Badge tone="neutral">{scene.location_id}</Badge>
                <Badge tone="accent">{scene.time_of_day || 'day'}</Badge>
              </div>
              <span className="text-xs text-muted">{scene.shots?.length || 0} shots</span>
            </div>

            <div className="space-y-3">
              {(scene.shots || []).map((shot, shIdx) => {
                const isSelected = selectedShotIdx === shot.shot_index;
                const isHoldTooLong = shot.duration_s > 6.0;

                return (
                  <div
                    key={shot.shot_index ?? shIdx}
                    onClick={() => {
                      setSelectedShotIdx(shot.shot_index);
                      if (onSelectShot) onSelectShot(shot.shot_index);
                    }}
                    className={
                      'cursor-pointer rounded-2xl border p-4 transition-all ' +
                      (isSelected
                        ? 'border-accent bg-surface2 ring-1 ring-accent'
                        : 'border-border bg-surface hover:border-border/80')
                    }
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="rounded-lg bg-surface px-2 py-0.5 font-mono text-xs font-bold text-text">
                          Shot #{shot.shot_index + 1}
                        </span>
                        <Badge tone={shot.render_tier === 'video' ? 'accent' : 'neutral'}>
                          {shot.render_tier || '2.5d'}
                        </Badge>
                        <span className="text-xs text-muted">{shot.shot_size} &bull; {shot.camera_move}</span>
                      </div>

                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-1 text-xs text-muted">
                          <Clock className="h-3.5 w-3.5" />
                          <span>{shot.duration_s?.toFixed(1)}s</span>
                        </div>
                        {isHoldTooLong && (
                          <Badge tone="danger">
                            <AlertTriangle className="h-3 w-3" /> Still hold &gt; 6s
                          </Badge>
                        )}
                      </div>
                    </div>

                    <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
                      <div>
                        <label className="text-[10px] font-semibold uppercase tracking-wider text-muted">Action &amp; Pose</label>
                        <input
                          type="text"
                          value={shot.action || ''}
                          onChange={(e) => updateShot(scIdx, shIdx, { action: e.target.value })}
                          className="mt-1 w-full rounded-xl border border-border bg-surface px-3 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
                        />
                      </div>

                      <div className="flex gap-2">
                        <div className="flex-1">
                          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted">Framing</label>
                          <select
                            value={shot.shot_size || 'medium'}
                            onChange={(e) => updateShot(scIdx, shIdx, { shot_size: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-border bg-surface px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
                          >
                            {SHOT_SIZES.map((sz) => (
                              <option key={sz} value={sz}>{sz}</option>
                            ))}
                          </select>
                        </div>

                        <div className="flex-1">
                          <label className="text-[10px] font-semibold uppercase tracking-wider text-muted">Camera Movement</label>
                          <select
                            value={shot.camera_move || 'static'}
                            onChange={(e) => updateShot(scIdx, shIdx, { camera_move: e.target.value })}
                            className="mt-1 w-full rounded-xl border border-border bg-surface px-2 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
                          >
                            {CAMERA_MOVES.map((cm) => (
                              <option key={cm} value={cm}>{cm}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                    </div>

                    {shot.dialogue && shot.dialogue.length > 0 && (
                      <div className="mt-3 rounded-xl border border-border/60 bg-surface/50 p-3">
                        <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                          <MessageSquare className="h-3 w-3" /> Dialogue &amp; Performance
                        </div>
                        <div className="mt-2 space-y-2">
                          {shot.dialogue.map((diag, dIdx) => (
                            <div key={dIdx} className="flex flex-wrap items-center gap-2 text-xs">
                              <Badge tone="accent">{diag.speaker_id}</Badge>
                              <span className="italic text-text">&ldquo;{diag.text}&rdquo;</span>
                              {diag.emotion && (
                                <Badge tone="neutral">
                                  {diag.emotion} (intensity {diag.intensity ?? 1})
                                </Badge>
                              )}
                              {diag.nonverbal && diag.nonverbal.length > 0 && (
                                <span className="text-[10px] text-muted">[{diag.nonverbal.join(', ')}]</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {shot.onomatopoeia && (
                      <div className="mt-2 text-xs text-accent">
                        <span className="font-semibold uppercase">Onomatopoeia:</span> {shot.onomatopoeia}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
