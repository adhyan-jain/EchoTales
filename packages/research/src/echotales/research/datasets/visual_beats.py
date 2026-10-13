"""Fixed-seed visual stimuli for the visual arm (H-VRUNG, H-JUDGE-V).

Twenty generic beats (original text, no source novel) in a balanced 2x2 of
gender x hair colour across ten pre-modern settings, so an attribute probe's
chance rate is 50% by design. Prompts are assembled through the product's
own `persona/prompt.py::fit_tiers_to_budget` in the product's priority order
(cast tag > character clause > beat > setting > framing), so whether an
injected error *survives the CLIP budget* is measured on the real assembly
code rather than assumed -- the 77-token truncation that killed the T3
interface direction is a measured stage here, not a confound.

Renders are cached by (prompt, seed, engine): the two experiments share the
committed images, and a rerun never re-renders.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from echotales.pipeline.paths import RESEARCH_SCRATCH_DIR

VISUAL_DIR = RESEARCH_SCRATCH_DIR / "visual"

SETTINGS = (
    "in a candlelit library", "on a misty mountain path", "in a walled garden",
    "on a riverbank at dusk", "in a busy market street", "in a stone temple hall",
    "on a windy cliff by the sea", "in a crowded tavern", "in a snowy forest",
    "in a palace courtyard",
)

#: Beat sentences of deliberately mixed length: the long ones push the setting
#: clause past the token budget, which is the truncation stage H-JUDGE-V
#: measures.
BEATS = (
    "reads a letter",
    "draws a sword slowly while watching the shadows near the doorway",
    "kneels to pick up a fallen lantern",
    "laughs at a joke",
    "turns around in surprise as a stranger calls out a name from far behind",
    "holds an umbrella",
    "carries a heavy basket of bread and apples while stepping around puddles",
    "points at the sky",
    "sits on a wooden bench sharpening a knife and humming an old song quietly",
    "waves goodbye",
)

HAIR = {"black": "black hair", "blonde": "blonde hair"}
GENDER_TAG = {"F": "1girl", "M": "1boy"}

#: Commitment rungs. The withholding ones keep the attribute *in the prompt*
#: (variant "in") to test whether framing hides it, or drop it (variant
#: "free") to test whether the generator commits to a default anyway.
RUNGS = {
    "committed": "upper body, looking at viewer, face visible",
    "back_view": "from behind, back view, facing away, face not visible",
    "silhouette": "silhouette, backlit, dark figure against bright light, no visible features",
    "distant": "very wide shot, tiny distant figure, scenery focus",
    "crop": "close-up of hands only, face out of frame",
}


@dataclass(frozen=True, slots=True)
class Spec:
    beat_id: str
    gender: str
    hair: str
    setting: str
    beat: str


@dataclass(slots=True)
class Stimulus:
    key: str
    spec: Spec
    rung: str
    variant: str  # "in" | "free" | "error:<type>"
    prompt: str
    seed: int
    kept: dict[str, bool] = field(default_factory=dict)  # clause -> survived the budget

    @property
    def path(self) -> Path:
        return VISUAL_DIR / f"{self.key}.png"


def specs(n: int = 20) -> list[Spec]:
    return [Spec(beat_id=f"b{i:02d}", gender="FM"[i % 2], hair=("black", "blonde")[(i // 2) % 2],
                 setting=SETTINGS[i % len(SETTINGS)], beat=BEATS[(i * 3) % len(BEATS)])
            for i in range(n)]


def _budget() -> int:
    from echotales.pipeline.persona.prompt import _USABLE_TOKENS, count_tokens

    # render_panels reserves the engine's quality prefix off the budget.
    return _USABLE_TOKENS - count_tokens("score_9, score_8_up")


def build(spec: Spec, rung: str, variant: str, *, gender: str | None = None,
          hair: str | None = None, setting: str | None = None, seed: int = 1234) -> Stimulus:
    """Assemble a panel prompt with the product's own `build_image_prompt`
    (persona/prompt.py): headcount tags and style anchor in tier 1, beat,
    appearance and framing in tier 2, locale in tier 3. A withholding rung
    is passed as the hand-authored `directive` -- the slot the product's own
    silhouette fallback uses (render/direction.py) -- so it is tier 1."""
    from echotales.pipeline.persona.prompt import build_image_prompt
    from echotales.pipeline.persona.runner import CharacterCast, PanelCast

    g = gender or spec.gender
    h = hair or spec.hair
    s = setting or spec.setting
    free = variant == "free"
    who = "person" if free else ("woman" if g == "F" else "man")
    name = "the traveler"
    appearance = "" if free else HAIR[h]
    beat = f"A {who} {spec.beat}."
    prompt = build_image_prompt(
        PanelCast(foreground_characters=[CharacterCast(self_label=name,
                                                       attire="simple brown traveling clothes")]),
        beat=beat,
        directive="" if rung == "committed" else RUNGS[rung],
        character_appearances={name: appearance} if appearance else {},
        character_genders=[] if free else ["female" if g == "F" else "male"],
        locale=s, limit=_budget())
    kept = {"cast": free or GENDER_TAG[g] in prompt,
            "character": free or HAIR[h] in prompt,
            "beat": spec.beat.split()[0] in prompt,
            "setting": s in prompt,
            "rung": rung == "committed" or RUNGS[rung].split(",")[0] in prompt}
    key = hashlib.sha256(json.dumps([prompt, seed, "noobai-gpu-35"]).encode()).hexdigest()[:16]
    return Stimulus(key=key, spec=spec, rung=rung, variant=variant, prompt=prompt, seed=seed, kept=kept)


def description(spec: Spec) -> str:
    """The *intended* content in plain words, for holistic judges."""
    who = "woman" if spec.gender == "F" else "man"
    return f"A {who} with {HAIR[spec.hair]} {spec.beat} {spec.setting}."


#: NoobAIEngine's own constants (render/panels.py), copied so research
#: renders match product renders without going through its loader.
NOOBAI = {"model_id": "Laxhar/noobai-XL-1.1", "steps": 35, "guidance": 7.0,
          "quality_prefix": "score_9, score_8_up",
          "negative_suffix": ", animal ears, cat ears, kemonomimi, fantasy armor, "
                             "modern clothing, school uniform, elf"}
NEGATIVE = "multiple people, 2girls, 2boys"


def gpu_free(max_used_mib: int = 1500) -> tuple[bool, str]:
    """The card is ours only if nothing else holds it: little memory in use
    and no model loaded in ollama (diffusion and ollama never share it)."""
    import subprocess
    import urllib.request

    used = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, check=True).stdout.split()[0])
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=5) as r:
            loaded = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        loaded = []
    ok = used <= max_used_mib and not loaded
    return ok, f"gpu memory used {used} MiB, ollama models loaded {loaded}"


def render_gpu(stims: list[Stimulus], *, steps: int = NOOBAI["steps"]) -> int:
    """Render NoobAI-XL panels with every weight on the GPU, never in RAM.

    The product engine (`render/panels.py::IllustriousEngine`) uses
    `enable_model_cpu_offload`, which keeps the whole SDXL pipeline resident
    in system RAM: measured 2026-10-02 at ~4.2 GB RSS, which on top of the
    owner's swap pushed the laptop to 21/22 GB swap and load 15. Here the
    two text encoders load straight to cuda, encode every prompt once, and
    are freed; then the UNet and VAE load straight to cuda (peak ~5.5 GB
    VRAM on the 8 GB card). Same checkpoint, prompt prefix, negatives,
    steps and CFG as the product engine.
    """
    todo = list({s.key: s for s in stims if not s.path.exists()}.values())
    if not todo:
        return 0
    ok, why = gpu_free()
    if not ok:
        raise RuntimeError(f"GPU not free, refusing to render: {why}")
    import gc

    import torch
    from diffusers import AutoencoderKL, StableDiffusionXLPipeline, UNet2DConditionModel
    from echotales.pipeline.render.panels import _cached_snapshot

    snap = _cached_snapshot(NOOBAI["model_id"]) or NOOBAI["model_id"]
    f16 = torch.float16
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: prompt embeddings, in a subprocess. Freeing the text encoders
    # in-process did not release their VRAM (accelerate device-map hooks keep
    # references): measured 2026-10-02, 6.89 GB allocated = UNet 4.93 + VAE
    # 0.16 + both encoders, and the first denoise step OOMed. A process exit
    # is the one release that cannot leak.
    import subprocess
    import sys

    job = VISUAL_DIR / "_encode_job.json"
    out = VISUAL_DIR / "_embeds.pt"
    job.write_text(json.dumps({"snap": str(snap), "prompts": {
        s.key: f"{NOOBAI['quality_prefix']}, {s.prompt}" for s in todo},
        "negative": NEGATIVE + NOOBAI["negative_suffix"]}))
    subprocess.run([sys.executable, "-m", "echotales.research.datasets.visual_beats", "encode",
                    str(job), str(out)], check=True)
    embeds = torch.load(out, map_location="cuda")
    job.unlink()
    out.unlink()

    # Phase 2: denoise + decode (UNet and VAE only, on the GPU).
    unet = UNet2DConditionModel.from_pretrained(snap, subfolder="unet", torch_dtype=f16, device_map="cuda")
    vae = AutoencoderKL.from_pretrained(snap, subfolder="vae", torch_dtype=f16, device_map="cuda")
    pipe = StableDiffusionXLPipeline.from_pretrained(
        snap, unet=unet, vae=vae, text_encoder=None, text_encoder_2=None, tokenizer=None,
        tokenizer_2=None, torch_dtype=f16)
    # Tiling on the VAE module itself: the pipeline-level enable_vae_tiling()
    # did not take in diffusers 0.39 -- the decode ran untiled (`_decode`) and
    # OOMed asking for 1 GiB at 1024x1024 with the UNet still resident.
    # Tiling alone is not enough: SDXL's VAE only tiles above
    # tile_sample_min_size, which defaults to 1024 -- so a 1024x1024 panel
    # never tiles. 512-pixel tiles (64 latent) keep the decode under ~1 GB.
    vae.enable_slicing()
    vae.enable_tiling()
    vae.tile_sample_min_size = 512
    vae.tile_latent_min_size = 64
    manifest_p = VISUAL_DIR / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    with torch.inference_mode():
        for s in todo:
            pe, npe, ppe, nppe = embeds.pop(s.key)
            img = pipe(prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=ppe,
                       negative_pooled_prompt_embeds=nppe, width=1024, height=1024,
                       num_inference_steps=steps, guidance_scale=NOOBAI["guidance"],
                       generator=torch.Generator(device="cpu").manual_seed(s.seed)).images[0]
            img.save(s.path)
            manifest[s.key] = {"prompt": s.prompt, "seed": s.seed, "engine": "noobai-gpu",
                               "steps": steps, "kept": s.kept}
            manifest_p.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    del pipe, unet, vae
    gc.collect()
    torch.cuda.empty_cache()
    return len(todo)


def render_all(stims: list[Stimulus], *, engine_name: str = "noobai", steps: int = 28) -> int:
    """Render through the product engine (any engine name). Kept for the
    stub path and engine comparisons; real research runs use `render_gpu`,
    which never parks the pipeline in system RAM."""
    if engine_name == "noobai-gpu":
        return render_gpu(stims, steps=steps)
    """Render whatever is not cached yet; returns how many were rendered.
    Frees the diffusion pipeline afterwards so ollama can take the GPU
    (the two never share the 8 GB card)."""
    todo = list({s.key: s for s in stims if not s.path.exists()}.values())
    VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    manifest_p = VISUAL_DIR / "manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    if todo:
        from echotales.pipeline.render.panels import PanelImageRequest, get_engine

        eng = get_engine(engine_name, **({"steps": steps} if engine_name != "stub" else {}))
        for s in todo:
            eng.generate(PanelImageRequest(prompt=s.prompt, out_path=s.path, seed=s.seed,
                                           negative_prompt="multiple people, 2girls, 2boys"))
            manifest[s.key] = {"prompt": s.prompt, "seed": s.seed, "engine": engine_name,
                               "kept": s.kept}
            manifest_p.write_text(json.dumps(manifest, indent=1, sort_keys=True))
        del eng
        import gc

        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass
    return len(todo)


def _encode_main(job_path: str, out_path: str) -> None:
    """Subprocess body for `render_gpu` phase 1: text encoders on the GPU,
    every prompt encoded once, embeddings saved, process exits."""
    import torch
    from diffusers import StableDiffusionXLPipeline
    from transformers import CLIPTextModel, CLIPTextModelWithProjection, CLIPTokenizer

    job = json.loads(Path(job_path).read_text())
    snap, f16 = job["snap"], torch.float16
    te1 = CLIPTextModel.from_pretrained(snap, subfolder="text_encoder", torch_dtype=f16, device_map="cuda")
    te2 = CLIPTextModelWithProjection.from_pretrained(snap, subfolder="text_encoder_2", torch_dtype=f16,
                                                      device_map="cuda")
    enc = StableDiffusionXLPipeline.from_pretrained(
        snap, unet=None, vae=None, text_encoder=te1, text_encoder_2=te2,
        tokenizer=CLIPTokenizer.from_pretrained(snap, subfolder="tokenizer"),
        tokenizer_2=CLIPTokenizer.from_pretrained(snap, subfolder="tokenizer_2"), torch_dtype=f16)
    embeds = {}
    with torch.inference_mode():
        for key, prompt in job["prompts"].items():
            t = enc.encode_prompt(prompt=prompt, device="cuda", num_images_per_prompt=1,
                                  do_classifier_free_guidance=True, negative_prompt=job["negative"])
            embeds[key] = tuple(x.detach().cpu() for x in t)
    torch.save(embeds, out_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 4 and sys.argv[1] == "encode":
        _encode_main(sys.argv[2], sys.argv[3])
