# Baselines — configuration, cost, and what they can and cannot show

**Written 2026-09-24.** Two academic comparison points, both built, both
local-only and zero API spend. Where a run has not happened this file says so,
rather than leaving a blank that reads as a zero.

Everything here is scored against an **LLM-derived silver reference set, not
human gold, with no IAA** (`docs/GOLD_DATASET_README.md`).

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
meaningful are **100% surface-trivial** (`docs/EVAL_RETRIEVER.md` Section 1): their
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
| Section size | **10 chapters**, not `plans.md`'s 30 |
| Call shape | **O(sections)** — ~6 calls for ch1-60 |
| Has | Long context, a running roster |
| Lacks | Gazetteer, temporal scoping, incremental evidence, alias typing, DEFER/correction |

**Why 10 chapters and not 30.** Measured, not assumed: RI runs ~2,300 input
tokens per chapter, so 15 chapters already clamps at the 32,768 ceiling, and
`num_ctx` covers input *and* output combined in Ollama. A 30-chapter section
silently truncates rather than raising — `prompt_eval_count` pins at 32,768
whether the request asked for 32,768 or 65,536. `plans.md`'s "approximately 30
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

This is the honest, non-strawman result of the architecture `plans.md`
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
(`docs/PRIOR_ART_LINKKG.md`): LINK-KG is a *legal-document* system scored on
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
> `scripts/baseline_comparison.py` → `data/eval/baseline_comparison.json` →
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
