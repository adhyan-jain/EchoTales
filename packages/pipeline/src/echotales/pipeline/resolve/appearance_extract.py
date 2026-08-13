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

from pydantic import BaseModel, Field

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
from echotales.core.models import Attribute
from echotales.core.store import Store

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

    named: list[str] = []
    unnamed: list[str] = []
    overflow: list[str] = []

    for chapter in chapters:
        present_blocks = {
            m.block_index
            for m in store.get_mentions(novel_id, chapter)
            if m.target_id == target_id and m.reference_mode is ReferenceMode.PRESENT
        }
        if not present_blocks:
            continue

        taken = 0
        for span in store.get_spans(novel_id, chapter):
            if span.block_index not in present_blocks:
                continue
            if span.span_type not in _DESCRIPTIVE:
                continue
            text = span.text.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            clipped = text[:_MAX_PASSAGE_CHARS]

            if taken >= per_chapter:
                # Past this chapter's share. Kept aside rather than dropped,
                # to backfill if the novel simply has fewer descriptive
                # passages than the budget wants.
                overflow.append(clipped)
                continue
            taken += 1
            if any(sf in clipped.casefold() for sf in surfaces):
                named.append(clipped)
            else:
                unnamed.append(clipped)

    return (named + unnamed + overflow)[:max_passages]


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

        passages = gather_appearance_passages(
            store,
            novel_id,
            entity.id,
            max_chapters=max_chapters,
            allowed_chapters=allowed,
        )
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
        except Exception as exc:  # noqa: BLE001 - one bad entity must not sink the stage
            log.warning("appearance extraction failed for %s: %s", entity.id, exc)
            report.failures += 1
            continue

        report.entities_called += 1
        values = _clean_values(
            _values_from(result.value),
            entity.canonical_label,
            " ".join(passages).casefold(),
        )
        if not values:
            continue

        persona_id = f"{entity.id}:body1"
        known = {
            (a.key, a.value)
            for a in store.get_attributes(TargetKind.PERSONA, persona_id)
            if a.is_standing
        }

        written = 0
        for key, value in values.items():
            if (key, value) in known:
                report.attributes_already_known += 1
                continue
            store.add_attribute(
                novel_id,
                Attribute(
                    target_kind=TargetKind.PERSONA,
                    target_id=persona_id,
                    key=key,
                    value=value,
                    interval=FuzzyInterval.open_ended(
                        entity.first_attested_pos.chapter,
                        last_evidence=entity.first_attested_pos.chapter,
                    ),
                    learned_at_pos=entity.first_attested_pos,
                    observer_id=OBSERVER_READER,
                    # A model's reading of the prose, not the prose's own
                    # assertion -- an explicit declaration outranks this.
                    asserted_by=AssertedBy.INFERENCE,
                    truth_status=TruthStatus.INFERRED,
                    evidence=f"{len(passages)} narration passages"[:200],
                ),
            )
            written += 1

        report.attributes_written += written
        if written:
            report.by_entity[entity.canonical_label] = (
                report.by_entity.get(entity.canonical_label, 0) + written
            )

    store.conn.commit()
    return report
