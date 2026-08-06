"""Detecting surface-form variants that should share one identity.

Three distinct problems get confused with each other, and separating them is
the whole point of this module:

**1. Lexical variants of one alias** -- "Miss Justice", "Lady Justice", "The
Justice", "Justice". These are one alias written several ways. The
`comparison_key` collapses them, and this module *audits* that it does.
Purely a string problem, no world knowledge needed.

**2. Several aliases, one entity** -- a code name and a legal name bound to the
same `self`. Two `alias_binding` rows, one `target_id`. This is what the global
resolver is for.

**3. Disguise with audience scoping** -- the code name exists specifically to
conceal the legal name from some observers. Same as (2) plus `observer_id` and
`truth_status=FABRICATED` on the binding, so a query as the deceived faction
returns only the code name.

Only (1) is safe to solve mechanically. (2) and (3) are the research problem,
and hand-supplying them as *input* would be solving the task by hand -- so this
module deliberately reports candidates rather than merging anything.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from echotales.pipeline.ingest.normalize import comparison_key, strip_honorifics

#: Decorations that mark a variant of the same underlying name rather than a
#: different name. Used only to explain a collision, never to create one.
_DECORATIONS = ("the ", "a ", "mr", "mrs", "ms", "miss", "lady", "lord", "sir", "elder", "old")


@dataclass(slots=True)
class VariantFamily:
    """Surface forms that already collapse to one comparison key."""

    key: str
    surfaces: set[str] = field(default_factory=set)

    @property
    def canonical(self) -> str:
        """Shortest bare form -- the one that matches the most mentions."""
        return min(self.surfaces, key=lambda s: (len(strip_honorifics(s)), len(s)))

    @property
    def size(self) -> int:
        return len(self.surfaces)


@dataclass(slots=True)
class SuspectedSplit:
    """Two forms that look like variants but do NOT share a key.

    A warning, not a merge. Every one of these is either a normalisation gap
    worth fixing or two genuinely distinct entities, and only inspection tells
    which.
    """

    a: str
    b: str
    key_a: str
    key_b: str
    reason: str


def group_variants(surfaces: list[str]) -> dict[str, VariantFamily]:
    """Group surface forms by comparison key."""
    families: dict[str, VariantFamily] = {}
    for surface in surfaces:
        key = comparison_key(surface)
        if not key:
            continue
        family = families.setdefault(key, VariantFamily(key=key))
        family.surfaces.add(surface)
    return families


def _shares_head_noun(a: str, b: str) -> bool:
    """Whether two forms end in the same word.

    "Miss Justice" and "The Justice" share a head noun; "Miss Justice" and
    "Miss Star" do not. The head is what carries identity in a decorated
    title, so a shared head with different decoration is the signature of a
    normalisation gap.
    """
    ta, tb = a.split(), b.split()
    return bool(ta and tb) and ta[-1].casefold() == tb[-1].casefold()


def _decoration_only_difference(a: str, b: str) -> bool:
    """Whether two forms differ only by leading decoration."""
    bare_a = strip_honorifics(a, strip_articles=True).casefold()
    bare_b = strip_honorifics(b, strip_articles=True).casefold()
    return bare_a == bare_b and bare_a != ""


def find_suspected_splits(
    surfaces: list[str], *, max_pairs: int = 200_000
) -> list[SuspectedSplit]:
    """Find pairs that look like variants but normalise differently.

    This is the audit that would have caught "Mr. Fool" failing to strip while
    "Miss Justice" stripped fine -- an inconsistency invisible to eye review
    because both *look* handled.

    Compared within head-noun buckets rather than all-pairs, so the cost stays
    linear in practice on an alias set of thousands.
    """
    by_head: dict[str, list[str]] = defaultdict(list)
    for surface in surfaces:
        tokens = surface.split()
        if tokens:
            by_head[tokens[-1].casefold()].append(surface)

    out: list[SuspectedSplit] = []
    checked = 0
    for head, group in by_head.items():
        if len(group) < 2:
            continue
        for a, b in combinations(sorted(set(group)), 2):
            checked += 1
            if checked > max_pairs:
                return out
            key_a, key_b = comparison_key(a), comparison_key(b)
            if key_a == key_b:
                continue
            if _decoration_only_difference(a, b):
                reason = "differ only by honorific/article decoration"
            elif _shares_head_noun(a, b) and abs(len(a) - len(b)) <= 12:
                reason = f"share head noun {head!r} with different decoration"
            else:
                continue
            out.append(
                SuspectedSplit(a=a, b=b, key_a=key_a, key_b=key_b, reason=reason)
            )
    return out


@dataclass(slots=True)
class VariantReport:
    families: int = 0
    multi_form_families: int = 0
    largest_family: tuple[str, int] = ("", 0)
    suspected_splits: list[SuspectedSplit] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.suspected_splits

    def summary(self) -> str:
        lines = [
            f"{self.families} variant families, "
            f"{self.multi_form_families} with more than one surface form",
        ]
        if self.largest_family[1] > 1:
            lines.append(
                f"  largest: {self.largest_family[0]!r} ({self.largest_family[1]} forms)"
            )
        if self.suspected_splits:
            lines.append(f"  SUSPECTED SPLITS: {len(self.suspected_splits)}")
            for split in self.suspected_splits[:10]:
                lines.append(f"    {split.a!r} / {split.b!r} -- {split.reason}")
            if len(self.suspected_splits) > 10:
                lines.append(f"    ... and {len(self.suspected_splits) - 10} more")
        else:
            lines.append("  no suspected splits")
        return "\n".join(lines)


def audit_surfaces(surfaces: list[str]) -> VariantReport:
    """Audit an alias set for normalisation gaps."""
    families = group_variants(surfaces)
    multi = [f for f in families.values() if f.size > 1]
    largest = max(families.values(), key=lambda f: f.size, default=None)
    return VariantReport(
        families=len(families),
        multi_form_families=len(multi),
        largest_family=(largest.canonical, largest.size) if largest else ("", 0),
        suspected_splits=find_suspected_splits(surfaces),
    )
