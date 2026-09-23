"""The invariant that 6,952 records violated, as code rather than a comment.

`eval/generate_gold.py:95-102` already said, in the function that wrote them,
that labels read out of the pipeline's own `mention` table "can only ever agree
with it" and must never be flipped to confirmed. It was a comment, so it was
flipped anyway and a B-cubed result was published from the outcome. These tests
exist so the next attempt fails at construction instead of at peer review.
"""

import json

import pytest
from echotales.pipeline.eval.gold import (
    CIRCULAR_DRAFTERS,
    CircularGoldError,
    GoldMention,
    GoldSet,
    Provenance,
    ReviewDepth,
    UnattributedConfirmationError,
    read_gold,
    write_gold,
)


def _mention(**kw) -> GoldMention:
    base = dict(novel_id="n", chapter=1.0, offset=0, surface="Fang Yuan", identity="Fang Yuan")
    return GoldMention(**{**base, **kw})


def test_circular_drafter_cannot_be_confirmed_even_by_a_named_human():
    """Confirmation is the wrong instrument: a human re-reading these records is
    checking whether the system agrees with the system."""
    with pytest.raises(CircularGoldError):
        _mention(
            drafted_by="gold-auto-builder",
            confirmed=True,
            confirmed_by="a-real-person",
            review_depth=ReviewDepth.PER_RECORD,
        )


def test_circular_drafter_is_fine_while_unconfirmed():
    m = _mention(drafted_by="gold-auto-builder", confirmed=False)
    assert m.drafted_by in CIRCULAR_DRAFTERS


def test_confirmation_must_name_a_reviewer():
    with pytest.raises(UnattributedConfirmationError):
        _mention(drafted_by="claude-opus-5", confirmed=True, review_depth=ReviewDepth.PER_RECORD)


def test_bulk_approval_does_not_make_a_record_gold():
    """The 2026-08-12 failure mode: a real person really did look, in aggregate,
    and that is not an adjudication."""
    with pytest.raises(UnattributedConfirmationError):
        _mention(
            drafted_by="claude-opus-5",
            confirmed=True,
            confirmed_by="adhyan-jain",
            review_depth=ReviewDepth.BULK,
        )


def test_a_genuine_per_record_confirmation_is_accepted():
    m = _mention(
        drafted_by="claude-opus-5",
        provenance=Provenance.HUMAN,
        confirmed=True,
        confirmed_by="adhyan-jain",
        review_depth=ReviewDepth.PER_RECORD,
    )
    assert m.confirmed and GoldSet("n", [m]).confirmed_only.mentions == [m]


def test_bulk_reviewed_records_are_excluded_from_confirmed_only():
    bulk = _mention(drafted_by="claude-opus-5", confirmed_by="adhyan-jain", review_depth=ReviewDepth.BULK)
    assert len(GoldSet("n", [bulk]).confirmed_only) == 0


def test_review_metadata_survives_a_write_read_round_trip(tmp_path):
    """Provenance that does not survive export is how a caveat gets lost: the
    bulk-approval note existed the whole time, in a field no scorer reads."""
    src = GoldSet("n", [_mention(drafted_by="claude-opus-5", confirmed_by="adhyan-jain", review_depth=ReviewDepth.BULK)])
    path = write_gold(src, tmp_path / "g.jsonl")
    back = read_gold(path).mentions[0]
    assert back.confirmed_by == "adhyan-jain"
    assert back.review_depth is ReviewDepth.BULK


def test_reading_a_falsified_file_raises_rather_than_scoring_it(tmp_path):
    """Exactly the shape of data/gold/_unusable/reverend-insanity-c1-c50.jsonl:
    machine-drafted, provenance rewritten to human, confirmed true."""
    bad = {
        "novel_id": "reverend-insanity", "chapter": 1.0, "offset": 1,
        "surface": "Fang Yuan", "identity": "Fang Yuan", "kind": "character",
        "alias_type": "RIGID_NAME", "context": "", "provenance": "human",
        "drafted_by": "gold-auto-builder", "confirmed": True,
        "note": "[golden_qa] Ground-truth mention for Fang Yuan.",
    }
    p = tmp_path / "falsified.jsonl"
    p.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(CircularGoldError):
        read_gold(p)


def test_legacy_records_without_the_new_fields_still_load(tmp_path):
    """Files predating `confirmed_by`/`review_depth` are unconfirmed drafts, and
    must keep loading as such rather than failing the whole corpus."""
    legacy = {
        "novel_id": "n", "chapter": 1.0, "offset": 0, "surface": "X",
        "identity": "X", "kind": "character", "alias_type": "RIGID_NAME",
        "context": "", "provenance": "model", "drafted_by": "claude-opus-5",
        "confirmed": False, "note": "",
    }
    p = tmp_path / "legacy.jsonl"
    p.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    m = read_gold(p).mentions[0]
    assert m.review_depth is ReviewDepth.NONE and m.confirmed_by == ""
