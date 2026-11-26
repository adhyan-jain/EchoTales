# Adaptation director plan: from "one panel per block" to a storyboard artist

Status: **PLAN ONLY, not started** (written 2026-11-22). The owner will start it when usage allows.
It extends `community_roadmap.md` and does not replace it. Where the two disagree on panel/voice quality work, this plan wins.

## 1. Why

On 2026-11-22 the owner watched and listened to the whole showcase (`data/exports/showcase_20261122/`). Verdict: "it is shit overall".

Compared with a published Reverend Insanity manhua chapter 1, the problems were:

- **Panels and directing:** far too few panels; "the director's job is gone".
- **Selective adaptation:** we have a narration-pruning mode, but it doesn't work well enough. The real adaptation drops lines, turns narration into images, and invents small connective scenes.
- **Character detail:** missing or wrong for many characters, including wrong genders.
- **Dialogue:** lines attributed to the wrong speaker.
- **Audio:** sounds sped up and slowed down. Emotion is severely lacking, and voices are inconsistent. The heavy clan-head voice was the one good one.
- **Foreshadowing:** the reference plants it (the drowning panel), which only makes sense volumes later. That is the reason the project reads a whole volume first.

My own reviews approved these outputs. They used a lenient 5-question checklist on contact sheets, never a side-by-side with a real adaptation, and nobody listened to the audio. The review bar in section 6 replaces that checklist.

## 2. What the reference does (RI manhua ch1, first ~65 of 182 slices studied)

The reference images live only in `data/scratch/reference/ri_manhua/ch01/`: owner-supplied, local, copyrighted, never committed. Slices are 1600 px wide and about 1080 px tall, from a vertical-scroll chapter.

The sheet-building script is `scratchpad/refsheet.py`; recreate it as `scripts/review/ref_sheet.py` when P0 starts.

Finding these patterns from slices 66-182, and from chapters 2-3, is task P0.1.

**Density**
- Slices 1-65 cover only the cliff battle and the death/rebirth montage, roughly novel blocks 0-30.
- Our render gave that same span about 12 panels. The reference spends about 60 slices, roughly 35-45 drawn panels.
- One line of dialogue often gets a whole panel, and one beat can get 3-5 panels: shout, face, reaction, insert.

**Cold open**
- The chapter opens on a giant SFX title spread over 4 slices: the crowd shouting "FANG YUAN!!" in red brush letters.
- The text's opening line comes only after that.

**Crowd lines become people**
- The novel's anonymous besiegers are given individual faces with personal grudges.
- Example: a woman wreathed in lightning says "300 years ago you humiliated me..." and "you massacred my entire family...".
- That invented minor detail is consistent with the text: it fits who Fang Yuan was.

**Look by epoch**
- The 500-year-old Fang Yuan at the cliff has long white hair, red eyes and a bloodied green robe.
- The reborn young Fang Yuan has black hair.
- We drew a young black-haired man at the cliff, because the "age at this point in the story" fact never reached the prompt.

**Inserts and symbols**
- A blood drop splashing ("Splot"), a hair whip, a robe close-up, an eye extreme close-up.
- Diagonal panel cuts with black gutters.

**Caption styles carry meaning**
- Plain white balloons for speech, rectangular boxes for time skips ("6 HOURS PASS").
- Soft round balloons over pale washes for the poem lines.
- Glowing golden ring captions for memory narration.

**Narration becomes visuals**
- "So many memories... begun to relive themselves" becomes a memory montage: a modern man in a suit in a library (his Earth past life), a grave stone, falling leaves, and an underwater drowning scene.
- That backstory is not in the chapter text. The adapter took it from later volumes. This is the "volume knowledge" use the owner designed the project for.

**Palette per segment**
- Magenta and red for the battle.
- Pale cream for the poem.
- Gold for the memory light.
- Deep blue for the underwater memory.
- Each segment holds one palette; we hold one look for the whole chapter.

**Lines dropped**
- Not every novel sentence appears. Narration is cut, merged, or shown instead of told.

## 3. Why ours falls short (root causes in the code)

