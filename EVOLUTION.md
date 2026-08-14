# EchoTales — what changed, and why

`plans.md` is the original spec. This file is the diff between it and the
system that exists, written for someone who will work on the code and needs
to know which decisions were *replaced* and what evidence replaced them.

Rule of thumb throughout: **the plan was rarely wrong about the goal and
often wrong about the mechanism.** Almost every entry below is a mechanism
being swapped after real chapters disagreed with it, not a goal being
abandoned. Where a decision is still an open bet, it says so.

---

## The one thing that never changed

The graph is the contribution; audio and pictures are the demonstration
surface. Every query goes through

```
state_of(target, timeline, position, observer=READER)
```

and everything downstream — which voice, which face, which facts a prompt is
allowed to know — is a consumer of that one call. Nothing below touched
this, and several entries below only make sense as attempts to make it
*true* rather than aspirational.

---

## 1. Automation → bounded review

**Planned:** full automation, no human in the loop.

**Now:** high-precision automation with a *measured* review queue. The
escalation rate is a reported metric, not a failure.

**Why:** the plan already contained a correction interface, a DEFER queue,
active learning from corrections, and translator-handoff confirmation. A
system that quantifies and bounds its review burden is a stronger claim than
one that pretends to need none. This one was amended in `plans.md` itself.

---

## 2. Clustering → incremental resolution

**Planned and kept.** BookNLP was tried and failed; clustering was rejected
before any code was written, because identity in this corpus is asymmetric
and conditional — two mentions may share no characters and denote one
person, or be identical and denote two.

**What we learned by building it anyway:** the incremental resolver's
*scorer* has never linked anything. Fed a maximal evidence vector it returns
p=0.711 against a 0.80 threshold. Every link in the system comes from
`score.prefilter()`.

Calibrating against confirmed gold then disproved the obvious fix: precision
plateaus at **0.66–0.77 across the entire usable threshold range**, and a
calibrated gate merges six members of one clan into one entity. **The
problem is the features, not the threshold**, and the pre-filter-only regime
is therefore the correct regime for this feature set, not a workaround.

The shape of a feature that *does* work: `_ambiguous_tokens`, which knows
"Chi" is shared by six people and therefore proves nothing.

---

## 3. Genre rules → per-novel, corpus-derived rules

**Planned:** per-genre edge-case handling.

**Now:** per-novel, and wherever possible *induced from the text* rather
than written down.

**Why, repeatedly and expensively:** every vocabulary written from intuition
has scored zero or near-zero on real chapters.

| Table | Written from | Result |
|---|---|---|
| Combat verbs, v1 | intuition ("slammed", "erupted") | **0 hits** across RI ch1, 8, 20 — a massacre chapter matched none of them, because the translation says "killed" |
| Identity-declaration phrases | lexicon, induced per novel | works |
| Body-change cues | grepped out of RI/LOTM ch1 | works first try |
| Transmigration, bare noun form | intuition | merged a *country* into the protagonist — in a book whose premise is transmigration, the word is topic vocabulary, not a discriminator |

The rule that came out of this: **a cue vocabulary that never fires is worse
than none**, because it silently degrades a score into whatever signal
remains. Grep the corpus first, always.

---

## 4. One flat appearance → per-body, position-dated facts

This is the longest chain of replacements in the project, and the most
load-bearing.

**Planned:** `Self` / `Persona` split, with `SelfPersonaBinding` over
story-time intervals. The plan's own worked example was reincarnation.

**Built first:** one persona per self, open-ended from first sighting — the
common case, with the reincarnation row of the table left aspirational.

**Then:** appearance extraction, which immediately produced the failure the
split existed to prevent. RI chapter 1 is Fang Yuan's death scene, so
extraction gave him `current_condition: injured`, `deathly pale`, robes
"torn to shreds" — and that was his appearance for all 199 chapters.

Three fixes, in order, each exposing the next:

1. **Split standing keys from transient ones.** A garment is `green robes`;
   the shredding is a condition, and conditions belong to the scene.
2. **Date every fact where the text attests it**, not at the entity's first
   sighting. Without this a chapter-90 reveal is available to a chapter-12
   prompt — the ending leaking into the opening, which for a novel built on
   reveals is the worst thing this layer can do.
3. **Detect the body change and file facts against the right body.**
   `persona/split.py`. Fang Yuan is 500 years old in chapter 1 and fifteen
   from partway through it, so *dating* a fact was necessary but not
   sufficient — the facts also had to belong to different things.

**And then one more, which is the current state:** extraction now runs **per
body**, over only the chapters the character was in that body. Pooling both
bodies' evidence into one call asks a model to average a 500-year-old and a
teenager into one face; it answers, and the answer describes neither.

