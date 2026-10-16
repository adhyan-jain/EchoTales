# PD reveal benchmark: draft event additions (v7, fame-stratified), selection notes

Companion to `docs/research/preregistrations/PD_events_v7_additions.json` and `docs/research/preregistrations/PD_v7_fame_snapshot.txt`. Status: **draft, not frozen**, not in any MANIFEST, not read by `pd_reveal_benchmark.py` or `pd_v2.py` (using v7 needs a builder change and a new manifest, both deliberately not done here). Provenance: selected by model-drafter, exact-search verified, fame class fixed by Gutenberg top-100 rule before any model run, owner spot-check pending. No label is human-verified.

**Purpose:** prospectively test one hypothesis, *the leakage gap is larger for famous books than obscure books*, with a fame label that is fixed by an objective rule rather than by the drafter's judgement.

**Shortfall, stated first:** the brief asked for 12 to 16 events with at least 6 famous and 6 obscure. This file has **9 events: 5 famous, 4 obscure**. The default bounds therefore report `FAIL file: 9 events, need 12..16` (and the 6/6 minimum is not met); with `--min-events 1` the verifier reports **FAIL 0, WARN 1** for all nine. I did not pad the set with events I could not verify. I reached the download cap (30 text files, the brief said about 28) and stopped there.

## The fame rule (fixed before drafting)

- Fetched `https://www.gutenberg.org/browse/scores/top` on 2026-10-16 at 04:54 UTC, before opening any candidate text. The three "Top 100 EBooks" lists (yesterday, last 7 days, last 30 days) are saved, titles and ranks (plus the Gutenberg id and no download counts), in `PD_v7_fame_snapshot.txt` (sha256 `6c9c4297...2e73db`, also recorded in the JSON `note`).
- **famous** = the book's title (or Gutenberg id) appears in any of the three lists; **obscure** = it appears in none. `scripts/chimera/pd_verify_v7.py` recomputes the class from the snapshot for every event and FAILs on a mismatch; a famous event's `fame_evidence` must cite a `<list> #<rank>` that the snapshot contains, an obscure event's must be exactly `absent from all Top-100 lists`.
- Caveats on the rule, stated so the analysis does not over-read it. (1) The lists are one-month popularity snapshots, so "famous" means "in the Gutenberg Top-100 now". Two famous events here (The Green Mummy, The Secret of Chimneys) are not canonical books; they are listed because of transient download spikes. (2) The rule does not look at fame outside Gutenberg: a well known book that happens to be absent from the lists would be classed obscure. I avoided that by not drafting from books I knew to be widely known but absent from the lists (Frankenstein, Dorian Gray, Our Mutual Friend, Treasure Island and the like were not tried), except The Valley of Fear (VF, below), which is obscure by the rule but is a Holmes novel. (3) Both classes contain Doyle and Hume or Christie-style detective fiction, so genre and author are partly balanced but not controlled; the class split is 3 Doyle events (2 famous, 1 obscure).
- No adaptation search was run for the obscure books; "none recalled" in the JSON means exactly that.

## Events (9)

