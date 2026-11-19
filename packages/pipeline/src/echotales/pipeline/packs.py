"""Adaptation packs (`.etpack`): share an adaptation without sharing the book.

A pack is a zip holding a JSON manifest and one JSON file per kind of decision: the cast (entities and their names),
per-interval appearance descriptions, voice casting, panel direction with its prompts, and reviewer corrections.
Every item is keyed to the SHA-256 of the chapter it came from (`long_series.chapter_hash`), so a pack only applies
where the chapter text is the same. Someone who owns the same book imports it and renders the community's adaptation
locally; nobody has to distribute the novel.

The product rule is that a pack never carries the copyrighted text. `check_no_book_text` enforces it at export: any
string that shares a run of `LEAK_NGRAM_WORDS` consecutive words with the book's blocks rejects the whole export.
Graph `evidence` fields (quotations of the book) are never exported.
"""

from __future__ import annotations

import json
import re
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from echotales.core.enums import AliasType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import AliasBinding, Attribute, DiscoursePosition, VoiceProfile
from echotales.core.store import Store, normalize_alias
from echotales.pipeline.long_series import chapter_hash

PACK_FORMAT = "etpack"
PACK_VERSION = 1
PACK_SUFFIX = ".etpack"

#: Words in a row that a pack string may share with the book before the export is refused. Eight words is longer
#: than any name, title or short descriptive phrase ("tall man in a long grey coat") a description legitimately
#: repeats, and shorter than a sentence a reader would recognise as the author's.
LEAK_NGRAM_WORDS = 8

#: How many offending fields an error lists; the rest are counted.
LEAK_REPORT_LIMIT = 5

#: Attribute keys that are appearance and delivery facts a renderer uses (the Characters page's curated set).
APPEARANCE_KEYS = (
    "gender", "age_band", "typical_attire", "current_condition", "hair_color", "hair_style", "eye_color",
    "height_build", "skin_tone", "distinguishing_features", "register",
)

_PLAN_FILE = "panel_plan.jsonl"
_PLAN_FIELDS = (
    "panel_id", "panel_seq", "scene_index", "slot_kind", "lead_block", "block_indexes", "location", "direction",
    "prompt", "negative_prompt",
)
_ID_KEYS = ("from_id", "into_id", "speaker_id", "target_id", "self_id")
_WORD = re.compile(r"[a-z0-9]+")


class PackError(ValueError):
    """A pack that cannot be read or written."""


class PackLeakError(PackError):
    """The export would carry the book's own words."""

    def __init__(self, leaks: list[tuple[str, str]], total: int) -> None:
        self.leaks, self.total = leaks, total
        shown = "; ".join(f"{path}: {frag!r}" for path, frag in leaks)
        super().__init__(
            f"refusing to export: {total} field(s) share {LEAK_NGRAM_WORDS} or more consecutive words with the "
            f"book text ({shown})"
        )


# --- leak check -------------------------------------------------------------


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("’", "'").replace("'", ""))


def _grams(words: list[str]) -> Iterator[tuple[int, int]]:
    n = LEAK_NGRAM_WORDS
    for i in range(len(words) - n + 1):
        yield i, hash(" ".join(words[i : i + n]))


def book_ngrams(store: Store, novel_id: str) -> set[int]:
    """Hashes of every word 8-gram in the novel's blocks. Hashed, not stored: a 1,000-chapter book is millions."""
    out: set[int] = set()
    for chapter in store.iter_chapters(novel_id):
        for block in chapter.blocks:
            out.update(h for _, h in _grams(_words(block.text)))
    return out


def _strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _strings(v, f"{path}[{i}]")


def check_no_book_text(store: Store, novel_id: str, payload: Any) -> None:
    """Raise `PackLeakError` if any string in `payload` repeats `LEAK_NGRAM_WORDS` words of the book."""
    book = book_ngrams(store, novel_id)
    leaks: list[tuple[str, str]] = []
    total = 0
    for path, text in _strings(payload):
        words = _words(text)
        hit = next((i for i, h in _grams(words) if h in book), None)
        if hit is not None:
            total += 1
            if len(leaks) < LEAK_REPORT_LIMIT:
                leaks.append((path, " ".join(words[hit : hit + LEAK_NGRAM_WORDS])))
    if total:
        raise PackLeakError(leaks, total)


# --- export -----------------------------------------------------------------


def _chapter_hashes(store: Store, novel_id: str) -> dict[float, str]:
    return {c.number: chapter_hash(c) for c in store.iter_chapters(novel_id)}


