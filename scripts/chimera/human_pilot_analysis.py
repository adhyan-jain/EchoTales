"""Analysis of the 72-item pilot sheet once the HUMAN (single annotator) labels are in. Zero spend, no model call.

Refuses to run unless `validate_pilot_sheet.validate` reports no errors (blank/model-named annotator, provenance not
HUMAN, edited item columns, ...). It never fills, edits or adjudicates a label. There is ONE annotator, so no
agreement statistic between annotators is computed or claimed; "model-vs-human agreement" below compares the
model-drafted silver omniscient label with the human one.

Needs data/eval/chimera/silver_pilot_results.json (it carries each item's system target id; regenerate it with
silver_pilot_analysis.py on a scratch copy of the RI database first).

    python scripts/chimera/human_pilot_analysis.py --sheet <returned sheet.csv> --out data/eval/chimera/human_pilot_results.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_pilot_sheet as V  # noqa: E402

SILVER = "data/eval/chimera/silver_pilot_results.json"
SPECIAL = V.SPECIAL


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - r) / d), min(1.0, (c + r) / d)]


def row(k: int, n: int) -> dict:
    return dict(k=k, n=n, rate=(k / n if n else None), wilson95=wilson(k, n))


def parse_candidates(s: str) -> list[tuple[str, str]]:
    out = []
    for part in s.split(" | "):
        m = re.match(r"([A-Z])\.\s+(.*?)\s+\[([0-9a-f]{4})\]\s*$", part.strip())
        if m:
            out.append((m.group(2), m.group(3)))
    return out


def resolve(answer: str, cands: list[tuple[str, str]]):
    """-> (kind, name, id4): kind in entity | special | free."""
    a = answer.strip()
    if a in SPECIAL:
        return ("special", a, None)
    if re.fullmatch(r"[A-Z]", a) and ord(a) - 65 < len(cands):
        name, i4 = cands[ord(a) - 65]
        return ("entity", name, i4)
    return ("free", a, None)


def norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "", s.lower().split(" (")[0]).strip()


def loose(a: str, b: str) -> bool:
    ta, tb = set(norm(a).split()), set(norm(b).split())
    return bool(ta and tb and (ta <= tb or tb <= ta))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", default=V.KEY)
    ap.add_argument("--silver", default=SILVER)
    ap.add_argument("--manifest", default=V.MANIFEST)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rows = V.read(args.sheet)
    key = {r["item_id"]: r for r in V.read(args.key)}
    manifest = json.loads(Path(args.manifest).read_text())
    errors, summary = V.validate(rows, set(key), manifest.get("frozen_cols_sha256"))
    if errors:
        print("REFUSING TO ANALYSE: validator errors\n" + "\n".join(errors))
        return 1
    silver = {x["item"]: x for x in json.loads(Path(args.silver).read_text())["per_item"]}

    labelled = [r for r in rows if any(r[c].strip() for c in ("reader_warranted", "omniscient_id"))]
    n_diff = n_diff_linked = n_premature = 0
    ctrl_n = ctrl_ok = 0
    agree_n = agree_k = 0
    per_item = []
    pre_n = pre_diff = 0
    for r in labelled:
        k = key[r["item_id"]]
        cands = parse_candidates(r["candidates"])
        rd = resolve(r["reader_warranted"], cands)
        om = resolve(r["omniscient_id"], cands)
        sys_t = (silver.get(r["item_id"]) or {}).get("system_target_id")
        sys4 = sys_t[-4:] if sys_t else None
        differs = rd[:2] != om[:2]
        if k["tier"] == "P":
            pre_n += 1
            pre_diff += differs
        if differs and k["category"] != "not_entity_control":
            n_diff += 1
            if sys4 is not None:
                n_diff_linked += 1
                n_premature += om[2] is not None and sys4 == om[2]
        if k["tier"] == "C" and k["source"] == "system" and om[0] == "entity":
            ctrl_n += 1
            ctrl_ok += sys4 == om[2] and not differs
        if k["source"] == "gold" and k["gold_identity"] and om[0] == "entity":
            agree_n += 1
            agree_k += loose(k["gold_identity"], om[1])
        per_item.append(dict(item=r["item_id"], tier=k["tier"], category=k["category"], reader_kind=rd[0],
                             omniscient_kind=om[0], views_differ=differs,
                             system_links_final_identity=bool(sys4 and om[2] and sys4 == om[2])))

    res = dict(
        label_provenance="HUMAN (single annotator): reader_warranted / omniscient_id columns of the returned sheet. "
                         "Silver (model-drafted) labels appear only in the model-vs-human agreement row.",
        annotator_note="One annotator: no inter-annotator agreement is computed or claimed.",
        validator=summary,
        pre_reveal_items_labelled=pre_n,
        pre_reveal_items_where_reader_view_differs_from_omniscient=row(pre_diff, pre_n),
        premature_resolution=dict(
            note="among labelled items where the human reader view differs from the omniscient view, share where the "
                 "pipeline's mention-level link equals the human omniscient identity (pipeline = deterministic "
                 "resolver run of record; unlinked counts as not premature)",
            all_differing_items=row(n_premature, n_diff),
            among_differing_items_the_pipeline_links=row(n_premature, n_diff_linked)),
        controls_sanity_plain_names=row(ctrl_ok, ctrl_n),
        model_vs_human_agreement_on_omniscient_identity=dict(
            note="silver (model-drafted gold) vs human omniscient label on gold-sourced items with a candidate answer",
            agreement=row(agree_k, agree_n)),
        per_item=per_item,
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k != "per_item"}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
