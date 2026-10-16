# Event-mining rules for the confirmatory study (version 1; fixed before any mining or model call)

Part of `PREREG_PD_CONFIRM.md`. Hash in `MANIFEST_PD_CONFIRM.json`. A change is a new version, never an edit. Everything below is decided before a single candidate passage is read.

## 1. Eligible books
- Source: Project Gutenberg plain-text eBooks, language `en`, type Text, public domain in the US, first published before 1928; the Gutenberg catalogue file (`pg_catalog.csv`) fetched once and its SHA-256 recorded with the retrieval date.
- Fiction only: catalogue subjects contain "Fiction" or the LCC class starts with PR, PS or PZ; exclude subjects containing "Drama", "Poetry", "Essays", "Letters" or "Biography".
- Length: 40,000 to 400,000 words after stripping the Gutenberg header and footer (`*** START` and `*** END` markers).
- Excluded: every Gutenberg id used in PD v1 to v7 (list frozen in `PD_CONFIRM_excluded_books.json`, hashed) and any book whose text lacks the START and END markers. Translations are allowed but flagged; at most 15% of retained books may be translations.

## 2. Book sampling (stratified by fame, seeded)
- Fame band for stratification: `W` = number of Wikipedia language editions of the book's Wikidata item, fetched from the public Wikidata API (retrieval date and item id recorded; books without an item get W = 0). Bands: high (W >= 20), mid (3 <= W < 20), low (W < 3).
- Draw 40 books per band uniformly at random from the eligible list with seed 20261101 (120 candidate books). If a band has fewer than 40 eligible books, take all of them and record the shortfall.
- Books are mined in the drawn order until the targets below are met; the order and every skipped book are logged.

## 3. Candidate generation (deterministic)
- Reveal-cue patterns, fixed list, case-insensitive, matched on sentences: `was none other than`, `was in reality`, `was in fact`, `was really`, `in reality`, `the real `, `disguised as`, `in disguise`, `under the name`, `under the assumed name`, `assumed the name`, `alias`, `otherwise known as`, `known to the world as`, `threw off his disguise`, `threw off her disguise`, `unmasked`, `revealed himself`, `revealed herself`, `you are the`, `it was he who`, `it was she who`. (This restricts events to reveals stated in a sentence of this kind; stated as a limitation.)
- A candidate passage is the matching sentence plus the two preceding sentences; it must contain at least two distinct capitalised name surfaces of three or more letters.

## 4. Extraction (fixed prompt, model, temperature)
- Miner: `gpt-4o-mini` at temperature 0 reads each candidate passage and returns JSON `{alias_surfaces, identity_name, reveal_sentence}`; `reveal_sentence` must be a verbatim substring of the passage (whitespace-insensitive) or the candidate is dropped. The miner prompt is stored in `PD_confirm_prompts_v1.json` and hashed.
- Alias surfaces are the expressions the book uses for the person before the reveal; the identity name is the person's real name as the book gives it.

## 5. Deterministic verification (same rules as `pd_verify_v6.py` and `pd_verify_v7.py`)
For each candidate event, on the full book text:
1. the reveal sentence occurs exactly once (whitespace-insensitive search);
2. the cutoff is the start of the nearest chapter heading before the reveal, or, if the alias does not occur before that heading, a fixed phrase position at least 200 characters before the reveal sentence; the cutoff precedes the reveal;
3. at least 3 alias occurrences before the cutoff and no alias occurrence within 200 characters of an identity token before the cutoff;
4. no sentence before the cutoff contains both an alias surface and an identity token;
5. the identity name shares no capitalised token with any alias surface (no lexical cue);
6. the cast list is the 7 to 9 most frequent non-identity capitalised name surfaces in the prefix (tie-break alphabetical), plus the identity; at least 8 mentions of non-identity cast names before the cutoff.

## 6. Independent audit
An auditor model of a different family from the miner (a model served by a different vendor where one is available; otherwise a different model, flagged) reads the reveal sentence and the two sentences before it and labels it EXPLICIT, IMPLIED or NOT_SUPPORTED for the claim "alias is identity". Events labelled EXPLICIT form the **primary set**; the others are kept as the **secondary set** and reported separately. The auditor prompt is hashed with the miner prompt.

## 7. Selection and caps
- At most 5 events per book (seeded random choice among the verified events of that book); total target 150 to 250 events from at least 60 books. If the mining yields fewer, the shortfall is reported and no event is padded in.
- Events are ordered and numbered by book id then reveal position; the final list, cast lists, aliases, anchors, fame variables and split assignment are written to `PD_confirm_events_v1.json` and hashed **before any model sees any item** (checkpoint CP-L).

## 8. Fame variables (fixed before any model call)
`F_wiki` = log2(1 + W) with W as in section 2 (primary). `F_dl` = log10(1 + Gutenberg downloads in the last 30 days at retrieval, from the book page; recorded with the date) (secondary). A model-specific recognition score from the title-assisted probe is **exploratory only**.

## 9. Split
Books, not events, are assigned: dev if `int(SHA-256(str(gutenberg_id) + "20261101")[:8], 16) % 100 < 20`, else test. Dev items are used only to confirm that every prompt parses and that no answer format fails; no prompt, rule or threshold may be changed after the dev run.

## 10. Items per event
Pre-reveal alias mentions: up to 6, evenly spaced over the prefix. Post-reveal alias mentions: up to 2 (none if the alias does not occur after the reveal). Plain controls: 4 (two non-identity cast names with the most prefix mentions, two evenly spaced mentions each). Window: the last 1,200 characters ending at the end of the mention's sentence, mention marked `[[ ]]`. Candidates: the cast list in a seeded shuffle (seed 20261101 plus the item index), identical in every arm and model, plus `UNDETERMINED`.

## 11. Known biases of these rules (stated now)
Events are limited to reveals stated in a sentence matching the cue list; the miner and auditor are both language models (no human check, by owner decision); the fame bands rest on Wikipedia coverage, which tracks Western canon; the cast-list rule can include a name that is a nickname of the identity (the verifier catches shared tokens only).
