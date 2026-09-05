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

from dataclasses import dataclass, field

from echotales.core.enums import Prominence
from echotales.core.models import RefImageCandidate
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
