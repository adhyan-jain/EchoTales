# Experiment results: baselines, external benchmark, retriever, scorer diagnosis, NER windowing, self/persona and state_of validation, CLIPScore

> Merged on 2026-10-22 from 8 separate documents to keep the docs tree small. Each section below is one original file, text unchanged; its old path is in the section heading. The originals are in git history.

---

<!-- merged-from: docs/results/BASELINES.md -->
## Source: `docs/results/BASELINES.md`

# Baselines — configuration, cost, and what they can and cannot show

**Written 2026-09-24.** Two academic comparison points, both built, both
local-only and zero API spend. Where a run has not happened this file says so,
rather than leaving a blank that reads as a zero.

Everything here is scored against an **LLM-derived silver reference set, not
human gold, with no IAA** (`docs/results/GOLD_AND_ANNOTATION.md`).

---

## 0. The comparison is narrower than it looks — read this first

Both baselines produce a **coreference partition** and are scored by the same
unmodified `score_b3` / `score_all` as the resolver. That is the only axis on
which the three are comparable.

They are **not** comparable on what the project actually claims. Neither
baseline has, or can have, a temporal axis, a truth status, a Self/Persona
split, an observer, or a downstream generation consumer — so "EchoTales beats
Baseline A on B³" would be a claim about coreference quality, not about the
contribution. The architectural difference has to be argued from the
mechanisms and the ablations, not from these two numbers.

**And a coreference number from this corpus is worth little on its own.** The
silver files that cover enough chapters to make a baseline comparison
meaningful are **100% surface-trivial** (`docs/results/EVAL_RETRIEVER.md` Section 1): their
partitions are reproducible by grouping on the surface string, so a baseline
that merely string-matches competently scores ~100% precision too. The only
non-trivial set, `reverend-insanity-hardcases.jsonl`, is 89 records spread
over 51 chapters — too sparse for a short baseline run to hit often.

That is the honest framing: these baselines measure **cost and failure shape**
far more informatively than they measure accuracy on this corpus.

---

## 1. Baseline A — long-context LLM, no graph

`packages/pipeline/src/echotales/pipeline/eval/baseline_a.py`

| | |
|---|---|
| Architecture | One call per volume *section*, raw chapter text + a running entity roster |
| Model | `qwen2.5:7b`, temperature 0, local Ollama, no API |
| Context | `num_ctx` 32,768 — the model's **hard architecture ceiling** |
| Section size | **10 chapters**, not `docs/design/plans.md`'s 30 |
| Call shape | **O(sections)** — ~6 calls for ch1-60 |
| Has | Long context, a running roster |
| Lacks | Gazetteer, temporal scoping, incremental evidence, alias typing, DEFER/correction |

**Why 10 chapters and not 30.** Measured, not assumed: RI runs ~2,300 input
tokens per chapter, so 15 chapters already clamps at the 32,768 ceiling, and
`num_ctx` covers input *and* output combined in Ollama. A 30-chapter section
silently truncates rather than raising — `prompt_eval_count` pins at 32,768
whether the request asked for 32,768 or 65,536. `docs/design/plans.md`'s "approximately 30
chapters" is not achievable with this model, and was not taken at face value.

**Offset recovery.** The model is never asked for a character offset — LLMs
count tokens, not characters, and would fabricate one. It quotes the exact
surface plus a short verbatim window, and `_locate` finds the literal offset
by substring search with `difflib` context tie-breaking.

### Status: RUN 2026-09-24 — first execution in the project's life

One section, chapters 1-10, `qwen2.5:7b`, `num_ctx` 32,768.

| | |
|---|---:|
| LLM calls | **1** |
| Prompt tokens | 24,302 |
| Output tokens | **697** |
| Wall time | **146 s** |
| Entities found | **7** |
| Mentions found | **10** |
| B³ precision | 100.0% |
| **B³ recall** | **0.2%** |
| B³ F1 | 0.3% |

Scored against the silver ch1-10 subset (356 gold mentions); **346 of them the
baseline never produced at all**.

**The failure mode is output budget, not comprehension.** The prompt consumed
24,302 of the model's 32,768-token combined budget, leaving roughly 8k tokens
of headroom, and it emitted 697 — **10 mentions for 10 chapters**, about one
per chapter. On the same range the silver gold annotates **356** and the
EchoTales pipeline finds **359** (312 before the NER fix). The model was not
asked a question it answered badly; it was asked to enumerate hundreds of
spans in a single completion, and it stopped after ten.

| ch1-10, same range | mentions |
|---|---:|
| Silver gold | 356 |
| EchoTales, post-NER-fix | **359** |
| EchoTales, pre-NER-fix | 312 |
| **Baseline A** | **10** |

Precision of 100.0% on 10 mentions is not a quality signal — it is ten easy
RIGID_NAME hits on a surface-trivial gold subset (see Section 0). **Recall is the
informative half here**, and 0.2% is the number that matters.

This is the honest, non-strawman result of the architecture `docs/design/plans.md`
specified: a long-context LLM given a whole section at once, with no graph and
no gazetteer, does not scale to volume-length coreference — not because it
reasons poorly, but because one completion cannot carry the output.

---

## 2. Baseline B — LLMLINK-style dual-LLM memorisation

`packages/pipeline/src/echotales/pipeline/eval/baseline_b.py` — **new
2026-09-24**; every status document before today recorded this as "not
started".

| | |
|---|---|
| Architecture | Two roles, each blind to what would let it cheat |
| LLM-1 EXTRACTOR | Reads one 3,000-char chunk, returns mentions + a short descriptor. **Never sees the entity memory**, so it cannot be primed by it |
| LLM-2 LINKER | Sees one mention + its descriptor + the compact memory, returns link-or-new. **Never sees the chapter text** |
| Memory | Flat, append-only; last 60 entries rendered to the linker |
| Model | `qwen2.5:7b`, `num_ctx` 8,192 — small on purpose |
| Call shape | **O(mentions)** — one extractor call per chunk *plus one linker call per mention* |
| Lacks | Temporal binding, transferable-title detection, correction/DEFER loop, gazetteer, Self/Persona split, truth status, observer |

**Why LLMLINK and not LINK-KG is the target.** Verified against the full paper
(`docs/paper/PRIOR_ART_LINKKG.md`): LINK-KG is a *legal-document* system scored on
node-duplication and noise rates over 16 court opinions, with no coreference
metric at all. Its own related-work section describes LLMLINK as "effective on
structured, homogeneous datasets like **book chapters**" while it "struggles
with complex texts involving **multi-role entities, shifting aliases**, and
plural references" — this project's exact subject. LLMLINK is the comparable
system; LINK-KG is a supporting citation.

**Not a strawman.** Same model, same host, same offset-recovery code, same
`Mention` round-trip, so one unmodified scorer measures all three systems. The
architecture is given its real advantage: the linker sees a compact memory
rather than 23k tokens of raw text, so it should not degrade with section
length the way a long-context prompt does.

### Status: RUN 2026-09-24 — first execution

Chapters 1-10, `qwen2.5:7b`, `num_ctx` 8,192, 3,000-char chunks.

