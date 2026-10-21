# Public-domain events set: v2, v3, v6, v7 notes

> Merged on 2026-10-22 from 4 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/research/PD_EVENTS_V2_NOTES.md -->
## Source: `docs/research/PD_EVENTS_V2_NOTES.md`

# PD reveal benchmark: draft event additions (v2), selection notes

Companion to `docs/research/preregistrations/PD_events_v2_additions.json`. Status: **draft, not frozen**, not in `MANIFEST_PD.json`, not read by `scripts/chimera/pd_reveal_benchmark.py` (whose `load_events` reads only the hash-checked v1 file; using v2 needs a builder change and a new manifest, both deliberately not done here). Provenance: selected by model-drafter, exact-search verified, owner spot-check pending. No label is human-verified.

Verification tool: `scripts/chimera/pd_verify_additions.py --events <json> --texts <dir with pgNNN.txt>` (imports the builder's `load_text`, `locate`, `control_mentions`, `surfaces_for`, `build_items`). Result on the 12 events: **FAIL 0, WARN 1, exit 0**, 150 items in the builder dry run. Checks per event: schema keys equal v1; id and Gutenberg id distinct from v1 and within the file; cast size 7 to 9 with the identity in it; reveal sentence found by whitespace-insensitive exact search **exactly once** in the book body; cutoff strictly before the reveal; at least 3 pre-cutoff alias occurrences; at least 3 usable control mentions; every non-identity cast name occurs before the cutoff.

Everything below is a count of the verification run; the reveal anchors are short fragments of public-domain text (as in v1), no other novel text is stored.

## Events kept (12, all from different books, no v1 book reused)

| id | book (author, origin) | pg | alias surfaces -> identity | pre / post alias occ. | cut-to-reveal chars | note |
|---|---|---|---|---|---|---|
| MC | The Count of Monte Cristo (Dumas, French, English translation) | 1184 | Sinbad the Sailor -> Edmond Dantès | 30 / 7 | 5,702 | gradual, see caveat 1 |
| LM | Les Misérables (Hugo, French, translation) | 135 | M./Monsieur/Mayor/Father Madeleine -> Jean Valjean | 120 / 92 | 35 | narrator sentence, single |
| JH | Jekyll and Hyde (Stevenson) | 43 | Mr. Hyde, Hyde -> Henry Jekyll | 50 / 49 | 14,058 | famous twist |
| IV | Ivanhoe (Scott) | 82 | the Black Knight -> Richard Plantagenet | 37 / 6 | 29,907 | label name differs from sentence wording |
| MI | The Mysterious Island (Verne, French, translation) | 1268 | genius of the island, mysterious being -> Captain Nemo | 12 / 0 | 1,248 | no post items (WARN) |
| VI | Villette (C. Bronte) | 9182 | Dr. John -> Graham Bretton | 55 / 78 | 22,920 | narrator sentence |
| SA | The Secret Adversary (Christie) | 1155 | Mr. Brown -> Sir James Peel Edgerton | 62 / 4 | 9,104 | villain's own speech |
| DL | Daddy-Long-Legs (Webster, epistolary) | 157 | Daddy-Long-Legs, Daddy -> Jervis Pendleton | 177 / 9 | 18 | reveal is a salutation |
| DQ | Don Quixote (Cervantes, Spanish, Ormsby translation) | 996 | Knight of the Grove/Mirrors -> Samson Carrasco | 4 / 6 | 20,969 | only 4 pre alias occ. |
| WW | The Woman in White (Collins) | 583 | woman in white -> Anne Catherick | 8 / 11 | 1,193 | hint-rich prefix |
| OT | Oliver Twist (Dickens) | 730 | Monks -> Edward Leeford | 85 / 39 | 4,390 | reveal in speech; name absent in prefix |
| TM | The Three Musketeers (Dumas, French, translation) | 1257 | Milady -> Anne de Breuil | 212 / 477 | 4,205 | reveal in Athos's speech |

Spread: 11 authors (Dumas twice, via MC and TM); Bronte (VI) and Dickens (OT) also appear in v1 under other books (JE, GE), the books themselves differ. Five are translations (MC, LM, MI, TM from French; DQ from Spanish). Genres: adventure, gothic, crime/spy, epistolary romance, epic comedy, sensation, social novel, scientific romance. If the owner wants strictly one book per author, drop TM (or MC); VI and OT are the next candidates.

## Per-event notes and caveats

1. **MC (Monte Cristo)** - The text-derived sentence is the dying Morrel's last words, `Maximilian, it was Edmond Dantès!`, reported by his son: the mysterious benefactor who saved the Morrels (signing as Sinbad the Sailor) was Edmond Dantès. This is a character's conviction, later confirmed by the plot, not a narrator statement. The Count = Sinbad link is already in the prefix (Italy chapters), and the Count is deliberately not in the cast (he is the same person as the answer). Other candidate reveals exist later (Mercédès recognises him as Edmond; `I am Edmond Dantès!` to Villefort, about 1.26M characters later) but they all come after this one; this earliest explicit sentence was chosen so the prefix contains none. Result: pass, but the weakest oracle of the set and the one the owner should look at first.
2. **LM** - `The reader has, no doubt, already divined that M. Madeleine is no other than Jean Valjean.` Translation from French. No prefix sentence contains both an alias and a Valjean token (0). Cutoff = the chapter heading, 35 characters before the sentence, so the prefix is the whole Fantine arc up to that point.
3. **JH** - Lanyon's narrative: `there stood Henry Jekyll!`. Four prefix sentences contain both Hyde and Jekyll tokens; I read them (the will naming Hyde as heir, Utterson's worry, the stick presented to Jekyll, `that's not Jekyll's voice - it's Hyde's`), none equates them. Heavily memorised twist, likely strong closed-book hit.
4. **IV** - `I am Richard of England!` The Black Knight reveals himself to Locksley. The label name is Richard Plantagenet (given explicitly in the next chapters), not the phrase "Richard of England". Richard occurs in the prefix as the absent king. Cutoff is the start of the chapter, about 30,000 characters before the reveal (long distance, mostly in the over-20,000 bin).
5. **MI** - The narrator equates the benefactor with the person Harding has just called Captain Nemo; the name Nemo is absent from the prefix. Distance only 1,248 characters; **no post-reveal alias occurrence** (the alias surfaces are not used after the reveal), so no post items (WARN). "mysterious being" was checked at all 9 pre occurrences and refers to the benefactor, not generically.
6. **VI** - `this Graham Bretton, _was_ Dr. John: he, and no other`. Gutenberg italics marks (`_was_`) are part of the anchor. The boy Graham and Mrs. Bretton are in the prefix; Mrs. Bretton and Mr. Home are left out of the cast (shared surnames would add control-label noise). Same author as v1 JE, different book.
7. **SA** - the villain says the treaty is in the hands of Mr. Brown, so no one will search the pockets of Sir James Peel Edgerton. It is an implication in a single sentence, not "I am Mr. Brown"; the diary later states it at length. Same chapter earlier contains a decoy accusation (Julius is Mr. Brown). Weaker explicitness than JH or LM.
8. **DL** - **the reveal is only a compound salutation** (`Master-Jervie-Daddy-Long-Legs Pendleton-Smith`); cutoff 18 characters before it. A careful reader may have inferred it in the preceding letters (Master Jervie, Uncle Jervis, the pre-visit note). The 1 prefix sentence flagged for containing alias and a Pendleton token is a false positive (it is about Julia Pendleton). Julia Pendleton is entered as `Julia`, and Jimmie McBride is excluded, for shared-surname reasons.
9. **DQ** - Part II, Chapter XIV: `it is the rash and ill-advised bachelor Samson Carrasco, our fellow townsman`. **Only 4 pre-cutoff alias occurrences** (all `Knight of the Grove`), so there are 4 pre items rather than 8. Single-name cast entries (`Quixote`, `Sancho`, ...) avoid the `Don` and `Panza` shared-token problem. Translation (Ormsby) from 17th-century Spanish; archaic English may behave differently for small models.
10. **WW** - `We had identified the unhappy woman whom I had met in the night-time with Anne Catherick`. The prefix contains Mrs. Fairlie's letter about the child Anne Catherick and the discovery of the likeness, so the equation can be inferred; the explicit sentence is in the next chapter. Fairlie-family names are excluded from the cast for control-label noise; the cast is therefore the minimum 7 (Laura, Sarah are single-name entries). The alias is case-sensitive lower-case `woman in white` so the book title is not matched.
11. **OT** - `yes, Edward Leeford, even now`: Brownlow addresses Monks by his real name. Name absent from the prefix (the only event besides GE and SS in v1 for which this holds, hence the verifier's identity-may-be-absent exemption). Same author as v1 GE.
12. **TM** - `the name Milady Clarik concealed Anne de Breuil`, spoken by Athos in the confrontation chapter; the Comte de la Fère equation is in the same speech just before it. Milady also appears as Lady de Winter in the prefix. The Comte de la Fère appears in the book's preface as the memoir author, so that name is not a clean decoy and is not in the cast. Many post occurrences (477).

## Dropped (examined, not included)

- **The Hound of the Baskervilles (pg2852)**: the man on the tor = Holmes, but the alias `the man upon the tor` occurs only twice before the reveal (needs at least 3), and Stapleton/Beryl is a relationship reveal rather than an alias-to-identity one. Also a third Doyle book. Dropped.
- **The Tenant of Wildfell Hall (pg969)**: Mrs. Graham = Helen Huntingdon is revealed gradually through a diary (no single explicit sentence found), and the Gutenberg text contains front-matter that mentions Huntingdon. Dropped.
- **The Scarlet Letter (pg25344)**: Chillingworth is Hester's husband from the first chapters, and Dimmesdale as Pearl's father is revealed gradually with no stable alias surface. Dropped.
- **Other candidates not downloaded** (Kidnapped, Zenda, Treasure Island, Moonstone, Lady Audley, Mystery of the Yellow Room, Hunchback, Silas Marner, Tom Jones, Pudd'nhead Wilson, the Odyssey): not examined for lack of a certain Gutenberg id or because the identity reveal is not an alias-to-name equation; this is a limit of my search, not a finding that they are unsuitable. 13 files were downloaded in total (pg43, 1155, 157, 82, 1268, 969, 9182, 1258, 996, 583, 25344, 730, 1257); pg1258 is *Ten Years Later* (wrong guess for The Three Musketeers) and pg969, pg25344 were downloaded but unused.

## What is not verified

- Whether each reveal sentence is the **earliest** explicit equation in the book was checked by searching same-sentence co-occurrence of alias and identity tokens before the cutoff (0 hits except JH 4 and DL 1, read by hand) and, for MC, WW, TM, by reading the passages. It was not checked by a full close read of each novel; a careful reader may find an earlier hint or statement.
- The 150 items are a builder dry run (offsets only, nothing written to `data/`), not a built manifest.
- Control-mention label noise (a surface such as `Hartright`, `Beck`, `Quixote` standing for one cast name) is flagged by the verifier only when the chosen surface is a token of another cast name; it printed no such warning on the final cast, but it cannot detect different people sharing a name (e.g. `Judy`, `Tommy` are unambiguous here; `Fantine`, `Cedric`, `Utterson`, `Pencroft`, `Franz` were spot-chosen by count).
- Owner spot-check of all 12 reveal anchors: pending. Each takes under a minute: search the Gutenberg text for the `reveal_sentence` (spaces in the anchor may be line breaks in the file).

---

<!-- merged-from: docs/research/PD_EVENTS_V3_NOTES.md -->
## Source: `docs/research/PD_EVENTS_V3_NOTES.md`

# PD reveal benchmark: draft event additions (v3), selection notes

Companion to `docs/research/preregistrations/PD_events_v3_additions.json`. Status: **draft, not frozen**, not in any MANIFEST, not read by `pd_reveal_benchmark.py` or `pd_v2.py` (whose event-file lists are hash-checked; using v3 needs a builder change and a new manifest, both deliberately not done here). Provenance: selected by model-drafter, exact-search verified, owner spot-check pending. No label is human-verified.

Purpose: a third, fully fresh set for a confirmatory re-test. Every book is new (none of the 19 books of v1 and v2), the 12 authors are new except that Leroux (YR) also wrote the v1 Phantom of the Opera (one earlier book, so no author reaches three), and 10 of 12 books are original English.

Verification tool: `scripts/chimera/pd_verify_v3.py --events <json> --texts <dir with pgNNN.txt> [--cleared VW,EL]`. It reuses `pd_reveal_benchmark.py` (`load_text`, `locate`, `surfaces_for`, `sentence_end`, `spaced`) by import and re-implements the `pd_v2.controls` selector locally. Result on the 12 events: **FAIL 0, WARN 0, exit 0 with `--cleared VW,EL`** (without it, VW and EL fail on one sentence each, both read by hand and cleared below). 216 items would be built: 96 pre, 24 post, 96 plain controls (8 per event). Checks per event, all pass: schema keys equal v1; event id, Gutenberg id and title distinct from v1, v2 and each other; cast 7 to 9 with the identity in it; anchor found by whitespace-insensitive exact search **exactly once** in the book body; cutoff anchor found and strictly before the anchor; at least 3 pre-cutoff alias occurrences (the smallest is 14); the v2 control selector yields **8 items** (two cast names, four mentions each); at least 8 non-identity cast mentions before the cutoff (the smallest event has 151); every non-identity cast name occurs before the cutoff; no prefix sentence has an alias and the full identity name, except two read and cleared by hand; no control surface is a surface of another cast name (WARN 0). Anchors are short fragments of public-domain text (12 to 125 characters), as in v1 and v2; no other novel text is stored.

Reported but not tests: the number of alias occurrences within 200 characters of the full identity name in the prefix (0 for ten events, 1 for VW, 3 for EL, all in the cleared sentences or their neighbours), and the first alias+full-identity sentence in the whole book relative to the anchor (in the table below).

## Events kept (12, all from different books)

pre / post = alias occurrences before the cutoff / after the anchor. gap = characters from cutoff to anchor. Identity in prefix: whether the identity name (any token) occurs before the cutoff.

| id | book (author, year) | pg | alias surfaces -> identity | pre / post | gap | identity name in prefix | note |
|---|---|---|---|---|---|---|---|
| KM | King Solomon's Mines (Haggard, 1885) | 2166 | Umbopa -> Ignosi | 50 / 15 | 3,464 | yes (5, as the lost child) | assumed name, spoken |
| VW | The Vicar of Wakefield (Goldsmith, 1766) | 2667 | Mr Burchell, Burchell -> Sir William Thornhill | 42 / 3 | 10,889 | yes (4, as the squire's uncle) | narrator, cleared sentence |
| LA | Lady Audley's Secret (Braddon, 1862) | 8954 | Lucy Graham, Lady Audley -> Helen Talboys | 116 / 104 | 62,353 | yes (6, as George's dead wife) | accusation, longest gap |
| CO | The Castle of Otranto (Walpole, 1764) | 696 | Friar/Father Jerome, Jerome -> Count of Falconara | 14 / 55 | 2,502 | no | short prefix, spoken |
| GG | The Great Gatsby (Fitzgerald, 1925) | 64317 | Jay Gatsby, Gatsby -> James Gatz | 116 / 144 | 1,149 | no (name Gatz absent) | narrator, heavily memorised |
| PG | Father Goriot (Balzac, 1835; English translation) | 1237 | M. Vautrin, Vautrin -> Jacques Collin | 117 / 37 | 45,706 | no (Collin absent) | translation, narrator |
| MK | The Monk (Lewis, 1796) | 601 | Rosario -> Matilda | 19 / 19 | 6,707 | no (0) | disguise, spoken |
| YR | The Mystery of the Yellow Room (Leroux, 1907; English translation) | 1685 | Frédéric Larsan, Larsan -> Ballmeyer | 150 / 74 | 16,988 | no (0) | translation, courtroom accusation |
| IM | The Invisible Man (Wells, 1897) | 5230 | the Invisible Man, the stranger -> Griffin | 74 / 57 | 6,833 | no (0) | generic descriptors as alias |
| RP | Riders of the Purple Sage (Grey, 1912) | 1300 | Bess -> Elizabeth Erne | 134 / 39 | 20,558 | token Erne only (40) | hidden parentage, spoken |
| EL | East Lynne (Wood, 1861) | 3322 | Captain Thorn, Mr. Thorn, Thorn -> Francis Levison | 215 / 126 | 11,856 | yes (207, as a separate person) | cleared sentence, spoken |
| BR | The Blithedale Romance (Hawthorne, 1852) | 2081 | Old Moodie, Moodie -> Fauntleroy | 38 / 3 | 16,571 | no (0) | **weakest oracle** |

Anchors and cutoffs (all located by exact search; cutoffs are the start of the chapter or scene named): KM chapter X start; VW chapter XXX start (the contents list is ignored by the builder's "nearest preceding match" rule); LA chapter XXVII start; CO the sentence before the unveiling of Theodore as the Friar's son; GG chapter VI start; PG the opening of the scene in which the police agent first meets Poiret and Michonneau; MK the sentence before Rosario returns to the bench and tells the dead-sister story; YR chapter XXVII start; IM chapter XVII start; RP chapter XXI start; EL chapter XXXVI start; BR the heading of chapter XXII.

Spread: 12 authors; years 1764 to 1925; gothic (CO, MK), eighteenth-century domestic (VW), sensation/domestic melodrama (LA, EL), adventure (KM), French social realism (PG), detective (YR), scientific romance (IM), western (RP), modernist (GG), American romance (BR). Reveal types: assumed name (KM, GG), disguise (MK, CO's title, EL), narrator-announced hidden identity (VW, PG), hidden parentage (RP), pseudonym/second identity (LA, YR, IM, BR). Translations: **2 of 12** (PG, YR), against 5 of 12 in v2.

## Per-event notes and caveats

1. **KM** - Umbopa, the Zulu hunter in the party, says he is Ignosi, the rightful king (spoken to Infadoos). Ignosi occurs 5 times in the prefix as the dispossessed child of the murdered king, never joined to Umbopa (0 alias+identity sentences, 0 alias occurrences within 200 characters). The cutoff is 3,464 characters before the anchor, at the chapter start, so the prefix has none of Umbopa's story. Captain Good is not in the cast because 'Good' is an ordinary word.
2. **VW** - the vicar, narrating, learns that Mr Burchell is Sir William Thornhill. One prefix sentence contains both names: Burchell comments in conversation on that gentleman's character, so it treats them as two people; **read and cleared by hand** (pass `--cleared VW`). Three further sentences with an alias and the token Thornhill (the squire, Thornhill-castle) were read and are not equations. Burchell's remarks about Sir William are hints a careful reader could use. The squire is not in the cast (shared surname).
3. **LA** - **accusation, not a narrator statement**: Robert Audley tells Lady Audley that Helen Talboys disappeared on one day and reappeared as Lucy Graham the next. A confession and a narrator line confirm it later, outside this event. The earliest narrator-level deduction joining the two names lies 40,415 characters before the anchor, after the cutoff (the cutoff, at chapter XXVII, is 62,353 characters before the anchor, the longest in the file). One prefix sentence has an alias and the tokens Helen and Talboys: Robert's thought listing Helen Maldon, Lady Audley and Clara Talboys as separate women, which treats them as different. Cast uses first names (Robert, George, Alicia, Phoebe, Luke) to avoid the shared Talboys and Audley tokens.
4. **CO** - Manfred tells the Friar that he is no longer Friar Jerome but the Count of Falconara. Falconara is absent from the prefix. The cutoff is placed before the unveiling of Theodore as Jerome's son, so the parentage reveal is not in the prefix. Only 14 pre-cutoff alias occurrences, all in chapter II. The identity label is a title. Spoken by a character, 2,502 characters before the anchor.
5. **GG** - Nick states that Gatsby's legal name was James Gatz. The only 'James' in the prefix is another man (James B. Ferret). The first occurrence of the token Gatz in the book is a sentence about 'James Gatz of North Dakota' 48 characters before the anchor, inside the gap (the cutoff, the chapter start, is 1,149 characters before the anchor), so the anchor is the first sentence stating the name as his real name, not the first mention of the token. Very heavily memorised: expect closed-book recall of Gatz. US public-domain text of a 1925 novel.
6. **PG** - English translation (Marriage) of a French novel. The narrator gives the real name of Vautrin as Jacques Collin. The cutoff is placed before the scene in which a police agent first accuses 'the so-called Vautrin' of being the convict nicknamed Trompe-la-Mort and then names Jacques Collin (about 4,000 characters after the cutoff; the agent says the minister only suspects). The chosen anchor is therefore the earliest **narrator** equation, not the earliest equation by any speaker, and the 45,706-character gap contains the agent's accusation. Collin is absent from the prefix; the token Jacques occurs 3 times there for a servant and a street name.
7. **MK** - the novice Rosario confesses to being a woman and says 'I am Matilda'. The cutoff precedes Rosario's dead-sister story, so 'Matilda' does not occur in the prefix at all and the false-sister decoy is not in it. Spoken by the character, confirmed at once by the narrator. Only 19 pre-cutoff alias occurrences.
8. **YR** - English translation (Teixeira de Mattos). Rouletabille tells the court that Larsan is Ballmeyer. Ballmeyer is absent from the prefix (0 of 28 occurrences in the book). The chapter at the cutoff also contains the earlier accusation that Larsan is the murderer, which is not an alias-to-identity equation. A courtroom accusation, confirmed later by the narrator. Same author as the v1 Phantom of the Opera event (different book).
9. **IM** - the lodger, called only 'the stranger' or 'the Invisible Man', names himself Griffin to Kemp. The alias surfaces are generic descriptors (they are how the narration refers to him; this is a weak-alias caveat, not a counting problem: 74 pre-cutoff occurrences). Griffin is absent from the prefix (0 of 27 occurrences in the book). Kemp (9 prefix mentions) is in the cast as a decoy, being the person addressed. Bunting is not in the cast because it names two people.
10. **RP** - Bess, who rode as the Masked Rider, is addressed by Jane as Elizabeth Erne after Lassiter explains her parentage (that explanation is after the cutoff). The token Erne occurs 40 times in the prefix for Milly Erne, 0 alias+token sentences. The Gutenberg front matter lists a line containing 'Bess' in the illustration captions (harmless). Jane is entered as a first name because 'Withersteen' is also a house and a herd name.
11. **EL** - the man believed to be the murderer under the name Thorn is Sir Francis Levison. Thorn (215 prefix occurrences) and Levison (207) are two separate people in the prefix. One prefix sentence has an alias and the full name: Barbara's journal says Richard knows Sir Francis Levison and that he and Thorn are intimate; it presents them as two people and is the opposite of an equation; **read and cleared by hand** (pass `--cleared EL`). A second sentence has Thorn and the title Captain Levison, again as two. The anchor is a witness's remark; Barbara's suspicion that the man is Thorn comes just after the cutoff, inside the gap, so the gap carries hints. The narrator's earlier statement that Madame Vine is Lady Isabel is not part of this event.
12. **BR** - **weakest oracle of the set**. The only sentence joining Moodie and Fauntleroy is the narrator's parenthetical question, 'or shall we call him Fauntleroy?'. The chapter that starts at the cutoff is titled with the name and tells the story of a man 'whom we shall call Fauntleroy', so the equation is strongly implied inside the gap and stated only in the anchor. Fauntleroy is absent from the prefix (0 of 20). Cast has only 7 names; only 3 post-reveal alias occurrences. A reasonable candidate to drop if the owner wants only explicit statements.

Weak oracles in this set, in order: BR (rhetorical question), LA (a character's accusation), YR and EL (accusations or remarks by characters, though later confirmed), CO (spoken address). Strongest: PG, GG, VW (narrator statements). IM's alias is generic. The two translations are PG and YR.

## Dropped (examined, not included)

- **Tarzan of the Apes (pg78)**: the narrator equates the baby Tarzan with Lord Greystoke in the early chapters, so any prefix already contains the equation. Dropped.
- **The House of the Seven Gables (pg77)**: the Holgrave = Maule equation is stated in the last chapter, but the Gutenberg body begins with an introduction that already says the Pyncheons and Maules unite through Phoebe and Holgrave (an alias+identity sentence in the prefix). Dropped.
- **Lorna Doone (pg840)**: the Dugal parentage is stated as 'Lorna's father was the Earl of Dugal', not as an alias-to-identity sentence; the full name 'Lorna Dugal' first occurs 82,000 characters later. No clean anchor. Dropped.
- **Tom Jones (pg6593)**: Mrs Waters being Jenny Jones is never stated with the name Jenny Jones in the late book (the name occurs 8 times, all in the first 340,000 characters); the late reveal is about Tom's parentage, with no alias surface. Dropped.
- **East Lynne, Madame Vine = Lady Isabel**: the narrator states it early (about 563,000 characters in, long before the other characters learn it), so no cutoff is both before the equation and after enough alias mentions. The Thorn = Levison event of the same book was used instead (EL).
- **The Blithedale Romance, Veiled Lady = Priscilla**: no explicit sentence; the unveiling is described without the name in the same sentence. The Moodie = Fauntleroy event of the same book was used instead (BR, flagged weak).
- **Not downloaded, so not examined**: The Prisoner of Zenda, The Thirty-Nine Steps, The Man Who Was Thursday, Evelina, A Little Princess, Frankenstein, Persuasion, Silas Marner, Daniel Deronda and others. This is a limit of my search and download budget (below), not a finding that they are unsuitable. 813 and The Hollow Needle (Leblanc, translations) were also left out to keep translations low.

## Download log and limits

17 fetches in total from gutenberg.org: one catalogue file (`pg_catalog.csv`, used to look up ids offline) and 16 book texts, 2 seconds apart, polite user agent, saved in `scratchpad/pd3/` (not in the existing `pd/` folder). That is two above the "about 15" guideline. Twelve of the 16 texts became events; four (pg78 Tarzan, pg77 Seven Gables, pg840 Lorna Doone, pg6593 Tom Jones) were downloaded and dropped. Nothing was written to the repository except the three new files (the event file, this notes file and `scripts/chimera/pd_verify_v3.py`); no existing file was edited.

## What is not verified

- Whether each anchor is the **earliest** explicit equation in the book was checked by (a) the whole-book scan for the first sentence containing both an alias and the full identity name, relative to the anchor (in the verifier output; it is before the cutoff only for VW and EL, both cleared, and equals or follows the anchor for the others except LA, where it is a narrator deduction 40,415 characters earlier, discussed above), (b) reading the passages around each anchor. It was not checked by a full close read of each novel; a careful reader may find an earlier hint, and the gap passages contain hints for LA, EL, KM and PG.
- Co-occurrence is tested by sentence and by a 200-character window; an equation phrased with pronouns across sentences would not be detected.
- Whether the Gutenberg text of each book is the author's text (front matter, introductions and illustration lists are in the body and are searched too; the Seven Gables introduction showed that this matters).
- Label noise from surface sharing among cast names was checked only by the verifier's rule (control surface equal to a surface of another cast name: none). Different people sharing one surface in the book (for example 'Richard' or 'Moses' referring to two people) were spot-checked for the control names only, not for every cast name.
- The 216 items are a dry-run count (selection rule of `pd_v2.build_items`), not a built manifest; nothing is written to `data/`.
- Owner spot-check of all 12 anchors: pending. Each takes under a minute: search the Gutenberg text for the `reveal_sentence` (spaces in the anchor may be line breaks in the file).

---

<!-- merged-from: docs/research/PD_EVENTS_V6_NOTES.md -->
## Source: `docs/research/PD_EVENTS_V6_NOTES.md`

# PD reveal benchmark: draft event additions (v6), selection notes

Companion to `docs/research/preregistrations/PD_events_v6_additions.json`. Status: **draft, not frozen**, not in any MANIFEST, not read by `pd_reveal_benchmark.py` or `pd_v2.py` (using v6 needs a builder change and a new manifest, both deliberately not done here). Provenance: selected by model-drafter, exact-search verified, owner spot-check pending. No label is human-verified.

**Shortfall, stated first:** the brief asked for 14 to 18 events. This file has **7**. Roughly one in four of the books I fetched held a clean, single-sentence alias-to-identity equation that is not already in the prefix; the rest are listed under "Dropped". I did not pad the set with events I could not verify. Run against the default bounds the verifier therefore reports `FAIL file: 7 events, need 14..18`; with `--min-events 1` it reports **FAIL 0, WARN 0** for all seven.

Anchor form differs and matters: **PN and AL** have an alias form and the identity name in the anchor sentence; **UD** has the bare first name 'Agnes' and the identity in it; **GP and TH** are explicit statements whose subject is the aliased person (the alias is named in the adjacent sentence, not in the anchor); **GR and CM** are weaker (flagged below). Only PN and AL are a single sentence joining an alias and the identity. One book was drafted and dropped by judgement (Monsieur Beaucaire, below).

Verification tool: `python scripts/chimera/pd_verify_v6.py --events docs/research/preregistrations/PD_events_v6_additions.json --texts data/raw/pd_gutenberg_v6 --min-events 1 [--show-token-sentences]`. It is `pd_verify_v3.py` plus: a sentence splitter that no longer ends a sentence at 'Mr.', 'Mrs.', 'Dr.', 'M.', 'Mme.' and similar (v3's splitter cut there and hid same-sentence alias/identity pairs; I found this while checking GP; the v3 events were not re-checked with the corrected splitter, so a same-sentence pair hidden by it in v3 would not have been seen); the used sets now cover v1, v2 **and v3** (event ids, Gutenberg numbers, first-three-word titles); the author in the last parenthesis of the book string must not be one of the 25 surnames that already have a book in v1 to v3 (hard-coded in the script); event-count bounds are arguments. It reuses `pd_reveal_benchmark.py` (`load_text`, `locate`, `surfaces_for`, `sentence_end`, `spaced`) by import and re-implements the `pd_v2.controls` selector locally. Texts are in `data/raw/pd_gutenberg_v6/` (git-ignored by `data/*`); `data/raw/pd_gutenberg/` was not touched.

## Result on the 7 events

All per-event checks pass: schema keys equal v1; id, Gutenberg number, title and author new; cast 7 to 9 with the identity in it; anchor found by whitespace-insensitive exact search **exactly once** in the book body; cutoff anchor found and strictly before it; at least 3 pre-cutoff alias occurrences (smallest 6); the v2 control selector yields 8 items per event; at least 8 non-identity cast mentions before the cutoff (smallest event 36); every non-identity cast name occurs before the cutoff; **no prefix sentence has an alias and the full identity name** (0 for all seven, no `--cleared` needed); no alias occurrence within 200 characters of the full identity name in the prefix (0 for all seven); no control surface is a surface of another cast name (WARN 0). Dry-run item count (rule of `pd_v2.build_items`): 54 pre, 14 post, 56 control = **124 items** (8 pre and 2 post per event except TH, which has 6 pre because it has 6 alias occurrences).

| id | book (author, year) | pg | alias surfaces -> identity | pre / post alias | gap (chars) | identity name in prefix | oracle |
|---|---|---|---|---|---|---|---|
| GP | The Great God Pan (Machen, 1894) | 389 | Mrs. Beaumont, Beaumont -> Helen Vaughan | 8 / 10 | 1,276 | yes (22 'Helen', as the woman also called Mrs. Herbert) | spoken, explicit |
| TH | The Man Who Was Thursday (Chesterton, 1908) | 1695 | Professor de Worms, de Worms -> Wilks | 6 / 5 | 17,528 | once, as a policeman's colleague | spoken, explicit |
| CM | Carmilla (Le Fanu, 1872) | 10007 | Carmilla -> Mircalla | 52 / 11 | 8,452 | yes (5, portrait scene) | **weak**, pronoun, hint-rich prefix |
| PN | The Pioneers (Cooper, 1823) | 2275 | Oliver Edwards, Edwards -> Effingham | 174 / 3 | 7,407 | surname only (15), for the old Major | narrator, explicit |
| GR | Graustark (McCutcheon, 1901) | 5142 | Miss Guggenslocker -> Yetive | 13 / 10 | 4,730 | no (0) | **medium-weak**, anchor has no identity name |
| AL | 813 (Leblanc, 1910; English translation) | 34758 | Prince Sernine, Sernine, Paul Sernine -> Arsène Lupin | 51 / 73 | 41,077 | yes (91, as a separate wanted man) | letter accusation, explicit |
| UD | The Mysteries of Udolpho (Radcliffe, 1794) | 3268 | sister Agnes, Sister Agnes -> Laurentini | 8 / 2 | 14,630 | yes (7, as the castle's legend) | narrator, explicit |

gap = characters from cutoff to anchor. Cutoffs are chapter starts: GP the heading 'THE ENCOUNTER IN SOHO' (chapter VII); TH chapter VIII; CM chapter XIV 'The Meeting'; PN chapter XL; GR chapter X 'YETIVE'; AL chapter VII; UD chapter XVI of the last volume (regex `CHAPTER XVI(?!I)`, the nearest preceding match before the anchor is used by the builder's rule). Spread: 7 authors, 1794 to 1910; gothic (UD, CM, GP), adventure romance (PN, GR), philosophical thriller (TH), detective/adventure (AL). Reveal types: assumed name/second identity (GP, AL, CM), disguise/impersonation (TH), hidden heir (PN, GR), hidden identity of a recluse (UD). **Translations: 1 of 7 (AL).** Original English: 6 of 7.

## Per-event notes

1. **GP** (Machen, pg389). Why chosen: the story's central deduction is a single spoken sentence, Villiers telling Austin that Mrs. Beaumont is Helen Vaughan (also Mrs. Herbert of Paul Street). Verified: anchor once; 8 pre-cutoff alias occurrences (the minimum is 3); 230 non-identity cast mentions in the prefix; 0 alias+identity-token sentences; first alias+full-identity sentence in the book: 1,052 characters after the anchor (Villiers: it was with no thought of finding Helen Vaughan that he searched for Mrs. Beaumont). The anchor sentence itself holds Mrs. Herbert and the identity, not Beaumont; the alias is in the question-and-answer just before it. Caveats: **the prefix already equates Helen Vaughan with a different alias** (Mrs. Herbert), so the identity name is well known to the prefix and only the Beaumont link is withheld. Only 8 alias occurrences (the lowest of the strong events). Mrs. Herbert is not a cast name (she is the identity). Novella; widely read.
2. **TH** (Chesterton, pg1695). Why chosen: the impersonator names himself (an actor called Wilks) in one sentence. Verified: anchor once; 6 pre-cutoff alias occurrences; 329 non-identity mentions; 0 token sentences. Caveats: the alias surfaces are the explicit name forms only; the descriptor 'the Professor' is the usual narrative label and is deliberately not an alias, so 6 undercounts how often the character appears. The name Wilks occurs once in the prefix (a policeman praising a young colleague who understood a poem), which a very careful reader could connect. The gap (17.5k characters) holds narration, shortly before the anchor, stating that the man impersonated the professor, without a name. Calendar words and code names are not cast names (Sunday, Thursday). Cast has small counts for Bull (4), Marquis (5), Rosamond (2), but the total is 329.
3. **CM** (Le Fanu, pg10007). **Weak oracle.** The General's reply names the visitor as the same person who long ago was called Mircalla, Countess Karnstein; the anchor sentence has a pronoun subject and the previous sentence of the same speech ('that is Millarca') is not in the anchor. Millarca is the same person but is neither alias nor cast name (it occurs only in the General's story inside the prefix, 11 times). The prefix is **hint-rich**: the guest reads the name Mircalla, Countess Karnstein off a portrait and says she descends from that family; the General says the countess is not so dead as supposed. Carmilla and Mircalla are anagrams (lexical cue). No prefix sentence or 200-character window joins them, which is all the verifier can test. Cast has 7 names, 36 non-identity mentions. Recommend: drop unless the owner wants a deliberately hard case.
4. **PN** (Cooper, pg2275). Why chosen: the narrator writes Edwards, 'or rather Effingham as we must now call him', in the chapter that brings the lost Major out of his cave. Verified: anchor once and its sentence is the **first** alias+identity sentence in the book (it starts 22 characters before the anchor fragment); 174 pre-cutoff alias occurrences; 1,484 non-identity mentions; 0 token sentences. Caveats: the identity label is the surname alone **because the first name Oliver is shared by the alias 'Oliver Edwards' and the grandson's full name, which gave 16 'token' sentences and would be a lexical cue**; with the surname alone the label is ambiguous with the old Major Effingham (15 prefix mentions, always the old Major or his land grant). The gap holds the youth's own statement that the old man is the lost Major, before the narrator's equation, so it carries hints. Cutoff 7.4k characters before the anchor. Only 3 post-reveal alias occurrences.
5. **GR** (McCutcheon, pg5142). **Medium-weak oracle.** The anchor is the princess's spoken answer ('I am the Princess') after the hero sees her face; it does not contain the identity name. Yetive occurs 0 times in the prefix and first appears in the heading of the chapter that starts at the cutoff and about 17.7k characters after the anchor. A narrator sentence joining the princess to 'erstwhile Miss Guggenslocker' is about 56k characters after the cutoff (later than the anchor); the anchor is the first, spoken equation. Verified: anchor once; 13 pre-cutoff alias occurrences; 300 non-identity mentions. Caspar and Yvonne (the supposed uncle and aunt, in reality members of the princess's party) are not cast names.
6. **AL** (Leblanc, pg34758, **English translation**, Teixeira de Mattos). Why chosen: an anonymous letter read in the chapter states in one sentence that Prince Paul Sernine, Mrs. Kesselbach's friend, is really Arsène Lupin, and notes the anagram. The letter is an accusation by an unknown writer; the story confirms it in later chapters (the anchor's sentence is the first alias+identity sentence in the book; the narrator's own statement that Lenormand and Sernine are Lupin comes 37k characters later). Verified: anchor once; 51 pre-cutoff alias occurrences; 586 non-identity mentions; 0 token sentences. Lupin is a separate wanted man in the prefix (91 mentions). Gap 41k characters.
7. **UD** (Radcliffe, pg3268). Why chosen: the narrator says the nun 'may now be called the Lady Laurentini' in the scene where the dying nun shows Emily two miniatures. Verified: anchor once; 8 pre-cutoff alias occurrences; 4,801 non-identity mentions; 0 token sentences; first alias+identity sentence in the book: none (the anchor has the bare 'Agnes', which is not an alias surface here). Caveats: the alias list is 'sister Agnes' only because bare 'Agnes' also names an unrelated woman in an early chapter (4 mentions); the gap (14.6k characters) holds the nun's delirium and the miniatures, which are hints; Laurentini is in the prefix 7 times as the castle's legend. The first download of this file was truncated mid-text (no `*** END`); it was re-fetched once and the second copy has both markers.

## Dropped (examined, not included)

Downloaded and read by phrase search and targeted close reads; "no event" means I found no usable single-sentence alias-to-identity equation, not that none exists.

- **Monsieur Beaucaire (pg1983)**: a full event was drafted and **passes the verifier mechanically** (identity Louis-Philippe de Valois, cutoff chapter Six, 94 pre-cutoff alias occurrences) but I dropped it by judgement: the anchor is a formal presentation of the prince and contains no alias; the prefix carries a gossip story about a prince of the blood who defied Louis XV and the arrival of a French count with the ambassador, so the identity is guessable; and there are 0 post-reveal alias occurrences, so no post items. Can be added back if the owner wants it (id BC, regex `Chapter Six`).
- **The Riddle of the Sands (pg2360)**: the villain's real name is never printed ('Lieut. X——, R.N.').
- **The Great Impersonation (pg5815)**: the opening chapters already identify the man who then impersonates the baronet; the equation precedes any alias use.
- **Pudd'nhead Wilson (pg102)**: in chapter 3 the narrator already puts both names of the swapped child in one sentence.
- **Under Two Flags (pg3465)**: the narrator equates Louis Victor with Bertie Cecil at the first use of the alias.
- **The Spy (pg9845)**: Mr. Harper is Washington only by implication; I found no sentence stating it.
- **The Wonderful Wizard of Oz (pg55)**: the Wizard's full name is not in this book.
- **Evelina (pg6053)**: the false-heiress equation is spread over several letters, with no single sentence.
- **The Sorrows of Satan (pg42332)**: the equation is made by 'Do you know Me now?' with no name in the sentence, after a long run of hints.
- **Scaramouche (pg1947)**: only a paternity reveal, without an alias.
- **Joseph Andrews vol. 2 (pg9609)**: paternity reveal (Mr. Wilson's son) with no distinct identity name; the novel is split across two Gutenberg numbers.
- **The Sheik (pg7031)**: the hero is revealed as an earl's son but never given a separate name.
- **Dracula (pg345)**: Count de Ville is never joined to Dracula in a sentence.
- **The Thirty-Nine Steps (pg558), The Prisoner of Zenda (pg95), Trent's Last Case (pg2568), The Beetle (pg5164), The Mystery of a Hansom Cab (pg4223), The Eye of Osiris (pg24201)**: phrase scans only ('real name', 'disguise', 'none other than', 'alias' and similar) plus a look at the hits; no usable event found. The Eye of Osiris has an explicit impersonation deduction ('the visitor was not the missing man but Mr. Jellicoe') but the alias 'the visitor' occurs once before it. These six were not close-read, so a missed event is possible.
- **Not downloaded** (budget, not a finding of unsuitability): Kim, Silas Marner, Middlemarch, Frankenstein, Persuasion, Emma, Tess, The House by the Church-Yard (a second Le Fanu, and the author already has Carmilla here), Bardelys the Magnificent, A Little Princess, The Prince and the Pauper, Under the Red Robe, Dorian Gray ('Prince Charming' is joined to the name in the prefix, from memory, unchecked).

## Download log and limits

26 distinct books were fetched from gutenberg.org with a polite user agent, 2 seconds apart, plus one re-fetch (UD, truncated first time): **27 downloads, three above the 'about 24' guideline**. All 26 files have `*** START` and `*** END` markers (checked after the re-fetch). Seven books became events; 19 were fetched and dropped. The ids were looked up in the catalogue file left by the v3 session in the session scratchpad (not fetched again). Nothing was written to the repository except the event file, this notes file and `scripts/chimera/pd_verify_v6.py`; no existing file was edited; no ollama, GPU or API key was used; nothing was committed.

## What is not verified

- **Earliest equation.** For each event I checked, by a whole-book scan of sentences with an alias and the full identity name, that none exists before the cutoff (and where one exists later it is reported). For GR and UD the anchor's own sentence does not contain both an alias surface and the identity name, so that scan is blind there; I relied on targeted searches (Guggenslocker with Princess; Agnes with Laurentini) instead. Pronoun and cross-sentence equations are not detected by any check here.
- **Hints in the prefix and gap** were read only around the anchors and for the identity-name mentions listed above. I did not read any novel in full. CM and GR are the events most exposed.
- **Label noise among cast surfaces.** Counts were checked, but mentions of a surface were not each read (for example 'Bull', 'Marquis' and 'Mary' have small counts, and 'Richard', 'Elizabeth' and 'Benjamin' in PN were taken to be single persons).
- **The Gutenberg text is the author's text** (front matter and contents lists are inside the searched body; the nearest-preceding-match cutoff rule skips the contents list).
- **Owner spot-check of all 7 anchors is pending.** Each takes under a minute: search the Gutenberg file for the `reveal_sentence` (spaces in the anchor may be line breaks in the file; GR's anchor contains a curly quote).

---

<!-- merged-from: docs/research/PD_EVENTS_V7_NOTES.md -->
## Source: `docs/research/PD_EVENTS_V7_NOTES.md`

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
