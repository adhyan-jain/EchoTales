# EchoTales decisions log

A running, plain-language record of **what we decided, why, and what it changed**, written so you can learn the project from it. It is the "why" companion to `docs/HANDOFF.md` (what is open now) and `docs/EVOLUTION.md` (numbered bug and fix history). New decisions are appended; nothing is deleted, only superseded (marked **Superseded**).

How to read an entry: **Decision** (what), **Why** (the measured or stated reason), **Effect** (files and behaviour), **Status** (planned / done / reversed).

---

## 0. The project in one page

EchoTales reads a web-novel volume and builds a **bitemporal narrative knowledge graph**: who exists, which names point at whom, how they look, and *when* each fact became true versus when the reader learned it. From that graph it drives an audiobook (voices) and a manga-style video (images, motion). The graph is the research contribution; audio and video are the demonstration.

Pipeline order: ingest -> segment/spans -> mentions -> (reader pass, new) -> resolve -> speakers -> personas -> appearance -> voice -> render -> compositor/video.

Core ideas you will meet everywhere:
- **Self vs persona**: a Self is a continuous mind (Klein); a Persona is a body/identity it wears (Mr. Fool, a disguise). One Self can have many personas.
- **State of the world** is always asked at a position: `state_of(target, chapter)`. Chapter is not time; story time, reading time and knowledge time are separate axes.
- **Evidence**: every fact should carry the quote that proves it.
- **Stub-first**: everything runs deterministically with no GPU or network in tests (`ECHOTALES_LLM_MODE=stub`).

## 1. Direction decisions (2026-10-22, from the build-plan session)

### D1. Fix the extractor before any new media work
- **Decision**: Phase A (extraction rewrite) must pass its accuracy gates before real image/voice/video backends are built.
- **Why**: the audit of Lord of the Mysteries ch1-40 found 0 appearance attributes for 93 entities, no second personas, speaker accuracy 41% on hand-labelled ch7, and placeholder reference images. Rendering from that bible only produces confident nonsense.
- **Effect**: plan phases A (bible) -> B (review UI) -> C (real media backends) -> D (screenplay/episodes) -> E (Path 2 video). Each ends in a gate; the next starts only when it passes. Calendar estimates were dropped on purpose.
- **Status**: planned, Phase A in progress.

### D2. Reader LLM is local ollama for now
- **Decision**: the chapter reader pass runs on local `qwen2.5:7b` through the existing provider switch. A strong hosted model is a later swap behind the same switch, only if the local model misses the gates, and only after asking.
- **Why**: earlier owner rules: local models only (no RunPod/OpenAI since 2026-10-17) and a $5-10 total cloud budget. The build-plan doc assumed a paid API; this overrides it.
- **Effect**: prompts must be small and schema-light (7B models), with sub-calls if needed.
- **Status**: decided.

### D3. Gold labels come from Claude in-session, spot-checked by you
- **Decision**: Claude labels 5 chapters each of LotM, Reverend Insanity (RI) and Omniscient Reader (ORV): cast, aliases, personas by chapter range, appearance facts with quotes, and the speaker of every line. You check a sample.
- **Why**: labels must not come from the pipeline's own output ("circular gold", rejected in code by `CircularGoldError`).
- **Effect**: new gold files under `data/gold/`, scorer under `eval/`.
- **Status**: planned.

### D4. Gates for Phase A
- **Decision**: speaker accuracy >= 90%, appearance-fact recall >= 85%, persona-link recall >= 90%, entity-kind accuracy >= 95%.
- **Why**: a published method reaches about 90% speaker attribution with the cast list in the prompt (Michel et al.); today's pipeline is far below. The other thresholds keep the review queue bounded (non-negotiable 7).
- **Status**: decided.

### D5. Text-only canon
- **Decision**: delete the hand-written appearance tables (`persona/canon.py`, `render/beat_canon.py`, per-novel `persona/attire.py` entries). Appearance comes only from the book text. A human override becomes a visible correction record.
- **Why**: `canon.py` hard-coded Klein's eyes as "deep grey" and a trench coat while the text says brown eyes and a linen shirt, so renders drew grey eyes.
- **Status**: planned (step A8).

### D6. Review-gated workflow
- **Decision**: analyse automatically -> user reviews flagged items -> lock a versioned bible -> generate. Renders read only a locked snapshot. Edits are correction records re-applied after any re-extraction.
- **Why**: bounded review plus reproducible snapshots enforces quality without trusting every automatic decision, and stops a later edit silently changing an episode already made.
- **Status**: planned (Phase B).

### D7. Licence-clean model stack for anything sold
- **Decision**: product media models must be commercially licensed (Apache/MIT class). NoobAI XL / Illustrious are non-commercial and leave the product path once their replacement passes Gate C. Character LoRAs are not in the plan unless you ask.
- **Why**: a non-commercial model's licence also covers the images it generates.
- **Status**: decided; removal waits for Gate C.

## 2. Phase A implementation decisions

### D8. Version stamping and stale-build refusal (A1) - done 2026-10-22
- **Decision**: every database build records a `PIPELINE_VERSION` (now `"2"`) in `pipeline_run.pipeline_version`. A real (non-stub) render is refused with HTTP 409 when the database's newest stamp is missing, empty, or older.
- **Why**: the field existed but was always empty. LotM's personas were built from "0 spoken lines" before the speaker-join fix and nothing flagged it.
- **Effect**:
  - `packages/pipeline/src/echotales/pipeline/version.py`: `PIPELINE_VERSION`, `staleness_reason()`.
  - `core/pipeline_run.py::ensure_pipeline_run(pipeline_version=...)` stamps new runs and re-stamps a re-entered run.
  - `core/store.py`: `set_pipeline_run_version`, `latest_pipeline_version`.
  - Stage digests used a hard-coded `v1`; they now use the version, so a bump invalidates cached stage results.
  - `webview_server.py::_stale_build_refusal` guards the render routes; the **stub engine is exempt**.
  - Tests: `packages/pipeline/tests/test_pipeline_version.py`.
- **How to use**: bump `PIPELINE_VERSION` whenever extraction output changes meaning.
- **Known limit**: the stamp means "newest code that touched this run", not "every stage was rebuilt".
- **Status**: done, full core+pipeline suite green.

