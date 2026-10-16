# Pre-registration T4: renaming validity (version 2)

Supersedes `PREREG_T4_renaming_validity.md` (v1, sha256 `34e35ebced6d270db1e525a23d78e243ede7ac6cc1f1fb4119e0e46d732aede2`). v1 stays in place unedited as the frozen record. Everything in v1 applies **unchanged** except the items in sections 1 and 2 below. This file is frozen (hash in `MANIFEST_v2.json`) **before any full-novel T4 run exists**.

## 0. Deviation record (why v2 exists)

1. v1 was frozen at 2026-10-15T08:31:05Z. The runner and the renaming module were then written.
2. A **smoke run on chapters 1-3** (120 mentions; v1 allows a smoke run "to measure runtime", "not used for any decision") was executed. It finished in 2.3 s. Its output is kept as `data/eval/chimera/t4_smoke_ch1-3.json` and is **not** a decision run.
3. The smoke run showed that under v1's pi the renamed run disagreed with the original on most mentions even though the partitions were identical (B-cubed F1 = 1.0). Inspection showed the cause is **in pi, not in the resolver**: for example "Fang Yuan" became "Brom Das" and the resolver's `display_label` shows "Brom Da", because `strip_morphology` (`ingest/normalize.py`) removes a trailing "s" from any surface longer than 4 characters unless it ends in "ss", "us" or "is". v1's invented tokens could end in "s" (so they got folded), and an original token ending in "s" could be replaced by one that does not (so it stopped being folded). The pre-registered classifier would have called these "evidence loss", which is wrong: it is a construction defect of pi.
4. No full-novel O1/O2/I/R/N run has been executed. The fix below is derived from reading the repo's normalisation code, not from any outcome. v1 itself anticipated this: implementation defects of pi are "fixed only through a new pre-registered version, and the run repeated".

## 1. Changes to pi (replaces v1 section 3, items 1-2)

pi must **commute with the repo's own normalisers**. The construction therefore adds, to v1's rules:

1. **Exact length.** A replacement token has **exactly** the length of the original token (v1 allowed +/- 2). This preserves every length-based predicate (`len(text) > 4` in `strip_morphology`) on every surface pi touches.
2. **Morphology class preserved.** Define `s_class(t) = t ends in "s" or "S" and not in ("ss", "us", "is")`. A replacement has the same `s_class` as the original: if the original is strippable-final-s, the replacement ends in a plain "s" (not "ss", "us", "is"); otherwise it does not end in "s"/"S" at all. (Possessives "'s" are handled by regex on text and are untouched, since pi renames letter tokens only.)
3. **Honorific and article words protected.** Any token t with `strip_honorifics(t + " x", strip_articles=True) != t + " x"` (i.e. matching the repo's prefix/article lists) is **not renamed**, and no replacement token may equal any word in `_HONORIFIC_PREFIXES`, any `_HONORIFIC_SUFFIXES` word without its hyphen, or "the", "a", "an".
4. Everything else in v1 section 3 stands (bijection, capitalisation, no collision with any existing lower-cased corpus word, seed 20261015, protected title/role/kinship/blocklist/stop-word vocabularies, offsets through a monotone map, no renaming of lower-case words).

## 2. New hard gate before any resolver run (the "commutation gate")

Before O1 is run, on the real vocabulary and **without running the resolver**, the runner checks over **every distinct surface** in `self_entity.canonical_label`, `alias_binding.alias` and `mention.text` of alias type `RIGID_NAME`, and over every pair of tokens:

- **G1 display commutation:** `display_label([pi(s)]) == pi(display_label([s]))`.
- **G2 key-class preservation:** the map `comparison_key(s) -> comparison_key(pi(s))` is a well-defined **bijection** between equivalence classes: two surfaces share a comparison key if and only if their renamed forms do.
- **G3 containment preservation:** for every pair of aliases (a, b) of one entity where `b` is a whole-token substring of `a`, `pi(b)` is a whole-token substring of `pi(a)`.

**If any of G1-G3 has a violation the run does not start**; the violations are reported as a pi defect and fixed only in v3. A pi that passes G1-G3 cannot change a decision through the normalisation layer, which is exactly the failure that appeared in the smoke run.

## 3. Classification (adds to v1 section 5)

v1's order is kept (offset error, lexicon gap, evidence loss). Because of the gate, **a changed decision that still involves a surface whose label differs from `pi(label_O)` only by a trailing "s" is reported separately as `morphology_artefact`** and counted as an implementation defect of pi, not as evidence loss. The decision rule's FAIL clause then applies to the sum of `evidence_loss` only; if `morphology_artefact` is nonzero after the gate passed, the run is **INCONCLUSIVE** (the gate was not sufficient) and pi gets a v3.

## 4. Decision rule, runs, metrics, power, scope

Unchanged from v1 sections 4-8 (runs O1, O2, I, R, N; primary metric per-mention agreement by label under pi; PASS requires observed agreement >= 0.98, Wilson lower bound >= 0.97, O1 = O2 = I at 100%, and N below R; entity-clustered bootstrap, 2,000 draws, seed 20261015).

One addition to PASS: **the commutation gate must have passed** before the full run began.

## 5. Findings recorded now, before the run (from reading code, not from results)

- The RI lexicon file named in `data/sources.toml` (`data/lexicons/reverend-insanity.toml`) **does not exist locally**, so `load_or_seed` falls back to the generic `_seed.toml`. T4 therefore tests the resolver under the generic seed lexicon, which is the same lexicon the run of record used when it was built here. Renaming a lexicon with few proper tokens exercises lexicon renaming weakly; this is a scope limit.
- `Mention.offset` is sometimes one character early (measured on chapter 1: 6 of 44 mentions). Those mentions are counted as `preexisting_offset_defect` and never as a defect of pi.

## 6. Deviations log

v1 -> v2: as section 0. No other deviation at freeze.
