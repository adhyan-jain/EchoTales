"""Whether a title distinguishes people depends on what the name is (owner, 2026-10-31).

After a surname, Mr., Mrs. and Miss name different members of a family; "Mr. Bennet", "Mrs. Bennet" and "Miss Bennet"
shared the key `bennet` and merged into one person (Pride and Prejudice: Mrs. Bennet voiced as Mr. Bennet). After a
first name or a codename the title is decoration: "Mr. Fool" and "Fool" are one person (Lord of the Mysteries). The
book itself says which: a token that carries two different titles is a family name.
"""

from __future__ import annotations

import pytest
from echotales.pipeline.ingest import normalize
from echotales.pipeline.ingest.normalize import comparison_key, derive_family_tokens


@pytest.fixture(autouse=True)
def _reset_family_tokens():
    normalize.set_family_tokens(frozenset())
    yield
    normalize.set_family_tokens(frozenset())


AUSTEN = ["Mr. Bennet", "Mrs. Bennet", "Miss Bennet", "Mr. Darcy", "Darcy", "Elizabeth", "Lady Lucas", "Miss Lucas"]
CODENAMES = ["Mr. Fool", "Fool", "Miss Justice", "Justice", "Mr. Azik"]


def test_a_surname_with_two_titles_is_a_family_name() -> None:
    tokens = derive_family_tokens(AUSTEN)  # in key form, as `comparison_key` compares them ("lucas" -> "luca")
    assert len(tokens) == 2 and "bennet" in tokens
    assert "darcy" not in tokens and "elizabeth" not in tokens


def test_codenames_and_single_titles_are_not() -> None:
    assert derive_family_tokens(CODENAMES) == frozenset()
    assert derive_family_tokens(["Mr. Darcy", "Darcy", "Mr. Bingley"]) == frozenset()


def test_titles_keep_family_members_apart() -> None:
    normalize.set_family_tokens(derive_family_tokens(AUSTEN))
    keys = {comparison_key(n) for n in ("Mr. Bennet", "Mrs. Bennet", "Miss Bennet")}
    assert len(keys) == 3
    assert comparison_key("Lady Lucas") != comparison_key("Miss Lucas")
    assert comparison_key("Mr. Bennet") == comparison_key("Mr Bennet") == comparison_key("Mr. Bennet's")


def test_a_title_on_a_single_person_name_still_meets_the_bare_name() -> None:
    normalize.set_family_tokens(derive_family_tokens(AUSTEN))
    assert comparison_key("Mr. Darcy") == comparison_key("Darcy")


def test_codenames_still_collapse() -> None:
    normalize.set_family_tokens(derive_family_tokens(CODENAMES))
    assert comparison_key("Mr. Fool") == comparison_key("Fool")
    assert comparison_key("Miss Justice") == comparison_key("Justice")


def test_without_family_tokens_behaviour_is_unchanged() -> None:
    assert comparison_key("Mr. Bennet") == comparison_key("Mrs. Bennet") == "bennet"
