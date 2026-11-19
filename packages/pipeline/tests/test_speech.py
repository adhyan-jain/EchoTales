"""The beat's director request names who says each line and to whom (RI ch1 ultimatum panels, 2026-11-19)."""

from __future__ import annotations

from echotales.core.models import Span, SpanType
from echotales.pipeline.render.direction import build_prompt, system_prompt
from echotales.pipeline.render.speech import spoken_lines


def _sp(block: int, text: str, speaker: str | None, kind: SpanType = SpanType.DIALOGUE) -> Span:
    return Span(id=f"x:{block}", novel_id="x", chapter=1, block_index=block, start=0, end=len(text), span_type=kind, text=text,
                speaker_self_id=speaker)


FANG = "Fang Yuan"
SPANS = [
    _sp(0, "“Fang Yuan, quietly hand over the Spring Autumn Cicada and I'll give you a quick death!”", FANG),
    _sp(1, "“Old bastard Fang, stop attempting to resist anymore, today all of the major factions have combined.”", "Bai Ning Bing"),
    _sp(18, "“The sun sets above the blue mountain.”", FANG),
    _sp(25, "“I shall still be a demon in my next life!”", FANG, SpanType.INNER_MONOLOGUE),
]


def _label(sp: Span) -> str:
    return sp.speaker_self_id or ""


def test_a_line_by_someone_outside_cast_is_attributed_to_them_and_addressed_to_the_lead() -> None:
    out = spoken_lines(SPANS, [1], label_of=_label, cast=[FANG])
    assert "not in CAST" in out and "says to Fang Yuan" in out
    assert "Bai Ning Bing" not in out  # the director may only name CAST


def test_a_quote_that_opens_by_naming_its_speaker_is_not_theirs() -> None:
    # the graph gave block 0 to Fang Yuan, who is the man being addressed
    out = spoken_lines(SPANS, [0], label_of=_label, cast=[FANG])
    assert out.startswith("- someone who is not in CAST") and "to Fang Yuan" in out


def test_the_leads_own_line_and_thought_name_him() -> None:
    assert spoken_lines(SPANS, [18], label_of=_label, cast=[FANG]).startswith("- Fang Yuan says:")
    assert spoken_lines(SPANS, [25], label_of=_label, cast=[FANG]).startswith("- Fang Yuan thinks")
    assert spoken_lines(SPANS, [5], label_of=_label, cast=[FANG]) == ""


def test_the_director_request_lists_the_lines_and_says_the_speaker_owns_the_face() -> None:
    lines = spoken_lines(SPANS, [1], label_of=_label, cast=[FANG])
    p = build_prompt("The warriors shouted.", cast={FANG: ""}, novel_style="x", spoken=lines)
    assert "SPOKEN LINES" in p and lines in p
    assert "SPOKEN LINES in this passage" not in build_prompt("He stood.", cast={FANG: ""}, novel_style="x")
    sysp = system_prompt("").lower()
    assert "reaction" in sysp and "third person" in sysp
