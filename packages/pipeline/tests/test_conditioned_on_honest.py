"""B3 (CHIMERA defect backlog): `conditioned_on` and the conditioned-panel counter reflect what the request contains.

Panel generation is called with `reference_images=[]` (IP-Adapter was removed on purpose), but the render loop still
listed every character that HAS a reference sheet in `conditioned_on` and counted the panel as conditioned, so the
manifest claimed conditioning that never reached the generation call. Now both are derived from the request that was
actually sent. Synthetic strings only; stub engine.
"""

from __future__ import annotations

import json

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AssertedBy,
    BlockType,
    ReferenceMode,
    SpanType,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import Attribute, Block, Chapter, DiscoursePosition, Mention, Self
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import REFERENCE_PATH_KEY
from echotales.pipeline.persona.split import BodyEpoch, write_epochs
from echotales.pipeline.render.panels import character_looks, render_panels


def _store_with_a_reference_sheet(tmp_path) -> tuple[Store, object]:
    store = Store(str(tmp_path / "t.db"))
    store.add_novel("t", "T", "x.epub", "generic")
    store.add_chapter(Chapter(novel_id="t", number=1.0, title="T", source_href="a.html", blocks=[
        Block(index=0, block_type=BlockType.HEADING, text="Chapter 1"),
        Block(index=1, block_type=BlockType.PROSE, text="Zorrin Vale stood."),
    ]))
    store.add_self(Self(id="t:self1", novel_id="t", canonical_label="Zorrin Vale",
                        first_attested_pos=DiscoursePosition(chapter=1.0, offset=0), kind=TargetKind.SELF))
    store.add_mentions([Mention(id="m1", novel_id="t", segment_id="s", chapter=1.0, offset=0, block_index=1,
                                text="Zorrin Vale", alias_type=AliasType.RIGID_NAME,
                                span_type=SpanType.NARRATION_ACTION, reference_mode=ReferenceMode.PRESENT,
                                target_kind=TargetKind.SELF, target_id="t:self1")])
    write_epochs(store, "t", store.get_self("t:self1"),
                 [BodyEpoch(index=0, persona_id="t:self1:body1", body_label="Zorrin Vale", from_pos=1.0, to_pos=None,
                            cause="", evidence="")], observer_id=OBSERVER_READER)
    sheet = tmp_path / "sheet.png"
    sheet.write_bytes(b"")
    store.add_attribute("t", Attribute(
        target_kind=TargetKind.PERSONA, target_id="t:self1:body1", key=REFERENCE_PATH_KEY, value=str(sheet),
        interval=FuzzyInterval.open_ended(1.0), learned_at_pos=DiscoursePosition(chapter=1.0, offset=0),
        observer_id=OBSERVER_READER, asserted_by=AssertedBy.INFERENCE, truth_status=TruthStatus.INFERRED))
    store.conn.commit()
    return store, sheet


def test_manifest_claims_no_conditioning_when_no_reference_image_is_sent(tmp_path) -> None:
    store, sheet = _store_with_a_reference_sheet(tmp_path)
    looks = character_looks(store, "t:self1", novel_id="t", chapter=1.0)
    assert looks is not None and looks[2] == sheet          # a sheet exists, so the old code would have listed it
    report = render_panels("t", store, out_dir=tmp_path / "panels", version="v1_honest")
    manifest = (tmp_path / "panels" / "ch1" / "v1_honest" / "manifest.jsonl").read_text().splitlines()
    rows = [json.loads(x) for x in manifest]
    assert rows
    assert all(r["conditioned_on"] == [] for r in rows)
    assert report.conditioned_panels == 0 and report.prompt_only_panels >= 1
