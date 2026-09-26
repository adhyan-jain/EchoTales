# Observer-contrast validation — generation and read-set invalidation

**Run 2026-09-25 on the local RTX 4060.** Closes `docs/archive/COMPLETION_PLAN.md`
item 18, open since the observer axis was built, and removes the "never run
against a real image engine" caveat that qualified the project's two strongest
technical claims.

```bash
for OBS in READER reverend-insanity:self:a8bdaf3bfb; do
  echotales --db data/scratch/reruns/ner-window-ri.db render \
      --novel reverend-insanity --chapters 169 --block-range 1-10 --max-panels 3 \
      --image-engine noobai --observer "$OBS" --skip-motion --skip-compose \
      --panel-dir "data/novels/RI/panels-obs-<tag>"
done
```

Everything is held constant except the observer: same chapter, same blocks,
same checkpoint (NoobAI XL), same seed, same engine settings.

---

## 1. The result

| | `READER` | a character who never witnessed the reveal |
|---|---|---|
| Panels generated | 5 | 5 |
| **Reference-conditioned** | **5** | **0** |
| **Prompt-only** | 0 | **5** |
| Cache key identical across the two runs | **no** — 10/10 blocks differ | — |
| Pixels identical across the two runs | **no** — 10/10 blocks differ | — |

Per block, the manifest records what the generator was told:

```
block 1   READER       conditioned_on = ['Bai Ning Bing', 'Fang Yuan']
          non-witness  conditioned_on = []
block 5   READER       conditioned_on = ['Fang Yuan', 'Bai Ning Bing']
          non-witness  conditioned_on = []
block 9   READER       conditioned_on = ['Bai Ning Bing']
          non-witness  conditioned_on = []
```

And the delivered prompt itself diverges:

```
READER       2boys, male focus, guofeng illustration, chinese ink painting,
             xianxia, medium shot, Bai Ning Bing, black…

non-witness  1boy, male focus, solo, guofeng illustration, chinese ink
             painting, xianxia, medium shot, a figure, stand…
```

## 2. Why this is the claim and not a trick

Three things make this a property of the data model rather than of two
hand-written prompts.

**The character is named in one and anonymous in the other.** The reader's
panel says `Bai Ning Bing`; the non-witness's says `a figure`. Nothing in the
render path substitutes that string — the prompt assembler asks the graph who
is present and receives a different answer.

**The cast count changes.** `2boys` versus `1boy … solo`. The observer who
never witnessed the reveal does not merely lack her name; **she is not in
their scene at all**, so the composition itself differs. A redaction step
applied to a finished image cannot produce that.

**The cache key changes, on every block.** `render/cache_key.py` derives the
artifact key from `plan.state_digest`, which hashes the facts the graph
returned. Different observer → different read set → different digest →
different key → a genuinely separate cached artifact. This is the composition
the disclosure calls P3 ∘ P6, observed working: the excluded information never
reaches the prompt because the query never returned it.

## 3. What this closes

- **`COMPLETION_PLAN` item 18** — the two-observer contrast, the paper's
  central figure. Artifacts at `data/novels/RI/experiments/observer-contrast/reader/` and
  `data/novels/RI/experiments/observer-contrast/nonwitness/`, 5 panels each, 1.4–1.6 MB per PNG.
- **The stub-mode caveat on P6 and P7.** Both had read "wired and unit-tested
  but never run against a real image engine." They have now run.
- **Phase 11, the multimodal proof of concept** — text → resolved state →
  render plan → generated artifact, with the graph query as the only variable.

## 4. What it does not close

- **This is a with-identity / without-identity contrast, not two different
  depictions of the same person.** The strongest possible version — the same
  scene as the Wu clan *believes* it versus as the reader knows it, where both
  observers see a character but a *different* one — needs a `FABRICATED` alias
  (a sustained disguise) in the corpus. Reverend Insanity has none
  (`docs/results/SELF_PERSONA_VALIDATION.md` Section 2). Lord of the Mysteries is the
  candidate.
- **No claim about image quality.** No rendered pixel in this project has ever
  been scored; the CLIPScore bench remains unbuilt. These five panels show the
  mechanism reaches the generator, not that the output is good.
- **Five panels is a demonstration, not a benchmark.** Bounded deliberately —
  `--max-panels 3 --block-range 1-10` — because GPU time is for answering a
  specific question and stopping.

## 5. A caveat worth carrying into the paper

The non-witness render drops the character rather than depicting her as a
stranger. That follows from every `self_persona_binding` row carrying
`observer_id = READER`, so a character observer can resolve an alias but never
a persona (`docs/results/SELF_PERSONA_VALIDATION.md` Section 3).

Arguably a witness who knows someone's name should also know their face, and
the intended semantics is probably "depict her without the reveal-dependent
attributes" rather than "omit her". The binding row already carries an
`observer_id` column; `detect_observations.py` simply has no writer for it.
Until that exists the contrast is sharper than the model really intends —
worth stating plainly rather than presenting the starker figure as the design.


---

## 6. Exact records for the contrast run

| | READER | non-witness (`reverend-insanity:self:a8bdaf3bfb`) |
|---|---|---|
| `state_of(Bai Ning Bing, position=169)` aliases | 2 | 0 |
| `state_of(...)` persona_ids | `…:0035e71331:body1` | none |
| Plan `characters` | 1 | 0 |
| `state_digest` | `de02bdbf43ff8294` | `3ce2442598531a35` |
| Block 1 cache key | `5066f03cc44fef0a` | `a27b42d9057e64a3` |
| Block 1 output | `data/novels/RI/experiments/observer-contrast/reader/ch169/v1/p001_b0001.png` | `data/novels/RI/experiments/observer-contrast/nonwitness/ch169/v1/p001_b0001.png` |
| Seed | CLI default, identical for both runs | identical |

## 7. Controlled read-set invalidation

`packages/pipeline/tests/test_readset_invalidation.py` — five tests on a
controlled store, stub path, no GPU. The claim has two halves and both hold:

| State change | Cache key |
|---|---|
| None (rebuild the same plan) | **unchanged** |
| Attribute added to a character **in** the panel's cast | **changes** |
| Attribute added to a character **not** in the cast | **unchanged** |
| New body bound to a cast character | **changes** |
| New alias for a cast character | **unchanged** — see below |

The offstage case is the one that matters: it is what makes this precise
invalidation rather than "any change busts every cache".

**A limit this exposed.** `render/plan_builder.py` hashes persona ids and
attributes into `state_digest`, **not aliases**. A revelation that only adds a
name to a character therefore does not invalidate a panel that already depicts
them. The test pins this as current behaviour so a future change to it is a
deliberate decision, and the disclosure's P6 should describe the read set as
"embodiment and attribute facts", not "all facts consulted".
