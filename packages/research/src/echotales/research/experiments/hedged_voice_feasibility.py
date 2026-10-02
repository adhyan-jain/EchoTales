"""H-HEDGE (machine-perception kill test): can the product's TTS render a
*graded* blend between two candidate speakers at all?

"Hedged rendering" proposes voicing an uncertain line with a voice between
the top-2 candidate speakers, weighted by posterior. The literature predicts
failure (lit pass, decision G3): voice identity is perceived categorically
(Latinus & Belin 2012) and embedding interpolation is used to *create new
speakers* (INSIDE 2508.19210). Before any listener sees one, this checks the
generator itself: Chatterbox conditions on continuous embeddings (T3 speaker
embedding, S3Gen x-vector) *and* discrete/prompt features (speech-token prompt,
reference mel) that cannot be interpolated. If the output's identity jumps
when the discrete prompt switches -- instead of moving smoothly with alpha --
the generator cannot express a hedge, whatever listeners would make of one.
"""

from __future__ import annotations

import numpy as np

from echotales.research.config import ExperimentConfig
from echotales.research.schema import RunResult, Trial

HYPOTHESIS_ID = "H-HEDGE"
DEFAULT_PARAMS = {"pairs": [["earsp004", "earsp024"], ["earsp010", "earsp012"]],
                  "alphas": [0.0, 0.25, 0.5, 0.75, 1.0],
                  "texts": ["I told you already, I will not go back to that house tonight.",
                            "Then tell me plainly what you want, and be done with it."],
                  "device": "cuda"}


def _identity_curve(sims_a: list[float], sims_b: list[float]) -> list[float]:
    """Relative identity in [0,1]: 0 = sounds like A, 1 = sounds like B."""
    out = []
    for a, b in zip(sims_a, sims_b):
        out.append(float((1 - a) / ((1 - a) + (1 - b))) if (2 - a - b) > 0 else 0.5)
    return out


def run(cfg: ExperimentConfig, *, stub: bool):
    p = cfg.params
    alphas = [float(a) for a in p["alphas"]]
    trials: list[Trial] = []
    curves = {}
    if stub:
        # A categorical step at 0.5: the shape the literature predicts.
        for a, b in p["pairs"]:
            curve = [0.05 if al < 0.5 else 0.95 for al in alphas]
            curves[f"{a}~{b}"] = curve
        inputs = {}
    else:
        import torch
        from chatterbox.tts import ChatterboxTTS, Conditionals, T3Cond

        from echotales.pipeline.paths import RESEARCH_SCRATCH_DIR
        from echotales.research.evaluators.voice_geometry import ears_geometry, identify, load_encoder
        from echotales.research.human_studies.synthesize import _clip_for

        geom, ve = ears_geometry(), load_encoder()
        model = ChatterboxTTS.from_pretrained(device=p["device"])
        out_dir = RESEARCH_SCRATCH_DIR / "hedged_voice" / cfg.hash
        out_dir.mkdir(parents=True, exist_ok=True)
        import torchaudio
        for a_id, b_id in p["pairs"]:
            model.prepare_conditionals(str(_clip_for(a_id)))
            ca = model.conds
            model.prepare_conditionals(str(_clip_for(b_id)))
            cb = model.conds
            rel = []
            for al in alphas:
                # Continuous parts are interpolated; discrete prompt parts
                # cannot be, so they switch at alpha = 0.5.
                src = ca if al < 0.5 else cb
                t3 = T3Cond(speaker_emb=(1 - al) * ca.t3.speaker_emb + al * cb.t3.speaker_emb,
                            cond_prompt_speech_tokens=src.t3.cond_prompt_speech_tokens,
                            emotion_adv=src.t3.emotion_adv)
                gen = dict(src.gen)
                gen["embedding"] = (1 - al) * ca.gen["embedding"] + al * cb.gen["embedding"]
                model.conds = Conditionals(t3, gen)
                ids_sims = []
                for ti, text in enumerate(p["texts"]):
                    torch.manual_seed(cfg.base_seed + ti)
                    wav = model.generate(text)
                    path = out_dir / f"{a_id}-{b_id}-a{int(al * 100):03d}-t{ti}.wav"
                    torchaudio.save(str(path), wav, model.sr, encoding="PCM_S", bits_per_sample=16)
                    nearest, sims = identify(path, geom, ve)
                    ids_sims.append((nearest, sims[a_id], sims[b_id]))
                    trials.append(Trial(unit_id=f"{a_id}~{b_id}:t{ti}", condition=f"alpha={al}",
                                        seed=cfg.base_seed + ti,
                                        outputs={"nearest": nearest,
                                                 "third_identity": nearest not in (a_id, b_id)},
                                        metrics={"sim_a": round(sims[a_id], 4), "sim_b": round(sims[b_id], 4)}))
                sa = float(np.mean([x[1] for x in ids_sims]))
                sb = float(np.mean([x[2] for x in ids_sims]))
                rel.append(_identity_curve([sa], [sb])[0])
            curves[f"{a_id}~{b_id}"] = [round(x, 4) for x in rel]
        inputs = {}
    # Graded vs categorical: how much of the A->B identity change happens in
    # the single step that crosses the discrete switch (0.25 -> 0.75 bracket).
    summary = {"alphas": alphas, "curves": curves, "step_share": {}}
    for k, c in curves.items():
        total = abs(c[-1] - c[0]) or 1e-9
        i_lo, i_hi = alphas.index(0.25), alphas.index(0.75)
        mid = abs(c[alphas.index(0.5)] - c[i_lo])
        summary["step_share"][k] = round(mid / total, 4)
        summary.setdefault("endpoint_separation", {})[k] = round(total, 4)
        _ = i_hi
    third = [t for t in trials if t.outputs.get("third_identity")]
    summary["third_identity_share"] = round(len(third) / len(trials), 4) if trials else None
    shares = list(summary["step_share"].values())
    categorical = all(s > 0.6 for s in shares)
    hint = ("KILL-SIGNAL: identity changes mostly at the discrete prompt switch (categorical); "
            "this generator cannot express a graded hedge" if categorical else
            "SURVIVES (machine level): identity moves gradually with alpha; a listener test is next")
    return (RunResult(hypothesis_id=HYPOTHESIS_ID, experiment="hedged_voice_feasibility",
                      mode="stub" if stub else "real", config_hash=cfg.hash,
                      n_units=len(curves), n_trials=len(trials), summary=summary, verdict_hint=hint,
                      notes=["identity measured by Chatterbox's own voice encoder, not by listeners"]),
            trials, inputs)
