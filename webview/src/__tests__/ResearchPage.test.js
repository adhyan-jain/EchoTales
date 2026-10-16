import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

// The Research view must show the stored headline numbers, the probe must show the three arms with answers and
// timings, and a missing demo-items file must surface the server's actionable message rather than a generic one.
// CRA's jest config sets `resetMocks: true`, so implementations are set inside each test.
jest.mock('../api', () => ({
  api: {
    researchSummary: jest.fn(),
    researchItems: jest.fn(),
    researchProbe: jest.fn(),
  },
}));

// eslint-disable-next-line import/first
import { api } from '../api';
// eslint-disable-next-line import/first
import ResearchPage, { excerptAroundMarker, Channel2Card, RfE2ECard } from '../pages/ResearchPage';

const cell = (gap, lo, hi, events = 10) => ({ gap, lo, hi, events, items: null });
const RFRULE = (w, v) => ({ rule: 'Judge rule', events: 54, whole_renamed: w, versioned_renamed: v, input_channel: { gap: w - v, lo: 0.1, hi: 0.3 }, memory_channel: { gap: 0, lo: 0, hi: 0.03 }, supported: true });
const SUMMARY = {
  rf_e2e: { strata: [{ label: '7-8B local models', models: ['qwen2.5:7b'], rules: [RFRULE(0.222, 0.019)] }, { label: '24-32B open models', models: ['qwen32b'], rules: [RFRULE(0.231, 0.019)] }] },
  confirmatory: { events: 68, primary: 32, models: ['qwen32b'], pooled_gap: { gap: 0.0011, lo: -0.0497, hi: 0.0518 }, fame_contrast: { gap: 0.0759, lo: -0.014, hi: 0.1833 }, fame_p: 0.0595 },
  provenance: 'Text-derived oracle; model-selected events; no human labels.',
  headline: {
    reference_gap: cell(0.2596, 0.1678, 0.3604, 38),
    local_pool_gap: cell(0.1151, 0.0454, 0.1899, 38),
    cue_recovered: { fraction: -0.1078, lo: -0.3565, hi: 0.0606, events: 31, gap_A_minus_B: 0.1456, gap_A_minus_B3: 0.1613 },
  },
  gap_by_model: {
    datasets: [{ key: 'v2', label: 'v2' }],
    rows: [
      { model: 'gpt-5.6-luna', reference: true, cells: { v2: cell(0.35, 0.2, 0.5), v3: cell(0.18, 0.05, 0.34), v6: cell(0.17, 0.05, 0.29) } },
      { model: 'llama3.1:8b', reference: false, cells: { v2: cell(0.14, 0.03, 0.27), v6: cell(-0.16, -0.41, 0.04) } },
    ],
    pools: [
      { key: 'v2', kind: 'local_pool', ...cell(0.15, 0.06, 0.26) },
      { key: 'all_v2_v3_v6', kind: 'local_pool', ...cell(0.1151, 0.0454, 0.1899, 38) },
      { key: 'all_v2_v3_v6', kind: 'reference', ...cell(0.2596, 0.1678, 0.3604, 38) },
    ],
    note: 'Gap note.',
  },
  cue_preserving: {
    pools: [
      {
        label: 'Local models passing the validity gate (4)',
        models: ['llama3.1:8b'],
        items: 924,
        events: 31,
        arms: [
          { arm: 'A', label: 'original names', premature: 0.2284, control_accuracy: 0.96 },
          { arm: 'B', label: 'letter cipher', premature: 0.0828, control_accuracy: 0.9 },
          { arm: 'B3', label: 'cue-preserving pseudonyms', premature: 0.0671, control_accuracy: 0.95 },
        ],
        gap_A_minus_B: 0.1456,
        gap_A_minus_B3: 0.1612,
        recovered_fraction: -0.1078,
        recovered_fraction_ci: [-0.3565, 0.0606],
      },
    ],
    note: 'B3 note.',
  },
  dose_response: {
    table: [
      { recognised: 0, events: 10, mean_gap_reference: 0.0875, mean_gap_local: 0.0031 },
      { recognised: 5, events: 7, mean_gap_reference: 0.2946, mean_gap_local: 0.4085 },
    ],
    spearman_reference: 0.37,
    perm_p_reference: 0.024,
    spearman_local: 0.586,
    perm_p_local: 0.00015,
    note: 'Post hoc.',
  },
  validity: null,
  design: null,
  verdicts: [{ experiment: 'v6 (7 fresh events)', verdict: 'NOT SUPPORTED' }],
  timings: null,
  sources: { pooled: 'data/eval/chimera/pd_final_pooled.json' },
  missing: [],
};

