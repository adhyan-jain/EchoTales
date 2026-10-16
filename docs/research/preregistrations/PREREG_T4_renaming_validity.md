# Pre-registration T4: renaming validity (version 1)

Written and frozen **before any renaming code, scratch database or resolver run exists**. Repo HEAD `6c7e2c2`, branch `validation/evidence-pass-2026-09-24`, tracked change `.gitignore` only, 2026-10-15. The SHA-256 of this file is recorded in `MANIFEST.json` in this directory before anything runs. A change after freezing is a new file `PREREG_T4_renaming_validity_v2.md`, never an edit.

## 1. Question

Does a consistent, token-compositional renaming pi of every person name, alias, proper part of a title, clan name, place name and coined term leave the repo's deterministic resolver's decisions unchanged on more than 98% of mentions? If not, whole-input renaming destroys evidence the resolver uses, and it cannot serve as the leakage control for candidate C1 until it is redesigned.

Why it matters: C1's decisive comparison is "mechanism vs plain renaming of the whole input". A control that changes the resolver's answer for reasons unrelated to memorisation (a renamed token that breaks a containment relation, an offset that no longer lines up) would make renaming look protective or harmful for the wrong reason.

## 2. System under test and items

- **System:** `echotales.pipeline.resolve.resolve_novel` with defaults: no LLM (`use_llm` unset, no router), `capture_evidence=False`, the induced lexicon loaded as the CLI does (`load_or_seed(get_source(novel).lexicon)`). Stub mode: `ECHOTALES_LLM_MODE=stub`.
- **Input:** a scratch copy of the RI database (`data/db/reverend-insanity.db`, copied while its `-wal` is 0 bytes). The resolver is run on the **existing detected mentions**, so mention detection (the LLM-dependent stage) is held fixed and never re-run. This isolates exactly the stage the control is meant to leave alone.
- **Items:** every mention row in the scratch database (11,174 at HEAD). **Primary analysis = all mentions.** Secondary, descriptive only: the 72 pilot items' mentions (a 1-mention change is 1.4 percentage points, so 98% cannot be judged on 72).
- Mentions the resolver leaves unresolved count as an item with decision "unresolved".

## 3. The renaming function pi (frozen specification)

pi is generated once by a seeded RNG (**seed 20261015**) and never regenerated.

1. **Vocabulary.** Take every capitalised token that occurs in any `self_entity.canonical_label`, any `alias_binding.alias`, or any mention text of alias type `RIGID_NAME`. Remove (do **not** rename) any token whose lower-case form is in the repo's title/role/kinship/ambiguity vocabularies: `AMBIGUITY_BLOCKLIST` (`mentions/gazetteer.py`), `_TRANSFERABLE_TITLE_NOUNS` and `_ROLE_NOUNS` (`mentions/alias_type.py`), the kinship terms in `anaphora/local.py`, and English stop words. Remove tokens that are all of {"I", "He", "She", "It", "We", "They", "You"}.
2. **Mapping.** Each remaining token maps to a fresh invented token that is (a) type-preserving (capitalisation pattern kept), (b) of the same number of letters +/- 2 and drawn from a fixed syllable inventory, (c) never equal to any existing English word in the corpus's lower-cased token set, (d) one-to-one (bijection on the vocabulary). Mapping is **token-level**, so "Fang Yuan" -> "T V" and "Yuan" -> "V" with the same V: containment, prefix and surface-similarity relations survive by construction.
3. **Application.** pi is applied to: every block text in `chapter.blocks_json`, `mention.text`, `span.text`, the induced lexicon entries and identity-declaration strings, and the mention/span character offsets, which are **recomputed through a monotone offset map** built from each substitution (renamed tokens change length). A renamed mention's new text must equal pi(old text) and must index the new block text at the new offset; any mention failing that check is an "offset error" and is counted, never silently fixed.
4. **Not renamed:** lower-case words, titles and role nouns, punctuation, numbers. This is a deliberate limit: pi renames identity-bearing proper tokens, not the whole text. It does not test whether a model can recognise the story from plot.

