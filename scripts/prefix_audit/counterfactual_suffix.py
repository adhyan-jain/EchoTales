"""Counterfactual-suffix test of the persona stage (docs/research/PREFIX_FAITHFULNESS/PREREG_COUNTERFACTUAL.md, H14.1-H14.4).

    python scripts/prefix_audit/counterfactual_suffix.py

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Deterministic persona path, stub LLM mode, CPU only.

Truncate-and-rebuild compares the full build with one other volume (the prefix), so a value that depends on later chapters but
happens to equal the prefix value is scored clean. Here chapters <= k stay byte-identical, the pronouns of every later span are
swapped, and the whole volume is rebuilt: a change of the value served at k + 0.5 is dependence on the suffix. Only ids, chapter
numbers and closed-vocabulary values are written, no novel text.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A  # noqa: E402
import common as C  # noqa: E402
from echotales.pipeline.persona import build as persona_build  # noqa: E402

SERIALS = ("lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity")
SWAP = {"he": "she", "she": "he", "him": "her", "his": "her", "her": "him", "hers": "his", "himself": "herself", "herself": "himself"}
_PRON = re.compile(r"\b(" + "|".join(SWAP) + r")\b", re.IGNORECASE)
PREREG = Path(__file__).resolve().parents[2] / "docs/research/PREFIX_FAITHFULNESS/PREREG_COUNTERFACTUAL.md"


def swap(text: str) -> str:
    def one(m: re.Match) -> str:
        w = m.group(0)
        out = SWAP[w.lower()]
        return out.capitalize() if w[0].isupper() else out

    return _PRON.sub(one, text)


def flipped_build(nid: str, src: Path, k: int, repair: bool):
    db = C.fresh_copy(src, f"{nid}_cf_k{k}_{'on' if repair else 'off'}")
    con = sqlite3.connect(db)
    rows = con.execute("SELECT id, text FROM span WHERE novel_id=? AND chapter > ?", (nid, k)).fetchall()
    con.executemany("UPDATE span SET text=? WHERE id=?", [(swap(t), i) for i, t in rows])
    con.commit()
    con.close()
    A.prepare(db, nid, None)  # drops persona and attribute rows only; resolution held fixed
    store = C.Store(db)
    persona_build.build_personas(nid, store, **({"prefix_causal": True} if repair else {}))
    store.conn.commit()
    return store, len(rows)


def compare(full_state: dict, cf_state: dict) -> list[tuple[str, str, str, str]]:
    out = []
    for e in sorted(set(full_state) & set(cf_state)):
        for pid in sorted(set(full_state[e]["attrs"]) & set(cf_state[e]["attrs"])):
            for key in A.TRAITS:
                a, b = full_state[e]["attrs"][pid].get(key), cf_state[e]["attrs"][pid].get(key)
                if a is not None or b is not None:
                    out.append((e, key, str(a), str(b)))
    return out


def main() -> None:
    result: dict = dict(audit="counterfactual-suffix", label_provenance="SYSTEM-INTERNAL, no labels",
                        prereg_sha256=hashlib.sha256(PREREG.read_bytes()).hexdigest(), serials={})
    pooled = {False: Counter(), True: Counter()}
    for nid in SERIALS:
        src = C.snapshot_source(nid)
        trunc = {}
        for repair in (False, True):
            d = json.loads((C.RESULTS / f"audit_repair-{'on' if repair else 'off'}_{nid}.json").read_text())
            for r in d["rows"]:
                t = trunc.setdefault((repair, r["entity"], r["key"], r["k"]), dict(diverge=False, exposed=r["exposed"], prefix=r["prefix_value"], full=r["full_value"]))
                t["diverge"] |= r["diverge"]
        per = {}
        for repair in (False, True):
            full, _ = A.build(nid, src, f"cf_full_{'on' if repair else 'off'}", None, repair)
            rows = []
            for k in C.CUTS[nid]:
                cf, n_spans = flipped_build(nid, src, k, repair)
                for e, key, a, b in compare(A.read_state(full, nid, k), A.read_state(cf, nid, k)):
                    t = trunc.get((repair, e, key, k), {})
                    rows.append(dict(entity=e, key=key, k=k, flips=a != b, full_value=a, cf_value=b, trunc_diverge=t.get("diverge"),
                                     exposed=t.get("exposed"), prefix_value=t.get("prefix")))
                cf.close()
                print(nid, "repair" if repair else "status-quo", "k", k, "suffix spans swapped", n_spans,
                      "gender flips", sum(r["flips"] for r in rows if r["k"] == k and r["key"] == "gender"), flush=True)
            full.close()
            g = [r for r in rows if r["key"] == "gender"]
            c = Counter(
                compared=len(g), flips=sum(r["flips"] for r in g),
                trunc_diverge=sum(bool(r["trunc_diverge"]) for r in g),
                diverge_and_flip=sum(bool(r["trunc_diverge"]) and r["flips"] for r in g),
                flip_no_diverge=sum(r["flips"] and r["trunc_diverge"] is False for r in g),
                flip_no_diverge_prefix_final=sum(r["flips"] and r["trunc_diverge"] is False and r["prefix_value"] not in (None, "None", "unknown") for r in g),
                flip_no_diverge_prefix_unknown=sum(r["flips"] and r["trunc_diverge"] is False and r["prefix_value"] == "unknown" for r in g),
                flip_outside_window=sum(r["flips"] and r["exposed"] is False for r in g),
                flip_unmatched=sum(r["flips"] and r["trunc_diverge"] is None for r in g),
            )
            other = {key: sum(r["flips"] for r in rows if r["key"] == key) for key in A.TRAITS if key != "gender"}
            per["repair" if repair else "status_quo"] = dict(gender=dict(c), other_traits_flips=other, rows=rows)
            pooled[repair] += c
        result["serials"][nid] = per
    sq, rp = pooled[False], pooled[True]
    result["pooled"] = dict(status_quo=dict(sq), repair=dict(rp))
    result["hypotheses"] = dict(
        H14_1=dict(diverging=sq["trunc_diverge"], of_which_flip=sq["diverge_and_flip"],
                   share=sq["diverge_and_flip"] / sq["trunc_diverge"] if sq["trunc_diverge"] else None,
                   supported=bool(sq["trunc_diverge"] and sq["diverge_and_flip"] / sq["trunc_diverge"] >= 0.70)),
        H14_2=dict(flip_without_divergence=sq["flip_no_diverge"], prefix_final=sq["flip_no_diverge_prefix_final"],
                   prefix_unknown=sq["flip_no_diverge_prefix_unknown"], supported=sq["flip_no_diverge"] >= 1),
        H14_3=dict(flips_outside_window=sq["flip_outside_window"], supported=sq["flip_outside_window"] == 0),
        H14_4=dict(repaired_flips=rp["flips"], supported=rp["flips"] == 0))
    out = C.RESULTS / "counterfactual_suffix.json"
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result["pooled"]), "\n", json.dumps(result["hypotheses"], indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
