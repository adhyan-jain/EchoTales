"""Assign a reference voice to every character (`architecture.md Section 8b`).

**Graph colouring runs within each archetype bucket, never globally**, and
that decision is already made and reasoned in `architecture.md Section 8b`: in a long
cultivation novel the co-occurrence graph over principal characters is close
to complete, so the chromatic number exceeds any archetype-appropriate
palette and global collision-free assignment is not achievable. A young
female disciple and an elderly male patriarch never needed distinct colours
anyway -- their timbres already differ.

What follows from that, and is honoured here:

- Characters are coloured only against others **in their own bucket**.
- Residual collisions between non-co-occurring minor characters in one bucket
  are **accepted and explicitly logged** (`CastingReport.collisions`).
- The system does **not** claim global collision-free assignment, and
  `CastingReport.summary()` says so in the output rather than in a comment
  nobody reads.

Principals are coloured first, so when a bucket runs short of voices the
reuse lands on incidental characters -- the ones a listener is least likely
to be tracking by voice.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from echotales.core.enums import Prominence
from echotales.core.store import Store
from echotales.pipeline.persona.traits import TraitProfile
from echotales.pipeline.voice.bank import BankVoice, VoiceBank

#: Deterministic by default: re-running casting must not silently recast a
#: novel whose audio is half-rendered.
DEFAULT_SEED = 20260812


@dataclass(slots=True)
class VoiceAssignment:
    target_id: str
    label: str
    speaker_id: str
    bucket: str
    archetype: str
    prominence: Prominence
    #: True when this voice is already used by a character sharing a scene.
    #: Kept rather than avoided-at-all-costs: Section 8b accepts residual collisions
    #: and requires them to be visible.
    collides_with: str = ""


@dataclass(slots=True)
class CastingReport:
    novel_id: str
    assigned: int = 0
    collisions: list[tuple[str, str]] = field(default_factory=list)
    bucket_pressure: dict[str, tuple[int, int]] = field(default_factory=dict)

    def summary(self) -> str:
        pressure = ", ".join(
            f"{bucket}={chars}chars/{voices}voices"
            for bucket, (chars, voices) in sorted(self.bucket_pressure.items())
        ) or "none"
        lines = [
            f"{self.novel_id}: {self.assigned:,} characters cast",
            f"  bucket pressure: {pressure}",
            f"  co-occurring same-voice collisions: {len(self.collisions)}"
            " (accepted by design -- architecture.md Section 8b)",
        ]
        for a, b in self.collisions[:5]:
            lines.append(f"    {a} shares a voice with {b}")
        return "\n".join(lines)


def co_occurrence(store: Store, novel_id: str) -> dict[str, set[str]]:
    """Which entities share a chapter with which.

    Chapter granularity rather than scene: casting is a whole-novel decision
    and two characters who share any chapter are likely enough to share a
    scene that treating them as adjacent is the safe read. Scene-level
    precision would let more voices be reused, which is the wrong direction
    to optimise when the bank is the scarce resource.
    """
    by_chapter: dict[float, set[str]] = {}
    for row in store.conn.execute(
        "SELECT DISTINCT chapter, target_id FROM mention"
        " WHERE novel_id=? AND target_id IS NOT NULL",
        (novel_id,),
    ):
        by_chapter.setdefault(float(row["chapter"]), set()).add(row["target_id"])

    graph: dict[str, set[str]] = {}
    for cast in by_chapter.values():
        for entity in cast:
            graph.setdefault(entity, set()).update(cast - {entity})
    return graph


def cast_voices(
    novel_id: str,
    profiles: dict[str, TraitProfile],
    bank: VoiceBank,
    *,
    store: Store | None = None,
    seed: int = DEFAULT_SEED,
) -> tuple[dict[str, VoiceAssignment], CastingReport]:
    """Colour the cast within buckets and return one assignment per character."""
    report = CastingReport(novel_id=novel_id)
    rng = random.Random(seed)
    adjacency = co_occurrence(store, novel_id) if store is not None else {}

    # Principals first, then by descending prominence, then by label for a
    # stable order independent of dict iteration.
    rank = {Prominence.PRINCIPAL: 0, Prominence.RECURRING: 1, Prominence.INCIDENTAL: 2}
    ordered = sorted(
        profiles.values(), key=lambda p: (rank.get(p.prominence, 3), p.label)
    )

    assignments: dict[str, VoiceAssignment] = {}
    used_in_bucket: dict[str, dict[str, str]] = {}

    for profile in ordered:
        candidates = bank.nearest_bucket(profile.gender, profile.age_band)
        if not candidates:
            continue
        bucket = f"{profile.gender}:{profile.age_band}"
        taken = used_in_bucket.setdefault(bucket, {})

        neighbours = adjacency.get(profile.target_id, set())
        neighbour_voices = {
            assignments[n].speaker_id for n in neighbours if n in assignments
        }

        # Prefer a voice no scene-partner is using and that is least reused in
        # this bucket overall; `rng` only breaks ties, so casting stays
        # deterministic for a given seed.
        def cost(voice: BankVoice) -> tuple[int, int, float]:
            return (
                1 if voice.speaker_id in neighbour_voices else 0,
                sum(1 for v in taken.values() if v == voice.speaker_id),
                rng.random(),
            )

        chosen = min(candidates, key=cost)
        collision = ""
        if chosen.speaker_id in neighbour_voices:
            collision = next(
                (
                    assignments[n].label
                    for n in neighbours
                    if n in assignments and assignments[n].speaker_id == chosen.speaker_id
                ),
                "",
            )
            report.collisions.append((profile.label, collision))

        assignments[profile.target_id] = VoiceAssignment(
            target_id=profile.target_id,
            label=profile.label,
            speaker_id=chosen.speaker_id,
            bucket=bucket,
            archetype=profile.archetype,
            prominence=profile.prominence,
            collides_with=collision,
        )
        taken[profile.target_id] = chosen.speaker_id
        report.assigned += 1

    buckets = bank.by_bucket()
    for bucket, members in used_in_bucket.items():
        report.bucket_pressure[bucket] = (len(members), len(buckets.get(bucket, [])))

    return assignments, report
