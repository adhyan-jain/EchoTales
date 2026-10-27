# Targeted validation protocol for the pipeline-disclosure labels

Status: PROPOSAL for review. No human annotation has been done under this protocol.
Written 2026-10-27. Sampler: `scripts/paper/build_validation_sample.py` (seed 20261101).

## Summary for the supervisor

We do not propose annotating every story or every instance. The 36 human-validated reveal events stay as they are.
The reliability of the pipeline-disclosure results is established in three layers, kept separate in the paper:

1. **Deterministic checks (no annotator).** Reveal positions by exact match; divergence between the served value and
   a prefix-only rebuild; counterfactual-suffix dependence; resolver prefix-causality (0 of 28,165 comparisons);
   zero divergence under versioning; a synthetic volume with known truth.
2. **Model screening, labelled MODEL-GENERATED.** Two model annotators (Claude, frozen by sha256; gpt-5.6-luna), strict
   and permissive prompts. Preliminary only.
3. **A small stratified human sample: 48 cases plus 4 repeats**, two annotators per case, who see only the prefix
   passages, so no story needs reading in full. About 7 annotator-hours in total. Reported with agreement,
   disagreements, and how far humans support the model labels.

The human sample is purposive. It estimates how well the model labels agree with humans in each stratum. It does
not estimate how common disclosure is.

## Layer 1: deterministic checks

| Check | Status |
|---|---|
| Reveal position (exact match) | done; oracle rules to be tabulated |
| Divergence vs prefix-only rebuild | done (41/685) |
| Counterfactual-suffix dependence | done (47/289) |
| Resolver prefix-causality | done (0/28,165) |
| Versioning divergence | done (0/289, 0/685, 0 per synthetic configuration) |
| Prefix-boundary assertion (no row past the cut enters the prefix build) | to do: assert max chapter/span/mention/segment index <= cut on every truncate-and-rebuild DB; `audit.py` has no such assertion today (checked 2026-10-27) |

## Layer 2: model screening and a synthetic benchmark

Model labels are reported as model labels everywhere. A synthetic benchmark with controlled reveal points
(`scripts/prefix_audit/synthetic_oracle.py`, invented text, truth by construction) gives each model annotator's
accuracy against ground truth with no human effort. Planned difficulty strata: explicit cue, implicit cue, adversarial
pronouns, descriptive-identity names. Caveat: synthetic text is easier than a novel, so this bounds the judges'
behaviour and does not replace real-text validation.

## Layer 3: human sample

Unit: one character-cut pair, the unit of the 289 and 685 denominators. Populations below are computed from the
stored audit and label files (`--counts`), restricted to pairs that carry a model prefix label.

| Stratum | What it is | Population (all five books / three serials) | Drawn |
|---|---|---|---|
| S1 | Divergent; model-judged genuine disclosure (positives) | 21 / 18 | 10 |
| S2 | Divergent; model-judged supported by the prefix | 26 / 21 | 8 |
| S3 | Model annotators disagree (Claude vs luna, or strict vs permissive) | 13 | 8 |
| S4 | Reverse direction (served unknown, prefix build held a value) | 2 / 2 | 2 |
| S5 | Repaired output withholds a value the prefix may support | 92 | 8 |
| S6 | Non-divergent controls, random | 363 | 12 |

The serial-only populations reproduce the paper's figures (18 + 21 + 2 = 41 divergent; 91 withheld on exposed cuts,
here 92 across all five books). Drawn sample: 11 Lord of the Mysteries, 11 Reverend Insanity, 11 Omniscient Reader's
Viewpoint, 10 Oliver Twist, 5 Three Musketeers; 34 original-cut and 14 added-cut cases. Selection: smallest stratum
first, each case in one stratum only, round-robin across books within a stratum, fixed seed. Four repeated cases
measure annotator self-consistency. The manifest hash is recorded before any annotator sees a case:
`sha256 450801920be79cc0a2c6c3333a494468bac7d05a5f9e197f41fb117ea680a692`.

Limits of the draw: S3 draws only on pairs with both annotators' prefix labels (Claude labelled 46 prefix items);
no S3 case comes from the English novels or from the added cuts. S6 is restricted to pairs that have a model prefix
label, so it is a random draw within the labelled pairs, not within all 685 cut pairs.

Passage budget: humans see up to 8 passages per case (150 characters before and 350 after each mention, spread over
the chapters up to the cut); model annotator 2 saw up to 24. A human-model disagreement can therefore come from
different evidence, not only different judgement, and the write-up says so. Annotators are not expected to have read
any of the books, as in the reveal study; Q0 records it.

## Rubric (one page)

The blind sheet shows the character's name and aliases and the passages that mention them up to the cut
(the format of `scripts/prefix_audit/label_sheets.py`). Nothing after the cut. No model label, build identity
or served value in step A.

- **A (before seeing any system output).** Q1: from these passages alone, is the character male, female, or not
  determined? Q2: confidence (clear / suspect / none).
- **B (then the served value is shown).** Q3: is the served value supported, unsupported or contradicted by the
  passages? Q4: would a first-time reader of this prefix plausibly hold this value (yes / no)?
- **Q5.** Flag NEEDS-BROADER-CONTEXT if the call depends on events outside the sheet. These are counted and reported,
  left out of the primary agreement table and kept in a sensitivity table.
- **Rule.** Judge only what the prefix shows. Record whether the annotator already knew the book, as in the reveal study.
- **Calibration.** Six non-sample cases, discussed, then the rubric is frozen.

## Effort estimate

| Item | Time |
|---|---|
| Engineering (sheets from the manifest, reuse of `reveal_validation_app`, scoring script) | about 1 working day, no annotator time |
| Calibration (6 cases) | about 30 min per annotator |
| Annotation, 52 cases at about 4 min, three annotators, each case to two of them in rotation | about 35 cases (about 2.3 h) per annotator, about 7 h in total |
| Adjudication by the third author | about 1 h |

Realistically two 2-hour sessions per annotator. If time is short the fallback is S1 + S2 + S4 + S6 only (32 cases,
about 2.2 h per annotator), which still covers positives, negatives and controls.

## Analysis plan

Cohen's kappa and raw agreement between the two humans (raw agreement per stratum where kappa degenerates);
categorised disagreements (prefix ambiguity, pronoun ambiguity, needs-context, annotator error); adjudicated human
label against each model annotator (confusion matrix, agreement, kappa, per stratum, Wilson intervals); sensitivity
excluding needs-context cases; S1 precision (model-judged disclosures that humans confirm) and a recall proxy from
S2 and S6; self-consistency on the 4 repeats. With n = 48 intervals are wide (40 of 48 in agreement has a Wilson
interval of roughly 70 to 91%), and they are reported as such.

## Limitations to state

Purposive sample, so no prevalence estimate; annotators are authors and know the hypotheses; three serials plus two
public-domain novels; gender is the only attribute checked; the human check bounds the model labels on this sample
and does not validate the whole 685-cut audit. Until results exist, the paper keeps calling the disclosure rates
model-annotated and provisional.
