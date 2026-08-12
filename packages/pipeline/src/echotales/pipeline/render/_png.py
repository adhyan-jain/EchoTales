"""Minimal, dependency-free PNG writer shared by the stub image/motion engines.

Pillow is not a project dependency -- `voice/engine.py::StubEngine` gets real
WAV files for free via the stdlib `wave` module, and this is the image-format
equivalent: raw `zlib`/`struct`, no third-party import, so the stub path
(`panels.py::StubImageEngine`, `motion.py::StubMotionEngine`) never needs the
`render` ML extras installed.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def write_solid_png(path: Path, width: int, height: int, colour: tuple[int, int, int]) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data))
        )

    row = bytes([0]) + bytes(colour) * width  # filter byte, then RGB per pixel
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
