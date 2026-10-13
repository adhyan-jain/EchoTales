"""H-ACT (convergence pass C3): hold the source line and an injected speaker
error fixed, vary only the rendering action, and measure how the error
manifests in the audio.

X (text) -> Z (speaker inference) -> A (rendering action) -> Y (audio). We set
Z to gold or to an injected wrong speaker and A to the product's three real
treatments (`pipeline/voice/runner.py`): narrator, the "unconfirmed" generic
voice of the predicted speaker's gender, or the predicted speaker's own cast
voice. Everything else -- text, reference clip, TTS settings, seed -- is fixed.

What is *not* measured here is perceptual cost. The measures are machine
manifestation (an independent WavLM speaker-verification margin toward the
gold voice, a gender cue, ASR fidelity), and the protocol carries its own
triviality control: if the audio margins are just the reference-clip
geometry restated (R^2 >= 0.9), the "causal effect" is real but
definitional -- choosing a voice changes which voice you hear -- and is
reported that way (CONVERGENCE.md C3).

Stages, so TTS and the measuring models never share the 8 GB card:
`render` (Chatterbox), `measure` (WavLM-SV + whisper-small), `all`.
"""

from __future__ import annotations

import gc
import json
import random
import re
import time
from pathlib import Path

import numpy as np

from echotales.research.config import ExperimentConfig, derive_seed
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-ACT"
DEFAULT_PARAMS = {
    "per_type": 20, "error_types": ["cross_gender", "same_gender", "addressee"],
    "min_chars": 40, "max_chars": 220, "local_window": 20,
    "stage": "all", "engine": "chatterbox", "resamples": 2000,
    "sv_model": "microsoft/wavlm-base-plus-sv", "asr_model": "openai/whisper-small",
}
ROLES = ("spec_err", "spec_gold", "gen_err", "gen_gold", "narr", "spec_err#1", "spec_gold#1")


# --------------------------------------------------------------------------
# design


def _generic(bank_ids, genders, gender, exclude, rng):
    """`voice/runner.py:334-347`: a voice of the predicted speaker's gender,
    never that speaker's own voice nor the narrator nor a voice already in
    use around this line; falls back to the same-gender bank."""
    pool = [v for v, g in zip(bank_ids, genders) if g == gender and v not in exclude["all"]]
    pool = pool or [v for v, g in zip(bank_ids, genders) if g == gender and v not in exclude["min"]]
    return rng.choice(sorted(pool))


