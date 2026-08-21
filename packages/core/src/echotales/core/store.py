"""SQLite persistence for the narrative knowledge graph.

Storage is plain SQLite, not a graph database. The queries this system runs are
temporal range filters over a handful of well-indexed tables, which is exactly
what a relational engine is good at; graph traversal is not the bottleneck.

Two structural commitments:

**The event log is append-only.** `resolution_event` is never updated or
deleted. Every mutation to the graph is expressed as an event, so any state can
be reconstructed by replay, and a wrong decision made at chapter 40 can be
audited from chapter 190.

**Facts are closed, not deleted.** A title changing hands closes an interval; a
false claim being exposed sets `retracted_at`. Neither removes a row, because
"what did the reader believe at chapter 100" stays answerable either way.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from echotales.core.enums import (
    AliasType,
    AssertedBy,
    Canonicity,
    EventType,
    NarrativeLayer,
    Prominence,
    ResolutionMethod,
    SegmentType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import POS_INF, FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Attribute,
    Chapter,
    DiscoursePosition,
    Mention,
    NarrativeSegment,
    Persona,
    Relation,
    ResolutionEvent,
    Self,
    SelfPersonaBinding,
    Span,
)

SCHEMA_VERSION = 1

# Story positions may be +/-inf; SQLite has no infinity literal, so they are
# stored as REAL and Python's float('inf') round-trips correctly through the
# driver. Explicit here because it is easy to "fix" this into a bug.
_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS novel (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    adapter TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapter (
    novel_id TEXT NOT NULL REFERENCES novel(id),
    number REAL NOT NULL,
    title TEXT NOT NULL,
    source_href TEXT NOT NULL,
    blocks_json TEXT NOT NULL,
    PRIMARY KEY (novel_id, number)
);

CREATE TABLE IF NOT EXISTS span (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter REAL NOT NULL,
    block_index INTEGER NOT NULL,
    start INTEGER NOT NULL,
    end INTEGER NOT NULL,
    span_type TEXT NOT NULL,
    text TEXT NOT NULL,
    speaker_self_id TEXT,
    attribution_method TEXT NOT NULL,
    co_speaker_json TEXT NOT NULL DEFAULT '[]',
    delivery_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_span_chapter ON span(novel_id, chapter, start);
CREATE INDEX IF NOT EXISTS ix_span_speaker ON span(novel_id, speaker_self_id);

CREATE TABLE IF NOT EXISTS narrative_segment (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_from REAL NOT NULL,
    offset_from INTEGER NOT NULL,
    chapter_to REAL NOT NULL,
    offset_to INTEGER NOT NULL,
    timeline_id TEXT NOT NULL,
    story_seq_from REAL NOT NULL,
    story_seq_to REAL NOT NULL,
    segment_type TEXT NOT NULL,
    narrative_layer TEXT NOT NULL,
    canonicity TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_segment_span
    ON narrative_segment(novel_id, chapter_from, chapter_to);
CREATE INDEX IF NOT EXISTS ix_segment_timeline
    ON narrative_segment(novel_id, timeline_id, story_seq_from);

CREATE TABLE IF NOT EXISTS self_entity (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    canonical_label TEXT NOT NULL,
    first_chapter INTEGER NOT NULL,
    first_offset INTEGER NOT NULL,
    prominence TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_self_novel ON self_entity(novel_id);

CREATE TABLE IF NOT EXISTS persona (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    body_label TEXT NOT NULL,
    first_chapter INTEGER NOT NULL,
    first_offset INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_persona_novel ON persona(novel_id);

CREATE TABLE IF NOT EXISTS self_persona_binding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    self_id TEXT NOT NULL,
    persona_id TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    story_from_lb REAL NOT NULL,
    story_from_ub REAL NOT NULL,
    story_to_lb REAL NOT NULL,
    story_to_ub REAL NOT NULL,
    learned_chapter INTEGER NOT NULL,
    learned_offset INTEGER NOT NULL,
    observer_id TEXT NOT NULL,
    truth_status TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_spb_self ON self_persona_binding(self_id, timeline_id);
CREATE INDEX IF NOT EXISTS ix_spb_persona ON self_persona_binding(persona_id, timeline_id);

CREATE TABLE IF NOT EXISTS alias_binding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT NOT NULL,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    story_from_lb REAL NOT NULL,
    story_from_ub REAL NOT NULL,
    story_to_lb REAL NOT NULL,
    story_to_ub REAL NOT NULL,
    learned_chapter INTEGER NOT NULL,
    learned_offset INTEGER NOT NULL,
    observer_id TEXT NOT NULL,
    asserted_by TEXT NOT NULL,
    truth_status TEXT NOT NULL,
    retracted_chapter INTEGER,
    retracted_offset INTEGER,
    evidence TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_alias_lookup ON alias_binding(novel_id, alias_norm, timeline_id);
CREATE INDEX IF NOT EXISTS ix_alias_target ON alias_binding(target_kind, target_id);

CREATE TABLE IF NOT EXISTS attribute (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    story_from_lb REAL NOT NULL,
    story_from_ub REAL NOT NULL,
    story_to_lb REAL NOT NULL,
    story_to_ub REAL NOT NULL,
    learned_chapter INTEGER NOT NULL,
    learned_offset INTEGER NOT NULL,
    observer_id TEXT NOT NULL,
    asserted_by TEXT NOT NULL,
    truth_status TEXT NOT NULL,
    retracted_chapter INTEGER,
    retracted_offset INTEGER,
    evidence TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_attr_target ON attribute(target_kind, target_id, key);

CREATE TABLE IF NOT EXISTS relation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT NOT NULL,
    src_self TEXT NOT NULL,
    dst_self TEXT NOT NULL,
    type TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    story_from_lb REAL NOT NULL,
    story_from_ub REAL NOT NULL,
    story_to_lb REAL NOT NULL,
    story_to_ub REAL NOT NULL,
    learned_chapter INTEGER NOT NULL,
    learned_offset INTEGER NOT NULL,
    observer_id TEXT NOT NULL,
    asserted_by TEXT NOT NULL,
    truth_status TEXT NOT NULL,
    retracted_chapter INTEGER,
    retracted_offset INTEGER,
    evidence TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_rel_src ON relation(src_self, type);
CREATE INDEX IF NOT EXISTS ix_rel_dst ON relation(dst_self, type);

CREATE TABLE IF NOT EXISTS mention (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    chapter REAL NOT NULL,
    offset INTEGER NOT NULL,
    text TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    span_type TEXT NOT NULL,
    reference_mode TEXT NOT NULL,
    speaker_self_id TEXT,
    target_kind TEXT,
    target_id TEXT,
    local_group_id TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    method TEXT,
    provenance TEXT NOT NULL DEFAULT 'MACHINE',
    block_index INTEGER NOT NULL DEFAULT 0,
    entity_label TEXT
);
CREATE INDEX IF NOT EXISTS ix_mention_chapter ON mention(novel_id, chapter, offset);
CREATE INDEX IF NOT EXISTS ix_mention_target ON mention(target_kind, target_id);
CREATE INDEX IF NOT EXISTS ix_mention_group ON mention(local_group_id);

CREATE TABLE IF NOT EXISTS resolution_event (
    id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL UNIQUE,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    cause_chapter INTEGER NOT NULL,
    cause_offset INTEGER NOT NULL,
    read_set_hash TEXT NOT NULL DEFAULT '',
    method TEXT,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_event_seq ON resolution_event(seq);
CREATE INDEX IF NOT EXISTS ix_event_cause ON resolution_event(cause_chapter, cause_offset);

CREATE TABLE IF NOT EXISTS observation (
    observer_id TEXT NOT NULL,
    fact_ref TEXT NOT NULL,
    learned_chapter INTEGER NOT NULL,
    learned_offset INTEGER NOT NULL,
    PRIMARY KEY (observer_id, fact_ref)
);

-- Every LLM call routed by the escalation ladder. plans.md Section 7 names
-- "% routed to expensive inference vs accuracy gained" as a contribution, so
-- this table is evaluation data, not telemetry.
CREATE TABLE IF NOT EXISTS llm_call (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage TEXT NOT NULL,
    tier TEXT NOT NULL,
    model TEXT NOT NULL,
    escalated INTEGER NOT NULL DEFAULT 0,
    escalation_reason TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    ok INTEGER NOT NULL DEFAULT 1,
    novel_id TEXT NOT NULL DEFAULT '',
    chapter REAL
);
CREATE INDEX IF NOT EXISTS ix_llm_stage ON llm_call(stage, tier);

-- Read-set tracking for cache invalidation (plans.md Section 6 Phase 7).
CREATE TABLE IF NOT EXISTS derived_artifact (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    read_set_json TEXT NOT NULL,
    read_set_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    invalidated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_artifact_tier ON derived_artifact(tier, invalidated);
"""


