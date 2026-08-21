"""Phase 7: build a `Persona` per character and profile it (Section 10 item 4).

Until this stage existed, `architecture.md Section 4`'s self/persona split had no
code on the persona side at all: `Persona` had a runner nowhere in the
pipeline, so nothing consumed the `SelfPersonaBinding` table and voice/image
work had nothing to bind to.

**One persona per self, for now, and that is a real limitation stated
plainly.** The split exists so that reincarnation, body-swap and sustained
disguise can put *two* personas on one self (LOTM's Zhou Mingrui / Klein
Moretti is the worked example in `architecture.md Section 4` and Section 4.15). Detecting
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
from echotales.core.models import Attribute
from echotales.core.store import Store
from echotales.pipeline.persona.split import (
    SplitReport,
    detect_body_changes,
    epochs_for,
    persona_at,
    write_epochs,
)
from echotales.pipeline.persona.traits import TraitProfile, infer_traits_deterministic

#: Below this many mentions an entity gets a deterministic profile only. A
#: model call per walk-on is exactly the per-entity equivalent of the
#: per-mention waste Section 3's budget rule forbids, and a character with three
#: mentions has almost no evidence to read anyway.
LLM_MENTION_FLOOR = 25

#: Prominence thresholds, by mention count. Drives generation budget
#: downstream (plans.md Section 6 Phase 8) and which characters earn a cloned voice
#: rather than a bank voice (`4b` step 4).
PRINCIPAL_FLOOR = 300
RECURRING_FLOOR = 30


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
    store: Store, novel_id: str, target_id: str, *, max_chapters: int = 12
) -> tuple[list[str], list[str], list[str], int]:
    """Spoken lines, narration samples, surface forms and dialogue count.

    Sampled across at most `max_chapters` chapters *where this entity actually
    appears* rather than the first N of the novel -- a character introduced at
    chapter 90 would otherwise be profiled from no evidence at all.
    """
    dialogue: list[str] = []
    narration: list[str] = []
    surfaces: set[str] = set()
    dialogue_total = 0

    chapters = store.chapters_for_target(novel_id, target_id, limit=max_chapters)
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


def build_personas(
    novel_id: str,
    store: Store,
    *,
    client: object | None = None,
    llm_mention_floor: int = LLM_MENTION_FLOOR,
) -> PersonaReport:
    """Mint a persona per character entity, bind it, and profile it.

    `client=None` runs the deterministic path throughout -- see
    `persona/traits.py` on why that is a supported mode and not a degradation.
    """
    report = PersonaReport(novel_id=novel_id)
    report.split = SplitReport(novel_id=novel_id)
    profiles: dict[str, TraitProfile] = {}

    for entity in store.all_selves(novel_id):
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
        )
        if client is not None and mention_count >= llm_mention_floor:
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
        )
        report.personas += len(epochs)
        report.bindings += len(epochs)

        # Traits are demographics and personality -- properties of the
        # *consciousness*, not of the body it currently wears -- so they are
        # written to every epoch rather than only the first. Appearance is
        # the opposite and is dated per attestation by
        # `appearance_extract`, which is why that stage picks its persona by
        # position and this one does not.
        for epoch in epochs:
            for key, value in (
                ("age_band", profile.age_band),
                ("gender", profile.gender),
                ("register", profile.register),
                ("archetype", profile.archetype),
                ("big_five", _big_five_str(profile)),
                ("trait_provenance", profile.provenance),
            ):
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
                        learned_at_pos=entity.first_attested_pos,
                        observer_id=OBSERVER_READER,
                        evidence=profile.evidence[:200],
                    ),
                )

        report.by_archetype[profile.archetype] = (
            report.by_archetype.get(profile.archetype, 0) + 1
        )
        profiles[entity.id] = profile

    store.conn.commit()
    return report


def _big_five_str(p: TraitProfile) -> str:
    return (
        f"o={p.openness:.2f},c={p.conscientiousness:.2f},e={p.extraversion:.2f},"
        f"a={p.agreeableness:.2f},n={p.neuroticism:.2f}"
    )


def load_trait_profiles(novel_id: str, store: Store) -> dict[str, TraitProfile]:
    """Rebuild trait profiles from stored persona attributes.

    Lets voice casting run as its own stage against an already-built graph
    instead of only inside the same process that built the personas.
    """
    out: dict[str, TraitProfile] = {}
    for entity in store.all_selves(novel_id):
        if not entity.kind.is_person:
            continue
        # Traits are body-independent, so any epoch answers -- but ask
        # `persona_at` rather than assuming `:body1`, so a re-split character
        # still resolves through one accessor.
        persona_id = persona_at(store, entity.id)
        attrs = {
            a.key: a.value
            for a in store.get_attributes(TargetKind.PERSONA, persona_id)
            if a.is_standing
        }
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
