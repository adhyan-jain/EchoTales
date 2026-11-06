"""`review_gate.voice_refusal`: a real voice render needs a current build, a locked canon and no unapplied decisions.

Audit 2026-10-31 (B2, B5): `render` was guarded, `voice` was not, so a book could be voiced from unlocked edits and from
review decisions still sitting in the corrections log.
"""

from __future__ import annotations

from echotales.core.store import Store
from echotales.pipeline import review_gate as rg


class _Log:
    def __init__(self, pending: int) -> None:
        self._pending = pending

    def summary(self) -> dict[str, object]:
        return {"pending_actionable": self._pending}


def _store() -> Store:
    store = Store(":memory:")
    store.add_novel("n", "N", "x.epub", "generic")
    return store


def test_stub_is_never_refused() -> None:
    assert rg.voice_refusal(_store(), "n", "stub") is None


def test_real_engine_is_refused_without_a_current_locked_build() -> None:
    # An unstamped database is what `data/db/` holds today, and what the Studio already refuses to render.
    assert rg.voice_refusal(_store(), "n", "chatterbox")


def test_unapplied_review_decisions_block_a_real_voice_render(monkeypatch) -> None:
    monkeypatch.setattr(rg, "staleness_reason", lambda *_: None)
    monkeypatch.setattr(rg, "unlocked_reason", lambda *_: None)
    reason = rg.voice_refusal(_store(), "n", "chatterbox", _Log(pending=3))
    assert reason and "3 review decision" in reason
    assert rg.voice_refusal(_store(), "n", "chatterbox", _Log(pending=0)) is None



def test_ears_m4b_needs_allow_noncommercial() -> None:
    """EARS is CC BY-NC 4.0: binding its voices into an M4B must be an explicit choice."""
    from echotales.pipeline.voice.bank import noncommercial_refusal

    assert noncommercial_refusal("ears", m4b=True, allowed=False)
    assert noncommercial_refusal("ears", m4b=True, allowed=True) is None
    assert noncommercial_refusal("ears", m4b=False, allowed=False) is None
    assert noncommercial_refusal("vctk", m4b=True, allowed=False) is None
