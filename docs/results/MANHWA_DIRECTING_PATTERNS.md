# How real manhwa direct a chapter, and what we measure against

Written 2026-11-27 from an Opus read of every slice of two owner-supplied chapters:

- RI manhua ch1: 179 slices in `data/scratch/reference/ri_manhua/ch01/`, Kodoku Studio.
- Legend of the Northern Blade ch1: 25 tall pages in `data/raw/comics/lotnb/lotnb_ch1.pdf`.

The comparison point is our RI ch1 v57 (`data/novels/RI/panels/ch1/v57_round8/`, 45 panels).

Images and long quotes are never committed. Quotes below are a few words at most.

## 1. RI ch1, the reference, segment by segment

| # | Slices | Layer | What the adapter did |
|---|---|---|---|
| S1 | 1-5 | past (prior loop) | **Cold open.** A title card, then a 4-slice brush-SFX spread of the crowd shouting the hero's name, before any narration. Crimson and magenta. |
| S2 | 6-37 | past (prior loop) | **Cliff siege.** The anonymous besiegers become five or more individual accusers, each with their own close-up and grudge line. A tall full-body hero shot. Inserts: a blood drop ("Splot"), whipping hair, an extreme close-up of an eye. Diagonal panel cuts and black gutters. A time-skip box ("6 HOURS PASS") over an overhead shot of the encirclement. The poem lines sit as soft round balloons on a pale wash. |
| S3 | 38-70 | memory | **Reminiscence montage.** Glowing gold-ring captions over past-life imagery: a scholar on Earth, a grave, falling leaves, under water, past selves. A gold and deep-blue palette. The imagery comes from volume knowledge that is not in ch1's text. |
| S4 | 71-89 | past (prior loop) | **Defiance and self-detonation.** A fist insert, a giant red "HA HA HA" SFX, spiky shout balloons, crowd reactions. Then a full-height explosion SFX whose light streak falls onto a night mountain village. **The scene cut is carried by a graphic match, not a caption.** |
| S5 | 90-157 | present (main timeline, 500 years before the cliff) | **Rain-night ritual.** Exterior establishing shot with rain SFX ("tak tak"), a lantern insert, the clan head praying, the elders kneeling in rows in white, an altar wide shot, a kowtow ("THUD"). In the elders' talk, talking heads alternate with chatter SFX. **Characters who are only talked about appear as inset "imagined" panels with a glow treatment, never standing in the room.** The clan head's thoughts are in rectangular narration boxes. Exit: the elders leave in the rain, seen from high; the clan head at a round window. |
| S6 | 158-179 | present (main timeline) | **Reveal.** A village wide shot with a thunder SFX, then a burst caption naming the village. Young Fang Yuan, black hair and blue robe, at a window in the rain. Rectangular boxes explain the artefact. Inserts: an open palm in the rain, a clenched fist ("THUD"), a closing eye. It ends on a thunder SFX. |

Text facts our v57 got wrong, though ch1 states each one:
- The clan head is "middle-aged" (block 37).
- The elders kneel "in loose white ceremonial garments" (block 39).
- Reborn Fang Yuan has "young and soft, pale palms" (block 83).
- Blocks 31 and 79 are unmarked scene cuts. Block 79 ("At the very same moment, a pair of clear eyes...") is a match cut from the clan head's window to Fang Yuan's. The eyes are his, and block 80 names him.

Owner reading (2026-11-28; gold in `data/gold/segment/ri_ch1_owner.json`):
- The cliff is the prior loop.
- The ritual and the window are the main timeline.
- Only the clan head and the elders are at the ritual.
- Bai Ning Bing, the young genius from Fang Zhi's side, Fang Yuan and Fang Zhi are only talked about there. Bai Ning Bing has no lines.
- The manhua's adapters could draw these mentioned people well because they knew every volume. We must direct with whole-novel knowledge too: looks at each story time, future significance, and genre institutions learned from the novel, not ruled.

## 2. LotNB ch1: same grammar, different conventions

