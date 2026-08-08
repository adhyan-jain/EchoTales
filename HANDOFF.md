# EchoTales — Handoff

**Purpose:** let a different agent (or a future you) resume work without
re-deriving context. Read this first, then `architecture.md` for the model and
`details.md` for per-file detail.

**Last updated:** 2026-08-08, after wiring the LLM into layer 1, fixing the
Phase 6 blockers it exposed, a first (model-drafted, unconfirmed) gold set,
cross-novel A/B on all three corpus novels, a real reading-order bug in
`Store` that affected every entity count in this document to an unmeasured
degree (§4.16), a browsable coref/attribution viewer (static + React, §8a),
an interactive correction workflow with six correction types -- mention/
speaker reassignment, entity creation, line merging, flagging, span
retyping (§4.18), and anonymous voice-slot assignment for unattributed
dialogue (§4.19).
**Test status:** 450 passing, 1 failing (`uv run pytest packages/`). The failure
is `test_segment.py::test_llm_fires_only_on_ambiguous_chapters` and it predates
this work — the runner counts a call the stub never receives.

**Everything through this point is committed and pushed** — 12 commits on
`master`, `origin/master` up to date, working tree clean except the
git-ignored `data/webview-working/` and `data/corrections/` (working state
for the interactive tool, not source). If picking this up in a fresh
session: `git log --oneline -12` shows the commit-by-commit breakdown, each
message describes what it changed and why. **The webview backend and
frontend may or may not still be running** depending on what happened to
this machine's processes between sessions -- check with
`curl -s http://127.0.0.1:8787/api/manifest` and
`curl -s -o /dev/null -w '%{http_code}' http://localhost:4173/`before
assuming either; restart instructions are in §8a.

---

## 1. Read this before touching anything

**The pipeline runs end to end.** `uv run echotales run --novel reverend-insanity`
completes RI vol 1 (199 ch) in ~37 min with the LLM backend (§4.14) or ~3 min
deterministic (`--no-llm`), and writes a SQLite graph.
`uv run echotales review --novel reverend-insanity` produces a console table,
an HTML audit, a JSONL export, and optionally a line-by-line script view
(`--script <range>`, §4.13).

**Accuracy moved from unusable to plausible, and that is the current work.**
RI: 1,862 -> 82 entities. LOTM: 730 -> 102. ORV: 859 -> 63 (all LLM vs.
deterministic, §4.14/§4.15). All three now under-count against a 150-300 cast
rather than wildly over-count, which is the better failure mode but still a
failure mode — two specific, diagnosed-not-guessed identity-continuity gaps
are in §4.15 (LOTM transmigration, ORV given-name-only mentions), and the
scorer-can't-LINK defect in §4.1 is still the structural root cause under all
of it. Do not present these entity counts as validated results — they are
plausibility, not accuracy; §4.12's gold set is unconfirmed.

**The LLM now runs in layer 1** (§4.10 — done). `.env` sets
`ECHOTALES_MODEL_BACKEND=ollama`; `ollama serve` must be up. Segmentation,
coreference and adjudication are still deterministic — see §4.10 for what is
left. `--no-llm` forces the old path for A/B comparison.

**Chapter NER is cached** at `data/lexicons/<novel>-ner-cache.json`, keyed by a
hash of the chapter text and the model name. That turns a re-run from ~35 min
into ~15 s, which is what makes downstream tuning possible at all. Delete the
file to force a fresh read. **The cache flushes every 25 chapters, not only at
the end** (§4.14) — an earlier version lost a whole run to this.

**A gold set exists but is not gold yet.** `data/gold/reverend-insanity-c1-c5.toml`,
26 identities over RI ch1-5, model-drafted (§4.12). Every record carries
`provenance=model`, `confirmed=false`. Do not report a number computed from it
as a recall or accuracy result — `eval/gold.py::GoldSet.confirmed_only` is the
enforcement point. A request to "compare against gold" can now be partially
satisfied for RI ch1-5 specifically, with that caveat stated; anything broader
still cannot.

**`plans.md` is the spec but has been amended three times** (NER/coref
restructure, architecture review, per-novel-not-per-genre correction). Where
they conflict, the amendments win; they are marked *(revised)*.

---

## 2. What actually works

Measured on the real corpus, not projected.

| Phase | Module | State | Measured |
|---|---|---|---|
| 0 Ingestion | `pipeline/ingest/` | **Working** | RI 199 ch / 16,360 blocks · LOTM 213 / 16,670 · ORV 188 / 26,470. ~3 s each |
| 1 Span classification | `pipeline/spans/` | **Working** | RI 21,297 spans · LOTM 23,540 · ~107–111 per chapter |
| 2 Segmentation | `pipeline/segment/` | **Working**, recall unverified | RI 200 segments (1 dream, 65 time skips) · LOTM 217 (3 dreams) |
| 3 Mention detection | `pipeline/mentions/` | **Working, LLM layer 1** | RI full vol: 9,568 mentions (21,751 deterministic), 9.9 s/chapter cold, ~0 cached. Cache flushes every 25 ch |
| Layer 0 seeding | `pipeline/mentions/seed.py` | **Working** | 122 / 133 / 153 names, 0.7 s per novel, no model |
| 4 Speaker attribution | `pipeline/speakers/` | **Working, regressed with LLM layer 1** — §4.14 | RI det 64.9% → LLM 48.8% full volume. Not yet recovered |
| 5 Local anaphora | `pipeline/anaphora/` | **Working** | RI 9,671 groups / 4 splits · LOTM 12,260 / 13 (deterministic baseline) |
| 6 Global resolution | `pipeline/resolve/` | **Runs; scorer cannot LINK** — §4.1 | RI full vol: 1,002 groups → **82 entities** (1,862 deterministic). LOTM 730→102, ORV 859→63 — §4.14/§4.15 |
| 6b Contradiction sweep | `pipeline/resolve/contradiction.py` | **Built, unvalidated** — §4.8 | `split` fires; 2 found on RI vol 1 |
| 7 Eval harness | `pipeline/eval/` | **Gold exists, unconfirmed** — §4.12 | B-cubed scorer built (`coref_score.py`); RI ch1-5 gold drafted (model, not human) — recall@k gold mode still empty |
| CLI + review | `pipeline/commands.py`, `review.py` | **Working, + script view** — §4.13 | `run` / `review [--script]` / `query` / `export` / `eval` |
| 8 Dataset export | — | **Not started** | JSONL export exists but is machine-only |
| Persona / TTS | — | **Design only, no code** — §4b | `Persona` model has no appearance/voice fields; nothing constructs one |

`packages/core/` (models, store, `state_of`, interval algebra) is complete and
well-tested — 74 tests including the full §3 case table.

---

## 3. Environment

```bash
uv sync --python 3.12      # 3.12 exactly; ML wheels lag newer
uv run pytest packages/
```

Hardware this was built against: **RTX 4060 Laptop, 8 GB VRAM**, 15 GB system
RAM (~4.5 GB free), 16 cores.

**Models.** `ollama serve` must be running. Installed and sufficient:
`qwen2.5:7b`, `gemma2:9b`, `qwen2.5-coder:7b`, `llama3:latest`.
**No further pulls needed** — `preflight()` passes as-is.

**Hard constraint: every local model must fit entirely in VRAM.** Partial CPU
offload is not an acceptable trade — the pipeline already streams chapters to
stay inside ~4.5 GB of free system RAM, so a spilling model competes with the
pipeline itself.

That caps local models at 7–8B q4: ~4.7 GB weights + ~0.5–1 GB KV cache at
`num_ctx=8192` ≈ 5.7 GB of 8.0 GB. **`qwen2.5:14b` is ~9 GB of weights before
any context and is deliberately not used**, despite its quality advantage.
Hard adjudication escalates to the API tier instead — that is the intended path
for the one stage that genuinely wants a bigger model.

