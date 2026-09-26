# Moving GPU work to RunPod — what actually has to change

**Written 2026-09-25.** Local GPU (RTX 4060, 8 GB) remains the default and is
sufficient for everything the project currently measures. This note exists so
that when a rented GPU *is* used, the changes are known in advance rather than
discovered at $0.40/hour.

> **Budget posture.** Cloud GPU is for **bounded evaluation only** — answering
> a specific question and stopping. It is not a development environment. Every
> item below is written to keep a session short and its cost predictable.
> `docs/archive/COMPLETION_PLAN.md` Track 5 item 24 budgets roughly $5–10 in total.

---

## 1. What the 8 GB constraint currently forces

These are accommodations for a small GPU. Each is a knob to *undo* on a larger
card, and each is worth measuring before and after.

| Accommodation | Where | On a 24–48 GB GPU |
|---|---|---|
| `enable_model_cpu_offload()` | `render/panels.py:269, 527, 596` | **Remove.** It streams submodules between host and device per step and is the single largest per-image cost on the local card. |
| `enable_vae_slicing()` | `render/panels.py:267` | Remove; decode the latent in one pass. |
| `torch_dtype=float16` | `render/panels.py:255, 387` | Keep. A quality/speed choice, not a memory workaround. |
| `render.direction_first: true` | `config.json` | **The important one.** It exists so the LLM director and the diffusion pipeline never hold the GPU simultaneously — on 8 GB they cannot coexist. With headroom, set it `false` and let direction and generation interleave, removing a whole serialised pass. |
| One sequential job worker | `jobs.py:332` — "one daemon worker thread; jobs run strictly sequentially, process-wide" | Explicitly documented as matching the ollama/diffusion GPU-sharing constraint. With headroom it can become a small pool. **Raise the worker count only after confirming VRAM headroom**, or two jobs will OOM each other. |
| `max_references=2` on multi-character panels | `render/panels.py` | Measured as a *checkpoint* ceiling, not a memory one (EVOLUTION 4.45/4.46). Do not assume a bigger GPU lifts it. |

---

## 2. Configuration that must change

Both files already exist; nothing new is needed.

**`.env`** — environment-dependent values:

```
ECHOTALES_LLM_MODE=local
ECHOTALES_MODEL_BACKEND=ollama
ECHOTALES_LLM_LOCAL_HOST=http://localhost:11434   # -> the pod's own ollama
ECHOTALES_LLM_LOCAL_NUM_CTX=8192                  # raise if the pod allows
```

Run ollama **on the pod**, not over the network from home. A remote
`LOCAL_HOST` would put an internet round trip on every one of ~550 NER calls
per volume.

**`config.json`** — hand-edited values: `render.direction_first` (above) and
`gateway.host`, which points at a local service that will not exist on the pod.

**Do not copy `.env` to the pod.** It holds live OpenRouter / Gemini / NVIDIA /
CivitAI keys that no GPU job needs. Write a minimal one on the pod with only
the four `ECHOTALES_*` values.

---

## 3. What has to be transferred, and what must not be

| Item | Size | Notes |
|---|---|---|
| Diffusion checkpoints (NoobAI XL, Illustrious, GuoFeng3) | GBs each | Put on a **persistent volume**, not the container image. Re-downloading per session is most of a short session's cost. |
| CLIP ViT-L/14 (pixel-QA bench) | ~1.7 GB | The only thing blocking `COMPLETION_PLAN` Track 5 items 19–21. Trivial to fetch on a pod. |
| The SQLite database | ~20 MB | Transfer the one `data/scratch/reruns/*.db` the run needs, not all of `data/`. |
| Source EPUBs | ~20 MB | **Third-party copyrighted texts.** Never bake into an image, never push to a registry. Transfer directly; delete with the pod. |
| `.env` with API keys | — | **Do not transfer.** |
| Generated panels/video | Hundreds of MB | Plan the *return* path before starting. Output lands under `data/novels/<CODE>/panels/vN/` per `pipeline/paths.py`. |

---

## 4. Run-order trap, learned the hard way

**`resolve` destroys persona state.** `resolve/runner.py:832` executes
`DELETE FROM self_persona_binding WHERE self_id LIKE '<novel>:%'`.

On 2026-09-25 a full-volume `run` was followed by a separate
`resolve --capture-evidence` to populate the ablation cache. That second
resolve silently dropped all 92 Self↔Persona bindings the personas stage had
just written. The symptom surfaces three stages later and looks nothing like
the cause: `state_of` returns no `persona_ids`, so `build_render_plan` yields
`characters=0`, so every panel prompt comes out generic with no character
identity in it. The render *appears* to succeed.

**Correct order is `run` → `observations`. If an evidence capture is needed,
`resolve --capture-evidence` must run before the personas stage, or the
personas stage must be rebuilt afterwards.** On a rented GPU this mistake costs
the whole session, because nothing fails loudly.

---

## 5. What to measure in the first paid session

Keep it to a single question and record the answer so it need not be re-bought.

1. **Per-panel wall time with offload removed.** The local figure is the honest
   comparison point. This number decides whether volume-scale rendering is
   feasible at all.
2. **Whether `direction_first: false` is actually faster**, or whether
   interleaving costs more in model-swap overhead than it saves.
3. **One observer-contrast pair** (`COMPLETION_PLAN` item 18) at production
   quality — the project's central figure.
4. **CLIPScore over the existing ~1,180 panels.** Compute-cheap once the model
   is resident, and it needs no new generation at all: it converts "is the
   output getting better?" into a curve across versions.

Items 3 and 4 are the highest value per rented minute, because both leave
artifacts that remain useful after the pod is gone.

---

## 6. What does *not* need a rented GPU

Stated because it is easy to over-buy:

- The full resolution pipeline. A 199-chapter volume completes in **47 minutes**
  on the local card with 0 escalations.
- Every evaluation command — `eval`, `ablate`, `annotate` — is pure SQLite and
  Python, with no GPU at all.
- Both baselines. Baseline A is one model call; Baseline B is 177 small ones.
- Stub-mode renders, which exercise the whole plan/cache/compose path without
  generating a pixel. **The observer-conditioning mechanism can be verified this
  way** — only the final *image* needs real hardware.
