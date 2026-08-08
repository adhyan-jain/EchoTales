# EchoTales — Architecture

High-level design. For per-file detail see [`details.md`](details.md); for the
original design decisions see [`plans.md`](plans.md).

**Status:** build-order steps 1–7 (the publishable core). Voice and visual
pipelines are deliberately not started — they get built against a validated
resolver, not a moving one.

---

## 1. The one-sentence version

EchoTales reads a volume of a web novel, builds a **bitemporal narrative
knowledge graph** while reading, and answers one query:

```
state_of(target, timeline, position, observer=READER)
  -> {aliases, attributes, relationships, persona, truth_status}
```

Voice selection, prosody, reference images and panel casting are all downstream
consumers of that query. The graph is the contribution; audio and visual are
the demonstration surface.

---

## 2. Why the obvious design fails

The target content is translated Chinese and Korean web fiction. Three
properties break tooling built for Western fiction:

**Names are unstable.** One character carries dozens of surface forms and the
set *shifts* over the story. Two mentions may share no characters yet denote
one person; two mentions may be character-identical yet denote different
people. Similarity-based clustering therefore fails in both directions, which
is why this system does incremental resolution with structured evidence
instead of clustering.

**Chapter number is not a time coordinate.** A single chapter may hold present
action, a dream replaying a third party's past, and past-life memory. Treating
`story_time = chapter_number` misattributes all of it.

**Identity is asserted, faked, and withdrawn.** A title transfers to a new
holder ("was true, then stopped"). An impostor is unmasked ("was never true").
These are different operations and collapsing them corrupts the graph.

---

## 3. Three axes of time

| Axis | Representation | Order | Answers |
|---|---|---|---|
| **Discourse** | `(chapter, offset)` | total, always known | "when did the reader learn this?" |
| **Story** | `(timeline_id, FuzzyInterval)` | *partial* | "when did this happen?" |
| **Knowledge** | `(observer_id, discourse_pos)` | per observer | "who knows this, and since when?" |

Story time is a partial order on purpose. `MAIN_TIMELINE`,
`PREVIOUS_LIFE_<char>`, `DREAM_<id>` and `MEMORY_<id>` coexist, and positions
across two timelines are **not comparable**. Comparing them would invent an
ordering the text never supplies, so cross-timeline facts are excluded rather
than ranked.

### Fuzzy endpoints

Text almost never states when a binding *stopped*. Each endpoint is a bounded
pair (`from_lb/from_ub`, `to_lb/to_ub`), and containment returns three values:

- `CERTAIN` — holds under every consistent reading
- `PLAUSIBLE` — holds under some reading
- `EXCLUDED` — holds under none

An open interval is `(last_evidence, +inf)`. Confidence therefore **decays**
past the last sighting: a title attested once at chapter 20 is only PLAUSIBLY
held by the same person at chapter 400, because nothing in the text speaks to
the intervening 380 chapters. Re-attestation advances `last_evidence` and grows
the certain zone, so confidence tracks evidence rather than assumption.

Note the decay is justified by *absence of evidence over a long span*, not by
an assumption that titles in some genre usually transfer. Whether a given novel
transfers titles at all is a property of that novel.

---

## 4. Self vs persona

A flat entity table cannot express reincarnation, body-swap, clones, or
sustained disguise. The entity model splits:

- **`Self`** — a continuity of consciousness. Owns memory, relationships,
  roles, knowledge.
- **`Persona`** — a physical embodiment. Owns appearance, age, attire, voice
  timbre. **Generation binds here.**

`SelfPersonaBinding` connects them over a story-time interval. Every hard case
falls out of the cardinality:

| Case | Shape |
|---|---|
| Ordinary character | 1 self, 1 persona, open binding |
| Reincarnation | 1 self, 2 personas, sequential |
| Body swap | 2 selves, 2 personas, crossed at the swap |
| Clone / soul avatar | 1 self, **concurrent** personas |
| Possession | 2 selves contesting 1 persona |
| Sustained disguise | 1 self, concurrent personas, different audience scopes |
| Dream identity | 1 self, persona scoped to a dream timeline |

