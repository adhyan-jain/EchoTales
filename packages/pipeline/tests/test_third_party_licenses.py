"""THIRD_PARTY_LICENSES.md must not drift from the engine registry and the voice banks.

The registry (`engines/registry.py`) and `voice/bank.py::BANK_LICENCES` are the sources of truth; this file is the human
copy. An entry added there with a stated licence and forgotten here is how the doc kept naming VCTK as the bank.
"""

from __future__ import annotations

import re
from pathlib import Path

from echotales.pipeline.engines.registry import ENGINES
from echotales.pipeline.voice.bank import BANK_LICENCES

DOC = Path(__file__).resolve().parents[3] / "THIRD_PARTY_LICENSES.md"
#: How the doc names an engine whose registry name is not how a person writes it.
ALIASES = {
    "cv": "OpenCV",
    "z-image-turbo": "Z-Image Turbo",
    "lama": "LaMa",
    "depth-anything-v2-small": "Depth Anything V2 Small",
}
#: Licence strings that state no third-party licence: unchecked, a hosted service's terms, or this repository's own.
NOT_THIRD_PARTY = ("unchecked", "hosted service terms", "this repository")


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_every_registry_engine_with_a_stated_licence_is_listed() -> None:
    doc = _doc().casefold()
    missing = sorted(
        {
            e.name
            for e in ENGINES
            if not any(marker in e.licence for marker in NOT_THIRD_PARTY)
            and ALIASES.get(e.name, e.name).casefold() not in doc
        }
    )
    assert not missing, f"engines with a licence in the registry but absent from THIRD_PARTY_LICENSES.md: {missing}"


def test_the_listed_licence_matches_the_registry_for_each_row() -> None:
    rows = {line.split("|")[1].strip().casefold(): line for line in _doc().splitlines() if line.startswith("| ")}
    for e in ENGINES:
        if any(marker in e.licence for marker in NOT_THIRD_PARTY):
            continue
        key = ALIASES.get(e.name, e.name).casefold()
        row = next((line for name, line in rows.items() if key in name), None)
        if row is None or e.commercial_safe is None:
            continue  # a row marked "verify" does not claim the registry's value
        first = re.split(r"[ (;]", e.licence)[0]
        assert first.casefold() in row.casefold() or "non-commercial" in row.casefold(), (e.name, e.licence, row)


def test_every_voice_bank_licence_is_in_the_doc() -> None:
    doc = _doc()
    for bank, licence in BANK_LICENCES.items():
        if bank == "audiobook":
            continue  # the combination of the two below it
        assert licence.split(" 1.0")[0].split(" 4.0")[0] in doc, (bank, licence)
    assert "Hi-Fi TTS" in doc and "OpenSLR 109" in doc and "LibriTTS-R" in doc


def test_vctk_is_not_named_as_the_default_bank() -> None:
    doc = _doc()
    assert "VCTK 0.92 (default bank)" not in doc
    assert "default bank is `audiobook`" in doc


def test_the_benchmark_and_font_credits_are_present() -> None:
    doc = _doc()
    for needle in ("Pepper&Carrot", "David Revoy", "CC BY 4.0", "Comic Neue", "Bangers", "Open Font License"):
        assert needle in doc, needle