def design(novels, geom, p, base_seed):
    """Units (one injected error each) and the voice for every render role."""
    from echotales.research.controllers.casting import cast
    from echotales.research.evaluators.voice_geometry import BankGeometry
    from echotales.research.experiments.xdis_alias_rescore import canon
    from echotales.research.transforms.error_injection import inject

    centre = geom.emb.mean(axis=0)
    narrator = geom.ids[int((geom.emb @ centre).argmax())]  # H-COST's rule
    keep = [i for i, v in enumerate(geom.ids) if v != narrator]
    sub = BankGeometry([geom.ids[i] for i in keep], [geom.genders[i] for i in keep], geom.emb[keep])

    rng = random.Random(derive_seed(base_seed, "units"))
    by_novel: dict[str, list] = {}
    casts = {}
    for nv in novels:
        counts: dict[str, int] = {}
        for q in nv.quotes:
            counts[q.speaker] = counts.get(q.speaker, 0) + 1
        chars = sorted(nv.characters.values(), key=lambda c: (-counts.get(c.name, 0), c.name))
        casts[nv.name] = cast([(c.name, c.gender) for c in chars], sub, mode="diverse",
                              seed=derive_seed(base_seed, nv.name, "diverse"))
        elig = []
        for q in nv.quotes:
            g = canon(q.speaker, nv.characters) if q.speaker else None
            if (q.start >= 0 and g and nv.gender_of(g) in ("M", "F")
                    and p["min_chars"] <= len(q.text) <= p["max_chars"]):
                elig.append((q, g))
        rng.shuffle(elig)
        by_novel[nv.name] = elig
    nvmap = {nv.name: nv for nv in novels}
    units, used = [], set()
    for et in p["error_types"]:
        got, names, ptr = 0, sorted(by_novel), {k: 0 for k in by_novel}
        while got < p["per_type"] and any(ptr[k] < len(by_novel[k]) for k in names):
            for name in names:  # round-robin over novels
                if got >= p["per_type"] or ptr[name] >= len(by_novel[name]):
                    continue
                q, g = by_novel[name][ptr[name]]
                ptr[name] += 1
                if (name, q.id) in used:
                    continue
                nv, assign = nvmap[name], casts[name]
                near = [x for x in nv.quotes if abs(x.index - q.index) <= p["local_window"]]
                local = {canon(s, nv.characters) for x in near for s in (x.speaker, *x.addressees)}
                local = {c for c in local if c and nv.gender_of(c) in ("M", "F")} | {g}
                adr = [canon(a, nv.characters) for a in q.addressees]
                inj = inject([{"speaker": g, "addressees": [a for a in adr if a]}],
                             {c: nv.gender_of(c) for c in local}, rate=1.0, error_type=et,
                             seed=derive_seed(base_seed, name, q.id, et), eligible={0})
                if not inj or assign.get(inj[0].rendered_as) == assign.get(g):
                    continue
                w = inj[0].rendered_as
                uid = f"{name}:{q.id}"
                in_use = {assign[c] for c in local if c in assign}
                voices = {"spec_err": assign[w], "spec_gold": assign[g], "narr": narrator}
                for role, who in (("gen_err", w), ("gen_gold", g)):
                    voices[role] = _generic(geom.ids, geom.genders, geom.gender(assign[who]),
                                            {"all": in_use | {narrator, assign[who]},
                                             "min": {narrator, assign[who]}},
                                            random.Random(derive_seed(base_seed, uid, "generic", who)))
                voices["spec_err#1"], voices["spec_gold#1"] = voices["spec_err"], voices["spec_gold"]
                # PDNC keeps the source line breaks inside a quote; TTS reads
                # whitespace-collapsed text (same words).
                units.append({"unit": uid, "novel": name, "qid": q.id, "text": " ".join(q.text.split()), "error_type": et,
                              "gold": g, "wrong": w, "gender_gold": nv.gender_of(g),
                              "gender_wrong": nv.gender_of(w), "voices": voices})
                used.add((name, q.id))
                got += 1
    return units, narrator


# --------------------------------------------------------------------------
# render (GPU: Chatterbox)


def _clip(voice_id: str) -> Path:
    from echotales.pipeline.paths import VOICE_BANK_DIR

    return VOICE_BANK_DIR / "ears" / voice_id.removeprefix("ears") / "emo_neutral_sentences.wav"


def render(units, out_dir: Path, engine_name: str, base_seed: int) -> list[dict]:
    import torch

    from echotales.pipeline.voice.engine import SynthesisRequest, get_engine

    tts = get_engine(engine_name)
    renders, done = [], {}
    for u in units:
        for role in ROLES:
            v = u["voices"][role]
            sidx = 1 if role.endswith("#1") else 0
            key = f"{u['unit']}|{v}|{sidx}"  # one render per (line, voice, seed)
            path = out_dir / "wav" / f"{derive_seed(base_seed, key):010d}.wav"
            if key not in done:
                t0, seed = time.time(), derive_seed(base_seed, u["unit"], v, sidx)
                if not path.exists():
                    random.seed(seed)
                    np.random.seed(seed % 2**32)
                    torch.manual_seed(seed)
                    if torch.cuda.is_available():
                        torch.cuda.manual_seed_all(seed)
                    tts.synthesize(SynthesisRequest(text=u["text"], out_path=path,
                                                    reference_clip=_clip(v) if engine_name != "stub" else None))
                done[key] = round(time.time() - t0, 3)
            renders.append({"unit": u["unit"], "role": role, "voice": v, "seed_idx": sidx,
                            "path": str(path), "synth_s": done[key]})
    del tts
    gc.collect()
    try:
        torch.cuda.empty_cache()
    except Exception:
        pass
    return renders


# --------------------------------------------------------------------------
# measure (GPU after TTS is released: WavLM-SV, whisper-small)


def _norm_words(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]+", " ", s.lower().replace("’", "'")).split()


def wer(ref: str, hyp: str) -> float:
    r, h = _norm_words(ref), _norm_words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


