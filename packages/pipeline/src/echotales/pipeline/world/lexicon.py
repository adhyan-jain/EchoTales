"""What this novel's own words denote, derived from the graph.

**The failure this exists for.** RI's narration calls Fang Yuan a demon on
almost every page. The SDXL checkpoints read "demon" as a *species* and
returned a grinning red-eyed youth with fangs and a forehead gem; in this
novel it is a moral word for a human being. That was patched once by adding
`red eyes, fangs, horns` to the negatives -- a fix that works for the one
word somebody noticed, in the one novel somebody was watching, and does
nothing for the next such word or the next book.

The graph already holds the answer, and holds it for every word at once.
Resolution binds the mention "demon" to a `Self` whose `kind` is a person,
so the statement "in this world, a demon is a human being" is a query, not
an annotation someone has to write. `world/context.py` made the same
argument for facts about a *position*; this is the same argument for facts
about the novel's *vocabulary*.

Two consumers, both upstream of the image model where a fix is cheapest:
the director is told what the word means before it writes a shot, and the
negative prompt is told what the word must not summon.

**Position-filtered like everything else here.** A word whose referent is
only revealed in chapter 90 must not gloss that word in chapter 12, so the
scan is bounded by the chapter being rendered.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from echotales.core.enums import ReferenceMode, TargetKind
from echotales.core.store import Store

#: Common nouns that name a *kind of being* and that an image model will
#: draw literally. Only these are checked: the point is not to gloss the
#: whole novel, it is to catch words whose literal reading produces a
#: monster where the book has a person. A word not in this list has no
#: costume for the model to reach for.
CREATURE_WORDS: frozenset[str] = frozenset(
    {
        "demon", "devil", "monster", "beast", "fiend", "ghost", "spirit",
        "phantom", "zombie", "corpse", "immortal", "fairy", "dragon",
        "witch", "vampire", "angel", "god", "goddess", "giant", "ogre",
        "elf", "orc", "worm", "insect", "serpent", "wolf", "fox",
    }
)

#: The costume each word makes a checkpoint reach for. Emitted as negative
#: prompt terms when the word turns out to denote a person here.
_COSTUMES: dict[str, str] = {
    "demon": "demon horns, red eyes, fangs, demonic wings, monster",
    "devil": "devil horns, red skin, tail, pitchfork, monster",
    "monster": "monster, creature, non-human anatomy",
    "beast": "animal head, fur, claws, quadruped",
    "fiend": "monster, fangs, glowing eyes",
    "ghost": "transparent body, floating sheet, ectoplasm",
    "spirit": "transparent body, glowing wisp",
    "phantom": "transparent body, faceless figure",
    "zombie": "rotting flesh, exposed bone, undead",
    "corpse": "rotting flesh, skeleton",
    "immortal": "halo, glowing aura, angel wings",
    "fairy": "fairy wings, tiny person, antennae",
    "dragon": "dragon, scales, wings, reptilian head",
    "witch": "witch hat, broomstick, cauldron",
    "vampire": "fangs, bat wings, pale undead",
    "angel": "angel wings, halo",
    "god": "glowing deity, multiple arms, halo",
    "goddess": "glowing deity, halo",
    "giant": "gigantic body, towering over buildings",
    "ogre": "ogre, tusks, green skin",
    "elf": "pointed ears, elf",
    "orc": "orc, tusks, green skin",
    "worm": "giant worm, larva",
    "insect": "giant insect, antennae, compound eyes",
    "serpent": "giant snake, scales",
    "wolf": "wolf, muzzle, fur",
    "fox": "fox ears, tails, kemonomimi",
}

#: How often a word must resolve to a person before it counts as this
#: novel's usage rather than one mis-resolved mention. Two is enough to
#: separate a pattern from an accident without waiting for a whole arc.
_MIN_ATTESTATIONS = 3

#: Blocks either side of the epithet that may supply the person's name.
_PRESENCE_WINDOW = 3

#: Share of a word's uses that must be epithets before it is glossed.
#:
#: Calibrated against the whole of RI (199 chapters): demon 5/27 = 0.19 and
#: god 4/13 = 0.31 clear it, while worm 47/737 = 0.06, wolf 19/604 = 0.03
#: and beast 9/199 = 0.05 do not -- which is the right split, since that
#: novel contains real worms, real wolves and real beasts.
#:
#: **Without this the lexicon suppresses the novel's real content.** RI's
#: characters call each other beasts, wolves and monsters in anger, but the
#: book also contains actual beasts and actual wolves; glossing those words
#: would emit "animal head, fur, claws" as a negative and quietly make the
#: novel's real animals unrenderable. A word earns a gloss only when
#: name-calling is what it is mostly *for* -- "demon" in RI is used that
#: way constantly, "wolf" is not.
_MIN_EPITHET_SHARE = 0.15

_WORDS = "|".join(sorted(CREATURE_WORDS))

#: **The word has to be used *at* or *of* a person, not merely nearby.**
#: Proximity alone glosses far too much: RI describes Gu worms in blocks
#: where people are standing, and a "worm" gloss would then suppress the
#: insect imagery the novel is built on. Vocatives and epithets are the
#: constructions that actually assert "this creature word names this
#: person" -- "Fang Yuan you damn demon", "Wicked demon, what are you
#: laughing about?", "Demon, 300 years ago you insulted me".
#:
#: Lowercase only, deliberately: the novel capitalises proper names, so
#: this matches "the wicked demon" and never "Demon Suppression Tower".
#: Every lowercase use of a creature word, epithet or not -- the
#: denominator for `_MIN_EPITHET_SHARE`.
_ANY_USE_RE = re.compile(rf"(?<![\w'])({_WORDS})(?![\w'])")

_EPITHET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "you damn demon", "you demon"
    re.compile(rf"\byou\s+(?:\w+\s+){{0,2}}({_WORDS})(?![\w'])"),
    # A vocative opening a quoted line, with or without an insult attached.
    # "Wicked demon, ...", "Demon, ..." -- any 0-2 words may sit between
    # the quote mark and the epithet, since the insult attached to it is
    # arbitrary and often capitalised.
    re.compile(rf"[\"“]\s*(?:\w+\s+){{0,2}}({_WORDS})(?![\w'])\s*[,!?]"),
    # "this demon", "that demon" -- used of someone, not to them.
    re.compile(rf"\b(?:this|that)\s+(?:\w+\s+){{0,1}}({_WORDS})(?![\w'])"),
)


@dataclass(slots=True)
class WorldLexicon:
    """Novel-specific word senses, as of one position in the story."""

    novel_id: str
    #: creature word -> the person it names here, most-mentioned first.
    people_called: dict[str, list[str]] = field(default_factory=dict)

    def director_note(self) -> str:
        """One line for the director's prompt, or an empty string."""
        if not self.people_called:
            return ""
        parts = [
            f"'{word}' means {labels[0]}, a human being"
            for word, labels in sorted(self.people_called.items())
        ]
        return (
            "In this novel these words name people, not creatures: "
            + "; ".join(parts)
            + ". Draw them as human."
        )

    def negative_terms(self) -> str:
        """Costume terms to suppress, comma-joined, or an empty string."""
        seen: list[str] = []
        for word in sorted(self.people_called):
            for term in _COSTUMES.get(word, "").split(", "):
                if term and term not in seen:
                    seen.append(term)
        return ", ".join(seen)


