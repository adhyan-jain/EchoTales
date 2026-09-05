"""Tests for Phase 3 mention detection."""

from __future__ import annotations

from pathlib import Path

import pytest
from echotales.core.enums import AliasType, BlockType, ReferenceMode, ResolutionMethod
from echotales.core.models import Block, Chapter
from echotales.core.store import Store
from echotales.pipeline.mentions import (
    Gazetteer,
    HeuristicDetector,
    Lexicon,
    ParentheticalKind,
    classify_alias_type,
    classify_parenthetical,
    detect_mentions,
    find_parentheticals,
    load_lexicon,
    seed_from_lexicon,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LEXICON_DIR = REPO_ROOT / "data" / "lexicons"


@pytest.fixture
def xianxia() -> Lexicon:
    """A synthetic cultivation-genre lexicon.

    Built in-memory rather than loaded from disk: per-novel lexicons are now
    *induced from the text*, so their contents vary by run and by model. A test
    asserting on induced vocabulary would be asserting on a language model's
    output, which is not what these tests are for.
    """
    return Lexicon(
        id="test-xianxia",
        transferable_titles={"Sect Master", "Peak Lord", "Grand Elder"},
        era_locked_titles={"Immortal Venerable"},
        progressive_ranks={"Golden Core", "Nascent Soul", "Foundation Establishment"},
        relational_deictics={"Senior Brother", "Master", "Junior Sister"},
        generic_descriptors={"the innkeeper", "the guard", "the old man"},
        honorific_prefixes=("Elder", "Senior", "Young Master"),
        identity_declarations=("his true name was", "was none other than"),
    )


@pytest.fixture
def lotm() -> Lexicon:
    """A synthetic occult-genre lexicon exercising the pathway/tarot split."""
    return Lexicon(
        id="test-lotm",
        transferable_titles={"Captain", "Bishop"},
        pathway_titles={"Seer", "Clown", "Marionettist"},
        tarot_titles={"The Fool", "The Hanged Man", "Miss Justice"},
        progressive_ranks={"Sequence 9", "Sequence 8"},
        relational_deictics={"Mr.", "Miss", "Sir"},
        generic_descriptors={"the detective", "the landlady"},
    )


@pytest.fixture
def seed() -> Lexicon:
    """The genre-neutral seed that ships in the repo."""
    return load_lexicon(LEXICON_DIR / "_seed.toml")


# ---------------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------------


class TestLexicon:
    def test_transferable_titles_load(self, xianxia: Lexicon) -> None:
        assert "Sect Master" in xianxia.transferable_titles

    def test_titles_classify_as_transferable(self, xianxia: Lexicon) -> None:
        assert xianxia.alias_type_for("Sect Master") is AliasType.TRANSFERABLE_TITLE

    def test_deictics_classify_relative_to_speaker(self, xianxia: Lexicon) -> None:
        assert xianxia.alias_type_for("Senior Brother") is AliasType.RELATIONAL_DEICTIC

    def test_generic_descriptors_are_recognised_so_they_can_be_dropped(
        self, xianxia: Lexicon
    ) -> None:
        assert xianxia.alias_type_for("the innkeeper") is AliasType.GENERIC_DESCRIPTOR

    def test_pathway_and_tarot_titles_are_distinguished(self, lotm: Lexicon) -> None:
        assert lotm.alias_type_for("Seer") is AliasType.PATHWAY_TITLE
        assert lotm.alias_type_for("The Fool") is AliasType.TAROT_TITLE

    def test_unknown_surface_returns_none(self, xianxia: Lexicon) -> None:
        assert xianxia.alias_type_for("Zzzyx") is None

    def test_progressive_rank_is_detected(self, xianxia: Lexicon) -> None:
        """Rank drift is one person advancing, not a title changing hands."""
        assert xianxia.is_progressive_rank("Golden Core Elder Wang")

    def test_rank_stripping_makes_the_forms_comparable(self, xianxia: Lexicon) -> None:
        assert xianxia.strip_rank("Golden Core Elder Wang") == "Elder Wang"
        assert xianxia.strip_rank("Nascent Soul Elder Wang") == "Elder Wang"

    def test_learned_names_become_rigid(self, xianxia: Lexicon) -> None:
        xianxia.learn("Fang Yuan")
        assert xianxia.alias_type_for("Fang Yuan") is AliasType.RIGID_NAME

    def test_missing_file_yields_an_empty_lexicon(self) -> None:
        assert load_lexicon(LEXICON_DIR / "nope.toml").transferable_titles == set()


class TestGenreNeutralSeed:
    """The seed is the cold-start floor before induction has run.

    It must contain only English structural invariants -- no novel-specific
    vocabulary -- because anything it asserts lands at 0.95 confidence and
    outranks every heuristic.
    """

    def test_seed_loads(self, seed: Lexicon) -> None:
        assert seed.id == "_seed"

    def test_seed_blocks_generic_descriptors_on_a_cold_start(self, seed: Lexicon) -> None:
        assert seed.alias_type_for("the innkeeper") is AliasType.GENERIC_DESCRIPTOR

    def test_seed_supplies_declaration_phrases(self, seed: Lexicon) -> None:
        """Feeds the highest-weighted feature in the evidence vector."""
        assert "also known as" in seed.identity_declarations

    def test_seed_carries_no_novel_specific_vocabulary(self, seed: Lexicon) -> None:
        """Per-novel titles and ranks must come from induction, not from recall."""
        assert seed.transferable_titles == set()
        assert seed.progressive_ranks == set()
        assert seed.pathway_titles == set()
        assert seed.tarot_titles == set()


# ---------------------------------------------------------------------------
# Gazetteer -- the compounding mechanism
# ---------------------------------------------------------------------------


class TestGazetteer:
    def test_exact_match(self) -> None:
        g = Gazetteer()
        g.add("Fang Yuan", AliasType.RIGID_NAME, "s1")
        hits = g.find("Then Fang Yuan stepped forward.")
        assert [h.alias for h in hits] == ["Fang Yuan"]
        assert hits[0].target_id == "s1"

    def test_offsets_index_the_original_text(self) -> None:
        g = Gazetteer()
        g.add("Fang Yuan", AliasType.RIGID_NAME)
        text = "Then Fang Yuan stepped forward."
        hit = g.find(text)[0]
        assert text[hit.start : hit.end] == "Fang Yuan"

    def test_romanization_variants_match(self) -> None:
        """Matching is folded; offsets still point at the surface form."""
        g = Gazetteer()
        g.add("Fang Yuan", AliasType.RIGID_NAME)
        text = "Then FangYuan stepped forward."
        hits = g.find(text)
        assert hits and text[hits[0].start : hits[0].end] == "FangYuan"

    def test_no_match_inside_a_longer_word(self) -> None:
        """Folding removes spaces, so 'Li' would otherwise match in 'Lian'."""
        g = Gazetteer()
        g.add("Li", AliasType.RIGID_NAME)
        assert g.find("The lian flower bloomed.") == []

    def test_longest_match_wins(self) -> None:
        g = Gazetteer()
        g.add("Wang", AliasType.RIGID_NAME)
        g.add("Sect Master Wang", AliasType.TRANSFERABLE_TITLE)
        hits = g.find("Sect Master Wang arrived.")
        assert [h.alias for h in hits] == ["Sect Master Wang"]

    def test_generic_descriptors_are_refused(self) -> None:
        """Non-negotiable #4, enforced at the cheapest, highest-trust path."""
        g = Gazetteer()
        g.add("the innkeeper", AliasType.GENERIC_DESCRIPTOR)
        assert len(g) == 0

    def test_single_characters_are_refused(self) -> None:
        g = Gazetteer()
        g.add("A", AliasType.RIGID_NAME)
        assert len(g) == 0

    def test_adding_marks_the_automaton_stale(self) -> None:
        g = Gazetteer()
        g.build()
        g.add("Klein", AliasType.RIGID_NAME)
        assert g.is_stale

    def test_empty_gazetteer_finds_nothing(self) -> None:
        assert Gazetteer().find("Anything at all.") == []

    def test_seeding_from_lexicon(self, xianxia: Lexicon) -> None:
        """Titles must be recognised as titles from chapter one."""
        g = Gazetteer()
        seed_from_lexicon(g, xianxia)
        hits = g.find("The Sect Master nodded.")
        assert hits and hits[0].alias_type is AliasType.TRANSFERABLE_TITLE

    def test_seeding_excludes_generic_descriptors(self, xianxia: Lexicon) -> None:
        g = Gazetteer()
        seed_from_lexicon(g, xianxia)
        assert not any(
            h.alias_type is AliasType.GENERIC_DESCRIPTOR for h in g.find("The innkeeper spoke.")
        )

    def test_gazetteer_grows(self) -> None:
        """The compounding property, in miniature."""
        g = Gazetteer()
        before = len(g.find("Klein Moretti walked in."))
        g.add("Klein Moretti", AliasType.RIGID_NAME)
        assert before == 0
        assert len(g.find("Klein Moretti walked in.")) == 1


# ---------------------------------------------------------------------------
# Alias typing
# ---------------------------------------------------------------------------


class TestAliasTyping:
    def test_proper_name_is_rigid(self) -> None:
        assert classify_alias_type("Fang Yuan")[0] is AliasType.RIGID_NAME

    @pytest.mark.parametrize(
        "text", ["the innkeeper", "the guard", "that woman", "the old man", "the servant"]
    )
    def test_article_led_role_nouns_are_generic(self, text: str) -> None:
        assert classify_alias_type(text)[0] is AliasType.GENERIC_DESCRIPTOR

    def test_descriptive_article_led_names_are_epithets(self) -> None:
        """'the Ashen Duke' is an epithet; 'the innkeeper' is a descriptor."""
        assert classify_alias_type("the Crimson Emperor")[0] is AliasType.EPITHET

    def test_self_referential_deictics(self) -> None:
        assert classify_alias_type("this old man")[0] is AliasType.RELATIONAL_DEICTIC

    def test_lexicon_overrides_heuristics(self, xianxia: Lexicon) -> None:
        assert classify_alias_type("Sect Master", lexicon=xianxia)[0] is (
            AliasType.TRANSFERABLE_TITLE
        )

    def test_progressive_rank_reclassifies_the_remainder(self, xianxia: Lexicon) -> None:
        """Rank drift must not be mistaken for a transferable title."""
        alias_type, _ = classify_alias_type("Golden Core Elder Wang", lexicon=xianxia)
        assert alias_type is not AliasType.TRANSFERABLE_TITLE

    def test_direct_address_raises_the_deictic_prior(self) -> None:
        assert classify_alias_type("Master", is_address=True)[0] is (
            AliasType.RELATIONAL_DEICTIC
        )

    def test_generic_types_are_not_persistable(self) -> None:
        assert not AliasType.GENERIC_DESCRIPTOR.enters_graph

    @pytest.mark.parametrize(
        "text", ["the clan head", "the clan leader", "the sect leader", "the village head"]
    )
    def test_single_holder_offices_are_transferable_titles(self, text: str) -> None:
        """Section 5.1: HANDOFF's worked example -- the clan leader in RI ch1
        blocks 68-78 must not classify identically to "the innkeeper" just
        because neither remainder is capitalised."""
        assert classify_alias_type(text)[0] is AliasType.TRANSFERABLE_TITLE

    def test_bare_single_holder_office_with_no_article(self) -> None:
        assert classify_alias_type("clan head")[0] is AliasType.TRANSFERABLE_TITLE

    def test_ordinary_bystander_roles_stay_generic_even_if_similar_shape(self) -> None:
        """Not every article-led occupation is a title -- only curated,
        single-holder offices are (non-negotiable #4's bias toward calling
        something generic when it looks generic still applies elsewhere)."""
        assert classify_alias_type("the innkeeper")[0] is AliasType.GENERIC_DESCRIPTOR
        assert classify_alias_type("the merchant")[0] is AliasType.GENERIC_DESCRIPTOR
        assert AliasType.RIGID_NAME.enters_graph


# ---------------------------------------------------------------------------
# Parentheticals -- three readings, three consequences
# ---------------------------------------------------------------------------


class TestParentheticals:
    def test_romanization_variant_is_a_gloss(self) -> None:
        kind, conf, _ = classify_parenthetical("Wu Liao", "WuLiao")
        assert kind is ParentheticalKind.TRANSLATOR_GLOSS
        assert conf > 0.9

    def test_single_character_variant_is_a_gloss(self) -> None:
        """Translators differ by one letter far more often than two names collide."""
        kind, _, _ = classify_parenthetical("Shi Cheng", "Shi Chen")
        assert kind is ParentheticalKind.TRANSLATOR_GLOSS

    def test_two_character_difference_is_not_treated_as_a_variant(self) -> None:
        """The tolerance stops at one character, so distinct names stay distinct."""
        kind, _, _ = classify_parenthetical("Wu Liao", "Wu Liu")
        assert kind is not ParentheticalKind.TRANSLATOR_GLOSS

    def test_two_established_entities_is_simultaneous_action(self) -> None:
        """Merging them would destroy a character."""
        known = frozenset({"wuan", "wuliao"})
        kind, _, _ = classify_parenthetical(
            "Wu An", "Wu Liao", following_text=" nodded.", known_entities=known
        )
        assert kind is ParentheticalKind.SIMULTANEOUS_ACTION

    def test_unknown_inner_name_is_identity_disclosure(self) -> None:
        known = frozenset({"wuyihai"})
        kind, _, _ = classify_parenthetical(
            "Wu Yi Hai", "Fang Yuan", known_entities=known
        )
        assert kind is ParentheticalKind.IDENTITY_DISCLOSURE

    def test_shared_surname_argues_against_disclosure(self) -> None:
        """Same surname means relatives, not one person behind a disguise."""
        kind, _, _ = classify_parenthetical("Wu An", "Wu Bei", known_entities=frozenset())
        assert kind is not ParentheticalKind.IDENTITY_DISCLOSURE

    def test_insufficient_evidence_escalates(self) -> None:
        kind, conf, _ = classify_parenthetical("Alpha Beta", "Gamma Delta")
        assert kind is ParentheticalKind.AMBIGUOUS
        assert conf < 0.5

    def test_finding_in_text(self) -> None:
        found = find_parentheticals("Then Wu Yi Hai (Fang Yuan) smiled.")
        assert len(found) == 1
        assert found[0].outer == "Wu Yi Hai"
        assert found[0].inner == "Fang Yuan"

    def test_ordinary_parentheses_are_ignored(self) -> None:
        assert find_parentheticals("He paused (briefly) and continued.") == []


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class TestHeuristicDetector:
    def test_finds_multi_token_names(self) -> None:
        spans = HeuristicDetector().detect("Fang Yuan stepped forward.")
        assert "Fang Yuan" in {s.text for s in spans}

    def test_leading_stopword_is_trimmed_not_dropped(self) -> None:
        """'Then Fang Yuan' must yield 'Fang Yuan', not nothing."""
        spans = HeuristicDetector().detect("Then Fang Yuan stepped forward.")
        assert "Fang Yuan" in {s.text for s in spans}

    def test_bare_stopwords_are_not_names(self) -> None:
        spans = HeuristicDetector().detect("However, the matter was settled.")
        assert "However" not in {s.text for s in spans}

    def test_multi_token_spans_score_higher(self) -> None:
        spans = {s.text: s.score for s in HeuristicDetector().detect("Klein Moretti arrived.")}
        assert spans.get("Klein Moretti", 0) >= 0.8


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def chapter(*texts: str, number: float = 1.0) -> Chapter:
    return Chapter(
        novel_id="t",
        number=number,
        title="T",
        source_href="a.html",
        blocks=[Block(index=i, block_type=BlockType.PROSE, text=t) for i, t in enumerate(texts)],
    )


class TestRunner:
    @pytest.fixture
    def store(self) -> Store:
        s = Store(":memory:")
        s.add_novel("t", "T", "x.epub", "generic")
        return s

    def test_mentions_are_persisted(self, store: Store) -> None:
        store.add_chapter(chapter("Fang Yuan stepped forward.", "Wu An followed him."))
        store.conn.commit()
        report = detect_mentions("t", store)
        assert report.mentions > 0
        assert len(store.get_mentions("t")) == report.mentions

    def test_generic_descriptors_never_reach_the_store(
        self, store: Store, xianxia: Lexicon
    ) -> None:
        store.add_chapter(chapter("The innkeeper nodded at the guard."))
        store.conn.commit()
        detect_mentions("t", store, lexicon=xianxia)
        assert all(
            m.alias_type is not AliasType.GENERIC_DESCRIPTOR for m in store.get_mentions("t")
        )

    def test_gazetteer_hits_are_recorded_as_such(
        self, store: Store, xianxia: Lexicon
    ) -> None:
        store.add_chapter(chapter("The Sect Master nodded gravely at the assembly."))
        store.conn.commit()
        detect_mentions("t", store, lexicon=xianxia)
        methods = {m.method for m in store.get_mentions("t")}
        assert ResolutionMethod.GAZETTEER_EXACT in methods

    def test_dialogue_mentions_are_not_marked_present(self, store: Store) -> None:
        """Only PRESENT mentions get drawn; a name spoken aloud is not presence."""
        store.add_chapter(chapter('"Fang Yuan betrayed us," Wu An said.'))
        store.conn.commit()
        detect_mentions("t", store)
        modes = {m.text: m.reference_mode for m in store.get_mentions("t")}
        assert modes.get("Fang Yuan") is ReferenceMode.DIALOGUE_REFERENCE

    def test_narration_mentions_are_present(self, store: Store) -> None:
        store.add_chapter(chapter("Fang Yuan stepped forward and drew his blade."))
        store.conn.commit()
        detect_mentions("t", store)
        modes = {m.reference_mode for m in store.get_mentions("t")}
        assert ReferenceMode.PRESENT in modes

    def test_gazetteer_grows_across_chapters(self, store: Store) -> None:
        """The compounding mechanism, end to end."""
        for i in range(1, 6):
            store.add_chapter(chapter(f"Fang Yuan met Wu An in hall {i}.", number=float(i)))
        store.conn.commit()
        report = detect_mentions("t", store)
        assert report.gazetteer_size > 0
