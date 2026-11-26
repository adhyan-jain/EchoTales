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
