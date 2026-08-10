# EchoTales — File-Level Details

What every file does, why it exists, and the non-obvious decisions inside it.
For the high-level picture see [`architecture.md`](architecture.md).

Kept current as modules land. Files not yet written are marked **(pending)**.

---

## Root

### `pyproject.toml`
uv workspace root, `package = false` — the root is a virtual project, not a
buildable one. Members are `packages/*`.

Pinned to **Python 3.12** (`>=3.12,<3.13`) even though the machine runs 3.14:
ML wheels (sentence-transformers, torch) lag the newest interpreter.
`uv sync --python 3.12`
fetches it.

Holds shared tool config so it lives in one place: ruff (line length 100, `E W
F I B UP N SIM RUF`), mypy (`strict`, pydantic plugin), and pytest markers —
`slow` (loads ML models), `corpus` (needs the EPUBs), `net` (needs ollama or
network). The markers exist so CI can run `-m "not slow and not corpus and not
net"` on a bare checkout.

### `README.md`
Orientation for a new contributor: what the project is, why the naming problem
is hard, layout, setup, and the data-handling rule (novels not committed;
`data/gold/` holds offsets, not text).

### `architecture.md`, `details.md`
This documentation pair. Architecture is the conceptual model; details is the
per-file map.

### `plans.md`
The original design document. Treated as the specification — section numbers
are cited throughout the code (`plans.md §4.3`, non-negotiable #5, etc.) so any
reader can trace a line of code back to the decision that motivated it.

---

## `packages/core/` — the graph

Imports **nothing** from the pipeline. Enforced in CI, because "generation
pipelines do not need to understand the novel" is a claim the paper makes.

### `src/echotales/core/enums.py`
Every controlled vocabulary. Deliberately not bare strings — several carry
behaviour that would otherwise be duplicated at call sites.

| Enum | Purpose | Notable members / properties |
|---|---|---|
| `TargetKind` | `SELF` vs `PERSONA` | decides where an attribute routes |
| `AliasType` | the §4.1 typology | `.enters_graph` is `False` only for `GENERIC_DESCRIPTOR`; `.is_transfer_eligible`; `.is_speaker_relative` |
| `SpanType` | the 8 span kinds | `.is_renderable_visually` excludes `NARRATION_EXPOSITION` — kept in audio, skipped in panels |
| `ReferenceMode` | is the mention physically present? | `.is_physically_present` gates panel casting |
| `TruthStatus` | `TRUE`/`CLAIMED`/`CONTESTED`/`FALSE`/`UNKNOWN`/`FABRICATED`/`INFERRED` | `FABRICATED` = invented wholesale, not impersonating a real person |
| `AssertedBy` | provenance of a claim | narrator / character / rumour / system window / inference |
| `SegmentType`, `NarrativeLayer`, `Canonicity` | segmentation vocabulary | `VOIDED` keeps facts queryable, just off-canon |
| `BlockType` | Phase 0 output | `.is_story_content` filters out author/translator notes and nav junk |
| `EventType` | the append-only log vocabulary | **`RETRACT` and `CLOSE_INTERVAL` are separate members on purpose** |
| `Decision` | `LINK`/`NEW`/`DEFER` | the three-way gate |
| `Prominence` | `PRINCIPAL`/`RECURRING`/`INCIDENTAL` | generation budget per entity |
| `Provenance` | `MACHINE`/`HUMAN_VERIFIED`/`HUMAN_AUTHORED` | keeps silver and gold distinguishable |
| `AttributionMethod`, `ResolutionMethod` | which tier produced an answer | feeds the escalation-ladder metric |

Also defines `OBSERVER_READER` and `OBSERVER_SYSTEM`.

### `src/echotales/core/interval.py`
The fuzzy temporal interval and its three-valued algebra. Small file, and the
one most worth reading closely.

- `Certainty` — `CERTAIN` / `PLAUSIBLE` / `EXCLUDED`. `__and__` combines
  independent constraints and takes the *weaker* value, so a story-time check
  AND a knowledge-time check compose correctly. `.is_possible` is "anything but
  excluded".
- `FuzzyInterval` — frozen model of `from_lb/from_ub/to_lb/to_ub`. The
  validator rejects inverted bounds and any interval that could never be
  non-empty.
- Constructors carry the semantics:
  - `point_known(start, end)` — both endpoints attested.
  - `open_ended(start, last_evidence=…)` — **`to_lb` is the last evidence, not
    the start.** This is the decay property: a fact attested once at chapter 20
    is only PLAUSIBLE at chapter 400, because in this genre the title has very
    likely changed hands. Reporting CERTAIN there is the fabricated precision
    the whole model exists to prevent.
  - `since_before(first_evidence)` — start unbounded below. This is the reveal
    shape, and it is what lets a chapter-200 disclosure bind a fact back to
    chapter 1 without contradicting the first-attestation prior.
  - `unbounded()` — no temporal claim at all.
- `with_evidence_through(pos)` — re-attestation grows the certain zone.
  Monotonic; never moves evidence backwards.
- `contains(pos)` / `overlaps(other)` — the three-valued predicates.
  `overlaps` drives the co-presence signal in the resolver.
- `with_end(lb, ub)` — the `close_interval` operation. Explicitly *not*
  retraction; the docstring says so because the two are easy to conflate.

### `src/echotales/core/models.py`
Pydantic v2 models for every table in §5.

- `DiscoursePosition` — `(chapter, offset)`, total order, with comparison
  operators and `as_sortable()`/`from_sortable()` for SQL indexing.
- `Block`, `Chapter` — Phase 0 output. `Block.italic_ranges` preserves source
  emphasis (an independent inner-monologue signal that only survives because
  ingestion is EPUB-based); `Block.system_fields` holds parsed
  `SYSTEM_WINDOW` key-values. `Chapter.number` is a `float` so split chapters
  (45.1) are representable.
- `Span` — a classified span with speaker, `co_speaker_self_ids` (joint
  attribution is a first-class outcome) and `delivery_markers`.
- `NarrativeSegment` — the discourse-span → story-span mapping.
- `Self`, `Persona`, `SelfPersonaBinding` — the entity split.
- `TemporalFact` — base class carrying `timeline_id`, `interval`,
  `learned_at_pos`, `observer_id`, `asserted_by`, `truth_status`,
  `retracted_at`, `evidence`, `confidence`. Subclassed by `AliasBinding`,
  `Attribute`, `Relation` so every fact is uniformly time- and
  observer-scoped.
- `AliasBinding` — has a `model_validator` that **raises on
  `GENERIC_DESCRIPTOR`**. Non-negotiable #4 enforced at the type level rather
  than by convention, so no call site can persist one by accident.
- `Mention`, `Observation`, `ResolutionEvent`.
- `EvidenceVector` + `FEATURE_ORDER` (all 10 signals) and **`SCORED_FEATURES`**
  (the 5 actually fed to the model). The other three are hard pre-filters /
  blockers — see `resolve/score.py::prefilter`. Ordering is frozen so weights
  stay aligned across runs.
- `Candidate`, `ResolutionOutcome`, `StateOfResult`.

### `src/echotales/core/store.py`
SQLite persistence. Schema as a single `executescript` string; WAL mode;
foreign keys on.

Design commitments:
- **The event log is append-only.** `resolution_event` is never updated or
  deleted, so any state is reconstructable by replay and a bad chapter-40
  decision is auditable from chapter 190. `seq` is `UNIQUE`.
- **Facts are closed, never deleted.** `close_alias_interval` moves the end
  bounds; `retract_alias` sets `retracted_at`. Two methods, matching the two
  event types.
- `iter_chapters()` is a **generator**. The machine has ~4.5 GB free RAM and a
  500-chapter novel's parsed blocks will not fit alongside an NER model.
- `normalize_alias()` only casefolds and squashes whitespace. Honorific
  stripping is deliberately *not* done here — that is a scoring concern, and
  normalising it at the index level would silently merge "Elder Wang" and
  "Wang", destroying evidence the scorer needs.
- `find_alias_bindings()` returns **all** holders, unfiltered by time. Alias →
  target is one-to-many; hiding the ambiguity here would defeat the resolver.
- Infinities round-trip through `REAL` columns; noted in a comment because it
  looks like a bug worth "fixing".
- `llm_call` table — every routed call with tier, model, escalation reason,
  tokens, latency. Evaluation data, not telemetry. `escalation_stats()`
  aggregates it.
- `derived_artifact` + `invalidate_by_facts()` — read-set intersection.

### `src/echotales/core/readset.py`
Read-set tracking for incremental invalidation.

- `CacheTier` — `TEXT` / `GRAPH` / `RENDER`, with
  `.invalidated_by_graph_events` false only for `TEXT`.
- `fact_ref()` and friends build **string** references rather than integer row
  ids, so read sets survive a database rebuild in which autoincrement ids would
  shift.
- `hash_read_set()` sorts before hashing (blake2b, 16 bytes), so two artifacts
  that read the same facts in different orders share a digest.
- `ReadSetRecorder` — context manager threaded through `state_of`.

### `src/echotales/core/state.py`
`state_of()` — the central query. Four filters compose:

1. **Story-time containment** — via the fuzzy algebra, scoped to a timeline.
   Mismatched timelines return `EXCLUDED` rather than being compared, because
   cross-timeline ordering is a partial order and comparing would invent an
   ordering the text never gave.
2. **Knowledge time** — `learned_at_pos <= knowledge_pos`. `observer_scope()`
   returns `None` (= all) only for `SYSTEM`; a character observer sees only
   facts recorded for them and **does not inherit reader knowledge**.
3. **Truth status** — with the subtlety that a fact carrying `retracted_at` is
   governed by *position alone*: visible before the reveal, hidden after. The
   standalone `FALSE` filter must not also fire for it, or the observer's past
   belief gets erased. (This was a real bug the tests caught.)
4. **Canonicity** — `VOIDED` timelines excluded.

Other notes:
- `knowledge_pos` defaults to `chapter=int(position)` **only on
  `MAIN_TIMELINE`**, where the default segmentation sets `story_seq = chapter
  index`. Inside a dream that identity does not hold, so the default there is
  "unbounded". (Also a real bug the tests caught.)
- Attributes resolve last-learned-wins per key, so a character described
  black-haired at ch 3 and white-haired at ch 150 renders correctly at each.
- `persona_ids` is a **list** — concurrency is legitimate and is how clones and
  simultaneous disguises are represented.
- `resolve_alias()` returns *all* temporally valid holders with their
  certainty. A candidate-set filter, never a resolver.
- `concurrent_personas()` supports suppressing the co-presence penalty for
  clones.

### `tests/test_interval.py`
34 tests. Hypothesis strategies generate well-formed intervals; properties
cover totality, that `CERTAIN` implies containment in the widest extent, that
widening bounds never strengthens certainty, and that overlap is symmetric.
Named cases cover the decay property, re-attestation, and fuzzy-end transfer.

### `tests/test_state.py`
40 tests organised as **one class per row of the §3 case table**: ordinary
character, reincarnation, body swap, clone/avatar, possession, sustained
disguise, dream persona. Plus transferable titles, retraction-vs-interval-end,
knowledge time, voided spans, attribute routing, certainty propagation, and
store mechanics (event log, invalidation, read sets).

The headline test is
`TestSustainedDisguise::test_the_two_views_differ` — one query, differing only
in observer, returning different alias sets.

---

## `packages/pipeline/` — ingest, resolve, evaluate

### `src/echotales/pipeline/cli.py`
`argparse` entry point exposing `run`, `ingest`, `resolve`, `review`,
`query state-of`, `eval`, `export`, `webview`, `webview-server`. Kept
importable with **no optional dependencies installed** so `--help` works on
a bare checkout; the heavy import happens inside `main()`.

`webview` takes `--format {static,react}` (default `static`) and repeated
`--source DB_PATH:NOVEL_ID[:LABEL]`. `webview-server` takes the same
`--source` shape plus `--host`/`--port` (default `127.0.0.1:8787`) and has
no format flag — it only ever serves the live, correctable payload.

### `src/echotales/pipeline/commands.py`
Dispatch layer behind the CLI, one function per verb.

`cmd_run` builds a single `ModelClient` for the whole run
(`_build_client`) and threads it into every stage that can use one, rather
than each stage constructing its own — preflighted once before the first
chapter, so a missing/oversized model fails immediately instead of at
chapter 140. Returns `None` on the `stub` backend rather than a stub
client: a stub client would make a stage take the model-backed code path
and get canned answers, which would print as a working LLM run without
being one.

`cmd_webview`/`cmd_webview_server` parse the repeated `--source` flag
(`DB_PATH:NOVEL_ID[:LABEL]`, split on `:` with `maxsplit=2` so a Windows
drive-letter path would still break — not hit yet on this project's
platforms) and hand a list of `NovelSource` to `webview.py`/
`webview_server.py`.

### `src/echotales/pipeline/config.py`
`Settings` via pydantic-settings, prefix `ECHOTALES_`, reading `.env`.

`LLMMode` is the switch that matters: `stub` / `local` / `api` / `hybrid`.
Also holds `escalation_confidence_threshold` (0.75),
`max_escalations_per_run` (a hard ceiling so a misconfiguration cannot turn a
600-chapter job into an unbounded API bill), `window_size` (40 chapters per LLM
window) and `conformal_alpha` (0.05).

### `src/echotales/pipeline/llm/base.py`
Provider protocol. Every call site requests **structured output validated by a
Pydantic schema**, never free text — an unparseable answer must fail loudly at
one call site rather than silently corrupt a downstream heuristic, and a
validated schema is what makes a 7B local model and an API model genuinely
interchangeable.

Providers never retry or fall back on their own; that is the router's job, so
every escalation is recorded in one place.

`extract_json()` is more forgiving than it first looks, deliberately: it tries
raw text, then a fenced block, then the outermost brace-balanced span (tracking
string state so a `}` inside a string does not terminate it). Small local models
wrap JSON in prose far more often than large ones, and rejecting those would
inflate the escalation rate with purely cosmetic failures — distorting the very
metric the ladder exists to report. Text that already starts with `{` is handed
straight to pydantic, whose error message is better than anything re-derived
here.

### `src/echotales/pipeline/llm/stub.py`
Deterministic canned responses. Makes CI able to exercise Phases 1–6 with no
GPU, no model download and no network, and makes resolver tests independent of
a language model's mood.

`_empty_for_schema()` builds the most conservative instance a schema accepts —
the stub **declines rather than guesses**. If it invented plausible answers, a
"no LLM configured" bug would surface as quietly wrong output instead of as
itself.

### `src/echotales/pipeline/llm/ollama.py`
The bulk tier. Passes the JSON Schema to ollama's `format` parameter
(constrained decoding) *and* renders it into the prompt — constrained decoding
fixes syntax, not comprehension. Long default timeout (180 s) on purpose: a
spurious timeout would escalate an answerable case to the paid tier and skew
the report.

### `src/echotales/pipeline/llm/anthropic.py`
The escalation tier. Imported lazily so a checkout without the optional
`anthropic` extra still runs in `stub` or `local` mode. Prefills an opening
brace in the assistant turn to suppress preamble.

### `src/echotales/pipeline/llm/router.py`
**The escalation ladder — a measurement instrument, not plumbing.**

`EscalationReason` is an enum, not free text, so the report can group by cause:
`LOCAL_UNAVAILABLE`, `LOCAL_PARSE_FAILURE`, `LOW_CONFIDENCE`,
`CALLER_REQUESTED`, `BUDGET_EXHAUSTED`.

Every call is logged including the ones that never escalate — a rate is
meaningless without its denominator — and a *failed* local attempt is logged
before its escalation, so the stats cannot overstate how well the cheap tier
performs.

`force_escalate` is how the resolver says "the conformal gate already returned
DEFER on this one", which is the highest-value use of the expensive tier. If
the API tier fails, a usable local answer is preferred over raising.

### `src/echotales/pipeline/ingest/epub.py`
EPUB container reading over `zipfile` + `lxml` rather than a reader library —
the parts needed (spine order, TOC labels) are a few lines of XPath, and a
reader library would normalise away exactly the per-source quirks the adapters
exist to handle.

**The TOC is the authority on chapter identity, never the filename.** The RI
export names Chapter 1 `page-0.html`. `_find_opf()` falls back to scanning for
a `.opf` when `META-INF/container.xml` is absent, which that same export needs.

`parse_chapter_label()` handles `Chapter 45.1` (split chapters stay floats, so
45.1 never collapses onto 45) and flags side stories / interludes as
unnumbered rather than defaulting them to 0, which would collide them into the
main sequence.

### `src/echotales/pipeline/ingest/classify.py`
Block-level classification. Deterministic and conservative: anything not
clearly special stays `PROSE`, because a false `NON_DIEGETIC` silently deletes
story content while a missed one only adds noise.

`SYSTEM_WINDOW` detection requires a bracket or a system keyword **and** at
least two `Key: Value` lines. Being strict matters — misreading dialogue as a
stat block would inject fabricated attributes at the highest-confidence tier in
the pipeline.

`_APPENDIX_HEADINGS` covers the publisher back matter. These are excluded
because they describe *end-of-volume* state; letting them in would hand the
reader knowledge they do not have yet and defeat the knowledge-time model.

DIALOGUE vs PROSE is deliberately **not** decided here — a paragraph routinely
mixes a spoken line with its narration, so that is a Phase 1 span-level call.

### `src/echotales/pipeline/ingest/adapters/`
- `base.py` — `SourceAdapter` ABC, HTML walking, and `ChapterRange`
  (inclusive at both ends, float-valued so split chapters fall in naturally).
  `extract_block()` flattens an element to text while recording **emphasis
  character ranges**, re-mapped onto the whitespace-normalised string so the
  offsets stay valid against what is actually stored. `<hr>` becomes a `* * *`
  scene-break marker — free evidence for Phase 2.

  Back matter latches only *after* the first real chapter has been seen.
  Several appendix headings ("Table of Contents", "Front Cover") also appear as
  front matter, and latching on those skipped the entire novel — a real bug the
  tests now pin down.
- `lightnovelworld.py` — RI. Narrows to `div.chapter-ugc` and drops the
  repeated bold title paragraph (only within the first two blocks, so a
  mid-chapter cross-reference is not deleted). Left in, that paragraph
  manufactures a context-free mention at offset 0 in every chapter whose title
  names a character.
- `calibre.py` — LOTM. Drops the leading `<h1>` (the TOC already carries the
  title). The `<i class="calibre6">` inner-monologue markup is handled by the
  base extractor.
- `generic.py` — fallback for an unfamiliar EPUB; the intended first step when
  adding a novel.

### `src/echotales/pipeline/ingest/sources.py`
Loads `data/sources.toml` into `SourceConfig`. Registering a novel is a config
block naming an adapter, a path and a chapter range — never a code change.

### `src/echotales/pipeline/ingest/normalize.py`
Romanization normalization and translator-handoff detection.

`normalize_romanization()` folds case, diacritics, internal punctuation and
**all** whitespace, so "Shi-Cheng" / "Shi Cheng" / "ShiCheng" collapse. Removing
spacing entirely is aggressive on purpose — Chinese given names are romanised
with inconsistent word breaks that carry no information — and is therefore
applied per-source rather than globally.

The normalised form is a **matching key, never a display form**. The original
surface string is always what gets stored and shown.

`detect_translator_handoffs()` looks for a batch of surface forms that vanish
and are simultaneously replaced by romanization *variants of themselves* at one
chapter boundary (threshold 20, per plans.md). One name changing is noise;
twenty changing together is a new translator — and to an entity resolver that
looks exactly like a cast of new characters arriving at once, which is why it
is detected explicitly. Adjacent detections are collapsed so one handoff is not
reported several times.

### `src/echotales/pipeline/ingest/runner.py`
Phase 0 orchestration. Streams chapter by chapter, committing in batches, so
nothing accumulates a whole novel in memory.

`ingest_config()` honours `config.chapters` unless the caller overrides it —
ignoring it silently ingested all 500 chapters of a novel configured for 199
(another bug the tests caught). `_find_gaps()` reports chapters the range asked
for but ingestion did not produce; a silently skipped chapter is a hole in the
discourse timeline that makes every downstream position subtly wrong rather
than obviously broken.

**Measured on the real corpus:** RI 1–199 → 199 chapters / 16,360 blocks / 499
emphasis blocks in 3.0 s. LOTM 1–213 → 213 chapters / 16,670 blocks / **1,325**
emphasis blocks in 3.2 s. No gaps in either.

### `tests/test_llm.py`
33 tests: JSON extraction from messy model output, stub behaviour, and every
router branch — confident-local-kept, low-confidence escalation, unavailable
and parse-failure escalation, `force_escalate`, API-failure fallback, budget
exhaustion, and the accounting invariants.

### `tests/test_ingest.py`
57 tests. Synthetic EPUBs are built in a temp dir (`build_epub()`) so CI needs
no corpus; tests against the real files are marked `corpus` and skip when
`data/raw/` is empty.

### `src/echotales/pipeline/spans/delivery.py`
Delivery-marker extraction. ~90 markers across six polarities: `FLAT`,
`HEIGHTENED`, `HUSHED`, `COLD`, `WARM`, `HESITANT`.

`dominant_polarity()` gives `FLAT` absolute precedence — non-negotiable #10.
The canonical case is a protagonist described "expressionless" during the most
violent scenes: a scene-level sentiment model reads the carnage and assigns a
dramatic voice, which is exactly wrong, because the contrast between the
flatness and the carnage *is* the characterisation. A majority vote or an
average would let the surrounding drama back in through the side door.

Alternation is ordered longest-first so "in a low voice" is not reduced to
"low".

### `src/echotales/pipeline/spans/classify.py`
Phase 1. Splits blocks into spans and types each one.

Three signals, in decreasing reliability: quotation marks, **source emphasis**,
attribution verbs. Emphasis is trusted above everything else — the translator
marked it explicitly, whereas every other cue is inference.

`split_block()` splits at **both quote and emphasis boundaries**. That emphasis
is a boundary rather than a span attribute was a real bug: translated volumes
put an italicised thought and its trailing narration in one paragraph, so
quote-only splitting yields a single span in which the emphasis covers 13–44%
of the text and fails any coverage threshold — discarding the exact signal that
motivated ingesting EPUB over PDF. Fixing it moved `INNER_MONOLOGUE` from 2.7%
to 14.1% (RI) and 2.1% to 5.6% (LOTM).

`_is_quote_open()` / `_find_closer()` keep a mid-word apostrophe from opening or
closing a quote, and let an unterminated quote run to end-of-block (the normal
shape of a multi-paragraph speech).

`_promote_crowd_runs()` re-types short exclamations only when three or more
appear in a run. One "Impossible!" beside a named speaker is that speaker's
line; three unattributed in a row is a crowd, and forcing a speaker onto each
would invent three attributions from nothing.

Thought verbs include the "said in his heart" calques, which are the
highest-yield members of the set in translated Chinese web fiction.

**Measured:** RI 21,297 spans / 199 ch; LOTM 23,540 / 213 ch (~107–111 per
chapter).

### `src/echotales/pipeline/segment/markers.py`
Rule-based boundary markers: dream entry/exit, flashback entry/exit, vision,
time skip, scene break.

Confidences are deliberately uneven. Dream entry is formulaic **in the one
novel here that uses dreams at all** — it is not a genre feature, and
`MarkerSet` keeps the detector opt-in per novel. Where present, the formula
("his vision changed") and scores 0.85; flashback openers score 0.5 because
"years ago" appears in ordinary dialogue constantly and must never mint a
timeline on its own.

### `src/echotales/pipeline/segment/detect.py`
Builds `NarrativeSegment` rows from markers.

Default is **one chapter → one MAIN segment, `story_seq = chapter index`**,
which reduces the whole temporal apparatus to naive behaviour on a linear
novel. Overrides need `confidence >= 0.7` (`PROMOTION_THRESHOLD`) and a span of
at least `MIN_SEGMENT_BLOCKS` (3) — "he recalled that day" mid-fight is a
sentence, not a flashback.

`_timeline_id()` keys each derived timeline by chapter *and* ordinal, so two
dreams never share one. Sharing would let entities from unrelated dreams be
compared on a coordinate system they never shared.

An unterminated layer runs to end-of-chapter: that is the normal shape for a
dream continuing into the next chapter, and closing it early would strand its
cast on the main timeline.

`find_time_skips()` is separate from segmentation. A skip does not branch the
timeline; it marks a gap of unobserved change, so a character who returns
stronger reads as elapsed time rather than as a contradiction.

### `src/echotales/pipeline/segment/llm_pass.py`
**One call per chapter, and only for chapters the rules found ambiguous.**

`needs_llm_pass()` returns true only when suggestive evidence exists that did
not clear the threshold — a linear chapter gets no call, and a confidently
marked one was already resolved. On the real corpus that gates ~44% of
chapters, ≈2.8 min locally.

`_block_digest()` sends block index plus first/last words per block, **not full
chapter text**: it keeps the prompt inside an 8k context on an 8 GB card and
keeps the model's attention on structure rather than plot.

### `src/echotales/pipeline/segment/runner.py`
Phase 2 orchestration. Rule segments win on overlap with model proposals — the
rules fire on explicit formulae and are higher precision.

Time-skip event ids carry block index *and* ordinal: `Marker.offset` is a
character position within its block, so two skips in different blocks collide
without it (a real `UNIQUE constraint failed` bug).

**Measured:** RI 200 segments / 199 ch (1 dream, 65 time skips); LOTM 217 / 213
(3 dreams, 8 skips). Detection *recall* is unverified — distinguishing a missed
dream from a genuinely rare one needs the gold set.

### `src/echotales/pipeline/mentions/lexicon.py`
Per-novel vocabulary. Different novels use different systems — Sequence vs
Rank, Pathway vs Cultivation Path — so lexicons are per-source, seeded per
genre and **grown while reading** (`learned_names`).

The transferable-title list must ship on day one: it cannot be learned from the
text, because the first holder of a title is textually identical to the second.
Only prior knowledge that a title *is* transferable makes the distinction
available at all.

`is_progressive_rank()` / `strip_rank()` handle the case that is far more
common than true transfer: "Golden Core Elder Wang" → "Nascent Soul Elder Wang"
is one person advancing. Reading it as a transfer splits one character in two.

### `src/echotales/pipeline/mentions/gazetteer.py`
**The compound-interest mechanism.** Aho-Corasick over confirmed aliases,
rebuilt at window boundaries. Aho-Corasick specifically because the alias set
reaches thousands of entries and every chapter is scanned against all of them —
it matches every pattern in one pass regardless of pattern count.

`_fold()` casefolds and strips spacing/punctuation while keeping an **offset
map**, so "FangYuan" matches "Fang Yuan" yet the stored span still points at
the surface form the reader sees. Without the map, normalised matching would
make every offset unusable downstream.

`_is_boundary()` checks the *original* text: folding removes spaces, so "Li"
would otherwise match inside "Lian". `_resolve_overlaps()` keeps the longest
match, so "Sect Master Wang" is not reduced to "Wang".

`add()` refuses `GENERIC_DESCRIPTOR` outright — admitting one here would
reintroduce the largest class of false matches through the cheapest,
highest-trust path in the pipeline.

**Measured hit rate by window** (the compounding curve):
RI 55→62→65→64→63%; LOTM 23→28→28→31→35→33%. LOTM is the cleaner
demonstration; RI plateaus, consistent with a cast introduced early.

### `src/echotales/pipeline/mentions/ner.py`
Layer 1. `GlinerDetector` is the intended path (zero-shot, so it handles
invented entity types like "Gu Master"), loaded lazily and `lru_cache`d because
the model costs seconds and hundreds of MB.

`HeuristicDetector` is the fallback when the `ml` extra is absent, and is
genuinely useful rather than a placeholder — these translations capitalise
personal names consistently. It **trims** leading stopwords rather than
dropping the span, so "Then Fang Yuan" yields "Fang Yuan". Recall is favoured
over precision: layer 2 supplies precision, and a mention never detected can
never be recovered.

`get_detector()` degrades silently — a missing optional dependency should cost
recall, not stop the run.

### `src/echotales/pipeline/mentions/alias_type.py`
Assigns `AliasType` at detection time, which is what makes the resolver
tractable.

**Precedence is load-bearing.** Deictics are decided *before* the generic
branches, because the two overlap textually and only the determiner separates
them: "this old man" is a character referring to themselves; "the old man" is a
scene-local descriptor — same head noun, opposite handling. Likewise a form
used as direct address is relational even when its head is an ordinary role
noun ("Master, I have returned"). Both were real ordering bugs.

`_EPITHET_MARKERS` separates "the Crimson Emperor" (epithet, a specific holder)
from "the innkeeper" (descriptor, scene-local).

### `src/echotales/pipeline/mentions/parenthetical.py`
The three readings of a parenthesised name, each with a different consequence:
translator gloss (one entity, two surface forms), simultaneous-action shorthand
(two entities — merging them destroys a character), and identity disclosure
(one self, two personas, alias marked `FABRICATED`).

Ordering matters: the gloss check runs first because a romanisation variant is
detectable with no world knowledge, while the other two need to know whether
both names are already established separately.

`_close_keys()` tolerates exactly **one** character of difference — translators
differ by a vowel far more often than two distinct characters collide, but the
tolerance has to stop there or genuinely different names merge.
`_shares_surname()` argues *against* disclosure: a shared leading token means
relatives, not one person behind a disguise. `_trim_leading_stopwords()` keeps
"Then Wu Yi Hai" from being captured as a name.

### `src/echotales/pipeline/mentions/runner.py`
Merges the layers with the **gazetteer winning on overlap** — an exact match on
a confirmed alias is higher-precision evidence than a statistical span, and it
carries a target id the NER span lacks.

`_reference_mode()` maps span type onto physical presence. A name spoken inside
dialogue becomes `DIALOGUE_REFERENCE`, not `PRESENT`: without this a chapter
that merely *names* nine characters produces a panel containing nine, most
absent or dead.

**Measured (deterministic, pre-LLM):** RI 28,646 mentions / 199 ch (611-entry
gazetteer, 75 generics dropped); LOTM 31,775 / 213 ch (789 entries, 523
dropped). ~7–9 s per novel.

**Superseded as the default path by `chapter_ner.py`** (below): when a
`client` is passed, layer 1 becomes a two-step pass instead of pure
capitalisation matching. Measured on RI vol 1 with the LLM path:
1,862 → 82 entities, 47% → 20% singleton rate. `detector_name`,
`llm_calls`, `llm_surfaces`, `llm_rejected` on `MentionReport` distinguish
which path a given run actually took — never assume from the code alone
that a run used the model.

### `src/echotales/pipeline/mentions/chapter_ner.py`
Layer 1's LLM path. **Never asks the model where a mention is** — only,
once per chapter, which surface forms in the chapter are names — and the
returned vocabulary (`VocabularyDetector`) is matched over spans with the
same Aho-Corasick machinery `gazetteer.py` already uses. Per-span prompting
is 34.5h against this corpus by the measured 1.9s/call budget; per-chapter
is ~35 min for 199 chapters, and offsets stay exact instead of being
hallucinated back as character positions by the model.

`NameCache` keys on a hash of the chapter text plus the model name, and
flushes on the same `commit_every` cadence as the store commit — it used to
flush only once, at the very end, and an interrupted 199-chapter run lost
the whole run's GPU work with nothing written yet. `plausible_name()`
rejects the concrete failure modes actually observed from a small local
model: whole copied sentences, punctuation-bearing fragments, wholly
lowercase returns (this corpus's translations capitalise names without
exception, so a lowercase return is a paraphrased description).

### `src/echotales/pipeline/mentions/commonness.py`
Separates a capitalised common noun (a role word, an item name, a
power-scale term) from a personal name using **determiner and plural rate**,
measured from the corpus itself — capitalisation alone cannot, since both
run near 0% lowercase in this content. `CommonnessProfile` retains the
casefolded corpus text so a surface the LLM path proposes *after* the
profile was built can still be measured on demand
(`is_common_noun`/`measure`); without this, an LLM-discovered surface (the
seed list never contained it) silently skipped the filter entirely, which
is how "Grandpa" became an entity before possessive pronouns were added to
`_DETERMINERS`.

`credit_surfaces()` catches translation-group names specifically: a
character occasionally appears near the word "translator", a translation
group's name essentially always does, so a high co-occurrence rate with
credit vocabulary is the signal, not a fixed name list.

### `src/echotales/pipeline/speakers/attribution.py`
Phase 4, four-tier ladder: explicit → proximal → turn-taking → contextual.

**Tier 1** checks the *following* text before the preceding text. `"…," X said`
is far more common than `X said, "…"` in this prose, and checking the wrong
side first picks up the previous line's speaker.

**Tier 2** takes the **last** name before the line, not the first. This is the
split-sentence case plans.md names: in "Wu Liao excused himself, but Wu An
hesitated and said softly:" the speaker is Wu An — proximity is measured
outward from the quote.

**Tier 3** applies only when the recent history holds exactly two distinct
speakers. With three or more the alternation assumption is unfounded, and a
confident wrong answer is worse than deferring.

`_known()` matches on the honorific-stripped comparison key, not string
equality. Exact matching rejected "Wang" against a recorded "Elder Wang" and
cost ~13 points of coverage.

Two outcomes are first-class results, not failures: `JOINT` (forcing one
speaker discards the other) and `UNATTRIBUTED_CHORUS` (attributing a crowd to
whoever spoke last invents attributions that propagate into voice casting).

`detect_pov_holder()` uses inner-monologue proximity rather than first-person
pronoun density — this content is overwhelmingly third-person limited, so the
POV holder is whoever the narration reports thoughts *for*, not whoever says
"I".

### `src/echotales/pipeline/speakers/runner.py`
Windows reach into **adjacent blocks**, with in-block narration placed nearest
the quote (it is stronger evidence). ~15% of speech spans occupy a paragraph of
their own with the attribution in the neighbouring block; a block-local window
made those unattributable no matter how explicit the text was.

The name roster **accumulates across the novel** rather than being rebuilt per
chapter — a character introduced in chapter 5 still speaks in chapter 12
whether or not the detector re-fired on them there.

`recent_speakers` resets at chapter boundaries **and scene breaks**, and only
`EXPLICIT`/`JOINT` results seed it: seeding alternation from a guess makes the
next guess worse.

**Measured:** RI 54.0% coverage (904 explicit, 624 proximal, 590 turn-taking,
698 POV, 273 chorus); LOTM 74.1% (2134 / 1180 / 961 / 1709 / 332). Both were
~11–14 points lower before the adjacent-block window and accumulated roster.

**Known gap:** 26–46% remain `UNRESOLVED`, well above the 2–5% deferred slice
plans.md anticipates. A large share are pronoun subjects ("he said"), which
Phase 5 local anaphora is expected to recover; tier 4 was deliberately not
over-engineered ahead of that feedback.

`_assign_anonymous_slots()` runs after the ladder, over what it left
`UNRESOLVED`, for `DIALOGUE` spans only. Turn-taking alternation between a
small cap of chapter-scoped slots (`_MAX_ANON_SLOTS = 4`) -- never a `Self`
row, deliberately: downstream synthesis needs two different unattributed
lines to sound different far more often than it needs to know who either
of them is, and minting an entity for a background speaker who may never
be named again clutters the reviewed cast for no benefit. New
`AttributionMethod.ANONYMOUS_SLOT` is excluded from `report.attributed`,
which keeps its original meaning ("linked to a known identity"). Measured
on RI vol 1 (post-LLM-layer-1 numbers, chapter counts differ from the
54.0%/74.1% figures above which predate that change): 2,930 lines given a
distinct anonymous voice out of 5,725 total, coverage unaffected
(48.8%, same value with or without the anonymous-slot pass, confirming it
never leaks into the tracked metric).

### `src/echotales/pipeline/anaphora/local.py`
Phase 5. **Not clustering** (non-negotiable #1) — every link is made by a rule
that can be named, and anything without a nearby antecedent is left alone.

`resolve_pronoun()` considers only mentions *before* the pronoun (cataphora is
rare here and admitting it roughly doubles the candidate set), within 600
characters, and only rigid names. It returns `None` rather than guessing when
nothing agrees — precision over recall (#9) in practice. A *unique* agreeing
antecedent scores higher than the nearest of several.

`infer_gender()` is used only to **reject** incompatible antecedents, never to
assert an attribute: a wrong guess should cost a missed link, not a fabricated
fact about a character. Unknown gender is compatible with everything, or recall
collapses.

`present_cast()` filters on `reference_mode`, so a character merely named in
dialogue is not counted as being in the scene.

### `src/echotales/pipeline/anaphora/validate.py`
Where precision comes back. A violating group is **split, not repaired** —
guessing which half was right trades a detectable error for a silent one, and
splitting is done by surface form because that was the grouper's only evidence.

`_segment_for()` compares **block indices**. `Mention.offset` is a character
offset within its block, while segment bounds are block indices; comparing the
two made most mentions match no segment, and the resulting empty timeline split
against `MAIN_TIMELINE` produced **2,007 phantom layer-boundary violations on
RI alone**. `Mention.block_index` was added to fix it, and an unsegmented
mention now defaults to `MAIN_TIMELINE` rather than to a distinct unnamed one.

`check_co_presence()` accepts `concurrent_personas` and suppresses the split
for them. Clones, soul avatars and sustained parallel disguises are *expected*
to co-occur — this suppression is exactly why the penalty is defined between
personas and never between selves.

### `src/echotales/pipeline/anaphora/runner.py`
Also feeds pronoun resolutions **back into Phase 4**. Attribution deliberately
leaves "he said" unresolved rather than guessing; once the pronoun has an
antecedent the line becomes attributable, which is why the phases run in
sequence. The recovered confidence is discounted ×0.8 because it is a two-step
inference (pronoun → antecedent → speaker).

**Measured (after the block-index fix):** RI 9,671 groups, 23,139 pronoun
links, **4** splits; LOTM 12,260 groups, 27,558 links, **13** splits. The split
counts now square with segmentation having found 1 and 3 dream segments.

**Feedback into Phase 4 coverage:** RI 54.0% → **73.4%**; LOTM 74.1% → **82.8%**.

### `src/echotales/pipeline/resolve/` — Phase 6

**`retrieve.py`** — `EntityProfile` accumulates aliases, context terms and
speech partners per entity. `BM25Index` is hand-rolled (one short document per
entity; the tuning that matters is tokenisation, not the ranking function).

`retrieve()` scores the **BM25 shortlist plus the most prominent entities**,
not every profile. Scoring all profiles made it O(groups × entities): 7.5
ms/group at 20 chapters rising to 15.3 at 40, timing out before a full volume.
The prominent-entity tail is retained deliberately — a disguise identity shares
no surface form with its holder and would never reach the BM25 shortlist, so
dropping it would make the flagship case unretrievable. Residual growth remains
(the per-group re-sort); cache the ranking at window boundaries.

**`evidence.py`** — builds the evidence vector. `jaro_winkler` is used over
edit distance because romanised variants of one name agree at the prefix and
drift at the end.

**`score.py`** — **five** scored features, not ten:
`surface_similarity`, `context_embedding_similarity`,
`speech_partner_compatibility`, `temporal_validity`,
`first_attested_soft_prior`.

`prefilter()` handles the three that were removed from scoring:

| Signal | Verdict |
|---|---|
| `co_presence_violation` | BLOCK |
| `temporal_validity == 0` | BLOCK |
| `declaration_match` | FORCE_LINK |
| `gazetteer_exact_match` | FORCE_LINK |

Blockers are evaluated before force-links: a co-present pair that also matches a
declaration is more likely a detector error than a real identity.

**This fixed a live blocker.** As a scored feature at weight 2.5,
`gazetteer_exact_match` drove probability to 0.957 unaided; since every link
grows an entity's alias set, each wrong link made the next easier, and 2,753
groups collapsed to **7 entities** over 40 chapters.

`SURFACE_SIMILARITY_FLOOR = 0.80` — below it, similarity contributes nothing.
Measured Jaro-Winkler between unrelated names in this corpus: Klein/Leonard
0.676, Audrey/Alger 0.630, Dunn/Daly 0.550. `DEFAULT_BIAS = -4.0` (was −2.0,
which left unrelated pairs at p≈0.77).

**Honest characterisation: a hand-tuned rule system with a learned tiebreaker
on five dense features.** Not a learned model. The rare high-weight signals are
rules precisely because they would never accumulate enough gold instances to
fit — calling them "learned" would be unearned.

**`gate.py`** — `ConformalGate` plus `DeferredQueue`. Currently *standard*
conformal; **must become Mondrian/class-conditional keyed on `alias_type`**,
because the compounding gazetteer explicitly violates exchangeability.

**`detectors.py`** — transfer / deception / reveal / death / reputation. Each
maps to a distinct event type. Note what is absent: retraction fires only when
a deception is exposed, and is deliberately not the same operation as closing
an interval.

**`wiki.py`** — entity summaries regenerated at window boundaries. The graph is
the source of truth; the summary is a cache and is never read back in.

**`adjudicate.py`** — deferred cases only, `force_escalate=True`. A returned
`target_id` outside the candidate list is treated as hallucination and
downgraded to DEFER rather than trusted.

**`runner.py`** — processes strictly in discourse order, so an entity profile at
chapter 40 contains only what had been read by chapter 40.

**Measured (LOTM, after the pre-filter fix):**

| Chapters | Time | ms/group | Groups | Entities | linked / new / deferred |
|---|---|---|---|---|---|
| 10 | 5.0 s | 7.3 | 688 | 412 | 274 / 412 / 2 |
| 20 | 10.6 s | 7.6 | 1,394 | 673 | 716 / 673 / 5 |
| 40 | 25.0 s | 9.1 | 2,753 | 980 | 1,766 / 980 / 7 |
| 80 | 63.9 s | 11.7 | 5,458 | 1,495 | 3,955 / 1,495 / 8 |

**Superseded by two later findings, both load-bearing for anyone touching
this package next:**

**The scorer cannot reach LINK at all, structurally, independent of
tuning.** `DEFAULT_BIAS = -4.0` and `gate.FALLBACK_LINK_THRESHOLD = 0.80`
were set independently and are mutually unreachable: a maximal plausible
evidence vector (surface_similarity=1.0, context=0.6,
speech_partner=1.0, temporal=1.0) scores p=0.711 through
`ScoringModel.probability()`. So **every link the system has ever made
came from `prefilter()`**, never from the scorer — which is the real
explanation for the over-splitting the table above shows, not merely
untuned thresholds. Not fixed by hand-rebalancing the bias (that is fitting
to nothing without gold); the real fix is `ConformalGate.calibrate()`
against confirmed examples once enough exist.

**`name_containment` is now a fourth pre-filter row**, added after the
above was diagnosed: one name is the other with a leading house-prefix
token dropped and a shared tail of >=2 tokens (`normalize.py`). Two
guards, both load-bearing: the >=2-token floor stops a bare shared surname
from merging unrelated people ("Elder Wang"/"Xiao Wang" must not merge on
"Wang" alone), and the short form must be a token-*suffix*, not any
substring, so the house name itself ("Gu Yue", also two tokens) doesn't
match every member of the house it prefixes. `co_presence_violation` is
suppressed when `name_containment` holds -- a chapter introducing "Gu Yue
Mo Bei" and calling him "Mo Bei" three lines later puts both surfaces in
one scene, which the raw co-presence check read as two people standing
together, firing *before* the pre-filter that would have merged them ever
got a chance.

**Measured after the LLM layer-1 change (§ mentions/runner.py above) plus
these fixes, full volumes:** RI 199 ch: 1,862 → **82** entities (47% → 20%
singleton rate). Cross-novel: LOTM 730 → 102, ORV 859 → 63 -- same regime
shift on both, i.e. the fix generalises rather than being overfit to RI's
xianxia house-prefix convention. Two known-open gaps found by that
cross-novel check and deliberately not hand-fixed: LOTM ch1 is a
reincarnation opening (Zhou Mingrui/Klein Moretti/Klein split into three
entities -- the declaration detector doesn't recognise "memories began
flooding him" as an identity-continuity assertion) and ORV's Korean
family-name-first convention drops recall on given-name-alone references
("Kim Dokja"/"Dokja" -- the >=2-token floor above is doing its job on the
surname side and costing recall on the given-name side, since a Korean
given name used alone is usually unambiguous in a small cast the way a
bare surname is not).

### `src/echotales/pipeline/eval/`

**`gold.py`** — `GoldMention`/`GoldSet`, the annotation schema. Every record
carries `Provenance` (`MODEL` vs `HUMAN`) and a `confirmed: bool` — a
model-drafted annotation is a draft, never gold, until a person confirms
it. `GoldSet.confirmed_only` is the only subset any recall/accuracy number
may legitimately be computed from; nothing in this codebase should read a
`provenance=MODEL, confirmed=False` record as ground truth.
`MentionKind.NOT_AN_ENTITY` is a first-class kind, not an absence — a
detector's false positive (a role noun, an item, a translation credit) is
itself something gold needs to be able to say, or precision has no way to
be measured at the entity-existence level, only at the coreference level.

**`retriever_eval.py`** — recall@k, the plans.md §8.2 gate: recall@10 on
`TRANSFERABLE_TITLE` below 80% means candidate retrieval is the research
problem and scorer tuning is premature. `SELF_RETRIEVAL` mode needs no
annotations and is a smoke test only (proves there's no indexing/
tokenisation bug); `GOLD` mode is the real measurement and needs
`GoldSet.confirmed_only` data that does not exist yet at any scale.

**`coref_score.py`, `draft.py`** — coreference scoring and gold-drafting
support. `data/gold/reverend-insanity-c1-c5.toml` is the first draft this
produced: 26 identities over RI ch1-5, model-drafted (an LLM reading the
source text directly, deliberately *not* reading the pipeline's own output
first, to avoid grading the system against its own guess) and explicitly
not gold until a person reviews it and flips `confirmed`.

**Not built:** MUC/B³/CEAF coreference metrics, the two baselines (long-
context LLM, dual-LLM memorisation per COLING 2025), and the ablation
harness (would cost no additional LLM calls, since it re-scores cached
evidence vectors with zeroed weights).

### Compute and cost budget

Measured baseline: **1.9 s/call** (`qwen2.5:7b`, steady state, RTX 4060 8 GB).
Batching gives no throughput gain — token generation is the bottleneck.

Scope after the reductions: **RI 199 chapters primary**, LOTM and ORV at 5
chapters each = **209 chapters** of LLM processing.

| Pass | Granularity | Calls | Local wall-clock |
|---|---|---|---|
| Lexicon induction | 12 samples × 3 novels, one-off | 36 | ~1 min |
| Layer 1 NER | per chapter | 209 | ~7 min |
| Layer 3 gap-fill sweep | per chapter | 209 | ~7 min |
| Segmentation | gated (~44% of chapters) | ~92 | ~3 min |
| Coreference | per *ambiguous paragraph* | ~2,400 | **~76 min** |
| Adjudication | deferred cases only | ~200–1,000 | 6–32 min |
| **Total** | | **~3,150** | **≈1.7–2.2 h** |

Coreference dominates and is the pass to watch: it is the only stage below
chapter granularity, and its cost scales with how often the deterministic
routes fail.

**Ablations add no LLM cost** — five ablations re-score cached evidence vectors
with zeroed weights; no re-inference.

Token estimate: ~1,500 tokens/call average (prompt + completion) × ~3,150 calls
≈ **4.7M tokens** per full run. Local: free but ~2 h of GPU. On an API backend
this is the number to price before switching `model_backend`.

**`qwen2.5:14b` is excluded by policy**, not merely unmeasured: ~9 GB of
weights against an 8 GB card guarantees CPU offload, which competes with the
pipeline for the ~4.5 GB of free system RAM it already streams chapters to stay
inside. All local models are 7-8B q4. `ModelClient.preflight()` enforces this
by measured size, so substituting a larger model fails at startup rather than
silently halving throughput mid-run.

**Generation budgets:**
- Panels: 3-chapter showcase ≈ **40 images**, chosen to demonstrate temporal
  reference sheets (one character at two story-time states).
- TTS: primary novel only ≈ **21,000 spans** (199 ch × ~107 spans/ch).

### `src/echotales/pipeline/review.py`
Assembles what a human needs to audit the graph, in three shapes for three
jobs: console table (quick sanity read), HTML (browsable, evidence inline,
for actually auditing entities), JSONL (scripting, or seeding annotation).

`EntityRow.evidence` is capped at `SNIPPET_CHARS = 110` and centred on the
mention -- enough to confirm or reject a decision at a glance, deliberately
far too little to reconstruct the source, matching the `data/gold/`
convention of offsets-plus-snippet rather than chapter text.

`ScriptLine`/`ChapterScript` are the view the entity table cannot give:
not "does Fang Yuan exist as one entity" but "line 40 of chapter 3 is
spoken by Fang Yuan" -- entity-list cleanliness and per-line attribution
coverage are different failure surfaces, and an entity list can look clean
while a third of dialogue has no speaker, invisible until the lines are
read in reading order. Rendered only for `script_chapters` explicitly
passed in, so a top-200-entity review never materialises the whole novel.

### `src/echotales/pipeline/webview.py`
`build_novel_payload()` is the single source of truth both viewer builds
render from -- one function, two consumers, so the static and interactive
builds can never quietly disagree about what a merge or a mention looks
like.

Entity colour is assigned by **mention-count rank**, not a hash of the id,
so the highest-traffic characters get the most visually distinguishable
hues and a long tail of walk-ons doesn't fight for colour; beyond rank 16
(`_COLOURED_RANKS`, the palette length) everything shares a neutral grey.
`_ANON_SPEAKER_RE`/`_anon_slot_label()` recognise the
`{novel_id}:anon:{chapter}:{slot}` id shape `speakers/runner.py` mints and
render "Unknown Speaker N" -- there is deliberately no `Self` row behind
that id for `store.get_self()` to find.

`write_webview()` emits the dependency-free static build: one HTML shell
plus one `<script src>`-loaded JS data file per novel (not `fetch`,
specifically because `fetch()` of local JSON is blocked by the browser's
same-origin policy on `file://` and `<script src>` is not).
`write_webview_json()` emits the same payload as plain JSON files for the
React app's `public/data/`, which needs a server either way.

### `src/echotales/pipeline/webview_server.py`
The live backend for the React app's "Live edit" mode. Stdlib
`http.server` only, single-threaded deliberately: `Store` opens its
sqlite3 connection once in the main thread, and sqlite3 forbids
cross-thread use by default -- `ThreadingHTTPServer` crashed on the first
concurrent request during verification, caught by actually calling the
endpoint rather than by reading the code.

`_overlay_corrections()` recomputes the full payload fresh on every
request from `corrections.py`'s pending-and-applied log, rather than
tracking deltas incrementally -- with seven correction types now each able
to touch a mention's entity, a span's speaker, and the entity list at
once, one from-scratch walk that rebuilds marks and counts together is far
easier to get right than several deltas that all have to reconcile with
each other. `merge_lines` and `create_mention` are the types this
function does not preview live (`create_mention` mints a `Mention` that
doesn't exist yet, so there's nothing to overlay onto until `apply`) --
their effect is only visible after `apply`.

### `src/echotales/pipeline/corrections.py`
`Correction`/`CorrectionLog`/`apply_pending`. A correction is never fed
back into the resolver as input -- HANDOFF §6 already rules that out for
hand-curated alias mappings, and a correction is the same category of
thing: a resolver graded against its own answer key measures nothing.
Instead a correction does two things: preview (`webview_server.py`,
immediate) and, on request, a one-time patch to *this run's* store
(rebind, delete an absorbed span, append a `ResolutionEvent`) -- the same
relationship a human copy-editor has to a draft, not a change to how
future runs decide anything.

Six types: `merge_entities`, `reassign_mention`, `reassign_speaker`,
`merge_lines`, `flag`, `reassign_span_type`. `reassign_mention`/
`reassign_speaker` can mint a brand-new entity instead of picking an
existing one (`new_manual_entity_id()` decides the id once, at the moment
the correction is logged, so the live preview and the eventual store
write can never disagree about what "the new character" refers to).
`flag` is excluded from `apply_pending` entirely -- it has no store-side
effect, and sweeping it into "apply pending corrections" would silently
mark a note as dealt with the moment something unrelated gets fixed; a
flag stays open until explicitly removed.

`apply_pending()` wraps each correction's apply in its own try/except and
commits the store after every single item, not once at the end -- a
prior version committed once at the very end after marking every item
applied as it went, so a later item raising left the log claiming an
earlier correction was applied while its store write sat in an
uncommitted transaction that a crash would silently discard. Found by an
actual crash during verification (a stale-closure frontend bug sending
`chapter: null`), not anticipated in advance.

**Data safety, load-bearing:** `webview-server` must be run against
`data/webview-working/*.db`, copies of the databases every measurement in
this document comes from, never those databases directly. Verified after
a full edit-and-apply pass: originals byte-identical to before, working
copy showing every change.

### `tests/test_anaphora.py`
33 tests, weighted toward what the resolver must decline to do: no cataphora,
no distant antecedents, no gender-mismatched links, no split when personas are
known to be concurrent, and no split from mentions that fall outside every
segment (the phantom-violation regression).

### `tests/test_speakers.py`
25 tests covering each tier in isolation, the ladder's precedence, the
split-sentence case, cross-block attribution, scene-break reset, and the two
first-class non-speaker outcomes.

### `tests/test_mentions.py`
53 tests: lexicon loading and rank stripping, gazetteer offset integrity and
word-boundary rejection, alias-type precedence, the three parenthetical
readings, and runner-level guarantees (generics never reach the store, dialogue
mentions are never marked present).

### `tests/test_spans.py`
67 tests: quote splitting (apostrophes, unterminated quotes, CJK brackets),
emphasis-as-boundary, thought-verb detection, narration subtypes, crowd runs,
and the `FLAT`-wins delivery rule.

### `tests/test_segment.py`
38 tests, weighted toward what segmentation must *refuse* to do: a chapter that
merely mentions the past stays MAIN, a short chapter is never split, an empty
LLM response never invents segments, and the LLM fires only on ambiguous
chapters.

---

## `tools/` — never built; superseded by a different design

`check_deps.py`/`annotate.py`/`replay.py` as originally planned do not
exist. The human-promotion job `annotate.py` was meant for is now
`corrections.py` + `webview_server.py` + the React app's "Live edit" mode
-- an interactive tool rather than a batch script, because the actual need
turned out to be "click the wrong mention and fix it while reading," not
"run a promotion pass over a dump." `replay.py`'s job (reconstruct graph
state at any discourse position) is `core/state.py::StateResolver`, already
built and exposed as `echotales query state-of`. `check_deps.py` (fail CI
if `core` imports `pipeline`) is still genuinely unbuilt -- the rule is
enforced by convention only, not by a check.

---

## `data/`

- `raw/` — source EPUBs. **Not committed.**
- `sources.toml` — per-novel adapter config; adding a novel is a TOML block,
  not a code change.
- `gold/` — annotations as character offsets plus short evidence snippets,
  never chapter text. Same convention as CoNLL/OntoNotes, so the directory can
  be shared with collaborators without redistributing the novels.
  `reverend-insanity-c1-c5.toml` is tracked (a human-editable draft source);
  the `.jsonl` it expands to via `eval/draft.py` is git-ignored (derived,
  regenerable, and would duplicate the toml's content under source control
  for no benefit).
- `lexicons/` — per-novel honorifics, ranks, transferable titles. Seeded per
  genre and grown during processing. `*-ner-cache.json` (chapter-NER results,
  keyed by a hash of chapter text) is git-ignored -- pure cache, regenerates
  on the next LLM-backed run, same philosophy as the induced lexicon TOMLs.
- `webview/` — the static viewer's build output (`echotales webview`).
  Git-ignored, regenerate on demand.
- `webview-working/` — copies of the run-of-record `.db` files, edited by
  `webview-server` so a correction can never mutate the databases this
  document's numbers are measured from. Git-ignored; re-copy from the
  originals to reset. See `webview_server.py` above.
- `corrections/` — one JSONL per novel, the human-correction log
  (`corrections.py::CorrectionLog`). **Not** git-ignored, deliberately --
  unlike `webview/` and `webview-working/` this is irreplaceable human
  review, not a regenerable build artifact, and it contains no source text
  (only target ids and notes), so there is no copyright reason to exclude
  it either.
