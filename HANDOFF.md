# EchoTales — Handoff

**What this file is:** where the last session ended and where the next one
picks up. Current state, the open defect list, and nothing else — the
history of how any of it got this way lives in `EVOLUTION.md`, not here.

**The other three, in the order you want them:**

| File | Answers |
|---|---|
| `EVOLUTION.md` | *Why is it built this way?* The diff between the original spec and reality — which mechanisms were replaced and what evidence replaced them. **Read before changing a design decision.** |
| `architecture.md` | The model: three axes of time, self vs persona, observers |
| `details.md` | Per-file detail |
| `plans.md` | The original spec. Amended three times; the amendments win and are marked *(revised)* |

**Last updated:** 2026-08-15. §4.30 built the first chapter video with real
cloned audio and block-scoped casting
(`data/video_v3/reverend-insanity/ch1.mp4`, 545s, 1080x1920). §4.31 recorded
the author's watch-through: nine specific defects. **This session fixed
four of them** (speed default, reference-sheet wiring, the panel-relevance
cluster) **plus three bugs found afterward by reading ch1's actual span
table directly, not in the original nine** — a translator's-note ingestion
leak that minted a phantom "Daoist Gu" speaker (§4.32), a store bug where
`add_spans`/`add_mentions` never deleted stale rows on re-run so old wrong
data survived every subsequent fix (§4.33), and two roster-pollution bugs
plus a missing epithet-based attribution tier that let a location and a
self-referential idiom get attributed as speakers while the clan leader's
real speaker tags went unused (§4.34). **Voice register (item 2) and voice
casting are still open** and are the next pick-up point; speaker
attribution is meaningfully better but the pronoun-to-epithet coreference
gap noted at the end of §4.34 is the natural next increment on it, not a
finished job.

**§4.32-§4.34, found this session, not in the original nine:** re-reading
ch1's actual span table (not just the video) surfaced three real bugs
independent of §4.31's list — see those sections below. All fixed. The
full 1-199 resolve/persona/speaker pipeline was re-run twice this session
(once after §4.32/§4.33, once after §4.34) to build
a real character knowledge base before any further per-chapter rendering;
see §0's workflow note.


## 0. Current state, in one screen

**The pipeline runs phases 0-9 end to end on free, local models** —
ingest → spans → segments → mentions → speakers → anaphora → resolve →
personas (with body split) → appearance → world facts → beats → LLM art
direction → local image generation → ffmpeg video, with picture length
locked exactly to audio length.

**Read `EVOLUTION.md` before changing a design decision.** It is the diff
between `plans.md` (the original spec) and what exists: which mechanisms were
replaced, and what evidence replaced them. Most of what looks like an
arbitrary choice in this codebase is a mechanism that was tried, measured and
swapped — the combat vocabulary that scored literally zero, the scorer that
can never reach its own threshold, the panel-per-paragraph that produced 89
near-duplicate images. This file is the *open defect list*; that one is the
reasoning.

**What is blocked, and by what:**

| Blocked | By |
|---|---|
| ~~Real audio~~ | **Done, §4.30.** VCTK extracted (110 speakers), Chatterbox runs via an isolated `uv run --with chatterbox-tts --with "setuptools<81"` overlay -- no separate venv was ever actually needed, only an ephemeral one |
| Reference-conditioned panels | Sheets exist now (`data/references_v2/`, §4.30) but no render has been pointed at them yet -- every panel to date is prompt-only |
| Any accuracy claim | Gold is 0% human-confirmed (§4.12). Entity counts here are plausibility, not accuracy |
| LOTM's transmigration demo | Resolve still splits `Zhou Mingrui` from `Klein` (§4.15). Not a persona-stage problem |

**The governing constraint, from the author:** the research submission runs
on **free models and APIs**. Paid APIs are not ruled out, but are a last
option reserved for the point where the pipeline is good enough to be worth
scaling — not a workaround for a quality problem that is actually a pipeline
problem. §4.25 has the measured costs for when that point arrives.

