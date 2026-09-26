# Annotation datasets — provenance, protocol, and what may be claimed from them

**Written 2026-09-24.** The authoritative description of what is in
`data/gold/`, how it was produced, and what a number computed from it is
allowed to say.

> ## The one-sentence version
>
> **There is no human-annotated gold in this repository.** Every record is
> model-drafted. The usable subset is an **LLM-derived silver reference set**,
> and every metric computed from it carries the banner
> `SILVER -- LLM-derived reference set (Claude), not human gold; no IAA`.

---

## 1. Three tiers, and why the middle one exists

| Tier | Definition | Count (RI) | May be reported as |
|---|---|---:|---|
| **CONFIRMED** | A person adjudicated the record individually (`confirmed=True`, `confirmed_by` set, `review_depth=PER_RECORD`) | **0** | a result |
| **SILVER** | Model-drafted by a family *other* than the one under test, reading chapter text | **3,889** | a measurement against a silver reference set, always banner-labelled |
| **CIRCULAR** | Drafted by `gold-auto-builder`, i.e. `SELECT`ed from the pipeline's own `mention` table | **4,422** | nothing, at any confirmation level |

`GoldSet.confirmed_only` / `.silver_only` / `.circular` implement these.
`confirmed_only` is empty and stays empty; the tier exists so the honest number
remains visible rather than being quietly redefined.

**Why SILVER is not gold.** No person adjudicated it. There is no
inter-annotator agreement, because there is one annotator and it is a language
model. It is evidence — a second opinion from a different model family than
the system under test (`qwen2.5:7b`), produced by reading the novel rather than
the database — and it is weaker than human annotation. Both halves of that
sentence must survive into any paper.

**Why CIRCULAR is worthless.** `generate_gold.py::_extract_gold_from_db` runs
`SELECT text, target_id, ... FROM mention WHERE target_id IS NOT NULL`. Gold
built that way *is* the system's output, so scoring against it measures the
system against itself. That produced the retraction in `docs/EVOLUTION.md` 4.74.

---

## 2. File inventory

| File | Records | Chapters | Drafter | Tier | Tracked |
|---|---:|---:|---|---|---|
| `reverend-insanity.jsonl` | 7,879 | 198 | mixed | 3,457 silver / 4,422 circular | yes |
| `reverend-insanity-c1-c5.jsonl` | 343 | 5 | `claude-opus-5` | silver | yes (since 2026-09-24) |
| `reverend-insanity-hardcases.jsonl` | 89 | 51 | `claude-sonnet-5-gold-hardcases` | silver | yes (since 2026-09-24) |
| `lord-of-the-mysteries.jsonl` | 6,756 | 213 | `gold-auto-builder` | **100% circular** | yes |
| `omniscient-readers-viewpoint.jsonl` | 4,836 | 186 | `gold-auto-builder` | **100% circular** | yes |
| `reverend-insanity-c1-c5.toml` | 26 identities | 1–5 | `claude-opus-5` | silver source | yes |
| `reverend-insanity-c1-c60-extended.toml` | 22 surfaces | 1–60 | `claude-sonnet-5` | silver source | yes |
| `lord-of-the-mysteries-c1-c3.toml` | 24 identities | 1–3 | `claude-opus-5` | silver source | yes |
| `_unusable/reverend-insanity-c1-c50.jsonl` | 6,952 | 198 | `gold-auto-builder` | **quarantined** | README only |

The two `.jsonl` files added to tracking on 2026-09-24 were previously
gitignored while all three *circular* files were tracked — the repository was
committing the annotations that cannot score the pipeline and excluding the
only two that can.

**TOML vs JSONL.** TOML is the authored artifact, grouped by identity
(`[[identity]] name/kind/surfaces`, `[[not_entity]] reason/surfaces`). JSONL is
the machine expansion, one record per occurrence, produced by
`eval/draft.py::expand_draft` with a word-boundary regex over the ingested
chapter text and a ±60-char real context window.

---

## 3. Record schema

```json
{"novel_id": "demo", "chapter": 1.0, "offset": 42, "surface": "Name A",
 "identity": "Person A", "kind": "character", "alias_type": "RIGID_NAME",
 "context": "<~70 chars of source text around the offset>",
 "provenance": "model", "drafted_by": "claude-opus-5", "confirmed": false,
 "confirmed_by": "", "review_depth": "none", "note": ""}
```