class Measurer:
    def __init__(self, sv_model: str, asr_model: str):
        import torch
        from transformers import AutoFeatureExtractor, WavLMForXVector, pipeline

        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.fe = AutoFeatureExtractor.from_pretrained(sv_model)
        self.sv = WavLMForXVector.from_pretrained(sv_model).to(self.dev).eval()
        self.asr = pipeline("automatic-speech-recognition", model=asr_model,
                            device=0 if self.dev == "cuda" else -1)

    def embed(self, path) -> np.ndarray:
        import librosa
        import torch

        wav, _ = librosa.load(str(path), sr=16000)
        inp = self.fe(wav, sampling_rate=16000, return_tensors="pt").to(self.dev)
        with torch.inference_mode():
            e = self.sv(**inp).embeddings[0].float().cpu().numpy()
        return e / np.linalg.norm(e)

    def transcribe(self, path) -> str:
        import librosa

        wav, _ = librosa.load(str(path), sr=16000)
        return self.asr({"raw": wav, "sampling_rate": 16000},
                        generate_kwargs={"language": "en", "task": "transcribe"},
                        return_timestamps=True)["text"]  # a runaway render can exceed 30 s


def _f0(path) -> float | None:
    import librosa

    wav, sr = librosa.load(str(path), sr=16000)
    f0, voiced, _ = librosa.pyin(wav, fmin=65, fmax=400, sr=sr)
    f = f0[voiced] if voiced is not None else np.array([])
    return float(np.nanmedian(f)) if len(f) else None


def _duration(path) -> float:
    import wave

    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


# --------------------------------------------------------------------------
# analysis


def _boot(xs, resamples, seed):
    xs = np.asarray([x for x in xs if x is not None], dtype=float)
    if len(xs) == 0:
        return {"mean": None, "ci": [None, None], "n": 0}
    rng = np.random.default_rng(seed)
    bs = xs[rng.integers(0, len(xs), (resamples, len(xs)))].mean(axis=1)
    return {"mean": round(float(xs.mean()), 4), "ci": [round(float(np.percentile(bs, 2.5)), 4),
                                                       round(float(np.percentile(bs, 97.5)), 4)],
            "n": int(len(xs))}


