"""Appearance extraction: what a character actually looks like.

Until this stage existed, nothing in the pipeline ever read a character's
*appearance* out of the text. `persona/build.py` writes demographics and Big
Five -- everything voice casting needs -- but image generation needs hair,
eyes, build, attire and insignia, and none of that was extracted anywhere.
Every character was a blank to the visual pipeline (HANDOFF §4.23's first
listed gap).

**Evidence is narration where the character is physically present.** Only
`ReferenceMode.PRESENT` mentions count: a character described in someone
else's dialogue, or recalled in a memory, is not being looked at, and
scraping those passages is how a disguise or a rumour ends up baked into a
reference sheet. This is the same filter `spans/scene.py` applies for panel
casting, applied to a different question.

**One call per entity, above a prominence floor -- never per mention.** The
§3 budget rule again: ~80 entities against ~9,500 mentions in a 199-chapter
novel, and appearance is a property of the character, not of each sighting.

**Accumulated, never overwritten.** A novel describes a character across
scattered sentences over dozens of chapters -- hair in chapter 2, a scar in
chapter 40. Re-running on more chapters *adds* attestations rather than
replacing them, so a profile grows monotonically as evidence arrives. A key
whose value is already recorded is not written twice; a genuinely new value
lands as an additional `Attribute` row, which is exactly what the temporal
fact model is for (`architecture.md §3`).

Everything written here is `truth_status=INFERRED` /
`asserted_by=INFERENCE`: it is a model's reading of the prose, not the
prose's own assertion, and any explicit textual declaration outranks it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from echotales.core.enums import (
    OBSERVER_READER,
    AssertedBy,
    Prominence,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition
from echotales.core.store import Store
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

#: The controlled vocabulary. An answer outside these keys is discarded --
#: same hallucination discipline as `persona/extract.py`, because a silently
#: accepted invented key would flow straight into a generation prompt.
APPEARANCE_KEYS = (
    "hair_color",
    "hair_style",
    "eye_color",
    "skin_tone",
    "height_build",
    "distinguishing_features",
    "typical_attire",
    "rank_insignia",
    "current_condition",
)

#: Keys describing a character's **standing identity** -- what makes them
#: recognisable as themselves in any scene. These, and only these, build the
#: reference sheet that conditions every panel
#: (`persona/reference_gen.py`).
STANDING_KEYS = (
    "hair_color",
    "hair_style",
    "eye_color",
    "skin_tone",
    "height_build",
    "distinguishing_features",
    "typical_attire",
    "rank_insignia",
)

#: Keys describing a **moment**, not a person.
#:
#: This split is what keeps a character consistent across chapters. Measured
#: on RI: Fang Yuan's chapter 1 is his death scene, and an unsplit
#: extraction returned `typical_attire="deep green robes that had been torn
#: to shreds"` and `distinguishing_features="disheveled hair, covered in
#: blood"`. Baking that into his reference sheet would have drawn him
#: bloodied and in rags for all 199 chapters -- the exact failure this
#: pipeline exists to avoid. The garment is `green robes`; the shredding is
#: a condition, and conditions belong to the scene that caused them.
TRANSIENT_KEYS = ("current_condition",)

#: Narration only. Dialogue is what characters *say*, and a character's own
#: account of how someone looks is a claim, not an observation.
_DESCRIPTIVE = (SpanType.NARRATION_DESCRIPTION, SpanType.NARRATION_ACTION)

#: Below this, an entity gets no call at all. An incidental walk-on has
#: almost no descriptive evidence and is not drawn with a reference sheet
#: anyway (`persona/reference_gen.py` skips them by the same rule).
_ELIGIBLE = (Prominence.PRINCIPAL, Prominence.RECURRING)


def eligible_prominence(store: Store, novel_id: str, entity: object) -> Prominence:
    """This entity's prominence, derived from mention count rather than read
    off the stored column.

    `Self.prominence` is written by `persona/build.py`, but every database
    built before that write landed still carries the `INCIDENTAL` default
    for its entire cast -- measured on `data/reruns/reverend-insanity.db`,
    where all 120 entities read `INCIDENTAL` including Fang Yuan at 5,191
    mentions. Trusting the column there would make this stage silently
    process nothing, which is the worst possible failure for a stage whose
    output is invisible until a panel renders wrong. Deriving it costs one
    indexed COUNT per entity and is correct regardless of what has or has
    not been re-run.
    """
    from echotales.pipeline.persona.build import PRINCIPAL_FLOOR, RECURRING_FLOOR

    count = store.mention_count_for(novel_id, entity.id)  # type: ignore[attr-defined]
    if count >= PRINCIPAL_FLOOR:
        return Prominence.PRINCIPAL
    if count >= RECURRING_FLOOR:
        return Prominence.RECURRING
    return Prominence.INCIDENTAL

#: Passage sampling bounds. Enough prose to characterise a face without
#: turning a per-entity call into a per-chapter one. Raised from 40 once
#: sampling was spread across the volume rather than front-loaded: with an
#: even stride there is more *distinct* description to be had, and a
#: character's look is usually stated in a handful of sentences scattered
#: over their whole arc.
_MAX_PASSAGES = 60
_MAX_PASSAGE_CHARS = 400

SYSTEM = (
    "You extract physical appearance from a translated web novel. Report only "
    "what the passages state or directly imply about how the character looks. "
    "Never invent a detail that is not there -- omit the key instead. "
    "The passages describe several people; report only the named subject, "
    "never anyone standing near them. Return only JSON."
)


class AppearanceResponse(BaseModel):
    """Every field optional: a novel that never states eye colour must
    produce no eye colour, not a plausible guess."""

    hair_color: str = ""
    hair_style: str = ""
    eye_color: str = ""
    skin_tone: str = ""
    height_build: str = ""
    distinguishing_features: list[str] = Field(default_factory=list)
    typical_attire: str = ""
    rank_insignia: str = ""
    current_condition: str = ""


@dataclass(slots=True)
class AppearanceReport:
    novel_id: str
    entities_considered: int = 0
    entities_called: int = 0
    attributes_written: int = 0
    attributes_already_known: int = 0
    skipped_no_evidence: int = 0
    skipped_not_prominent: int = 0
    failures: int = 0
    by_entity: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        top = sorted(self.by_entity.items(), key=lambda kv: -kv[1])[:6]
        listed = ", ".join(f"{k}={v}" for k, v in top) or "none"
        return (
            f"{self.novel_id}: {self.attributes_written:,} appearance attributes "
            f"from {self.entities_called} model calls\n"
            f"  considered {self.entities_considered} entities; "
            f"skipped {self.skipped_not_prominent} not prominent, "
            f"{self.skipped_no_evidence} with no descriptive evidence\n"
            f"  already known (not rewritten): {self.attributes_already_known}; "
            f"failed calls: {self.failures}\n"
            f"  most described: {listed}"
        )


#: Words that mark a sentence as *about how someone looks*. Used to find
#: descriptive passages across the whole novel rather than hoping they fall
#: on a sampling grid.
_APPEARANCE_CUES = (
    "hair", "eyes", "eye", "gaze", "stare", "face", "features", "skin",
    "complexion", "robe", "robes", "clothes", "clothing", "dressed", "wore",
    "wearing", "attire", "sleeve", "tall", "short", "thin", "lean", "slender",
    "stout", "build", "figure", "handsome", "beautiful", "ugly", "plain",
    "scar", "beard", "brow", "pale",
)


#: Attribute words that make a cue noun an actual *description* rather than a
#: passing mention. "his emotionless face" and "under the gazes of the masses"
#: both contain a cue noun from `_APPEARANCE_CUES` and describe nothing --
#: measured on RI, 56 of 60 gathered passages for Fang Yuan's second body
#: scored zero here, which is why that body extracted no appearance at all
#: despite 196 chapters of evidence being in range.
_DESCRIPTORS = (
    "black", "white", "red", "green", "blue", "golden", "gold", "silver",
    "grey", "gray", "brown", "purple", "jade", "crimson", "pale", "dark",
    "fair", "blond", "azure",
    # Real RI text: "bearing a sickly yellow skin" (ch87 b40) scored zero
    # without these -- a verified miss, not speculative vocabulary growth.
    "yellow", "yellowish", "sickly", "sallow", "ruddy", "ashen", "swarthy", "tall", "short", "thin", "slender", "lean",
    "stout", "sturdy", "thick", "slim", "broad", "narrow", "petite", "burly",
    "long", "straight", "curly", "messy", "dishevelled", "disheveled",
    "smooth", "sharp", "deep", "bright", "handsome", "beautiful", "ugly",
    "plain", "delicate", "gaunt", "hollow", "wrinkled", "youthful", "aged",
    "scarred", "muscular", "frail", "bony", "rosy", "tanned", "silky",
)

#: Cue nouns that can be described. Narrower than `_APPEARANCE_CUES` (which
#: is a recall-first *retrieval* filter): this set is used for precision
#: *ranking*, so verbs-in-noun-clothing ("build" as in "build up") are
#: excluded -- that exact string produced a false positive on real text
#: ("had long build up deep steel-like determination").
_DESC_NOUNS = (
    "hair", "eyes", "eye", "face", "features", "skin", "complexion",
    "robe", "robes", "clothes", "clothing", "attire", "sleeve", "sleeves",
    "figure", "brow", "brows", "beard", "scar", "nose", "lips", "cheeks",
    "chin", "forehead", "physique", "stature",
    # Whole-person nouns: a description frequently attaches to the person
    # rather than a part -- "The youth was thin, slightly shorter than Fang
    # Yuan" (RI ch2, real text) is exactly the sentence this stage exists to
    # find, and a parts-only noun list scored it zero.
    "youth", "man", "woman", "boy", "girl", "child", "elder", "figure",
    # "The leading person was neither short nor tall" (RI ch87 b40).
    "person",
)

_D = "|".join(_DESCRIPTORS)
_N = "|".join(_DESC_NOUNS)

#: "long black hair", "deep red robes" -- attribute before the noun. A
#: determiner/possessive is required so a verb reading cannot match.
_DESC_PRE = re.compile(
    rf"\b(?:his|her|their|its|the|a|an|with|in|had|has)\b[\w\s,\-]{{0,20}}?"
    rf"\b(?:{_D})\b[\w\s,\-]{{0,15}}?\b(?:{_N})\b",
    re.IGNORECASE,
)
#: "his face was pale", "eyes were sharp", "his face had become deathly pale"
#: -- attribute after a copula. `had become`/`turned` are load-bearing: RI's
#: real ch1 line is "his face had become deathly pale", which a `was|were`-only
#: copula list scored zero.
_DESC_POST = re.compile(
    rf"\b(?:{_N})\b\s+(?:was|were|is|are|looked|seemed|appeared|"
    rf"had\s+become|has\s+become|became|become|turned|grew)\s+"
    rf"[\w\s]{{0,12}}?\b(?:{_D})\b",
    re.IGNORECASE,
)
#: Possession/attire verbs: "wore green robes", "was in deep green robes".
_DESC_HAS = re.compile(
    rf"\b(?:wore|wearing|dressed\s+in|clad\s+in|was\s+in|were\s+in)\b"
    rf"[\w\s,\-]{{0,20}}?\b(?:{_N})\b",
    re.IGNORECASE,
)


def descriptive_score(text: str) -> int:
    """How strongly this passage *describes a body*, not merely mentions one.

    `find_descriptive_blocks` is deliberately recall-first: a bare cue word
    anywhere in the block admits it. That is right for retrieval and wrong
    for ranking, and nothing downstream re-ranked, so a model asking "what
    does this character look like" was handed 60 passages of which 56 said
    nothing about anyone's appearance. Higher is more descriptive; 0 means
    "mentions a body part, describes nothing".
    """
    return (
        len(_DESC_PRE.findall(text)) * 2
        + len(_DESC_POST.findall(text)) * 2
        + len(_DESC_HAS.findall(text))
    )


def describes_target(text: str, surfaces: set[str]) -> bool:
    """Whether the described body plausibly belongs to this entity.

    **Block-level co-presence is not attribution.** `find_descriptive_blocks`
    admits any block where the target is PRESENT, so a block in which Fang
    Yuan watches someone else being described admits *that* person's
    appearance as evidence for Fang Yuan -- measured on real RI text, his
    highest-scoring passages described "a man with a yellowish skin tone...
    huge body size and developed muscles", who is not him. Requiring the
    description to sit in a possessive/naming construction tied to the
    target is a cheap, text-verified guard against that.
    """
    lowered = text.casefold()
    for surface in surfaces:
        for pattern in (f"{surface}'s", f"{surface}\u2019s", surface):
            idx = lowered.find(pattern)
            while idx != -1:
                window = lowered[idx : idx + len(pattern) + 90]
                if _DESC_PRE.search(window) or _DESC_POST.search(window) or _DESC_HAS.search(window):
                    return True
                idx = lowered.find(pattern, idx + 1)
    return False


def find_descriptive_blocks(
    store: Store, novel_id: str, target_id: str
) -> list[tuple[float, int]]:
    """`(chapter, block_index)` for every block that both contains this
    entity as PRESENT *and* reads like a physical description.

    **This replaced uniform chapter sampling, which was losing the
    descriptions it existed to find.** Striding evenly across a character's
    197 chapters samples 40 of them -- 20% coverage -- and appearance
    sentences are rare and concentrated rather than evenly spread, so the
    stride missed them by construction. Measured on RI: Fang Yuan's
    canonical "his eyes dark like the abyss" is chapter 33, in a
    `NARRATION_DESCRIPTION` block where he is `PRESENT` -- every upstream
    stage had done its job, and the sampler simply never looked at chapter
    33, because the grid went 30, 35.

    A `LIKE` scan over the entity's own blocks is both cheaper than the
    per-chapter span loads it replaces and complete over the volume, which
    is the point of pre-processing the volume in the first place.
    """
    cue_sql = " OR ".join("LOWER(s.text) LIKE ?" for _ in _APPEARANCE_CUES)
    params: list[object] = [novel_id, target_id, ReferenceMode.PRESENT.value]
    params += [f"%{c}%" for c in _APPEARANCE_CUES]

    rows = store.conn.execute(
        "SELECT DISTINCT s.chapter, s.block_index FROM span s "
        "JOIN mention m ON m.novel_id = s.novel_id AND m.chapter = s.chapter "
        "  AND m.block_index = s.block_index "
        "WHERE s.novel_id = ? AND m.target_id = ? AND m.reference_mode = ? "
        f"AND s.span_type IN ('NARRATION_DESCRIPTION','NARRATION_ACTION') "
        f"AND ({cue_sql}) "
        "ORDER BY s.chapter, s.block_index",
        params,
    ).fetchall()
    return [(float(r["chapter"]), int(r["block_index"])) for r in rows]


#: A *reveal*: an unnamed figure is described, then named. RI ch87 b40 is the
#: verified case this is built from -- "The leading person was neither short
#: nor tall, bearing a sickly yellow skin -- it was Gu Yue Jiao San." The
#: description attaches to no resolved mention of Jiao San, so
#: `find_descriptive_blocks`'s `m.target_id` join never sees it and the only
#: physical description that character gets in the volume is invisible to
#: appearance extraction.
#:
#: **The possessive exclusion is load-bearing.** Without it this matches
#: "it was Fang Yuan's life elementary force" and "this was Gu Yue Chi Lian's
#: grandson", which name a *different* referent -- measured on the real
#: volume, possessives outnumbered true reveals roughly 2:1 in an early
#: version of this pattern.
_REVEAL = re.compile(
    r"\b(?:it|this|that|he|she|they)\s+(?:was|were|is|are)\s+"
    r"(?:none\s+other\s+than\s+)?"
    r"(?P<name>[A-Z][\w’']*(?:\s+[A-Z][\w’']*){0,3})"
    r"(?![’']s)\b",
    re.UNICODE,
)


def find_reveal_blocks(
    store: Store, novel_id: str, target_id: str
) -> list[tuple[float, int]]:
    """Blocks that describe someone and *then* name them as this entity.

    Complements `find_descriptive_blocks`, which requires a resolved mention
    of the target in the block. A delayed-identity reveal has no such
    mention by construction: the describing sentences refer to "a young man"
    or "the leading person", and only the closing clause names them. Those
    blocks carry some of the only physical description a character gets, and
    were silently unreachable.

    Kept to the *same block* as the reveal deliberately. Walking back over
    preceding blocks would catch the two-paragraph form too, but it also
    invents attributions whenever the reveal follows unrelated narration,
    and there is no way to tell those apart without the coreference the
    resolver does not yet do (`EVOLUTION.md`'s open declaration-pre-filter
    defect is the same missing mechanism).
    """
    surfaces = {s for s in _surface_forms(store, novel_id, target_id) if " " in s or len(s) > 3}
    if not surfaces:
        return []

    out: list[tuple[float, int]] = []
    seen: set[tuple[float, int]] = set()
    for row in store.conn.execute(
        "SELECT chapter, block_index, text FROM span"
        " WHERE novel_id = ? AND span_type IN ('NARRATION_DESCRIPTION','NARRATION_ACTION')",
        (novel_id,),
    ):
        text = str(row["text"])
        for match in _REVEAL.finditer(text):
            revealed = match.group("name").casefold()
            # **Match on the name's tail, not the whole string.** This corpus
            # names people with a clan prefix at first mention and without it
            # thereafter -- the reveal reads "it was Gu Yue Jiao San" while
            # every resolved mention of him is the bare "Jiao San", so an
            # equality test found nothing at all. Same clan-prefix gap the
            # open `variants.py` defect describes, handled locally here
            # rather than left to block this stage.
            if not any(
                revealed == sf or revealed.endswith(" " + sf) for sf in surfaces
            ):
                continue
            # The block has to actually describe a body, or this is just a
            # naming sentence with no appearance in it.
            if not descriptive_score(text):
                continue
            key = (float(row["chapter"]), int(row["block_index"]))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return sorted(out)


def gather_appearance_evidence(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    max_chapters: int = 40,
    max_passages: int = _MAX_PASSAGES,
    allowed_chapters: set[float] | None = None,
) -> list[tuple[float, str]]:
    """`(chapter, passage)` pairs -- the same evidence, with its provenance.

    **The chapter is load-bearing, not decoration.** An appearance is not a
    timeless property: Fang Yuan is a 500-year-old man in chapter 1 and a
    fifteen-year-old from chapter 2 onward, and the novel reveals facts
    about each body at different points. An attribute recorded without the
    chapter it came from cannot answer `state_of(..., position)` at all --
    it can only assert one flat appearance for the whole novel, which for a
    regressor is wrong for most of the book.
    """
    pairs: list[tuple[float, str]] = []
    for chapter, text in _gather_pairs(
        store,
        novel_id,
        target_id,
        max_chapters=max_chapters,
        max_passages=max_passages,
        allowed_chapters=allowed_chapters,
    ):
        pairs.append((chapter, text))
    return pairs


def gather_appearance_passages(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    max_chapters: int = 40,
    max_passages: int = _MAX_PASSAGES,
    allowed_chapters: set[float] | None = None,
) -> list[str]:
    """Narration blocks where this entity is physically present.

    Sampled across chapters the entity actually appears in (see
    `Store.chapters_for_target` on why the novel's first N would be wrong),
    and restricted to blocks carrying a `PRESENT` mention of them -- see the
    module docstring on why reference mode is load-bearing here.

    `allowed_chapters` scopes the evidence to an explicit chapter set; the
    `max_chapters` sample bound is then redundant and is not applied, since
    the caller has already said exactly which chapters count.

    **Passages that name the entity are preferred over the rest of their
    block.** Evidence is gathered per *block*, and a block routinely
    describes several people, so an unranked sample invites the model to
    attribute a neighbour's description to this character -- measured on RI
    ch1-5, where an unranked Fang Yuan sample produced
    `height_build="thin, slightly shorter than Fang Yuan"`, which is
    self-evidently about someone else. Naming passages therefore fill the
    budget first, and unnamed same-block passages only backfill what is
    left; they are still worth keeping, because the sentence carrying the
    appearance is frequently the pronoun sentence right after the naming
    one ("Fang Yuan was in deep green robes... His hair was disheveled").
    """
    seen: set[str] = set()
    surfaces = _surface_forms(store, novel_id, target_id)

    chapters = [
        c
        for c in store.chapters_for_target(novel_id, target_id)
        if allowed_chapters is None or c in allowed_chapters
    ]
    if not chapters:
        return []

    # Sample **evenly across the character's whole run**, not the first N
    # chapters they appear in. The full volume is pre-processed precisely so
    # appearance can be read from everywhere a character is described, and
    # `LIMIT`-ing to the earliest chapters threw that away: it profiled Fang
    # Yuan entirely from chapter 1, the scene he dies in. An even stride
    # keeps the cost bounded while covering the arc.
    if len(chapters) > max_chapters:
        stride = len(chapters) / max_chapters
        chapters = [chapters[int(i * stride)] for i in range(max_chapters)]

    # Spread the budget across chapters instead of filling it from the
    # earliest one. Measured on RI: Fang Yuan's 40-passage sample came
    # entirely from chapters 1-3, so he profiled as `deathly pale` /
    # `injured` / robes `torn to shreds` -- an accurate reading of his
    # opening death scene and a useless one for every panel afterwards. A
    # per-chapter cap is what makes "typical appearance" mean typical.
    per_chapter = max(2, max_passages // len(chapters))

    return [t for _c, t in _gather_pairs(
        store,
        novel_id,
        target_id,
        max_chapters=max_chapters,
        max_passages=max_passages,
        allowed_chapters=allowed_chapters,
    )]


def _gather_pairs(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    max_chapters: int,
    max_passages: int,
    allowed_chapters: set[float] | None,
) -> list[tuple[float, str]]:
    # Targeted retrieval across the WHOLE volume, not a 20% stride -- see
    # `find_descriptive_blocks` on why the stride was losing exactly the
    # sentences this stage exists to find.
    wanted = find_descriptive_blocks(store, novel_id, target_id)
    # Delayed-identity reveals carry description that no resolved mention
    # points at -- see `find_reveal_blocks`. Merged rather than replacing,
    # and de-duplicated below by block.
    wanted = sorted(set(wanted) | set(find_reveal_blocks(store, novel_id, target_id)))
    if allowed_chapters is not None:
        wanted = [(c, b) for c, b in wanted if c in allowed_chapters]
    if not wanted:
        return []

    by_chapter: dict[float, list[int]] = {}
    for chapter, block in wanted:
        by_chapter.setdefault(chapter, []).append(block)

    # Still capped per chapter, so one talkative chapter cannot crowd out
    # the rest of the arc -- but the candidates are now descriptive blocks
    # rather than whatever happened to sit on a grid line.
    per_chapter = max(2, max_passages // max(1, min(len(by_chapter), max_chapters)))

    named: list[tuple[float, str]] = []
    unnamed: list[tuple[float, str]] = []
    overflow: list[tuple[float, str]] = []
    seen: set[str] = set()
    surfaces = _surface_forms(store, novel_id, target_id)

    for chapter in sorted(by_chapter):
        blocks = set(by_chapter[chapter])
        taken = 0
        for span in store.get_spans(novel_id, chapter):
            if span.block_index not in blocks or span.span_type not in _DESCRIPTIVE:
                continue
            text = span.text.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            clipped = text[:_MAX_PASSAGE_CHARS]
            if taken >= per_chapter:
                overflow.append((chapter, clipped))
                continue
            taken += 1
            if any(sf in clipped.casefold() for sf in surfaces):
                named.append((chapter, clipped))
            else:
                unnamed.append((chapter, clipped))

    # **Rank by how much each passage actually describes a body, and whose.**
    # Naming alone was the only signal before, and it is nearly useless here:
    # every passage in this pool already comes from a block where the target
    # is PRESENT, so "contains the name" separates almost nothing. Measured on
    # RI's Fang Yuan body 2, 56 of the 60 passages that reached the model
    # described no appearance at all, and the highest-scoring ones that did
    # described *other people* standing near him -- which is how a body with
    # 196 chapters of evidence in range extracted nothing but one attire
    # string. `describes_target` outranks a bare descriptive hit, since an
    # accurate description of the wrong person is worse than no description.
    def _rank(pair: tuple[float, str]) -> tuple[int, int]:
        text = pair[1]
        score = descriptive_score(text)
        return (score + (4 if score and describes_target(text, surfaces) else 0), score)

    ordered = sorted(named + unnamed + overflow, key=_rank, reverse=True)
    return ordered[:max_passages]


def _surface_forms(store: Store, novel_id: str, target_id: str) -> set[str]:
    """Case-folded surfaces this entity is actually referred to by.

    Read from resolved mentions rather than the canonical label alone, so
    "Fang Yuan", "Gu Yue Fang Yuan" and a bare "Fang" all count as naming
    him. Single-character surfaces are dropped -- they match everything.
    """
    out = {
        str(r["text"]).strip().casefold()
        for r in store.conn.execute(
            "SELECT DISTINCT text FROM mention WHERE novel_id=? AND target_id=?",
            (novel_id, target_id),
        )
    }
    entity = store.get_self(target_id)
    if entity is not None:
        out.add(entity.canonical_label.strip().casefold())
    return {s for s in out if len(s) > 1}


def build_prompt(label: str, passages: list[str]) -> str:
    lines = [f"Passages about {label}:", ""]
    lines += [f"  - {p}" for p in passages]
    lines += [
        "",
        f"Extract {label}'s physical appearance as a JSON object with these "
        "keys, including a key only if the passages state it:",
        "  hair_color, hair_style, eye_color, skin_tone, height_build,",
        "  distinguishing_features (list of strings), typical_attire,",
        "  rank_insignia, current_condition (injured/healthy/transformed).",
        "",
        # The split that keeps a character recognisable between chapters.
        # Without it, a character introduced mid-disaster is permanently
        # drawn mid-disaster -- see TRANSIENT_KEYS.
        "Separate what is permanently true about this person from what is "
        "only true in these scenes:",
        "  - typical_attire is the garment they normally wear, described "
        "undamaged: 'green robes', never 'torn green robes'.",
        "  - distinguishing_features are permanent marks only (scars, "
        "birthmarks, unusual eyes). Never injuries, blood, dirt, sweat, "
        "tears or dishevelment.",
        "  - current_condition is where any injury, damage or transformation "
        "goes.",
        "",
        # These passages are whole narration blocks, so they routinely
        # describe bystanders too. Without this, a neighbour's build gets
        # attributed to the subject -- see `gather_appearance_passages`.
        f"Some passages describe other people standing near {label}. Report "
        f"only {label}'s own appearance. If a detail describes someone else "
        f"-- including anyone compared to {label} (\"taller than {label}\") "
        f"-- omit it entirely.",
        "Return only JSON, no explanation.",
    ]
    return "\n".join(lines)


#: Words that describe a *state* of hair or clothing rather than its
#: identity. `hair_style` is the field these leak into: "disheveled" is not
#: a hairstyle, it is what happened to a hairstyle, and storing it makes a
#: character permanently mid-crisis (measured on RI: Fang Yuan's chapter 1
#: death scene put `hair_style="disheveled"` on his standing profile).
_TRANSIENT_DESCRIPTORS = (
    "disheveled", "dishevelled", "messy", "tangled", "matted", "unkempt",
    "bloodied", "bloody", "torn", "tattered", "shredded", "ragged",
    "burnt", "singed", "soaked", "drenched", "dirty", "muddy",
)


#: Generic nouns that carry no identifying information. A value's *other*
#: words are what must be grounded -- "robes" appears in almost every
#: passage of a xianxia novel and proves nothing; "green" is the claim.
_GENERIC_NOUNS = frozenset(
    {
        "hair", "eyes", "eye", "skin", "robe", "robes", "clothes", "clothing",
        "attire", "garment", "garments", "build", "body", "face", "wearing",
        "with", "and", "the", "his", "her", "their", "colour", "color",
        "coloured", "colored", "tone", "style", "long", "short", "small",
        "large", "features", "appearance", "young", "old", "man", "woman",
    }
)


def attesting_chapter(
    value: str, evidence: list[tuple[float, str]]
) -> float | None:
    """The earliest chapter whose passage actually states this value.

    This is what makes an appearance attribute answerable by
    `state_of(..., position)`. Without it every attribute is written against
    the entity's first attestation, which asserts that a description
    revealed in chapter 90 was true -- and known to the reader -- from
    chapter 1. For a regressor that is wrong for most of the novel: Fang
    Yuan's aged, pre-regression body and his fifteen-year-old one are both
    real, at different positions, and a flat profile can represent neither.

    Returns None when nothing attests the value, which is the same signal
    `_grounded` gives and is handled the same way -- the value is dropped.
    """
    words = [
        w
        for w in re.findall(r"[a-z]{3,}", value.casefold())
        if w not in _GENERIC_NOUNS
    ]
    if not words:
        # Nothing checkable; attribute it to the earliest evidence rather
        # than inventing a position.
        return min((c for c, _ in evidence), default=None)

    for chapter, text in sorted(evidence):
        low = text.casefold()
        if all(w in low for w in words):
            return chapter
    return None


def _grounded(value: str, blob: str) -> bool:
    """Whether the passages actually support this value.

    The model invents. Measured on RI: Bai Ning Bing is introduced as
    "This white-clothed young man was none other than ... Bai Ning Bing",
    and the extractor returned `typical_attire="green robes"` -- green
    being the Gu Yue clan's colour and the novel's most frequent robe
    description, so the model reached for the genre default over the
    sentence in front of it. Nothing about that is detectable from the
    response alone; it is only wrong relative to the evidence.

    So every distinguishing word in a value must appear somewhere in the
    evidence. Generic nouns are exempt (see `_GENERIC_NOUNS`) because they
    carry no claim, and a value made *only* of generic words is left alone
    rather than dropped -- there is nothing to check.
    """
    words = [
        w
        for w in re.findall(r"[a-z]{3,}", value.casefold())
        if w not in _GENERIC_NOUNS
    ]
    if not words:
        return True
    return all(w in blob for w in words)


def _clean_values(values: dict[str, str], label: str, blob: str = "") -> dict[str, str]:
    """Drop extractions that are about a moment, a technique, or someone else.

    Three filters, each from a real mis-extraction on RI:

    - **Transient descriptors** in identity fields ("disheveled" as a
      `hair_style`) -- the state/identity split again, applied to the value
      rather than the key.
    - **Self-referential values** ("streamline, matching up with Fang Yuan's
      slowly growing body" as his own `height_build`). A description of the
      subject never needs to name the subject; when it does, the model has
      quoted a comparison or a technique's description instead.
    - **Overlong values**, which are always a swallowed sentence rather than
      an attribute.
    """
    folded_label = label.casefold()
    out: dict[str, str] = {}

    for key, value in values.items():
        low = value.casefold()

        if len(value) > 120:
            continue
        if key != "current_condition" and folded_label in low:
            continue
        if key in ("hair_style", "typical_attire", "distinguishing_features"):
            if any(word in low for word in _TRANSIENT_DESCRIPTORS):
                continue
        # The evidence has to actually say it -- see `_grounded`.
        if blob and not _grounded(value, blob):
            continue
        out[key] = value

    return out


def _values_from(response: AppearanceResponse) -> dict[str, str]:
    """Flatten a response to key -> value, dropping empties.

    `distinguishing_features` is a list in the schema (a character can have
    several) but is stored as one comma-joined `Attribute` value, because a
    generation prompt consumes it as one clause.
    """
    out: dict[str, str] = {}
    for key in APPEARANCE_KEYS:
        raw = getattr(response, key, "")
        if isinstance(raw, list):
            joined = ", ".join(str(v).strip() for v in raw if str(v).strip())
            value = joined
        else:
            value = str(raw).strip()
        if value and value.lower() not in ("unknown", "none", "n/a", "not stated"):
            out[key] = value
    return out


def extract_appearance(
    novel_id: str,
    store: Store,
    *,
    client: object,
    chapters: list[float] | None = None,
    max_chapters: int = 40,
) -> AppearanceReport:
    """Read appearance out of narration and store it under each persona.

    `chapters` restricts which chapters count as evidence; None uses every
    chapter the entity appears in (bounded by `max_chapters`). Requires a
    model client -- there is no deterministic fallback, because unlike age or
    gender there is no honorific or pronoun that states hair colour, and a
    guess would be pure invention.
    """
    from echotales.pipeline.llm.tasks import Task

    report = AppearanceReport(novel_id=novel_id)
    allowed = set(chapters) if chapters is not None else None

    for entity in store.all_selves(novel_id):
        if not entity.kind.is_person:
            continue
        report.entities_considered += 1

        if eligible_prominence(store, novel_id, entity) not in _ELIGIBLE:
            report.skipped_not_prominent += 1
            continue

        # **One call per body, not per character.** A regressor's two bodies
        # are described in disjoint stretches of the novel, and pooling their
        # evidence into one call asks the model to average a 500-year-old and
        # a fifteen-year-old into a single face -- it will answer, and the
        # answer will describe neither. Splitting the evidence by epoch is
        # what lets each body be read out of the text rather than written
        # down by hand (`persona/canon.py::CANON_BY_BODY` was the stopgap).
        #
        # Chapter granularity here, deliberately: a body change can fall
        # mid-chapter (RI's does), but evidence is gathered per chapter, so
        # the transition chapter goes wholly to the body that holds most of
        # it. Splitting evidence per block would be more precise and is not
        # worth the complexity until a novel needs it.
        bodies = _chapters_by_body(store, novel_id, entity.id, allowed)
        if not bodies:
            # No chapters in range at all. Counted rather than skipped
            # silently: a stage whose output is invisible until a panel
            # renders wrong must not quietly drop entities from its own
            # accounting.
            report.skipped_no_evidence += 1
            continue

        for persona_id, epoch_chapters in bodies:
            evidence = gather_appearance_evidence(
                store,
                novel_id,
                entity.id,
                max_chapters=max_chapters,
                allowed_chapters=epoch_chapters,
            )
            passages = [t for _c, t in evidence]
            if not passages:
                report.skipped_no_evidence += 1
                continue

            try:
                result = client.complete(  # type: ignore[attr-defined]
                    Task.APPEARANCE_EXTRACTION,
                    build_prompt(entity.canonical_label, passages),
                    AppearanceResponse,
                    system=SYSTEM,
                    novel_id=novel_id,
                )
            except Exception as exc:
                log.warning("appearance extraction failed for %s: %s", entity.id, exc)
                report.failures += 1
                continue

            report.entities_called += 1
            values = _clean_values(
                _values_from(result.value),
                entity.canonical_label,
                " ".join(t for _c, t in evidence).casefold(),
            )
            if not values:
                continue

            _write_appearance(
                store,
                novel_id,
                entity,
                persona_id,
                values,
                evidence,
                report=report,
            )

    store.conn.commit()
    return report


def _chapters_by_body(
    store: Store,
    novel_id: str,
    target_id: str,
    allowed: set[float] | None,
) -> list[tuple[str, set[float]]]:
    """`(persona_id, chapters)` for each body this character has, in order.

    Grouped through `persona_at` rather than by re-reading intervals, so
    there is exactly one rule in the codebase for "which body is this
    consciousness in at this position". An unsplit character -- the
    overwhelming majority -- comes back as a single group, which is
    byte-identical to the behaviour before bodies existed.
    """
    from echotales.pipeline.persona.split import persona_at

    by_body: dict[str, set[float]] = {}
    for chapter in store.chapters_for_target(novel_id, target_id):
        if allowed is not None and chapter not in allowed:
            continue
        # **Ask at the chapter's midpoint, not its first block.** `persona_at`
        # takes the fractional story position `split.py::write_epochs` writes
        # its body boundaries in (`chapter + block / n_blocks`); a bare integer
        # chapter number means "the very start of the chapter", so a body that
        # takes over partway through one still reported the *previous* body for
        # the whole of it. The midpoint implements this function's own stated
        # rule -- the transition chapter goes wholly to the body holding most
        # of it -- instead of always to whichever body opened it.
        by_body.setdefault(
            persona_at(store, target_id, chapter + 0.5), set()
        ).add(chapter)
    if not by_body:
        return []
    return sorted(by_body.items())


def _write_appearance(
    store: Store,
    novel_id: str,
    entity: object,
    persona_id: str,
    values: dict[str, str],
    evidence: list[tuple[float, str]],
    *,
    report: AppearanceReport,
) -> None:
    """Store one body's appearance, each attribute dated where it is stated."""
    known = {
        (a.key, a.value)
        for a in store.get_attributes(TargetKind.PERSONA, persona_id)
        if a.is_standing
    }
    passages = [t for _c, t in evidence]

    written = 0
    for key, value in values.items():
        if (key, value) in known:
            report.attributes_already_known += 1
            continue
        # Position this fact where the text actually attests it, not at
        # the entity's first sighting -- see `attesting_chapter`.
        at = attesting_chapter(value, evidence)
        if at is None:
            continue
        pos = DiscoursePosition(chapter=at, offset=0)
        store.add_attribute(
            novel_id,
            Attribute(
                target_kind=TargetKind.PERSONA,
                target_id=persona_id,
                key=key,
                value=value,
                # Open-ended *from the attesting chapter*: the fact
                # holds from where the novel states it, and a later
                # contradicting attestation lands as its own row rather
                # than silently replacing this one.
                interval=FuzzyInterval.open_ended(at, last_evidence=at),
                learned_at_pos=pos,
                observer_id=OBSERVER_READER,
                # A model's reading of the prose, not the prose's own
                # assertion -- an explicit declaration outranks this.
                asserted_by=AssertedBy.INFERENCE,
                truth_status=TruthStatus.INFERRED,
                evidence=f"attested ch{at:g}; {len(passages)} passages"[:200],
            ),
        )
        written += 1

    report.attributes_written += written
    if written:
        label = str(entity.canonical_label)  # type: ignore[attr-defined]
        report.by_entity[label] = report.by_entity.get(label, 0) + written
