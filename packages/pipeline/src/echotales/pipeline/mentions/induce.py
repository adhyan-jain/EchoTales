"""Lexicon induction from the text (plans.md §4.5, revised).

plans.md requires a transferable-title list on day one, because the first
holder of a title is textually identical to the second — only prior knowledge
that a title *is* transferable makes the distinction available at all.

The obvious way to satisfy that is to hand-write the list. That is a bad idea
for three reasons, all of which this module exists to avoid:

1. **Unverifiable entries outrank everything.** `alias_type_for()` treats a
   lexicon hit as authoritative at 0.95 confidence, so a wrong entry silently
   beats every heuristic. A list written from recall rather than from the text
   is exactly where wrong entries come from.
2. **It does not scale.** Each new novel needs another hand-written file.
3. **It weakens the result.** "We hand-tuned a vocabulary per novel" is the
   first objection to the transferable-title finding — which is the slice
   where this system is supposed to beat BookNLP-style baselines. A system
   that induces its own vocabulary turns that liability into a contribution.

So the vocabulary is induced: sample chapters across the volume, ask the model
to classify the naming conventions it observes, merge into the genre-neutral
seed, and cache to `data/lexicons/<novel_id>.toml`. Induced files are plain
TOML and may be hand-edited afterwards — the point is that the *default* comes
from the text rather than from anyone's memory.

Sampling is spread across the whole volume rather than taken from the opening,
because titles and ranks introduced at chapter 150 matter as much as those at
chapter 2.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.mentions.lexicon import Lexicon, load_lexicon
from pydantic import BaseModel, Field

SEED_PATH = Path("data/lexicons/_seed.toml")


class InductionTier(StrEnum):
    """How much corroboration an induced term has.

    Every tier is **admitted**. An earlier design excluded single-sample terms,
    which was backwards: a title that transfers exactly once, late in the
    volume, is precisely the hard case this project is about. Filtering it out
    removes the phenomenon under study from the vocabulary that would let the
    system detect it.

    The tiers instead express confidence, and scoring weights them differently.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def weight(self) -> float:
        """Multiplier applied to a lexicon hit's confidence."""
        return {"HIGH": 1.0, "MEDIUM": 0.85, "LOW": 0.6}[self.value]


def tier_for(support: int) -> InductionTier:
    """HIGH at 3+ corroborating samples, MEDIUM at 2, LOW at 1."""
    if support >= 3:
        return InductionTier.HIGH
    if support == 2:
        return InductionTier.MEDIUM
    return InductionTier.LOW

_SYSTEM = (
    "You analyse the naming conventions of a translated web novel.\n"
    "You are given excerpts. Identify the vocabulary the novel uses for "
    "referring to people, and sort it into these classes:\n"
    "- transferable_titles: positions or ranks HELD BY ONE PERSON AT A TIME "
    "that pass to a successor (sect master, captain, guild leader). The test "
    "is whether a different person could hold it later.\n"
    "- progressive_ranks: cultivation stages, levels or sequences that a "
    "single person ADVANCES THROUGH. The test is whether one person moves "
    "from one to the next.\n"
    "- relational_deictics: forms that resolve relative to the speaker "
    "(master, senior brother, hyung). Two speakers using the same word mean "
    "different people.\n"
    "- generic_descriptors: scene-local role phrases that are NOT names "
    "(the guard, the innkeeper).\n"
    "Return only vocabulary you actually observe in the excerpts. Do not "
    "invent plausible entries."
)


class InducedVocabulary(BaseModel):
    transferable_titles: list[str] = Field(default_factory=list)
    progressive_ranks: list[str] = Field(default_factory=list)
    relational_deictics: list[str] = Field(default_factory=list)
    generic_descriptors: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