def analyse(units, meas, ref_emb, genders_by_voice, p, base_seed, manip):
    """`meas[(unit, role)]` -> {emb, wer, dur, f0}; `ref_emb[voice]`."""
    cF = np.mean([ref_emb[v] for v, g in genders_by_voice.items() if g == "F"], axis=0)
    cM = np.mean([ref_emb[v] for v, g in genders_by_voice.items() if g == "M"], axis=0)
    cF, cM = cF / np.linalg.norm(cF), cM / np.linalg.norm(cM)

    def gcue(e):
        return float(e @ cF - e @ cM)

    per_unit, pairs = [], []
    for u in units:
        rg, rw = ref_emb[u["voices"]["spec_gold"]], ref_emb[u["voices"]["spec_err"]]
        row = {"unit": u["unit"], "error_type": u["error_type"]}
        for role in ROLES:
            m = meas[(u["unit"], role)]
            v = u["voices"][role]
            row[f"m_{role}"] = float(m["emb"] @ rg - m["emb"] @ rw)
            row[f"mhat_{role}"] = float(ref_emb[v] @ rg - ref_emb[v] @ rw)
            row[f"g_{role}"] = gcue(m["emb"])
            row[f"ghat_{role}"] = gcue(ref_emb[v])
            row[f"wer_{role}"], row[f"dur_{role}"], row[f"f0_{role}"] = m["wer"], m["dur"], m["f0"]
            if "#" not in role:
                pairs.append((row[f"m_{role}"], row[f"mhat_{role}"]))
        for a, (zg, ze) in {"spec": ("spec_gold", "spec_err"), "gen": ("gen_gold", "gen_err"),
                            "narr": ("narr", "narr")}.items():
            row[f"D_{a}"] = row[f"m_{zg}"] - row[f"m_{ze}"]
            row[f"Dhat_{a}"] = row[f"mhat_{zg}"] - row[f"mhat_{ze}"]
            row[f"G_{a}"] = abs(row[f"g_{ze}"] - row[f"g_{zg}"])
            row[f"Ghat_{a}"] = abs(row[f"ghat_{ze}"] - row[f"ghat_{zg}"])
        row["price_narr"] = row["m_spec_gold"] - row["m_narr"]
        row["price_gen"] = row["m_spec_gold"] - row["m_gen_gold"]
        row["seed_noise_spec"] = abs(row["m_spec_gold"] - row["m_spec_gold#1"])
        per_unit.append(row)

    R = int(p["resamples"])
    m_arr, mh_arr = np.array([a for a, _ in pairs]), np.array([b for _, b in pairs])
    slope, icpt = np.polyfit(mh_arr, m_arr, 1)
    r2 = float(1 - np.sum((m_arr - (slope * mh_arr + icpt)) ** 2) / np.sum((m_arr - m_arr.mean()) ** 2))

    def order(a, b):
        return [k for k, _ in sorted([("spec", a), ("gen", b), ("narr", 0.0)], key=lambda t: -t[1])]

    by_type = {}
    for et in p["error_types"]:
        rows = [r for r in per_unit if r["error_type"] == et]
        if not rows:
            continue
        cell = {"n": len(rows)}
        for k in ("D_spec", "D_gen", "Dhat_spec", "Dhat_gen", "G_spec", "G_gen", "Ghat_spec", "Ghat_gen",
                  "price_narr", "price_gen"):
            cell[k] = _boot([r[k] for r in rows], R, derive_seed(base_seed, et, k))
        cell["D_spec_minus_D_gen"] = _boot([r["D_spec"] - r["D_gen"] for r in rows], R,
                                           derive_seed(base_seed, et, "sg"))
        cell["G_gen_minus_Ghat_gen"] = _boot([r["G_gen"] - r["Ghat_gen"] for r in rows], R,
                                             derive_seed(base_seed, et, "gres"))
        cell["order_real"] = order(cell["D_spec"]["mean"], cell["D_gen"]["mean"])
        cell["order_pred"] = order(cell["Dhat_spec"]["mean"], cell["Dhat_gen"]["mean"])
        by_type[et] = cell
    roles_cost = {role: {
        "wer": _boot([r[f"wer_{role}"] for r in per_unit], R, derive_seed(base_seed, role, "wer")),
        "dur": _boot([r[f"dur_{role}"] for r in per_unit], R, derive_seed(base_seed, role, "dur")),
    } for role in ("spec_gold", "gen_gold", "narr")}

    q1 = {et: bool(c["D_spec"]["ci"][0] is not None and c["D_spec"]["ci"][0] > 0) for et, c in by_type.items()}
    same_order = all(c["order_real"] == c["order_pred"] for c in by_type.values())
    cg = by_type.get("cross_gender", {})
    leak = bool(cg and cg["G_gen_minus_Ghat_gen"]["ci"][0] is not None
                and cg["G_gen_minus_Ghat_gen"]["ci"][0] > 0)
    if manip < 0.9:
        status = "INVALID (manipulation check)"
    elif not any(q1.values()):
        status = "KILL"
    elif r2 >= 0.9 and same_order and not leak:
        status = "DEFINITIONAL"
    else:
        status = "PHENOMENON"
    summary = {
        "units": len(units), "manipulation_check": round(manip, 4), "r2_margin_vs_geometry": round(r2, 4),
        "geometry_fit": {"slope": round(float(slope), 4), "intercept": round(float(icpt), 4)},
        "action_order_matches_geometry": same_order, "q1_specific_manifests": q1,
        "q2_unpredicted_gender_leak_cross_gender": leak, "by_error_type": by_type,
        "fidelity_and_cost_on_correct_lines": roles_cost,
        "seed_noise_spec_margin": _boot([r["seed_noise_spec"] for r in per_unit], R,
                                        derive_seed(base_seed, "noise")),
        "status": status,
    }
    return summary, per_unit


# --------------------------------------------------------------------------


