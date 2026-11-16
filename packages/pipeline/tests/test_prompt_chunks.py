"""Chunking arithmetic for the long-prompt encoder, with the real CLIP tokenizer and no GPU."""

from __future__ import annotations

import pytest
from echotales.pipeline import workers_local as wl

pytest.importorskip("compel")


@pytest.fixture(scope="module")
def tokenizer():
    from transformers import CLIPTokenizer

    try:
        return CLIPTokenizer.from_pretrained(wl._snapshot(wl.MODEL_ID) + "/tokenizer")
    except (FileNotFoundError, OSError):
        pytest.skip("NoobAI tokenizer is not in the local Hugging Face cache")


def test_short_prompt_is_one_chunk(tokenizer) -> None:
    plan = wl.plan_chunks(tokenizer, [("quality", "score_9"), ("count", "1boy, solo")])
    assert plan["chunks"] == 1 and plan["sections"] == {"quality": [0], "count": [0]}


def test_long_prompt_spans_chunks_and_keeps_every_section(tokenizer) -> None:
    sections = [("quality", "score_9, score_8_up"), ("setting", ", ".join(f"mountain peak {i}" for i in range(40))),
                ("style", "monochrome, greyscale, screentone")]
    plan = wl.plan_chunks(tokenizer, sections)
    assert plan["tokens"] > 75 and plan["chunks"] == -(-plan["tokens"] // 75)
    spans = plan["sections"]
    assert spans["quality"] == [0]
    assert len(spans["setting"]) >= 2  # straddles a boundary and reports both
    assert spans["style"][-1] == plan["chunks"] - 1  # the tail is still in the prompt, not cut
    assert wl.fit_prompt(tokenizer, "", ", ".join(t for _, t in sections)) != ", ".join(t for _, t in sections)


def test_chunk_boundary_is_exact(tokenizer) -> None:
    word = ", ".join(["tree"] * 100)
    n = len(tokenizer(word, add_special_tokens=False).input_ids)
    plan = wl.plan_chunks(tokenizer, [("a", word)])
    assert plan["tokens"] == n and plan["chunks"] == -(-n // 75)


def test_compel_escape_roundtrips_parentheses() -> None:
    from compel.prompt_parser import PromptParser

    text = "fang yuan (young), 6+boys"
    parsed = PromptParser().parse_conjunction(wl._compel_safe(text))
    assert "fang yuan (young), 6+boys" in str(parsed)
