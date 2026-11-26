# Romanized-name NER: bake-off and real-data check

The span-level bake-off (boundary F1, test split) is in `data/eval/ner/bakeoff-*.json`; the hybrid detector is
`pipeline/mentions/hybrid.py` (decision D69). This file holds the check on real novels. Bake-off section: not yet
written here; numbers are in the JSON files.

## Real-data check (2026-11-27)

**Setup.** Scratch copies of the three run-of-record DBs trimmed to a chapter prefix (`data/scratch/ner_realdata/`, not
committed; `scripts/eval/ner_realdata_compare.py`). Legacy = `mentions.detector: llm` (qwen2.5:7b). Hybrid = GLiNER-medium
(local path, rev 40ec419) + spaCy + qwen3:8b classifier, tau 0.7/0.3. Cold name caches, ollama stopped before GLiNER loads,
then `anaphora` and `resolve` (no LLM adjudication). Raw numbers: `data/eval/ner/realdata_legacy_vs_hybrid.json`.

| Slice | Mentions L / H | Distinct surfaces | Entities (person-kind) | Detection wall time | Peak GPU |
|---|---|---|---|---|---|
| RI ch1-5 | 205 / 241 | 31 / 47 | 22 (11) / 33 (17) | 67 s / 198 s | 4.9 / 5.8 GB |
| RI ch1-32 | 1301 / 1412 | 78 / 121 | 53 (22) / 84 (35) | 575 s / 1305 s | 4.9 / 5.8 GB |
| LotM ch1-3 | 138 / 160 | 19 / 26 | 17 (9) / 25 (13) | 71 s / 141 s | 4.9 / 5.8 GB |
| ORV ch1-3 | 65 / 74 | 12 / 22 | 8 (8) / 16 (14) | 40 s / 133 s | 4.9 / 5.8 GB |

Hybrid costs about 2-3x the wall time (GLiNER load, spaCy, then a qwen3:8b swap) and never holds GLiNER and ollama at once.

**Resolve (RI ch1-32).** Groups 259 / 340; linked 137 / 198; new entities 53 / 84; deferred 2 / 2; escalated 2 / 2
(0.8% / 0.6% of groups). The other novels deferred or escalated 0-2 groups under both detectors. 10 legacy entities have no
hybrid counterpart (alias overlap < 0.5) and 41 hybrid entities have no legacy counterpart; most of the 41 are items, places
and organisations.

**RI hard cases** (`scripts/eval/hardcase_resolution.py --max-chapter N`, silver): hybrid changes nothing. Ch1-32, 17 cases,
overlap alignment: 8 not detected, 7 correct, 0 wrong, 2 gold-unmapped, for both legacy and hybrid (exact alignment 11 not
detected / 6 correct, both). Ch1-5: 6 cases, identical. Hybrid adds mentions, but not the ones the hard cases need.

**LitBank** (20-document seeded subset, standard protocol, proper-name mentions, MUC/B3/CEAF-e F1): legacy 68.2 / 76.3 /
35.4, hybrid 71.7 / 79.4 / 43.1 (key-restricted: 73.4 / 76.0 / 44.6 vs 77.1 / 78.0 / 60.0). Full-person key (incl. nominals and
pronouns): 12.2 / 38.7 / 4.6 vs 13.3 / 39.2 / 8.6. System mentions 446 vs 570. Hybrid took 1218 s vs 356 s.

**Reading the difference lists** (my classification of the surfaces; top-30 by frequency, RI ch1-32):
- Only hybrid (55 surfaces, top 30): about 7 person names (Chen Bo, Fang, Sir Flower Wine, Chi Chen, Chi Lian, Gu Yue Dong Tu,
  Chibigen?), about 16 named non-persons (Spring Autumn Cicada, Gu worm names, Demonic Faction, River of Time, Primeval Sea,
  Gu Clan, South Border), about 7 not names (Predicaments x12, Rank, Photo, House, clan head x7, a title phrase, and the broken
  "Fang Zhi's").
- Only legacy (12 surfaces): real losses are Gu Yue Zao Xie and Fang Zhi (see the defect below); Gu Yue Chen Bo, Feng and
  Uncle Gu Yue Dong Tu are the same people under a shorter or titled surface in hybrid; the rest are titles or generic
  ("Gu Master", "Gu Yue clan head", "New Year").
- LotM ch1-3: hybrid adds Lord Ye, Hermes, Feysac, Earth Mother, Tingen University, Machinery, Arcane Arts, Technical School
  (none is a character except possibly Lord Ye); loses "Sunday" (a weekday there, so the loss is a gain).
- ORV ch1-3: hybrid adds Kim Dok, Yoo Sangah-ssi, Sangah, Kang, Han (names) and Han Kang, Murakami Haruki, Raymond Carver
  (real authors cited in the text); junk: "Reader-nim" with a footnote digit, "HR", "Reader", a book title.

**Defects found.** (1) Hybrid keeps the curly possessive in "Fang Zhi's" (2 mentions), so the entity Fang Zhi exists only as a
broken surface. (2) Footnote digits stay attached to ORV surfaces ("Yoo Sangah-ssi2"). (3) "Predicaments" is accepted 12 times
as an organisation through the gazetteer.

**Verdict.** On the 3-5 chapter slices and the 32-chapter RI run, hybrid finds more real people (RI person-kind entities 22 to
35) and keeps escalation flat, but it also admits non-person capitalised terms and a few junk surfaces, and on the RI hard
cases it fixes nothing. LitBank proper-name coreference improves (CEAF-e F1 35 to 43 standard). The quality edge is real but
modest for a 2-3x time cost; the possessive bug should be fixed before it becomes the default. Not decided here.

**Model policy note.** qwen3:8b reports 8.2B in `ollama show`, above the 8.0B ceiling read literally (D70). It is not in the
engine registry, so `check_llm_model` passes it by its "8b" tag only. Whether it is an owner exception needs a decision before
a registry entry can be added.