| Gap | Where |
|---|---|
| Panel count is a fixed ratio of text: `DENSITY_BLOCKS_PER_PANEL = {"beat": 4, "dense": 1}` | `pipeline/compute.py:347`, used in `render/panels.py` |
| The director writes a prompt for each chosen block. It never decides what deserves a panel, what to cut, or what to invent. | `render/direction.py`, `render/panels.py` |
| The director is gemma2:9b with a 4096-token context that spills to CPU on 8 GB. It sees one scene paragraph and a staging sheet, never the volume. | `config.json` director model, `compute.py` presets |
| Volume knowledge never reaches the director: no arcs, no setup/payoff, no backstory, no look-by-epoch for this moment | graph to director boundary |
| Identity is one text sentence per character. No reference image (IP-Adapter removed); LoRA trainer built but never run. | `render/compiler.py`, `workers/runpod/lora_trainer` |
| Narration pruning is a crude video-side filter (`--prune-narration`, off by default). It is not an adaptation decision. | `render/runner.py` |
| Gender of xianxia names comes only from pronoun votes; there is no name prior for them | `persona/gender.py` (4.192/4.193) |
| Speaker attribution: RI is at about 95% on unchecked silver refs, and 15 of 29 ch1 lines are unresolved crowd lines | reader; `reader/speakers_pass.py` must not be edited without the owner |
| Audio applies tempo and pitch post-processing after synthesis, the "sped up" artifact; emotion is an intensity dial | `voice/delivery.py` `_BY_INTENSITY`, `voice/pitch.py` |
| One look and one palette per chapter; caption style does not encode meaning | `render/compiler.py`, `pages/lettering.py` |
| **Owner review 2026-11-27 of the RI ch1 sheet draft:** the clan-head ritual scene is never drawn, Fang Yuan is put into it instead, and reborn Fang Yuan still looks old. Likely root cause, not yet verified: abrupt scene changes never reach the director. Web novels cut scenes with a single line ("Southern Border", "Heavenly Court") or with no marker at all. Ch1 has two cuts: the future cliff, then the past (the clan head and elders' ritual), then young Fang Yuan after that talk. So each panel inherits the previous scene's cast and look. The `segment/` stage (markers, LLM boundary pass, `find_time_skips`) exists, but whether its segments reach the director and the persona-state choice is unverified. | `segment/`, `render/direction.py`, `persona/split.py` |

## 4. The plan

### P0. Reference corpus and adaptation metrics
This comes first because it sets the targets.

1. Owner supplies 3-5 RI manhua chapters locally (saved-page import, EVOLUTION 4.196) into `data/scratch/reference/ri_manhua/chNN/`.
2. Stitch the slices and cut them into panels with the existing comic panel detection (`comic/panels.py`).
3. Align each panel to novel blocks with a model-drafted alignment, which the owner spot-checks.
4. Measure per chapter:
   - panels per 1,000 words
   - panels per beat
   - the share of narration that becomes a visual, a caption, or a cut
   - invented panels and their kind: reaction, insert, symbolic, flashback, crowd-individual, establishing
   - the shot-type mix
   - palette segments
   - caption-style taxonomy
5. Write the result as `docs/results/ADAPTATION_STUDY.md` with numbers only; never commit images or quotes longer than a few words.
6. Keep 10-20 aligned examples, as block text plus a panel description we write ourselves (never the images), in `data/gold/adaptation/adaptation_examples.jsonl`. They become few-shot examples for the director and an evaluation set.

### P0.5. Per-novel convention induction: scene cuts and time jumps learned from one volume (owner review 2026-11-27)
Owner rule: **no hand-written patterns for one novel.** Every novel marks scene changes its own way: one-line realm headers, `***` or `◆` separators, "Meanwhile…", POV-name headers, system windows, or no marker at all. EchoTales must learn the novel's own conventions from its first volume, the same way `mentions/induce.py` learns a per-novel lexicon and `segment/markers.py` already treats patterns as per-novel defaults rather than universals.

1. **Discontinuity signal, computed per block boundary across the volume and convention-free:**
   - the change in the active cast (who is mentioned or speaking in the window before versus after)
   - location change (NER locations)
   - a time expression (from the existing time-skip finder)
   - tense or aspect shift (past perfect for flashbacks)
   - a POV change
2. **Candidate marker signatures:** describe each block by its shape rather than its words:
   - length, whether it stands alone, case pattern
   - punctuation-only, centred-symbol line
   - whether it is a single named entity and of what type
   - its position in the chapter
   Then cluster blocks with the same signature.
3. **Induction:** a signature becomes one of this novel's markers when it recurs across the volume and its blocks sit on high-discontinuity boundaries far more often than the base rate. Measure lift and keep the evidence counts.
   - For example, "a short standalone title-case line that NER tags as a place" would be learned for RI rather than coded.
   - `***` would be learned for a novel that uses it.
   - A small model confirms a few examples per signature. The induced set is saved per novel next to the lexicon and shown in the Studio for review (bounded queue, non-negotiable 7).
4. **Implicit cuts** with no marker, such as ch1's future cliff to past ritual: the highest-discontinuity boundaries go to the LLM boundary pass with their context. The conservative threshold policy applies.
5. **Evaluation, kept separate:**
   - Hand-mark scene boundaries for a few chapters each of 4 or more structurally different novels: RI, LotM, ORV, P&P, plus one more.
   - Report boundary P/R per novel, which conventions were induced per novel, and RI ch1's two cuts as a named check.
   - Report "learned from volume 1, tested on later chapters" so the induction is shown to generalise within a novel.
6. **Each segment carries its narrative layer and story time to the director:**
   - The director stages only that segment's cast, so the clan head and elders get their own scene.
   - The character's look is chosen by story time (the P1.1 look-by-epoch rule), so reborn Fang Yuan is young.
   - This is the three-axis temporal model (non-negotiable 2) doing its job.
7. **Remembered or past scenes** get a visible treatment: their own palette (desaturated or sepia), a vignette, a frame-edge effect, and a caption card.
   - Volume 1 gives no knowledge of Fang Yuan's future, unlike the manhua's director, who knew the whole story.
   - So treat the reminiscence as a dramatic effect over what the text shows. Do not invent content.

### P1. Volume pre-pass: the director's bible
Built once per volume and stored in the graph.

1. **Look by epoch and setting** for each main character: hair, eyes, build and clothes per interval and per location type. The cliff Fang Yuan is old with white hair; the reborn one is young with black hair. This extends the existing appearance intervals (`persona/split.py`, identity lock).
2. **Arcs and backstory facts** per character, with the chapter where each is revealed, so a memory montage can draw them.
3. **Setup/payoff index:** objects, places and events introduced early that matter later. Find candidates from the graph (mention bursts later in the volume, entities tied to climaxes), then rank them with a model.
4. **Locations sheet:** look, palette and recurring props.
5. **Segment palettes:** a mood or palette tag per scene segment (battle, memory, poem, ceremony, night).

### P2. Storyboard director (new stage)
It replaces the per-block director; the compiler stays.

1. **Input:**
   - the chapter text
   - bible entries for the characters present, at this time
   - setup/payoff hints for this chapter
   - target density from P0
   - few-shot aligned examples
2. **Output:** an ordered panel list. Each panel carries:
   - purpose (beat, reaction, insert, establishing, symbolic, flashback, crowd-individual, SFX title)
   - which text it carries (speech, caption, or none, since a line may be cut)
   - who is in it, with their look-at-time
   - shot type and palette segment
   - caption style
   - `invented: true/false` with a one-line reason
3. **Validators** (reuse the director validators):
   - no contradiction with `state_of()` at this point in the story
   - invented panels may not add plot facts, only texture
   - every spoken line is kept unless the storyboard explicitly cuts it, with a reason
   - names must be from the cast
4. **Selective adaptation replaces `--prune-narration`:**
   - The storyboard decides keep, show or cut per narration sentence.
   - Video, pages and the audiobook read the same decision; the audiobook ignores cuts.
5. **Crowd voices become people:** an unattributed crowd line may get an invented minor speaker with a stable look and voice, marked invented, consistent with the text.
6. **Model decision (owner):** a 9B local model cannot do this well in 8 GB.
   - Options:
     - a strong cloud model (Claude) for this text-only stage, once per chapter, cached, through the spend ledger (`cloud/ledger`)
     - a larger local model on bigger hardware
   - Recommendation: Claude for the storyboard only; images and voice stay local.
   - This changes the local-only rule, so the owner decides.

### P3. Render the storyboard

1. **Panel types the compiler must support:**
   - SFX title
   - insert or extreme close-up
   - symbolic
   - flashback montage with its own palette
   - crowd-individual
   - diagonal or irregular webtoon panels
   - black gutters
2. **Palette per segment** from P1/P2, instead of one look per chapter.
3. **Caption-style taxonomy** in `pages/lettering.py`: speech, thought, memory, time-skip, poem and narration each get a distinct look.
4. **Density:** the panel count comes from the storyboard, not from `DENSITY_BLOCKS_PER_PANEL`. Keep the old modes as a fallback.

### P4. Characters that hold detail
This is what the RunPod run is for.

1. Approve one character sheet per main character per look-interval (Studio approval already exists).
2. Train a LoRA per main character with the RunPod LoRA trainer, then load it into Z-Image. For secondary characters, use multi-reference keyframes (Qwen-Image-Edit worker).
3. Gender and identity:
   - The bible's look includes a gender the owner can correct.
   - Add a xianxia-name gender model or prior: the reader asks once per character over the volume.
   - Owner corrections are final (D29-D32).

### P5. Audio rebuild
Independent of P1-P4, so it can run in parallel.

1. Remove the tempo and pitch post-processing (`voice/delivery.py`, `voice/pitch.py`), then A/B the result by listening.
2. Per-line emotion:
   - Take the emotion from the storyboard or reader per line, not an intensity dial.
   - Drive it with the TTS engine's native controls.
   - Evaluate emotion-capable open TTS options against chatterbox on 20 RI lines.
3. One locked voice per character, including invented crowd speakers and "unconfirmed" lines (4.200 was started on this, see section 7).
4. Speaker attribution:
   - Hand-check RI ch1-3 speakers as true gold.
   - Measure, then decide with the owner whether the reader needs a stronger model, since speakers_pass.py may not be edited without the owner.
5. A blind listening test before any "good" claim. The owner's notes from 2026-11-22 are the first test.

### P6. Evaluation gate (replaces my checklist)
- Side-by-side with the reference chapter: our storyboard and panels against theirs, rated by the owner 1-5 on directing, character detail, mood and flow.
- Numbers against P0:
  - panels per 1,000 words within ±25% of the reference
  - invented-panel share
  - character-ID consistency (vision check)
  - attribution accuracy on hand-checked lines
  - zero gender errors on the main cast
- Audio: the owner's listening test; loudness -16 LUFS with every product matching.
- Nothing is called showcase-ready without the owner's rating.

## 5. Order and size

1. P0, starting with RI ch1-3: 1-2 agent sessions plus the owner supplying chapters.
2. P5 in parallel, since audio is independent.
3. P1, then P2 on RI ch1 only; iterate against the P6 gate until it is close.
4. P3.
5. P4, during the RunPod run.
6. Scale to RI ch1-10, then P&P ch1-3 (the public demo).

## 6. Owner decisions needed

1. Supply RI manhua chapters 1-5 locally (Ctrl+S "Webpage, Complete", then `echotales comic fetch <saved.html>`).
2. The storyboard model: a strong cloud model through the spend ledger (recommended), or local only.
3. Approve one character sheet per main-character look before LoRA training.

## 7. State left behind (2026-11-22)

Three fix agents were stopped by the usage limit. Nothing from them is merged. Their worktrees remain, and their work can be salvaged or dropped.

| Worktree | EVOLUTION | Scope |
|---|---|---|
| `.claude/worktrees/agent-a995b697c86097689` | 4.198 | comic audio |
| `.claude/worktrees/agent-af651163e707ceb39` | 4.199 | comic visual |
| `.claude/worktrees/agent-ad0fb92427dcb61f9` | 4.200 | pages, anime and unconfirmed voice |

- Review each with `git -C <worktree> log master..HEAD` before deciding.
- Master was at `a2e2d36` (4.197): suite 3082 passed, ruff 540, mypy 567.
- Compressed showcase videos for sharing are in `data/exports/showcase_20261122/share/`.
