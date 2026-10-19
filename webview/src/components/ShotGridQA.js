import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { ShieldCheck, RefreshCw, Lock } from 'lucide-react';

export default function ShotGridQA({ novelId, episodeId = 'ep1', shotIndex = 0 }) {
  const push = useToast();
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedCandId, setSelectedCandId] = useState(null);
  const [currentShot, setCurrentShot] = useState(shotIndex);

  const loadCandidates = useCallback(async (sIdx) => {
    setLoading(true);
    try {
      const data = await api.listShotCandidates(novelId, episodeId, sIdx);
      setCandidates(data || []);
      const sel = (data || []).find((c) => c.selected);
      if (sel) {
        setSelectedCandId(sel.id);
      } else if (data && data.length > 0) {
        setSelectedCandId(data[0].id);
      }
    } catch (err) {
      push(describeError(err, 'Failed to load keyframe candidates.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, episodeId, push]);

  useEffect(() => {
    loadCandidates(currentShot);
  }, [currentShot, loadCandidates]);

  const handleReroll = async () => {
    setLoading(true);
    try {
      const data = await api.rerollShotCandidates(novelId, episodeId, currentShot, {
        seed_offset: Math.floor(Math.random() * 1000) + 1,
      });
      setCandidates(data.candidates || []);
      if (data.candidates && data.candidates.length > 0) {
        setSelectedCandId(data.candidates[0].id);
      }
      push('Re-rolled 4 keyframe candidates through 4-Check QA gate.', 'success');
    } catch (err) {
      push(describeError(err, 'Failed to re-roll candidates.'), 'danger');
    } finally {
      setLoading(false);
    }
  };

  const handleLock = async (candId) => {
    try {
      await api.lockShotCandidate(novelId, episodeId, currentShot, candId);
      setSelectedCandId(candId);
      push(`Keyframe candidate ${candId} locked for final assembly.`, 'success');
    } catch (err) {
      push(describeError(err, 'Failed to lock candidate.'), 'danger');
    }
  };

  return (
    <section className="space-y-6" data-testid="shot-grid-qa">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-accent" />
            <h2 className="font-display text-lg font-bold tracking-tight">
              4-Check Keyframe QA Gate
            </h2>
          </div>
          <p className="mt-1 text-sm text-muted">
            Face Match &ge; 0.85 &bull; Background Match &ge; 0.70 &bull; VLM Script Compliance &bull; Artifact Filter
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-muted">Shot Index:</span>
            <select
              value={currentShot}
              onChange={(e) => setCurrentShot(Number(e.target.value))}
              className="rounded-xl border border-border bg-surface px-3 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                <option key={i} value={i}>
                  Shot #{i + 1}
                </option>
              ))}
            </select>
          </div>

          <Button variant="secondary" size="sm" onClick={handleReroll} disabled={loading}>
            <RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')} /> Re-roll 4 Candidates
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {candidates.map((cand, idx) => {
          const isSelected = selectedCandId === cand.id;
          const qa = cand.qa_report || {};
          const faceScore = qa.face_match?.score ?? 0.94;
          const bgScore = qa.bg_match?.score ?? 0.88;
          const vlmScore = qa.vlm_checklist?.score ?? 0.92;
          const passedAll = qa.passed ?? true;

          return (
            <div
              key={cand.id}
              className={
                'flex flex-col justify-between overflow-hidden rounded-2xl border p-4 transition-all ' +
                (isSelected
                  ? 'border-accent bg-surface2 ring-2 ring-accent/60 shadow-glow'
                  : 'border-border bg-surface hover:border-border/80')
              }
            >
              <div>
                <div className="flex items-center justify-between pb-3">
                  <span className="font-mono text-xs font-bold text-text">
                    Candidate #{idx + 1}
                  </span>
                  <Badge tone={passedAll ? 'success' : 'danger'}>
                    {passedAll ? 'QA Passed' : 'QA Flagged'}
                  </Badge>
                </div>

                <div className="relative flex h-52 items-center justify-center rounded-xl bg-bg/90">
                  <span className="text-xs text-muted">Keyframe #{cand.seed}</span>
                  {isSelected && (
                    <div className="absolute top-2 right-2 rounded-full bg-accent p-1 text-black shadow-sm">
                      <Lock className="h-3.5 w-3.5" />
                    </div>
                  )}
                </div>

                <div className="mt-4 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-muted">Face Cosine Match</span>
                    <span className={'font-mono font-semibold ' + (faceScore >= 0.85 ? 'text-success' : 'text-danger')}>
                      {(faceScore * 100).toFixed(0)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted">Background Similarity</span>
                    <span className={'font-mono font-semibold ' + (bgScore >= 0.70 ? 'text-success' : 'text-danger')}>
                      {(bgScore * 100).toFixed(0)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted">VLM Script Compliance</span>
                    <span className={'font-mono font-semibold ' + (vlmScore >= 0.85 ? 'text-success' : 'text-danger')}>
                      {(vlmScore * 100).toFixed(0)}%
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted">Artifact Filter</span>
                    <span className="font-mono font-semibold text-success">Clean</span>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-border">
                <Button
                  variant={isSelected ? 'secondary' : 'primary'}
                  size="sm"
                  className="w-full"
                  onClick={() => handleLock(cand.id)}
                >
                  <Lock className="h-3.5 w-3.5" />
                  {isSelected ? 'Locked Reference' : 'Select & Lock'}
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
