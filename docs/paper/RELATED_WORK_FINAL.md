# Related work — final comparison

**2026-09-25.** For the report and the paper. Short paraphrases only.
- Records were checked against primary text where marked "(full text)"; otherwise from the abstract or landing page.
- The complete record list, with links, is kept privately alongside the IP due-diligence notes; the table below is the citable subset.
- "Year" is the first public version.

| Paper | Year | Problem | Method | Narrative state? | Temporal identity? | Observer knowledge? | Entity resolution? | Multimodal output? | Generation consistency? | Evaluation | EchoTales distinction (methodological, not "better") |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LlmLink (Zhu, Wang, He; COLING 2025) (full text) | 2025 | Long-narrative coreference | Dual LLM with memory across chunks | partial (memory) | no | no | **yes** | no | no | LitBank, DOC-ARC; MUC/B³/CoNLL | EchoTales resolves with zero LLM calls at resolution and adds time-scoped identity |
| LINK-KG (Meher, Domeniconi, Correa-Cabrera; arXiv 2510.26486) (full text) | 2025 | KG from legal smuggling-case documents | Extends LlmLink with a type-specific prompt cache | no | no | no | **yes** | no | no | Node duplication, noise | Different domain and metrics; EchoTales' gazetteer is a measured compounding property |
| BOOKCOREF (ACL 2025) | 2025 | Book-scale coreference benchmark | Annotation plus a pipeline | no | no | no | **yes** | no | no | CoNLL-F1 | EchoTales does not report on it yet (a planned experiment) |
| EvolvTrip / LitCharToM (Yang et al.; arXiv 2506.13641) (full text) | 2025 | Character ToM in literature | Perspective-aware temporal belief triples per plot segment (GPT-4o plus review) | yes | no | **yes** (per character) | no | no | no | ToM QA | EchoTales scopes *identity facts* per observer and queries them at arbitrary positions |
| STAGE (Tian et al.; arXiv 2601.08510) (full text) | 2026 | Screenplay understanding benchmark | Checkpointed character states; epistemic links (witnessed / told / inferred) | **yes** | partial | **yes** | partial | no | no | KG, QA, role-play | EchoTales derives witnessing automatically for identity reveals and drives generation from it |
| Computer-Assisted Authoring (Sanghrajka et al., Disney; IAAI-18) (full text) | 2018 | Script authoring assistance | Per-character knowledge bases with the time point learned | yes | no | **yes** | co-reference preprocessing | storyboards (related patents) | no | Qualitative | Identity visibility, time-scoped aliases/bodies, generation conditioned on the observer |
| Living the Novel (Huang et al.; arXiv 2512.07474) (full text) | 2025 | Timeline-aware role-play agents | Story-time KG with a global cutoff | yes | no | reader-position only | alias normalisation | no | no | Dialogue quality | Per-character observers; identity bindings |
| TimeChara (Ahn et al.; Findings ACL 2024) | 2024 | Point-in-time role-play | Evaluation plus narrative-expert method | partial | no | point-in-time | no | no | no | Hallucination rate | Graph, not prompting |
| ToMi / FANToM / Hi-ToM / OpenToM | 2019–2024 | ToM evaluation | Synthetic or LLM-generated stories and conversations | local | no | **yes** | no | no | no | QA accuracy | EchoTales works on real long novels and persists the result |
| E2RAG / ChronoQA (Zhang et al.) | 2025 | Time-aware narrative QA | Entity-event graph per position | **yes** | partial | no | partial | no | no | QA | Identity intervals and observer axis |
| Narrative Graph Prompting (Shin & Kaneko; ICCVW 2025) | 2025 | Visually consistent story images | Graph with canonical attributes → LLM prompts | yes (static) | no | no | no | images | **yes** | Consistency metrics | Graph derived from real text; time- and observer-scoped |
| StoryWeaver (arXiv 2412.07375) | 2024 | Knowledge-enhanced character customisation | Character Graph | yes (static) | no | no | no | images | **yes** | Visual metrics | Same |
| CANVAS (Mondal et al.; arXiv 2604.13452) | 2026 | Continuity-aware storyboarding | Continuity plan of appearance, location and props | **yes** (temporal) | appearance over time | no | no | images | **yes** | Continuity metrics plus a human study | Observer axis; state resolved from long source text |
| FilmWorld (arXiv 2607.19038) | 2026 | Novel-to-film | Discretised entity states with hashed references | **yes** | per-state references | no | no | video | **yes** | Video metrics | Observer axis; Self/Persona split; volume-scale input |
| StoryState (Sarkar et al.; arXiv 2602.01305) | 2026 | Editable storybooks | Persistent state with localized page edits | yes | no | no | no | images | yes | Consistency | Dependency digest of consulted facts; observer axis |

**Positioning sentence for the paper.** Prior work tracks what characters believe (EvolvTrip, STAGE, ToM benchmarks) or keeps generated media consistent from a global story state (NGP, CANVAS, FilmWorld). EchoTales maintains time- and observer-scoped *identity* over a real multi-hundred-chapter text and uses that same query to condition generation. The distinction lies in that pairing and in the empirical findings, not in either half alone.

**Not directly comparable, and not reproduced here:** LINK-KG's node-duplication metrics; BOOKCOREF and LitBank scores (the adapter has not been run); any human-evaluated generation benchmark.
