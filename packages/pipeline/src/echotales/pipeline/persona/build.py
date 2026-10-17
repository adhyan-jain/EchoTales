"""Phase 7: build a `Persona` per character and profile it (Section 10 item 4).

Until this stage existed, `docs/design/architecture.md Section 4`'s self/persona split had no
code on the persona side at all: `Persona` had a runner nowhere in the
pipeline, so nothing consumed the `SelfPersonaBinding` table and voice/image
work had nothing to bind to.

**One persona per self, for now, and that is a real limitation stated
plainly.** The split exists so that reincarnation, body-swap and sustained
disguise can put *two* personas on one self (LOTM's Zhou Mingrui / Klein
Moretti is the worked example in `docs/design/architecture.md Section 4` and Section 4.15). Detecting
that a second body has appeared is an identity-resolution question this
stage is downstream of, not one it can answer -- `resolve/` decides who is
whom, and a persona split would have to come from there. What this stage
does is make the common case real: every character that can be voiced now
has a persona row, a binding, and a trait profile.

Traits are stored as `Attribute` rows against the persona (`TargetKind.
PERSONA`), which is where `models.Attribute`'s own docstring says
appearance/age/voice belong, so `persona/runner.py::get_panel_cast` and
voice casting both read them through the existing accessor rather than a
new side table.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.core.enums import (
    OBSERVER_READER,
    Prominence,
    SpanType,
    TargetKind,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, DiscoursePosition
from echotales.core.pipeline_run import PartialStageFailure
from echotales.core.store import Store
from echotales.pipeline.persona.split import (
    SplitReport,
    detect_body_changes,
    detect_permanent_injuries,
    epochs_for,
    persona_at,
    standing_values,
    write_epochs,
)
from echotales.pipeline.persona.traits import TraitProfile, anchored_window, infer_traits_deterministic

#: Below this many mentions an entity gets a deterministic profile only. A
#: model call per walk-on is exactly the per-entity equivalent of the
#: per-mention waste Section 3's budget rule forbids, and a character with three
#: mentions has almost no evidence to read anyway.
LLM_MENTION_FLOOR = 25

#: Prominence thresholds, by mention count. Drives generation budget
#: downstream (docs/design/plans.md Section 6 Phase 8) and which characters earn a cloned voice
#: rather than a bank voice (`4b` step 4).
PRINCIPAL_FLOOR = 300
RECURRING_FLOOR = 30

#: Chapters (where the entity is attested) that feed a trait read. A trait therefore has an *evidence horizon*, the
#: last of those chapters, which is later than the chapter of first sighting that was used as its stamp until the
#: prefix audit (docs/research/PREFIX_FAITHFULNESS/PREREG.md): 23 of 289 character-cuts served a gender that the
#: truncated graph could not yet know.
EVIDENCE_CHAPTERS = 12

#: A trait computed from whole chapters is known once the chapter is over, not from its first mention.
_END_OF_CHAPTER = 10**6


@dataclass(slots=True)
class PersonaReport:
    novel_id: str
    personas: int = 0
    bindings: int = 0
    profiled_llm: int = 0
    profiled_deterministic: int = 0
    skipped_non_person: int = 0
    split_characters: int = 0
    by_archetype: dict[str, int] = field(default_factory=dict)
    split: SplitReport | None = None

    def summary(self) -> str:
        top = sorted(self.by_archetype.items(), key=lambda kv: -kv[1])[:6]
        buckets = ", ".join(f"{k}={v}" for k, v in top) or "none"
        out = (
            f"{self.novel_id}: {self.personas:,} personas, {self.bindings:,} bindings\n"
            f"  profiled: {self.profiled_llm} llm, "
            f"{self.profiled_deterministic} deterministic\n"
            f"  skipped (not a person): {self.skipped_non_person}\n"
            f"  characters with more than one body: {self.split_characters}\n"
            f"  top archetype buckets: {buckets}"
        )
        if self.split is not None:
            out += "\n  " + self.split.summary().replace("\n", "\n  ")
        return out


def _prominence_for(mention_count: int) -> Prominence:
    if mention_count >= PRINCIPAL_FLOOR:
        return Prominence.PRINCIPAL
    if mention_count >= RECURRING_FLOOR:
        return Prominence.RECURRING
    return Prominence.INCIDENTAL


def _gather_evidence(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    max_chapters: int = EVIDENCE_CHAPTERS,
    upto: float | None = None,
) -> tuple[list[str], list[str], list[str], int]:
    """Spoken lines, narration samples, surface forms and dialogue count.

    Sampled across at most `max_chapters` chapters *where this entity actually
    appears* rather than the first N of the novel -- a character introduced at
    chapter 90 would otherwise be profiled from no evidence at all.

    `upto` restricts the sample to chapters <= upto, which is exactly what a
    build from a truncated volume would have sampled: the earliest chapters
    are taken first, so cutting the list at `upto` equals sampling the prefix.
    """
    dialogue: list[str] = []
    narration: list[str] = []
    surfaces: set[str] = set()
    dialogue_total = 0

    chapters = store.chapters_for_target(novel_id, target_id, limit=max_chapters)
    if upto is not None:
        chapters = [c for c in chapters if c <= upto]
    for chapter in chapters:
        mentions = [
            m for m in store.get_mentions(novel_id, chapter) if m.target_id == target_id
        ]
        if not mentions:
            continue
        surfaces.update(m.text for m in mentions)
        by_block = {m.block_index for m in mentions}

        for span in store.get_spans(novel_id, chapter):
            if span.speaker_self_id == target_id:
                if span.span_type is SpanType.DIALOGUE:
                    dialogue_total += 1
                    if len(dialogue) < 20:
                        dialogue.append(span.text)
                elif span.span_type is SpanType.INNER_MONOLOGUE and len(narration) < 10:
                    narration.append(span.text)
            # Narration in a block this entity is named in. This is the
            # pronoun evidence: it is not exclusively about them (other
            # characters share the paragraph), which is exactly why
            # `gender_from_pronouns` requires a majority rather than a hit.
            elif (
                span.block_index in by_block
                and span.span_type
                in (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION)
                and len(narration) < 24
            ):
                narration.append(span.text)

    return dialogue, narration, sorted(surfaces), dialogue_total


def _gather_anchors(
    store: Store,
    novel_id: str,
    target_id: str,
    *,
    max_chapters: int = EVIDENCE_CHAPTERS,
    upto: float | None = None,
    variant: str = "v1",
) -> list[str]:
    """Text right after each mention, inside its own narration span (PREREG_ANCHORED.md).

    The same chapter window as `_gather_evidence`, so `upto` again equals sampling the prefix. Dialogue spans are skipped:
    a pronoun inside a quoted line is the speaker's, not the narrator's, and usually about someone else.
    """
    windows: list[str] = []
    chapters = store.chapters_for_target(novel_id, target_id, limit=max_chapters)
    if upto is not None:
        chapters = [c for c in chapters if c <= upto]
    narrative = (SpanType.NARRATION_ACTION, SpanType.NARRATION_DESCRIPTION, SpanType.INNER_MONOLOGUE)
    for chapter in chapters:
        mentions = [m for m in store.get_mentions(novel_id, chapter) if m.target_id == target_id]
        if not mentions:
            continue
        spans = [s for s in store.get_spans(novel_id, chapter) if s.span_type in narrative]
        for m in mentions:
            for s in spans:
                if s.block_index == m.block_index and s.start <= m.offset < s.end:
                    windows.append(anchored_window(s.text[m.offset - s.start + len(m.text):], variant))
                    break
    return windows


def _trait_values(profile: TraitProfile) -> dict[str, str]:
    """The persisted trait keys, in the order they have always been written."""
    return {
        "age_band": profile.age_band,
        "gender": profile.gender,
        "register": profile.register,
        "archetype": profile.archetype,
        "big_five": _big_five_str(profile),
        "trait_provenance": profile.provenance,
    }


class _MemoClient:
    """Answers a repeated prompt from memory (PREREG_LLM.md Addendum 3).

    The model prompt holds the label, the first 12 spoken lines and the first 6 narration samples, so once those windows
    fill, every later chapter re-asks the identical question. At temperature 0 the answer is the same (noise floor 0
    measured in REPORT 4.8a); asking again would only multiply the call count by the number of attested chapters.
    """

    def __init__(self, inner: object) -> None:
        self.inner, self.cache = inner, {}

    def complete(self, task, prompt, schema, *, system="", novel_id="", **kwargs):  # noqa: ANN001, ANN003, ANN201
        key = (task, prompt, system)
        if key not in self.cache:
            self.cache[key] = self.inner.complete(task, prompt, schema, system=system, novel_id=novel_id, **kwargs)  # type: ignore[attr-defined]
        return self.cache[key]


def _prefix_trait_revisions(
    store: Store,
    novel_id: str,
    entity: object,
    anchored: tuple[int, float] | None = None,
    client: object | None = None,
    llm_mention_floor: int = LLM_MENTION_FLOOR,
) -> list[tuple[DiscoursePosition, dict[str, str], TraitProfile]]:
    """Trait values as a reader would have held them after each chapter the entity appears in.

    One revision per attested chapter c at which any trait value changes, computed from the evidence and the mention
    count of chapters <= c only, and stamped at the end of c. `state_of` keeps the latest-stamped value per key, so
    the value served at a reading position equals the value a build from that prefix would have produced -- the
    property the single first-sighting stamp lacked (measured on 3 serials, PREFIX_FAITHFULNESS). Only the
    deterministic path can be replayed per chapter; a model read per prefix would multiply the call count.
    """
    attested = store.chapters_for_target(novel_id, entity.id)  # type: ignore[attr-defined]
    per_chapter = store.mention_counts_by_chapter(novel_id, entity.id)  # type: ignore[attr-defined]
    revisions: list[tuple[DiscoursePosition, dict[str, str], TraitProfile]] = []
    previous: dict[str, str] | None = None
    seen = 0
    evidence = None
    memo = _MemoClient(client) if client is not None else None
    for idx, chapter in enumerate(attested):
        seen += per_chapter.get(chapter, 0)
        # The sample is the first EVIDENCE_CHAPTERS attested chapters, so it stops growing after that many; from then
        # on only the cumulative mention count (extraversion's denominator) can still move a trait.
        if evidence is None or idx < EVIDENCE_CHAPTERS:
            evidence = _gather_evidence(store, novel_id, entity.id, upto=chapter)  # type: ignore[attr-defined]
            anchors = (
                _gather_anchors(store, novel_id, entity.id, upto=chapter, variant=anchored[2] if len(anchored) > 2 else "v1")  # type: ignore[attr-defined,misc]
                if anchored else None
            )
        dialogue, narration, surfaces, dialogue_total = evidence
        profile = infer_traits_deterministic(
            entity.id,  # type: ignore[attr-defined]
            entity.canonical_label,  # type: ignore[attr-defined]
            surfaces=surfaces or [entity.canonical_label],  # type: ignore[attr-defined]
            dialogue_lines=dialogue_total,
            mention_count=seen,
            prominence=_prominence_for(seen),
            pronoun_passages=narration,
            anchor_windows=anchors,
            anchor_min_obs=anchored[0] if anchored else 2,
            anchor_majority=anchored[1] if anchored else 0.85,
        )
        # The gate is decided on the mentions read so far, not on the whole volume's count: a build over the prefix would
        # have used the model for this character exactly when its prefix reaches the floor.
        if memo is not None and seen >= llm_mention_floor:
            from echotales.pipeline.persona.extract import extract_traits

            profile = extract_traits(profile, dialogue=dialogue, narration=narration, client=memo, novel_id=novel_id)
        values = _trait_values(profile)
        changed = values if previous is None else {k: v for k, v in values.items() if previous.get(k) != v}
        if changed:
            revisions.append((DiscoursePosition(chapter=chapter, offset=_END_OF_CHAPTER), changed, profile))
        previous = values
    return revisions


def build_personas(
    novel_id: str,
    store: Store,
    *,
    client: object | None = None,
    llm_mention_floor: int = LLM_MENTION_FLOOR,
    commit_every: int = 20,
    prefix_causal: bool = False,
    anchored_gender: tuple[int, float] | None = None,
) -> PersonaReport:
    """Mint a persona per character entity, bind it, and profile it.

    `client=None` runs the deterministic path throughout -- see
    `persona/traits.py` on why that is a supported mode and not a degradation.

    `prefix_causal=True` writes each trait as a series of revisions stamped by their evidence horizon instead of one
    row stamped at first sighting (`_prefix_trait_revisions`). Off by default: it multiplies attribute rows, and the
    readers of persona attributes outside `state_of` (webview, reference_gen, appearance_extract) have not been
    audited against more than one row per key. Body-split bindings are not repaired (`SelfPersonaBinding` has no
    supersession in `state_of`). With a `client`, the model read is gated on the mentions read *so far* at each
    chapter instead of the whole volume's count, and repeated prompts are answered from memory
    (PREREG_LLM.md Addendum 3).

    `anchored_gender=(min_obs, majority)` adds the anchored pronoun cue (`traits.gender_from_anchors`) as a fallback
    when the paragraph rule cannot call a gender (PREREG_ANCHORED.md). Off by default. It uses the same
    first-`EVIDENCE_CHAPTERS` window as every other trait, so it is prefix-causal under `prefix_causal=True`.
    """
    report = PersonaReport(novel_id=novel_id)
    report.split = SplitReport(novel_id=novel_id)
    profiles: dict[str, TraitProfile] = {}

    # Core Pipeline Hardening #6: previously this whole function committed
    # exactly once, at the very end -- an exception anywhere in the loop
    # (a body-change detector call, an attribute write) discarded every
    # entity processed so far, with no record of how far it got. Periodic
    # commits plus an explicit rollback-and-attribute-the-failure on
    # exception bounds that blast radius to `commit_every` entities,
    # matching `resolve_novel`'s own commit_every pattern (#9.7).
    last_committed_index = 0
    idx = 0
    entity = None
    try:
        for idx, entity in enumerate(store.all_selves(novel_id), start=1):
            # Section 10 item 5's typing, doing the job it was added for: a location or
            # a faction has no body to draw and no voice to cast.
            if not entity.kind.is_person:
                report.skipped_non_person += 1
                continue

            mention_count = store.mention_count_for(novel_id, entity.id)
            prominence = _prominence_for(mention_count)
            if prominence is not entity.prominence:
                store.set_prominence(entity.id, prominence)

            dialogue, narration, surfaces, dialogue_total = _gather_evidence(
                store, novel_id, entity.id
            )

            profile = infer_traits_deterministic(
                entity.id,
                entity.canonical_label,
                surfaces=surfaces or [entity.canonical_label],
                dialogue_lines=dialogue_total,
                mention_count=mention_count,
                prominence=prominence,
                pronoun_passages=narration,
                anchor_windows=(
                    _gather_anchors(store, novel_id, entity.id, variant=anchored_gender[2] if len(anchored_gender) > 2 else "v1")  # type: ignore[misc]
                    if anchored_gender else None
                ),
                anchor_min_obs=anchored_gender[0] if anchored_gender else 2,
                anchor_majority=anchored_gender[1] if anchored_gender else 0.85,
            )
            # `prefix_causal` decides the gate chapter by chapter in `_prefix_trait_revisions`; the whole-volume count used
            # here is exactly the decision that made a full build disagree with a prefix build (REPORT 4.8a).
            if client is not None and mention_count >= llm_mention_floor and not prefix_causal:
                from echotales.pipeline.persona.extract import extract_traits

                profile = extract_traits(
                    profile,
                    dialogue=dialogue,
                    narration=narration,
                    client=client,
                    novel_id=novel_id,
                )

            if profile.provenance == "llm":
                report.profiled_llm += 1
            else:
                report.profiled_deterministic += 1

            # One persona per *body*, not per character. A character with no
            # detected body change gets exactly one epoch, so the common case is
            # byte-identical to what this stage produced before `split.py`
            # existed -- `self1:body1`, open-ended from their first sighting.
            report.split.entities_scanned += 1
            changes = detect_body_changes(
                store, novel_id, entity, client=client, report=report.split
            )
            # Section 3: a lasting injury to the SAME body is a boundary too,
            # not just a rebirth/regression -- fed into the exact same
            # `epochs_for`/`write_epochs` call below rather than a parallel
            # body-creation path. Scoped to PRINCIPAL/RECURRING only (3.1);
            # `prominence` here is this loop's own live computation just above,
            # not a stored column (matches `eligible_prominence()`'s own
            # stale-column caution elsewhere in this pipeline).
            injuries = detect_permanent_injuries(store, novel_id, entity, prominence=prominence)
            if injuries:
                changes = sorted(changes + injuries, key=lambda c: c.story_pos)
            report.split.confirmed += len(changes)
            if changes:
                report.split.by_entity[entity.canonical_label] = [c.kind for c in changes]
                report.split_characters += 1

            seen_chapters = store.chapters_for_target(novel_id, entity.id)
            epochs = epochs_for(
                entity.id,
                entity.canonical_label,
                entity.first_attested_pos.chapter,
                changes,
                last_pos=seen_chapters[-1] if seen_chapters else None,
            )
            # Rebuilding, not appending: bindings are a plain INSERT because one
            # self legitimately has several, so a re-run would otherwise double
            # them (see `Store.clear_self_persona_bindings`).
            store.clear_self_persona_bindings(entity.id)
            write_epochs(
                store,
                novel_id,
                entity,
                epochs,
                observer_id=OBSERVER_READER,
                notes=f"auto-built from {entity.id}; {profile.provenance} traits",
                prefix_causal=prefix_causal,
            )
            report.personas += len(epochs)
            report.bindings += len(epochs)

            # Traits are demographics and personality -- properties of the
            # *consciousness*, not of the body it currently wears -- so they are
            # written to every epoch rather than only the first. Appearance is
            # the opposite and is dated per attestation by
            # `appearance_extract`, which is why that stage picks its persona by
            # position and this one does not.
            # Default: one row per key, stamped at first sighting (unchanged). prefix_causal: one revision per
            # evidence-horizon change, each stamped at the end of the chapter it was computed from.
            if prefix_causal:
                trait_rows = _prefix_trait_revisions(store, novel_id, entity, anchored_gender, client, llm_mention_floor)
                if trait_rows:
                    final = trait_rows[-1][2]
                    if final.provenance != profile.provenance:  # the counts above used the unrefined profile
                        report.profiled_deterministic -= final.provenance == "llm"
                        report.profiled_llm += final.provenance == "llm"
                    profile = final
                else:
                    # No attested chapter to replay (a self minted by a whole-volume pass, or one whose mentions were
                    # all reassigned): the default build still writes its label-only profile, and the repaired build
                    # wrote nothing, so voice casting lost these characters' traits (two "Klein" selves on LotM,
                    # scripts/prefix_audit/product_parity.py). That profile reads no chapter evidence, so the
                    # first-sighting stamp is honest for it.
                    trait_rows = [(entity.first_attested_pos, _trait_values(profile), profile)]
            else:
                trait_rows = [(entity.first_attested_pos, _trait_values(profile), profile)]
            for epoch in epochs:
                for stamp, values, row_profile in trait_rows:
                    for key, value in values.items():
                        store.add_attribute(
                            novel_id,
                            Attribute(
                                target_kind=TargetKind.PERSONA,
                                target_id=epoch.persona_id,
                                key=key,
                                value=value,
                                interval=FuzzyInterval.open_ended(
                                    epoch.from_pos,
                                    last_evidence=epoch.last_evidence or epoch.from_pos,
                                ),
                                learned_at_pos=stamp,
                                observer_id=OBSERVER_READER,
                                evidence=row_profile.evidence[:200],
                            ),
                        )

            report.by_archetype[profile.archetype] = (
                report.by_archetype.get(profile.archetype, 0) + 1
            )
            profiles[entity.id] = profile

            if idx % commit_every == 0:
                store.conn.commit()
                last_committed_index = idx
    except Exception as exc:
        store.conn.rollback()
        label = entity.canonical_label if entity is not None else "?"
        if last_committed_index > 0:
            raise PartialStageFailure(
                f"build_personas({novel_id!r}) failed at entity #{idx} ({label}): {exc}",
                progress=f"committed through entity #{last_committed_index}",
            ) from exc
        raise RuntimeError(
            f"build_personas({novel_id!r}) failed at entity #{idx} ({label}) with no"
            f" prior commit this run: {exc}"
        ) from exc

    store.conn.commit()
    return report


def _big_five_str(p: TraitProfile) -> str:
    return (
        f"o={p.openness:.2f},c={p.conscientiousness:.2f},e={p.extraversion:.2f},"
        f"a={p.agreeableness:.2f},n={p.neuroticism:.2f}"
    )


def load_trait_profiles(
    novel_id: str, store: Store, *, position: float | None = None
) -> dict[str, TraitProfile]:
    """Rebuild trait profiles from stored persona attributes.

    Lets voice casting run as its own stage against an already-built graph
    instead of only inside the same process that built the personas.

    `position`, when given, selects which body's attribute rows to read via
    `persona_at(..., position)` -- the same pattern
    `world/context.py::_appearance_brief` already uses for appearance (Core
    Pipeline Hardening #8.1/#14). `position=None` (the default, and what
    every caller passes today) keeps "their latest body", which is a real,
    stated limitation, not a fixed one: `build_personas` currently computes
    one trait profile per *entity* and writes that same profile's values to
    every body epoch, so a transmigrated character's traits do not actually
    differ by body yet even once this accessor is asked for a specific
    position -- the write side, not this read side, is the remaining gap.
    See HANDOFF for the follow-up (rework `build_personas` to gather
    evidence and infer traits per epoch, the way `extract_appearance`
    already does per body for appearance).
    """
    out: dict[str, TraitProfile] = {}
    for entity in store.all_selves(novel_id):
        if not entity.kind.is_person:
            continue
        persona_id = persona_at(store, entity.id, position)
        # whole-novel values: voice casting must commit before the narration states a gender (REPORT 8)
        attrs = standing_values(store, persona_id)
        if not attrs:
            continue
        profile = TraitProfile(
            target_id=entity.id,
            label=entity.canonical_label,
            age_band=attrs.get("age_band", "adult"),
            gender=attrs.get("gender", "unknown"),
            register=attrs.get("register", "neutral"),
            prominence=entity.prominence,
            provenance=attrs.get("trait_provenance", "deterministic"),
        )
        for part in attrs.get("big_five", "").split(","):
            key, _, value = part.partition("=")
            field_name = {
                "o": "openness", "c": "conscientiousness", "e": "extraversion",
                "a": "agreeableness", "n": "neuroticism",
            }.get(key.strip())
            if field_name and value:
                setattr(profile, field_name, float(value))
        out[entity.id] = profile
    return out
