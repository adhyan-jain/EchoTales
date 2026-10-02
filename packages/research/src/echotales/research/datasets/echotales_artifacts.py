"""Read-only views over artifacts the product already wrote: render and audio
manifests, speech spans with their attribution tier, and the correction log.

Read-only by construction (SQLite opened with `mode=ro`): an experiment must
never mutate the run of record (`data/db/<novel>.db`), the rule
`data/scratch/reruns/` exists to protect.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from echotales.pipeline.paths import CORRECTIONS_DIR, db_path


@dataclass(frozen=True, slots=True)
class SpeechSpan:
    span_id: str
    chapter: float
    block_index: int
    span_type: str
    text: str
    speaker_self_id: str | None
    speaker_label: str | None
    method: str
    confidence: float


def speech_spans(novel_id: str, *, db: Path | None = None,
                 chapters: tuple[float, float] | None = None) -> list[SpeechSpan]:
    path = Path(db) if db else db_path(novel_id)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        q = (
            "SELECT s.id, s.chapter, s.block_index, s.span_type, s.text, s.speaker_self_id, "
            "e.canonical_label, s.attribution_method, s.confidence FROM span s "
            "LEFT JOIN self_entity e ON e.id = s.speaker_self_id "
            "WHERE s.novel_id = ? AND s.span_type IN ('DIALOGUE','INNER_MONOLOGUE')"
        )
        args: list[object] = [novel_id]
        if chapters:
            q += " AND s.chapter BETWEEN ? AND ?"
            args += [chapters[0], chapters[1]]
        q += " ORDER BY s.chapter, s.block_index, s.start"
        return [SpeechSpan(*row) for row in con.execute(q, args)]
    finally:
        con.close()


def read_jsonl(path: Path) -> list[dict]:
    with Path(path).open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def corrections(novel_id: str, *, kinds: set[str] | None = None,
                human_only: bool = True) -> list[dict]:
    """Correction records for a novel across every log file.

    `human_only` drops `agent:*` sources: an automated sweep's guesses are
    hypotheses, not labels, and treating them as ground truth would make any
    detector evaluated against them circular.
    """
    out = []
    for f in sorted(CORRECTIONS_DIR.glob("*.jsonl")):
        for rec in read_jsonl(f):
            if rec.get("novel_id") != novel_id:
                continue
            if kinds and rec.get("type") not in kinds:
                continue
            src = str(rec.get("payload", {}).get("source", ""))
            if human_only and src.startswith("agent"):
                continue
            out.append({**rec, "_file": f.name})
    return out
