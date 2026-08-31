# EchoTales — what changed, and why

**Purpose: permanent changelog, append-only, never pruned.** Every
numbered session/fix entry lives here for good — nothing gets deleted or
summarized away, even once a defect is fixed and no longer "current."
`HANDOFF.md` is where *current* open tasks live; when a HANDOFF entry
is resolved or superseded, it moves here rather than being deleted, so
the reasoning behind a decision stays findable later.

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

**Measured render wall-clock, RI ch1, 8 GB VRAM (2026-08-15):** 14 panels,
`--image-engine manga --motion-engine svd --compose-engine ffmpeg`, cold
model load included — **30m55s** end to end, with `--no-director` (LLM art
direction skipped). `0` panels reused from cache, `7` generated with real
reference conditioning (the first successful conditioned render since the
mechanism was wired up), `7` prompt-only (only 2 of the chapter's personas
have a reference sheet on disk yet). `0` motion clips despite `--motion-
engine svd` and a 2-per-chapter budget — not yet explained, worth checking
`director.py`'s clip-placement gate against this specific chapter before
assuming the SVD engine itself is broken. Final video: 646s at 1.0x speed
(the reverted default; ~545s at the previous, too-fast 1.25x default is
consistent with this once speed-scaled).

**The LLM director and the local diffusion engine cannot run in the same
`render` invocation on 8 GB VRAM.** `--image-engine manga` (no `--no-
director`) with `ollama serve` warm from the director's own calls earlier in
the *same run* hit `CUDA OutOfMemoryError` loading the diffusion pipeline —
ollama's resident model (~5 GB) plus the diffusion pipeline don't both fit.
This is the same non-negotiable `HANDOFF.md` section 3 states for the LLM
tier ("no stage may share the GPU with another resident model"), just newly
discovered to apply *within* one `render` invocation too, not only across
separate pipeline phases -- `cmd_render` builds an LLM client for art
direction and loads the local image engine in the same process, with no
ordering guarantee that ollama's model has unloaded (its own idle timeout,
not this pipeline's) by the time diffusion needs the GPU. Until `render`
sequences the two (or `ollama serve` is stopped beforehand, same as the
voice-synthesis rule already documented in `HANDOFF.md` section 8),
**`--no-director` is required alongside `--image-engine manga`**, not merely
an option — the mechanical prompt path still gets every non-LLM fix (beat
boundaries, mob detection, locale cues), it just skips LLM-authored prompt
phrasing.

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

### The 2026-08-18/19 visual-and-audio run — every setback, in the order it bit

Written for study: each one is *symptom -> what it looked like -> what it
actually was -> the lesson that generalises*. Several of these look like
different bugs and are the same mistake wearing different clothes.

**1. A fix that was patched onto the wrong class and passed every test.**
Genre anchoring meant for `IllustriousEngine` was applied by a scripted
`str.replace` that matched the *first* occurrence of a common line, which
lived in `SDXLEngine`. Result: `SDXLEngine.generate` referenced a
`quality_prefix` field it did not have (an `AttributeError` waiting for
anyone who chose that engine) while `IllustriousEngine` silently kept none
of the anchoring it was supposed to get. Two rounds of renders were
attributed to "the checkpoint ignores genre tags". *Lesson: a scripted edit
that matches on generic text is a coin flip; assert on something unique to
the target, and read the diff.*

**2. The stale prompt cache that ate two fixes.** `prompt_cache` keyed on
`chapter:block`. Beat selection changed twice, and both times the render
served prompts written for the *old* beats -- so the measurement said "no
change" and the natural conclusion was "the fix does not work". *Lesson: any
cache key must contain every input that can change the cached value. If a
fix appears to do nothing, suspect the cache before suspecting the fix.*

**3. Scene-wide scoping, applied three times, wrong all three.** Panels used
to be one-per-scene, so "resolve it over the scene" was correct everywhere.
The moment scenes were chunked into several panels, the same line of
reasoning became a hallucination source in three separate places: crowds
(`cast.background_mobs`) asserted a besieging army over a dying man's
private thoughts; cast (`get_panel_cast`) handed the protagonist to a scene
of elders gossiping, and the director wrote him into it; beat prose fell
back to the scene's narration, i.e. a different moment. *Lesson: when a unit
of work is subdivided, every "per unit" scope decision inherited from the
old granularity is now a bug. Grep for them deliberately -- they will not
fail a test.*

**4. Anonymous voice slots that collided on purpose.** The slot counter
restarts at 1 after every attributed line, and ids were chapter-scoped, so
collisions were not rare -- they were systematic. A cultivator besieging the
protagonist and a villager gossiping three hundred years earlier were both
`anon:1:1`, read by TTS in one voice. *Lesson: an id scoped to the wrong
unit is worse than no id, because it asserts sameness rather than admitting
ignorance.*

**5. Then the fix for #4 did nothing, for a reason worth remembering.**
Scoping slots to `ActiveScene` changed no output: narrative segmentation
emits exactly **one MAIN segment per chapter across all 199** (200 segments,
199 chapters). The type was named `ActiveScene` and was not a scene. *Lesson:
verify what a table actually contains before scoping anything to it; a
plausible name is not evidence.*

**6. A checkpoint that reads a moral word as a species.** "Demon" in this
novel is name-calling. The SDXL checkpoints drew a grinning red-eyed youth
with fangs and a forehead gem. The first fix was a negative-prompt patch,
which fixes one word in one novel. The graph-derived version had its own
trap: the obvious source -- resolved mentions -- has *never once recorded
the bare word "demon"*, because resolution only mints mentions for name-like
spans; it knows "Bloodwing Demon Sect". Evidence had to come from prose,
gated by graph presence. *Lesson: "the graph knows this" is a hypothesis.
Check which table would hold it before designing on top of it.*

**7. Two filters that had to be measured, not assumed.** The lexicon nearly
suppressed the novel's real content: RI's characters call each other worms,
wolves and beasts, but the book also contains actual worms, wolves and
beasts, and glossing those words would have emitted "animal head, fur,
claws" as a permanent negative. Counting over all 199 chapters gave the
split -- demon 5/27 and god 4/13 are mostly name-calling; worm 47/737, wolf
19/604, beast 9/199 are mostly animals. *Lesson: a heuristic's threshold is
a measurement, not a taste. The corpus already contains the answer.*

**8. A diffusers API shape that only breaks with two inputs.**
`ip_adapter_image` takes one entry *per loaded adapter*, with a nested list
for that adapter's images. A flat list of two raises. Harmless for months
because no panel ever carried more than one reference -- then curated
references landed and it killed a full chapter run 54 panels in. *Lesson: a
latent API misuse surfaces the day a feature makes the second case reachable.
The bug was introduced long before the change that exposed it.*

**9. Fandom returned 403 to urllib's default User-Agent** -- indistinguishable
from "this novel has no wiki", since both produce an empty result. Then the
subdomain guess was wrong (`reverend-insanity`, not `reverendinsanity`),
which produces 404, which also looks like "no page". Then sequential requests
were dropped silently, so a page that fetched fine alone vanished inside a
60-page loop, and the cache -- which overwrote rather than merged -- deleted
the entries an earlier run had got. *Lesson: on any network path, make
"absent" and "failed" different states in the report, and never let a
refresh be destructive.*

**10. Resolution thinks Gu worms are people.** Understandable -- the novel
talks about them the way it talks about characters -- and it meant the wiki
importer wrote `skin_tone=bronze` into the canon of things that are not
characters. The wiki's own categories were a better classifier than our
resolver. *Lesson: when an external source disagrees with the pipeline about
a type, it is worth asking which one is actually better positioned to know.*

**11. Delivery markers read from inside the quoted line.** A besieging
cultivator shouts "Fang Yuan, *quietly* hand over the Spring Autumn Cicada"
-- "quietly" is what he demands, not how he says it. Six of chapter 1's
twenty-seven dialogue lines were marked HUSHED and whispered. *Lesson: a
signal has a location as well as a vocabulary. Matching the right words in
the wrong span is a category error, not a tuning problem.*

**12. The emotion dial that could not produce emotion.** Chatterbox clones
the prosody of its reference clip, so `exaggeration` scales intensity around
whatever that clip already sounds like -- and every clip was VCTK read
speech. No setting makes a man reading a prompt sentence sound like a
warlord. The fix was a different *corpus* (CREMA-D, 91 actors performing six
emotions), not a different number. *Lesson: check what a parameter is
relative to before tuning it.*

**13. Inserting a dataclass field in the middle.** `DeliverySettings` gained
an `emotion` field, positioned third; every existing positional construction
silently shifted `pitch_semitones` into `rationale`. Caught by one assertion
comparing a float to a string. *Lesson: append-only for any dataclass that is
constructed positionally anywhere -- or make it keyword-only and take the
churn once.*

**14. Filenames that encoded the wrong thing.** Panels were named for their
lead block, so one scene produced `block0021`, `block0026`, `block0047`, and
a directory listing interleaved panels from different scenes. Reading the
output required knowing the slot-assignment algorithm. *Lesson: an artefact's
name is an interface. Sort order is part of it.*

**15. The measurement that was missing until late, and immediately paid.**
Every relevance defect up to this point was found by a human opening a PNG.
Once `echotales relevance` existed, it found in minutes that prompt assembly
ranked the standing appearance clause above the beat, so the beat kept losing
the 77-token budget -- panels of a correct-looking man doing nothing
identifiable. *Lesson: in a pipeline whose output is subjective, the
highest-leverage code is often the thing that turns "looks wrong" into a
number. Build it earlier than feels justified.*

**16. Two ways of destroying your own evidence.** A working copy of the
database was truncated to zero rows by an interrupted process, and a `pkill`
pattern aimed at a render matched the shell that owned it. Neither lost real
data because the originals were untouched -- which is the only reason they
were merely annoying. *Lesson: measure on copies; keep the originals
read-only in practice; and check what a kill pattern matches before running
it.*


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

---

## Full session-by-session record

**This is the detailed, dated log HANDOFF.md used to carry directly.**
Moved here so HANDOFF.md can stay a short pick-up-here document; nothing
below is current-state reference — for that, read HANDOFF.md's own
condensed open-defects list, which supersedes any specific number quoted
in an old entry below it contradicts. Kept close to verbatim rather than
rewritten, since the value here is the measured evidence and the
reasoning at the time, not prose polish.

## 4. Open defects — highest priority first

### 4.1b Gold confirmed, gate calibrated — and the answer is "the features are too weak" *(2026-08-12)*

The owner bulk-approved the gold set (Section 4.12) so calibration could finally
run. **It ran, and it disproves Section 4.1's implied fix.** Recorded here because
the negative result is more useful than the item it replaces.

`eval/calibrate.py` replays resolution against confirmed gold and labels
every scored (mention, candidate) pair, producing the
`(probability, is_correct)` input `ConformalGate.calibrate()` always wanted
and never had. On RI vol 1, 964 scored pairs:

| | n | min | median | p90 | max |
|---|---:|---:|---:|---:|---:|
| correct | 95 | 0.169 | 0.217 | 0.291 | 0.349 |
| incorrect | 869 | 0.049 | 0.061 | 0.161 | 0.334 |

**First finding: a floor in `calibrate()` made calibration a no-op.**
`link_threshold = max(incorrect[index], 0.5)` sits above the scorer's entire
observed range (0.049–0.349), so every calibration silently fell back to
`FALLBACK_LINK_THRESHOLD = 0.80`. That floor was Section 4.1's mechanism. Removed —
`ScoringModel.probability` is a logistic over hand-set weights with a large
negative bias, so its output is a *score*, not a likelihood, and reading 0.5
as "even odds" is a category error.

**Second finding, and the important one: fixing the threshold does not fix
the problem.** The scorer separates correct from incorrect only weakly, and
precision never becomes acceptable:

| threshold | links | precision | recall |
|---:|---:|---:|---:|
| 0.181 (best F1) | 139 | 0.662 | 0.968 |
| 0.220 | 63 | 0.714 | 0.474 |
| 0.250 | 34 | 0.765 | 0.274 |
| 0.335 | 3 | 1.000 | 0.032 |

Precision plateaus at **0.66–0.77** across the entire usable range. Applying
the calibrated gate (alpha=0.05, threshold 0.188) gives 62 entities and
visibly wrong merges — `Chi Chen`/`Chi Lian`/`Mo Chen`/`Chi Shan`/`Chi She`/
`Chi Zhong` collapse into one entity, as do `Lord Yao Ji`/`Ruo Nan`/
`Tie Xue Leng`. Surname-sharing characters are exactly what the scored
features cannot separate.

**So the pre-filter-only regime is not a workaround, it is the correct
choice for this feature set**, and Section 4.1 should be read accordingly: the
problem is not an unreachable threshold, it is that
`surface_similarity`/`context_embedding_similarity`/`speech_partner`/
`temporal_validity` do not carry enough signal to separate two members of
one clan. **The next move is better features, not a better threshold** —
and `_ambiguous_tokens` (Section 4.15) is the shape of what works: a signal that
knows "Chi" is shared by six people and therefore proves nothing.

Default behaviour is unchanged (82 entities / 821 links): an uncalibrated
`ConformalGate` still uses the fallback thresholds, and nothing enables a
calibrated gate automatically. Reproduce with
`eval/calibrate.py::calibrate_from_gold` against a scratch DB.

### 4.1 The scorer cannot reach LINK *(blocker — root cause found; see Section 4.1b for the resolution)*

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
threshold by hand is fitting to nothing, which is the Section 4.6 trap. What was fixed
instead is the categorical half: signals that genuinely *are* near-certain moved
into the pre-filter where they can act. See Section 4.11.

The real fix is gold + `ConformalGate.calibrate()`, still Section 5 item 3.

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

### 4.3 Contradiction detector — built *(review Section 1, done)*
`resolve/contradiction.py` sweeps at every window boundary and on a final pass,
re-scoring committed links against evidence accumulated since. Three classes:
co-presence discovered later, too many distinct normalised names, and
mutually-exclusive attribute conflicts. Emits `split` and returns affected
entities to the deferred queue. See Section 4.8 for its validation gap.

### 4.4 Gazetteer guards — complete *(review Section 1, done)*
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
The harness exists (`eval/retriever_eval.py`) and enforces the Section 8.2 gate, but
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
trigger it. It cannot be validated against the corpus until Section 4.1 thresholds are
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
per Section 4.1 a scored feature could not have linked them.

Two guards, both load-bearing and both tested:
- The shared tail must be **≥ 2 tokens**, so a bare shared surname does not
  merge a family. That is Section 4.5 restated structurally, with no clan list.
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

| Metric | deterministic | + LLM layer 1 | + the Section 4.11 fixes |
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
   entity *typing* (Section 4.9 item 3 as originally written) rather than a filter, so
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
"item/artifact names — needs entity typing" (Section 4.9 old item 3) for the
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
flagging it rather than tuning blind, per Section 4.6's warning. **Extend gold past
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

### 4.14 Full RI vol 1 run, LLM layer 1 + all Section 4.11 fixes

The 40-chapter numbers held up at full volume, and the shape of the win is the
same: not a small improvement, a different regime.

| Metric | deterministic (Section 4.9 original) | LLM + fixes, full 199 ch |
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
the 40-chapter sample's 54.3%) -- confirms Section 4.9's flagged regression and shows
it compounds over the volume rather than being a chapter-1-5 artifact. This is
now the clearest single number arguing that layer-1 recall is too tight, ahead
of the singleton rate.

### 4.15 Cross-novel A/B (LOTM, ORV ch1-40) — one real defect found, not xianxia-overfitting

Run to check whether Section 4.11's fixes (`name_containment` especially) were
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
declaration phrases are induced per-novel (Section 6), so a phrase this
novel-specific was never going to be in the seed lexicon; it would need
either a broader structural pattern ("memories... flooded/surfaced/returned")
or to wait for the lexicon induction pass to see enough examples across the
volume. Not fixed this session -- flagged because it's a clean, specific,
citable case for whoever tackles the declaration detector next, and because
it's independent confirmation that reincarnation/transmigration (which
`architecture.md Section 4` designed for) is currently unhandled by any live code
path, matching Section 4b's finding that `Persona` itself has no runner.

**ORV (859 -> 63 entities, same regime shift) found a second, cleaner case of
the same failure family — since fixed, see the top-of-file note on this
session's work; left as originally written below for the diagnosis history.**
Structural, not a one-off reveal, and diagnosed
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
leading component dropped. `name_containment` (Section 4.11) doesn't catch it
because the shared tail is **one token**, and the >= 2-token floor is there
specifically to stop a bare *surname* from merging unrelated people (Section 4.5,
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
resolver as input"** -- Section 6 rules that out explicitly (a resolver graded
against its own answer key measures nothing). Instead:

