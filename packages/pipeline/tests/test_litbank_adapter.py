"""The LitBank adapter must map conll clusters onto the .txt exactly.

Built against a synthetic document in the real formats: whitespace-tokenised
text, a conll file whose last column carries cluster brackets (including a
nested and a single-token mention), and an .ann with both kinds of T-line the
real corpus has -- typed ("PROP_PER") and cluster-name ("Anne-0"). The first
version of the parser let the cluster-name lines overwrite the types.
"""

from __future__ import annotations

from pathlib import Path

from echotales.pipeline.eval.litbank import parse_document, person_clusters, score

TEXT = "Anne met her sister .\nThe house stood .\n"
CONLL = "\n".join([
    "#begin document (d); part 0",
    "d\t0\t0\tAnne\t_\t_\t_\t_\t_\t_\t_\t_\t(0)",
    "d\t0\t1\tmet\t_\t_\t_\t_\t_\t_\t_\t_\t_",
    "d\t0\t2\ther\t_\t_\t_\t_\t_\t_\t_\t_\t(1|(0)",
    "d\t0\t3\tsister\t_\t_\t_\t_\t_\t_\t_\t_\t1)",
    "d\t0\t4\t.\t_\t_\t_\t_\t_\t_\t_\t_\t_",
    "",
    "d\t0\t0\tThe\t_\t_\t_\t_\t_\t_\t_\t_\t(2",
    "d\t0\t1\thouse\t_\t_\t_\t_\t_\t_\t_\t_\t2)",
    "d\t0\t2\tstood\t_\t_\t_\t_\t_\t_\t_\t_\t_",
    "d\t0\t3\t.\t_\t_\t_\t_\t_\t_\t_\t_\t_",
    "#end document",
]) + "\n"
ANN = "\n".join([
    "T1\tPROP_PER 0 4\tAnne",
    "T2\tAnne-0 0 4\tAnne",
    "T3\tPRON_PER 9 12\ther",
    "T4\tNOM_PER 9 19\ther sister",
    "T5\tNOM_FAC 22 31\tThe house",
]) + "\n"


def _write(tmp_path: Path) -> tuple[Path, Path, Path]:
    txt, conll, ann = tmp_path / "d_brat.txt", tmp_path / "d_brat.conll", tmp_path / "d_brat.ann"
    txt.write_text(TEXT)
    conll.write_text(CONLL)
    ann.write_text(ANN)
    return txt, conll, ann


def test_clusters_and_types_map_to_exact_offsets(tmp_path: Path) -> None:
    text, mentions = parse_document(*_write(tmp_path))
    spans = {(m.surface, m.cluster, m.mention_type, m.entity_type) for m in mentions}
    assert ("Anne", "0", "PROP", "PER") in spans  # typed line wins over "Anne-0"
    assert ("her", "0", "PRON", "PER") in spans
    assert ("her sister", "1", "NOM", "PER") in spans  # nested, opened on "her"
    assert ("The house", "2", "NOM", "FAC") in spans
    assert all(text[m.start:m.end] == m.surface for m in mentions)


def test_only_person_clusters_are_kept(tmp_path: Path) -> None:
    _text, mentions = parse_document(*_write(tmp_path))
    assert person_clusters(mentions) == {"0", "1"}


def test_gold_against_itself_scores_100(tmp_path: Path) -> None:
    _text, mentions = parse_document(*_write(tmp_path))
    people = person_clusters(mentions)
    docs = {"d": (mentions, [(m.start, m.end, m.cluster) for m in mentions if m.cluster in people])}
    result = score(docs, prop_only=False, key_restricted=False)
    assert result["CoNLL_F1"] == 100.0
    assert result["gold_mentions"] == 3


def test_spurious_system_mentions_cost_precision_only_in_standard_mode(tmp_path: Path) -> None:
    """A spurious mention merged into a real cluster costs B3 precision in
    standard mode. A spurious *singleton* does not: the house `b_cubed` scores
    an unmatched mention against itself, which EXTERNAL_BENCHMARK.md states as
    a difference from the CoNLL-2012 scorer. CEAF-e does count the extra entity."""
    _text, mentions = parse_document(*_write(tmp_path))
    merged = {"d": (mentions, [(0, 4, "a"), (9, 12, "a"), (13, 19, "a")])}  # "sister" is not a key mention
    assert score(merged, prop_only=False, key_restricted=True)["system_mentions"] == 2
    standard = score(merged, prop_only=False, key_restricted=False)
    assert standard["system_mentions"] == 3
    assert standard["B3_P"] < score(merged, prop_only=False, key_restricted=True)["B3_P"]

    singleton = {"d": (mentions, [(0, 4, "a"), (9, 12, "a"), (13, 19, "b")])}
    std = score(singleton, prop_only=False, key_restricted=False)
    restricted = score(singleton, prop_only=False, key_restricted=True)
    assert std["B3_P"] == restricted["B3_P"]
    assert std["CEAFe_P"] < restricted["CEAFe_P"]
