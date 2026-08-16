"""One reference image per character, for identity-consistent panels.

The gap this closes: nothing had ever generated a reference image for any
character, so IP-Adapter conditioning in `render/panels.py` had nothing to
condition *against* and every panel re-rolled a new face. A reference sheet
is the anchor that makes "the same character across panels" mean anything.

**Built from the appearance attributes, not from the prose.**
`resolve/appearance_extract.py` already turned scattered narration into
structured `Attribute` rows; this stage only has to phrase them. That split
matters: appearance is extracted once per novel and reused by every
downstream visual consumer, rather than each of them re-reading the text.

**Regenerated only when the appearance changes.** A digest of the character's
appearance attributes is stored alongside the image path, and generation is
skipped when the digest still matches -- re-generating every principal on
every run is not viable at a few seconds of GPU time each, and the source
data changes far more rarely than the pipeline is run.

**Prominence decides the budget**, as `plans.md` Phase 8 always specified:
principals get a full detailed sheet, recurring characters a shorter prompt,
and incidental characters no reference image at all (they fall back to the
archetype/faction defaults in `persona/attire.py`, which is what those tiers
exist for).

The engine is `render/panels.py`'s `PanelImageEngine` protocol, unchanged --
a reference sheet is one more text-to-image call, and giving it its own
parallel backend abstraction would mean two places to wire every new
checkpoint.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import (
    OBSERVER_READER,
    AssertedBy,
    Prominence,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute
from echotales.core.store import Store
from echotales.pipeline.persona.attire import resolve_appearance
from echotales.pipeline.persona.canon import apply_canon
from echotales.pipeline.persona.prompt import fit_to_budget
from echotales.pipeline.persona.split import bodies_of

log = logging.getLogger(__name__)

#: Attribute key holding the generated sheet's path.
REFERENCE_PATH_KEY = "reference_image_path"

#: Attribute key holding the digest of the appearance data that produced it.
#: Its whole job is cache invalidation -- see the module docstring.
REFERENCE_DIGEST_KEY = "reference_appearance_digest"

#: Appearance keys, in the order they read naturally in a prompt. Not the
#: same order as `appearance_extract.APPEARANCE_KEYS`, which is the storage
#: vocabulary; this is a sentence.
_PROMPT_ORDER = (
    "height_build",
    "hair_color",
    "hair_style",
    "eye_color",
    "skin_tone",
    "distinguishing_features",
    "typical_attire",
    "rank_insignia",
)

#: The style contract. Non-negotiable per the brief: the output must be
#: inked black-and-white manga.
#:
#: **"character reference sheet" is deliberately absent.** It reads to the
#: model as a literal instruction to draw a *sheet* -- the first real
#: generation came back as a collage of twelve thumbnail poses, which is
#: the worst possible IP-Adapter input: the adapter needs one clear face to
#: lock onto, and given twelve small ones it locks onto none of them. What
#: this stage wants is a single portrait that happens to serve as a
#: reference, not a page of model sheets.
#: **Three-quarter, not an upper-body crop.** The sheet was asking for
#: "upper body portrait", and a bust crop discards the two things that
#: identify a xianxia character in silhouette: the length of the hair and
#: the shape of the robe. Measured on the first real cast -- a sheet showing
#: shoulders and up, for a protagonist whose canon description is
#: waist-length hair, so the sheet could not carry the feature the panels
#: were supposed to inherit from it.
#:
#: Three-quarter rather than full body because IP-Adapter needs a clear
#: face to lock onto -- the reference-sheet-as-collage failure was exactly
#: a face too small to read. Head-to-thigh keeps the face large and still
#: shows the hair falling past the waist.
#:
#: **Vocabulary matches `persona/prompt.py` deliberately**, including the
#: terms that moved to the negative side there: "rich colors, cinematic
#: lighting, masterpiece, best quality" were in this string while the panel
#: prompt was rejecting them, so the sheet and the panels conditioned on it
#: were asking for opposite pictures. That divergence is the failure mode
#: `prompt.py`'s docstring warns about, found in this file.
#: The framing and medium, short enough to lead every sheet prompt. Split
#: out of `REFERENCE_STYLE` for the same reason panel framing was split out
#: of the panel style: the appearance clause alone is ~65 of the 75
#: available tokens, so anything appended after it is dropped -- and what
#: was being dropped was the three-quarter framing and the ink-painting
#: medium, i.e. the entire point of the style string.
REFERENCE_ANCHOR = (
    "three-quarter shot from head to thigh, "
    "guofeng illustration, chinese ink painting, xianxia"
)

REFERENCE_STYLE = (
    "solo, single character, three-quarter shot from head to thigh, "
    "facing viewer, detailed face, plain background, "
    "guofeng illustration, chinese ink painting, xianxia, wuxia, "
    "hanfu with long wide sleeves, ink wash, muted limited palette, "
    "serious cold expression, mature proportions, sharp features"
)
# Tried dropping "serious cold expression ... sharp features" in favour of
# neutral framing-only language, reasoning that it fought characters
# described as plain/ordinary. Reverted: the author's own visual judgement
# on the resulting images was that they were worse on every axis except
# clothing colour, which was the actual bug (see `canon.py`'s
# `CANON_APPEARANCE`, now fixed there instead of here).

#: Ordered most-discriminating first and fitted to CLIP's 77 tokens, same
#: as `prompt.py::negative_for`. The collage terms lead because that is the
#: failure that destroys a sheet's whole purpose: IP-Adapter handed twelve
#: small faces locks onto none of them.
_REFERENCE_NEGATIVE_PARTS = (
    "multiple views, character sheet, multiple poses, collage, grid",
    "two people, crowd, extra limbs, deformed hands",
    "chibi, cute, moe, kawaii, big round eyes, child",
    "photorealistic, 3d render, western comic",
    "rich colors, oversaturated, glossy, plastic skin",
    "school uniform, modern clothing, cherry blossoms, birds",
    "watermark, text, speech bubble",
)

REFERENCE_NEGATIVE = fit_to_budget(list(_REFERENCE_NEGATIVE_PARTS))


@dataclass(slots=True)
class ReferenceReport:
    novel_id: str
    generated: int = 0
    reused_cached: int = 0
    skipped_no_appearance: int = 0
    skipped_incidental: int = 0
    engine: str = "stub"
    paths: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.generated} reference sheets generated "
            f"({self.engine}), {self.reused_cached} reused from cache\n"
            f"  skipped: {self.skipped_incidental} incidental, "
            f"{self.skipped_no_appearance} with no appearance data"
        )


def appearance_of(
    store: Store, persona_id: str, *, standing_only: bool = True
) -> dict[str, str]:
    """Appearance attributes for a persona, key -> value.

    Later attestations win on a repeated key: `appearance_extract` appends
    rather than overwrites (a scar is added later), so the most recent row
    is the current reading.

    `standing_only` (the default) drops `TRANSIENT_KEYS` -- a character's
    injuries belong to the scene that caused them, not to their face. This
    is the second half of the consistency guarantee: the extractor is asked
    to keep condition out of the identity fields, and this drops it again
    at the boundary in case the model ignored the instruction. A reference
    sheet built from a character's worst day would redraw them wounded in
    every chapter thereafter.
    """
    from echotales.pipeline.resolve.appearance_extract import (
        APPEARANCE_KEYS,
        TRANSIENT_KEYS,
    )

    allowed = set(APPEARANCE_KEYS)
    if standing_only:
        allowed -= set(TRANSIENT_KEYS)

    out: dict[str, str] = {}
    for attr in store.get_attributes(TargetKind.PERSONA, persona_id):
        if attr.key in allowed and attr.is_standing and attr.value:
            out[attr.key] = attr.value
    return out


def _demographics(
    store: Store, persona_id: str, *, novel_id: str = "", entity_id: str = ""
) -> tuple[str, str]:
    """`(gender, age_band)` from the trait profile `persona/build.py` wrote.

    **Falls back to pronoun evidence when the stored gender is `unknown`.**
    That column is as stale as `Self.prominence` in existing databases --
    measured on RI, Fang Yuan himself reads `unknown` -- and an unknown
    gender is not a harmless default here the way it is for voice casting:
    `build_reference_prompt` degrades to "person", and an anime checkpoint
    handed "person" draws a woman. The protagonist of a 199-chapter novel
    came out female on the first real run.

    `traits.py::gender_from_pronouns` is the existing answer to exactly this
    question (English translation makes narration unavoidably gendered even
    when the name and honorifics state nothing), so it is consulted rather
    than reimplemented -- and it returns `None` on thin or mixed evidence,
    which is preserved as `unknown` rather than forced.
    """
    attrs = {
        a.key: a.value
        for a in store.get_attributes(TargetKind.PERSONA, persona_id)
        if a.is_standing
    }
    gender = attrs.get("gender", "unknown")
    age_band = attrs.get("age_band", "adult")

    if gender == "unknown" and novel_id and entity_id:
        from echotales.pipeline.persona.traits import gender_from_pronouns
        from echotales.pipeline.resolve.appearance_extract import (
            gather_appearance_passages,
        )

        passages = gather_appearance_passages(store, novel_id, entity_id)
        inferred, _reason = gender_from_pronouns(passages)
        if inferred:
            gender = inferred

    # **Same treatment for age, and it must be scoped to *this body*.**
    # `age_band` had no evidence path at all -- nothing ever overrode the
    # `"adult"` default -- so RI's reborn fifteen-year-old was prompted as a
    # grown man on every panel and every reference sheet. Unlike gender, age
    # differs *between bodies* of the same character, so the evidence has to
    # come from this persona's own chapters: pooling both bodies would let
    # the 500-year-old's chapters answer for the teenager's.
    if age_band == "adult" and novel_id and entity_id:
        from echotales.pipeline.persona.traits import age_band_from_text
        from echotales.pipeline.resolve.appearance_extract import (
            _chapters_by_body,
            gather_appearance_passages as _passages,
        )

        scoped = dict(_chapters_by_body(store, novel_id, entity_id, None))
        chapters = scoped.get(persona_id)
        body_passages = _passages(
            store, novel_id, entity_id, allowed_chapters=chapters
        )
        if body_passages:
            inferred_age, _why = age_band_from_text(body_passages)
            if inferred_age:
                age_band = inferred_age

    return gender, age_band


def build_reference_prompt(
    label: str,
    appearance: dict[str, str],
    *,
    gender: str = "unknown",
    age_band: str = "adult",
    detailed: bool = True,
    with_style: bool = True,
    solo: bool = True,
    crowd: bool = False,
) -> str:
    """Phrase a character's stored appearance as a generation prompt.

    `detailed=False` (recurring characters) keeps only the strongest identity
    cues, which is the whole point of the prominence tiering: a walk-on does
    not need -- and has not got the evidence to support -- a full sheet.

    **`solo=False` for anything but an actual reference sheet.** This
    function is reused by `render/panels.py::character_looks` to phrase a
    character's clause *inside a scene panel's prompt*, and the "solo" tag
    was leaking through there unconditionally -- a real, confirmed bug:
    RI ch1's opening panel prompt read "...1boy, solo, male... a xianxia
    mountain stronghold..., warlords with drawn swords..." in the same
    string, and the generated image was a single clean solo portrait with
    no warlords, no wound, no crowd at all. `solo` is a strongly-weighted
    anime-tag token on this checkpoint (see below) and was overriding
    everything else in the prompt describing other people in frame.
    Reference-sheet generation (`generate_references`) always wants
    `solo=True`; panel prompts embedding a cast member never do.
    """
    parts: list[str] = []

    # Danbooru-style tags first. Anime/manga checkpoints are trained on that
    # vocabulary and weight `1boy`/`1girl` far more strongly than the plain
    # English word -- and this is the token that decides whether the
    # protagonist comes out male, so it leads the prompt rather than sitting
    # inside a descriptive clause. `solo` reinforces the single-figure
    # framing that `REFERENCE_STYLE` is also asking for -- but only when
    # actually generating a reference sheet; see the `solo` param docs.
    # **`crowd=True` drops the numeric headcount.** "1boy" is a Danbooru
    # count tag meaning *exactly one male*, and this checkpoint weights it
    # far above any English phrasing -- so a panel whose prompt also said
    # "surrounded by armed warlords and warrior women" rendered one man
    # alone on a mountainside. Only resolved characters reach this clause,
    # and a mob never resolves, so the count was systematically wrong for
    # exactly the scenes that needed other people in them. Same failure as
    # the `solo` tag above, one layer along.
    if gender == "male":
        head = "male" if crowd else ("1boy, solo, male" if solo else "1boy, male")
    elif gender == "female":
        head = "female" if crowd else ("1girl, solo, female" if solo else "1girl, female")
    else:
        head = "androgynous person" if (crowd or not solo) else "solo, androgynous person"
    parts.append(head)

    if age_band != "adult":
        parts.append(age_band)

    keys = _PROMPT_ORDER if detailed else ("hair_color", "hair_style", "typical_attire")
    for key in keys:
        value = appearance.get(key)
        if not value:
            continue
        if key == "hair_color":
            # Merged with hair_style below when both are present, so a
            # prompt reads "long black hair", not "black, long hair".
            continue
        if key == "hair_style":
            colour = appearance.get("hair_color", "")
            # Canon styles read as full phrases ("very long straight hair
            # down to the waist"); appending "hair" to those produced
            # "...down to the waist hair".
            phrase = f"{colour} {value}".strip()
            if "hair" not in value.casefold():
                phrase = f"{phrase} hair"
            parts.append(phrase)
        elif key == "eye_color":
            parts.append(f"{value} eyes")
        elif key == "typical_attire":
            parts.append(f"wearing {value}")
        else:
            parts.append(value)

    if appearance.get("hair_color") and not appearance.get("hair_style"):
        parts.append(f"{appearance['hair_color']} hair")

    if not with_style:
        return ", ".join(p for p in parts if p)

    # Priority order, fitted to CLIP's 77 tokens. The headcount tag and the
    # framing/medium anchor lead because losing them changes *what kind of
    # picture this is*; the appearance follows; the style elaboration goes
    # last because it is the cheapest thing to lose. Before this, appearance
    # ran to ~65 tokens and the style never reached the model at all.
    head, *appearance_parts = parts
    return fit_to_budget([head, REFERENCE_ANCHOR, *appearance_parts, REFERENCE_STYLE])


def _digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def _seed_for(entity_id: str, base: int) -> int:
    """A stable seed unique to this character.

    Derived from the entity id rather than `random`, so the same character
    regenerates to the same face on any machine and in any run -- the whole
    point of a reference sheet. Mixed with `base` so a caller can shift the
    entire cast to a different draw without losing per-character
    separation.
    """
    digest = hashlib.sha256(f"{base}:{entity_id}".encode()).hexdigest()
    return int(digest[:8], 16)


def _write_marker(
    store: Store, novel_id: str, persona_id: str, key: str, value: str, entity: object
) -> None:
    store.add_attribute(
        novel_id,
        Attribute(
            target_kind=TargetKind.PERSONA,
            target_id=persona_id,
            key=key,
            value=value,
            interval=FuzzyInterval.open_ended(
                entity.first_attested_pos.chapter,  # type: ignore[attr-defined]
                last_evidence=entity.first_attested_pos.chapter,  # type: ignore[attr-defined]
            ),
            learned_at_pos=entity.first_attested_pos,  # type: ignore[attr-defined]
            observer_id=OBSERVER_READER,
            asserted_by=AssertedBy.INFERENCE,
            truth_status=TruthStatus.INFERRED,
        ),
    )


def generate_references(
    novel_id: str,
    store: Store,
    *,
    engine: object | None = None,
    out_dir: str | Path = "data/references",
    top: int | None = None,
    include_recurring: bool = True,
    width: int = 768,
    height: int = 1024,
    seed: int = 0,
) -> ReferenceReport:
    """Generate one cached reference sheet per prominent character.

    `top` limits the run to the N most-mentioned eligible characters, which
    is how a first pass gets reviewed before committing GPU time to a full
    cast.
    """
    from echotales.pipeline.render.panels import get_engine
    from echotales.pipeline.resolve.appearance_extract import eligible_prominence

    engine = engine or get_engine("stub")
    out_dir = Path(out_dir) / novel_id
    report = ReferenceReport(novel_id=novel_id, engine=getattr(engine, "name", "?"))

    people = [e for e in store.all_selves(novel_id) if e.kind.is_person]
    ranked = sorted(
        people, key=lambda e: -store.mention_count_for(novel_id, e.id)
    )

    eligible: list[tuple[object, Prominence]] = []
    for entity in ranked:
        prominence = eligible_prominence(store, novel_id, entity)
        if prominence is Prominence.INCIDENTAL:
            report.skipped_incidental += 1
            continue
        if prominence is Prominence.RECURRING and not include_recurring:
            continue
        eligible.append((entity, prominence))

    if top is not None:
        eligible = eligible[:top]

    # One sheet per **body**, not per character. A reborn or transmigrated
    # character has two personas with genuinely different appearances, and a
    # single sheet would condition every panel in the book on whichever one
    # happened to be extracted first. `bodies_of` returns exactly one entry
    # for the overwhelming majority of the cast, so this loop costs nothing
    # for characters who never change.
    for entity, prominence in eligible:
        bodies = [pid for pid, _interval in bodies_of(store, str(entity.id))]  # type: ignore[attr-defined]
        for persona_id in bodies or [f"{entity.id}:body1"]:  # type: ignore[attr-defined]
            _generate_one(
                store,
                novel_id,
                entity,
                persona_id,
                prominence,
                engine=engine,
                out_dir=out_dir,
                report=report,
                width=width,
                height=height,
                seed=seed,
                multi_body=len(bodies) > 1,
            )

    store.conn.commit()
    return report


def _generate_one(
    store: Store,
    novel_id: str,
    entity: object,
    persona_id: str,
    prominence: Prominence,
    *,
    engine: object,
    out_dir: Path,
    report: ReferenceReport,
    width: int,
    height: int,
    seed: int,
    multi_body: bool,
) -> None:
    """Generate (or reuse) the sheet for one body of one character."""
    from echotales.pipeline.render.panels import PanelImageRequest

    appearance = appearance_of(store, persona_id)
    if not appearance:
        report.skipped_no_appearance += 1
        return

    gender, age_band = _demographics(
        store, persona_id, novel_id=novel_id, entity_id=str(entity.id)  # type: ignore[attr-defined]
    )
    # Genre defaults for whatever the prose never stated. Without this
    # the diffusion model picks those features itself, differently every
    # time it is asked -- see `attire.py::APPEARANCE_DEFAULTS`.
    # Canon first (a reader beats an extractor), then genre defaults
    # for whatever neither states.
    appearance = apply_canon(
        novel_id,
        str(entity.canonical_label),  # type: ignore[attr-defined]
        appearance,
        persona_id,
    )
    appearance = resolve_appearance(novel_id, appearance)
    prompt = build_reference_prompt(
        entity.canonical_label,  # type: ignore[attr-defined]
        appearance,
        gender=gender,
        age_band=age_band,
        detailed=prominence is Prominence.PRINCIPAL,
    )
    digest = _digest(prompt)

    stored = {
        a.key: a.value
        for a in store.get_attributes(TargetKind.PERSONA, persona_id)
        if a.is_standing
    }
    image_path = out_dir / f"{persona_id.replace(':', '_')}.png"

    if (
        stored.get(REFERENCE_DIGEST_KEY) == digest
        and image_path.exists()
    ):
        report.reused_cached += 1
        report.paths[_report_key(entity, persona_id, multi_body)] = str(image_path)
        return

    engine.generate(  # type: ignore[attr-defined]
        PanelImageRequest(
            prompt=prompt,
            out_path=image_path,
            negative_prompt=REFERENCE_NEGATIVE,
            width=width,
            height=height,
            # Per-*body*, not per-run: two characters sharing one seed
            # and a similar prompt come out looking like siblings, a seed
            # that moved between runs would redraw a face downstream
            # panels are already conditioned on, and two bodies of one
            # character must not come out as the same face -- which is the
            # entire point of splitting them.
            seed=_seed_for(persona_id, seed),
        )
    )

    if stored.get(REFERENCE_PATH_KEY) != str(image_path):
        _write_marker(
            store, novel_id, persona_id, REFERENCE_PATH_KEY, str(image_path), entity
        )
    _write_marker(store, novel_id, persona_id, REFERENCE_DIGEST_KEY, digest, entity)

    report.generated += 1
    report.paths[_report_key(entity, persona_id, multi_body)] = str(image_path)


def _report_key(entity: object, persona_id: str, multi_body: bool) -> str:
    """How a generated sheet is named in the report.

    Unqualified for the ordinary one-body character, so existing output is
    unchanged; qualified by body when there is more than one, because two
    rows reading "Fang Yuan" would silently overwrite each other.
    """
    label = str(entity.canonical_label)  # type: ignore[attr-defined]
    return label if not multi_body else f"{label} [{persona_id.rsplit(':', 1)[-1]}]"


def reference_path_for(store: Store, persona_id: str) -> Path | None:
    """The stored reference sheet for a persona, if one exists on disk.

    Returns None rather than raising when the attribute points at a file
    that has since been deleted -- `render/panels.py` treats a missing
    reference as "fall back to prompt-only", which is a degradation, not a
    failure.
    """
    for attr in store.get_attributes(TargetKind.PERSONA, persona_id):
        if attr.key == REFERENCE_PATH_KEY and attr.is_standing and attr.value:
            path = Path(attr.value)
            if path.exists():
                return path
    return None