const WINDOW = 'Long before the party began, a quiet man arrived. He said little. They called him [[Gatsby]] and wondered. More text follows here.';
const cands = (names) => names.map((n, i) => ({ letter: 'ABC'[i], name: n }));
const ITEMS = {
  selection: 'ILLUSTRATIVE selection note.',
  arms: [
    { arm: 'A', label: 'original names' },
    { arm: 'B', label: 'letter cipher' },
    { arm: 'B3', label: 'cue-preserving pseudonyms' },
  ],
  models: ['qwen2.5:7b', 'llama3.1:8b'],
  items: [
    {
      id: 'GG-pre073',
      book: 'The Great Gatsby',
      surface: { A: 'Gatsby', B: 'Fcbsxz', B3: 'Emmett' },
      windows: { A: WINDOW, B: WINDOW.replace('Gatsby', 'Fcbsxz'), B3: WINDOW.replace('Gatsby', 'Emmett') },
      candidates: { A: cands(['Daisy', 'Tom', 'James Gatz']), B: cands(['Ecisz', 'Bon', 'Dcnts Fcbg']), B3: cands(['Lindsay', 'Wilfred', 'Victor']) },
      true_letter: 'C',
      reveal_note: 'Fixed reveal: stated about 54% through the text.',
      stored_runs: { models: 5, A: 5, B: 1, B3: 0 },
    },
  ],
};
const PROBE = {
  item_id: 'GG-pre073',
  model: 'qwen2.5:7b',
  true_letter: 'C',
  true_identity: 'James Gatz',
  total_seconds: 7.5,
  verdict: 'Original names: answers the true identity before the book reveals it; Letter cipher: abstains; Cue-preserving pseudonyms: other',
  arms: {
    A: { arm: 'A', answer: 'C', answer_name: 'James Gatz', seconds: 4.2, load_seconds: 3.1, outcome: 'true_identity', is_true_identity: true },
    B: { arm: 'B', answer: 'UNDETERMINED', answer_name: null, seconds: 1.5, load_seconds: 0, outcome: 'abstain', is_true_identity: false },
    B3: { arm: 'B3', answer: 'A', answer_name: 'Lindsay', seconds: 1.8, load_seconds: 0, outcome: 'other', is_true_identity: false },
  },
};

function mount() {
  api.researchSummary.mockResolvedValue(SUMMARY);
  api.researchItems.mockResolvedValue(ITEMS);
  render(
    <MemoryRouter>
      <ResearchPage />
    </MemoryRouter>
  );
}

test('headline cards show the pipeline leak, the versioned card and the confirmatory memory gap, with the provenance note', async () => {
  mount();
  expect(await screen.findByText('22% / 23%')).toBeInTheDocument();
  expect(screen.getByText('2% / 2%')).toBeInTheDocument();
  expect(screen.getByText('+0.1 pts')).toBeInTheDocument();
  expect(screen.getAllByText(/events were selected by a model/i).length).toBeGreaterThan(0);
  expect(screen.getByRole('img', { name: /gap between original-name and renamed accuracy/i })).toBeInTheDocument();
  expect(screen.getByRole('img', { name: /mean gap by how many of five local models/i })).toBeInTheDocument();
});

test('the probe shows three arms, then answers, per-arm latency, total and the verdict after Run', async () => {
  mount();
  const arm = (k) => screen.findByTestId(`arm-${k}`);
  expect(await arm('A')).toBeInTheDocument();
  expect(within(await arm('B')).getByText('Not run yet')).toBeInTheDocument();
  api.researchProbe.mockResolvedValue(PROBE);

  userEvent.click(screen.getByRole('button', { name: /run/i }));

  await waitFor(() => expect(within(screen.getByTestId('arm-A')).getByText('Premature: true identity')).toBeInTheDocument());
  expect(api.researchProbe).toHaveBeenCalledWith('GG-pre073', 'qwen2.5:7b');
  expect(within(screen.getByTestId('arm-B')).getByText('Abstains')).toBeInTheDocument();
  expect(within(screen.getByTestId('arm-B3')).getByText('Other candidate')).toBeInTheDocument();
  expect(within(screen.getByTestId('arm-A')).getByText(/4\.2 s/)).toBeInTheDocument();
  const verdict = screen.getByTestId('probe-verdict');
  expect(verdict).toHaveTextContent(/answers the true identity before the book reveals it/);
  expect(verdict).toHaveTextContent('total 7.5 s');
});