| | |
|---|---:|
| Extractor calls | 43 |
| Linker calls | **134** |
| Total LLM calls | **177** |
| Prompt tokens | 142,835 |
| Output tokens | 8,487 |
| Wall time | **435 s** |
| Entities found | **32** |
| Mentions found | **133** |
| B³ precision | 95.4% |
| **B³ recall** | **4.6%** |
| B³ F1 | 8.8% |

72 of 356 silver gold mentions matched; 284 unresolved.

**The memorisation architecture works, and it is expensive.** Against Baseline
A on the identical range it finds **13× more mentions** (133 vs 10) — the
chunked extractor is not fighting a single completion's output budget, which
is exactly the weakness LLMLINK's design addresses. It pays **177× the calls**
and **5.9× the prompt tokens** for that, and still recovers under 5% of the
reference set.

Precision stays high (95.4%) because what it does find is mostly easy
RIGID_NAME material. Recall is the honest number, and the gap to EchoTales
(359 mentions on the same range) is the result.

---

## 3. Cost shape — the comparison that is already informative

This needs no gold set to be true, and it is a real architectural result:

| | Baseline A | Baseline B | EchoTales resolver |
|---|---|---|---|
| Call complexity | O(sections) | **O(mentions)** | O(chapters) for NER, O(1) per resolution |
| Calls, ch1-60 (est.) | ~6 | **hundreds to low thousands** | ~180 NER calls + **0** LLM resolution calls |
| Context per call | up to 32,768 tokens | ~1,000 tokens | ~6,000 chars per NER window |
| Degrades with volume length | Yes — hard ceiling near 15 chapters | No — memory is bounded | No — and the gazetteer *improves* with length |

The resolver's resolution stage makes **zero** LLM calls: every link is a
deterministic pre-filter (`by_method`: `GAZETTEER_EXACT=870, DECLARATION=5,
NAME_CONTAINMENT=2, RELATIONAL_COPRESENCE=3, SCORED=0`). Both baselines pay an
LLM call for work the resolver does with a dictionary lookup. That is a
defensible efficiency claim independent of any accuracy number, and it is the
comparison this corpus currently supports best.

---

## 4. Results

Both baselines executed 2026-09-24 on chapters 1-10, same model, same host,
same scorer. **Scored against an LLM-derived silver reference set, not human
gold** — and on a range whose gold is 100% surface-trivial, so **precision is
tautological and recall is the informative half.**

| | Baseline A | Baseline B | EchoTales |
|---|---:|---:|---:|
| Architecture | long-context, 1 call/section | dual-LLM memorisation | graph + gazetteer |
| **LLM calls** | **1** | **177** (43 extract + 134 link) | ~30 NER, **0** resolution |
| Prompt tokens | 24,302 | 142,835 | — |
| Wall time | 146 s | 435 s | — |
| Entities found | 7 | 32 | 261 (full volume) |
| **Mentions found** | **10** | **133** | **359** |
| B³ precision | 100.0% | 95.4% | 100.0% |
| **B³ recall** | **0.2%** | **4.6%** | **79.1%** (ch1-10) |

Silver gold for ch1-10 holds **356** mentions.

> **Corrected 2026-09-25.** This table first showed EchoTales at 96.3% B³
> recall, which is its *full-volume* figure (Table 4), beside the baselines'
> ch1-10 figures. On the same 356 ch1-10 silver mentions it is **79.1%** (65
> unresolved). The comparison now comes from one script,
> `scripts/eval/baseline_comparison.py` → `data/eval/baseline_comparison.json` →
> `docs/paper/TABLES.md` Table 7. The direction of every finding below is
> unchanged; the size of EchoTales' lead is smaller.

**Three findings this table supports:**

1. **Long-context single-pass extraction does not scale.** Baseline A's prompt
   consumed 24,302 of a 32,768-token combined budget and it emitted 697 output
   tokens — ten mentions for ten chapters. The failure is output budget, not
   comprehension.
2. **Memorisation fixes that, at a steep price.** Baseline B's chunked
   extractor finds 13× more mentions than A, because no single completion has
   to carry the whole answer. It costs 177× the calls.
3. **The resolver's cost advantage is structural, not incidental.** Its
   resolution stage makes **zero** LLM calls — every link is a deterministic
   pre-filter. Both baselines spend model calls on work a dictionary lookup
   does.

**Caveat that limits all three:** EchoTales' 79.1% B³ recall is measured
against gold that is 100% recoverable by grouping on the surface string, so it
substantially measures string matching. The baselines are handicapped on the
same axis in the opposite direction — they must *find* the mention before they
can match it. Treat the recall column as an extraction-coverage comparison,
which it genuinely is, and not as a coreference-quality comparison, which this
corpus cannot currently support.

---

## 5. Known limitations of this comparison

1. **No human gold on either side.** Both are scored against a silver set, so
   the comparison is relative, not absolute.
2. **Surface triviality caps what a win means.** On a 100%-surface-trivial
   file, high precision demonstrates string matching. Only the 89-record
   hardcases file discriminates, and it is sparse.
3. **One model family.** All three systems use `qwen2.5:7b`. A larger model
   would likely lift both baselines, and nothing here measures that.
4. **Baseline B's linker sees a descriptor written by the extractor**, so
   extraction errors propagate into linking with no recovery path. Faithful to
   the architecture — it has no correction loop — but it means a bad chunk
   costs more there than in the resolver's DEFER path.
5. **Neither baseline is evaluated on the mechanisms the project claims.**
   Temporal binding, observer conditioning and the Self/Persona split have no
   baseline counterpart, so the ablations (`echotales ablate`) rather than
   these baselines are what evidence those.

---

<!-- merged-from: docs/results/CLIPSCORE.md -->
## Source: `docs/results/CLIPSCORE.md`

# Prompt-image alignment (CLIPScore)

**Measured 2026-09-27.** `scripts/eval/clip_score.py`, CLIP ViT-L/14
(`openai/clip-vit-large-patch14`, local cache, no download), seed 20260927.
Result file: `data/eval/clipscore.json`.

**What it measures.** CLIPScore (Hessel et al., 2021) between each rendered
panel and the prompt that produced it, truncated to CLIP's 77 tokens exactly as
the image engine sees it. Panels in one render share style tags, so the mean
alone says little. Each image is therefore also scored against the prompt of a
*different* panel of the same render. "Beats control" counts how often the
image matches its own prompt better than another panel's, which is the
evidence that the image follows the prompt's *content*.

**What it does not measure.** Image quality, character identity consistency
across panels, or whether the prompt itself was a good reading of the text.
It measures alignment between a panel and its prompt, nothing else. No human
rating exists.

| Render | Engine era | Panels | CLIPScore (mean ± sd) | Shuffled-prompt control | Beats control |
|---|---|---:|---:|---:|---:|
| RI ch1 `v54_crowd-solo-scenestate-fix` (current) | NoobAI XL, director prompts | 87 | 66.7 ± 7.6 | 54.3 | **77/87 (89%)** |
| RI ch1 `v9_short-clause-scene-restored` | GuoFeng3 (SD1.5), 2026-08-17 | 21 | 64.9 ± 4.2 | 62.9 | 7/21 (33%) |
| RI ch169 observer contrast, reader view | NoobAI XL | 10 | 69.4 ± 6.0 | 64.4 | 6/10 |
| RI ch169 observer contrast, non-witness view | NoobAI XL | 10 | 71.7 ± 3.0 | 69.8 | 6/10 |
| LOTM ch1 | NoobAI XL | 73 | 54.0 ± 6.6 | 48.4 | 62/73 (85%) |

