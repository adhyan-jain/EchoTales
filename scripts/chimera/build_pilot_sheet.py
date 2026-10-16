"""Build the CHIMERA single-annotator pilot sheet (Checkpoint 2, W1 trimmed).

Why this exists: the disclosure question needs two labels per mention at a
cut point -- what a careful reader of chapters 1..c is warranted to believe,
and the omniscient answer -- and the repo has neither. Measured before this
script was written (scratch copy of the RI database, 2026-10-15):

- 2 of 11,095 alias bindings have `learned_chapter > story_from_lb`, both for
  "the clan head" (one entity);
- only 5 mentions (that same entity, chapter 1) are resolved to an entity
  that no RIGID_NAME mention names until a later chapter;
- the `rebind`/`merge` events are regex-detector noise, not reveals.

So the system's own state supplies almost no pre-reveal items. The pre-reveal
tier is therefore the three "the clan head" mentions plus the 20 hard-case
records whose own note uses disclosure language (withheld, doubt, secret,
unaware, ...). That is the best deterministic selection available without a
model reading the book, and the pilot's power statement must be written from
the resulting counts, not from the 89.

Everything here is deterministic (fixed seed) and read-only on the database.
The blind sheet carries source windows of the novel and is local only: it is
written to a path matched by the existing `data/eval/human_review_*.csv`
ignore rule, so no `.gitignore` edit is needed. Machine suggestions (the
gold draft identity and the system's target) live in a separate key file and
never in the sheet the annotator sees.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from echotales.core.store import Store
from echotales.pipeline.eval.coref_score import _block_starts

NOVEL = "reverend-insanity"
SEED = 20261015
GOLD = "data/gold/reverend-insanity-hardcases.jsonl"
SHEET = "data/eval/human_review_chimera_pilot.csv"
KEY = "data/eval/human_review_chimera_pilot_key.csv"
MANIFEST = "data/eval/chimera/pilot_manifest.json"

# Disclosure language in a hard-case note. Chosen from reading what the notes
# say (REVEAL/DISGUISE/withheld/...), not tuned on any result.
DISCLOSURE = re.compile(
    r"withheld|conceal|unnamed|not yet|hidden|before the reveal|until|later revealed|"
    r"doubt|secret|unaware|does not know|misdirect|false belief|cover",
    re.I,
)

N_CLAN_HEAD = 3
N_HARD_OTHER = 17
N_PLAIN = 30
WINDOW_BEFORE, WINDOW_AFTER = 250, 150
BATCH = 24


def category(note: str) -> str:
    m = re.match(r"\[(\w+)\]", note)
    return m.group(1) if m else "uncategorised"


def window(text: str, start: int, length: int) -> str:
    lo, hi = max(0, start - WINDOW_BEFORE), min(len(text), start + length + WINDOW_AFTER)
    return text[lo:start] + "[[" + text[start : start + length] + "]]" + text[start + length : hi]


SHIFTS: Counter = Counter()


def realign(text: str, at: int, surface: str, slack: int = 5) -> int:
    """Chapter-absolute offset of a system mention, corrected for a known defect.

    `Mention.offset` is sometimes one character early inside a block (measured
    2026-10-15: 6 of 44 chapter-1 mentions in the RI database, e.g. block 78
    offset 84 and block 68 offset 219 for "the clan head"), so `block start +
    offset` does not always index `story_text`. Search a few characters either
    side for the exact surface, and count how often a shift was needed so the
    defect is reported rather than silently absorbed. Failing to find the
    surface is an error, never a guess.
    """
    for d in sorted(range(-slack, slack + 1), key=abs):
        if text[at + d : at + d + len(surface)] == surface:
            SHIFTS[d] += 1
            return at + d
    raise SystemExit(f"cannot align system mention {surface!r} near offset {at}")


def label(ent: dict) -> str:
    return f"{ent['canonical_label']} [{ent['id'][-4:]}]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="a SCRATCH copy of the RI database")
    args = ap.parse_args()
    rng = random.Random(SEED)

    store = Store(args.db)
    chapters = {c.number: c for c in store.iter_chapters(NOVEL)}
    ents = {
        r[0]: dict(id=r[0], canonical_label=r[1], first_chapter=r[2], kind=r[3])
        for r in store.conn.execute(
            "select id, canonical_label, first_chapter, kind from self_entity where novel_id=?", (NOVEL,)
        )
    }
    by_label = defaultdict(list)
    for e in ents.values():
        by_label[e["canonical_label"].lower()].append(e)

    gold = [json.loads(line) for line in open(GOLD, encoding="utf-8")]
    for r in gold:
        r["_cat"] = category(r["note"])

    # --- tier P: pre-reveal candidates ---------------------------------------
    clan_rows = store.conn.execute(
        "select chapter, offset, text, block_index, target_id from mention "
        "where novel_id=? and lower(text) in ('the clan head','the guyue clan head') and chapter < 6 "
        "order by chapter, block_index, offset",
        (NOVEL,),
    ).fetchall()
    starts1 = _block_starts(store, NOVEL, 1.0)
    clan = [
        dict(src="system", chapter=float(c), offset=realign(chapters[1.0].story_text, starts1[b] + o, t), surface=t,
             category="clan_head_prereveal",
             gold_identity="", system_target=tgt)
        for c, o, t, b, tgt in clan_rows
    ]
    clan = sorted(clan, key=lambda r: r["offset"])[:N_CLAN_HEAD] if len(clan) <= N_CLAN_HEAD else rng.sample(clan, N_CLAN_HEAD)
    flagged = [r for r in gold if r["_cat"] != "not_entity_control" and DISCLOSURE.search(r["note"])]
    tier_p = clan + [
        dict(src="gold", chapter=r["chapter"], offset=r["offset"], surface=r["surface"], category=r["_cat"],
             gold_identity=r["identity"], system_target="")
        for r in flagged
    ]
    taken = {(r["chapter"], r["offset"]) for r in tier_p}

    # --- tier H: other hard cases, stratified by category --------------------
    rest = [r for r in gold if r["_cat"] != "not_entity_control" and (r["chapter"], r["offset"]) not in taken]
    cats = sorted({r["_cat"] for r in rest})
    pool = {c: [r for r in rest if r["_cat"] == c] for c in cats}
    picks: list[dict] = []
    while len(picks) < N_HARD_OTHER and any(pool.values()):
        for c in cats:
            if pool[c] and len(picks) < N_HARD_OTHER:
                picks.append(pool[c].pop(rng.randrange(len(pool[c]))))
    tier_h = [
        dict(src="gold", chapter=r["chapter"], offset=r["offset"], surface=r["surface"], category=r["_cat"],
             gold_identity=r["identity"], system_target="")
        for r in picks
    ]

    # --- tier C: plain-name controls (reader and truth expected to agree) ----
    first_name = {
        r[0]: r[1]
        for r in store.conn.execute(
            "select target_id, min(chapter) from mention where novel_id=? and alias_type='RIGID_NAME' "
            "and target_id is not null group by target_id",
            (NOVEL,),
        )
    }
    plain_rows = [
        r
        for r in store.conn.execute(
            "select chapter, offset, text, block_index, target_id from mention "
            "where novel_id=? and alias_type='RIGID_NAME' and target_id is not null and length(text) >= 4",
            (NOVEL,),
        )
        if r[4] in ents and ents[r[4]]["kind"] == "SELF" and r[2][:1].isupper() and r[0] > first_name.get(r[4], 1e9) + 0
        and (r[0], r[1]) not in taken
    ]
    bins: dict[int, list] = defaultdict(list)
    for r in plain_rows:
        bins[min(9, int(r[0] // 20))].append(r)
    per_bin = N_PLAIN // 10
    plain: list[dict] = []
    for b in range(10):
        for r in rng.sample(bins[b], min(per_bin, len(bins[b]))):
            st = _block_starts(store, NOVEL, r[0])
            plain.append(
                dict(src="system", chapter=float(r[0]),
                     offset=realign(chapters[float(r[0])].story_text, st[r[3]] + r[1], r[2]), surface=r[2],
                     category="plain_control", gold_identity="", system_target=r[4])
            )
    controls = [
        dict(src="gold", chapter=r["chapter"], offset=r["offset"], surface=r["surface"], category="not_entity_control",
             gold_identity=r["identity"], system_target="")
        for r in gold
        if r["_cat"] == "not_entity_control"
    ]
    tier_c = plain + controls

    # --- order: pre-reveal first, then a seeded shuffle of the rest ---------
    rest_items = [dict(i, tier="H") for i in tier_h] + [dict(i, tier="C") for i in tier_c]
    rng.shuffle(rest_items)
    items = [dict(i, tier="P") for i in tier_p] + rest_items

    sheet_rows, key_rows = [], []
    for n, it in enumerate(items, 1):
        c, off = it["chapter"], it["offset"]
        text = chapters[c].story_text
        if text[off : off + len(it["surface"])] != it["surface"]:
            raise SystemExit(f"offset mismatch for item {n}: ch{c} off{off} {it['surface']!r}")
        # Candidate shortlist: entities named in chapters c-3..c (introduced <= c),
        # plus the model's answer and three decoys, deduped and shuffled. The
        # same recipe for every tier, so the list itself does not mark an item.
        near = Counter(
            r[0]
            for r in store.conn.execute(
                "select target_id from mention where novel_id=? and chapter between ? and ? "
                "and alias_type='RIGID_NAME' and target_id is not null",
                (NOVEL, c - 3, c),
            )
            if r[0] in ents and ents[r[0]]["first_chapter"] <= c
        )
        cand_ids = [i for i, _ in near.most_common(8)]
        model_ids = []
        if it["system_target"] in ents:
            model_ids.append(it["system_target"])
        gi = it["gold_identity"].split(" (")[0].strip().lower()
        for e in by_label.get(gi, []):
            if e["first_chapter"] <= c:
                model_ids.append(e["id"])
        extra = [e["id"] for e in ents.values() if e["first_chapter"] <= c and e["kind"] == "SELF"]
        cand_ids = list(dict.fromkeys(cand_ids + model_ids))
        decoys = [x for x in rng.sample(extra, min(len(extra), 12)) if x not in cand_ids][:3]
        cand_ids = cand_ids + decoys
        rng.shuffle(cand_ids)
        cand_ids = cand_ids[:12]
        cand_txt = " | ".join(f"{chr(65 + k)}. {label(ents[i])}" for k, i in enumerate(cand_ids))
        item_id = f"CP-{n:03d}"
        sheet_rows.append(
            dict(
                item_id=item_id, batch=(n - 1) // BATCH + 1, novel=NOVEL, chapter=c, mention_offset=off,
                mention_surface=it["surface"], source_window=window(text, off, len(it["surface"])),
                candidates=cand_txt, reader_warranted="", reader_evidence="", omniscient_id="",
                omniscient_evidence="", reveal_chapter="", confidence_1to3="", minutes_spent="",
                notes="", annotator="", provenance="",
            )
        )
        key_rows.append(
            dict(
                item_id=item_id, tier=it["tier"], category=it["category"], source=it["src"],
                gold_identity=it["gold_identity"], system_target=it["system_target"],
                candidate_ids=";".join(cand_ids),
            )
        )
    store.close()

    Path(SHEET).parent.mkdir(parents=True, exist_ok=True)
    for path, rows in ((SHEET, sheet_rows), (KEY, key_rows)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
    manifest = {
        "built": "2026-10-15",
        "seed": SEED,
        "n_items": len(items),
        "tiers": dict(Counter(i["tier"] for i in items)),
        "categories": dict(Counter(i["category"] for i in items)),
        "pre_reveal_candidates": len(tier_p),
        "mention_offset_shifts": {str(k): v for k, v in sorted(SHIFTS.items())},
        "script_sha256": sha(__file__),
        "sheet_sha256": sha(SHEET),
        "key_sha256": sha(KEY),
        "sheet_is_local_only": True,
    }
    Path(MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
