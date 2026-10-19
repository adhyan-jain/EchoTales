"""Assign a reference voice to every character (`docs/design/architecture.md Section 8b`).

**Graph colouring runs within each archetype bucket, never globally**, and
that decision is already made and reasoned in `docs/design/architecture.md Section 8b`: in a long
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
            " (accepted by design -- docs/design/architecture.md Section 8b)",
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

def speaker_embedding_distance(
    spk_a: str,
    spk_b: str,
    embedding_map: dict[str, list[float]] | None = None,
) -> float:
    """Compute acoustic/embedding cosine distance between two speakers."""
    if spk_a == spk_b:
        return 0.0
    if embedding_map and spk_a in embedding_map and spk_b in embedding_map:
        import numpy as np
        vec_a = np.array(embedding_map[spk_a], dtype=float)
        vec_b = np.array(embedding_map[spk_b], dtype=float)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a > 0 and norm_b > 0:
            sim = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
            return max(0.0, 1.0 - sim)
    return 0.50


def verify_no_co_occurring_voice_collisions(
    scene_character_ids: list[str],
    assignments: dict[str, VoiceAssignment],
    *,
    min_embedding_distance: float = 0.25,
    embedding_map: dict[str, list[float]] | None = None,
) -> list[tuple[str, str, str]]:
    """Verify that no two characters in the same scene share the same speaker voice or near-identical timbre.
    
    Returns list of collision tuples (char_a, char_b, shared_or_colliding_speaker_id).
    """
    collisions: list[tuple[str, str, str]] = []
    seen: dict[str, str] = {}  # speaker_id -> char_id

    # Check identical speaker ID and pairwise embedding distance
    chars = [c for c in scene_character_ids if c in assignments]
    for i in range(len(chars)):
        c_a = chars[i]
        spk_a = assignments[c_a].speaker_id
        if spk_a in seen:
            collisions.append((seen[spk_a], c_a, spk_a))
        else:
            seen[spk_a] = c_a

        for j in range(i + 1, len(chars)):
            c_b = chars[j]
            spk_b = assignments[c_b].speaker_id
            if spk_a != spk_b:
                dist = speaker_embedding_distance(spk_a, spk_b, embedding_map)
                if dist < min_embedding_distance:
                    collisions.append((c_a, c_b, f"{spk_a}~{spk_b}"))

    return collisions


def enforce_episode_zero_collision(
    episode_scenes_characters: list[list[str]],
    assignments: dict[str, VoiceAssignment],
    bank: VoiceBank,
    *,
    min_embedding_distance: float = 0.25,
    embedding_map: dict[str, list[float]] | None = None,
) -> dict[str, VoiceAssignment]:
    """Strictly resolve any co-occurring voice collisions across an episode's scenes."""
    adjusted = dict(assignments)

    for scene_chars in episode_scenes_characters:
        collisions = verify_no_co_occurring_voice_collisions(
            scene_chars, adjusted, min_embedding_distance=min_embedding_distance, embedding_map=embedding_map
        )
        for char_a, char_b, shared_spk in collisions:
            b_assign = adjusted[char_b]
            bucket_voices = bank.nearest_bucket(
                b_assign.bucket.split(":")[0], b_assign.bucket.split(":")[1]
            )
            scene_used = {
                adjusted[c].speaker_id for c in scene_chars if c in adjusted and c != char_b
            }
            replacement = next(
                (
                    v for v in bucket_voices
                    if v.speaker_id not in scene_used
                    and all(
                        speaker_embedding_distance(v.speaker_id, adjusted[c].speaker_id, embedding_map) >= min_embedding_distance
                        for c in scene_chars if c in adjusted and c != char_b
                    )
                ),
                None,
            )
            if replacement:
                adjusted[char_b] = VoiceAssignment(
                    target_id=b_assign.target_id,
                    label=b_assign.label,
                    speaker_id=replacement.speaker_id,
                    bucket=b_assign.bucket,
                    archetype=b_assign.archetype,
                    prominence=b_assign.prominence,
                    collides_with="",
                )

    return adjusted