### D10. The reference set is "silver", and the scorer matches by name (A2, started 2026-10-22)
- **Decision**: Claude-drafted labels live in `data/gold/reader/<novel>-ch<NN>.json` with `provenance: "model"` and `confirmed: false`. We call them **silver** in every report; only a person confirming record by record (the `eval/gold.py` contract) makes them gold. The plan's word "gold set" means this silver set until you spot-check it.
- **Why**: the repo already burned itself once: 6,952 labels read back out of the pipeline's own table were reported as human gold (EVOLUTION 4.74). Labels here are drafted from the text only, without looking at pipeline output, which is what keeps them independent.
- **Effect**:
  - `eval/reader_gold.py` scores per-line speaker accuracy (and counts "false dialogue", spans that cover no gold line, e.g. scare quotes), persona links (Fool -> Klein), entity kind, explicit ages, and appearance facts.
  - Gold characters are matched to pipeline entities **by name and alias, never by id**, so the reference stays independent of the pipeline's inventory. The pipeline's speaker column sometimes holds the label itself ("Audrey") rather than an entity id, so an id with no entity row is read as a name; anonymous slot ids never equal a gold name, so an unnamed slot is never correct.
  - A multi-paragraph speech opens a quote in every paragraph and closes only in the last, so a quote runs to its closing mark or the end of the block.
  - Tests: `packages/pipeline/tests/test_reader_gold.py`.