def _pos_cols(pos: DiscoursePosition) -> tuple[int, int]:
    return pos.chapter, pos.offset


def _opt_pos_cols(pos: DiscoursePosition | None) -> tuple[int | None, int | None]:
    return (pos.chapter, pos.offset) if pos else (None, None)


def _interval_cols(iv: FuzzyInterval) -> tuple[float, float, float, float]:
    return iv.from_lb, iv.from_ub, iv.to_lb, iv.to_ub


def _interval_from_row(row: sqlite3.Row) -> FuzzyInterval:
    return FuzzyInterval(
        from_lb=row["story_from_lb"],
        from_ub=row["story_from_ub"],
        to_lb=row["story_to_lb"],
        to_ub=row["story_to_ub"],
    )


def _pos_from_row(row: sqlite3.Row, prefix: str) -> DiscoursePosition:
    return DiscoursePosition(chapter=row[f"{prefix}_chapter"], offset=row[f"{prefix}_offset"])


def _opt_pos_from_row(row: sqlite3.Row, prefix: str) -> DiscoursePosition | None:
    ch = row[f"{prefix}_chapter"]
    if ch is None:
        return None
    return DiscoursePosition(chapter=ch, offset=row[f"{prefix}_offset"] or 0)


def normalize_alias(alias: str) -> str:
    """Casefold and squash whitespace for index lookups.

    Deliberately conservative: honorific stripping is a *scoring* concern
    handled in the resolver, not a storage concern. Normalising too
    aggressively here would silently merge "Elder Wang" and "Wang" at the
    index level, destroying evidence the scorer needs to weigh.
    """
    return " ".join(alias.split()).casefold()


