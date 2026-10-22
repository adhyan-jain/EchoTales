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


def test_the_stub_is_the_default_and_the_env_switch_selects_the_local_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ECHOTALES_IMAGE_WORKER", raising=False)
    stub = wc.run_image_worker(ImageWorkerRequest(prompt="x", width=64, height=64))
    assert stub.status == "COMPLETED" and base64.b64decode(stub.image_b64)[:4] == b"\x89PNG"

    seen: list[str] = []

    def fake(req: ImageWorkerRequest) -> ImageWorkerResponse:
        seen.append(req.prompt)
        return ImageWorkerResponse(image_b64="", seed=req.seed)

    monkeypatch.setattr(wl, "run_local_image_worker", fake)
    monkeypatch.setenv("ECHOTALES_IMAGE_WORKER", "noobai")
    wc.run_image_worker(ImageWorkerRequest(prompt="a boy"))
    assert seen == ["a boy"]
    monkeypatch.setenv("ECHOTALES_IMAGE_WORKER", "something-else")
    wc.run_image_worker(ImageWorkerRequest(prompt="ignored", width=64, height=64))
    assert seen == ["a boy"]  # any other value is the stub


def test_a_gpu_that_is_not_free_is_refused_before_any_load(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "mem_get_info", lambda: (2 * 2**30, 8 * 2**30))
    with pytest.raises(RuntimeError, match="stop ollama"):
        wl.LocalNoobAIWorker()._check_gpu()


def test_a_long_prompt_loses_whole_trailing_clauses_not_the_middle_of_one() -> None:
    class Tok:  # one token per word is enough to check the dropping rule without loading CLIP
        def __call__(self, text: str, add_special_tokens: bool = False):  # noqa: ANN204
            class Out:
                input_ids = text.replace(",", " ").split()

            return Out()

    fitted = wl.fit_prompt(Tok(), "q1 q2", "alpha beta, gamma delta, epsilon zeta, eta theta", limit=8)
    assert fitted == "q1 q2, alpha beta, gamma delta, epsilon zeta"  # the lowest-priority clause went, whole
    assert wl.fit_prompt(Tok(), "", "one, two", limit=75) == "one, two"