- `chapter` is a **float ordinal**, not a date. Nothing here carries a date.
- `offset` is **chapter-absolute**, over the `"\n\n"`-join of story blocks.
  `Mention.offset` in the database is **block-local**. The translation lives in
  exactly one place, `coref_score._block_starts`; writing it a second time has
  caused two documented bugs.
- `kind` ∈ `character, location, item, organization, not_an_entity`.
- `context` stores a short evidence snippet, never chapter text in bulk — the
  CoNLL/OntoNotes convention, so annotations are shareable without
  redistributing copyrighted novels.

### Mention key

`(novel_id, chapter, offset, normalised_surface)`. The surface joined the key
on 2026-09-24. Before that, a word-boundary **prefix** surface collided with
the longer surface it prefixes — both start at the same offset — and one
silently overwrote the other. In `reverend-insanity-c1-c5.jsonl` that destroyed
**55 of 343 records (16%)** at load time, with no error anywhere.

---

## 4. Adjudication decisions

Recorded because the project's rule is that changing what an annotator asserted
is the owner's call, not a maintainer's.

**Prefix collisions (owner decision, 2026-09-24): fix the key, keep every
annotation.** 14 collisions in `c1-c5.toml`, 13 in the extended draft, 5 found
while drafting LOTM. Both records at such an offset are *correct* — "Gu Yue"
the clan and "Gu Yue Fang Yuan" the person genuinely both begin there. The
destruction was in the data model, not the data. `_prefix_collisions` is now
advisory rather than fatal, and both drafts expand again.

**Human annotation (owner decision, 2026-09-24): not performed.** The research
pipeline is explicitly not blocked on human IAA. The silver tier is used
instead, labelled as such everywhere.

---

## 5. Known defects and ambiguities

Found by `eval/validate_gold.py`, left in place, flagged rather than edited.

1. **770 spans shifted by +1**, all in `reverend-insanity.jsonl`, all
   `gold-auto-builder`, all chapters 61–199. The silver subset is clean —
   3,457 of 3,457 spans verified against chapter text. It does not affect
   scoring (the ±8-char match tolerance absorbs it) but it is a real defect in
   the circular tier and one more reason not to use it.
2. **One contract violation** in hardcases: `ch3@7926 'the Awakening Ceremony'`
   is typed `not_an_entity` yet carries an identity. **Needs your
   adjudication** — either the kind or the identity is wrong.
3. **One within-chapter surface conflict** in hardcases: `ch32 'fang zheng'`
   maps to both `Fang Yuan (hypothetical misidentification)` and
   `Fang Yuan (the servants' guess is wrong)`. Almost certainly the same
   intended referent written twice; the `identity` field is carrying prose,
   which makes two notes look like two identities.
4. **Klein / Zhou Mingrui** (LOTM) is annotated as **one referent**, with the
   drafter's dissent recorded in the TOML: a partition that split them fails on
   *"Melissa gave her elder brother a piercing stare"*, where the brother is
   Klein and the person stared at is Zhou Mingrui. In this project's own
   vocabulary the split is **Self vs Persona, not two Selves** — and the gold
   format annotates coreference over mentions, which has no way to express
   that. A reviewer may reasonably overturn it.
5. **Deities are typed `character`**, deliberately. `MentionKind` has no deity
   value; they are single named referents rather than places or organizations,
   and `not_an_entity` would be false since the text treats them as persons
   with will. Their churches are separate `organization` entries.
6. **`alias_type` defaults to `RIGID_NAME`** for records drafted before the
   field existed. That default is a known undercount, not a measurement.
7. **Span drift: 7 silver records fall outside chapter 1 on the rerun
   database** (`data/scratch/reruns/ner-window-ri.db`, measured 2026-09-25). "3,457 of
   3,457 verified" in item 1 was checked against the older
   `data/db/` database and remains true there. The rerun's
   ingest classifies chapter 1's three closing author's-note blocks
   (*"This novel has another name, Daoist Gu."*) as `TRANSLATOR_NOTE`, where
   the older ingest had them as `PROSE`, so `story_text` shrinks from 13,100 to
   12,484 characters. The 7 affected records (`ch1@12522`–`ch1@13089`, all
   `'Gu'`) annotate words *inside that note* — they were never diegetic
   mentions, and the new exclusion is the correct behaviour. Every other
   chapter-1 record precedes the notes and is unaffected. Effect on scoring:
   those 7 are unmatchable and count as unresolved, a recall cost of at most
   7 / 1,816 = 0.4 pts on the SILVER tier. Left in place rather than deleted,
   per this section's rule. **Lesson:** gold offsets are only valid against
   the ingest that produced them — a classifier change silently invalidates
   them, which is why `--validate-gold` takes `--db`.

