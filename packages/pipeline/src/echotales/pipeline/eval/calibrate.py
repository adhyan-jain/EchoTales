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
from echotales.pipeline.eval.gold import GoldSet, MentionKey
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
    want: dict[MentionKey, str] = {}
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


@dataclass(slots=True)
class HeldOutCoverage:
    """Empirical coverage of a conformal gate on data it did not see.

    A conformal predictor's (1-alpha) guarantee is about *unseen* exchangeable
    data. `calibrate_from_gold` fits and reports on the identical sample set,
    so the number it produces is a fit statistic and the guarantee is never
    validated -- a gate could memorise its calibration set and still look
    perfect (COMPLETION_PLAN Track 2 item 9, EVOLUTION 4.81).

    **Split by chapter range, never randomly.** Knowledge time only moves
    forward, and this system's whole claim is that the gazetteer compounds as
    reading proceeds. A random split leaks late-volume evidence about an
    entity into the calibration of an early-volume decision about the same
    entity, which is the same self-agreement failure as 4.74 wearing different
    clothes. Calibrating on chapters 1..k and testing on k+1.. is the only
    split that respects the arrow the model is built around.
    """

    novel_id: str
    split_chapter: float = 0.0
    alpha: float = 0.05
    calibration_size: int = 0
    test_size: int = 0
    #: Test pairs whose *correct* label the gate would have linked.
    covered: int = 0
    #: Test pairs the gate linked that were in fact wrong.
    false_links: int = 0
    link_threshold: float = 0.0

    @property
    def empirical_coverage(self) -> float:
        positives = self.covered + self.missed
        return self.covered / positives if positives else 0.0

    #: Correct pairs the gate would NOT have linked -- the guarantee's misses.
    missed: int = 0

    @property
    def target_coverage(self) -> float:
        return 1.0 - self.alpha

    def summary(self) -> str:
        if not self.test_size:
            return (
                f"{self.novel_id}: no held-out pairs after the chapter-"
                f"{self.split_chapter:g} split -- coverage not evaluated"
            )
        verdict = (
            "MET" if self.empirical_coverage >= self.target_coverage else "**NOT MET**"
        )
        return (
            f"{self.novel_id}: calibrated on chapters <= {self.split_chapter:g} "
            f"({self.calibration_size:,} pairs), tested on later chapters "
            f"({self.test_size:,} pairs)\n"
            f"  link threshold from calibration half: {self.link_threshold:.3f}\n"
            f"  empirical coverage {self.empirical_coverage:.1%} vs target "
            f"{self.target_coverage:.1%} -- {verdict}\n"
            f"  false links on held-out data: {self.false_links:,}"
        )


def held_out_coverage(
    novel_id: str,
    store: Store,
    gold: GoldSet,
    *,
    alpha: float = 0.05,
    split_fraction: float = 0.6,
) -> HeldOutCoverage:
    """Calibrate on an early chapter range, report coverage on a later one."""
    samples, _unmapped = collect_samples(novel_id, store, gold)
    result = HeldOutCoverage(novel_id=novel_id, alpha=alpha)
    if not samples:
        return result

    chapters = sorted({s.chapter for s in samples})
    if len(chapters) < 2:
        # One chapter cannot be split forwards in time. Reported as
        # "not evaluated" rather than silently returning a fit statistic
        # dressed as a held-out one.
        result.split_chapter = chapters[0] if chapters else 0.0
        result.calibration_size = len(samples)
        return result

    index = max(0, min(len(chapters) - 2, int(len(chapters) * split_fraction) - 1))
    split = chapters[index]
    result.split_chapter = split

    calibration = [s for s in samples if s.chapter <= split]
    test = [s for s in samples if s.chapter > split]
    result.calibration_size = len(calibration)
    result.test_size = len(test)
    if not calibration or not test:
        return result

    gate = ConformalGate(alpha=alpha).calibrate(
        [(s.probability, s.is_correct) for s in calibration], alpha=alpha
    )
    result.link_threshold = gate.link_threshold
    for sample in test:
        would_link = sample.probability >= gate.link_threshold
        if sample.is_correct:
            if would_link:
                result.covered += 1
            else:
                result.missed += 1
        elif would_link:
            result.false_links += 1
    return result


def calibrate_from_gold(
    novel_id: str,
    store: Store,
    gold: GoldSet,
    *,
    alpha: float = 0.05,
) -> tuple[ConformalGate, CalibrationReport]:
    """Fit a gate to confirmed gold and report what it saw.

    **This is a fit statistic, not a validated guarantee** -- it calibrates
    and reports on the same samples. Use `held_out_coverage` for the
    out-of-sample number.
    """
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
