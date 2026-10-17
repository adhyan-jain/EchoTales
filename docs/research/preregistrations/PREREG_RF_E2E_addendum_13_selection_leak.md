# RF-E2E addendum 13: a selection leak, where every served passage is before the reader's position and the answer still spoils (written 2026-10-17, before any of these cells exists)

**Seen before writing:** all results of addenda 6 to 11. Addendum 12 (suffix canaries) was frozen and started, but none of its results had been read. No cell of this addendum exists.

## Why

Position-aware assistants are described as filtering what they serve: every fact or passage carries a progress point and only those before the reader's are used (Technical Disclosure Commons 8646; the Kindle product page). Addendum 12's suffix canaries detect **content** flowing from the suffix to the output. A second class of leak moves no suffix content at all. A whole-volume index can decide **which prefix passages belong together** using the suffix. For example, entity resolution over the whole book merges the alias with the identity because the reveal says they are one person, and retrieval for the alias then returns prefix passages about the identity. Every passage served is before the cut, so position filtering passes and a content test (canary, string match against suffix text) is blind by construction. Only truncate-and-rebuild (an index built from the prefix would not merge them) can see it. EchoTales' own prominence gate (paper Section 5.3) is one instance of this class (a control decision rather than content); this addendum measures a retrieval instance on a generic design.

## Events

From the 57 measurable events of addendum 6: those with audit EXPLICIT or IMPLIED whose identity is already named in the reader's prefix (at least one mention of an identity surface, `pd_reveal_benchmark.surfaces_for`, in a sentence that ends before the cut). These are exactly the events rule A could not score.

## Builds (cipher names throughout, first cipher of addendum 6, so memory cannot contribute)

- **Resolver (index time, may read the whole book).** `qwen2.5:7b` reads the reveal window (1,500 characters before the reveal sentence to 500 after it, cipher names) and answers JSON `{"same": true|false}` to "In this passage, are the character called "<alias>" and the character called "<identity>" the same person?". This is a stand-in for whole-volume entity resolution; a "true" means a whole-book index would hold one entity for both names.
- **M_ren (merged-entity retrieval, position-filtered).** Card prompt of addendum 6 for the alias, with up to K = 12 passages spaced over the union of the pre-cut alias mentions and the pre-cut identity mentions, each window clipped at the cut. Assertion in code: no character after the cut is in the input.
- **P_ren (prefix-built index, the truncate-and-rebuild reference).** The stored P_ren card of addendum 6 (pre-cut alias mentions only); an index built from the prefix has no reveal to merge on.

Generators: `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b-instruct` (temperature 0, same options as addendum 6). Judge: `qwen3:8b`, prompt and JSON schema of addendum 6, on M_ren (P_ren labels are the stored ones).

## Hypotheses (event-cluster bootstrap, 10,000 resamples, seed 20261101; pooled per-event value = mean over models)

- **H13.1 (primary).** Over events the resolver merges, judge-rule leak M_ren minus P_ren is at least +10 points with a 95% lower limit above 0 and positive for at least 2 of 3 models.
- **H13.2 (secondary).** The same contrast over all selected events with the merge assumed (an ideal whole-volume resolver).
- **Structural.** The M input contains no post-cut text in any event (asserted), so the suffix canaries of addendum 12 cannot fire on it; reported as a property of the design, not as a measurement.
- **Descriptive.** Resolver merge rate; per-model rates and sign tests; share of M passages that are identity passages.

## Caveats fixed now

The judge was validated against the text rule only on rule-A events (paper 7.7); on these events the identity is named in the passages, so a card can name both people without equating them, and the judge prompt asks specifically whether the card states or clearly implies they are the same person. This is reported as a limit. The retrieval design is a controlled stand-in for an entity-indexed assistant, not a specific product.

Order: after addendum 12 finishes on the GPU. Cost $0 (local).