---

## 6. The limitation that matters most

**Surface triviality.** A gold set whose partition can be reproduced by
grouping on the surface string cannot measure an identity resolver — any
exact-string matcher reproduces it perfectly.

| File | scorable | surfaces | identities | surface-trivial |
|---|---:|---:|---:|---:|
| `reverend-insanity.jsonl` (silver) | 1,816 | 23 | 20 | **100.00%** |
| `reverend-insanity-c1-c5.jsonl` | 308 | 34 | 26 | **100.00%** |
| `reverend-insanity-hardcases.jsonl` | 88 | 44 | 26 | **63.64%** |

Scoring the system against the first returns B³ **P=100.0% R=94.6% F1=97.2%**
— byte-identical to the figure `docs/EVOLUTION.md` 4.74 retracted for circularity.
That figure was doomed twice over: circular in provenance *and* trivial in
task.

`eval/validate_gold.py::_surface_triviality` now **fails** any file at ≥99% and
warns at ≥90%.

**Consequence: `reverend-insanity-hardcases.jsonl` is the only evaluation set
in this corpus that measures anything**, and at 89 records it is small. Its
alias-type spread (RIGID_NAME 42, RELATIONAL_DEICTIC 29, TRANSFERABLE_TITLE 17,
EPITHET 1) and its case categories (`[body_change]` 11, `[reveal]` 17,
`[title_transfer]` 17, `[disguise]` 13, `[relational_deictic]` 29,
`[not_entity_control]` 2) are what make it non-trivial.

---

## 7. Leakage prevention

- **Drafting never reads the database.** `expand_draft` touches only the TOML
  and `Chapter.story_text`; it hardcodes `provenance=MODEL`, `confirmed=False`,
  and cannot mint a confirmed or human record.
- **`CIRCULAR_DRAFTERS` is structural.** `GoldMention.__post_init__` raises
  `CircularGoldError` if a `gold-auto-builder` record is ever marked confirmed.
- **Confirmation requires attribution.** `confirmed=True` without
  `confirmed_by` raises `UnattributedConfirmationError`; `review_depth` must be
  `PER_RECORD`, so a bulk approval cannot become gold.
- **Self-declared anchoring risk.** `reverend-insanity-c1-c5.toml:10-14`
  records that its drafter had seen pipeline output earlier in the same
  session. The LOTM ch1-3 draft claims stronger independence. Neither claim is
  externally verifiable; both are recorded rather than asserted away.
- **Blind annotation tooling exists and is unused.** `echotales annotate` emits
  a surface plus a ±240-char window with `FORBIDDEN_TASK_FIELDS` enforced,
  refuses pre-filled answers, shuffles before `--sample`, and skips blanks
  rather than defaulting them. Built, round-tripped, never run at scale.

---

## 8. Train / dev / test

**No split is marked in the data.** Splitting happens at evaluation time only,
in `eval/calibrate.py::held_out_coverage`, and is **by chapter range, never
random** — a random split leaks late-volume evidence about an entity into the
calibration of an early-volume decision about that same entity, which is
EVOLUTION 4.74's failure wearing different clothes. Because the split is
derived per run, it is not reproducible from the corpus alone; the chosen
`split_chapter` is recorded in each run's `metrics.json`.

---

## 9. What would make this gold

In increasing order of cost: run `echotales annotate` at scale over the
hardcases and c1-c5 files (they are unconfirmed, not circular, so a human pass
promotes them directly); add a second annotator on ~30 shared hard cases and
report Cohen's κ; replace the 100%-circular LOTM and ORV files with independent
drafts (LOTM ch1-3 of 40 exist). Until the first of those happens, no accuracy
claim in this repository is anchored to human judgement, and every document
must say so.
