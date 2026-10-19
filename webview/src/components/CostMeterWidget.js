import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api';
import Button from './ui/Button';
import Badge from './ui/Badge';
import { useToast } from './ui/Toast';
import { describeError } from '../lib/errors';
import { DollarSign, AlertCircle, RefreshCw, Film } from 'lucide-react';

export default function CostMeterWidget({ novelId, episodeId = 'ep1', onTierChange }) {
  const push = useToast();
  const [tier, setTier] = useState('path1');
  const [costData, setCostData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchCost = useCallback(async (selectedTier) => {
    setLoading(true);
    try {
      const data = await api.getEpisodeCost(novelId, episodeId, selectedTier);
      setCostData(data);
    } catch (err) {
      push(describeError(err, 'Failed to fetch pre-render cost estimate.'), 'danger');
    } finally {
      setLoading(false);
    }
  }, [novelId, episodeId, push]);

  useEffect(() => {
    fetchCost(tier);
  }, [fetchCost, tier]);

  const handleTierToggle = (newTier) => {
    setTier(newTier);
    if (onTierChange) onTierChange(newTier);
  };

  const maxAllowedCost = tier === 'path1' ? 0.50 : 1.80;
  const isOverBudget = costData && costData.cost_per_finished_minute_usd > maxAllowedCost;

  return (
    <section className="rounded-3xl border border-border bg-surface p-6 shadow-card" data-testid="cost-meter-widget">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <DollarSign className="h-5 w-5 text-accent" aria-hidden="true" />
            <h2 className="font-display text-lg font-bold tracking-tight">Pre-Render Cost Meter</h2>
          </div>
          <p className="mt-1 text-sm text-muted">
            Itemized RunPod serverless GPU and open-model token budget before rendering.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div role="group" aria-label="Render tier selection" className="inline-flex rounded-xl border border-border bg-surface2 p-1">
            <button
              type="button"
              aria-pressed={tier === 'path1'}
              onClick={() => handleTierToggle('path1')}
              className={
                'rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ' +
                (tier === 'path1' ? 'bg-primary text-white shadow-sm' : 'text-muted hover:text-text')
              }
            >
              Path 1: 2.5D Reels
            </button>
            <button
              type="button"
              aria-pressed={tier === 'path2'}
              onClick={() => handleTierToggle('path2')}
              className={
                'rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ' +
                (tier === 'path2' ? 'bg-primary text-white shadow-sm' : 'text-muted hover:text-text')
              }
            >
              Path 2: Wan 2.2 Video
            </button>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => fetchCost(tier)}
            disabled={loading}
            aria-label="Refresh cost estimate"
          >
            <RefreshCw className={'h-4 w-4 ' + (loading ? 'animate-spin' : '')} />
          </Button>
        </div>
      </div>

      {loading && !costData ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted" data-testid="cost-loading">
          Calculating episode token &amp; GPU costs...
        </div>
      ) : costData ? (
        <div className="mt-6 space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-2xl border border-border bg-surface2 p-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">Cost Per Min</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-display text-2xl font-bold tracking-tight text-text" data-testid="cost-per-minute">
                  ${costData.cost_per_finished_minute_usd.toFixed(2)}
                </span>
                <span className="text-xs text-muted">/ finished min</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <Badge tone={isOverBudget ? 'danger' : 'success'}>
                  {isOverBudget ? 'Over Budget' : 'Within Budget'}
                </Badge>
                <span className="text-xs text-muted">(Target &le; ${maxAllowedCost.toFixed(2)})</span>
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-surface2 p-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">Total Episode Cost</span>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-display text-2xl font-bold tracking-tight text-accent" data-testid="total-cost">
                  ${costData.total_estimated_usd.toFixed(2)}
                </span>
                <span className="text-xs text-muted">USD</span>
              </div>
              <p className="mt-2 text-xs text-muted">
                {costData.num_shots} shots &bull; {(costData.episode_duration_s / 60).toFixed(1)} minutes
              </p>
            </div>

            <div className="rounded-2xl border border-border bg-surface2 p-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted">Render Strategy</span>
              <div className="mt-2 flex items-center gap-2">
                <Film className="h-5 w-5 text-primary" />
                <span className="font-semibold text-text">
                  {tier === 'path1' ? '2.5D Parallax Motion Comic' : 'Wan 2.2 S2V / A14B + Fallback'}
                </span>
              </div>
              <p className="mt-2 text-xs text-muted">
                {tier === 'path1' ? 'RunPod Serverless Flex ($0.0003/s)' : 'Hybrid Video & Parallax fallback'}
              </p>
            </div>
          </div>

          {isOverBudget && (
            <div className="flex items-center gap-3 rounded-2xl border border-danger/40 bg-danger/10 p-4 text-sm text-danger" role="alert">
              <AlertCircle className="h-5 w-5 shrink-0" />
              <span>
                Cost estimate exceeds target ceiling (${maxAllowedCost.toFixed(2)}/min). Consider reducing shot count or switching to Path 1 2.5D reels.
              </span>
            </div>
          )}

          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Itemized Breakdown</h3>
            <div className="overflow-hidden rounded-2xl border border-border bg-surface">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border bg-surface2 font-semibold text-muted">
                  <tr>
                    <th className="px-4 py-2.5">Engine / Resource</th>
                    <th className="px-4 py-2.5">Units</th>
                    <th className="px-4 py-2.5 text-right">Estimated Cost (USD)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/60">
                  {costData.breakdown && (
                    <>
                      <tr>
                        <td className="px-4 py-2 font-medium text-text">LLM Screenplay Compilation</td>
                        <td className="px-4 py-2 text-muted">{costData.breakdown.llm_screenplay_tokens?.toLocaleString() || 0} tokens</td>
                        <td className="px-4 py-2 text-right font-mono">${(costData.breakdown.llm_screenplay_cost_usd || 0).toFixed(4)}</td>
                      </tr>
                      <tr>
                        <td className="px-4 py-2 font-medium text-text">Keyframe Image Generation</td>
                        <td className="px-4 py-2 text-muted">{costData.breakdown.image_generation_count || 0} images</td>
                        <td className="px-4 py-2 text-right font-mono">${(costData.breakdown.image_generation_cost_usd || 0).toFixed(4)}</td>
                      </tr>
                      <tr>
                        <td className="px-4 py-2 font-medium text-text">Voice Synthesis (Qwen3-TTS / Dia2)</td>
                        <td className="px-4 py-2 text-muted">{costData.breakdown.audio_seconds?.toFixed(1) || 0}s audio</td>
                        <td className="px-4 py-2 text-right font-mono">${(costData.breakdown.voice_synthesis_cost_usd || 0).toFixed(4)}</td>
                      </tr>
                      <tr>
                        <td className="px-4 py-2 font-medium text-text">Compositor / Video Render</td>
                        <td className="px-4 py-2 text-muted">{costData.breakdown.video_render_seconds?.toFixed(1) || 0}s GPU</td>
                        <td className="px-4 py-2 text-right font-mono">${(costData.breakdown.video_render_cost_usd || 0).toFixed(4)}</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
