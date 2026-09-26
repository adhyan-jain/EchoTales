# Quarantined annotations — not gold, not usable as a measurement

Files here are kept, not deleted. What went wrong is worth more as a record
than as an absence, and this project's convention (`docs/EVOLUTION.md`) is to
append a correction rather than erase the mistake.

**Nothing in this directory may be read by an eval path, cited in a paper, or
counted in a coverage number.**

---

## `reverend-insanity-c1-c50.jsonl` — circular: the system scored against itself

Quarantined 2026-09-23.

**6,952 records**, 198 chapters, 5 distinct identities, every record
`kind=character`, every record `provenance: human`, `confirmed: true`,
`drafted_by: gold-auto-builder`.

### What it actually is

Produced by `eval/generate_gold.py::_extract_gold_from_db`, whose first
statement is:

```sql
SELECT text, target_id, block_index, offset, alias_type
FROM mention WHERE chapter=? AND target_id IS NOT NULL AND target_id!=''
```

The labels are the pipeline's own resolution output, read back out of its own
`mention` table and rewritten as annotations. A human supplied only the
`identity_map` — the display name for each `target_id` the system had already
decided on. No record here reflects anyone reading the source text and
independently judging who a surface form denotes.

### Why confirming it did not fix it

`generate_gold.py:95-102` says so directly, in the code that wrote these rows:

> Extracted straight from the pipeline's own resolved `mention` table
> (target_id/offset/alias_type are all pipeline output) -- it is a draft to be
> audited, never ground truth. **a label expressed in the system's own ids can
> only ever agree with it, and a recall number computed from model-drafted
> labels stops being a measurement of anything. Do not flip this to
> Provenance.HUMAN/confirmed=True without an actual human review pass.**

It was flipped anyway, and the per-record note that the generator writes —
*"Auto-extracted candidate mention ... NOT independently verified. Requires a
human confirmation pass before use as ground truth"* — was replaced with
*"[golden_qa] Ground-truth mention for Fang Yuan."*

Confirmation is the wrong instrument for this defect. A human re-reading these
records is checking whether the system agrees with the system. Even a perfect,
per-record, blind review pass would not make the file a measurement, because
the quantity being measured was never independent of the thing under test.

### What it invalidated

The headline coreference result, reported in `docs/EVOLUTION.md` 4.69 and repeated
in `docs/status/STATUS.md`:

    confirmed-tier B-cubed, RI ch1-60, 1,816 scored mentions
    precision = 100.0%   recall = 94.6%   f1 = 97.2%

A precision of exactly 100.0% against a 6,952-record gold set is not a strong
result. It is the arithmetic signature of scoring a partition against itself;
the only reason recall is not also 100% is that the `identity_map` covers 5
characters and the run resolved a few mentions the map had no entry for.

**That number is retracted.** See `docs/EVOLUTION.md` §4.74.

### What was *not* quarantined, and why

- `data/gold/reverend-insanity-c1-c5.jsonl` (343 records, `claude-opus-5`)
  stays in `data/gold/`. Its source, `reverend-insanity-c1-c5.toml`, states
  that it was drafted "reading the chapter text directly, NOT by a person, and
  NOT by inspecting the pipeline's output," and it self-documents its own
  anchoring risk. It is an LLM annotation, so it is not gold — but it is
  *independent of the system under test*, which is the property this file
  lacks. Its `confirmed` flags were reset to `false`, which is the defect it
  actually had. It also carries 35 `not_an_entity` records, the only negative
  cases in the corpus.
- `lord-of-the-mysteries.jsonl` and `omniscient-readers-viewpoint.jsonl` are
  also `gold-auto-builder` output and therefore equally circular — but they
  are 0% confirmed and the two-tier reporting in `commands.py` already
  excludes them from every reported number. They stay in place as drafts.
  **Do not confirm them.** `eval/gold.py` now refuses.

## The invariant this should have been

The comment that would have prevented this existed, in the right file, and was
correct. It was a comment. As of 2026-09-23 it is code: `eval/gold.py` defines
`CIRCULAR_DRAFTERS` and raises `CircularGoldError` when a record drafted from
the pipeline's own output is marked confirmed, and requires every confirmation
to name the person who made it (`confirmed_by`). See
`packages/pipeline/tests/test_gold_provenance.py`.
