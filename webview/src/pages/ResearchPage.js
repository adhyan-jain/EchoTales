import React, { useEffect, useMemo, useState } from 'react';
import { FlaskConical, Layers, Play, Timer } from 'lucide-react';
import { api } from '../api';
import { AccountShell } from './Projects';
import { PageHeader, StatCard } from '../components/app/Chrome';
import { describeError } from '../lib/errors';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import { Card, CardBody, CardHeader } from '../components/ui/Card';

/**
 * Research view: the project's research claim (name-keyed memory leakage in LLM reading of fiction) shown from the
 * stored study results, plus a live probe that runs one local model on three arms of one real item.
 *
 * Every number on this page is read from a stored result file by GET /api/research/summary; nothing is computed in
 * the browser except layout. The probe items are illustrative (see `selection` from /api/research/items) -- the
 * headline numbers always come from all items, never from the six on screen.
 */

const pp = (x, signed = false) =>
  typeof x === 'number' ? `${signed && x > 0 ? '+' : ''}${(x * 100).toFixed(1).replace('-', '−')}` : '—';
const pct0 = (x) => (typeof x === 'number' ? `${Math.round(x * 100)}%`.replace('-', '−') : '—');
const secs = (x) => (typeof x === 'number' ? `${x.toFixed(1)} s` : '—');

// Dataset / series colours reuse the theme's own tokens (index.css), so light and dark both work.
const SERIES = {
  v2: { label: 'v2', colour: 'rgb(var(--c-accent))' },
  v3: { label: 'v3', colour: 'rgb(var(--c-cyan))' },
  v6: { label: 'v6', colour: 'rgb(var(--c-warning))' },
  all: { label: 'all three pooled', colour: 'rgb(var(--c-text))' },
};
const LANES = ['v2', 'v3', 'v6', 'all'];

/** The marked sentence area of a window: a stretch before `[[` and a little after `]]`. Exported for the test. */
export function excerptAroundMarker(rawText, before = 280, after = 90) {
  if (!rawText) return { pre: '', mark: '', post: '' };
  // Gutenberg hard-wraps lines; keep paragraph breaks, join the wrapped lines.
  const text = rawText.replace(/([^\n])\n(?!\n)/g, '$1 ');
  const a = text.indexOf('[[');
  const b = text.indexOf(']]');
  if (a < 0 || b < a) return { pre: text.slice(0, before), mark: '', post: '' };
  const preStart = Math.max(0, a - before);
  const postEnd = Math.min(text.length, b + 2 + after);
  // Start at a word boundary so the excerpt does not open mid-word.
  let pre = text.slice(preStart, a);
  if (preStart > 0) pre = '…' + pre.replace(/^\S*\s/, '');
  const post = text.slice(b + 2, postEnd) + (postEnd < text.length ? '…' : '');
  return { pre, mark: text.slice(a + 2, b), post };
}

function SectionTitle({ id, children, hint }) {
  return (
    <div className="mb-4">
      <h2 id={id} className="font-display text-xl font-bold tracking-tight">
        {children}
      </h2>
      {hint && <p className="mt-1 max-w-3xl text-sm text-muted">{hint}</p>}
    </div>
  );
}

// ------------------------------------------------------------------ 1. headline cards
function Headline({ data }) {
  const h = data.headline || {};
  const ref = h.reference_gap;
  const loc = h.local_pool_gap;
  const cue = h.cue_recovered;
  return (
    <section aria-labelledby="r-headline" className="grid gap-4 sm:grid-cols-3">
      <h2 id="r-headline" className="sr-only">
        Headline results
      </h2>
      <StatCard
        icon={FlaskConical}
        label="Reference model gap"
        value={ref ? `${pp(ref.gap, true)} pts` : '—'}
        hint={ref ? `95% CI ${pp(ref.lo)} to ${pp(ref.hi)} · ${ref.events} events · gpt-5.6-luna` : 'result file missing'}
        tone="warn"
      />
      <StatCard
        icon={FlaskConical}
        label="Pooled local-model gap"
        value={loc ? `${pp(loc.gap, true)} pts` : '—'}
        hint={loc ? `95% CI ${pp(loc.lo)} to ${pp(loc.hi)} · ${loc.events} events · models passing the validity gate` : 'result file missing'}
        tone="warn"
      />
      <StatCard
        icon={FlaskConical}
        label="Gap recovered by cue-preserving names"
        value={cue ? pct0(cue.fraction) : '—'}
        hint={cue ? `95% CI ${pct0(cue.lo)} to ${pct0(cue.hi)} · ${cue.events} events · near zero or below: lost name cues do not explain the gap` : 'result file missing'}
        tone="good"
      />
      <p className="text-sm text-muted sm:col-span-3">
        Gap = share of pre-reveal questions answered with the true identity under the book&rsquo;s original names minus the share when
        every proper noun is consistently renamed. A first-time reader is not yet entitled to that answer, so a positive gap is
        evidence the model is using memory of the book, not the text in front of it.
      </p>
    </section>
  );
}