def _plan_files(panel_root: Path) -> dict[float, Path]:
    """Each chapter's newest panel plan (`panels/chN/vK_suffix/`); versions compare as integers (v10 is after v9)."""
    best: dict[float, tuple[int, Path]] = {}
    for pf in panel_root.glob(f"ch*/v*/{_PLAN_FILE}"):
        head = pf.parent.name[1:].split("_")[0]
        try:
            chapter, num = float(pf.parent.parent.name[2:]), int(head)
        except ValueError:
            continue
        if chapter not in best or num > best[chapter][0]:
            best[chapter] = (num, pf)
    return {c: p for c, (_, p) in best.items()}


def _correction_chapter(store: Store, novel_id: str, payload: dict[str, Any]) -> float | None:
    """The chapter a correction acts on, from the id it names; None when nothing in it points at a chapter."""
    if "chapter" in payload:
        return float(payload["chapter"])
    for key, table in (("span_id", "span"), ("mention_id", "mention")):
        if payload.get(key):
            row = store.conn.execute(f"SELECT chapter FROM {table} WHERE id=?", (payload[key],)).fetchone()
            if row:
                return float(row["chapter"])
    for key in ("from_id", "self_id", "target_id"):
        entity = store.get_self(str(payload[key])) if payload.get(key) else None
        if entity is not None:
            return float(entity.first_attested_pos.chapter)
    return None


def build_pack(
    store: Store, novel_id: str, *, corrections: Any = None, data_root: Path | str | None = None
) -> dict[str, Any]:
    """The pack's contents as plain JSON-able dicts, before the leak check and before zipping."""
    from echotales.pipeline import paths

    hashes = _chapter_hashes(store, novel_id)
    key = lambda n: {"chapter": n, "hash": hashes[n]}  # noqa: E731  (a one-line label for every item)
    novel = store.get_novel(novel_id) or {}
    skipped: list[dict[str, Any]] = []

    aliases: dict[str, list[dict[str, Any]]] = {}
    for b in store.all_aliases(novel_id):
        aliases.setdefault(b.target_id, []).append({"alias": b.alias, "type": b.alias_type.value})
    cast = []
    for e in store.all_selves(novel_id):
        n = float(e.first_attested_pos.chapter)
        if n in hashes:
            cast.append({"id": e.id, "label": e.canonical_label, "kind": e.kind.value,
                         "aliases": sorted(aliases.get(e.id, []), key=lambda a: a["alias"]), **key(n)})

    appearance = []
    targets = store.conn.execute("SELECT DISTINCT target_kind, target_id FROM attribute WHERE novel_id=?", (novel_id,))
    for t in targets.fetchall():
        for a in store.get_attributes(TargetKind(t["target_kind"]), t["target_id"]):
            n = float(a.learned_at_pos.chapter)
            if a.key in APPEARANCE_KEYS and a.retracted_at is None and n in hashes:
                appearance.append({
                    "target_kind": a.target_kind.value, "target_id": a.target_id, "key": a.key, "value": a.value,
                    "interval": [a.interval.from_lb, a.interval.from_ub, a.interval.to_lb, a.interval.to_ub],
                    "offset": a.learned_at_pos.offset, **key(n),
                })

    voices = []
    spoken = _first_voice_by_speaker(novel_id, data_root)
    for e in store.all_selves(novel_id):
        vp = store.get_voice_profile(novel_id, e.id)
        manifest_voice = spoken.get(e.id)
        n = float(e.first_attested_pos.chapter)
        if (vp or manifest_voice) and n in hashes:
            voices.append({
                "self_id": e.id, "label": e.canonical_label,
                "profile": vp.model_dump(exclude={"id", "novel_id", "self_id"}) if vp else None,
                "voice": manifest_voice, **key(n),
            })

    direction = []
    for n, pf in sorted(_plan_files(paths.asset_dir(novel_id, "panels", data_root=data_root or paths.DATA_ROOT)).items()):
        if n not in hashes:
            skipped.append({"kind": "direction", "chapter": n, "reason": "chapter not in the database"})
            continue
        panels = []
        for line in pf.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                panels.append({k: row.get(k) for k in _PLAN_FIELDS} | {
                    "cast": [{"self_id": c["self_id"], "label": c.get("label", "")} for c in row.get("cast", [])]})
        direction.append({"panels": panels, **key(n)})

    corrections_out = []
    for c in (list(corrections) if corrections is not None else []):
        if c.type.value == "flag":
            continue
        n = _correction_chapter(store, novel_id, c.payload)
        if n is None or n not in hashes:
            skipped.append({"kind": "correction", "id": c.id, "reason": "names no chapter"})
            continue
        corrections_out.append({"type": c.type.value, "payload": c.payload, **key(n)})

    return {
        "manifest": {
            "format": PACK_FORMAT, "version": PACK_VERSION, "novel_title": novel.get("title", novel_id),
            "created_at": time.time(), "chapters": {f"{n:g}": h for n, h in sorted(hashes.items())},
            "skipped": skipped,
        },
        "cast": cast, "appearance": appearance, "voices": voices, "direction": direction,
        "corrections": corrections_out,
    }


