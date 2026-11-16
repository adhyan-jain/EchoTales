"""The `z-image-turbo` natural-language profile and the compiled-prompt routing (no GPU, no weights)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from echotales.pipeline.render import compiled_route
from echotales.pipeline.render.compiler import (
    CharacterBrief,
    CrowdBrief,
    OutputMode,
    PanelBrief,
    PromptFormat,
    compile_prompt,
    genre_direction,
    identity_sentence,
    model_profile,
)
from echotales.pipeline.workers_contract import ImageWorkerResponse
from echotales.pipeline.workers_zimage import hf_name

FANG = dict(
    name="Fang Yuan", gender="male", age_band="adult",
    appearance={"hair_color": "long black", "eye_color": "dark brown", "scar": "scar on cheek"},
    attire="deep green robes", condition="wounded and bloodied",
    big_five={"o": 0.5, "c": 0.7, "e": 0.3, "a": 0.4, "n": 0.8}, lead=True,
)
Z = model_profile("z-image-turbo")


def brief(**over) -> PanelBrief:
    art, wardrobe, manhua = genre_direction("")
    fields = dict(
        novel_id="n", characters=[CharacterBrief(**FANG)],
        crowd=CrowdBrief("righteous sect martial artists", "many", "male", "ringed around him on all sides, weapons drawn", count=14),
        location="mountain cliff edge", setting="grey rock, mist, jagged peaks", lighting="late afternoon sun",
        shot="wide", camera="from slightly above", action="standing alone at the centre", mood="tense", tension=0.8,
        mode=OutputMode.MANGA, art_direction=art, era_wardrobe=wardrobe, manhua=manhua,
    )
    fields.update(over)
    return PanelBrief(**fields)


def order(c, *labels):
    positions = [c.positive.index(dict(c.section_texts())[label]) for label in labels]
    assert positions == sorted(positions)


def test_profile_is_natural_language_without_negative_prompt():
    assert Z.family is PromptFormat.NATURAL and Z.guidance == 0.0 and Z.negative_base == ""
    assert compile_prompt(brief(), Z).negative == ""


def test_lead_and_crowd_order_content_and_no_truncation():
    c = compile_prompt(brief(), Z)
    labels = [s.label for s in c.sections]
    assert labels == ["composition", "character:Fang Yuan", "demeanour", "others", "setting", "style"]
    order(c, *labels)
    assert c.positive == " ".join(t for _, t in c.section_texts())
    text = dict(c.section_texts())
    assert text["composition"].startswith("A wide establishing shot, from slightly above")
    assert "14 righteous sect martial artists" in text["others"] and "ringed around him on all sides" in text["others"]
    assert "mountain cliff edge" in text["setting"] and "late afternoon sun" in text["setting"]
    assert "wounded and bloodied" in text["demeanour"]
    assert 3 <= c.positive.count(". ") + 1 <= 7
    assert "solo" not in c.positive and "," in c.positive  # prose, not tags: no tag-only headcount


def test_solo_brief_has_no_others_section_and_few_sentences():
    c = compile_prompt(brief(crowd=None, shot="close", camera="eye level", action="", key_objects=[]), Z)
    labels = [s.label for s in c.sections]
    assert "others" not in labels and labels[0] == "composition"
    assert c.positive.startswith("A close-up portrait, eye level")
    assert 3 <= len([s for s in c.positive.split(". ") if s]) <= 6


def test_identity_sentence_is_identical_across_different_panels():
    a = compile_prompt(brief(), Z)
    b = compile_prompt(brief(crowd=None, shot="close", mood="calm", tension=0.0, lighting="dusk"), Z)
    sa, sb = dict(a.section_texts())["character:Fang Yuan"], dict(b.section_texts())["character:Fang Yuan"]
    assert sa == sb == identity_sentence(CharacterBrief(**FANG))
    assert sa == "Fang Yuan is a man with long black hair, dark brown eyes and scar on cheek, wearing deep green robes."


def test_manga_and_colour_style_lines_describe_chinese_culture_positively():
    manga = dict(compile_prompt(brief(), Z).section_texts())["style"]
    assert "black-and-white manga" in manga and "no panel borders" in manga and "no text" in manga
    assert "paifang" in manga and "hanfu" in manga and "topknots" in manga
    assert "jian" not in manga  # props belong to the scene: the global line put a sword on the lead in 13 of 13 panels
    for named in ("torii", "kimono", "katana", "Japanese"):  # naming an excluded object primes the model to draw it
        assert named not in manga
    assert manga.count(". ") == 0
    colour = dict(compile_prompt(brief(mode=OutputMode.COLOUR), Z).section_texts())["style"]
    assert "black-and-white" not in colour and "no panel borders" in colour
    assert "guofeng" in colour and "donghua" in colour and "muted" in colour and "torii" not in colour
    assert "hanfu" not in dict(compile_prompt(brief(manhua=False), Z).section_texts())["style"]


def test_cold_lead_demeanour_is_unmistakable_and_never_a_bare_smile_or_laugh():
    plain = dict(compile_prompt(brief(), Z).section_texts())["demeanour"]
    assert "cold and unmoved" in plain and "contempt" in plain and "no warmth" in plain
    smile = CharacterBrief(**{**FANG, "stated_expression": "light_smile"})
    laugh = CharacterBrief(**{**FANG, "stated_expression": "laughing"})
    s = dict(compile_prompt(brief(characters=[smile]), Z).section_texts())["demeanour"]
    g = dict(compile_prompt(brief(characters=[laugh]), Z).section_texts())["demeanour"]
    assert "thin mocking smirk" in s and "never a warm or cheerful smile" in s and "no warmth" in s
    assert "cold mocking laugh" in g and "dead eyes" in g
    warm = CharacterBrief(**{**FANG, "big_five": {"a": 0.8, "e": 0.7}, "stated_expression": "light_smile"})
    assert "cold" not in dict(compile_prompt(brief(characters=[warm]), Z).section_texts())["demeanour"]


def test_extra_named_character_gets_their_own_fixed_sentence():
    other = CharacterBrief(name="Elder Mo", gender="male", appearance={"hair_color": "white"}, attire="grey robes")
    c = compile_prompt(brief(characters=[CharacterBrief(**FANG), other], crowd=None), Z)
    assert "Elder Mo is a man with white hair, wearing grey robes." in dict(c.section_texts())["others"]


def test_hf_name_maps_gguf_tensor_names():
    assert hf_name("token_embd.weight") == "embed_tokens.weight"
    assert hf_name("blk.3.attn_q.weight") == "layers.3.self_attn.q_proj.weight"
    assert hf_name("blk.0.ffn_down.weight") == "layers.0.mlp.down_proj.weight"
    assert hf_name("output.weight") is None


class FakeWorker:
    def __init__(self):
        self.calls = []

    def generate_many(self, requests, sections=None, *, greyscale=False):
        self.calls.append((requests, sections, greyscale))
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
        return [ImageWorkerResponse(image_b64=base64.b64encode(buf.getvalue()).decode(), seed=r.seed, duration_s=0.0) for r in requests]


@pytest.mark.parametrize("key", ["z-image-turbo", "noobai-xl-1.1", "anima"])
def test_routing_sends_the_whole_compiled_prompt_to_the_matching_worker(tmp_path: Path, key):
    from echotales.pipeline.render.panels import PanelImageRequest

    fake = FakeWorker()
    compiled_route.set_worker(key, fake)
    try:
        sections = [("composition", "A wide shot."), ("style", "Manga.")]
        req = PanelImageRequest(prompt="A wide shot. Manga.", out_path=tmp_path / "x" / "p.png", negative_prompt="n", width=832, height=1216, seed=7)
        compiled_route.generate_compiled(req, sections, key, greyscale=True)
    finally:
        compiled_route.set_worker(key, None)
    (reqs, secs, grey), = fake.calls
    assert reqs[0].prompt == "A wide shot. Manga." and reqs[0].seed == 7 and secs == [sections] and grey is True
    assert (tmp_path / "x" / "p.png").read_bytes().startswith(b"\x89PNG")


def test_unknown_model_key_raises():
    with pytest.raises(ValueError):
        compiled_route.worker_for("nope")