The demonstration, one query, differing only in position:

```
ch1 : tall and lean, gaunt with age and injury, ... aged, hollow-cheeked
ch20: slim adolescent build, not yet grown, ... a boy's face wearing an
      adult's cold, ruthless expression
```

**Still true and worth stating:** a body the prose never describes cannot be
extracted, only written down. `canon.py` is that layer, and it is deliberate
— a reader beats an extractor, and for a novel's most recognisable
characters it is not close.

---

## 5. Entity table → typed entities

**Planned:** entities are people.

**Now:** `TargetKind` carries `LOCATION`, `ORGANIZATION`, `ITEM`,
`MOB_GROUP` alongside `SELF`/`PERSONA`, and `kind.is_person` is the single
check every consumer uses.

**Why:** Phase 6 resolves every recurring *name*, and names denote places and
objects as readily as people. Deleting the non-people was tried first and
over-deleted real content — "the Gu Yue clan" and "the Spring Autumn Cicada"
are worth resolving. So they are kept and typed. Measured: 45 of RI's 120
entities are not people, and typing is what keeps them out of the voice cast.

Typing is **unanimous, not majority**: one founding mention labelled
"character" keeps the entity a person, because a wrong `SELF` is a visible
correctable row while a wrong `LOCATION` silently deletes a character from
voice *and* panel casting at once.

---

## 6. Per-span model calls → a hard budget rule

**Planned:** model calls wherever they help.

**Now:** *no stage may call a model per-span or per-mention at bulk.*

**Why, measured:** 1.9 s/call steady state. Against 600 chapters / 65,296
spans that is **34.5 hours per span**, 19 minutes per chapter, 29 seconds per
40-chapter window. Batching gains nothing — token generation is the
bottleneck, not request overhead.

Consequence: every model stage is per *chapter*, per *entity*, or per
*candidate*, never per occurrence. Appearance, world facts and character
profiles are ~80 calls for a 199-chapter novel; the body-change adjudicator
is 8.

---

## 7. Bigger models → a hard VRAM ceiling

**Planned:** best available model per task.

**Now:** every local model must fit **entirely** in 8 GB of VRAM, enforced
by measured size at preflight rather than by name.

**Why:** partial CPU offload is not a neutral trade here — the pipeline
already streams chapters to stay inside ~4.5 GB of free system RAM, so a
spilling model competes with the pipeline itself. `qwen2.5:14b` is ~9 GB of
weights before any context and is deliberately unused despite being better.
Hard adjudication escalates to an API tier instead; that is the one stage
that genuinely wants a bigger model.

---

## 8. One panel per paragraph → beats, then dramatic beats

**Planned:** Phase 10 specified beat segmentation.

**Built first:** one panel per block, which produced **89 images for one
chapter**, mostly near-duplicate backgrounds, each drawn from one
paragraph's worth of context.

**Then:** `render/beats.py` — a beat starts where the picture would change
(segment boundary, cast change, prose-kind shift, accumulated length), and
everything inside it shares one panel. RI ch1: 92 blocks → 14 panels.

**Then, because every chapter saturates the budget:** the *merge* rule, not
the boundary rule, is what actually decides what gets drawn. It kept the
longest beats, and in a web novel the longest prose is exposition —
cultivation mechanics, an inventory of a Gu room, a clan's history. It now
merges by the director's impact score, with length only as a tiebreak.

**And one more, because scoring alone still missed the chapter's climax:**
"I have been reborn, going back to the time of 500 years ago" scored zero
(no cue knew a transformation was drawable) *and* sat interior to a
thirteen-block beat about clan elders discussing the weather — unreachable
by a merge that only chooses between beats. A body change is now both a
boundary and a score, from the same cue table the graph splits personas on.

The through-line: **one definition of "a body changed here"**, consumed by
the graph, the beat segmenter and the director, so they cannot drift. They
already drifted once — the director's combat stems and `motion.py`'s clip
tags became disjoint vocabularies, and a block scored maximally on violence
then played the neutral idle loop.

---

## 9. Hosted image APIs → local generation

**Planned:** hosted generation.

**Now:** local (`--image-engine manga`) for shipping; a paid API is a
last-resort, reserved for a demonstration chapter or two.

**Why, all tested with real keys rather than read off documentation:**

| Backend | Result |
|---|---|
| OpenRouter | works, ~$0.05/image; no free image model exists there; a content-filtered call still bills |
| Gemini direct | HTTP 429 `limit: 0` on every image model — the free tier has no image quota at all |
| NVIDIA NIM | authenticates, then times out past 180 s |
| Pollinations | HTTP 403, no longer keyless |
| **Local** | free, unlimited, unfiltered |

