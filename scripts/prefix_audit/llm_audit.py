"""Prefix-faithfulness of the LLM trait path (docs/research/PREFIX_FAITHFULNESS/PREREG_LLM.md).

    # plumbing only: a fake client whose answers are hashed from the prompt. Measures nothing about a model.
    PYTHONPATH=<worktree>/packages/core/src:<worktree>/packages/pipeline/src \
      python scripts/prefix_audit/llm_audit.py --novel omniscient-readers-viewpoint --backend fake

    # the real run: refuses unless PREFIX_AUDIT_ALLOW_GPU=1 AND the GPU is not already in use
    PREFIX_AUDIT_ALLOW_GPU=1 python scripts/prefix_audit/llm_audit.py --novel <id> --backend model

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Stored mention assignment held fixed (PREREG.md Amendment 1). Output holds
counts and closed-vocabulary values only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import types
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A  # noqa: E402
import common as C  # noqa: E402
from echotales.pipeline.persona import build as persona_build  # noqa: E402
from echotales.pipeline.persona.extract import CharacterProfileResponse  # noqa: E402,F401

DISCRETE = ("gender", "age_band", "register")
BIG5_THRESHOLDS = (0.05, 0.10, 0.20)
GPU_MAX_USED_FRACTION = 0.35


def gpu_is_free() -> tuple[bool, str]:
    """The owner's rule: heavy models run on a GPU that has been checked free first. Any doubt means not free."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip().splitlines()[0]
        used, total = (float(x) for x in out.split(","))
        runner = subprocess.run(["pgrep", "-f", "ollama runner"], capture_output=True, text=True).stdout.split()
    except Exception as exc:  # noqa: BLE001
        return False, f"could not read GPU state ({exc})"
    if used / total > GPU_MAX_USED_FRACTION:
        return False, f"GPU memory {used:.0f}/{total:.0f} MiB in use (limit {GPU_MAX_USED_FRACTION:.0%})"
    if runner:
        return False, f"an ollama runner is active (pids {', '.join(runner)})"
    return True, "GPU free"


class FakeClient:
    """Answers hashed from the prompt: identical prompts agree, different prompts differ. Plumbing only."""

    backend = "fake"

    def complete(self, task, prompt, schema, *, system="", novel_id="", **_kw):  # noqa: ANN001
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        value = schema(
            gender=("male", "female", "unknown")[h % 3], age_band=("youth", "adult", "elder")[(h >> 8) % 3],
            speech_register=("formal", "neutral", "casual")[(h >> 16) % 3],
            extraversion=round(((h >> 24) % 100) / 100, 2),
        )
        return types.SimpleNamespace(value=value)


class Counting:
    """Counts calls and enforces the budget declared in the pre-registration."""

    def __init__(self, inner, cap: int) -> None:
        self.inner, self.cap, self.calls = inner, cap, 0
        self.backend = getattr(inner, "backend", None)
        self.resolved_models = getattr(inner, "resolved_models", None)

    def complete(self, *args, **kwargs):  # noqa: ANN002, ANN003
        self.calls += 1
        if self.calls > self.cap:
            raise RuntimeError(f"call budget {self.cap} exceeded")
        return self.inner.complete(*args, **kwargs)


def make_factory(backend: str, cap: int):
    if backend == "fake":
        return lambda _store: Counting(FakeClient(), cap)
    ok, why = gpu_is_free()
    import os

    if os.environ.get("PREFIX_AUDIT_ALLOW_GPU") != "1":
        raise SystemExit("refusing: set PREFIX_AUDIT_ALLOW_GPU=1 after the owner has approved the run")
    if not ok:
        raise SystemExit(f"refusing to start the model backend: {why}")
    from echotales.pipeline.llm.client import ModelClient

    def factory(store):  # noqa: ANN001, ANN202
        client = ModelClient(store=store)
        # A worktree has no .env (gitignored), so settings silently resolve to the STUB backend and require_ready()
        # passes: a "model" run would then measure the stub. Pin the backend to the local daemon (the $0 path of the
        # pre-registration; the gateway on :11435 is not known to be local and is never used here).
        from echotales.pipeline.config import ModelBackend
        from echotales.pipeline.llm.tasks import Task

        if client.backend is not ModelBackend.OLLAMA:
            raise SystemExit(f"refusing: backend resolved to {client.backend}, need ECHOTALES_LLM_MODE=local (ollama)")
        # require_ready() demands every task's model, including llama3:latest for segmentation/sentiment, which the
        # persona stage never calls; check only the two tasks this audit uses.
        client.resolved_models = {t.value: client.model_for(t) for t in (Task.CHARACTER_PROFILE, Task.PERSONA_SPLIT)}
        import httpx

        installed = {m["name"] for m in httpx.get(f"{client.settings.llm_local_host}/api/tags", timeout=5.0).json()["models"]}
        missing = sorted(set(client.resolved_models.values()) - installed)
        if missing:
            raise SystemExit(f"refusing: ollama models not installed: {missing}")
        return Counting(client, cap)

    return factory


def big_five(text: str | None) -> dict[str, float]:
    return {k.strip(): float(v) for k, _, v in (p.partition("=") for p in (text or "").split(",")) if v}


def pair_diff(a: dict, b: dict) -> dict:
    out = {"discrete": [k for k in DISCRETE if a.get(k) != b.get(k)]}
    fa, fb = big_five(a.get("big_five")), big_five(b.get("big_five"))
    delta = max((abs(fa[k] - fb[k]) for k in fa.keys() & fb.keys()), default=0.0)
    out["big_five_delta"] = round(delta, 3)
    return out


