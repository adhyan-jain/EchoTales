"""Demonstratives before a full name are an idiom, not a class-noun signal.

On RI, "this Wang Er was rather intractable" and four more like it pushed Wang
Er's determiner rate to 12.5% (threshold 8%), so the commonness filter dropped
him from every chapter of the volume (EVOLUTION 4.90). Single-word role nouns
must still be caught: "this grandpa" is exactly the class use the filter
exists for.
"""

from __future__ import annotations

from echotales.pipeline.mentions.commonness import build_profile


def _corpus(name: str, demonstrative_hits: int, plain_hits: int) -> str:
    return " ".join(
        [f"this {name} was strong." for _ in range(demonstrative_hits)]
        + [f"{name} laughed." for _ in range(plain_hits)]
    )


def test_multiword_name_survives_demonstrative_idiom() -> None:
    profile = build_profile(_corpus("Wang Er", 5, 45), ["Wang Er"])
    assert not profile.is_common_noun("Wang Er")


def test_single_word_role_noun_is_still_caught_by_demonstratives() -> None:
    profile = build_profile(_corpus("Grandpa", 5, 45), ["Grandpa"])
    assert profile.is_common_noun("Grandpa")


def test_articles_still_count_for_multiword_surfaces() -> None:
    """Only demonstratives are dropped: "the clan elder" remains a class."""
    corpus = " ".join(["the Clan Elder spoke."] * 10 + ["Clan Elder nodded."] * 40)
    profile = build_profile(corpus, ["Clan Elder"])
    assert profile.is_common_noun("Clan Elder")
