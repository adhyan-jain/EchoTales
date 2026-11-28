"""The 13 hand-built RI ch1 panels of the art-drama bake-off (docs/results/ART_DRAMA.md).

Built by hand from the owner gold (`data/gold/segment/ri_ch1_owner.json`) and the text facts in
`docs/results/MANHWA_DIRECTING_PATTERNS.md`, so the cast is exactly right (clan head middle-aged in white ceremonial robe,
elders in loose white garments, reborn Fang Yuan 15 with soft pale palms, the eyes panel with no identity) and the bake-off
isolates the ART from director errors. Not a test file (leading underscore): the bake-off script imports it.

The brief asked for 12 panels but listed 13 items; all 13 are here.

Flagged inventions (never plot facts): the cliff hair colour/style, the accuser's face, and Bai Ning Bing's look (no dossier look
exists yet in this checkout, so a white-clad look with a cold glow is used and marked `invented_look=True`). In this story time he is male (v2: the v1 fixture said female and the sheet drew a woman).."""

from __future__ import annotations

from dataclasses import dataclass, field

from echotales.pipeline.render.compiler import CharacterBrief, CrowdBrief, OutputMode, PanelBrief
from echotales.pipeline.render.lightgrade import light_grade
from echotales.pipeline.storyboard.schema import (
    CastMember,
    Layer,
    Letter,
    LetterKind,
    Panel,
    Purpose,
    Shape,
    Shot,
)

_SHOT_WORD = {Shot.EXTREME_WIDE: "wide", Shot.WIDE: "wide", Shot.OVERHEAD: "wide", Shot.LOW_ANGLE: "wide", Shot.MEDIUM: "medium",
              Shot.MEDIUM_CLOSE: "medium", Shot.CLOSE: "close", Shot.EXTREME_CLOSE: "close", Shot.INSERT: "close"}


@dataclass
class BakeoffPanel:
    panel: Panel
    brief: PanelBrief
    #: NoobAI tag inputs (arm C/D): who, and the scene, as tags.
    identity_tags: list[str] = field(default_factory=list)
    scene_tags: list[str] = field(default_factory=list)
    crowd: bool = False
    gender_tag: str = "boy"
    invented_look: bool = False
    note: str = ""

    @property
    def panel_id(self) -> str:
        return self.panel.panel_id


def _panel(pid: str, seg: str, layer: Layer, purpose: Purpose, shape: Shape, shot: Shot, visual: str,
           cast: list[tuple[str, bool]] | None = None, letters: list[Letter] | None = None, blocks: list[int] | None = None) -> Panel:
    return Panel(
        panel_id=pid, segment_id=seg, layer=layer, purpose=purpose, shape=shape, shot=shot, visual=visual,
        cast=[CastMember(entity_id=n.lower().replace(" ", "_"), name=n, invented=inv) for n, inv in (cast or [])],
        letters=letters or [], source_blocks=blocks or [],
    )


def _person(name: str, gender: str, band: str, hair: str, attire: str, *, condition: str = "", years: int = 0, expr: str = "",
            eyes: str = "", features: str = "") -> CharacterBrief:
    app = {"hair": hair}
    if features:
        app["features"] = features
    if eyes:
        app["eyes"] = eyes
    return CharacterBrief(name=name, gender=gender, age_band=band, appearance=app, attire=attire, condition=condition,
                          age_years=years, stated_expression=expr, lead=True)


def _brief(panel: Panel, who: list[CharacterBrief], comp: str, *, light: str, mood: str = "", crowd: CrowdBrief | None = None,
           place: str = "", focus: str = "", empty_hands: bool = False) -> PanelBrief:
    # Novel id "" is the RI/xianxia vocabulary (`persona.genre.genre_of`), which is what these panels want without a store.
    return PanelBrief(
        novel_id="", characters=who, crowd=crowd, location=place, shot=_SHOT_WORD[panel.shot], mood=mood, mode=OutputMode.COLOUR,
        composition=comp, staging=f"Light: {light}", lighting=light, frame_focus=focus, empty_hands=empty_hands,
        grade=light_grade(f"Light: {light}", comp, mood=mood), manhua=False,
    )


