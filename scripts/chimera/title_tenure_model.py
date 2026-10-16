"""M3b: bitemporal title-holder model on the SIO v1 worlds (implements PREREG_M3b v1). Synthetic labels, CPU only.

Compares volume-first (V, the shipped behaviour), causal-only (C) and bitemporal (B) tenure handling on title
mentions under the reader view and the omniscient view. Tenure representation follows TAC-KBP's [T1 T2 T3 T4] idea
(start lower/upper, end lower/upper); nothing here is claimed as a new tenure model. Imports the SIO generator and the
shipped resolver unchanged.

    python scripts/chimera/title_tenure_model.py --out data/eval/chimera/m3b_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sio_synthetic_oracle as S  # noqa: E402

DECL = re.compile(r"Clan head (?P<name>[A-Z]\w+(?: [A-Z]\w+)?) rose from the dais")


def declarations(w: S.World) -> list[tuple[int, int, str]]:
    out = []
    for n, text in sorted(w.chapters.items()):
        for m in DECL.finditer(text):
            out.append((n, m.start(), m.group("name")))
    return out


def first_decl(decls) -> dict[str, tuple[int, int]]:
    fd: dict[str, tuple[int, int]] = {}
    for n, off, name in decls:
        fd.setdefault(name, (n, off))
    return fd


def q(est: float, truth: float) -> float:
    return 1 / (1 + abs(est - truth))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    acc: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    q_story: dict[str, list[float]] = defaultdict(list)
    q_reader: dict[str, list[float]] = defaultdict(list)
    agree_s0_v = [0, 0]

    for seed in range(S.N_WORLDS):
        w = S.make_world(seed)
        base = S.run(w, S.N_CHAPTERS)
        decls = declarations(w)
        fd = first_decl(decls)
        h1, h2 = w.names[w.title["h1"]], w.names[w.title["h2"]]
        second_pos = fd[h2]

        def story_holder(pos: tuple[int, int]) -> str:
            return h2 if pos >= second_pos else h1

        def causal_holder(pos: tuple[int, int]) -> str | None:
            latest = None
            for n, off, name in decls:
                if (n, off) <= pos:
                    latest = name
            return latest

        for m in w.mentions:
            if m.kind not in ("title_pre", "title_post"):
                continue
            pos = (m.chapter, m.offset)
            pre = m.kind == "title_pre"
            sh = story_holder(pos)
            views = {
                "V": (sh, sh),  # (reader view, omniscient view)
                "C": (causal_holder(pos), causal_holder(pos)),
                "B": (sh if fd[sh] <= pos else None, sh),
                "S0_shipped": (base[m.id], base[m.id]),
            }
            for sys_, (rv, ov) in views.items():
                a = acc[sys_]
                a["n"] += 1
                a["n_pre"] += pre
                a["reader_correct"] += rv == m.reader
                a["omni_correct"] += ov == m.omni
                if pre:
                    a["premature"] += rv == m.omni
            if base[m.id] is not None:
                agree_s0_v[1] += 1
                agree_s0_v[0] += base[m.id] == views["V"][1]
        decl_h1 = [(n, o) for n, o, name in decls if name == h1]
        last_decl_h1 = decl_h1[-1][0]
        story_est = (1, last_decl_h1)            # V and B story time: start extended to 1, end at last declaration
        reader_est = (fd[h1][0], last_decl_h1)   # C and B reader time: start at first declaration
        story_truth, reader_truth_iv = (1, 4), (fd[h1][0], 4)
        for s_ in ("V", "B"):
            q_story[s_].append((q(story_est[0], story_truth[0]) + q(story_est[1], story_truth[1])) / 2)
        for s_ in ("C", "B"):
            q_reader[s_].append((q(reader_est[0], reader_truth_iv[0]) + q(reader_est[1], reader_truth_iv[1])) / 2)

    def r(k, n):
        return dict(k=k, n=n, rate=(k / n if n else None), wilson95=S.wilson(k, n))

    out = {}
    for sys_, a in acc.items():
        out[sys_] = dict(n_title_mentions=a["n"], n_title_pre=a["n_pre"],
                         reader_accuracy=r(a["reader_correct"], a["n"]),
                         omniscient_accuracy=r(a["omni_correct"], a["n"]),
                         premature=r(a["premature"], a["n_pre"]))
    res = dict(
        preregistration="PREREG_M3b_title_tenure.md v1",
        label_provenance="SYNTHETIC (by construction from the world spec); no model, no human, no novel text",
        worlds=S.N_WORLDS, systems=out,
        shipped_resolver_agrees_with_V_on_links_it_makes=r(*agree_s0_v),
        tenure_score_Q_story_time={k: sum(v) / len(v) for k, v in q_story.items()},
        tenure_score_Q_reader_time={k: sum(v) / len(v) for k, v in q_reader.items()},
        note="V is volume-first (shipped behaviour); C causal-only; B bitemporal. Designed outcomes hold by construction.",
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
