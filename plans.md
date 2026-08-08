# EchoTales — Complete Architecture & Implementation Prompt

**Paste this entire document as context for Claude Code. It contains every finalized decision from the design process.**

---

## FIRST: Clean Slate

Delete any existing EchoTales code, folders, or scaffolding. We are starting from scratch.

---

## 0. What EchoTales Is

EchoTales is a fully automated pipeline that takes one volume of a web novel (~250 chapters) and produces:

1. A full-cast audiobook where each character has a distinct voice reflecting their state at that point in the story
2. A manga-style or instagram web-novel edits(stacking images and then putting effects like zoom-in/out and shaking effects to give a video like affect) visual adaptation where characters and settings remain visually consistent across panels

Both outputs are driven by a single shared artifact: a **bitemporal narrative knowledge graph** built incrementally while reading. The graph answers one query:

```
state_of(target, timeline, position, observer=READER)
→ {aliases, attributes, relationships, persona, truth_status}
```

Everything downstream — voice selection, prosody, reference images, panel casting — consumes that query. The graph is the research contribution. Audio and visual are the demonstration surface.

**The end goal is high-precision automation with a bounded, measurable review queue.** The escalation rate — the share of decisions routed to human review — is a *reported metric*, not a failure mode.

*(Revised. The earlier "full automation, no human in the loop" framing contradicted four things already in this architecture: the correction interface, the DEFER queue, active learning from correction behaviour, and translator-handoff confirmation. A system that quantifies and bounds its own review burden is a stronger claim than one that pretends to need none — and it is what is actually being built.)*

