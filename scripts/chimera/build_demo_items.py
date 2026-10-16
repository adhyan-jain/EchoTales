"""Build the six demo probe items for the webview Research page (data/scratch/demo/probe_items.json).

Each item is ONE pre-reveal mention from ONE event of the public-domain PD benchmark, rendered under the three arms of
the study so a local model can be asked the same question three ways:

  A   original names                     (the model may recognise the book)
  B   consistent letter cipher           (renamers_for, seed 20261015, every proper noun)
  B3  cue-preserving natural pseudonyms  (pd_v5 build_maps / make_b3: cast and alias names only)

Prompts are the frozen study prompts (PD_prompts_v1 A_B_prefix + the PD_prompts_v2 JSON tail), built by the study's own
item builders so the item ids, windows, candidate letters and letter order are IDENTICAL to the stored v2/v3 runs.

SELECTION IS ILLUSTRATIVE, NOT A SAMPLE. Per event the script picks the pre-reveal item where the stored local runs show
the effect most clearly (most models name the true identity under original names, fewest under the cipher), among items
whose window does not already contain a token of the true identity's name. Six events, six different books. The headline
numbers on the Research page come from ALL items, never from these six; the output records the stored per-item counts so
the page can show how typical each demo item is.

Texts are read from the git-ignored local Gutenberg copy (data/raw/pd_gutenberg/pg<ID>.txt); the output lives in the
git-ignored data/scratch/. Nothing here calls a model or the network.

    source .venv/bin/activate
    python scripts/chimera/build_demo_items.py            # writes data/scratch/demo/probe_items.json
    python scripts/chimera/build_demo_items.py --texts data/raw/pd_gutenberg --out data/scratch/demo/probe_items.json
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))  # the study modules are flat scripts, not a package

# The study modules resolve docs/research/... and data/eval/... relative to the repo root.
LAUNCH_CWD = Path.cwd()
os.chdir(REPO)

import l1_llm_leakage as L1  # noqa: E402
import pd_reveal_benchmark as PD  # noqa: E402
import pd_v2 as V2  # noqa: E402
import pd_v3 as V3  # noqa: E402
import pd_v5_cuepres as V5C  # noqa: E402

P = Path("docs/research/preregistrations")
DEFAULT_TEXTS = Path("data/raw/pd_gutenberg")
DEFAULT_OUT = Path("data/scratch/demo/probe_items.json")
#: Event ids in demo order. Six events from six different books; GG is The Great Gatsby (owner asked for it).
DEMO_EVENTS = ["GG", "PH", "IM", "PG", "RP", "JH"]
LOCAL_MODELS = ["gemma2:9b", "llama3.1:8b", "mistral:7b-instruct", "phi4-mini:latest", "qwen2.5:7b"]
#: A fixed, hand-checked display name for the study's alias surface is not needed: the surface is the text's own words.
REVEAL_NOTE = (
    "Fixed reveal: the book states this identity explicitly about {pct}% of the way through the text, after the shown "
    "passage. A first-time reader at this point is not yet entitled to know it. Revealing sentence: \"{sentence}\""
)


def book_title(text_path: Path) -> str:
    head = text_path.read_text(encoding="utf-8", errors="replace")[:4000]
    m = re.search(r"^Title:\s*(.+?)\s*$", head, re.M)
    if m:
        return re.sub(r"\s+", " ", m.group(1))
    # Some Gutenberg files carry no metadata block (pg1237): the first non-empty line after the START marker is the title.
    body = head.split("***", 2)[-1].split("\n", 1)[-1] if "*** START" in head else head
    first = next((ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("***")), text_path.stem)
    return first.title()


@functools.lru_cache(maxsize=None)
def _run(ver: str, model: str) -> dict | None:
    f = Path(f"data/eval/chimera/{ver}/run_{model.replace(':', '_').replace('/', '_')}.json")
    return json.loads(f.read_text()) if f.exists() else None


def stored_counts(ver: str, item_id: str, b3_runs: dict) -> dict:
    """How many of the five local models named the true identity on this item in the stored runs (A, B mean of B/B2, B3)."""
    a = b = b3 = n = 0
    for m in LOCAL_MODELS:
        r = _run(ver, m)
        if r is None or item_id not in r["real"]:
            continue
        ident = r["truth"][item_id]["identity_letter"]
        row = r["real"][item_id]
        n += 1
        a += row["A"] == ident
        b += row["B"] == ident
        b3 += b3_runs.get(m, {}).get(item_id) == ident
    return dict(models=n, A=a, B=b, B3=b3)


def load_b3_runs() -> dict:
    out = {}
    for m in LOCAL_MODELS:
        f = Path(f"data/eval/chimera/pd_v5/run_{m.replace(':', '_').replace('/', '_')}.json")
        if f.exists():
            out[m] = json.loads(f.read_text())["B3"]
    return out


def build(texts: Path) -> dict:
    tpl_base = json.loads((P / "PD_prompts_v1.json").read_text())
    tpl_tail = json.loads((P / "PD_prompts_v2.json").read_text())
    b3_runs = load_b3_runs()
    out_items, used_books = [], set()
    for ver, mod in (("pd_v2", V2), ("pd_v3", V3)):
        evs, items, books = V5C.datasets(texts, mod)
        wanted = [e for e in DEMO_EVENTS if e in evs]
        if not wanted:
            continue
        maps, _audit = V5C.build_maps(list(evs.values()), books)
        renamers = mod.renamers_for(books)
        for ev_id in wanted:
            ev = evs[ev_id]
            gid = ev["gutenberg"]
            text = books[gid]
            loc = PD.locate(ev, text)
            ident_tokens = [t for t in PD.TOKEN.findall(ev["identity"]) if t[:1].isupper() and len(t) >= 3
                            and t.lower() not in PD.HONORIFICS and t not in {"Abel"}]
            ranked = []
            for i, it in enumerate(items):
                if it["event"] != ev_id or it["kind"] != "pre":
                    continue
                win = PD.window_for(text, it)
                if any(re.search(r"\b" + re.escape(t) + r"\b", win) for t in ident_tokens):
                    continue  # the window itself names the identity: not a memory probe
                sc = stored_counts(ver, it["id"], b3_runs)
                ranked.append((-(sc["A"] - sc["B"]), -sc["A"], it["distance"], i, it, win, sc))
            if not ranked:
                print(f"skip {ev_id}: no pre-reveal window free of the identity name")
                continue
            ranked.sort(key=lambda r: r[:4])
            _s1, _s2, _d, i, it, win, sc = ranked[0]
            cl = PD.cand_letters(ev, i)
            letter_of = {n: L for L, n, _ in cl}
            r1, _r2 = renamers[gid]
            b3 = V5C.make_b3(r1, maps[gid])
            surface = it["surface"]
            arms = {
                "A": (lambda s: s, "original names"),
                "B": (r1.rename, "consistent letter cipher"),
                "B3": (b3, "cue-preserving pseudonyms"),
            }
            windows, prompts, cands = {}, {}, {}
            for arm, (fn, _label) in arms.items():
                windows[arm] = fn(win)
                p = L1.fill(tpl_base["A_B_prefix"], WINDOW=windows[arm], SURFACE=fn(surface),
                            CANDIDATES=L1.cand_block(cl, None if arm == "A" else fn))
                prompts[arm] = mod.tail_swap(p, tpl_tail)
                cands[arm] = [dict(letter=L, name=fn(n)) for L, n, _i in cl]
            pct = round(100 * loc["reveal_start"] / len(text))
            out_items.append(dict(
                id=it["id"], event=ev_id, dataset=ver, gutenberg=gid, book=book_title(texts / f"pg{gid}.txt"),
                surface=dict(A=surface, B=r1.rename(surface), B3=b3(surface)),
                window=windows["A"], windows=windows, prompts=prompts, candidates=cands,
                true_letter=letter_of[ev["identity"]], true_identity=ev["identity"],
                reveal_note=REVEAL_NOTE.format(pct=pct, sentence=re.sub(r"\s+", " ", ev["reveal_sentence"]).strip()),
                distance_chars_to_cutoff=it["distance"],
                stored_runs=dict(sc, note="local models (of 5) naming the true identity on this item in the stored runs; "
                                          "B3 only where the cue-preserving run exists"),
            ))
            used_books.add(gid)
    order = {e: k for k, e in enumerate(DEMO_EVENTS)}
    out_items.sort(key=lambda d: order[d["event"]])
    return dict(
        label_provenance="Exploratory results; human labelling pending. Labels are text-derived (explicit revealing sentence + "
                         "regex-located cutoff); event selection by the model-drafter; owner spot-check pending.",
        selection="ILLUSTRATIVE: per event, the pre-reveal item where the stored local runs show the effect most clearly "
                  "(window free of the identity's name tokens). Not a sample; headline numbers use all items.",
        arms=dict(A="original names", B="consistent letter cipher", B3="cue-preserving pseudonyms"),
        seed_cipher=20261015, seed_letters=PD.SEED_ITEM,
        items=out_items,
        books=len(used_books),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--texts", default=str(DEFAULT_TEXTS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    texts = (LAUNCH_CWD / a.texts)
    if not texts.is_dir():
        sys.exit(f"Gutenberg texts not found at {texts}; fetch them with data/raw/pd_gutenberg/fetch.sh first")
    res = build(texts)
    if len(res["items"]) < 6 or res["books"] < 3:
        sys.exit(f"only {len(res['items'])} items from {res['books']} books; need 6 items from at least 3 books")
    out = LAUNCH_CWD / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    for it in res["items"]:
        print(f"{it['id']:10s} {it['book'][:34]:34s} surface={it['surface']['A']!r:24} true={it['true_letter']} "
              f"stored A/B/B3 {it['stored_runs']['A']}/{it['stored_runs']['B']}/{it['stored_runs']['B3']} of {it['stored_runs']['models']}")
    print("wrote", out)


if __name__ == "__main__":
    main()
