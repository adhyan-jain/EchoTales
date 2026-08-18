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

The owner bulk-approved the gold set (§4.12) so calibration could finally
run. **It ran, and it disproves §4.1's implied fix.** Recorded here because
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
`FALLBACK_LINK_THRESHOLD = 0.80`. That floor was §4.1's mechanism. Removed —
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
choice for this feature set**, and §4.1 should be read accordingly: the
problem is not an unreachable threshold, it is that
`surface_similarity`/`context_embedding_similarity`/`speech_partner`/
`temporal_validity` do not carry enough signal to separate two members of
one clan. **The next move is better features, not a better threshold** —
and `_ambiguous_tokens` (§4.15) is the shape of what works: a signal that
knows "Chi" is shared by six people and therefore proves nothing.

Default behaviour is unchanged (82 entities / 821 links): an uncalibrated
`ConformalGate` still uses the fallback thresholds, and nothing enables a
calibrated gate automatically. Reproduce with
`eval/calibrate.py::calibrate_from_gold` against a scratch DB.

### 4.1 The scorer cannot reach LINK *(blocker — root cause found; see §4.1b for the resolution)*

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
(`resolve/runner.py::_maybe_flag_non_character`, item 5 in §10's list):
NER's own "location"/"organization" label was being computed and then
discarded — every mention that reaches resolve becomes a `Self` regardless,
since there's no non-person `TargetKind` (see §10 item 5 for why this is
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
- §10 item 8 (new): recurring unnamed characters (a named character's
  retinue, a minor character across a few chapters) still get a fresh
  anonymous slot every chapter — no cross-chapter persistence exists.
- `create_mention` has no frontend UI yet (above).
- Extending `TargetKind` past `SELF`/`PERSONA` so a flagged item/location
  can actually stop behaving like a character everywhere, not just get a
  review note (§10 item 5).

### 4.21 Phases 7 and 8 — personas, voice casting, TTS (2026-08-12)

**Phase 7 (`persona/build.py`)** mints one `Persona` per character entity,
binds it, and writes a trait profile as `Attribute` rows under
`TargetKind.PERSONA`. This closes §10 item 4 and unblocks everything below.

*One persona per self*, so `architecture.md §4`'s table is still aspirational
below its first row: reincarnation needs a *second* persona, and deciding a
second body exists is a `resolve/` question Phase 7 sits downstream of. §4.15's
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
- **Engine is Chatterbox (MIT), not XTTS-v2** as §4b originally proposed.
  XTTS is non-commercial-only from a shut-down company and has no emotion
  control; Chatterbox has an explicit `exaggeration` dial. User confirmed
  no near-term commercialisation, but MIT costs nothing to prefer.
  `turbo` variant for the 8 GB budget. **`ollama serve` must not be resident
  during synthesis** — same non-negotiable as every GPU stage (measured:
  ollama alone holds 5.0 of 8.0 GB).
- **Casting colours within buckets**, principals first, age relaxed before
  gender. Collisions logged, not claimed absent (`architecture.md §8b`).
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

**120 entities of which only 75 are people** — §10 item 5's typing is
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

### 4.31 User watch-through of the §4.30 video — nine real defects, none fixed yet *(2026-08-15)*

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
   48.8%" number in §4.9/§4.14 -- that number measures coverage, not
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
   now (§4.30). Change both to `1.0` first -- this is the one purely
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
   already known and *already partly fixed, just not wired in*: §4.30
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
   panel wastes the same GPU time §10 item 11 (block-range testing) was
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
    hall. Given §4.30's `has_mob`/`resolved_subjects` work was aimed
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

### 4.30 Real cloned audio, block-scoped casting, and the panels that go with them *(2026-08-15)*

Direct response to watching the §4.29 video with the sound on and at real
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
second stale-column bug in the same family as §4.15's.** `Mention
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

**Real audio, finally.** VCTK's zip (11.7 GB, §4.29 already found it
complete) extracted properly this time -- into `data/`, not `/tmp`, which
is a small tmpfs and filled on the first attempt. `load_vctk` sees all
110 speakers. Chatterbox runs via `uv run --with chatterbox-tts --with
"setuptools<81"` -- an **ephemeral overlay**, not a second `.venv`: it
resolves per-invocation without touching the project's own environment,
which means the "chatterbox and diffusers can't share a venv" blocker in
§4.21/§4.25 was never actually true, only under-specified. `setuptools<81`
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
fixes (§4.28's follow-up): stub voice (real, correctly-timed WAVs; no real
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
same frame described in §4.27/§4.28's design discussion, now actually in a
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
listed size) -- §4.21/§10 item 9's "2.5 of ~11 GB, partial" is stale. Not
extracted this session (an attempt into `/tmp` filled the 7.7 GB tmpfs
before I redirected it into `data/voice/`, wasting time worth flagging: extract
into the repo's own disk, `/tmp` is tmpfs and small). Extracting it and
wiring `chatterbox-tts` (remember the separate-venv warning, §4.25) is what
turns this session's silent stub audio into a real audiobook track.

### 4.28 Per-body appearance, and panels chosen by drama *(2026-08-13)*

Two changes that turned out to be one: the pipeline knew a character could
change bodies (§4.27) and neither the extractor nor the camera used it.

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
drifted before — §4.24 records the director's combat stems and `motion.py`'s
clip tags becoming disjoint vocabularies, so a block scored maximally on
violence and then played the neutral idle loop.

### 4.27 The persona split — two bodies, one consciousness *(2026-08-13)*

**§10 item 11a, done.** `persona/split.py`. Fang Yuan is a 500-year-old
demonic cultivator in chapter 1 and a fifteen-year-old clan boy for the
other 198 chapters, and until now the graph said he was one body throughout
— which made every panel of him wrong on one side of that line or the other.
`architecture.md §4` was designed around exactly this case and `build.py`
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
against §4.22's 191.1s for 75 — the split costs nothing measurable.

**The corpus corrected four things, none of which a fixture would have.**

1. **Both worked examples sit in blocks with no resolved mention.** RI ch1's
   "memories of his previous life on Earth emerged before his eyes" and
   LOTM ch1's "memories began flooding him" refer to the character only as
   "his" — and an unresolved pronoun is not a mention, so the obvious
   same-block presence rule found *neither* of the two cases the module
   exists for. Widened to a ±3-block neighbourhood. This is §10 item 11d
   (mention resolution is the ceiling) showing up in a new place.
2. **The clearest statement in each chapter is the character's own line.**
   Fang Yuan *says* "With the use of the Spring Autumn Cicada I have been
   reborn"; Zhou Mingrui *thinks* "C-could I have transmigrated?".
   Narration-only detection missed both. Dialogue and inner monologue now
   count when the speaker is this entity and the line is first-person —
   which needs the `speaker_self_id`↔entity join on `comparison_key`, the
   same §4.21 defect voice casting hit.
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
selves (§4.15, still open — needs the declaration detector), so there is no
single consciousness for two personas to hang off. Every ch1 candidate there
was correctly vetoed as a back-reference; the two the model kept before the
regex fix were the trance above. This is a clean statement of what §4.15
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

**How much of the ch1/ch20 contrast is extracted, stated exactly.** §4.28
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

**The gap.** The graph has typed its entities since §10 item 5 and has had a
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
§0 says so outright -- and image quality is a confound to remove, not a
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

§4.23 built the video *assembly* (timing, compositing, shot decisions) but
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
of ~11 GB — so §4.21's blocker still stands), stub panel images, and a
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
module exists to fix, and the same chapter now produces **14** (§4.28). The
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
> **Not fixed, and this is the flagship case §4 was designed for:** Fang
> Yuan needs **two personas on one self** -- the aged pre-regression body
> and the regressed one -- exactly the split `architecture.md §4` describes
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

**The recurring lesson across §4.24: the persona table's stored values
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
is ~9 GB of weights against §3's 8 GB card and `tasks.py`'s own
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
gap §4.21 already flagged for Phase 8, not a new one: `data/voice/` (VCTK)
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

## 4b. Voice / TTS design — **superseded, kept for its reasoning** (2026-08-07)

**This section is the design *proposal*; §4.21 is what was built.** Where
they differ, §4.21 wins — most notably the engine (Chatterbox, MIT, not
XTTS-v2) and the bank (VCTK, for its hand-recorded age/gender/accent
metadata). Kept because the trade-offs it works through are still the
reasoning behind the built version.

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

