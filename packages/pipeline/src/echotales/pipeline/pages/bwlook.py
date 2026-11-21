"""Black-and-white manga look for an already-rendered colour panel (`echotales pages --look bw`, EVOLUTION 4.187).

Why: the colour render is the product, but a black-and-white manga page is a second demo, and when only colour panels exist the
cheap route is to convert them instead of drawing again. The conversion is what a manga page is made of: luminance, a levels
step that crushes the darks to solid ink and blows the highlights to paper, and a 45 degree dot screen (screentone) on the tones
between. Lettering is drawn on the page afterwards, so it stays black on white and is never screened.

It runs on the picture already fitted to its place on the page, not on the source panel: a dot screen resampled by the layout
turns into moire and grey smears, so the dots have to be laid at the size they are printed.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

#: Luminance at or below which a pixel is solid ink, and at or above which it is paper; the dot screen fills what lies between.
BLACK_POINT = 0.20
WHITE_POINT = 0.80
#: Dot pitch as a fraction of the picture's width, so a tone looks the same on a phone-sized and a print-sized page, and its floor in
#: pixels (a screen finer than this is below what a screen or a printer resolves as a dot).
DOT_PITCH = 1 / 170
MIN_DOT_PITCH_PX = 4


def to_manga_bw(img: Image.Image, *, pitch: int | None = None) -> Image.Image:
    """`img` as ink and paper only (mode `L`, values 0 and 255): crushed blacks, white highlights, dot-screened midtones."""
    lum = np.asarray(img.convert("L"), dtype=np.float32) / 255.0
    lum = np.clip((lum - BLACK_POINT) / (WHITE_POINT - BLACK_POINT), 0.0, 1.0)
    h, w = lum.shape
    cell = float(pitch or max(MIN_DOT_PITCH_PX, round(w * DOT_PITCH)))
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = (x + y) / np.sqrt(2.0), (x - y) / np.sqrt(2.0)  # the screen runs at 45 degrees, as printed screentone does
    screen = (np.cos(2 * np.pi * u / cell) + np.cos(2 * np.pi * v / cell)) / 4.0 + 0.5  # 0 at a dot's centre, 1 between dots
    paper = lum >= screen
    paper[lum <= 0.0] = False  # a crushed black has no white dot in it
    paper[lum >= 1.0] = True
    return Image.fromarray(np.where(paper, 255, 0).astype(np.uint8), mode="L")