1. **Logged** (`corrections.py::Correction`, JSONL per novel at
   `data/corrections/<novel>.jsonl`) as a human-provenance record, distinct
   from and *not* the same file as the model-drafted gold in `data/gold/` --
   this is a faster, less rigorous log meant to accumulate real evidence for
   calibrating `ConformalGate` later (Section 4.1), not a replacement for gold review.
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
  classifier split (Section 4.16's quote-plus-narration-tag case is the common one).
  "merge ↑" button, hover-revealed per line. **No live preview** -- folding
  two spans into one mid-render was judged too likely to hide a subtle bug for
  the time available; the merge is only visible after Apply. Verified directly
  instead: applying the exact Section 4.16 example (block 29, chapter 9) turned two
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
`Zhou Mingrui` in LOTM (Section 4.15) produced one 1131-mention entity; merging RI
chapter 9 block 29 (Section 4.16) restored the quote-plus-narration-tag sentence to
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
see architecture.md Section 4's new note on this being a stand-in for `Persona`,
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

### 4.20 Session — six root-cause fixes, tier-4 attribution, entity auto-flag, corrections capabilities, gold-eval wiring (2026-08)

A long session working from user-reported webview defects on RI/LOTM/ORV
chapters 1-60. Root-caused each report rather than patching the symptom;
several turned out to be the same underlying bug wearing different faces.
All merged to `master` in separate commits (see git log for exact diffs).

**Pipeline fixes:**
- `mentions/gazetteer.py` `AMBIGUITY_BLOCKLIST` gained "gu" and "veil" —
  genre-common nouns (RI's worm/insect term, LOTM's spirit-barrier term)
  that the determiner-rate filter can't catch (rarely take "a"/"the" in
  these books' phrasing) and that were becoming standalone gazetteer
  entities, matching every bare occurrence.
- `ingest/epub.py`/`adapters/base.py`: EPUB emphasis detection only saw
  inline `<i>`/`<em>` tags. LOTM marks some inner-monologue paragraphs with
  a whole-block CSS class instead (`<p class="block_6">`, italic via the
  stylesheet) — `Epub.italic_classes()` now parses bundled stylesheets for
  `font-style: italic/oblique` classes.
- `spans/classify.py` `split_block()`: split at *every* italic-range
  boundary regardless of length. RI's source italicises the bare word "Gu"
  everywhere, including mid-name ("Uncle *Gu* Yue Dong Tu"), tearing the
  name into two spans. Italic runs under 4 chars now stay merged into their
  containing span.
- Net effect on RI ch9's "Gu Yue Dong Tu" scene, which needed a manual
  merge+reassign every single time before this session: now ingests as one
  clean span, no correction needed. Verified against the real EPUB, not
  just unit tests.

**New capability — tier-4 LLM speaker attribution**
(`speakers/contextual.py`, gated by `--llm-attribution-chapters`, default
3): the deterministic ladder (explicit/proximal/turn-taking) has nothing to
work with in a book's opening chapters — no established cast, no
alternation history — so a protagonist's first lines of inner monologue
landed `UNRESOLVED` no matter how obvious. This was the majority of both
RI's and LOTM's manual corrections, concentrated entirely in ch1-2. New
`Task.SPEAKER_ATTRIBUTION` (qwen2.5:7b local / Haiku on the API backend —
a narrow "does this match one of N roster names" read, not a hard identity
call). Hallucination-proof: an answer outside the known roster is
discarded, same as the regex tiers already discard an unrecognised
capitalised token.

**New capability — auto-flag non-character entities**
(`resolve/runner.py::_maybe_flag_non_character`, item 5 in Section 10's list):
NER's own "location"/"organization" label was being computed and then
discarded — every mention that reaches resolve becomes a `Self` regardless,
since there's no non-person `TargetKind` (see Section 10 item 5 for why this is
capped short of a real fix). `Mention.entity_label` now carries the label
through (additive nullable column, lazy `ALTER TABLE` migration in
`Store._migrate` — this project has no other migration mechanism); an
entity founded *unanimously* on a non-character label gets an automatic
`flag` correction (`source: "agent:pipeline"`) instead of silently joining
the cast list. Off by default (`corrections_log=None`).
  - **Caught by actually re-running, not by tests:** the first wiring of
    this into `commands.py` keyed the corrections log off novel id alone,
    but entity ids (`self1`, `self2`, ...) are a fresh in-memory counter
    every resolve run, never resumed from disk — a run against a
    non-canonical `--db` mints ids that don't correspond to the same
    characters in the canonical store. 12 auto-flags landed in the *real*
    `reverend-insanity.jsonl` referencing a throwaway run's entities before
    this was caught and fixed (now keyed off the database's filename stem).
    All unit tests were green while this was live. Take this as the
    argument for why "green tests" and "safe to iterate unattended" are not
    the same claim.

**New webview/corrections capabilities**, from using the webview directly:
- `reassign_speaker` accepts `payload.anon_slot` (1-4): puts a line into a
  numbered "Unknown Speaker N" voice slot (same id scheme as
  `_assign_anonymous_slots`) instead of only being able to clear it to bare
  "unattributed" — including recovering from an accidental clear, which was
  previously a dead end. Exposed in the picker UI as 4 numbered buttons.
- New `create_mention` correction type: text the detector never proposed as
  a mention at all ("old bastard Fang" referring to Fang Yuan) has no
  `Mention.id` for `reassign_mention` to correct. The reviewer supplies a
  span-local character range (same coordinate space the frontend already
  renders marks in); alias type is inferred via `classify_alias_type`
  rather than assumed. **Backend + tests done; no frontend text-selection
  UI yet** — a reviewer can't actually trigger this from the browser. Next
  step if picked back up: mouse-selection handling in `ScriptLine.js`.
- Dropdown option-list text was unreadable (white-on-white) in the webview
  — `<option>` doesn't reliably inherit the page's `Canvas`/`CanvasText`
  theme colors from the browser's native popup rendering. Fixed with an
  explicit `select option` color/background pin.

**New capability — gold-set comparison wired into `eval`**: `cmd_eval` ran
only the self-retrieval smoke test and printed a note that real recall@k
needed gold data. Now auto-loads `data/gold/<novel>.jsonl` if present and
runs B-cubed scoring (`score_b3`) against it, reported in the two tiers
`gold.py` already draws (draft vs. human-confirmed) so a number computed
from unconfirmed drafts is never silently reported as a result. RI's gold
set extended from ch1-5 (343 mentions) to ch1-60 (3,457 mentions, still
0% human-confirmed — a draft and a second opinion, not gold yet) via a new
`data/gold/reverend-insanity-c1-c60-extended.toml`, following the existing
draft file's conventions exactly (proper names extended across the full
range where unambiguous, plus a not_entity net for this session's specific
false-positive pattern). Verified end-to-end: precision=100% recall=95%
f1=97.4% over 1,816 scored entity mentions against a fresh full pipeline
run.

**Not done, worth knowing:**
- The clan-prefix alias-linking gap is still open: "Gu Yue Dong Tu" (full
  name, clan prefix "Gu Yue" + given name) still doesn't auto-link to a
  bare "Dong Tu" alias elsewhere in the book — no clan/surname-prefix
  stripping in `variants.py`. Different bug from the two fixed above; this
  one is a resolver change, not an ingestion/segmentation one.
- Section 10 item 8 (new): recurring unnamed characters (a named character's
  retinue, a minor character across a few chapters) still get a fresh
  anonymous slot every chapter — no cross-chapter persistence exists.
- `create_mention` has no frontend UI yet (above).
- Extending `TargetKind` past `SELF`/`PERSONA` so a flagged item/location
  can actually stop behaving like a character everywhere, not just get a
  review note (Section 10 item 5).

### 4.21 Phases 7 and 8 — personas, voice casting, TTS (2026-08-12)

**Phase 7 (`persona/build.py`)** mints one `Persona` per character entity,
binds it, and writes a trait profile as `Attribute` rows under
`TargetKind.PERSONA`. This closes Section 10 item 4 and unblocks everything below.

*One persona per self*, so `architecture.md Section 4`'s table is still aspirational
below its first row: reincarnation needs a *second* persona, and deciding a
second body exists is a `resolve/` question Phase 7 sits downstream of. Section 4.15's
LOTM case now links the identity but produces one self with one persona, not
one self with two sequential personas.

**Trait inference has two paths and the deterministic one carries the run.**
`Task.CHARACTER_PROFILE` fires once per entity above a mention floor (~80
calls for a 199-chapter novel, not per mention). Below the floor, and with
`--no-llm`, inference is deterministic — and **pronoun counting is what makes
that viable**: honorifics alone left **91% of RI vol 1's cast
gender-unknown**; counting third-person pronouns in narration around each
character's mentions cut it to **49%**. Pronouns outrank honorifics for
gender (measured: "Lord Yao Ji" is female, and translated xianxia uses
"Lord" for both genders), honorifics outrank pronouns for age ("Granny" is
exact). 6-observation floor, 70% majority, because those passages are
narration *neighbourhoods* holding other characters' pronouns too.

**Phase 8 (`voice/`)** — bank, casting, delivery, engine, runner. Detail in
`details.md`; the decisions worth repeating here:

- **Bank is CSTR VCTK 0.92** (110 speakers, CC BY 4.0, ~11 GB), picked for
  its *hand-recorded* age/gender/accent metadata. Two limits reported rather
  than hidden: it skews young (few real `elder` voices), and it has **no
  register metadata**, so register does not partition the bank — it becomes
  a synthesis parameter instead.
- **Engine is Chatterbox (MIT), not XTTS-v2** as Section 4b originally proposed.
  XTTS is non-commercial-only from a shut-down company and has no emotion
  control; Chatterbox has an explicit `exaggeration` dial. User confirmed
  no near-term commercialisation, but MIT costs nothing to prefer.
  `turbo` variant for the 8 GB budget. **`ollama serve` must not be resident
  during synthesis** — same non-negotiable as every GPU stage (measured:
  ollama alone holds 5.0 of 8.0 GB).
- **Casting colours within buckets**, principals first, age relaxed before
  gender. Collisions logged, not claimed absent (`architecture.md Section 8b`).
- **Non-negotiable #10 is enforced at synthesis**, not just extraction: a
  `FLAT` marker overrides scene sentiment *and* the speaker's Big Five
  baseline.

**Found while wiring, and it matters beyond voice:** `Span.speaker_self_id`
**does not hold a `Self` id despite the name.** The attribution ladder writes
a *surface form* there ("Fang Yuan", and possessives like "Fang Yuan's") and
resolution never revisits it. Casting saw zero characters until
`voice/runner.py::speaker_index()` joined the two on `comparison_key`
(0 → 26 character lines on RI ch1-3, unattributed dialogue 13 → 3). Anything
else keying off that column has the same latent bug.

**Status of the voice path, honestly:** the architecture is complete and
tested (20 tests), and the whole chain runs end to end against a stub engine
that writes real WAVs. **No real audio has been synthesised yet** — VCTK is
an ~10-hour download at the observed ~330 KB/s, and `torch`/`chatterbox` are
not installed. `--engine stub` is the default precisely so nobody mistakes a
manifest for a rendered audiobook.

### 4.22 Full re-run of all three novels on the v1 pipeline (2026-08-12)

Databases in `data/reruns/` (git-ignored). RI, phases 0-7, warm NER cache:

| Stage | Time | Result |
|---|---:|---|
| 0 ingest | 2.8s | 199 ch / 16,360 blocks |
| 2 segment | 3.4s | 200 segments |
| 3 mentions | 228.5s | 9,717 mentions |
| 4 speakers | 73.1s | 2,494/5,194 (48.0%) |
| 5 anaphora | 4.9s | 967 groups |
| 6 resolve | 44.6s | 1,066 groups → **120 entities** |
| 7 personas | 191.1s | **75 personas** |
| **total** | **548s** | |

**120 entities of which only 75 are people** — Section 10 item 5's typing is
excluding 45 locations/organisations from the cast at full scale, which is
the clearest evidence it does what it was built for. Read the 120 against
the older documented 82 with care: this is a *fresh* run (new NER, 9,717
mentions vs 9,568), not a re-resolve, so it is not a controlled comparison.

Phase 8 against that DB, 199 chapters, dry run: **20,449 audible lines,
75 characters cast, 1,976 character lines / 2,700 anonymous-slot /
15,773 narrator, and only 253 dialogue lines with no identity (1.2%).**

**Two weaknesses this exposed, both real:**

1. **49 of 75 characters still have `gender=unknown`.** Pronoun inference
   needs narration around a character's mentions, and minor characters
   often have none. They currently fall back to an age-matched voice of any
   gender. Raising this is the single highest-value improvement to audio
   quality available right now.
2. **Bucket pressure is severe on a small bank** (`male:adult` = 14
   characters over 6 voices in the test bank), producing 7 logged
   collisions. Real VCTK has 110 speakers rather than 30, so this should
   ease substantially — but it is worth re-reading `casting.txt` after the
   real bank lands rather than assuming.

Also surfaced: NER returned truncated JSON on chapter 143 (handled, chapter
skipped with a warning) — pre-existing robustness gap in `chapter_ner.py`,
not new.

### 4.30 Real cloned audio, block-scoped casting, and the panels that go with them *(2026-08-15)*

Direct response to watching the Section 4.29 video with the sound on and at real
length: the cast was wrong in several panels, the opening had nothing to
draw, playback was slower than the reel format this is modelled on, and
the audio was silent. All four are now fixed and verified end to end --
**this is the first chapter video with real voice, not stub timing.**

```
RI ch1 final: 1080x1920, 545.1s (video and audio streams match exactly),
14 real GuoFeng3 panels (accent palette), 154 caption cards, real
Chatterbox-cloned dialogue for every character line.
```

**`present_cast`'s non-person filter never worked, and the reason is a
second stale-column bug in the same family as Section 4.15's.** `Mention
.target_kind` is written once when a mention first links and never
updated when the resolver's typing pass later reclassifies the entity --
verified directly: "Qing Mao Mountain" (LOCATION) and "Daoist Gu"
(ORGANIZATION) both still read `target_kind=SELF` on every mention while
`Self.kind` correctly reads their real type. `present_cast` now takes a
`person_ids` set built from `Self.kind`, and that is what fixed the
opening panel's "smiling stranger" defect -- two of the three "characters"
the old code handed to the prompt had no appearance data and never could,
because they were not people.

**`get_panel_cast` was scoping "who's present" to the whole
`NarrativeSegment`, and RI ch1 has exactly one, covering all 92 blocks.**
A segment marks story-time continuity (a dream, a flashback), not a
cinematic scene, so a chapter with no flashbacks is *correctly* one
segment -- reading that as "the cast for this panel" meant every panel in
the chapter shared one cast: Fang Yuan showed up in the clan-elders
conversation because he appears *somewhere* in the chapter, and the
elders' own scene showed nobody specific. Added `block_window` (defaults
to the single block, callers pass a beat's own range), matching the
window `present_beat_entities` already used for appearance --
**verified against the final video**: the "quietly gazed... rain from the
wind" narration panel now correctly shows and captions "Fang Yuan", not
"Unknown Speaker".

**A close-up needs someone to close up on.** `shot_style` takes
`resolved_subjects`/`has_mob` now: zero resolved subjects routes to a
scene or establishing shot instead of a checkpoint inventing a face, and a
detected background mob routes to a scene shot showing a group.

**Hand-authored staging for the two panels no director can derive**
(`render/beat_canon.py`, same argument `persona/canon.py` makes about
appearance, one level up): the opening (a lone figure surrounded by an
armed faction -- the prose is one hostile line with no resolved speaker,
nothing to stage from) and the rebirth line (blood pooled where he
stands, calm expression, the Cicada glowing in his raised palms -- true
of the *reader's* image of the moment, not recoverable from "I have been
reborn" by any extraction). Wiring it surfaced the token-budget priority
bug a third time: a directive concatenated into `beat` lost its second
sentence to `beat`'s 110-char cap, and once given its own slot, still
lost the fit to the character's shorter, less important appearance
clause. `directive` now has its own 240-char budget and sits ahead of
both. **The cicada's exact rendering was chased and then deliberately
un-chased.** An unqualified "cicada" rendered as a dark bladed object in
two generations; the first fix forced "a golden cicada insect... no
weapon, no sword" to steer away from that -- but RI ch1-2 never actually
states the Spring Autumn Cicada's physical form. It is introduced only
functionally, the seventh-ranked of the Ten Great Mystical Gu, something
Fang Yuan *cultivates* rather than an object with a stated shape, and Gu
in this novel are routinely depicted as strange or weapon-adjacent
artifacts rather than literal bugs -- which is closer to what the
checkpoint drew unprompted than to a garden insect. Forcing "insect" was
inventing a detail the text does not support, the same discipline
`appearance_extract.py` already enforces for model extraction, applied
here to a hand-authored directive instead. Reworded to "a small glowing
Gu artifact" and left open rather than re-forced in either direction.

**Real audio, finally.** VCTK's zip (11.7 GB, Section 4.29 already found it
complete) extracted properly this time -- into `data/`, not `/tmp`, which
is a small tmpfs and filled on the first attempt. `load_vctk` sees all
110 speakers. Chatterbox runs via `uv run --with chatterbox-tts --with
"setuptools<81"` -- an **ephemeral overlay**, not a second `.venv`: it
resolves per-invocation without touching the project's own environment,
which means the "chatterbox and diffusers can't share a venv" blocker in
Section 4.21/Section 4.25 was never actually true, only under-specified. `setuptools<81`
is required because Chatterbox's watermarker (`perth`) imports
`pkg_resources`, which modern `setuptools` stopped bundling -- the failure
with no pin is `TypeError: 'NoneType' object is not callable`, nothing in
the message about setuptools at all.

**Real audio surfaced a real bug the stub could never have: `torchaudio
.save` writes IEEE-float WAV by default, and the stdlib `wave` module
every duration read/concatenation in `render/` uses cannot open it.**
`wave.Error: unknown format: 3`, discovered composing a real chapter
after all 104 lines had already been synthesised (~12 minutes of model
inference). Fixed with explicit `encoding="PCM_S", bits_per_sample=16` on
the save call; the already-synthesised files were reloaded and resaved
rather than re-run.

**Also generated real reference sheets** (`data/references_v2/`, GuoFeng3,
not yet wired into a re-render): Fang Yuan's two bodies plus one
supporting character. `render_panels` reported `conditioned_panels=0` for
the whole session up to this point -- every panel has been prompt-only,
with nothing to IP-Adapter-condition against, because this stage had
never been run against the current checkpoint. Not yet fed back into a
video; the next render pointed at this directory is where identity
consistency across panels should visibly improve.

**New, for iterating without paying for both GPU stages at once:**
`ECHOTALES_ENABLE_IMAGE_GEN` / `ECHOTALES_ENABLE_TTS` (config.py, default
true) force that stage to its stub engine regardless of the CLI flag, and
`echotales render --block-range LO-HI` restricts panel generation to a
contiguous block span -- panel cost is set by `--max-panels`, not chapter
length, so a full-chapter test run costs the same whether you're tuning
one portion of it or all of it.

### 4.29 First real chapter video with the fixed prompts *(2026-08-14)*

Ran the full pipeline end to end after the token-budget and reference-sheet
fixes (Section 4.28's follow-up): stub voice (real, correctly-timed WAVs; no real
TTS yet) → 14 GuoFeng3 panels with the fixed prompts → stub motion clips →
`ffmpeg` compose with captions, on RI chapter 1 against `ri-body.db` (has
the persona split and per-body appearance from earlier this session).

```
14 panels (manga engine, GuoFeng3, 832x1248)     531s
5 motion clips (stub)                              1s
1 chapter video (ffmpeg), 154 caption cards     1352s
ch1.mp4: 1080x1920, 938.0s video == 938.0s audio (exact), 321 MB
```

**The chapter's climax renders correctly.** Pulled the frame at the "I have
been reborn, going back to the time of 500 years ago!" line (t=855s, block
83): a real ink-style panel, waist-length flowing black hair as the
composition, correctly captioned and attributed to Fang Yuan. This is the
same frame described in Section 4.27/Section 4.28's design discussion, now actually in a
composed, timed, captioned video rather than a standalone generation.

**One non-issue worth recording so it isn't re-investigated:** a frame
pulled at t=30s came back solid blue with only the caption visible. Traced
to block 2's shot being a **motion clip**, not a still panel -- and the
`--motion-engine stub` used for this run writes solid-colour placeholder
frames by design (`motion.py`'s stub, same contract as every other stub in
this pipeline). The 14 still panels are all real; only the 2
motion-clip cutaways per chapter are placeholders until `--motion-engine
svd` runs. Confirmed by reconstructing the shot timeline offline
(`build_shot_plan` + `build_timeline`) and checking `panel_images` keys
against the flat frame's block index.

**VCTK's zip is now fully downloaded** (11.7 GB, matches the archive's own
listed size) -- Section 4.21/Section 10 item 9's "2.5 of ~11 GB, partial" is stale. Not
extracted this session (an attempt into `/tmp` filled the 7.7 GB tmpfs
before I redirected it into `data/voice/`, wasting time worth flagging: extract
into the repo's own disk, `/tmp` is tmpfs and small). Extracting it and
wiring `chatterbox-tts` (remember the separate-venv warning, Section 4.25) is what
turns this session's silent stub audio into a real audiobook track.

### 4.28 Per-body appearance, and panels chosen by drama *(2026-08-13)*

Two changes that turned out to be one: the pipeline knew a character could
change bodies (Section 4.27) and neither the extractor nor the camera used it.

**Appearance is extracted per body, not per character.** Pooling a
regressor's evidence into one call asks the model to average a 500-year-old
and a fifteen-year-old into one face; it answers, and the answer describes
neither. Evidence is grouped by body through `persona_at`, one call each.
Measured, RI ch1-40, 13 attributes from 10 calls: **body 1 keeps `deathly
pale` from the chapter 1 death scene, and body 2 — extracted from ch2 onward
— does not inherit it.** That is what `CANON_BY_BODY` previously had to be
hand-written to achieve, now falling out of the evidence.

Chapter granularity, deliberately: a body change can fall mid-chapter (RI's
does), but evidence is gathered per chapter, so the transition chapter goes
wholly to the body holding most of it. Per-block evidence would be more
precise and is not worth the complexity until a novel needs it.

**Panel survival is now dramatic rather than lexical.** The 89-images-per-
chapter problem was already fixed by `render/beats.py` (RI ch1: 92 blocks →
14 panels) — but **every chapter saturates the budget**, so `_merge_to_budget`,
not the boundary logic, is what actually decides what gets drawn, and it kept
whatever the prose spent the most words on. In a web novel that is
exposition: cultivation mechanics, an inventory of a Gu room, a clan's
history. It now merges by `director.py`'s impact score with length as a
tiebreak, so one definition of "dramatic" governs both which moments are
drawn and which of them move.

**Scoring alone was not enough, and the corpus said so.** RI ch1's climax —
"With the use of the Spring Autumn Cicada I have been reborn, going back to
the time of 500 years ago!" — scored **zero**, because nothing in the
vocabulary knew a transformation was drawable, *and* it sat interior to a
thirteen-block beat about clan elders discussing the weather, which a merge
that only chooses *between* beats can never reach. So a body change is now
both a **boundary** and a **score**, taken from `persona/split.py`'s cue
table and imported by both consumers rather than restated.

RI ch1 after: 14 panels, and the rebirth holds two of them (blocks 82 and
83). Before: it was invisible, inside panel 12 of a conversation.

**The through-line worth keeping:** one definition of "a body changed here",
consumed by the graph, the beat segmenter and the director. These have
drifted before — Section 4.24 records the director's combat stems and `motion.py`'s
clip tags becoming disjoint vocabularies, so a block scored maximally on
violence and then played the neutral idle loop.

### 4.27 The persona split — two bodies, one consciousness *(2026-08-13)*

**Section 10 item 11a, done.** `persona/split.py`. Fang Yuan is a 500-year-old
demonic cultivator in chapter 1 and a fifteen-year-old clan boy for the
other 198 chapters, and until now the graph said he was one body throughout
— which made every panel of him wrong on one side of that line or the other.
`architecture.md Section 4` was designed around exactly this case and `build.py`
carried "one persona per self, for now" as a stated limitation. It no longer
does.

**The demonstration, and it is the figure worth putting in the write-up.**
One character, one query, nothing different but the position:

```
ch1 : 1boy, solo, male, tall and lean, gaunt with age and injury,
      midnight black very long straight hair down to the waist, ...
      aged, hollow-cheeked, cold expressionless stare
ch20: 1boy, solo, male, slim adolescent build, not yet grown,
      midnight black very long straight hair down to the waist, ...
      a boy's face wearing an adult's cold, ruthless expression
```

Identity (hair, eyes, build-independent features) survives the change; the
body does not. A flat pipeline cannot produce the second line at all.

**Measured, all three novels, local ollama, free:**

| Novel | Candidates | Model-vetoed | Confirmed |
|---|---:|---:|---|
| RI | 8 | 7 | **1 — Fang Yuan, ch1 b82, rebirth (correct)** |
| LOTM | 10 | 13 | 0 — see below |
| ORV | 6 | 6 | 1 false positive (Bihyung) |

Full RI persona stage: **182.7s for 76 personas across 75 characters**,
against Section 4.22's 191.1s for 75 — the split costs nothing measurable.

**The corpus corrected four things, none of which a fixture would have.**

1. **Both worked examples sit in blocks with no resolved mention.** RI ch1's
   "memories of his previous life on Earth emerged before his eyes" and
   LOTM ch1's "memories began flooding him" refer to the character only as
   "his" — and an unresolved pronoun is not a mention, so the obvious
   same-block presence rule found *neither* of the two cases the module
   exists for. Widened to a ±3-block neighbourhood. This is Section 10 item 11d
   (mention resolution is the ceiling) showing up in a new place.
2. **The clearest statement in each chapter is the character's own line.**
   Fang Yuan *says* "With the use of the Spring Autumn Cicada I have been
   reborn"; Zhou Mingrui *thinks* "C-could I have transmigrated?".
   Narration-only detection missed both. Dialogue and inner monologue now
   count when the speaker is this entity and the line is first-person —
   which needs the `speaker_self_id`↔entity join on `comparison_key`, the
   same Section 4.21 defect voice casting hit.
3. **Echoes swamp events.** Fang Yuan's rebirth is referred back to in
   chapters 2, 19, 71, 105, 135, 145, 187 and 198. A distance window alone
   gave him **eight bodies**. A cue of a kind already accepted is now folded
   at any distance; only a genuinely different kind can open a new epoch.
4. **A rebirth is narrated once and stood next to by everyone in the
   scene.** "Fang Yuan's rebirth changed his current situation" (ch109) was
   minting a second body for *Jia Fu*, who is merely nearby. A passage that
   names another character and not this one is about them — 4,833 rejections
   on RI, free, no model call.

**A cue that is wrong in a plausible-sounding way is worse than one that
never fires.** The first soul-transfer pattern matched LOTM ch126's "his
mind, body, and soul suddenly entered a magical state" — a trance — and the
**model agreed with it**, so the veto did not save it and Klein got a
spurious second body. Fixed by requiring a destination body in the pattern.
Do not assume the adjudicator catches a bad regex; it is a second opinion,
not a filter.

**LOTM's transmigration is still not expressible, and the reason is
upstream.** Resolve produces `Zhou Mingrui` and `Klein` as two separate
selves (Section 4.15, still open — needs the declaration detector), so there is no
single consciousness for two personas to hang off. Every ch1 candidate there
was correctly vetoed as a back-reference; the two the model kept before the
regex fix were the trance above. This is a clean statement of what Section 4.15
costs, not a defect in this module.

**What changed downstream.** `f"{self_id}:body1"` was hardcoded in seven
places; all now call `persona_at(store, self_id, position)`. The one that
matters is **appearance extraction**, which files each attribute against the
body attested at that fact's own chapter — so RI ch1's "green robes" (his
death-scene attire) lands on body 1 and does not describe the teenager.
`reference_gen` generates one sheet per body, seeded per body so two bodies
of one character do not come out as the same face. `persona_at` is total: a
database with no bindings returns `:body1`, so every existing graph keeps
working unsplit.

**How much of the ch1/ch20 contrast is extracted, stated exactly.** Section 4.28
made extraction run per body, and it does separate them from the text: body
1 carries `deathly pale` from the death scene, body 2 does not. But RI's
narration describes Fang Yuan's death scene and very little about him
afterwards, so body 2's *extracted* profile is thin (`green robes`, ch14),
and the age contrast in the prompts above comes from
`canon.py::CANON_BY_BODY` — a reader writing down what the prose never
states, which is exactly the argument `canon.py` was created for. Read the
contrast as evidence that **the graph knows there are two bodies and hands
the right one to the right chapter**, not that extraction inferred a
teenager.

**Known rough edge, pre-existing and now more visible:** re-running the
persona stage against a graph that already has persona attributes appends a
second copy of each trait row rather than replacing it (`add_attribute` is
an INSERT). Harmless — `_facts_as_of` takes the latest attestation — but an
attribute count off that table will double-count.

### 4.26 `world/` — structured facts for every entity, and position-filtered retrieval *(2026-08-13)*

**The gap.** The graph has typed its entities since Section 10 item 5 and has had a
temporal fact table all along, and nothing ever populated either for
anything that was not a character's face. Measured on the real RI database:
**10 locations and 35 organisations -- Qing Mao Mountain, Gu Yue Village,
the South Border, the Gu Yue Clan -- all resolved, named, and carrying zero
facts.** That is why `persona/attire.py` grew hand-written `SCENE_LOCALES`
and `FACTION_ATTIRE` tables inventing generic courtyards and guessing clan
colours; those tables were a workaround for this package not existing.

**`world/schema.py`** fixes a *closed* vocabulary per kind -- a place has
`terrain`/`architecture`/`atmosphere`, a faction has `colors_attire`/
`territory`, an item has `powers`/`owner`, a person has `cultivation_rank`/
`faction`/`status`/`abilities`. Open-ended "tell me about this entity"
produces prose that cannot be queried, compared, or rendered into a prompt.

**`world/extract.py`** fills it in, one model call per entity, **importing**
rather than copying `appearance_extract`'s retrieval/grounding/dating
discipline. Evidence differs by kind on exactly one axis: a person's facts
come from scenes they are `PRESENT` in (a character discussed in absentia is
being gossiped about), a place is described whether or not anyone stands in
it.

**`world/context.py` is the half that makes it usable.**
`story_context(novel, store, chapter, blocks)` returns everything relevant
at one position as a compact brief, **filtered by what is known at that
position rather than by what exists**. A brief that ignored position would
leak the ending into the opening, which for a novel built on reveals is the
worst thing this layer could do. `render/direction.py` now receives it, so
panel prompts can know a character's rank and faction and who holds the
village he is standing in.

**Measured, RI full volume, local ollama, free:**

```
124 world facts from 73 model calls, 0 failures
  by kind: LOCATION=13, ORGANIZATION=37, SELF=74
  skipped: 46 not prominent, 1 no evidence
```

**Bitemporal retrieval verified end to end** -- the thing the whole
architecture exists for:

```
ch1 : Fang Yuan facts = {}                                    <- correct: not yet stated
ch20: {'cultivation_rank': 'Rank one initial stage',          <- attested ch15
       'faction': 'Gu Yue clan'}                              <- attested ch4
```

No leakage backwards. This is the cleanest demonstration in the codebase
that `state_of(..., position)` does something a flat pipeline cannot, and is
the figure worth putting in the write-up.

### 4.25 Image backends — what is actually available, measured *(2026-08-13)*

Every hosted option was tested with real keys rather than judged from
documentation. **There is no free hosted image API usable for a batch.**

| Backend | Result |
| --- | --- |
| OpenRouter (`gemini-2.5-flash-image`) | Works. No free image model exists there -- every image-output model is priced. A free-tier key returns `HTTP 402` after its grace (measured: 3 calls, `total_credits: 0`, `total_usage: 0.155`). **~$0.05/image**, and a content-filtered call still bills. |
| Gemini direct (AI Studio) | `HTTP 429`, `limit: 0` on *every* image model including Imagen. Not a rate limit -- the free tier has no image quota at all. Needs billing. |
| NVIDIA NIM (`flux.1-schnell`) | Authenticates, then times out past 180 s. Queued; unusable for a chapter batch. |
| Pollinations | `HTTP 403`. No longer keyless. |
| **Local (`--image-engine manga`)** | **Free, unlimited, unfiltered.** Lower quality, and the only option with no content filter -- which matters for this corpus. |

**Cost, if paying:** 12 panels/chapter ≈ **$0.60/chapter**, ~$120 for a
199-chapter volume, plus ~20% for content-filter retries on this novel.

**The recommendation for the research phase is to pay the ~$2** for one to
three demonstration chapters. The contribution is the graph -- `plans.md`
Section 0 says so outright -- and image quality is a confound to remove, not a
variable to optimise. Free/local is the right answer for *shipping*, where
each user brings their own GPU and per-user cost is zero, which is also a
genuinely stronger product architecture than any API tier.

**Content filtering is a permanent property of the hosted path here.**
Reverend Insanity's first chapter is a massacre; both OpenRouter and Gemini
refuse gore outright (`content_filter`, `PROHIBITED_CONTENT`). Refusals are
retried once with the violence abstracted (`openrouter.soften`), so the
moment is implied rather than explicit. The local engine has no such
filter.

### 4.24 Phase 7b + Phase 9 completion — appearance, reference sheets, manga panels *(2026-08-13)*

Section 4.23 built the video *assembly* (timing, compositing, shot decisions) but
left four gaps that meant it could never produce a watchable panel. All four
are now closed, and the work was driven against the real RI database rather
than fixtures — which is where most of what follows came from.

**1. Appearance was never extracted** (`resolve/appearance_extract.py`,
`Task.APPEARANCE_EXTRACTION`). `persona/build.py` writes demographics and
Big Five — everything *voice* casting needs — and nothing else. Hair, eyes,
build, attire and insignia were read nowhere, so every character was a blank
to the visual pipeline. One model call per prominent entity, over narration
where that entity is `ReferenceMode.PRESENT`, written as `INFERRED` /
`AssertedBy.INFERENCE` `Attribute` rows under `TargetKind.PERSONA` and
accumulated across chapters rather than overwritten.

**2. No reference images existed** (`persona/reference_gen.py`). IP-Adapter
conditioning needs something to condition against; nothing had ever been
generated. Built from the appearance rows (not re-read from prose), tiered
by prominence, and cached against a digest of the appearance data so a
re-run only regenerates a sheet whose source actually changed.

**3. Reference conditioning was not implemented** and **4. manga style was
specified nowhere** (`render/panels.py::MangaDiffusersEngine`,
`persona/prompt.py`). `--image-engine manga` generates from an anime/manga
finetune — the *checkpoint* carries the style, and one that returns
photorealism is the wrong checkpoint, not a prompting problem — and feeds
each present character's sheet as IP-Adapter conditioning at 0.65. Missing
sheet or unavailable adapter degrades to prompt-only **and logs it**, since
silently losing conditioning looks identical to having it.

**5. Motion placement is now competitive, not local** (`render/director.py`).
Scores every block in a chapter and takes the best two, non-adjacent, or
zero if nothing clears the threshold.

**Five things the real data corrected, none of which fixtures would have
caught:**

- **`Self.prominence` is stale in every existing database.** All 120
  entities in `data/reruns/reverend-insanity.db` read `INCIDENTAL`,
  including Fang Yuan at 5,191 mentions. `set_prominence` works — it simply
  predates these databases. Appearance extraction therefore *derives*
  prominence from mention count; trusting the column would have made the
  stage silently process nothing, the worst failure mode for a stage whose
  output is invisible until a panel renders wrong. **The stale column is
  still there and still wrong** — anything else reading `entity.prominence`
  off an existing DB has the same bug.
- **The combat vocabulary scored literally zero on real chapters.** The
  first `_COMBAT_VERBS` list was past-tense whole words ("struck",
  "slammed", "erupted", "shattered") and matched **nothing** in RI ch1, ch8
  or ch20 — ch1 is a massacre, and the translation says "killed" and
  "attacked". A cue vocabulary that never fires silently degrades the impact
  score to a cast-change detector. Now stem-matched and corpus-derived; ch1
  selects blocks 2 and 27.
- **The panel prompt was being fed spoken dialogue.** Block 0's cue was
  `"Fang Yuan, quietly hand over the Spring Autumn Cicada..."` — words the
  audio track already carries, describing nothing visible. The beat is now
  drawn from narration spans, falling back to raw block text only for a
  pure-dialogue block.
- **`resolve_attire`'s last tier is a style, not a garment**, so characters
  with no attire data produced "Fang Yuan wearing xianxia web-novel
  illustration", repeated once per character.
- **`present_cast` returns surface text, not entity ids.** `active_selves`
  holds `"he"`/`"his uncle"` — fine for counting a scene's cast, useless for
  looking up a persona, so `panels.py` resolves ids from mentions directly.

**Measured output, RI chapters 1–5** (`ECHOTALES_MODEL_BACKEND=ollama`,
qwen2.5:7b): 15 appearance attributes from 5 model calls across 75 person
entities — 46 skipped as not prominent, 24 with no descriptive evidence, 0
failures. Fang Yuan resolved to `deep green robes that had been torn to
shreds` / `disheveled` / `deathly pale` / `injured`; Shen Cui to `black`
hair, `green robe with long sleeves and trousers, embroidered shoes`.

**Two honest quality caveats on that output**, both visible in the data:
Fang Yuan's ch1–5 profile is his *death scene* (`current_condition:
injured`, `deathly pale`) rather than his typical look — the accumulate-
don't-overwrite design is what lets a wider chapter range correct this, but
nothing yet prefers a standing description over a transient one. And Shen
Cui's `hair_style` came back `pearl hairpin`, which is an accessory, not a
style.

**First real end-to-end chapter video, RI ch1.** Produced with a synthetic
6-speaker voice bank and the stub TTS (VCTK is a partial download — 2.5 GB
of ~11 GB — so Section 4.21's blocker still stands), stub panel images, and a
**real `ffmpeg` encode**:

```
89 panels, 5 motion clips, 1 chapter video (ffmpeg)
ffprobe duration: 938.000s   summed audio: 938.0s    <- exact match
shots: 87 pan / 2 clip
pan directions: zoom_out 32, zoom_in 27, pan_left 15, pan_right 13
clips: block 2 (score 6), block 7 (score 5)
```

**The 89 is superseded — do not quote it as the current panel count.** That
run predates `render/beats.py`; one panel per *block* was the defect that
module exists to fix, and the same chapter now produces **14** (Section 4.28). The
timing and shot numbers below still hold.

The timing claim is the one that matters and it holds exactly: picture
length is the audio length, not an estimate. Clip selection with real
durations picked block 2 (`kill` +3, 11.6s +2, cast change +1) and block 7
(`wound` +3, 12.4s +2). Block 3 tied at 6 and was correctly rejected as
adjacent to block 2, with the tie broken toward the earlier block.

That run also exposed a defect nothing synthetic would have: **both clips
initially cued `idle`**. The director's combat stems (`kill`, `wound`) and
`motion.py`'s tag keywords (`sword`, `clashed`) had drifted into disjoint
vocabularies, so a block could score maximally on violence and then play
the neutral loop. The two tables are now kept deliberately in step, and
both blocks cue `impact`.

**First real image generation** (`torch 2.5.1+cu121`, `diffusers 0.39.0`,
MeinaMix_V11 on an RTX 4060 8 GB, ~5.5 s for 28 steps at 512×640). Three
defects, none of which any test could have caught, all found by *looking at
the output*:

1. **Full colour**, despite `monochrome` in the prompt and `color, colored`
   in the negative prompt. MeinaMix is an anime *colour* checkpoint and
   that is what it knows. Fixed by converting to greyscale in code after
   generation, where it cannot fail, rather than rewording a prompt that
   demonstrably does not win. The checkpoint still earns its place: it
   supplies anatomy, linework and xianxia costume vocabulary a
   photorealistic base cannot.
2. **A collage of twelve thumbnail poses**, because `"character reference
   sheet"` reads as a literal instruction to draw a sheet. That is the
   worst possible IP-Adapter input — the adapter needs one clear face and,
   given twelve small ones, locks onto none.
3. **Fang Yuan generated as a woman.** His stored `gender` reads `unknown`
   (the same staleness as `Self.prominence`), `build_reference_prompt`
   degraded that to the word "person", and an anime checkpoint handed
   "person" draws a woman. Fixed by falling back to
   `traits.py::gender_from_pronouns` — which already existed for voice
   casting, was written to solve exactly this (honorifics alone left 91% of
   the cast unknown), and which nothing in the visual path was calling —
   and by leading the prompt with the danbooru tag `1boy`/`1girl`, which
   these checkpoints weight far more heavily than the English word.

4. **A girl holding cherry blossoms, for a scene where two men threaten to
   kill each other** (RI ch1 block 2). Two compounding causes: the block
   has no narration spans, so the beat fell back to the quoted line (words
   the audio already carries, describing nothing visible), and the prompt
   named two characters without saying anything about them. Handed a
   vacuum, the checkpoint fell back to its training prior, which is
   overwhelmingly female. Panel prompts now lead with danbooru headcount
   tags (`1boy`/`2boys`/`1girl`), the same lever that fixed the reference
   sheets.
5. **Every unconditioned panel crashed once IP-Adapter had loaded.**
   Loading it rewrites the UNet's attention processors, which then read
   `added_cond_kwargs["image_embeds"]` unconditionally -- so a later call
   without `ip_adapter_image` passes `None` into the UNet and raises. Not
   an edge case: most blocks name nobody with a reference sheet, so panels
   alternate constantly, and the run died on the first unconditioned panel
   after the first conditioned one. Unconditioned panels now pass a blank
   image at scale 0.0 (arithmetically identical to no conditioning) rather
   than paying an unload/reload per block.

**Conditioning verified working**: a panel generated with Fang Yuan's sheet
carries his face and hair into a completely different pose and setting
(full body, courtyard, pagoda), which is the balance 0.65 is chosen for --
identity held, composition free.

6. **Panels had no world in them.** Characters floated on abstract ink
   swirls, because the prompt's "environment" slot was filled by
   `resolve_attire`, whose last tier returns the novel's house *style*
   (`"xianxia web-novel illustration, Gu-worm era Chinese fantasy"`) -- an
   instruction about how to draw, saying nothing about where anyone is
   standing. A diffusion model draws a courtyard from "stone courtyard" and
   draws nothing recognisable from "Chinese fantasy". `WORLD_SETTING`
   (scenery nouns per novel) and `SCENE_LOCALES` (concrete places, cue-
   matched against the block's own text, rotating by block index when the
   prose states none) fixed it: the same block that was a floating bust
   became a figure on a misty cliff path with pines, distant peaks and
   architecture.

> ### ⚠ `chatterbox-tts` is dependency-incompatible with the image stack
>
> Installing it **silently downgraded `diffusers` 0.39.0 → 0.29.0**, plus
> `transformers` 5.15.0 → 5.2.0 and `torch` 2.5.1 → 2.6.0, which broke image
> generation outright (`cannot import name 'FLAX_WEIGHTS_NAME'`). Restoring
> `diffusers==0.39.0` and `transformers==5.15.0` repairs the image path and
> breaks chatterbox instead.
>
> ### ⚠ Appearance is bitemporal, and only half-built
>
> Raised by the user, and correct: **a character's appearance is not a
> timeless property, and this pipeline still largely treats it as one.**
> Fang Yuan is a 500-year-old man in chapter 1 and a fifteen-year-old from
> chapter 2 onward; the novel reveals facts about each body at different
> discourse positions. A single flat profile is wrong for most of the book.
>
> **Half fixed.** Attributes now carry the chapter that actually attests
> them (`attesting_chapter`), so `interval` and `learned_at_pos` are real
> rather than every fact claiming to hold from the entity's first sighting.
> That much makes appearance answerable by `state_of(..., position)`.
>
> **Not fixed, and this is the flagship case Section 4 was designed for:** Fang
> Yuan needs **two personas on one self** -- the aged pre-regression body
> and the regressed one -- exactly the split `architecture.md Section 4` describes
> and `persona/build.py` flags as its known "one persona per self, for now"
> limitation. Until that exists, `reference_gen` builds one sheet per
> character from a merged profile, and panels cannot ask "what did he look
> like *here*". The visual pipeline is therefore blocked on an identity
> question, which is the right place for it to be blocked -- `resolve/`
> decides who is whom -- but it is blocked.
>
> Second, smaller gap from the same investigation: some descriptive blocks
> carry **no resolved mention at all** (RI ch12's "his body figure was tall
> and thin, his skin pale" is a bare "The young man...", never linked to
> Fang Yuan), so they are invisible to extraction no matter how it samples.
> That is a mention-resolution gap, not an appearance one.
>
> **Voice and image cannot currently share one venv.** Whoever wires real
> audio needs a separate environment for TTS, a different TTS, or a
> compatible chatterbox pin -- and should expect `uv pip install` to
> silently rearrange the image stack otherwise. This is the single most
> likely thing to waste an afternoon here.

**The recurring lesson across Section 4.24: the persona table's stored values
cannot be trusted in existing databases.** `prominence` and `gender` both
read as defaults on `data/reruns/*.db`, and both had to be re-derived at
point of use. Anything else reading those columns has the same bug.

**Measured, 6 reference sheets, RI:** all six generated as single-figure
monochrome inked portraits. Fang Yuan and Fang Zheng come out looking
*similar*, and that is the data rather than the generator — both extracted
to `green robes` + default black hair + male. See the `green robes`
contamination noted above; it is visible in the output, not just the
attributes.

**Status: qwen2.5:7b — not the 14b this stage was specified with.** A 14B q4
is ~9 GB of weights against Section 3's 8 GB card and `tasks.py`'s own
`VRAM_BUDGET_FRACTION` (~5.7 GB), so it cannot be resident; naming it would
fail the `models_required` preflight outright rather than degrade.

### 4.23 Phase 9 — panel images, motion clips, and video assembly (`render/`) *(2026-08-12)*

**What this is, and what it deliberately is not.** The brief was a
manhwa-panel-to-video technique observed in the wild (a reel adapting *The
Legend of the Northern Blade*): mostly still panels animated with Ken-Burns
pan/zoom, occasionally cut to a small number of short AI-generated motion
loops that get reused constantly rather than regenerated per cut, all timed
to a voice track. This is **not** a from-scratch video generator — every
design choice below exists to keep it cheap (ideally free in dev) and to
reuse what Phases 7-8 already produce, not to generate more than the bare
minimum of new pixels.

**Five new modules under `render/`, mirroring the `llm`/`voice` shape**
(`Protocol` backend, a dependency-free stub, a lazily-imported real engine):

1. **`persona/prompt.py`** — `build_image_prompt(panel_cast)` turns
   `persona/runner.py`'s already-resolved `PanelCast` into one SDXL prompt
   string (environment → foreground characters+attire → background mobs →
   a fixed quality suffix), plus a shared `NEGATIVE_PROMPT`. No new data;
   this only says what `get_panel_cast` already knew, in prompt order.
2. **`render/panels.py`** — one cached image per `(chapter, block_index)`.
   `StubImageEngine` writes a real, dependency-free PNG (raw `zlib`/`struct`,
   no Pillow — same reasoning as `voice/engine.py::StubEngine` writing real
   silent WAVs); `SDXLEngine` lazy-loads `torch`/`diffusers` on first real
   use, matching `ChatterboxEngine`'s load discipline. Re-runs skip any
   block whose PNG already exists — regenerating thousands of panels per
   iteration would be too slow even before cost is a factor.
3. **`render/motion.py`** — a **small, fixed, reused** clip library, not
   one clip per scene. `GENERIC_TAGS` (`clash`/`wind`/`flame`/`impact`) is
   generated **at most once each**, cached, and matched against a block's
   text via `match_tag` (keyword vocabulary first, `spans/delivery.py`'s
   `DeliveryPolarity` as a lower-precision fallback — reusing the voice
   stage's own delivery-cue extraction rather than a second emotion
   vocabulary). Clips are stored as PNG frame sequences, not an encoded
   video — nothing in this project's dependencies can write a video
   container, and `ffmpeg`'s `image2` demuxer reads a frame directory
   directly, so that is the lightest thing that could work.
4. **`render/director.py`** — per block, decide the shot: pan/zoom on the
   still panel by default, or cut to a motion clip when (a) `match_tag`
   actually hits something in the block's text and (b) at least
   `clip_gap_blocks` (default 6) blocks have passed since the last cutaway.
   Both guards exist so a clip reads as an accent, not a glitch or the
   default. **Pan direction is a starting rule, not a settled one:**
   dialogue → zoom in, pure description → lateral pan, everything else →
   zoom out. Flagged explicitly for re-tuning once it's been eyeballed
   against real chapters — nobody has done that yet.
5. **`render/timeline.py`** — turns the director's per-block decision into
   real start/end timestamps by reading each line's *already-rendered* WAV
   duration (`voice/runner.py`'s `manifest.jsonl`) via the stdlib `wave`
   module. Image duration is locked to speech, never estimated. A block
   with audio but no shot (a partial run, stages out of sync) carries the
   previous shot forward rather than leaving a silent gap in the picture,
   and is flagged `carried_over=True` so a review pass can see exactly
   where — same "make the gap visible, don't invent data" instinct as
   `AttributionMethod.ANONYMOUS_SLOT`.
6. **`render/compose.py`** — the compositor. `StubComposeEngine` needs no
   `ffmpeg`: it does the one dependency-free part of this stage for real
   (concatenating the actual WAVs at the sample level via `wave`, raising
   on a format mismatch rather than resampling silently) and writes a JSON
   shot manifest alongside. `FfmpegComposeEngine` renders each shot to its
   own segment (`zoompan` for a still, a trimmed/looped frame sequence for
   a clip), concatenates via the concat demuxer, and muxes against the real
   concatenated audio. **This one was verified against a real `ffmpeg`
   encode**, not just the stub — a full pan+clip+audio chapter produced a
   genuinely playable mp4 of the expected duration.
7. **`render/runner.py`** — `render_videos` ties all of the above together,
   reading the panel and voice manifests already on disk rather than
   regenerating either (both are expensive; this stage's job is arranging
   already-paid-for assets, never re-paying for them). A chapter with
   panels but no voice manifest yet is skipped and counted, not an error —
   the two upstream stages are allowed to run at different paces.

**Wired into the CLI as `echotales render`**, three independently-skippable
sub-stages (`--skip-panels`/`--skip-motion`/`--skip-compose`) mirroring
`render_panels`'s own on-disk caching. `--image-engine`/`--motion-engine`/
`--compose-engine` each default to `stub`.

**Status, honestly, and why:** architecture is complete and tested (31 new
tests across `test_render_panels/motion/director/timeline/compose/runner.py`,
including one real end-to-end `ffmpeg` encode), but **nothing has run
against a real novel or real audio yet.** Concretely blocked on the same
gap Section 4.21 already flagged for Phase 8, not a new one: `data/voice/` (VCTK)
is not downloaded, so no real `manifest.jsonl` with real per-line durations
exists to build a real timeline against. `SDXLEngine`/`SVDEngine` are also
unexercised — `torch`/`diffusers` are not installed (`pip install
echotales-pipeline[render]`), and neither has been run against a GPU.
**Do not read "31 tests pass" as "produces a good-looking chapter video"** —
the tests prove the timing math, prompt assembly, tag matching and ffmpeg
plumbing are correct, not that SDXL's panels or SVD's clips look right, or
that the pan-direction rule reads well. Nobody has watched one yet.

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

- Cost. Per-span is 34.5 h by the Section 3 budget; per-chapter is ~35 min for 199
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

## 4b. Voice / TTS design — **superseded, kept for its reasoning** (2026-08-07)

**This section is the design *proposal*; Section 4.21 is what was built.** Where
they differ, Section 4.21 wins — most notably the engine (Chatterbox, MIT, not
XTTS-v2) and the bank (VCTK, for its hand-recorded age/gender/accent
metadata). Kept because the trade-offs it works through are still the
reasoning behind the built version.

Not started, but scoped now because it consumes exactly what the graph
produces and the design decisions constrain what `Persona` needs to carry.
`plans.md` already committed to the shape: `persona` owns "voice timbre,
physical attributes -- this is what image generation and TTS bind to", and
`architecture.md Section 8b` already ruled out global collision-free voice
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
   not per mention. Same discipline as layer 1 (Section 4.10): the input is the
   entity's accumulated evidence (attributed dialogue, narrator descriptions,
   relationships already in the graph), the output is Big Five scores plus
   coarse demographics (age band, gender, register). This is a new
   `Task.CHARACTER_PROFILE` in `llm/tasks.py`, same router.
2. **Archetype bucket = demographics + register, not raw Big Five.** Five
   continuous traits don't cluster into voice categories; age/gender/register
   do. Reuses the bucket concept `architecture.md Section 8b` already committed to
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
5. **Consumes the script view (Section 4.13) directly.** `ScriptLine.speaker_label` +
   `attribution_method` is already the exact input TTS needs: text, who says
   it, and how confident the attribution is. An `UNRESOLVED` line is a
   decision point (narrator voice? skip? flag for manual pass?) the script
   view now makes visible before synthesis, not after.

**Blocked on:** Section 4.10's speaker-attribution regression (54.9% -> 48.8% at full
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
in architecture.md Section 4 has no code on the persona side at all". Phase 6 only
produces `Self` rows today.



---

## Migrated from HANDOFF.md (sessions 2026-08-15 through 2026-08-31)

The entries below lived in HANDOFF.md until a 2026-08-31 cleanup pass
moved every completed-fix / historical entry here, per HANDOFF's own
stated purpose (current tasks only). Original numbering and dates kept
as-written, including one pre-existing collision: two different entries
are both titled "4.45" (one at the position below, dated 2026-08-20,
the other later in this same migrated block) -- this was already wrong
in HANDOFF before the move and is flagged here rather than silently
renumbered.

### 4.31 User watch-through of the 4.30 video — nine real defects, none fixed yet *(2026-08-15)*

The author watched `data/video_v3/reverend-insanity/ch1.mp4` start to finish
with sound on and reported nine specific problems. **Nothing in this
section is fixed** — this is intake for the next session, written down
before any code changed so the next session starts from the actual report
rather than a paraphrase. Ranked in the order the author raised them, not
by guessed severity; the diagnosis under each is this session's best
inference from the code, not confirmed by re-running anything.

1. **Speaker attribution has real classification gaps.** The clan leader
   speaks before his name is introduced in the text, and the pipeline
   never resolved his line back to him -- he was cast as an anonymous
   slot instead. Likely cause: the four-tier attribution ladder
   (`speakers/`) and `_assign_anonymous_slots` both key on a name already
   being *known*, and nothing revisits an anonymous slot once the
   speaker's identity becomes clear later in the same scene. This is a
   real gap distinct from the tracked "attribution regressed 64.9% →
   48.8%" number in 4.9/4.14 -- that number measures coverage, not
   whether an anonymous slot silently swallows an identifiable speaker.

2. **Voice casting ignores authority/register.** The clan leader -- an
   authority figure -- got a voice the author heard as "a weak asian
   man," wrong for the role regardless of correctness on age/gender.
   `voice/bank.py::nearest_bucket` buckets purely by age band and gender;
   nothing in casting reads `register` (formal/authoritative, already
   computed by `persona/traits.py`) or picks toward a commanding-sounding
   reference clip within a bucket. Casting needs a second axis, not just
   a better bucket match.

3. **Speed reverted: 1.25x is too fast, back to 1.0.** `compose.py`'s
   `speed` default and the CLI's `--speed` default are both `1.25` right
   now (4.30). Change both to `1.0` first -- this is the one purely
   mechanical fix in this list, no design question attached to it.

4. **The "~30 panels would be enough" framing was wrong; retracted by the
   author who said it.** More panels are needed, but explicitly *after*
   relevance is fixed, not before -- see item 9.

5. **"The pipeline isn't able to have even the slightest level of
   understanding of the scenes."** The author's summary judgment, and
   items 6-9 below are the specific cases underneath it.

6. **Establishing shots work; character/action panels mostly don't.**
   The mountain-stronghold and Qing Mao Mountain panels landed; "rest was
   absolute trash" (author's words). Consistent with `beat_canon.py`'s
   two hand-staged panels being the only ones with real content behind
   them -- every other panel is still assembled from `beat_prose` alone,
   with no equivalent staging.

7. **Panels don't track who is acting at each beat, or the actual staged
   scene.** When a different character speaks, shouting at Fang Yuan, the
   panel should show *that* character's face and expression, not
   whichever image the previous beat carried forward. The text also
   states several people surround Fang Yuan at a distance, waiting until
   sunrise for his last attack, and describes specifically how he dies --
   none of that staging reached any panel. This is `beat_canon.py`'s
   whole justification generalised past two entries: the beat's own
   prose is being under-used, and speaker-turn changes are not treated as
   panel-worthy events the way `render/beats.py`'s cast-change boundary
   should already be catching. Worth checking whether that boundary is
   actually firing here, or whether it fires but the *prompt* still
   doesn't reflect who the beat's subject is.

8. **No character-design consistency across panels.** Fang Yuan's look
   changes panel to panel; the author gave a specific reference
   description earlier in this project (waist-length black hair, cold
   narrow eyes, per `canon.py`) that isn't being held. Root cause is
   already known and *already partly fixed, just not wired in*: 4.30
   generated real reference sheets (`data/references_v2/`) but no render
   has been pointed at them yet -- `render_panels` reports
   `conditioned_panels=0` for every run to date, meaning every panel is
   still prompt-text-only with nothing to IP-Adapter-condition against.
   Wiring `data/references_v2/` (or a fresh generation) into the next
   `render_panels` call is the direct next step here, not a new
   mechanism.

9. **More panels only after they're relevant, not before.** Direct
   sequencing instruction from the author: fix relevance (items 6-8)
   first, then raise `--max-panels`. Producing more of an already-wrong
   panel wastes the same GPU time 10 item 11 (block-range testing) was
   built to protect.

10. **Gu/Gu worms mis-classified, and the definition should come from the
    text, not a web search.** The author explicitly flagged this against
    the web-search-phase idea raised in the same conversation: the novel
    itself defines Gu ("actual insect-like spirits with special power")
    in narration later in the book, so extraction should already be able
    to find and use it without any external source -- **prefer in-text
    definitions over external lookup wherever the text actually states
    the thing**, which bears directly on how any future web-search phase
    should be scoped (supplementary only, not a replacement for
    extraction the pipeline should be doing anyway). Separately, the
    author also flagged that mentions of "Gu" are for some reason
    sometimes classified as narrator speech, which is a `spans/` or
    `speakers/` classification bug worth reproducing directly rather than
    guessed at.

11. **Group scenes render as one isolated figure with no one else and no
    background.** The ancestral hall scene (clan leader and elders
    present) rendered as a single unrelated figure, no other people, no
    hall. Given 4.30's `has_mob`/`resolved_subjects` work was aimed
    exactly at this class of scene, the likely next question is whether
    `detect_mobs` (`spans/scene.py`) is actually firing on this specific
    block's language ("elders", "ancestral hall" style phrasing) or
    silently missing it, and whether `scene_locale`'s cue table
    (`persona/attire.py::SCENE_LOCALES`/`_LOCALE_CUES`) has an "ancestral
    hall" or "hall" cue that this block's actual wording matches --
    worth checking against the real block text before assuming either
    mechanism is broken versus simply not cued for this phrasing.

**Suggested order for the next session, synthesising the above:** item 3
(one-line fix) first; then item 8 (wire the existing reference sheets --
already-built machinery, not new work) since it is likely the single
highest-value fix per unit of effort; then items 6/7/11 together, since
they are all instances of "the panel doesn't reflect the beat's actual
content" and a proper fix probably touches `beat_canon.py`'s pattern,
`render/beats.py`'s boundary logic, and `scene_locale`'s cue table at
once; then items 1/2 (attribution/casting); item 10's classification bug
last, reproduced against the real block first rather than guessed at. The
web-search phase the author asked about is explicitly *not* next --
item 10 is a standing instruction to prefer in-text extraction first, and
none of the above defects are caused by missing world knowledge the text
doesn't already contain.

**Items 3, 8, 6/7/11 done this session (2026-08-15), items 1/2/10 still
open:**

- **Item 3**: `cli.py`'s `--speed` default was `1.25`; `compose.py`'s was
  already `1.0`. Fixed the CLI default to `1.0`.
- **Item 8**: root cause confirmed empirically -- every `data/*.db` had
  zero `reference_image_path` attribute rows, for any novel, so
  `reference_path_for` always returned `None` regardless of which store
  `render_panels` read. The conditioning plumbing in `render_panels`
  itself needed no changes. Wrote `scripts/backfill_reference_markers.py`,
  a one-off that reverse-derives `persona_id` from each
  `data/references_v2/<novel>/*.png` filename and writes the missing
  marker directly into `data/reruns/reverend-insanity.db` -- the only DB
  with RI's persona rows populated (all other `data/*.db` files have zero
  persona rows for RI; confirmed with the author before writing). 2 of 3
  reference sheets matched an existing persona (`self1:body1`,
  `self13:body1`); `self1:body2` has no matching persona row in that DB
  yet and was skipped, not invented. Verified `reference_path_for` now
  resolves both. **Not yet done: an actual re-render to confirm
  `conditioned_panels > 0` end to end** -- that needs a real (costly) GPU
  render pass, left for the next session's watch-through.
