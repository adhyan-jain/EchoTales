# CHIMERA pilot item schema

Files (local only; see `scripts/chimera/build_pilot_sheet.py`):

- `data/eval/human_review_chimera_pilot.csv`: the blind sheet the annotator fills. Matches the existing ignore rule `data/eval/human_review_*.csv`.
- `data/eval/human_review_chimera_pilot_key.csv`: the key. **Never shown to the annotator.** Holds the model-provenance fields.
- `data/eval/chimera/pilot_manifest.json`: counts, seed, script and file hashes. No excerpts, safe to share.

## Blind sheet columns

| Column | Filled by | Meaning |
|---|---|---|
| `item_id` | builder | `CP-001` ... `CP-072` |
| `batch` | builder | 1-3, 24 items each; batch 1 is the pre-reveal candidates |
| `novel` | builder | `reverend-insanity` |
| `chapter` | builder | chapter number c (float) |
| `mention_offset` | builder | character offset of the mention in the chapter text (`Chapter.story_text`) |
| `mention_surface` | builder | the mention text |
| `source_window` | builder | about 400 characters around the mention, mention in `[[ ]]` |
| `candidates` | builder | shortlist `A. Name [id4] | B. ...`; same recipe for every item, includes decoys |
| `reader_warranted` | annotator | what a careful reader of text up to the end of the mention's sentence is warranted to believe |
| `reader_evidence` | annotator | quote or chapter supporting it |
| `omniscient_id` | annotator | the true referent using the whole book |
| `omniscient_evidence` | annotator | quote or chapter settling it |
| `reveal_chapter` | annotator | chapter where a reader can first tell; blank if the reader already knew |
| `confidence_1to3` | annotator | 1 unsure, 2 fairly sure, 3 certain |
| `minutes_spent` | annotator | wall-clock minutes for this item |
| `notes` | annotator | free text |
| `annotator` | annotator | person's name, non-blank, never a model name |
| `provenance` | annotator | the literal `HUMAN` |

Allowed answers for `reader_warranted` and `omniscient_id`: a candidate letter, free text, `NEW`, `UNDETERMINED`, `NOT_AN_ENTITY`.

## Key columns (model provenance; not for the annotator)

`item_id`, `tier` (`P` pre-reveal candidate, `H` other hard case, `C` control), `category`, `source` (`gold` or `system`), `gold_identity` (the model-drafted gold label, **not** truth), `system_target` (the system's resolved entity id), `candidate_ids`.

## Mapping to the Checkpoint 2 directive's schema

The directive's `final_truth_id` is the annotator's `omniscient_id`; `reader_warranted_id_at_c` is `reader_warranted`; `reveal_distance` is computed later as `reveal_chapter - chapter`; `machine_suggestion` lives only in the key file; `category` is in the key. `evidence span offsets` are the free-text evidence columns in this pilot (offsets would cost the annotator too much time).

## Known construction limits

- Items are **chosen**, not sampled. Tier P has 3 "the clan head" mentions (the only system-derived pre-reveal mentions in the RI database) plus 20 hard-case records whose own note uses disclosure language. Tier H is 17 other hard cases stratified by category. Tier C is 30 plain-name mentions (10 chapter bins, 3 each) plus 2 not-entity controls.
- System mention offsets are corrected for a measured defect (`Mention.offset` can be one character early); the manifest records how many were shifted.
- The candidate list includes the model's answer and three decoys for every item. This is symmetric but can anchor.