## 4. Runs

| Run | Input | Purpose |
|---|---|---|
| O1 | original scratch copy | baseline decisions |
| O2 | a second fresh original scratch copy | **determinism check**: O1 vs O2 must agree on 100% of mentions; if not, the resolver is nondeterministic and the noise floor is subtracted from T4 |
| I | pi = identity pushed through the same transformation code | transformation-code sanity: must agree 100% with O1 |
| R | pi-renamed copy | the test |
| N (negative control) | a **broken** pi that renames "Fang Yuan" and "Yuan" independently (non-compositional) | shows the test can fail; agreement must drop below R's. If N does not drop, the comparison is insensitive and T4 is **inconclusive**, not passed |

Each run: fresh scratch copy of the database; `resolve_novel(..., force_rewipe=True)` is allowed **only on scratch copies** (it deletes bindings). The owner's database is never opened for writing. Host: this machine, CPU only, one process, no GPU. A smoke run on chapters 1-3 first to measure runtime is allowed and reported as such; it is not used for any decision.

## 5. Metrics

For mention m, the decision in a run is the tuple (resolved?, entity label, resolution method, confidence rounded to 3 decimals). Entity ids are hashes of label, chapter and offset, so they differ under pi by construction and are **not** compared. Compare **by label under pi** and by partition:

- **Primary: per-mention agreement** = share of mentions with (resolved?)_O == (resolved?)_R, and, when resolved, label_R(target_R(m)) == pi(label_O(target_O(m))).
- Secondary: B-cubed F1 between the original and renamed partitions of resolved mentions; share with identical method; mean absolute confidence change.
- Each changed decision is classified by rule, in this order: **offset error** (renamed mention text does not index the renamed block at the new offset); **lexicon gap** (the changed mention's context or lexicon entry contains a capitalised proper token that is not in pi's vocabulary but should have been); **evidence loss** (anything else). The three are reported separately; only "evidence loss" is evidence against renaming as a control.

Intervals: Wilson 95% for agreement; entity-clustered bootstrap (resample entities, 2,000 draws, seed 20261015) as a robustness interval because mentions of one entity are not independent.

## 6. Decision rule (fixed now)

- **PASS (renaming is a valid control for this resolver):** primary agreement in R >= 0.98 **and** its Wilson lower bound >= 0.97 (the lower bound alone is satisfied at 0.9732 for n = 11,174, so the 0.98 point rule binds), **and** O1 = O2 = I at 100%, **and** N is below R.
- **FAIL:** agreement < 0.98 after excluding offset errors and lexicon gaps that are bugs in the **implementation** of pi (these are reported, fixed only through a new pre-registered version, and the run repeated). C1 work stops; report redesign options (for example a length-preserving renaming, renaming only names and not coined terms, or per-class renaming).
- **INCONCLUSIVE:** O1 != O2 above 0.5%, or N does not fall below R, or the clustered interval straddles 0.98.
- What it kills or keeps: PASS keeps C1's renaming control alive (it says nothing about C1 itself). FAIL stops C1 until the control is redesigned. T4 alone never kills C1; T3 and the labels do that.

## 7. Power statement

n = 11,174 mentions, but they cluster in 268 entities, so the effective sample is smaller; the entity-clustered interval is the honest one. With independent items the test can detect a 1 percentage-point drop below 98%. It cannot detect a loss concentrated in a handful of entities with a small mention share, and it says nothing about LLM behaviour.

## 8. Scope limits

T4 uses the deterministic resolver on **fixed detected mentions**. It does not test that the **detector** is rename-invariant (it is LLM-based and out of scope), nor that renaming removes parametric knowledge in an LLM (T3's job), nor that renamed text is natural.

## 9. Deviations log

None at freeze.
