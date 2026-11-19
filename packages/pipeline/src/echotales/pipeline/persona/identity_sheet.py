"""A reference sheet image per character per body, drawn from the locked identity and approved in the Studio.

Why this and not a new mechanism: `persona/refimg.py` already registers sheet candidates per persona and
`assets/approval.py`/the Studio already approve them. What was missing is that the picture and the panels say the same
words. The sheet is generated from the persona's locked identity sentence (`persona/identity_lock.py`), the sentence and the
lock are stored with the candidate, and `identity_lock.approved_sheet_lock` reads them back once the candidate is approved,
so approving a sheet in the Studio is what fixes hair, eyes, build and outfit for every later panel of that body. Z-Image
Turbo has no reference-image input, so words are the only identity channel there is.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from echotales.pipeline.persona import identity_lock as il
from echotales.pipeline.persona import refimg

log = logging.getLogger(__name__)

_FRAMING = (
    "Full-body character reference: a single person standing straight, facing the viewer, arms relaxed, on a plain light "
    "grey background with nothing else in the frame."
)


def sheet_description(store: Any, candidate_id: str) -> str:
    """The identity sentence this sheet was drawn from, or '' for a sheet that was not made from a lock."""
    row = store.conn.execute("SELECT payload_json FROM derived_artifact WHERE id=?", (f"identity_sheet_text:{candidate_id}",)).fetchone()
    return json.loads(row["payload_json"]) if row is not None else ""


def _position_of(store: Any, self_id: str, persona_id: str) -> float:
    from echotales.pipeline.persona.split import bodies_of

    for pid, interval in bodies_of(store, self_id):
        if pid == persona_id:
            return float(interval.from_lb)
    entity = store.get_self(self_id)
    return float(entity.first_attested_pos.chapter) if entity is not None else 1.0


def generate_sheet(
    store: Any, novel_id: str, self_id: str, *, persona_id: str | None = None, out_dir: Path, draw: Any, model_key: str,
    seed: int = 0,
) -> Any:
    """Draw one sheet for this body and register it, unapproved, with the words it was drawn from.

    `draw` is `render/compiled_route.generate_compiled_batch`, or a stand-in. Calling again draws another picture of the same
    words under a new seed, so the owner can pick the best face without the description moving."""
    from echotales.pipeline.persona.genre import style_lead
    from echotales.pipeline.persona.split import persona_at
    from echotales.pipeline.render.compiler import character_brief, identity_sentence
    from echotales.pipeline.render.panels import PanelImageRequest

    persona_id = persona_id or persona_at(store, self_id, None)
    brief = character_brief(store, novel_id, self_id, _position_of(store, self_id, persona_id))
    sentence = identity_sentence(brief)
    existing = len(refimg.list_sheets(store, novel_id, self_id, persona_id=persona_id))
    seed = seed or int(hashlib.sha256(f"{persona_id}:{existing}".encode()).hexdigest()[:8], 16)
    safe = persona_id.replace(":", "_")
    out = Path(out_dir) / f"{safe}_{existing + 1}.png"
    prompt = f"{style_lead(novel_id)} {_FRAMING} {sentence}"
    request = PanelImageRequest(prompt=prompt, out_path=out, width=832, height=1216, seed=seed)
    failed = draw([request], [[("style", style_lead(novel_id)), ("framing", _FRAMING), (f"character:{brief.name}", sentence)]],
                  model_key, greyscale=False)
    if failed or not out.exists():
        raise RuntimeError(f"the sheet for {brief.name} ({persona_id}) was not drawn")
    cand = refimg.register_sheet_candidate(store, novel_id, self_id, persona_id, out, brief.name)
    lock = brief.locked
    store.record_artifact(f"identity_sheet:{cand.id}", il.TIER, [], "", lock.to_json())  # type: ignore[union-attr]
    store.record_artifact(f"identity_sheet_text:{cand.id}", il.TIER, [], "", json.dumps(sentence))
    store.conn.commit()
    return cand


def generate_sheets(
    store: Any, novel_id: str, *, self_ids: list[str] | None = None, out_dir: Path, draw: Any, model_key: str,
) -> list[Any]:
    """One sheet for every body of every listed character (default: the characters that earn a sheet,
    `refimg.eligible_characters`)."""
    from echotales.pipeline.persona.split import bodies_of

    ids = self_ids if self_ids is not None else [e.id for e in refimg.eligible_characters(store, novel_id)]
    made = []
    for sid in ids:
        bodies = [pid for pid, _iv in bodies_of(store, sid)] or [None]
        for pid in bodies:
            made.append(generate_sheet(store, novel_id, sid, persona_id=pid, out_dir=out_dir, draw=draw, model_key=model_key))
    return made