class Store:
    """Typed access to the graph. Owns the connection and the event sequence."""

    def __init__(self, path: Path | str = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def _migrate(self) -> None:
        """Additive column upgrades for databases created before they existed.

        `CREATE TABLE IF NOT EXISTS` in `_SCHEMA` only creates a table on a
        fresh database; it does not touch an existing table's columns, so a
        new nullable column needs an explicit, idempotent `ALTER TABLE` here.
        """
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(mention)")}
        if "entity_label" not in existing:
            self.conn.execute("ALTER TABLE mention ADD COLUMN entity_label TEXT")

        # Nullable rather than DEFAULT 'SELF': a pre-existing row genuinely
        # has no recorded kind, and reading NULL back as SELF is a decision
        # `get_self` makes explicitly (and documents) rather than one the
        # schema makes silently.
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(self_entity)")}
        if "kind" not in existing:
            self.conn.execute("ALTER TABLE self_entity ADD COLUMN kind TEXT")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---- novels and chapters -----------------------------------------

    def add_novel(self, novel_id: str, title: str, source_path: str, adapter: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO novel(id, title, source_path, adapter) VALUES (?,?,?,?)",
            (novel_id, title, source_path, adapter),
        )
        self.conn.commit()

    def add_chapter(self, chapter: Chapter) -> None:
        blocks = json.dumps([b.model_dump() for b in chapter.blocks])
        self.conn.execute(
            "INSERT OR REPLACE INTO chapter(novel_id, number, title, source_href, blocks_json)"
            " VALUES (?,?,?,?,?)",
            (chapter.novel_id, chapter.number, chapter.title, chapter.source_href, blocks),
        )

    def get_chapter(self, novel_id: str, number: float) -> Chapter | None:
        row = self.conn.execute(
            "SELECT * FROM chapter WHERE novel_id=? AND number=?", (novel_id, number)
        ).fetchone()
        if row is None:
            return None
        return Chapter(
            novel_id=row["novel_id"],
            number=row["number"],
            title=row["title"],
            source_href=row["source_href"],
            blocks=json.loads(row["blocks_json"]),
        )

    def iter_chapters(self, novel_id: str) -> Iterator[Chapter]:
        """Stream chapters in order.

        A generator rather than a list on purpose: the machine has ~4.5 GB of
        free RAM and a 500-chapter novel's parsed blocks will not fit
        comfortably alongside an NER model.
        """
        cur = self.conn.execute(
            "SELECT * FROM chapter WHERE novel_id=? ORDER BY number", (novel_id,)
        )
        for row in cur:
            yield Chapter(
                novel_id=row["novel_id"],
                number=row["number"],
                title=row["title"],
                source_href=row["source_href"],
                blocks=json.loads(row["blocks_json"]),
            )

    def chapter_count(self, novel_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM chapter WHERE novel_id=?", (novel_id,)
        ).fetchone()
        return int(row["n"])

    # ---- spans --------------------------------------------------------

    def add_spans(self, spans: Sequence[Span]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO span(id, novel_id, chapter, block_index, start, end,"
            " span_type, text, speaker_self_id, attribution_method, co_speaker_json,"
            " delivery_json, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    s.id,
                    s.novel_id,
                    s.chapter,
                    s.block_index,
                    s.start,
                    s.end,
                    s.span_type.value,
                    s.text,
                    s.speaker_self_id,
                    s.attribution_method.value,
                    json.dumps(s.co_speaker_self_ids),
                    json.dumps(s.delivery_markers),
                    s.confidence,
                )
                for s in spans
            ],
        )

    def delete_span(self, novel_id: str, span_id: str) -> None:
        """Remove one span permanently.

        Only correct when nothing still depends on it existing: mentions
        address a block/offset range, not a span id, so a mention that fell
        inside the deleted span's range is unaffected as long as some other
        span (or an extended neighbour) now covers that range instead --
        `corrections.py::_apply_merge_lines` is responsible for that, this
        method only removes the row.
        """
        self.conn.execute(
            "DELETE FROM span WHERE novel_id=? AND id=?", (novel_id, span_id)
        )

    def delete_spans_for_chapter(self, novel_id: str, chapter: float) -> None:
        """Remove every span row for one chapter, before a full re-classification.

        `add_spans` is `INSERT OR REPLACE` keyed by span id
        (`{novel}:{chapter}:{block}:{i}`). That only overwrites ids the new
        batch actually produces -- if a re-run yields *fewer* spans for a
        block than a previous run did (a block reclassified from `PROSE` to
        `NON_DIEGETIC`, say, collapsing three spans into one), the ids the
        new batch never touches are silently left behind forever, mixed in
        with the fresh, correct rows. Any caller that re-derives a whole
        chapter's spans from scratch (`speakers/runner.py::attribute_novel`)
        must call this first.
        """
        self.conn.execute(
            "DELETE FROM span WHERE novel_id=? AND chapter=?", (novel_id, chapter)
        )

    def get_spans(self, novel_id: str, chapter: float) -> list[Span]:
        # `start`/`end` are offsets *within a block*, not within the chapter
        # (docstring on `Mention.offset` states the same convention for
        # mentions -- see `get_mentions` below). Ordering by `start` alone
        # sorts every block's first span together, then every block's second
        # span together, and so on, which is not reading order the moment any
        # block contains more than one span. `block_index` must be the primary
        # sort key.
        cur = self.conn.execute(
            "SELECT * FROM span WHERE novel_id=? AND chapter=? ORDER BY block_index, start",
            (novel_id, chapter),
        )
        return [
            Span(
                id=r["id"],
                novel_id=r["novel_id"],
                chapter=r["chapter"],
                block_index=r["block_index"],
                start=r["start"],
                end=r["end"],
                span_type=r["span_type"],
                text=r["text"],
                speaker_self_id=r["speaker_self_id"],
                attribution_method=r["attribution_method"],
                co_speaker_self_ids=json.loads(r["co_speaker_json"]),
                delivery_markers=json.loads(r["delivery_json"]),
                confidence=r["confidence"],
            )
            for r in cur
        ]

    # ---- segments -----------------------------------------------------

    def add_segments(self, segments: Sequence[NarrativeSegment]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO narrative_segment(id, novel_id, chapter_from, offset_from,"
            " chapter_to, offset_to, timeline_id, story_seq_from, story_seq_to, segment_type,"
            " narrative_layer, canonicity, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    s.id,
                    s.novel_id,
                    s.chapter_from,
                    s.offset_from,
                    s.chapter_to,
                    s.offset_to,
                    s.timeline_id,
                    s.story_seq_from,
                    s.story_seq_to,
                    s.segment_type.value,
                    s.narrative_layer.value,
                    s.canonicity.value,
                    s.confidence,
                )
                for s in segments
            ],
        )

    def get_segments(self, novel_id: str, chapter: float | None = None) -> list[NarrativeSegment]:
        if chapter is None:
            cur = self.conn.execute(
                "SELECT * FROM narrative_segment WHERE novel_id=? ORDER BY chapter_from,"
                " offset_from",
                (novel_id,),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM narrative_segment WHERE novel_id=? AND chapter_from<=?"
                " AND chapter_to>=? ORDER BY chapter_from, offset_from",
                (novel_id, chapter, chapter),
            )
        return [
            NarrativeSegment(
                id=r["id"],
                novel_id=r["novel_id"],
                chapter_from=r["chapter_from"],
                offset_from=r["offset_from"],
                chapter_to=r["chapter_to"],
                offset_to=r["offset_to"],
                timeline_id=r["timeline_id"],
                story_seq_from=r["story_seq_from"],
                story_seq_to=r["story_seq_to"],
                segment_type=SegmentType(r["segment_type"]),
                narrative_layer=NarrativeLayer(r["narrative_layer"]),
                canonicity=Canonicity(r["canonicity"]),
                confidence=r["confidence"],
            )
            for r in cur
        ]

    def void_span(self, segment_ids: Sequence[str]) -> None:
        """Flip segments to VOIDED (the illusion-arc case, plans.md Section 2.4).

        Facts inside a voided span stop contributing to canonical-timeline
        queries but remain fully queryable for "what did the reader believe at
        the time", which is why this updates canonicity rather than deleting.
        """
        self.conn.executemany(
            "UPDATE narrative_segment SET canonicity=? WHERE id=?",
            [(Canonicity.VOIDED.value, sid) for sid in segment_ids],
        )

    # ---- entities -----------------------------------------------------

    def add_self(self, entity: Self) -> None:
        ch, off = _pos_cols(entity.first_attested_pos)
        self.conn.execute(
            "INSERT OR REPLACE INTO self_entity(id, novel_id, canonical_label, first_chapter,"
            " first_offset, prominence, notes, kind) VALUES (?,?,?,?,?,?,?,?)",
            (
                entity.id,
                entity.novel_id,
                entity.canonical_label,
                ch,
                off,
                entity.prominence.value,
                entity.notes,
                entity.kind.value,
            ),
        )

    def get_self(self, self_id: str) -> Self | None:
        r = self.conn.execute("SELECT * FROM self_entity WHERE id=?", (self_id,)).fetchone()
        if r is None:
            return None
        return Self(
            id=r["id"],
            novel_id=r["novel_id"],
            canonical_label=r["canonical_label"],
            first_attested_pos=DiscoursePosition(
                chapter=r["first_chapter"], offset=r["first_offset"]
            ),
            prominence=Prominence(r["prominence"]),
            notes=r["notes"],
            # NULL means the row predates the `kind` column, not that it has
            # no kind. SELF is the right reading: every entity written before
            # typing existed was minted as a person by a resolver that could
            # not express anything else.
            kind=TargetKind(r["kind"]) if r["kind"] else TargetKind.SELF,
        )

    def all_selves(self, novel_id: str) -> list[Self]:
        cur = self.conn.execute("SELECT id FROM self_entity WHERE novel_id=?", (novel_id,))
        out = []
        for r in cur.fetchall():
            entity = self.get_self(r["id"])
            if entity:
                out.append(entity)
        return out

    def chapter_numbers(self, novel_id: str) -> list[float]:
        """Chapter numbers in reading order, without loading their blocks.

        `iter_chapters` materialises every block of every chapter, which is
        wasteful for a caller that only needs to know which chapters exist
        before fetching spans per chapter.
        """
        return [
            float(r["number"])
            for r in self.conn.execute(
                "SELECT number FROM chapter WHERE novel_id=? ORDER BY number",
                (novel_id,),
            )
        ]

    def mention_count_for(self, novel_id: str, target_id: str) -> int:
        """How many mentions resolved to this entity."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM mention WHERE novel_id=? AND target_id=?",
            (novel_id, target_id),
        ).fetchone()
        return int(row["n"] or 0)

    def chapters_for_target(
        self, novel_id: str, target_id: str, *, limit: int | None = None
    ) -> list[float]:
        """Chapters where this entity is mentioned, in reading order.

        `limit` samples the *earliest* such chapters rather than the novel's
        first N: a character introduced at chapter 90 would otherwise be
        sampled from chapters they never appear in, and read as having no
        evidence at all.
        """
        sql = (
            "SELECT DISTINCT chapter FROM mention WHERE novel_id=? AND target_id=?"
            " ORDER BY chapter"
        )
        params: list[object] = [novel_id, target_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [float(r["chapter"]) for r in self.conn.execute(sql, params)]

    def set_prominence(self, self_id: str, prominence: Prominence) -> None:
        self.conn.execute(
            "UPDATE self_entity SET prominence=? WHERE id=?", (prominence.value, self_id)
        )

    def add_persona(self, persona: Persona) -> None:
        ch, off = _pos_cols(persona.first_attested_pos)
        self.conn.execute(
            "INSERT OR REPLACE INTO persona(id, novel_id, body_label, first_chapter,"
            " first_offset, notes) VALUES (?,?,?,?,?,?)",
            (persona.id, persona.novel_id, persona.body_label, ch, off, persona.notes),
        )

    def get_persona(self, persona_id: str) -> Persona | None:
        r = self.conn.execute("SELECT * FROM persona WHERE id=?", (persona_id,)).fetchone()
        if r is None:
            return None
        return Persona(
            id=r["id"],
            novel_id=r["novel_id"],
            body_label=r["body_label"],
            first_attested_pos=DiscoursePosition(
                chapter=r["first_chapter"], offset=r["first_offset"]
            ),
            notes=r["notes"],
        )

    def add_self_persona_binding(self, binding: SelfPersonaBinding) -> None:
        lch, loff = _pos_cols(binding.learned_at_pos)
        self.conn.execute(
            "INSERT INTO self_persona_binding(self_id, persona_id, timeline_id, story_from_lb,"
            " story_from_ub, story_to_lb, story_to_ub, learned_chapter, learned_offset,"
            " observer_id, truth_status, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                binding.self_id,
                binding.persona_id,
                binding.timeline_id,
                *_interval_cols(binding.interval),
                lch,
                loff,
                binding.observer_id,
                binding.truth_status.value,
                binding.confidence,
            ),
        )

    def clear_self_persona_bindings(self, self_id: str) -> int:
        """Drop every binding for one self, returning how many went.

        `add_self_persona_binding` is a plain INSERT (a self legitimately has
        several bindings, so INSERT OR REPLACE would be wrong), which makes
        re-running the persona stage additive: a second run would leave the
        character bound to two copies of each body. Callers that *rebuild* a
        self's bodies clear first. Same class of bug as `resolve_novel`
        clearing stale resolution events before re-resolving.
        """
        cur = self.conn.execute(
            "DELETE FROM self_persona_binding WHERE self_id=?", (self_id,)
        )
        return cur.rowcount

    def get_self_persona_bindings(
        self, *, self_id: str | None = None, persona_id: str | None = None
    ) -> list[SelfPersonaBinding]:
        clauses, params = [], []
        if self_id:
            clauses.append("self_id=?")
            params.append(self_id)
        if persona_id:
            clauses.append("persona_id=?")
            params.append(persona_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = self.conn.execute(f"SELECT * FROM self_persona_binding {where}", params)
        return [
            SelfPersonaBinding(
                self_id=r["self_id"],
                persona_id=r["persona_id"],
                timeline_id=r["timeline_id"],
                interval=_interval_from_row(r),
                learned_at_pos=_pos_from_row(r, "learned"),
                observer_id=r["observer_id"],
                truth_status=TruthStatus(r["truth_status"]),
                confidence=r["confidence"],
            )
            for r in cur
        ]

    # ---- facts --------------------------------------------------------

    def add_alias_binding(self, novel_id: str, binding: AliasBinding) -> int:
        """Persist an alias binding.

        Construction of `AliasBinding` already rejects GENERIC_DESCRIPTOR, so
        by the time a value reaches this method the type invariant holds.
        """
        lch, loff = _pos_cols(binding.learned_at_pos)
        rch, roff = _opt_pos_cols(binding.retracted_at)
        cur = self.conn.execute(
            "INSERT INTO alias_binding(novel_id, alias, alias_norm, alias_type, target_kind,"
            " target_id, timeline_id, story_from_lb, story_from_ub, story_to_lb, story_to_ub,"
            " learned_chapter, learned_offset, observer_id, asserted_by, truth_status,"
            " retracted_chapter, retracted_offset, evidence, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                novel_id,
                binding.alias,
                normalize_alias(binding.alias),
                binding.alias_type.value,
                binding.target_kind.value,
                binding.target_id,
                binding.timeline_id,
                *_interval_cols(binding.interval),
                lch,
                loff,
                binding.observer_id,
                binding.asserted_by.value,
                binding.truth_status.value,
                rch,
                roff,
                binding.evidence,
                binding.confidence,
            ),
        )
        return int(cur.lastrowid or 0)

    def _alias_from_row(self, r: sqlite3.Row) -> AliasBinding:
        return AliasBinding(
            alias=r["alias"],
            alias_type=AliasType(r["alias_type"]),
            target_kind=TargetKind(r["target_kind"]),
            target_id=r["target_id"],
            timeline_id=r["timeline_id"],
            interval=_interval_from_row(r),
            learned_at_pos=_pos_from_row(r, "learned"),
            observer_id=r["observer_id"],
            asserted_by=AssertedBy(r["asserted_by"]),
            truth_status=TruthStatus(r["truth_status"]),
            retracted_at=_opt_pos_from_row(r, "retracted"),
            evidence=r["evidence"],
            confidence=r["confidence"],
        )

    def find_alias_bindings(
        self, novel_id: str, alias: str, timeline_id: str | None = None
    ) -> list[AliasBinding]:
        """All bindings for a surface form, unfiltered by time.

        Returns every holder because alias->target is one-to-many at any given
        moment. Temporal and observer filtering happen in `state_of`; doing it
        here would hide the ambiguity the scorer is supposed to resolve.
        """
        if timeline_id:
            cur = self.conn.execute(
                "SELECT * FROM alias_binding WHERE novel_id=? AND alias_norm=? AND timeline_id=?",
                (novel_id, normalize_alias(alias), timeline_id),
            )
        else:
            cur = self.conn.execute(
                "SELECT * FROM alias_binding WHERE novel_id=? AND alias_norm=?",
                (novel_id, normalize_alias(alias)),
            )
        return [self._alias_from_row(r) for r in cur]

    def get_aliases_for(self, target_kind: TargetKind, target_id: str) -> list[AliasBinding]:
        cur = self.conn.execute(
            "SELECT * FROM alias_binding WHERE target_kind=? AND target_id=?",
            (target_kind.value, target_id),
        )
        return [self._alias_from_row(r) for r in cur]

    def all_aliases(self, novel_id: str) -> list[AliasBinding]:
        cur = self.conn.execute("SELECT * FROM alias_binding WHERE novel_id=?", (novel_id,))
        return [self._alias_from_row(r) for r in cur]

    def close_alias_interval(self, binding_id: int, end_lb: float, end_ub: float | None) -> None:
        """The fact was true and has stopped being true (title transferred)."""
        self.conn.execute(
            "UPDATE alias_binding SET story_to_lb=?, story_to_ub=? WHERE id=?",
            (end_lb, end_lb if end_ub is None else end_ub, binding_id),
        )

    def retract_alias(self, binding_id: int, at: DiscoursePosition) -> None:
        """The fact was never true (impostor unmasked).

        Distinct from `close_alias_interval` by design; see enums.EventType.
        The interval is left untouched because the *claim* did span that time,
        and a reader-observer query before `at` must still surface it.
        """
        self.conn.execute(
            "UPDATE alias_binding SET retracted_chapter=?, retracted_offset=?,"
            " truth_status=? WHERE id=?",
            (at.chapter, at.offset, TruthStatus.FALSE.value, binding_id),
        )

    def add_attribute(self, novel_id: str, attr: Attribute) -> int:
        lch, loff = _pos_cols(attr.learned_at_pos)
        rch, roff = _opt_pos_cols(attr.retracted_at)

        # **An exact-duplicate row carries no information, and re-runs made
        # many of them.** This is a plain INSERT with no delete-on-rederive,
        # the same store-hygiene gap `delete_spans_for_chapter` /
        # `delete_mentions_for_chapter` closed for spans and mentions -- but
        # attributes are position-dated facts, so blanket-deleting a target's
        # rows before a re-derive would throw away attestations a partial run
        # never regenerates. Dropping only *byte-identical* rows is the
        # conservative half of that fix: it cannot lose a fact, and it stops
        # the accumulation. Measured on RI, Fang Yuan's body 1 carried three
        # identical `gender`/`age_band`/`register`/`big_five` rows each.
        existing = self.conn.execute(
            "SELECT id FROM attribute WHERE novel_id=? AND target_kind=? AND target_id=?"
            " AND key=? AND value=? AND learned_chapter IS ? AND learned_offset IS ?"
            " AND retracted_chapter IS ? AND retracted_offset IS ?",
            (
                novel_id,
                attr.target_kind.value,
                attr.target_id,
                attr.key,
                attr.value,
                lch,
                loff,
                rch,
                roff,
            ),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])

        cur = self.conn.execute(
            "INSERT INTO attribute(novel_id, target_kind, target_id, key, value, timeline_id,"
            " story_from_lb, story_from_ub, story_to_lb, story_to_ub, learned_chapter,"
            " learned_offset, observer_id, asserted_by, truth_status, retracted_chapter,"
            " retracted_offset, evidence, confidence)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                novel_id,
                attr.target_kind.value,
                attr.target_id,
                attr.key,
                attr.value,
                attr.timeline_id,
                *_interval_cols(attr.interval),
                lch,
                loff,
                attr.observer_id,
                attr.asserted_by.value,
                attr.truth_status.value,
                rch,
                roff,
                attr.evidence,
                attr.confidence,
            ),
        )
        return int(cur.lastrowid or 0)

    def get_attributes(self, target_kind: TargetKind, target_id: str) -> list[Attribute]:
        cur = self.conn.execute(
            "SELECT * FROM attribute WHERE target_kind=? AND target_id=?",
            (target_kind.value, target_id),
        )
        return [
            Attribute(
                target_kind=TargetKind(r["target_kind"]),
                target_id=r["target_id"],
                key=r["key"],
                value=r["value"],
                timeline_id=r["timeline_id"],
                interval=_interval_from_row(r),
                learned_at_pos=_pos_from_row(r, "learned"),
                observer_id=r["observer_id"],
                asserted_by=AssertedBy(r["asserted_by"]),
                truth_status=TruthStatus(r["truth_status"]),
                retracted_at=_opt_pos_from_row(r, "retracted"),
                evidence=r["evidence"],
                confidence=r["confidence"],
            )
            for r in cur
        ]

    def add_relation(self, novel_id: str, rel: Relation) -> int:
        lch, loff = _pos_cols(rel.learned_at_pos)
        rch, roff = _opt_pos_cols(rel.retracted_at)
        cur = self.conn.execute(
            "INSERT INTO relation(novel_id, src_self, dst_self, type, timeline_id, story_from_lb,"
            " story_from_ub, story_to_lb, story_to_ub, learned_chapter, learned_offset,"
            " observer_id, asserted_by, truth_status, retracted_chapter, retracted_offset,"
            " evidence, confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                novel_id,
                rel.src_self,
                rel.dst_self,
                rel.type,
                rel.timeline_id,
                *_interval_cols(rel.interval),
                lch,
                loff,
                rel.observer_id,
                rel.asserted_by.value,
                rel.truth_status.value,
                rch,
                roff,
                rel.evidence,
                rel.confidence,
            ),
        )
        return int(cur.lastrowid or 0)

    def get_relations(self, self_id: str, *, as_src: bool = True) -> list[Relation]:
        col = "src_self" if as_src else "dst_self"
        cur = self.conn.execute(f"SELECT * FROM relation WHERE {col}=?", (self_id,))
        return [
            Relation(
                src_self=r["src_self"],
                dst_self=r["dst_self"],
                type=r["type"],
                timeline_id=r["timeline_id"],
                interval=_interval_from_row(r),
                learned_at_pos=_pos_from_row(r, "learned"),
                observer_id=r["observer_id"],
                asserted_by=AssertedBy(r["asserted_by"]),
                truth_status=TruthStatus(r["truth_status"]),
                retracted_at=_opt_pos_from_row(r, "retracted"),
                evidence=r["evidence"],
                confidence=r["confidence"],
            )
            for r in cur
        ]

    # ---- mentions -----------------------------------------------------

    def add_mentions(self, mentions: Sequence[Mention]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO mention(id, novel_id, segment_id, chapter, offset, text,"
            " alias_type, span_type, reference_mode, speaker_self_id, target_kind, target_id,"
            " local_group_id, confidence, method, provenance, block_index, entity_label)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    m.id,
                    m.novel_id,
                    m.segment_id,
                    m.chapter,
                    m.offset,
                    m.text,
                    m.alias_type.value,
                    m.span_type.value,
                    m.reference_mode.value,
                    m.speaker_self_id,
                    m.target_kind.value if m.target_kind else None,
                    m.target_id,
                    m.local_group_id,
                    m.confidence,
                    m.method.value if m.method else None,
                    m.provenance.value,
                    m.block_index,
                    m.entity_label,
                )
                for m in mentions
            ],
        )

    def delete_mentions_for_chapter(self, novel_id: str, chapter: float) -> None:
        """Remove every mention row for one chapter, before a full re-extraction.

        Same hazard as `delete_spans_for_chapter`: `add_mentions` is
        `INSERT OR REPLACE` keyed by id, so a re-run that extracts *fewer*
        mentions for a chapter than a previous run did (a block newly
        excluded from story content, say) leaves the old run's now-invalid
        ids behind as permanent stale rows. `mentions/runner.py`'s
        per-chapter loop must call this before extending `pending` for that
        chapter.
        """
        self.conn.execute(
            "DELETE FROM mention WHERE novel_id=? AND chapter=?", (novel_id, chapter)
        )

    def get_mentions(
        self, novel_id: str, chapter: float | None = None, *, resolved_only: bool = False
    ) -> list[Mention]:
        sql = "SELECT * FROM mention WHERE novel_id=?"
        params: list[Any] = [novel_id]
        if chapter is not None:
            sql += " AND chapter=?"
            params.append(chapter)
        if resolved_only:
            sql += " AND target_id IS NOT NULL"
        # `offset` is block-local (see the field docstring on `Mention`), so
        # `ORDER BY chapter, offset` alone interleaves mentions from different
        # blocks by coincidence of their local offset rather than reading
        # order -- the same bug as `get_spans`, and more consequential here:
        # `resolve/runner.py::resolve_novel` explicitly relies on this call
        # for "strictly in discourse order" processing within a chapter.
        sql += " ORDER BY chapter, block_index, offset"
        cur = self.conn.execute(sql, params)
        return [Mention.model_validate(dict(r)) for r in cur]

    def mention_counts(self, novel_id: str) -> dict[str, int]:
        """Mentions per resolved target -- the primary prominence signal."""
        cur = self.conn.execute(
            "SELECT target_id, COUNT(*) AS n FROM mention WHERE novel_id=?"
            " AND target_id IS NOT NULL GROUP BY target_id",
            (novel_id,),
        )
        return {r["target_id"]: r["n"] for r in cur}

    # ---- event log ----------------------------------------------------

    def next_seq(self) -> int:
        row = self.conn.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM resolution_event").fetchone()
        return int(row["m"]) + 1

    def append_event(self, event: ResolutionEvent) -> None:
        """Append to the log. Never updates; the log is immutable by contract."""
        ch, off = _pos_cols(event.cause_pos)
        self.conn.execute(
            "INSERT INTO resolution_event(id, seq, type, payload, cause_chapter, cause_offset,"
            " read_set_hash, method, confidence) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                event.id,
                event.seq,
                event.type.value,
                json.dumps(event.payload, default=str),
                ch,
                off,
                event.read_set_hash,
                event.method.value if event.method else None,
                event.confidence,
            ),
        )

    def iter_events(self, up_to: DiscoursePosition | None = None) -> Iterator[ResolutionEvent]:
        """Replay the log in sequence order, optionally truncated.

        `up_to` is what makes the replay debugger work: reconstruct exactly
        what the graph believed at chapter 40, before the chapter 190 reveal
        rewrote it.
        """
        if up_to is None:
            cur = self.conn.execute("SELECT * FROM resolution_event ORDER BY seq")
        else:
            cur = self.conn.execute(
                "SELECT * FROM resolution_event WHERE (cause_chapter, cause_offset) <= (?, ?)"
                " ORDER BY seq",
                (up_to.chapter, up_to.offset),
            )
        for r in cur:
            yield ResolutionEvent(
                id=r["id"],
                seq=r["seq"],
                type=EventType(r["type"]),
                payload=json.loads(r["payload"]),
                cause_pos=_pos_from_row(r, "cause"),
                read_set_hash=r["read_set_hash"],
                method=ResolutionMethod(r["method"]) if r["method"] else None,
                confidence=r["confidence"],
            )

    def event_counts(self) -> dict[str, int]:
        cur = self.conn.execute(
            "SELECT type, COUNT(*) AS n FROM resolution_event GROUP BY type"
        )
        return {r["type"]: r["n"] for r in cur}

    # ---- llm accounting ------------------------------------------------

    def log_llm_call(
        self,
        *,
        stage: str,
        tier: str,
        model: str,
        escalated: bool = False,
        escalation_reason: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: int = 0,
        ok: bool = True,
        novel_id: str = "",
        chapter: float | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO llm_call(stage, tier, model, escalated, escalation_reason,"
            " prompt_tokens, completion_tokens, latency_ms, ok, novel_id, chapter)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                stage,
                tier,
                model,
                int(escalated),
                escalation_reason,
                prompt_tokens,
                completion_tokens,
                latency_ms,
                int(ok),
                novel_id,
                chapter,
            ),
        )

    def escalation_stats(self) -> list[dict[str, Any]]:
        """Per-stage escalation rates -- direct input to the Section 7 contribution."""
        cur = self.conn.execute(
            "SELECT stage, tier, COUNT(*) AS calls, SUM(escalated) AS escalations,"
            " SUM(prompt_tokens+completion_tokens) AS tokens, AVG(latency_ms) AS avg_ms"
            " FROM llm_call GROUP BY stage, tier ORDER BY stage, tier"
        )
        return [dict(r) for r in cur]

    # ---- derived artifacts / cache ------------------------------------

    def record_artifact(
        self, artifact_id: str, tier: str, read_set: Sequence[str], read_set_hash: str, payload: str
    ) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO derived_artifact(id, tier, read_set_json, read_set_hash,"
            " payload_json, invalidated) VALUES (?,?,?,?,?,0)",
            (artifact_id, tier, json.dumps(list(read_set)), read_set_hash, payload),
        )

    def invalidate_by_facts(self, changed_facts: Sequence[str]) -> int:
        """Invalidate artifacts whose read set intersects the changed facts.

        Set intersection rather than full reprocessing: a chapter-190 reveal
        should invalidate the handful of artifacts that consulted the affected
        entity, not 190 chapters of work.
        """
        changed = set(changed_facts)
        if not changed:
            return 0
        n = 0
        cur = self.conn.execute(
            "SELECT id, read_set_json FROM derived_artifact WHERE invalidated=0"
        )
        stale = []
        for r in cur.fetchall():
            if changed & set(json.loads(r["read_set_json"])):
                stale.append(r["id"])
        for aid in stale:
            self.conn.execute("UPDATE derived_artifact SET invalidated=1 WHERE id=?", (aid,))
            n += 1
        return n

    # ---- misc ---------------------------------------------------------

    def timelines(self, novel_id: str) -> list[str]:
        cur = self.conn.execute(
            "SELECT DISTINCT timeline_id FROM narrative_segment WHERE novel_id=?", (novel_id,)
        )
        return [r["timeline_id"] for r in cur]

    def open_interval_count(self, novel_id: str) -> int:
        """How many bindings still have no attested end. Useful as a sanity metric."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM alias_binding WHERE novel_id=? AND story_to_ub=?",
            (novel_id, POS_INF),
        ).fetchone()
        return int(row["n"])