- The lore prologue is an **ink-wash silhouette** sequence with **scroll-style caption boxes** ("130 years ago...").
- **Name and title cards** appear on a character's first entrance: name, age, rank.
- **Place cards** open a new location.
- **Dread balloons** (black fuzzy outline) for menacing speakers.
- Extreme close-ups of eyes at shock beats.
- Wide horizontal strips for armies and charges.
- Generous white space for pacing; text-only white beats between scenes.
- A restrained palette per layer: grey ink for lore, red sunset for the fall of the sect.

## 3. The general grammar: what both do (the targets)

These hold for both adapters. Each work chooses its own **look** for each item, so we learn the grammar, not one studio's style.

1. **Hook before exposition.** A cold open (an SFX spread, a title card, or a striking image) comes before the first narration.
2. **One visual language per narrative layer, kept consistent within the work.** Present, memory, lore/prologue, imagined and dream each get their own palette, caption shape and gutter colour.
3. **Scene cuts are always signalled:** a place or time card, a graphic match, or an establishing wide shot. Then comes a detail insert, then people.
4. **Presence is not mention.** Only people physically in the scene stand in it. People who are talked about appear in inset or imagined panels, never in the room.
5. **Density follows drama, not text length.** A peak beat gets 3-5 panels (shout, face, reaction, insert). Exposition shrinks to captions or is cut.
6. **Anonymous crowds become individuals.** A few distinct faces each carry one line consistent with the text.
7. **Inserts and extreme close-ups** (eyes, hands, blood, objects) punctuate peaks.
8. **Balloon taxonomy carries meaning:** speech, shout (spiky), dread (fuzzy black), thought or memory (glow), narration box, time/place card, name card, poem on wash, and SFX lettering in the art.
9. **Panel shape carries rhythm:** wide strips for space and crowds, tall for heroes and falls, diagonals for clashes, insets for asides, full-bleed for peaks.
10. **Gutters pace the read:** tight in action, long white or black between beats and scenes.
11. **Look by story time:** the same person is drawn differently in different epochs, such as old at the cliff and young after rebirth.

## 4. Scorecard (RI ch1). "Better" means at or past the reference on every row

| Aspect | Reference | Ours v57 | How it is measured |
|---|---|---|---|
| Scene cuts placed and signalled | 3 of 3 | 0 of 3 | segments vs. hand-marked boundaries; card/match/establishing at each |
| Presence correct: the right people in each scene | yes | no: Fang Yuan in the ritual, clan head drawn as Fang Yuan | storyboard cast vs. hand list per segment |
| Look by story time | old at cliff, young after rebirth | same adult look throughout | prompt facts per segment vs. text facts |
| Distinct faces for distinct characters | yes | no: one default face | vision check: pairwise face similarity across named cast |
| Panels | about 84 (to be measured with `comic/panels.py`) | 45 | count |
| Cold open | yes | no | storyboard purpose |
| Layer treatments | 4 (battle, memory, ritual, rain) | 1 | palette/caption/gutter per layer |
| Balloon and caption kinds used | 8 or more | 2 | lettering kinds |
| SFX lettering | 10 or more | 0 | count |
| Inserts and extreme close-ups | 10 or more | 2 | storyboard purpose |
| Individualised crowd speakers | 5 or more | 0 | storyboard |
| Referenced-character insets | 2 or more | 0 | storyboard |
| Panel shapes used | 5 or more (wide, tall, diagonal, inset, bleed) | 1 (3:4) | composer |
| Art quality and consistency (rated by Opus side by side) | professional | below | side-by-side sheet, honest verdict |
| Scenes and presence match the owner gold (`ri_ch1_owner.json`) | 3 scenes, exact cast | 0 of 3 | storyboard segments and cast vs gold |
| Referenced people drawn with their whole-novel dossier look | yes (Bai Ning Bing silhouette) | no | inset cast look_id has quote-verified facts from any chapter |
| Withheld reveal kept (clear eyes before the name) | yes | no | storyboard: eye extreme close-up before the Fang Yuan reveal |
| Foreshadowing or curiosity beat from future knowledge | yes | no | storyboard panel citing the future brief |
| Speaker attribution on hand-checked lines | n/a (human) | about 95% on silver | reader eval |

Faithfulness rule: invented panels may add texture (faces, inserts, reactions, the look of a memory) but never plot facts. Every invented panel is flagged with a reason.