Content filtering is a *permanent* property of the hosted path for this
corpus — RI chapter 1 is a massacre and both hosted backends refuse it. And
local is the stronger product architecture anyway: each user brings their own
GPU, so per-user cost is zero.

---

## 10. Gold set: dense short-span → long-span sparse

**Planned:** dense annotation of a few chapters.

**Now:** sparse annotation across a long span, because the hard cases are
*cross-chapter* — an alias dropped at chapter 4 and reused at chapter 90 is
invisible to a five-chapter dense set.

**Status, stated exactly:** RI ch1–60, 3,457 mentions, **0% human-confirmed**.
`eval/gold.py::GoldSet.confirmed_only` is the enforcement point. Nothing may
report a number off the unconfirmed set as a result.

---

## 11. Things that only showed up by running it

Not design changes — defects that changed how the code is written. Kept
because each cost real time and would cost it again.

- **`Span.speaker_self_id` does not hold a `Self` id.** The attribution
  ladder writes a surface form there and resolution never revisits it.
  Anything keying off that column must join on `comparison_key` first. Found
  twice, independently, by voice casting and by body-change detection.
- **Block-local vs chapter-absolute offsets.** `Span.start` and
  `Mention.offset` are block-local; `story_text` is the joined chapters.
  Sorting by offset alone scrambled reading order — which looked like the
  webview "cutting off sentences" and was silently feeding the resolver
  mentions out of discourse order.
- **`Self.prominence` is stale in every database built before it was
  written.** Derive it from mention count; trusting the column makes a stage
  silently process nothing.
- **An unresolved pronoun is not a mention.** Both body-change worked
  examples sit in blocks whose only reference to the character is "his", so
  a same-block presence rule found neither. Mention resolution is the ceiling
  on every extraction stage above it.
- **Green tests are not "safe to iterate unattended".** A corrections log
  keyed off novel id rather than database wrote 12 auto-flags referencing a
  throwaway run's entity ids into the real file. Every unit test was passing
  while this was live.
- **Look at the output.** Full-colour images despite a monochrome prompt; a
  reference sheet drawn as a literal collage of twelve thumbnails; the male
  protagonist rendered as a woman because his stored gender read `unknown`
  and the word "person" hands an anime checkpoint a female prior. No test
  catches any of these.
- **Look at the *composed* output, not just isolated generations.** Every
  panel-prompt fix in this document was found by generating single images
  in isolation and looked correct in isolation. Watching one assembled
  chapter video surfaced three defects none of those generations could:
  `Mention.target_kind` going stale after the resolver retypes an entity
  (a location and an organisation rode into a panel prompt as people, and
  the checkpoint drew a stranger with no grounding at all); `get_panel_cast`
  scoping "who's present" to a whole chapter-wide `NarrativeSegment` instead
  of a block, so a group conversation and a scene fifty blocks away shared
  one cast; and a hand-authored staging directive silently losing a budget
  fight to a *shorter, less important* appearance clause, twice, because a
  greedy token-fit tries whatever comes first in the list regardless of
  which matters more. None of these are visible from one prompt's token
  count or one panel's pixels — only from watching the whole thing play.
- **A modern `setuptools` breaks a well-known TTS library, silently.**
  Chatterbox's watermarker (`perth`) imports `pkg_resources`, which
  `setuptools` stopped bundling somewhere past v81 — the failure is
  `TypeError: 'NoneType' object is not callable` deep inside a class
  constructor, nothing about missing setuptools in the message at all.
  `uv run --with chatterbox-tts --with "setuptools<81"` is the fix, and
  it is also the answer to the earlier-recorded "chatterbox and diffusers
  can't share a venv" blocker: `uv run --with` resolves an ephemeral
  overlay *per invocation* rather than modifying the project's own
  `.venv`, so the image-generation environment was never actually at risk
  — the two stages just needed to run as separate processes, which they
  always could.

---

## Where this leaves the original plan

Intact: the three-axis time model, self/persona, typed and induced aliases,
incremental resolution, the four-tier attribution ladder, bounded review.

Replaced by evidence: the scorer's role (pre-filter carries it), genre-level
rules (per-novel and induced), per-span model calls (budget rule), bigger
models (VRAM ceiling), one-panel-per-paragraph (dramatic beats), hosted
images (local), dense gold (long-span sparse).

Still open bets: the scorer's feature set, the declaration detector for
transmigration, concurrent bindings for clones and possession, and whether
any of the entity counts in `HANDOFF.md` survive contact with confirmed gold.