def _first_voice_by_speaker(novel_id: str, data_root: Path | str | None) -> dict[str, dict[str, Any]]:
    from echotales.pipeline import paths
    from echotales.pipeline.webview import _voice_assignments_from_manifest

    found = _voice_assignments_from_manifest(novel_id, str(data_root or paths.DATA_ROOT))
    return {k: {"voice": v["voice"], "label": v["speaker_label"]} for k, v in found.items()}


_KINDS = ("cast", "appearance", "voices", "direction", "corrections")


def export_pack(
    store: Store, novel_id: str, out: Path | str, *, corrections: Any = None, data_root: Path | str | None = None
) -> Path:
    pack = build_pack(store, novel_id, corrections=corrections, data_root=data_root)
    # The manifest's chapter table is hashes only; everything else is checked word for word against the book.
    check_no_book_text(store, novel_id, {k: pack[k] for k in _KINDS} | {"title": pack["manifest"]["novel_title"]})
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(pack["manifest"], indent=2))
        for kind in _KINDS:
            z.writestr(f"{kind}.json", json.dumps(pack[kind], ensure_ascii=False))
    tmp.replace(out)
    return out


# --- import -----------------------------------------------------------------


@dataclass(slots=True)
class ImportReport:
    applied: dict[str, int] = field(default_factory=dict)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    direction_dir: str = ""

    def count(self, kind: str) -> None:
        self.applied[kind] = self.applied.get(kind, 0) + 1

    def skip(self, kind: str, reason: str, item: dict[str, Any]) -> None:
        self.skipped.append({"kind": kind, "reason": reason, "chapter": item.get("chapter"),
                             "what": item.get("label") or item.get("key") or item.get("type") or item.get("id") or ""})

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "skipped": self.skipped, "direction_dir": self.direction_dir}


def read_pack(path: Path | str) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as z:
            pack = {"manifest": json.loads(z.read("manifest.json"))} | {k: json.loads(z.read(f"{k}.json")) for k in _KINDS}
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise PackError(f"not a readable {PACK_SUFFIX} file: {exc}") from exc
    m = pack["manifest"]
    if m.get("format") != PACK_FORMAT or m.get("version") != PACK_VERSION:
        raise PackError(f"unsupported pack format {m.get('format')!r} version {m.get('version')!r}")
    return pack


