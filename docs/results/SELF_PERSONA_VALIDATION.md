# Self / Persona validation — what is real data and what is tests only

**Measured 2026-09-25** against `data/scratch/reruns/ner-window-ri.db`, the
post-NER-fix full-volume Reverend Insanity database (92 personas, 92 bindings).

The model separates two node types. A **Self** is a continuity of
consciousness — memory, relationships, role, knowledge state. A **Persona** is
a physical embodiment — appearance, age, attire. They are joined by
`self_persona_binding`, a temporally scoped, many-to-many relation.

The separation is structural rather than a flag: **appearance may never be
read off a Self.** That is what prevents a disguised or reincarnated
character's generated reference image from inheriting the wrong face.

---

## 1. Real data — sequential reincarnation

One case in the corpus exercises the split on real data, and it is the
protagonist.

```
self:476821534c  (Fang Yuan)
  ├─ body1   story  1.000 → 1.891          learned ch1   TRUE
  └─ body2   story  1.891 → 199.0 … inf    learned ch1   TRUE
```

Fang Yuan dies and is reborn at story position ≈1.89; `body2` carries the
remaining 197 chapters. The personas stage reports it as
*"1 body change across 91 entities · split: Fang Yuan (1+1 bodies)"*.

Two properties are the mechanism rather than bookkeeping:

- **The bodies are temporally disjoint and adjacent.** `body1` ends exactly
  where `body2` begins. A query at position 1.5 resolves to `body1`; at any
  later position, to `body2`. Identity is continuous across the boundary;
  embodiment is not.
- **Downstream artifacts are keyed per persona, not per character.** Reference
  sheets are generated one per `persona_id` (`persona/reference_gen.py`), so
  `body1` and `body2` are separate visual identities that a panel selects
  between by story position. That is the concrete downstream consequence of
  the split — without it, a chapter-1 panel and a chapter-150 panel would draw
  the same face.

## 2. What the corpus does not contain

Measured across the databases in the repository:

| Case | Real-data rows | Status |
|---|---:|---|
| Sequential reincarnation | **1 self with 2 personas** | **Real data** (above) |
| Concurrent bindings (one Self, two Personas at once) | 0 | Tests only |
| Possession / body-swap (one Persona, two Selves) | 0 | Tests only |
| Clone or soul avatar | 0 | Tests only |
| Sustained disguise (`FABRICATED` alias) | 0 | Tests only |
| Dream-realm persona (non-`MAIN_TIMELINE` binding) | 0 | Tests only |

Each is covered by a unit test in `packages/core/tests/test_state.py` —
`TestReincarnation`, `TestBodySwap`, `TestCloneOrSoulAvatar`,
`TestPossession`, `TestSustainedDisguise`, `TestDreamRealmPersona` — with
synthetic fixtures. **The schema supports every one and the query logic is
exercised; the corpus has not produced an instance.** A claim that concurrent
embodiment is demonstrated on real data would be wrong, and the invention
disclosure was corrected on 2026-09-24 to say so.

Reverend Insanity is a reincarnation story, not a disguise story, so this is a
corpus property rather than a defect. Lord of the Mysteries contains a
transmigration (Zhou Mingrui → Klein Moretti) and is the obvious candidate for
a second real case.

## 3. A gap this measurement exposed

**All 92 bindings carry `observer_id = READER`.**

Combined with the observer axis (`docs/results/STATE_OF_VALIDATION.md` Section 5),
that produces an asymmetry: a character who witnessed an identity reveal
learns the *alias* but cannot resolve the *persona*. Measured on Bai Ning Bing
at chapter 169:

| Observer | aliases | persona_ids |
|---|---:|---|
| `READER` | 2 | `…:body1` |
| a witness to the reveal | 1 | **—** |
| a non-witness | 0 | — |

For panel casting this means a witness-conditioned render **drops the
character entirely** rather than depicting them with partial knowledge — which
is almost certainly not the intended semantics, since a witness who knows the
person's name presumably also knows their face.

The cause is that `resolve/detect_observations.py` records observations
against alias facts only; `self_persona_binding` has no equivalent writer. A
missing writer, not a model limitation — the binding row already carries an
`observer_id` column.

## 4. Reproducing this

```bash
python3 - <<'PY'
import sqlite3
c = sqlite3.connect("file:data/scratch/reruns/ner-window-ri.db?mode=ro", uri=True)
c.row_factory = sqlite3.Row
for r in c.execute("""select self_id, persona_id, story_from_lb, story_to_lb,
                             story_to_ub, observer_id, truth_status
                      from self_persona_binding
                      where self_id = 'reverend-insanity:self:476821534c'
                      order by story_from_lb"""):
    print(dict(r))
PY
```

Note the `uri=True`. `Store` calls `sqlite3.connect(path)` **without** it
(`store.py:541`), so passing a `file:…?mode=ro` string to `Store` silently
creates an empty database at a literal path of that name, and every query then
returns nothing. That produced a convincing false negative on 2026-09-25 —
"this character has no persona binding" — that took an hour to unwind.
