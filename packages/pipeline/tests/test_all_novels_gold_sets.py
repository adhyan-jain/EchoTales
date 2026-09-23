from pathlib import Path

from echotales.pipeline.eval.gold import CIRCULAR_DRAFTERS, ReviewDepth, read_gold

# No novel has confirmed gold. This used to say reverend-insanity did, on the
# strength of a 2026-08-12 bulk approval, and that claim is what let a B-cubed
# number (P=100.0%, R=94.6%, F1=97.2%) be reported from labels the pipeline had
# drafted for itself -- see EVOLUTION.md 4.74 and data/gold/_unusable/README.md.
# The set is empty now because it was always empty; only the flag said otherwise.
#
# When a real per-record pass lands, add the novel here and the test starts
# demanding coverage instead of asserting its absence.
NOVELS_WITH_CONFIRMED_GOLD: set[str] = set()
ALL_NOVELS = ["reverend-insanity", "lord-of-the-mysteries", "omniscient-readers-viewpoint"]


def test_gold_datasets_exist_and_load_for_all_three_novels():
    gold_dir = Path("data/gold")

    for novel_id in ALL_NOVELS:
        file_path = gold_dir / f"{novel_id}.jsonl"
        assert file_path.exists(), f"Gold dataset missing for {novel_id}"

        gold_set = read_gold(file_path, novel_id=novel_id)
        assert len(gold_set) > 0, f"Gold dataset for {novel_id} is empty"

        # Ensure partition map extracts non-empty identities
        partition = gold_set.partition()
        assert len(partition) > 0


def test_confirmed_gold_only_exists_where_a_human_pass_actually_happened():
    gold_dir = Path("data/gold")

    for novel_id in ALL_NOVELS:
        gold_set = read_gold(gold_dir / f"{novel_id}.jsonl", novel_id=novel_id)
        confirmed_set = gold_set.confirmed_only

        if novel_id in NOVELS_WITH_CONFIRMED_GOLD:
            assert len(confirmed_set) > 0, f"No confirmed gold annotations for {novel_id}"
        else:
            assert len(confirmed_set) == 0, (
                f"{novel_id}'s gold set has confirmed records but has never had a "
                "per-record human review pass. If one genuinely happened, add the novel "
                "to NOVELS_WITH_CONFIRMED_GOLD -- do not flip the flag on the records."
            )


def test_no_shipped_gold_record_is_both_circular_and_confirmed():
    """The invariant the 6,952-record incident violated, asserted on real files.

    `gold.py` raises on construction, so a violating file cannot even be read --
    this test exists so the failure names the corpus rather than surfacing as an
    exception from whichever eval path happened to touch it first.
    """
    for path in sorted(Path("data/gold").glob("*.jsonl")):
        for mention in read_gold(path):
            if mention.drafted_by in CIRCULAR_DRAFTERS:
                assert not mention.confirmed, (
                    f"{path.name} ch{mention.chapter:g}@{mention.offset} is drafted from "
                    "the pipeline's own output and marked confirmed -- that scores the "
                    "system against itself."
                )
            if mention.confirmed:
                assert mention.confirmed_by, f"{path.name}: confirmation names no reviewer"
                assert mention.review_depth is ReviewDepth.PER_RECORD


def test_quarantined_corpus_is_not_reachable_from_the_gold_directory():
    """`data/gold/_unusable/` must stay out of every `data/gold/*.jsonl` glob.

    Every eval path globs the flat directory; the quarantine works only because
    it is a subdirectory. A file moved back up is a silent regression.
    """
    quarantine = Path("data/gold/_unusable")
    if not quarantine.exists():
        return
    assert (quarantine / "README.md").exists(), "quarantine must explain itself"
    flat = {p.name for p in Path("data/gold").glob("*.jsonl")}
    assert not (flat & {p.name for p in quarantine.glob("*.jsonl")})