**Test status: 682 passing**, no failures.

**Two working practices that cost real time to learn, kept because they will
cost it again:**

- **Never `git add -A`.** Stage by path. An orphaned working-tree edit
  (`DEFAULT_BIAS -4.0 → -2.5`) was swept into a commit this way and cost 82 →
  59 entities to false merges before it was root-caused.
- **`data/*.db` are the run of record; `data/webview-working/*.db` are what a
  correction session edits.** Re-copy from the originals to reset.


## 1. Running it, and how to read its numbers

```bash
uv run echotales run    --novel reverend-insanity          # ~37 min w/ LLM, ~3 min --no-llm
uv run echotales review --novel reverend-insanity --script 1-5
```

`review` gives a console table, an HTML audit, a JSONL export, and a
line-by-line script view (§4.13) — the script view is the fastest way to see
speaker-attribution coverage directly rather than inferring it.

**`ollama serve` must be up.** `.env` sets
`ECHOTALES_MODEL_BACKEND=ollama`; `--no-llm` forces the deterministic path,
which is a supported A/B mode, not a degradation.

**Chapter NER is cached** at `data/lexicons/<novel>-ner-cache.json`, keyed on
chapter text + model name — a re-run is ~15 s instead of ~35 min, which is
what makes downstream tuning possible at all. It flushes every 25 chapters,
not only at the end; an earlier version lost 175 chapters of GPU work to that.

**How to read every entity count in this file: as plausibility, not
accuracy.** RI went 1,862 → 82 entities (deterministic → LLM layer 1), which
against a plausible 150-300 cast is *under*-counting — a better failure mode
than over-counting, and still a failure mode. §4.1b is the root cause and
§4.12 is why no number here is a validated result: the gold set is 0%
human-confirmed, and `eval/gold.py::GoldSet.confirmed_only` enforces it.

**Report the singleton *count* next to the percentage.** The rate moves the
wrong way when the fix is working — 49% of 551 entities is 271 singletons,
35% of 31 is 11. Quoting the rate alone misleads (§4.9).


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
| 7 Eval harness | `pipeline/eval/` | **Gold exists, unconfirmed; wired into `eval`** — §4.12, §4.20 | B-cubed scorer built (`coref_score.py`); RI gold extended ch1-5 → ch1-60 (3,457 mentions, still 0% confirmed); `echotales eval --novel X` now auto-scores against `data/gold/X.jsonl` when present — no longer a separate manual step |
| CLI + review | `pipeline/commands.py`, `review.py` | **Working, + script view** — §4.13 | `run` / `review [--script]` / `query` / `export` / `eval` |
| 7 Personas + traits | `pipeline/persona/` | **Working, + body split** — §4.21, §4.27 | RI vol 1: 76 personas / 75 characters (Fang Yuan has two bodies, split at ch1 b82). Gender resolved for 51% of cast deterministically (91% unknown before pronoun counting) |
| 8 Voice casting | `pipeline/voice/` | **Working, stub engine only** — §4.21 | Casts every character, writes manifest + casting report. **No real audio yet**: VCTK downloading, `torch`/`chatterbox` not installed |
| 7b Appearance | `resolve/appearance_extract.py` | **Working, per body** — §4.24, §4.28 | One call per *body*, over only that body's chapters. RI ch1-40: 13 attributes / 10 calls, 0 failures |
| 7c World facts | `pipeline/world/` | **Working** — §4.26 | RI full vol: 124 facts / 73 calls, 0 failures. Position-filtered retrieval verified |
| 9 Panels + video | `pipeline/render/` | **Working, local + free, + real cloned audio** — §4.24, §4.28, §4.30 | RI ch1: 92 blocks → **14 panels**, drama-weighted, block-scoped casting; real ffmpeg encode with real Chatterbox-cloned audio, picture length == audio length exactly |
| 8 Dataset export | — | **Not started** | JSONL export exists but is machine-only |

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

