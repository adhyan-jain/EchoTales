"""§4.15's LOTM transmigration case: identity continuity across a name *change*.

`detect_declaration`'s lexicon phrases run in the opposite temporal direction
(a new name revealing an old identity) and are flat substrings, so they cannot
express "memories *began* flooding him". This detector is structural instead.

Its precision rests on three guards, each of which has a test below because
each was added in response to a measured false positive on real text, not
defensively:

1. **Two different names, word-boundary matched.** A bare `in` test matches
   "a" inside "came".
2. **Proximity.** A name at the far end of the context window is elsewhere in
   the paragraph, not part of the claim.
3. **Memory ownership.** "his childhood memories came flooding back" is
   ordinary recollection; "memories began flooding him" is acquisition.
"""

from __future__ import annotations

from echotales.pipeline.resolve.evidence import detect_identity_continuity

#: The real sentence from LOTM chapter 1, verbatim from the ingested EPUB.
LOTM_CH1 = (
    "After taking a few deep breaths, Zhou Mingrui worked hard to stop panicking. "
    "At that moment, as his mind and body calmed down, memories began flooding him "
    "as they slowly appeared in his mind! Klein Moretti, a citizen of the Northern "
    "Continent's Loen Kingdom, Awwa County, City of Tingen."
)


class TestFires:
    def test_the_real_lotm_transmigration_sentence(self) -> None:
        score, why = detect_identity_continuity(LOTM_CH1, "Klein Moretti", "Zhou Mingrui")
        assert score == 1.0
        assert "memories" in why

    def test_name_possessive_is_not_treated_as_ownership(self) -> None:
        """"Klein Moretti's memories began flooding him" is the transmigration
        shape stated more explicitly, not a counterexample to it."""
        text = "Zhou Mingrui froze. Klein Moretti's memories began flooding him."
        assert detect_identity_continuity(text, "Klein Moretti", "Zhou Mingrui")[0] == 1.0

    def test_transitive_transmigration_verb(self) -> None:
        text = "Zhou Mingrui had transmigrated into Klein Moretti."
        assert detect_identity_continuity(text, "Klein Moretti", "Zhou Mingrui")[0] == 1.0


class TestDoesNotFire:
    def test_bare_transmigration_noun_is_topic_vocabulary(self) -> None:
        """Measured on LOTM, whose *premise* is transmigration: the bare noun
        appears throughout as ordinary narration and merged a country and a
        faction into the protagonist. A word that is the subject matter of the
        book cannot also be a discriminator within it."""
        text = "Zhou Mingrui pondered his transmigration. The Loen Kingdom was vast."
        assert detect_identity_continuity(text, "Loen Kingdom", "Zhou Mingrui")[0] == 0.0

    def test_already_owned_memories_are_ordinary_recollection(self) -> None:
        text = "Fang Yuan told Fang Zheng his childhood memories came flooding back."
        assert detect_identity_continuity(text, "Fang Yuan", "Fang Zheng")[0] == 0.0

    def test_names_too_far_from_the_phrase(self) -> None:
        text = (
            "Klein Moretti went to town. " + "x" * 300
            + " memories began flooding him. " + "y" * 300
            + " Zhou Mingrui slept."
        )
        assert detect_identity_continuity(text, "Klein Moretti", "Zhou Mingrui")[0] == 0.0

    def test_short_surface_does_not_match_inside_a_word(self) -> None:
        """"a" is present in "came" and "b" in "back" -- a plain `in` test
        would satisfy the two-name guard on prose containing neither name."""
        text = "His childhood memories came flooding back to him."
        assert detect_identity_continuity(text, "A", "B")[0] == 0.0

    def test_one_name_alone_asserts_nothing(self) -> None:
        assert detect_identity_continuity(LOTM_CH1, "Klein Moretti", "Audrey Hall")[0] == 0.0

    def test_a_name_against_itself_is_repetition_not_continuity(self) -> None:
        assert detect_identity_continuity(LOTM_CH1, "Klein Moretti", "Klein Moretti")[0] == 0.0

    def test_two_names_without_any_continuity_phrase(self) -> None:
        text = "Zhou Mingrui met Klein Moretti for tea."
        assert detect_identity_continuity(text, "Klein Moretti", "Zhou Mingrui")[0] == 0.0
