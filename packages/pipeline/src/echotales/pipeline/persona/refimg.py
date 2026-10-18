"""Orchestration for reference-image candidate search and selection.

Thin glue between `refimg_search.py` (finds candidates) and
`core/store.py`'s `ref_image_candidate` / `ref_image_selection_log` tables
(persists them and the audit trail). This is the module the CLI
(`persona refimg ...`) and `commands.py::cmd_persona` call into.

Everything here is opt-in and backend-only: nothing in this module, or
anywhere else in the pipeline as of this writing, reads `ref_image_candidate`
to condition image generation. See `core/models.py::RefImageCandidate`.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import Prominence
from echotales.core.models import RefImageCandidate, RefImageSelectionEvent
from echotales.core.store import Store


@dataclass
class SearchResult:
    self_id: str
    character_label: str
    query: str
    candidates: list[RefImageCandidate] = field(default_factory=list)
    error: str = ""


def eligible_characters(store: Store, novel_id: str) -> list:
    """PRINCIPAL/RECURRING characters, most-mentioned first.

    Same eligibility rule as `persona/reference_gen.py`'s reference-sheet
    generation (`appearance_extract.eligible_prominence`) -- an incidental
    walk-on gets no reference-image search either, for the same reason it
    gets no reference sheet: there is nothing to search *for*.
    """
    from echotales.pipeline.resolve.appearance_extract import eligible_prominence

    people = [e for e in store.all_selves(novel_id) if e.kind.is_person]
    ranked = sorted(people, key=lambda e: -store.mention_count_for(novel_id, e.id))
    return [
        e for e in ranked if eligible_prominence(store, novel_id, e) != Prominence.INCIDENTAL
    ]


def search_and_store(
    store: Store,
    novel_id: str,
    novel_title: str,
    self_id: str,
    *,
    backend=None,
    max_results: int = 5,
) -> SearchResult:
    """Search for one character and persist every candidate found.

    Persisted candidates are always `selected=False` -- see module
    docstring. Calling this twice for the same character does not
    duplicate rows (candidate ids are content-hashed by URL) but does not
    deduplicate against a *different* backend's hit for the same image
    either; that is an acceptable gap for a review-queue mechanism, not a
    correctness bug.
    """
    from echotales.pipeline.persona.refimg_search import search_candidates

    entity = store.get_self(self_id)
    label = entity.canonical_label if entity else self_id
    try:
        candidates = search_candidates(
            novel_id, novel_title, self_id, label, backend=backend, max_results=max_results
        )
    except Exception as exc:
        return SearchResult(self_id=self_id, character_label=label, query="", error=str(exc))

    for c in candidates:
        store.add_ref_image_candidate(c)

    query = candidates[0].query if candidates else ""
    return SearchResult(self_id=self_id, character_label=label, query=query, candidates=candidates)


def search_batch(
    store: Store,
    novel_id: str,
    novel_title: str,
    *,
    self_ids: list[str] | None = None,
    backend=None,
    max_results: int = 5,
) -> list[SearchResult]:
    """Search for several characters in one call -- the CLI's `search` command.

    `self_ids=None` runs every PRINCIPAL/RECURRING character in the novel,
    which is the whole-cast batch path; passing explicit ids is how a
    caller (or a test) targets just one or two without a full sweep.
    """
    targets = self_ids or [e.id for e in eligible_characters(store, novel_id)]
    return [
        search_and_store(store, novel_id, novel_title, sid, backend=backend, max_results=max_results)
        for sid in targets
    ]


def list_candidates(store: Store, novel_id: str, self_id: str) -> list[RefImageCandidate]:
    return store.list_ref_image_candidates(novel_id, self_id)


def select_candidate(
    store: Store, novel_id: str, self_id: str, candidate_id: str, *, actor: str = "user", note: str = ""
) -> RefImageCandidate:
    """Manual override: mark one already-found candidate as selected.

    Selection is *not* propagated anywhere else in the pipeline -- it only
    updates this table and appends to the log. Wiring a selected candidate
    into generation conditioning is a deliberately separate, not-yet-built
    step (see module docstring).
    """
    store.select_ref_image_candidate(novel_id, self_id, candidate_id, actor=actor, note=note)
    candidate = store.get_ref_image_candidate(candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)
    return candidate


def register_user_image(
    store: Store, novel_id: str, self_id: str, image_path: str, *, actor: str = "user", note: str = ""
) -> RefImageCandidate:
    """User-override path: register and select a locally supplied image."""
    entity = store.get_self(self_id)
    label = entity.canonical_label if entity else self_id
    return store.register_user_ref_image(
        novel_id, self_id, label, image_path, actor=actor, note=note
    )


def register_sheet_candidate(
    store: Store,
    novel_id: str,
    self_id: str,
    persona_id: str,
    image_path: Path | str,
    character_label: str = "",
    *,
    selected: bool = False,
    actor: str = "pipeline",
    note: str = "generated sheet",
) -> RefImageCandidate:
    """Register a generated reference sheet as a RefImageCandidate.

    Content-addressed: id includes the first 10 hex digits of the file's sha1.
    If a row with this id already exists, it is returned without overwriting
    existing selection state.
    """
    path = Path(image_path).resolve()
    file_bytes = path.read_bytes()
    file_sha = hashlib.sha1(file_bytes).hexdigest()[:10]
    candidate_id = f"{persona_id}:sheet:{file_sha}"

    existing = store.get_ref_image_candidate(candidate_id)
    if existing is not None:
        return existing

    if not character_label:
        entity = store.get_self(self_id)
        character_label = entity.canonical_label if entity else self_id

    candidate = RefImageCandidate(
        id=candidate_id,
        novel_id=novel_id,
        self_id=self_id,
        character_label=character_label,
        source_url=f"file://{path}",
        thumbnail_url="",
        title=f"{character_label} reference sheet",
        source_page="",
        query="",
        backend="generated-sheet",
        found_at=time.time(),
        user_uploaded=False,
        selected=selected,
        persona_id=persona_id,
        quality_score=None,
        role="sheet",
    )
    store.add_ref_image_candidate(candidate)
    if selected:
        store.select_ref_image_candidate(novel_id, self_id, candidate_id, actor=actor, note=note)
    return candidate


def approved_reference_path(store: Store, novel_id: str, persona_id: str) -> Path | None:
    """The human-approved reference image path for this persona, if valid on disk.

    Returns a path only if a selected=1 candidate exists for this persona_id,
    its source_url is a local file that exists, and its file contents match
    the candidate's sha1 digest (preventing stale approvals after regeneration).
    """
    cur = store.conn.execute(
        "SELECT * FROM ref_image_candidate WHERE novel_id=? AND persona_id=? AND selected=1"
        " ORDER BY found_at DESC",
        (novel_id, persona_id),
    )
    for row in cur.fetchall():
        from echotales.core.store import _refimg_from_row

        candidate = _refimg_from_row(row)
        if not candidate.source_url.startswith("file://"):
            continue
        path = Path(candidate.source_url.removeprefix("file://"))
        if not path.is_file():
            continue
        if ":sheet:" in candidate.id:
            expected_sha = candidate.id.rsplit(":sheet:", 1)[-1]
            try:
                actual_sha = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
                if actual_sha != expected_sha:
                    continue
            except OSError:
                continue
        return path
    return None


def approve_sheet(
    store: Store,
    novel_id: str,
    self_id: str,
    candidate_id: str,
    *,
    actor: str = "user",
    note: str = "",
) -> RefImageCandidate:
    """Approve a character reference sheet candidate."""
    store.select_ref_image_candidate(novel_id, self_id, candidate_id, actor=actor, note=note)
    candidate = store.get_ref_image_candidate(candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)
    return candidate


def reject_sheet(
    store: Store,
    novel_id: str,
    self_id: str,
    candidate_id: str,
    *,
    actor: str = "user",
    note: str = "",
) -> RefImageCandidate:
    """Reject (unselect) a character reference sheet candidate."""
    row = store.conn.execute(
        "SELECT id, persona_id FROM ref_image_candidate WHERE id=? AND novel_id=? AND self_id=?",
        (candidate_id, novel_id, self_id),
    ).fetchone()
    if row is None:
        raise KeyError(f"no ref image candidate {candidate_id!r} for self {self_id!r}")
    cand_persona_id = row["persona_id"] if "persona_id" in row.keys() else None
    with store.transaction():
        store.conn.execute(
            "UPDATE ref_image_candidate SET selected=0 WHERE id=?", (candidate_id,)
        )
    store.log_ref_image_event(
        RefImageSelectionEvent(
            novel_id=novel_id,
            self_id=self_id,
            candidate_id=candidate_id,
            action="reject",
            actor=actor,
            note=note,
            at=time.time(),
            persona_id=cand_persona_id,
        )
    )
    candidate = store.get_ref_image_candidate(candidate_id)
    if candidate is None:
        raise KeyError(candidate_id)
    return candidate


def list_sheets(
    store: Store,
    novel_id: str,
    self_id: str,
    *,
    persona_id: str | None = None,
) -> list[RefImageCandidate]:
    """List reference sheet candidates for a character (or specific persona/body)."""
    return store.list_ref_image_candidates(
        novel_id, self_id, persona_id=persona_id, role="sheet"
    )