- **Item 6/7/11**: three separate, verified fixes, not one mechanism:
  - `render/beats.py`'s cast-change boundary (`segment_beats`) required
    *both* `cast` and `prev_cast` non-empty to fire, and separately
    carried a stale `prev_cast` forward across any empty-cast block
    (`cast or prev_cast`) -- so one narration-only or unattributed block
    could silently swallow the *next* block's real cast change too. Fixed
    both: the condition now fires on `cast and cast != prev_cast`, and
    `prev_cast` is always the immediately preceding block's actual cast,
    never carried forward.
  - `spans/scene.py::detect_mobs`'s regex required the quantifier
    ("the"/"a"/...) to sit *immediately* before the role noun, which
    missed the real RI ch1 ancestral-hall text almost entirely -- "the
    clan's elders", "the experienced elders", "the clan elders" (the
    exact recurring phrase in that scene) never matched. Now allows one
    optional intervening word between the quantifier and the role noun.
    Verified against the real chapter-1 blocks: block 12 and 57/62 (which
    didn't fire before) now correctly detect "elders" as a mob; a
    possessive form ("clan's elders", apostrophe breaks the token) still
    doesn't match -- a known, smaller residual gap.
  - `persona/attire.py`'s `_LOCALE_CUES` had no "temple" cue. The
    ancestral-hall scene's actual wording is "ancestral temple" / "sacred
    temple" in every block *except* one interior line that says "hall" --
    so most of the scene's blocks were falling through to the rotating
    fallback locale instead of matching. Added `"temple": "hall"`.
    Verified block 57 (which mentions "temple") now resolves to the
    "hall" locale correctly. Did **not** touch the "clan" -> "village" cue
    or add speculative vocabulary beyond what the real text needed.
  - `uv run pytest packages/` still 682 passing after all of the above.
  - **Not yet done: a real re-render of RI ch1 to eyeball the combined
    effect** -- per the author's own item-9 instruction, more panels (or
    a fresh render pass) should wait until relevance is fixed, and these
    changes are the relevance fix, but nobody has watched the output yet.
