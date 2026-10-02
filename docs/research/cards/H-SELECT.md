# Card: H-SELECT, which moments to illustrate

- **Problem:** a chapter affords k pictures. Which beats do readers want drawn?
- **Gap:** no preference-learned moment selection was found. ViStoryBench draws every storyboard line; KathaTrace is recoverability-driven; visualness work has no budget.
- **Precondition result (met):**
  - Cheap notions disagree: best top-k Jaccard 0.22 against a 0.16 random floor (13 chapters, 671 beats).
  - A zero-shot LLM follows visualness (0.33 against a 0.11 floor), not drama.
- **Next:** pairwise annotation (`moment_annotation.html`), agreement on overlap pairs, a Bradley-Terry human ranking, then alignment with the scorers.
- **Kill:** low agreement, or an LLM at the human ceiling.
- **Generalization:** illustrated editions, educational content, slide and storyboard generation.
- **Reproducibility:** `python -m echotales.research run moment_selection_baselines [--param llm=true]`.
