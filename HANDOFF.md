# EchoTales — Handoff

**Purpose: current open tasks only, ephemeral.** This file answers "what do
I work on next" and nothing else — it should be readable in under a
minute. The history of how the system got here (every fix, every
completed defect, the reasoning behind each change) lives in
`EVOLUTION.md`, not here. A render-version number (`v44`, `v51`, `v54`,
...) is tracked in the relevant novel's `panels/ch<N>/VERSIONS.md`, never
here and never in `EVOLUTION.md` — a HANDOFF/EVOLUTION section number
(like "4.52") is not a render version, and the two must never be
conflated.

**The other three, in the order you want them:**

| File | Answers |
|---|---|
| `EVOLUTION.md` | *Why is it built this way?* The diff between the original spec and reality — which mechanisms were replaced and what evidence replaced them, plus the permanent, append-only session log. **Read before changing a design decision, or to find out what was already tried.** |
| `architecture.md` | The model: three axes of time, self vs persona, observers |
| `details.md` | Per-file detail |
| `plans.md` | The original spec. Amended three times; the amendments win and are marked *(revised)* |

**Last updated:** 2026-08-31.

## Pick up here

The live area of work is the render/direction pipeline
(`packages/pipeline/src/echotales/pipeline/render/`). Most recently
(EVOLUTION's newest entries): the byte-identical crowd-panel bug, a
solo-tag front-load gap, and a Danbooru-tag-form gap in the crowd/solo
contradiction validator were all found and fixed, then confirmed at full
48-panel scale (`v54_crowd-solo-scenestate-fix`, see `VERSIONS.md`).

**New, not yet investigated:** block 31 of RI ch1's v54 render mis-casts
**"Qing Mao Mountain" — a location — as a named character**, attaching
appearance attributes (`black_hair, blood, wounded, androgynous_person`)
to it and rendering two figures despite a `standing_alone` layout tag
with no `solo` anywhere in the prompt. This bypassed `cast_tags()`'s
silhouette-fallback branch entirely, meaning something upstream in
persona/cast resolution treated a place name as a resolved character.
This is a **persona/resolution bug** (a location entity leaking into
character casting), not a prompt-construction or crowd-contradiction
issue — do not conflate it with anything in the render-path fixes above.
Next step: trace where "Qing Mao Mountain" (presumably a `Self`/mention
entity with `kind` misclassified, or a cast-resolution step that doesn't
filter on `entity.kind.is_person`) gets into a panel's resolved cast.

**Process note for whoever debugs this next:** `prompt_cache_v1.json` is
a phase-1/stub-engine intermediate, not the delivered prompt — a
mid-session misdiagnosis this round came from reading that file instead
of `manifest.jsonl`. Always check the manifest (or the real generation
call) for what a panel actually received.

## Open defects — highest priority first

**Full history — every defect found, fixed, and the reasoning behind each
change — lives in `EVOLUTION.md`, not here.** This section is only what's
genuinely unresolved *today*.

1. **The scorer's features are too weak to link anything** (root cause,
   not a tuning gap). Calibrating against confirmed gold disproved the
   obvious fix: precision plateaus at 0.66–0.77 across the entire usable
   threshold range, and a calibrated gate merges six members of one clan
   into one entity. Every link in the system runs through the pre-filter,
   never the scorer. Needs better features (`_ambiguous_tokens` is the
   shape of what works), not a rebalanced weight.
2. **LOTM's transmigration reveal still isn't caught.** "Zhou Mingrui"
   acquiring "Klein Moretti" needs a *declaration* pre-filter that
   recognises "memories began flooding him" as an identity-continuity
   assertion — structurally different from a name-containment fix, not
   yet built. This is also why the persona split can't demonstrate LOTM's
   worked example: resolve still produces two selves, so there's no one
   consciousness for two personas to hang off.
3. **Speaker attribution regressed with LLM layer 1 and hasn't recovered**:
   64.9% (deterministic) → 48.8% (full RI volume). Confirmed as a real,
   user-visible problem — an identifiable speaker (the clan leader) got
   cast as anonymous.
4. **Retriever recall@k has no gold annotations.** The self-retrieval
   smoke test passes 100% at every k by construction (it only proves
   there's no indexing bug); real recall is unmeasured.
5. **Contradiction detector unvalidated on real data** — fires correctly
   on constructed over-merges, finds zero on 60 real chapters, which is
   diagnostic (Phase 6 over-splits, so nothing accumulates enough aliases
   to trigger it) rather than reassuring.
6. **Clan-prefix alias linking gap**: "Gu Yue Dong Tu" (full name) doesn't
   auto-link to a bare "Dong Tu" alias elsewhere — no surname-prefix
   stripping in `variants.py`.
7. **`TargetKind` typing is a review flag, not a real type.** A
   non-person entity gets an automatic `flag` correction instead of
   silently joining the cast, but a *kept* item/location still displays
   and behaves like a character everywhere else (webview, voice casting).
   Likely the same root cause as the new Qing Mao Mountain defect above —
   worth checking together.
8. **Recurring unnamed characters have no cross-chapter persistence** — a
   named character's retinue or a minor recurring character gets a fresh
   anonymous voice slot every chapter.
9. **ORV block classification gaps**: 188 `HEADING` blocks survive per
   novel; `SYSTEM_WINDOW` detection under-fires because this source's
   status messages are bracketed prose, not `Key: Value` lines.
10. **`create_mention` has no frontend UI** — backend and tests exist; a
    reviewer can't trigger it from the browser yet.

## Architecture-review items not yet implemented

From the 2026-08-06 review. None of these are done; all are folded into
the docs.

| # | Item | Status |
|---|---|---|
| 1 | Contradiction detector + gazetteer blocklist | **DONE** — `resolve/contradiction.py`, swept at each window boundary; `split` now actually fires. Blocklist in `gazetteer.AMBIGUITY_BLOCKLIST`. **Unvalidated on real data** |
| 2 | Retriever recall@k harness | **PARTIAL** — `eval/retriever_eval.py` built with the 8.2 gate. Gold mode needs annotations; self-retrieval smoke test passes 100% @all k (313 cases, no misses), which only proves there is no indexing bug |
| 3 | Long-span sparse gold (~200 hard cases) + IAA | **not started** |
| 4 | Mondrian/class-conditional conformal by `alias_type` | **not started** — current gate is standard conformal |
| 5 | Scorer reduced to 5 features; `declaration_match` + `gazetteer_exact_match` as hard pre-filters; `co_presence_violation` as hard blocker | **DONE**, plus `name_containment` as a third pre-filter. But the pre-filters are not an optimisation, they are the *only* path to a link (see open defect 1). |
| 6 | Lexicon induction confidence tiers (admit single-sample at LOW) | **not started** — `induce.py` currently *excludes* single-sample terms (`min_support=2`) |
| 7 | Voice coloring within archetype buckets | not started (voice pipeline unbuilt) |
| 8 | Asymmetric segmentation thresholds (aggressive on explicit, conservative on implicit) | **not started** — currently uniform |
| 9 | Visual pipeline → 3-chapter showcase | scope change, pipeline unbuilt |
| 10 | RI Vol 1 as primary; LOTM/ORV 5-chapter spot-checks | scope change |
| 11 | Baseline A (long-context LLM) + Baseline B (LLMLink) | **not started** |
| 12 | Drop "full automation" framing | docs updated |
| 13 | `audience_scope_compatibility` scoped to explicit region tags | **not started** — currently returns 0.5 default |

## Decisions already made — do not relitigate

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
