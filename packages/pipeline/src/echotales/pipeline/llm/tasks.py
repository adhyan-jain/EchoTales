"""Task-to-model routing.

Different pipeline stages need genuinely different things from a model, and
using one model everywhere wastes capability on easy stages and starves the
hard ones.

**Hard constraint: every local model must fit entirely in VRAM.** Partial CPU
offload is not an acceptable trade here — the machine has ~4.5 GB of free
system RAM and the pipeline already streams chapters to stay inside it, so a
model spilling into RAM competes with the pipeline itself and degrades
throughput far beyond the model's own slowdown.

On an 8 GB card that caps local models at **7-8B at q4**: ~4.7 GB of weights
plus ~0.5-1 GB of KV cache at `num_ctx=8192` leaves roughly 2 GB of headroom.
A 14B at q4 is ~9 GB of weights *before* any context and cannot fit, so it is
deliberately not used regardless of its quality advantage. `ModelClient.preflight()`
enforces this by measured size, not by name.

**NER and mention detection** need cultural knowledge. Qwen2.5 is trained on
Chinese web-novel content *and* its English translations, so it recognises
xianxia naming conventions -- compound epithet-names built from a descriptor
plus a personal name -- in English prose. Western-trained models have no such
prior and read those as noun phrases rather than names.

**Segmentation, span classification and sentiment** are language-agnostic
structural tasks. "Is this a flashback?" and "is this dialogue or narration?"
do not require knowing what a Gu Master is, so a smaller general model is the
right trade.

**Hard adjudication** gets the strongest available model at higher temperature.
These are the cases the deterministic path could not settle; sampling less
greedily lets the model consider a second reading rather than committing to the
first token path.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Task(StrEnum):
    """A pipeline stage that calls a model."""

    #: Character and location recognition. Needs xianxia cultural knowledge.
    NER = "ner"
    #: Layer 3 gap-fill sweep over a chapter. Same knowledge requirement.
    MENTION_SWEEP = "mention_sweep"
    #: Deferred identity decisions. The expensive tier.
    ADJUDICATION = "adjudication"
    #: Pronoun resolution over an ambiguous paragraph.
    COREFERENCE = "coreference"
    #: Narrative-layer boundaries. Structural, language-agnostic.
    SEGMENTATION = "segmentation"
    #: Span typing. Structural.
    SPAN_CLASSIFICATION = "span_classification"
    #: Delivery and emotion extraction. Structural.
    SENTIMENT = "sentiment"
    #: Tier 4 of speaker attribution: who speaks/thinks a line the deterministic
    #: ladder could not settle, given the established cast. Cold-start chapters
    #: only -- see `speakers/contextual.py`.
    SPEAKER_ATTRIBUTION = "speaker_attribution"
    #: One call per prominent entity (never per mention), turning that
    #: entity's accumulated evidence into the demographics and Big Five
    #: traits voice casting and image generation bind to -- see `4b` and
    #: `persona/traits.py`.
    CHARACTER_PROFILE = "character_profile"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """Model and sampling settings for one task."""

    ollama_model: str
    anthropic_model: str
    temperature: float = 0.0
    max_tokens: int = 1024


#: Ollama is the development backend; Anthropic the production one. Switching
#: is a single config value -- no call site names a model.
TASK_PROFILES: dict[Task, TaskProfile] = {
    # Qwen2.5 for anything needing cultural knowledge: it is trained on Chinese
    # web-novel content and its English translations, so it has priors for
    # compound epithet-plus-name forms that read in English as ordinary noun
    # phrases. The 7b rather than the 14b purely because the 14b cannot fit in
    # 8 GB of VRAM -- this is a capability sacrifice made knowingly to keep the
    # model fully resident on the GPU.
    Task.NER: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=2048,
    ),
    Task.MENTION_SWEEP: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=1536,
    ),
    # Higher temperature on purpose: these are the cases greedy decoding
    # already failed to settle, so a less committed sampling path is the point.
    #
    # This is the stage that most wants a larger model and cannot have one
    # locally. In `hybrid`/`api` mode it escalates to the API tier instead,
    # which is the intended path for hard adjudication.
    Task.ADJUDICATION: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-sonnet-5",
        temperature=0.3,
        max_tokens=800,
    ),
    Task.COREFERENCE: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=800,
    ),
    # Structural tasks: language-agnostic, no cultural knowledge needed, so a
    # general model is the correct trade rather than a compromise. `llama3` is
    # what is installed; `llama3.1:8b` also fits in VRAM if pulled.
    Task.SEGMENTATION: TaskProfile(
        ollama_model="llama3:latest",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=800,
    ),
    Task.SPAN_CLASSIFICATION: TaskProfile(
        ollama_model="llama3:latest",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=1024,
    ),
    Task.SENTIMENT: TaskProfile(
        ollama_model="llama3:latest",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=512,
    ),
    # Needs the same cultural-naming prior as NER (the roster it picks from is
    # xianxia-style names), so qwen2.5:7b locally. Unlike adjudication this is
    # not a hard call between close identity candidates -- it is "does the
    # surrounding text name one of these N established characters" -- so the
    # cheaper Haiku tier is deliberately used on the API backend rather than
    # Sonnet, mirroring the local/API cost split the module already makes
    # elsewhere for tasks that do not need the strongest model.
    Task.SPEAKER_ATTRIBUTION: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-haiku-4-5-20251001",
        temperature=0.0,
        max_tokens=300,
    ),
    # Cultural knowledge again: judging a xianxia character's age band and
    # register from their dialogue needs the same priors NER does (an "Elder"
    # is old, a "Young Master" is not, and neither is stated outright).
    # Budget is not a concern here the way it is for per-chapter stages --
    # this fires once per *prominent entity*, so a 199-chapter novel with an
    # 82-entity cast is well under a hundred calls for the whole book.
    Task.CHARACTER_PROFILE: TaskProfile(
        ollama_model="qwen2.5:7b",
        anthropic_model="claude-sonnet-5",
        temperature=0.0,
        max_tokens=500,
    ),
}

#: Weights must not exceed this fraction of total VRAM, leaving room for the
#: KV cache and the CUDA context. 0.70 of 8 GB is ~5.7 GB, which accommodates a
#: 7B q4 (~4.7 GB) plus an 8k-context cache without spilling.
VRAM_BUDGET_FRACTION = 0.70


def profile_for(task: Task) -> TaskProfile:
    return TASK_PROFILES[task]


def models_required(backend: str) -> set[str]:
    """Every model the configured backend needs.

    Used by the preflight check so a missing pull fails at startup with a
    `ollama pull` command rather than mid-run on chapter 140.
    """
    attr = "ollama_model" if backend == "ollama" else "anthropic_model"
    return {getattr(p, attr) for p in TASK_PROFILES.values()}
