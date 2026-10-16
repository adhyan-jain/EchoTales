# Integration Register notes, family F6: information-flow control (IFC) for LLM context (2026-10-15)

Scope rule: only "what enters each LLM prompt, with provenance and labels, and blocking disallowed flows" is in scope. General agent security
(prompt-injection defence, tool-call authorisation, exfiltration through egress tools) is OUT-OF-FIELD for EchoTales and is named as such below.
Track S (product-leaning): merging any of this is ENGINEERING and carries no paper novelty unless stated.
Method: PDFs fetched from arxiv.org/pdf/<id> into a scratch dir, `pdftotext -layout` only, nothing executed. Licences quoted from the GitHub API
`license` field (repo metadata, not a LICENSE file read). Tags: [PUB] method and experiment sections read in the paper text; [LEAD] snippet or abstract only.

## 0. What EchoTales already does (do not reinvent)

- `core/state.py::_visible_to_observer` is a per-fact visibility test on a (learned_at_pos, observer, retracted_at, truth_status) label: a fact is
  visible iff `learned_at_pos <= knowledge_pos` (or the observer's own `witnessed_at` for a character observer), not retracted before that position,
  and not FALSE. `observer_scope` gives characters no inheritance of reader knowledge. This IS a position/observer label check, at the graph read.
- `core/state.py::GenerationState` carries `allowed_facts`, `forbidden_facts`, `provenance_refs` (audit, not hashed) and `read_set` (hashed into the
  cache key). `core/readset.py::ReadSetRecorder`/`fact_ref` give stable string refs per fact.
- `core/disclosure.py::compile_minimal_disclosure` only NARROWS the `state_of` candidate set per `TaskSpec`; its stated invariant (tested in
  `core/tests/test_disclosure.py`) is `allowed_facts` is a subset of what `compile_generation_state` yields. Its only non-test caller is the
  experiment-only `render/plan_builder.py` (`use_mdc=True`).
- `core/readset.py::EpistemicLeakageValidator.validate(gen_state, text)` is a post-hoc casefold-substring scan of finished prompt text for
  `forbidden_facts`. Tested in `core/tests/test_state.py::TestGenerationStateAndValidator`. grep over `packages/` finds NO production caller.
- `pipeline/world/context.py::story_context` (director brief) filters `_facts_as_of` by chapter number only: `attr.learned_at_pos.chapter > chapter`.
  It does not go through `state_of`, so it has no observer axis, no retraction handling, no truth_status test (also CHIMERA_COMPONENT_MATRIX s.8).
- `conditioned_on` is a free `list[str]` on `PanelImage` (`render/panels.py:1027`), set from a pre-selection `conditioned` list while
  `engine.generate` runs with `reference_images=[]` (`panels.py:2808-2864`); CHIMERA_DEFECT_BACKLOG B3 records it still over-claims.

What an IFC-style check ADDS: (a) a label on every item at the point it is placed into a prompt, not only at graph read; (b) a refusal at the
prompt-builder boundary, so the guarantee covers paths that bypass `state_of` (story_context, wiki canon, free-text director context); (c) an
auditable invariant per generated artifact: "no context item with learned_at > position, or observer not in scope, was placed in this prompt", plus
a `conditioned_on` that is derived from the labelled items actually serialised, not asserted by the caller.
What it does NOT add: a defence against parametric leakage (the model remembering the novel); no label can stop that (see NOVELTY_REPORT prior-art A).

## Donor 1: FIDES, "Securing AI Agents with Information-Flow Control"

- **Source**: Costa, Koepf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Beguelin (Microsoft). arXiv:2505.23643v2 [cs.CR], 3 Sep 2025
  (v1 29 May 2025). Brief's lead confirmed. No venue found. [PUB]
- **What it contributes** (s.4.1-4.3, s.5, s.7-8): labels from a lattice (confidentiality as authorised-reader sets, integrity trusted/untrusted;
  join = least upper bound) attached to every node of a tool result and to every message. Planning loop (Alg. 5-6) propagates labels
  conservatively: a model response gets the join of all labels in its context ("signifying the inability to precisely propagate labels through
  LLMs"). Policy check before a tool call: label of tool and each argument must be at or below a static policy label. s.5.1 `HIDE` swaps any node
  whose label exceeds the current context label for an opaque variable, so the prompt's label does not rise. s.8 on AgentDojo (949 attacks, gpt-4o):
  successful injections Basic 163 (156), FIDES 24 (23), FIDES with policy 1 (0); Task Completion Rate reported as "modest loss".
- **Artifact and licence**: github.com/microsoft/fides (tutorial per abstract); GitHub API: "MIT License", spdx MIT, last push 2025-05-30. Paper's
  eval code release UNVERIFIED (only the tutorial is claimed).
- **EchoTales component**: none today. Idea would land as a thin wrapper in the prompt-assembly path of `render/panels.py` (director call near
  `story_context`, `panels.py:2370`) and `world/context.py::StoryContext` items; label type reuses `fact_ref` + `DiscoursePosition`.
- **Product value**: low-moderate. The reusable part is the shape: label every context node, `HIDE` (drop and keep a reference) when the label exceeds
  the context level, and a pre-call policy `label <= bound`. EchoTales' lattice would be a total order on `DiscoursePosition` times observer scope,
  which is far simpler than FIDES' product lattice.
- **Paper value**: none for novelty (IFC labels on context are the donor's idea; position-as-label is a trivial instance). Possible ablation baseline:
  "conservative join" label propagation vs per-item label, relevant to the `conditioned_on` over-approximation.
- **Integration form**: baseline-only for the library; the idea itself becomes an isolated adapter (a `PromptItem(label, text)` builder). No dependency.
- **Cost**: reading cost only for the donor; adapter ~1-2 days with tests, no GPU, no API spend.
- **Evidence needed and available**: need a fixture graph with facts at chapters 3/9/20 and a position of 9; available in `core/tests` helpers
  (`make_self`, `bind_alias`). No EchoTales-side measurement needed to adopt the idea; none exists of leak rate through `story_context`.
- **Limits**: stated: policies enforced on tool calls only, so text-to-text attacks pass (s.8.1); labels must be supplied by trusted wrappers
  ("security guarantees ... only as good as the labels"); implicit flows not prevented. Found: the guarantee is about the labelled channel; it says
  nothing about what the model memorised, which is EchoTales' main leak (see prior-art A). Tool-call, egress and prompt-injection parts are OUT-OF-FIELD.
- **Decision**: baseline-only (the code); adapt the idea (see summary item 3). Not "adopt" because nothing is imported.
- **Test that would justify it**: on a fixture graph, assert for N random (position, observer) pairs that every item in the serialised director
  brief satisfies `label <= (position, observer)`, and that a deliberately planted chapter-20 fact is refused at position 9.

## Donor 2: Permissive Information-Flow Analysis for Large Language Models

- **Source**: Siddiqui, Gaonkar, Koepf, Krueger, Paverd, Salem, Tople, Wutschitz, Xia, Zanella-Beguelin. arXiv:2410.03055v3 [cs.LG], 14 Jan 2026;
  TMLR 10/2025. Not in the brief; found via FIDES s.9 (ref [29]). [PUB]
- **What it contributes** (s.2.2, s.3.1-3.2, Alg. 1, s.4-6): naive taint takes the join of all context labels as the output label. They instead
  search for the least-restrictive label L' whose sub-context `C|L'` yields an output with utility (negative perplexity) within lambda of the
  full-context output (Definition 1, "lambda-similar"), via a DAG search over labels below the full-context label; two propagators
  (prompt-based retrieval augmentation, kNN-LM) vs an introspection baseline. Results: more permissive label than baseline in >85% of cases
  (synthetic key-value and news-article datasets, s.5). Cost: extra LLM calls (s.3.5, s.6.2).
- **Artifact and licence**: no code link found in the paper text (keyword sweep for github/licen returns only LangChain). UNVERIFIED.
- **EchoTales component**: `render/panels.py` `conditioned_on` / `PanelImage`, `GenerationState.read_set` vs `provenance_refs`. The defect B3
  (provenance lists items that did not condition the generation) is the same over-approximation problem, in the opposite direction: here the
  list is too LARGE because it joins everything in scope, not because the model used it.
- **Product value**: low. Needs repeated LLM calls per panel to find the minimal sub-context; EchoTales' cheaper route is deterministic: provenance
  = exactly the items serialised into the prompt (what `compile_minimal_disclosure` already narrows to).
- **Paper value**: closest conceptual cousin of "minimal sufficient evidence"; relevant to the disclosure-minimisation claim as RELATED WORK, and its
  lambda-similar test is a possible ablation (does dropping an item change the output?). Not novel for EchoTales to adopt.
- **Integration form**: baseline-only (cited, not run).
- **Cost**: re-implementation ~1 week plus many LLM calls; not justified.
- **Evidence needed and available**: would need a utility metric for panels/director output; none defined. Unavailable.
- **Limits**: stated: more LLM calls; adversary can add distractors so the label never improves (s.6.2). Found: utility is perplexity of a fixed
  reference completion, which does not transfer to image prompts.
- **Decision**: baseline-only (cite as related work for `conditioned_on` semantics).
- **Test**: none to run; the deterministic alternative is tested under Donor 1.

## Donor 3: CaMeL, "Defeating Prompt Injections by Design"

- **Source**: Debenedetti, Shumailov, Fan, Hayes, Carlini, Fabian, Kern, Shi, Terzis, Tramer (Google, DeepMind, ETH). arXiv:2503.18813v2 [cs.CR],
  24 Jun 2025. Brief's lead confirmed. [PUB]
- **What it contributes** (s.3.1, s.5.2-5.4, s.6, s.7): a Privileged LLM writes restricted Python from the trusted query; a custom interpreter
  runs it, a Quarantined LLM parses untrusted data. Each value carries a capability tag (provenance: User, CaMeL, or a tool plus inner source; set of
  allowed readers). The interpreter keeps a dependency graph per variable (STRICT mode adds control-flow dependencies) and checks Python-function
  policies (Allowed/Denied with reason, Fig. 6) before each tool call. s.6: 77% of AgentDojo tasks solved with provable security vs 84% undefended.
  s.7 documents side channels (exceptions, timing, external resource).
- **Artifact and licence**: github.com/google-research/camel-prompt-injection; GitHub API: "Apache License 2.0", spdx Apache-2.0, last push 2025-06-20.
- **EchoTales component**: none; the transferable idea is per-value provenance tags plus a recorded dependency graph, i.e. what
  `ReadSetRecorder`/`fact_ref` already are for graph facts, and the "origin of displayed content can be traced" property (s.3.1 non-goals).
- **Product value**: low. The interpreter architecture (code-writing planner) is a different system; EchoTales' prompt assembly is deterministic
  code already, so the dual-LLM split buys nothing.
- **Paper value**: none for novelty. Ablation baseline: no.
- **Integration form**: reject as a dependency; cite for the capability/provenance vocabulary.
- **Cost**: adopting the interpreter is weeks and a redesign of render; not warranted.
- **Evidence needed and available**: n/a.
- **Limits**: stated: text-to-text attacks that do not change data flow are out of scope; "Data requires action" failure (s.6.1.2) where the planner
  cannot read data it must act on; side channels (s.7). Found: security is defined per tool call, not per prompt content.
- **Decision**: reject (as code); the provenance-tag idea is already covered by Donor 1's adapter. Prompt-injection and exfiltration defence is OUT-OF-FIELD.
- **Test**: none.

## Donor 4: RTBAS, "Defending LLM Agents Against Prompt Injection and Privacy Leakage"

- **Source**: Zhong, Chen, Wang, McCall, Titzer, Miller, Gibbons (CMU, Two Sigma). arXiv:2502.08966v2 [cs.CR], 14 Feb 2025. Not in the brief; named in
  FIDES s.9. [PUB for s.7-8 sections read; the lattice/proof parts skimmed]
- **What it contributes** (s.7, s.8): regions of the history carry integrity and confidentiality labels; a "dependency screener" decides which
  regions the next output depends on, so only those labels propagate (and unused regions are redacted). Two screeners: LM-as-judge on
  `<REGION_N>` markers, and an attention-feature LSTM (85% train, 81% test on 40 AgentDojo cases, Phi-3-Mini). Baselines Naive Tainting, Redact All,
  Tool Filter. Results (GPT-4o, AgentDojo, 629 security cases): blocks all attacks violating the policy; <1% (LM-judge) and 3% (attention) utility
  loss under attack, 7.4-10% without attack; Slack suite utility falls to 22-33%.
- **Artifact and licence**: no repository found (GitHub search for "rtbas" returned unrelated repos; paper text has no code link). UNVERIFIED.
- **EchoTales component**: same as Donor 2 (`conditioned_on` over-approximation). The "redact unused regions" step corresponds to
  `compile_minimal_disclosure` dropping unneeded facts.
- **Product value**: low; a judge/attention screener per panel is costly and unneeded when the prompt text is built by deterministic code from known
  items.
- **Paper value**: related work only.
- **Integration form**: baseline-only (cited).
- **Cost**: high (extra model passes, a trained classifier); no.
- **Evidence needed and available**: none.
- **Limits**: stated: "security guarantees ... only as good as the labels provided and the policies enforced"; one workspace case missed because
  user text labelled trusted contained an injection. Found: the screener is itself a probabilistic component, so the guarantee becomes
  probabilistic wherever it is used to drop a label.
- **Decision**: baseline-only.
- **Test**: none.

## Donor 5: Progent, "Securing AI Agents with Privilege Control"

- **Source**: Shi, He, Wang, Li, Wu, Guo, Song (UC Berkeley and others). arXiv:2504.11703v3 [cs.CR], 14 May 2026. Brief's lead confirmed. [PUB for
  abstract, s.8.1, s.9; policy-language sections skimmed only]
- **What it contributes**: a symbolic allow/forbid policy over tool names and arguments, LLM-generated from the task and updated at runtime; an SMT
  solver classifies each update as narrowing (auto) or expansion (needs approval), giving monotonic confinement. AgentDojo ASR 39.9% -> 1.0% (gpt-4o).
- **Artifact and licence**: github.com/sunblaze-ucb/progent; GitHub API: "MIT License", last push 2026-09-24.
- **EchoTales component**: none. It controls which ACTIONS an agent may take, not what content enters a prompt; EchoTales has no tool-calling agent in
  the render path.
- **Product value**: none for this field. **Paper value**: none.
- **Integration form**: reject (OUT-OF-FIELD: general agent security / privilege control).
- **Cost**: n/a. **Evidence needed**: n/a.
- **Limits**: stated: does not address text-to-text attacks (s.9 "Defense Scope"); text only, no multimodal.
- **Decision**: reject, out-of-field. **Test**: none.

## Novelty threats (position / time visibility labels for narratives)

- No IFC paper read here labels context by story position or reader knowledge. FIDES/CaMeL use trust and reader-set lattices; Siddiqui et al. mention
  timestamps only as an example of an infinite lattice (s.3.2). A narrative-specific position-and-observer label check is not pre-empted by these donors.
- Adjacent, LEAD only (abstracts read on arxiv.org/abs, methods not read): TEMPO arXiv:2605.18843 (Zhang, Stadie, 13 May 2026) and TimeSPEC
  arXiv:2602.17234 (Zhang, Chen, Stadie, 19 Feb 2026) enforce a pre-cutoff evidence rule for LLM backtesting (temporally filtered retrieval plus
  claim-level supervision / trained temporal discipline). This is the nearest "position-based visibility" prior art, in forecasting, not narrative. A
  search snippet also reports date-filtered retrieval alone still leaks (El Lahib et al., ACL 2026; UNVERIFIED, not opened). Treat "time-cutoff
  evidence filtering for LLM prompts" as NOT novel in general; EchoTales' narrower claim (observer-conditioned bitemporal `state_of` with retraction
  and witnessed-at) is not shown by any of these.
- StoRM (Guiding Neural Story Generation with Reader Models, Findings EMNLP 2022) [LEAD, snippet]: models the reader's beliefs as a graph, for
  planning, not for blocking prompt content.

## Summary (10 lines)

1. Worth building: one `PromptItem(text, ref, learned_at_pos, observer_scope)` builder that REFUSES any item whose label exceeds `(position, observer)` and
   returns `conditioned_on` as the refs of items actually serialised. Engineering, not a contribution.
2. Invariant test: for any (position, observer), `max(item.learned_at_pos for item in prompt_items) <= knowledge_pos` and every item is in
   `state_of(...).allowed_facts`; plant a chapter-20 fact and assert refusal at position 9 on a fixture graph; assert `conditioned_on == serialised refs`.
3. Overlap: `_visible_to_observer`, `GenerationState.allowed/forbidden/read_set` and `compile_minimal_disclosure` already enforce the label rule AT GRAPH READ;
   the new part is enforcement at the prompt boundary.
4. Gap it closes: `world/context.py::story_context` filters by chapter number only (no observer, retraction or truth_status) and bypasses `state_of`.
5. `EpistemicLeakageValidator` is a substring post-check with no production caller in `packages/`; wiring it is cheaper than any donor.
6. `conditioned_on` defect (B3): FIDES-style conservative join over-approximates; Siddiqui et al. confirm the problem but fix it with extra LLM calls. Fix it
   deterministically instead.
7. Decisions: FIDES baseline-only (idea adapted); Siddiqui baseline-only; CaMeL reject (idea covered); RTBAS baseline-only; Progent reject, out-of-field.
8. No donor labels by story position or reader knowledge; nearest prior art is LEAD-only: TEMPO 2605.18843 and TimeSPEC 2602.17234 (forecasting cutoff).
9. Corrections to the brief: FIDES id and authors confirmed (v2, 3 Sep 2025, MIT); CaMeL and Progent exist (Apache-2.0, MIT); Siddiqui (2410.03055) and RTBAS
   (2502.08966) are the better-fitting additions, the latter two have no verified code.
10. No label stops parametric leakage (model memory of the novel); this family cannot support any claim about that.
