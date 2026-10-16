"""B1-only end-to-end check on the REAL production render path with the stub engine (CPU, no LLM, no GPU).

Plan section 6 asks for an end-to-end stub render. T is not wired into production, so only B1 can be run
end to end; this script documents what today's `render_panels` puts into the emitted panel prompt for a
constructed store, and scores it with the harness oracle rules applied to prompt strings.

    ECHOTALES_LLM_MODE=stub .venv/bin/python docs/research/technical_contribution_probes/e2e_b1_stub_render.py

The database lives in a temporary directory; nothing is written under data/.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ECHOTALES_LLM_MODE", "stub")

from echotales.core.enums import (  # noqa: E402
    OBSERVER_READER, AliasType, BlockType, ReferenceMode, SpanType, TargetKind,
)
from echotales.core.interval import FuzzyInterval  # noqa: E402
from echotales.core.models import (  # noqa: E402
    Attribute, Block, Chapter, DiscoursePosition, Mention, Self,
)
from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.persona.split import BodyEpoch, write_epochs  # noqa: E402
from echotales.pipeline.render.panels import render_panels  # noqa: E402

DP = lambda c: DiscoursePosition(chapter=float(c))  # noqa: E731
OPEN = lambda a: FuzzyInterval.open_ended(a, last_evidence=1e6)  # noqa: E731

#: token -> (description, oracle admissibility at p=5, k=5, o=READER)
FACTS = {
    "teal": ("hair_color, learned ch1", True),
    "zigzag scar": ("distinguishing_features true from ch3 but disclosed ch100 (retrospective reveal)", False),
    "crimson": ("eye_color, learned ch1, retracted ch50 (belief still held at k=5)", True),
}


def build(tmp: Path) -> Store:
    s = Store(str(tmp / "e2e.db"))
    s.add_novel("t", "T", "x.epub", "generic")
    s.add_chapter(Chapter(novel_id="t", number=5.0, title="T", source_href="a.html", blocks=[
        Block(index=0, block_type=BlockType.HEADING, text="Chapter 5"),
        Block(index=1, block_type=BlockType.PROSE, text="Mo Wen smiled and said, \"I will not yield,\" his face calm as he looked straight at them.")]))
    ent = Self(id="t:s1", novel_id="t", canonical_label="Mo Wen", first_attested_pos=DP(1), kind=TargetKind.SELF)
    s.add_self(ent)
    write_epochs(s, "t", ent, [BodyEpoch(index=1, persona_id="t:p1", body_label="body", from_pos=1.0, to_pos=None,
                                         cause="birth", evidence="")], observer_id=OBSERVER_READER)
    s.add_mentions([Mention(id="m1", novel_id="t", segment_id="s", chapter=5.0, offset=0, block_index=1,
                            text="Mo Wen", alias_type=AliasType.RIGID_NAME, span_type=SpanType.NARRATION_ACTION,
                            reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id="t:s1")])

    def attr(key, val, start, learned, ret=None):
        s.add_attribute("t", Attribute(target_kind=TargetKind.PERSONA, target_id="t:p1", key=key, value=val,
                                       interval=OPEN(start), learned_at_pos=DP(learned), observer_id=OBSERVER_READER,
                                       retracted_at=DP(ret) if ret else None))

    attr("hair_color", "teal", 1, 1)
    attr("distinguishing_features", "zigzag scar", 3, 100)
    attr("eye_color", "crimson", 1, 1, ret=50)
    s.conn.commit()
    return s


def prompts(report_dir: Path) -> list[str]:
    out = []
    for line in (report_dir / "manifest.jsonl").read_text().splitlines():
        row = json.loads(line)
        out.append(" | ".join(str(v) for k, v in row.items() if "prompt" in k.lower()))
    return out


def main() -> int:
    results = {}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        s = build(tmp)
        for obs in (OBSERVER_READER, "WU"):
            out = tmp / f"panels_{obs}"
            render_panels("t", s, out_dir=out, chapters=[5.0], observer_id=obs, version=f"v1_e2e-{obs.lower()}")
            ps = prompts(out)
            text = " ".join(ps).casefold()
            results[obs] = {
                "n_panels": len(ps),
                "present": {t: (t.casefold() in text) for t in FACTS},
                "prompt_sample": ps[0][:300] if ps else "",
            }
    r = results[OBSERVER_READER]
    # If no attribute (admissible or not) reaches the prompt, the render path did not emit an appearance clause
    # at all, so absence says nothing about policy. Scoring it as "omission" would be a false finding.
    surfaced = any(r["present"].values())
    verdict = {t: {"oracle_admissible": adm, "in_prompt": r["present"][t],
                   "error": ("UNAUTHORIZED EXPOSURE" if r["present"][t] and not adm else
                             "UNJUSTIFIED OMISSION" if adm and not r["present"][t] and surfaced else
                             "INCONCLUSIVE (no appearance clause emitted)" if not surfaced else "ok")}
               for t, (_, adm) in FACTS.items()}
    print(json.dumps({"reader_p5_k5": verdict, "raw": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
