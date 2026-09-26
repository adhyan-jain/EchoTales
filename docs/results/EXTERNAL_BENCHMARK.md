# External benchmark — LitBank coreference (human-annotated)

**2026-09-26.**
- Code: `packages/pipeline/src/echotales/pipeline/eval/litbank.py`, `scripts/eval/litbank_eval.py`, tests `test_litbank_adapter.py`.
- Result: `data/eval/litbank_results.json`.

This is the project's **only accuracy number against a human-annotated key**; everything else uses the LLM-drafted silver set.

## Dataset and run

| | |
|---|---|
| Dataset | LitBank coreference layer (Bamman, Lewke & Mansoor, LREC 2020; CC BY 4.0), `github.com/dbamman/litbank` |
| Subset | **All 100 documents** (about 2,000 tokens each), `coref/brat` + `coref/conll` |
| Key used | **Person clusters only** (majority PER-typed). 24,180 key mentions: 2,665 proper names (PROP), 6,064 nominals (NOM), 15,451 pronouns (PRON) |
| System | The unmodified EchoTales pipeline (segment → mentions → anaphora → resolve), zero-shot: no training on LitBank; NER by `qwen2.5:7b` via local ollama |
| Runtime | 1,001 s for 100 documents on the local RTX 4060 |
| Adapter check | Gold scored against itself: **CoNLL 100.0** on the full person key |

## Protocols

- **P1, full person key:** all mention types. EchoTales never proposes pronoun or nominal mentions (by design), so recall is capped at the proper-name share, about 11% of key mentions.
- **P2, proper-name mentions only:** the key restricted to PROP mentions of person clusters. This is the subset EchoTales is designed to resolve.

Each protocol is scored two ways:
- **key-restricted:** the house convention, as in every other number in this repository. System mentions that do not match a key span exactly are ignored.
- **standard:** all system person mentions are scored, so spurious ones count.

Mentions match by **exact character span**. Aggregation is micro, over pooled documents; CEAF-e is matched per document and then pooled.

## Results

| Protocol | Scoring | MUC F1 | B³ F1 | CEAF-e F1 | **CoNLL F1** | Key / system / exact matches |
|---|---|---:|---:|---:|---:|---|
| P1 full person key | key-restricted | 6.2 | 34.8 | 3.8 | **14.9** | 24,180 / 977 / 977 |
| P1 full person key | standard | 6.0 | 38.5 | 3.4 | **15.9** | 24,180 / 1,898 / 977 |
| P2 proper names only | key-restricted | 45.0 | 60.2 | 34.9 | **46.7** | 2,665 / 887 / 887 |
| P2 proper names only | standard | 36.3 | 68.0 | 23.1 | **42.4** | 2,665 / 1,898 / 887 |

**Precision and recall, P2 key-restricted:**

| Metric | P | R |
|---|---:|---:|
| MUC | 99.0 | 29.2 |
| B³ | 99.7 | 43.1 |
| CEAF-e | 57.4 | 25.1 |

## What this shows

- **Linking precision transfers to human annotation.** When EchoTales links two name mentions, it is almost always right (MUC P 99.0, B³ P 99.7 key-restricted), consistent with the silver-set finding (B³ P 100).
- **Recall is the weakness, and it starts at detection.** Only 887 of 2,665 proper-name key mentions (33%) are produced with an exactly matching span. 1,011 further system mentions do not exactly match a key span; they are partly boundary differences (e.g. titles such as "Mr." inside or outside the span) and partly spurious.
- **The full-key number (CoNLL about 15–16) mostly measures design scope.** Pronouns and nominals make up 89% of LitBank person mentions, and EchoTales does not propose them as mentions.

## Comparability — read before quoting any number

| Published reference | Setting | Result | Why it is not comparable |
|---|---|---|---|
| Bamman et al. 2020, Table 5 | Supervised neural coref trained on LitBank, **predicted mentions**, 10-fold cross-validation, **all six entity classes**, all mention types | Average F1 **68.1** (B³ 62.7, MUC 84.3, CEAF-φ4 57.3) | Supervised in-domain training vs zero-shot; all entity classes vs persons; pronouns and nominals included; the official CoNLL scorer vs this repository's scorer |
| Bamman et al. 2020, Table 3 | Same system, **gold mentions** | Average F1 79.3 | Gold mention boundaries given |

**No claim of parity or superiority is made.** P1 is the closest analogue to the published setting, and EchoTales is far below it, mainly because it resolves names only.

## Known incompatibilities and caveats

1. **Genre:** 19th–20th-century English literary fiction, not translated Chinese web novels. The gazetteer cannot compound over a 2,000-token excerpt as it does over a 199-chapter volume.
2. **Single chapter per document:** the volume-scale mechanisms (compounding, temporal identity, observer state) are not exercised. This measures the resolver's local behaviour only.
3. **Exact-span matching:** stricter than head matching, so boundary disagreements count as misses.
4. **Scorer differences from CoNLL-2012:** this repository's B³ scores an unmatched ("twinless") mention against itself. In standard mode that inflates B³ in both precision and recall; for example, P2 standard B³ recall (58.8) exceeds key-restricted (43.1) for this reason. **In standard mode, MUC and CEAF-e are the reliable figures.**
5. **Person-cluster restriction:** a cluster counts as a person if most of its typed mentions are PER. LitBank's other classes are excluded.
6. **Tokenisation:** the input is LitBank's whitespace-tokenised text (e.g. "Lincoln 's Inn"), not natural prose, which can affect NER.
