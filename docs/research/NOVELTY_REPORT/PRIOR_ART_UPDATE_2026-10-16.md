# Prior-art update, 2026-10-16 (owner message at about 17:58 IST) and the re-ranked contribution claims

Tags: **[VERIFIED-ABS]** = the arXiv abstract page was fetched and read on 2026-10-16 (not the full text); **[LEAD]** = the owner's summary, not verified by me; **[READ]** = read in the earlier notes (`PRIOR_ART.md`, `PRIOR_ART_E0.md`). Nothing below was read in full today.

| Work | What the owner's note says | What I verified | Consequence for our claims |
|---|---|---|---|
| Chang, Cramer, Soni, Bamman 2023, "Speak, Memory" (EMNLP) | memorisation tracks web frequency; downstream accuracy higher on memorised books | [READ] in `PRIOR_ART_E0.md` (Spearman 0.74 for pre-1928 books against web hits, Table 3) | our fame dose-response is a **confirmation**, not a contribution |
| Jiang and Ferraro, arXiv 2412.14368 | "v5", name replacement exposes memorisation; proposes a cue-preserving mitigation | [VERIFIED-ABS] the current page is **v6** (24 Apr 2026; v1 18 Dec 2024); the abstract says "We introduce a simple yet effective method to mitigate mechanized memorization in character understanding evaluations" and says it keeps the implicit cues needed for comprehension | our pseudonym test (B3) and the E4 mitigation are **replications and baselines** of theirs, not new methods |
| WhoDunIt, arXiv 2502.07747 | name swaps on Gutenberg mysteries, full-story only; closest prior work | [VERIFIED-ABS] Kshitij Gupta, 11 Feb 2025, "WHODUNIT: Evaluation benchmark for culprit detection in mystery stories"; tests original names, name swaps and substitutions with well-known real or fictional entities on GPT-4o, GPT-4-turbo, GPT-4o-mini; accuracy drops under some substitutions, "particularly those with wide recognition". The abstract does **not** say Gutenberg, truncation or memorisation | Gutenberg source and "full-story only" stay **[LEAD]** until the full text is read; our stated difference is pre-reveal truncation with an entitlement oracle |
| DatedGPT, arXiv 2603.11838 | look-ahead-bias literature; parent concept | [VERIFIED-ABS] Yan, Tang, Gao, Jiang, Lu, 12 Mar 2026 (v2 23 Jul 2026), "Preventing Lookahead Bias in Large Language Models with Time-Aware Pretraining": twelve 1.3B models with annual data cutoffs, financial forecasting; the abstract does not use "point-in-time correctness" (that framing is an interpretation) | cite as the **parent concept** (look-ahead bias); reader-faithfulness is the reader-position analogue |
| SurrealDB "Spectron" spoiler-safe narrative memory | product precedent for story-time stamping | [LEAD] not fetched | our difference: **derived** attributes, not stamped events |

## Re-ranked claimed contributions (owner, 17:58 IST)
1. **Premature-resolution construct under prefix truncation**, with a text-derived oracle (entitlement, not truth of the full story).
2. **Renaming validity checks are themselves memory-assisted** (plain controls on famous books are easier with original names; the memory-free gate).
3. **Derived-attribute horizon leakage and its repair** (Channel 2, the prefix-faithfulness session's results).
4. **OLMo training-data link, if it works** (exploratory, addendum 3).
5. **E5 recap harm** (spoiler rate in a realistic reader task).
Not claimed as contributions: the fame dose-response (confirms Chang et al.), the pseudonym test and the E4 mitigation (replications and baselines of Jiang and Ferraro).