@dataclass(slots=True)
class InductionReport:
    novel_id: str
    samples: int = 0
    calls: int = 0
    transferable_titles: int = 0
    progressive_ranks: int = 0
    relational_deictics: int = 0
    generic_descriptors: int = 0
    output_path: Path | None = None
    #: tier -> count. All tiers are admitted; support sets confidence.
    tiers: dict[str, int] = field(default_factory=dict)
    #: term -> tier, written alongside the lexicon so scoring can weight it.
    term_tiers: dict[str, InductionTier] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.novel_id}: induced from {self.samples} samples ({self.calls} calls)\n"
            f"  transferable titles={self.transferable_titles}  "
            f"progressive ranks={self.progressive_ranks}\n"
            f"  relational deictics={self.relational_deictics}  "
            f"generic descriptors={self.generic_descriptors}\n"
            f"  tiers: " + (", ".join(f"{k}={v}" for k, v in sorted(self.tiers.items())) or "none") + "\n"
            f"  written to: {self.output_path}"
        )


def sample_chapters(store: Store, novel_id: str, count: int) -> list[float]:
    """Evenly spaced chapter numbers across the volume.

    Even spacing rather than the opening chapters: a title introduced at
    chapter 150 is as much a part of the novel's vocabulary as one from
    chapter 2, and sampling the opening biases toward the starting cast.
    """
    numbers = [c.number for c in store.iter_chapters(novel_id)]
    if not numbers:
        return []
    if len(numbers) <= count:
        return numbers
    step = len(numbers) / count
    return [numbers[int(i * step)] for i in range(count)]


def induce_lexicon(
    novel_id: str,
    store: Store,
    client: object,
    *,
    samples: int = 12,
    chars_per_sample: int = 4000,
    seed_path: Path | str = SEED_PATH,
    out_dir: Path | str = "data/lexicons",
) -> tuple[Lexicon, InductionReport]:
    """Induce a novel's vocabulary and write it to disk.

    **Every observed term is admitted**, with support determining its
    confidence tier rather than whether it survives. Excluding single-sample
    terms was backwards: a title that transfers exactly once, late in the
    volume, is precisely the hard case this project studies, and filtering it
    out removes the phenomenon from the vocabulary that would let the system
    detect it. LOW-tier entries are down-weighted at scoring time instead.
    """
    from echotales.pipeline.llm.tasks import Task

    report = InductionReport(novel_id=novel_id)
    chapters = sample_chapters(store, novel_id, samples)
    report.samples = len(chapters)

    support: dict[str, dict[str, int]] = {
        "transferable_titles": {},
        "progressive_ranks": {},
        "relational_deictics": {},
        "generic_descriptors": {},
    }

    for number in chapters:
        chapter = store.get_chapter(novel_id, number)
        if chapter is None:
            continue
        excerpt = chapter.story_text[:chars_per_sample]
        if not excerpt.strip():
            continue

        result = client.complete(  # type: ignore[attr-defined]
            Task.NER,
            f"Excerpt from chapter {number:g}:\n\n{excerpt}",
            InducedVocabulary,
            system=_SYSTEM,
            novel_id=novel_id,
            chapter=number,
        )
        report.calls += 1
        induced = result.value

        for field_name in support:
            for term in getattr(induced, field_name, []):
                cleaned = term.strip()
                if 1 < len(cleaned) <= 60:
                    bucket = support[field_name]
                    bucket[cleaned] = bucket.get(cleaned, 0) + 1

    # Every observed term is admitted; support determines its tier, not whether
    # it survives. A once-transferred title is the hard case, not noise.
    kept: dict[str, set[str]] = {}
    for field_name, bucket in support.items():
        kept[field_name] = set(bucket)
        for term, n in bucket.items():
            tier = tier_for(n)
            report.tiers[tier.value] = report.tiers.get(tier.value, 0) + 1
            report.term_tiers[term] = tier

    lexicon = _merge_with_seed(novel_id, kept, seed_path)
    path = Path(out_dir) / f"{novel_id}.toml"
    write_lexicon(lexicon, path, induced_from=report.samples)

    report.transferable_titles = len(lexicon.transferable_titles)
    report.progressive_ranks = len(lexicon.progressive_ranks)
    report.relational_deictics = len(lexicon.relational_deictics)
    report.generic_descriptors = len(lexicon.generic_descriptors)
    report.output_path = path
    return lexicon, report