- **First measurement (LotM ch7, current run-of-record DB, scratch copy)**: speakers **16/43 = 37%** (the audit's by-hand count was 16/39 = 41%; same result, different denominator since multi-quote lines are counted separately), **8** pipeline dialogue spans cover no gold line, persona links **1/4** (Fool, Justice, Hanged Man unlinked), age **0/1** (Audrey's 17 not recorded), kind 6/6 on the 6 entities that exist. This is the baseline Phase A must beat; Gate A needs speakers >= 90%.
- **Reference set written (2026-10-22)**: LotM ch1, 3, 7, 12, 14; RI ch1-5; ORV ch2-5 (ch1 is a quote-free prologue). ORV ch4 and ch5 are **partial** (`lines_complete: false`): only quotes whose speaker is clear from the text are listed, so false-dialogue is not reported for them. Unnamed speakers are labelled `_anon`, and the scorer counts them right only if the pipeline left them unnamed (pinning a crowd shout on a named hero would cast that hero's voice). ORV uses straight quotes and LotM/RI curly ones; the scorer handles both.
- **Baseline of the current run-of-record databases** (`scripts/eval/score_reader_gold.py`; silver, scratch copies):

  | Novel | Speakers | Appearance | Persona links | Kind | False dialogue |
  |---|---|---|---|---|---|
  | LotM (5 ch) | 47/136 = 34.6% | 0/14 | 2/5 = 40% | 22/25 = 88% | 27 |
  | RI (5 ch) | 27/84 = 32.1% | 0/11 | n/a | 24/24 = 100% | 4 |
  | ORV (4 ch) | 29/144 = 20.1% | 0/3 | n/a | 10/11 = 91% | 18 (ch2-3 only) |

  Gate A is speakers >= 90%, appearance >= 85%, persona links >= 90%, kind >= 95%. Every gate except RI's kind score is currently missed, and appearance is exactly zero everywhere, which confirms the audit: the extractor never reads appearance.
- **Status**: reference set and scorer done. Next is A3, the chapter reader pass.

### D11. Experiment log: can a local 7B model attribute speakers? (A3 feasibility, 2026-10-22)
Question: Gate A needs speakers >= 90%, and the current pipeline scores 20-35%. The build plan assumed a strong API model would be needed. Does local `qwen2.5:7b` get there if it is given the cast list?

What was tried, in order, on LotM ch7 (43 reference lines), with each step's result:

| Step | Change | ch7 speakers |
|---|---|---|
| 0 | Current pipeline (regex ladder + cold-start LLM, rotating anonymous slots) | 16/43 = 37% |
| 1 | One prompt per ~2,600-character window; cast list with aliases in the prompt; model asked to name the speaker of every tagged quote | 25/43 = 58% (the model silently skipped 12 tags) |
| 2 | Same prompt, but list every tag that must be answered ("exactly one answer per tag, in order") and re-ask for any tag still missing, up to 3 times | **39/43 = 91%** |

Lesson: the jump from 58% to 91% was **not** a smarter model or a longer prompt; it was making the output contract explicit and retrying omissions. Most of the "errors" in step 1 were not wrong answers, they were absent answers.

Same method, other chapters (no further tuning), local model, about 13-53 seconds per chapter on the 8 GB GPU:

| Chapter | Result | What the misses were |
|---|---|---|
| LotM ch12 (dream, Dunn) | 27/31 = 87% | the carriage driver, who is Dunn in disguise, and Dunn confused with Melissa |
| LotM ch14 (Daly) | 50/53 = 94% | two Dunn/Daly swaps in rapid two-person exchanges |
| RI ch1 | 22/29 = 76% | unnamed crowd voices attributed to "the clan head"; inner thoughts answered UNKNOWN |
| RI ch3 | 13/13 = 100% | none |
| ORV ch2 (first person) | 42/61 = 69% | in a two-person ping-pong, the model swaps Dokja and Sangah, and "I" narration is hard |

What this does and does not show (read before quoting these numbers):
- **It shows** a 7B local model can reach the 90% bar on named multi-speaker scenes when given the cast list (3 of 5 chapters at 87-100%). Because the failures are swaps within alternating two-person dialogue and unnamed crowds, they point at specific fixes (alternation constraint, an explicit "narrator is the first-person character" hint, a rule that unnamed groups are `_anon`), not at the model being too small.
- **It does not yet prove Gate A.** (1) The prototype took the cast list from the reference file. The real stage has to discover characters from the text first, and a wrong or missing cast list will cost accuracy. (2) These are scored with a throwaway script, not through the pipeline and database path the scorer measures. (3) The reference set is model-drafted silver, not human-confirmed gold. (4) Only speakers were tested; appearance and persona links are still unbuilt.
- **Cost**: local only, no cloud spend, within the $5-10 budget rule (D2).

Next (A3 proper): build the reader stage with a cast-discovery pass, the explicit per-tag contract plus omission retries, alternation and first-person hints, then write results into the database and re-score through `scripts/eval/score_reader_gold.py`.

### D12. The reader stage, speaker half (A3a, built 2026-10-22)
- **Decision**: speaker attribution moves into `reader/` (`speakers_pass.py`, `runner.py`, `quotes.py`; CLI `echotales reader --novel X [--chapters 1-5]`; `Task.READER`). A local model is shown the chapter cast and a window of tagged text and must answer once per quoted line. The old regex ladder only survives where it found an explicit "X said".
- **How the numbers moved** (real stage through the database path, scored by `scripts/eval/score_reader_gold.py`, local `qwen2.5:7b`, silver references; "-" = not yet run at that step). Each row is one change on top of the previous:

  | Step | What changed | LotM (136 lines) | RI (84) | ORV (144) |
  |---|---|---|---|---|
  | 0 | Current run-of-record databases | 34.6% | 32.1% | 20.1% |
  | 1 | First stage: cast from the database, tagged windows, retry omissions | 78.7% | - | - |
  | 2 | Count quotes typed as inner speech or crowd reaction (the classifier mistypes dialogue); retype a crowd reaction to dialogue when a named person owns it; mint a named speaker the cast lacks (Daly) but never a place | 80.1% | - | - |
  | 3 | Show the answer template with **one slot per pending tag** | **87.5%** | 50.0% | 34.7% |
  | 4 | Cast filter accepts rows with an empty `kind` (all of ORV's people were excluded) | 87.5% | 50.0% | **51.4%** |
  | 5 | Prompt: "a person only talked about is not the speaker; unnamed people -> UNKNOWN" | 86.0% | 46.4% | 54.2% |
  | 6 | On UNKNOWN, clear the old ladder's guess unless it was an explicit "X said" | 84.6% | **64.3%** | 52.8% |

- **What each lesson was**:
  - Step 3 was a pure format bug. The prompt's example showed one entry, the model copied it, and each call answered one tag, so 24 tags per run went unanswered. Showing a slot for every pending tag removed all retries (0 re-asks) and gained about 7 points on LotM.
  - Step 4 shows the cost of old data: ORV's entity rows predate the `kind` column, so a filter written for the new schema silently emptied the cast.
  - Steps 5 and 6 trade precision against recall and are mixed: they helped RI (crowd and enemy lines) by 14-18 points and cost LotM about 3. They do not fix ORV.
  - A quote the classifier called a "crowd reaction" or inner speech is a span-typing defect separate from misattribution; the reader now repairs the crowd-reaction case.
- **Still open for Gate A (speakers >= 90%)**: LotM 84.6%, RI 64.3%, ORV 52.8%. The remaining errors, read from the miss lists:
  1. **ORV, first-person narration with two people trading lines**: the model swaps Dokja and Sangah and returns UNKNOWN for many "I"-narrated lines. Needs a narrator hint and an alternation constraint.
  2. **Recurring unnamed roles** ("the academy elder", "the clan head"): the gold treats them as characters; the old code gives them a new anonymous slot on every line (the audit's slot-rotation defect). Needs one slot per unseen speaker held across lines (A6).
  3. **Identity splits**: "Fool", "Emperor", "Zhou Mingrui" and "Klein" are separate entities, so a correct reading of "Mr. Fool" can land on the wrong row. Needs persona linking (A5).
- **Not yet done**: appearance facts, ages and persona links are still 0 (A3b/A5); validators (A4) and the version stamp for the new stage are not wired in; the stage is not yet part of `echotales run`.
- **Honesty note**: these are scores on the same 14 chapters the prompts were tuned against, so they are optimistic for unseen chapters. A fresh held-out chapter per novel is needed before claiming a number.
- **Status**: speaker half built and tested (`test_reader_speakers.py`, 5 tests); gate not yet met.

### D13. The reader stage, facts half: appearance, ages, new names (A3b + A4 validators, 2026-10-22)
- **Decision**: `reader/facts_pass.py` reads each chapter for appearance traits, exact ages and new names/code names. Every claim carries an evidence quote, and is stored only if the quote is real text of the passage and the value passes a per-attribute check. It runs after the speaker pass inside `echotales reader`.
- **Why**: the audit found 0 appearance attributes for 93 LotM entities and no Fool/Justice/Hanged Man links. Appearance is stored as dated `PERSONA` attributes (open-ended from the chapter that states it), and a new name as an alias binding on the character, so `look_at`/`persona_at` consumers and the review screens can read them.
- **How the numbers moved** (LotM, silver references; appearance = 14 facts):

  | Step | Change | Appearance | Persona links | Ages |
  |---|---|---|---|---|
  | 0 | Run-of-record database | 0/14 | 2/5 | 0/1 |
  | 1 | One call for appearance + names + ages over whole 2,600-character windows | 2/14 (14%) | 5/5 | 1/1 |
  | 2 | **Appearance in its own call, with a worked example in the prompt** | 9/14 (64%) | 5/5 | 1/1 |
  | 3 | Pre-filter to sentences with body/clothing cue words (shorter, focused prompt) | 9/14 | 5/5 | 1/1 |
  | 4 | Per-attribute validators (below) | **10/14 (71%)** | 5/5 (100%) | 1/1 (100%) |

- **Lessons**:
  - Asking one JSON object for three things at once made the 7B model return empty lists for "the gray-eyed police inspector". One focused call plus a one-example prompt fixed most of the recall. The cue pre-filter did not change recall but made the calls much shorter.
  - **The first facts run stored wrong facts**, which no recall number shows: Daly's `eye_color` was "blue eyeshadow", Klein's `height_build` was "quivered", and Klein got an age of 25 that is written nowhere. So the stage now rejects or remaps these: makeup words go to `distinguishing_features`, `height_build` must contain a build word, colour keys must contain a colour word, and an age is accepted only if the number is written in its evidence quote.
  - Quote handling: a model quote that is not verbatim is repaired to the real passage sentence that states the value, never kept as the model's words. A first version "repaired" a hair-colour claim to a sentence about a black robe; repair now also requires a cue for the right attribute (hair, eyes, skin) and strips the window's block marker. The test that caught it is `test_reader_facts.py`.
- **Final measurements, current code (all three novels, local `qwen2.5:7b`, silver references)**:

  | Novel | Speakers | Appearance | Persona links | Kind | Ages |
  |---|---|---|---|---|---|
  | LotM (5 ch) | 84.6% (was 34.6) | 71.4% (was 0) | **100%** (was 40) | 88% | 1/1 (was 0/1) |
  | RI (5 ch) | 64.3% (was 32.1) | 45.5% (was 0) | n/a | 100% | n/a |
  | ORV (4 ch) | 50.7% (was 20.1) | 66.7% (2/3) | n/a | 90.9% | 0/1 |

  Only persona links on LotM meet its gate so far. Speakers (>= 90%), appearance (>= 85%) and kind (>= 95%) are still below.
- **Known remaining gaps**: a trait stated about a sibling ("his sister's brown eyes") is assigned to the narrator; appearance on RI is limited by what the cast list contains; ORV first-person two-person dialogue still swaps speakers; 27 LotM dialogue spans cover no reference line (the span classifier voices scare quotes); entity kinds such as universities typed as LOCATION instead of ORGANIZATION are not touched by this stage.
- **Status**: built, tested (`test_reader_facts.py`, 5 tests; whole suite green), not yet part of `echotales run`.

### D14. Text-only canon, and the reader stage joins the pipeline (A8 + wiring, 2026-10-22)
- **Decision**: `persona/canon.py` `CANON_APPEARANCE` and `CANON_BY_BODY` are now empty dictionaries. The reader stage is part of `echotales run` as stage `6b reader` (after resolve, before personas; `--skip-reader` opts out) and is a job kind `reader` for the Studio queue.
- **Why**: those tables held hand-typed looks that silently beat the text. For Klein they said "deep grey" eyes and a black trench coat, while chapter 1 says "Black hair, brown eyes, a linen shirt, thinly built", so every v2 render drew grey eyes. With the reader pass reading appearance with evidence quotes, the tables were not just redundant but harmful.
- **Effect**: `canon_for`/`apply_canon` keep their signatures, and the wiki tier (imported on request, dated to first appearance) still applies. A look someone wants to force must be a correction record, not source code. The old per-body test now injects its own tables (so the layering mechanism stays covered) and a new test asserts the shipped tables stay empty.
- **Left for Phase D**: `render/beat_canon.py` (hand-written RI chapter-1 beats keyed by block range) is the same problem one layer up, but it sits inside the render path that Phase D replaces, so it is deleted there rather than patched here.
- **Status**: done; whole suite green.

### D15. First-person narrator hint (ORV speakers, 2026-10-22)
- **Decision**: in a chapter whose non-quoted text has 12 or more standalone "I", the speaker prompt is told who the narrator is. The narrator is the cast member who appears in other people's quotes (two or more times) but is named at most twice in narration.
- **Why / what was tried**: ORV is told by Kim Dokja, who is almost never named in narration, and the model swapped him with Yoo Sangah through whole two-person scenes (ORV speakers 50.7%). Experiment: pick the narrator as the **most-mentioned** cast member -> it chose Yoo Sangah and made things **worse (47.9%)**. Picking by *where* the name appears (addressed in quotes, absent from narration) chose Kim Dokja and gave **58.3%**.
- **Side finding**: ORV's cast list contains "Sing Shangshong", the author of the novel-within-the-novel, because the name occurs in the text. The model offered him as the second speaker in a conversation. This is a cast-quality defect (mention-based entities, not speakers) for A5/A6.
- **Checked for regression**: LotM stays 84.6% and RI 64.3%; the hint fires only on first-person chapters.
- **Test**: `test_first_person_narrator_is_the_one_others_address_but_narration_rarely_names`.
- **Status**: ORV speakers 20.1% (original database) -> 58.3% now; gate (90%) still missed.

### D16. Role slots for unnamed speakers (A6, 2026-10-22) - built, benefit not proven
- **Decision**: when the model answers `UNKNOWN: <role>` ("UNKNOWN: academy elder"), the line gets one slot id per role per chapter, `<novel>:anon:<chapter>:<role>`, held across lines (attribution method EPITHET_SLOT, confidence 0.5). Plain UNKNOWN clears the old ladder's non-explicit guess.
- **Why**: the audit's slot-rotation defect gave a single unnamed elder a new voice on each line (RI ch4: `anon:4:s7:1`, `:2`, `:3` for consecutive elder lines).
- **Honest result**: speaker scores moved slightly down (LotM 84.6 -> 82.4, RI 64.3 -> 63.1, ORV 58.3 -> 55.6) because the scorer cannot credit a role slot as correct for a character the references name (a "carriage driver" who is Dunn; the "clan head" character). The benefit I wanted, fewer distinct voices for unnamed lines, is **not measurable on the reference set**: it has only 2-11 unnamed lines per chapter, and many are now cleared rather than slotted, so I cannot claim the voice count improved.
- **What to do with it**: kept, because holding one slot per role is the right behaviour and costs nothing; but it is not counted as progress toward Gate A. A real check needs the voice stage to cast these slots and a listening test.
- **Process note**: two commits (`4f44257`, `db61bc9`) were pushed with a failing narrator test because the test command was piped through `tail`, which hid pytest's exit code. The fix is `e9abbc9`; since then test runs are checked by exit code before any push.
- **Test**: `test_an_unnamed_speaker_with_a_role_gets_one_stable_slot`.

### D17. The kind gate counts a place and an organisation as the same side (2026-10-22)
- **Decision**: the reference scorer accepts either LOCATION or ORGANIZATION for a reference entity labelled location or organisation. Person-vs-non-person is still strict.
- **Why**: LotM scored 88% kind accuracy only because three institutions (Tingen University, Tingen Technical School, Backlund University) were typed LOCATION where my references said organisation. A university is both, so that was a disagreement about wording, not a mistake that matters. What the gate protects against is a non-person being cast a voice, as "Chanis Gate" (a place) did for 18 lines.
- **Result**: kind accuracy 25/25 (LotM), 24/24 (RI), 11/11 (ORV), so the kind gate (95%) now passes on all three.
- **Caveats**: the sample is small and is measured only over entities the pipeline created, so a person the pipeline never made is a recall miss (counted under speakers and persona links), not here; the references skip `creature` and a non-person that speaks is checked by the speaker pass, not by this number. This change loosened the scorer, so the improvement is not a model improvement, and it is logged separately for that reason.

### D18. Held-out chapter, and written text is not speech (2026-10-22)
- **Decision**: (1) keep one reference chapter that no prompt was tuned on (`data/gold/reader/lord-of-the-mysteries-ch21.json`, `"held_out": true`) and report it separately; (2) a quote that opens with a date ("18th November.", "1184, 1st January.") is a written entry, not speech, and a quote the model calls NONE is moved from dialogue to narration.
- **Why**: every number in D11-D16 was measured on chapters the prompts were tuned against, so they are optimistic. And LotM ch21 quotes nine of Emperor Roselle's diary entries, which the old pipeline voiced as dialogue; the 7B model did not answer NONE for them even though the prompt allows it.
- **Held-out result** (LotM ch21, 37 reference lines, never used for tuning):

  | | Original database | Reader stage | Reader stage + written-text rule |
  |---|---|---|---|
  | Speakers | 18/37 = 49% | 32/37 = 86% | 32/37 = 86% |
  | False dialogue spans | 13 | 13 | **5** |
  | Appearance | 0/3 | 0/3 | 0/3 |

  So the speaker gain generalises (49% -> 86%, close to the 84.6% on the tuned LotM chapters), which is the evidence I did not have before. Appearance did **not** generalise on this chapter: Leonard Mitchell had no entity in the database (the old pipeline first saw him in chapter 39) and the facts pass could not resolve him, which matches the "stated about someone not yet in the cast" gap already listed.
- **Remaining misses on ch21**: the model attributes two of Old Neil's lines to Klein, a joint line ("in unison") has no single speaker, and "Midnight Poet" became its own role slot instead of Leonard.
- **Tests**: `test_dated_written_entries_are_not_speech_and_leave_dialogue`, `test_a_none_answer_retypes_dialogue_to_narration`.

### D19. The ablation series: what moved the speaker score, and what did not (2026-10-22)
- **Rule adopted** (owner, after D16-D18): never read a gain off the chapter a change was tuned on. `scripts/eval/reader_ablation.py` runs the whole stage on **all 16 reference chapters of all three novels** from a fresh copy of each run-of-record database, writes `data/eval/reader/<label>.json`, and `compare` prints every chapter's change and flags any that got worse. One-chapter swings of about 5 lines happen from prompt wording alone (v2 and v5 have identical totals, 282, but differ by up to 7 lines on single chapters), so a change counts only if the 401-line total moves by more than about 10 and the big chapters agree.
- **The series.** Speakers = correct of 401 reference lines; appearance of 31 facts. "qwen" = `qwen2.5:7b`, "gemma" = `gemma2:9b`, both local.

  | Run | Change (cumulative) | Model | Speakers | Appearance | Chapters worse |
  |---|---|---|---|---|---|
  | v0 | code as of D16 | qwen | 277 (69%) | 17 | - |
  | v1 | canonical names claim a name before aliases; `UNKNOWN: <cast name>` resolves to that person | qwen | 276 | 18 | 1 |
  | v2 | + chapter-wide role -> name pass | qwen | 282 (70%) | 18 | 2 |
  | v3 | same code, **model swapped** | gemma | **330 (82%)** | 21 | 3 |
  | v4 | + titles as persistent entities, cast by story-time validity | qwen | 279 | 19 | 4 |
  | v5 | + roles must use words found in the chapter; novel-specific prompt examples removed | qwen | 282 | 19 | 7 |
  | v6 | + honorific suffixes stripped when matching names | qwen | 291 (73%) | 19 | 1 |
  | v7 | v6 code | gemma | 319 (80%) | 20 | 6 |
  | v8 | + only office words ("elder", "head", "captain"...) become persistent title entities | gemma | 339 (85%) | 21 | 4 |
  | v9 | + concrete example in the names prompt | gemma | 341 (85%) | 21 | 0 |
  | v10 | + naming-cue focus with the following lines | gemma | 340 | 21 | 1 |
  | v11 | + wrong evidence pointer for a new name repaired to the sentence naming it | gemma | 339 (85%) | 21 (persona links 4/5) | 1 |

- **What actually moved the number, in order of size**:
  1. **The model** (v2 -> v3): +48 lines, by far the largest single lever. It is not a clean "more parameters" effect: `gemma2:9b` is a different family from `qwen2.5:7b`, it is 2.75x slower (1,665 s vs 604 s for the 16 chapters), it did **not** win everywhere (ORV ch3 -5, RI ch4 -2 in v3), and it regressed persona links until the prompt bugs below were fixed.
  2. **Honorific handling** (v5 -> v6): +9 lines, all in ORV ch5 (and -1 in ORV ch3), LotM and RI byte-identical. "Yoo Sangah-ssi" was not recognised as Yoo Sangah, so a **duplicate entity** was minted and later chapters answered with it.
  3. **Restricting persistent title entities to offices** (v7 -> v8): +20 lines on gemma. v7 had *minted* "dokkaebi" (a creature), "grandmother", "old man", "first man" as persistent entities; they entered later chapters' cast lists and gemma gave **12 of the narrator's lines in ORV ch5 to "dokkaebi"** (32 -> 18 on that chapter, hidden inside a 2-point total dip). The title design was right in principle; its unrestricted version was harmful, and only the per-chapter table showed where.
  4. **Role reconciliation** (v1 -> v2): +6 lines, uneven by novel (LotM +6, ORV +2, RI -2).
- **What did not move it, though the trace said it would**: the name-matching fixes (v0 -> v1: 277 -> 276). The trace showed real mechanisms ("UNKNOWN: Dunn Smith" becoming a role slot; an alias "Welch" on Klein stealing an answer), but they were rare in the reference chapters. A correct fix is not the same as a large one.
- **Two prompt bugs that only showed with the stronger model**: (a) my prompt listed "the clan head" as an example role, and a model wrote it into an ORV chapter that has no clan head (now removed, and a claimed role must be made of words found in the chapter); (b) the names prompt showed `"quote": "..."` as a placeholder, and gemma copied the literal `...` as the evidence quote for "Justice" and "The Hanged Man", failing the quote check (now a concrete example).
- **Persona-link misses are partly model variance in the evidence pointer.** On some runs gemma named Zhou Mingrui's new identity correctly but quoted an unrelated line ("It's nothing.") as proof. The validator rightly rejected it; the stage now repairs the pointer to the real passage sentence that contains the new name. The scorer also no longer treats "Mr. Fool" and "The Fool" as different code names (article or title only).
- **Honest scope**: the prompts and fixes above were written while looking at these same 16 chapters. The held-out LotM chapter (ch21) is the only one never used for tuning and it scores 35/37 (95%) on gemma, but it is one chapter of one novel. Nothing here shows the same holds for RI or ORV on unseen chapters.

### D20. Titles are transferable aliases with two clocks (owner's design point, built 2026-10-22)
- **Decision**: a title ("the clan head", "elder", "first elder") is a **transferable alias** of a person, not an anonymous crowd slot and not a second character. It has a **story interval** (when the person actually held it, which can reach back before the reader learned it) and a **knowledge time** (when the book told the reader). Before the holder's name is learned the reader sees the title; afterwards the name, with the title noted. A title can move to a new holder (the old interval closes, the earlier lines stay attributed to the old holder; transfer is not retraction), and one person can hold several titles over time (elder, then first elder).
- **Why**: I first treated "clan head" as an unnamed role and called the reference's `clan_head` character an artifact. That was wrong against the project's own research, which already has this machinery: `resolve/title_holders.py` binds RI's "the clan head" to Gu Yue Bo with story time from chapter 1 and knowledge time at chapter 6, so the clan head's first five chapters of lines have a consistent voice.
- **What was built**: `build_cast` includes a person when an alias is valid in story time at the chapter and appears in its text, shows them by title until the name is learned (a later name never appears in an earlier prompt), and resolves a repeated title to whichever holder's interval covers the chapter. A role with no known holder becomes a persistent **title entity** (only for office words, see D19) that a later chapter can name through an identity claim. The RI reference lists "Gu Yue Bo" and "the clan head" as aliases of the same character.
- **Tests**: `test_a_title_is_shown_before_its_holders_name_is_known_and_the_name_after`, `test_a_title_follows_its_holder_through_a_handover`, `test_one_person_can_hold_several_titles_as_they_advance`, `test_only_offices_become_persistent_title_entities`.
- **Not done**: no step yet closes a holder's interval when the *reader pass* sees a handover (that remains `title_holders.py`'s job in the resolve stage); "previous/next/fourth-generation" titles are not handled in the reader; the faithfulness check (truncate-and-rebuild) has not been run on the reader stage.

### D21. A reference error, found by reading the text (ORV ch3, 2026-10-22)
- The failure taxonomy on the best run showed 27 lines where the model named a speaker the reference called unnamed (RI 13, ORV 14). Eight were ORV ch3 "Han Myungoh". Reading blocks 46-66 in full showed the entire offer scene is Department Head Han (named Han Myungoh in ch5): four lines I had marked unnamed from a truncated view were his, one of his lines (54.1) was missing, and the reference character lacked the alias "Han Myungoh".
- **Corrected**: those four lines, the missing line and the alias. This changes the reference (ORV 144 -> 145 lines), so the ORV ch3 numbers in earlier rows of D19 were scored against the old labels and are not strictly comparable.
- **Effect on the best run (v11 outputs, re-scored, no model rerun)**: LotM 165/173 (**95.4%**, passes the 90% gate), RI 64/84 (76.2%), ORV 113/145 (77.9%).
- **Why it matters for trust**: this is exactly the failure mode the reference-set warning describes. A reference drafted from truncated views understates the model, and the model's disagreement is a prompt to re-read, not proof either way. The remaining 19 "named but expected unnamed" lines (RI 13, ORV 6 after the fix) have **not** been re-checked against the text and could be reference errors in the same way.

### D22. The default reader model is now `gemma2:9b` (supersedes the model half of D2, 2026-10-22)
- **Decision**: `Task.READER` defaults to local `gemma2:9b`; `ECHOTALES_READER_MODEL` overrides it. Still local ollama only, no cloud spend, so the local-only rule and the $5-10 budget are untouched.
- **Why**: measured on the same 16 reference chapters, same code: 330 vs 282 correct speakers (82% vs 70%), with the held-out LotM chapter at 95%. It fits the 8 GB card. Cost: about 2.75x the time (roughly 27 minutes vs 10 for the 16 chapters; about 49 s per chapter on `qwen2.5:7b` in the full-volume LotM run, so roughly 2 minutes per chapter on gemma, or about 80 minutes for a 40-chapter volume).
- **Not shown**: that a still larger model would do better, or that gemma holds up on unseen chapters of RI and ORV. `qwen3:8b` and `llama3.1:8b` are installed and were not tried.

### D23. Phase B: the review gate and the locked bible (built and browser-verified 2026-10-22)
- **Decision**: a person reviews what the reader flagged, then locks a versioned bible; a real render may only read a current lock. Built as `pipeline/review_gate.py` (read models, lock, guard), a `bible_lock` table, four routes, and a Studio tab "Bible review" (`webview/src/components/BibleReview.js`) with three sub-tabs.
  - **Lines to check**: `GET /api/novels/<id>/review/lines`. Queues unnamed lines, role slots and low-confidence guesses, ranked by **how many lines one decision covers** (lines in the chapter sharing the same speaker slot), then by confidence. A named model guess is only listed in the audit view (`?all=1`), because listing every guess would defeat a bounded queue (non-negotiable 7). Fixing a speaker uses the existing corrections API, so corrections stay records that re-apply after re-extraction.
  - **Character timeline**: `GET .../characters/<id>/timeline`. Every look version and every name or title with its evidence quote, and for names **both clocks**: `story_from` and `learned_chapter`, so "held since ch 1, learned ch 6" is visible (D20). Repeated identical bindings are shown once (the LotM database holds "Klein Moretti" three times).
  - **Lock**: `GET .../bible`, `POST .../bible/lock`. A lock stores a digest of what a render reads (who speaks each quoted line, every attribute and alias by learned chapter, entities), **per chapter**. A later edit changes exactly its chapter's digest, so the status says which chapters changed and so which episodes need to render again. A stale build (version stamp, D8) cannot be locked.
  - **Render guard**: a real (non-stub) engine now needs the version stamp **and** a lock with no edits since (`_stale_build_refusal`). The stub stays exempt.
- **Verified, not just asserted** (real server, real LotM output of the v11 run, copied to `data/scratch/reruns/lotm_review_demo.db`, driven in a browser):
  1. The queue returned 1,251 lines for LotM and the UI rendered them in the existing violet look.
  2. Lock v1 recorded 1,803 lines, 585 attributes, 2,341 aliases, 95 entities.
  3. One speaker correction through the corrections API, applied, made the bible dirty with `changed_chapters = [17]`, exactly the edited chapter.
  4. A real-engine render was refused: "has edits since bible v1 (chapters 17); lock a new version first." (HTTP 409).
  5. Lock v2 reported `changed_chapters = [17]`; the Lock tab then listed v1 and v2 and offered "Lock bible v3".
- **Defects found only by the browser check** (the 129 mocked Jest tests passed without seeing them): the timeline repeated identical alias rows; quoted lines displayed doubled quote marks because the text already carries its own. Both fixed. Evidence quotes in the timeline are cut mid-sentence by the 200-character truncation; left as is.
- **A finding about the review burden**: 1,251 lines to check across 40 chapters is about 31 per chapter, far above the target (about 15 minutes of review per 10 chapters). That is because only 6 chapters have been through the reader; the rest still carry the old low-confidence turn-taking guesses (confidence 0.6). A fully reader-processed volume should queue far fewer, but that is **not measured yet**; on the full-volume LotM run of 40 chapters the stage named 1,285 of 1,518 quotes, leaving about 233 unnamed or role-slot lines to review, roughly 6 per chapter.
- **Not done in Phase B**: a cast board that merges entities from this screen (the existing Review page already has merge, reassign, retype and flag), voice screens with upload and record (needs the voice stage, Phase C), a places and props screen, and a lock step that records *which episodes* were built from which bible version (episodes do not exist yet).
- **How it was built**: the Python side by me; the React side by a subagent against a written API contract. The subagent hit a rate limit before reporting, so I verified its saved work myself (129/129 Jest tests, the build, and the browser run above) instead of trusting a summary.

### D24. Spoiler-safety audit of the reader stage, and re-adjudicating the disputed lines (2026-10-22)
- **What the audit can and cannot do.** A true truncate-and-rebuild is not possible for this stage alone: its cast is drawn from the resolve-stage database, built over the whole volume, so any dependence on later chapters would come in as a *selection* leak, the kind the research shows a truncated rebuild of one stage cannot expose (FORMAL P10). `scripts/eval/reader_faithfulness_audit.py` measures the one selection channel the reader opens on purpose (D20): a quoted line at chapter k attributed to an entity whose name is first learned after k. That is only safe if the reader at k is shown the title the book used then, not the later name.
- **Results on the v11 outputs** (reader-attributed lines):

  | Novel | Lines | Name already known | Ahead, servable by a title | Flagged as exposed | Reader facts learned later than they start |
  |---|---|---|---|---|---|
  | LotM | 183 | 180 | 0 | 0 | 0 |
  | RI | 65 | 49 | **8** | 0 | 0 |
  | ORV | 153 | 133 | 0 | 11 | 0 |

  - RI's 8 are the clan head at chapter 1, attributed to Gu Yue Bo, named from chapter 6: the designed case, safe because the label to show at chapter 1 is the title.
  - ORV's 11 flags are all chapter 3 lines attributed to "Han Myungoh" (entity first attested at chapter 5). On inspection this is a **false positive of the audit caused by a resolve-stage defect**: chapter 3 names him itself ("It was Han Myungoh, department head of the finance team", block 53), so no early name is shown; the entity's first-attested chapter is simply wrong because mention detection missed that sentence.
  - **What this does not show**: that the reader stage is faithful in general. It shows the facts it writes are stamped at the stating chapter (0 violations) and that the title-before-name channel behaves as designed on the cases present. The Read page and the review screen still show `canonical_label` for an entity, so serving the title instead of a not-yet-learned name at the display layer is **not built for the reviewer view** (the Read page's `build_reader_cast` does its own gating).
- **Re-adjudicating the 24 lines where the model named a speaker the reference called unnamed** (RI 13, ORV 11 after the earlier ORV ch3 fix). Read against the text: 22 are the model being wrong (attackers named as the clan head or Fang Zhi, "Someone said..." given to Fang Zheng, a crowd's "Wow, so pretty!" given to named elders, a creature's lines given to Ren Zu, commuters and an unnamed actor given to Han, a crowd shout given to Lee Hyunsung). **One reference error found and fixed**: RI ch4 block 31 ("...the clan head said with a deep sigh"), which I had labelled unnamed. **One left unresolved**: RI ch1 block 71 ("Then this is good night, please take care.") follows the elders' replies with no speaker named; the text does not decide it, so it is neither relabelled nor counted as settled.
- **Effect**: RI speakers 65/84 = **77.4%** (was 76.2%). Reference errors found by the model's disagreements across D21 and D24: 2 of about 40 disputed lines, so the disputed set was mostly model error, which is the more reassuring answer to the question of whether the remaining gap is a labelling problem.

### D25. Phase C step 1: a real local image worker on NoobAI, no CPU offload (2026-10-22)
- **Decision** (owner): build the real image backend on NoobAI XL first and judge the pictures, then free storage and try the licence-clean models (Z-Image Turbo, SDXL base; airllm if it helps). NoobAI is non-commercial (D7), so this is for development and review only; the model sits behind the worker contract so it is a config change to swap.
- **The recipe that fits the 8 GB card without CPU offload** (the old engines used `enable_model_cpu_offload`, which the owner ruled out after the 2026-10-02 RAM spike):
  1. Load a text-encoder-only pipeline (`unet=None, vae=None`) straight onto the GPU (`device_map="cuda"`), encode every prompt, free it.
  2. Keep only the UNet and VAE resident (4.95 GiB) and denoise from the cached embeddings.
  3. Decode the VAE in 256-pixel tiles. This was the real obstacle: SDXL's VAE is upcast to float32 to decode, doubling its activations, and a fully resident pipeline died in `vae.decode`. Two earlier attempts failed (everything resident; encoders freed but default 512 tiles).
  - **Measured**: peak **5.36 GiB** VRAM, about **22 s per 28-step image** at 832x1216 or 1024x1024, system memory watched by a watchdog that never fired. Enabled with `ECHOTALES_IMAGE_WORKER=noobai`; the stub stays the default, so CI never touches a GPU. A request over about 1.1 MP is scaled down (the old 1920x1080 sheet becomes 1344x768). The worker refuses to start if under 6.5 GiB of VRAM is free.
- **Three bugs this exposed in earlier work** (all fixed and tested):
  1. `bible_at` never returned any extracted look: the reader writes to `<self>:body1` (what `persona_at` answers) but `bible_at` asked for `<self>:default`, so every character's attributes were empty. Phase B's and Phase C's inputs were silently missing the whole of Phase A's appearance work.
  2. The turnaround prompt wrote every bible attribute into the image prompt as `key: value`, including `big_five`, `archetype`, `reference_image_path` and digests.
  3. A look about "her" was stored for a male character (Melissa's "her skin remained lustrous" became Klein's skin tone). A pronoun/gender check now rejects it.
- **What was generated**: six LotM characters (Zhou Mingrui, Dunn Smith, Daly, Leonard Mitchell, Melissa, Audrey Hall), each a 3-view sheet, three view crops, an expression sheet and seven expression crops (72 images, about 268 s per character), from a clean database re-read by the reader on the reference chapters, in `data/scratch/phase_c/lotm/contact_*.png` (disposable).
- **What the pictures show, honestly** (judged on Klein and Daly):
  - **Fidelity to the text is real.** Klein: black hair, brown eyes, loose linen-type shirt, slim build, no invented skin tone. Daly: emerald eyes, black robe, blue eyeshadow and blush, all stated in the book and all present. A trait the book does not state is not drawn on purpose.
  - **Identity is not held across crops.** The 3-view sheet is consistent, but the book never gives Daly's hair colour, so every separate image invents one: the expression crops show blonde, green, grey and dark blue hair. The same would happen with any unstated trait. Expression crops also sometimes come back as multi-face grids instead of one portrait.
  - **Cause**: text-to-image alone cannot hold an identity; that is what the consistency plan (approved reference, then reference-conditioned generation) and the plan's Qwen-Image-Edit are for. A cheaper first step that stays within NoobAI: when the book leaves a trait open, **decide it once per character, record it as "assumed" with a visible flag, and let a reviewer lock it** (the Reference images screen in the plan), then include it in every prompt.
- **Not done**: reference-conditioned generation, the keyframe QA gate with real face and background checks, locations, and the other models.

### D26. One fixed art style; the genre decides clothing and era (owner, 2026-10-22)
- **Decision**: every novel is drawn in the same art style (Chinese anime / donghua: `FIXED_ART_STYLE` in `persona/genre.py`). What changes with the book is the clothing, the era and the setting, taken from the genre profile. A new `wardrobe` (and `wardrobe_female`) field on each genre carries the clothes; the old per-genre "gothic engraving" style tags are no longer used for character sheets, because an art style is not a genre.
- **Why**: the first Phase C sheets (D25) hard-coded `visual_genre="anime"` and ignored the genre system entirely. LotM's Klein came out in a modern white shirt and black trousers. Owner: "absolutely trashy, the genre is not taken into account at all, it was a 100x better before".
- **What the prompt now does**: priority order is identity from the book (hair, eyes, build, the attire the book names), then the genre wardrobe, then the fixed art style, then framing. The genre's `negative_culture` goes in as the negative prompt. Traits the book leaves open (hair, eyes, skin) take the genre's default **in every image of that character** and are listed on the contact sheet as "assumed by the genre", so an assumption is never mistaken for a fact from the text and one character is not redrawn with a new hair colour each time.
- **Result on LotM (Klein, Daly)**: Victorian tailcoat, waistcoat, cravat and gloves for Klein with black hair and brown eyes from the text; a black Victorian dress with corset and gloves for Daly with her emerald eyes and the blue eyeshadow and blush the book states, and the same brown hair in all 12 images (previously blonde, green, grey and dark blue). Remaining: the sheet prompt invites fake handwriting around the figures (negatives added), some expression crops are multi-face grids, and the book's "hooded black robe" for Daly became a dress under the genre wardrobe.
- **Token limit**: the worker now drops whole low-priority clauses to fit CLIP's 77 tokens instead of cutting silently. The limit belongs to the CLIP text encoder of SD1.5/SDXL-family models, not to model size; Z-Image, Qwen-Image and FLUX.2 use language-model encoders with hundreds of tokens and natural-language prompts, so the budgeting code is specific to this model family.
- **Visual reference**: the owner pointed out that LotM has an anime adaptation to calibrate looks. I cannot watch video and the adaptation's designs are its own copyrighted work, so stills the owner supplies would be used only as a private check on era, wardrobe and mood, never as canon to copy; the book's text stays the source of each look.

### D27. Pivot: EchoTales is a product, not a research project (owner, 2026-10-24)
- **Decision**: the one sentence that must become fully true is "Drop in any EPUB -> review a short queue of uncertain lines -> get a full-cast audiobook (M4B with chapter markers), plus an illustrated motion-comic for any chapter the user picks." Audio is the main deliverable, visuals are secondary, everything runs locally (ollama + local GPU).
- **What changes**: no paper and no new human annotation or gold labelling. Gate A (D1) is no longer a blocker; the silver set stays only as a regression check in `scripts/eval/reader_ablation.py` (a change must not make it worse) and the reader is no longer prompt-tuned against it. PDNC speaker scoring is optional and skipped if it turns into work. Gate C's numeric thresholds are replaced by two rules: every score shown in the UI is actually measured, and QA fails closed.
- **Dropped**: Phase E (lip-sync, motion transfer, LTX montages, LoRAs), RunPod/hosted workers, AI video generation unless a local model fits the GPU after everything else, series planner and recap openers, and the research-only items (reader faithfulness re-run, re-adjudicating the 19 reference lines). Research docs stay where they are until the packaging step moves them to `docs/archive/`.
- **New order**: (1) honesty pass: fabricated QA scores, fallback to unrelated images, fail-open video QA, swallowed LLM errors, open CORS, solid-colour worker stubs, dead code; (2) generalise to unseen books by removing novel-keyed tables and acceptance-testing on a public-domain EPUB with no code changes; (3) audiobook end to end (upload, review, lock, casting, Chatterbox, M4B, resumable per chapter, guided first lock); (4) visuals for one chosen chapter; (5) packaging: setup script, CI, ruff, route split, licences, archive course files, README as a product page using public-domain demos only.
- **Why**: the owner wants a usable tool, not a result. A code review found the UI showing numbers that were never measured; that is worse for a product than a missing feature.
- **In flight when decided**: the reader's subject-and-pronoun check on appearance facts (finished and committed as the last research-era step) and the course Project Document, which stays as is and moves to the archive in step 5.
- **Status**: step 1 next.

### D28. Journal paper resumed, with a 48-case human check (owner, 2026-10-30)
- **Decision**: the journal manuscript (`docs/paper/journal/`) is being finished for submission, and the disclosure labels got a small human check, which D27 had ruled out.
- **What changes**: D27's "no paper and no new human annotation" no longer holds for this one track. The product pivot is unchanged for the rest of the code. The check has three author-annotators, 48 cases and 4 repeats (`data/eval/validation/disclosure_labels/`, scored by `scripts/review/score_disclosure_validation.py`).
- **Departure from the protocol**: the first author adjudicated, and drew on knowledge of the books, where `VALIDATION_PROTOCOL.md` asked a third author to adjudicate from the passages alone. The paper says so and reports the raw pairs beside the adjudicated labels. A third-author re-adjudication of the 11 rulings is still open (HANDOFF).
- **Why**: the model-judged disclosure rates were the paper's weakest evidence, and a reviewer would ask for a human check.
- **Status**: paper built and committed locally (EVOLUTION 4.130).

## 3. Documentation policy

### D9. Few, living docs
- **Decision**: keep a small set of maintained docs and archive the rest; no new loose docs. Entry points: `README.md`, `CLAUDE.md`, `docs/README.md` (index), `docs/HANDOFF.md` (open work), `docs/EVOLUTION.md` (history), `docs/design/decisions.md` (this file), `docs/design/architecture.md`.
- **Why**: dozens of small docs drift out of date and cannot be trusted.
- **What was done (2026-10-22)**: tracked markdown went from about 190 files to 123. Research docs were **merged, not archived** (your call: the research gave good results), into one file per topic under `docs/research/` (table in `docs/research/README.md`); 16 results docs became 3 under `docs/results/`; duplicate root files (`RUN_STEPS.md`, `Demo_Video_Script.*`) were removed (copies live in `docs/paper/project_doc/`); `docs/status/REFACTOR_REPORT.md` moved to `docs/archive/`. Each merged section keeps the original text and names its old path, and the originals remain in git history.
- **Left alone on purpose**: the 84 files in `docs/research/preregistrations/` (hash-manifested locked records), `docs/research/PREFIX_FAITHFULNESS/`, `PAPER/`, `experiments/` and `technical_contribution_probes/` (read by code or scripts), and `docs/paper/`.
- **Known cost**: relative links inside the locked preregistrations that point at a merged file are now stale; they are records, so they were not edited. Search `docs/research/README.md`'s table to find where a file went.
- **Status**: done.

## 4. Open questions
- Whether the local 7B model reaches Gate A, or the reader must move to a hosted model (needs your approval; see D2).
- Overwriting run-of-record databases in `data/db/` (rebuilds go to `data/scratch/reruns/` first).
- Which model caches to delete, one by one.

## 5. Maintenance rule
Whenever a decision is made or reversed, or a phase step lands, add or update an entry here in the same turn, with the measured result when there is one. Bug-level detail goes to `docs/EVOLUTION.md`; open work to `docs/HANDOFF.md`.
