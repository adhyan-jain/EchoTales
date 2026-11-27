"""Per-work style table for the storyboard webtoon renderer (data, not code).

Why a table: the grammar (docs/results/MANHWA_DIRECTING_PATTERNS.md section 3) is shared by every adapter but each
work picks its own look per item, e.g. RI's present layer is a black battle gutter while LotNB's lore layer is grey
ink on parchment. Another novel gets another `StyleTable` (or a JSON file via `from_dict`); nothing in the renderer
names a work. All lengths are written for a 1600 px wide strip and scaled by `width / 1600`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

RGB = tuple[int, int, int]
REF_WIDTH = 1600


@dataclass(frozen=True)
class LayerStyle:
    #: Gutter colour at the top and bottom of a gap (a gap fades prev.end -> next.start, so a layer change is a
    #: gradient, not a hard seam, and a memory gutter can be soft gold into near-white).
    gutter_start: RGB = (255, 255, 255)
    gutter_end: RGB = (255, 255, 255)
    #: Image grade name: none | memory | past | imagined | lore | dream (see storyboard_render.GRADES).
    grade: str = "none"
    sfx_fill: RGB = (220, 40, 70)
    sfx_edge: RGB = (255, 255, 255)
    caption_fill: RGB = (236, 233, 224)
    caption_ink: RGB = (60, 56, 50)
    caption_edge: RGB = (110, 105, 95)
    #: Inset frame colour for this layer's insets (imagined gets a cool glow on top of it).
    frame: RGB = (255, 255, 255)


def _default_layers() -> dict[str, LayerStyle]:
    return {
        # Present battle: black gutters, crimson SFX (RI slices 1-37, 71-89).
        "present": LayerStyle(gutter_start=(8, 8, 12), gutter_end=(8, 8, 12), sfx_fill=(226, 36, 66),
                              sfx_edge=(255, 255, 255), frame=(255, 255, 255)),
        # Past / ritual: white gutters, quiet cream captions (RI slices 90-157).
        "past": LayerStyle(gutter_start=(255, 255, 255), gutter_end=(250, 248, 243), grade="past",
                           sfx_fill=(30, 30, 34), sfx_edge=(255, 255, 255), frame=(20, 20, 24)),
        # Memory: soft gold into near-white, gold-and-deep-blue montage (RI slices 38-70).
        "memory": LayerStyle(gutter_start=(255, 232, 178), gutter_end=(255, 250, 238), grade="memory",
                             sfx_fill=(255, 196, 64), sfx_edge=(40, 36, 80), frame=(255, 220, 130)),
        # Lore prologue: parchment, ink-wash images, scroll captions (LotNB prologue).
        "lore": LayerStyle(gutter_start=(236, 222, 190), gutter_end=(230, 214, 178), grade="lore",
                           sfx_fill=(40, 36, 32), sfx_edge=(236, 222, 190), caption_fill=(226, 208, 168),
                           caption_ink=(50, 38, 24), caption_edge=(110, 84, 48), frame=(60, 48, 34)),
        "imagined": LayerStyle(gutter_start=(255, 255, 255), gutter_end=(250, 248, 243), grade="imagined",
                               sfx_fill=(60, 120, 220), sfx_edge=(255, 255, 255), frame=(150, 200, 255)),
        "dream": LayerStyle(gutter_start=(240, 232, 255), gutter_end=(252, 246, 255), grade="dream",
                            sfx_fill=(170, 110, 230), sfx_edge=(255, 255, 255), frame=(210, 180, 255)),
    }


@dataclass
class StyleTable:
    width: int = REF_WIDTH
    layers: dict[str, LayerStyle] = field(default_factory=_default_layers)
    #: Gap between two panels, by what the transition is. Tight inside a beat, long between beats, longest at a
    #: scene cut (pattern 10). `gap_layer_extra` is added when the layer also changes.
    gap_tight: int = 36
    gap_beat: int = 150
    gap_scene: int = 440
    gap_layer_extra: int = 120
    #: Panel height by shape (and optional purpose override) at the reference width.
    shape_height: dict[str, int] = field(default_factory=lambda: {
        "standard": 1100, "wide": 560, "tall": 1900, "diagonal": 1150, "inset": 800, "bleed": 1500, "text_only": 380,
    })
    purpose_height: dict[str, int] = field(default_factory=lambda: {
        "insert": 760, "extreme_close": 820, "reaction": 900, "establishing": 800, "crowd_individual": 1000,
    })
    #: Purposes tied tightly to the panel before them (an insert, a reaction, a close-up of a crowd face).
    tight_purposes: tuple[str, ...] = ("insert", "extreme_close", "reaction", "crowd_individual", "dialogue")
    diagonal_slant: int = 150
    inset_frame: int = 10
    bleed_fade: int = 160
    font_px: int = 46
    min_font_px: int = 34
    slice_target: int = 1350
    slice_min: int = 1000
    slice_max: int = 1700

    @property
    def scale(self) -> float:
        return self.width / REF_WIDTH

    def s(self, v: float) -> int:
        """A reference-width length scaled to this strip's width."""
        return max(1, round(v * self.scale))

    def layer(self, name: str) -> LayerStyle:
        return self.layers.get(name) or self.layers["present"]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> StyleTable:
        d = dict(d)
        layers = {
            k: LayerStyle(**{kk: tuple(vv) if isinstance(vv, list) else vv for kk, vv in v.items()})
            for k, v in d.pop("layers", {}).items()
        }
        if "tight_purposes" in d:
            d["tight_purposes"] = tuple(d["tight_purposes"])
        t = cls(**d)
        if layers:
            t.layers = {**t.layers, **layers}
        return t


DEFAULT_STYLE = StyleTable()
