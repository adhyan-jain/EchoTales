# ner_romanized gold changelog

Changes: 3 spans added or adjusted (1 each under rules (a) and (e), 1 under the existing bare-title rule).
Passage text is never altered; JSONL rebuilt by `scripts/eval/build_ner_romanized_gold.py` from the marker sources.
Net change +2 spans (Kerala, Emperor); Sentry Dovrin is a span extension. Totals now: dev 467, test 798 (all sources).

Review method: false positives under boundary mode proposed by >= 2 systems (overlapping), gold spans missed by every
system, and a scan of the passage sources for title + name, name + "the X", and name + "of <Place>" patterns. Almost
all system-proposed spans were system errors (generic nouns, "Court", "Palace", word-like names, sentence starts) and
were kept as they are.

| doc_id | split | before | after | rule |
|---|---|---|---|---|
| in05 | dev | "Kerala" unannotated ("born in Kerala") | `Kerala` location | (e) |
| inv13 | dev | `Dovrin` (preceded by "Sentry") | `Sentry Dovrin` person, category title | (a) |
| pd_zh06 | dev | "when the Emperor was making a progress" unannotated | `Emperor` title_epithet | bare sole-referent title (README annotation rules); same as `Emperor` in pd_zh03 |

## Reviewed and left unchanged

- "Captain Yoo", "Detective Oh", "Sigrid the Younger/Elder" already follow (a)/(c); "King Wên" + "Chʻu" follows (d);
  "Mr. Darcy of Pemberley" follows (d).
- pd_in01 "the Brahmana Chandabhargava" / "the Brahmana Kalaghata": "Brahmana" is a class noun, not a rank; left
  outside the span under (a). Ambiguous.
- pd_in01 "Kohala Devasarman": gold keeps two persons, as in the source list; every system predicts one span.
  Ambiguous (the join removed the original comma).
- ko10 "Tae-sik sunbae": spaced suffix, bare name kept under (b).
- Possessive and title-adjacent misses by all systems (pd_ja06 "Emperor's", "Prince's", pd_zh02 "Wuchʻêng", pd_zh03
  "Tu-ting", pd_ja04 "Takasago", pd_eu06 "Sahri-"): gold correct, system boundary errors.

## 2026-11-27 owner-requested full review

Sixteen marker edits across 14 passages (the brief counted 15 fixes; the in12 row covers two markers and ja05 has three edits). Passage words are unchanged; only markers changed. Rebuilt with
`scripts/eval/build_ner_romanized_gold.py`; offsets asserted; `test_ner_spans.py` 15 passed.

| doc_id | before | after | reason |
|---|---|---|---|
| zh06 | "[[Grace|p|wl]] Tan carried" | `[[Grace Tan|p|wl]] carried` | Surname was left outside the person span; the name is "Grace Tan" (rule (a)-style: whole name inside the span). |
| ja05 | "The clan head of the [[Kurosawa clan|o]] and the clan head of the [[Shinjo clan|o]]" | "The [[clan head|t|sh]] of the [[Kurosawa clan|o]] and the [[clan head|t|sh]] of the [[Shinjo clan|o]]" | Shared title used alone for a specific person is title_epithet, shared_title category; it was unannotated. |
| ja05 | "both were called uncle by half" | "both were called [[uncle|t|sh]] by half" | Shared kinship title used alone; generic-role rule applies by the lower-case test. |
| ja05 | "[[Uncle|t|sh]] has refused," | "[[Uncle|t|sh|gen]] has refused," | Capitalised kinship address term used alone: relational reference, generic_role forced. |
| in10 | "[[Vikram bhai|p|tit]]," someone said | "[[Vikram|p]] bhai," someone said | Rule (b): spaced suffix "bhai" stays outside the span; bare name kept as the person span. |
| in02 | "[[Beti|p|ali]]" | "[[Beti|t|ali|gen]]" | Kinship address term (daughter) used alone: relational reference, generic_role forced; was a person span. |
| in03 | "[[Thambi|p|tit]]," called an old woman | "[[Thambi|t|ali|gen]]," called an old woman | Kinship address term (younger brother): relational reference, generic_role forced. |
| in09 | "[[Amma|p|tit]]," called | "[[Amma|t|ali|gen]]," called | Kinship address term (mother) used alone: relational reference, generic_role forced. |
| in12 | "[[Ammamma|p|tit]]," she said (both occurrences) | "[[Ammamma|t|ali|gen]]," she said; "[[Ammamma|t|ali|gen]] folded" | Kinship address term (grandmother) used alone: relational reference, generic_role forced. |
| in15 | "[[Maa|p|tit]]" from the courtyard | "[[Maa|t|ali|gen]]" from the courtyard | Kinship address term (mother) used alone: relational reference, generic_role forced. |
| eu10 | "the [[city council|o]] was voting" | "the city council was voting" | Generic noun phrase, not a named organisation. |
| mix07 | "befriended a [[Sultan|t]], [[Harun|p]]" | "befriended a Sultan, [[Harun|p]]" | Bare lower-case-article title "a Sultan" is a generic descriptor, not a named epithet. |
| pd_ja04 | "Tell his Majesty this" | "Tell [[his Majesty|t|ali]] this" | Honorific used as a named reference to the Emperor (alias epithet). |
| pd_ko03 | "near His Majesty and" | "near [[His Majesty|t|ali]] and" | Same as pd_ja04: honorific alias for a specific sovereign. |
| pd_eu02 | "everything her Ladyship said" | "everything [[her Ladyship|t|ali]] said" | Honorific alias for a specific person (Lady Catherine); consistent with "Her Ladyship" marked elsewhere. |
| pd_zh05 | "Then both the Yüans will fall" | "Then both the [[Yüans|o|ord]] will fall" | Named family/faction of the Yüan clan, ordinal use; annotated as organisation. |
