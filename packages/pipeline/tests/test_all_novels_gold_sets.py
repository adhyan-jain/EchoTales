from pathlib import Path
from echotales.pipeline.eval.gold import read_gold


def test_gold_datasets_exist_and_load_for_all_three_novels():
    gold_dir = Path("data/gold")
    novels = ["reverend-insanity", "lord-of-the-mysteries", "omniscient-readers-viewpoint"]

    for novel_id in novels:
        file_path = gold_dir / f"{novel_id}.jsonl"
        assert file_path.exists(), f"Gold dataset missing for {novel_id}"

        gold_set = read_gold(file_path, novel_id=novel_id)
        assert len(gold_set) > 0, f"Gold dataset for {novel_id} is empty"

        confirmed_set = gold_set.confirmed_only
        assert len(confirmed_set) > 0, f"No confirmed gold annotations for {novel_id}"

        # Ensure partition map extracts non-empty identities
        partition = gold_set.partition()
        assert len(partition) > 0