def build(nid: str, src: Path, tag: str, k: int | None, factory, prefix_causal: bool = False):
    db = C.fresh_copy(src, f"{nid}_llm_{'pc_' if prefix_causal else ''}{tag}")
    A.prepare(db, nid, k)
    store = C.Store(db)
    client = factory(store)
    persona_build.build_personas(nid, store, client=client, prefix_causal=prefix_causal)
    store.conn.commit()
    return store, client.calls, f"{getattr(client, 'backend', None)} {client.resolved_models or ''}".strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novel", required=True)
    ap.add_argument("--backend", choices=("fake", "model"), required=True)
    ap.add_argument("--ks", default=None)
    ap.add_argument("--max-calls", type=int, default=200, help="per build; the pre-registered upper bound is below this")
    ap.add_argument("--out", default=None)
    ap.add_argument("--prefix-causal", action="store_true", help="PREREG_LLM.md Addendum 3: gate the model read on the mentions read so far")
    args = ap.parse_args()
    nid = args.novel
    ks = [int(x) for x in args.ks.split(",")] if args.ks else C.CUTS[nid]
    factory = make_factory(args.backend, args.max_calls)
    src = C.snapshot_source(nid)
    full, full_calls, backend_name = build(nid, src, "full", None, factory, args.prefix_causal)
    result: dict = dict(
        audit="prefix-faithfulness, LLM trait path", novel=nid, backend=args.backend, backend_name=backend_name,
        PLUMBING_ONLY=args.backend == "fake", label_provenance="SYSTEM-INTERNAL, no labels",
        calls=dict(full=full_calls), by_k={},
    )
    pairs: list[dict] = []
    for k in ks:
        pre, calls, _ = build(nid, src, f"k{k}", k, factory, args.prefix_causal)
        pre2, calls2, _ = build(nid, src, f"k{k}_repeat", k, factory, args.prefix_causal)
        result["calls"][str(k)] = [calls, calls2]
        fs, ts, t2 = A.read_state(full, nid, k), A.read_state(pre, nid, k), A.read_state(pre2, nid, k)
        common = sorted(e for e in set(fs) & set(ts) & set(t2) if pre.chapters_for_target(nid, e))
        classes: Counter = Counter()
        for e in common:
            for pid in sorted(set(fs[e]["attrs"]) & set(ts[e]["attrs"]) & set(t2[e]["attrs"])):
                a, b, c = fs[e]["attrs"][pid], ts[e]["attrs"][pid], t2[e]["attrs"][pid]
                pa, pb = a.get("trait_provenance"), b.get("trait_provenance")
                cls = "both_llm" if pa == pb == "llm" else ("gate" if pa != pb else "both_deterministic")
                classes[cls] += 1
                pairs.append(dict(novel=nid, entity=e, k=k, cls=cls, full_vs_prefix=pair_diff(a, b), prefix_vs_repeat=pair_diff(b, c)))
        result["by_k"][str(k)] = dict(entities_in_both=len(common), classes=dict(classes))
        print(nid, "k=", k, "classes", dict(classes), "calls", calls, calls2, flush=True)
        pre.close()
        pre2.close()
    result["summary"] = summarise(pairs)
    result["pairs"] = pairs
    out = Path(args.out) if args.out else C.RESULTS / f"llm_{args.backend}{'_pc' if args.prefix_causal else ''}_{nid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print("wrote", out)


def summarise(pairs: list[dict], seed: int = 20261016) -> dict:
    """L1: among both-model pairs, full-vs-prefix difference rate minus the repeat-vs-repeat (noise) rate, cluster bootstrap."""
    out: dict = {"classes": dict(Counter(p["cls"] for p in pairs))}
    both = [p for p in pairs if p["cls"] == "both_llm"]
    out["both_llm_pairs"] = len(both)
    if not both:
        out["note"] = "no pair in which both builds used the model: L1 cannot be assessed"
        return out
    d = [(bool(p["full_vs_prefix"]["discrete"]), bool(p["prefix_vs_repeat"]["discrete"])) for p in both]
    out["discrete_full_vs_prefix"] = sum(x for x, _ in d)
    out["discrete_noise_floor"] = sum(y for _, y in d)
    for t in BIG5_THRESHOLDS:
        out[f"big_five_full_vs_prefix_gt_{t}"] = sum(p["full_vs_prefix"]["big_five_delta"] > t for p in both)
        out[f"big_five_noise_floor_gt_{t}"] = sum(p["prefix_vs_repeat"]["big_five_delta"] > t for p in both)
    clusters: dict = {}
    for p, (x, y) in zip(both, d, strict=True):
        clusters.setdefault((p["novel"], p["entity"]), []).append(int(x) - int(y))
    keys = list(clusters)
    rng = random.Random(seed)
    means = []
    for _ in range(2000):
        draw = [v for key in (rng.choice(keys) for _ in keys) for v in clusters[key]]
        means.append(sum(draw) / len(draw))
    means.sort()
    out["excess_over_noise_mean"] = round(sum(x - y for x, y in d) / len(d), 4)
    out["excess_over_noise_bootstrap95"] = [round(means[50], 4), round(means[1949], 4)]
    out["L1_verdict_rule"] = "supported only if the bootstrap interval excludes 0 (lower bound > 0)"
    return out


if __name__ == "__main__":
    main()