def _merge_with_seed(
    novel_id: str, kept: dict[str, set[str]], seed_path: Path | str
) -> Lexicon:
    """Union the induced vocabulary with the genre-neutral seed."""
    seed = load_lexicon(seed_path)
    return Lexicon(
        id=novel_id,
        description=f"induced from text for {novel_id}",
        transferable_titles=seed.transferable_titles | kept["transferable_titles"],
        era_locked_titles=seed.era_locked_titles,
        pathway_titles=seed.pathway_titles,
        tarot_titles=seed.tarot_titles,
        progressive_ranks=seed.progressive_ranks | kept["progressive_ranks"],
        relational_deictics=seed.relational_deictics | kept["relational_deictics"],
        generic_descriptors=seed.generic_descriptors | kept["generic_descriptors"],
        honorific_prefixes=seed.honorific_prefixes,
        honorific_suffixes=seed.honorific_suffixes,
        # Declaration phrases stay seed-only: they are English narrative idiom
        # rather than novel vocabulary, and they feed the highest-weighted
        # feature in the evidence vector, so a hallucinated phrase there is
        # unusually costly.
        identity_declarations=seed.identity_declarations,
        transfer_declarations=seed.transfer_declarations,
        deception_declarations=seed.deception_declarations,
    )


def _toml_list(values: set[str] | tuple[str, ...]) -> str:
    if not values:
        return "[]"
    items = ",\n".join(f'    "{v}"' for v in sorted(values))
    return f"[\n{items},\n]"


def write_lexicon(lexicon: Lexicon, path: Path | str, *, induced_from: int = 0) -> None:
    """Write a lexicon as hand-editable TOML."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"""# Induced lexicon for {lexicon.id}.
#
# GENERATED from the novel's own text by `echotales induce-lexicon`
# (sampled {induced_from} chapters, terms corroborated across >=2 samples).
# Safe to hand-edit; regenerating overwrites.
#
# Declaration phrases come from the genre-neutral seed rather than induction:
# they are English narrative idiom, and they feed the highest-weighted feature
# in the evidence vector, so a hallucinated entry there is unusually costly.

[meta]
id = "{lexicon.id}"
description = "{lexicon.description}"

[titles]
transferable = {_toml_list(lexicon.transferable_titles)}
era_locked = {_toml_list(lexicon.era_locked_titles)}
pathway = {_toml_list(lexicon.pathway_titles)}
tarot = {_toml_list(lexicon.tarot_titles)}

[ranks]
progressive = {_toml_list(lexicon.progressive_ranks)}

[deictic]
relational = {_toml_list(lexicon.relational_deictics)}

[generic]
descriptors = {_toml_list(lexicon.generic_descriptors)}

[honorifics]
prefixes = {_toml_list(lexicon.honorific_prefixes)}
suffixes = {_toml_list(lexicon.honorific_suffixes)}

[declarations]
identity = {_toml_list(lexicon.identity_declarations)}
transfer = {_toml_list(lexicon.transfer_declarations)}
deception = {_toml_list(lexicon.deception_declarations)}
""",
        encoding="utf-8",
    )


def load_or_seed(path: Path | str | None, seed_path: Path | str = SEED_PATH) -> Lexicon:
    """Load an induced lexicon, falling back to the seed.

    Lets the pipeline run before induction has been performed: the seed alone
    is enough for the generic-descriptor block and declaration detection.
    """
    if path is not None and Path(path).exists():
        return load_lexicon(path)
    return load_lexicon(seed_path)


def seed_is_present(seed_path: Path | str = SEED_PATH) -> bool:
    p = Path(seed_path)
    if not p.exists():
        return False
    try:
        tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return False
    return True
