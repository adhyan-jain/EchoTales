"""The local image worker's GPU-free parts: size fitting and the provider switch (no model is loaded)."""

from __future__ import annotations

import base64

import pytest
from echotales.pipeline import workers_contract as wc
from echotales.pipeline import workers_local as wl
from echotales.pipeline.workers_contract import ImageWorkerRequest, ImageWorkerResponse


def test_requests_are_scaled_to_the_pixel_budget_in_multiples_of_64() -> None:
    assert wl.fit_size(1920, 1080) == (1344, 768)  # the old turnaround sheet size, too big for the 8 GB card
    assert wl.fit_size(1080, 1920) == (768, 1344)
    assert wl.fit_size(832, 1216) == (832, 1216)  # already measured to fit
    assert wl.fit_size(1024, 1024) == (1024, 1024)
    for w, h in ((1920, 1080), (4000, 3000), (700, 900)):
        fw, fh = wl.fit_size(w, h)
        assert fw % 64 == 0 and fh % 64 == 0 and fw * fh <= wl.MAX_PIXELS


def test_the_worker_choice_never_defaults_to_a_flat_image_outside_stub_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A solid-colour image must not come out of a real run (owner, 2026-10-31): unset means the stub only in the
    project's stub mode, NoobAI otherwise, and an unknown value is an error, not a silent stub."""
    from echotales.pipeline import config

    seen: list[str] = []

    def fake(req: ImageWorkerRequest) -> ImageWorkerResponse:
        seen.append(req.prompt)
        return ImageWorkerResponse(image_b64="", seed=req.seed)

    monkeypatch.setattr(wl, "run_local_image_worker", fake)

    monkeypatch.delenv("ECHOTALES_IMAGE_WORKER", raising=False)
    monkeypatch.setattr(config, "_settings", config.Settings(llm_mode=config.LLMMode.STUB))
    stub = wc.run_image_worker(ImageWorkerRequest(prompt="x", width=64, height=64))
    assert stub.status == "COMPLETED" and base64.b64decode(stub.image_b64)[:4] == b"\x89PNG" and not seen

    monkeypatch.setattr(config, "_settings", config.Settings(llm_mode=config.LLMMode.LOCAL))
    wc.run_image_worker(ImageWorkerRequest(prompt="a boy"))
    assert seen == ["a boy"]  # real mode, variable unset: the real worker

    monkeypatch.setenv("ECHOTALES_IMAGE_WORKER", "stub")
    assert base64.b64decode(wc.run_image_worker(ImageWorkerRequest(prompt="s", width=64, height=64)).image_b64)[:4] == b"\x89PNG"
    monkeypatch.setenv("ECHOTALES_IMAGE_WORKER", "something-else")
    with pytest.raises(ValueError, match="not a worker"):
        wc.run_image_worker(ImageWorkerRequest(prompt="ignored"))
    assert seen == ["a boy"]