test('a probe failure shows the server message', async () => {
  mount();
  await screen.findByTestId('arm-A');
  api.researchProbe.mockRejectedValue(Object.assign(new Error('x'), { status: 503, serverMessage: 'Ollama is not reachable at http://127.0.0.1:11434. Start it with `ollama serve` and retry.' }));
  userEvent.click(screen.getByRole('button', { name: /run/i }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/ollama serve/);
});

test('missing demo items surface the build command, not a generic error', async () => {
  api.researchSummary.mockResolvedValue(SUMMARY);
  api.researchItems.mockRejectedValue(
    Object.assign(new Error('x'), { status: 404, serverMessage: 'Demo items not found. Build them once with: python scripts/chimera/build_demo_items.py' })
  );
  render(
    <MemoryRouter>
      <ResearchPage />
    </MemoryRouter>
  );
  expect(await screen.findByText(/build_demo_items\.py/)).toBeInTheDocument();
});

test('excerptAroundMarker keeps the marked sentence area and trims the rest', () => {
  const long = `${'word '.repeat(200)}the [[mark]] is here${' tail'.repeat(100)}`;
  const e = excerptAroundMarker(long);
  expect(e.mark).toBe('mark');
  expect(e.pre.startsWith('…')).toBe(true);
  expect(e.pre.length).toBeLessThan(300);
  expect(e.post.length).toBeLessThan(120);
  expect(excerptAroundMarker('no marker here').mark).toBe('');
});

test('Channel 2 card displays prefix-faithfulness headline numbers from REPORT.md', async () => {
  mount();
  const card = await screen.findByTestId('channel-2-card');
  expect(card).toBeInTheDocument();
  expect(within(card).getByText(/Channel 2: Derivation Look-Ahead/i)).toBeInTheDocument();
  expect(within(card).getByText('6.0%')).toBeInTheDocument();
  expect(within(card).getByText('2.6%')).toBeInTheDocument();
  expect(within(card).getByText('0')).toBeInTheDocument();
  expect(within(card).getByText('97%')).toBeInTheDocument();
  expect(within(card).getByText(/41 of 685 cuts/i)).toBeInTheDocument();
  expect(within(card).getByText(/18 of 685 cuts/i)).toBeInTheDocument();
  expect(within(card).getByText(/Horizon-Versioned Repair/i)).toBeInTheDocument();
  expect(within(card).getByText(/claude\/prefix-faithfulness · REPORT\.md/i)).toBeInTheDocument();
});

test('Channel2Card renders standalone with read-only badge and headline metrics', () => {
  render(<Channel2Card />);
  expect(screen.getByTestId('channel-2-card')).toBeInTheDocument();
  expect(screen.getByText('Status Quo Divergence')).toBeInTheDocument();
  expect(screen.getByText('6.0%')).toBeInTheDocument();
  expect(screen.getByText('Premature Disclosures')).toBeInTheDocument();
  expect(screen.getByText('2.6%')).toBeInTheDocument();
  expect(screen.getByText('Horizon-Versioned Repair')).toBeInTheDocument();
  expect(screen.getByText('0')).toBeInTheDocument();
  expect(screen.getByText('Anchored Cue Recovery')).toBeInTheDocument();
  expect(screen.getByText('97%')).toBeInTheDocument();
});


test('RfE2ECard shows whole-book versus versioned leak per rule and renders nothing without data', () => {
  const rf = { strata: [{ label: '7-8B local models', models: ['qwen2.5:7b'], rules: [
    { rule: 'Judge rule', events: 54, whole_renamed: 0.222, versioned_renamed: 0.019, input_channel: { gap: 0.204, lo: 0.111, hi: 0.306 }, memory_channel: { gap: 0.009, lo: 0, hi: 0.028 }, supported: true },
  ] }] };
  const { container, unmount } = render(<RfE2ECard rf={rf} />);
  expect(screen.getByTestId('rf-e2e-card')).toBeInTheDocument();
  expect(screen.getByText('22%')).toBeInTheDocument();
  expect(screen.getByText(/supported/)).toBeInTheDocument();
  unmount();
  const empty = render(<RfE2ECard rf={null} />);
  expect(empty.container).toBeEmptyDOMElement();
  void container;
});