A direct consequence: the co-occurrence penalty applies **between personas,
never between selves**. Two simultaneous mentions is evidence of two distinct
bodies — which for a clone is not evidence of two distinct characters.

**`Persona` itself has no runner yet** — nothing in the pipeline creates one.
One practical consequence surfaced before that gap was closed properly:
unattributed dialogue needs a *distinct voice* far more often than it needs a
*known identity* (two unnamed guards trading lines is read wrong in one
voice), but minting a full `Self` for someone who may never be named again
is exactly the flat-entity-table failure this section exists to avoid on the
named side. `speakers/runner.py::_assign_anonymous_slots` is the interim
answer: a locally-scoped id, never a `Self` row, assigned by turn-taking
alternation and consumed the same way a `Persona` id eventually will be. It
is not a substitute for building `Persona` — it has no appearance, no
timbre, no binding, none of what this section defines — only a stand-in for
the one thing generation needs immediately that identity resolution alone
cannot provide.

---

## 5. Observers and the spoiler problem

Every fact records who learned it and when. A character observer sees only
facts explicitly recorded as known to them and **does not inherit the reader's
knowledge** — that inheritance is the spoiler bug the model exists to prevent.

The headline acceptance test is one query differing only in observer:

```
state_of(fang_yuan, observer=READER)   -> {Fang Yuan, Wu Yi Hai}
state_of(fang_yuan, observer=WU_CLAN)  -> {Wu Yi Hai}
```

`SYSTEM` is the omniscient oracle: it ignores knowledge time and sees `FALSE`
facts. It exists for evaluation and debugging, and is never used for
generation.

### Retraction ≠ interval end

| | Meaning | Mechanism | Effect before the reveal |
|---|---|---|---|
| `close_interval` | was true, then stopped | move `to_lb`/`to_ub` | still true |
| `retract` | was **never** true | set `retracted_at` | **still believed** |

A claim retracted at chapter 200 is still returned for an observer standing at
chapter 150, because they did believe it then. Nothing is ever deleted; "what
did the reader believe at chapter 100" stays answerable forever.

---

## 6. Pipeline

Deterministic stages run over all chapters in one streaming pass. LLM-dependent
stages run in 30–50 chapter windows with the graph accumulating across them.

```
Phase 0  Ingestion        EPUB -> chapters -> classified blocks
Phase 1  Span classification    dialogue / action / description / inner monologue
Phase 2  Narrative segmentation detect dreams, flashbacks, time skips
Phase 3  Mention detection      NER -> gazetteer -> LLM sweep
Phase 4  Speaker attribution    4-tier escalation + delivery markers
Phase 5  Local anaphora         within one chapter, within one layer
Phase 6  Global resolution      retrieve -> evidence -> score -> gate   <- the heart
Phase 7  Event log + state_of   append-only, replayable
Phase 8  Prominence tiering     principal / recurring / incidental
```

**Volume-first.** The whole volume is processed before anything is generated.
That is what makes prominence tiering, complete title-transfer tracking and
correct reveal handling possible at all.

### Which devices exist is a property of the novel, not the genre

An easy and expensive mistake. Narrative devices do **not** distribute evenly
across a genre:

| Device | Actually scoped to |
|---|---|
| Dream realms | **one specific novel** in this corpus — not a cultivation-genre feature; most cultivation novels have no dream mechanic |
| Transferable titles | broadly cultivation-typical, but a given novel may never transfer one |
| Regression loops, system windows | Korean system fiction, not Chinese cultivation |
| Pathway / constellation epithets | single-source conventions |

So detectors are **opt-in per novel** (`segment.MarkerSet`), and the vocabulary
they key on is **induced from the text** rather than assumed from genre. A
detector hunting for a device the novel does not use produces only false
positives, and each one mints a spurious timeline that later facts get bound
to.