**Reading it.**
- The current RI pipeline's panels follow their own prompts: 89% score higher
  against their own prompt than against another panel's. The August render
  was near chance (33%), so the director and prompt-budget work between v9 and
  v54 is measurably visible in the images, not only by eye.
- LOTM's absolute scores are lower. Its prompts carry more proper nouns and
  Western period detail that CLIP embeds weakly, but the matched-vs-shuffled
  gap is similar (85%).
- The observer-contrast renders (n = 10 each) are too small to separate the two
  views. Their panels differ in what is drawn, not in how well each follows its
  prompt, so this metric is not the right test for the observer claim.

**Stub renders are excluded.** RI ch169 `v1` in the main panel folder is stub
output (8 KB placeholders). Scoring it would measure nothing.

---

<!-- merged-from: docs/results/EVAL_RETRIEVER.md -->
## Source: `docs/results/EVAL_RETRIEVER.md`

# Retriever evaluation — Recall@K by alias type

**Measured 2026-09-24.** The first per-alias-type recall@K this project has
ever produced against annotated data. Every number here is scored against an
**LLM-derived silver reference set, not human gold, with no IAA** — see
`docs/results/GOLD_AND_ANNOTATION.md`.

Reproduce:

```bash
echotales --db data/archive/db/reverend-insanity-webview-working.db eval \
    --novel reverend-insanity \
    --gold data/gold/reverend-insanity-hardcases.jsonl
```

Machine-readable output lands in `data/eval/results/<run_id>/metrics.json`
under `metrics.silver.recall_at_k`, alongside the commit, seed and platform.

---

## 1. Read this before any number below

**A coreference gold set whose partition can be reproduced by grouping on the
surface string measures string matching, not identity resolution.**

Not hypothetical. Measured across this corpus:

| File | scorable mentions | distinct surfaces | identities | **surface-trivial** | alias types |
|---|---:|---:|---:|---:|---|
| `reverend-insanity.jsonl` (silver subset) | 1,816 | **23** | 20 | **100.00%** | RIGID_NAME only |
| `reverend-insanity-c1-c5.jsonl` | 308 | 34 | 26 | **100.00%** | RIGID_NAME only |
| `reverend-insanity-hardcases.jsonl` | 88 | 44 | 26 | **63.64%** | 4 types |

The first two encode the assertion *"these ~25 strings denote these ~20
people, one-to-one."* Any exact-string matcher reproduces them perfectly.

**Consequence, stated plainly:** scoring the system against
`reverend-insanity.jsonl`'s silver subset returns **B³ P=100.0%, R=94.6%,
F1=97.2%** — byte-identical to the headline `docs/EVOLUTION.md` 4.74 retracted.
4.74 withdrew it for being *circular* (gold drafted from the pipeline's own
`mention` table). This is a **second, independent reason the same number is
meaningless**: even the non-circular subset is a tautology, because the task
it encodes is trivially satisfiable. The figure was doomed twice over, and it
must not reappear under a "silver" label as though relabelling fixed it.

This is now an automated check
(`eval/validate_gold.py::_surface_triviality`) that **fails** any file at ≥99%
and warns at ≥90%, so the mistake cannot be made silently again.

**Therefore `reverend-insanity-hardcases.jsonl` (89 records) is the only
evaluation set in this corpus that measures anything** — and even it is 64%
trivial, so roughly 32 of its mentions carry the actual signal.

---

## 2. Results — hardcases, silver tier, pre-re-run database

44 retrieval cases (18 of 62 identities did not map to a system `target_id`).

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|
| **Overall** | 44 | 63.6% | 75.0% | 75.0% | 88.6% |
| RIGID_NAME | 30 | 80.0% | 83.3% | 83.3% | 93.3% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 66.7% | 66.7% | 88.9% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 50.0% |
| EPITHET | 1 | 100% | 100% | 100% | 100% |

**Gate verdict: FAIL.** `retriever_eval.GATE` requires recall@10 ≥ 80% on
`TRANSFERABLE_TITLE`; measured **66.7%**. The gate's own message is the right
reading: *candidate retrieval is the research problem; scorer tuning is
premature.*

### Honest caveats

- **n is small.** 9 TRANSFERABLE_TITLE and 4 RELATIONAL_DEICTIC cases. One
  case moves TRANSFERABLE_TITLE by 11 points and RELATIONAL_DEICTIC by 25.
  Directional, not precise; no confidence interval rescues this n.
- **EPITHET n=1 is not a measurement.** Printed because omitting a row is
  worse than printing one that declares its own n.
- **18 of 62 identities unmapped.** `build_gold_retrieval_cases` maps a gold
  identity to a system `target_id` by majority vote and drops what it cannot
  map. Unmapped identities are disproportionately the hard ones, so the true
  figures are likelier below these than above.
- Scored against the **pre-re-run** canonical database. The post-NER-windowing
  comparison follows separately.

---

## 3. A documented claim this refutes

`docs/status/STATUS.md` "Stale claims found this pass" #2, and `docs/EVOLUTION.md` Section 4.69,
conclude that the TRANSFERABLE_TITLE recall@k gate:

> "cannot produce a number on this novel no matter how much more gets
> annotated."

