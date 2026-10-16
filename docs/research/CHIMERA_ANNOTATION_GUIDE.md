# CHIMERA pilot annotation guide (single annotator)

For: the owner, one sitting-day. Sheet: `data/eval/human_review_chimera_pilot.csv` (72 items, local only, gitignored). Do not share the sheet or the key; both contain excerpts of the novel.

This is a **single-annotator pilot**. There is no second annotator, so there is no agreement statistic. Results will be reported as counts with Wilson intervals only, labelled "single-annotator pilot".

## 1. What you are labelling

Each row marks one mention in the novel with `[[double brackets]]` inside a source window of about 400 characters. For each mention you give **two** answers:

1. **`reader_warranted`**: who a careful first-time reader of the book is warranted in taking this mention to refer to, **at that point in the text**, using only what has been read so far.
2. **`omniscient_id`**: who the mention actually refers to, using the whole book.

These two are often the same. They differ when the text withholds, disguises or later changes an identity. The comparison between them is the whole point of the pilot, so **do not make them agree out of habit**.

## 2. The cut point (what "so far" means)

The reader has read: every chapter before the mention's chapter, **and** the mention's chapter up to the **end of the sentence that contains the `[[mention]]`**. Nothing after that sentence. The mention's own sentence counts, because a reader reads the whole sentence before moving on (a name given in apposition, such as "his uncle Gu Yue Dong Tu", is therefore known).

If you remember the book or know a spoiler, ignore it for `reader_warranted`. Use the window and the earlier text. When you cannot tell what you would have believed, say `UNDETERMINED` rather than guessing.

## 3. Allowed answers

For both `reader_warranted` and `omniscient_id`:

| Answer | When |
|---|---|
| a candidate **letter** (`A`, `B`, ...) from the `candidates` column | the entity is in the list |
| **free text** (a name) | the entity is real but not in the list |
| `NEW` | a person or thing not yet introduced that the reader cannot name yet |
| `UNDETERMINED` | the reader (or, for omniscient, the book) does not settle it |
| `NOT_AN_ENTITY` | the highlighted words do not refer to an individual (a ritual, an event, a generic noun) |

The candidate list is a shortlist built the same way for every item. It always contains some entities and some decoys, and the correct answer may not be on it. **Never choose a letter just because it is there.**

**Misdirection.** If the text deliberately leads the reader to a cover identity (someone disguised, or the narrator misleading), the reader-warranted answer is the cover identity, and the omniscient answer is the real one. Say so in `notes`.

**Title and relational words** ("the clan head", "his uncle", "junior brother"): the reader-warranted answer is whoever holds the title or relation *at that point as far as the reader has been told*. If the text has not yet said who, answer `NEW` or `UNDETERMINED`.

## 4. The other columns

| Column | What to write |
|---|---|
| `reader_evidence` | the chapter and a short quote (or character offset) that supports your reader answer, or the last place the information was missing |
| `omniscient_evidence` | the chapter and a short quote that settles the true identity |
| `reveal_chapter` | the chapter where a reader first gets enough to know the true identity. **Leave blank if the reader already knew** (both answers agree and nothing was withheld) |
| `confidence_1to3` | 1 = unsure, 2 = fairly sure, 3 = certain |
| `minutes_spent` | honest wall-clock minutes for this item (used to plan the next batch) |
| `notes` | anything odd: wrong highlight, misdirection, you used an outside spoiler, etc. |
| `annotator` | your name, on **every** row you label |
| `provenance` | the word `HUMAN` on every row you label |

Leave items you cannot judge **blank** and say why in `notes`. Do not fill a row with a placeholder.

## 5. Order and pacing

The sheet is ordered with the **pre-reveal candidates first**: batch 1 (items CP-001 to CP-024) is almost entirely those. If time runs short, finish batch 1 before the rest, because those are the items the pilot most needs. Batches 2 and 3 are mixed. Estimate: 5-10 minutes per item; 72 items is roughly 6-12 hours. Fewer than 72 is fine; the first 24 matter most.

Do not use any model, search a summary, or look at a machine's answer. The sheet carries no machine suggestion; the separate key file stays untouched.

## 6. Worked examples from the repo's own cases

These are illustrations of the rules, **not answers for the sheet**:

- *Reveal at the mention.* "It was actually his older brother Fang Yuan who had grasped his collar" (ch 6). Before this sentence the reader does not know who pulled him up. At the end of this sentence the mention "Fang Yuan" refers to Fang Yuan (both answers agree, reveal chapter = 6 if you are labelling an earlier unnamed reference).
- *Manufactured doubt.* "Who told you I was Gu Yue Fang Yuan?" (ch 32). The speaker tries to make the listener doubt his identity. For `reader_warranted`, decide what a reader who has followed the story believes; for `omniscient_id`, the true person. If the text leaves the reader unsure, `UNDETERMINED`.
- *Not an entity.* "the Awakening Ceremony" is an event, so `NOT_AN_ENTITY`.

## 7. What the pilot can and cannot say

It reports how many of the 72 items have `reader_warranted` different from `omniscient_id`, with Wilson intervals, and gives the first honest count of pre-reveal items in the book. It cannot give an agreement statistic, cannot represent the whole novel (the items are chosen, not sampled), and cannot support any claim about other novels. It is evidence for the novelty report's "what could be measured and how big the effect set is", not a benchmark.

## 8. Reference

The reader and omniscient views follow the idea in KoCoNovel (Kim, Lee, Lee, arXiv 2404.01140): in the Reader version, entities that the text keeps separate until a reveal stay separate; in the Omniscient version they are merged (the paper's Table 3: "Taehoon", "Kyungsuk" and "Ms. B" are separate for the reader and one entity for the omniscient author) [PUB, read]. I read the paper's introduction and Table 3; I did not read its full annotation guidelines section, so this guide is **not** a reproduction of their protocol.
