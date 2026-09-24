# EchoTales — final readiness

**Written 2026-09-25**, branch `validation/evidence-pass-2026-09-24`.
1,071 tests passing; touched files ruff-clean; `.env` never committed (checked
against all refs); `docs/IP/` untracked. All accuracy figures are scored
against an **LLM-derived SILVER reference set (Claude), not human gold, no
IAA**.

---

## VERIFIED — measured on real data, command recorded

| Item | Evidence |
|---|---|
| Full-volume pipeline on local hardware | 199 chapters, 47 min, 660 calls, 0 escalations — `docs/NER_WINDOWING_RESULT.md` |
| Mention-layer repair and its adjudicated prediction | Entities 82→261; CEAF-e recall 25.2→48.9%; "mentions double" **refuted** |
| Observer-scoped knowledge state, both axes | Reader 2 / witness 1 / non-witness 0; witness 0 before the reveal, 1 after — `docs/STATE_OF_VALIDATION.md` |
| Observer-conditioned visual generation on a real engine | Reader 5/5 reference-conditioned, non-witness 0/5; keys and pixels differ on 10/10 blocks — `docs/OBSERVER_CONTRAST_VALIDATION.md` |
| Read-set-derived invalidation | Cast change invalidates, offstage change does not — `test_readset_invalidation.py` |
| Self/Persona, sequential case | One Self, two disjoint bodies — `docs/SELF_PERSONA_VALIDATION.md` |
| Baselines A and B | 10 and 133 mentions vs 359, at 1 and 177 calls vs 0 at resolution — `docs/BASELINES.md` |
| Retriever recall@K by alias type | Given the span: rigid 83.9%, title 77.8%, relational 25.0% @10 — `docs/EVAL_RETRIEVER.md` |
| Scorer diagnosis | Ranks correctly 94.2%; capped at p=0.550 by three inert features; refit does not help — `docs/SCORER_DIAGNOSIS.md` |
| Ablations | Gazetteer carries 66% of links; temporal gate fires on 0 pairs |
| Prior art | LLMLINK and LINK-KG verified against full text — `docs/PRIOR_ART_LINKKG.md` |

## EXPERIMENTAL — implemented, exercised only in part

| Item | What is missing |
|---|---|
| Three-axis time | No fact is ever written to a non-main timeline |
| Temporal identity bindings for hard alias types | 16/17 title-transfer and 25/29 relational mentions never detected |
| EARS voice bank | Loader, whisper routing and tests landed; full-bank Chatterbox render of ch1 **queued behind the download** (see `data/audio-ears/`, log `/tmp/claude-1000/ears_voice.log`) |

## DESIGNED — specified, not exercised end to end
- Retraction distinct from interval end: query tested, **writer has no caller**.
- Concurrent Self/Persona, disguise, body-swap, possession, clone, dream persona: unit tests only.
- Observer-scoped persona bindings: the `observer_id` column exists; no writer.

## BLOCKED
| Item | Blocker |
|---|---|
| Any human-anchored accuracy figure | No human annotation, by owner decision |
| Evaluating a fitted scorer or an investigator | No labelled pairs in the scorer's operating region (all 103 labelled gold candidates are pre-filter-decided) |
| CLIPScore pixel QA | 1.7 GB model download; not attempted |
| Two-depiction observer contrast | Needs a sustained disguise; the primary corpus has none |

## MISSING
- A shared multimodal `GenerationState`: the audio path does not consume `state_of`.
- Detection of relational/deictic and title spans — where the hard cases are lost.
- Aliases in the render read set: a name-only reveal does not invalidate a panel.

---

## Final research limitations
1. Silver-only evaluation; two of three reference files are surface-trivial.
2. The learned scorer contributes nothing; resolution is rule-driven.
3. Hard cases are lost at mention detection, before retrieval or scoring.
4. One primary novel; generalisation asserted, not measured.
5. No image-quality measurement; five-panel demonstrations, not benchmarks.

## Final patent-disclosure limitations
1. **Public since 2026-08-07** — timing is counsel's first question.
2. Two close prior works (Narrative Graph Prompting, ICCVW 2025; StoryWeaver,
   2024) are **unread** and must be before filing.
3. Temporal KG literature not searched.
4. Mechanisms M2–M4 are EXPERIMENTAL or DESIGNED, not VERIFIED —
   `docs/IP/ECHOTALES_INVENTION_DISCLOSURE_DRAFT.md`.

## Final report readiness
All 16 sections have source material (`docs/REPORT_MATERIAL.md`); tables are
generated from artifacts (`docs/paper/TABLES.md`); data-dependent figures are
explicit TODOs (`docs/paper/FIGURES.md`). **Remaining:** complete author lists
for references 3–12; team confirmation of Section 7; draw the seven diagram
figures.

## Exact remaining work, in priority order
1. Read Narrative Graph Prompting and StoryWeaver before any filing.
2. Improve mention detection for relational/deictic and title spans.
3. Retire or activate the three inert scorer features; if kept, make the
   decision comparative (rank + margin) — ranking is already 94% correct.
4. Blind-annotate SCORE-verdict pairs so any scorer change can be evaluated.
5. Write observer-scoped persona bindings.
6. Evaluate on BOOKCOREF for a non-silver, externally comparable number.
7. Rotate the API keys in `.env`; remove the stray `./file:data/` directory.