- **Items 1, 2, 10: still open, untouched this session.** Root causes are
  fully diagnosed (see the numbered list above) but no code changed for
  any of them -- `_assign_anonymous_slots`'s forward-only pass (item 1),
  `voice/bank.py::nearest_bucket`'s missing register axis (item 2), and
  `spans/classify.py`'s short-emphasis-span exposition-regex interaction
  (item 10) are all real, next-session work.


---

### 4.32 Translator's-note continuation blocks were leaking into the story graph *(2026-08-15)*

Found by dumping RI ch1's actual span table (`store.get_spans`) end to end
and reading every line's `speaker_self_id`, prompted by the author's report
that classification "isn't even able to detect the clan leader" and "took
[the author's extra info] as a stupid dialogue of narrator." The dump
confirmed both complaints, plus a third the author hadn't named yet:

- **Blocks 88, 89, and 91 — the actual body of the chapter's "TL Note:" and
  its footnote — were classified `PROSE`, not `TRANSLATOR_NOTE`, and fed
  straight into span classification and speaker attribution.**
  `ingest/classify.py::classify_block` only recognises a *labelled* note
  block (one starting with "TL Note:"/"Translator's Note:"/etc.); its own
  continuation paragraphs carry no such marker and were re-entering the
  story as ordinary prose. One of those continuation blocks (89) literally
  says *"This novel has another name, Daoist Gu"* — and the pipeline
  resolved a phantom character entity named **"Daoist Gu"** out of that
  sentence, then used it as the attributed speaker for several of the real
  clan leader's actual dialogue lines elsewhere in the chapter (blocks 47,
  48, 55, 71). This is likely the single biggest reason "the clan leader"
  reads as absent: some of his lines were captured by a person who does not
  exist, invented from the translator's meta-commentary about the novel's
  alternate title.
- **Fixed** in `ingest/adapters/base.py::parse_chapter`: once a block
  classifies as `TRANSLATOR_NOTE`/`AUTHOR_NOTE`, every remaining block in
  the chapter is now forced to the same type, rather than only the labelled
  block. In this corpus a translator's note is always chapter-terminal —
  including a second `* * *` separator and a footnote *after* it (RI ch1's
  actual layout) — so latching to the end of the chapter is the correct
  boundary, not merely a convenient one. Verified against the real EPUB:
  re-ingesting ch1 now classifies blocks 87-89 and 91 as `TRANSLATOR_NOTE`
  (were `PROSE`); `BlockType.is_story_content` already excludes that type,
  so downstream phases now see nothing from that section without any other
  change required.
- **Separately confirmed, not yet fixed:** block 2 of ch1 — a shouted
  line, `"Fang Yuan you damn demon..."` — was attributed to
  `speaker_self_id = "Qing Mao Mountain"`, a *place* name, not a person.
  This is the `TargetKind`-typing gap already tracked as open defect #7 in
  4 above, but this is the first confirmed case of it corrupting a
  *speaker* attribution rather than just a review-table display, which is
  a more serious instance of the same root cause than previously recorded.
- **Still not fixed, and now better understood:** even with 4.32's bug
  gone, the clan leader's dialogue (blocks 37, 47, 48, 54, 62, 68, 69, 78)
  is scattered across four different `anon:1:N` slots rather than
  consolidated onto one, because `_assign_anonymous_slots` cycles slots
  per-unresolved-run rather than per-speaker (4 item 1's forward-only-pass
  diagnosis, confirmed again here against real chapter-1 data). Fixing item
  1 is what actually makes the clan leader "detected" as one continuous
  character rather than four unrelated anonymous voices; 4.32's fix only
  stops a wrong person from stealing some of his lines.
- **Workflow clarification from the author, worth recording:** the
  intended shape of a normal session is to run ingest through persona
  build across the *whole* novel once (building the full character
  knowledge base the resolver/speaker/persona stages need to work
  correctly), and treat voice/render as a separate, cheap, per-chapter step
  drawn from that knowledge base — not to re-derive character identity
  from a single chapter's text in isolation. A same-session verification
  run against ch1 alone (`--chapters 1-1`) produced only 2 entities/21
  mentions from a chapter that clearly has more named characters than
  that, which is a demonstration of exactly this: the mention/resolve
  stages are tuned against multi-chapter context (lexicon induction,
  cross-chapter alias linking) and are not representative of quality when
  starved of it. This was already the pipeline's designed structure (0,
  8's `run` vs `voice`/`render` split) — nothing to build, just to run
  correctly and document as the expected workflow going forward.

### 4.33 `add_spans`/`add_mentions` never deleted stale rows on re-run — the real reason "Daoist Gu" survived 4.32's fix *(2026-08-15)*

After 4.32's ingest fix landed and a full 1-199 `run` completed cleanly,
re-inspecting ch1's span table directly (`store.get_spans`) still showed
the phantom "Daoist Gu" speaker on real dialogue lines. Root cause was one
level deeper than 4.32: **`Store.add_spans` and `Store.add_mentions` are
both `INSERT OR REPLACE` keyed by row id, with no corresponding delete of
rows a fresh re-derivation no longer produces.** When a block's
classification changes such that it now yields *fewer* spans/mentions than
a previous run did (exactly what 4.32's fix does — one `NON_DIEGETIC`
span instead of three story-typed ones), the previous run's now-orphaned
ids are simply never touched again and sit in the table forever, mixed in
with the correct new rows. `speakers/runner.py::attribute_novel` (spans)
and `mentions/runner.py`'s per-chapter loop (mentions) both write this
way. This is a **general store-hygiene bug, not specific to translator
notes** — any block whose span/mention count changes between two runs
against the same database (a regex tightened, a bug fixed, a corpus
adapter changed) leaks stale rows the same way, silently, with no error.

Given `data/reruns/reverend-insanity.db` has been re-run across many
sessions, this means **its current mention/span/entity counts likely
include an unknown amount of accumulated stale-row noise from every prior
session's fixes** — not just today's. No way to quantify how much without
a from-scratch re-ingest, which is exactly what the next full run (started
after this fix) does for the first time since the bug was introduced.

Fixed: `Store.delete_spans_for_chapter` / `delete_mentions_for_chapter`,
called immediately before each chapter's fresh rows are written in both
runners. `uv run pytest packages/` 682 passing. A second full 1-199 `run`
confirmed clean: `store.get_spans`/`get_mentions` on ch1 show no duplicate
rows, and the "Daoist Gu" mention/self_entity rows are gone entirely.

### 4.34 Speaker attribution: two roster-pollution bugs and a missing tier, found against real ch1 data *(2026-08-15)*

