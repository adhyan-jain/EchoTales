"""Art bake-off v3 (docs/results/ART_V3.md): C2 tag compiler, LoRA trainer command, ControlNet options, driver plumbing.

No GPU and no model weights: the driver runs against its stub runner, the trainer only in `--dry-run`."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from _art_bakeoff_panels import bakeoff_panels
from echotales.pipeline.render.compiler import PROFILES
from echotales.pipeline.render.drama_tags import CHECKPOINTS, compile_c2, identity_tags
from echotales.pipeline.render.sdxl_control import CONTROLNETS, ControlSpec, control_map, validate
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


driver = _load("art_bakeoff_v3", "scripts/eval/art_bakeoff_v3.py")
trainer = _load("train_character_lora", "scripts/art/train_character_lora.py")
lorasets = _load("build_lora_set", "scripts/art/build_lora_set.py")

PANELS = {bp.panel_id: bp for bp in bakeoff_panels()}


def c2(pid: str, ck: str = "noobai", **kw):
    bp = PANELS[pid]
    return compile_c2(bp.panel, bp.brief, checkpoint=ck, **kw)


def tags(t) -> set[str]:
    return {x.strip() for x in t.positive.split(",")}


# ---- C2 tag compilation ----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", list(PANELS))
@pytest.mark.parametrize("ck", list(CHECKPOINTS))
def test_every_panel_compiles_with_its_checkpoint_quality_words(pid, ck):
    t = c2(pid, ck)
    assert t.positive.startswith(PROFILES[CHECKPOINTS[ck]].quality_tags)
    assert t.negative.startswith(PROFILES[CHECKPOINTS[ck]].negative_base.split(",")[0])
    assert len(t.positive.split(", ")) == len(set(t.positive.split(", "))), "tags are de-duplicated"
    assert ("score_9" in t.positive) == (ck == "noobai"), "score tags are NoobAI's, not Illustrious's"


def test_empty_cast_panels_draw_no_people():
    for pid in ("p05_detonation", "p06_village"):
        t = c2(pid)
        assert "no humans" in tags(t)
        assert not tags(t) & {"1boy", "1girl", "solo", "male focus"}
        assert "1boy" in t.negative and "person" in t.negative


def test_eyes_only_panel_is_eyes_only():
    t = c2("p12_eyes")
    assert {"eye focus", "extreme close-up", "solo"} <= tags(t)
    assert not tags(t) & {"1boy", "no humans", "male focus"}
    assert "nose" in t.negative and "mouth" in t.negative


def test_imagined_inset_is_an_isolated_subject_on_a_void():
    t = c2("p10_bainingbing")
    assert {"solo", "simple background", "black background", "floating"} <= tags(t)
    assert "1boy" in tags(t)  # the man is male (v2 fixture), spelled as a tag
    assert not tags(t) & {"mountain", "temple", "indoors", "crowd"}
    assert "background" in t.negative and "scenery" in t.negative
    assert "chiaroscuro" not in tags(t)  # an isolated figure takes the layer glow, not the room's drama


def test_age_and_gender_are_tags():
    assert {"teenager", "youthful"} <= tags(c2("p13_young"))
    assert {"middle-aged", "mature male", "wrinkles"} <= tags(c2("p07_clanhead"))
    assert {"old man", "white hair", "beard"} <= tags(c2("p09_elder"))
    for pid, bp in PANELS.items():
        if bp.brief.characters and not bp.brief.crowd:
            assert "1boy" in tags(c2(pid)) or "1girl" in tags(c2(pid)), pid


def test_identity_tags_come_from_the_cast_look_facts():
    t = identity_tags(PANELS["p01_hero"].brief.characters[0])
    assert {"black hair", "long hair", "blood on clothes", "robe", "chinese clothes"} <= set(t)
    assert "smirk" in t and "expressionless" not in t  # "a cold mocking smile": the first expression match wins


def test_crowd_count_tag_replaces_single_person_tags():
    t = c2("p03_overhead")
    assert "6+boys" in tags(t) and "1boy" not in tags(t)
    assert {"from above", "bird's-eye view"} <= tags(c2("p03_overhead")) or "from above" in tags(t)


def test_drama_vocabulary_on_peaks_only():
    peak = tags(c2("p01_hero"))
    assert {"chiaroscuro", "rim light", "from below", "foreshortening", "high contrast", "ink wash"} <= peak
    assert {"dutch angle", "speed lines"} <= tags(c2("p04_laugh"))
    assert "dutch angle" in tags(c2("p02_accuser"))
    calm = tags(c2("p07_clanhead"))
    assert not calm & {"chiaroscuro", "dutch angle", "rim light"}
    assert "calm" in calm


def test_trigger_word_leads_the_identity_tags():
    t = c2("p01_hero", trigger="fangyuan_ri")
    names = [k for k, _ in t.sections]
    assert names.index("trigger") == names.index("identity") - 1
    assert t.positive.index("fangyuan_ri") < t.positive.index("1boy")


# ---- LoRA trainer: dry run --------------------------------------------------------------------------------------------------

def _set(tmp_path: Path, n: int = 10) -> Path:
    d = tmp_path / "set"
    d.mkdir()
    rows = []
    for i in range(n):
        Image.new("RGB", (64, 64), (i, 2, 3)).save(d / f"{i}.png")
        rows.append({"file_name": f"{i}.png", "text": f"fangyuan_ri, 1boy, view {i}"})
    (d / "metadata.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def test_lora_dry_run_builds_an_8gb_command_under_the_gpu_lock(tmp_path, capsys):
    d = _set(tmp_path, 10)
    rc = trainer.main(["--data", str(d), "--out", str(tmp_path / "o"), "--base", "illustrious", "--dry-run", "--rank", "32"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    cmd = out["command"]
    assert cmd[:2] == ["flock", "/tmp/echotales-gpu.lock"]
    for flag in ("--gradient_checkpointing", "--use_8bit_adam", "--random_flip"):
        assert flag in cmd
    assert cmd[cmd.index("--mixed_precision") + 1] == "fp16"
    assert cmd[cmd.index("--rank") + 1] == "32"
    assert cmd[cmd.index("--resolution") + 1] == "768"
    assert cmd[cmd.index("--train_batch_size") + 1] == "1"
    assert cmd[cmd.index("--pretrained_model_name_or_path") + 1] == "OnomaAIResearch/Illustrious-xl-early-release-v0"
    assert cmd[cmd.index("--pretrained_vae_model_name_or_path") + 1] == "madebyollin/sdxl-vae-fp16-fix"
    assert out["steps"] == 400 and cmd[cmd.index("--max_train_steps") + 1] == "400"


def test_lora_steps_scale_with_the_set_and_no_flip_is_honoured(tmp_path, capsys):
    assert trainer.default_steps(5) == 400 and trainer.default_steps(20) == 800 and trainer.default_steps(500) == 1500
    d = _set(tmp_path, 8)
    trainer.main(["--data", str(d), "--out", str(tmp_path / "o"), "--dry-run", "--no-flip", "--steps", "123"])
    cmd = json.loads(capsys.readouterr().out)["command"]
    assert "--random_flip" not in cmd and cmd[cmd.index("--max_train_steps") + 1] == "123"
    assert cmd[cmd.index("--pretrained_model_name_or_path") + 1] == "Laxhar/noobai-XL-1.1"


def test_lora_refuses_a_set_without_metadata_or_images(tmp_path):
    with pytest.raises(FileNotFoundError):
        trainer.read_set(tmp_path)
    d = _set(tmp_path, 3)
    (d / "1.png").unlink()
    with pytest.raises(ValueError, match="no image"):
        trainer.read_set(d)


def test_pinned_trainer_hash_is_enforced(tmp_path):
    bad = tmp_path / "t.py"
    bad.write_text("print('not the trainer')")
    with pytest.raises(RuntimeError, match="pinned"):
        trainer.ensure_trainer(bad)


# ---- training-set assembly ---------------------------------------------------------------------------------------------------

def _fake_tree(tmp_path: Path) -> Path:
    import random

    root = tmp_path / "data"
    sheets = root / "novels/RI/references/turnarounds/reverend-insanity_self_476821534c/body1"
    sheets.mkdir(parents=True)
    rnd = random.Random(1)
    for name in ("view_front", "view_side", "expr_angry"):  # real-looking: noisy, so big and unique
        Image.frombytes("RGB", (400, 600), bytes(rnd.getrandbits(8) for _ in range(400 * 600 * 3))).save(sheets / f"{name}.png")
    Image.new("RGB", (32, 32)).save(sheets / "view_back.png")  # a stub
    return root


def test_placeholders_are_rejected_and_real_sheets_are_captioned(tmp_path):
    root = _fake_tree(tmp_path)
    res = lorasets.build("fang_yuan", tmp_path / "set", root, base_tags="1boy, black hair")
    assert res["found"] == 4 and res["usable"] == 3 and len(res["rejected"]) == 1
    rows = [json.loads(line) for line in (tmp_path / "set/metadata.jsonl").read_text().splitlines()]
    assert all(r["text"].startswith("fangyuan_ri, 1boy, black hair") for r in rows)
    assert any("angry" in r["text"] for r in rows) and any("from side" in r["text"] for r in rows)
    assert Image.open(tmp_path / "set" / rows[0]["file_name"]).size == (lorasets.SIZE, lorasets.SIZE)


def test_character_with_no_sheets_has_nothing_usable(tmp_path):
    assert lorasets.build("kim_dokja", tmp_path / "k", _fake_tree(tmp_path))["usable"] == 0


# ---- ControlNet option -------------------------------------------------------------------------------------------------------

def test_control_kinds_and_resident_size_rules():
    assert set(CONTROLNETS) == {"canny", "lineart", "depth", "openpose"}
    validate(ControlSpec("canny", "x.png"))
    validate(ControlSpec("depth", "x.png", scale=0.5, start=0.1, end=0.7))
    with pytest.raises(ValueError, match="unknown"):
        validate(ControlSpec("scribble", "x.png"))
    with pytest.raises(ValueError, match="skeleton"):
        validate(ControlSpec("openpose", "x.png", preprocess=True))
    with pytest.raises(ValueError, match="does not fit"):
        validate(ControlSpec("openpose", "x.png", preprocess=False))
    validate(ControlSpec("openpose", "x.png", preprocess=False), allow_big=True)
    with pytest.raises(ValueError, match="window"):
        validate(ControlSpec("canny", "x.png", start=0.9, end=0.5))
    assert ControlSpec.from_dict({"kind": "openpose", "image": "p.png"}).preprocess is False
    assert ControlSpec.from_dict({"kind": "canny", "image": "p.png"}).preprocess is True


def test_canny_control_map_is_a_white_on_black_edge_image(tmp_path):
    src = tmp_path / "ref.png"
    im = Image.new("RGB", (200, 300), "black")
    im.paste(Image.new("RGB", (80, 120), "white"), (60, 90))
    im.save(src)
    m = control_map(ControlSpec("canny", str(src)), (128, 192))
    assert m.size == (128, 192) and m.getextrema()[0] == (0, 255)
    raw = control_map(ControlSpec("openpose", str(src), preprocess=False), (64, 64))
    assert raw.size == (64, 64)


# ---- driver plumbing ---------------------------------------------------------------------------------------------------------

LORAS = {"Fang Yuan": {"path": "/x/l.safetensors", "scale": 0.8, "trigger": "fangyuan_ri"}}


def test_arm_job_plans_share_seeds_and_sizes(tmp_path):
    rows = driver.compile_all(LORAS)
    plans = {a: driver.plan_arm(a, rows, tmp_path, LORAS) for a in ("B2", "C2_noobai", "C2_illustrious", "D")}
    assert {len(v) for v in plans.values()} == {13}
    for i in range(len(rows)):
        assert {p[i]["seed"] for p in plans.values()} == {4200 + i}
        assert {(p[i]["width"], p[i]["height"]) for p in plans.values()} == {(832, 1216)}
    assert "negative" not in plans["B2"][0] and "negative" in plans["C2_noobai"][0]
    assert plans["D"][0]["init"].endswith("B2/p01_hero.png") and plans["D"][0]["strength"] == 0.45
    assert plans["C2_noobai"][0]["out"] == str(tmp_path / "C2_noobai/p01_hero.png")
    assert "score_9" not in plans["C2_illustrious"][0]["prompt"]


def test_lora_arms_only_have_panels_with_a_lora_and_lead_with_the_trigger(tmp_path):
    rows = driver.compile_all(LORAS)
    jobs = driver.plan_arm("C2_noobai_lora", rows, tmp_path, LORAS)
    assert [j["panel_id"] for j in jobs] == ["p01_hero", "p03_overhead", "p04_laugh", "p13_young"]
    assert all(j["lora"] == {"path": "/x/l.safetensors", "scale": 0.8} and "fangyuan_ri" in j["prompt"] for j in jobs)
    assert driver.plan_arm("B2_lora", rows, tmp_path, LORAS) == []  # an SDXL LoRA cannot drive Z-Image
    assert driver.plan_arm("D_lora", rows, tmp_path, LORAS)[0]["init"].endswith("B2/p01_hero.png")


def test_control_option_reaches_sdxl_jobs_but_not_zimage(tmp_path):
    rows = driver.compile_all({})
    ctl = {"kind": "canny", "image": "ref.png", "scale": 0.5}
    assert driver.plan_arm("C2_noobai", rows, tmp_path, control=ctl)[0]["control"] == ctl
    assert "control" not in driver.plan_arm("B2", rows, tmp_path, control=ctl)[0]


def test_parse_loras_rejects_unknown_characters():
    assert driver.parse_loras(["klein=/a.safetensors:0.6"])["Klein Moretti"]["scale"] == 0.6
    with pytest.raises(SystemExit):
        driver.parse_loras(["nobody=/a.safetensors"])


def test_stub_run_writes_arm_folders_and_stacked_sheets(tmp_path):
    rc = driver.main(["--phase", "all", "--stub", "--out", str(tmp_path), "--lora", "fang_yuan=/x/l.safetensors"])
    assert rc == 0
    for arm in ("B2", "C2_noobai", "C2_illustrious", "D"):
        assert len(list((tmp_path / arm).glob("*.png"))) == 13
    assert len(list((tmp_path / "C2_noobai_lora").glob("*.png"))) == 4
    spec = json.loads((tmp_path / "jobs_C2_noobai.json").read_text())
    assert spec["checkpoint"] == "Laxhar/noobai-XL-1.1" and len(spec["jobs"]) == 13
    assert json.loads((tmp_path / "jobs_C2_illustrious.json").read_text())["checkpoint"].startswith("OnomaAIResearch/")
    sheets = tmp_path / "sheets"
    assert len(list(sheets.glob("p*.png"))) == 13 and len(list(sheets.glob("all_*.png"))) == 4
    assert json.loads((tmp_path / "prompts.json").read_text())["p12_eyes"]["C2_noobai"]["positive"]