`ModelClient.preflight()` enforces this **by measured size** (`nvidia-smi` +
ollama's reported model size against `VRAM_BUDGET_FRACTION = 0.70`), not by
model name, so substituting a larger model fails loudly at startup.

Current task→model map (`llm/tasks.py`):

| Task | Model |
|---|---|
| ner, mention_sweep, adjudication, coreference | `qwen2.5:7b` |
| segmentation, span_classification, sentiment | `llama3:latest` |

**Measured LLM budget** (`qwen2.5:7b`, steady state): **1.9 s/call**. Batching
gives no throughput gain — token generation is the bottleneck, not request
overhead. Against 600 chapters / 65,296 spans:

| Granularity | Wall clock |
|---|---|
| per span | **34.5 h — not viable** |
| per chapter | 19 min |
| per 40-ch window | 29 s |
| deferred 5% | 1.7 h |

**Design rule: no stage may call a model per-span or per-mention at bulk.**

---

## 4. Open defects — highest priority first

### 4.1 The scorer cannot reach LINK *(blocker — root cause found)*

**This is not a tuning problem. It is arithmetic.** `DEFAULT_BIAS = -4.0` and
`gate.FALLBACK_LINK_THRESHOLD = 0.80` were set independently and are mutually
unreachable. Feed the model a maximal plausible evidence vector — surface
similarity 1.0, context 0.6, speech partner 1.0, temporal 1.0 — and it returns
**p = 0.711**. The link threshold is 0.80.

    uv run python -c "
    from echotales.pipeline.resolve.score import ScoringModel
    from echotales.core.models import EvidenceVector
    v = EvidenceVector(surface_similarity=1.0, context_embedding_similarity=0.6,
                       speech_partner_compatibility=1.0, temporal_validity=1.0)
    print(ScoringModel().probability(v))"

So **no combination of scored features has ever produced a link.** Every link
the system makes comes from `score.prefilter()`. That single fact explains the
over-splitting, the 47% singleton rate, and why `deferred` sat at 8 — the DEFER
band between 0.35 and 0.80 is almost unreachable from below.

**Not fixed, deliberately.** Rebalancing the bias against an uncalibrated
threshold by hand is fitting to nothing, which is the §4.6 trap. What was fixed
instead is the categorical half: signals that genuinely *are* near-certain moved
into the pre-filter where they can act. See §4.11.

The real fix is gold + `ConformalGate.calibrate()`, still §5 item 3.

### 4.2 Phase 6 retrieval still mildly superlinear
**Improved,** not fixed. `retrieve()` no longer scores every profile, but the
prominent-entity fallback re-sorts all profiles per group.

| Chapters | ms/group (before) | ms/group (after) |
|---|---|---|
| 20 | 7.7 | 7.6 |
| 40 | 15.3 | 9.1 |
| 80 | (timed out) | 11.7 |

80 chapters now completes in 64 s where a full volume previously timed out at
10 min. The residual growth is the per-group `sorted(self.profiles...)` call —
cache that ranking and refresh it at window boundaries.

### 4.3 Contradiction detector — built *(review §1, done)*
`resolve/contradiction.py` sweeps at every window boundary and on a final pass,
re-scoring committed links against evidence accumulated since. Three classes:
co-presence discovered later, too many distinct normalised names, and
mutually-exclusive attribute conflicts. Emits `split` and returns affected
entities to the deferred queue. See §4.8 for its validation gap.

### 4.4 Gazetteer guards — complete *(review §1, done)*
All three now present: word-boundary matching (`_is_boundary`), min-length-2
(`add()`), and `AMBIGUITY_BLOCKLIST` — ~70 words that are common nouns in some
contexts and names in others. Blocked as whole surface forms only; compounds
containing them are still admitted, since surrounding tokens disambiguate.

### 4.5 "Elder Wang" / "Xiao Wang" false merge
`comparison_key` strips honorifics, so `"Elder Wang"` and `"Wang"` collapse to
one seed candidate. In a clan with several Wangs that is a false merge at the
earliest stage. A bare surname identifies a *family*, not a person.

Direction (not yet implemented): keep `comparison_key` broad for **retrieval**
(it should narrow candidates), but stop using it as an **identity** key in
`seed.py::canonical_surface`. Single-token bare forms should keep their
decorated variants as separate candidates and let context decide.

### 4.6 Retriever recall@k measured only on the easy case
The harness exists (`eval/retriever_eval.py`) and enforces the §8.2 gate, but
**gold mode has no data**. The self-retrieval smoke test returns 100% at every
k over 313 cases — which is the easy case by construction and proves only that
there is no indexing or tokenisation bug.

The gate reports `untested` because there are no `TRANSFERABLE_TITLE` cases
without annotations. Do not read the 100% as a recall result.

### 4.8 Contradiction detector is unvalidated on real data
`resolve/contradiction.py` runs at every window boundary and emits `split`
correctly (unit-tested against constructed over-merges in
`tests/test_contradiction.py`). But on 60 chapters of the primary novel it
finds **zero** contradictions.

That is expected and diagnostic rather than reassuring: the detector catches
over-*merging* (too many aliases on one entity, or two forms co-present), and
Phase 6 currently over-*splits*, so no entity accumulates enough aliases to
trigger it. It cannot be validated against the corpus until §4.1 thresholds are
tuned.

### 4.7 ORV block classification gaps
188 `HEADING` blocks survive (one per chapter — the calibre adapter's heading
skip doesn't fire on this file). Only 66 `SYSTEM_WINDOW` blocks across 188
chapters, implausibly low for a system-fiction novel: the detector requires 2+
`Key: Value` lines and this source's status messages are mostly bracketed prose.

### 4.11 Phase 6 fixes that landed *(measured, RI ch1–40)*

Three defects, all found by A/B-ing the LLM run against `--no-llm`:

**Possessive and article forms labelled entities.** `_apply_link` and
`resolve_group` took the *longest raw surface* as the label, so "<name>'s" won
whenever it was longest. Now `normalize.display_label()` — strips inflection and
a leading article, keeps honorifics (a title is information; an inflection is
noise).

**House-prefixed names split from their short forms.** "Gu Yue Mo Bei" (ch4–38)
and "Mo Bei" (ch24–36) were two entities. Jaro-Winkler is prefix-weighted and
scores them ~0.5, under the similarity floor. `normalize.name_containment()`
compares *token suffixes* instead and is a pre-filter, not a scored feature —
per §4.1 a scored feature could not have linked them.

Two guards, both load-bearing and both tested:
- The shared tail must be **≥ 2 tokens**, so a bare shared surname does not
  merge a family. That is §4.5 restated structurally, with no clan list.
- The short form must be a **suffix**, not any substring. The house name itself
  ("Gu Yue") is a two-token *prefix*, and without this it merged the whole clan.

**Co-presence was hiding the fix.** `co_presence_violation` fired on any two
distinct surfaces in one scene, so "Gu Yue Mo Bei ... Mo Bei" three lines later
read as two people standing together — and blockers are checked *before*
pre-filters, so the merge never got a chance. Now suppressed when containment
holds, and the identity test is on `comparison_key` rather than raw text (which
also un-split "Fang Yuan" from its hyphenated spelling).

**Kinship nouns became entities.** "Grandpa" is capitalised as consistently as a
name and never pluralises, so both grammatical tests passed it. Possessive
pronouns are now determiners in `commonness.py`: "his grandpa" is ubiquitous,
"his Fang Yuan" does not occur. And `CommonnessProfile` retains the corpus so it
can measure surfaces discovered *after* it was built — the LLM proposes
vocabulary the Layer 0 seed list never contained, and an unmeasured surface
skipped the filter entirely.

**A group with no naming mention no longer founds an entity.** "sir", "miss",
"this one" were minting entities that duplicated a real character and had no
retrievable identity. Left unresolved instead; counted as `deictic_only`.

### 4.9 Precision — the headline problem, largely moved

**A/B on RI ch1–40**, identical code, the only difference being whether layer 1
is `QwenNerDetector` or `HeuristicDetector` (`--no-llm`):

| Metric | deterministic | + LLM layer 1 | + the §4.11 fixes |
|---|---:|---:|---:|
| mentions | 3,676 | 1,678 | 1,479 |
| entities | **551** | 43 | **31** |
| seen once only | **49%** | 26% | **35%** |
| speaker attribution | **63.4%** | 54.6% | 54.3% |

RI's named cast over 40 chapters is plausibly 30–50, so 31 is in range where 551
was not. The top-20 is now characters and places rather than `I'll`, `Right`,
`Tomorrow` and `Fang Yuan's`.

**Be careful how you read the singleton rate.** 35% of 31 is 11 entities; 49% of
551 was 271. The *percentage* went up between the last two columns because the
denominator collapsed faster than the numerator. Absolute singleton count fell
by 96%. Quote the count alongside the rate or the number misleads.

**Speaker attribution regressed 63.4% → 54.3% and that is a real cost.** The
deterministic detector emits far more capitalised candidates, some of which
`speakers/` uses as attribution anchors even when they are not people. Fewer,
better mentions means fewer anchors. Not yet addressed. It is the clearest
argument that layer 1 recall is now too tight.

**Still wrong, in priority order:**

1. **Recall loss on item/creature names.** The Gu worms are inconsistent:
   `Longevity Gu`, `Stream Gu`, `Bear Strength Gu` survive but `Liquor Worm`,
   `Flower Wine` and `Moonlight` — which the deterministic path found with
   137/74/64 mentions — are gone entirely. These are real named world entities.
   The cause is the model's per-chapter judgement varying, not a filter. Needs
   entity *typing* (§4.9 item 3 as originally written) rather than a filter, so
   items are kept and labelled rather than kept or dropped by accident.
2. **Speaker attribution regression** — above.
3. **Singletons are now mostly one-chapter walk-ons** (`Gu Yue Bei Ju`,
   `Gu Yue Dong Tu`, `Guin`, `Brother Zhang`). Several are genuine minor
   characters, so the remaining 11 are no longer obviously wrong. Distinguishing
   a real walk-on from an over-split needs gold, not another heuristic.
4. **Translation-group credits**: not observed in the LLM run — the model does
   not return them. Unverified on the other two novels.

### 4.12 Gold set exists, model-drafted, one bug already caught it

**`data/gold/reverend-insanity-c1-c5.toml`** — 26 identities over RI ch1-5,
drafted by reading the source text directly (not by inspecting pipeline
output first, to reduce anchoring -- though see the file's own provenance
note for why that mitigation is a claim and not a guarantee). Every record
carries `provenance=model`, `confirmed=false`. **Not gold until a person
reviews it** -- `eval/gold.py::GoldSet.confirmed_only` is the enforcement
point; nothing should read a number off the unconfirmed set and report it as
a result.

New modules: `eval/gold.py` (records + provenance), `eval/draft.py` (expands
the readable TOML into per-occurrence JSONL against ingested chapter text),
`eval/coref_score.py` (B-cubed precision/recall/F1 against the system's
partition).

**It found a real coordinate-system bug on first use.** `Mention.offset` is
relative to the *block* it was found in (`span.start + hit.start`, and
`Span.start` is block-local); `Chapter.story_text` -- and every gold offset --
is the `"\n\n"`-joined concatenation of blocks. Comparing them directly
matches nothing past a chapter's first paragraph and silently reports
catastrophic recall on every chapter with more than one block, i.e. all of
them. Fixed in `coref_score.py::_block_starts`, which reconstructs each
block's chapter-absolute start before comparing. This bug is specific to the
new scorer -- nothing else in the pipeline compares a `Mention.offset` against
`story_text`, so it was not previously reachable.

**It also found a real precision-vs-recall bug in `commonness.py`, not just a
scoring bug.** The determiner-rate test's premise -- "a personal name is not
preceded by 'the'" -- is true for people and false for everything else: "the
Spring Autumn Cicada" (the central plot item, 94.8% determiner rate) and "the
Gu Yue clan" (23.9%) take an article as naturally as "the guard" does. The
filter was deleting them outright, not mistyping them. Fixed by threading
layer 1's own character/location/organization label into the commonness
check (`mentions/runner.py::rejected`) so the determiner test only applies to
surfaces labelled `character`. This directly closes HANDOFF's earlier item
"item/artifact names — needs entity typing" (§4.9 old item 3) for the
recall-loss half of that problem; the mistyping half (an item shown as if it
were a character in the review table) is unaffected and still open.

Effect on RI ch1-5 B-cubed, same 40-chapter run, before/after the commonness
fix (still model-drafted gold, so read this as a regression check on the
scorer's own sensitivity, not a final number):

| | before | after |
|---|---:|---:|
| precision | 100.0% | 91.6% |
| recall | 36.2% | 45.9% |
| f1 | 53.1% | 61.2% |

Recall improved as expected. Precision dropped 8.4 points -- some newly
admitted surfaces are merging into the wrong entity (`Gu Yue`, the clan, is
now sometimes entity #7 with 23 mentions, sometimes folded elsewhere; a
one-token `Gu` singleton also appeared). Not chased further this session --
flagging it rather than tuning blind, per §4.6's warning. **Extend gold past
ch5 before drawing conclusions from this table**; five chapters is a small
enough sample that a handful of disagreements moves both numbers a lot.

**How to reproduce:**

```bash
uv run python -c "
from echotales.core.store import Store
from echotales.pipeline.eval.draft import expand_draft
from echotales.pipeline.eval.gold import write_gold
from echotales.pipeline.eval.coref_score import score_b3

store = Store('data/llm40.db')  # or whichever db has the LLM run
gold = expand_draft('data/gold/reverend-insanity-c1-c5.toml', store)
write_gold(gold, 'data/gold/reverend-insanity-c1-c5.jsonl')
result = score_b3(store, 'reverend-insanity', gold)
print(result.summary())
print(result.worst_report(20))
"
```

### 4.13 Script view — the thing an entity table can't show you

`review.py` only ever answered "does this entity exist and look right." It
could not answer "who says line 40 of chapter 3, and is that attribution
correct" -- which is what a TTS or manga pipeline actually consumes, and
where attribution coverage can be bad while the entity table looks clean.

`uv run echotales review --novel X --script 1-5` renders every span in those
chapters in reading order: span type, attributed speaker (or `unattributed`,
in amber, with the attribution method), and the mentions inside it resolved
to entity labels. Both the console-adjacent JSONL/HTML paths are untouched --
this is additive and off by default (`script_chapters=None`), since
rendering it for a whole 199-chapter novel would dwarf the entity table.

First real signal from it: RI ch1-2, 15/42 dialogue lines attributed (36%).
Chapter 1 is almost entirely unattributed war-council dialogue with no
narration tag ("Fang Yuan, quietly hand over..." -- said by whom is never
stated in-text at that point), which may be a genuinely hard case rather than
a pipeline defect. Worth checking against a few more chapters before treating
36% as representative.

### 4.14 Full RI vol 1 run, LLM layer 1 + all §4.11 fixes

The 40-chapter numbers held up at full volume, and the shape of the win is the
same: not a small improvement, a different regime.

| Metric | deterministic (§4.9 original) | LLM + fixes, full 199 ch |
|---|---:|---:|
| entities | **1,862** | **82** |
| seen once only | 47% (875) | 20% (16) |
| mentions | 21,751 | 9,568 |
| resolution rate | -- | 99.0% |
| speaker attribution | 64.9% | 48.8% |

82 entities against a plausible 150-300 cast is now **under-**counting, which
is a materially better failure mode than 1,862 -- the top 25 by mention count
(`Fang Yuan` through `Xiong Jiao Man`) reads as an actual character list, not
noise. The full run took 37 min, almost entirely the mentions stage (9.9
s/chapter); everything downstream is now single-digit seconds.

**Speaker attribution fell further at full scale** (64.9% -> 48.8%, worse than
the 40-chapter sample's 54.3%) -- confirms §4.9's flagged regression and shows
it compounds over the volume rather than being a chapter-1-5 artifact. This is
now the clearest single number arguing that layer-1 recall is too tight, ahead
of the singleton rate.

### 4.15 Cross-novel A/B (LOTM, ORV ch1-40) — one real defect found, not xianxia-overfitting

Run to check whether §4.11's fixes (`name_containment` especially) were
tuned to RI's house-prefix naming convention and would misfire elsewhere.
**They did not appear to** -- both novels' det->LLM moved the same way RI
did: LOTM 730 -> 102 entities, ORV 859 -> 63, same shape each time, and
nothing in either top-25 looks like a `name_containment` false merge. The
fix generalises rather than being xianxia-specific.

**But cross-novel testing found something more valuable: a real architecture
gap, not a tuning artifact.** LOTM ch1 is a transmigration opening --
`architecture.md`'s own worked example, "1 self, 2 personas, sequential
bindings." Zhou Mingrui (Earth chemistry graduate) wakes up in a new body;
partway through chapter 1, "Klein Moretti['s]... memories began flooding
him." The system produces **three separate entities** for what is
architecturally one continuity of consciousness:

| Entity | Mentions | Chapters |
|---|---:|---|
| `Klein` | 954 | ch4-40 |
| `Zhou Mingrui` | 177 | ch1-26 |
| `Klein Moretti` | 9 | ch1-24 |

This is not `name_containment` failing -- "Zhou Mingrui" and "Klein Moretti"
share no tokens, so no surface-level rule could catch it. It needs the
**declaration** pre-filter (`score.prefilter`, `evidence.detect_declaration`)
to recognise "memories began flooding him" as an identity-continuity
assertion, the same class of signal as "his true name was X" but running in
the opposite temporal direction -- an *existing* identity acquiring a new
name and backstory, not a new name revealing an old identity. Lexicon-driven
declaration phrases are induced per-novel (§6), so a phrase this
novel-specific was never going to be in the seed lexicon; it would need
either a broader structural pattern ("memories... flooded/surfaced/returned")
or to wait for the lexicon induction pass to see enough examples across the
volume. Not fixed this session -- flagged because it's a clean, specific,
citable case for whoever tackles the declaration detector next, and because
it's independent confirmation that reincarnation/transmigration (which
`architecture.md §4` designed for) is currently unhandled by any live code
path, matching §4b's finding that `Persona` itself has no runner.

**ORV (859 -> 63 entities, same regime shift) found a second, cleaner case of
the same failure family** -- structural, not a one-off reveal, and diagnosed
without needing to re-read the source text since the two forms are unambiguous
by target_id in the store:

| Entity | Mentions | Chapters |
|---|---:|---|
| `Dokja` | 148 | ch2-38 |
| `Kim Dokja` | 36 | ch1-36 |

`Kim Dokja` is the protagonist's full name (Korean family-name-first order);
`Dokja` is his given name used alone, and it resolves to exactly one
`target_id` across all 148 occurrences -- unambiguous in this cast, verified
directly against the mention table rather than assumed. Structurally this is
identical to RI's `Gu Yue Mo Bei` -> `Mo Bei`: a personal name with its
leading component dropped. `name_containment` (§4.11) doesn't catch it
because the shared tail is **one token**, and the >= 2-token floor is there
specifically to stop a bare *surname* from merging unrelated people (§4.5,
`Wang`). The floor is doing its job on the surname side and costing recall on
the given-name side, because Korean family-name-first order puts the
ambiguous component (surname, shared by many) and the specific component
(given name, usually unique in a small cast) in the same token positions that
`Gu Yue`/`Mo Bei` put the unambiguous house name and specific personal name.
The rule cannot currently tell "this dropped token was a surname" from "this
dropped token was a given name" -- it only counts tokens. A fix would need to
know which, which is a lexicon/gazetteer question (is the dropped token itself
attested elsewhere as a *bare* alias for multiple entities?) rather than a
pure token-count threshold. Not fixed this session, for the same reason as the
LOTM case -- flagged with exact numbers so it's falsifiable rather than tuned
blind.

**Infrastructure note, expensive to learn:** the NER cache used to flush only
once, at the very end of `detect_mentions`. A run interrupted at chapter 175
of 199 -- which happened once during this session, for reasons unrelated to
the pipeline itself -- lost the entire 175 chapters of GPU work because
nothing had been written yet. Fixed: the cache now flushes on the same
`commit_every` cadence as the store commit (`mentions/runner.py`), so an
interruption loses at most ~25 chapters, not the whole run.

### 4.16 `Store.get_spans`/`get_mentions` returned scrambled reading order *(fixed)*

Found while chasing a user report that the webview "cuts off sentences" --
`he sighed`-style narration tags trailing a quote seemed to vanish. They
didn't: `split_block` (`spans/classify.py`) has always correctly split
`"..." he sighed.` into two spans, and `classify_chapter` has always produced
both. **The bug was in retrieval, not classification.** `Span.start`/`end` and
`Mention.offset` are block-local, not chapter-local (documented on
`Mention.offset`'s own docstring), but `get_spans` ordered by `start` alone
and `get_mentions` by `(chapter, offset)` alone -- neither includes
`block_index`. Every block's *first* span (`start=0`) sorted together by
coincidence; every block's *second* span sorted somewhere else entirely, next
to whichever unrelated block happened to share its offset. A narration tag at
local offset 59 didn't disappear -- it rendered dozens of positions away from
its own quote, which reads exactly like a truncated sentence.

**This was not only a display bug.** `resolve/runner.py::resolve_novel`
explicitly claims "Order is not an implementation detail... strictly in
discourse order" and builds its per-chapter group-processing order directly
from `store.get_mentions(novel_id, chapter.number)`. That call was returning
mentions in scrambled block order, not reading order, for any chapter where a
block contributed more than one mention -- which is common. So every entity
count in this document, all from `resolve_novel` runs made before this fix,
was computed with mentions processed out of true discourse order *within* each
chapter (chapter-to-chapter order was never affected -- `iter_chapters` orders
correctly by `number`). How much this changed any specific decision is
unmeasured; re-running to find out would cost the GPU time this session
already spent once. Treat existing entity counts as directionally right, not
byte-reproducible against a re-run.

**Fixed** in `core/store.py`: both queries now order by `block_index` first.
Regression tests in `packages/core/tests/test_store_ordering.py` reproduce the
exact shape that exposed it (a block with two spans/mentions, straddled by
another block's offsets) and pin `resolve_novel`'s specific dependency. No
pipeline re-run was needed to pick up the fix -- both `get_spans` and
`get_mentions` are pure retrieval, so the already-computed data was always
complete; only its order was wrong. The webview/review data was rebuilt from
the existing databases and the narration tags now sit next to their quotes.

**How I found it, since the debugging path is worth keeping:** a diagnostic
script that grabbed a span by text match and printed its `list_pos ± 2`
neighbours looked like proof the tail span was missing -- it wasn't, the
neighbours in *storage order* just weren't the neighbours in *reading order*.
Cross-checked by calling `classify_chapter` fresh (always correct, doesn't
touch the DB) against what `get_spans` returned for the same chapter and
diffing block-by-block, which is what actually located the bug in the query
rather than the classifier.

### 4.17 Inner monologue now shows whose thought it is

`speakers/attribution.py::attribute_chapter` has always resolved a POV holder
for `INNER_MONOLOGUE` spans (`AttributionMethod.POV_INFERRED`) and the data was
always in the payload -- both webview builds simply only ever rendered the
speaker column for `DIALOGUE`. A paragraph of inner monologue showed no
attribution at all, which is a real gap when a chapter has more than one
plausible POV holder. Fixed in both `webview.py` (static) and
`ScriptLine.js` (React): the speaker column now shows `<name> / thinking` for
`INNER_MONOLOGUE` when a POV holder was resolved, styled distinctly (italic)
from a `DIALOGUE` speaker so the two aren't visually confused. Unlike
`DIALOGUE`, an unresolved inner-monologue speaker renders blank rather than
the red "unattributed" flag -- that flag is reserved for the tracked
dialogue-attribution KPI, and inner-monologue POV coverage is a different,
untracked number that would be misleading to conflate with it.

### 4.18 Interactive correction workflow (`webview/`, `webview_server.py`, `corrections.py`)

The read-only viewer accepts corrections and does something with them,
closing a loop the static build had no way to close. Six correction types,
all wired end-to-end (backend + UI) except where noted.

**Two things happen to a correction, and neither is "feed it back into the
resolver as input"** -- §6 rules that out explicitly (a resolver graded
against its own answer key measures nothing). Instead:

1. **Logged** (`corrections.py::Correction`, JSONL per novel at
   `data/corrections/<novel>.jsonl`) as a human-provenance record, distinct
   from and *not* the same file as the model-drafted gold in `data/gold/` --
   this is a faster, less rigorous log meant to accumulate real evidence for
   calibrating `ConformalGate` later (§4.1), not a replacement for gold review.
2. **Previewed immediately**: `webview_server.py::_overlay_corrections`
   redirects the payload's display -- entity list, every inline mark, every
   span's speaker -- to reflect pending *and* applied corrections, recomputed
   fresh per request. One exception: `merge_lines` has no live preview (below).
3. **Optionally applied** to the live SQLite store on request
   (`corrections.py::apply_pending`): rebinds mentions/speakers, deletes an
   absorbed span, appends a `ResolutionEvent` per change with
   `source: human_correction`. Idempotent per item -- an already-applied
   correction is skipped; a correction whose apply fails is *not* marked
   applied, so it surfaces again rather than silently vanishing.

**The six types:**

- **`merge_entities`** -- two entities are the same person; fold one into the
  other. Sidebar ⇄ icon, then click the target row.
- **`reassign_mention`** -- one occurrence of a name was linked to the wrong
  entity, addressed by `Mention.id` (not surface text, so fixing "this one
  'Mo Bei'" never touches an unrelated occurrence that spells the same way).
  Click any highlighted mention in edit mode.
- **`reassign_speaker`** -- a dialogue/inner-monologue line has the wrong
  speaker or none, addressed by `Span.id`. Click the speaker cell.
- **`merge_lines`** -- two adjacent spans in one block are one sentence the
  classifier split (§4.16's quote-plus-narration-tag case is the common one).
  "merge ↑" button, hover-revealed per line. **No live preview** -- folding
  two spans into one mid-render was judged too likely to hide a subtle bug for
  the time available; the merge is only visible after Apply. Verified directly
  instead: applying the exact §4.16 example (block 29, chapter 9) turned two
  stored spans back into one, text byte-identical to the original block
  (re-sliced from source, not string-joined, so the join character is never
  guessed at or duplicated).
- **`flag`** -- not a fix, a note: "look at this again." Never touched by
  Apply (`pending_actionable` in the summary excludes it) -- a flag stays open
  until explicitly removed (the existing undo endpoint), so "I fixed something
  else" can never silently mark it dealt with. Carries a `source` field
  (`"human"` vs `"agent:<model>"`) so an unattended nightly sweep's guesses are
  never visually confused with your own review. `reassignMention`/
  `reassignSpeaker` can also mint a **brand new entity** instead of picking an
  existing one (`EntityPicker`'s "+ Create new character" row) -- the new
  entity's id is decided once at correction-creation time
  (`new_manual_entity_id`), so the live preview and the eventual store write
  always agree on what "the new character" refers to, and it renders in a
  fixed teal (`#2EC4B6`) distinct from the ranked palette so a manually-created
  character is visually obvious in the sidebar.
- **`reassign_span_type`** -- the classifier's `SpanType` was wrong: prose
  read as narration that's actually a translator's note (retype
  `NON_DIEGETIC`, which drops it from both audio and panels and clears any
  speaker), or the reverse. Addressed by `Span.id`. A per-line `<select>` in
  edit mode, populated from every `SpanType` value with `NON_DIEGETIC` and
  the narration types listed first -- the two the request was specifically
  about. Verified live in the overlay preview, not just at apply time.

**Data safety: corrections are never applied to the databases this document's
numbers came from.** `webview-server` is run against copies in
`data/webview-working/` (`echotales.db`, `llm-lotm.db`, `llm-orv.db` copied in
under their novel-id names), not `data/echotales.db` etc. directly --
requested explicitly and worth keeping as standard practice: `data/*.db` are
the run of record, `data/webview-working/*.db` are what a correction session
edits. Re-copy from the originals to reset. Verified after a full edit-and-apply
pass: originals byte-unchanged (entity count still 82, a specific mention's
`target_id` still `self1`), working copy showing every change correctly.

**Three real bugs this surfaced**, all fixed, all worth keeping as cautions:

1. **Cross-thread sqlite3.** `ThreadingHTTPServer` handed each request its own
   thread; `Store`'s connection was opened once in the main thread, and
   sqlite3 forbids cross-thread use by default. Fixed by switching to a plain
   single-threaded `HTTPServer` -- correct for this tool's actual concurrency
   profile (one reviewer, one request at a time), not a workaround.
2. **Stale closure sending `chapter: null`.** `handleSpeakerClick` was
   memoised on `[chapterIdx, novelId]`, not `novel` -- if that closure got
   created on a render where `novel` was still `undefined` (before the first
   fetch resolved), it kept referencing `undefined` even after `novel`
   populated, because neither of its actual dependencies had changed. The
   crash (`float() argument ... not 'NoneType'` in `_apply_reassign_speaker`)
   surfaced it. Fixed by threading the chapter number explicitly down from
   `ScriptView` (which is already rendering that exact chapter) instead of
   re-deriving it from state that can be stale -- removes the whole bug class,
   not just this instance of it.
3. **Partial-batch inconsistency in `apply_pending`.** It committed once, at
   the very end, after marking every item applied as it went. A later item
   raising (bug 2, live) meant the exception propagated out before the commit
   ran -- so the log claimed an earlier correction was applied while its
   store write sat in an uncommitted, about-to-be-discarded transaction. Fixed
   two ways together: each correction's apply is now wrapped so one failure
   can't sink the batch, and the store commits after every item, not once at
   the end, so `mark_applied` and "actually persisted" can never disagree.

**Verified against the real UI**, not curl alone, for every type above:
headless Chromium via the DevTools protocol, real clicks on the actual DOM
(merge icon, mention marks, speaker cells, flag/merge buttons), reading back
both the rendered page and a fresh SQLite query afterward. Confirmed on the
exact cases this session had already found and named: merging `Klein` and
`Zhou Mingrui` in LOTM (§4.15) produced one 1131-mention entity; merging RI
chapter 9 block 29 (§4.16) restored the quote-plus-narration-tag sentence to
one span with its original text intact.

One test-harness false alarm from the merge-only verification pass is worth
keeping on record so it isn't rediscovered: a checkbox toggled via the "set
the native property then dispatch a synthetic event" trick (needed for
React-controlled `<select>` elements) does not reliably fire a checkbox's
`onChange` the same way -- a plain `.click()` does. The same trick *is*
required for a React-controlled `<input type=text>` (used for the picker's
search/create field) -- `.value = x` plus a synthetic event does nothing
there; only the native setter works. Different element, different answer;
check which before assuming.

**Not built:** `mark_not_entity` (an entity is a false positive -- role noun,
item, translation credit -- and should stop existing rather than be reassigned
anywhere) is still only a documented idea, not implemented. The nightly
agent-review sweep discussed with the user (a scheduled job reusing
`ModelClient`/`Task` routing to emit `flag` corrections with
`source: "agent:<model>"`, human-reviewed before anything is applied) is
designed but not built.

### 4.19 Anonymous voice slots for unattributed dialogue (`speakers/runner.py`)

The user's framing, worth keeping verbatim because it's the actual design
constraint: unattributed lines "don't even need to be stored as a
character," but leaving them all simply unattributed means downstream
synthesis has no way to tell two different unnamed speakers apart --
"we need different voices for different people" even when neither is known.

`_assign_anonymous_slots()` runs after the normal four-tier attribution
ladder, over whatever `DIALOGUE` it left `UNRESOLVED`. Turn-taking
alternation only, explicitly not claiming to be coreference: consecutive
unresolved lines alternate between up to `_MAX_ANON_SLOTS = 4` chapter-scoped
slots, and any resolved line (a real speaker) restarts the count. The id
(`f"{novel_id}:anon:{chapter:g}:{slot}"`) is never written as a `Self` row --
see architecture.md §4's new note on this being a stand-in for `Persona`,
which still has no runner. New `AttributionMethod.ANONYMOUS_SLOT` stays out
of the tracked attribution-coverage KPI on purpose; it means "linked to a
known identity," and an anonymous slot deliberately is not one.

**Measured, full volumes, re-running attribution on top of the LLM-layer-1
mention data:**

| Novel | Attributed | Anonymous slots | Coverage (unaffected) |
|---|---:|---:|---:|
| RI | 2,795 / 5,725 | 2,930 | 48.8% |
| LOTM | 1,290 / 1,812 | 522 | 71.2% |
| ORV | 1,286 / 2,959 | 1,673 | 43.5% |

Both webview builds render the slot as `Unknown Speaker N` (never the raw
id), coloured from a small fixed palette distinct from the ranked entity
palette, styled italic -- neither the bold treatment a named speaker gets
nor the red "missing" treatment, since this is a design category, not a
defect. `reassign_speaker` still works on an anonymous-slot line exactly as
on any other -- naming the real speaker, if you know it, clears the
anonymous styling and folds the line into the normal attribution-coverage
count.

**Found in passing, not fixed:** re-running attribution surfaced
`speaker="As"` on several `EXPLICIT`-confidence lines in RI -- almost
certainly a malformed extraction from narration text like "As he said
this," not a real name. Predates every change in this document; not
something this session's edits caused, and not investigated further. Worth
a look before trusting `EXPLICIT`-tier output at face value.

### 4.10 LLM wiring — layer 1 done, three stages left

**Done:** `commands.py::_build_client` builds one `ModelClient` per run,
preflights it, and threads it into `detect_mentions`. It returns `None` on the
`stub` backend rather than a stub client, so a stage cannot mistake canned
answers for a working model run.

**The shape of the NER pass matters more than the wiring.** The model is *not*
asked where the mentions are. It is asked, once per chapter, **which surface
forms in this chapter are names**; the returned vocabulary is then matched over
every span by the same Aho-Corasick machinery layer 2 uses
(`mentions/chapter_ner.py`). Two reasons:

- Cost. Per-span is 34.5 h by the §3 budget; per-chapter is ~35 min for 199
  chapters (measured 9.9 s/chapter including chunking).
- Correctness. Offsets, word boundaries and overlap resolution stay exact
  instead of being hallucinated back as character positions. The model
  contributes only the judgement capitalisation cannot make.

Returns are filtered before use (`plausible_name`): a length and token cap, no
sentence punctuation, and an initial capital. On chapter 1 the model returned a
whole clause as an entity, so this is load-bearing, not defensive.

**Still deterministic:**

- `segment/runner.py` — `use_llm=True` with a router
- `resolve/runner.py` — `use_llm=True` so deferred cases reach adjudication
- `anaphora/coref.py` — the client for ambiguous paragraphs. Budget this one
  carefully: ~76 min, and it is the only stage below chapter granularity.


---

## 4b. Voice / TTS design (proposed, not built — 2026-08-07)

Not started, but scoped now because it consumes exactly what the graph
produces and the design decisions constrain what `Persona` needs to carry.
`plans.md` already committed to the shape: `persona` owns "voice timbre,
physical attributes -- this is what image generation and TTS bind to", and
`architecture.md §8b` already ruled out global collision-free voice
assignment in favour of archetype-bucket colouring. Both stand; nothing below
relitigates them.

**Engine: XTTS-v2 (Coqui), local.** Multi-speaker, zero-shot cloning from a
~6s reference clip, ~2-4 GB VRAM at inference — fits the existing 8 GB budget
if sequenced after the LLM stages rather than run concurrently with them (the
same non-negotiable as `qwen2.5:7b`: no stage shares the GPU with another
model resident at once). Chosen over ElevenLabs for the same reason the LLM
tier defaults to ollama: a 199-chapter novel is hundreds of thousands of
words, and that's the pipeline's dominant recurring cost at API rates. Revisit
F5-TTS as a drop-in swap if a short bake-off (2-3 real lines, both engines)
shows materially better prosody — same interface, so this is a provider
choice, not an architecture choice.

**Pipeline, in dependency order:**

1. **Trait extraction — one LLM call per `Self` above a mention-count floor**,
   not per mention. Same discipline as layer 1 (§4.10): the input is the
   entity's accumulated evidence (attributed dialogue, narrator descriptions,
   relationships already in the graph), the output is Big Five scores plus
   coarse demographics (age band, gender, register). This is a new
   `Task.CHARACTER_PROFILE` in `llm/tasks.py`, same router.
2. **Archetype bucket = demographics + register, not raw Big Five.** Five
   continuous traits don't cluster into voice categories; age/gender/register
   do. Reuses the bucket concept `architecture.md §8b` already committed to
   for collision avoidance — one bucketing serves both voice-collision
   avoidance and reference-voice selection.
3. **Big Five picks the voice within the bucket**, and separately shapes
   delivery: high extraversion -> more dynamic prosody / faster pacing, low
   agreeableness -> clipped delivery, etc. This is a parameter mapping onto
   XTTS-v2's sampling settings, not a separate model.
4. **Reference-voice library, not per-character cloning, for the long tail.**
   A curated set of ~40-60 reference clips (age/gender/register-tagged, e.g.
   drawn from VCTK or a similar open multi-speaker corpus) covers a 150-300
   entity cast via bucket matching. Cloning a dedicated reference clip is
   reserved for the 10-15 principals where a distinct voice earns its cost —
   mirrors the hybrid local/API escalation ladder already built for the LLM
   tier (`llm/router.py`), same pattern applied to voice budget instead of
   inference tier.
5. **Consumes the script view (§4.13) directly.** `ScriptLine.speaker_label` +
   `attribution_method` is already the exact input TTS needs: text, who says
   it, and how confident the attribution is. An `UNRESOLVED` line is a
   decision point (narrator voice? skip? flag for manual pass?) the script
   view now makes visible before synthesis, not after.

**Blocked on:** §4.10's speaker-attribution regression (54.9% -> 48.8% at full
volume). Casting a voice for a line with no resolved speaker is meaningless,
so recovering attribution coverage is upstream of this being buildable at all
against the current run, not just a nice-to-have.

**Not decided:** whether trait extraction runs as its own pipeline phase after
Phase 6 (resolve) or is folded into `resolve/adjudicate.py`'s existing
per-entity LLM touchpoint. Leaning toward a new phase — adjudication is
identity-focused and keeping trait extraction separate keeps that stage's
job legible — but this hasn't been tested against the actual `Self`/`Persona`
schema. Checked while writing this: `Persona` (models.py) has `id`,
`novel_id`, `body_label`, `first_attested_pos` and nothing else — no
appearance, no voice timbre, despite the docstring claiming both.
`store.add_persona`/`get_persona` exist but **nothing in the pipeline ever
constructs a `Persona`** — no runner creates one from a resolved `Self`. So
this is not "add fields to a working stage", it is "the self/persona split
in architecture.md §4 has no code on the persona side at all". Phase 6 only
produces `Self` rows today.

## 5. Architecture-review items not yet implemented

From the 2026-08-06 review. None of these are done; all are folded into the
docs.

| # | Item | Status |
|---|---|---|
| 1 | Contradiction detector + gazetteer blocklist | **DONE** — `resolve/contradiction.py`, swept at each window boundary; `split` now actually fires. Blocklist in `gazetteer.AMBIGUITY_BLOCKLIST`. **Unvalidated on real data** — see §4.8 |
| 2 | Retriever recall@k harness | **PARTIAL** — `eval/retriever_eval.py` built with the §8.2 gate. Gold mode needs annotations; self-retrieval smoke test passes 100% @all k (313 cases, no misses), which only proves there is no indexing bug |
| 3 | Long-span sparse gold (~200 hard cases) + IAA | **not started** |
| 4 | Mondrian/class-conditional conformal by `alias_type` | **not started** — current gate is standard conformal |
| 5 | Scorer reduced to 5 features; `declaration_match` + `gazetteer_exact_match` as hard pre-filters; `co_presence_violation` as hard blocker | **DONE**, plus `name_containment` as a third pre-filter (§4.11). But see §4.1: the pre-filters are not an optimisation, they are the *only* path to a link. |
| 6 | Lexicon induction confidence tiers (admit single-sample at LOW) | **not started** — `induce.py` currently *excludes* single-sample terms (`min_support=2`) |
| 7 | Voice coloring within archetype buckets | not started (voice pipeline unbuilt) |
| 8 | Asymmetric segmentation thresholds (aggressive on explicit, conservative on implicit) | **not started** — currently uniform |
| 9 | Visual pipeline → 3-chapter showcase | scope change, pipeline unbuilt |
| 10 | RI Vol 1 as primary; LOTM/ORV 5-chapter spot-checks | scope change |
| 11 | Baseline A (long-context LLM) + Baseline B (LLMLink) | **not started** |
| 12 | Drop "full automation" framing | docs updated |
| 13 | `audience_scope_compatibility` scoped to explicit region tags | **not started** — currently returns 0.5 default |

---

## 6. Decisions already made — do not relitigate

- **EPUB only, never PDF.** PDF loses italics, which is an independent
  inner-monologue signal. Measured: making emphasis a *span boundary* rather
  than an attribute moved `INNER_MONOLOGUE` from 2.7%→14.1% (RI), 2.1%→5.6%
  (LOTM).
- **No clustering.** Incremental resolution with evidence accumulation.
- **Lexicons are induced, not hand-written.** Hand-written versions are
  archived at `data/lexicons/_handwritten_archive/`. Reason: a lexicon hit is
  authoritative at 0.95 confidence, so an entry written from recall silently
  outranks every heuristic — and "we hand-tuned per novel" is the first
  reviewer objection to the transferable-title result.
- **Hand-curated alias→entity mappings are gold labels, never pipeline input.**
  Supplying them as input means the resolver reads the answer instead of
  discovering it.
- **`retract` ≠ `close_interval`.** Different event types, different semantics.
- **GLiNER and fastcoref both dropped.** Qwen2.5 for NER (trained on Chinese
  web-novel content and its translations); five-route strategy for coreference.
- **`data/gold/` stores offsets + short evidence snippets, never chapter text.**
  CoNLL/OntoNotes convention — annotations stay shareable without
  redistributing the novels.

---

## 7. Corpus

`data/raw/` — **not committed**, supply your own copies.

| Novel | File | Adapter | Range | In file |
|---|---|---|---|---|
| Reverend Insanity | `reverend-insanity-c1-c500.epub` | `lightnovelworld` | **1–199** (primary) | 500 |
| Lord of the Mysteries | `Clown - LotM Vol. 1.epub` | `calibre` | 1–213 | 213 |
| Omniscient Reader's VP | `Omniscient Reader's Viewpoint - Sing-shong (singsyong).epub` | `calibre` | 1–188 | 551 |

Source quirks the adapters absorb: RI names Chapter 1 `page-0.html` (chapter
numbers come from the TOC, never the filename) and repeats the title as a bold
first paragraph; LOTM marks inner monologue with `<i>` and ships
Pathways/Characters/Locations appendices that must stay `NON_DIEGETIC`.

---

## 8. Running things

```bash
# whole pipeline, one novel (RI vol 1 = ~3 min, deterministic mode)
uv run echotales run --novel reverend-insanity

# limited range while iterating
uv run echotales run --novel reverend-insanity --chapters 1-40

# human review: console table + HTML audit + JSONL export
uv run echotales review --novel reverend-insanity
#   -> data/review/<novel>-review.html   (open in a browser; per-entity citations)
#   -> data/review/<novel>-entities.jsonl

# the central query
uv run echotales query state-of --novel reverend-insanity \
    --target "Fang Yuan" --chapter 150 --observer READER

# browsable coref/attribution viewer, across all three novels at once
# option A: dependency-free static build (open the file directly, no server)
uv run echotales webview \
    --source "data/echotales.db:reverend-insanity:Reverend Insanity" \
    --source "data/llm-lotm.db:lord-of-the-mysteries:Lord of the Mysteries" \
    --source "data/llm-orv.db:omniscient-readers-viewpoint:Omniscient Reader's Viewpoint" \
    --out data/webview
#   -> data/webview/index.html   (open directly, file:// works)

# option B: the same viewer as a React app (webview/)
uv run echotales webview --format react \
    --source "data/echotales.db:reverend-insanity:Reverend Insanity" \
    --source "data/llm-lotm.db:lord-of-the-mysteries:Lord of the Mysteries" \
    --source "data/llm-orv.db:omniscient-readers-viewpoint:Omniscient Reader's Viewpoint" \
    --out webview/public/data
cd webview && npm start                 # dev server, or:
npm run build && npx serve -s build      # production build, needs a server either way

# option B needs this running too, for "Live edit" -- corrections, live payload
#
# ALWAYS point this at working copies, never at the databases above directly --
# a correction's "Apply" writes real sqlite mutations, and these are the files
# every number in this document is measured from. Re-copy from the originals
# whenever you want a clean slate.
mkdir -p data/webview-working
cp data/echotales.db data/webview-working/reverend-insanity.db
cp data/llm-lotm.db  data/webview-working/lord-of-the-mysteries.db
cp data/llm-orv.db   data/webview-working/omniscient-readers-viewpoint.db

# The three databases above predate anonymous voice-slot assignment (§4.19)
# -- re-run attribution on the working copies to populate it. Fast (spans are
# already classified, mentions already resolved; this only redoes Phase 4).
uv run python -c "
from echotales.core.store import Store
from echotales.pipeline.speakers import attribute_novel
for novel, db in [
    ('reverend-insanity', 'data/webview-working/reverend-insanity.db'),
    ('lord-of-the-mysteries', 'data/webview-working/lord-of-the-mysteries.db'),
    ('omniscient-readers-viewpoint', 'data/webview-working/omniscient-readers-viewpoint.db'),
]:
    attribute_novel(novel, Store(db))
"

uv run echotales webview-server \
    --source "data/webview-working/reverend-insanity.db:reverend-insanity:Reverend Insanity" \
    --source "data/webview-working/lord-of-the-mysteries.db:lord-of-the-mysteries:Lord of the Mysteries" \
    --source "data/webview-working/omniscient-readers-viewpoint.db:omniscient-readers-viewpoint:Omniscient Reader's Viewpoint"
#   -> http://127.0.0.1:8787 by default; check "Live edit" in the React app
#      once this is running, or it shows a clear error instead of hanging
```

**§8a. `webview`** (`pipeline/webview.py`) reads the prose with every resolved
mention underlined and colour-coded by entity, and every dialogue line headed
by its attributed speaker -- the fastest way to *see* a wrong merge rather than
infer one from counts. Novel switcher, chapter navigator, entity sidebar with
a click-to-filter that dims every line not touching that entity, and a hover
tooltip on each mention (entity, resolution status, confidence).

**Two builds share one Python data layer** (`build_novel_payload` in
`webview.py`), because the two delivery constraints are opposite and neither
should compromise the other:

- **`--format static`** — one HTML file + one JS-global data file per novel
  (`<script src>`, not `fetch`). Opens via `file://` with zero server, because
  `fetch()` of local JSON is blocked by the browser's same-origin policy but a
  `<script src>` load is not. Vanilla JS, no build step, no `node_modules`.
- **`--format react`** (`webview/`, scaffolded with `create-react-app` — noted
  deprecated by the React team as of writing, kept anyway since that's what
  was asked for and `react-scripts 5.0.1` still builds cleanly against React
  19) — writes plain JSON to `webview/public/data/`, fetched normally.
  Needs `npm start` or a served `build/`; will **not** work opened directly
  via `file://`, unlike the static version. Same CSS, same interaction logic,
  ported by hand from the vanilla version rather than reimplemented from
  scratch, specifically so the two stay behaviourally identical.

**Both verified against a real Chromium instance via the DevTools protocol**,
not just by reading the code — real clicks, real mouse-move events, DOM state
read back after each. Numbers match exactly between the two builds: entity-click
dims 93/111 unrelated lines in RI ch1 and highlights the 18 that mention `Fang
Yuan`; novel-switching re-renders correctly for all three; the hover tooltip
fires on a real mouse-move over a `Kim Dokja` mark with the right text. The
React build's first verification pass *did* turn up a real bug this way, worth
noting as a caution for testing this class of app: querying DOM state in the
same synchronous tick as a programmatic `.click()` reads pre-render, because
React's state update and re-render land a task later than a plain DOM
mutation would — the click appeared to silently do nothing until an `await`
was added after it. A second, smaller finding was a genuine oversight: two
elements were missing the `id` attributes their CSS already targeted by class
(`#novel-sub`, `#stats-strip`), harmless visually but would break any script
or a11y tooling querying by id. Both fixed.

Incidentally, the tool immediately makes both §4.15 findings visible by eye,
in either build: LOTM's sidebar shows `Klein` / `Zhou Mingrui` / `Klein
Moretti` as three separate rows, and ORV's shows `Dokja` / `Kim Dokja`
similarly split — this is the fastest way to *show* those bugs to someone, not
just cite the numbers.

Config lives in `.env` (copy `.env.example`). The two switches that matter:

```
ECHOTALES_LLM_MODE=local        # stub | local | api | hybrid
ECHOTALES_MODEL_BACKEND=ollama  # stub | ollama | anthropic
```

**`.env` now exists and selects ollama.** `ollama serve` must be running or the
run aborts at preflight rather than silently degrading. The library defaults are
still `stub`, so a checkout with no `.env` runs deterministically.

```bash
# A/B the LLM against the deterministic path — this is how §4.9's table was made
uv run echotales --db data/det.db run --novel reverend-insanity --chapters 1-40 --no-llm
uv run echotales --db data/llm.db run --novel reverend-insanity --chapters 1-40

# note the global flags come BEFORE the subcommand
uv run echotales --db PATH -v run --novel ...
```

**The NER cache is what makes iteration possible.**
`data/lexicons/<novel>-ner-cache.json`, keyed on chapter-text hash + model. A
40-chapter run is 6m41s cold and 14s warm. Everything downstream of layer 1 was
tuned against the warm path. Delete the file to force a re-read; changing the
model or re-ingesting invalidates it automatically.

---

## 9. Layout

```
packages/core/     models, store, state_of()   — imports NOTHING from pipeline
packages/pipeline/
  llm/       base, stub, ollama, anthropic, router, client, tasks
  ingest/    epub, adapters/, classify, normalize, sources, runner
  spans/     classify, delivery
  segment/   markers, detect, llm_pass, runner
  mentions/  seed(L0), ner(L1), gazetteer(L2), lexicon, induce, variants,
             alias_type, parenthetical, runner
  speakers/  attribution, runner
  anaphora/  local, coref, validate, runner
  resolve/   retrieve, evidence, score, gate, detectors, wiki, adjudicate, runner
  webview.py builds both viewer targets (§8a) from one shared payload
  webview_server.py  live backend for corrections (§4.18)
  corrections.py     Correction/CorrectionLog/apply_pending (§4.18)
data/
  raw/         source EPUBs (not committed)
  lexicons/    _seed.toml + induced per-novel + _handwritten_archive/
  gold/        annotations (draft: reverend-insanity-c1-c5.toml, model-drafted — §4.12)
  webview/     static viewer build (git-ignored, regenerate with `echotales webview`)
  corrections/ human corrections log, one JSONL per novel (§4.18). NOT
               git-ignored, deliberately -- unlike data/webview/ this is
               irreplaceable human review, not a regenerable build artifact.
               Contains no source text, only target_ids -- no copyright
               reason to exclude it either.
  webview-working/  copies of the *.db files above, edited by
               webview-server so a correction's Apply can never touch the
               databases this document's numbers are measured from (§4.18).
               Git-ignored -- regenerate by re-copying.
webview/     React viewer (git-ignored node_modules/build; §8a, §4.18)
```

`core` importing `pipeline` is a CI failure, not a style preference.

---

## 10. Suggested next steps, in order

1. **Get a person to confirm §4.12's gold set, then calibrate the gate** (§4.1).
   The scorer cannot emit a linking probability above p=0.71 against a 0.80
   threshold — every link in the system runs through the pre-filter, not the
   scorer. This is the root cause under §4.1, and it is why §4.15's two
   identity-continuity misses can't be fixed by scoring harder: they need new
   *pre-filter* signal (a declaration variant, a lexicon-aware containment
   check), not a rebalanced weight. Extend the confirmed gold past ch5 before
   calibrating — five chapters is too small a sample, §4.12 says so explicitly.
2. **Fix the two §4.15 identity-continuity misses**, now that they're each
   reduced to one paragraph with exact entity counts: LOTM's transmigration
   reveal needs the declaration detector to recognise "memories flooded him"
   as an identity-continuity assertion; ORV's `Dokja`/`Kim Dokja` split needs
   `name_containment` to distinguish a dropped surname (ambiguous, correctly
   blocked) from a dropped given name (usually unambiguous, currently also
   blocked) — a lexicon question, not a token-count threshold.
3. **Recover the speaker-attribution regression** (§4.9/§4.14). 64.9% → 48.8%
   at full RI volume, and it got worse as the run scaled up, not better.
4. **Build `Persona`'s runner** (§4b). Currently `Persona` has no fields beyond
   an id and a label, and nothing in the pipeline ever constructs one — the
   self/persona split `architecture.md §4` designs around doesn't exist in
   code yet. Blocks TTS/voice work (§4b) and is the same underlying gap as
   §4.15's LOTM case: reincarnation/disguise needs two personas on one self,
   and there is currently nowhere to put the second persona even if resolution
   correctly identified the split.
5. **Entity typing at the `Mention`/`Self` level, not just the commonness
   filter.** §4.11's fix stopped items/locations from being silently deleted,
   but a kept item still displays and behaves like a character in the review
   table — `chapter_ner.py` has the label as far as `VocabularyDetector`, and
   it is still discarded at `_make_mention`.
6. Wire the remaining three LLM stages (§4.10), coreference last and budgeted.
7. Then: Mondrian conformal, baselines (§5).

**How to check your work:** `uv run echotales run --novel <novel>` then
`uv run echotales review --novel <novel> --script <a-b>`. Report the singleton
**count** next to the percentage (§4.9's warning: the rate moves the wrong way
when the fix is working). The script view's dialogue-attribution coverage is
now the fastest way to see the speaker-attribution regression directly, rather
than inferring it from the summary line.