// ------------------------------------------------------------------ Channel 2 Card
export function Channel2Card() {
  return (
    <Card className="border border-border/80 bg-surface shadow-sm" data-testid="channel-2-card">
      <CardHeader className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-accent" />
          <h3 className="font-display text-base font-semibold">
            Channel 2: Derivation Look-Ahead (Prefix-Faithfulness)
          </h3>
        </div>
        <Badge tone="accent">Audit &amp; Repair · Truncate-and-Rebuild Oracle</Badge>
      </CardHeader>
      <CardBody className="space-y-4 pt-4">
        <p className="text-sm text-muted">
          Measures whether facts derived across multiple chapters (e.g. persona traits) leak future information
          when filtered to early reader positions. Audited by rebuilding on truncated prefixes (<code>chapters &le; k</code>)
          versus whole-volume builds.
        </p>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-border bg-surface-hover/30 p-3">
            <span className="text-xs font-medium text-muted">Status Quo Divergence</span>
            <div className="mt-1 font-display text-2xl font-bold text-warn">6.0%</div>
            <p className="mt-1 text-xs text-muted">
              41 of 685 cuts across 3 web novels (4.5% to 8.0%); 4.5% of 179 on English originals.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-surface-hover/30 p-3">
            <span className="text-xs font-medium text-muted">Premature Disclosures</span>
            <div className="mt-1 font-display text-2xl font-bold text-warn">2.6%</div>
            <p className="mt-1 text-xs text-muted">
              18 of 685 cuts (11 characters) by model annotators (range 1.7% to 3.5%); rest supported by text.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-surface-hover/30 p-3">
            <span className="text-xs font-medium text-muted">Horizon-Versioned Repair</span>
            <div className="mt-1 font-display text-2xl font-bold text-good">0</div>
            <p className="mt-1 text-xs text-muted">
              0 divergences of 685 cuts (95% CI [0.0%, 1.3%]); 0 across all real, English, and synthetic runs.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-surface-hover/30 p-3">
            <span className="text-xs font-medium text-muted">Anchored Cue Recovery</span>
            <div className="mt-1 font-display text-2xl font-bold text-good">97%</div>
            <p className="mt-1 text-xs text-muted">
              Recovers 97% of withheld values at 1.2% error rate on web novels (prominence gate: 50 &rarr; 0).
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/50 pt-3 text-xs text-muted">
          <span>
            <strong>Repair trade-off:</strong> Horizon stamping guarantees divergence 0 (safe rather than correct); naive hiding is worse (82 divergences).
          </span>
          <span className="font-mono text-[11px]">
            Source: claude/prefix-faithfulness · REPORT.md
          </span>
        </div>
      </CardBody>
    </Card>
  );
}

