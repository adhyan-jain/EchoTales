# Look by epoch (2026-11-27)

Code: `packages/pipeline/src/echotales/pipeline/persona/looks.py`, wired in `render/compiler.py::character_brief`
(switch off with `ECHOTALES_LOOK_BY_EPOCH=0`). Measurement: `scripts/eval/look_by_epoch.py`; raw output in
`data/eval/looks/` (`ri_ch1.json`, `lotm_ch1.json`, `pnp_ch1.json`, `summary.json`).

## Failure fixed (RI ch1, render v57)

Every character got the same genre-default sentence ("long black hair tied up in a topknot with a hairpin ... an adult
face"), and Fang Yuan had one look for the whole chapter although the text separates epochs (cliff after 500 years,
torn deep-green robes, block 5; the reborn youth with "young and soft, pale palms", block 83).

## Contract

```python
look_at(store, novel_id, entity_id, *, chapter: float, block: int, client=None) -> Look
Look: look_id, entity_id, epoch_label, age_band, gender, description, facts[{field, value, source_block, invented, reason}]
      (+ hair, eyes, build, face, outfit, condition, marks, block_from, block_to)
```

How: scene windows (break blocks, the first reset statement such as a rebirth, size cap) -> one `Task.READER`
(gemma2:9b) read per window the character is in -> every value kept only if the block it cites holds most of its words and
it is short enough for a prompt -> epochs split where the stated age band changes -> gaps filled from a per-novel slot bank
(stored once, each new person at least 3 of 5 dimensions away from all earlier ones), flagged `invented` with a reason.
Age comes from cue words in sentences about the character (a model band is accepted only when its cited block carries
the same cue; at 7B it called the clan head "young adult" and the 500-year-old "teen" from stray words). Gender: stored/owner
value, then pronoun counts; no name-suffix rules. A condition (torn, blood) belongs to its own epoch only.

## Results, chapter 1

RI (Fang Yuan has 2 looks, as required):

| Entity | Epoch | Look |
|---|---|---|
| Fang Yuan | blocks 0-30, ageless-ancient | chestnut brown hair with a few silver strands, long and loose, broad-shouldered, deathly pale, deep green robes, covered in blood, torn to shreds, numerous wounds |
| Fang Yuan | blocks 31-91, teen | chestnut brown hair, long and loose, slim boyish build, narrow face, charcoal grey robe (invented, the cliff's green is not carried) |
| Gu Yue clan head | whole chapter, middle-aged | dark brown hair graying at the temples, graying sideburns, broad-shouldered, ceremonial white robes (stated, block 37) |
| Fang Zhi | whole chapter, adult | black hair, medium-length, lean build, ochre robe (all invented; text states nothing about his body) |

Distinctness (pairs of characters co-present in a scene window; distinct = differ on >=2 of hair, age band, clothes,
build/face). "Before" = persona facts plus `identity_lock` stored defaults, without the scene-look model call.

| Novel | Pairs | Before | After |
|---|---|---|---|
| RI ch1 (3 entities) | 3 | 2 | 3 |
| LotM ch1, entities with >=3 present blocks | 5 | 5 | 5 |
| LotM ch1, all 22 detected (mostly NER noise: "Ouch", "Hey") | 127 | 97 | 127 |
| P&P ch1 (3 entities, one is a place) | 3 | 3 | 3 |

The "before" metric is weak: its defaults already differ by id hash in clothes colour. What it does not capture is the
measured v57 collapse (same topknot sentence), age band, and epoch changes, so the table understates the gain on RI; the
epoch result (2 looks for Fang Yuan against 1) is the main one.

## Unmeasured / known weak

- No image was rendered with the new prompts; the prompt text and `identity_sentence` output were not compared in a render.
- Age is mostly cue-word regex; a chapter with no age word gives `adult` flagged invented. Model reads are noisy at 9B too
  (a stray "clear eyes" was handed to the clan head from a neighbouring block).
- Epochs are cut only at scene breaks and the first reset statement of a chapter; a mid-scene change of age is missed.
- Looks are per chapter; cross-chapter continuity of invented values relies on the slot bank, not on re-reading.
- LotM/P&P were run on scratch DBs whose entities are noisy; Klein is split over several entities there.
- One model call per character per window on the director pass; the image pass reads the cache and falls back to a
  deterministic (unmodelled, uncached) build when there is none.
