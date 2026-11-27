"""The storyboard-measurable rows of the MANHWA_DIRECTING_PATTERNS.md section 4 scorecard.

Rows that need images (art quality, face distinctness) or the composer (palette per layer) are not here. Presence
correctness is measured against a hand list written from the chapter text, never from the director's own output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from echotales.pipeline.storyboard.schema import LetterKind, Purpose, Storyboard

#: What the real RI manhua ch1 reaches (docs/results/MANHWA_DIRECTING_PATTERNS.md section 4). `None`: no reference number.
REFERENCE_RI = {
    "panels": 84, "cold_open": True, "layers_used": 4, "letter_kinds": 8, "sfx": 10, "inserts_and_ecu": 10,
    "crowd_individuals": 5, "referenced_insets": 2, "shapes_used": 5, "cuts_signalled": 3,
}
_GENERIC_HEAD = re.compile(r"^[a-z]")


def _tok(name: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9 ]+", " ", name.lower().replace("-", " ")).split())


def _same(name: str, aliases: list[str]) -> bool:
    t = _tok(name)
    for a in aliases:
        at = _tok(a)
        if at and t and (at <= t or t <= at):
            return True
    return False


def load_hand_list(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def score(sb: Storyboard, *, n_blocks: int, hand: dict | None = None) -> dict:
    ps = sb.panels
    kinds = {lt.kind for p in ps for lt in p.letters}
    out: dict = {
        "panels": len(ps),
        "panels_per_block": round(len(ps) / max(1, n_blocks), 2),
        "cold_open": bool(ps) and ps[0].purpose is Purpose.COLD_OPEN,
        "layers_used": len({p.layer for p in ps}),
        "layers": sorted({p.layer.value for p in ps}),
        "letter_kinds": len(kinds),
        "letter_kind_list": sorted(k.value for k in kinds),
        "sfx": sum(1 for p in ps for lt in p.letters if lt.kind is LetterKind.SFX),
        "inserts_and_ecu": sum(1 for p in ps if p.purpose in (Purpose.INSERT, Purpose.EXTREME_CLOSE)),
        "reactions": sum(1 for p in ps if p.purpose is Purpose.REACTION),
        "crowd_individuals": sum(1 for p in ps if p.purpose is Purpose.CROWD_INDIVIDUAL),
        "referenced_insets": sum(1 for p in ps if p.purpose is Purpose.REFERENCED_INSET),
        "cards": sum(1 for p in ps if p.purpose in (Purpose.TIME_PLACE_CARD, Purpose.TITLE_CARD, Purpose.NAME_CARD)),
        "shapes_used": len({p.shape for p in ps}),
        "shape_list": sorted({p.shape.value for p in ps}),
        "invented_panels": sum(1 for p in ps if p.invented),
        "segments": len(sb.segments),
    }
    signal = {Purpose.TIME_PLACE_CARD, Purpose.TRANSITION, Purpose.ESTABLISHING}
    cuts_ok = 0
    for seg in sb.segments[1:]:
        first = next((p for p in ps if p.segment_id == seg.segment_id), None)
        cuts_ok += bool(first and first.purpose in signal)
    out["segment_cuts"] = max(0, len(sb.segments) - 1)
    out["segment_cuts_signalled"] = cuts_ok
    if hand:
        out.update(_vs_hand(sb, hand, cuts_ok))
    return out


def _vs_hand(sb: Storyboard, hand: dict, cuts_signalled: int) -> dict:
    starts = [s.block_from for s in sb.segments[1:]]
    found = [c for c in hand.get("cuts", []) if any(abs(c - s) <= 1 for s in starts)]
    signalled = 0
    for c in found:
        seg = next((s for s in sb.segments if abs(s.block_from - c) <= 1), None)
        first = next((p for p in sb.panels if seg and p.segment_id == seg.segment_id), None)
        signalled += bool(
            first and first.purpose in (Purpose.TIME_PLACE_CARD, Purpose.TRANSITION, Purpose.ESTABLISHING)
        )
    rows: list[dict] = []
    room_violations = 0
    for hs in hand["segments"]:
        b0, b1 = hs["blocks"]
        aliases = hs.get("aliases", {})
        in_range = [
            p for p in sb.panels if p.source_blocks and b0 <= min(p.source_blocks) <= b1
        ]
        cast_names = {m.name for p in in_range for m in p.cast if not m.entity_id.startswith(("crowd:", "unknown:"))}
        has_crowd = any(m.invented or m.entity_id.startswith("crowd:") for p in in_range for m in p.cast)
        present_hit, present_miss = [], []
        for n in hs["present"]:
            al = [n, *aliases.get(n, [])]
            ok = has_crowd if _GENERIC_HEAD.match(n) else any(_same(c, al) for c in cast_names)
            (present_hit if ok else present_miss).append(n)
        wrong = []
        for n in hs.get("referenced", []):
            al = [n, *aliases.get(n, [])]
            for p in in_range:
                if p.purpose is Purpose.REFERENCED_INSET:
                    continue
                if any(_same(m.name, al) for m in p.cast) or any(a.lower() in p.visual.lower() for a in al):
                    wrong.append({"name": n, "panel": p.panel_id, "purpose": p.purpose.value})
        room_violations += len(wrong)
        inset_hit = [
            n for n in hs.get("referenced", [])
            if any(
                p.purpose is Purpose.REFERENCED_INSET and any(_same(m.name, [n, *aliases.get(n, [])]) for m in p.cast)
                for p in sb.panels
            )
        ]
        rows.append(
            {"blocks": hs["blocks"], "present_found": present_hit, "present_missing": present_miss,
             "referenced_in_room": wrong, "referenced_shown_as_inset": inset_hit, "panels": len(in_range)}
        )
    total_present = sum(len(r["present_found"]) + len(r["present_missing"]) for r in rows)
    return {
        "hand_cuts": hand.get("cuts", []),
        "hand_cuts_found": found,
        "hand_cuts_found_and_signalled": signalled,
        "presence_recall": round(sum(len(r["present_found"]) for r in rows) / max(1, total_present), 2),
        "referenced_in_room_violations": room_violations,
        "presence_by_segment": rows,
    }


def format_table(card: dict) -> str:
    ref = REFERENCE_RI
    lines = ["| Row | Ours | Reference |", "|---|---|---|"]

    def row(label: str, key: str, fmt=str) -> None:
        r = ref.get(key)
        lines.append(f"| {label} | {fmt(card[key])} | {'' if r is None else fmt(r)} |")

    row("Panels", "panels")
    row("Cold open", "cold_open")
    row("Layers used", "layers_used")
    row("Letter kinds", "letter_kinds")
    row("SFX letters", "sfx")
    row("Inserts + extreme close-ups", "inserts_and_ecu")
    row("Crowd individuals", "crowd_individuals")
    row("Referenced insets", "referenced_insets")
    row("Panel shapes used", "shapes_used")
    lines.append(f"| Scene cuts signalled (director's own segments) | {card['segment_cuts_signalled']} of {card['segment_cuts']} | 3 of 3 |")
    if "hand_cuts" in card:
        lines.append(
            f"| Hand-marked cuts found / found and signalled | {len(card['hand_cuts_found'])} / "
            f"{card['hand_cuts_found_and_signalled']} of {len(card['hand_cuts'])} | all |"
        )
        lines.append(f"| Presence recall vs hand list | {card['presence_recall']} | 1.0 |")
        lines.append(f"| Referenced people drawn in the room | {card['referenced_in_room_violations']} | 0 |")
    return "\n".join(lines)