**Full history — every defect found, fixed, and the reasoning behind each
change — now lives in `EVOLUTION.md`, not here.** This section is only
what's genuinely unresolved *today*, kept short on purpose so picking this
up doesn't mean reading a session-by-session log first. If you need to know
*why* something is built the way it is, `EVOLUTION.md` is the answer;
if you need to know *why a number here looks worse than an old number you
remember*, the explanation is there too, not duplicated in this file.

**Still open, in priority order:**

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
   64.9% (deterministic) → 48.8% (full RI volume). Confirmed by §4.31's
   watch-through as a real, user-visible problem — an identifiable speaker
   (the clan leader) got cast as anonymous.
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
8. **Recurring unnamed characters have no cross-chapter persistence** — a
   named character's retinue or a minor recurring character gets a fresh
   anonymous voice slot every chapter.
9. **ORV block classification gaps**: 188 `HEADING` blocks survive per
   novel; `SYSTEM_WINDOW` detection under-fires because this source's
   status messages are bracketed prose, not `Key: Value` lines.
10. **`create_mention` has no frontend UI** — backend and tests exist; a
    reviewer can't trigger it from the browser yet.

---

**§4.31 below is the actual pick-up point** — the author's own
watch-through report on the most recent real chapter video, nothing in it
fixed yet, with a suggested attack order at the end of the section.

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
  §4 above, but this is the first confirmed case of it corrupting a
  *speaker* attribution rather than just a review-table display, which is
  a more serious instance of the same root cause than previously recorded.
- **Still not fixed, and now better understood:** even with §4.32's bug
  gone, the clan leader's dialogue (blocks 37, 47, 48, 54, 62, 68, 69, 78)
  is scattered across four different `anon:1:N` slots rather than
  consolidated onto one, because `_assign_anonymous_slots` cycles slots
  per-unresolved-run rather than per-speaker (§4 item 1's forward-only-pass
  diagnosis, confirmed again here against real chapter-1 data). Fixing item
  1 is what actually makes the clan leader "detected" as one continuous
  character rather than four unrelated anonymous voices; §4.32's fix only
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
  starved of it. This was already the pipeline's designed structure (§0,
  §8's `run` vs `voice`/`render` split) — nothing to build, just to run
  correctly and document as the expected workflow going forward.

### 4.33 `add_spans`/`add_mentions` never deleted stale rows on re-run — the real reason "Daoist Gu" survived §4.32's fix *(2026-08-15)*

