from pathlib import Path
from echotales.pipeline.eval.gold import read_gold

# Only reverend-insanity has actually been through a human review pass
# (bulk-approved by the project owner -- see the note on its records in
# data/gold/reverend-insanity.jsonl). lord-of-the-mysteries and
# omniscient-readers-viewpoint are auto-extracted from the pipeline's own
# resolution output by generate_gold.py -- Provenance.MODEL, confirmed=False
# -- and must NOT be asserted as confirmed here until a real human pass
# happens. Asserting confirmed_only > 0 for them would silently mask the
# fact that no one has ever looked at these labels (see eval/gold.py's
# module docstring on why provenance has to survive every consumer).
NOVELS_WITH_CONFIRMED_GOLD = {"reverend-insanity"}
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
                f"{novel_id}'s gold set has confirmed records but has never had a human "
                "review pass -- generate_gold.py should be stamping these Provenance.MODEL/"
                "confirmed=False. If a real human confirmation pass happened, add the novel "
                "to NOVELS_WITH_CONFIRMED_GOLD."
            )