After 4.32/4.33 cleared the "Daoist Gu" phantom, re-inspecting ch1's
dialogue spans still showed real damage: a location (`Qing Mao Mountain`)
and a self-referential idiom (`"this one"`) both got attributed as the
*speaker* of real lines, and the clan leader's dialogue was scattered
across unrelated anonymous slots (or worse, credited to Fang Yuan) despite
the text containing explicit speaker tags for him ("...the clan head
sighed", "The clan head strictly instructed."). Three fixes, all verified
against ch1's actual spans, not just tests:

1. **Roster pollution, source 1**: `speakers/runner.py::attribute_novel`
   built `known_names`/`display_roster` (which gate both the deterministic
   tiers' `_known()` check and tier 4's LLM prompt) from every mention with
   `alias_type.enters_graph`, with no check on `entity_label`. A mention
   the NER layer confidently tagged `"location"`/`"organization"` entered
   the roster exactly like a person — how a mountain became an attributed
   speaker. Fixed: those two labels are now excluded before a mention
   reaches the roster.
2. **Roster pollution, source 2**: `AliasType.RELATIONAL_DEICTIC` ("this
   one", "that person") is defined in `core/enums.py` as *speaker-relative*
   — its referent depends on who's already talking — but was entering the
   roster as if it were a fixed name anyway, so the LLM tier attributed a
   line to the literal string "this one". Fixed: `RELATIONAL_DEICTIC`
   mentions are now excluded from the roster too.
3. **A missing tier, not a missing mechanism**: the text does carry a real
   speaker tag for the clan leader — he's never named in ch1, only ever
   referred to by title ("the clan head"/"the Gu Yue clan head"), and the
   attribution ladder had no tier that could use a title-based tag the way
   it already uses a name-based one. Added `attribute_epithet`
   (`AttributionMethod.EPITHET_SLOT`): fires on the exact same
   speech-verb-adjacency `attribute_explicit` requires, but for a bounded,
   text-verified role-title list (currently just `"clan head"` — extend
   only against other real chapters, not speculatively, per EVOLUTION.md's
   warning about the combat-vocabulary mechanism that scored zero from
   guessing). A match mints a **stable id keyed by the title itself**,
   scoped to the chapter — never a graph `Self` (a title can transfer to a
   different person later, unlike a name) — so every line tagging "the
   clan head" lands on the same consistent voice instead of a fresh
   anonymous slot each time. Also closed a real gap in `_SPEECH_VERBS`
   ("instructed"/"instructs" were missing; one of the two verified hits
   depended on it) and caught-and-fixed a regression during
   development: checking the *preceding* window as well as *following*
   let one line's postposed tag ("...the clan head instructed.") bleed
   into the *next* line's window and misattribute the reply that came
   after it to the same title. `attribute_epithet` now checks `following`
   only — the only direction with a verified real case.

Result on ch1 (deterministic tiers only, no LLM client): "Qing Mao
Mountain" and "this one" no longer appear as speakers anywhere; two of the
clan leader's postposed-tag lines (`the clan head instructed`, `the clan
head sighed`) now resolve to one consistent `epithet:1:clan-head` id
instead of two unrelated anonymous slots. **Deliberately incomplete, and
correctly so**: lines with a *pronoun* tag ("he faced the clan elders and
said,") or no tag at all still fall through to `ANONYMOUS_SLOT`/unresolved
— per the author's explicit instruction, some lines genuinely have no
recoverable textual evidence and forcing an attribution onto them would be
a confident wrong answer, worse than leaving them unresolved. Pronoun-to-
epithet coreference (resolving "he" to the most recent epithet-tagged
subject) is the natural next increment but needs scene-scoped state this
pass doesn't build — left for a session that can verify it against real
text the way this one did, not guessed at now.

`uv run pytest packages/` 682 passing throughout.

### 4.35 Full-volume processing isn't actually helping early chapters — the clan head's real name never reaches ch1, for two stacked reasons *(2026-08-15, diagnosed, not fixed)*

The author's own observation, confirmed correct: the Gu Yue clan head is
*named* later in volume 1 — "Gu Yue Bo" — used explicitly in chapters 6,
25, 39, 54+ ("go against me, Gu Yue Bo!", "the clan head, Gu Yue Bo"). If
whole-volume processing (0's stated point of running `resolve`/personas
across all 199 chapters rather than one at a time) actually paid off for
early chapters, chapter 1's "the clan head" should be attributable to that
name once the rest of the book has been read. It currently is not, for two
independent, stacked reasons — both diagnosed against real data, not
guessed at:

**Issue 1 — "Gu Yue Bo" the mention barely exists at all, for two different reasons depending on the chapter:**

- **Most chapters (25, 39, 54, ...): the database is stale relative to the
  NER cache, not a code bug.** `data/lexicons/reverend-insanity-ner-cache.json`
  correctly contains "Gu Yue Bo" → `character` in 31 separate chapter
  entries — re-running `detect_mentions_in_chapter` against the *current*
  cache and chapter 25's real text reproduces a correct
  `Mention("Gu Yue Bo", RIGID_NAME, confidence=0.7)` directly. But
  `data/reruns/reverend-insanity.db`'s actual mention rows for chapter 25
  only have "Gu Yue Mo Bei" — the run that populated this database used an
  older, smaller version of the cache than exists on disk now (the cache
  file has clearly been extended since, likely by isolated NER iteration in
  an earlier session, without a corresponding mentions re-run). Fix: just
  re-run the mentions phase against the current cache — no code change
  needed for this part.
- **Chapter 6 specifically: a real, still-live bug.** Its current cache
  entry is an empty `{}` — the model call happened and returned candidates,
  but every one was rejected by `chapter_ner.py`'s `plausible_name()`
  filter. Strong inference (not confirmed by replaying the exact raw model
  output, since that requires a live model call to reproduce): the text
  reads `Gu Yue Bo!”` with punctuation directly adjacent, and
  `chapter_ner.py`'s `_SENTENCE_MARK = re.compile(r"[.!?;:,]")` rejects any
  candidate surface containing one of those characters — if the model
  copied the trailing `!` into its returned string, the whole candidate is
  discarded rather than punctuation-stripped and kept. Needs a real fix:
  strip trailing sentence punctuation from a candidate before the
  plausibility check, not reject the candidate outright.

**Issue 2 — even with the name captured, nothing carries it backward.**
This is the deeper, architectural gap, and it's a real gap, not a bug:
speaker/mention processing runs forward, chapter by chapter. Bare role
titles ("the clan head") are deliberately excluded from ever becoming a
mention at all (`GENERIC_DESCRIPTOR`, never entering the graph) —
specifically to avoid a title falsely binding to the wrong person, which
is a real risk in this exact book: chapters 7/13/15/16 discuss a
*different*, historical "**the fourth generation clan head**" — proof that
naively binding every "clan head" mention across the whole volume to one
name would actively break things. 4.34's epithet-tag tier (added this
session) works around this locally per-chapter but does not solve
backward propagation.

**A design sketch exists, not yet built or validated — the author is
ideating on this with other agents in parallel, so treat this as a
starting point for that conversation, not a spec to implement blind:**

1. A lightweight, whole-book pass (after mentions/resolve, before
   attribution) that finds occurrences of a bounded, verified epithet
   phrase in direct proximity to an already-resolved `RIGID_NAME` mention
   (e.g. "the clan head, Gu Yue Bo" / "Gu Yue Bo... the current clan
   leader"), and records that binding.
2. **The disambiguating signal already exists in the text and doesn't need
   to be guessed**: an ordinal + "generation" ("the fourth generation clan
   head") marks a *different*, historical referent; a bare, unqualified
   epithet is the current holder. Gate the backward pass on this pattern
   specifically, not a vaguer "temporal window" or a guessed trigger-word
   list — this book already tells you which occurrences are safe to bind
   and which aren't.
3. **This must never become a graph `Self` fact.** It has to stay an
   attribution-layer lookup (something `attribute_epithet`/
   `_assign_epithet_speakers` can consult), exactly like 4.34's per-
   chapter epithet ids already do, not a permanent binding written into
   `self_entity`/mentions — a title provably changes hands in this book
   (the fourth-generation/current-generation split *is* a title transfer),
   and the codebase already has a documented, deliberate rule against
   letting a `GENERIC_DESCRIPTOR`-class reference enter the graph as a
   fixed identity for exactly this reason (`core/enums.py`'s `AliasType`
   docstring; see also `EVOLUTION.md` on why lexicons are induced rather
   than hand-written, and on the pre-filter-not-scorer design generally --
   the pattern of "verify against real text, keep the binding narrow and
   revocable" recurs throughout this codebase's history for good reason).

Neither issue is fixed. Issue 1's "stale DB" half is a one-line re-run,
not a code change; its chapter-6 half needs a real fix in
`chapter_ner.py::plausible_name`. Issue 2 needs new code, not yet written.

### 4.36 ch1.mp4 regenerated with today's fixes, then actually watched — video output is now versioned as data/video_v4/ *(2026-08-15)*

`ch1.mp4` was re-rendered against the fully fixed pipeline (4.32-4.34's
ingest/attribution fixes, item 8's reference-conditioning fix, the beat-
boundary/mob-detection/locale-cue fixes) — the panel cache had to be
cleared first (moved to `data/panels/reverend-insanity/ch1.bak-pre-fixes`),
since `render_panels` only checks whether a file exists at the expected
path, not whether the prompt that would produce it has changed, so the
previous session's stale PNGs were silently being reused despite every fix
above. **7 of 14 panels now have real reference conditioning** — the first
time `conditioned_panels > 0` has ever been true for this novel. Discovered
and documented mid-render: the LLM director and the local diffusion engine
cannot share this machine's 8 GB VRAM within one `render` invocation
(`EVOLUTION.md` section 9 has the measured OOM and the fix — `--no-director`
required alongside `--image-engine manga` until `render` sequences the two
itself); this render used `--no-director`, so its prompts are the mechanical
assembly path, not LLM-authored. Full measured timing (30m55s, cache/
conditioning counts) is in `EVOLUTION.md` section 9, not duplicated here.

**A real mistake, recorded rather than quietly fixed:** this render was
first written in place to `data/video_v3/reverend-insanity/ch1.mp4`,
overwriting the previous session's 545s reference video — the one the
author had actually watched to produce 4.31's nine-item list. That file is
git-ignored (video output is documented as "regenerable," not tracked) and
is **not recoverable** — checked `/tmp` for stray copies from the same
period and found three (`video`, `video_v2`, `video_manga`), all from
2026-08-13 with different durations/sizes, none matching the 545s file
that existed when this session started. **Going forward, a pipeline output
directory is never overwritten in place** — this run's output has been
moved to `data/video_v4/reverend-insanity/`, and each subsequent full
re-render gets its own `video_vN/` directory so the author can always watch
the previous version back to back with the new one, which is the entire
point of keeping history here rather than only in prose.

**This one got watched — see 4.37 for the real findings.**

### 4.37 Author watch-through of data/video_v4/reverend-insanity/ch1.mp4 — six real findings, none fixed yet *(2026-08-15)*

Mixed result, in the author's own words: some parts better, some parts
worse than the previous (now-lost, see 4.36) version. Nothing in this
section is fixed — intake for the next session, in the order raised.

1. **The clan head's very first actual line was voiced as a woman**,
   despite the character being male. This is a real, direct regression the
   author caught by ear, distinct from and worse than the fragmentation
   problem 4.34/4.35 already tracked — a wrong-gender voice is a confident
   wrong answer, not merely an inconsistent one. Likely cause, not yet
   confirmed: 4.34's `epithet:1:clan-head` id and the plain `anon:*` slots
   both carry no gender signal into voice casting at all — casting
   presumably falls back to a rotation or default bucket for any speaker
   id that isn't a resolved `Self`/`Persona` with a known gender attribute.
   The text itself states his gender unambiguously ("his voice",
   "he clenched his fists") on nearly every line attributed to him, so the
   signal exists and simply isn't reaching the caster — worth checking
   `voice/casting.py`'s handling of `EPITHET_SLOT`/`ANONYMOUS_SLOT` speaker
   ids specifically, not the bucket-matching logic itself.
2. **Many of the clan head's lines are still an unknown/anonymous
   speaker.** Expected and already tracked (4.34's "deliberately
   incomplete" note, 4.35's pronoun-coreference gap) — recorded here only
   to confirm it's still visibly true by ear, not a new finding.
3. **Voice collision: anonymous slot 1 and the narrator used the same
   reference voice in one chapter.** This must never happen — the corpus
   has enough distinct voices that a narrator/character collision within
   one chapter is a casting bug, not a resource limit. Check whether
   `voice/casting.py`'s collision-avoidance pool includes the narrator
   voice at all, or only tracks collisions among character/anonymous
   slots and treats the narrator as a separate, unchecked lane.
4. **The narrator's voice is too flat — no emotional delivery.** The
   author wants real narrative emotion in the narrator's reading, not just
   in character dialogue. Likely lands in `voice/delivery.py`'s parameter
   mapping (already designed to read register/Big Five per `EVOLUTION.md`
   section 4b, but that mapping may not be reaching the narrator lane, or
   may be under-driving Chatterbox's actual expressiveness range) — needs
   a real listen-and-tune pass, not a guess.
5. **Age/gender bucketing alone is not enough register signal.** Direct
   quote of the pattern: the "asian voice" (author's description) sounded
   weak/unconfident when cast for an elder, and elders — described in the
   text as authoritative pillars of the clan — need a voice with real
   confidence and strength. By contrast the female voices used elsewhere
   already had good emotion and pacing; the male voices skewed too
   fast-paced and bland. This is exactly item 2's already-tracked gap
   (`voice/bank.py::nearest_bucket` has no register axis, 4.31/4.34) now
   confirmed by ear with specific, actionable detail: register needs to
   bias not just *which* voice gets picked but the delivery parameters on
   top of it (pacing, confidence/strength), and the current default
   delivery for the male bucket is measurably worse than the female one —
   worth checking whether `delivery.py`'s parameter mapping is symmetric
   across genders or was tuned/tested mostly against female reference
   clips.
6. **Image frequency/focus is wrong in a specific way.** Fang Yuan's
   design "matches a little" with his described appearance (some progress
   from 4.34/8's reference-conditioning fix), but the chapter reads as a
   sequence of different portraits *of Fang Yuan* rather than images that
   track what the scene actually contains — the same complaint as 4.31
   items 6/7/11, now reconfirmed after this session's beat-boundary/mob/
   locale fixes, meaning those fixes improved *relevance* somewhat but did
   not fix *whose face is on screen*, which is a casting-per-panel problem
   (`get_panel_cast`/`present_beat_entities` in `render/panels.py`), not a
   scene-content problem. **Explicit pacing target from the author: panel/
   image change frequency should be roughly 60% of a typical manhwa's cut
   rate** — fewer panels than a real manhwa page-turn, but enough that the
   story reads as progressing rather than as one character's portrait
   gallery. This is a concrete, checkable number against `--max-panels`
   and `_merge_to_budget`'s behavior, not a vague "more panels" ask (4.31
   item 9 already warned against blindly raising `--max-panels` before
   relevance is fixed — this is the same warning, now with a real target
   ratio to test against instead of a guess).

**None of these six are fixed.** Given the size of this session already,
they're intake for the next one, not a queue to clear immediately.

### 4.38 4.37's six findings: four fixed and verified, one improved, one blocked on real prerequisites *(2026-08-15)*

Worked through 4.37's list same-session, against real ch1 data at every
step, not just tests (682 passing throughout).

**Item 1 (wrong-gender voice) — fixed.** `voice/runner.py` was casting
anonymous/epithet slots with a hardcoded `"unknown"` gender, which VCTK has
no bucket for, so `nearest_bucket` silently fell back to a mixed-gender
pool -- roughly even odds of a male character getting a female voice.
Fixed by inferring gender from pronoun density in the narration
surrounding *every* occurrence of a slot across the whole chapter
(`persona.traits.gender_from_pronouns`), widened to a +/-5 block window --
narrower windows (+/-1, +/-3) didn't clear the function's own 6-pronoun
floor; +/-5 cleared it unanimously (6/6, 8/8) on the real clan-head case.
Verified: the clan head now gets `p347`/`p360`-class male voices, not a
coin flip.

**Item 2 (many lines still unknown) — meaningfully improved, not solved.**
Wired the previously dead `_PRONOUN_SUBJECT` regex (defined last session,
never called) into a real tier: `attribute_pronoun_epithet` resolves a bare
"he/she + speech verb" tag to the chapter's current epithet holder, tracked
via `epithet_mentioned()` on every block's narration (speech-verb adjacency
not required). Caught a real regression during verification before it
shipped: without also clearing the state when a *different* named
character's narration takes over, Fang Yuan's own line at block 84 got
misattributed to "the clan head" (nothing between block 68 and 84 ever hit
an EXPLICIT resolution to clear it the original way). Fixed by also
clearing on any block whose narration mentions a different known name.
Full-volume EPITHET_SLOT count: 8 (before this session) -> 26 (naive,
included the false positive) -> **9 (real, after the fix)**. Still open:
lines with no epithet tag *and* no pronoun tag anywhere nearby correctly
stay `ANONYMOUS_SLOT` -- that's the honest remaining gap, not a bug.

**Item 3 (voice collisions) — fixed.** Anonymous/epithet slots could land
on the narrator's voice, a named character's voice, or each other's, by
coincidence -- confirmed on ch1 (narrator == Unknown Speaker 1 before the
fix). Fixed with a per-chapter "voices already in use" set that every
slot-casting decision checks against, widened to same-gender/any-age
before actually accepting a repeat (VCTK's `male:adult` bucket is only 6
speakers wide and RI ch1 needs 6 simultaneously: narrator, Fang Yuan, and
4-5 anonymous/epithet slots -- genuine resource pressure, not a logic
bug). Verified: all 7 distinct ch1 speakers now have 7 distinct voices.

**Item 4 (flat narrator) — fixed, and found something bigger while fixing
it.** The entire delivery-marker/polarity system -- `spans/delivery.py`'s
own "non-negotiable #10" -- was extracted at span-classification time and
then never reached synthesis at all: `voice/runner.py` hardcoded
`polarity=None` on every call to `settings_for`. This was very likely the
dominant cause of "flat," not merely a tuning issue. Wired in: narration
checks its own text for a marker, dialogue/inner-monologue falls back to
the surrounding block window (where a postposed speech tag actually
lives). Also nudged narration's baseline (0.40/0.55 -> 0.46/0.52) as a
secondary, smaller tweak. Verified: real lines now carry `HUSHED`/`WARM`/
etc. rationale strings in the manifest instead of every line reading
`"neutral"`.

**Item 5 (register-blind casting) — partially addressed, ceiling is real
and unmoved.** VCTK carries no register metadata (`voice/bank.py`'s own
documented limitation) and this session did not change the *bank* -- it
can't, without new voice data. What it *can* do: bias delivery parameters
by `TraitProfile.register`. A `"formal"` register (elders, authority
figures) now lowers `cfg_weight` -- the documented lever for slower, more
deliberate pacing -- in both the narration and dialogue paths. This
directly targets the "male voices too fast-paced" half of the complaint;
it does not and cannot address "the elder sounded weak" if the underlying
reference clip itself reads as unconfident -- that needs either new voice
data or a smarter clip-selection heuristic within a bucket, genuinely not
built.

**Item 6 (image frequency / whose-face) — panel budget raised on explicit
instruction; whose-face is blocked on real prerequisites, not deferred out
of laziness.** `--max-panels` default raised 14 -> 70 (author instruction,
targeting ~60% of a manhwa's panel density) in both `render/beats.py` and
`cli.py`. This is a real cost trade-off, not a free change -- roughly 5x
the render wall-clock for the same GPU (measured 14-panel baseline:
~31 minutes with `--no-director`, `EVOLUTION.md` section 9). A 70-panel
ch1 render was started this session; see this file's top-of-document
status for its outcome once it lands.

Whose-face-on-screen was investigated, not fixed: checked whether ch1 has
*any* other resolved named character besides Fang Yuan to generate a
reference sheet for, and it does not -- chapter 1 resolves to exactly two
`Self` entities, Fang Yuan and "Qing Mao Mountain" (the location-as-Self
bug, 4.32). The clan head cannot get a reference sheet because he is not a
graph entity at all, which is 4.35's still-open mention-detection gap
("Gu Yue Bo" is confidently NER-extracted 31 times and never becomes a
mention). Generating more reference sheets right now would have produced
nothing useful for this specific chapter, so it was skipped rather than
faked. **4.35 is upstream of item 6 being properly fixable for ch1's clan
head specifically** -- worth remembering the next time item 6 looks like
a pure image-generation problem.

### 4.39 Voice layer: pitch shift, gender coin-flip, mob casting; a local multi-provider LLM gateway; scene-grouped image generation replacing per-block generation -- large session, several real bugs caught before shipping *(2026-08-15)*

Picking this up fresh: **this section is the actual state of the render
pipeline as of this session's end.** Read it before 4.30-4.38 if you only
have time for one -- several things those sections describe (per-beat
panel generation, the additive motion-clip scorer, no register/age lever
in voice casting) were replaced in this session, not merely patched.

**Voice layer, all verified against real data, not just tests:**

- **Pitch shift** (`voice/pitch.py`, new): post-synthesis, via ffmpeg's
  `rubberband` filter (duration-preserving, unlike `asetrate`+`atempo`).
  `DeliverySettings.pitch_semitones` -2 for `profile.register == "formal"`.
  Author correction that shaped this: in a cultivation novel "elder" is a
  *rank* (authority, seniority), not a biological age descriptor -- the
  fix targets *sounding commanding*, not *sounding old*. Neither VCTK nor
  Chatterbox exposes an age/authority dial, so this is the only lever
  available short of new voice data.
- **50/50 gender coin-flip for genuinely unresolved speakers and crowds**
  (author instruction): `voice/runner.py` no longer lets VCTK's own
  population imbalance (63 female / 47 male) bias casting when the text
  states no gender at all. `CROWD_REACTION` spans also got real mob-voice
  casting for the first time -- they were falling into the narrator
  branch by default before this.
- **VCTK's real limitation, confirmed, not assumed**: only 6 male-adult /
  8 female-adult voices, zero elder, zero child; 96 of 110 speakers are
  "youth". Researched but **not yet integrated**: LibriTTS-R (2,456
  speakers, CC BY 4.0, openslr.org/141, balanced gender, no
  child/teen/elderly either) as the adult-bucket fix. Explicitly **not**
  pursuing a dedicated elderly-speaker dataset, per the rank-not-age
  correction above -- VCTK's own youth skew is actually well-suited to
  RI's early, disciple-heavy chapters and should stay.
- Also this session (documented in 4.38, still true): wrong-gender voice
  casting fixed, voice collisions fixed, the dead delivery-marker/polarity
  system wired into synthesis for the first time, pronoun-to-epithet
  coreference added to speaker attribution.

**A local multi-provider LLM gateway** (`llm/gateway.py`, new
`ModelBackend.GATEWAY`): the author's own separate project, a
key-rotation/fallback proxy across free-tier providers (Gemini, Groq,
OpenRouter, ...), OpenAI-compatible, `127.0.0.1:11435/v1`. Verified as a
real, legitimate local service before any code was written against it
(checked what was actually listening on that port). Exists specifically
to get LLM calls off `ollama` for stages that can't share this machine's
8 GB VRAM with a local image/TTS engine.

- `config.json` (gitignored, `config.json.example` committed -- same
  pattern as `.env`/`.env.example`): holds `gateway.host`, `gateway.model`,
  and `render.direction_first` (bool), since these are meant to be
  hand-edited directly. `Settings` applies `config.json` only where an env
  var hasn't already set the field.
- **Real, caught issue, not yet fully resolved**: some providers the
  gateway routes to under load don't honour "JSON only" as reliably as
  others -- confirmed directly (identical requests, one clean JSON
  response, one markdown bullet list, no code change in between).
  Mitigated three ways: 4 retries (gives the gateway's own rotation a
  second chance), a much stronger anti-markdown instruction in
  `schema_instructions` (stated three times: opening, worked example,
  closing), and a markdown-bullet-list salvage parser as a last resort.
  **Still not bulletproof**: mid-render this session, the backing Gemini
  key hit its free-tier rate limit (confirmed via the author's own usage
  dashboard -- a spike of 429s), which cascaded into the gateway itself
  returning 502s for a stretch, and those calls fell back to mechanical
  prompts after exhausting all 4 retries. This is provider-side rate
  limiting, not a bug in `gateway.py` -- but it means a real render can
  still have a meaningfully lower director-coverage rate than intended if
  it lands during a rate-limit window.
- `response_format` upgraded to `json_schema` (`strict: false`, for
  uneven provider support) from the weaker `json_object`.

**Two-phase render (direction pass, then image pass)**, config-gated via
`render_direction_first`: `render_panels` gained `prompt_cache_path` --
every beat's prompt is cached to JSON keyed by `chapter:block_index`, so a
second call against the same cache reuses it and skips the director
entirely. `cmd_render` runs phase 1 (director calls, whatever backend is
configured, `StubImageEngine`, no GPU cost) then phase 2 (the real local
image engine, `client=None`, no further LLM calls) when a director client
is configured and the toggle is on.

- **A real, caught bug, fixed same-session**: phase 1 originally wrote to
  `args.panel_dir` -- the *same* directory phase 2 uses. `StubImageEngine`
  writes a real (placeholder) PNG file, and `render_panels`'s own
  cross-run cache checks `image_path.exists()` -- so phase 1's placeholder
  files made phase 2 think every image was already rendered, and it
  silently skipped real SDXL generation for all 39 panels in the first
  full run of this feature. Fixed: phase 1 now writes to a `tempfile.
  mkdtemp()` scratch directory, cleaned up after phase 2 completes. Only
  `prompt_cache_path` needs to survive between the two phases; the image
  files must not.
- **Still open, not yet fixed**: `ollama` runs as a persistent background
  server, not an in-process model. Two-phase generation avoids one
  *specific* GPU conflict (the director LLM and local diffusion loaded in
  the same Python process), but if `director_client.backend is
  ModelBackend.OLLAMA`, `ollama serve` stays resident across both phases
  of one `cmd_render` invocation regardless -- there is currently no code
  that stops it between phase 1 and phase 2. Every ollama-backed render
  this session that avoided the OOM did so by the operator manually
  stopping `ollama serve` between phases, not because the code guarantees
  it. **This is the immediate next thing to build**: an explicit ollama
  shutdown between phase 1 and phase 2 in `cmd_render`, gated on
  `director_client.backend is ModelBackend.OLLAMA`, before switching the
  gateway back off in favour of ollama for the next render (which is
  where this session was headed when it stopped -- the gateway's Gemini
  key was rate-limited, and the author asked to switch to ollama for
  directing next).

**Scene-grouped image generation, replacing per-block/per-beat generation
entirely** -- this is the biggest structural change of the session, from
an explicit author spec (full text not reproduced here; ask for it if the
exact numeric targets matter again). Core idea: a chapter's blocks group
into *scenes* (contiguous stretches sharing cast, place and timeline), and
a scene's *length in blocks* sets a hard image budget (1 for <=3 blocks, 2
for 4-7, 3 for 8+) rather than one image per beat/block.

- `render/scenes.py` (new): `group_scenes()`. Boundary fires on a
  `NarrativeSegment` change, a cast change, or a location change
  (`persona/attire.py::scene_locale`).
- `render/panels.py`: rewritten to iterate scenes, generate only the
  slots (establishing/close-up/wide -- reusing the existing
  `STYLE_ESTABLISHING`/`CLOSEUP`/`SCENE` prompt machinery, not a new
  parallel one) a scene's blocks actually use, and write one manifest row
  per *block* pointing at its slot's (possibly shared) image -- this is
  what keeps `render/timeline.py` and everything downstream unchanged
  while cutting the actual generation count.
- `render/director.py`: added `KEN_BURNS_ZOOM_IN/ZOOM_OUT/PAN_SCALE/
  PAN_TRANSLATE_PCT` constants (`# TUNING`, first-guess). Motion-clip
  scoring rewritten to an exact three-tier priority order (duration>8s +
  clip-tag / duration>6s + scene emotional peak via `spans/delivery.py`
  markers / duration>6s alone) replacing the previous additive scorer.
  `pan_direction` rule left exactly as-is (explicit instruction).
- `render/compose.py`: `_zoompan_filter` now reads `director.py`'s Ken
  Burns constants instead of its own local `_MAX_ZOOM`.
- **Two real scene-boundary bugs found and fixed before the real render,
  by checking numbers against the spec's own 15-25 sanity range first**:
  (1) `scene_locale`'s rotating fallback (deliberate, for *panel-
  background* variety on unstated blocks) looked like a location change
  on nearly every block -- fixed with a new `strict=True` parameter that
  returns `""` instead of rotating, used only by `scenes.py`. (2)
  Comparing cast only against the *immediately preceding* block treated
  an ordinary rotating exchange (RI ch1's opening: four unnamed attackers
  taking turns) as a new scene on every turn -- fixed by comparing against
  the accumulated union of the current scene's speakers, and excluding
  `ANONYMOUS_SLOT` speakers from the cast signal entirely (a rotating
  anon slot is an unidentified member of a group already present, not a
  new arrival; `EPITHET_SLOT` still counts). Measured: ch1 78 -> 19 scenes
  (30 images), ch2 -> 4 scenes (10 images) -- **not a clean fit to the
  spec's 18-22 target either direction, and further tuning needs a real
  watch-through this session didn't reach.** Flagged honestly, not
  chased to an exact number under time pressure.
- **The real SDXL render this was all building toward has not
  successfully completed yet.** One run finished in ~24 min but produced
  every panel as a stub placeholder (the caching bug above, since fixed).
  Another run's director coverage was degraded by the mid-run Gemini
  rate-limit. **Next session's concrete first step**: build the ollama-
  stop-between-phases fix, switch `ECHOTALES_MODEL_BACKEND` back to
  `ollama`, and run `echotales render --novel reverend-insanity --chapters
  1-2 --image-engine sdxl --motion-engine svd --compose-engine ffmpeg`
  for real, then report the 10 numbers the original spec asked for (scene
  counts, image counts, timeline event counts, video duration, motion-clip
  block indices and scores, average/outlier hold durations,
  zero-image/carried-over block counts) -- none of that reporting has
  happened yet because no run has completed with both a real director and
  real image generation at the same time.

`uv run pytest packages/` 682 passing throughout this entire session.

---


### 4.45 Six render-path bugs found and fixed, 746 tests passing *(2026-08-20)*

All found against real run output and code inspection, not guessed at. None
required a design change — all were gaps in existing mechanisms.

1. **Hallucinated group phrases in final prompt string — fixed.** The field-
   level `_validate_direction()` (which blanks `action`/`layout`) was swallowing
   its own `log.warning` through the pipeline's log filter, so "warrior women"
   survived into the prompt cache. Added `sanitize_prompt()` in `direction.py`
   as a belt-and-suspenders string-level filter on the final assembled prompt
   just before `prompt_cache[cache_key] = prompt` in `panels.py`. Strips
   any comma-clause containing a banned phrase. Prints to stderr (bypasses
   the log filter). Caught 3 "warrior women" occurrences per run.

2. **Transformers tokenizer warning `81 > 77` spamming run output — fixed.**
   `fit_to_budget` calls `count_tokens` on candidates that intentionally exceed
   the CLIP limit (to check whether to drop them). The CLIPTokenizer fires a
   warning on every such call. Suppressed by setting the transformers logger to
   ERROR level inside `count_tokens`.

3. **Missing `1boy, male focus` on dialogue-only blocks — fixed.** `cast_tags`
   uses `beat_prose` for pronoun-based gender detection. For block 0 of RI ch1
   (an enemy shout in second person), `beat_prose` has no "he/him/his" and
   `genders` is empty, so `cast_tags` returned `""` — no gender tags prepended.
   The director's own `action`/`layout` output ("enemies ring *him* on all
   sides") does have the male pronoun. Fixed: `cast_tags` in the director path
   now receives `beat=f"{beat_prose} {directed.direction.action} {directed.direction.layout}"`.

4. **Negative feminine clause silently truncated by CLIP — fixed.** Critical
   regression: `negative_for(STYLE_SCENE)` alone measures 69 tokens. The gender
   clause (`_NEGATIVE_FEMININE`, ~14 tokens) was appended LAST, pushing the total
   to ~98 tokens — 23 over CLIP's 75-token limit. CLIP truncates from the right,
   so the gender clause (the most important guard against feminisation) was the
   first thing dropped at inference time. Fixed by re-fitting the assembled
   negative as a comma-split priority list with gender terms first. Regression
   test added to `test_prompt_budget.py`.

5. **`gender_negative` had same dialogue-block gap as `cast_tags` — fixed.**
   The negative prompt's feminine exclusion also used `beat_prose` only for
   pronoun detection. Applied the same `directed.direction.action/.layout`
   extension so the negative clause fires even on dialogue-only blocks.

6. **Character appearance dropped from director prompts when name in layout
   only — fixed.** `to_image_prompt` in `direction.py` added the appearance
   clause only when the character's name appeared in `d.action`. The director
   sometimes names the character in `layout` ("Fang Yuan stands alone") while
   using a pronoun in `action` ("He watches"). Fixed by checking
   `f"{d.action} {d.layout}".lower()` for the name.

**Also found but NOT fixed (real, small, low-priority):**

- Possessive mob phrase "clan's elders" still missed by `detect_mobs` — zero
  occurrences in first 10 real chapters, correctly documented in Section 4.31 as a
  known residual gap. No change per EVOLUTION.md's vocabulary-growth rule.

- NER `plausible_name()` fix: strips trailing sentence punctuation (`!?.,;:`)
  before rejecting a candidate — fixes "Gu Yue Bo!" being discarded in ch6
  (Section 4.35's diagnosed-but-unimplemented fix). Internal punctuation still rejected.

**Test count: 746 passing** (was 745 before, 682 before the sessions above; +1
from the negative-prompt regression guard added this session).

---


### 4.40 Image-model bake-off, curated references wired in, fandom-wiki canon, and the real cause of "the images are irrelevant" *(2026-08-18)*

**The headline: relevance was structural, not a director or checkpoint
failure.** Panel slots were assigned by content type alone (narration ->
establishing, dialogue -> close-up), so a scene produced at most three
images however long it was, each anchored to the first block that claimed
its slot. Measured on RI ch1: **22 panels for 92 blocks, with single panels
covering 12 and 16 consecutive blocks.** The audio reads every block but the
picture only changes when a new panel starts, so sixteen blocks of narration
played over one image of the scene's opening moment. The director's prose
was fine throughout ("Fang Yuan slowly turns his body, causing the group of
warriors to step back in unison") and the checkpoint understood it.

Blocks are now chunked at `_MAX_BLOCKS_PER_PANEL = 4` inside a scene, each
chunk taking its own director call and its own beat prose. **RI ch1: 22
panels -> 48, longest hold 16 blocks -> 4.**

**Three defects that only appeared once chunking existed:**

1. `cast.background_mobs` resolves over a whole *scene*, so every chunk of
   RI ch1's opening inherited the besieging crowd -- including a dying
   man's private last thoughts, which lost its character sheet (crowd wides
   drop sheets) and picked up the one-vs-many composition reference. The
   crowds were never random; they were one crowd asserted everywhere. Mobs,
   curated references and crowd roles now resolve from the panel's own
   blocks: **7 of 48 panels assert a crowd, down from every panel of every
   scene that had one.**
2. `ip_adapter_image` was passed as a flat list. diffusers reads the outer
   list as one entry *per loaded adapter*, so two images against one adapter
   raises `must have same length as the number of IP Adapters`. Harmless
   until curated references landed and a panel could carry two. Killed a
   full chapter run 54 panels in.
3. The prompt cache keyed on `chapter:block`, which outlived every change to
   how beats are chosen -- a render kept serving prompts written for the old
   whole-scene beats, and two rounds of "the fix changed nothing" were the
   cache answering. Key now includes a beat digest.

**`echotales relevance` -- the metric that was missing.** Scores each
panel's prompt against the blocks it plays under, exempting crowd cuts
(fixed template) and `beat_canon.py` staging (hand-authored precisely
because the prose was not the wanted picture). It immediately found that
prompt ordering put the standing appearance clause ahead of the beat, and
Fang Yuan's clause runs ~20 tokens of hair and eyes, so the beat kept
losing the greedy 77-token fit -- panels came back as a correct-looking man
doing nothing identifiable, or as pure locale scenery. Beat now goes first:
**mean overlap 0.19 -> 0.27, panels below 0.10 21 -> 9** (RI ch1,
mechanical prompts). All-dialogue chunks also had nothing to fall back on
but the scene's narration -- a different moment -- and now draw from their
own lines, one speaker and a few words, short enough to survive the budget.

**Image model bake-off, measured on the same panels (8 GB RTX 4060 laptop,
15 GB RAM).** Settled stack, engine name `refined`:

| Job | Model | Why |
|---|---|---|
| Composition, crowds | Animagine XL 4.0 (SDXL) | SDXL places many figures; SD1.5 cannot at any prompt. The *finished* checkpoint, not Illustrious's early release |
| Culture and finish | GuoFeng3, img2img @ 0.35 | Chinese art in the weights -- fixes the Japanese drift the Danbooru-trained SDXL checkpoints introduce, for free |
| Identity | IP-Adapter + curated references | `data/scene-references/`, finally consumed (`render/scene_refs.py`) |

Rejected: Illustrious early-release (composes, renders flat), SDXL/SD1.5
base (photoreal), Flux.1 (12B, needs nf4 on 15 GB RAM, ~2 min/panel),
SD3.5/PixArt (fix the 77-token cage, weak style), Kolors (won't fit), Pony
(wrong genre drift), compositing (visible seams, rejected on sight).
NoobAI-XL never finished downloading -- TLS failures on this connection.

**The two-model pass is not compositing.** Nothing is pasted; GuoFeng3
repaints every pixel and inherits only the layout. It cannot change *what
moment* is depicted, so it costs nothing in relevance -- only time (a
second pass), CPU/RAM (two checkpoints resident) and a little crispness.

**Japanese drift is a real error, and the tell matters.** The crossed collar
is *not* one -- hanfu closes right-over-left too. The actual errors are a
wide flat obi, straight eaves, shoji screens, torii and cherry blossom. It
happens because Animagine/Illustrious/NoobAI are Danbooru-trained: "anime"
means Japanese visual defaults in those weights.

**`world/lexicon.py` -- what this novel's words denote, from the graph.**
RI calls Fang Yuan a demon constantly and the checkpoints read that as a
species: a close-up of his dying thoughts came back as a grinning red-eyed
youth with fangs and a forehead gem. Reading mentions was the obvious
design and does not work -- resolution only mints mentions for name-like
spans, so the table knows "Bloodwing Demon Sect" and has never recorded the
bare "demon". Evidence comes from the prose instead: a lowercase creature
word used vocatively or as an epithet, in a block where a person is
present. Two filters keep it from eating real content -- lowercase-only
separates "the wicked demon" from "the Demon Suppression Tower", and a
minimum epithet share (measured across all 199 chapters: demon 5/27 and god
4/13 clear it; worm 47/737, wolf 19/604, beast 9/199 do not, correctly,
since RI has real worms, wolves and beasts). Feeds the director's brief and
the negative prompt.

**`persona/wiki_canon.py` -- appearance from the fandom wiki.** Precedence
is **hand-authored canon > wiki > extraction**. Spoiler containment is
structural: appearance sections only, first 1,200 characters of one (Fang
Yuan's runs 6,700 across three bodies including a six-metre zombie form),
and only typed traits are ever kept. Four things had to be measured: fandom
answers urllib's default User-Agent with a blanket 403 that looks exactly
like an empty wiki; the subdomain is `reverend-insanity`, not
`reverendinsanity`; sequential requests get dropped silently, so pages are
retried and the cache *merges* rather than overwrites; and resolution
classifies Gu worms as people, so the wiki's own categories decide what is
a character. RI top 72 by mention count: 5 with traits, 26 with no page
(mostly epithets like "Gu Master"), 17 not people.

**`speakers/runner.py` -- anonymous slots collided across scenes.** The slot
counter restarts at 1 after every resolved line, so a chapter-scoped id made
collisions systematic: `anon:1:1` was a cultivator besieging Fang Yuan in
block 0 *and* a villager gossiping at the ceremony in block 45, read by TTS
in one voice. Slots are now scene-scoped, and the scenes come from
`render/scenes.py::group_scenes`, **not** from narrative segments --
segmentation emits exactly one MAIN segment per chapter across all 199 (200
segments, 199 chapters), so scoping to a segment would have been scoping to
the chapter under another name. **RI: 727 distinct anonymous voices ->
1,877; ch1 alone 4 recycled slots -> 19 across 8 scenes.** Anonymity itself
is deliberate: background mobs never need names, they need not to share a
voice with someone from another scene.

**Director system prompt now states specifications** (`render/direction.py`):
sex of each named person ("an unstated subject is drawn as a woman"),
ancient-China detail and never Japanese detail, never invent a character
from an insult ("Old bastard Fang" became a character), draw what the
passage *does* rather than what it says, one ground plane per shot. Stated
here rather than in negatives because a rule in the director's prose is free
while the same rule in `panels.py` spends CLIP tokens on every panel of
every chapter.

**Still open after this session:**

- Attribution has not been re-run against the live DB (the render held the
  write lock); the 1,877-voice figure is measured on a working copy.
- Dialogue coverage is **51.3% attributed** over 199 chapters. The slot fix
  made those voices distinct, not *named* -- separate work.
- Nine scored ch1 panels still sit below 0.10 relevance; that list is the
  next thing to work.
- No full chapter has yet gone end-to-end (director -> panels -> SVD ->
  ffmpeg) since chunking landed.
- CPU load during a run, in order: `enable_model_cpu_offload` shuttling
  weights (unavoidable at 8 GB VRAM, doubled by `refined`), ffmpeg compose,
  ollama, then TTS and PNG encoding.

### 4.41 The relevance hunt continued: cast leakage, panel numbering, faction-scoped roles, and an audio layer that could not produce emotion *(2026-08-19)*

**Cast leakage was the largest remaining relevance defect.** `get_panel_cast`
took the whole scene's block range, and the protagonist is present somewhere
in nearly every scene, so a chunk of Gu Yue elders gossiping about a third
party was handed Fang Yuan as cast -- and the director wrote *"Fang Yuan
stands in a stone courtyard, his gaze distant as he contemplates the future
of the Bai clan"* for a passage he does not appear in. Cast and present
entities now resolve from the panel's own blocks. This is the same
scene-wide-scoping mistake as the crowd bug in 4.40, in a third place.

**Panel filenames encoded the lead block**, so one scene produced
`block0021`, `block0026`, `block0047` and a directory listing interleaved
panels from different scenes -- readable only if you knew the slot-assignment
algorithm. Now `p003_b0026.png`: sequential in play order, block kept for
tracing.

**Gender steer only fired when the cast resolved.** `genders` is empty
whenever nobody in frame resolves to a persona, and empty meant "say
nothing", which on these checkpoints means "draw a woman". The beat's own
pronouns now decide.

**`render/factions.py` -- role words carry their faction.** "Elders discuss
worriedly" is accurate and unusable in a novel that runs that word past the
Gu Yue, Bai and Xiong clans in one volume. The graph cannot answer it yet
(RI ch1 has no resolved ORGANIZATION mention at all; the first is ch4), so
the faction is read from the scene's prose by the genre's naming convention,
and no match leaves the role where it started. Scoped per scene, which is
also the answer to a character moving between clans.

**Audio, measured before touching anything.** Chapter 1's v3 render: 97
lines, **70% narration, all at exaggeration 0.40-0.46**. Two real defects
under that:

1. **Delivery markers were read from inside the quoted line.** Block 0 is a
   besieging cultivator shouting "Fang Yuan, quietly hand over the Spring
   Autumn Cicada" -- "quietly" is what he demands, not how he says it. Six of
   the chapter's twenty-seven dialogue lines were marked HUSHED, so threats
   were whispered at 0.40.
2. **The emotion dial cannot produce emotion against read speech.**
   Chatterbox clones its reference clip's prosody, so `exaggeration` scales
   intensity around whatever that clip already sounds like -- and VCTK is 110
   speakers reading prompt sentences. Fixed with a corpus, not a number:
   CREMA-D, 91 actors x 6 emotions with published age/sex, 7,442 clips, and
   `EMOTION_FOR_POLARITY` picking the performance to prompt with.
   `--bank-kind cremad`; VCTK remains the default.

**Video directories now match panels**: `video/ch<N>/v<K>_<date>_<label>/`
holding `ch<N>.mp4`, `segments/` and any `.ass`. The five earlier renders
were loose mp4s beside `video_v2/`-`video_v4/`; they are sorted and labelled
in `data/RI/README.md`.

**Two open items named honestly:**

- **Homonymous factions are not handled.** The second Bai clan, after Qing
  Mao mountain, is a different organisation with the same name.
  `factions.py` is text-derived and will conflate them. The fix is to key a
  faction by name *plus attested locale*, the same shape as the entity-split
  logic resolution already runs.
- **No video has been produced since any of this work.** The newest cut
  predates chunking, the crowd fix, beat-first prompts and sequential
  numbering.

**Where the numbers stand.** Mechanical prompts on RI ch1: mean relevance
0.27, 9 of 40 scored panels below 0.10. The v32 render's director-written
prompts scored 0.09 -- partly the metric punishing paraphrase, partly the
cast leakage above, which is now fixed and untested.

### 4.42 The count-tag bug, and exactly what to do next *(2026-08-19, session end)*

**The bug that invalidated most of this session's visual output.** Panels
came back as women no matter what the prose said. Cause:
`persona/prompt.py::build_image_prompt` puts `1boy, male focus` at the very
front -- these checkpoints weight Danbooru count tags far above any English
phrasing -- while `render/direction.py::Direction.to_image_prompt` composes
its own string from action, cast, setting, lighting and mood, **with no tags
at all**. Every panel a real director wrote therefore reached the model with
no headcount steer and fell back to its training prior, which is
overwhelmingly female.

**The lesson, because this is the second time it has happened:** there are
two prompt paths, and only one of them runs in production. The mechanical
assembler runs under `--no-director`; the director path runs in every real
render. The crowd count tag had the same split three rounds earlier. *Any
prompt-level fix must be applied to both paths and verified on the director
one.* A stub render proving a fix works proves it works on the path nobody
uses.

**State at session end**

- A ch1+ch2 render is running on the fixed code (`refined` engine, director
  on), chained to: relevance audit -> CREMA-D narration -> SVD motion ->
  ffmpeg compose, output under `data/RI/video/`. Logs: `/tmp/ch12b.log`,
  `/tmp/product2.log`. If it died, re-run
  `scratchpad/ch12.sh` then `scratchpad/product.sh` (both in this session's
  scratchpad; they are three lines each and trivially reconstructed from the
  commands in Section 4.41).
- **Nothing in this session has been visually verified after the count-tag
  fix.** Every number quoted in 4.40-4.41 predates it.

**Continue from here, in this order**

1. **Look at the finished panels and the video.** Not the metric first --
   the metric cannot see anatomy, gender or composition. Then run
   `uv run echotales --db data/reruns/reverend-insanity.db relevance
   --novel reverend-insanity --worst 15` for the number.
2. **Check ch1 against ch2 for consistency**, which has never been tested:
   does Fang Yuan look like himself across chapters, do anonymous voice
   slots stay distinct, do the Gu Yue elders look like one clan.
3. **If panels still do not match their beats, stop tuning prompts.**
   Seven rounds of input fixes this week were all real bugs and are all
   fixed; if the output is still wrong after them, the remaining gap is that
   a text-to-image checkpoint *invents* a composition rather than
   reconstructing the one in the prose. The untried lever is **ControlNet
   openpose** -- place the figures explicitly -- or a model larger than an
   8 GB card runs. Do not spend another session on wording.
4. **Verify the audio changes by ear.** The delivery-marker fix and the
   CREMA-D emotional bank are both unheard. Chapter 1 block 0 is the test
   case: a siege threat that used to be whispered.
5. **Open items that are stated and not done:** homonymous factions beyond
   the `faction_key` region hack (the second Bai clan needs a graph entity,
   not a string); dialogue attribution at 51.3%; no batching, checkpointing
   or crash recovery, which makes 199 chapters ~25 GPU-days on this
   hardware; CREMA-D is research-licensed; and the source novel is
   copyrighted, which gates shipping anything publicly.

**Tooling added this session that the next one should use rather than
rebuild:** `echotales relevance` (panel-vs-source scoring, exempting crowd
cuts and hand-authored staging), `echotales graph` (self-contained KG page
with a chapter slider, `data/webview/graph.html`), `echotales persona
wiki-canon`, `--bank-kind cremad`, `render/factions.py`, `world/lexicon.py`,
`persona/forms.py`.

### 4.43 START HERE — NoobAI-XL checkpoint bake-off on 5 real ch1 panels: single-character shots are genuinely better, crowd/establishing shots are not *(2026-08-19)*

**What this session did, deliberately small in scope:** rather than another
full-chapter render (each one costs real GPU hours and the last three did
not settle the question), generated a handful of individual panels against
**real ch1 blocks** with `--image-engine noobai` (`Laxhar/noobai-XL-1.1`,
single-checkpoint, no GuoFeng3 repaint pass) instead of the current default
`refined` engine (Animagine compose + GuoFeng3 repaint), director on, so the
4.42 count-tag fix was live. Command:
`echotales --db data/reruns/reverend-insanity.db render --novel
reverend-insanity --chapters 1-1 --block-range 0-40 --image-engine noobai
--max-panels 5 --panel-dir data/diag/noobai/panels --skip-motion
--skip-compose` (`--max-panels` caps beats merged per chapter, not raw
output count -- 39 panels actually landed at 22s/panel on this checkpoint,
notably faster than `refined`'s two-pass ~2 min/panel).

**Result, looked at directly, not just scored:**

- **Single-character panels (director prompt carries `1boy, male focus` +
  the persona's attribute string) are a real, visible improvement.** Blocks
  9, 29 (`p005`, `p013`): correct gender, correct long-black-hair/white-and-
  dark-green-robe description, a readable face, five fingers on visible
  hands, a legible foreground subject. This is categorically better than
  the "distorted, unrecognizable" panels the author described -- the
  checkpoint swap alone measurably helped here, on this specific class of
  shot.
- **Crowd and establishing-shot panels did not improve, and reproduce the
  count-tag bug's sibling.** Block 0 (`p001`), the chapter's opening "crowd
  of chinese cultivators... 6+boys... elders" prompt, rendered as a single
  feminine-presenting central figure in ornate robes with two smaller
  attendants -- the `6+boys` tag is present in the prompt text and was
  still overridden by the checkpoint's prior. This is **not the same code
  path 4.42 fixed**: that fix was in `persona/prompt.py::build_image_prompt`
  for named-persona panels; the crowd/establishing prompt is assembled
  elsewhere (the mob-detection/scene-locale path) and never got an
  equivalent headcount-tag audit. Block 36 (`p016`), "elders gather... faces
  illuminated by paper lanterns," rendered atmospherically coherent (real
  lanterns, real pavilion, real dusk lighting) but as two figures seen from
  behind, not a gathered group with lit faces -- the checkpoint composed a
  *plausible* scene, not the *described* one, which is exactly the "invents
  a composition rather than reconstructing the one in the prose" ceiling
  4.42 already flagged.

**Conclusion:** swapping the checkpoint is a real, low-cost lever for one
specific failure mode (single-subject anatomy/identity fidelity) but does
**not** touch the other one (multi-subject scene composition, headcount
fidelity outside the per-persona prompt path). Two concrete next actions,
neither of which is "try another checkpoint" again:

1. **Audit the crowd/establishing prompt path for the same class of bug
   4.42 found** -- find where `spans/scene.py`'s mob detection or
   `render/direction.py`'s establishing-shot assembly builds its prompt
   string and confirm whether a headcount/gender tag is present, leading,
   and actually respected on a real render, the same way 4.42 verified the
   per-persona path.
2. **The multi-subject composition gap is very likely the base-model
   ceiling, not a prompt problem** -- consistent with 4.42's own
   conclusion. ControlNet-openpose (explicit figure placement) or a model
   too large for an 8 GB card are the untried levers; per 4.42, further
   prompt wording is not expected to move this.

**On the free-vs-paid question directly, now with a real data point behind
it:** the gap between "single-character panel, checkpoint swap" (fixed by
a free local model) and "multi-subject scene composition" (not fixed by
any local checkpoint tried) is a reasonable proxy for what a larger,
paid/hosted model would likely buy across the board -- more capacity
generally buys exactly this kind of prompt-adherence and composition
fidelity. That remains an expectation, not a result measured in this
project, since staying free/local is the deliberate constraint being
demonstrated.

Diagnostic output, not deleted, for the next session to look at directly:
`data/diag/noobai/panels/ch1/v1/` (39 PNGs + `manifest.jsonl` with every
prompt). Not wired into the real pipeline's default engine -- this was a
look, not a switch.

### 4.44 Two real fixes, found sitting uncommitted from an earlier turn plus one new one: crowd-panel gender tags, and dialogue self-reference for voice gender *(2026-08-20)*

**Housekeeping first, because it mattered**: this session started with
`persona/prompt.py`, `render/panels.py`, `test_prompt_budget.py` and part
of this file already modified on disk but never committed — complete,
tested, working code from earlier in the day that simply never made it
into a commit. Verified (`pytest`, read the diff) before committing rather
than assumed. **If you ever find yourself picking up a session and
`git status` shows unexpected modifications, read the diff before doing
anything else** — it may be finished work, not a mess to clean up.

That work was item 1 of 4.43's own two next actions: `persona/prompt.py::
cast_tags` gained a `beat=` parameter. When `genders` is empty (an
unresolved cast — an unnamed mob role, or a director-named character whose
block window carried no matching mention), it now pushes a positive
`1boy, male focus` / `1girl` tag from the beat's own pronouns, the same
signal `gender_negative` already trusted for its negative-only case.
Measured necessary on real output, not assumed: RI ch1 blocks 0 and 36
both still rendered feminine-presenting subjects on the noobai checkpoint
despite `gender_negative`'s exclusion already applying — excluding a look
is not the same as asking for one.

**New this session**: the author reported a line addressed entirely in
second person ("you demon, you took what was mine!") got voiced with the
wrong gender. Root cause is structural: `voice/runner.py::slot_gender`'s
only signal, `gender_from_pronouns`, reads the narration *surrounding* a
line, and a purely second-person line states nothing grammatically about
its own speaker — no window size fixes that, because the signal it needs
isn't in the window at all, it's in the line itself.

Added `persona/traits.py::self_reference_gender`: matches this genre's own
"this `<gendered term>`" third-person self-reference convention ("this
king", "this humble maiden", "this old master") directly in the speaker's
own quoted text. Deliberately narrower than running the full
`_GENDER_TERMS`/`_honorific_signals` address-form table against arbitrary
dialogue text would be: a bare honorific inside a line is usually the
speaker addressing *someone else* ("Elder, please forgive this disciple"),
and the broader table would misattribute the addressee's gender to the
speaker. Verified this distinction holds before shipping it (test:
`test_honorific_addressing_someone_else_is_not_self_reference`). Wired
into `slot_gender` as the first check, ahead of the pronoun window — a
self-reference, when present, is more direct evidence than a majority
vote over nearby narration.

**Not verified against real RI text**: the author's exact quoted line
("you demon, you took my priority") does not appear verbatim anywhere in
chapters 1-29 of the stored text (checked directly) — likely a paraphrase
of a similar real line, or from later in the volume. The *mechanism* gap
this fix closes is real and general regardless (any purely second-person
line was structurally unresolvable by gender before this), but the
specific reported line has not been re-checked against the actual fix.
Worth doing once a chapter with real audio is re-rendered.

`uv run pytest packages/` passing throughout (682 at session start,
counted differently by the time Section 4.40+'s new test files landed — check
the live count with `uv run pytest packages/ --collect-only -q | tail -1`
rather than trusting a number quoted here, since this file does not keep
that count current across every session).

**Where render output stood at this section's start, still true**: the
last real SDXL/director run (4.42/4.43's session) died on a transient
Hugging Face Hub error loading `cagliostrolab/animagine-xl-4.0`, and a
separate run's CREMA-D voice bank loaded empty — both have dedicated fixes
already committed (`c57e4b4`, `1a289c3`, `dde0d91`) that this section's
work has not yet re-tested with an actual end-to-end render. **The next
concrete step is still: run a real chapter through the full chain
(direction -> images -> relevance audit -> CREMA-D narration -> motion ->
compose) with today's fixes in place, and actually look at the result** —
per 4.42's own standing instruction, look at the panels and listen to the
audio before trusting any metric.

### 4.45 One-panel-at-a-time verification finds a real director bug, then three prompt-engineering attempts fail to fix multi-subject composition, then solo framing works on the first try — the ceiling is now triple-confirmed, not just theorized *(2026-08-20)*

**Method change that mattered**: instead of another full-chapter render,
generated `ch1` block 0 alone, repeatedly, actually looking at each image
before changing anything. This is what caught a real bug the full-chapter
runs never isolated.

**Real bug found and fixed**: `render/direction.py`'s director (qwen2.5:7b
via ollama) wrote `"Fang Yuan stands resolute, flanked by armed warlords
and warrior women closing in."` for block 0 — **the LLM invented "warrior
women" that appear nowhere in the source text.** Not a checkpoint/prompt-
application bug like 4.42's count-tag issue; the fabrication happened
*before* the image model ever ran. Root cause: the SYSTEM prompt's "never
invent a person" rule is scoped to *named* individuals (the "Old bastard
Fang" example) and says nothing about inventing unnamed background
figures/groups. A 7B model given a thin or empty cast list padded the
scene with generic filler to make the description feel populated. Fixed:
added an explicit rule -- "never invent a background figure or group
either, named or not... an empty or sparse cast is real information, not
a gap to fill." Verified: regenerating block 0 with the fix produced
`"Fang Yuan, a man, stands resolute under the encroaching night,
surrounded by armed opponents"` -- no more fabricated women. Tests
passing.

**Three more real experiments after that, each one actually generated and
looked at, not assumed:**

1. Regenerated block 0 with the fixed prompt (`refined` engine): still a
   feminine-presenting central figure, and the scene composed as a calm,
   lantern-lit market conversation between smiling people -- nothing like
   "surrounded by armed opponents." The gender-fabrication bug was fixed;
   the underlying wrong-gender, wrong-mood *composition* was not.
2. Same block, `noobai` engine (the checkpoint 4.43 found genuinely better
   for single-character shots): worse on this scene specifically -- an
   even more clearly feminine figure in a serene temple-courtyard
   composition with a small girl companion, praying pose. Confirms 4.43's
   own finding held: the checkpoint swap helps single-subject shots and
   does not touch multi-subject composition.
3. Added an experimental `layout` field to `PanelDirection`
   (`render/direction.py`) -- the director now writes an explicit spatial
   sentence ("Fang Yuan alone at centre; three attackers surround him at
   the edges, left, right and behind") in addition to `action`, on the
   hypothesis that forcing concrete spatial commitment would help the
   image model more than loose prose. Verified the director produced
   exactly that sentence, correctly. **The generated image still failed**:
   still a feminine-presenting central figure, now surrounded by 5-6
   people who look like a friendly group photo, several smiling. Checked
   `.base.png` (the Animagine compose stage, before GuoFeng3's img2img
   repaint) directly: the wrong composition is already present at the
   *base* stage, unchanged by repaint -- the failure is Animagine XL's own
   prior for this style/prompt combination, not something happening
   downstream. **This experiment is a validated negative result, kept in
   code** (harmless when it doesn't help, and plausibly helps *other*
   scenes even though it didn't fix this one) **but not proof of concept
   for anything further along this path.**
4. Control test: hand-written prompt, forced solo framing ("1boy, solo,
   Fang Yuan, long black hair, cold narrow eyes, deep green robes torn to
   shreds, blood on his body... close-up... "), negative prompt excluding
   "2girls, crowd, group, extra people". **Worked on the first try**:
   correctly male, black hair, torn green robes, visible blood, defiant/
   injured expression, alone -- and it independently matches the actual
   prose ("deep green robes that had been torn to shreds... his entire
   body was covered in blood... his expression did not change, it was
   calm") that the director-composed multi-subject version never managed
   to honour either.

**Conclusion, now backed by four independent tests in one sitting rather
than one prior session's checkpoint bake-off alone**: multi-subject/crowd
composition on an 8 GB card's anime SDXL checkpoints is a real ceiling,
not a prompt-wording gap -- checkpoint swap (4.43), gender-tag fixes
(4.44), and explicit spatial layout (this section) were all tried in good
faith and all failed on the same scene, while solo framing succeeded
immediately and independently matched the source prose. This matches
4.42's own standing conclusion; it is no longer a hypothesis.

**Research done this session on the two real remaining levers, so the next
session doesn't have to re-derive it:**

- **ControlNet-openpose, SDXL-compatible versions exist**
  ([sdxl-controlnet-openpose](https://www.aimodels.fyi/models/replicate/sdxl-controlnet-openpose-lucataco),
  [ControlNet-Union-SDXL-1.0](https://crepal.ai/blog/controlnet-union-sdxl-1-0-free-image-generate-online/)
  supports openpose among 12 control types). **Real blocker**: openpose
  conditioning needs a *pose reference image* (a skeleton) to condition
  on, and this project has no pose references at all -- a text-only
  novel has no images to extract poses from. Would need either
  hand-authored skeletons per multi-subject panel (does not scale to 199
  chapters) or an LLM-to-layout-to-skeleton synthesis step, which is a
  real, novel piece of engineering, not a config change.
- **GLIGEN** (bounding-box/entity grounded diffusion,
  [paper](https://arxiv.org/abs/2301.07093),
  [project page](https://gligen.github.io/)): checked directly --
  `diffusers==0.39.0` (already installed) ships
  `StableDiffusionGLIGENPipeline`, but **only for SD1.5, not SDXL**. Using
  it as-is would mean dropping to SD1.5 for multi-subject panels, a real
  quality trade against the SDXL anime checkpoints already in use.
  SDXL-compatible GLIGEN-style approaches exist in the literature (HiCo-SDXL
  per the NeurIPS 2024 paper) but are not bundled, off-the-shelf
  `diffusers` pipelines -- would need real integration work.
- **DiffSensei** ([arXiv:2412.07589](https://arxiv.org/pdf/2412.07589)):
  a manga-specific framework built exactly for "precise character and
  dialog layout control" in panel generation -- the closest match to this
  project's actual use case in the literature found this session. Not
  evaluated hands-on (a separate model/framework, real integration
  project, not a drop-in). Worth a dedicated look next.
- **Story-visualization consistency literature** (StorySync, TemporalStory,
  Scene De-Contextualization -- search results in this session's history)
  mostly targets a *different* problem than the one blocking this
  project: keeping one character's identity consistent *across* several
  generated panels. This project already has a answer to that one
  (reference-sheet IP-Adapter conditioning, item 8/4.36). The open problem
  here is single-panel multi-subject composition fidelity, which none of
  these papers directly address.

**Concrete recommendation, not yet implemented**: bias panel/slot
selection toward **solo framing wherever the story allows it** -- most of
a scene's dramatic weight sits on one or two named characters anyway, and
that is exactly the class this pipeline can already render reliably.
Reserve true multi-subject "crowd surrounds the hero" moments for the
already-built `_crowd_slot` mechanism (`panels.py`) as a *separate,
lower-fidelity, explicitly-labelled category* rather than trying to fold
protagonist-plus-antagonists into one composition -- and treat a scoped,
budget-capped escalation to a paid API for *just* those specific
multi-subject panels (not a wholesale switch) as the more honest
"last resort" the project's own free-model policy already allows for,
ahead of building real ControlNet/GLIGEN infrastructure. Building the
pose-conditioning infrastructure remains the deeper, more capable fix,
but is real, scoped engineering work for a session that starts fresh on
it specifically, not a tonight fix.

`uv run pytest packages/` passing throughout.

### 4.46 Found and partly fixed a real double-injection bug; the remaining gap on RI ch1 block 0 is the checkpoint ceiling working as expected, not a new bug *(2026-08-20, same session as 4.45, continued)*

**A second real bug, found the same way as 4.45's**: `render/panels.py`'s
crowd-context injection (`if _chunk_mobs: ... "many people present: ...,
surrounding him"`) had no `is_crowd_cut` gate at all. A scene with a
detected mob got that clause stapled onto *every* slot's director prompt
in its chunk -- including the main/establishing slot, whose job is a solo
shot of the named subject, and whose own dedicated crowd cut
(`_crowd_slot`) already exists specifically to carry the crowd. The crowd
was being asserted twice, and the solo-capable slot never got a chance to
be solo. Fixed: the injection now only fires on the crowd slot itself, or
when no dedicated crowd slot exists for the scene at all; every other slot
in a mob scene now gets an explicit "draw only the named subject alone
here -- the surrounding crowd is a separate panel" instruction instead.

**Verified this fixed most of the scene, and did not fix block 0
specifically -- and that second part is correct, not a remaining bug.**
Re-ran RI ch1 blocks 0-17 (a real scene spanning the opening confrontation
through its aftermath) end to end. Checked the actual prompt cache (the
run timed out before the full image pass finished, so this is prompts,
not final pixels, for most of the range):

- **Blocks 5, 9, 13, 17 -- all clean, all correct.** `"1boy, male focus,
  Fang Yuan looks around... Fang Yuan alone at center; no one else in
  frame..."`, and similarly for the others. These are the scene's
  narration-only beats (Fang Yuan reflecting alone after the confrontation),
  and the fix produced exactly the right prompt for every one of them.
  This is the real, validated payoff of 4.45's finding: most of a scene's
  panels are single-subject moments this pipeline can now render reliably.
- **Block 0 -- still says "surrounded by attackers," unchanged by the new
  "draw only alone" instruction.** Checked why before assuming the fix
  failed: block 0 *is* the scene's actual confrontation-establishing beat
  -- four unnamed attackers are narratively present and threatening Fang
  Yuan at that exact moment, which is what the passage says. The director
  correctly refused to lie about the scene even when explicitly told to
  omit the crowd. **This is not a prompt bug**: the checkpoint's inability
  to render "one named man plus several unnamed attackers" correctly (4.45's
  triple-confirmed ceiling) is a real property of the moment being drawn,
  not something any instruction wording fixes. The honest fix for *this*
  specific beat is exactly what 4.45 already concluded: real spatial
  conditioning (ControlNet/GLIGEN), or accepting this specific class of
  panel renders at lower fidelity than the rest of the chapter.

**Net effect of 4.45+4.46 together**: the pipeline can now be trusted to
render the *majority* of a typical scene's panels (the single-subject
narration/reaction beats) reliably and correctly, and the *specific*
panels that genuinely require multiple people in one frame remain the
known, now precisely-scoped ceiling -- not "the pipeline is broken," but
"this one class of shot needs a lever this session did not build." That
is a materially better place to hand off from than "it's hallucinating a
lot" was at the start of this session's block-by-block work.

`uv run pytest packages/` passing.

### 4.47 Render rounds v38–v39: three code fixes shipped, three open defects identified, director "stands alone" collapse is the ceiling *(2026-08-21)*

**Context:** Five iterative render rounds targeting first 10 panels of RI ch1
with NoobAI XL 1.1. IP-Adapter reference conditioning permanently removed this
session (was causing colour bleeding across characters).

**Fixes shipped (all in the commit tagged 4.47):**

1. **Teal robe negative suppression** (`render/panels.py`): NoobAI has a
   strong teal/cyan prior for xianxia male characters. When "white robe"
   appears in the positive prompt, we now prepend
   `"teal clothing, cyan robe, blue-green robe, turquoise outfit"` at the
   front of the negative priority list. Verified v38 p004_b0005: robe
   shifted from teal to dark charcoal (partial — teal blocked, white not
   yet achieved).

2. **White robe positive reinforcement** (`render/direction.py`): v38
   produced dark charcoal instead of white when teal was suppressed
   (checkpoint's second preferred colour). Added standalone
   `"pure white outer robe"` term after the character appearance clause
   whenever `condense_clause()` yields "white robe". Applies from v39 onward.

3. **Score_9 tags before scene_locale** (`render/direction.py`): v37 had
   score_9 in only 5/24 prompts; v38 had 19/52. Root cause: score tags were
   appended after scene_locale and key_objects, so the 20-token character
   clause + 10-token locale exhausted the 75-token budget before quality tags
   were reached. Fixed by moving `"score_9, score_8_up, highly detailed,
   cinematic lighting"` immediately after the character appearance loop.

4. **Crowd female suppression priority** (`render/panels.py`): `_crowd_neg`
   female terms (`"girl, girls, female, woman, women, bishoujo"`) were placed
   last in `_neg_parts` and were being trimmed by `fit_to_budget()` before
   they were ever applied (gender_neg=6 tokens + base_neg=69 tokens = 75,
   no budget left). Moved crowd female terms before base_neg. Crowd gore
   terms (`blood, muscular, bare chest`…) remain at end as lowest priority.

**Open defects (not fixed, prioritised):**

1. **Director collapses to solo panels** — 36/52 prompts in v39 contain
   "stands alone; no one else is present." The director's SYSTEM prompt rules
   ("NEVER invent people," "ONLY describe what the passage shows") are being
   over-applied: even beats that clearly place multiple people in scene get
   solo layouts. The Awakening Ceremony (500+ clan members watching) renders
   as "no one else is present." This is the dominant quality ceiling — scene
   content is correct, composition is not. Candidate fixes: (a) tighter
   layout validation that cross-checks `action` vs `layout` for obvious
   contradictions; (b) a separate director re-query when layout says "alone"
   but action names multiple people; (c) revert to mechanical assembler for
   group beats and keep director only for solo narration.

2. **Crowd panels feel allied not hostile** — when crowds do render via the
   `:crowd` slot, they look supportive (facing Fang Yuan symmetrically). The
   prompt says "enemies ring him on all sides" but the checkpoint's guofeng
   prior defaults to harmonious group arrangements. Needs explicit
   adversarial composition vocabulary ("backs half-turned, weapons raised,
   closing in") — but this is a diffusion prior problem, not a prompt
   wording problem, and v38/v39 iterations confirm wording changes don't move
   this.

3. **Background changes every panel within same scene** — `scene_locale` is
   re-derived per panel from a keyword lookup. Director picks different
   settings per beat even within one continuous scene. Eight consecutive
   Awakening Ceremony panels render as eight different locations. Fix:
   lock `scene_locale` for the duration of an `ActiveScene` span rather than
   re-deriving per panel.

**v39 prompt cache stats (52 entries):**
- score_9 present: 36/52 (up from 5/24 in v37)
- white robe panels: 13/52
- "stands alone / no one else": 36/52
- crowd variants: 7 separate `:crowd` slots

**What worked and shouldn't be undone:** guofeng/xianxia aesthetic is solid
across all panels; Fang Yuan face consistency is good; score_9 fix is real.
The ceiling is composition (solo collapse + crowd directionality), not style.

### 4.48 Root cause confirmed: prompt token order defeats style anchor; all three visual defects now precisely scoped for ideation *(2026-08-21)*

User confirmed v39 panels look like anime portraits with no Chinese vibe,
inconsistent clothing, and irrelevant crowds. This session ends here; the
three defects below are ready to ideate on with a fresh Claude session (web
or otherwise) without needing to read any code.

**Root cause 1 — `1boy, male focus` before STYLE_ANCHOR kills the Chinese aesthetic**

Every solo panel prompt starts: `1boy, male focus, guofeng illustration,
chinese ink painting, xianxia, ...`

CLIP weights earlier tokens more strongly. `1boy, male focus` are danbooru
portrait triggers that activate anime-portrait mode before the style anchor
fires. By the time `guofeng illustration, chinese ink painting, xianxia`
is read, the portrait prior is already dominant. The style anchor should be
token positions 0–2, not positions 2–4.

Fix candidate: move `STYLE_ANCHOR` before cast headcount tags, or drop
`1boy, male focus` entirely (NoobAI XL's xianxia weights are sufficient to
infer male/single-figure from `guofeng illustration` alone).

**Root cause 2 — Director LLM over-applies "never invent people" rule, collapses group scenes**

36/52 v39 prompts contain "stands alone; no one else is present." SYSTEM
prompt rules ("NEVER invent people," "ONLY describe what the passage shows")
are being over-applied: even the Awakening Ceremony scene (500+ clan members
explicitly in the text) gets solo layout. The director treats "don't invent"
as "erase everyone not named individually."

The `layout` field is supposed to force spatial commitment but currently
echoes the same solo framing as `action`. A layout that says "Fang Yuan stands
alone" when `action` says "everyone is wary of Fang Yuan" is internally
contradictory — but no validation catches it.

Fix candidates: (a) post-generation cross-check: if `action` mentions third
parties but `layout` says "alone", re-query or inject a crowd count; (b)
change the rule from "never invent" to "use the passage's headcount — if it
names a group, you must represent it, even if individuals are unnamed";
(c) for known group beats (mob detected by `detect_mobs`), bypass the director
entirely and use the mechanical assembler with crowd vocabulary.

**Root cause 3 — scene_locale re-derived per panel, background drifts every beat**

`scene_locale` is a keyword-lookup run on each beat's text independently.
The Awakening Ceremony spans ~15 beats in the same physical space; each beat
has slightly different vocabulary so the lookup returns different location
strings: "stone courtyard," "timber clan hall," "terraced hillside village,"
"moonlit courtyard at night." Eight consecutive panels of the same ceremony
render as eight different locations.

Fix: lock `scene_locale` for the entire `ActiveScene` span on first
derivation; only update it when the scene boundary changes.

**What was working and must not be undone:**
- Guofeng ink-painting texture is present (when style anchor isn't clobbered)
- Fang Yuan face is consistent across panels
- score_9/score_8_up quality tags now in 36/52 prompts (up from 5/24 in v37)
- Teal robe prior is suppressed (panels show charcoal, not teal — step toward white)
- Director hallucination guards (warrior-women sanitizer, layout placeholder validator) work

**Prompt for ideation with a fresh Claude session:**

```
I'm building a xianxia manhwa adaptation pipeline for "Reverend Insanity" using
NoobAI XL 1.1 (SDXL checkpoint). An LLM art-director reads story beats and
produces PanelDirection JSON (action, layout, setting, lighting, mood, key_objects),
which gets assembled into a CLIP prompt with a 77-token budget.

Three bugs, in priority order:

1. TOKEN ORDER: Every prompt starts "1boy, male focus, guofeng illustration,
   chinese ink painting, xianxia, ..." — the danbooru portrait tags (1boy,
   male focus) come before the style anchor and clobber it, producing generic
   anime portraits instead of Chinese guofeng paintings. How should I reorder
   these, and should I drop 1boy/male focus entirely given NoobAI's xianxia
   weights?

2. DIRECTOR SOLO COLLAPSE: The LLM director has a rule "NEVER invent people —
   only describe what the passage explicitly shows." It's over-applying this
   to collapse group scenes (500-person Awakening Ceremony → "Fang Yuan stands
   alone; no one else is present"). The layout field is supposed to force
   spatial commitment but echoes the solo framing. How do I fix the rule
   wording or add a post-generation validation pass so group beats actually
   render as groups?

3. BACKGROUND DRIFT: scene_locale (location vocabulary) is re-derived per
   beat from a keyword lookup on the beat's text. Same scene, 15 different
   beats → 15 different location strings → 15 different backgrounds. Should
   I lock it per ActiveScene span, and how should the lock interact with
   genuine scene changes mid-chapter?

Constraint: NoobAI XL 1.1 only, no multi-model. 77 CLIP token budget.
LLM director runs on ollama (qwen2.5:7b locally). No paid APIs.
```

### 4.49 Appearance-extraction contamination fixed and verified live; render round v40 finds the director inventing named characters, not just erasing them *(2026-08-22)*

**Context.** A second session (this one) ran the appearance-extraction fixes
that "green robes on 16/16 characters" and the CLI/gold-set findings called
for, then ran a real render (v40, ch1, NoobAI XL, 48 panels) to check whether
any of it actually reaches a panel. It does — and it also surfaces a defect
worse than 4.48's solo-collapse: the director inventing a *specific named
character* who is not in the chapter at all.

**Fixes shipped and verified against the real 199-chapter corpus, live, with
qwen2.5:7b (not a mock):**

1. **Grounding requires proximity, not co-occurrence** (`resolve/appearance_extract.py::is_grounded`/`attesting_chapter`/`_grounded`).
   The old check asked "does this word appear anywhere in the 60 pooled
   passages" — true for "green" describing a *bystander's* eyes two
   sentences from Bai Ning Bing's name, which is how he ended up with
   `typical_attire="green robes"` despite the text calling him
   white-clothed. Now a distinguishing word must sit within 40 chars of
   the target's own surface form (or the model's citation must be near
   the target's name — see next item).

2. **Citation-forced extraction prompt.** The model must now return
   `{"value": ..., "source": "<exact quoted sentence>"}` per attribute.
   Two checks before anything reaches the store: the quote must be a real
   (whitespace-normalized) substring of the passages sent to the model,
   and the target's surface form must sit within 60 chars of that quote.
   Both discards are counted by reason on the report
   (`missing_source`/`source_not_in_passages`/`target_not_near_source`).

3. **Chapter-scoped `appearance_of(..., position=...)`** so a panel at
   chapter 5 can't pick up an attribute only attested at chapter 100.
   Reference-sheet generation stays unscoped (a sheet is deliberately the
   whole-history canonical look); panel-time reads pass `position`.

4. **CLI `query attributes --kind PERSONA` no longer hides body2** — it
   iterates `bodies_of()` and prints one block per body instead of
   hardcoding `:body1`.

**Verified, not asserted:** purged all appearance attributes from a scratch
copy of `data/reruns/reverend-insanity.db` and re-ran extraction clean.
Result: **0 `typical_attire` values anywhere in the corpus** (down from
16/16 "green robes" pre-fix) — every attempt the model made at attire was
either correctly grounded to something non-green or correctly discarded by
the citation checks. Bai Ning Bing specifically: no `typical_attire`,
correct `hair_color="white"` and `distinguishing_features="white hair and
white clothes"` at ch189, both citation-verified. This scratch-copy result
has **not** been applied to the real `data/reruns/reverend-insanity.db` —
that purge-and-re-extract is a one-time bulk `DELETE` the harness's
auto-mode classifier would not approve unattended, so the real file still
carries the pre-fix contaminated rows until someone runs it deliberately
with a human present.

**Gold set (`data/gold/reverend-insanity.jsonl`, 3,457 rows, 100%
`confirmed=True` despite `eval/draft.py` defaulting new rows to `False`):**
this is a **prior session's** bulk glance-review by the project owner
(2026-08-12 per that session's own note), not an auto-flip script and not
a row-by-row human pass. Calibration built on it should say so.

**`get_panel_cast` now also resolves narrator reveals** (`resolve/detect_reveals.py`,
new this session): a block whose only mention is a placeholder ("the
stranger") but which the narrator reveals in the same block ("this was
none other than X") now adds X to the foreground cast. Additive only —
verified with a same-block positive case and a different-block negative
case so it can't leak a reveal into the wrong block.

**New bug found by actually running v40, unrelated to any of the above:**

`render_panels()` takes `max_panels: int = 14` and `commands.py` wires
`--max-panels` straight to it — but grep the whole function body and the
parameter is **never read again**. No slice, no cap, no early exit. `--max-panels
5` on ch1 produced 48 panels, twice, in two independent runs. The docstring
("the cost is set by `max_panels`, not by chapter length") describes intent
that was apparently never implemented, or was implemented once and lost in
a later edit. Anyone budgeting GPU time off this flag today is not getting
what they asked for.

**New visual defect, distinct from 4.48's "director erases everyone":** on
v40's ch1 render, three panel slots (p022/p023/p024, all covering the same
beat: *"The elders' faces show worry"* — no named subject, no PRESENT
mention, no fallback mention, nothing in `mention` or `resolution_event`
placing anyone there) came back with the director's own text reading
`"Bai Ning Bing stands alone; no one else is present."` Checked directly
against the store: **`self55` (Bai Ning Bing) has zero mentions and zero
resolution events anywhere before chapter 108** — he is not introduced for
another 107 chapters. Nothing in the resolved cast, the appearance
pipeline, or the reveal detector above could have produced this name; the
`cast` dict `direct_beat()` was called with for this beat was built from
`present_beat_entities`/the PRESENT-fallback over chapter-1-only mentions
(`store.get_mentions(novel_id, chapter_number)`, correctly chapter-scoped —
checked), and neither path had anything to contribute for this beat. The
only remaining source is the director LLM itself inventing the name from
its own pretrained knowledge of the novel's cast list, not from anything in
`cast` or the beat text.

This is a different, worse failure mode than 4.48's "over-applies never
invent people, collapses to solo": here the model *does* invent a person,
specifically a real named character who is textually and chronologically
impossible in this scene. And because "Bai Ning Bing" was never routed
through `character_looks()` (he's not in `appearances`), his entry never
reached the `genders` list either — so `direction.py`'s own rule 2
("anything unstated is drawn female by default") applied to him, and the
checkpoint rendered a woman. Bai Ning Bing is canonically male. **The
"there's a woman in chapter 1 and there shouldn't be" complaint and the
"it's just Fang Yuan in every panel" complaint are two sides of the same
gap**: when a beat names no one, the director should either draw the scene
alone (correct, and what most of v40's scenery-only beats already do —
p014/p015/p016/p039/p042 all correctly render "no one present") or default
to whoever the *scene* is actually about — not reach for an unrelated named
character from later in the book. The SYSTEM prompt's rule 5 ("use the
character's actual name, not a placeholder — write 'Fang Yuan stands alone'
not 'X stands alone'") was written with Fang Yuan as the illustrative
example and has no explicit constraint limiting names to the `cast` dict
actually passed in; the model appears to have generalized "name a real
character" without "...from the ones you were given."

**Fix candidate (not yet implemented — flagged for next session, matches
4.48's ideation framing):** either (a) validate `PanelDirection.action`/`layout`
post-hoc against the `cast` dict's keys and strip/reject any proper name not
present in it or in the beat text, or (b) tighten SYSTEM rule 5 to state
explicitly: "Only name characters that appear in the cast list below or are
named in the passage itself. If the passage names no one, do not introduce
anyone — describe the scene alone or by role ('an elder'), never invent a
specific character from elsewhere in the novel."

**Net effect:** the appearance-extraction contamination this session set
out to fix is fixed and proven, live, at the source. It does not fix, and
was never going to fix, the separate director-hallucination defect family
4.48 already opened — v40 just found a second, more specific member of that
family than the one already on file.

### 4.50 4.49's fix candidate shipped, three real bugs found in the uncommitted draft, and verified clean against a real ch1 render *(2026-08-23)*

**Context.** 4.49 flagged both fix candidates as "not yet implemented." A
third session found both already half-written and sitting uncommitted in
the working tree — `direction.py`'s SYSTEM rule 5 already restricted to the
`CAST` list, and a `_validate_character_names` guardrail already existed.
Neither had ever been run: `panels.py` never passed `store` into
`direct_beat`, so the guardrail's `if store and novel_id` guard was always
false. Reading the guardrail itself found it would have crashed immediately
if it had run:

- `store.iter_entities(novel_id)` — no such method (`Store` only has
  `all_selves`).
- `entity.entity_id` — the `Self` model's field is `id`, not `entity_id`.
- `gazetteer.add(label, alias_type="CAST", ...)` — `alias_type` must be an
  `AliasType` enum member; a plain string crashes the first time `add()`
  reads `alias_type.enters_graph`.
- `gazetteer.scan(...)` — no such method (`Gazetteer.find`).
- The `cast` dict is `{name: appearance_clause}` (`build_prompt`'s own
  docstring), not `{entity_id: name}` — the draft's `for entity_id, label
  in cast.items()` had the two swapped, so even with the above fixed the
  registered alias would have been an appearance-description sentence, not
  a name, and would never match anything in the director's prose.
- The spec's case 3 ("name not in the entity table at all → fabricated")
  cannot be produced by gazetteer lookup alone — a gazetteer only matches
  names it already knows, so it can never surface a name it doesn't know.
  Added a second pass using `mentions/ner.py`'s `HeuristicDetector` (the
  same offline capitalised-name detector the mention pipeline uses) over
  the director's own text; anything it flags that isn't in the cast or the
  entity table is genuinely invented.

Fixed all of the above, wired `store` through the `direct_beat` call site,
and added `packages/pipeline/tests/test_direction.py` (4 cases: cast member
kept, out-of-scene known character stripped, fabricated name stripped,
validation skipped cleanly with no store).

**Two more real bugs found from the first live run, not from reasoning
about the code:** the heuristic detector's regex captures a trailing
possessive as part of the span, so "Fang Yuan's" (a real cast member,
correctly named) was being flagged and stripped as fabricated. And
"Everyone" / "Someone" — indefinite pronouns, not names — were being
flagged the same way. Fixed by stripping a trailing `'s`/`'s` before the
cast/entity-table comparison, and adding `Everyone`, `Everybody`, `Someone`,
`Somebody`, `Anyone`, `Anybody`, `None` to `mentions/ner.py`'s shared
`_STOPWORDS` list (a repo-wide improvement, not local to this call site —
none of those words is ever a valid character name in this corpus).

**Verified against a real render, not just unit tests.** Ran
`echotales render --novel reverend-insanity --chapters 1 --max-panels 5
--image-engine stub` against the `data/reruns/reverend-insanity.db` scratch
copy 4.49 already fixed extraction on, through the real two-phase
direction pass (ollama, qwen2.5:7b) end to end. Output archived at
`data/RI/panels/ch1/v41_stub-director-validation/` (panels, manifest,
prompt cache, run log) — named out of the plain `vN` sequence deliberately:
`--image-engine stub` writes solid-colour placeholders, not a real render,
so it would misrepresent v1-v40's actual image-engine history to sit among
them unlabelled. 21 panels produced for chapter 1 (max-panels caps the 5
scenes generated, not raw panel count —
see below). Zero occurrences of "Bai Ning Bing" anywhere in the run log or
the 21 cached final prompts (checked directly against
`prompt_cache_v1.json`, not just the log); "Fang Yuan" — the real chapter 1
protagonist — appears in 13/21. Fifteen names were caught and stripped by
the validator across the run: 8 were locations/factions the director
misnamed as characters ("Qing Mao Mountain" x2, "Gu Yue Village" x2, "Gu Yue
clan" x4 — all real entities, correctly rejected as non-person), 7 were
genuinely fabricated words with no entity-table match at all ("Gu Yue" x4 —
a clan-name fragment, not the clan's own registered surface form; "Spring",
"Heads", "People"). None were a specific invented *named individual* the way
Bai Ning Bing was in 4.49 — the worst the director did this run was
misname a location as a person, which the validator's non-person branch
catches correctly. Both the false-positive fixes above were verified by
their absence in this second run: the first run (launched before the
possessive/pronoun fix) showed "Fang Yuan's" and "Someone"/"Everyone" being
wrongly stripped; the second, identical run with the fix in place showed
neither.

Eighteen distinct director (LLM) calls fired this run (18 distinct
beat-hashes in the prompt cache); the 15 strips above landed across that
set, so the raw name-error rate this beat structure produced is roughly
15/18 calls touched at least one wrong name before the validator ran — the
prompt constraint alone (rule 5) is visibly not holding on every call, which
is exactly the case for the validator being load-bearing rather than
defensive redundancy. No 1girl/female tag and no invented gendered figure
appeared anywhere in the 21 final prompts for an empty-cast beat — but the
model also never produced the literal "silhouette"/"back-turned" vocabulary
rule 6 suggests; empty-cast beats instead read "No one is present" / "a
figure ... ; no one else is present" (partly the director's own phrasing,
partly the strip mechanism's `"a figure"` substitution). The outcome rule 6
is meant to prevent — a specific gendered person invented for an unstated
figure — did not happen in this run, but not via the exact mechanism
specified; worth re-checking on a larger sample before calling the wording
itself correct.

**Fix C, also already present in the uncommitted draft and verified
correct:** `render_panels()` now slices `scenes[:max_panels]` (4.49 found
this parameter was read but never acted on — confirmed by the missing
slice, not by grep alone). Caps *scenes*, not raw panel count — a scene's
image budget (1-3) and crowd-cut logic can still produce several panels per
scene, which is why `--max-panels 5` above produced 21 panels, not 5.
Verified directly against `group_scenes` output for this chapter: ch1 has
14 scenes over 92 blocks, and scene 5 (0-indexed `scenes[4]`) ends at block
46; the `--max-panels 5` run's highest cached block index was 46 — the cap
engaged exactly at the 5th-scene boundary, not partway through it and not
at the chapter's real end (block 85, scene 14). Without the cap this
matches 4.49's report of `--max-panels 5` on ch1 producing 48 panels twice
(all 14 scenes, ignoring the flag). This is a scene cap, not a literal
panel-count cap — if a literal panel-count cap is wanted later, that's a
different, larger change (truncating mid-scene rather than dropping whole
scenes), not a bug in this fix.

**Net effect:** 4.49's flagged defect (a real, out-of-scene named character
appearing in chapter 1) is fixed and verified absent under the same
scratch-db/render conditions that found it. The fix that shipped was not
the one 4.49 described in prose — it was a mostly-complete but never-run
draft with real bugs in it, which is itself worth naming as a pattern: an
uncommitted change that "looks done" in a diff is not verified until it has
actually executed once.

### 4.51 Appearance-precedence fix shipped for RI ch1 blocks 5/9/13 (canon attire silently overriding a beat's own narration) — text-level bug fixed and verified, visual goal still not met *(2026-08-26)*

**The bug.** `character_looks()` in `render/panels.py` restated the
character's static wiki-canon appearance clause
(`data/RI/canon/wiki-appearance.json`'s `typical_attire: "white robes"`)
unconditionally on every panel, even when the block's own narration
described a contradicting transient physical state. RI ch1 blocks 5, 9 and
13 read "deep green robes... torn to shreds," "covered in blood," and
"disheveled hair" respectively, but every prompt through v43 asserted
pristine white robes regardless — canon was overriding the scene.

**The fix.** `character_looks()` now returns a 5-tuple (`label, clause,
sheet, gender, condition`) instead of 4: `clause` is identity-only
(hair/eyes/build, never overridden by scene state), `condition` is a
separate attire/transient-state string built by
`apply_transient_overrides()` from the block's own narration when it
states a conflicting physical state, falling back to canon attire
otherwise, capped at 10 tokens via `fit_to_budget`. `apply_transient_overrides()`
no longer folds "disheveled hair" into `hair_style` (that had been leaking
a transient signal into the supposedly-permanent identity clause) — it now
goes into `current_condition` with the other transient signals.
`direction.py`'s `Direction` gained a `conditions: dict[str, str]` field
threaded through `direct_beat()`; `to_image_prompt_parts()` appends
identity and condition as two independent list entries so `fit_to_budget`
can drop one without the other, and the `framing` phrase (wide/medium/
close) was shortened from a full clause to 2-3 tokens after measuring that
giving it a full sentence — on top of the newly added `conditions` entry —
starved identity of budget.

**A real regression, caught before shipping, not by the agent that caused
it.** An interrupted subagent session (hit its account session limit
mid-task) left half-applied code in the working tree that merged the
transient override into the *same* string as hair/eyes/build. That single
oversized string got dropped whole by `fit_to_budget` under budget
pressure, losing the character's identity entirely on 3/3 test panels —
worse than the original bug (canon-only wrong attire) it was meant to fix.
Found by direct inspection of the cached prompts before shipping; the
subagent's own work was never run against a real render. That broken
intermediate output briefly occupied the `v44`/`v45` slot and was deleted.

**What actually shipped, verified against a real NoobAI render**
(`--block-range 0-15 --max-panels 2`, `data/RI/panels/ch1/v44_appearance-precedence-fix/`):
identity clause present in 6/6 real panels (was 0/3 in the broken
intermediate build); all 6 final prompts measured under 77 tokens with the
real CLIP tokenizer (one panel had measured 80/77 pre-fix). The condition
override is genuinely best-effort under CLIP's 77-token budget: it
survived in 1/3 target panels (block 13, "gravely wounded") and was
dropped in 2/3 (blocks 5, 9) when the director's own action/layout text
for that beat left no remaining room.

**Verdict — do not read this as resolved.** Looked at as images, not
prompts: blocks 5, 9 and 13 still render as near-identical clean,
undamaged portraits — same pose, same pristine robes, no visible blood or
tears in any of the three, *including* block 13 whose prompt does contain
"gravely wounded." The prompt-composition bug (canon silently overriding
local narration) is real and is now correctly fixed at the text level, but
two things stand between the fixed text and the fixed image: the 77-token
budget means the override text often doesn't survive into the final prompt
at all, and even the one panel where it did survive shows the checkpoint
not treating "wounded" as a strong enough visual cue against its own
training bias toward clean formal robes. Fixing the prompt was necessary
but not sufficient. Next thread (not started this session): either free
more budget specifically for the condition clause, or find a
stronger/differently-weighted cue for visible damage on this checkpoint —
a dedicated negative-prompt term against "clean robes," or testing whether
Danbooru-style damage tags outperform plain English the way `1boy`
outperforms "male" for headcount. Full before/after narrative and file
paths: `data/RI/panels/ch1/VERSIONS.md`, `v44_appearance-precedence-fix`.


### 4.52 SceneState built (core model + render wiring), Section 0 audit corrected mid-session (v51 is real, not v44), permanent-injury tracking added and caught its own false positive live — but the v52 verification render surfaced a more serious, unexplained bug and was stopped before completion *(2026-08-29)*

**Context.** A large scoped task: audit resource utilization across the
pipeline (Section 0), populate whatever the audit found empty (Section 0.5),
build a `SceneState` core model for scene-level location/crowd/condition
tracking (Sections 1-2), extend body-transition tracking to permanent
injury (Section 3), fix two render defects plus one newly-found one
(Section 4), then re-render and pixel-review chapter 1 (Section 5). Sections
0-4 completed; Section 5 stopped early on a serious new finding — see below.

**Section 0 audit — real numbers, and one self-correction worth recording.**
`attribute`: 0 rows. `self_persona_binding`: 0 rows. Both on the canonical
`data/webview-working/reverend-insanity.db`, despite `chapter`/`span`
covering the full 199 chapters. Gazetteer, `WORLD_CONTEXT`,
`eligible_prominence()` all wired live. Conformal calibration: class
constructed in `resolve/runner.py` but `.calibrate()` never called in
production — always running the uncalibrated fallback. Gold set: all
3,457 rows still `confirmed=True` from a prior bulk glance-review, not a
row-by-row human pass — unresolved, unrelated to this session's work.

**Self-correction, recorded because it should not happen twice:** an early
pass in this session concluded "v51" and "block 75" didn't exist in this
repo, reasoning only from `git log`/reflog/stash — but render output is
deliberately gitignored (`cf2c84e`), so absence from git history proves
nothing about the actual `data/RI/panels/` directory. A real pixel check
against the files on disk found v51 is real (48 panels, most recent render
at the time, 2026-08-27) and block 75 has a genuine, reproducible defect.
**Lesson for the next session: check the actual output directory before
concluding a version or defect doesn't exist — git history only covers
source, this repo's render output is never committed.**

**Section 0.5 — extraction run, real numbers.** Ran `appearance` (chapters
1-199) then `persona` build (`build_personas`) against the canonical DB.
`attribute`: 0 → 528 rows. `self_persona_binding`: 0 → 83 rows.
**One** body-transition event detected across the full volume: Fang Yuan's
own regression (ch1). No other body-transition-eligible events found in
this pass — stated plainly per the non-negotiable against inflating
findings.

**Sections 1-2 — `SceneState`.** New model in
`packages/core/src/echotales/core/models.py` (`SceneState`: `location`,
`crowd_mood`, `default_severity`, all opaque consumer-defined tags, per
non-negotiable #4 — this model does not invent genre vocabulary), new
`scene_state` table in `store.py` (`SCHEMA_VERSION` bumped 1→2), new
`render/scene_state.py` deriving it from the exact same `scene_locale`/
`detect_mobs` calls `panels.py` already made per scene (this *is* Section
4.48 root cause 3's own recommended fix: lock `scene_locale` once per
`ActiveScene` span, now literally persisted instead of recomputed).
Wired into `panels.py`: location floor, crowd-mood floor (feeds 4.1),
condition floor (feeds `apply_transient_overrides` via a new
`floor_severity` parameter, populating the tier-1 condition slot even on
beats whose own text says nothing). Net budget impact: zero new prompt
parts — routes through slots that already existed. Full test coverage:
`packages/core/tests/test_scenestate.py`,
`packages/pipeline/tests/test_scene_state.py`.

**Section 3 — permanent injury, and a live false positive it's worth
recording.** New `is_permanent_injury_phrasing()`/
`find_permanent_injury_candidates()`/`detect_permanent_injuries()` in
`persona/split.py`, scoped to PRINCIPAL/RECURRING only, fed into the exact
same `epochs_for`/`write_epochs` call `build.py` already makes for
regression (no parallel body-creation path). **First real run against the
full DB minted a second body for Shen Cui** on the passage "Shen Cui vowed
she would never forget his eyes for the rest of her life" — a figure of
speech about memory, matched by an overly generic
`"for the rest of (his|her|their) life"` pattern. Removed rather than
patched around; the remaining patterns are specific enough not to need it.
Re-ran `build_personas` after the fix: back to the correct 1 body-transition
count (Fang Yuan only). **This is exactly the kind of finding the
"verified, not asserted" convention exists to catch — the synthetic unit
test alone would never have found it; only the real DB run did.**

**Section 4.1 — crowd/layout contradiction, extended.** New
`_layout_contradicts_crowd()`/`_rewrite_layout_for_crowd()` in
`direction.py`'s `_validate_direction()`, using `SceneState.crowd_mood` as
ground truth (chosen over bypassing the director entirely, to keep its
real per-beat content on non-contradicted beats). Also added
`_layout_invents_second_subject()` for the inverse case found in this
session's own pixel audit (see below) — logged only, not auto-corrected,
since there's no single correct rewrite for an invented figure.

**Section 4.2 — verified, not regressed.** `get_panel_cast`'s
`block_window` scoping (Section 4.41's fix) confirmed still panel-local,
not scene- or segment-wide.

**Section 4.4 — a fresh pixel audit found two real, previously-undiagnosed
defects, both root-caused and fixed at the code level.** Against the actual
v51 output (not v44, per the correction above): (1) `conditioned_on:
["curated"]` was being written into 39/84 manifest rows for panels that
received **no actual conditioning** — `panels.py`'s `engine.generate()`
call has been hard-coded `reference_images=[], reference_weight=0.0` since
Section 4.47's deliberate IP-Adapter removal, and the tagging code above it
was never updated to match. Fixed by no longer setting the tag when no
conditioning happens; re-wiring real conditioning was explicitly not
attempted (4.47's removal was for a measured cross-novel-generalization
reason). (2) Block 75 ("the clan head looked out of the window") rendered
with **zero people** in v51 — root-caused to the subject having no tracked
persona/reference sheet, so the only human-presence content was a
generic `"a figure, solo"` filler stuck in `direction.py`'s lowest-priority
tier-3 clause behind setting/lighting tags. Fixed by promoting an untracked
figure's presence marker into tier 1 when no cast member resolves.

**Section 5 — stopped early on a serious new finding, not completed.**
Launched a real re-render of RI ch1 (`data/RI/panels/ch1/v52_scenestate-and-crowd-fix/`,
NoobAI XL, real GPU diffusion) to verify all of the above against actual
pixels. **Stopped by explicit user instruction after 3 of 48 panels, on
sight of the crowd panel (block 0) looking identical to v51's.** A file
hash check confirmed it precisely: **`p003_b0000_crowd.png` is
byte-for-byte identical between v51 and v52** (same md5), despite (a) a
demonstrably different final cached prompt string between the two runs
(v51: `"ancient china, xianxia, wuxia, hanfu robes, crowd of chinese
cultivators..."`; v52: `"crowd, multiple people, 6+boys, guofeng
illustration, chinese ink painting, xianxia, wide shot..."` — no shared
prefix at all) and (b) the v52 file being a genuinely freshly-generated
file (different inode, today's mtime), not a disk-cache hit
(`image_path.exists()` skip was checked and ruled out). Both runs use the
same fixed default `--seed 20260812`, so a same-seed, same-checkpoint,
genuinely-different-prompt pair produced identical output. **This should
not happen under normal diffusion sampling and was not investigated
further per the user's stop instruction** — the two other generated panels
in this run (p001, p002) did differ from v51's versions, so this is not a
blanket "nothing regenerates" bug, but something specific to at least this
crowd-slot code path (or a coincidence improbable enough to warrant
dedicated investigation before trusting it). **Flagging this as the
highest-priority open item for the next session, ahead of any further
SceneState/crowd-fix verification work** — until it's explained, no claim
that Sections 1-4's fixes changed anything at the pixel level can be made,
even though they are unit-tested and the code changes are real.

**What this session leaves in a genuinely uncertain state, stated
plainly:** Sections 0.5-4 are code-complete, reviewed against real data
where real data existed, and covered by passing unit/integration tests
(`packages/pipeline/tests/` + `packages/core/tests/`, full suite green
throughout). **None of it has been verified as visually effective** — the
one re-render attempt that could have shown that surfaced a more
fundamental, unexplained rendering anomaly instead and was stopped before
producing enough panels to check. Do not report the crowd-template,
block-75, or invented-figure fixes as "fixed" until (a) the byte-identical-
output anomaly above is root-caused, and (b) a full 48-panel re-render is
actually reviewed pixel-by-pixel.

**Still open, unrelated to this session's work, restated so it doesn't
get lost:** conformal calibration never run in production; gold set still
bulk-confirmed, not row-reviewed; v44's own open finding (condition clause
survives CLIP's 77-token budget in only 1/3 target panels, and even then
the checkpoint under-responds to "wounded") is not addressed by this
session's `floor_severity` wiring, which only guarantees the slot is
*populated*, not that it survives budget or renders visibly.

**Follow-up, same session: the byte-identical crowd panel is root-caused
and fixed, verified at small scale.** Per the user's own 5-step diagnostic
(isolated seed test, then a code trace), the cause was not the diffusion
engine or the cache — `panels.py`'s `is_crowd_cut` branch unconditionally
overwrote the correctly-computed, `SceneState`-aware prompt with a fully
static hardcoded template, so every crowd cut rendered the same ceremony-
hall image regardless of what the scene actually was. Rewritten to build
from `directed.direction.layout` and `SceneState.crowd_mood`/`location`
instead (`hostile_confrontation_modifier()`, new in `persona/attire.py`,
supplies the siege-vs-ceremony atmosphere clause). Re-rendered
`--block-range 0-8 --max-panels 3` (`data/RI/panels/ch1/v53_crowd-fix-test/`):
the crowd panel is now byte-different from every prior version and shows a
crowd, hostile framing, and the mountain locale together in one prompt.

**Same pass also found and fixed a real fourth instance of the
"front-loading fix built, never reaches this specific path" pattern —
except this one wasn't that.** `cast_tags()`'s silhouette fallback (the
genuinely gender-unresolved, pronoun-free case, `persona/prompt.py:452-458`)
*was* already correctly front-loaded (`"silhouette, back_turned, faceless"`
sits at position 0 of the assembled prompt, per the existing headcount-
first ordering rule) — so the routing itself was fine. The actual bug was
narrower: that one branch never asserted an explicit `solo` tag the way its
two sibling branches (`["1boy", ..., "solo"]` / `["1girl", "solo"]`) both
do, so the only `solo` in the final prompt came from the *layout* tail text,
past the budget's effective priority. Added `"solo"` to that branch's tag
list. Re-render confirms the invented-second-figure defect is gone on this
panel (`p001_b0000.png` in the same test dir): exactly one silhouette now,
where the same seed/prompt shape previously rendered two.

**Cross-reference, not yet fixed:** that same corrected panel still defaults
to a feminine-coded silhouette (visible hair, gown) despite carrying zero
gender signal — the identical bias the pronoun-based `gender_negative`/
`cast_tags` backstop (commit `088a3b3`, HANDOFF §4.x "gender-default
backstop") was built to correct for the *resolved*-pronoun case. The
backstop has no equivalent assertion for the fully-unresolved silhouette
case (there is no gender to assert against). Worth a positive fix (e.g. an
explicit `androgynous`/no-gender-cue tag) next time this path is touched,
rather than being rediscovered as a fresh bug.

**All three fixes (is_crowd_cut rewrite, `hostile_confrontation_modifier`,
solo-tag front-load) confirmed together, not just individually:** one more
render (`--block-range 0-8 --max-panels 3`, same seed) produced all three
panel types in a single pass — solo silhouette (one figure), the crowd cut
(hostile mountain framing), and Fang Yuan's condition panel (torn robes,
visible blood) — with no interaction defects between them. This is the
first re-render since the byte-identical anomaly that can be trusted at the
pixel level, at this reduced scale; the full 48-panel re-render and pixel
audit (Section 5 of the SceneState plan) is the next step.

**Process lesson, worth repeating so it isn't rediscovered: `prompt_cache_v1.json`
is a phase-1/stub-engine artifact, not the delivered prompt.** Mid-session,
inspecting that cache file's `:crowd`-suffixed entry for the full-chapter
run looked like the crowd fix wasn't reaching the real (`directed is not
None`) director path — it was missing the hostile/locale content entirely.
That reading was wrong. `panels.py`'s `is_crowd_cut` rewrite block sits
*after and outside* the cache-hit/cache-miss branch, and runs unconditionally
on every crowd-cut panel regardless of cache status or director success; the
value written to `prompt_cache_v1.json` is the **pre-overwrite** intermediate
from phase 1 (director-only pass, stub engine), never updated after the
crowd-cut post-processing runs. The actual delivered prompt only shows up in
`manifest.jsonl` (or the real generation call) written during phase 2. A
future debugging session investigating what prompt a panel *actually*
received should check the manifest, never `prompt_cache_v1.json` — that file
answers a different, earlier question.

**New defect found during the v54 full-chapter pixel review, not fixed
here, explicitly not part of anything just fixed:** block 31
(`p014_b0031.png`) mis-casts **"Qing Mao Mountain" — a location — as a
named character**, attaching appearance attributes (`black_hair, blood,
wounded, androgynous_person`) to it, and renders two figures despite a
`standing_alone` layout tag with no `solo` anywhere in the prompt — meaning
this panel never went through `cast_tags()`'s silhouette-fallback branch at
all, because *something* upstream in cast/persona resolution treated a
place name as a resolved character. This is a **persona/resolution bug** (a
location entity leaking into character casting somewhere before
`panels.py`'s prompt assembly), not a prompt-construction or
crowd-contradiction issue — do not bundle it with, or mistake it for, any
of this session's is_crowd_cut/solo-tag/hostile-modifier fixes. Next
session: trace where "Qing Mao Mountain" (presumably a `Self`/mention
entity with `kind` misclassified as a person, or a cast-resolution step
that doesn't filter on `entity.kind.is_person`) gets into a panel's
resolved cast.

**v54 shipped** (`data/RI/panels/ch1/v54_crowd-solo-scenestate-fix/`, 51/51
panels, full pixel review in `VERSIONS.md`): the crowd-template,
invented-figure, and block-75 fixes are now confirmed at full-chapter scale,
not just small-scale. Two mountain-path crowd cuts (blocks 37, 45) are the
first in this novel's render history to escape the ceremony-hall template.


---

### Section 10 (superseded "suggested next steps" list, as of the 2026-08-31 cleanup)

This was HANDOFF's own "suggested next steps, in order" section before
the cleanup. Kept here for the reasoning trail (why certain items were
prioritized), but it is stale as a task list -- most of section 10 dates
to 2026-08-13, predates the entire 4.31-4.52 arc above, and several items
are already marked done inline. Do not treat this as current; see
HANDOFF.md's live open-defects list for that.

## 10. Suggested next steps, in order

**Picking this up fresh, read 4.31 before this list.** It is the author's
own watch-through report on the most recent real chapter video and it
outranks everything below until it's addressed — nine specific defects,
none fixed yet, with a suggested order at the end of that section.

1. **Get a person to confirm 4.12's gold set, then calibrate the gate** (4.1).
   The scorer cannot emit a linking probability above p=0.71 against a 0.80
   threshold — every link in the system runs through the pre-filter, not the
   scorer. This is the root cause under 4.1, and it is why 4.15's two
   identity-continuity misses can't be fixed by scoring harder: they need new
   *pre-filter* signal (a declaration variant, a lexicon-aware containment
   check), not a rebalanced weight. Extend the confirmed gold past ch5 before
   calibrating — five chapters is too small a sample, 4.12 says so explicitly.
2. **One of the two 4.15 identity-continuity misses is fixed: ORV's
   `Dokja`/`Kim Dokja` split** — `name_containment` now distinguishes a
   dropped surname (ambiguous, correctly still blocked) from a dropped given
   name (usually unambiguous, now merges) via a corpus-wide ambiguous-token
   set rather than a token-count threshold. See the top-of-file note on this
   session's work for the mechanism and verification. **Still open:** LOTM's
   transmigration reveal needs the declaration detector to recognise "memories
   flooded him" as an identity-continuity assertion — different mechanism, not
   touched this session.
3. **Recover the speaker-attribution regression** (4.9/4.14). 64.9% → 48.8%
   at full RI volume, and it got worse as the run scaled up, not better.
4. ~~**Build `Persona`'s runner**~~ **Done, 4.21** — `persona/build.py`,
   Phase 7. What remains from the original item: **a second persona per
   self**. Reincarnation/disguise needs it, and 4.15's LOTM case now links
   the identity but still yields one persona. That is a `resolve/` change
   emitting a persona split, not a Phase 7 one.
5. ~~**Entity typing at the `Mention`/`Self` level, not just the commonness
   filter.**~~ **Partially done, 4.20.** `Mention.entity_label` now carries
   NER's label through to resolve, which auto-flags an entity founded
   unanimously on a non-"character" label instead of silently letting it
   join the voice-cast list. What's still missing: the flag is a review
   note, not a type — a kept item/location still displays and behaves like
   a character everywhere else (review table, webview, voice casting),
   because `TargetKind` only has `SELF`/`PERSONA`, nothing for a non-person
   entity to actually *be*. Extending `TargetKind` is the real fix; the
   auto-flag was deliberately the safe, additive step short of that (see
   4.20 for why a blunt filter at mention-detection time was rejected —
   already regressed once, per this same section's history).
6. Wire the remaining three LLM stages (4.10), coreference last and budgeted.
7. Then: Mondrian conformal, baselines (5).
8. **Not started — recurring unnamed characters and voice consistency.**
   A mob of retainers/guards attached to a named character, or a minor
   character who recurs across a handful of chapters without ever being
   named, gets a fresh anonymous slot every chapter (4.19) — there is no
   persistence across chapters, only within one. Mechanically possible
   today via `merge_entities`/`reassign_speaker`'s `new_label` (promote the
   recurring anon slot to a manual `Self` once, then merge later chapters'
   occurrences into it), but nothing makes this easy or automatic, and
   nobody has done it by hand yet either. The dormant `Relation` table
   (`core/models.py`) is a plausible place to tag such a group as
   `retainer_of`/similar once it exists, for UI grouping — see the turn-1
   discussion in this session's conversation log for the fuller design
   trade-offs (mob-vs-collective-voice, cold-start slot numbering).

9. **Finish the voice path to real audio** (4.21). Everything is built and
   tested against a stub. Three concrete steps, in order:
   a. Let `data/voice/vctk.zip` finish (~10 h at ~330 KB/s; resumable —
      re-run the same `curl -C -` if interrupted), then extract it there.
   b. `uv add torch torchaudio chatterbox-tts` — several GB; do it when the
      VCTK download is not competing for bandwidth.
   c. **Stop `ollama serve` first**, then
      `uv run echotales voice --novel reverend-insanity --engine chatterbox
      --chapters 1-2` and *listen to it*. Nothing in the test suite can tell
      you whether a voice suits a character.
10. **Temporal voice evolution and audio post-processing are unbuilt**
    (plans.md Phase 9 items 1, 3, 5): `state_of`-keyed voice parameters,
    the inner-monologue filter effect, and per-setting reverb. Item 3 is the
    cheapest and most audible of the three.
11. **START HERE if you are picking this up fresh** — the visual pipeline,
    in priority order, as of 2026-08-13.

    **Constraint from the author, which governs every choice below:** the
    research submission must run on **free models and APIs**. Paid APIs are
    not ruled out, but are a **last option, reserved for the point where the
    pipeline is good enough to be worth scaling** — paying to mass-produce
    output from a crude pipeline buys nothing. Do not reach for a paid
    backend to work around what is actually a pipeline problem. 4.25 has
    the measured costs for when that point arrives.

    a. ~~**Build the persona split**~~ **Done, 4.27/4.28.** Fang Yuan has
       two personas on one self, split at ch1 b82; appearance is extracted
       per body; the transformation gets its own panels. Left over: the
       *other* rows of `architecture.md 4`'s table — body swap, clones,
       possession — have nothing emitting concurrent or crossed bindings.

    b. **Render the ablation figure. This is now the highest-value item.**
       ch1 and ch40 twice, once `state_of`-driven and once flat. The flat
       arm drawing a teenager as a 500-year-old is what *proves* the
       contribution rather than asserting it. The data exists (4.27 has the
       two prompts, differing by position alone); what is left is four
       images, a layout, and a `--flat` switch pinning `persona_at` to the
       latest body — so the ablation arm is a real code path, not a
       hand-edited prompt.

    c. **Mention resolution is the ceiling on everything above**, and it
       bit twice more this session: RI ch12's "his body figure was tall and
       thin, his skin pale" has no resolved mention (4.24), and *both*
       body-change worked examples sit in blocks whose only reference to the
       character is "his" (4.27). Improving it lifts appearance, world
       facts, panel casting and split detection at once.

    d. **Body 2's appearance is thin because the prose is thin.** RI
       describes Fang Yuan's death scene and little else, so per-body
       extraction gives body 2 one attribute. Either widen the chapter range
       past 40, or accept `canon.py` as the layer that carries it — both are
       defensible, the second is already built.


12. **Work the relevance list.** `uv run echotales relevance --novel
    reverend-insanity` ranks panels by how little of their prompt the source
    text says, exempting crowd cuts and hand-authored staging. Nine ch1
    panels are still under 0.10. This replaces "open PNGs until something
    looks wrong" as the way visual defects are found, and it is the only
    number in the visual path that moves when the director improves.

13. **Watch the output.** The render pipeline has produced a real chapter
    video (4.24) but its shot rules have still never been *eyeballed*: the
    pan-direction rule in `director.py` and the clip tag vocabulary in
    `motion.py` are first-guess heuristics. 4.24's list of five defects
    found purely by looking at generated images — a woman drawn for the male
    protagonist, a collage of twelve thumbnails, a girl with cherry blossoms
    for a death threat — is the argument for doing this before anything
    else in the visual path is tuned. Nothing in the test suite can tell you
    whether a shot reads well.


**How to check your work:** `uv run echotales run --novel <novel>` then
`uv run echotales review --novel <novel> --script <a-b>`. Report the singleton
**count** next to the percentage (4.9's warning: the rate moves the wrong way
when the fix is working). The script view's dialogue-attribution coverage is
now the fastest way to see the speaker-attribution regression directly, rather
than inferring it from the summary line.