After §4.32's ingest fix landed and a full 1-199 `run` completed cleanly,
re-inspecting ch1's span table directly (`store.get_spans`) still showed
the phantom "Daoist Gu" speaker on real dialogue lines. Root cause was one
level deeper than §4.32: **`Store.add_spans` and `Store.add_mentions` are
both `INSERT OR REPLACE` keyed by row id, with no corresponding delete of
rows a fresh re-derivation no longer produces.** When a block's
classification changes such that it now yields *fewer* spans/mentions than
a previous run did (exactly what §4.32's fix does — one `NON_DIEGETIC`
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

After §4.32/§4.33 cleared the "Daoist Gu" phantom, re-inspecting ch1's
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

---

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

# Phase 8: cast voices and render. --dry-run writes the manifest and the
# casting decisions without synthesising, which is how casting is reviewed
# before spending GPU time on it. --engine stub (the default) writes real
# but silent WAVs -- it is for testing the path, never for listening.
uv run echotales voice --novel reverend-insanity --dry-run
uv run echotales voice --novel reverend-insanity --engine chatterbox --chapters 1-2
#   -> data/audio/<novel>/manifest.jsonl   (one row per line, with the
#      voice, the synthesis parameters, and *why* they were chosen)
#   -> data/audio/<novel>/casting.txt      (bucket pressure + collisions)
#
# STOP `ollama serve` BEFORE synthesising: ollama alone holds 5.0 of 8.0 GB
# and no stage may share the GPU with another resident model (§3).

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
  spans/scene.py  active scene participants + mob detection (xyz.md Step 2)
  persona/   traits, extract, build (Phase 7); attire, runner (panel casting)
  voice/     bank, casting, delivery, engine, runner (Phase 8)
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
  voice/       CSTR VCTK 0.92, extracted. NOT committed (~11 GB, CC BY 4.0)
               -- download from datashare.ed.ac.uk, see §4.21.
  audio/       Phase 8 output: per-chapter WAVs + manifest.jsonl +
               casting.txt, one directory per novel. Git-ignored,
               regenerable with `echotales voice`.
  panels/      Phase 9 output: one cached PNG per (chapter, block_index) +
               manifest.jsonl. Git-ignored, regenerable with `echotales
               render` (§4.23).
  motion/      Phase 9 output: the reused motion-clip library, one frame-
               sequence directory + manifest.json per tag. Git-ignored,
               regenerable with `echotales render` (§4.23).
  video/       Phase 9 output: one mp4 per chapter (or, under the stub
               compose engine, a concatenated WAV + shot-manifest JSON
               instead). Git-ignored, regenerable with `echotales render`
               (§4.23).
  reruns/      full-pipeline re-run databases, one per novel (§4.22).
  webview-working/  copies of the *.db files above, edited by
               webview-server so a correction's Apply can never touch the
               databases this document's numbers are measured from (§4.18).
               Git-ignored -- regenerate by re-copying.
webview/     React viewer (git-ignored node_modules/build; §8a, §4.18)
```

`core` importing `pipeline` is a CI failure, not a style preference.

---

## 10. Suggested next steps, in order

**Picking this up fresh, read §4.31 before this list.** It is the author's
own watch-through report on the most recent real chapter video and it
outranks everything below until it's addressed — nine specific defects,
none fixed yet, with a suggested order at the end of that section.

1. **Get a person to confirm §4.12's gold set, then calibrate the gate** (§4.1).
   The scorer cannot emit a linking probability above p=0.71 against a 0.80
   threshold — every link in the system runs through the pre-filter, not the
   scorer. This is the root cause under §4.1, and it is why §4.15's two
   identity-continuity misses can't be fixed by scoring harder: they need new
   *pre-filter* signal (a declaration variant, a lexicon-aware containment
   check), not a rebalanced weight. Extend the confirmed gold past ch5 before
   calibrating — five chapters is too small a sample, §4.12 says so explicitly.
2. **One of the two §4.15 identity-continuity misses is fixed: ORV's
   `Dokja`/`Kim Dokja` split** — `name_containment` now distinguishes a
   dropped surname (ambiguous, correctly still blocked) from a dropped given
   name (usually unambiguous, now merges) via a corpus-wide ambiguous-token
   set rather than a token-count threshold. See the top-of-file note on this
   session's work for the mechanism and verification. **Still open:** LOTM's
   transmigration reveal needs the declaration detector to recognise "memories
   flooded him" as an identity-continuity assertion — different mechanism, not
   touched this session.
3. **Recover the speaker-attribution regression** (§4.9/§4.14). 64.9% → 48.8%
   at full RI volume, and it got worse as the run scaled up, not better.
4. ~~**Build `Persona`'s runner**~~ **Done, §4.21** — `persona/build.py`,
   Phase 7. What remains from the original item: **a second persona per
   self**. Reincarnation/disguise needs it, and §4.15's LOTM case now links
   the identity but still yields one persona. That is a `resolve/` change
   emitting a persona split, not a Phase 7 one.
5. ~~**Entity typing at the `Mention`/`Self` level, not just the commonness
   filter.**~~ **Partially done, §4.20.** `Mention.entity_label` now carries
   NER's label through to resolve, which auto-flags an entity founded
   unanimously on a non-"character" label instead of silently letting it
   join the voice-cast list. What's still missing: the flag is a review
   note, not a type — a kept item/location still displays and behaves like
   a character everywhere else (review table, webview, voice casting),
   because `TargetKind` only has `SELF`/`PERSONA`, nothing for a non-person
   entity to actually *be*. Extending `TargetKind` is the real fix; the
   auto-flag was deliberately the safe, additive step short of that (see
   §4.20 for why a blunt filter at mention-detection time was rejected —
   already regressed once, per this same section's history).
6. Wire the remaining three LLM stages (§4.10), coreference last and budgeted.
7. Then: Mondrian conformal, baselines (§5).
8. **Not started — recurring unnamed characters and voice consistency.**
   A mob of retainers/guards attached to a named character, or a minor
   character who recurs across a handful of chapters without ever being
   named, gets a fresh anonymous slot every chapter (§4.19) — there is no
   persistence across chapters, only within one. Mechanically possible
   today via `merge_entities`/`reassign_speaker`'s `new_label` (promote the
   recurring anon slot to a manual `Self` once, then merge later chapters'
   occurrences into it), but nothing makes this easy or automatic, and
   nobody has done it by hand yet either. The dormant `Relation` table
   (`core/models.py`) is a plausible place to tag such a group as
   `retainer_of`/similar once it exists, for UI grouping — see the turn-1
   discussion in this session's conversation log for the fuller design
   trade-offs (mob-vs-collective-voice, cold-start slot numbering).

9. **Finish the voice path to real audio** (§4.21). Everything is built and
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
    backend to work around what is actually a pipeline problem. §4.25 has
    the measured costs for when that point arrives.

    a. ~~**Build the persona split**~~ **Done, §4.27/§4.28.** Fang Yuan has
       two personas on one self, split at ch1 b82; appearance is extracted
       per body; the transformation gets its own panels. Left over: the
       *other* rows of `architecture.md §4`'s table — body swap, clones,
       possession — have nothing emitting concurrent or crossed bindings.

    b. **Render the ablation figure. This is now the highest-value item.**
       ch1 and ch40 twice, once `state_of`-driven and once flat. The flat
       arm drawing a teenager as a 500-year-old is what *proves* the
       contribution rather than asserting it. The data exists (§4.27 has the
       two prompts, differing by position alone); what is left is four
       images, a layout, and a `--flat` switch pinning `persona_at` to the
       latest body — so the ablation arm is a real code path, not a
       hand-edited prompt.

    c. **Mention resolution is the ceiling on everything above**, and it
       bit twice more this session: RI ch12's "his body figure was tall and
       thin, his skin pale" has no resolved mention (§4.24), and *both*
       body-change worked examples sit in blocks whose only reference to the
       character is "his" (§4.27). Improving it lifts appearance, world
       facts, panel casting and split detection at once.

    d. **Body 2's appearance is thin because the prose is thin.** RI
       describes Fang Yuan's death scene and little else, so per-body
       extraction gives body 2 one attribute. Either widen the chapter range
       past 40, or accept `canon.py` as the layer that carries it — both are
       defensible, the second is already built.


12. **Watch the output.** The render pipeline has produced a real chapter
    video (§4.24) but its shot rules have still never been *eyeballed*: the
    pan-direction rule in `director.py` and the clip tag vocabulary in
    `motion.py` are first-guess heuristics. §4.24's list of five defects
    found purely by looking at generated images — a woman drawn for the male
    protagonist, a collage of twelve thumbnails, a girl with cherry blossoms
    for a death threat — is the argument for doing this before anything
    else in the visual path is tuned. Nothing in the test suite can tell you
    whether a shot reads well.


**How to check your work:** `uv run echotales run --novel <novel>` then
`uv run echotales review --novel <novel> --script <a-b>`. Report the singleton
**count** next to the percentage (§4.9's warning: the rate moves the wrong way
when the fix is working). The script view's dialogue-attribution coverage is
now the fastest way to see the speaker-attribution regression directly, rather
than inferring it from the summary line.
