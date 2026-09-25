# Research contribution matrix

**2026-09-25.** Separates genuine research contributions from engineering integration.
- Evidence comes from `docs/FINAL_EVIDENCE_TABLE.md`, scored against the **LLM-drafted silver reference set** (not human-annotated).
- Prior-work details are in `docs/paper/RELATED_WORK_FINAL.md`.
- Patent novelty is a different question, handled separately and privately; paper novelty is assessed here on its own terms.

| Class | Contribution | Research gap | Closest prior work | EchoTales difference | Evidence | Result | Strength | Missing validation |
|---|---|---|---|---|---|---|---|---|
| A. Narrative representation | Temporal identity graph: fuzzy story-time intervals separate from chapter order; Self / Persona split; typed and transferable aliases | Most literary KGs key state to chapter or plot segment; identity is one static node | E2RAG/ChronoQA; Living the Novel; HPD; near-identity guidelines (LitBank, FantasyCoref) | Identity itself is time-scoped (who a name refers to, which body a Self has) rather than only attributes | Canonical run; 1 real reincarnation case; 11,092 interval-scoped alias bindings | Representation works end to end | **Medium**: coherent and implemented, but real data exercises only part of it | Transmigration fails (LOTM); concurrent cases test-only; no non-main timeline facts |
| B. Entity resolution | Precision-first incremental resolution with hard constraints and a compounding gazetteer | Chunked LLM coref (LlmLink) spends model calls per link | BOOKCOREF, LlmLink, LINK-KG, Vala 2015 | Zero model calls at resolution; rules make every link | Table 4, 6, 7; hard cases | CEAF-e F1 67.4; B³ P 100; 24/24 detected hard cases correct; baselines 0.2% / 4.6% vs 78.9% recall (ch1–10) | **Medium as an empirical finding**, low as a method (rules) | Human-annotated sample; external benchmark (BOOKCOREF/LitBank); detection of address terms, relational references and titles (58/88 missed) |
| C. Observer-conditioned state | Identity visibility per observer and per knowledge position, with observations derived from reveal-scene co-presence | ToM work models beliefs but does not maintain a queryable identity graph from real long text | Disney IAAI-18 (per-character KB with learned time); EvolvTrip; STAGE; ToM benchmarks | Visibility of *identity facts* (which names resolve to whom), derived automatically, queryable at any position | `observer_evidence.json` | Reader 2 / witness 1 / non-witness 0; witness 0/1/1 over time | **Medium**: the specific form is different, the general idea is crowded | Only 3 reveals / 12 observation rows; no precision/recall of witness derivation |
| D. Temporal reasoning | Three axes (story, discourse, knowledge); retraction distinct from interval end | Classical narratology plus bitemporal DBs; rarely combined for identity | Mani; NarrativeTime; Snodgrass; Zep | Retraction semantics for narrative identity | Tests only for retraction and timelines | — | **Low** as evaluated | Real retraction and non-main timeline data |
| E. Multimodal generation | Generation compiled from `state_of(position, observer)`; per-Persona references | Story visualisation uses global or authored state, with no viewpoint | NGP, CANVAS, FilmWorld, StoryState | Observer axis in generation | `OBSERVER_CONTRAST_VALIDATION.md` | Reader 5/5 vs non-reader 0/5 identity-conditioned panels (1 chapter; any character observer currently gets 0/5) | **Medium-low**: a distinctive demonstration, tiny scale, no quality metric | Multi-chapter contrast; witness-level rendering; CLIPScore or human preference |
| F. Consistency / invalidation | Artifact cache keys from a digest of consulted facts | Build-system technique; not applied to narrative-state media | Build Systems à la Carte; StoryState localized edits | Applied to observer- and position-filtered narrative state | Tests; keys differ 10/10 | — | **Low** as research (engineering) | Measured regeneration savings |
| G. Retrieval / efficiency | Candidate retrieval given the span | Standard | — | — | Table 5 | Recall@10 89.1% (n=46) | **Low** (supporting result) | — |
| H. Empirical findings | (1) Hard cases are lost at detection, not linking. (2) Surface-trivial reference sets make MUC/B³ measure string matching. (3) Learned scorer adds nothing over rules. (4) Pre-registered predictions: 2 of 3 refuted. (5) LLM speaker attribution is unstable across runs | Evaluation practice in literary coref | BOOKCOREF, LitBank methodology | Honest negative and diagnostic results | Tables 4–7, taxonomy, EVOLUTION 4.84–4.90 | See left | **Medium-high as a findings/analysis paper** | Human-annotated confirmation sample |

**Which are genuine research contributions:**
- **H** (empirical and diagnostic findings);
- **C** in its identity-visibility form;
- **A** as a representation, if the evaluation is made sharper.

**Engineering integration:** B's rules, F, G, and most of E.

**Strongest single paper framing.** "Observer- and time-scoped identity in long serialised fiction: a representation, a pipeline, and what actually limits it." It leads with C and A as the representation, H as findings, and E as a demonstration.
