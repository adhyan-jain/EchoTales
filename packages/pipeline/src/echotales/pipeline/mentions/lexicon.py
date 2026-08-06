"""Per-novel lexicons (plans.md §4.5).

Different novels use different vocabularies -- Sequence vs Rank, Pathway vs
Cultivation Path -- so the lexicon is per-source, seeded per genre and grown
during processing.

The transferable-title list has to ship on day one. It cannot be learned from
the text, because the first holder of a title looks textually identical to the
second; only prior knowledge that the title *is* transferable makes the
distinction available at all. This is also the evaluation slice where
BookNLP-style baselines score near zero.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import AliasType


@dataclass(slots=True)
class Lexicon:
    """Vocabulary for one novel or genre."""

    id: str = "generic"
    description: str = ""
    transferable_titles: set[str] = field(default_factory=set)
    era_locked_titles: set[str] = field(default_factory=set)
    pathway_titles: set[str] = field(default_factory=set)
    tarot_titles: set[str] = field(default_factory=set)
    progressive_ranks: set[str] = field(default_factory=set)
    relational_deictics: set[str] = field(default_factory=set)
    generic_descriptors: set[str] = field(default_factory=set)
    honorific_prefixes: tuple[str, ...] = ()
    honorific_suffixes: tuple[str, ...] = ()
    identity_declarations: tuple[str, ...] = ()
    transfer_declarations: tuple[str, ...] = ()
    deception_declarations: tuple[str, ...] = ()

    # Aliases confirmed while reading. This is the growth half of the lexicon:
    # it starts empty and accumulates, which is what makes later chapters
    # cheaper to process than earlier ones.
    learned_names: set[str] = field(default_factory=set)

    def alias_type_for(self, surface: str) -> AliasType | None:
        """Look up a surface form's alias type, or None if unknown.

        Checked most-specific first. `GENERIC_DESCRIPTOR` is deliberately
        reachable here so callers can *detect* one and drop it -- the binding
        model refuses to persist it.
        """
        key = surface.strip().casefold()
        if key in {t.casefold() for t in self.generic_descriptors}:
            return AliasType.GENERIC_DESCRIPTOR
        if key in {t.casefold() for t in self.tarot_titles}:
            return AliasType.TAROT_TITLE
        if key in {t.casefold() for t in self.pathway_titles}:
            return AliasType.PATHWAY_TITLE
        if key in {t.casefold() for t in self.era_locked_titles}:
            return AliasType.TRANSFERABLE_TITLE
        if key in {t.casefold() for t in self.transferable_titles}:
            return AliasType.TRANSFERABLE_TITLE
        if key in {t.casefold() for t in self.relational_deictics}:
            return AliasType.RELATIONAL_DEICTIC
        if key in {t.casefold() for t in self.learned_names}:
            return AliasType.RIGID_NAME
        return None

    def is_progressive_rank(self, surface: str) -> bool:
        """Whether a prefix denotes advancement rather than a transferred title.

        "Golden Core Elder Wang" becoming "Nascent Soul Elder Wang" is one
        person advancing. Reading it as a transfer would split one character
        into two, and progressive drift is far more common than true transfer.
        """
        key = surface.strip().casefold()
        return any(rank.casefold() in key for rank in self.progressive_ranks)

    def strip_rank(self, surface: str) -> str:
        """Remove a progressive-rank prefix so the two forms compare equal."""
        text = surface.strip()
        for rank in sorted(self.progressive_ranks, key=len, reverse=True):
            if text.casefold().startswith(rank.casefold()):
                return text[len(rank) :].strip()
        return text

    def learn(self, name: str) -> None:
        self.learned_names.add(name.strip())

    @property
    def all_titles(self) -> set[str]:
        return (
            self.transferable_titles
            | self.era_locked_titles
            | self.pathway_titles
            | self.tarot_titles
        )


def load_lexicon(path: Path | str | None) -> Lexicon:
    """Load a lexicon TOML, or return an empty one when no path is configured."""
    if path is None:
        return Lexicon()
    p = Path(path)
    if not p.exists():
        return Lexicon()

    data = tomllib.loads(p.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    titles = data.get("titles", {})
    ranks = data.get("ranks", {})
    deictic = data.get("deictic", {})
    generic = data.get("generic", {})
    honorifics = data.get("honorifics", {})
    declarations = data.get("declarations", {})

    return Lexicon(
        id=meta.get("id", p.stem),
        description=meta.get("description", ""),
        transferable_titles=set(titles.get("transferable", [])),
        era_locked_titles=set(titles.get("era_locked", [])),
        pathway_titles=set(titles.get("pathway", [])),
        tarot_titles=set(titles.get("tarot", [])),
        progressive_ranks=set(ranks.get("progressive", [])),
        relational_deictics=set(deictic.get("relational", [])),
        generic_descriptors=set(generic.get("descriptors", [])),
        honorific_prefixes=tuple(honorifics.get("prefixes", [])),
        honorific_suffixes=tuple(honorifics.get("suffixes", [])),
        identity_declarations=tuple(declarations.get("identity", [])),
        transfer_declarations=tuple(declarations.get("transfer", [])),
        deception_declarations=tuple(declarations.get("deception", [])),
    )