def bakeoff_panels() -> list[BakeoffPanel]:
    out: list[BakeoffPanel] = []

    def add(panel: Panel, brief: PanelBrief, **kw) -> None:
        out.append(BakeoffPanel(panel, brief, **kw))

    # ---- scene 1: the cliff (prior loop, layer PAST)
    fy = _person("Fang Yuan", "male", "adult", "long black hair", "a torn deep-green robe soaked with blood",
                 condition="wounded and bloody, a pool of blood beneath his feet", expr="a cold mocking smile")
    p = _panel("p01_hero", "s1", Layer.PAST, Purpose.HERO, Shape.TALL, Shot.LOW_ANGLE,
               "Fang Yuan stands alone on a cliff edge, bloody, in a torn deep-green robe, a pool of blood at his feet, wind tearing his robe",
               [("Fang Yuan", False)], blocks=[0, 1])
    add(p, _brief(p, [fy], "Fang Yuan stands alone at the edge of a bare cliff, his torn deep-green robe soaked in blood, a wide pool "
                  "of blood spreading beneath his feet, wind tearing at his hair and robe, far below him rows of fighters in pale robes.",
                  light="a blood-red dusk sky behind the cliff", mood="grim, hostile", place="a cliff edge at dusk"),
        identity_tags=["fang yuan", "1boy", "long black hair", "torn green robe", "chinese clothes", "blood on clothes", "blood on face", "blood pool"],
        scene_tags=["cliff", "mountain", "sunset", "red sky", "wind"], note="HERO: low angle, tall")

    acc = _person("The accuser", "male", "middle-aged", "grey-streaked black topknotted", "pale grey sect robes",
                  expr="a snarl of hatred, teeth bared")
    p = _panel("p02_accuser", "s1", Layer.PAST, Purpose.CROWD_INDIVIDUAL, Shape.STANDARD, Shot.CLOSE,
               "an individual accuser from the besieging crowd shouts with hatred, close-up", [("The accuser", True)],
               [Letter(kind=LetterKind.SHOUT, text="You killed my master!")], [5])
    add(p, _brief(p, [acc], "A middle-aged fighter in pale grey sect robes shouts in hatred, teeth bared, his face lit from the side "
                  "by a red sky, the blurred shapes of other fighters behind him.", light="a blood-red dusk sky", mood="hostile",
                  place="a cliff at dusk"),
        identity_tags=["1boy", "middle-aged", "topknot", "grey robe", "angry", "shouting", "teeth", "clenched teeth"],
        scene_tags=["red sky", "blurry background", "crowd behind"], note="invented crowd face, never a plot actor")

    p = _panel("p03_overhead", "s1", Layer.PAST, Purpose.BEAT, Shape.WIDE, Shot.OVERHEAD,
               "the encircling crowd seen from directly above, packed in rows around one small bloodied figure",
               [("Fang Yuan", False)], blocks=[2, 3])
    add(p, _brief(p, [_person("Fang Yuan", "male", "adult", "long black hair", "a torn deep-green robe soaked with blood")],
                  "Seen from directly above, a small bloodied man in a deep-green robe stands alone on a rock platform, and dozens of "
                  "fighters in pale robes are packed in rows on every side of him, all of them facing him, weapons drawn.",
                  light="a red dusk sky, long shadows", mood="menacing", place="a cliff-top platform",
                  crowd=CrowdBrief("fighters in pale robes", size="many", count=40, stance="stand packed in rows facing him, weapons drawn")),
        identity_tags=["fang yuan", "green robe", "blood"], scene_tags=["from above", "crowd", "cliff", "red sky", "weapons"],
        crowd=True, note="crowd seen from overhead")

    p = _panel("p04_laugh", "s1", Layer.PAST, Purpose.EXTREME_CLOSE, Shape.BLEED, Shot.EXTREME_CLOSE,
               "Fang Yuan's laugh, extreme close-up of the mouth and eyes, blood on his teeth", [("Fang Yuan", False)],
               [Letter(kind=LetterKind.SFX, text="HA HA HA")], [20])
    add(p, _brief(p, [_person("Fang Yuan", "male", "adult", "long black hair", "a torn deep-green robe", condition="blood on his lips and teeth",
                              expr="a wide mad laugh with blood on the teeth")],
                  "Extreme close-up of Fang Yuan's face, his mouth wide open in a mad laugh, blood on his teeth, one wild eye in focus.",
                  light="a blood-red sky", mood="manic"),
        identity_tags=["fang yuan", "1boy", "long black hair", "laughing", "open mouth", "blood on teeth", "crazy eyes"],
        scene_tags=["extreme close-up", "red background"], note="extreme close-up, SFX")

    p = _panel("p05_detonation", "s1", Layer.PAST, Purpose.TRANSITION, Shape.BLEED, Shot.WIDE,
               "the self-detonation: a blinding burst of light erupts on the cliff, shock-wave tearing the sky and the rock",
               [], [Letter(kind=LetterKind.SFX, text="BOOM")], [29])
    add(p, _brief(p, [], "A blinding white-gold explosion of light erupts at the top of a cliff, a shock-wave tearing through the clouds "
                  "and shattering the rock, debris flung outward, light streaking down the mountain.",
                  light="a blinding white explosion of light", mood="catastrophic", place="a cliff-top"),
        identity_tags=[], scene_tags=["explosion", "light beam", "shockwave", "cliff", "debris", "clouds", "glowing", "no humans"],
        note="self-detonation light, no identity")

    # ---- scene 2: the rain-night village (PRESENT, main timeline)
    p = _panel("p06_village", "s2", Layer.PRESENT, Purpose.ESTABLISHING, Shape.WIDE, Shot.EXTREME_WIDE,
               "a mountain village at night in spring rain, lanterns glowing in the windows", [], blocks=[31])
    add(p, _brief(p, [], "A mountain village of stone and wooden houses seen at night in the spring rain, lanterns glowing in the "
                  "windows, a stone path climbing the dark mountain, rain falling in streaks.",
                  light="night, spring rain, glowing lanterns", mood="quiet", place="a mountain village at night in the rain"),
        identity_tags=[], scene_tags=["village", "night", "rain", "lantern", "mountain", "scenery", "no humans"],
        note="establishing, calm")

    ch = _person("The clan head", "male", "middle-aged", "black topknotted", "a white ceremonial robe",
                 expr="solemn and tired")
    p = _panel("p07_clanhead", "s2", Layer.PRESENT, Purpose.BEAT, Shape.STANDARD, Shot.MEDIUM,
               "the clan head, middle-aged, in a white ceremonial robe, prays kneeling before rows of ancestral tablets by candlelight",
               [("The clan head", False)], blocks=[37, 38])
    add(p, _brief(p, [ch], "A middle-aged man in a white ceremonial robe kneels with his palms pressed together in prayer before "
                  "rows of wooden ancestral tablets on an altar, candles burning in front of them.",
                  light="candlelight in a dark temple at night", mood="solemn", place="an ancestral temple at night",
                  empty_hands=False),
        identity_tags=["1boy", "middle-aged", "white robe", "chinese clothes", "kneeling", "praying", "topknot", "beard"],
        scene_tags=["temple", "altar", "candles", "tablets", "night", "indoors"], note="calm beat: should keep calmer light")

    p = _panel("p08_elders", "s2", Layer.PRESENT, Purpose.BEAT, Shape.WIDE, Shot.WIDE,
               "over ten elders kneel in rows in loose white garments behind the clan head", [], blocks=[39])
    add(p, _brief(p, [], "More than ten elders kneel in neat rows in loose white garments, facing the altar, seen from behind and above in "
                  "a dim temple hall.", light="dim candlelight in a temple hall at night", mood="solemn",
                  place="an ancestral temple hall at night",
                  crowd=CrowdBrief("elders in loose white garments", size="many", count=12, stance="kneel in rows facing the altar")),
        identity_tags=["multiple boys", "old man", "white robe", "kneeling", "from behind"], scene_tags=["temple", "hall", "candles", "night", "indoors"],
        crowd=True, note="rows, loose white garments")

    el = _person("An elder", "male", "elder", "long white", "loose white ceremonial garments",
                 expr="grave, speaking", features="a long white beard")
    p = _panel("p09_elder", "s2", Layer.PRESENT, Purpose.DIALOGUE, Shape.STANDARD, Shot.MEDIUM_CLOSE,
               "an elder in loose white garments speaks gravely", [("An elder", False)],
               [Letter(kind=LetterKind.SPEECH, text="The Bai clan's talent is the worry.")], [55])
    add(p, _brief(p, [el], "An old man with long white hair and a white beard, in loose white garments, speaks gravely, one hand raised.",
                  light="dim candlelight in a temple at night", mood="grave", place="an ancestral temple at night"),
        identity_tags=["1boy", "old man", "white hair", "white beard", "white robe", "chinese clothes", "serious"],
        scene_tags=["temple", "candles", "night", "indoors"], note="dialogue, calm")

    bnb = _person("Bai Ning Bing", "male", "youth", "long straight black hair", "a flowing white robe with pale sleeves",
                  expr="cold and composed")
    p = _panel("p10_bainingbing", "s2", Layer.IMAGINED, Purpose.REFERENCED_INSET, Shape.INSET, Shot.MEDIUM,
               "Bai Ning Bing, imagined: a silent young man in white with a cold glow around him", [("Bai Ning Bing", False)], blocks=[55])
    add(p, _brief(p, [bnb], "A young man in a flowing white robe stands alone and silent in darkness, a cold pale glow surrounding "
                  "him, his face calm and distant, as if pictured in someone's mind.",
                  light="a cold pale glow in darkness", mood="distant"),
        identity_tags=["1boy", "solo", "long black hair", "white robe", "chinese clothes", "glowing", "cold", "expressionless"],
        scene_tags=["dark background", "glow"], gender_tag="boy", invented_look=True,
        note="INVENTED LOOK: no dossier look exists in this checkout; white-clad, cold glow")

    p = _panel("p11_garret", "s2", Layer.PRESENT, Purpose.BEAT, Shape.STANDARD, Shot.MEDIUM,
               "the clan head at his garret window looks out over the village lights in the rain", [("The clan head", False)], blocks=[73, 78])
    add(p, _brief(p, [_person("The clan head", "male", "middle-aged", "black topknotted", "a white ceremonial robe",
                              expr="pensive")],
                  "A middle-aged man in a white ceremonial robe stands at a small garret window with his hand on the frame, looking out "
                  "at the village lights glimmering in the night rain.",
                  light="night, a dim lamp behind him, rain at the window", mood="pensive", place="a garret room at night"),
        identity_tags=["1boy", "middle-aged", "white robe", "chinese clothes", "topknot", "window", "looking outside"],
        scene_tags=["garret", "night", "rain", "village lights", "indoors"], note="calm beat")

    p = _panel("p12_eyes", "s3", Layer.PRESENT, Purpose.EXTREME_CLOSE, Shape.WIDE, Shot.EXTREME_CLOSE,
               "a pair of clear eyes, extreme close-up of the eyes only, no identity", [], blocks=[79])
    add(p, _brief(p, [], "An extreme close-up of a pair of clear, bright young eyes only, reflecting the glimmer of lantern light, "
                  "nothing else of the face in frame.", light="night, glimmering lantern light reflected in the eyes", mood="intent",
                  focus="eyes"),
        identity_tags=[], scene_tags=["extreme close-up", "eyes", "eye focus", "reflection", "night"], note="withheld identity, eyes only")

    fyy = _person("Fang Yuan", "male", "youth", "black hair", "a plain dark blue robe", condition="soft, pale palms", years=15,
                  expr="startled, then intent")
    p = _panel("p13_young", "s3", Layer.PRESENT, Purpose.BEAT, Shape.TALL, Shot.MEDIUM,
               "young Fang Yuan, fifteen, at his window in the rain, soft pale palms, wind and rain at the sill", [("Fang Yuan", False)], blocks=[80, 83])
    add(p, _brief(p, [fyy], "A fifteen-year-old boy stands at a window in the night rain, looking at his own soft, pale palms, rain "
                  "blowing in over the sill.", light="night, rain at the window, dim lamplight", mood="stunned",
                  place="a small room at night in the rain"),
        identity_tags=["fang yuan", "1boy", "15 years old", "teenager", "black hair", "blue robe", "chinese clothes", "looking at hands", "window"],
        scene_tags=["night", "rain", "indoors", "wind"], note="young: 15, soft pale palms")
    return out