def run(cfg: ExperimentConfig, *, stub: bool):
    import tempfile

    from echotales.pipeline.paths import RESEARCH_SCRATCH_DIR
    from echotales.research.datasets import pdnc
    from echotales.research.evaluators.voice_geometry import ears_geometry, synthetic_geometry

    p = cfg.params
    if stub:
        novels = [pdnc.synthetic_novel(seed=cfg.base_seed, n_quotes=200)]
        geom = synthetic_geometry(seed=cfg.base_seed)
        p = {**p, "per_type": 4, "engine": "stub", "resamples": 50, "min_chars": 10}
        out_dir = Path(tempfile.mkdtemp())
    else:
        novels = [pdnc.load_novel(n) for n in pdnc.available()]
        geom = ears_geometry()
        out_dir = RESEARCH_SCRATCH_DIR / "action_counterfactual" / f"{cfg.base_seed}-{p['per_type']}"
    units, narrator = design(novels, geom, p, cfg.base_seed)
    manifest = out_dir / "manifest.json"
    if p["stage"] in ("render", "all") or stub:
        renders = render(units, out_dir, p["engine"], cfg.base_seed)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"narrator": narrator, "units": units, "renders": renders}, indent=1))
        if p["stage"] == "render" and not stub:
            return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="action_counterfactual", mode="real",
                              config_hash=cfg.hash, n_units=len(units), n_trials=len(renders),
                              summary={"rendered": len(renders), "manifest": str(manifest)},
                              verdict_hint="RENDER STAGE ONLY (no measurement)"), [], {})
    data = json.loads(manifest.read_text())
    if data["units"] != units:
        raise RuntimeError("manifest units differ from the frozen design")
    renders = data["renders"]
    genders_by_voice = dict(zip(geom.ids, geom.genders))
    if stub:
        rng = np.random.default_rng(cfg.base_seed)
        ref_emb = {v: geom.emb[i] for i, v in enumerate(geom.ids)}
        meas = {}
        for r in renders:
            e = ref_emb[r["voice"]] + 0.1 * rng.normal(size=geom.emb.shape[1])
            meas[(r["unit"], r["role"])] = {"emb": e / np.linalg.norm(e), "wer": 0.05, "dur": 2.0, "f0": None}
        manip = 1.0
    else:
        from echotales.research.evaluators.voice_geometry import identify, load_encoder

        # Manipulation check with Chatterbox's own encoder (CPU), before the
        # measuring models take the GPU.
        ve = load_encoder()
        spec = [r for r in renders if r["role"] == "spec_gold"]
        manip = float(np.mean([identify(Path(r["path"]), geom, ve)[0] == r["voice"] for r in spec]))
        del ve
        gc.collect()
        mz = Measurer(p["sv_model"], p["asr_model"])
        ref_emb = {v: mz.embed(_clip(v)) for v in geom.ids}
        text_of = {u["unit"]: u["text"] for u in units}
        cache: dict[str, dict] = {}
        meas = {}
        for r in renders:
            if r["path"] not in cache:
                cache[r["path"]] = {"emb": mz.embed(r["path"]), "dur": _duration(r["path"]),
                                    "f0": _f0(r["path"]), "asr": mz.transcribe(r["path"])}
            c = cache[r["path"]]
            meas[(r["unit"], r["role"])] = {**c, "wer": wer(text_of[r["unit"]], c["asr"])}
        del mz
        gc.collect()
    summary, per_unit = analyse(units, meas, ref_emb, genders_by_voice, p, cfg.base_seed, manip)
    summary["narrator_voice"] = narrator
    voices_of = {u["unit"]: u["voices"] for u in units}
    trials = [Trial(unit_id=r["unit"], condition=r["error_type"], seed=0,
                    outputs={"voices": voices_of[r["unit"]]},
                    metrics={k: round(v, 5) for k, v in r.items()
                             if k not in ("unit", "error_type") and isinstance(v, float)})
              for r in per_unit]
    hint = (f"{summary['status']}: manip {summary['manipulation_check']}, R^2(margin~geometry) "
            f"{summary['r2_margin_vs_geometry']}, Q1 {summary['q1_specific_manifests']}, "
            f"gender leak beyond geometry {summary['q2_unpredicted_gender_leak_cross_gender']}")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="action_counterfactual",
                      mode="stub" if stub else "real", config_hash=cfg.hash, n_units=len(units),
                      n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["machine manifestation only -- not perceptual cost",
                             "narrator Delta = 0 by construction (Z-invariant render)",
                             "speaker identity by WavLM-SV, independent of the generator",
                             "audio in data/scratch/research/action_counterfactual (not committed)"]),
            trials, {} if stub else {"manifest": manifest})
