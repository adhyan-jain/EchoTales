"""Calibrate `ConformalGate` against confirmed gold (Section 4.1, Section 5 item 3).

**This is the fix for the blocker, not a tuning knob.** `DEFAULT_BIAS` and
`FALLBACK_LINK_THRESHOLD` were set independently and are mutually
unreachable: a maximal plausible evidence vector scores p≈0.71 against a 0.80
threshold, so no combination of scored features has ever produced a link, and
every link in the system comes from `score.prefilter`. Hand-moving either end
is fitting to nothing (and was tried: it cost 23 entities to false merges,
see Section 0). Conformal calibration sets both ends *from data* instead.

The input `calibrate()` wants is `(probability, is_correct)` pairs, and
nothing in the pipeline produced them. This module does: it replays
resolution with a hook on `score_evidence`, recording every
(mention, candidate) probability alongside whether gold says that candidate
was the right entity.

**Correctness is judged by gold cluster, not by label string.** Two entities
can share a canonical label, and one entity legitimately carries several
aliases, so "did the system pick the entity that gold puts this mention
with" is the only question that transfers. A candidate is correct when its
`target_id` is the one gold's identity maps to, established by majority over
already-aligned mentions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _system_partition
from echotales.pipeline.eval.gold import GoldSet
from echotales.pipeline.resolve.gate import ConformalGate


@dataclass(slots=True)
class CalibrationSample:
    probability: float
    is_correct: bool
    surface: str = ""
    chapter: float = 0.0


@dataclass(slots=True)
class CalibrationReport:
    novel_id: str
    samples: list[CalibrationSample] = field(default_factory=list)
    link_threshold: float = 0.0
    new_threshold: float = 0.0
    alpha: float = 0.05
    #: Gold identities that no system entity ever represented, so no pair
    #: involving them could be labelled. Reported because a calibration set
    #: that silently dropped half the cast would still look healthy.
    unmapped_identities: int = 0

    @property
    def positives(self) -> int:
        return sum(1 for s in self.samples if s.is_correct)

    def summary(self) -> str:
        pos, total = self.positives, len(self.samples)
        span = (
            f"{min(s.probability for s in self.samples):.3f}"
            f"-{max(s.probability for s in self.samples):.3f}"
            if self.samples
            else "n/a"
        )
        return (
            f"{self.novel_id}: {total:,} scored pairs "
            f"({pos:,} correct, {total - pos:,} incorrect)\n"
            f"  probability range observed: {span}\n"
            f"  calibrated at alpha={self.alpha}: "
            f"link>={self.link_threshold:.3f}  new<={self.new_threshold:.3f}\n"
            f"  gold identities with no system entity: {self.unmapped_identities}"
        )


def _identity_to_target(
    store: Store, novel_id: str, gold: GoldSet
) -> tuple[dict[str, str], int]:
    """Map each gold identity to the system entity that best represents it.

    Majority vote over aligned mentions rather than a label match: an entity's
    canonical label is whichever surface won `display_label`, which need not be
    the string an annotator chose, and two entities can share a label.
    """
    partition = _system_partition(store, novel_id, gold)
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for m in gold.mentions:
        if not m.identity:
            continue
        if target := partition.get(m.key):
            votes[m.identity][target] += 1

    mapping = {ident: c.most_common(1)[0][0] for ident, c in votes.items() if c}
    identities = {m.identity for m in gold.mentions if m.identity}
    return mapping, len(identities - set(mapping))


def collect_samples(
    novel_id: str, store: Store, gold: GoldSet
) -> tuple[list[CalibrationSample], int]:
    """Replay resolution, labelling every scored pair against gold.

    Runs against a *copy* of the caller's store contents in the sense that it
    re-resolves in place -- the caller is expected to hand this a scratch
    database, exactly as `HANDOFF` Section 0 warns for any re-resolution.
    """
    confirmed = gold.confirmed_only
    if not confirmed.mentions:
        return [], 0

    identity_to_target, unmapped = _identity_to_target(store, novel_id, confirmed)
    # Gold mention position -> the system entity gold implies it belongs to.
    want: dict[tuple[str, float, int], str] = {}
    for m in confirmed.mentions:
        if m.identity and (target := identity_to_target.get(m.identity)):
            want[m.key] = target

    samples: list[CalibrationSample] = []
    if not want:
        return samples, unmapped

    from echotales.pipeline.resolve import runner as R
    from echotales.pipeline.resolve.score import ScoringModel

    gold_by_chapter: dict[float, list] = defaultdict(list)
    for m in confirmed.mentions:
        if m.key in want:
            gold_by_chapter[m.chapter].append(m)

    model = ScoringModel()
    original = R.score_evidence

    def traced(mention, candidate, profile, ctx):  # type: ignore[no-untyped-def]
        vector = original(mention, candidate, profile, ctx)
        for gm in gold_by_chapter.get(mention.chapter, ()):
            # Surface match is enough to label the pair: the question being
            # calibrated is "given this evidence, is this candidate right",
            # and a same-surface mention in the same chapter shares the
            # answer closely enough for a threshold estimate.
            if gm.surface.strip().casefold() == mention.text.strip().casefold():
                samples.append(
                    CalibrationSample(
                        probability=model.probability(vector),
                        is_correct=candidate.target_id == want[gm.key],
                        surface=mention.text,
                        chapter=mention.chapter,
                    )
                )
                break
        return vector

    R.score_evidence = traced
    try:
        R.resolve_novel(novel_id, store)
    finally:
        R.score_evidence = original
    return samples, unmapped


def calibrate_from_gold(
    novel_id: str,
    store: Store,
    gold: GoldSet,
    *,
    alpha: float = 0.05,
) -> tuple[ConformalGate, CalibrationReport]:
    """Fit a gate to confirmed gold and report what it saw."""
    samples, unmapped = collect_samples(novel_id, store, gold)
    report = CalibrationReport(
        novel_id=novel_id, samples=samples, alpha=alpha, unmapped_identities=unmapped
    )
    gate = ConformalGate(alpha=alpha)
    if samples:
        gate.calibrate([(s.probability, s.is_correct) for s in samples], alpha=alpha)
    report.link_threshold = gate.link_threshold
    report.new_threshold = gate.new_threshold
    return gate, report
