"""M2 (Haiku subagent replication of arms A and B): prompt preparation and result collection (PREREG_M2 v1).

LABEL PROVENANCE: silver only. No API key, no paid call. Prompt files hold NOVEL TEXT and are written ONLY to --workdir
(the session scratchpad), never to the repository; the repository receives letters, hashes and counts only.

  --prepare   write A_<id>.txt / B_<id>.txt for the 62 items with a silver truth letter, plus spawn_list.json
  --collect   read answers (out_<arm>_<id>_<attempt>.txt) and tool counts (toolcounts.tsv: arm id attempt tool_uses),
              validate (valid spawn = exactly 2 tool calls), and run the pre-registered analysis

    python scripts/chimera/m2_haiku_prepare.py --db <scratch RI copy> --workdir <scratchpad>/m2 --prepare
    python scripts/chimera/m2_haiku_prepare.py --db <scratch RI copy> --workdir <scratchpad>/m2 --collect --out data/eval/chimera/m2_results.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import l1_llm_leakage as L1  # noqa: E402

from echotales.core.store import Store  # noqa: E402

WRAPPER = (
    "Read the file {path}. It contains a reading-comprehension question; answer it exactly as the file instructs. "
    "Then use the Write tool to write ONLY your answer token (one letter, or the word UNDETERMINED) to the file "
    "{outpath}, and reply done. Use no other tool, read no other file, and do not search for anything."
)


def tpl_v1() -> dict:
    man = json.loads(Path(L1.MANIFEST).read_text())
    raw = Path(L1.PROMPTS).read_bytes()
    if hashlib.sha256(raw).hexdigest() != man["prompts_file_sha256"]:
        sys.exit("REFUSING: L1_prompts_v1.json hash mismatch")
    return json.loads(raw)


def m2_items(store: Store) -> list[dict]:
    return [i for i in L1.load_items(store) if i["truth_letter"]]


def prepare(args, store: Store) -> None:
    tpl = tpl_v1()
    items = m2_items(store)
    need = {it["chapter"] - k for it in items for k in range(0, 4)}
    chapters = {c.number: c.story_text for c in store.iter_chapters(L1.NOVEL) if c.number in need}
    pi = L1.build_pi(args.db)[0]
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    spawns, hashes = [], {}
    for it in items:
        win, _ = L1.build_window(chapters, it)
        for arm in ("A", "B"):
            if arm == "A":
                p = L1.fill(tpl["A_B_prefix"], WINDOW=win, SURFACE=it["surface"],
                            CANDIDATES=L1.cand_block(it["cands"]))
            else:
                p = L1.fill(tpl["A_B_prefix"], WINDOW=pi.rename(win), SURFACE=pi.rename(it["surface"]),
                            CANDIDATES=L1.cand_block(it["cands"], pi.rename))
            path = work / f"{arm}_{it['id']}.txt"
            path.write_text(p, encoding="utf-8")
            hashes[f"{arm}_{it['id']}"] = hashlib.sha256(p.encode()).hexdigest()[:16]
            spawns.append(dict(arm=arm, id=it["id"], path=str(path),
                               outpath=str(work / f"out_{arm}_{it['id']}_1.txt"),
                               description=f"M2 {arm} {it['id']}"))
    (work / "spawn_list.json").write_text(json.dumps(spawns, indent=1))
    Path("data/eval/chimera/m2_prompt_hashes.json").write_text(json.dumps(
        dict(wrapper_sha256=hashlib.sha256(WRAPPER.encode()).hexdigest(), n_prompts=len(hashes), hashes=hashes), indent=1))
    print(f"wrote {len(spawns)} prompt files to {work}; hashes (no text) to data/eval/chimera/m2_prompt_hashes.json")


def collect(args, store: Store) -> None:
    work = Path(args.workdir)
    items = m2_items(store)
    tool: dict[tuple[str, str, int], int] = {}
    for r in csv.reader(open(work / "toolcounts.tsv"), delimiter="\t"):
        if r and not r[0].startswith("#"):
            tool[(r[0], r[1], int(r[2]))] = int(r[3])
    ans: dict[tuple[str, str], str] = {}
    status: dict[str, int] = defaultdict(int)
    for it in items:
        letters = {L for L, _n, _i in it["cands"]}
        for arm in ("A", "B"):
            chosen = "INVALID"
            for attempt in (1, 2):
                f = work / f"out_{arm}_{it['id']}_{attempt}.txt"
                if (arm, it["id"], attempt) not in tool:
                    continue
                if tool[(arm, it["id"], attempt)] != 2 or not f.exists():
                    status["invalid_tool_count_or_missing"] += 1
                    continue
                t = f.read_text().strip().strip(".")
                if t in letters or t == "UNDETERMINED":
                    chosen = t
                    break
                status["unparsable"] += 1
            ans[(arm, it["id"])] = chosen
            status["final_" + ("invalid" if chosen == "INVALID" else "valid")] += 1
    ctrl = [i for i in items if i["category"] == "plain_control"]
    prim = [i for i in items if i["tier"] == "P" and i["reveal_chapter"] is not None]
    same = sum(ans[("A", i["id"])] == ans[("B", i["id"])] for i in ctrl)
    valid_r1 = same == len(ctrl)
    a = [int(ans[("A", i["id"])] == i["truth_letter"]) for i in items]
    b = [int(ans[("B", i["id"])] == i["truth_letter"]) for i in items]
    boot = L1.paired_bootstrap(a, b)
    n10 = sum(x == 1 and y == 0 for x, y in zip(a, b))
    n01 = sum(x == 0 and y == 1 for x, y in zip(a, b))
    replicates = bool(valid_r1 and boot["mean_diff"] >= 0.05 and boot["ci95"][0] > 0)
    res = dict(
        preregistration="PREREG_M2_haiku_subagent.md v1",
        label_provenance="SILVER; resolver is a Claude model, the silver labeller was also a Claude model "
                         "(confound NOT resolved)",
        n_items=len(items), spawn_status=dict(status),
        M2_R1_renaming_validity=dict(A_equals_B_on_plain_controls=L1.row(same, len(ctrl)), valid=valid_r1),
        accuracy_vs_silver=dict(A=L1.row(sum(a), len(a)), B=L1.row(sum(b), len(b))),
        M2_R2_A_minus_B=dict(
            **boot, discordant_A_right_B_wrong=n10, discordant_B_right_A_wrong=n01, replicates=replicates,
            reading=("gap replicates on a second model (same family as the silver labeller; confound unresolved)"
                     if replicates else "does not replicate, or not interpretable (see R1)")),
        controls_accuracy=dict(
            A=L1.row(sum(ans[("A", i["id"])] == i["truth_letter"] for i in ctrl), len(ctrl)),
            B=L1.row(sum(ans[("B", i["id"])] == i["truth_letter"] for i in ctrl), len(ctrl))),
        M2_R3_primary_counts=dict(
            n=len(prim), A=sum(ans[("A", i["id"])] == i["truth_letter"] for i in prim),
            B=sum(ans[("B", i["id"])] == i["truth_letter"] for i in prim),
            per_item=[dict(id=i["id"], A=ans[("A", i["id"])] == i["truth_letter"],
                           B=ans[("B", i["id"])] == i["truth_letter"]) for i in prim]),
        abstain_counts=dict(A=sum(ans[("A", i["id"])] == "UNDETERMINED" for i in items),
                            B=sum(ans[("B", i["id"])] == "UNDETERMINED" for i in items)),
        answers_letters_only={f"{arm}_{i}": v for (arm, i), v in ans.items()},
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "answers_letters_only"}, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--workdir", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prepare", action="store_true")
    g.add_argument("--collect", action="store_true")
    ap.add_argument("--out", default="data/eval/chimera/m2_results.json")
    args = ap.parse_args()
    store = Store(args.db)
    (prepare if args.prepare else collect)(args, store)


if __name__ == "__main__":
    main()
