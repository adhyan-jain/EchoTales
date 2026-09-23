"""Tests for the structural gold validator.

Each check here corresponds to a defect that was live in a shipped annotation
file and that nothing caught. Written as "this specific failure is detected",
not as coverage.
"""

from __future__ import annotations

import pytest
from echotales.pipeline.eval.gold import GoldMention, GoldSet, MentionKind, Provenance
from echotales.pipeline.eval.validate_gold import validate_gold


def _m(
    chapter: float,
    offset: int,
    surface: str,
    identity: str,
    *,
    kind: MentionKind = MentionKind.CHARACTER,
    drafted_by: str = "claude-opus-5",
) -> GoldMention:
    return GoldMention(
        novel_id="demo",
        chapter=chapter,
        offset=offset,
        surface=surface,
        identity=identity,
        kind=kind,
        provenance=Provenance.MODEL,
        drafted_by=drafted_by,
    )


def _finding(report, check: str):  # type: ignore[no-untyped-def]
    return next(f for f in report.findings if f.check == check)


class TestSurfaceTriviality:
    """The most important check in the module.

    A partition recoverable by grouping on the surface string is reproduced
    exactly by any string matcher, so agreeing with it measures string matching
    rather than identity resolution. Measured on the real corpus:
    `reverend-insanity.jsonl`'s silver subset is 1,816 mentions over 23
    surfaces, 100% trivial, and scoring against it returns the B-cubed figure
    EVOLUTION 4.74 retracted.
    """

    def test_a_one_to_one_surface_map_fails(self) -> None:
        gold = GoldSet(
            "demo",
            [
                _m(1.0, 0, "Name A", "Person A"),
                _m(1.0, 50, "Name A", "Person A"),
                _m(2.0, 10, "Name B", "Person B"),
            ],
        )
        finding = _finding(validate_gold(gold, "t"), "surface-triviality")
        assert finding.severity == "error"
        assert "100.0%" in finding.detail

    def test_an_ambiguous_surface_lowers_it(self) -> None:
        """One surface denoting two people is precisely what a resolver is for,
        and what a trivial gold set cannot contain."""
        gold = GoldSet(
            "demo",
            [
                _m(1.0, 0, "the Elder", "Person A"),
                _m(2.0, 0, "the Elder", "Person B"),
                _m(3.0, 0, "Name C", "Person C"),
            ],
        )
        finding = _finding(validate_gold(gold, "t"), "surface-triviality")
        assert finding.severity == "info"
        # 2 of 3 mentions sit on an ambiguous surface, so only 1/3 is trivial.
        assert "33.3%" in finding.detail

    def test_it_reports_the_shape_not_just_the_verdict(self) -> None:
        gold = GoldSet("demo", [_m(1.0, 0, "Name A", "Person A")])
        finding = _finding(validate_gold(gold, "t"), "surface-triviality")
        assert "1 distinct surfaces" in finding.detail
        assert "1 identities" in finding.detail


class TestCollidingKeys:
    def test_distinct_surfaces_at_one_offset_do_not_collide(self) -> None:
        """The prefix case, post-2026-09-24: "Gu Yue" (clan) and "Gu Yue Fang
        Yuan" (person) genuinely both begin at one offset, and both records
        must survive."""
        gold = GoldSet(
            "demo",
            [
                _m(1.0, 100, "Gu Yue", "Gu Yue clan", kind=MentionKind.ORGANIZATION),
                _m(1.0, 100, "Gu Yue Fang Yuan", "Fang Yuan"),
            ],
        )
        report = validate_gold(gold, "t")
        assert _finding(report, "colliding-keys").severity == "info"
        assert _finding(report, "positional-overlap").count == 1

    def test_a_true_duplicate_is_an_error(self) -> None:
        gold = GoldSet(
            "demo", [_m(1.0, 100, "Name A", "Person A"), _m(1.0, 100, "Name A", "Person B")]
        )
        finding = _finding(validate_gold(gold, "t"), "colliding-keys")
        assert finding.severity == "error"
        assert finding.count == 1


class TestImpossibleTargets:
    def test_a_negative_carrying_an_identity_is_an_error(self) -> None:
        """The real defect in reverend-insanity-hardcases.jsonl: ch3@7926
        'the Awakening Ceremony' is not_an_entity and carries an identity."""
        gold = GoldSet(
            "demo",
            [_m(3.0, 7926, "the Ceremony", "Something", kind=MentionKind.NOT_AN_ENTITY)],
        )
        assert _finding(validate_gold(gold, "t"), "impossible-targets").severity == "error"

    def test_an_entity_with_no_identity_is_an_error(self) -> None:
        gold = GoldSet("demo", [_m(1.0, 0, "Name A", "")])
        assert _finding(validate_gold(gold, "t"), "impossible-targets").severity == "error"


class TestProvenance:
    def test_circular_records_are_flagged(self) -> None:
        gold = GoldSet("demo", [_m(1.0, 0, "Name A", "Person A", drafted_by="gold-auto-builder")])
        finding = _finding(validate_gold(gold, "t"), "provenance")
        assert finding.severity == "warning"
        assert "circular=1" in finding.detail

    def test_silver_records_are_counted_separately(self) -> None:
        finding = _finding(
            validate_gold(GoldSet("demo", [_m(1.0, 0, "Name A", "Person A")]), "t"), "provenance"
        )
        assert "silver=1" in finding.detail
        assert "confirmed=0" in finding.detail


class TestSkippedChecksAreNotPasses:
    """A check that could not run must not look like one that passed -- the
    same conflation as EVOLUTION 4.74."""

    @pytest.mark.parametrize("check", ["malformed-spans", "missing-entities"])
    def test_store_dependent_checks_report_skipped(self, check: str) -> None:
        gold = GoldSet("demo", [_m(1.0, 0, "Name A", "Person A")])
        assert _finding(validate_gold(gold, "t", store=None), check).severity == "skipped"


class TestShippedCorpus:
    """Pins the real measurements, so a regression in the key or the tier
    definitions shows up as a test failure rather than as a changed number in a
    document nobody re-reads."""

    def test_hardcases_is_the_non_trivial_file(self) -> None:
        from pathlib import Path

        from echotales.pipeline.eval.gold import read_gold

        path = Path("data/gold/reverend-insanity-hardcases.jsonl")
        if not path.exists():
            pytest.skip("hardcases not present in this checkout")
        gold = read_gold(path, novel_id="reverend-insanity")
        finding = _finding(validate_gold(gold, str(path)), "surface-triviality")
        # 63.6% when measured 2026-09-24. Asserting the band, not the digit:
        # the point is that it sits well below the 99% failure line, which is
        # what makes it the only usable evaluation set in the corpus.
        assert finding.severity == "info"
        assert len({m.alias_type for m in gold.mentions}) >= 3

    def test_the_main_ri_file_is_surface_trivial(self) -> None:
        """Guards the finding itself. If this ever starts passing as
        non-trivial, somebody has changed the file, and the B-cubed number
        computed from it needs re-examining before it is quoted anywhere."""
        from pathlib import Path

        from echotales.pipeline.eval.gold import read_gold

        path = Path("data/gold/reverend-insanity.jsonl")
        if not path.exists():
            pytest.skip("gold not present in this checkout")
        gold = read_gold(path, novel_id="reverend-insanity")
        finding = _finding(validate_gold(gold.silver_only, str(path)), "surface-triviality")
        assert finding.severity == "error"
