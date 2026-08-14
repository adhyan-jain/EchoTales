"""One-off: point existing data/references_v2/ sheets at their personas.

The prior session generated real reference PNGs to disk but never wrote the
`reference_image_path` attribute that `render/panels.py` reads via
`persona.reference_gen.reference_path_for` -- so every render since has
reported `conditioned_panels=0` even though the sheets exist. This writes
the missing markers directly rather than re-running (expensive) generation,
since the images on disk are already the ones the author wants used.

Usage: uv run python scripts/backfill_reference_markers.py <db_path> <novel_id>
"""
from __future__ import annotations

import sys
from pathlib import Path

from echotales.core.enums import AssertedBy, OBSERVER_READER, TargetKind, TruthStatus
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import REFERENCE_PATH_KEY


def main(db_path: str, novel_id: str) -> None:
    store = Store(db_path)
    ref_dir = Path("data/references_v2") / novel_id
    if not ref_dir.is_dir():
        raise SystemExit(f"no reference dir at {ref_dir}")

    written = skipped = 0
    for png in sorted(ref_dir.glob("*.png")):
        stem = png.stem
        prefix = f"{novel_id}_"
        if not stem.startswith(prefix):
            print(f"skip (unexpected name): {png.name}")
            skipped += 1
            continue
        persona_id = f"{novel_id}:" + stem[len(prefix):].replace("_", ":")

        persona = store.get_persona(persona_id)
        if persona is None:
            print(f"skip (no such persona in {db_path}): {persona_id}")
            skipped += 1
            continue

        pos = persona.first_attested_pos
        store.add_attribute(
            novel_id,
            Attribute(
                target_kind=TargetKind.PERSONA,
                target_id=persona_id,
                key=REFERENCE_PATH_KEY,
                value=str(png.resolve()),
                interval=FuzzyInterval.open_ended(pos.chapter, last_evidence=pos.chapter),
                learned_at_pos=pos,
                observer_id=OBSERVER_READER,
                asserted_by=AssertedBy.INFERENCE,
                truth_status=TruthStatus.INFERRED,
            ),
        )
        print(f"wrote marker: {persona_id} -> {png}")
        written += 1

    store.conn.commit()
    print(f"\n{written} written, {skipped} skipped")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <db_path> <novel_id>")
    main(sys.argv[1], sys.argv[2])