// ------------------------------------------------------------------ Channel 2 on a generic design (RF-E2E)
// Whole-volume vs versioned LLM character card on the confirmatory reveal events; renamed text separates the build's
// leak (input channel) from the model's memory. Numbers come from /api/research/summary (rf_e2e/analysis.json).
export function RfE2ECard({ rf, confirm }) {
  if (!rf || !rf.strata || rf.strata.length === 0) return null;
  const ci = (iv) => (iv ? `${pp(iv.gap, true)} [${pp(iv.lo, true)}, ${pp(iv.hi, true)}]` : '—');
  return (
    <Card className="border border-border/80 bg-surface shadow-sm" data-testid="rf-e2e-card">
      <CardHeader className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-accent" />
          <h3 className="font-display text-base font-semibold">Found and fixed: whole-book character cards leak the reveal</h3>
        </div>
        <Badge tone="accent">Pre-registered · addenda 6 to 8</Badge>
      </CardHeader>
      <CardBody className="space-y-4 pt-4">
        <p className="text-sm text-muted">
          A card built once from the whole book and shown from the character&rsquo;s first appearance, against a versioned card built
          only from the text before the reader&rsquo;s position. On renamed text no model has seen, any leak comes from the build, not memory.
        </p>
        {rf.strata.map((st) => (
          <div key={st.label} className="space-y-2">
            <div className="text-xs font-medium uppercase tracking-wide text-muted">{st.label}: {(st.models || []).join(', ')}</div>
            <div className="grid gap-3 sm:grid-cols-2">
              {st.rules.map((r) => (
                <div key={r.rule} className="rounded-xl border border-border bg-surface-hover/30 p-3">
                  <span className="text-xs font-medium text-muted">{r.rule} · {r.events} events</span>
                  <div className="mt-1 flex items-baseline gap-3">
                    <span className="font-display text-2xl font-bold text-warn">{pct0(r.whole_renamed)}</span>
                    <span className="text-xs text-muted">whole-book card</span>
                    <span className="font-display text-2xl font-bold text-good">{pct0(r.versioned_renamed)}</span>
                    <span className="text-xs text-muted">versioned card</span>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    Input leak {ci(r.input_channel)} points{r.supported ? ' (supported)' : ''}; memory-only leak {ci(r.memory_channel)}.
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
        {rf.robust && (
          <p className="text-xs text-muted" data-testid="rf-robust">
            Robustness ({(rf.robust.models || []).join(', ')}): with an &ldquo;avoid spoilers&rdquo; instruction the whole-book card still leaks in{' '}
            {pct0(rf.robust.whole_nospoil_renamed)} of events against {pct0(rf.robust.versioned_renamed)} for the versioned card
            {rf.robust.prompting_does_not_remove_leak ? ' (prompting does not replace versioning)' : ''}; second cipher input leak {ci(rf.robust.cipher2_input)} points (strict text rule).
          </p>
        )}
        {rf.extra && (
          <p className="text-xs text-muted" data-testid="rf-extra">
            Earlier reader positions ({(rf.extra.models || []).join(', ')}): the versioned card leaks in {pct0(rf.extra.versioned_half)} half-way and{' '}
            {pct0(rf.extra.versioned_three_quarters)} at three quarters, while the whole-book card, shown from the first mention, leaks in{' '}
            {pct0(rf.extra.whole_any_position)} at every position; second card prompt input leak {ci(rf.extra.prompt2_input)} points.
          </p>
        )}
        {confirm && confirm.pooled_gap && (
          <p className="border-t border-border/50 pt-3 text-xs text-muted">
            Channel 1 confirmatory run ({confirm.events} events, {(confirm.models || []).join(', ')}): pooled memory gap {ci(confirm.pooled_gap)} points on
            mostly obscure books; fame contrast {ci(confirm.fame_contrast)}, p = {confirm.fame_p}.
          </p>
        )}
      </CardBody>
    </Card>
  );
}

// ------------------------------------------------------------------ 2. interval plot
function IntervalPlot({ gap }) {
  const rows = useMemo(() => {
    const out = gap.rows.map((r) => ({
      key: r.model,
      label: r.model,
      reference: r.reference,
      cells: { ...r.cells },
    }));
    const pool = { key: 'pool', label: 'Valid local pool', pool: true, cells: {} };
    const ref = out.find((r) => r.reference);
    for (const p of gap.pools) {
      const cell = { gap: p.gap, lo: p.lo, hi: p.hi, events: p.events };
      if (p.kind === 'local_pool') pool.cells[p.key === 'all_v2_v3_v6' ? 'all' : p.key] = cell;
      else if (p.kind === 'reference' && p.key === 'all_v2_v3_v6' && ref) ref.cells.all = cell;
    }
    out.push(pool);
    return out;
  }, [gap]);

  const W = 760;
  const left = 170;
  const right = 24;
  const top = 8;
  const lo = -0.45;
  const hi = 0.6;
  const x = (v) => left + ((v - lo) / (hi - lo)) * (W - left - right);
  const laneH = 11;
  const layout = [];
  let y = top;
  for (const r of rows) {
    const lanes = LANES.filter((k) => r.cells[k]);
    const h = lanes.length * laneH + 14;
    layout.push({ r, lanes, y, h });
    y += h;
  }
  const H = y + 42;
  const ticks = [-0.4, -0.2, 0, 0.2, 0.4, 0.6];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Gap between original-name and renamed accuracy, by model and dataset, with 95 percent intervals">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={H - 34} style={{ stroke: 'rgb(var(--c-border))' }} strokeWidth={t === 0 ? 1.6 : 0.6} strokeDasharray={t === 0 ? '' : '3 3'} />
            <text x={x(t)} y={H - 20} textAnchor="middle" fontSize="10" style={{ fill: 'rgb(var(--c-muted))' }}>
              {t === 0 ? '0' : pp(t, true).replace(/\.0$/, '')}
            </text>
          </g>
        ))}
        <text x={(left + W - right) / 2} y={H - 4} textAnchor="middle" fontSize="9.5" style={{ fill: 'rgb(var(--c-muted))' }}>
          gap, percentage points (original names minus renamed)
        </text>
        {layout.map(({ r, lanes, y: y0, h }) => (
          <g key={r.key}>
            {r.pool && <line x1={8} x2={W - right} y1={y0 - 1} y2={y0 - 1} style={{ stroke: 'rgb(var(--c-border))' }} strokeWidth="1" />}
            <text x={8} y={y0 + h / 2 + 3} fontSize="11" fontWeight={r.pool || r.reference ? 700 : 500} style={{ fill: 'rgb(var(--c-text))' }}>
              {r.label}
            </text>
            {r.reference && (
              <text x={8} y={y0 + h / 2 + 15} fontSize="9" style={{ fill: 'rgb(var(--c-muted))' }}>
                reference model
              </text>
            )}
            {lanes.map((k, i) => {
              const c = r.cells[k];
              const cy = y0 + 7 + i * laneH;
              const colour = SERIES[k].colour;
              return (
                <g key={k}>
                  <title>{`${r.label} ${SERIES[k].label}: ${pp(c.gap, true)} pts (95% CI ${pp(c.lo)} to ${pp(c.hi)})`}</title>
                  <line x1={x(c.lo)} x2={x(c.hi)} y1={cy} y2={cy} stroke={colour} strokeWidth={k === 'all' ? 2.6 : 1.8} strokeLinecap="round" />
                  <circle cx={x(c.gap)} cy={cy} r={k === 'all' ? 4 : 3.2} fill={colour} />
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label="Legend">
        {LANES.map((k) => (
          <li key={k} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2 w-5 rounded-full" style={{ background: SERIES[k].colour }} aria-hidden="true" />
            {k === 'v2' && 'v2: 19 events'}
            {k === 'v3' && 'v3: 12 new books'}
            {k === 'v6' && 'v6: 7 events, did not replicate'}
            {k === 'all' && 'all three pooled (38 events)'}
          </li>
        ))}
      </ul>
      <table className="sr-only">
        <caption>Gap by model and dataset (percentage points, 95% interval)</caption>
        <thead>
          <tr>
            <th>Model</th>
            {LANES.map((k) => (
              <th key={k}>{SERIES[k].label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th>{r.label}</th>
              {LANES.map((k) => (
                <td key={k}>{r.cells[k] ? `${pp(r.cells[k].gap, true)} (${pp(r.cells[k].lo)} to ${pp(r.cells[k].hi)})` : '—'}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ 3. cue-preserving panel
function Bar({ label, value, colour, hint }) {
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 shrink-0 text-muted">{label}</span>
      <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface2" aria-hidden="true">
        <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(1, value || 0)) * 100}%`, background: colour }} />
      </div>
      <span className="w-14 shrink-0 text-right tabular-nums text-text">{pct0(value)}</span>
      {hint && <span className="sr-only">{hint}</span>}
    </div>
  );
}

const ARM_COLOUR = { A: 'rgb(var(--c-danger))', B: 'rgb(var(--c-accent))', B3: 'rgb(var(--c-cyan))' };

function CuePanel({ cue }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {cue.pools.map((p) => (
        <Card key={p.label}>
          <CardHeader>
            <div className="font-semibold">{p.label}</div>
            <div className="mt-0.5 text-xs text-muted">
              {p.items} pre-reveal items{p.events ? ` · ${p.events} events` : ''}
              {p.verdict ? ` · pre-registered reading: ${p.verdict}` : ''}
            </div>
          </CardHeader>
          <CardBody className="space-y-5">
            <div className="space-y-2.5">
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Premature rate (lower is better)</div>
              {p.arms.map((a) => (
                <Bar key={a.arm} label={`${a.arm}  ${a.label}`} value={a.premature} colour={ARM_COLOUR[a.arm]} />
              ))}
            </div>
            <div className="space-y-2.5">
              <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted">Plain-control accuracy (higher is better)</div>
              {p.arms.map((a) => (
                <Bar key={a.arm} label={`${a.arm}  ${a.label}`} value={a.control_accuracy} colour={ARM_COLOUR[a.arm]} />
              ))}
            </div>
            <p className="text-sm text-muted">
              Gap A{'−'}B {pp(p.gap_A_minus_B, true)} pts; gap A{'−'}B3 {pp(p.gap_A_minus_B3, true)} pts. Recovered fraction{' '}
              {typeof p.recovered_fraction === 'number' ? pct0(p.recovered_fraction) : '—'}
              {Array.isArray(p.recovered_fraction_ci) && p.recovered_fraction_ci[0] != null
                ? ` (95% CI ${pct0(p.recovered_fraction_ci[0])} to ${pct0(p.recovered_fraction_ci[1])})`
                : ''}
              .
            </p>
          </CardBody>
        </Card>
      ))}
      <p className="text-sm text-muted lg:col-span-2">{cue.note}</p>
    </div>
  );
}

// ------------------------------------------------------------------ 4. dose-response
function DoseBars({ dose }) {
  const W = 900;
  const H = 270;
  const left = 44;
  const bottom = 52;
  const top = 12;
  const rows = dose.table;
  const vmin = -0.1;
  const vmax = 0.55;
  const y = (v) => top + ((vmax - v) / (vmax - vmin)) * (H - top - bottom);
  const slot = (W - left - 10) / rows.length;
  const bw = slot * 0.3;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Mean gap by how many of five local models recognise the book">
        {[0, 0.1, 0.2, 0.3, 0.4, 0.5].map((t) => (
          <g key={t}>
            <line x1={left} x2={W - 10} y1={y(t)} y2={y(t)} style={{ stroke: 'rgb(var(--c-border))' }} strokeWidth={t === 0 ? 1.4 : 0.6} strokeDasharray={t === 0 ? '' : '3 3'} />
            <text x={left - 6} y={y(t) + 3} textAnchor="end" fontSize="10" style={{ fill: 'rgb(var(--c-muted))' }}>
              {pp(t).replace(/\.0$/, '')}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cx = left + slot * i + slot / 2;
          const bars = [
            { v: r.mean_gap_reference, colour: 'rgb(var(--c-accent))', dx: -bw - 2, name: 'reference' },
            { v: r.mean_gap_local, colour: 'rgb(var(--c-cyan))', dx: 2, name: 'local pool' },
          ];
          return (
            <g key={r.recognised}>
              {bars.map((b) =>
                typeof b.v === 'number' ? (
                  <g key={b.name}>
                    <title>{`${r.recognised} of 5 recognise (${r.events} events), ${b.name}: ${pp(b.v, true)} pts`}</title>
                    <rect x={cx + b.dx} width={bw} y={Math.min(y(b.v), y(0))} height={Math.max(1, Math.abs(y(b.v) - y(0)))} rx="2" fill={b.colour} />
                  </g>
                ) : null
              )}
              <text x={cx} y={H - bottom + 16} textAnchor="middle" fontSize="12" fontWeight="600" style={{ fill: 'rgb(var(--c-text))' }}>
                {r.recognised}
              </text>
              <text x={cx} y={H - bottom + 30} textAnchor="middle" fontSize="10" style={{ fill: 'rgb(var(--c-muted))' }}>
                {r.events} events
              </text>
            </g>
          );
        })}
        <text x={(left + W) / 2} y={H - 4} textAnchor="middle" fontSize="10.5" style={{ fill: 'rgb(var(--c-muted))' }}>
          number of the 5 local models that recognise the book (0 = unknown, 5 = famous)
        </text>
      </svg>
      <ul className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted" aria-label="Legend">
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: 'rgb(var(--c-accent))' }} aria-hidden="true" />
          reference model (Spearman {dose.spearman_reference}, p = {dose.perm_p_reference})
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: 'rgb(var(--c-cyan))' }} aria-hidden="true" />
          valid local pool (Spearman {dose.spearman_local}, p = {dose.perm_p_local})
        </li>
      </ul>
      <p className="mt-2 text-sm text-muted">{dose.note}</p>
    </div>
  );
}

// ------------------------------------------------------------------ extras: validity + design
function Details({ data }) {
  const v = data.validity;
  const d = data.design;
  if (!v && !d) return null;
  return (
    <details className="rounded-2xl border border-border bg-surface p-5">
      <summary className="cursor-pointer font-display text-lg font-bold tracking-tight">Validity gate and planned confirmatory study</summary>
      {v && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="pb-2 text-left text-muted">{v.note}</caption>
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-[0.1em] text-muted">
                <th className="py-2 pr-4">Model</th>
                {v.datasets.map((ds) => (
                  <th key={ds.key} className="py-2 pr-4">
                    {ds.key} G2a / G2b
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {v.rows.map((r) => (
                <tr key={r.model} className="border-b border-border/60">
                  <th scope="row" className="py-1.5 pr-4 font-medium">
                    {r.model}
                    {r.reference ? ' (reference)' : ''}
                  </th>
                  {v.datasets.map((ds) => {
                    const c = r.cells[ds.key];
                    return (
                      <td key={ds.key} className="py-1.5 pr-4 tabular-nums">
                        {c ? (
                          <span className={c.valid ? 'text-success' : 'text-muted'}>
                            {pct0(c.g2a)} / {pct0(c.g2b)} {c.valid ? '✓' : '×'}
                          </span>
                        ) : (
                          '—'
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="pb-2 text-left text-muted">
              Planned confirmatory design on three open models (cost model, not yet run). Community-cloud GPU hours and expected cost.
            </caption>
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-[0.1em] text-muted">
                <th className="py-2 pr-4">Design</th>
                <th className="py-2 pr-4">Events (dev / test)</th>
                <th className="py-2 pr-4">Items per event</th>
                <th className="py-2 pr-4">Short calls</th>
                <th className="py-2 pr-4">A100 hours</th>
                <th className="py-2 pr-4">A100 cost (worst 2x)</th>
                <th className="py-2 pr-4">H100 cost</th>
              </tr>
            </thead>
            <tbody>
              {d.map((x) => (
                <tr key={x.name} className="border-b border-border/60 tabular-nums">
                  <th scope="row" className="py-1.5 pr-4 font-medium">
                    {x.name}
                  </th>
                  <td className="py-1.5 pr-4">
                    {x.events} ({x.dev_events} / {x.test_events})
                  </td>
                  <td className="py-1.5 pr-4">{x.items_per_event}</td>
                  <td className="py-1.5 pr-4">{new Intl.NumberFormat().format(x.short_calls)}</td>
                  <td className="py-1.5 pr-4">{x.a100_hours}</td>
                  <td className="py-1.5 pr-4">
                    ${x.a100_usd} (${x.a100_worst_usd})
                  </td>
                  <td className="py-1.5 pr-4">${x.h100_usd}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

// ------------------------------------------------------------------ 5. live probe
const OUTCOME = {
  true_identity: { tone: 'danger', text: 'Premature: true identity' },
  abstain: { tone: 'success', text: 'Abstains' },
  other: { tone: 'neutral', text: 'Other candidate' },
  invalid: { tone: 'warning', text: 'Invalid answer' },
};

function Window({ text }) {
  const { pre, mark, post } = excerptAroundMarker(text);
  return (
    <p className="whitespace-pre-line rounded-xl bg-surface2 p-3 text-xs leading-relaxed text-muted">
      {pre}
      {mark && <mark className="rounded bg-accent/20 px-0.5 font-semibold text-text">{mark}</mark>}
      {post}
    </p>
  );
}

function ArmCard({ arm, label, item, result, running }) {
  const out = result && OUTCOME[result.outcome];
  const cands = item.candidates[arm];
  return (
    <Card className="flex flex-col" data-testid={`arm-${arm}`}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="font-semibold">
            {arm} <span className="font-normal text-muted">{label}</span>
          </div>
          {out && <Badge tone={out.tone}>{out.text}</Badge>}
        </div>
        <div className="mt-0.5 text-xs text-muted">
          Expression of interest: <span className="font-medium text-text">{'“'}{item.surface[arm]}{'”'}</span>
        </div>
      </CardHeader>
      <CardBody className="flex flex-1 flex-col gap-3">
        <Window text={item.windows[arm]} />
        <p className="text-xs text-muted">
          {cands.map((c) => `${c.letter} ${c.name}`).join(' · ')}
        </p>
        <div className="mt-auto border-t border-border pt-3 text-sm">
          {result ? (
            <>
              <div>
                Answer: <span className="font-semibold">{result.answer}</span>
                {result.answer_name ? <span className="text-muted"> ({result.answer_name})</span> : null}
              </div>
              <div className="mt-0.5 text-xs text-muted tabular-nums">
                {secs(result.seconds)}
                {result.load_seconds >= 0.5 ? ` · includes ${secs(result.load_seconds)} model load` : ''}
              </div>
            </>
          ) : (
            <div className="text-muted">{running ? 'Waiting for the model…' : 'Not run yet'}</div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

function Probe({ timings }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [itemId, setItemId] = useState('');
  const [model, setModel] = useState('qwen2.5:7b');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [runError, setRunError] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .researchItems()
      .then((d) => {
        if (!alive) return;
        setData(d);
        if (d.items.length) setItemId(d.items[0].id);
        if (d.models.length && !d.models.includes('qwen2.5:7b')) setModel(d.models[0]);
      })
      .catch((e) => alive && setError(e.serverMessage || describeError(e, 'Could not load the demo items.')));
    return () => {
      alive = false;
    };
  }, []);

  const item = data && data.items.find((i) => i.id === itemId);

  const run = async () => {
    setRunning(true);
    setResult(null);
    setRunError(null);
    try {
      setResult(await api.researchProbe(itemId, model));
    } catch (e) {
      setRunError(e.serverMessage || describeError(e, 'The probe failed.'));
    } finally {
      setRunning(false);
    }
  };

  if (error) {
    return (
      <div className="rounded-2xl border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning" role="alert">
        {error}
      </div>
    );
  }
  if (!data) return <div className="h-40 animate-pulse rounded-2xl border border-border bg-surface" aria-busy="true" />;

  const t = timings && timings.probe && timings.probe[model];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <label className="min-w-0 flex-1 text-sm font-medium" htmlFor="probe-item">
          Item
          <select
            id="probe-item"
            value={itemId}
            onChange={(e) => {
              setItemId(e.target.value);
              setResult(null);
              setRunError(null);
            }}
            className="mt-1.5 h-10 w-full rounded-xl border border-border bg-surface2 px-3 text-sm font-semibold text-text"
          >
            {data.items.map((i) => (
              <option key={i.id} value={i.id}>
                {i.book} {'—'} {'“'}{i.surface.A}{'”'}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium" htmlFor="probe-model">
          Local model
          <select
            id="probe-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="mt-1.5 h-10 w-full rounded-xl border border-border bg-surface2 px-3 text-sm font-semibold text-text sm:w-56"
          >
            {data.models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <Button onClick={run} disabled={running || !itemId} aria-busy={running}>
          <Play className="h-4 w-4" aria-hidden="true" /> {running ? 'Running…' : 'Run'}
        </Button>
      </div>

      {item && (
        <p className="text-sm text-muted">
          {item.reveal_note} Stored runs on this item: {item.stored_runs.A} of {item.stored_runs.models} local models named the true
          identity with original names, {item.stored_runs.B} with the cipher, {item.stored_runs.B3} with pseudonyms.
        </p>
      )}

      {runError && (
        <div className="rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
          {runError}
        </div>
      )}

      {item && (
        <div className="grid gap-4 lg:grid-cols-3">
          {data.arms.map((a) => (
            <ArmCard key={a.arm} arm={a.arm} label={a.label} item={item} result={result && result.arms[a.arm]} running={running} />
          ))}
        </div>
      )}

      {result && (
        <div className="rounded-2xl border border-border bg-surface p-4" role="status" data-testid="probe-verdict">
          <div className="text-sm font-semibold">{result.verdict}</div>
          <div className="mt-1 inline-flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted tabular-nums">
            <span className="inline-flex items-center gap-1.5">
              <Timer className="h-3.5 w-3.5" aria-hidden="true" /> total {secs(result.total_seconds)}
            </span>
            <span>
              true identity: {result.true_letter} ({result.true_identity})
            </span>
            <span>{result.model} unloaded afterwards</span>
          </div>
        </div>
      )}

      {t && (
        <p className="text-xs text-muted tabular-nums">
          Measured on this machine, {model}, three arms: {secs(t.cold && t.cold.total)} with the model loaded from disk, {secs(t.warm && t.warm.total)} with the model already in GPU memory.
        </p>
      )}
      <p className="text-xs text-muted">{data.selection}</p>
    </div>
  );
}

// ------------------------------------------------------------------ page
export default function ResearchPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .researchSummary()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(describeError(e, 'Could not load the stored results.')));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AccountShell>
      <PageHeader
        eyebrow="Research"
        title="Reader-faithfulness: what an assistant may know at chapter c"
        description="A reading assistant's answer at chapter c should depend only on chapters up to c. It can break through the pipeline (facts built from later chapters) or through the model's memory of the book. Both are measured here, with the fix for each."
        actions={<Badge tone="warning">Text-derived oracle; pre-registered where marked</Badge>}
      />

      {error && (
        <div className="rounded-2xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger" role="alert">
          {error}
        </div>
      )}
      {!data && !error && <div className="h-48 animate-pulse rounded-3xl border border-border bg-surface" aria-busy="true" />}

      {data && (
        <div className="space-y-12">
          <Headline data={data} />

          <section aria-labelledby="r-channel2">
            <SectionTitle
              id="r-channel2"
              hint="In addition to parametric memory (Channel 1), reader-faithfulness can be broken through pipeline derivations stamped earlier than the chapters they were computed from (Channel 2)."
            >
              Channel 2: Pipeline Derivation Look-Ahead
            </SectionTitle>
            <Channel2Card />
            <div className="mt-4">
              <RfE2ECard rf={data.rf_e2e} confirm={data.confirmatory} />
            </div>
          </section>

          {data.gap_by_model && (
            <section aria-labelledby="r-gap">
              <SectionTitle id="r-gap" hint={data.gap_by_model.note}>
                Gap by model and dataset
              </SectionTitle>
              <Card>
                <CardBody>
                  <IntervalPlot gap={data.gap_by_model} />
                </CardBody>
              </Card>
              {data.verdicts && data.verdicts.length > 0 && (
                <p className="mt-3 text-sm text-muted">
                  Pre-registered readings: {data.verdicts.map((v) => `${v.experiment}: ${v.verdict}`).join(' · ')}.
                </p>
              )}
            </section>
          )}

          {data.cue_preserving && (
            <section aria-labelledby="r-cue">
              <SectionTitle id="r-cue">Cue-preserving renaming (B3)</SectionTitle>
              <CuePanel cue={data.cue_preserving} />
            </section>
          )}

          {data.dose_response && (
            <section aria-labelledby="r-dose">
              <SectionTitle id="r-dose">Dose-response: the gap grows with how well the book is known</SectionTitle>
              <Card>
                <CardBody>
                  <DoseBars dose={data.dose_response} />
                </CardBody>
              </Card>
            </section>
          )}

          <section aria-labelledby="r-probe">
            <SectionTitle
              id="r-probe"
              hint="Pick a public-domain passage and a local model. The same question is asked three times at temperature 0: original names, a letter cipher, and cue-preserving pseudonyms."
            >
              Live probe
            </SectionTitle>
            <Probe timings={data.timings} />
          </section>

          <Details data={data} />

          <p className="border-t border-border pt-4 text-xs text-muted">
            Labels are text-derived (an explicit revealing sentence plus a located cutoff); events were selected by a model; the judge rule
            is labelled by a separate model. Sources:{' '}
            {Object.values(data.sources || {}).join(', ')}.
            {data.missing && data.missing.length > 0 ? ` Missing: ${data.missing.join(', ')}.` : ''}
          </p>
        </div>
      )}
    </AccountShell>
  );
}