`MarkerSet.universal()` covers what any prose narrative has — flashbacks, time
skips, scene breaks. Everything else is enabled explicitly.

### Segmentation uses asymmetric thresholds

Boundary detection is **not** uniformly conservative. The two classes have
opposite cost profiles:

| Boundary class | Example cue | Threshold | Why |
|---|---|---|---|
| **Explicitly signalled** | fixed dream-entry formulae | **aggressive**, low threshold | A miss merges a dream persona into the main-timeline self, and that bad binding then *poisons the gazetteer* — every later mention exact-matches it and the pre-filter force-links |
| **Implicitly signalled** | unmarked flashback, tense shift | conservative, high confidence | A false positive costs one spurious timeline; a miss costs one temporal misattribution |

The earlier design applied conservative thresholds to both. That was wrong for
the explicit class. Where a novel *does* use an explicitly-signalled device,
the signalling is near-unambiguous, so a miss is far more expensive than a
false positive — but only for novels that opt into that detector at all.

### The compounding gazetteer

Phase 3 layer 2 is an Aho-Corasick automaton over confirmed aliases, rebuilt at
each window boundary. By chapter 50 it catches most name mentions with zero
error; by chapter 100 most decisions resolve by exact match. **The system gets
cheaper and more accurate as it reads**, and the curve of "decisions resolved
by exact match vs. chapter number" is a reportable result.

### Phase 6: pre-filters, then a small scorer

For each local mention group: retrieve top-10 candidates (BM25 over aliases +
context embeddings), apply **hard pre-filters**, score whatever survives, and
gate to `LINK` / `NEW` / `DEFER`.

**Hard pre-filters run before scoring** and are not features:

| Signal | Verdict | Why not a feature |
|---|---|---|
| `co_presence_violation` | **BLOCK** | Two mentions simultaneously present doing different things cannot be one persona. A near-certain negative; letting positives outvote it discards that certainty. |
| `temporal_validity == 0` | **BLOCK** | The binding is invalid here. A filter, not a vote. |
| `declaration_match` | **FORCE_LINK** | "His true name was X" is not evidence *for* a link — it *is* the link. |
| `gazetteer_exact_match` | **FORCE_LINK** | Exact match on a confirmed alias. |

Blockers are checked before force-links: a co-present pair that also matches a
declaration is far more likely to be a detector error than a real identity.

**This ordering was not a preference — it fixed a live blocker.** As a weighted
feature at 2.5, `gazetteer_exact_match` drove probability to 0.957 unaided.
Because every link grows an entity's alias set, each wrong link made the next
one easier: 2,753 mention groups collapsed to **7 entities** over 40 chapters.
Self-reinforcing error.

**Five scored features**, all dense enough that a fitted weight is defensible:
`surface_similarity`, `context_embedding_similarity`,
`speech_partner_compatibility`, `temporal_validity`,
`first_attested_soft_prior`.

`surface_similarity` is weighted *low* and floored at 0.80. Jaro-Winkler
between genuinely unrelated short romanised names runs 0.6–0.7 in this corpus
(measured: Klein/Leonard 0.676, Audrey/Alger 0.630), so below the floor it is
chance collision, not evidence.

**Be honest about what this is:** a hand-tuned rule system with a learned
tiebreaker on five dense features. Not a learned model. The rare, high-weight
signals are rules precisely because they would never have enough gold instances
to fit.

Deferred cases re-resolve later against accumulated evidence; the residual goes
to LLM adjudication.

### Contradiction detection — the gazetteer compounds errors too

The compounding property cuts both ways. A wrong `LINK` at chapter 30 adds a
bad surface form to an alias set, Aho-Corasick then exact-matches it forever,
and the pre-filter force-links on it every time. Nothing in the forward pass
can undo that.

So a **contradiction detector runs after every processing window**:

- Re-score every committed `LINK` against evidence accumulated since it was made
- Check specifically for: co-presence violations discovered later, new surface
  forms conflicting with the current binding, attribute contradictions
  (stated gender, contradictory ranks)
