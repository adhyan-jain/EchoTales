# Public-domain excerpts: pass A vs pass B adjudication

Pass A (first annotator, inline markers in `scripts/eval/ner_gold_passages/public_domain.py`) and pass B (an independent
model pass that saw only the README rules and the plain excerpts) were compared by exact span match.

Raw agreement before adjudication: A 331 spans, B 290, exact matches 275, span F1 **0.886** (P 0.948 / R 0.831 taking
B as the prediction). Of the 275 matches, 4 differed in label. After adjudication: 286 of 331 / 290 matched, F1 0.921;
the rest are kept A-only spans, decided below. Status: silver, not owner-checked.

Standing rules decided here: (1) attached honorifics/ranks stay inside the span ("Tai-yu Yang Piao", "king Virata");
(2) a bare title that is the sole referent of that title in the excerpt and points to one individual is `title_epithet`
(`shared_title` where several holders of the title occur); (3) a role noun in apposition to a name ("the Brahmana X") is a
descriptor, not part of the name; (4) titles of songs, poems and books are not entities; (5) a family or group acting as
one named party (Pandavas, Lucases, Gandharvas as the husbands) is `organization`.

| Excerpt | Surface | A | B | Resolution |
|---|---|---|---|---|
| zh01 | Tai-yu Yang Piao | span with rank | Yang Piao | A (rule 1) |
| zh02 | Prefect of Taichou | title_epithet | Taichou location | B: unnamed role + place is a descriptor; Taichou location |
| zh03 | Ho (bare) | missed | person | B added (alias of Ho Chin) |
| zh03 | Emperor x3, marquis | title_epithet | none | A (rule 2); Emperor marked shared_title |
| zh04 | Teacher Confucius | span with epithet | Confucius | A (rule 1) |
| zh04 | Governor | title_epithet | none | A (rule 2, appositive of Li Ying) |
| zh06 | King Wen | span | King Wen of Chu | A; Chu kept as separate location |
| zh06 | Tsin dynasty | organization | Tsin location | B: common noun "dynasty" dropped, Tsin location both times |
| ja01-ja06 | bare Emperor / Prince / Crown Prince / Heir Apparent / Secretary of the Right | title_epithet | none | A (rule 2); Emperor in ja06 shared_title |
| ja02 | The Lady of Mikasa Hill | item | none | B (rule 4), dropped |
| ja03 | Earth Star | item | none | B, dropped (generic astrology term) |
| ja04 | Takasago | location | none | A (named place) |
| ja06 | ex-Emperor Suzaku | span with prefix | none-different | A (rule 1) |
| in01 | Brahmana Chandabhargava / Kalaghata | span with Brahmana | name only | B (rule 3) |
| in01 | Vedas x3 | item | none | B (rule 4), dropped |
| in01 | Kohala Devasarman | one span | two persons | B: list is comma separated, the missing comma is a typo |
| in04 | Kuru | organization | none | A (rule 5, dynastic group) |
| in04 | king Virata | span | Virata | A (rule 1) |
| in04 | Virata ("city of Virata") | location | person | A: city named for the king, location |
| in05 | Bharata (vocative) | missed | person | B added |
| in06 | Sairindhri | person | title_epithet | A: used as Draupadi's assumed name; the groups are scoring-compatible anyway |
| in06 | Gandharvas x3 | none | organization | B (rule 5, a specific party in the story) |
| ko01 | Chinese Emperor | title_epithet | none | A (rule 2) |
| ko03 | king x3 | title_epithet | none | A (rule 2) |
| ko04 | Pil family, Pils | organization | none | A (rule 5) |
| ko05 | Caliph | title_epithet | none | A (rule 2) |
| ko05 | Arabian Nights | item | none | B (rule 4), dropped |
| eu03 | Lucases | organization | none | A (rule 5) |
| eu04 | Oxford | location | missed | A (B omission) |
| eu05 | Sun, Moon x7 | person | none | A: personified captives of Louhi, capitalised as characters |
| eu06 | Sahri x3 | location | none | A: place/people name, capitalised |

Remaining judgement calls that a human reviewer may well reverse: bare titles (rule 2) are the largest block
(about 40 spans); personified Sun/Moon; Gandharvas; the Kohala/Devasarman split.