def _translate(obj: Any, id_map: dict[str, str]) -> Any:
    if isinstance(obj, dict):
        return {k: (id_map.get(v, v) if k in _ID_KEYS and isinstance(v, str) else _translate(v, id_map)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_translate(v, id_map) for v in obj]
    return obj


def import_pack(
    store: Store, novel_id: str, path: Path | str, *, corrections_log: Any = None,
    data_root: Path | str | None = None,
) -> ImportReport:
    """Apply every item whose chapter hash matches this database's chapter, and report the rest.

    Entities are matched by id, then by label; one that matches neither is reported, never created (the local
    pipeline owns identity). Panel direction is written beside the novel's media, where a local render reads it.
    """
    from echotales.pipeline import paths

    pack = read_pack(path)
    local = _chapter_hashes(store, novel_id)
    report = ImportReport()

    def matches(item: dict[str, Any]) -> bool:
        ok = local.get(float(item["chapter"])) == item["hash"]
        if not ok:
            report.skip(_kind_of(item), "chapter text differs or is missing here", item)
        return ok

    selves = {e.id: e for e in store.all_selves(novel_id)}
    by_label = {e.canonical_label.casefold(): e.id for e in selves.values()}
    id_map: dict[str, str] = {}
    for item in pack["cast"]:
        if not matches(item):
            continue
        local_id = item["id"] if item["id"] in selves else by_label.get(item["label"].casefold())
        if local_id is None:
            report.skip("cast", "no entity with this id or label here; run the local pipeline first", item)
            continue
        id_map[item["id"]] = local_id
        report.count("cast")
        known = {normalize_alias(a.alias) for a in store.get_aliases_for(selves[local_id].kind, local_id)}
        for a in item["aliases"]:
            if normalize_alias(a["alias"]) not in known and AliasType(a["type"]).enters_graph:
                store.add_alias_binding(novel_id, AliasBinding(
                    alias=a["alias"], alias_type=AliasType(a["type"]), target_kind=selves[local_id].kind,
                    target_id=local_id, interval=FuzzyInterval.open_ended(float(item["chapter"])),
                    learned_at_pos=DiscoursePosition(chapter=int(item["chapter"])), observer_id="READER",
                ))
                known.add(normalize_alias(a["alias"]))

    persona_ids = {r["id"] for r in store.conn.execute("SELECT id FROM persona")}
    for item in pack["appearance"]:
        if not matches(item):
            continue
        target = _remap_target(item["target_id"], id_map)
        kind = TargetKind(item["target_kind"])
        if target is None or (kind is TargetKind.PERSONA and target not in persona_ids):
            report.skip("appearance", "its character or persona is not here", item)
            continue
        lb, ub, to_lb, to_ub = item["interval"]
        existing = {(a.key, a.value, a.interval) for a in store.get_attributes(kind, target)}
        interval = FuzzyInterval(from_lb=lb, from_ub=ub, to_lb=to_lb, to_ub=to_ub)
        if (item["key"], item["value"], interval) in existing:
            continue
        store.add_attribute(novel_id, Attribute(
            target_kind=kind, target_id=target, key=item["key"], value=item["value"], interval=interval,
            learned_at_pos=DiscoursePosition(chapter=int(item["chapter"]), offset=int(item.get("offset", 0))),
            observer_id="READER",
        ))
        report.count("appearance")

    root = paths.asset_dir(novel_id, "packs", data_root=data_root or paths.DATA_ROOT) / Path(path).stem
    casting: dict[str, Any] = {}
    for item in pack["voices"]:
        if not matches(item):
            continue
        target = id_map.get(item["self_id"])
        if target is None:
            report.skip("voices", "its character is not here", item)
            continue
        if item["profile"]:
            store.add_voice_profile(VoiceProfile(id=f"{target}:voice", novel_id=novel_id, self_id=target, **item["profile"]))
        if item["voice"]:
            casting[target] = item["voice"]
        report.count("voices")
    if casting:
        root.mkdir(parents=True, exist_ok=True)
        (root / "casting.json").write_text(json.dumps(casting, indent=2), encoding="utf-8")

    for item in pack["direction"]:
        if not matches(item):
            continue
        out = root / "direction" / f"ch{item['chapter']:g}.jsonl"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(_translate(p, id_map), ensure_ascii=False) + "\n" for p in item["panels"]),
                       encoding="utf-8")
        report.direction_dir = str(root / "direction")
        report.count("direction")

    if corrections_log is not None:
        from echotales.pipeline.corrections import Correction, CorrectionType

        have = {(c.type.value, json.dumps(c.payload, sort_keys=True)) for c in corrections_log}
        for item in pack["corrections"]:
            if not matches(item):
                continue
            payload = _translate(item["payload"], id_map)
            ids = [payload[k] for k in _ID_KEYS if isinstance(payload.get(k), str)]
            if any(i not in selves for i in ids):
                report.skip("corrections", "names a character that is not here", item)
                continue
            if (item["type"], json.dumps(payload, sort_keys=True)) in have:
                continue
            corrections_log.add(Correction(novel_id=novel_id, type=CorrectionType(item["type"]), payload=payload))
            report.count("corrections")
    store.conn.commit()
    return report


def _remap_target(target_id: str, id_map: dict[str, str]) -> str | None:
    """A persona id is `<self id>:<body>`; follow its self through the id map."""
    if target_id in id_map:
        return id_map[target_id]
    for old, new in id_map.items():
        if target_id.startswith(old + ":"):
            return new + target_id[len(old):]
    return None


def _kind_of(item: dict[str, Any]) -> str:
    for k in ("panels", "profile", "payload", "interval", "aliases"):
        if k in item:
            return {"panels": "direction", "profile": "voices", "payload": "corrections",
                    "interval": "appearance", "aliases": "cast"}[k]
    return "item"