- If the re-score falls below the link threshold → emit a `split` event and
  move the case to the DEFER queue for adjudication

`split` and `retract` already exist in the event vocabulary. Until the detector
exists, **nothing emits them** — the log records only growth, never correction,
which makes the "retroactive correction rate" metric unreportable.

The gazetteer additionally requires three guards: word-boundary matching (so
"Wang" cannot match inside a longer word), a two-character minimum, and an
**ambiguity blocklist** for common words that double as names.

---

### Conformal prediction — Mondrian, and an admitted violation

The three-way gate is calibrated by conformal prediction so that "at most α of
automatic links are wrong" is a claim the procedure supports rather than a
hand-picked threshold.

**But standard conformal assumes exchangeability, and this system explicitly
violates it.** The gazetteer is designed to make decisions *easier* as the
volume progresses — that is the compounding contribution. A decision at chapter
180 is drawn from a different distribution than one at chapter 5. We cannot
claim both the compounding effect and exchangeability.

Two consequences, both load-bearing:

1. **Mondrian (class-conditional) conformal**, taxonomy = `alias_type`.
   Calibrate separately for `RIGID_NAME`, `TRANSFERABLE_TITLE`, `EPITHET`,
   `RELATIONAL_DEICTIC`. These classes have genuinely different error
   profiles — a transferable title is hard in ways a rigid name is not — and
   pooling them produces a coverage guarantee that holds on average while
   failing badly on the class the paper is about.
2. **Calibrate within-novel, never across novels.** Vocabulary and naming
   conventions differ enough between sources that cross-novel calibration
   imports the wrong error distribution.

The residual exchangeability violation is **stated as a limitation**, not
papered over.

### Lexicon confidence tiers

Induced vocabulary is admitted at three tiers rather than being filtered by a
support threshold:

| Tier | Support | Use |
|---|---|---|
| HIGH | ≥3 corroborating samples | full weight |
| MEDIUM | 2 samples | full weight |
| LOW | 1 sample | admitted, down-weighted |

Excluding single-sample entries was wrong: **a title that transfers exactly
once, late in the volume, is precisely the hard case the work is about.**
Filtering it out removes the phenomenon under study from the vocabulary that
would let the system detect it.

## 7. LLM escalation ladder

Seven stages want an LLM. Rather than one model everywhere, a router runs a
cheap local model for bulk work and escalates only low-confidence cases:

```
ECHOTALES_LLM_MODE = stub | local | api | hybrid
```

`stub` returns deterministic canned responses, so the entire pipeline is
testable in CI with **no GPU and no network**. Every call — tier, model,
escalation reason, tokens, latency — is logged to `llm_call`. That table is
evaluation data, not telemetry: "% routed to expensive inference vs. accuracy
gained" is a claimed contribution.

### The LLM budget is the binding design constraint

Measured on this hardware (RTX 4060 8 GB, `qwen2.5:7b` via ollama): **1.9 s per
call at steady state**. Batching gives no throughput win — five spans in one
call costs the same per span as five separate calls, because the bottleneck is
token generation, not request overhead.

Against a 600-chapter, 65,296-span corpus (RI 199 + LOTM 213 + ORV 188):

| Granularity | Calls | Local wall-clock |
|---|---:|---:|
| **per span** | 65,296 | **34.5 h — not viable** |
| per chapter | 600 | 19 min |
| per 40-chapter window | 15 | 29 s |
| deferred 5% of spans | 3,265 | 1.7 h |
| deferred 2% of spans | 1,306 | 0.7 h |

**Design rule, enforced for every remaining phase: no stage may call the LLM
once per span or once per mention at bulk.** An LLM stage must be one of

1. **per chapter** — one call covering the whole chapter (segmentation, the
   mention sweep, POV detection),
2. **per window** — one call per 30–50 chapters (wiki summary regeneration),
3. **per deferred case** — only what a deterministic pass could not settle.