**It can, and the table above is one.** Section 4.69 was correct about its actual
subject: `generate_gold.py` only admits mentions carrying a resolved
`target_id`, and real TRANSFERABLE_TITLE mentions on RI correctly resolve to
`None` by design (non-negotiable #9), so gold derived *that way* can never
contain them. It does not generalise to **hand-drafted** gold.
`reverend-insanity-hardcases.jsonl` was written by reading chapter text, and
its 17 TRANSFERABLE_TITLE records carry identities that map to system targets
by majority vote.

What actually blocked the measurement was mechanical, not structural: `eval`
had **no `--gold` flag**, so the corpus's one alias-diverse file was
unreachable from the CLI, and the file itself was **gitignored**. Both fixed
2026-09-24.

`STATUS.md` needs correcting: the gate is measurable, it was measured, and it
**fails**.

---

## 4. Two defects in the measurement path, fixed here

1. **The retriever was evaluated with no context.** `commands.py` built its
   evaluation retriever by calling `observe(..., "", ...)` for every mention,
   zeroing the 0.35 contextual half of `CandidateRetriever.retrieve`'s
   0.65/0.35 lexical/contextual blend. Every recall number the tool would have
   printed described a **lexical-only retriever no production path uses**. Now
   supplied with the mention's real block text.
2. **The gold recall@k block never executed.** It sat inside
   `if confirmed.mentions:`, and confirmed gold has been zero corpus-wide since
   4.74. The only recall figure `eval` ever printed was the self-retrieval
   smoke test, which hardcodes `RIGID_NAME` and reports 100% at every K by
   construction. Now runs on the silver tier.

---

## 5. What this says about the scorer

`docs/EVOLUTION.md` 4.78 established that the learned scorer settles **0 of 880**
links, its maximum output over 10,058 real pairs being 0.527 against a 0.80
threshold. The open question was *why*: starvation (A), insufficient evidence
features (B), hard rules dominating (C), or the scorer being unnecessary (D).

These retrieval numbers bear on (A). At recall@10 of 66.7% for
TRANSFERABLE_TITLE and 25.0% for RELATIONAL_DEICTIC, **the correct candidate is
frequently not in the list the scorer ever sees**. A scorer cannot rank an
entity retrieval never returned, so no amount of reweighting addresses those
cases.

This does not settle the question. It establishes that retrieval is a real,
measured bottleneck on exactly the alias types the project is about, and that
fixing the scorer first would have been the wrong order. The ablation re-run
against the post-NER-fix evidence cache is what separates the remaining
alternatives.


---

## 6. Re-measured with production-exact context — 2026-09-25

Section 2 was measured before commit `ce622aa`, when the evaluation retriever
received each mention's *block* text. Production (`resolve/runner.py`) gives
it `_context_for(mention, chapter.story_text)` — a fixed window around the
surface in the whole chapter. The evaluation now calls that same function.

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|
| **Overall** | 45 | 62.2% | 77.8% | **84.4%** | 95.6% |
| RIGID_NAME | 31 | 77.4% | 83.9% | **90.3%** | 100% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | **88.9%** | 100% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 50.0% |
| EPITHET | 1 | 100% | 100% | 100% | 100% |

**Gate: PASS** — TRANSFERABLE_TITLE recall@10 88.9% against 80%. That is
one case (7/9 → 8/9) and must be reported with its n.

**This does not change the headline finding.** Retrieval is adequate *when
handed the span*; `docs/results/SCORER_DIAGNOSIS.md` Section 4 shows 16 of 17
title-transfer mentions and 25 of 29 relational/deictic mentions are never
detected as mentions at all, so in the real pipeline they never reach
retrieval. Relational/deictic retrieval (25% @10) remains weak even when given
the span.

## 7. By hard-case category, and which context the *query* gets — 2026-09-25

`scripts/eval/recall_by_category.py` → `data/eval/recall_by_category.json`. Same
cases as the CLI (`build_gold_retrieval_cases`), same index (`_context_for`
over each chapter's story text). The hard-case category is the `[tag]` in each
hardcases record's note.

Section 6's wording needs one correction: `ce622aa` moved the **index** side to
`_context_for`, but the **query** is still the gold record's ~70-char evidence
snippet (`RetrievalCase.context = m.context`). The real resolver queries with
`_context_for` too. Both are reported; the snippet row reproduces Section 6's
84.4% exactly, which is how the script was checked against the CLI.

| Category | n | snippet @1 | @5 | @10 | @20 | production @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **All** | 45 | 62.2% | 77.8% | 84.4% | 95.6% | 66.7% | 86.7% | **88.9%** | 97.8% |
| disguise | 9 | 100% | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| reveal | 15 | 73.3% | 80.0% | 86.7% | 100% | 80.0% | 93.3% | 93.3% | 100% |
| title_transfer | 9 | 33.3% | 77.8% | 88.9% | 100% | 33.3% | 88.9% | 88.9% | 100% |
| body_change | 8 | 62.5% | 75.0% | 87.5% | 100% | 75.0% | 75.0% | 75.0% | 87.5% |
| relational_deictic | 4 | 0.0% | 25.0% | 25.0% | 50.0% | 0.0% | 50.0% | 75.0% | 100% |

Reading it honestly:

- **Production context is mildly better overall (+4.5 pts @10, 2 cases of
  45).** It is not uniformly better: `body_change` *drops* one case at @10 —
  a wider window pulls in the other body's co-occurring names.
- **Relational/deictic moves from 1/4 to 3/4 @10** — the largest relative
  change, and on n=4 it is anecdote, not a result. These mentions carry no
  name, so the wider window is the only signal they have; that direction is
  expected, the magnitude is unmeasurable at this n.
- **@1 is where title transfer fails** (33.3% either way): the right holder is
  found but ranked below the title's other holders. That is exactly the
  decision the scorer — not the retriever — must make, and
  `docs/results/SCORER_DIAGNOSIS.md` shows it never gets the chance.
- Every per-category n is ≤ 15. No category-level difference in this table is
  statistically distinguishable; the table exists to say *where* retrieval is
  not the bottleneck (disguise, reveal), not to rank categories.
- All numbers are against the SILVER LLM-derived set, not human gold.

## 8. Final table — canonical v1 run, production context — 2026-09-25

This is the table the report uses (`docs/paper/TABLES.md` Table 5,
`data/eval/recall_by_category.json`, db `data/db/reverend-insanity.db`). One
context is used throughout: `_context_for`, the query the resolver actually
issues. Reference set: **LLM-DRAFTED SILVER REFERENCE SET**, hardcases file.

| Alias type | n | @1 | @5 | @10 | @20 |
|---|---:|---:|---:|---:|---:|
| **Overall** | 46 | 67.4% | 87.0% | **89.1%** | 95.7% |
| RIGID_NAME | 32 | 84.4% | 90.6% | 90.6% | 96.9% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 88.9% | 88.9% | 100% |
| RELATIONAL_DEICTIC | 4 | 0.0% | 50.0% | 75.0% | 75.0% |
| EPITHET | 1 | 100% | 100% | 100% | 100% |

- n rose from 45 to 46 because the demonstrative fix (EVOLUTION 4.90) gave "Wang Er" a system entity to map to.
- Sections 2, 6 and 7 are earlier measurements on `ner-window-ri.db`, kept as measured.
- With the CLI's snippet context, overall @10 is 84.4%.

---

<!-- merged-from: docs/results/EXTERNAL_BENCHMARK.md -->
## Source: `docs/results/EXTERNAL_BENCHMARK.md`

# External benchmark — LitBank coreference (human-annotated)

**2026-09-26.**
- Code: `packages/pipeline/src/echotales/pipeline/eval/litbank.py`, `scripts/eval/litbank_eval.py`, tests `test_litbank_adapter.py`.
- Result: `data/eval/litbank_results.json`.

This is the project's **only accuracy number against a human-annotated key**; everything else uses the LLM-drafted silver set.

## Dataset and run

| | |
|---|---|
| Dataset | LitBank coreference layer (Bamman, Lewke & Mansoor, LREC 2020; CC BY 4.0), `github.com/dbamman/litbank` |
| Subset | **All 100 documents** (about 2,000 tokens each), `coref/brat` + `coref/conll` |
| Key used | **Person clusters only** (majority PER-typed). 24,180 key mentions: 2,665 proper names (PROP), 6,064 nominals (NOM), 15,451 pronouns (PRON) |
| System | The unmodified EchoTales pipeline (segment → mentions → anaphora → resolve), zero-shot: no training on LitBank; NER by `qwen2.5:7b` via local ollama |
| Runtime | 1,001 s for 100 documents on the local RTX 4060 |
| Adapter check | Gold scored against itself: **CoNLL 100.0** on the full person key |

## Protocols

- **P1, full person key:** all mention types. EchoTales never proposes pronoun or nominal mentions (by design), so recall is capped at the proper-name share, about 11% of key mentions.
- **P2, proper-name mentions only:** the key restricted to PROP mentions of person clusters. This is the subset EchoTales is designed to resolve.

Each protocol is scored two ways:
- **key-restricted:** the house convention, as in every other number in this repository. System mentions that do not match a key span exactly are ignored.
- **standard:** all system person mentions are scored, so spurious ones count.

Mentions match by **exact character span**. Aggregation is micro, over pooled documents; CEAF-e is matched per document and then pooled.

## Results

| Protocol | Scoring | MUC F1 | B³ F1 | CEAF-e F1 | **CoNLL F1** | Key / system / exact matches |
|---|---|---:|---:|---:|---:|---|
| P1 full person key | key-restricted | 6.2 | 34.8 | 3.8 | **14.9** | 24,180 / 977 / 977 |
| P1 full person key | standard | 6.0 | 38.5 | 3.4 | **15.9** | 24,180 / 1,898 / 977 |
| P2 proper names only | key-restricted | 45.0 | 60.2 | 34.9 | **46.7** | 2,665 / 887 / 887 |
| P2 proper names only | standard | 36.3 | 68.0 | 23.1 | **42.4** | 2,665 / 1,898 / 887 |

**Precision and recall, P2 key-restricted:**

| Metric | P | R |
|---|---:|---:|
| MUC | 99.0 | 29.2 |
| B³ | 99.7 | 43.1 |
| CEAF-e | 57.4 | 25.1 |

## What this shows

- **Linking precision transfers to human annotation.** When EchoTales links two name mentions, it is almost always right (MUC P 99.0, B³ P 99.7 key-restricted), consistent with the silver-set finding (B³ P 100).
- **Recall is the weakness, and it starts at detection.** Only 887 of 2,665 proper-name key mentions (33%) are produced with an exactly matching span. 1,011 further system mentions do not exactly match a key span; they are partly boundary differences (e.g. titles such as "Mr." inside or outside the span) and partly spurious.
- **The full-key number (CoNLL about 15–16) mostly measures design scope.** Pronouns and nominals make up 89% of LitBank person mentions, and EchoTales does not propose them as mentions.

## Comparability — read before quoting any number

| Published reference | Setting | Result | Why it is not comparable |
|---|---|---|---|
| Bamman et al. 2020, Table 5 | Supervised neural coref trained on LitBank, **predicted mentions**, 10-fold cross-validation, **all six entity classes**, all mention types | Average F1 **68.1** (B³ 62.7, MUC 84.3, CEAF-φ4 57.3) | Supervised in-domain training vs zero-shot; all entity classes vs persons; pronouns and nominals included; the official CoNLL scorer vs this repository's scorer |
| Bamman et al. 2020, Table 3 | Same system, **gold mentions** | Average F1 79.3 | Gold mention boundaries given |

**No claim of parity or superiority is made.** P1 is the closest analogue to the published setting, and EchoTales is far below it, mainly because it resolves names only.

## Known incompatibilities and caveats

1. **Genre:** 19th–20th-century English literary fiction, not translated Chinese web novels. The gazetteer cannot compound over a 2,000-token excerpt as it does over a 199-chapter volume.
2. **Single chapter per document:** the volume-scale mechanisms (compounding, temporal identity, observer state) are not exercised. This measures the resolver's local behaviour only.
3. **Exact-span matching:** stricter than head matching, so boundary disagreements count as misses.
4. **Scorer differences from CoNLL-2012:** this repository's B³ scores an unmatched ("twinless") mention against itself. In standard mode that inflates B³ in both precision and recall; for example, P2 standard B³ recall (58.8) exceeds key-restricted (43.1) for this reason. **In standard mode, MUC and CEAF-e are the reliable figures.**
5. **Person-cluster restriction:** a cluster counts as a person if most of its typed mentions are PER. LitBank's other classes are excluded.
6. **Tokenisation:** the input is LitBank's whitespace-tokenised text (e.g. "Lincoln 's Inn"), not natural prose, which can affect NER.

---

<!-- merged-from: docs/results/NER_WINDOWING_RESULT.md -->
## Source: `docs/results/NER_WINDOWING_RESULT.md`

# The NER windowing re-run — measured result

**Run 2026-09-24.** Closes `docs/archive/COMPLETION_PLAN.md` Track 1 item 3, open since
2026-09-23 and described by `docs/HANDOFF.md` as "the measuring re-run. This gates
the most."

The prediction below was **recorded before the run** (COMPLETION_PLAN, written
2026-09-23) and is adjudicated here as recorded — one part of it is refuted.

```bash
echotales --db data/scratch/reruns/ner-window-ri.db run --novel reverend-insanity
echotales --db data/scratch/reruns/ner-window-ri.db observations --novel reverend-insanity
echotales --db data/scratch/reruns/ner-window-ri.db resolve --novel reverend-insanity --capture-evidence
python3 scripts/eval/ner_window_delta.py \
    data/archive/db/reverend-insanity-webview-working.db data/scratch/reruns/ner-window-ri.db
```

Full volume, 199 chapters, `qwen2.5:7b` on a local RTX 4060. **2,806 s (47
min)** for the pipeline, 660 LLM calls, 1.31 M tokens, 0 escalations.

> **The blocker was a misdiagnosis.** Every document recorded this run as
> blocked because "ollama is unreachable from a sandboxed Claude Code shell".
> The daemon was simply not running. `ollama serve` brought it up in **one
> second**. Nothing environmental ever prevented this measurement.

---

## 1. The pre-registered prediction, adjudicated

| # | Prediction (recorded 2026-09-23) | Measured | Verdict |
|---|---|---|---|
| 1 | "CEAF-e recall rises well above 32.1%" | **25.2% → 48.9%** (same gold file, same scorer) | **CONFIRMED** |
| 2 | "mentions per chapter roughly doubles" | 48.1 → 55.1, **+14.6%** | **REFUTED** |
| 3 | "identifiability rises from 45.5%" | 48.8% → 63.0% as persisted; **46.1%** honest (see note) | ~~CONFIRMED~~ **REFUTED** (2026-09-25) |

> **Superseded 2026-09-25 (EVOLUTION 4.88):** prediction 3 was first
> adjudicated CONFIRMED on the persisted 63.0%. 879 of those attributions came
> from a pronoun-recovery pass, mislabelled `CONTEXTUAL_LLM`, that a spot check
> found right 2 times in 15. With it off, the rate is 46.1% (2,392/5,192),
> flat against 45.5%. **Two of three predictions are refuted.** The rows below
> this note keep the original wording.

**Prediction 2 is refuted, and that is the interesting part.** The fix did not
find many more *mentions*. It found many more *entities*:

| | before | after | change |
|---|---:|---:|---|
| mentions | 9,568 | 10,957 | +14.5% |
| **entities** | **82** | **261** | **+218.3%** |
| mentions past offset 6,000 | 4,626 (48.3%) | 5,353 (48.9%) | +0.6 pp |

The share of mentions past the old 6,000-char cut barely moved, because
`_locate()` already searched the **whole** chapter for every surface form the
model returned. Truncation never hid occurrences of entities the model had
already named; it hid entities appearing **only** past 6,000 characters —
never named, therefore never created, therefore never resolvable.

That is exactly the mechanism `COMPLETION_PLAN` diagnosed, and the entity
count is where it shows. The prediction had the right root cause and the wrong
observable.

---

## 2. The decisive structural check

`COMPLETION_PLAN` named one character in advance. Bai Ning Bing is
gold-annotated at three offsets in chapter 1, all past the truncation point:

| | before | after |
|---|---|---|
| ch1 mentions | **`[]`** | **`[6697, 6814, 8757]`** |
| gold offsets | `[6697, 6814, 8757]` | `[6697, 6814, 8757]` |
| first chapters she appears in | 108, 121, 125, 131, 132 | **1**, 45, 55, 74, 82 |

Three for three, to the character. A named character who was structurally
invisible for 107 chapters is now present from chapter 1.

---

## 3. Coreference metrics, like for like

Same gold file, same scorer, both databases. **Read Section 5 before quoting any of
these.**

| Metric | before | after |
|---|---:|---:|
| B³ precision | 100.0% | 100.0% |
| B³ recall | 95.4% | 96.3% |
| MUC F1 | 97.9% | 98.4% |
| **CEAF-e precision** | 84.1% | **89.0%** |
| **CEAF-e recall** | **25.2%** | **48.9%** |
| **CEAF-e F1** | 38.8% | **63.1%** |
| **CoNLL F1** | 78.1% | **86.5%** |
| gold mentions unresolved | 89 | 67 |

CEAF-e is the metric that moved, and that is coherent rather than lucky: B³
and MUC are mention-linkage metrics a competent string matcher saturates,
while **CEAF-e is entity-based** — it asks whether the system's *clusters*
align one-to-one with the gold's. Missing entities and over-splitting are
exactly what it punishes, and missing entities are exactly what truncation
caused.

---

## 4. Side effects worth recording

**The contradiction detector fires on real data for the first time.**
`docs/status/STATUS.md` had it as "Experimental — fires on constructed over-merges,
**zero hits on 60 real chapters**". Post-fix: **50 contradictions → 50
splits**. It was not a broken detector; it was starved, exactly as had been
argued for the scorer.

**Entity typing went from mostly unknown to complete.** Adding `item` to the
NER label vocabulary (the second half of EVOLUTION 4.76) moved entity kinds
from `{(unset): 64, ORGANIZATION: 10, LOCATION: 8}` to
`{ITEM: 150, SELF: 91, LOCATION: 12, ORGANIZATION: 8}` — **261/261 typed, 0
unknown** — with 558 mentions now carrying an `item` label that did not exist
in the output before.

**Speaker attribution restructured, not merely improved.** `TURN_TAKING` (478
attributions, previously shown wrong 82.9% of the time) is gone;
`CONTEXTUAL_LLM` (911) and `EXPLICIT` (780 → 1,229) replace it.
`ANONYMOUS_SLOT` fell from 2,930 to 1,920.

**Other detectors now have material to work on:** `TRANSFER=48`, `REVEAL=18`,
`DEATH=105`, `RESURRECTION=5`, `DECEPTION=2`.

**Escalation rate is still 0.0%** — 660 calls, 0 escalations, and only 2
deferrals (0.1%) across 1,532 groups. The bounded-review claim holds; the
bound is currently zero.

---

## 5. What these numbers are NOT

**The B³/MUC figures above are tautological on this gold set and must not be
quoted as accuracy.** The silver subset of `reverend-insanity.jsonl` is 1,816
mentions over **23 distinct surfaces**, 100% recoverable by grouping on the
surface string (`docs/results/EVAL_RETRIEVER.md` Section 1). Any exact-string matcher scores
~100% precision on it. The pre-fix triple P=100.0/R=94.6/F1=97.2 is
byte-identical to the headline `docs/EVOLUTION.md` 4.74 retracted.

CEAF-e is the one metric in that table with real discriminative power here,
because entity-level clustering is not recoverable from surface strings alone.
The honest claim is therefore narrow and specific:

> **The NER windowing fix roughly doubled entity-level clustering agreement
> (CEAF-e recall 25.2% → 48.9%) and tripled the entity inventory (82 → 261) on
> Reverend Insanity, measured against an LLM-derived silver reference set.**

Not "EchoTales achieves 98% B³".

---

## 6. The finding that reorders the scorer question

`echotales ablate` re-run against the post-fix evidence cache, now **15,796**
pairs (was 10,058, +57%):

```
full                      force-link= 1,318 (8.3%)  reached-scorer= 11,590  scorer-would-link= 0
no-gazetteer-compounding  force-link=   448 (2.8%)  reached-scorer= 12,460  scorer-would-link= 0
no-temporal-scoping       force-link= 1,318 (8.3%)  blocked= 2,888          scorer-would-link= 0
no-copresence-blocking    force-link= 1,329 (8.4%)  blocked=     0          scorer-would-link= 0
no-prefilters-at-all      force-link=     0 (0.0%)  reached-scorer= 15,796  scorer-would-link= 0
```

**`scorer-would-link = 0` under every condition, including the one where all
15,796 pairs reach it.**

This settles the open A/B/C/D/E question in `docs/archive/COMPLETION_PLAN.md`:

- **(A) retrieval starvation — REFUTED as the explanation.** The starvation
  hypothesis was reasonable while the pipeline could not see half of every
  chapter. It now sees all of it, the evidence cache is 57% larger, the entity
  count has tripled — and the scorer still settles nothing. Starvation was
  real and is fixed; the scorer's inertness survived it.
- **(B) + (C) + (D) — supported.** The evidence features cannot express the
  decision, the hard pre-filters carry all 1,318 force-links (1,231 of them
  gazetteer, 93%), and the scorer is unnecessary to this corpus as built.

Two further ablation results reproduce post-fix:

- **The gazetteer carries the system.** Disabling it drops force-links from
  1,318 (8.3%) to 448 (2.8%) — it accounts for **66%** of all links.
  `NAME_CONTAINMENT` rises 33 → 385 as it stops being short-circuited.
- **Temporal blocking fires on zero pairs.** `no-temporal-scoping` changes
  *nothing*: `blocked` stays at 2,888, all of it from
  `co_presence_violation`. The temporal validity gate is inert on this corpus,
  now confirmed on a 57% larger sample.

---

## 7. Retriever, post-fix

Against the hardcases silver set (the only non-trivial evaluation set):

| Alias type | n | @1 | @5 | @10 | @20 | vs pre-fix @10 |
|---|---:|---:|---:|---:|---:|---|
| Overall | 45 | 62.2% | 77.8% | 77.8% | 91.1% | 75.0% → 77.8% |
| RIGID_NAME | 31 | 77.4% | 83.9% | 83.9% | 96.8% | 83.3% → 83.9% |
| TRANSFERABLE_TITLE | 9 | 33.3% | 77.8% | **77.8%** | 100% | 66.7% → **77.8%** |
| RELATIONAL_DEICTIC | 4 | 0.0% | 25.0% | 25.0% | 25.0% | 25.0% → 25.0% |

**The gate still FAILS**, at 77.8% against an 80% threshold — but by 2.2
points rather than 13.3. `RELATIONAL_DEICTIC` did not move at all and is the
weakest part of the system by a wide margin (n=4; directional only).

> **Superseded 2026-09-25.** Re-measured with the retriever given *production's exact* context (`resolve/runner.py::_context_for`, commit `ce622aa`) rather than block text: TRANSFERABLE_TITLE recall@10 **88.9%**, so the gate **passes** — by one case at n=9. See `docs/results/EVAL_RETRIEVER.md` Section 6.


---

## 8. Status changes this run justifies

- Mention detection: **Partial → Verified** for the truncation defect
  specifically. Effect measured, prediction adjudicated, one part refuted.
- Contradiction detection: **Experimental → Verified as firing** (50 real
  contradictions; whether each is *correct* is unreviewed).
- Scorer: stays **Experimental**, and the starvation defence is now closed.
- Speaker attribution: 45.5% (Section 4.60) → 63.0% as first reported; **46.1%** once 879 low-precision pronoun guesses are excluded (EVOLUTION 4.88). Not improved.
- `docs/status/STATUS.md`'s standing truth constraint — "nothing below may say or
  imply mention recall, CEAF-e, or speaker attribution improved" — is
  **discharged** for mention detection and CEAF-e, which improved. Speaker
  attribution did not (46.1% vs 45.5%, EVOLUTION 4.88) and must not be
  described as improved.

---

<!-- merged-from: docs/results/SCORER_DIAGNOSIS.md -->
## Source: `docs/results/SCORER_DIAGNOSIS.md`

# Scorer diagnosis — why the learned scorer links nothing

**Measured 2026-09-25** on `data/scratch/reruns/ner-window-ri.db` (post-NER-fix full
volume, 15,796 cached `(mention, candidate)` evidence vectors). No scorer code
was changed to produce this. SILVER — LLM-derived reference set (Claude), not
human gold; no IAA.

```bash
python3 scripts/eval/scorer_diagnosis.py     # -> data/eval/scorer_diagnosis/{cases,candidates}.csv, summary.json
python3 scripts/eval/scorer_fit_probe.py     # -> data/eval/scorer/{fit_probe,fitted}.json
```

The starvation hypothesis was closed earlier (`docs/results/NER_WINDOWING_RESULT.md`):
the scorer links nothing on a 57% larger cache. This document asks what does
explain it, and computes each candidate cause before choosing.

**Diagnosis: F — multiple causes, with one structural root.** In order of
weight: **E/D (threshold unreachable because features are dead)**, then
**C (calibration)**, with **A (detection, upstream of retrieval)** dominating
the hard cases. Ranking (**B**) is *not* the problem.

---

## 1. Ranking works

Every silver mention whose correct candidate appears in the evidence cache:

| | |
|---|---:|
| Gold candidate present and scored | 103 |
| **Gold ranked first by the scorer** | **97 (94.2%)** |
| Gold ranked second | 6 |
| AUC, gold score vs best-wrong score | 0.80 |
| Median margin gold − best wrong | +0.044 |

**B (ranking failure) is refuted.** The scorer orders candidates correctly.

## 2. The threshold is unreachable by arithmetic — the root cause

| Weighted feature | Weight | Distinct values over 15,796 pairs | Range |
|---|---:|---:|---|
| `surface_similarity` | 1.2 | 560 | 0.0 – 1.0 |
| `context_embedding_similarity` | 2.0 | 697 | 0.0 – 1.0 |
| `speech_partner_compatibility` | 1.5 | **1** | **always 0.0** |
| `temporal_validity` | 1.0 | **1** | **always 1.0** |
| `first_attested_soft_prior` | 0.4 | 2 | −1.0 or 0.0 |

With bias −4.0, the best achievable logit is
`−4.0 + 1.2 + 2.0 + 0 + 1.0 + 0 = 0.200`, so **the maximum possible probability
is 0.550**. Linking at 0.80 needs a logit of 1.386. A pair with perfect surface
*and* perfect context similarity cannot link. The observed maximum, 0.527, sits
just under the arithmetic ceiling.

So the ceiling is not weak evidence (D in the loose sense) and not a
miscalibrated threshold in isolation (E): **three of five weighted features
carry no information on this corpus**, which removes 2.9 logits of headroom the
threshold was implicitly budgeted against. `speech_partner_compatibility` never
fires; `temporal_validity` never varies (consistent with the ablation finding
that temporal blocking fires on zero pairs).

Across *all* eleven evidence features, seven have gold-vs-wrong AUC of exactly
0.50 — they never vary: `declaration_match`, `name_containment`,
`speech_partner_compatibility`, `temporal_validity`,
`audience_scope_compatibility`, `relationship_deictic_resolution`,
`first_attested_soft_prior`. The ones that do vary separate strongly:
`surface_similarity` 0.998, `gazetteer_exact_match` 0.990,
`context_embedding_similarity` 0.813.

## 3. Every labelled decision is taken before the scorer

The 103 gold candidates' pre-filter verdicts: **101 FORCE_LINK, 2 BLOCK,
0 SCORE.** No labelled pair in the silver corpus has its correct candidate
reach the scorer. The scorer's operating region — pairs the pre-filters leave
undecided — contains **no labelled examples at all**.

This is the blocker for Steps 4 and 5 of the completion plan, and it is a data
blocker, not a modelling one.

## 4. Hard cases mostly never become mentions

| Hard-case outcome (89 records) | n |
|---|---:|
| **Mention never detected** (no system span overlaps the gold span) | **59** |
| Gold identity has no silver support elsewhere (unmapped) | 13 |
| Detected but resolved without scoring | 13 |
| Gold pre-filter BLOCK | 1 |
| Gold pre-filter FORCE_LINK | 2 |

By category, detection failure is where the project claims difficulty:
`relational_deictic` 25 of 29 undetected, `title_transfer` 16 of 17. This
reconciles an apparent contradiction with `docs/results/EVAL_RETRIEVER.md`, where
TRANSFERABLE_TITLE recall@10 is 88.9%: that evaluation hands the gold span
straight to the retriever and so bypasses detection. **Retrieval is adequate
when given the span; the mention layer rarely produces the span.**

### 4a. What the resolver decides for the hard cases it *does* detect — 2026-09-25

> **Canonical v1 run (EVOLUTION 4.90):** 30 detected, **24 of 24** decidable
> linked correctly, 0 wrong, 58 undetected; the recovered case is "Wang Er"
> (ch175, disguise). The failure taxonomy of the remaining 58 is in
> `docs/results/FINAL_EVIDENCE_TABLE.md` Section 3. The table below is the 4.84
> database and is kept as measured.

`scripts/eval/hardcase_resolution.py` → `data/eval/hardcase_resolution.json`. Uses
the coreference scorer's own identity mapping, and reports two alignments:
**overlap** (the rule above, which reproduces the 59 exactly) and **exact**
(the scorer's surface-and-offset rule, what B³/MUC actually see).

| Category | n | not detected (overlap) | correct | wrong | unresolved | gold unmapped |
|---|---:|---:|---:|---:|---:|---:|
| **All** | 88 | 59 | **23** | **0** | 0 | 6 |
| reveal | 17 | 7 | 10 | 0 | 0 | 0 |
| disguise | 13 | 2 | 9 | 0 | 0 | 2 |
| body_change | 11 | 8 | 3 | 0 | 0 | 0 |
| title_transfer | 17 | 16 | 1 | 0 | 0 | 0 |
| relational_deictic | 29 | 25 | 0 | 0 | 0 | 4 |

- **Every decidable detected hard case is linked correctly: 23 of 23, no wrong
  links, no deferrals.** That fits non-negotiable 9 (precision over recall):
  the resolver is precise on what it sees. The loss is entirely upstream.
- Under **exact** alignment only 20 are detected (68 not detected): nine
  hard-case spans are found with different boundaries (e.g. a longer name
  span), so the coreference metrics undercount detection slightly relative to
  this table.
- The 6 "gold unmapped" are detected, but their gold identity has no system
  entity, so correct/wrong cannot be decided. They are not counted as correct.
- n is small and SILVER. "23/23" has a 95% Wilson lower bound of about 86%;
  it does not establish a precision figure for the hard types in general.

## 5. Would fitting help? Measured, not assumed

`scripts/eval/scorer_fit_probe.py` fits the existing `ScoringModel` (logistic, no new
architecture) on a **chronological** split — train ≤ ch38 (920 pairs, 68
positive), calibrate ch39–50 (160), test ch51+ (190 pairs, 19 mentions).

| Scorer | LINK coverage | DEFER | NEW | False-link rate |
|---|---:|---:|---:|---:|
| Raw (default weights) | 0.0 | 0.0 | 1.0 | — |
| Fitted | 0.0 | 0.0 | 1.0 | — |
| Fitted + Platt-calibrated | 0.0 | 0.0 | 1.0 | — |

The fit barely moves the model (bias −4.09 vs −4.00; weights within ±0.3 of
defaults): with two informative features and a 7% positive rate, logistic loss
has nothing to push against. **Fitting the existing model does not fix the
scorer**, and — per Section 3 — even a scorer that did link could not be
evaluated where it matters.

## 6. What this justifies, and what it does not

**Not justified, and not built:**
- A fitted or recalibrated production scorer. The probe shows no gain, and
  there are no labels in the scorer's operating region to validate one.
- A bounded LLM investigator for ambiguous cases (completion-plan Step 5).
  Its accuracy "before and after investigation" cannot be measured without
  labelled ambiguous cases, and 67% of the hard cases never reach candidate
  generation at all, so an investigator over candidates would not see them.
  Building it would add architecture to make a documentation claim true.

**Justified by this evidence, and recorded as the next real work:**
1. **Mention detection for relational/deictic and title spans.** This is
   where the hard cases are lost — before retrieval, scoring, or any
   investigator.
2. **Either retire the three dead features or make them fire.**
   `speech_partner_compatibility` depends on speaker attribution reaching the
   resolver; `temporal_validity` needs non-MAIN facts, of which the corpus has
   none. Until then the 0.80 threshold should be recomputed from the achievable
   range, or the decision made comparative (rank + margin), since ranking is
   94% correct.
3. **Labels where the scorer operates.** A blind-annotation pass
   (`echotales annotate`) restricted to SCORE-verdict pairs is the only route
   to evaluating any change in this area.

**Honest summary for the report.** The resolver's quality comes from its
deterministic pre-filters. The learned scorer ranks well but is arithmetically
unable to link, because the features its threshold was designed around are
inert on this corpus; fitting does not rescue it; and the hard cases are lost
upstream, at mention detection.

---

<!-- merged-from: docs/results/SELF_PERSONA_VALIDATION.md -->
## Source: `docs/results/SELF_PERSONA_VALIDATION.md`

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

---

<!-- merged-from: docs/results/STATE_OF_VALIDATION.md -->
## Source: `docs/results/STATE_OF_VALIDATION.md`

# `state_of()` validation — observer and knowledge time on real data

**Measured 2026-09-24** against `data/scratch/reruns/ner-window-ri.db`, the
post-NER-fix full-volume Reverend Insanity database. This is
`docs/design/architecture.md`'s own headline acceptance test, run against a freshly
resolved volume rather than the one database that happened to carry
observations.

```bash
echotales --db data/scratch/reruns/ner-window-ri.db observations --novel reverend-insanity
# -> 3 reveals, 3 with a co-present witness -> 12 observations across 11 observers

echotales --db data/scratch/reruns/ner-window-ri.db query state-of \
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
**different axis** from Section 2: Section 2 varies *who* is asking, Section 3 varies *when they
are asking from*, and both are needed for the claim that identity is observer-
and time-scoped rather than globally true.

EVOLUTION 4.80 demonstrated Section 2 on real data. **Section 3 on real data is new here**,
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

## 5. Observer-conditioned GENERATION — demonstrated at the plan level

**Measured 2026-09-25.** The previous revision of this document said the
generation half was "wired and unit-tested" but unexercised. It is now
exercised on real data, at the level where the mechanism actually lives.

One panel request, chapter 169, cast = Bai Ning Bing, varying **only** the
observer passed to `build_render_plan`:

| Observer | aliases | persona_ids | characters in plan | `state_digest` |
|---|---:|---|---:|---|
| `READER` | 2 | `…:body1` | **1** | `de02bdbf43ff8294` |
| a witness to the ch166 reveal | 1 | — | 0 | `3ce2442598531a35` |
| a non-witness | 0 | — | 0 | `3ce2442598531a35` |

`render/cache_key.py:43` derives the artifact cache key from
`plan.state_digest`, so **a different observer produces a different cache key
for the same panel request**. That is the composition the disclosure calls
P3 ∘ P6: the generator is handed different facts, so it would produce — and
cache — a different image. The excluded information never reaches the prompt,
because the query never returned it.

**What this still is not.** No image has been generated from these two plans.
The claim demonstrated here is that *the instruction to the generator differs
by observer*, which is the mechanism; producing the side-by-side pair remains
`COMPLETION_PLAN` item 18 and needs GPU time.

### A gap this measurement exposed

The witness sees **1 alias but 0 personas**. Every row in
`self_persona_binding` carries `observer_id = READER` (92 of 92), so a
character observer can learn someone's *name* and still not resolve their
*body*. For panel casting that means a witness-conditioned render drops the
character entirely rather than depicting them with partial knowledge, which is
almost certainly not the intended semantics. `resolve/detect_observations.py`
records observations against alias facts only; persona bindings have no
equivalent writer.

---

## 6. What is NOT validated here

- **Observer-conditioned *generation* has never produced a real image.**
  `render --observer` → `render_panels(observer_id=…)` →
  `StateResolver(default_observer=…)` is wired and unit-tested, and the query
  half above is real, but the two comparison figures the paper wants
  (`COMPLETION_PLAN` item 18 — one scene as the reader knows it versus as a
  witness does) do not exist. Do not describe Section 2/Section 3 as demonstrating
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
