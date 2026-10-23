"""Voice casting: no two voices that share a scene may collide."""

from __future__ import annotations

from echotales.core.enums import Prominence
from echotales.pipeline.voice.bank import BankVoice, VoiceBank
from echotales.pipeline.voice.casting import (
    VoiceAssignment,
    enforce_episode_zero_collision,
    verify_no_co_occurring_voice_collisions,
)


def test_casting_scene_collision_prevention() -> None:
    assignments = {
        "holmes": VoiceAssignment("holmes", "Holmes", "p225", "male:mature", "detective", Prominence.PRINCIPAL),
        "watson": VoiceAssignment("watson", "Watson", "p225", "male:mature", "doctor", Prominence.PRINCIPAL),
        "lestrade": VoiceAssignment("lestrade", "Lestrade", "p226", "male:mature", "inspector", Prominence.RECURRING),
    }

    # Holmes and Watson collide in the same scene
    collisions = verify_no_co_occurring_voice_collisions(["holmes", "watson"], assignments)
    assert len(collisions) == 1
    assert collisions[0] == ("holmes", "watson", "p225")

    # Holmes and Lestrade do not collide
    no_collisions = verify_no_co_occurring_voice_collisions(["holmes", "lestrade"], assignments)
    assert len(no_collisions) == 0

    # Test enforcement of zero collision
    bank = VoiceBank([
        BankVoice("p225", "male", 40, "english", "gentleman"),
        BankVoice("p226", "male", 45, "english", "inspector"),
        BankVoice("p227", "male", 50, "english", "scholar"),
    ])

    resolved = enforce_episode_zero_collision([["holmes", "watson"]], assignments, bank)
    after_collisions = verify_no_co_occurring_voice_collisions(["holmes", "watson"], resolved)
    assert len(after_collisions) == 0
    assert resolved["holmes"].speaker_id != resolved["watson"].speaker_id
