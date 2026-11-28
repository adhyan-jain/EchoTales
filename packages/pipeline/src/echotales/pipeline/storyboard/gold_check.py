"""Score a storyboard against a gold scene file with named checks, no model involved.

Why a separate checker beside `scorecard.score`: the scorecard counts how much of a manhua's vocabulary the board uses;
this answers the owner's named failures on RI ch1 one by one (v1 opened on the hero, drew Fang Yuan's face on the
withheld "pair of eyes", never showed Bai Ning Bing, put the prior-loop death on the wrong layer). The gold files are
prose plus block ranges, so the machine-readable parts (withheld block, inset person, poem and screen blocks, expected
sub-layers) live in a sibling `<gold stem>.checks.json` data file. Nothing here knows a novel: every name, block and
layer comes from those two files.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from echotales.pipeline.storyboard.schema import (
    CastMember,
    LetterKind,
    Panel,
    Purpose,
    Shot,
    Storyboard,
)
from echotales.pipeline.storyboard.validators import (
    BALLOON_KINDS,
    COLD_OPEN_SHOTS,
    EVIDENCE_PREFIXES,
    FORESHADOW_BEATS,
)

Row = tuple[str, bool, str]


def _tokens(name: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("-", " ")).split())


def gold_names(entries: list[str]) -> tuple[list[str], bool]:
    """Named people in a gold list, and whether it also asks for an anonymous crowd.

    "Bai Ning Bing (rival Bai clan talent)" -> "Bai Ning Bing"; "the clan elders (over 10)" is a crowd; a possessive
    description ("Klein's father") names nobody the board can be matched on and is skipped.
    """
    names: list[str] = []
    crowd = False
    for raw in entries:
        head = re.split(r"\s*[(,;]", raw, maxsplit=1)[0].strip()
        words = head.split()
        if not words or "'s" in head:
            continue
        if words[0][0].islower():
            crowd = crowd or head.lower().startswith(("the ", "a ", "an ", "some "))
            continue
        lead = []
        for w in words:
            if not w[0].isupper():
                break
            lead.append(w)
        if lead:
            names.append(" ".join(lead))
    return names, crowd


def _is(m: CastMember, name: str, aliases: dict[str, list[str]]) -> bool:
    want = [_tokens(name), *(_tokens(a) for a in aliases.get(name, []))]
    have = _tokens(m.name)
    return bool(have) and any(w and (w <= have or have <= w) for w in want)


def _named(p: Panel, name: str, aliases: dict[str, list[str]]) -> bool:
    return any(_is(m, name, aliases) for m in p.cast)


def _seg_for(sb: Storyboard, block: int):  # type: ignore[no-untyped-def]
    return next((s for s in sb.segments if s.block_from <= block <= s.block_to), None)


def _panels_in(sb: Storyboard, lo: int, hi: int) -> list[Panel]:
    return [p for p in sb.panels if p.source_blocks and lo <= min(p.source_blocks) <= hi]


def check_gold(sb: Storyboard, gold: dict, checks: dict | None = None) -> list[Row]:
    checks = checks or {}
    aliases = checks.get("aliases", {})
    rows: list[Row] = []
    scenes = gold["scenes"]
    rows.append(("scene count", len(sb.segments) == len(scenes), f"{len(sb.segments)} segments, gold {len(scenes)}"))
    for sc in scenes:
        n, b0 = sc["scene"], sc["block_from"]
        seg = next((s for s in sb.segments if abs(s.block_from - b0) <= 1), None)
        if n > 1:
            rows.append((f"scene {n} cut at b{b0}", seg is not None, f"segment starts {[s.block_from for s in sb.segments]}"))
        if seg is None:
            continue
        rows.append((f"scene {n} layer {sc['layer']}", seg.layer.value == sc["layer"], f"segment layer {seg.layer.value}"))
        in_seg = [p for p in sb.panels if p.segment_id == seg.segment_id]
        present, crowd = gold_names(sc.get("present", []))
        for name in present:
            ok = any(_named(p, name, aliases) for p in in_seg)
            rows.append((f"scene {n} present: {name}", ok, "drawn" if ok else "never in a panel's cast"))
        if crowd:
            ok = any(m.invented or m.entity_id.startswith("crowd:") for p in in_seg for m in p.cast)
            rows.append((f"scene {n} present: crowd", ok, "individualised" if ok else "no crowd face"))
        for name in gold_names(sc.get("referenced_only", []))[0]:
            wrong = [p.panel_id for p in in_seg if p.purpose is not Purpose.REFERENCED_INSET and _named(p, name, aliases)]
            rows.append((f"scene {n} not in the room: {name}", not wrong, f"in room in {wrong[:3]}" if wrong else "kept out"))
        if n in checks.get("match_cut_scenes", []):
            first = in_seg[0] if in_seg else None
            ok = bool(first and first.purpose is Purpose.TRANSITION and first.cut_signal == "match")
            rows.append((f"scene {n} match cut", ok, first.purpose.value if first else "no panel"))
    if checks.get("cold_open", True):
        first = sb.panels[0] if sb.panels else None
        ok = bool(first and first.purpose is Purpose.COLD_OPEN and (
            any(lt.kind is LetterKind.SFX for lt in first.letters) or first.shape.value == "text_only" or first.shot in COLD_OPEN_SHOTS))
        rows.append(("cold open is not the hero", ok, f"{first.purpose.value}/{first.shot.value}, cast {[m.name for m in first.cast]}" if first else "no panels"))
    for w in checks.get("withheld", []):
        b, rev = w["block"], w["reveal_block"]
        hold = [p for p in sb.panels if p.withheld and b in p.source_blocks]
        ok = bool(hold) and all(not [m for m in p.cast if not m.invented] and p.shot is Shot.EXTREME_CLOSE for p in hold)
        rows.append((f"b{b} identity withheld (extreme close, no person)", ok, f"{len(hold)} withheld panel(s)"))
        reveal = [p for p in sb.panels if p.cast and p.source_blocks and min(p.source_blocks) >= rev and not p.withheld]
        seg = _seg_for(sb, rev)
        reveal = [p for p in reveal if seg and p.segment_id == seg.segment_id]
        rows.append((f"b{rev} reveal shows the person", bool(reveal), reveal[0].panel_id if reveal else "no cast panel at or after the reveal"))
    for ins in checks.get("insets", []):
        found = [p for p in sb.panels if p.purpose is Purpose.REFERENCED_INSET and _named(p, ins["name"], aliases)]
        rows.append((f"inset: {ins['name']}", bool(found), f"{len(found)} inset panel(s)"))
        if found:
            rows.append((f"inset {ins['name']} silent", not any(lt.kind in BALLOON_KINDS for p in found for lt in p.letters), "no balloon"))
            src = {m.look_source for p in found for m in p.cast if _is(m, ins["name"], aliases)}
            rows.append((f"inset {ins['name']} look from {ins.get('look_source', 'dossier')}", src == {ins.get("look_source", "dossier")}, f"look_source {sorted(src)}"))
    for pm in checks.get("letter_ranges", []):
        lo, hi = pm["blocks"]
        kinds = {LetterKind(k) for k in pm["kinds"]}
        got = {lt.kind for p in _panels_in(sb, lo, hi) for lt in p.letters}
        rows.append((f"b{lo}-{hi} lettered as {'/'.join(sorted(k.value for k in kinds))}", bool(got & kinds), f"found {sorted(k.value for k in got)}"))
    for sl in checks.get("sub_layers", []):
        lo, hi = sl["blocks"]
        got = {p.layer.value for p in _panels_in(sb, lo, hi)}
        rows.append((f"b{lo}-{hi} sub-layer {sl['layer']}", sl["layer"] in got, f"layers {sorted(got)}"))
    if checks.get("foreshadow"):
        ok = any(p.beat in FORESHADOW_BEATS and p.source_blocks for p in sb.panels)
        rows.append(("foreshadow beat anchored in the text", ok, "present" if ok else "none"))
    bad = [p.panel_id for p in sb.panels if p.invented and not p.invented_reason.lower().startswith(EVIDENCE_PREFIXES)]
    rows.append(("every invented panel cites text/dossier/brief", not bad, f"{len(bad)} uncited" if bad else "all cited"))
    return rows


def format_rows(rows: list[Row]) -> str:
    out = ["| Check | Result | Detail |", "|---|---|---|"]
    out += [f"| {item} | {'pass' if ok else 'FAIL'} | {detail} |" for item, ok, detail in rows]
    out.append(f"\n{sum(ok for _i, ok, _d in rows)} of {len(rows)} checks pass")
    return "\n".join(out)


def load_gold(gold_path: str | Path) -> tuple[dict, dict]:
    p = Path(gold_path)
    sibling = p.with_name(p.stem + ".checks.json")
    return json.loads(p.read_text(encoding="utf-8")), (json.loads(sibling.read_text(encoding="utf-8")) if sibling.exists() else {})


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m echotales.pipeline.storyboard.gold_check <gold.json> <storyboard.json>")
        return 2
    gold, checks = load_gold(args[0])
    sb = Storyboard.model_validate_json(Path(args[1]).read_text(encoding="utf-8"))
    print(format_rows(check_gold(sb, gold, checks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
