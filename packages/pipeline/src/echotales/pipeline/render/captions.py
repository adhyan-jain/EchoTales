"""On-screen text, timed to the line being spoken.

**The text is not a subtitle, it is the format.** Every reference edit this
pipeline is modelled on puts one line of the novel's own prose on screen and
holds it -- "A rank nine immortal Gu House's full power attack. He had no
way to defend from it." over Fang Yuan's death; "I'm just a ghost of
yesterday, watching the people I love move toward tomorrow." over a still
portrait. The picture is the backdrop; the sentence is what the viewer came
for and what they screenshot. A chapter video without it is a slideshow with
a voiceover, which is a different and much weaker thing.

Everything needed was already on disk and unused. `voice/runner.py`'s
manifest carries each line's text, its speaker and its rendered audio, and
`timeline.py` already derives exact durations from those WAVs -- so caption
timing is *measured*, not estimated, exactly as picture timing is.

**ASS rather than drawtext**, for two reasons that both bite in practice: a
per-shot `drawtext` filter would have to escape arbitrary novel prose into a
filter-graph string (apostrophes, colons and commas are all filter syntax,
and this corpus is full of them), and one subtitle track burned in a single
pass keeps styling in one declarative place instead of scattered across a
hundred segment renders.

**Styling follows the reference edits, not subtitle convention.** Large,
centred, wide margins, heavy outline plus a soft shadow so the text survives
a busy panel, and positioned in the lower third rather than pinned to the
bottom edge. Dialogue is italicised and prefixed with the speaker, narration
is not -- that is the one distinction the reels make consistently, and it is
free here because attribution already knows which is which.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

#: Narration lines longer than this are split across successive caption
#: cards rather than shrunk. A wall of text over a portrait is the one
#: failure mode that makes an edit look automated; the reels never show more
#: than a couple of lines at once.
MAX_CHARS_PER_CARD = 140

#: Wrap width inside a card. Tuned for the portrait frame at the style's
#: font size -- roughly 30 characters is where a 1080-wide frame stops
#: looking comfortable with 100px side margins.
WRAP_WIDTH = 32

#: A card below this is too quick to read. Extends into the following line's
#: slot when the audio is shorter, which is safe because the *next* card
#: simply starts later; picture timing is untouched.
MIN_CARD_SECONDS = 1.2


@dataclass(slots=True)
class Caption:
    """One card: what it says, and exactly when."""

    start: float
    end: float
    text: str
    speaker: str = ""
    is_dialogue: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _split_into_cards(text: str) -> list[str]:
    """One long line -> successive readable cards, split on sentences.

    Splitting mid-sentence reads as a technical failure; splitting between
    sentences reads as pacing. Falls back to a hard wrap only when a single
    sentence is itself longer than a card, which in this corpus means a
    translated run-on and there is no good answer for it.
    """
    clean = " ".join(text.split())
    if len(clean) <= MAX_CHARS_PER_CARD:
        return [clean] if clean else []

    sentences: list[str] = []
    current = ""
    for piece in _sentence_pieces(clean):
        if current and len(current) + len(piece) + 1 > MAX_CHARS_PER_CARD:
            sentences.append(current.strip())
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current.strip():
        sentences.append(current.strip())

    out: list[str] = []
    for sentence in sentences:
        if len(sentence) <= MAX_CHARS_PER_CARD:
            out.append(sentence)
        else:
            out.extend(textwrap.wrap(sentence, MAX_CHARS_PER_CARD))
    return out


def _sentence_pieces(text: str) -> list[str]:
    """Split on sentence-final punctuation, keeping the punctuation."""
    pieces: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in ".!?…" and len(current.strip()) > 1:
            pieces.append(current.strip())
            current = ""
    if current.strip():
        pieces.append(current.strip())
    return pieces


def build_captions(
    lines: list[object],
    durations: dict[str, float],
    *,
    include_narration: bool = True,
) -> list[Caption]:
    """Timed caption cards for one chapter, in reading order.

    `lines` are voice-manifest lines (anything with `text`, `span_id`,
    `span_type` and `speaker_label`); `durations` maps `span_id` to that
    line's measured audio length. A line with no measured duration is
    skipped rather than guessed at -- an unsynced caption is worse than an
    absent one, because it lands over the wrong picture.

    A line whose audio is shorter than its text needs is *not* extended past
    the next line's start: the cards stay in sync with the voice, and a card
    that would be unreadably short is better than one that contradicts what
    is being said.
    """
    captions: list[Caption] = []
    clock = 0.0

    for line in lines:
        span_id = str(getattr(line, "span_id", ""))
        duration = durations.get(span_id)
        if duration is None:
            continue
        start, clock = clock, clock + duration

        span_type = str(getattr(line, "span_type", ""))
        is_dialogue = span_type in ("DIALOGUE", "INNER_MONOLOGUE")
        if not include_narration and not is_dialogue:
            continue

        cards = _split_into_cards(str(getattr(line, "text", "")))
        if not cards:
            continue

        # Divide the line's own airtime between its cards, proportional to
        # length -- the voice spends longer on the longer half, so the card
        # should too.
        total_chars = sum(len(c) for c in cards) or 1
        cursor = start
        for card in cards:
            share = duration * (len(card) / total_chars)
            end = min(cursor + max(share, MIN_CARD_SECONDS), start + duration)
            if end <= cursor:
                end = cursor + share
            captions.append(
                Caption(
                    start=cursor,
                    end=end,
                    text=card,
                    speaker=str(getattr(line, "speaker_label", "")),
                    is_dialogue=is_dialogue,
                )
            )
            cursor = end

    return captions


def _ass_time(seconds: float) -> str:
    """ASS uses `H:MM:SS.cc`, centiseconds, no leading zero on hours."""
    seconds = max(0.0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def _ass_escape(text: str) -> str:
    """ASS treats `{`/`}` as override blocks and `\\` as an escape."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_ass(
    captions: list[Caption],
    out_path: Path,
    *,
    width: int,
    height: int,
    font: str = "DejaVu Serif",
) -> Path:
    """Write a burnable subtitle track sized for this frame.

    Font size and margins scale with frame height rather than being fixed,
    so the same styling holds whether the output is a 1920-tall reel or a
    720-tall landscape preview.
    """
    size = max(28, round(height * 0.030))
    margin_v = round(height * 0.14)
    margin_h = round(width * 0.09)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Narration,{font},{size},&H00FFFFFF,&H00000000,&H80000000,0,0,1,{max(2, size // 12)},{max(1, size // 20)},2,{margin_h},{margin_h},{margin_v},1
Style: Dialogue,{font},{size},&H00F2F2F2,&H00000000,&H80000000,0,-1,1,{max(2, size // 12)},{max(1, size // 20)},2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    rows = []
    for cap in captions:
        if cap.duration <= 0:
            continue
        style = "Dialogue" if cap.is_dialogue else "Narration"
        # Escape first, then join with ASS's own line break, so `_ass_escape`
        # never sees (and never mangles) the `\N` separators we just added.
        body = "\\N".join(_ass_escape(part) for part in textwrap.wrap(cap.text, WRAP_WIDTH))
        if cap.is_dialogue and cap.speaker:
            body = f"{_ass_escape(cap.speaker)}:\\N{body}"
        rows.append(
            f"Dialogue: 0,{_ass_time(cap.start)},{_ass_time(cap.end)},{style},,0,0,0,,{body}"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return out_path