This is not a workaround for slow hardware. It is the same conclusion the
escalation ladder was designed around, now with a number attached: the
deterministic passes are not an optimisation, they are what makes the system
run at all. An API tier changes the cost but not the shape — 65k calls is
expensive at any price.

---

## 8. Caching and invalidation

Every derived artifact records the graph facts it consulted, hashed.
Invalidation is a set intersection, so a chapter-190 reveal invalidates the few
artifacts that depended on the affected entity rather than 190 chapters of
work.

| Tier | Contents | Invalidated by |
|---|---|---|
| `TEXT` | mentions, spans, embeddings | never (text-derived) |
| `GRAPH` | resolutions, `state_of` results | events intersecting the read set |
| `RENDER` | audio segments, panels | upstream state changes |

---

## 8b. Two features with scoped definitions

### `audience_scope_compatibility` — explicit tags only, or null

Earlier this feature was defined as "computed by replaying events", which is
unbounded: the text rarely states who witnessed what, so replaying yields
almost nothing and the feature silently became a constant.

Scoped definition:

- If the mention's scene carries an **explicit region/faction tag** and the
  candidate entity has no appearances under that tag → **weak negative** signal.
- If either side lacks an explicit tag → the feature returns **null** and is
  excluded from that scoring instance.

Absence of evidence is not evidence of absence. A feature that silently defaults
to a middling constant on most instances adds noise to every decision while
appearing to contribute.

### Voice assignment — colour within archetype buckets, not globally

In a long cultivation novel the co-occurrence graph over principal characters is
close to complete: the main cast shares scenes constantly. The chromatic number
therefore exceeds any archetype-appropriate voice palette, and **global
collision-free assignment is not achievable.**

Revised approach:

- Graph colouring runs **within each archetype bucket**, not across the whole
  cast — a young female disciple and an elderly male patriarch never needed
  distinct colours anyway, because their timbres already differ.
- Residual collisions between **non-co-occurring minor characters in the same
  bucket** are accepted and **explicitly logged**.
- The system does **not** claim global collision-free voice assignment.

## 9. Package boundaries

```
packages/core/       models, store, state_of()   <- imports nothing from pipeline
packages/pipeline/   ingest, resolve, eval
apps/api/            orchestration, correction UI
tools/               annotation CLI, replay debugger
```

`core` importing `pipeline` is a CI failure, not a style preference:
"generation pipelines do not need to understand the novel" is a claim the paper
makes, and the dependency graph is what keeps it honest.

Storage is plain SQLite. The workload is temporal range filters over
well-indexed tables — graph traversal is not the bottleneck.

---

## 10. Data handling

Source novels are **not committed**. `data/gold/` stores character offsets and
short evidence snippets rather than chapter text, following the CoNLL/OntoNotes
convention, so annotations can be shared with collaborators without
redistributing the novels.

Annotations carry `provenance` (`MACHINE` / `HUMAN_VERIFIED`) and `confidence`.
The generated dataset is **silver**; reported metrics must cite the
`HUMAN_VERIFIED` subset, because scoring the resolver against its own output
measures self-consistency rather than accuracy.

---

## 11. Non-negotiables

1. No clustering — incremental resolution with evidence accumulation
2. Chapter ≠ time — three-axis temporal model
3. Self ≠ persona
4. Generic descriptors never enter the graph
5. Retraction ≠ interval end
6. Volume-first processing
7. **High-precision automation with a bounded, measurable review queue.** The
   escalation rate — the share of decisions routed to human review — is a
   *reported metric*, not a failure mode. (This replaces the earlier "full
   automation, no human in the loop" framing, which contradicted the correction
   interface, the DEFER queue, active learning from correction behaviour, and
   the translator-handoff confirmation step — all of which are in the
   architecture. The bounded-queue claim is both truer and stronger.)
8. The gazetteer compounds
9. Precision over recall in local resolution
10. Delivery markers override scene sentiment