**Target content:** translated Chinese cultivation/xianxia fiction (e.g., Reverend Insanity), Korean regression/system fiction (e.g., Omniscient Reader's Viewpoint), Japanese light novels (e.g., Lord of the Mysteries), and Western LitRPG/progression fantasy. These genres have the most volatile naming conventions and are where existing tools fail.

**Team:** AJ (sole coder, architecture), Atharva Sheerh Pandey (labeling/testing), Aryan Gahlot (labeling/testing). University AI course semester project, 3-4 months. AJ has Claude Pro.

**Tech stack:** Python 3.12, uv workspaces, Pydantic v2, mypy strict, ruff, pytest, GitHub Actions CI, SQLite (→ Postgres later). React/Next.js for the web frontend.

---

## 1. The Two Hard Problems

**HP1 — Cross-chapter entity linking against a self-authored knowledge base.** This is NOT coreference resolution. It is entity linking against a KB that doesn't exist beforehand and is constructed while reading. One character carries dozens of surface forms that SHIFT over the story. BookNLP fails here because it was built for Western fiction with stable naming. Clustering-based approaches fail because identity resolution in these novels is asymmetric and conditional — two mentions may have zero surface similarity but strong contextual evidence of being the same entity. We tried BookNLP; it failed miserably. We are not using clustering.

**HP2 — Consistent multimodal generation conditioned on narrative state.** Voice and visual identity must reflect the character's state AT THE RENDERED MOMENT, not their final state. A character at chapter 10 and chapter 140 may look and sound deliberately different.

---

## 2. Time Model — Three Axes, Not Chapter Numbers

**CRITICAL: Chapter number is NOT a valid time coordinate.** A single chapter can contain present-time action, a dream realm replaying someone else's past from thousands of years ago, the protagonist's own past-life memories, and political analysis narrating offscreen events. Assigning story_time = chapter_number to all of these is wrong.

### 2.1 Discourse Position
- A monotonic counter: `(chapter, paragraph_offset)`
- Total order, always known, never ambiguous
- Use for: "when did the reader learn X," gazetteer growth ordering, confidence scoring

### 2.2 Story Time — A Partial Order, Not a Number
- Represented as `(timeline_id, relative_position)`
- Multiple timelines that may not be comparable
- Timeline types:
  - `MAIN_TIMELINE` — the current story
  - `PREVIOUS_LIFE_<character>` — e.g., Fang Yuan's 500-year past life
  - `DREAM_<identifier>` — each dream realm gets its own timeline (e.g., `DREAM_TU_SHI_CHENG`)
  - `MEMORY_<identifier>` — character memory sequences
- Cross-timeline ordering is an optional annotation, not a requirement
- Within a timeline, events are ordered. Across timelines, ordering may be partial or unknown

### 2.3 Knowledge Time — Per Observer
- Represented as `(observer_id, discourse_position)`
- `observer_id ∈ {READER, SYSTEM} ∪ {self_id}`
- Example: Fang Yuan = Wu Yi Hai is known to READER from chapter 1, but Wu clan members never learn this
- Implementation tiers:
  - **Fully implemented:** READER and SYSTEM observers
  - **Coarse approximation:** Per-character observers populated only from explicit textual evidence
  - **Scoped out:** Full epistemic modeling (stated as limitation)

### 2.4 Narrative Segments

Discourse is partitioned into segments mapping text spans to story-time spans:

```
narrative_segment(
  id,
  chapter_from, offset_from, chapter_to, offset_to,  -- discourse span
  timeline_id,                                        -- which timeline
  story_seq_from, story_seq_to,                       -- story span
  segment_type,     -- MAIN | FLASHBACK_OWN | DREAM_OTHER | VISION | PROPHECY
                    -- | HEARSAY | REGRESSION_PRIOR_LOOP | ILLUSION
  narrative_layer,  -- for generation: determines visual style, cast scoping
  canonicity        -- CANONICAL | VOIDED | DISPUTED
)
```

Default: one chapter → one MAIN segment, story_seq = chapter index. This reduces to naive behavior for linear novels. Non-linear segments detected by rules + LLM.

**Voiding:** An illusion arc revealed at ch 120 to have covered ch 100-120 → flip `canonicity = VOIDED`. Facts inside voided spans are excluded from `state_of()` on the canonical timeline but remain queryable for "what the reader believed at the time."

**Dream realms (specific to Reverend Insanity and similar):** The protagonist enters dream realms frequently, experiencing OTHER people's memories as if living them. Each dream realm = separate timeline with its own cast. Dream-realm entities do NOT cluster with main-timeline entities. Fang Yuan inside a dream as "Tu Shi Cheng's son" is a temporary dream persona, not his main-timeline identity.

### 2.5 Fuzzy Interval Endpoints

Most bindings never state when the previous holder stopped. Replace each endpoint with a bounded pair:

```
from_lb, from_ub    -- earliest and latest possible start
to_lb,   to_ub      -- earliest and latest possible end
```

Point-known: `lb == ub`. Unknown: `(last_evidence, +inf)`. Queries return CERTAIN / PLAUSIBLE / EXCLUDED.

---

## 3. Entity Model — Self vs Persona

A flat entity table cannot represent reincarnation, body-swap, clones, or sustained disguise identities. Split into:

- **`self`** — continuity of consciousness. Owns memory, relationships, roles, knowledge state.
- **`persona`** — a physical embodiment. Owns appearance, age, attire, voice timbre, physical attributes. This is what image generation and TTS bind to.

```
self    (id, canonical_label, first_attested_pos, notes)
persona (id, body_label, first_attested_pos)
self_persona_binding(
  self_id, persona_id,
  timeline_id, story_from_lb, story_from_ub, story_to_lb, story_to_ub,
  learned_at_pos, observer_id, confidence
)
```

### How this handles every hard case:

| Case | Representation |
|---|---|
| Ordinary character | one self, one persona, binding open-ended |
| Reincarnation / transmigration | one self, two personas, sequential bindings |
| Body swap | two selves, two personas, bindings crossed at swap point |
| Clone / soul avatar | one self, **concurrent** persona bindings |
| Possession | two selves contesting one persona over overlapping intervals |
| **Sustained disguise (Fang Yuan)** | one self, multiple simultaneous personas (Wu Yi Hai, Liu Guan Yi, etc.) with different audience scopes |
| Dream realm temporary identity | one self, temporary dream persona scoped to dream timeline only |
| Paper figurine / puppet proxy | self → proxy relationship, pronouns in proxy scene resolve transitively |

### Audience scope for disguise identities

Audience is NOT a fixed field. It's emergent from the event log:
- When Fang Yuan first appears as Liu Guan Yi: `new_persona(self=fang_yuan, persona=liu_guan_yi, context=northern_plains, witnesses=[specific_characters])`
- When Liu Guan Yi becomes famous after Reverse Flow River: `reputation_spread(persona=liu_guan_yi, scope=ALL_REGIONS, evidence="ch1289")`
- Audience at any point is computed by replaying events, not stored as static property
- `state_of(fang_yuan, audience=WU_CLAN)` → "Wu Yi Hai, rank 7, Wu clan member"
- `state_of(fang_yuan, audience=NARRATOR)` → "Fang Yuan, disguised as Wu Yi Hai"

### Co-occurrence signal fix

Co-occurrence penalty applies **between personas**, never between selves. Suppressed when concurrent `self_persona_binding` exists. Two simultaneous mentions = evidence for distinct personas (true), not distinct characters (often false in cultivation novels with clones/avatars).

---

## 4. Alias Model

### 4.1 Aliases Are Typed

| Type | Example | Behavior |
|---|---|---|
| `RIGID_NAME` | Li Wei, Fang Yuan | Near-permanent. Strong linking evidence. |
| `TRANSFERABLE_TITLE` | Sect Master, Frost Emperor, Immortal Venerable | Transfer-eligible. Rebind detector active. Very common in cultivation novels. |
| `RELATIONAL_DEICTIC` | Master, Father, "this old man", "my lord", Senior Brother | Resolves **relative to speaker**, never globally. |
| `EPITHET` | the Ashen Duke, "one of the three great fairies" | Usually rigid-per-holder. Can be shared (multiple holders simultaneously). |
| `PATHWAY_TITLE` | Seer, Black Emperor, Red Priest (LOTM-specific) | Can be pathway name, historical holder, or current holder. Needs disambiguation. |
| `TAROT_TITLE` | The Hanged Man, Miss Justice, The Fool (LOTM-specific) | Context-specific aliases within Tarot Club. |
| `GENERIC_DESCRIPTOR` | the innkeeper, a guard, "that woman" | **NOT a binding.** Scene-local only. Never enters the graph. |

Type assigned at detection time by lexicon + LLM. Getting GENERIC_DESCRIPTOR out of the binding table eliminates the largest class of false matches and false transfers.

### 4.2 Alias→target is one-to-many at a given time

"Elder," "Senior Brother," "Young Master" are held by many people simultaneously. The temporal index is a **candidate-set filter, not a resolver**. It narrows the pool; contextual scoring decides.

### 4.3 Truth Status

Every binding, attribute, and relation carries:

```
asserted_by     -- narrator | self_id | rumour | system_window
truth_status    -- TRUE | CLAIMED | CONTESTED | FALSE | UNKNOWN | FABRICATED
retracted_at    -- discourse position of retraction, null if standing
```

**CRITICAL DISTINCTION:** A retraction is NOT an interval end.
- Interval end = "was true, then stopped being true" (e.g., title transferred)
- Retraction = "was NEVER true; we were misinformed" (e.g., impostor revealed)
- `FABRICATED` = identity created from scratch, not impersonating someone real (e.g., Fang Yuan as Wu Yi Hai)

Distinct event types (`retract` vs `close_interval`) enforce this in the log.

### 4.4 First Appearance Is a Soft Prior, Not a Hard Constraint

Hard constraint blocks the exact reveal case the system exists for. If ch 200 reveals Frost Emperor = Li Wei since ch 1, but Li Wei first attested at ch 50, a hard constraint forbids the correct binding. Demote to soft negative prior that explicit declarations and reveal evidence can override.

### 4.5 Transferable Title Lexicon — **INDUCED, not hand-written** (revised)

A transferable-title list must exist before resolution starts, because the
first holder of a title is textually identical to the second: only prior
knowledge that a title *is* transferable makes the distinction available.

**Revised: the list is induced from the novel's own text, not authored.**
Hand-writing it was rejected for three reasons:

1. `alias_type_for()` treats a lexicon hit as authoritative at 0.95 confidence,
   so a wrong entry silently outranks every heuristic. Lists written from
   recall are where wrong entries come from.
2. It does not scale — every new novel needs another hand-written file.
3. It weakens the result. "We hand-tuned a vocabulary per novel" is the first
   objection to the transferable-title finding, which is the slice where this
   system is meant to beat BookNLP-style baselines. Inducing the vocabulary
   converts that liability into a contribution.

**Mechanism** (`pipeline/mentions/induce.py`):
- `data/lexicons/_seed.toml` holds a **genre-neutral** floor: English role
  nouns, kinship/address terms, and narrative declaration idiom. No
  novel-specific content whatsoever.
- `echotales induce-lexicon` samples chapters **evenly across the volume**
  (not the opening — a title introduced at ch 150 is as much part of the
  vocabulary as one from ch 2), asks the model to sort observed vocabulary
  into transferable titles / progressive ranks / relational deictics /
  generic descriptors, and requires **corroboration across ≥2 samples**.
- Output is hand-editable TOML at `data/lexicons/<novel_id>.toml`.
- **Declaration phrases stay seed-only.** They feed the highest-weighted
  feature in the evidence vector, so a hallucinated entry there is unusually
  costly.

Progressive rank mutation ("Golden Core Elder Wang" → "Nascent Soul Elder
Wang") is gradual drift, not discrete transfer — more common than title
transfer, and mistaking it for transfer splits one character into two.

### 4.6 Alias variants vs. alias→entity (revised)

Three problems are routinely conflated. They need different treatment:

| Level | Example | Resolved by |
|---|---|---|
| **Lexical variants of one alias** | "Miss Justice" / "Lady Justice" / "The Justice" / "Justice" | `comparison_key` — mechanical |
| **Several aliases, one self** | a code name and a legal name | the global resolver (§6 Phase 6) |
| **Disguise with audience scope** | one faction knows the code name, another the legal name | `observer_id` + `truth_status=FABRICATED` |

Only the first is safe to solve mechanically. `comparison_key` strips
honorific prefixes (including abbreviated forms with a trailing period),
honorific suffixes, **and leading articles**, so all four forms above reach one
key. Alias *typing* still sees the raw surface, where article-led-ness is what
separates an epithet ("the Crimson Emperor") from a generic descriptor ("the
innkeeper").

`pipeline/mentions/variants.py` audits an alias set for normalisation gaps and
**reports** suspected splits rather than merging them — a shared head noun is
as often two distinct entities ("Hope Gu" / "Strength Gu") as one entity in two
dresses ("Neil" / "Old Neil").

**Hand-curated alias→entity mappings are gold labels, never pipeline input.**
Supplying them as input means the resolver reads the answer instead of
discovering it, which invalidates every MUC/B³/CEAF number. They live in
`data/gold/` under `provenance=HUMAN_VERIFIED`.

---

## 5. Schema (Consolidated)

```
narrative_segment (id, chapter_from, offset_from, chapter_to, offset_to,
                   timeline_id, story_seq_from, story_seq_to,
                   segment_type, narrative_layer, canonicity)

self              (id, canonical_label, first_attested_pos, notes)
persona           (id, body_label, first_attested_pos)
self_persona_binding (self_id, persona_id, timeline_id,
                      story_from_lb, story_from_ub, story_to_lb, story_to_ub,
                      learned_at_pos, observer_id, confidence)

mention           (id, segment_id, chapter, offset, text, alias_type,
                   speaker_self_id, target_kind, target_id,
                   reference_mode, span_type,
                   confidence, method)

alias_binding     (alias, alias_type, target_kind, target_id, timeline_id,
                   story_from_lb, story_from_ub, story_to_lb, story_to_ub,
                   learned_at_pos, observer_id,
                   asserted_by, truth_status, retracted_at,
                   evidence, confidence)

attribute         (target_kind, target_id, key, value, timeline_id,
                   story_from_lb, story_from_ub, story_to_lb, story_to_ub,
                   learned_at_pos, observer_id, asserted_by, truth_status,
                   retracted_at, confidence)

relation          (src_self, dst_self, type, timeline_id,
                   story_from_lb, story_from_ub, story_to_lb, story_to_ub,
                   learned_at_pos, observer_id, asserted_by, truth_status,
                   retracted_at)

observation       (observer_id, fact_ref, learned_at_pos)

resolution_event  (id, seq, type, payload, cause_pos, read_set_hash)
```

`target_kind ∈ {SELF, PERSONA}`. Attributes route by kind: appearance/age/attire → persona; role/status/relationships/knowledge → self.

`reference_mode ∈ {PRESENT, DIALOGUE_REFERENCE, NARRATOR_REFERENCE, MEMORY_REFERENCE, INNER_THOUGHT_REFERENCE}` — only PRESENT characters get drawn in panels; only PRESENT characters count for voice-collision avoidance.

`span_type ∈ {DIALOGUE, NARRATION_ACTION, NARRATION_DESCRIPTION, NARRATION_EXPOSITION, INNER_MONOLOGUE, CROWD_REACTION, SYSTEM_WINDOW, NON_DIEGETIC}`

Event types: `new_entity | new_persona | link | merge | split | rebind | retract | close_interval | void_span | remap_segment | persona_bind | persona_unbind | attribute_update | relation_update | reputation_spread | time_skip | death | resurrection`

Storage: SQLite initially. Not a graph DB.

---

## 6. Processing Pipeline

**Process the full volume (~250 chapters) before generating any output.** This enables prominence tiering, complete title transfer tracking, and correct reveal handling. Generation is gated behind resolution completion.

**Processing windows:** Deterministic steps (ingestion, mention detection, gazetteer) run over all 250 chapters in one pass. LLM-dependent steps process in 30-50 chapter windows with the full deterministic outputs available and the graph accumulating across windows. Wiki-style entity summaries are regenerated from the graph at window boundaries for LLM context.

### Phase 0 — Ingestion and Cleaning (Deterministic)

- Accept epub, txt, PDF upload only. No web scraping.
- Chapter boundary detection: regex-first (match "Chapter XXX", "Ch. XXX", split chapters 45.1, bonus/side chapters), LLM-fallback for non-standard numbering.
- Content classification at block level:
  - `PROSE` — story text
  - `DIALOGUE` — spoken lines
  - `SYSTEM_WINDOW` — stat blocks, status screens, notifications (detected by formatting: brackets, monospace, `Key: Value` patterns). **Parse as structured key-value data** — highest-precision attribute source in the novel.
  - `AUTHOR_NOTE` — afterwords, apologies
  - `TRANSLATOR_NOTE` — TL notes, glossary entries. Includes inline translator glosses in parentheses.
  - `NON_DIEGETIC` — ads, navigation links, chapter links
- Non-diegetic content stripped before identity processing but archived.
- Romanization normalization: strip common variants to canonical form. Detect translator handoffs by monitoring vocabulary shift (20+ surface forms changing simultaneously at a chapter boundary → flag as handoff, present mapping for confirmation).

### Phase 1 — Span-Level Classification (Hybrid)

Within PROSE and DIALOGUE blocks, classify every span:
- `DIALOGUE` — spoken lines between quotes
- `NARRATION_ACTION` — "Fang Yuan stretched out his arm"
- `NARRATION_DESCRIPTION` — "a huge ball appeared on the river surface" (becomes image generation prompt)
- `NARRATION_EXPOSITION` — "The matters of the world were like games of chess..." (skip in visual, keep in audio)
- `INNER_MONOLOGUE` — "He sneered inwardly: 'This Wu An is simply shortsighted'" (detected by attribution verbs: thought, mused, sneered inwardly, sighed inwardly, mumbled inwardly, "said in his heart", "cried in her heart"). Gets different audio treatment — filtered voice effect, not character voice.
- `CROWD_REACTION` — unattributed sequential short reactions from unnamed characters ("Hmm?", "What Gu worm?", "Impossible!"). Don't force speaker attribution. Rotating generic voices for audio.

**Why this matters:** Without span classification, a chapter with Wu Yong, Qiao Si Liu, Wu Du Xiu, Ba De, Wu Bei, Tu Shi Cheng, Fang Yuan, Wu An, and Wu Liao all "in the scene" would generate a panel with nine characters, six of whom are absent or dead. Span types feed directly into both pipelines: NARRATION_DESCRIPTION → image prompts, DIALOGUE → speech bubbles, NARRATION_EXPOSITION → skip in visual.

### Phase 2 — Narrative Segmentation (Hybrid)

Detect non-linear segments within chapters:
- Flashbacks, dream realms, visions, POV switches, time skips
- Tag with `narrative_layer`: MAIN, FLASHBACK_OWN, DREAM_OTHER, VISION, PROPHECY
- Tag with estimated story-time relationship
- Detection: rule-based temporal markers ("years ago," "His vision changed," "entered the dream realm," "the memory faded") + LLM fallback for implicit boundaries
- **Default to MAIN/CANONICAL.** Override only on high confidence. A missed flashback costs a temporal misattribution; a false flashback costs the same PLUS a spurious timeline. Conservative detection.
- Dream realm entry in Reverend Insanity is always signalled ("His vision changed"), always has a different cast, and always has a signalled exit. Structurally detectable.
- Time skips → insert `time_skip` marker, represent gap of unobserved state change
- POV detection: track first-person pronoun density spikes, record POV holder as observer

### Phase 3 — Mention Detection (Four Layers) *(revised)*

**Layer 0 — Dialogue-attribution seeding (deterministic, no model).** Runs over
the **full volume before anything else**. Speech attribution is the
highest-precision naming signal a novel offers: `X said` is almost never
anything but a character name, and in dialogue-heavy web fiction it fires
constantly. Chapter titles are parsed too. Matches enter the working list at
HIGH confidence.

This inverts the usual order — the gazetteer arrives already populated and the
model is asked only about what the regex could not see, which is both cheaper
and more accurate than any ML-first ordering. Measured: 0.7 s per novel, no GPU.

**Layer 1 — Qwen2.5 NER** *(replaces GLiNER)*, per chapter, given the Layer 0
working list as context. The deciding factor is training data, not
architecture: Qwen is trained on Chinese web-novel content *and* its English
translations, so it has priors for compound epithet-plus-name forms that read
in English as ordinary noun phrases. Western-trained NER parses those as
descriptions and misses the entity entirely. New candidates enter at MEDIUM
confidence.

**Layer 2 — Growing Gazetteer:** Aho-Corasick automaton over confirmed aliases. Rebuilt after each processing window. By chapter 50, catches most name mentions with zero error. By chapter 100, most decisions are resolved by exact match. **This is the compound-interest mechanism that makes the system get easier as it reads.** Requires three guards: word-boundary matching, a two-character minimum, and an ambiguity blocklist for common words that double as names. It compounds *wrong* decisions equally well — hence the contradiction detector (§6 Phase 6).

**Layer 3 — LLM gap-fill pass:** Send chapter text with already-detected mentions highlighted. Ask: "Are there character or location references NOT already highlighted?" Catches pronouns, oblique references, titles doubling as common nouns, honorific-only dialogue.

**First-appearance strategy — triggered by events, not by chapter number.**
Web novels introduce characters at a constant rate throughout a volume; a new
sect master at chapter 200 is exactly as hard as one at chapter 2. So the
high-quality detection pass is **not** an early-chapter strategy. It fires
whenever Layer 0 finds a name absent from the working list, or the resolver
emits a `new_entity` event **at any point in the volume** — running the formal
introduction-pattern detector and a focused NER pass over the surrounding
context window, then seeding the gazetteer at HIGH confidence.

The difficulty curve is therefore: **easy** for known entities (the gazetteer
handles them), **constant** for new introductions regardless of chapter.

**Additional detection tasks at this phase:**
- Alias type classification (lexicon + LLM for unknowns, batched)
- Parenthetical disambiguation: three types identified —
  - (a) Translator gloss: "(Wu Liao)" as alternate romanization
  - (b) Simultaneous action shorthand: "Wu An (Wu Liao)" meaning "and also Wu Liao did this" — two separate characters (confirmed by checking if both are established as independent entities)
  - (c) Author/narrator disclosure of true identity: "Wu Yi Hai (Fang Yuan)" revealing disguise to reader
  - Disambiguation: heuristic (same-surname check, prior-entity check, clause detection) → LLM escalation for ambiguous cases
- Novel-specific title disambiguation for LOTM-style: "Red Priest" as pathway vs. historical figure vs. current holder. Surrounding syntax gives signal: "X pathway" = categorical, "the X" + action verb = title, "X [FullName]" = compound reference.

### Phase 4 — Speaker Attribution (Four-Tier Escalation)

1. **Explicit attribution** — "Li Wei said" → regex, near-perfect
2. **Proximal attribution** — dialogue follows character action in same paragraph → heuristic, ~85%. Must handle split sentences: "Wu Liao excused himself, but Wu An hesitated and said softly:" → speaker is Wu An, not Wu Liao.
3. **Turn-taking** — alternating speakers in conversation → state machine, ~80%
4. **Contextual** — no tag, no proximity, no alternation → LLM, ~70-80%

**Special cases:**
- Joint attribution: "Wu Liao and Wu An immediately responded" → JOINT_ATTRIBUTION with both speakers
- Inner monologue attributed to POV character automatically
- Crowd reactions tagged as UNATTRIBUTED_CHORUS — no forced speaker
- Delivery-marker extraction runs in parallel: scan for emotion/delivery words ("said calmly," "expressionless," "shouted," "snarled"). These override scene-level sentiment for TTS. **Critical for Fang Yuan** — he is repeatedly described as "expressionless" during the most emotional scenes. Scene-level sentiment would give him dramatic voice; delivery markers correctly give him flat monotone. The contrast IS the effect.

### Phase 5 — Local Anaphora Resolution (NOT Clustering)

**We are NOT using clustering.** Clustering fails on this content because it assumes similarity = identity, which is violated constantly (zero surface similarity between "Fang Yuan" and "Liu Guan Yi"; perfect surface similarity between two different "Elder Wang"s).

Instead: **explicit chain-following with precision over recall.**

**fastcoref is dropped entirely** *(revised)*. It is trained on OntoNotes-style
English literary prose, and the register, sentence rhythm and naming
conventions of translated web fiction sit outside that distribution — its
clusters have to be discarded more often than they can be used.

**Replacement: a five-route strategy, cheapest and most reliable first.**

1. **Attribution adjacency** (deterministic, no model). A pronoun immediately
   following a clear dialogue attribution refers to that speaker. The most
   common shape in dialogue-heavy fiction; the antecedent is stated one clause
   earlier, so no inference is needed.
2. **Honorific-only exchanges** resolve through the **relationship graph**, not
   a pronoun model. A role-only speaker names nobody; the referent is whoever
   stands in that relation to the current speaker, which is a graph lookup.
   Attempting it as coreference is why role-only exchanges defeat generic
   models.
3. **Inner monologue** first-person resolves to the POV character automatically.
4. **Crowd reactions** are tagged `UNATTRIBUTED_CHORUS` and left alone.
   Resolving them invents attributions that propagate into voice casting.
5. **Everything else** goes to the model, batched **per paragraph** with the
   scene's active character list supplied. Paragraph rather than chapter
   batching: an antecedent is nearly always within a paragraph or two, and a
   chapter-sized prompt buries the local evidence while costing far more
   context.

**Validation step after grouping** — check each group for violations:
- Mentions simultaneously present doing different things? → **Split**
- Group spans a narrative-layer boundary (main to dream)? → **Split**
- Cluster count suspiciously high relative to unique rigid names? → escalate

Groups are **split, not repaired**: guessing which half was right trades a
detectable error for a silent one.

- **Local only.** No cross-chapter resolution. Output: within-chapter mention groups, each labelled with most informative surface form.

### Phase 6 — Global Resolution (The Heart — Incremental, NOT Clustering)

**Architecture: incremental entity resolution with evidence accumulation.**

For each local mention group, ask: "Is this an existing entity or someone new?"

**Step 1 — Candidate Retrieval:** Top-k from graph. BM25 over known aliases (with honorific stripping) + semantic similarity over context embeddings. k=10 is enough.

**Step 2 — Evidence Scoring:** Structured evidence vector per candidate (NOT a single similarity score):

1. `declaration_match` — "His true name was," "also known as," "formerly called." Near-perfect precision. Extremely common in web novels. **Highest weight.**
2. `gazetteer_exact_match` — confirmed alias exactly matches. High precision, zero cost.
3. `surface_similarity` — Jaro-Winkler after honorific/title stripping. Handles "Elder Wang" ↔ "Wang."
4. `context_embedding_similarity` — cosine between mention context and candidate profile.
5. `speech_partner_compatibility` — does speaker have known relationship with this candidate?
6. `temporal_validity` — is candidate's alias binding valid at this discourse position? Filter, not scorer.
7. `co_presence_violation` — are candidate and mention simultaneously present doing different things? Strong negative evidence for same entity (but persona-level, concurrency-aware for clones).
8. `audience_scope_compatibility` — does candidate's known scope include current scene's region/faction?
9. `relationship_deictic_resolution` — if mention is "Master" and speaker is known, check relationship graph for mentor relationship.
10. `first_attested_soft_prior` — slight penalty for candidates first appearing after current chapter. Weak, overridable.

**Step 3 — Decision (NOT clustering):** Log-linear model over evidence vector. Hand-initialize weights. Fit by logistic regression on gold annotations. Output: LINK / NEW / DEFER.

**Step 4 — Threshold setting via conformal prediction.** Distribution-free coverage guarantee: "at most α% of auto-linked decisions are wrong." Set α to 5% for link threshold. Defer zone between link and new thresholds.

**Step 5 — Graph update.** LINK → add mention's surface form and context to entity profile, expanding alias set. NEW → create new entity node. DEFER → hold in pending queue.

**Step 6 — Deferred re-resolution.** After more chapters processed, revisit pending queue with accumulated evidence.

**Special-case detectors (run in parallel):**
- **Transfer detector:** "inherited the title," "the new X," "succeeded," "passed the mantle." Emit `rebind` event.
- **Deception detector:** "claimed to be," "posing as," "disguised as." Emit binding with `truth_status=CLAIMED`.
- **Reveal detector:** "had always been," "was none other than," "his true identity." Emit `merge` or update `learned_at`.
- **Death/departure detector:** "fell," "perished," "departed." Close persona binding. If they return, new binding opens. Between death and return: state = ABSENT.
- **Reputation spread detector:** Track when names go from locally known to widely known.

**LLM adjudication for deferred cases (~2-5%):** Send full context — entity wiki summary, surrounding paragraphs, candidate list. Record decision with method and confidence.

**Wiki-style entity summaries (LLMLink-inspired):** Generated from graph at window boundaries. Serve as LLM context during next window's resolution. The graph is the source of truth; the wiki summary is the cache layer for LLM consumption.

### Phase 7 — Event Log and state_of()

**Append-only event log in SQLite.** Each event: sequence number, type, payload, chapter that caused it, hash of facts it read.

**state_of() is the central query:**
```
state_of(target_id, target_kind, timeline, position, observer=READER)
→ {aliases, attributes, relationships, persona, truth_status}
```

Filter: `story_from_lb <= position <= story_to_ub` AND `learned_at <= observer's knowledge position` AND `truth_status != FALSE` (unless observer is SYSTEM) AND `canonicity = CANONICAL`.

**Cache with materialized views at chapter boundaries.** Three tiers:
- Text-derived (mentions, spans, embeddings) → never invalidates
- Graph-derived (resolutions, state_of results) → invalidated by events intersecting read set
- Render-derived (audio segments, panel images) → invalidated by state changes

**Read-set tracking:** Every derived artifact records the graph facts it consulted, hashed. Invalidation = set intersection. No full reprocessing.

### Phase 8 — Entity Tiering by Prominence

Only possible because full volume is processed first. Score every entity on: mention count, chapter span, dialogue line count, relationship degree.

- **Principal** — full reference sheet, dedicated voice, temporal state tracking, state-change-triggered reference regeneration
- **Recurring** — one reference image, one voice from bank, no state variation
- **Incidental** — deterministic template from hashed entity ID. No generation cost. Hash canonical_id + inferred attributes → seed for voice selection and visual template.

Mark inferred attributes as `truth_status=INFERRED` (not ATTESTED). Later textual evidence overrides.

### Phase 9 — Voice Pipeline

**Cast via archetype scoring + graph coloring.**
- Per entity: gender, age bracket, narrative role, register, emotional baseline → archetype match
- Voice bank: 30-50 reference clips covering archetype matrix. Use XTTS or Qwen3-TTS locally.
- **Graph coloring for collision avoidance:** Build co-occurrence graph from mention data. Greedy coloring ensures no two characters sharing a scene share a voice. Non-co-occurring characters reuse freely.
- **Temporal voice evolution:** For principal characters with state changes, modify synthesis parameters (pitch, cadence, breathiness) keyed to state_of() at each chapter.

**Per-line rendering:**
1. Query state_of(speaker, chapter) for current voice parameters
2. Delivery marker (if present) overrides scene-level sentiment
3. Inner monologue gets filtered voice effect (whisper/reverb)
4. Crowd reactions get rotating generic voices
5. Spatial audio: per-setting reverb impulse (cavern, open field, great hall)

**TTS everything in v1.** Span-type tags preserved so filtering is a config change later. When visual pipeline is partially done, add abstraction layer before TTS to filter text.

Export: chaptered M4B.

### Phase 10 — Visual Pipeline

**Beat segmentation:** Break chapters into panel-worthy moments. Rules (scene breaks, location change, action moments) + LLM (cast assignment per beat, setting description).

**Panel casting:** For each beat, query state_of() for every PRESENT character (use reference_mode tags — only PRESENT, never NARRATOR_REFERENCE or DIALOGUE_REFERENCE). This prevents drawing absent/dead characters.

**Reference generation:**
- Principal: regenerate reference image at each state-change point (temporal reference sheets — the visual contribution)
- Recurring: one reference, generated once from peak-information attribute set
- Incidental: deterministic template selection from hashed entity ID
- User-uploaded: IP-Adapter conditioning
- Settings: same approach, reference regenerated at state changes (pre-siege vs post-siege city)

**Panel generation:** 1-2 characters → direct generation. 3+ → compose separately + inpaint.

**Layout:** Template library (10-15 manga layouts) with LLM-selected template per beat type.

**Kinetic viewing layer (post-processing, client-side):**
- Ken Burns / parallax on static panels
- Particle effects by setting type (rain, dust, sparks, snow)
- Transition timing synced to audio narration beats
- No generative video. No identity drift risk.

**Dream realm segments:** visual style modifier (sepia, softened) to signal "this is a memory."

---

## 7. Scoring and Calibration

- **Combination:** Log-linear additive scorer. Hand-initialized weights, fit by logistic regression on gold.
- **Calibration:** Platt scaling or isotonic regression on held-out gold slice → usable confidence values.
- **Three-way gate:** Conformal prediction thresholds with distribution-free coverage guarantee.
- **Escalation ladder as contribution:** Measure % routed to expensive inference vs accuracy gained.

---

## 8. Evaluation — **long-span sparse, not dense short-span** (revised)

### Why the original design measured the wrong thing

The original plan was 3 novels × 20 chapters fully annotated. That design
**measures the regime where this system's contribution is invisible.** BookNLP
does perfectly well inside a 20-chapter window: within 20 chapters a title
rarely changes hands, no reveal lands, and nothing is retroactively corrected.
Every distinctive claim here — title transfer, late reveal, retroactive
correction, reputation spread — lives at **100+ chapter distances**.

### Revised gold design

**Primary: ~200 hard decision points annotated across a full volume.** Every
transfer, reveal, disguise, dream-persona entry, and deception. Sparse but
long-span. This is where the advantage lives and where it must be measured.

**Secondary: 3 novels × 5 chapters dense annotation**, for MUC/B³/CEAF baseline
comparison only. Enough to sit beside prior work on the standard metrics; not
where the argument is made.

**Inter-annotator agreement is a prerequisite, not a footnote.** Atharva and
Aryan annotate a shared subset of **30 hard cases**, and IAA is reported
*before* any results. Without it the gold set is not defensible and neither is
anything computed from it.

**Annotators fill four fields only:** mention text, `alias_type`, target entity,
`truth_status`.

They do **not** fill `story_from_lb`/`story_from_ub`, `observer_id`, or
`asserted_by`. Those are not reliably annotatable by hand, and shipping them
unvalidated would weaken the schema by attaching apparent ground truth to
fields nobody can actually adjudicate.

### Metrics

- Standard: MUC, B³, CEAF against Baseline A and Baseline B (§8.1)
- Transferred-title slice accuracy
- Resolution latency (chapters before correct conclusion)
- Retroactive correction rate — *requires the contradiction detector to exist*
- Deception handling accuracy
- Anachronism rate (mentions bound to a temporally invalid target)
- **Retriever recall@k**, broken down by `alias_type` (§8.2)
- **Escalation rate** — share of decisions routed to human review. A reported
  result, not a failure mode.

**Required ablations:** no temporal scoping; no alias typing; no self/persona
split; cheap-LLM only; strong-LLM only. All are implemented by zeroing named
weights, so they cost no additional LLM passes.

### 8.1 Baselines must be implemented, not merely cited

"BookNLP scores zero on transfers" is a strawman and reviewers will say so. Two
real baselines:

**Baseline A — strong long-context LLM.** 30 chapters of context plus a running
entity list, best available model, no temporal graph and no gazetteer. Pure
in-context resolution. This is the honest upper bound on what a naive LLM
approach achieves, and it is the comparison that actually matters.

**Baseline B — LLMLink reimplementation.** Dual-LLM setup with the memorisation
scheme from the COLING 2025 paper. No temporal binding, no transfer detection,
no correction. The direct academic comparison.

Both run **before** the headline evaluation.

### 8.2 Retriever recall@k — measure before building the scorer

**The scorer cannot exceed the retriever.** If the correct entity is not in the
top-k candidates, no amount of scoring quality recovers it. For the flagship
case — two aliases of one character used in different regions — BM25 contributes
nothing and context embeddings contribute little.

So: annotated mention→entity pairs, run the retriever, report recall@k for
k = 1, 5, 10, 20, **broken down by `alias_type`**.

**If recall@10 on `TRANSFERABLE_TITLE` is below 80%, candidate retrieval is the
research problem and the scorer is not worth tuning.** This is a decision
gate, not a diagnostic.

---

## 9. Advisor-Suggested Enhancements (5 of 8 adopted)

**Adopted fully:**
1. Cross-cultural honorific/title model → alias-type lexicon (section 4.1)
2. Sentiment-conditioned TTS → per-line emotion from dialogue tags + context
3. Active learning from correction behavior → log hesitation/reversals/edit order to re-rank review queue

**Adopted reduced:**
4. Multimodal feedback loop → post-generation consistency checker (persona-aware)
5. Spatial audio → per-setting reverb impulse at mix time

**Deferred/pushed back:**
6. Temporal Consistency Network → rule-based layout templates
7. Jetson edge module → graph IS the external memory
8. DNC memory bank → same as 7

---

## 10. Edge Cases — **novel-specific, not genre-specific** *(revised)*

> **Correction to the original framing.** These were written as though a genre
> implies a fixed set of devices. It does not, and assuming so is expensive.
>
> | Device | Actually scoped to |
> |---|---|
> | **Dream realms** | **one novel** in this corpus. *Not* a cultivation-genre feature — most cultivation novels have no dream mechanic at all. |
> | **Transferable titles** | broadly cultivation-typical, but a given novel may never transfer one. Presence must be verified, not assumed. |
> | Regression loops, system windows | Korean system fiction, not Chinese cultivation |
> | Pathway / constellation epithets | single-source conventions |
>
> Two consequences already implemented:
>
> 1. **Detectors are opt-in per novel** (`segment.MarkerSet`).
>    `MarkerSet.universal()` covers what any prose narrative has — flashbacks,
>    time skips, scene breaks. Everything else is enabled explicitly. A
>    detector hunting for an absent device yields only false positives, each
>    minting a spurious timeline that later facts get bound to.
> 2. **Vocabulary is induced from the text** (§4.5), not seeded from genre
>    assumptions.
>
> The list below is therefore a catalogue of phenomena *observed across the
> corpus*, not a checklist any one novel exhibits.

**Source-text:** romanization instability, translator handoffs, non-diegetic content, system windows as structured data, chapter numbering chaos.

**Naming:** progressive rank mutation (gradual drift not discrete transfer), honorific-only conversations, surname collisions at scale, deliberate name theft, titles that are common nouns.

**Narrative:** time skips with unobserved state changes, POV switching, death without permanence, gender concealment/reveal, non-human speakers (beast companions, sword spirits, system AIs), author continuity errors (detect + flag, don't force resolution).

**Multi-novel:** different vocabulary sets per novel (Sequence vs Rank, Pathway vs Cultivation Path). Lexicon must be novel-specific, seeded per genre, grown during processing.

---

## 11. Competitive Landscape

**Audiobook:** Audibloom, Spoken, Narratory, NovelHive, Alexandria. All re-infer per chapter, no persistent store. Audibloom: 80-90% on clear dialogue tags.

**Comic/Manga:** Anifusion, Dashtoon, Jenova, TextToManga. Reference sheets + IP-Adapter/LoRA. None connect to identity resolution.

**Academic:** LlmLink (COLING 2025) — closest work. Dual LLMs with memorisation. **Treats identity as static.** No temporal binding, transfer, deception, correction. This is the primary positioning target.

**Gap:** No product bridges audiobook + comic through shared temporal identity model. No system handles web-novel naming volatility as first-class constraint.

---

## 12. Repo Structure

Start with 2 packages, split out only when import boundaries are justified:

```
echotales/
├── packages/
│   ├── core/          # models, store, state_of() — imports NOTHING
│   └── pipeline/      # ingest, resolve, audio, visual as internal folders
│                      # split audio/ and visual/ into packages when they exist
│                      # because "generation cannot import resolution" is a paper claim
├── apps/
│   └── api/           # orchestration, job queue, progress, correction UI
├── data/
│   ├── gold/          # annotations
│   └── lexicons/      # honorifics, ranks, transfer patterns per genre
└── tools/             # annotation CLI, replay debugger
```

Dependency rule: `core` imports nothing. `audio` and `visual` (when split) import `core` ONLY, never `resolve`. This keeps "generation pipelines don't need to understand the novel" true in code.

---

## 13. Build Order

**Revised ordering.** Evaluation moved from week 8 to weeks 1–3. The original
order built the scorer for four weeks before anything could measure whether it
worked — and before knowing whether the retriever even surfaced the right
candidate to score.

1. **Phase 0 — Ingestion** (week 1-2): chapter segmentation, content classification, romanization normalization, system-window parsing
2. **Phase 3 — Mention detection** (week 2-3): layered detection (L0 attribution seeding → L1 Qwen NER → L2 gazetteer → L3 gap fill), alias typing, speaker attribution
3. **Evaluation harness** (week 1-3, *moved earlier*): MUC/B³/CEAF on 5 dense chapters. Get a number before building the scorer.
4. **Retriever recall@k** (week 2, *new*): recall@{1,5,10,20} by `alias_type`. **Decision gate** — if recall@10 on `TRANSFERABLE_TITLE` < 80%, retrieval is the research problem and scorer work is premature.
5. **Gold annotation starts** (week 3 onward): ~200 hard decision points across a full volume, plus 3×5 dense chapters. IAA on 30 shared hard cases reported before any results.
6. **Baseline A — long-context LLM** (week 3-4, *new*): 30-chapter context + running entity list, no graph, no gazetteer.
7. **Baseline B — LLMLink reimplementation** (week 3-4, *new*): dual-LLM memorisation, no temporal binding.
8. **Phase 5 — Local anaphora resolution** (week 3-4): within-chapter, with validation
9. **Phase 6 — Global resolver** (week 4-7): THE HEART. Retrieve + pre-filter + score + gate, transfer/deception/reveal detection
10. **Contradiction detector** (week 6-7, *new*): re-score committed links each window; emit `split`/`retract`. Without it the retroactive-correction metric is unreportable.
11. **Event log + graph** (week 7-8): append-only log, self/persona model, state_of(), materialized views
12. **Setting resolver** (week 9-10): same resolver with swapped feature weights
13. **Voice pipeline** (week 10-12): voice bank, archetype-bucketed casting, sentiment-conditioned synthesis, spatial audio. Primary novel only.
14. **Visual pipeline** (week 12-14): **3-chapter showcase only** — see §13.1
15. **Application** (week 13-16): correction interface, integration, upload-to-output workflow

### 13.1 Scope reductions

**Visual pipeline → 3-chapter showcase.** The visual pipeline is demonstration
surface, not contribution. Panels are generated for **three chapters total**,
chosen specifically to demonstrate *temporal reference sheets* — the same
character rendered at two different story-time states. Full-volume visual
generation is a stretch goal only.

**One primary novel.** **Reverend Insanity Vol. 1 (ch 1–199)** carries the
headline results. LOTM and ORV are **generalisation spot-checks at 5 chapters
each**.

Multi-novel breadth is what gets sacrificed. Hard-case accuracy across a full
volume is what is being sold, and three shallow novels demonstrate that worse
than one deep one.
12. **Paper** (week 14-16)

Steps 1-7 are a complete publishable system. If behind at week 9, thin the setting resolver and protect the voice pipeline.

---

## 14. Key Principles (Non-Negotiable)

1. **No clustering.** Incremental entity resolution with evidence accumulation.
2. **Chapter ≠ time.** Three-axis temporal model with timeline IDs.
3. **Self ≠ persona.** Split entity model for reincarnation, disguise, clones.
4. **Generic descriptors never enter the graph.**
5. **Retraction ≠ interval end.** Distinct event types.
6. **Volume-first processing.** Read everything before generating anything.
7. **High-precision automation with a bounded, measurable review queue.** The escalation rate is a reported metric, not a failure mode. *(Replaces "full automation, no human in the loop", which contradicted the correction interface, DEFER queue, active learning, and handoff confirmation.)*
8. **The gazetteer compounds.** Every correct decision makes the next chapter easier.
9. **Precision over recall** in local resolution. False merges are worse than missed links.
10. **Delivery markers override scene sentiment.** "Expressionless" during a climactic scene = flat voice, not dramatic voice.