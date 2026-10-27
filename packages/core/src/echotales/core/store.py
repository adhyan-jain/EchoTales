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
import time
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
    CharacterBibleEntry,
    DiscoursePosition,
    Job,
    LocationBibleEntry,
    LocationPlate,
    Mention,
    NarrativeSegment,
    Observation,
    PipelineRun,
    Persona,
    PersonaVersion,
    RefImageCandidate,
    RefImageSelectionEvent,
    Relation,
    ResolutionEvent,
    ReviewItem,
    SceneState,
    Self,
    SelfPersonaBinding,
    Span,
    StageArtifact,
    StageRun,
    StageStatus,
    StoryBibleSnapshot,
    VoiceProfile,
)

SCHEMA_VERSION = 3

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

CREATE TABLE IF NOT EXISTS scene_state (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    crowd_mood TEXT,
    default_severity TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{}',
    set_at_chapter REAL NOT NULL,
    set_at_offset INTEGER NOT NULL,
    closed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_scene_state_segment ON scene_state(segment_id);
CREATE INDEX IF NOT EXISTS ix_scene_state_novel ON scene_state(novel_id, closed);

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

-- Every LLM call routed by the escalation ladder. docs/design/plans.md Section 7 names
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

-- Read-set tracking for cache invalidation (docs/design/plans.md Section 6 Phase 7).
CREATE TABLE IF NOT EXISTS derived_artifact (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    read_set_json TEXT NOT NULL,
    read_set_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    invalidated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_artifact_tier ON derived_artifact(tier, invalidated);

-- Reference-image search candidates (opt-in, backend-only). Nothing in
-- render/generation reads this table -- see RefImageCandidate's docstring
-- in core/models.py for why auto-conditioning off image search results is
-- deliberately not wired up, and HANDOFF 4.47 for the failure mode
-- (contamination from an auto-selected single reference image) this is
-- built not to repeat.
CREATE TABLE IF NOT EXISTS ref_image_candidate (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    self_id TEXT NOT NULL,
    character_label TEXT NOT NULL,
    source_url TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    source_page TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    backend TEXT NOT NULL DEFAULT '',
    found_at REAL NOT NULL DEFAULT 0,
    user_uploaded INTEGER NOT NULL DEFAULT 0,
    selected INTEGER NOT NULL DEFAULT 0,
    persona_id TEXT,
    quality_score REAL,
    role TEXT
);
CREATE INDEX IF NOT EXISTS ix_refimg_self ON ref_image_candidate(novel_id, self_id);

-- Append-only, same reasoning as resolution_event: a selection made once
-- (auto-search finding it, a user approving or overriding it) stays
-- auditable rather than being silently overwritten.
CREATE TABLE IF NOT EXISTS ref_image_selection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT NOT NULL,
    self_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_refimg_log_self ON ref_image_selection_log(novel_id, self_id);

-- Pipeline-run / provenance tracking (Core Pipeline Hardening, session 1).
-- `pipeline_run` is one `echotales run` invocation or a manually-chained
-- stage sequence sharing a run_id. Deliberately not using AUTOINCREMENT
-- anywhere in this group -- run_id/stage_run_id/artifact_id are minted by
-- pipeline_run.py as stable, human-legible strings, matching the project's
-- explicit rule that a DB row id must never stand in for semantic identity.
CREATE TABLE IF NOT EXISTS pipeline_run (
    run_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    pipeline_version TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    model_versions_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING'
);
CREATE INDEX IF NOT EXISTS ix_pipeline_run_novel ON pipeline_run(novel_id);

-- One stage invocation within a pipeline_run. `input_digest` is the
-- resumability/cache-invalidation signal: a stage command checks for an
-- existing SUCCEEDED row with a matching (stage_name, input_digest) before
-- doing any work.
CREATE TABLE IF NOT EXISTS stage_run (
    stage_run_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_run(run_id),
    stage_name TEXT NOT NULL,
    input_digest TEXT NOT NULL DEFAULT '',
    output_digest TEXT NOT NULL DEFAULT '',
    config_json TEXT NOT NULL DEFAULT '{}',
    started_at REAL NOT NULL DEFAULT 0,
    finished_at REAL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    error_summary TEXT NOT NULL DEFAULT '',
    parent_stage_run_ids_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS ix_stage_run_run ON stage_run(run_id);
CREATE INDEX IF NOT EXISTS ix_stage_run_lookup ON stage_run(stage_name, input_digest, status);

-- What a stage_run produced -- a pointer (manifest path, image dir, DB
-- row-range descriptor), not a duplicate of the output itself.
CREATE TABLE IF NOT EXISTS stage_artifact (
    artifact_id TEXT PRIMARY KEY,
    stage_run_id TEXT NOT NULL REFERENCES stage_run(stage_run_id),
    kind TEXT NOT NULL,
    path_or_ref TEXT NOT NULL,
    content_digest TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_stage_artifact_stage ON stage_artifact(stage_run_id);

-- HTTP-facing unit of work (Product Orchestration track). Distinct from
-- pipeline_run/stage_run: those stay the internal provenance record a
-- job's execution writes into; this is "what did I ask the server to do,
-- and is it done" for the webview_server job queue.
CREATE TABLE IF NOT EXISTS job (
    job_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    params_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL DEFAULT 0,
    started_at REAL,
    finished_at REAL,
    error_summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_job_novel ON job(novel_id, created_at);

-- Every (mention, candidate) evidence vector the resolver scored, captured
-- so an ablation can re-score it instead of re-resolving the volume.
-- `docs/design/details.md` and `docs/design/plans.md` have claimed since the design phase that
-- ablations "cost no additional LLM passes because they re-score cached
-- evidence vectors"; that cache did not exist, `EvidenceVector` lived only
-- in memory inside `resolve_group`, and every ablation was therefore a full
-- re-resolve (EVOLUTION 4.78).
--
-- Written only when a run opts in (`resolve --capture-evidence`): RI alone
-- produces tens of thousands of rows and the default resolve path should not
-- pay for an evaluation artifact nobody asked for.
CREATE TABLE IF NOT EXISTS scoring_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_id TEXT NOT NULL,
    run_tag TEXT NOT NULL DEFAULT '',
    chapter REAL NOT NULL DEFAULT 0,
    mention_id TEXT NOT NULL DEFAULT '',
    surface TEXT NOT NULL DEFAULT '',
    candidate_id TEXT NOT NULL DEFAULT '',
    candidate_label TEXT NOT NULL DEFAULT '',
    features_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_scoring_evidence_novel
    ON scoring_evidence(novel_id, run_tag, chapter);

CREATE TABLE IF NOT EXISTS review_item (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter REAL NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    candidates_json TEXT NOT NULL DEFAULT '[]',
    resolved INTEGER NOT NULL DEFAULT 0,
    resolution TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_review_item_novel ON review_item(novel_id, resolved);

CREATE TABLE IF NOT EXISTS screenplay_episode (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    source_chapters_json TEXT NOT NULL DEFAULT '[]',
    episode_json TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_screenplay_episode_novel ON screenplay_episode(novel_id);

CREATE TABLE IF NOT EXISTS location_plate (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    location_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    angle TEXT NOT NULL DEFAULT 'establishing',
    time_of_day TEXT NOT NULL DEFAULT 'day',
    selected INTEGER NOT NULL DEFAULT 0,
    is_approved INTEGER NOT NULL DEFAULT 0,
    found_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_location_plate_novel ON location_plate(novel_id, location_id);

-- A locked, versioned bible: the review gate's output (decisions D6). Renders read a lock, never live edits. The
-- per-chapter digests are what let a later lock say exactly which chapters (and so which episodes) an edit touched.
CREATE TABLE IF NOT EXISTS bible_lock (
    novel_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    pipeline_version TEXT NOT NULL DEFAULT '',
    digest TEXT NOT NULL,
    chapter_digests_json TEXT NOT NULL DEFAULT '{}',
    counts_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (novel_id, version)
);

-- How a line is performed, read by the reader's delivery pass. Its own table rather than a span column: the pass
-- writes nothing else, so re-running it cannot disturb the measured speaker attribution on the same rows.
CREATE TABLE IF NOT EXISTS span_emotion (
    novel_id TEXT NOT NULL,
    span_id TEXT NOT NULL,
    chapter REAL NOT NULL,
    emotion TEXT NOT NULL,
    intensity INTEGER NOT NULL,
    PRIMARY KEY (novel_id, span_id)
);

CREATE TABLE IF NOT EXISTS persona_version (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    self_id TEXT NOT NULL,
    persona_id TEXT NOT NULL,
    chapter_introduced REAL NOT NULL,
    shift_reason TEXT NOT NULL DEFAULT 'outfit_change',
    turnaround_sheet_path TEXT,
    expression_sheet_path TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_persona_version_self ON persona_version(novel_id, self_id, chapter_introduced);

CREATE TABLE IF NOT EXISTS voice_profile (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    self_id TEXT NOT NULL,
    speaker_id TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT 'neutral',
    age_group TEXT NOT NULL DEFAULT 'adult',
    pitch REAL NOT NULL DEFAULT 1.0,
    speed REAL NOT NULL DEFAULT 1.0,
    accent TEXT
);
CREATE INDEX IF NOT EXISTS ix_voice_profile_self ON voice_profile(novel_id, self_id);
"""


def _pos_cols(pos: DiscoursePosition) -> tuple[int, int]:
    return pos.chapter, pos.offset


def _opt_pos_cols(pos: DiscoursePosition | None) -> tuple[int | None, int | None]:
    return (pos.chapter, pos.offset) if pos else (None, None)


def _interval_cols(iv: FuzzyInterval) -> tuple[float, float, float, float]:
    return iv.from_lb, iv.from_ub, iv.to_lb, iv.to_ub


def _refimg_from_row(row: sqlite3.Row) -> RefImageCandidate:
    keys = row.keys()
    return RefImageCandidate(
        id=row["id"],
        novel_id=row["novel_id"],
        self_id=row["self_id"],
        character_label=row["character_label"],
        source_url=row["source_url"],
        thumbnail_url=row["thumbnail_url"],
        title=row["title"],
        source_page=row["source_page"],
        query=row["query"],
        backend=row["backend"],
        found_at=row["found_at"],
        user_uploaded=bool(row["user_uploaded"]),
        selected=bool(row["selected"]),
        persona_id=row["persona_id"] if "persona_id" in keys else None,
        quality_score=row["quality_score"] if "quality_score" in keys else None,
        role=row["role"] if "role" in keys else None,
    )


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
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
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

        # Section 7.2: project creation needs a content-type distinct from
        # `adapter` (which names the *ingest format* -- epub/generic -- not
        # what kind of writing this is). A pre-existing row has no recorded
        # type; "novel" is the correct default since every project before
        # this column existed was one.
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(novel)")}
        if "content_type" not in existing:
            self.conn.execute(
                "ALTER TABLE novel ADD COLUMN content_type TEXT NOT NULL DEFAULT 'novel'"
            )
        # The project's visual genre (`pipeline/persona/genre.py`); NULL means "not chosen", which detection fills in
        # at render time rather than guessing here.
        if "visual_genre" not in existing:
            self.conn.execute("ALTER TABLE novel ADD COLUMN visual_genre TEXT")

        # Visual Rendering Track Phase 1d: reconcile ref_image_candidate's
        # self_id-only keying with reference_gen.py's persona_id (body)
        # keying, and stop discarding evaluate_candidate_quality's score
        # after search. Both nullable -- a pre-existing row has neither.
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(ref_image_candidate)")}
        if "persona_id" not in existing:
            self.conn.execute("ALTER TABLE ref_image_candidate ADD COLUMN persona_id TEXT")
        if "quality_score" not in existing:
            self.conn.execute("ALTER TABLE ref_image_candidate ADD COLUMN quality_score REAL")
        if "role" not in existing:
            self.conn.execute("ALTER TABLE ref_image_candidate ADD COLUMN role TEXT")

        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(ref_image_selection_log)")}
        if "persona_id" not in existing:
            self.conn.execute("ALTER TABLE ref_image_selection_log ADD COLUMN persona_id TEXT")

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

    def add_novel(
        self,
        novel_id: str,
        title: str,
        source_path: str,
        adapter: str,
        *,
        content_type: str = "novel",
    ) -> None:
        # An upsert, not INSERT OR REPLACE: replacing the row reset every column it does not name, so re-ingesting a
        # project would have dropped its chosen `visual_genre`.
        self.conn.execute(
            "INSERT INTO novel(id, title, source_path, adapter, content_type) VALUES (?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET title=excluded.title, source_path=excluded.source_path,"
            " adapter=excluded.adapter, content_type=excluded.content_type",
            (novel_id, title, source_path, adapter, content_type),
        )
        self.conn.commit()

    def set_visual_genre(self, novel_id: str, genre: str | None) -> None:
        self.conn.execute("UPDATE novel SET visual_genre=? WHERE id=?", (genre, novel_id))
        self.conn.commit()

    def get_novel(self, novel_id: str) -> dict[str, str] | None:
        row = self.conn.execute("SELECT * FROM novel WHERE id=?", (novel_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_novels(self) -> list[dict[str, str]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM novel").fetchall()]

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

    def set_span_speaker(
        self, novel_id: str, span_id: str, speaker_self_id: str | None, method: str, confidence: float
    ) -> None:
        """Replace one span's speaker without touching its text, type or delivery markers.

        `add_spans` is a whole-row `INSERT OR REPLACE`, so re-attributing a speaker through it would have to
        round-trip every other column; the reader pass only knows the speaker."""
        self.conn.execute(
            "UPDATE span SET speaker_self_id=?, attribution_method=?, confidence=? WHERE novel_id=? AND id=?",
            (speaker_self_id, method, confidence, novel_id, span_id),
        )

    def set_span_type(self, novel_id: str, span_id: str, span_type: str) -> None:
        """Retype one span. The reader pass uses it when a named speaker owns a quote the classifier called a crowd
        reaction (LotM ch7 "What about you, Mister?" said by Audrey)."""
        self.conn.execute("UPDATE span SET span_type=? WHERE novel_id=? AND id=?", (span_type, novel_id, span_id))

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
        """Flip segments to VOIDED (the illusion-arc case, docs/design/plans.md Section 2.4).

        Facts inside a voided span stop contributing to canonical-timeline
        queries but remain fully queryable for "what did the reader believe at
        the time", which is why this updates canonicity rather than deleting.
        """
        self.conn.executemany(
            "UPDATE narrative_segment SET canonicity=? WHERE id=?",
            [(Canonicity.VOIDED.value, sid) for sid in segment_ids],
        )

    # ---- scene state ----------------------------------------------------

    def add_scene_state(self, state: SceneState) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO scene_state(id, novel_id, segment_id, location,"
            " crowd_mood, default_severity, extra_json, set_at_chapter, set_at_offset,"
            " closed) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                state.id,
                state.novel_id,
                state.segment_id,
                state.location,
                state.crowd_mood,
                state.default_severity,
                json.dumps(state.extra),
                float(state.set_at_position.chapter),
                state.set_at_position.offset,
                int(state.closed),
            ),
        )

    def get_scene_state(self, novel_id: str, segment_id: str) -> SceneState | None:
        """Latest non-closed row for this segment, or the latest row overall
        if every row for this segment has been closed -- mirrors "what do we
        currently believe" semantics."""
        cur = self.conn.execute(
            "SELECT * FROM scene_state WHERE novel_id=? AND segment_id=? AND closed=0"
            " ORDER BY set_at_chapter DESC, set_at_offset DESC LIMIT 1",
            (novel_id, segment_id),
        )
        r = cur.fetchone()
        if r is None:
            cur = self.conn.execute(
                "SELECT * FROM scene_state WHERE novel_id=? AND segment_id=?"
                " ORDER BY set_at_chapter DESC, set_at_offset DESC LIMIT 1",
                (novel_id, segment_id),
            )
            r = cur.fetchone()
        if r is None:
            return None
        return SceneState(
            id=r["id"],
            novel_id=r["novel_id"],
            segment_id=r["segment_id"],
            location=r["location"],
            crowd_mood=r["crowd_mood"],
            default_severity=r["default_severity"],
            extra=json.loads(r["extra_json"]),
            set_at_position=DiscoursePosition(
                chapter=int(r["set_at_chapter"]), offset=r["set_at_offset"]
            ),
            closed=bool(r["closed"]),
        )

    def close_scene_state(self, id: str) -> None:
        self.conn.execute("UPDATE scene_state SET closed=1 WHERE id=?", (id,))

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

    def mention_counts_by_chapter(self, novel_id: str, target_id: str) -> dict[float, int]:
        """Mentions resolved to this entity, per chapter.

        `mention_count_for` is a whole-volume number: a trait computed from it at chapter 5 silently uses chapters
        the reader has not reached (prefix audit, docs/research/PREFIX_FAITHFULNESS). A cumulative sum over this
        dict up to chapter c is the count a build from chapters <= c alone would have seen.
        """
        rows = self.conn.execute(
            "SELECT chapter, COUNT(*) AS n FROM mention WHERE novel_id=? AND target_id=? GROUP BY chapter",
            (novel_id, target_id),
        )
        return {float(r["chapter"]): int(r["n"]) for r in rows}

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

    def unset_kind_self_ids(self, novel_id: str) -> list[str]:
        """Ids whose raw `kind` column is NULL/empty -- pre-a17ea32 rows.

        Deliberately reads the raw column rather than going through
        `get_self()`, which coerces a NULL `kind` to `TargetKind.SELF` for
        backward-compat display. That coercion is exactly the bug the kind
        backfill (`resolve/kind_backfill.py`) exists to fix, so this query
        must see the true unset state to find candidates for it.
        """
        rows = self.conn.execute(
            "SELECT id FROM self_entity WHERE novel_id=? AND (kind IS NULL OR kind='')",
            (novel_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    def default_kind_self_ids(self, novel_id: str) -> list[str]:
        """Ids typed SELF with no NER evidence behind it: none of their
        mentions carries an `entity_label`.

        `_entity_kind` writes SELF when its founding mentions have no label,
        which is every entity of a database whose mentions predate the NER
        labelling pass. That SELF is a default, not a judgement, but because
        it is not NULL the kind backfill skipped it: the LOTM product database
        had all 93 entities as SELF, including "Tingen" and "Pelican Street",
        while the NER cache labelled "Tingen" a location 18 times out of 18.
        """
        rows = self.conn.execute(
            "SELECT id FROM self_entity s WHERE novel_id=? AND kind='SELF' AND NOT EXISTS ("
            "SELECT 1 FROM mention m WHERE m.target_id=s.id AND m.entity_label IS NOT NULL)",
            (novel_id,),
        ).fetchall()
        return [r["id"] for r in rows]

    def set_kind(self, self_id: str, kind: TargetKind) -> None:
        self.conn.execute(
            "UPDATE self_entity SET kind=? WHERE id=?", (kind.value, self_id)
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

    # ---- reference-image candidates ------------------------------------
    #
    # Opt-in, backend-only mechanism: see RefImageCandidate's docstring in
    # core/models.py. Nothing here is read by render/generation code, and
    # `select_ref_image_candidate` never touches any persona/prompt table --
    # it only flips `selected` and appends a log row.

    def add_ref_image_candidate(self, candidate: RefImageCandidate) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ref_image_candidate(id, novel_id, self_id,"
            " character_label, source_url, thumbnail_url, title, source_page, query,"
            " backend, found_at, user_uploaded, selected, persona_id, quality_score, role)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                candidate.id,
                candidate.novel_id,
                candidate.self_id,
                candidate.character_label,
                candidate.source_url,
                candidate.thumbnail_url,
                candidate.title,
                candidate.source_page,
                candidate.query,
                candidate.backend,
                candidate.found_at,
                int(candidate.user_uploaded),
                int(candidate.selected),
                candidate.persona_id,
                candidate.quality_score,
                candidate.role,
            ),
        )
        self.conn.commit()

    def get_ref_image_candidate(self, candidate_id: str) -> RefImageCandidate | None:
        r = self.conn.execute(
            "SELECT * FROM ref_image_candidate WHERE id=?", (candidate_id,)
        ).fetchone()
        return _refimg_from_row(r) if r is not None else None

    def list_ref_image_candidates(
        self,
        novel_id: str,
        self_id: str,
        *,
        persona_id: str | None = None,
        role: str | None = None,
    ) -> list[RefImageCandidate]:
        sql = "SELECT * FROM ref_image_candidate WHERE novel_id=? AND self_id=?"
        params: list[object] = [novel_id, self_id]
        if persona_id is not None:
            sql += " AND persona_id=?"
            params.append(persona_id)
        if role is not None:
            sql += " AND role=?"
            params.append(role)
        sql += " ORDER BY selected DESC, found_at DESC"
        cur = self.conn.execute(sql, tuple(params))
        return [_refimg_from_row(r) for r in cur]

    def log_ref_image_event(self, event: RefImageSelectionEvent) -> int:
        cur = self.conn.execute(
            "INSERT INTO ref_image_selection_log(novel_id, self_id, candidate_id, action,"
            " actor, note, at, persona_id) VALUES (?,?,?,?,?,?,?,?)",
            (
                event.novel_id,
                event.self_id,
                event.candidate_id,
                event.action,
                event.actor,
                event.note,
                event.at,
                event.persona_id,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_ref_image_selection_log(
        self, novel_id: str, self_id: str
    ) -> list[RefImageSelectionEvent]:
        cur = self.conn.execute(
            "SELECT * FROM ref_image_selection_log WHERE novel_id=? AND self_id=?"
            " ORDER BY id",
            (novel_id, self_id),
        )
        return [
            RefImageSelectionEvent(
                id=r["id"],
                novel_id=r["novel_id"],
                self_id=r["self_id"],
                candidate_id=r["candidate_id"],
                action=r["action"],
                actor=r["actor"],
                note=r["note"],
                at=r["at"],
                persona_id=r["persona_id"] if "persona_id" in r.keys() else None,
            )
            for r in cur
        ]

    def select_ref_image_candidate(
        self, novel_id: str, self_id: str, candidate_id: str, *, actor: str, note: str = ""
    ) -> None:
        """Mark one candidate selected and every other candidate for this
        character unselected, logging the change.

        When the candidate has a persona_id, unselection is scoped to that persona_id
        so multiple bodies of the same character do not evict each other.
        """
        import time

        row = self.conn.execute(
            "SELECT id, persona_id FROM ref_image_candidate WHERE id=? AND novel_id=? AND self_id=?",
            (candidate_id, novel_id, self_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"no ref image candidate {candidate_id!r} for self {self_id!r}")
        cand_persona_id = row["persona_id"] if "persona_id" in row.keys() else None
        with self.transaction():
            if cand_persona_id:
                # Scoped to this body so multi-body characters keep other bodies selected
                self.conn.execute(
                    "UPDATE ref_image_candidate SET selected=0 WHERE novel_id=? AND self_id=? AND persona_id=?",
                    (novel_id, self_id, cand_persona_id),
                )
            else:
                self.conn.execute(
                    "UPDATE ref_image_candidate SET selected=0 WHERE novel_id=? AND self_id=?",
                    (novel_id, self_id),
                )
            self.conn.execute(
                "UPDATE ref_image_candidate SET selected=1 WHERE id=?", (candidate_id,)
            )
        self.log_ref_image_event(
            RefImageSelectionEvent(
                novel_id=novel_id,
                self_id=self_id,
                candidate_id=candidate_id,
                action="select",
                actor=actor,
                note=note,
                at=time.time(),
                persona_id=cand_persona_id,
            )
        )

    def register_user_ref_image(
        self,
        novel_id: str,
        self_id: str,
        character_label: str,
        image_path: str,
        *,
        actor: str = "user",
        note: str = "",
    ) -> RefImageCandidate:
        """User-override path: register a locally supplied image as a
        candidate and select it immediately, in one call.

        This is the CLI's ``persona refimg register`` command. It goes
        through the same candidate table as auto-search results so the
        selection log reads uniformly ("where did the selected image come
        from") whether the source was a search hit or a human's own file.
        """
        import hashlib
        import time

        candidate = RefImageCandidate(
            id=f"{self_id}:user:{hashlib.sha1(image_path.encode()).hexdigest()[:10]}",
            novel_id=novel_id,
            self_id=self_id,
            character_label=character_label,
            source_url=f"file://{image_path}",
            backend="user-upload",
            found_at=time.time(),
            user_uploaded=True,
        )
        self.add_ref_image_candidate(candidate)
        self.select_ref_image_candidate(
            novel_id, self_id, candidate.id, actor=actor, note=note or "user override"
        )
        candidate.selected = True
        return candidate

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
                source_row_id=r["id"] if "id" in r.keys() else None,
            )
            for r in cur
        ]

    def retract_attribute(self, attr_id: int, at: DiscoursePosition) -> None:
        """The attribute was never true (e.g. deceptive claim unmasked)."""
        self.conn.execute(
            "UPDATE attribute SET retracted_chapter=?, retracted_offset=?,"
            " truth_status=? WHERE id=?",
            (at.chapter, at.offset, TruthStatus.FALSE.value, attr_id),
        )

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

    # ---- observations (the observer axis) -----------------------------

    def add_observation(self, observation: Observation) -> None:
        """Record that `observer_id` learned `fact_ref` at a discourse position.

        The `observation` table has existed since the first schema and was
        **empty in every shipped database** -- there was no writer, so
        `docs/design/architecture.md`'s headline acceptance test (`state_of(observer=X)`
        differing from `observer=READER`) could not return anything different
        (EVOLUTION 4.80).

        `INSERT OR IGNORE`, not `REPLACE`: knowledge time only moves forward,
        so the *earliest* moment an observer learned something is the true
        one, and a later re-witnessing must not push their knowledge later.
        """
        chapter, offset = _pos_cols(observation.learned_at_pos)
        self.conn.execute(
            "INSERT OR IGNORE INTO observation(observer_id, fact_ref,"
            " learned_chapter, learned_offset) VALUES (?,?,?,?)",
            (observation.observer_id, observation.fact_ref, chapter, offset),
        )

    def add_observations(self, observations: Sequence[Observation]) -> int:
        if not observations:
            return 0
        self.conn.executemany(
            "INSERT OR IGNORE INTO observation(observer_id, fact_ref,"
            " learned_chapter, learned_offset) VALUES (?,?,?,?)",
            [
                (o.observer_id, o.fact_ref, *_pos_cols(o.learned_at_pos))
                for o in observations
            ],
        )
        return len(observations)

    def observations_for(self, observer_id: str) -> dict[str, DiscoursePosition]:
        """fact_ref -> the position this observer learned it.

        Returned whole rather than queried per fact: `state_of` filters every
        candidate fact of an entity, and a per-fact round trip would put a
        query inside the hot loop of the one operation this project most wants
        to be cheap.
        """
        cur = self.conn.execute(
            "SELECT fact_ref, learned_chapter, learned_offset FROM observation"
            " WHERE observer_id=?",
            (observer_id,),
        )
        return {
            r["fact_ref"]: DiscoursePosition(
                chapter=r["learned_chapter"], offset=r["learned_offset"]
            )
            for r in cur
        }

    def count_observations(self, observer_id: str = "") -> int:
        if observer_id:
            return int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM observation WHERE observer_id=?", (observer_id,)
                ).fetchone()[0]
            )
        return int(self.conn.execute("SELECT COUNT(*) FROM observation").fetchone()[0])

    def observers(self) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT observer_id FROM observation ORDER BY observer_id"
            )
        ]

    def escalation_summary(self) -> dict[str, Any]:
        """Volume-wide escalation, from the persisted record rather than a router.

        `llm/router.py::report()` computes the same rate from in-process
        counters and had **zero callers** -- so the escalation rate, which
        `docs/design/architecture.md` Section 7 names as a claimed contribution and
        non-negotiable #7 calls "a reported metric, not a failure mode", was
        never reported anywhere. A router's counters are also the wrong source
        for `eval`, which runs in a separate process that makes no LLM calls
        at all and would truthfully report zero.
        """
        row = self.conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(escalated),0) AS escalations,"
            " COALESCE(SUM(prompt_tokens+completion_tokens),0) AS tokens,"
            " COALESCE(AVG(latency_ms),0) AS avg_ms FROM llm_call"
        ).fetchone()
        calls = int(row["calls"] or 0)
        escalations = int(row["escalations"] or 0)
        return {
            "calls": calls,
            "escalations": escalations,
            "escalation_rate": round(escalations / calls, 4) if calls else 0.0,
            "tokens": int(row["tokens"] or 0),
            "avg_latency_ms": round(float(row["avg_ms"] or 0.0), 1),
            "by_stage": self.escalation_stats(),
        }

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

    # ---- pipeline run / provenance ------------------------------------

    #: Repo-relative path to the canonical-DB registry (pipeline/paths.py's
    #: DATA_ROOT convention: `data/` resolved against CWD, not this module's
    #: location, since the project already runs CLI/tests from the repo
    #: root). Resolved lazily per call, not cached, so editing the registry
    #: takes effect without restarting a long-lived process.
    _CANONICAL_REGISTRY = Path("data/canonical_dbs.json")

    @property
    def is_canonical(self) -> bool:
        """Whether this store's path is a registered run-of-record DB.

        Absence of the registry file means "nothing is registered", not "an
        error" -- a scratch/test DB never created one and should not be
        blocked from working. A path is compared after resolving both sides
        to absolute, so `data/db/x.db` and
        `./data/webview-working/x.db` are recognised as the same file.
        """
        if self.path == ":memory:":
            return False
        if not self._CANONICAL_REGISTRY.is_file():
            return False
        try:
            registry = json.loads(self._CANONICAL_REGISTRY.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        this_path = Path(self.path).resolve()
        for entry in registry.get("paths", []):
            if Path(entry).resolve() == this_path:
                return True
        return False

    def add_pipeline_run(self, run: PipelineRun) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO pipeline_run(run_id, novel_id, source_digest,"
            " pipeline_version, config_json, model_versions_json, created_at, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                run.run_id,
                run.novel_id,
                run.source_digest,
                run.pipeline_version,
                run.config_json,
                run.model_versions_json,
                run.created_at,
                run.status.value,
            ),
        )
        self.conn.commit()

    def update_pipeline_run_status(self, run_id: str, status: StageStatus) -> None:
        self.conn.execute(
            "UPDATE pipeline_run SET status=? WHERE run_id=?", (status.value, run_id)
        )
        self.conn.commit()

    def set_pipeline_run_version(self, run_id: str, pipeline_version: str) -> None:
        self.conn.execute(
            "UPDATE pipeline_run SET pipeline_version=? WHERE run_id=?",
            (pipeline_version, run_id),
        )
        self.conn.commit()

    def latest_pipeline_version(self, novel_id: str) -> str | None:
        """Stamp of the newest `pipeline_run` for the novel; None when the
        database has never recorded a run, "" when it predates stamping."""
        row = self.conn.execute(
            "SELECT pipeline_version FROM pipeline_run WHERE novel_id=?"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (novel_id,),
        ).fetchone()
        return None if row is None else row["pipeline_version"]

    def get_pipeline_run(self, run_id: str) -> PipelineRun | None:
        row = self.conn.execute(
            "SELECT * FROM pipeline_run WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return PipelineRun(
            run_id=row["run_id"],
            novel_id=row["novel_id"],
            source_digest=row["source_digest"],
            pipeline_version=row["pipeline_version"],
            config_json=row["config_json"],
            model_versions_json=row["model_versions_json"],
            created_at=row["created_at"],
            status=StageStatus(row["status"]),
        )

    def _stage_run_from_row(self, row: sqlite3.Row) -> StageRun:
        return StageRun(
            stage_run_id=row["stage_run_id"],
            run_id=row["run_id"],
            stage_name=row["stage_name"],
            input_digest=row["input_digest"],
            output_digest=row["output_digest"],
            config_json=row["config_json"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=StageStatus(row["status"]),
            error_summary=row["error_summary"],
            parent_stage_run_ids=json.loads(row["parent_stage_run_ids_json"]),
        )

    def add_stage_run(self, stage: StageRun) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO stage_run(stage_run_id, run_id, stage_name,"
            " input_digest, output_digest, config_json, started_at, finished_at,"
            " status, error_summary, parent_stage_run_ids_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                stage.stage_run_id,
                stage.run_id,
                stage.stage_name,
                stage.input_digest,
                stage.output_digest,
                stage.config_json,
                stage.started_at,
                stage.finished_at,
                stage.status.value,
                stage.error_summary,
                json.dumps(stage.parent_stage_run_ids),
            ),
        )
        self.conn.commit()

    def update_stage_run(
        self,
        stage_run_id: str,
        *,
        status: StageStatus,
        finished_at: float | None = None,
        output_digest: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Finalize (or re-mark) a stage_run. `None` args leave the column unchanged."""
        current = self.get_stage_run(stage_run_id)
        if current is None:
            raise KeyError(f"no stage_run {stage_run_id!r}")
        self.conn.execute(
            "UPDATE stage_run SET status=?, finished_at=?, output_digest=?,"
            " error_summary=? WHERE stage_run_id=?",
            (
                status.value,
                finished_at if finished_at is not None else current.finished_at,
                output_digest if output_digest is not None else current.output_digest,
                error_summary if error_summary is not None else current.error_summary,
                stage_run_id,
            ),
        )
        self.conn.commit()

    def get_stage_run(self, stage_run_id: str) -> StageRun | None:
        row = self.conn.execute(
            "SELECT * FROM stage_run WHERE stage_run_id=?", (stage_run_id,)
        ).fetchone()
        return self._stage_run_from_row(row) if row is not None else None

    def find_succeeded_stage_run(self, stage_name: str, input_digest: str) -> StageRun | None:
        """The resumability/cache-invalidation check: a prior SUCCEEDED run
        with an identical input_digest means this stage's work is already
        done and can be skipped. Most recent match wins if more than one
        (should not normally happen, but a reprocessed stage_name/digest
        pair is not itself an error)."""
        row = self.conn.execute(
            "SELECT * FROM stage_run WHERE stage_name=? AND input_digest=?"
            " AND status=? ORDER BY started_at DESC LIMIT 1",
            (stage_name, input_digest, StageStatus.SUCCEEDED.value),
        ).fetchone()
        return self._stage_run_from_row(row) if row is not None else None

    def list_stage_runs(self, run_id: str) -> list[StageRun]:
        cur = self.conn.execute(
            "SELECT * FROM stage_run WHERE run_id=? ORDER BY started_at", (run_id,)
        )
        return [self._stage_run_from_row(r) for r in cur.fetchall()]

    # ---- scoring evidence (ablation cache) ---------------------------

    def add_scoring_evidence(self, rows: Sequence[tuple[str, str, float, str, str, str, str, str]]) -> int:
        """Bulk-insert captured evidence vectors.

        `executemany` and a positional tuple rather than a model per row: a
        single RI resolve captures tens of thousands of pairs, and the point
        of the cache is that writing it is cheaper than recomputing it.
        """
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT INTO scoring_evidence(novel_id, run_tag, chapter, mention_id,"
            " surface, candidate_id, candidate_label, features_json)"
            " VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        return len(rows)

    def clear_scoring_evidence(self, novel_id: str, run_tag: str = "") -> int:
        """Drop a previous capture before re-capturing.

        Without this a second `--capture-evidence` run silently doubles every
        pair, and an ablation re-scoring the table would weight those pairs
        twice.
        """
        cur = self.conn.execute(
            "DELETE FROM scoring_evidence WHERE novel_id=? AND run_tag=?",
            (novel_id, run_tag),
        )
        self.conn.commit()
        return cur.rowcount or 0

    def iter_scoring_evidence(
        self, novel_id: str, run_tag: str = ""
    ) -> Iterator[tuple[float, str, str, str, str, str]]:
        """(chapter, mention_id, surface, candidate_id, candidate_label, features_json)."""
        cur = self.conn.execute(
            "SELECT chapter, mention_id, surface, candidate_id, candidate_label,"
            " features_json FROM scoring_evidence WHERE novel_id=? AND run_tag=?"
            " ORDER BY chapter, id",
            (novel_id, run_tag),
        )
        for row in cur:
            yield (row[0], row[1], row[2], row[3], row[4], row[5])

    def count_scoring_evidence(self, novel_id: str, run_tag: str = "") -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM scoring_evidence WHERE novel_id=? AND run_tag=?",
                (novel_id, run_tag),
            ).fetchone()[0]
        )

    def add_stage_artifact(self, artifact: StageArtifact) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO stage_artifact(artifact_id, stage_run_id, kind,"
            " path_or_ref, content_digest, created_at) VALUES (?,?,?,?,?,?)",
            (
                artifact.artifact_id,
                artifact.stage_run_id,
                artifact.kind,
                artifact.path_or_ref,
                artifact.content_digest,
                artifact.created_at,
            ),
        )
        self.conn.commit()

    def list_stage_artifacts(self, stage_run_id: str) -> list[StageArtifact]:
        cur = self.conn.execute(
            "SELECT * FROM stage_artifact WHERE stage_run_id=? ORDER BY created_at",
            (stage_run_id,),
        )
        return [
            StageArtifact(
                artifact_id=r["artifact_id"],
                stage_run_id=r["stage_run_id"],
                kind=r["kind"],
                path_or_ref=r["path_or_ref"],
                content_digest=r["content_digest"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def _job_from_row(self, row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"],
            novel_id=row["novel_id"],
            kind=row["kind"],
            run_id=row["run_id"],
            status=StageStatus(row["status"]),
            params_json=row["params_json"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            error_summary=row["error_summary"],
        )

    def add_job(self, job: Job) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO job(job_id, novel_id, kind, run_id, status,"
            " params_json, created_at, started_at, finished_at, error_summary)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                job.job_id,
                job.novel_id,
                job.kind,
                job.run_id,
                job.status.value,
                job.params_json,
                job.created_at,
                job.started_at,
                job.finished_at,
                job.error_summary,
            ),
        )
        self.conn.commit()

    def update_job(
        self,
        job_id: str,
        *,
        status: StageStatus | None = None,
        run_id: str | None = None,
        started_at: float | None = None,
        finished_at: float | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Partial update -- `None` args leave the column unchanged, same
        convention as `update_stage_run`."""
        current = self.get_job(job_id)
        if current is None:
            raise KeyError(f"no job {job_id!r}")
        self.conn.execute(
            "UPDATE job SET status=?, run_id=?, started_at=?, finished_at=?,"
            " error_summary=? WHERE job_id=?",
            (
                status.value if status is not None else current.status.value,
                run_id if run_id is not None else current.run_id,
                started_at if started_at is not None else current.started_at,
                finished_at if finished_at is not None else current.finished_at,
                error_summary if error_summary is not None else current.error_summary,
                job_id,
            ),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute("SELECT * FROM job WHERE job_id=?", (job_id,)).fetchone()
        return self._job_from_row(row) if row is not None else None

    def list_jobs(self, novel_id: str) -> list[Job]:
        cur = self.conn.execute(
            "SELECT * FROM job WHERE novel_id=? ORDER BY created_at DESC", (novel_id,)
        )
        return [self._job_from_row(r) for r in cur.fetchall()]

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

    # ---- Studio review items ------------------------------------------

    def _review_item_from_row(self, row: sqlite3.Row) -> ReviewItem:
        candidates = []
        if row["candidates_json"]:
            try:
                candidates = json.loads(row["candidates_json"])
            except json.JSONDecodeError:
                candidates = []
        return ReviewItem(
            id=row["id"],
            novel_id=row["novel_id"],
            chapter=float(row["chapter"]),
            kind=row["kind"],
            message=row["message"],
            candidates=candidates,
            resolved=bool(row["resolved"]),
            resolution=row["resolution"],
            created_at=float(row["created_at"]),
        )

    def add_review_item(self, item: ReviewItem) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO review_item(id, novel_id, chapter, kind, message,"
            " candidates_json, resolved, resolution, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.novel_id,
                item.chapter,
                item.kind,
                item.message,
                json.dumps(item.candidates),
                int(item.resolved),
                item.resolution,
                item.created_at,
            ),
        )
        self.conn.commit()

    def get_review_item(self, item_id: str) -> ReviewItem | None:
        row = self.conn.execute("SELECT * FROM review_item WHERE id=?", (item_id,)).fetchone()
        return self._review_item_from_row(row) if row is not None else None

    def list_review_items(
        self, novel_id: str, *, resolved: bool | None = None
    ) -> list[ReviewItem]:
        sql = "SELECT * FROM review_item WHERE novel_id=?"
        params: list[object] = [novel_id]
        if resolved is not None:
            sql += " AND resolved=?"
            params.append(int(resolved))
        sql += " ORDER BY created_at DESC"
        cur = self.conn.execute(sql, tuple(params))
        return [self._review_item_from_row(r) for r in cur.fetchall()]

    def resolve_review_item(self, item_id: str, resolution: str) -> None:
        self.conn.execute(
            "UPDATE review_item SET resolved=1, resolution=? WHERE id=?",
            (resolution, item_id),
        )
        self.conn.commit()

    def save_screenplay_episode(
        self,
        episode_id: str,
        novel_id: str,
        episode_dict: dict[str, Any] | None = None,
        title: str = "",
        source_chapters: list[float] | None = None,
        episode_json: str | None = None,
    ) -> None:
        if episode_dict is None and episode_json is not None:
            episode_dict = json.loads(episode_json)
        elif episode_dict is None:
            episode_dict = {}
        chapters = source_chapters or episode_dict.get("source_chapters", [])
        self.conn.execute(
            "INSERT OR REPLACE INTO screenplay_episode(id, novel_id, title, source_chapters_json, episode_json, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (
                episode_id,
                novel_id,
                title or episode_dict.get("title", ""),
                json.dumps(chapters),
                json.dumps(episode_dict),
                time.time(),
            ),
        )
        self.conn.commit()

    def get_screenplay_episode(self, episode_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT episode_json FROM screenplay_episode WHERE id=?", (episode_id,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["episode_json"])

    def list_screenplay_episodes(self, novel_id: str) -> list[dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT episode_json FROM screenplay_episode WHERE novel_id=? ORDER BY created_at ASC",
            (novel_id,),
        )
        return [json.loads(r["episode_json"]) for r in cur.fetchall()]

    # ---- Story Bible point-in-time snapshot ----------------------------

    def bible_at(self, novel_id: str, chapter: float) -> StoryBibleSnapshot:
        """Return point-in-time Story Bible snapshot for a given novel and chapter.

        Enforces strict bitemporal filtering: zero future chapter leakage
        (first_chapter / learned_chapter <= chapter). Facts retracted prior to
        or at chapter are excluded.
        """
        characters: dict[str, CharacterBibleEntry] = {}
        locations: dict[str, LocationBibleEntry] = {}

        # 1. Characters: query selves introduced on or before this chapter
        cur = self.conn.execute(
            "SELECT id, canonical_label, notes, kind FROM self_entity "
            "WHERE novel_id=? AND first_chapter <= ? AND (kind IS NULL OR kind IN ('SELF', 'PERSON'))",
            (novel_id, chapter),
        )
        for r in cur.fetchall():
            self_id = r["id"]
            canonical_label = r["canonical_label"]

            # Active persona: find the latest persona binding learned on or before this chapter
            spb_row = self.conn.execute(
                "SELECT persona_id FROM self_persona_binding "
                "WHERE self_id=? AND learned_chapter <= ? AND truth_status != 'FALSE' "
                "ORDER BY learned_chapter DESC, learned_offset DESC LIMIT 1",
                (self_id, chapter),
            ).fetchone()
            active_persona_id = spb_row["persona_id"] if spb_row else f"{self_id}:default"

            # Aliases learned on or before this chapter and not retracted
            alias_rows = self.conn.execute(
                "SELECT alias FROM alias_binding "
                "WHERE novel_id=? AND target_id IN (?, ?) AND learned_chapter <= ? "
                "AND ((retracted_chapter IS NULL AND truth_status != 'FALSE') OR retracted_chapter > ?)",
                (novel_id, self_id, active_persona_id, chapter, chapter),
            ).fetchall()
            aliases = list({a["alias"] for a in alias_rows if a["alias"] != canonical_label})

            # Attributes learned on or before this chapter and not retracted
            # `persona_at` (pipeline) is the accessor the reader pass and every persona writer use, and without a binding
            # it answers `<self>:body1`. This query asked only for `<self>:default`, so every look the reader extracted
            # (LotM: Klein's brown eyes, Daly's emerald eyes) never reached the bible and each character's attributes
            # were empty. When the active persona is the unbound default, the `:body1` persona is read too.
            holders = [self_id, active_persona_id]
            if active_persona_id == f"{self_id}:default":
                holders.append(f"{self_id}:body1")
            marks = ",".join("?" for _ in holders)
            attr_rows = self.conn.execute(
                "SELECT key, value FROM attribute "
                f"WHERE novel_id=? AND target_id IN ({marks}) AND learned_chapter <= ? "
                "AND ((retracted_chapter IS NULL AND truth_status != 'FALSE') OR retracted_chapter > ?) "
                "ORDER BY learned_chapter ASC, learned_offset ASC",
                (novel_id, *holders, chapter, chapter),
            ).fetchall()
            attrs: dict[str, str] = {}
            for a in attr_rows:
                attrs[a["key"]] = a["value"]

            active_outfit = attrs.get("outfit") or attrs.get("active_outfit")
            voice_id = attrs.get("voice_id") or attrs.get("voice_profile")

            characters[self_id] = CharacterBibleEntry(
                self_id=self_id,
                canonical_label=canonical_label,
                active_persona_id=active_persona_id,
                active_outfit=active_outfit,
                aliases=aliases,
                voice_id=voice_id,
                attributes=attrs,
            )

        # 2. Locations: query location entities introduced on or before this chapter
        loc_rows = self.conn.execute(
            "SELECT id, canonical_label, notes FROM self_entity "
            "WHERE novel_id=? AND first_chapter <= ? AND kind = 'LOCATION'",
            (novel_id, chapter),
        ).fetchall()
        for lr in loc_rows:
            loc_id = lr["id"]
            canonical_name = lr["canonical_label"]
            desc = lr["notes"] or ""

            loc_attrs_rows = self.conn.execute(
                "SELECT key, value FROM attribute "
                "WHERE novel_id=? AND target_id=? AND learned_chapter <= ? "
                "AND ((retracted_chapter IS NULL AND truth_status != 'FALSE') OR retracted_chapter > ?) "
                "ORDER BY learned_chapter ASC, learned_offset ASC",
                (novel_id, loc_id, chapter, chapter),
            ).fetchall()
            loc_attrs = {a["key"]: a["value"] for a in loc_attrs_rows}
            master_plate = loc_attrs.get("master_plate_path") or loc_attrs.get("plate_path")
            ambience = loc_attrs.get("ambience_sound") or loc_attrs.get("ambience")
            if not desc and "description" in loc_attrs:
                desc = loc_attrs["description"]

            locations[loc_id] = LocationBibleEntry(
                location_id=loc_id,
                canonical_name=canonical_name,
                description=desc,
                master_plate_path=master_plate,
                ambience_sound=ambience,
            )

        # 3. Relationships: active relations between characters learned <= chapter and not retracted
        rel_rows = self.conn.execute(
            "SELECT src_self, dst_self, type FROM relation "
            "WHERE novel_id=? AND learned_chapter <= ? "
            "AND ((retracted_chapter IS NULL AND truth_status != 'FALSE') OR retracted_chapter > ?)",
            (novel_id, chapter, chapter),
        ).fetchall()
        relationships: dict[str, dict[str, str]] = {}
        for r in rel_rows:
            src = r["src_self"]
            dst = r["dst_self"]
            rel_type = r["type"]
            if src not in relationships:
                relationships[src] = {}
            relationships[src][dst] = rel_type

        return StoryBibleSnapshot(
            novel_id=novel_id,
            chapter=chapter,
            characters=characters,
            locations=locations,
            relationships=relationships,
        )

    def add_bible_lock(self, novel_id: str, lock: dict) -> dict:  # type: ignore[type-arg]
        """Persist the next locked bible version and return it. Versions count up from 1 per novel and are never reused."""
        row = self.conn.execute("SELECT COALESCE(MAX(version), 0) FROM bible_lock WHERE novel_id=?", (novel_id,)).fetchone()
        version = int(row[0]) + 1
        self.conn.execute(
            "INSERT INTO bible_lock(novel_id, version, created_at, note, pipeline_version, digest,"
            " chapter_digests_json, counts_json) VALUES (?,?,?,?,?,?,?,?)",
            (novel_id, version, lock["created_at"], lock.get("note", ""), lock.get("pipeline_version", ""),
             lock["digest"], json.dumps(lock.get("chapter_digests", {})), json.dumps(lock.get("counts", {}))),
        )
        self.conn.commit()
        return {**lock, "version": version}

    def set_span_emotions(self, novel_id: str, chapter: float, rows: dict[str, tuple[str, int]]) -> None:
        """Replace one chapter's line emotions: span id -> (emotion, intensity 1-3)."""
        self.conn.execute("DELETE FROM span_emotion WHERE novel_id=? AND chapter=?", (novel_id, chapter))
        self.conn.executemany(
            "INSERT INTO span_emotion(novel_id, span_id, chapter, emotion, intensity) VALUES (?,?,?,?,?)",
            [(novel_id, span_id, chapter, emotion, intensity) for span_id, (emotion, intensity) in rows.items()],
        )
        self.conn.commit()

    def span_emotions(self, novel_id: str, chapter: float | None = None) -> dict[str, tuple[str, int]]:
        sql, args = "SELECT span_id, emotion, intensity FROM span_emotion WHERE novel_id=?", [novel_id]
        if chapter is not None:
            sql, args = sql + " AND chapter=?", [novel_id, chapter]
        return {r["span_id"]: (r["emotion"], int(r["intensity"])) for r in self.conn.execute(sql, args)}

    def list_bible_locks(self, novel_id: str) -> list[dict]:  # type: ignore[type-arg]
        rows = self.conn.execute(
            "SELECT * FROM bible_lock WHERE novel_id=? ORDER BY version", (novel_id,)
        ).fetchall()
        return [
            {
                "version": r["version"], "created_at": r["created_at"], "note": r["note"],
                "pipeline_version": r["pipeline_version"], "digest": r["digest"],
                "chapter_digests": json.loads(r["chapter_digests_json"]), "counts": json.loads(r["counts_json"]),
            }
            for r in rows
        ]

    def add_location_plate(self, plate: LocationPlate) -> None:
        """Persist a master environmental location plate."""
        self.conn.execute(
            "INSERT OR REPLACE INTO location_plate "
            "(id, novel_id, location_id, title, source_url, angle, time_of_day, selected, is_approved, found_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plate.id,
                plate.novel_id,
                plate.location_id,
                plate.title,
                plate.source_url,
                plate.angle,
                plate.time_of_day,
                int(plate.selected),
                int(plate.is_approved),
                plate.found_at,
            ),
        )
        self.conn.commit()

    def list_location_plates(self, novel_id: str, location_id: str | None = None) -> list[LocationPlate]:
        """List environmental plates for a location or novel."""
        if location_id:
            rows = self.conn.execute(
                "SELECT * FROM location_plate WHERE novel_id=? AND location_id=? ORDER BY found_at DESC",
                (novel_id, location_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM location_plate WHERE novel_id=? ORDER BY found_at DESC",
                (novel_id,),
            ).fetchall()
        return [
            LocationPlate(
                id=r["id"],
                novel_id=r["novel_id"],
                location_id=r["location_id"],
                title=r["title"],
                source_url=r["source_url"],
                angle=r["angle"],
                time_of_day=r["time_of_day"],
                selected=bool(r["selected"]),
                is_approved=bool(r["is_approved"]),
                found_at=r["found_at"],
            )
            for r in rows
        ]

    def add_persona_version(self, pv: PersonaVersion) -> None:
        """Persist a versioned persona visual state across serial chapters."""
        self.conn.execute(
            "INSERT OR REPLACE INTO persona_version "
            "(id, novel_id, self_id, persona_id, chapter_introduced, shift_reason, turnaround_sheet_path, expression_sheet_path, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pv.id,
                pv.novel_id,
                pv.self_id,
                pv.persona_id,
                pv.chapter_introduced,
                pv.shift_reason,
                pv.turnaround_sheet_path,
                pv.expression_sheet_path,
                int(pv.is_active),
            ),
        )
        self.conn.commit()

    def list_persona_versions(self, novel_id: str, self_id: str | None = None) -> list[PersonaVersion]:
        """List persona versions for a character across serial chapters."""
        if self_id:
            rows = self.conn.execute(
                "SELECT * FROM persona_version WHERE novel_id=? AND self_id=? ORDER BY chapter_introduced ASC",
                (novel_id, self_id),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM persona_version WHERE novel_id=? ORDER BY chapter_introduced ASC",
                (novel_id,),
            ).fetchall()
        return [
            PersonaVersion(
                id=r["id"],
                novel_id=r["novel_id"],
                self_id=r["self_id"],
                persona_id=r["persona_id"],
                chapter_introduced=r["chapter_introduced"],
                shift_reason=r["shift_reason"],
                turnaround_sheet_path=r["turnaround_sheet_path"],
                expression_sheet_path=r["expression_sheet_path"],
                is_active=bool(r["is_active"]),
            )
            for r in rows
        ]

    def add_voice_profile(self, vp: VoiceProfile) -> None:
        """Persist a character's assigned voice profile."""
        self.conn.execute(
            "INSERT OR REPLACE INTO voice_profile "
            "(id, novel_id, self_id, speaker_id, gender, age_group, pitch, speed, accent) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                vp.id,
                vp.novel_id,
                vp.self_id,
                vp.speaker_id,
                vp.gender,
                vp.age_group,
                vp.pitch,
                vp.speed,
                vp.accent,
            ),
        )
        self.conn.commit()

    def get_voice_profile(self, novel_id: str, self_id: str) -> VoiceProfile | None:
        """Fetch the voice profile for a character."""
        row = self.conn.execute(
            "SELECT * FROM voice_profile WHERE novel_id=? AND self_id=? LIMIT 1",
            (novel_id, self_id),
        ).fetchone()
        if not row:
            return None
        return VoiceProfile(
            id=row["id"],
            novel_id=row["novel_id"],
            self_id=row["self_id"],
            speaker_id=row["speaker_id"],
            gender=row["gender"],
            age_group=row["age_group"],
            pitch=row["pitch"],
            speed=row["speed"],
            accent=row["accent"],
        )