| id | fame | book (Gutenberg id) | alias -> identity | cutoff | verifier |
|---|---|---|---|---|---|
| GM | famous (yesterday #10, last 7 #11, last 30 #11) | The Green Mummy, Hume (2868) | Captain Hervey -> Vasa | chapter XVIII start, 18,710 chars before anchor | pass |
| CH | famous (yesterday #6, last 7 #6, last 30 #7) | The Secret of Chimneys, Christie (65238) | Mademoiselle Brun -> Queen Varaga | chapter 28 start, 15,349 | pass, WARN no post alias |
| LP | famous (yesterday #24, last 7 #17, last 30 #23) | Extraordinary Adventures of Arsene Lupin, Leblanc (6133) | Jean Daspry -> Arsène Lupin | mid-story phrase, 4,296 | pass |
| BS | famous (yesterday #77) | The Memoirs of Sherlock Holmes, Doyle (834) | Blessington -> Sutton | mid-story phrase, 4,196 | pass |
| LF | famous (yesterday #75) | The Return of Sherlock Holmes, Doyle (108) | Eduardo Lucas -> Henri Fournaye | mid-story phrase, 1,439 | pass |
| MS | obscure | Mr. Standfast, Buchan (560) | Moxon Ivery -> Graf von Schwabing | mid-chapter phrase, 19,445 | pass |
| CS | obscure | The Circular Staircase, Rinehart (434) | Alex -> Jack Bailey | chapter XXXIV start, 8,099 | pass |
| RR | obscure | The Red Redmaynes, Phillpotts (14167) | Giuseppe Doria -> Michael Pendean | chapter XVII start, 10,312 | pass |
| VF | obscure | The Valley of Fear, Doyle (3289) | McMurdo -> Birdy Edwards | chapter 'Danger' start, 29,648 | pass |

Pre-cutoff alias occurrences (all >= 3): GM 51, CH 8, LP 41, BS 20, LF 11, MS 92, CS 62, RR 250, VF 161. Every event passes: anchor found exactly once, cutoff strictly before it, 7 to 9 cast names, every non-identity cast name mentioned before the cutoff, the v2 control selector yields 8 items per event, and no prefix sentence holds an alias together with the full identity name. v2-builder item counts the verifier computes: pre/post/ctrl 72/13/72 = 157 items.

Per event (the full caveats are in the JSON):

- **GM.** Famous, but only through a download spike. The anchor is the first sentence in the book with both forms ("Thank you, Vasa," said De Gayangos, and Hervey, changing color); the narrator confirms three sentences later. Vasa is a missing thief in the prefix (27 mentions), and his description (scar, wrist tattoo) is in the prefix; no sentence joins Hervey and Vasa.
- **CH.** The anchor is Battle's question about "the lady who is dead"; the alias is not in the sentence (Mademoiselle Brun was shot at the end of the previous chapter). Hint-rich gap (the Baron's "She was killed ... On the steps of the Palace"). Only 8 pre-cutoff alias occurrences, and the alias never recurs after the reveal. Weakest of the famous events on gap hints.
- **LP.** Weak oracle: identity name saturates the prefix (the hero of the whole collection), the story's frame question names Lupin, and the first spoken equation ("Your name?" "Arsène Lupin.") is inside the gap. Included because the narrator's sentence is explicit and the alias appears 41 times before it. Translation (Teixeira de Mattos).
- **BS.** Cleanest single-sentence equation in the set ("Then Blessington must have been Sutton."), and Sutton never occurs before it. The gap already says "this so-called Blessington".
- **LF.** A newspaper-dispatch statement inside the story that Holmes then accepts ("this mad wife of his"). Fournaye never occurs before the telegram. Very short gap.
- **MS.** Sentence is explicit and the identity name is absent from the prefix, but the gap (19,445 chars) is Blenkiron's whole account of the Graf, so the equation is implicit long before the anchor. The cutoff is the question "Who is Ivery anyhow?".
- **CS.** First alias+identity sentence in the book ("So it was Alex, Jack Bailey, who had been our ghost"); Jack Bailey is in the prefix as the missing cashier; no sentence or 200-character window joins him with Alex.
- **RR.** Detective's explanation; the sentence is phrased "I had not imagined Doria and Michael Pendean were one and the same person", affirmed a few sentences later ("this double impersonation"). The Pendean surname is a cast cue through Jenny Pendean. 10 prefix sentences with an alias and a name token were read (Doria and Mrs. Pendean, his wife): not an equation.
- **VF.** Obscure by the rule only. Anchor is McMurdo's spoken "I am Birdy Edwards!" with a gap in which McMurdo says he knows Edwards "not here under that name". Recommend an analysis with and without it, because a Holmes novel is a different kind of "obscure" from the others.

## Dropped (checked and rejected; reason)

- **The Hound of the Baskervilles (2852, famous):** Stapleton is a Baskerville is said by Holmes before the retrospection ("The fellow is a Baskerville--that is evident"), and the retrospection anchor ("whose real name is the same as his father's") does not contain the alias; the equation is already in a cutoff-eligible prefix.
- **The Return of Sherlock Holmes, other stories:** only one event per book; "none other than my strange old book collector" (Empty House) is Holmes but the alias is a descriptor, not a name.
- **The Memoirs of Sherlock Holmes, The Gloria Scott:** a clean statement ("My name, dear lad, is not Trevor. I was James Armitage") but the alias Trevor is shared with the son Victor, so alias mentions are ambiguous; the other Memoirs story (BS) was kept instead. The Stockbroker's Clerk paragraph ("Hall Pycroft ... none other than Beddington") was dropped unread-to-the-end: the newspaper line calls the new clerk Hall Pycroft "none other than Beddington" while I recall Pycroft as the story's dupe, so it may be an impersonation rather than an alias; not verified, not used.
- **The String of Pearls (59828, famous):** "Thornhill was no other than Mark Ingestrie" is Johanna's theory, repeatedly doubted ("Thornhill was not Mark Ingestrie") and in the end they are two men. A trap; not an equation.
- **Cynthia's Chauffeur (31472, famous):** the narrator tells the reader early that the chauffeur is Medenham (equation in the prefix).
- **Linnet (48296, famous):** alias Forstemann first occurs inside the chapter holding the reveal; 0 pre-cutoff alias occurrences.
- **The Mystery of a Hansom Cab (4223, obscure):** the verifier caught the equation in the prefix ("Rosanna Moore, better known as Musette of the Frivolity"). Also a false-positive on the title head check against v1's Yellow Room; fixed in no file (a note for the verifier: the three-word title-head check is blunt).
- **The Leavenworth Case (4047, obscure):** the alias Robbins occurs only twice before the servant says the caller "called himself" Robbins and gave the name Clavering; the equation is nearly in the prefix and the alias count is below 3.
- **The Law and the Lady (1622, obscure):** a clean sentence ("Her name (and consequently her son's name) is Macallan", chapter V) but the opening 55,000 characters name only Valeria, Eustace, Starkweather and Benjamin; no 7-name cast with >= 8 non-identity mentions.
- **Roger Ackroyd (69087, famous):** Ursula Bourne -> Ursula Paton shares the first name (lexical cue) and Ralph Paton is a main cast name.
- **The Great Impersonation (5815):** the Von Ragastein/Dominey swap is set up in the prologue, long before the alias; not read to the end.
- **Trent's Last Case, The Beetle, The Big Bow Mystery, Dracula, The Sign of the Four, Lorna Doone, Twenty Years After, The Innocence of Father Brown, The Lady of the Lake, Under the Red Dragon, Thuvia, The Passionate Elopement:** scanned by keyword and by reading around matches; no explicit alias-to-identity sentence I could verify (Lorna Doone's Dugal parentage and Twenty Years After's Mordaunt are descriptions of descent, not names; The Lady of the Lake's identity is "Scotland's King"). Not exhaustively read.
- **Not tried** (no download budget): Carmen (2465), Edwin Drood, A Tale of Two Cities, Frankenstein, Dorian Gray, Treasure Island and other ideas in the brief.

## Verification

`python scripts/chimera/pd_verify_v7.py --events docs/research/preregistrations/PD_events_v7_additions.json --texts data/raw/pd_gutenberg_v7 --min-events 1` -> **TOTAL events 9; FAIL 0; WARN 1; famous 5, obscure 4**. With default bounds: `FAIL file: 9 events, need 12..16`. The verifier is `pd_verify_v6.py` with: schema v1 + fame + fame_evidence, fame recomputation from the snapshot, no author restriction, v6 events added to the used set plus the brief's list of ids, default bounds 12..16, and famous/obscure counts.

## What is not verified

- **Cross-sentence and pronoun equations** are not detected by any check here. The prefix of each event was read only around the anchors, around the identity-name mentions, and for the specific hint sentences quoted in the caveats. I did not read any novel in full.
- **Label noise from shared surfaces:** Alex (CS) is a first name, McMurdo and Hervey are unique, "Brun" (CH) is also a part of other names; I did not read each mention. Cast mentions such as 'Peter', 'Mary' and 'Jenny' were taken to be single persons.
- **Fame in the wider world** was not measured; the rule uses only the Gutenberg lists at one time, and the lists move daily.
- **Unmatched hypothesis balance:** 9 events (5 versus 4) is too few for a well-powered famous-versus-obscure comparison; the cutoff style is not uniform (BS, LF, LP, MS are mid-chapter cutoffs because the alias did not occur before the chapter start).
- **Owner spot-check of all 9 anchors is pending.** Each takes under a minute: search the Gutenberg file for the `reveal_sentence` (spaces in the anchor may be line breaks in the file; GM, LP and VF anchors contain a curly quote or accent).

## Method and housekeeping

New files only: `PD_v7_fame_snapshot.txt`, `PD_events_v7_additions.json`, `PD_EVENTS_V7_NOTES.md`, `scripts/chimera/pd_verify_v7.py`; 30 Gutenberg texts in the git-ignored `data/raw/pd_gutenberg_v7/` (polite user agent, 2-second sleeps, `cache/epub/ID/pgID.txt`, `*** START` and `*** END` markers present in all 30). 9 catalog searches (not texts) were used to find ids. No existing file was edited; no ollama, GPU or API key was used; nothing was committed.
