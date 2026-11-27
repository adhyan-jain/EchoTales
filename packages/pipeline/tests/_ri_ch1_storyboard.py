"""A hand-built, RI-ch1-like storyboard for the webtoon grammar renderer (docs/results/MANHWA_DIRECTING_PATTERNS.md).

Only structure and short invented caption text: no passage of the novel or of the reference manhua is copied.
Segment order follows the pattern doc's S1-S6: cold open, cliff siege with individualised accusers, time card,
memory montage, defiance and detonation, rain-night ritual with referenced insets, reveal with a name card.
"""

from __future__ import annotations

from echotales.pipeline.storyboard.schema import (
    CastMember,
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Segment,
    Shape,
    Shot,
    Storyboard,
)

HERO = CastMember(entity_id="hero", name="Hero")
ELDER = CastMember(entity_id="elder", name="Clan Head")


def _crowd(i: int) -> CastMember:
    return CastMember(entity_id=f"accuser{i}", name=f"Accuser {i}", invented=True)


def _p(pid, seg, layer, purpose, shape, letters=(), cast=(), shot=Shot.MEDIUM) -> Panel:
    return Panel(panel_id=pid, segment_id=seg, layer=layer, purpose=purpose, shape=shape, shot=shot,
                 cast=list(cast), letters=list(letters))


def L(kind, text, speaker=None):
    return Letter(kind=kind, text=text, speaker_id=speaker)


def ri_ch1_storyboard() -> Storyboard:
    K = LetterKind
    P, M, PA, IM = Layer.PRESENT, Layer.MEMORY, Layer.PAST, Layer.IMAGINED
    panels = [
        # S1 cold open
        _p("p01", "s1", P, Purpose.COLD_OPEN, Shape.BLEED, [L(K.SFX, "Ha ha ha!")]),
        _p("p02", "s1", P, Purpose.COLD_OPEN, Shape.TALL, [L(K.SFX, "Kill him!")]),
        # S2 cliff siege
        _p("p03", "s2", P, Purpose.ESTABLISHING, Shape.WIDE,
           [L(K.NARRATION, "The cliff edge. Every righteous sect has come for one man.")]),
        _p("p04", "s2", P, Purpose.CROWD_INDIVIDUAL, Shape.STANDARD,
           [L(K.SHOUT, "Hand it over, demon!", "accuser1")], [_crowd(1)], Shot.CLOSE),
        _p("p05", "s2", P, Purpose.CROWD_INDIVIDUAL, Shape.DIAGONAL,
           [L(K.SHOUT, "Your sins end today!", "accuser2")], [_crowd(2)], Shot.CLOSE),
        _p("p06", "s2", P, Purpose.CROWD_INDIVIDUAL, Shape.DIAGONAL,
           [L(K.DREAD, "You burned my master's hall.", "accuser3"), L(K.SPEECH, "Ten years I waited.", "accuser3")],
           [_crowd(3)], Shot.CLOSE),
        _p("p07", "s2", P, Purpose.INSERT, Shape.STANDARD, [L(K.SFX, "Splot")], shot=Shot.INSERT),
        _p("p08", "s2", P, Purpose.HERO, Shape.TALL,
           [L(K.NAME_CARD, "Fang Yuan | The Demon, 500 years of schemes"), L(K.WHISPER, "So many came for me.", "hero")],
           [HERO], Shot.LOW_ANGLE),
        _p("p09", "s2", P, Purpose.EXTREME_CLOSE, Shape.WIDE, [L(K.THOUGHT, "Still not enough to kill me.", "hero")],
           [HERO], Shot.EXTREME_CLOSE),
        _p("p10", "s2", P, Purpose.TIME_PLACE_CARD, Shape.TEXT_ONLY, [L(K.TIME_PLACE, "6 hours pass")]),
        _p("p11", "s2", P, Purpose.ESTABLISHING, Shape.WIDE, [L(K.POEM, "The morning is fine like hair, and night is like snow.")]),
        # S3 memory montage
        _p("p12", "s3", M, Purpose.MONTAGE, Shape.BLEED,
           [L(K.MEMORY, "All the memories of a life on Earth surfaced before my eyes.", "hero")], [HERO]),
        _p("p13", "s3", M, Purpose.MONTAGE, Shape.STANDARD, [L(K.MEMORY, "A quiet study. A long and ordinary life.", "hero")]),
        _p("p14", "s3", M, Purpose.MONTAGE, Shape.WIDE, [L(K.MEMORY, "Falling leaves over a grave.", "hero")]),
        _p("p15", "s3", M, Purpose.SYMBOLIC, Shape.TALL, [L(K.MEMORY, "And then, water, closing over everything.")]),
        # S4 defiance
        _p("p16", "s4", P, Purpose.INSERT, Shape.STANDARD, [L(K.SFX, "Crack")], shot=Shot.INSERT),
        _p("p17", "s4", P, Purpose.BEAT, Shape.DIAGONAL, [L(K.SHOUT, "I shall still be a demon in my next life!", "hero")],
           [HERO], Shot.CLOSE),
        _p("p18", "s4", P, Purpose.TRANSITION, Shape.BLEED, [L(K.SFX, "BOOM")]),
        # S5 ritual
        _p("p19", "s5", PA, Purpose.TIME_PLACE_CARD, Shape.TEXT_ONLY, [L(K.TIME_PLACE, "Gu Yue Village, a rainy night")]),
        _p("p20", "s5", PA, Purpose.ESTABLISHING, Shape.WIDE, [L(K.SFX, "tak tak")]),
        _p("p21", "s5", PA, Purpose.DIALOGUE, Shape.STANDARD,
           [L(K.NARRATION, "The clan head prays that the ceremony will draw talented young men.", "elder"),
            L(K.SPEECH, "We pray for outstanding talent.", "elder")], [ELDER]),
        _p("p22", "s5", IM, Purpose.REFERENCED_INSET, Shape.INSET, [L(K.SPEECH, "He is only a boy.", "elder")]),
        _p("p23", "s5", PA, Purpose.REACTION, Shape.STANDARD, [L(K.SPEECH, "Whether you succeed or fail.", "elder")],
           [ELDER]),
        _p("p24", "s5", PA, Purpose.BEAT, Shape.WIDE, [L(K.SFX, "THUD")]),
        # S6 reveal
        _p("p25", "s6", P, Purpose.ESTABLISHING, Shape.BLEED, [L(K.SFX, "Rumble")]),
        _p("p26", "s6", P, Purpose.HERO, Shape.TALL,
           [L(K.NAME_CARD, "Fang Yuan | Age 15, reborn"), L(K.NARRATION, "A young face at a rain-streaked window.", "hero"),
            L(K.THOUGHT, "Five hundred years, and I am back.", "hero")], [HERO]),
    ]
    segs = [Segment(segment_id=f"s{i}", chapter=1, block_from=0, block_to=0, layer=Layer.PRESENT) for i in range(1, 7)]
    return Storyboard(novel_id="RI", chapter=1, segments=segs, panels=panels)
