"""Backing functions for the webview's Research page (GET /api/research/summary, GET /api/research/items,
POST /api/research/probe).

The research claim shown here is name-keyed memory leakage in LLM reading of fiction: ask a model who an expression
refers to BEFORE the book reveals it, once with the original names (arm A) and once with every proper noun consistently
renamed (arm B, a letter cipher; arm B3, cue-preserving natural pseudonyms). A model that answers the true identity
only under original names is using memory of the book, not the text in front of it.

Two halves, both deliberately thin:

  * summary() reads ONLY the stored result files under data/eval/chimera/ and reshapes them. It computes nothing the
    study did not already measure, apart from weighted averages of stored per-model numbers (the cue-preserving table,
    where the stored files give gaps and original-name rates but not the cipher / pseudonym rates directly).
  * items() / probe() serve the six demo items that scripts/chimera/build_demo_items.py wrote to
    data/scratch/demo/probe_items.json, and run ONE local ollama model on one to three arms of one item.

Why this module is allowed to be dumb about the study: the pipeline package must not import the study scripts
(scripts/chimera/ are flat scripts that import the research stack and set ECHOTALES_LLM_MODE). Everything the server needs
is precomputed into the JSON files.

Safety rules baked in, from the owner's resource rules (2026-10-02, 2026-10-16): only the five local ollama models in
ALLOWED_MODELS can be called (no paid API is reachable from here); one probe at a time; the model is unloaded
(keep_alive 0) after the last arm even on failure; a model that ollama placed partly in system RAM is refused rather
than run; and a probe is refused when under 1 GiB of RAM is available (the machine is RAM-constrained).
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

OLLAMA_HOST = "http://127.0.0.1:11434"
#: The five local models the study ran. The tag ollama reports for phi4-mini is `phi4-mini:latest`.
ALLOWED_MODELS = ("qwen2.5:7b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "gemma2:9b")
_MODEL_ALIASES = {"phi4-mini": "phi4-mini:latest"}
ARMS = ("A", "B", "B3")
ARM_LABELS = {"A": "original names", "B": "letter cipher", "B3": "cue-preserving pseudonyms"}
#: Same decoding as the study (pd_v2.OPTS) so a live answer is comparable to a stored one.
OLLAMA_OPTIONS = {"temperature": 0, "seed": 20261016, "num_predict": 24, "num_ctx": 2048}
MIN_AVAILABLE_GIB = 1.0
PROVENANCE = "Text-derived oracle; model-selected events; no human labels."

EVAL_DIR = Path("data") / "eval" / "chimera"
FILES = {
    "pooled": "pd_final_pooled.json",
    "dose": "pd_dose_response.json",
    "v5": "pd_v5/analysis.json",
    "v6": "pd_v6/analysis.json",
    "v3": "pd_v3/analysis.json",
    "validity": "pd_memory_free_validity.json",
    "adversarial": "pd_adversarial_checks.json",
    "plan": "confirm_runpod_plan.json",
    "confirm": "confirm/main/analysis.json",
    "rf_e2e": "rf_e2e/analysis.json",
}
ITEMS_REL = Path("data") / "scratch" / "demo" / "probe_items.json"
TIMINGS_REL = Path("docs") / "paper" / "project_doc" / "figures" / "demo_timings.json"

REFERENCE_MODEL = "gpt-5.6-luna"
LOCAL_MODELS = ("gemma2:9b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "qwen2.5:7b")
DATASETS = (
    ("v2", "v2: 19 events"),
    ("v3", "v3: 12 new books"),
    ("v6", "v6: 7 events, did not replicate"),
)

_probe_lock = threading.Lock()


class ResearchDemoError(Exception):
    """A failure with an HTTP status the route can return as-is and a message a person can act on."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- helpers
def default_root() -> Path:
    """Repo root: the cwd when it holds the data folder (how the server is documented to run), else this file's repo."""
    cwd = Path.cwd()
    if (cwd / EVAL_DIR).is_dir():
        return cwd
    return Path(__file__).resolve().parents[5]


def _clean(x: Any) -> Any:
    """NaN and infinity are valid Python JSON but not valid JSON; the browser's parser rejects them."""
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def _read(root: Path, key: str, missing: list[str]) -> dict | None:
    path = root / EVAL_DIR / FILES[key]
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        missing.append(str(EVAL_DIR / FILES[key]))
    except ValueError:
        missing.append(f"{EVAL_DIR / FILES[key]} (unreadable)")
    return None


