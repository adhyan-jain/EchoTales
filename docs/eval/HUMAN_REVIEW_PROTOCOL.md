# Human review protocol

**Prepared 2026-09-25. No human labels exist yet.** This protocol and its sheets are the smallest review that lets the project say whether its silver-reference numbers transfer to human judgement.

## Sheets (local only; they contain short windows of copyrighted text)

Regenerate both with `python3 scripts/prepare_human_review.py` (seed 20260925, canonical database). They are gitignored; share them only with the review team.

| File | Rows | What |
|---|---:|---|
| `data/eval/human_review_200.csv` | 200 | Stratified sample of system mentions |
| `data/eval/human_review_hardcases_88.csv` | 88 | The hard-case reference records (silver) |

**Strata in the 200-mention sheet** (seeded, then sorted by position):

| Stratum | n |
|---|---:|
| easy_name | 30 |
| alias | 35 |
| title | 30 |
| relational | 35 |
| unresolved_name | 6 (all that exist) |
| observer_sensitive | 30 |
| background | 34 |

- **No pronoun stratum.** Pronouns never become graph mentions in this system (they are linked locally), so there is no system decision to judge.
- **Silver coverage is sparse.** Only 11 of the 200 rows fall where the silver set has a record. For the rest, the review measures the system's precision directly; it does not compare against silver.

## Columns

- `sample_id`, `chapter`.
- `source_text`: up to 200 characters, with the mention marked `[[like this]]`.
- `mention`.
- `predicted_entity`: the system's link, or UNRESOLVED.
- `candidate_entities`: entities that share the surface name.
- `system_decision`: link or no link, method, alias type.
- `reference_set_decision`: the silver identity, or "not in silver set".
- `category`.
- `reviewer_label`, `reviewer_notes`: **empty; for the reviewer only.**

## Instructions for the reviewer

1. Read `source_text`, plus the surrounding chapter if the window is not enough (the chapter number is given).
2. Decide who the marked mention refers to at that point in the story.
3. Set `reviewer_label` to exactly one of:
   - **correct**: the system's `predicted_entity` is the referent.
   - **incorrect**: the system linked to the wrong referent, or linked a mention that does not refer to a person, place or organisation.
   - **unresolved**: the system did not link (UNRESOLVED), **or** you cannot determine the referent from the text. Say which in `reviewer_notes`.
4. For the hard-case sheet, judge whether `reference_set_decision` (the silver identity) is right, using the same three labels. That measures the silver set itself.
5. Do not consult the system's other outputs while labelling. Do not change `predicted_entity` or `reference_set_decision`.
6. Record anything ambiguous (disguise, a title held by several people, a name used before a reveal) in `reviewer_notes`.

## Agreement

- **Two independent reviewers** label the same sheets without discussing them. Report Cohen's κ per sheet and per stratum (strata with fewer than 20 rows: report raw agreement only). Then adjudicate disagreements, and report precision with a Wilson 95% interval on the adjudicated labels.
- **With only one reviewer, κ is not reported.** Report precision with its interval and say that no inter-rater agreement exists.
- κ is computed only from real labels. Nothing in this repository computes or estimates it before those exist.

## Effort

About 6–8 person-hours for both sheets, per reviewer.
