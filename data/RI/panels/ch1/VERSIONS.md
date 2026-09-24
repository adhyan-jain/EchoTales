# ch1 panel version index

**Purpose: render-output tracking only.** This is the *only* place a
render version number (`v44`, `v51`, `v54`, ...) gets recorded — never a
HANDOFF/EVOLUTION section number, and never assume a section number
identifies a render version or vice versa. If a version referenced
elsewhere isn't listed here as its own `## vN...` entry, that's a real
documentation gap to fix here, not evidence the version never existed
(render output is gitignored — check the actual directory on disk before
concluding a version doesn't exist).

Why this exists: `v10`-`v40` (31 directories) have bare numeric names with
no link back to HANDOFF.md's fix log, and HANDOFF itself only names a
version number in 5 of its 21 sections. Looking at the directory told you
nothing. This file is the missing link — what was tried, in enough detail
to know what you're actually looking at, and an honest verdict, blunt and
from a viewer's point of view, not a metric.

Going forward (adopted 2026-08-25): every new version directory gets a
short descriptive suffix like `v1`-`v9` originally had (e.g.
`v44_carry-forward-cast-fix`), and an entry gets added here at the same
time — not after. See CLAUDE.md's "Versioned output directories" note.

---

## v1_per-paragraph-89panels — 2026-08-13

**What was tried:** the first real generation run, before any panel-budget
logic existed. One image per paragraph-level block, no merging of
consecutive blocks into a single "beat."

**Verdict:** 89 panels for one chapter — a wall of near-duplicate images,
most of them showing the same moment a paragraph apart. This is the
concrete number HANDOFF cites as the reason `render/beats.py` (later
`render/scenes.py`) exists at all. Not worth opening unless you specifically
want to see the "no budgeting" baseline.

## v2_14panel-drama-weighted — 2026-08-15

**What was tried:** panel count cut to 14/chapter, with selection weighted
toward the most dramatic beats rather than one-per-paragraph.

**Verdict:** A real improvement in count, but this predates every director
and cast-scoping fix documented below — expect wrong or missing characters,
no `1boy`/headcount steering tags at all (that bug wasn't found until
v34/4.42), and appearance clauses that may not match canon. Judge it only
on "does the panel count/selection make sense," nothing else.

## v3_70panel-no-director — 2026-08-15

**What was tried:** the mechanical (non-LLM) prompt assembler at a
70-panel budget, LLM director explicitly off (`--no-director`).

**Verdict:** HANDOFF's own framing: grammatical prompts that are "about
nothing" — cast tags, a truncated slice of narration, a locale from a
keyword table, stapled together with no comprehension of what's actually
happening in the beat. This is the deliberate baseline the director path
was built to beat, not a candidate for "final" output.

## v4_scene-grouped-no-conditioning — 2026-08-15

**What was tried:** the first scene-grouping pass — multiple blocks
sharing cast/place/timeline collapsed down to fewer images instead of one
per block — but with no reference-image conditioning wired in yet.

**Verdict:** Right structural idea (this is the ancestor of today's
`render/scenes.py::group_scenes`), but expect a character's face/identity
to drift between panels since nothing is holding it consistent yet.

## v5_pre-mob-scene-fix — 2026-08-15

**What was tried:** nothing new — a snapshot taken deliberately just
*before* a crowd/mob-scene fix landed, kept as a before/after comparison
point.

**Verdict:** Expect the crowd bug this snapshot precedes to still be
present (a scene with a mob asserting "many people present" onto every
panel in it, not just a dedicated crowd cut — the same class of bug fixed
properly later in v35-v37/4.46). Not a fix in itself.

## v6_pre-solo-tag-fix — 2026-08-15

**What was tried:** same pattern as v5 — a before-snapshot, this time
ahead of a fix to how a single/solo character gets tagged in the prompt.

**Verdict:** A baseline marker, not an improvement. Don't judge the project
by this one; it exists specifically to show what came before the fix.

## v7_pre-appearance-fixes — 2026-08-15

**What was tried:** another before-snapshot, taken ahead of a round of
appearance-clause fixes (the work that eventually became the
citation-grounded extraction pipeline in `resolve/appearance_extract.py`,
fixed properly in v40/4.49).

**Verdict:** Appearance data here is likely wrong or missing outright —
this is "before," not "after."

## v8_long-character-clause — 2026-08-17

**What was tried:** a full, detailed appearance clause (hair, eyes,
build, attire, all of it) embedded per character in every panel prompt.

**Verdict:** Reverted one version later. CLIP's prompt budget is 77
tokens, and a long clause spent most of it on one face — crowding out
setting, lighting, and the scene's own locale. If a panel from this
version shows a correct-looking character against a blank or generic
background, this is why.

## v9_short-clause-scene-restored — 2026-08-17

**What was tried:** the direct fix for v8 — condensed the appearance
clause to only the most discriminating features (`condense_clause`),
freeing the tokens that setting/lighting/locale need, and restored the
scene context that got crowded out.

**Verdict:** The actual fix v8 was reaching for. This condense-and-budget
approach is still how the pipeline works today (`persona/prompt.py`).

## v10-v27 — 2026-08-17 — UNDOCUMENTED

**What was tried:** genuinely unknown. 18 separate version directories —
half the entire history of this chapter's renders — were generated in a
single day with **zero corresponding HANDOFF entry** (HANDOFF has no
section dated 2026-08-17 at all) and no descriptive filename to go on
either. `git log` doesn't help either: a render's version number is a
runtime artifact, not a commit, so there's no reliable way to tie a
specific `vN` directory back to a specific code state after the fact
without re-running old commits against this exact chapter and comparing
output by eye.

**Verdict:** Unknown, and I'm not going to guess a plausible-sounding
story to fill this gap — that would be worse than admitting it's missing.
If you genuinely need to know what changed across these 18 versions, the
honest path is a manual diff of the prompts/images themselves, because no
one wrote down what happened. This is the single biggest concrete gap in
the project's documentation, and the direct answer to "why do we have this
many versions of the same chapter" — for this stretch, nobody kept a log.

## v28-v32 — 2026-08-18 — HANDOFF 4.40

**What was tried:** root-caused the "the images are irrelevant" complaint
as structural, not a director or checkpoint failure. Panel slots were
being assigned by content type alone (narration → establishing shot,
dialogue → close-up), so a scene of any length produced at most three
images, each anchored to whichever block first claimed that slot.
Measured directly on this exact chapter: **22 panels covering 92 blocks,
with individual panels covering 12 and 16 consecutive blocks of
narration** — sixteen blocks' worth of audio playing over one static
picture of the scene's opening moment. Fixed by chunking a scene's blocks
into groups of `_MAX_BLOCKS_PER_PANEL=4`, each chunk getting its own
director call and its own beat-specific prose.

**Verdict:** A real, measured relevance improvement — the picture now
changes roughly as often as the audio actually moves the scene forward,
instead of holding on one frame for sixteen blocks. Casting was still
broken throughout this batch (see v33 immediately after) — a scene-wide
cast-scoping bug hadn't been found yet, so expect characters appearing in
scenes they're not actually in.

## v33 — 2026-08-19 — HANDOFF 4.41

**What was tried:** fixed the cast-leakage bug v28-v32 still had —
`get_panel_cast` was scoped to the whole scene's block range, and since
the protagonist appears *somewhere* in nearly every scene, a chunk of
clan elders gossiping about an unrelated third party got handed him as
cast, and the director dutifully wrote him into a scene he isn't in.
Cast/presence now resolves from the panel's own blocks, not the scene's.
Also fixed: panel filenames were ordered by lead block number rather than
play order (`block0021`/`block0026`/`block0047` interleaved across
scenes in a directory listing), and role words got faction-qualified.

**Verdict:** Fixes one specific, confirmed instance of "wrong character
shown in a scene they aren't in." But this render still has the
count-tag/gender bug live (fixed one version later, in v34) — expect
panels here to potentially render as the wrong gender regardless of what
the prose says.

## v34 — 2026-08-20 — HANDOFF 4.42/4.43

**What was tried:** found and fixed the count-tag bug — HANDOFF's own
words: **"the bug that invalidated most of this session's visual
output."** The director's prompt-composition path (`Direction.
to_image_prompt`) built its string from action/cast/setting/lighting/mood
with no Danbooru-style count tag at all, while the mechanical assembler
put `1boy, male focus` at the very front. These checkpoints weight count
tags far above English phrasing, so every director-written panel fell
back to the checkpoint's training prior — overwhelmingly female — no
matter how plainly the prose said "he." Fixed, then a deliberately small,
targeted bake-off: 5 real ch1 panels on NoobAI-XL vs. the then-default
two-pass `refined` engine.

**Verdict:** This is the fix line to remember — **any earlier version
that went through the LLM director path should be assumed to have this
gender bug**, independent of anything else that version got right.
NoobAI-XL came out of the bake-off looking better for single-character
shots specifically; crowd/establishing shots did not (a limitation that
took several more sessions to actually work around).

## v35-v37 — 2026-08-21 — HANDOFF 4.45/4.46

**What was tried:** one-panel-at-a-time verification (rather than a full
chapter) found the director's own composition collapsing to "stands
alone" under any multi-subject prompt — three separate prompt-engineering
attempts to fix multi-subject composition directly all failed; switching
to solo framing worked on the first try, confirming a checkpoint ceiling
rather than a wording problem. Separately, a second real bug: the
crowd-context clause ("many people present... surrounding him") had no
`is_crowd_cut` gate, so it was getting stapled onto *every* slot in a
mob scene, including the main solo-subject slot — the crowd was being
asserted twice, and the solo slot never got a chance to actually be solo.

**Verdict:** The double-injection bug is a real, verified fix. But 4.46 is
explicit that the *remaining* gap on this chapter's block 0 after the fix
is "the checkpoint ceiling working as expected, not a new bug" — this
version cannot yet compose a correct multi-character confrontation scene,
and that's expected, not a regression to chase further here.

## v38-v39 — 2026-08-21 — HANDOFF 4.47/4.48

**What was tried:** three more code fixes shipped this round; root-caused
a prompt-token-ordering bug where the style anchor (`STYLE_ANCHOR`, the
few words that decide "this is ink painting, not a 3D render") was
getting silently defeated by truncation when it wasn't placed first.

**Verdict:** Three open visual defects were still on record after this
round per 4.48's own scoping note — this is "improving, precisely
diagnosed," not "solved." Read 4.47 and 4.48 directly before trusting
anything specific about this version's output.

## v40 — 2026-08-22 — HANDOFF 4.49

**What was tried:** two things at once. First, the appearance-extraction
contamination fix — the old grounding check asked "does this word appear
anywhere in the 60 pooled passages," which let a bystander's "green eyes"
two sentences away get attributed to the actual target; verified on a
scratch DB copy that this brought `typical_attire` contamination from
16/16 characters down to 0. Second — and unplanned — actually running this
render surfaced a new, worse bug: the director inventing **Bai Ning
Bing**, a real character who isn't introduced for another 107 chapters,
as present and PRESENT-tagged in chapter 1, because nothing constrained
the director's naming to the beat's actual cast.

**Verdict:** Mixed, and don't treat this as clean. The attire fix is real
and verified elsewhere (not in this specific render — it used the
already-contaminated production DB). This render itself still has the
Bai Ning Bing hallucination in it; it's the version that *found* that bug,
not the one that fixed it.

## v41_stub-director-validation — 2026-08-23 — HANDOFF 4.50

**What was tried:** verification that the CAST-constraint prompt rule +
a post-call fabrication validator (built to fix v40's Bai Ning Bing bug)
actually works. Run with `--image-engine stub` deliberately —
**solid-colour placeholder PNGs, not real pictures** — specifically to
check the director's *text* output cheaply, with no GPU cost.

**Verdict:** Confirms the fix in text: 0 Bai Ning Bing occurrences across
21 panels' worth of final prompts, checked directly against the cached
prompt data, not just the log. But there is nothing to look at as an
image here — opening this expecting a picture is the wrong expectation,
and asking for it caused exactly that confusion the first time around.

## v42 — 2026-08-23

**What was tried:** an interrupted real (NoobAI) render, stopped mid-run
by an explicit kill before it finished loading/generating past its first
few panels.

**Verdict:** 3 real panels only, and not representative of anything —
purely an accident of a kill command landing after some output had
already been written to disk. Don't read anything into this one.

## v43 (deleted once, then reused) — 2026-08-25

**What was tried:** two separate things landed in this slot. First: a
repeat of the stub-only casting verification (32 placeholder panels,
same mistake as v41 — reused for speed without noticing that's not what
was being asked for) — this was deleted after the second complaint about
receiving placeholders instead of images. Then: a real, deliberately
small NoobAI render (`--block-range 0-15 --max-panels 2`) specifically
verifying the empty-cast carry-forward fix — beats with no PRESENT-mode
character mention no longer fall back to *any* mention in their own
blocks (the confirmed mechanism behind "every panel is Fang Yuan," since
he's referenced in dialogue constantly even in scenes he's not
physically in). Confirmed directly against the real mention data: the
specific blocks (0-3) that used to wrongly cast him via a dialogue-only
reference now correctly show no character.

**Verdict:** The real v43 (6 panels) is a small, honest before/after
check of one specific fix, not a finished-chapter render — open it
expecting exactly that scope, nothing more.

## v44_appearance-precedence-fix — 2026-08-26

**What was tried:** a prompt-composition audit (separate from the casting
fixes above) found the beat's static wiki-canon appearance clause
(`data/RI/canon/wiki-appearance.json`'s `typical_attire: "white robes"`)
was being restated unconditionally on every panel, even when the block's
own narration described a contradicting physical state — chapter 1 blocks
5/9/13 read "deep green robes... torn to shreds," "covered in blood,"
"disheveled hair," but the v43 prompts asserted pristine white robes
regardless. Fix: `character_looks` now splits the appearance clause into
an identity part (hair/eyes/build — never overridden) and a separate
attire/condition part built from the block's own narration when it states
a transient physical state, falling back to canon attire otherwise. The
two are threaded through as independent parts (`Direction.conditions`) so
`fit_to_budget` can drop one without the other.

**First attempt regressed, badly.** An interrupted subagent session (hit
its account session limit mid-task) left half-applied code that merged
the transient override into the *same* string as hair/eyes/build. That
single oversized part got skipped by `fit_to_budget` wholesale under
budget pressure — losing the character's identity entirely on 3/3 test
panels, worse than the original bug. Caught by direct inspection of the
cached prompts before shipping, not by the subagent (its work was never
verified against a real render). That broken intermediate output briefly
occupied this `v44`/`v45` slot and was deleted.

**What actually shipped, verified against a real NoobAI render
(`--block-range 0-15 --max-panels 2`) after fixing the regression:**
splitting identity and condition into independent, separately-droppable
prompt parts, shortening the newly-added `framing` clause (it does not
need to be a full sentence), and capping the condition clause's own
length — because giving `framing` and `conditions` a place in the prompt
at all (neither existed in v43) used up enough of CLIP's 77-token budget
that identity was the one being dropped, not condition, until reordered
and shortened. Verified: identity clause present in 6/6 real render
panels (was 0/3 in the broken intermediate v44/v45); all 6 final prompts
measured under 77 tokens with the real CLIP tokenizer (was 80/77 for one
panel pre-fix). The attire/condition override itself is genuinely
best-effort under the remaining budget: it survived in 1/3 target panels
(block 13's "gravely wounded") and was dropped in 2/3 (blocks 5, 9) when
the director's own action/layout text for that beat left no room.

**Verdict, looked at as images, not just prompts: the fix did not
achieve what was asked.** Blocks 5, 9, and 13 still render as
near-identical clean, undamaged portraits — same pose, same pristine
robes, no visible blood or tears in any of the three, including block 13
whose *prompt* does contain "gravely wounded." The prompt-composition
bug (canon overriding local narration) is real and is now correctly
fixed at the text level, but two things stand in the way of it showing up
on screen: the 77-token budget means the override text often doesn't
survive at all, and even the one panel where it did survive shows the
checkpoint not responding to "wounded" as a strong enough visual cue
against its own training bias toward clean formal robes. Fixing the
prompt was necessary but not sufficient — the next thread (not started
here) is either freeing more budget for the condition clause specifically,
or finding a stronger/differently-weighted way to cue visible damage on
this checkpoint (a dedicated negative-prompt term against "clean robes",
or testing whether Danbooru-style damage tags outperform plain English
the way `1boy` outperforms "male" for headcount).

## v45-v51 — 2026-08-26/27 — UNDOCUMENTED

**What was tried:** genuinely unknown, same gap as v10-v27 above. Seven
directories exist on disk (v45: 8 panels, v46: 2, v47: 1, v48: 7, v49: 48,
v50: 48, v51: 48; mtimes 2026-08-26/27) with no corresponding HANDOFF
entry and no descriptive suffix. v51 is the last of these and is real —
confirmed by direct file audit (48 real panels) during the SceneState
session (HANDOFF, session of 2026-08-29) after an earlier pass in that
same session wrongly concluded it didn't exist by checking only `git log`
(render output is gitignored, so absence from git history proves
nothing). v49-v51 sharing a full 48-panel count suggests they're
consecutive full re-renders of the same fix-in-progress, and v45-v48's
partial counts look like interrupted/small-range test runs, but this is
inference from file counts, not a documented record — treat it the same
as the v10-v27 gap: don't guess a plausible story, note that it's
missing.

**Verdict:** Unknown. If specific detail is needed, the honest path is
the same as v10-v27's: diff the prompts/images directly, because nobody
wrote down what happened here either.

## v52_scenestate-and-crowd-fix (2026-08-29) — INCOMPLETE, stopped at 3/48 panels

**What this was testing:** SceneState (scene-level location/crowd-mood/
condition floor persisted instead of recomputed per caller), the crowd/
layout contradiction fix, the invented-figure validator, and the block-75
subject-vanishing fix (see HANDOFF 4.52 for full detail on all of these).

**What actually happened:** stopped by explicit instruction after only 3
panels generated, on sight of the crowd panel (block 0) looking unchanged
from v51. Confirmed by file hash, not just eyeballing:
`p003_b0000_crowd.png` is byte-for-byte identical to v51's version, despite
a demonstrably different final prompt string between the two runs and a
genuinely freshly-generated file (not a disk-cache hit). Not root-caused.
The other two generated panels (p001, p002) did differ from v51, so this
looks specific to the crowd-slot path rather than a blanket cache bug.

**Verdict: do not treat this as evidence the crowd-template fix works or
doesn't.** The one panel checked returned an anomalous result that
contradicts basic diffusion determinism assumptions and needs its own
investigation before any of Section 4.52's fixes can be pixel-verified.
Next session: root-cause the byte-identical output first, then re-render
the full 48 panels and do the real pixel-by-pixel review this version was
supposed to produce.

## v54_crowd-solo-scenestate-fix (2026-08-30/31) — completed, 51/51 panels, pixel-reviewed

**What this was testing:** the byte-identical crowd panel root cause
(`is_crowd_cut` was discarding the SceneState-aware prompt and replacing
it with a fully static template -- fixed, HANDOFF 4.52 follow-up), the
`hostile_confrontation_modifier` siege-atmosphere clause, the solo-tag
front-load fix for `cast_tags()`'s silhouette fallback, and the
`_SOLO_COLLAPSE_PHRASES` Danbooru-tag-form fix.

**What actually happened:** full chapter rendered clean, 51 panels, no
crash. Pixel-reviewed a representative sample across all 5 crowd cuts
(blocks 0, 37, 45, 62, 68), the solo silhouette panels, several Fang Yuan
condition panels, block 75 (long-flagged vanishing subject), and two
others.

**Verdict: real, verified improvement.** All 5 crowd cuts carry the
hostile/mountain content with zero crowd/solo contradiction; two (blocks
37, 45) show a genuine mountain-path crowd seen from behind -- the
intended framing, and a first for this novel's crowd cuts, which had
been stuck on the ceremony-hall template since v10. Every sampled solo
silhouette panel renders exactly one figure (the invented-second-figure
defect is gone wherever `cast_tags()`'s silhouette-fallback branch actually
fires). Block 75 shows a visible subject at the window, holding Section
4.4's earlier fix. Fang Yuan's condition panels (torn robes, blood)
remain consistent.

**One new, unrelated defect found in this pass, not fixed here:** block
31 (`p014_b0031.png`) mis-casts "Qing Mao Mountain" -- a location -- as a
named character (attaching `black_hair, blood, wounded,
androgynous_person` to it) and renders two figures despite
`standing_alone` with no `solo` tag; this bypassed `cast_tags()`'s
silhouette fallback entirely because *something* upstream resolved a
"cast" from a place name. This is a persona/resolution bug (a location
entity leaking into character casting), not a prompt-construction or
crowd-contradiction issue -- see HANDOFF for the next-session pointer.
