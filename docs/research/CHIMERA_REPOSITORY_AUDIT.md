# CHIMERA repository audit (Checkpoint 1, Gate 1)

| Field | Value |
|---|---|
| Commit | `6c7e2c2`, branch `validation/evidence-pass-2026-09-24`, 2026-10-15 |
| Read | `docs/research/{README,DECISION_LOG,ECHOTALES_NOVELTY_LEDGER}.md`, `docs/results/{GOLD_DATASET_README,SCORER_DIAGNOSIS,EXTERNAL_BENCHMARK,FINAL_EVIDENCE_TABLE}.md`; code excerpts cited by file:line below |
| Ran | `git --no-optional-locks` read-only commands; test suites in a scratch copy (not the owner's tree); read-only SQLite queries on a scratch copy of the RI database; unauthenticated GitHub API reads |
| Delegated | Three read-only Explore subagents traced the code. Their reports are model output. Every claim I rely on below is either re-verified by me ([INSPECT], marked V in tables) or marked INFERRED / agent-reported |
| Not done | No file in the repo was modified. No commits. No GPU. No paid API. No pipeline run beyond pytest |

---

## 1. Initial state

| Item | Finding | Tag |
|---|---|---|
| Branch / HEAD | `validation/evidence-pass-2026-09-24` @ `6c7e2c2` | [INSPECT] |
| Untracked paths | 23 (matches directive). Preserved, untouched. | [INSPECT] |
| Remote | `origin git@github.com:adhyan-jain/EchoTales.git` | [INSPECT] |
| `.git/index.lock` | **Does not exist** as of this audit. The directive says a stale lock existed. Either it was removed or it never persisted. Nothing for the owner to delete. | [INSPECT] contradiction |
| Local vs public snapshot | 134 commits ahead of `6aed9f9` | [INSPECT] |
| **Public visibility** | **The GitHub repo is public** (`visibility: public`, unauthenticated API 200). Public `master` is still `6aed9f9` (2026-09-12), but **branch `validation/evidence-pass-2026-09-24` is also public at `6c7e2c2`** (pushed 2026-10-13). No licence file. | [INSPECT] |
| What the public branch exposes | Tracked and on that branch: `packages/ecrdt/IPR_REVIEW{,_FINAL,_V2,_V3,_V4}.md`; `docs/archive/STORYTRACE_TRANSFER.md`; `data/gold/*.jsonl` (each record has a `context` field of about 130 characters of source-novel text, so roughly 20k short excerpts of copyrighted novels are public); all of `docs/research/` as of `6c7e2c2`. `docs/private/` is gitignored and **not** tracked (0 files), which is correct. The three gold/IP file groups are also on public `master`. | [INSPECT] |
| Relevance | Conflicts with D2's default ("nothing is pushed or made public; an arXiv version waits") and with CLAUDE.md's rule that source novels are never committed (excerpt-level text is committed). **No action taken. The decision belongs to the owner.** | [INSPECT] + [INFER] |
| Host | 16 CPUs, 15 GB RAM (about 2 GB free), not the "2 CPU / 3 GB" sandbox the directive mentions | [INSPECT] |

### Tests (scratch copy, `ECHOTALES_LLM_MODE=stub`, core + pipeline suites)
- First run: 1,237 passed, 9 failed, 6 skipped (1,252 collected). All 9 failures were in the owner's untracked `test_adjudication_package.py`, caused by **gitignored inputs that `git archive` does not carry** (`data/eval/human_review_*.csv`, `data/db/reverend-insanity.db`). [INSPECT]
- After copying those inputs into the scratch copy, `test_adjudication_package.py` + `test_llm_annotate.py`: **25 passed**. [INSPECT] Caveat: the RI database was copied without its `-wal` file, so it may lag the owner's live copy.
- The docs claim 1,277 tests; I collected 1,252 in the same two suites. The 25-test difference is unexplained (research tests were not run). [INSPECT]; discrepancy unexplained.

---

## 2. Firewall (decision D1)

- **Where the rule is stated:** `docs/research/README.md:22` ("StoryTrace firewall (no narrative temporal/observer/identity/alias/consistency contribution)"); `ECHOTALES_SOURCE_INVENTORY.md:28` names commit `79e28b6` (2026-10-02) as its adoption; `ECHOTALES_NOVELTY_LEDGER.md` section A heading ("Inside 2026-10-02 Firewall"); and **`packages/research/src/echotales/research/hypotheses.toml`**, where every hypothesis carries a `firewall = "..."` rationale ("no narrative modelling", "not identity resolution") that `packages/research/tests/test_registry.py:24` **requires non-empty**. [INSPECT]
- **Not recorded:** `DECISION_LOG.md` contains no mention of the firewall, its rationale, or any lift (grep returned nothing). The rationale is unrecorded in the repo, as the directive says. [INSPECT]
- **Still stating the old rule after a lift:** the four places above. `hypotheses.toml` plus its test is code, not prose, and encodes the old scope per hypothesis.
- **Proposed wording for the owner to add to `DECISION_LOG.md`** (I have not edited it):

  > **2026-10-15 - Firewall re-scoped (owner decision D1).** The 2026-10-02 StoryTrace firewall, which barred any narrative temporal / observer / identity / alias / consistency contribution from the research track, is lifted for the purpose of *auditing and gate-testing* candidates on those topics (see `CHIMERA_NOVELTY_GATE.md`). It is **not** lifted for: (a) the separately scoped StoryTrace prototype and its code; (b) patent-candidate detail, which stays in the gitignored `docs/private/IP/` with only a pointer in tracked files; (c) any claim of novelty, validation or reproduction, which still requires the evidence gates. Rationale for the original firewall: *[owner to supply; not recorded in the repo]*. Re-scope rationale: *[owner to supply]*.

- Until the owner records it, identity / observer / time candidates are treated as allowed for audit and gate-testing only (D1 default).

---

## 3. Architecture (as traced)

```
EPUB -> ingest/ (chapters, blocks)         [no models; deterministic]
     -> spans/ (rule-based classify)       [recomputed per stage, not read back]
     -> mentions/ (gazetteer + qwen2.5:7b NER, commonness filter, alias_type)
     -> anaphora/ (local groups, kinship)  [pronoun links computed, not stored]
     -> resolve/ (retrieve -> evidence -> prefilter FORCE_LINK/BLOCK/SCORE -> gate)
           post-loop: link_title_holders, merge_transmigrations, retry_deferred
     -> CLI-only: detect_reveals, detect_observations; appearance_extract (LLM)
     -> persona/ (split bodies, wiki_canon overlay, canon, reference sheets)
     -> core/state.py::state_of()  (story time x disclosure time x observer)
              +-> compile_render_state -> render/panels.py (persona choice only)
     appearance_of / persona_at / story_context / wiki canon   (BYPASS state_of)
     -> render: reference_images=[]  -> NoobAI XL
     -> voice/ (whole-book traits, no state, no observer)
     -> video/ (joins manifests by chapter; no state)
     eval: scripts/eval/*  (silver gold only; LitBank is the sole human key)
```

---

## 4. The questions the directive asked first

### 4.1 Can the resolver run on a strict chapter prefix? **Not as a supported mode.**
- `resolve_novel(...)` takes no chapter-limit argument and iterates `store.iter_chapters(novel_id)` over every chapter (`resolve/runner.py:811-827, 890`). [agent-reported]
- `echotales resolve --chapters` is parsed (`cli.py:101`) but **silently ignored**: `cmd_resolve` calls `resolve_novel` without it (`commands.py:728-737`). [INSPECT: verified; `args.chapters` is used at lines 112, 686, 756, 957, 1005 but not in the resolve call]
- A prefix run works only if the database holds just the prefix. Re-ingesting a prefix over a full database does not delete later chapters (INFERRED: no delete in `ingest_config`).
- Stages **upstream** of the resolver use whole-volume information, so a prefix-bounded resolver on a full DB is still not causal: commonness profile from the whole corpus (`mentions/runner.py:330-332`, `mentions/commonness.py:102-127`) and a lexicon induced from 12 chapters spread over the book (`mentions/induce.py:130-143`). [agent-reported]
- No test asserts prefix invariance (resolving chapters 1..c alone equals the first c chapters of a full run). [agent grep]

### 4.2 Can a decision at chapter c see context from after c? **Yes, in deliberate post-hoc passes.**
There are **no 30-50 chapter LLM windows** for NER or alias resolution. `Settings.window_size = 40` governs only the contradiction-sweep / `retry_deferred` cadence and compounding-curve bucketing (`config.py:127-128`, `resolve/runner.py:919-921`). The "30-50 chapter window" wording at `mentions/gazetteer.py:3-4` is stale (the gazetteer rebuilds on staleness per chapter). NER chunks are 6,000 characters within one chapter (`mentions/ner.py:48-53`). So the directive's "30-50 chapter windows" premise is **not what the code does**. [agent-reported]

Real look-ahead, by severity:
1. `link_title_holders` (`resolve/title_holders.py:301`): volume-first by design; the first holder's tenure is forced to start at chapter 1 (`:287`, "retroactive") and earlier title mentions are linked backward. Cannot run causally.
2. `merge_transmigrations` (`resolve/transmigration.py:104-114`): post-loop, rewrites mention targets across all chapters.
3. `retry_deferred` re-scores against later profiles. **Verified: it never links.** On `Decision.LINK` it removes the case from the queue and increments counters; there is no `_apply_link` and no store write (`resolve/runner.py:646-682`). Any "recovered from deferral" figure counts queue removals, not links. [INSPECT]
4. `adjudicate_remaining` (whole-book profiles, outcome discarded) runs only if `use_llm and router`; `cmd_resolve` passes neither. Not reached from the CLI path. [INSPECT for commands.py]
5. Downstream: appearance and world-fact extraction send whole-run samples to the LLM and stamp each value at the earliest grounding chapter, so later evidence can shape an earlier-stamped fact (`resolve/appearance_extract.py:481-533, 781-811`). `world/extract.py::extract_world` has no non-test caller. [agent-reported]

### 4.3 Does wiki-derived appearance describe a later state than its stamp? **Yes, and it has no stamp.**
- The module docstring promises "Every imported trait is dated to the character's *first appearance* chapter" (`persona/wiki_canon.py:26-28`). Not implemented: it stores flat `{label: {trait: value}}` JSON with no chapter, position or interval; grep for `first_appear|chapter` in the file finds only docstrings and comments. [INSPECT]
- The repo records the damage itself: the wiki `typical_attire: "white robes"` was "sourced from deep in the story (the body-2 era)" and "silently beat extraction's correct answer on every pre-regression panel" (`persona/canon.py:49-60`). The fix was hand-authored per-body canon for one character (Fang Yuan). The wiki layer stays position- and body-blind for every other character. [INSPECT]
- `apply_canon` is called after `state_of` and outside the cache digest: `render/panels.py:1398`, `world/context.py:248`, `persona/reference_gen.py:670`. [INSPECT] Agent report: the digest excludes canon, so editing `wiki-appearance.json` changes prompts without changing `state_digest` (INFERRED consequence: stale cache).

---

## 5. Do all render paths consult the same narrative state? **No.**

| Path | Narrative-state input |
|---|---|
| Persona choice per beat | `state_of` at fractional position, with `--observer` (`render/plan_builder.py`, `panels.py:2086`) |
| Persona **attributes** drawn | `appearance_of(position)` filters only `interval.from_lb > position`; ignores observer, `learned_at_pos`, timeline, retraction (`persona/reference_gen.py:208`) |
| Director brief | `story_context`: filters on `learned_at_pos.chapter <= chapter` only; no observer; integer chapter (`world/context.py:128-149`) |
| Cast membership / reveals | chapter-exact event scan, no observer (`render/panels.py:1126-1159`) |
| Reference sheets | whole-novel `appearance_of` + wiki canon, chosen by `reference_path_for`, ignoring position and observer (`persona/reference_gen.py:657-665, 788-801`) |
| Audio | none: whole-book trait profiles, `position=None` (latest body), no observer. The code says so (`voice/runner.py:199-207`) |
| Video | joins panel and voice manifests by chapter; no state; no check they share an observer |
| Visual-memory prototype | explicit (position, cutoff, observer, policy) with lineage; **not wired** into `render_panels` |

(Agent-traced.) So `--observer X` scopes persona choice and the state object's aliases, but the drawn appearance, director brief and reference sheet stay reader-view. INFERRED from the table, not demonstrated by a run.

### Reference conditioning is off in production
`render/panels.py:2740-2741` builds `PanelImageRequest(..., reference_images=[], reference_weight=0.0)` [INSPECT]. The only generation call is `engine.generate(_panel_request)` (`:2850`, agent-reported). Reference-selection code above it still runs but its result never reaches the engine, yet `conditioned_on` metadata and `report.conditioned_panels` are still populated (agent-reported `:2128, :2864, :2854-2855`). **Consequence for the evidence record (INFERRED from the agent's reading, not re-run):** the headline "reference-conditioned: reader 5/5, non-reader 0/5" in `FINAL_EVIDENCE_TABLE.md` and `OBSERVER_CONTRAST_VALIDATION.md` counts a manifest tag, not pixel conditioning. That run (2026-09-25) is after IP-Adapter removal (2026-08-21, EVOLUTION 4.47), and no repo script produces the figure.

### Visual-memory selection is unreachable and not in the cache key
`build_render_plan(visual_registry=...)` would select references through `VisualMemorySelector`, but its only render caller passes none, and the chosen `reference_paths` is neither hashed by `plan_digest` nor copied into the request (agent-reported: `plan_builder.py:171-229`, `contract.py:~155-160`). The selector is exercised only by tests and the owner's synthetic probe harness, which labels it `unwired_component ... on synthetic lineage`.

---

## 6. Component forensic trace (15 components)

Agent-traced; items marked (V) I re-verified.

| # | Component | Key interfaces / callers | Kept / dropped | Model | Known bypass or defect | Determinism | Evaluation trust |
|---|---|---|---|---|---|---|---|
| 1 | Ingestion / normalisation | `ingest_novel` (`ingest/runner.py:46`); `cmd_run`, `cmd_ingest` | Block text, italics; chapter number float from TOC; other markup dropped | none | `--chapters` honoured here only; prefix ingest does not delete later chapters (INFERRED) | deterministic | Fine |
| 2 | Mention detection | `detect_mentions` (`mentions/runner.py:289`); gazetteer + qwen2.5:7b NER, temp 0 | Segment always `segments[0]`; fractional chapters collide | qwen2.5:7b (ollama) | Hard cases lost here (below) | roster-dependent; NER cache key omits roster | **Low for hard cases** |
| 3 | Aliases / resolution / coref | `resolve_novel`; scorer; prefilters; `anaphora/` | Segment, speaker, scene, mention offset dropped; context by first text match | none in default path | Scorer links nothing alone (bias -4.0, threshold 0.80, `score.py:47-80`); `temporal_certainty`, `concurrent_personas`, `speaker` never populated, so the temporal BLOCK never fires | deterministic | Silver only |
| 4 | Fact / event extraction | `detectors.py` regexes; `detect_reveals`, `detect_observations` (CLI-only); `appearance_extract` (LLM); `world/extract.py` (no non-test caller) | Detector events use chapter-first mention; raw string subject/object | LLM | Reveals/observations are not pipeline stages; detector output is not fed back to resolution | LLM nondeterminism | Low |
| 5 | Graph and store | `core/store.py` (SQLite) | `state_of` return type drops per-fact provenance | none | No retract for attributes or relations | deterministic | n/a |
| 6 | Story-time vs disclosure-time | `TemporalFact.interval`, `learned_at_pos`; `state_of` (`core/state.py:207-353`) | Axes real | none | Writers stamp `learned_at` from whole-book analysis (`persona/split.py:~855-866`); whole-novel trait profiles stamped at first attestation (`persona/build.py:~270-290`) | deterministic | Axes real, stamps partly non-causal |
| 7 | Character knowledge | `Observation` table, `observer_id` | Observations attach only to alias facts; almost all facts are `observer_id=READER` | none | Attribute-level observer divergence is never written | deterministic | Self-referential eval |
| 8 | Retractions / contradictions | `retracted_at`; `contradiction.sweep` | `retract_alias_bindings` (`contradiction.py:277`) has **no non-test callers (V)**; `store.retract_alias` called only in tests (V) | none | **Zero production writers.** RI database: 0 retracted rows in alias_binding, attribute, relation (V) | deterministic | Implemented and tested, never exercised on real data |
| 9 | `state_of` / generation state | `compile_generation_state` (`state.py:751-813`) | Digest excludes observer, story position, canon | none | `appearance_of` bypasses `state_of` filters | deterministic | Core is tested |
| 10 | Retrieval / context | `story_context` (`world/context.py`); `CandidateRetriever` | Disclosure-time only, no observer | none | Alphabetical truncation of the known-name roster to 120 (`ner.py:249`) | deterministic | Low |
| 11 | Appearance tracking | `appearance_extract` (LLM, whole-run sample); `wiki_canon`; `canon.py` | Wiki traits unstamped | LLM | Section 4.3 | LLM | Low |
| 12 | Visual references / caching | `reference_gen`, `scene_refs`, `cache_key.py` | Key hashes plan, prompt, seed, backend; **no reference input** since refs are `[]` | NoobAI XL etc. | Prompt cache keyed by DB mtime+size, ignores observer, model, template (`panels.py:~2347`); audio and video have no cache key | seeded | n/a |
| 13 | Panels | `render_panels` (`panels.py`) | `conditioned_on` metadata overstates conditioning | gemma2:9b director; NoobAI XL | Section 5 | seeded | n/a |
| 14 | Audio / video | `voice/runner.py`; `render/runner.py` | No state | Chatterbox TTS; ffmpeg | No observer on the `voice` CLI; manifests can mismatch silently | TTS nondeterminism | No audio scoring script |
| 15 | Evaluation infrastructure | `echotales eval`, `scripts/eval/*`, `gold.py` | `confirmed` tier **empty (V)** | none | Every EchoTales-specific number is silver or model-provisional; LitBank is the only human key; "recovered from deferral" is not a link count | deterministic | See section 8 |

### Mention-detection defects behind the hard-case losses (agent-traced)
- `is_address` exists in `classify_alias_type` but **no caller passes it** (V: grep shows only the definition and recursion), so address-form relational deictics ("Master, ...") are never classified as such.
- `_TRANSFERABLE_TITLE_NOUNS` is a 23-entry hand list; titles outside it fall to `GENERIC_DESCRIPTOR` and are dropped under non-negotiable 4 (`mentions/alias_type.py:49-56, 131-132`).
- `AMBIGUITY_BLOCKLIST` (master, elder, father, uncle, king, lord ...) makes `Gazetteer.add` drop seeded deictics that are exactly one of those words (`mentions/gazetteer.py:37-62, 129-130`).
- The whole-volume commonness filter (`mentions/commonness.py:102-120`, determiner-rate threshold 0.08) would, by the agent's reading of the thresholds, drop surfaces like "master" or "uncle" (INFERRED; not run).
- Title strings absorbed as aliases can later FORCE_LINK to the first absorber and defeat title transfer (mechanism in code per the agent; consequence INFERRED).

---

## 7. Separation of kinds

- **Existing functionality (executed in pipeline or CLI):** ingest, spans, mentions (gazetteer + NER), local anaphora groups, resolve with prefilters, title-holder linking, transmigration merge, appearance extraction, persona split, per-beat `state_of` for persona choice, panels, voice, video.
- **Existing but unintegrated helpers:** `VisualMemorySelector`, `emit_scoped_reference`, `compile_minimal_disclosure` (experiment-only), `retract_alias_bindings`, `retry_deferred` (runs, never links), `adjudicate_remaining` (unreachable from CLI), `coref.resolve_span_pronouns`, `world/extract.py::extract_world`, the `is_address` parameter.
- **Prototypes / research code:** reveal-aware visual memory Phases 1-2 (`core/visual_memory.py`; docs under `docs/research/reveal_aware_visual_memory/`); the technical-contribution probes (synthetic lineage). No `reveal_aware_visual_memory` code exists in `packages/research`; the implementation is in `packages/core` and `packages/pipeline/persona/scoped_reference.py`.
- **Verified artifacts (I re-checked):** 0 confirmed gold records; 58 undetected hard cases (including 1 control, 2 span defects); `reference_images=[]`; 0 retracted rows, 12 observation rows and 0 relation rows in the RI database; 11,095 alias bindings (all TRUE) and 617 attributes (588 TRUE, 29 INFERRED); 25/25 owner tests pass when inputs are present.
- **Unverified earlier claims:** the cache-staleness consequence of wiki canon; `--observer` leaving the brief reader-view; the commonness filter's effect on "master"/"uncle"; what "reference-conditioned 5/0" means; the ~98.9% gazetteer share of FORCE_LINKs (a code comment at `score.py:104-108` only); the directive's "3 reveals" (not re-counted; the reveal detector is CLI-only and not a stored table).

---

## 8. Prioritised defect list

| Rank | Defect | Why it matters for research claims | Evidence |
|---|---|---|---|
| 1 | **No human gold anywhere.** 0 confirmed records; 3,457 RI records carry a reviewer name but `confirmed: false` | Every EchoTales accuracy number is model-provenance | V |
| 2 | **Public repo exposes IPR review files and about 20k excerpt-level text snippets** on a public branch, contradicting D2 defaults | IP and copyright exposure; owner decision | V |
| 3 | **Reference conditioning is off while metadata says "conditioned"** | The observer-conditioned visual result may not be a conditioning result | V (code), INFERRED (consequence) |
| 4 | **Wiki canon is position- and body-blind and outside the cache digest** | Later state leaks into earlier panels; the repo documents one measured instance | V |
| 5 | **No prefix-safe resolver mode; `resolve --chapters` is a silent no-op** | Blocks any disclosure-faithful claim | V |
| 6 | **`retry_deferred` never links; "recovered" counts are queue removals** | Any figure built on `recovered_from_deferral` overstates resolution | V |
| 7 | **Four narrative-state policies coexist; audio and video use none; `--observer` only partly effective** | "Same state for all outputs" cannot be claimed | agent-traced, INFERRED for the observer leak |
| 8 | **Retraction has zero production writers** | The retraction axis cannot be tested on real data | V |
| 9 | **Hard-case detection losses from curated lists, blocklist, commonness filter, unused `is_address`** | The engineering target for C3 | partly V |
| 10 | Test-count discrepancy (docs 1,277 vs 1,252 collected); the novelty ledger says "clean tree" while 23 paths are untracked | Documentation accuracy | V |

I did not exhaustively grep `docs/HANDOFF.md` or `EVOLUTION.md`, so I cannot say whether defects 3 and 6 are already recorded there.

---

## 9. Owner decisions (recorded only; I have decided none)

| ID | Decision | Status | Default applied |
|---|---|---|---|
| D1 | Lift or re-scope StoryTrace firewall | Owner chose to lift (chat, 2026-10-15). Not recorded in the repo. Draft wording in section 2. | Audit and gate-testing only |
| D2 | Publication / IP sequencing | **Open, and the repo is already public** (section 1) | Treat all outputs as private |
| D3 | Reconstruct GenWebNovel text | Not granted; Qidian terms INACCESSIBLE | Do not run |
| D4 | Paid or local-model inference | Not granted | None |
| D5 | Human annotator availability | Unanswered | One annotator plus a second on 20% |
| D6 | Evaluation corpus | Unanswered | RI / LOTM / ORV as local |