def _r(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(float(x), nd)


def _interval(gap: float | None, ci: list | None, events: int | None = None, items: int | None = None) -> dict | None:
    if gap is None or not ci:
        return None
    return dict(gap=_r(gap), lo=_r(ci[0]), hi=_r(ci[1]), events=events, items=items)


# --------------------------------------------------------------------------- summary
def _gap_by_model(pooled: dict | None, adv: dict | None) -> dict | None:
    """Per-model A-minus-B gap with its event-cluster 95% interval, per dataset (stored in the adversarial-checks file
    for v2 and v3, and in the pooled file for v6)."""
    if not adv and not pooled:
        return None
    rows = []
    for model in (REFERENCE_MODEL, *LOCAL_MODELS):
        cells = {}
        for ds in ("v2", "v3"):
            c = ((adv or {}).get(f"pd_{ds}") or {}).get("per_model_cluster", {}).get(model)
            if c:
                cells[ds] = _interval(c.get("pooled_gap"), c.get("event_cluster_ci95"), c.get("events"), c.get("items"))
        c6 = ((pooled or {}).get("v6_per_model") or {}).get(model, {}).get("cluster")
        if c6:
            cells["v6"] = _interval(c6.get("gap_A_minus_B"), c6.get("ci"), c6.get("events"))
        if cells:
            rows.append(dict(model=model, reference=(model == REFERENCE_MODEL), cells=cells))
    pools = []
    vp = (pooled or {}).get("valid_pool") or {}
    lp = (pooled or {}).get("luna_only") or {}
    for key, label in (("v2", "v2"), ("v3", "v3"), ("v6", "v6"), ("all_v2_v3_v6", "all three")):
        if key in vp:
            pools.append(dict(key=key, label=label, kind="local_pool",
                              **(_interval(vp[key]["gap_A_minus_B"], vp[key]["ci"], vp[key]["events"]) or {}),
                              events_positive=vp[key].get("events_positive"), events_negative=vp[key].get("events_negative")))
    for key, label in (("v2", "v2"), ("v3", "v3"), ("v6", "v6"), ("all_v2_v3_v6", "all three")):
        if key in lp:
            pools.append(dict(key=key, label=label, kind="reference",
                              **(_interval(lp[key]["gap_A_minus_B"], lp[key]["ci"], lp[key]["events"]) or {}),
                              events_positive=lp[key].get("events_positive"), events_negative=lp[key].get("events_negative")))
    return dict(datasets=[dict(key=k, label=lbl) for k, lbl in DATASETS], rows=rows, pools=pools,
                note="Gap = share of pre-reveal items answered with the true identity under original names minus under a "
                     "renamed text. Intervals are 95% event-cluster bootstrap. v6 is the fresh set that did not replicate.")


def _valid_local_models(pooled: dict | None) -> list[str]:
    per = (pooled or {}).get("per_dataset_valid_models") or {}
    sets = [set(per.get(k, [])) for k in ("v2", "v3")]
    return [m for m in LOCAL_MODELS if sets and all(m in s for s in sets)]


def _cue_rows(v5: dict | None, validity: dict | None, pooled: dict | None) -> dict | None:
    """Premature rate and plain-control accuracy for A, B and B3. The stored files give the original-name rate
    (validity file) and the gaps A-B and A-B3 (v5 analysis), so B = A - gap_AB and B3 = A - gap_AB3, averaged over the
    v2 and v3 cells weighted by the number of pre-reveal items. Control accuracy is the plain mean over the cells."""
    if not v5 or not validity:
        return None
    per_model = v5.get("per_model") or {}

    def pool(models: list[str], label: str, stored_pool: dict | None) -> dict | None:
        w = a = b = b3 = 0.0
        ctrl = dict(A=[], B=[], B3=[])
        for m in models:
            for ds in ("v2", "v3"):
                cell = (per_model.get(m) or {}).get(f"pd_{ds}")
                val = ((validity.get(f"pd_{ds}") or {}).get("per_model") or {}).get(m)
                if not cell or not val:
                    continue
                pe = cell["per_event"]
                n = pe["pairs"]
                a_rate = val["premature_A"]
                w += n
                a += n * a_rate
                b += n * (a_rate - pe["gap_A_minus_B"])
                b3 += n * (a_rate - pe["gap_A_minus_B3"])
                ctrl["A"].append(cell["ctrl_acc_A"])
                ctrl["B"].append(cell["ctrl_acc_B"])
                ctrl["B3"].append(cell["ctrl_acc_B3"])
        if not w:
            return None
        rate = dict(A=a / w, B=b / w, B3=b3 / w)
        gap_ab, gap_ab3 = rate["A"] - rate["B"], rate["A"] - rate["B3"]
        out = dict(label=label, models=models, items=int(w),
                   arms=[dict(arm=k, label=ARM_LABELS[k], premature=_r(rate[k]),
                              control_accuracy=_r(sum(ctrl[k]) / len(ctrl[k]))) for k in ARMS],
                   gap_A_minus_B=_r(gap_ab), gap_A_minus_B3=_r(gap_ab3))
        if stored_pool:
            out.update(events=stored_pool.get("events"), recovered_fraction=stored_pool.get("recovered_fraction"),
                       recovered_fraction_ci=stored_pool.get("recovered_fraction_ci"),
                       gap_A_minus_B3_ci=stored_pool.get("gap_A_minus_B3_ci"), verdict=stored_pool.get("verdict"))
        else:
            out.update(recovered_fraction=_r((gap_ab - gap_ab3) / gap_ab) if gap_ab > 1e-9 else None)
        return out

    valid = _valid_local_models(pooled)
    pools = [p for p in (
        pool(valid, f"Local models passing the validity gate ({len(valid)})", (v5.get("pools") or {}).get("G2_valid")),
        pool([REFERENCE_MODEL], "Reference model (gpt-5.6-luna)", None),
    ) if p]
    if not pools:
        return None
    return dict(pools=pools,
                note="B3 keeps the cues a letter cipher destroys (gender, first name vs surname) and replaces only the "
                     "specific names. If lost cues explained the gap, B3 would recover it; a recovered fraction near zero "
                     "or below means it does not.")


def _dose(dose: dict | None) -> dict | None:
    if not dose:
        return None
    luna = dose.get("luna_gap_vs_local_recognition") or {}
    loc = dose.get("valid_local_pool_gap_vs_local_recognition") or {}
    counts = sorted({*(luna.get("mean_gap_by_recognition_count") or {}), *(loc.get("mean_gap_by_recognition_count") or {})},
                    key=int)
    table = [dict(recognised=int(c),
                  events=(loc.get("events_per_count") or luna.get("events_per_count") or {}).get(c),
                  mean_gap_reference=_r((luna.get("mean_gap_by_recognition_count") or {}).get(c)),
                  mean_gap_local=_r((loc.get("mean_gap_by_recognition_count") or {}).get(c))) for c in counts]
    return dict(table=table, events=loc.get("events") or luna.get("events"),
                spearman_reference=_r(luna.get("spearman")), perm_p_reference=luna.get("perm_p"),
                spearman_local=_r(loc.get("spearman")), perm_p_local=loc.get("perm_p"),
                note="Post hoc. 'Recognised' = how many of the 5 local models name the true identity from the original "
                     "names with the book title given (0 = unknown book, 5 = famous). Gap grows with recognition.")


def _validity(validity: dict | None, pooled: dict | None) -> dict | None:
    if not validity:
        return None
    v6 = (pooled or {}).get("v6_per_model") or {}
    rows = []
    for m in (REFERENCE_MODEL, *LOCAL_MODELS):
        cells = {}
        for ds in ("v2", "v3"):
            c = ((validity.get(f"pd_{ds}") or {}).get("per_model") or {}).get(m)
            if c:
                cells[ds] = dict(g2a=_r(c.get("G2a_B_eq_B2_real_controls")), g2b=_r(c.get("G2b_A_eq_B_synthetic_unseen")))
        if m in v6:
            cells["v6"] = dict(g2a=_r(v6[m].get("g2a_v6")), g2b=_r(v6[m].get("synth_v3")))
        for c in cells.values():
            c["valid"] = bool(c["g2a"] is not None and c["g2b"] is not None and c["g2a"] >= 0.90 and c["g2b"] >= 0.80)
        if cells:
            rows.append(dict(model=m, reference=(m == REFERENCE_MODEL), cells=cells))
    return dict(rows=rows, datasets=[dict(key=k, label=lbl) for k, lbl in DATASETS],
                note="Memory-free validity gate. G2a: the two independent ciphers B and B2 give the same answer on plain "
                     "control items (>= 0.90), so renaming does not itself change reading. G2b: original and ciphered "
                     "text agree on synthetic unseen text (>= 0.80), so a cipher does not change answers where there is "
                     "nothing to remember. Models failing either are excluded from the local pool.")


def _design(plan: dict | None) -> list[dict] | None:
    if not plan:
        return None
    out = []
    for key, label in (("lean_120_events_7_items", "Lean"), ("core_150_events_7_items", "Core"),
                       ("wide_200_events_8_items", "Wide")):
        d = plan.get(key)
        if not d:
            continue
        g = d["design"]
        three = d.get("3_open_models") or {}
        a100, h100 = three.get("A100_80GB_community") or {}, next(
            (v for k, v in three.items() if k.startswith("H100")), {})
        out.append(dict(name=label, events=g["events"], dev_events=g["dev"], test_events=g["test"],
                        items_per_event=g["items_per_event"], short_calls=g["short_calls"], long_calls=g.get("long_calls_E5"),
                        a100_hours=a100.get("total_hours"), a100_usd=a100.get("expected_usd"),
                        a100_worst_usd=a100.get("worst_2x_usd"), h100_hours=h100.get("total_hours"),
                        h100_usd=h100.get("expected_usd")))
    return out or None


def _verdicts(v3: dict | None, v5: dict | None, v6: dict | None) -> list[dict]:
    out = []
    if v3 and v3.get("verdict"):
        out.append(dict(experiment="v3 (12 fresh books)", verdict=v3["verdict"]))
    if v5 and (v5.get("pools") or {}).get("G2_valid", {}).get("verdict"):
        out.append(dict(experiment="v5 (cue-preserving arm)", verdict=v5["pools"]["G2_valid"]["verdict"]))
    if v6 and (v6.get("pool") or {}).get("verdict"):
        out.append(dict(experiment="v6 (7 fresh events)", verdict=v6["pool"]["verdict"]))
    return out


def _timings(root: Path) -> dict | None:
    try:
        return json.loads((root / TIMINGS_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rf_stratum(a: dict | None, label: str) -> dict | None:
    """One model stratum of RF-E2E (whole-volume vs versioned character card): pooled leak rates per rule and the input/memory channels."""
    if not a:
        return None
    out = dict(label=label, models=a.get("models"), rules=[])
    for key, rule in (("A_primary_EXPLICIT_IMPLIED", "Strict text rule"), ("B_EXPLICIT_IMPLIED", "Judge rule")):
        q = (a.get(key) or {}).get("pooled") or {}
        if not q:
            continue
        rt, rf1, mem = q.get("rates") or {}, q.get("RF1_input_channel") or {}, q.get("RF3_memory_channel") or {}
        out["rules"].append(dict(rule=rule, events=(a.get(key) or {}).get("events"), whole_renamed=_r(rt.get("W_ren")), versioned_renamed=_r(rt.get("P_ren")),
                                 whole_original=_r(rt.get("W_orig")), versioned_original=_r(rt.get("P_orig")), input_channel=_interval(rf1.get("estimate"), rf1.get("ci")),
                                 memory_channel=_interval(mem.get("estimate"), mem.get("ci")), supported=rf1.get("passes")))
    return out if out["rules"] else None


def _rf(rf: dict | None) -> dict | None:
    # RF-E2E (PREREG_RF_E2E_addendum_6 to 8): the Channel 2 look-ahead on a generic LLM character-card design, split from memory by renaming
    if not rf:
        return None
    strata = [x for x in (_rf_stratum(rf, "7-8B local models"), _rf_stratum(rf.get("larger"), "24-32B open models")) if x]
    return dict(strata=strata, not_run=rf.get("not_run"), source="data/eval/chimera/rf_e2e/analysis.json") if strata else None


def _confirm(c: dict | None) -> dict | None:
    if not c or "H1" not in c:
        return None
    h1, p1 = c["H1"], c.get("P1") or {}
    return dict(events=c.get("n_events"), primary=c.get("n_primary_test"), models=c.get("models"), pooled_gap=_interval(h1.get("pooled"), h1.get("ci")),
                fame_contrast=_interval(p1.get("difference"), p1.get("ci")), fame_p=_r(p1.get("p_one_sided")))


def summary(root: Path | str | None = None) -> dict:
    """Everything the Research dashboard shows, from the stored result files only. A missing file leaves its section
    null and is listed under `missing`; it never fails the whole page."""
    base = Path(root) if root else default_root()
    missing: list[str] = []
    data = {k: _read(base, k, missing) for k in FILES}
    pooled, v5 = data["pooled"], data["v5"]
    vp = (pooled or {}).get("valid_pool") or {}
    lp = (pooled or {}).get("luna_only") or {}
    g2 = ((v5 or {}).get("pools") or {}).get("G2_valid") or {}
    cue = _cue_rows(v5, data["validity"], pooled)
    headline = dict(
        reference_gap=(_interval(lp["all_v2_v3_v6"]["gap_A_minus_B"], lp["all_v2_v3_v6"]["ci"], lp["all_v2_v3_v6"]["events"])
                       if "all_v2_v3_v6" in lp else None),
        local_pool_gap=(_interval(vp["all_v2_v3_v6"]["gap_A_minus_B"], vp["all_v2_v3_v6"]["ci"], vp["all_v2_v3_v6"]["events"])
                        if "all_v2_v3_v6" in vp else None),
        cue_recovered=(dict(fraction=_r(g2.get("recovered_fraction")), lo=_r((g2.get("recovered_fraction_ci") or [None, None])[0]),
                            hi=_r((g2.get("recovered_fraction_ci") or [None, None])[1]), events=g2.get("events"),
                            gap_A_minus_B=_r(g2.get("gap_A_minus_B")), gap_A_minus_B3=_r(g2.get("gap_A_minus_B3")))
                       if g2 else None),
    )
    return _clean(dict(
        provenance=PROVENANCE,
        headline=headline,
        gap_by_model=_gap_by_model(pooled, data["adversarial"]),
        cue_preserving=cue,
        dose_response=_dose(data["dose"]),
        validity=_validity(data["validity"], pooled),
        design=_design(data["plan"]),
        verdicts=_verdicts(data["v3"], v5, data["v6"]),
        rf_e2e=_rf(data["rf_e2e"]),
        confirmatory=_confirm(data["confirm"]),
        timings=_timings(base),
        sources={k: str(EVAL_DIR / v) for k, v in FILES.items()},
        missing=missing,
    ))


# --------------------------------------------------------------------------- demo items
def _load_items(root: Path) -> dict:
    path = root / ITEMS_REL
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ResearchDemoError(
            f"Demo items not found at {ITEMS_REL}. Build them once with: "
            "python scripts/chimera/build_demo_items.py (needs the local Gutenberg texts in data/raw/pd_gutenberg).",
            404,
        ) from None
    except ValueError:
        raise ResearchDemoError(f"{ITEMS_REL} is not valid JSON. Rebuild it with scripts/chimera/build_demo_items.py.", 500) from None


def items(root: Path | str | None = None) -> dict:
    """The demo items without their prompts (the server keeps those; the page shows windows and candidates)."""
    data = _load_items(Path(root) if root else default_root())
    slim = [{k: v for k, v in it.items() if k != "prompts"} for it in data.get("items", [])]
    return _clean(dict(provenance=PROVENANCE, label_provenance=data.get("label_provenance"), selection=data.get("selection"),
                       arms=[dict(arm=a, label=ARM_LABELS[a]) for a in ARMS],
                       models=list(ALLOWED_MODELS), items=slim))


# --------------------------------------------------------------------------- probe
def normalize_model(model: str) -> str:
    name = _MODEL_ALIASES.get((model or "").strip(), (model or "").strip())
    if name not in ALLOWED_MODELS:
        raise ResearchDemoError(
            f"Model {model!r} is not allowed. The live probe only runs the local models: {', '.join(ALLOWED_MODELS)}.", 400)
    return name


def classify(answer: str, true_letter: str) -> str:
    """`true_identity` = the premature answer (the item is always pre-reveal, so the true identity is not yet knowable);
    `abstain` = UNDETERMINED, the correct first-time-reader answer; `other` = a different candidate; `invalid`."""
    if answer == true_letter:
        return "true_identity"
    if answer == "UNDETERMINED":
        return "abstain"
    if answer and len(answer) == 1 and answer.isalpha():
        return "other"
    return "invalid"


def verdict_line(outcomes: dict[str, str]) -> str:
    phrase = {"true_identity": "answers the true identity before the book reveals it", "abstain": "abstains",
              "other": "other", "invalid": "other"}
    return "; ".join(f"{ARM_LABELS[a].capitalize()}: {phrase[o]}" for a, o in outcomes.items())


def _mem_available_gib() -> float | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for ln in fh:
                if ln.startswith("MemAvailable:"):
                    return int(ln.split()[1]) / 1048576
    except (OSError, ValueError):
        return None
    return None


def _http_json(method: str, url: str, payload: dict | None = None, timeout: float = 240.0) -> dict:
    """The single network call of this module (tests replace it). Raises ResearchDemoError with an actionable message."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed loopback host
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        if exc.code == 404 and "not found" in body.lower():
            raise ResearchDemoError("ollama does not have that model installed. Run `ollama pull <model>`.", 424) from None
        raise ResearchDemoError(f"ollama returned HTTP {exc.code}: {body[:200]}", 502) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise ResearchDemoError(
            f"Ollama is not reachable at {OLLAMA_HOST} ({exc}). Start it with `ollama serve` and retry.", 503) from None


def _unload(model: str) -> None:
    try:
        _http_json("POST", f"{OLLAMA_HOST}/api/generate", {"model": model, "keep_alive": 0, "prompt": ""}, timeout=30.0)
    except ResearchDemoError:
        log.warning("could not unload %s from ollama", model, exc_info=True)


def _ensure_in_gpu(model: str) -> None:
    """The study's rule: never run a model that ollama split into system RAM."""
    ps = _http_json("GET", f"{OLLAMA_HOST}/api/ps", timeout=10.0).get("models", [])
    m = next((x for x in ps if x.get("name") == model or x.get("model") == model), None)
    if m is not None and m.get("size_vram", 0) < m.get("size", 1):
        raise ResearchDemoError(
            f"{model} is not fully in GPU memory (ollama placed part of it in system RAM). Refusing to run it: "
            "CPU offload is not allowed on this machine. Free the GPU or pick a smaller model.", 507)


def probe(item_id: str, model: str, arms: list[str] | tuple[str, ...] | None = None, root: Path | str | None = None) -> dict:
    """Run one local model on one item, one to three arms, and report answer, latency and correctness per arm."""
    name = normalize_model(model)
    want = list(arms) if arms else list(ARMS)
    bad = [a for a in want if a not in ARMS]
    if bad or len(set(want)) != len(want):
        raise ResearchDemoError(f"arms must be a non-repeating subset of {list(ARMS)}; got {want}.", 400)
    data = _load_items(Path(root) if root else default_root())
    item = next((it for it in data.get("items", []) if it.get("id") == item_id), None)
    if item is None:
        raise ResearchDemoError(f"Unknown demo item {item_id!r}. Known: {[it.get('id') for it in data.get('items', [])]}.", 404)
    avail = _mem_available_gib()
    if avail is not None and avail < MIN_AVAILABLE_GIB:
        raise ResearchDemoError(
            f"Only {avail:.1f} GiB of RAM is available; refusing to load a model (need at least {MIN_AVAILABLE_GIB:.0f} GiB).", 503)
    if not _probe_lock.acquire(blocking=False):
        raise ResearchDemoError("Another probe is already running; wait for it to finish.", 409)
    results: dict[str, dict] = {}
    t_start = time.perf_counter()
    try:
        for k, arm in enumerate(want):
            cands = item["candidates"][arm]
            allowed = [c["letter"] for c in cands] + ["UNDETERMINED"]
            schema = {"type": "object", "properties": {"answer": {"type": "string", "enum": allowed}}, "required": ["answer"]}
            payload = dict(model=name, stream=False, options=dict(OLLAMA_OPTIONS), format=schema, keep_alive="2m",
                           messages=[dict(role="user", content=item["prompts"][arm])])
            t0 = time.perf_counter()
            resp = _http_json("POST", f"{OLLAMA_HOST}/api/chat", payload)
            seconds = time.perf_counter() - t0
            try:
                ans = str(json.loads((resp.get("message") or {}).get("content", "")).get("answer", ""))
            except (ValueError, AttributeError):
                ans = ""
            if ans not in allowed:
                ans = "INVALID"
            if k == 0:
                _ensure_in_gpu(name)
            by_letter = {c["letter"]: c["name"] for c in cands}
            results[arm] = dict(
                arm=arm, label=ARM_LABELS[arm], answer=ans, answer_name=by_letter.get(ans),
                seconds=round(seconds, 3), load_seconds=round((resp.get("load_duration") or 0) / 1e9, 3),
                is_true_identity=(ans == item["true_letter"]), outcome=classify(ans, item["true_letter"]))
        total = time.perf_counter() - t_start
    finally:
        _unload(name)  # keep_alive 0 after the last arm, also when an arm failed
        _probe_lock.release()
    return _clean(dict(
        item_id=item_id, model=name, true_letter=item["true_letter"], true_identity=item.get("true_identity"),
        arms=results, total_seconds=round(total, 3), verdict=verdict_line({a: r["outcome"] for a, r in results.items()}),
        options=dict(OLLAMA_OPTIONS)))
