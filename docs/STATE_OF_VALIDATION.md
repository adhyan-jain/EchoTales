# `state_of()` validation — observer and knowledge time on real data

**Measured 2026-09-24** against `data/reruns/ner-window-ri.db`, the
post-NER-fix full-volume Reverend Insanity database. This is
`architecture.md`'s own headline acceptance test, run against a freshly
resolved volume rather than the one database that happened to carry
observations.

```bash
echotales --db data/reruns/ner-window-ri.db observations --novel reverend-insanity
# -> 3 reveals, 3 with a co-present witness -> 12 observations across 11 observers

echotales --db data/reruns/ner-window-ri.db query state-of \
    --novel reverend-insanity --target <self_id> --chapter 200 --observer <observer_id>
```

---

## 1. The query

```
state_of(target_id, *, target_kind=SELF, timeline_id=MAIN_TIMELINE,
         position: float|None, observer_id: str|None,
         knowledge_pos: DiscoursePosition|None,
         include_plausible=True, recorder=None) -> StateOfResult
```

`position` is **story position (a float)**, not a discourse position; the two
coincide only on `MAIN_TIMELINE`, where the default segmentation sets
`story_seq` to the chapter index (`state.py:228-237`). `observer_id` defaults
to the resolver's `default_observer`, which is how `render --observer` carries
it without threading a parameter through every call site below the CLI.

## 2. The observer axis

Target: Bai Ning Bing (`reverend-insanity:self:0035e71331`), whose identity is
revealed at chapter 166 in front of three co-present characters.

| Observer | Aliases returned |
|---|---|
| `READER` | **2** — `Bai Ning Bing`, `Bai Ningbing` |
| `SYSTEM` | **2** — omniscient; sees everything, including `FALSE` facts |
| A character present at the reveal | **1** — `Bai Ning Bing` (a strict subset) |
| A character absent from it | **0** — `[]` |

A character observer does **not** inherit the reader's knowledge. That
inheritance is the spoiler defect the model exists to prevent, and the empty
result for a non-witness is the mechanism working, not a lookup failure.

## 3. Knowledge time — the axis the earlier verification did not show

The same witness, same target, same story position (200), varying only **the
position that observer is taken to be asking from**:

| `knowledge_pos` | Aliases returned |
|---|---|
| chapter 150 | **0** — `[]` |
| chapter 166 | **1** — `Bai Ning Bing` |
| chapter 200 | **1** — `Bai Ning Bing` |

The witness learns at chapter 166 and knows nothing before it. This is a
**different axis** from §2: §2 varies *who* is asking, §3 varies *when they
are asking from*, and both are needed for the claim that identity is observer-
and time-scoped rather than globally true.

EVOLUTION 4.80 demonstrated §2 on real data. **§3 on real data is new here**,
and it is the sharper of the two — a fact that is true, known to this
observer, and still correctly invisible at an earlier position is not
something an access-control filter or a post-hoc redaction produces.

## 4. Observation provenance

12 observations across 11 observers, over 2 distinct revealed facts:

| Fact | Learned at | Observers |
|---|---|---|
| `alias:…self:0035e71331:bai ning bing` | ch 166 | 3 |
| `alias:…self:0035e71331:bai ning bing` | ch 197 | 1 |
| `alias:…self:a8bdaf3bfb:gu yue yao ji` | ch 178 | 8 |

Granularity is the **enclosing `NarrativeSegment`**, not the reveal's own
block. Block granularity produced **zero** observations on RI, because each
reveal block holds exactly one person mention — the revealed character, who is
excluded by definition. Block granularity is right for panel casting (who is
in this frame) and wrong for witnessing (who is in the room). That correction
came from measurement, not from design review.

`fact_ref` is derived from the fact (`readset.observable_ref`), not from a row
id, so a re-resolve does not reset every character's knowledge. This re-run is
the proof: the volume was fully re-resolved and the observations regenerated
coherently.

## 5. What is NOT validated here

- **Observer-conditioned *generation* has never produced a real image.**
  `render --observer` → `render_panels(observer_id=…)` →
  `StateResolver(default_observer=…)` is wired and unit-tested, and the query
  half above is real, but the two comparison figures the paper wants
  (`COMPLETION_PLAN` item 18 — one scene as the reader knows it versus as a
  witness does) do not exist. Do not describe §2/§3 as demonstrating
  observer-conditioned generation. They demonstrate the query it would consume.
- **The observer axis is thinly populated.** 12 observations from 3 reveals
  across a 199-chapter volume. The mechanism is exercised; it is not
  saturated, and no claim about coverage follows from it.
- **`StateOfResult.truth_status` is inert.** The field exists with a hardcoded
  default and `state_of` never sets it (`state.py:334-346`), so the
  `{…, truth_status}` output promised by `README.md`'s query signature is not
  populated. Truth status *is* real on the underlying `TemporalFact`; it is
  the result object that does not surface it.
- **`resolve_alias` does not consult observations** (`state.py:380` calls
  `_visible_to_observer` without the `observations` argument), so that path is
  READER/SYSTEM-only in practice. It did not affect the results above, which
  go through `state_of`, but it is a real asymmetry inside the same module.
- **No fact is attached to a non-MAIN timeline** in any database, so the
  dream/flashback half of the temporal model remains unexercised on real data.
