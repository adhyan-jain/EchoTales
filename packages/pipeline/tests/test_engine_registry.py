"""The engine registry replaces six hand-kept lists; these tests pin that it reproduces each one exactly.

Why: before the registry, adding an engine meant editing compute.py, jobs.py, cli.py, voice/engine.py and
render/motion.py in step, and the lists had already drifted (the CLI offered `runpod` on `render` but not on
`persona reference`). A test that names the old values means a registry edit that silently changes behaviour fails here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from echotales.pipeline import compute, jobs
from echotales.pipeline.engines import registry as reg

ROOT = Path(__file__).resolve().parents[3]


def test_every_entry_is_well_formed() -> None:
    seen = set()
    for e in reg.ENGINES:
        assert e.kind in reg.KINDS and e.tier in reg.TIERS and e.role in reg.ROLES
        assert (e.kind, e.name) not in seen
        seen.add((e.kind, e.name))
        assert e.licence, e.name
        # a speed without a source is an invented number
        assert (e.speed_seconds is None) == (e.speed_source is None), e.name


def test_replaced_lists_are_reproduced() -> None:
    assert reg.names("image", surface="render-image") == (
        "stub", "sdxl", "manga", "illustrious", "noobai", "refined", "runpod", "gemini", "openrouter")
    assert reg.http_image_engines() == frozenset({"stub", "sdxl", "illustrious", "noobai", "refined", "manga"})
    assert compute.LOCAL_ENGINES == frozenset({"sdxl", "illustrious", "noobai", "refined", "manga"})
    assert compute.HOSTED_ENGINES == frozenset({"runpod", "gemini", "openrouter"})
    assert compute.VIDEO_ENGINES == frozenset({"ltx-local"})
    assert jobs.VIDEO_ENGINES == ("stills", "ltx-local")
    assert compute.LLM_PROVIDERS == ("ollama", "runpod", "openai", "gemini", "anthropic", "gateway", "stub")
    assert compute.IMAGE_PROVIDERS == ("local", "runpod", "gemini", "openrouter", "stub")
    assert compute.SECONDS_PER_PANEL == {
        "stub": 0.3, "sdxl": 45.0, "illustrious": 45.0, "noobai": 45.0, "refined": 60.0, "manga": 60.0}
    assert reg.names("tts") == ("stub", "chatterbox")
    assert reg.names("video", surface="motion-clip") == ("stub", "svd")
    assert reg.names("ocr") == ("rapidocr", "easyocr")
    assert reg.names("inpaint") == ("cv", "lama")


def test_studio_local_order_is_kept() -> None:
    assert reg.studio_local_engines() == ["stub", "noobai", "illustrious", "sdxl"]


def test_commercial_safe_filter_never_includes_unverified() -> None:
    safe = reg.select(commercial_safe=True)
    assert safe and all(e.commercial_safe is True for e in safe)
    # NoobAI is documented non-commercial (THIRD_PARTY_LICENSES.md, D7)
    assert "noobai" not in {e.name for e in safe}
    assert "noobai" in {e.name for e in reg.select()}


def test_kind_filter() -> None:
    assert {e.kind for e in reg.select(kind="tts")} == {"tts"}
    with pytest.raises(ValueError):
        reg.select(kind="nonsense")


def test_ocr_implementations_match_registry() -> None:
    from echotales.pipeline.comic import ocr

    assert tuple(ocr.ENGINES) == reg.names("ocr")


def test_setup_script_licences_agree_with_registry() -> None:
    """setup.sh cannot run Python (its tests give it a PATH without one), so it keeps its own display; this keeps it honest."""
    text = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    lines = re.findall(r'echo "model\s+(.*?)"', text)
    checked = 0
    for line in lines:
        for e in reg.ENGINES:
            if e.setup_label and e.setup_label in line:
                checked += 1
                assert e.licence in line, f"{e.name}: setup.sh says something other than {e.licence!r}"
    assert checked >= 3


def test_cli_listing(capsys: pytest.CaptureFixture[str]) -> None:
    from echotales.pipeline.cli import main

    assert main(["engines", "--commercial-safe", "--kind", "tts"]) == 0
    out = capsys.readouterr().out
    assert "chatterbox" in out and "noobai" not in out