def build_lexicon(
    store: Store,
    novel_id: str,
    *,
    through_chapter: float | None = None,
    min_attestations: int = _MIN_ATTESTATIONS,
) -> WorldLexicon:
    """Which creature words denote people in this novel, up to a position.

    **Not read from mentions, which was the obvious design and does not
    work.** Resolution only ever mints a mention for a name-like span, so
    RI's mention table knows "Bloodwing Demon Sect" and "Demon Suppression
    Tower" and has never once recorded the bare word "demon" -- the exact
    usage that produces the wrong picture. The evidence has to come from
    the prose.

    So: a lowercase creature word in a block where a person is present,
    counted across the story so far. Lowercase is doing real work -- it is
    what separates "the wicked demon" from "the Demon Suppression Tower",
    since the novel capitalises proper names and not epithets. Presence
    comes from the graph (`ReferenceMode.PRESENT`), so the claim being made
    is only ever "this word is used where a human being is standing".
    """
    lexicon = WorldLexicon(novel_id=novel_id)
    counts: dict[str, Counter[str]] = {}
    totals: Counter[str] = Counter()

    for chapter in store.chapter_numbers(novel_id):
        if through_chapter is not None and chapter > through_chapter:
            continue
        chapter_obj = store.get_chapter(novel_id, chapter)
        if chapter_obj is None:
            continue

        # Presence is checked over a small window rather than the exact
        # block: the epithet is usually inside a quoted line, and the name
        # that resolves the person sits in the narration a block or two
        # away. Measured on RI ch1, where every "demon" in the opening
        # siege is spoken and every "Fang Yuan" is narrated.
        present_by_block: dict[int, list[str]] = {}
        for mention in store.get_mentions(novel_id, chapter):
            if mention.reference_mode is not ReferenceMode.PRESENT:
                continue
            if mention.target_kind is not TargetKind.SELF or not mention.target_id:
                continue
            entity = store.get_self(mention.target_id)
            if entity is None or not entity.kind.is_person:
                continue
            present_by_block.setdefault(mention.block_index, []).append(
                entity.canonical_label
            )

        for block in chapter_obj.blocks:
            people = [
                label
                for offset in range(-_PRESENCE_WINDOW, _PRESENCE_WINDOW + 1)
                for label in present_by_block.get(block.index + offset, ())
            ]
            if not people:
                continue
            for word in _ANY_USE_RE.findall(block.text):
                totals[word] += 1
            for pattern in _EPITHET_PATTERNS:
                for word in pattern.findall(block.text):
                    counts.setdefault(word, Counter())[people[0]] += 1

    for word, labels in counts.items():
        hits = sum(labels.values())
        if hits < min_attestations:
            continue
        if hits / max(totals[word], hits) < _MIN_EPITHET_SHARE:
            continue
        lexicon.people_called[word] = [label for label, _ in labels.most_common()]
    return lexicon
