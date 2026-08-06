"""Phase 1: span-level classification (plans.md §6 Phase 1).

Blocks are split into spans and each span is typed. This is what stops a
chapter that merely *names* nine characters from producing a panel containing
nine characters, six of whom are absent or dead: `NARRATION_DESCRIPTION`
becomes an image prompt, `DIALOGUE` becomes a speech bubble,
`NARRATION_EXPOSITION` is kept in audio and skipped in panels.

Three signals drive classification, in decreasing order of reliability:

1. **Quotation marks** -- a quoted run is dialogue. Near-perfect precision.
2. **Source emphasis** -- the LOTM volume italicises inner monologue, giving a
   structural signal that survives only because ingestion is EPUB-based.
3. **Attribution verbs** -- "thought", "mused", "said in his heart". Recall-
   limited but source-independent, and the only signal available for RI.

Signal 2 is worth dwelling on: because one source carries it and the other does
not, the italicised spans double as a labelled slice for measuring how well the
verb heuristic in signal 3 actually performs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from echotales.core.enums import SpanType
from echotales.core.models import Block, Chapter, Span
from echotales.pipeline.spans.delivery import extract_delivery_markers

# Both sources use curly quotes; straight quotes appear in some exports.
_OPEN_QUOTES = "“‟‘‛\"'「『«"
_CLOSE_QUOTES = "”„’‚\"'」』»"

_QUOTE_PAIRS = {
    "“": "”",
    "‘": "’",
    '"': '"',
    "'": "'",
    "「": "」",
    "『": "』",
    "«": "»",
}

# Verbs that mark reported thought rather than speech. plans.md lists these
# explicitly; the "in his/her heart" forms are calques common in translated
# Chinese web fiction and are the highest-yield members of the set.
_THOUGHT_VERBS = (
    r"thought",
    r"mused",
    r"pondered",
    r"wondered",
    r"reflected",
    r"recalled",
    r"realised|realized",
    r"sighed inwardly",
    r"sneered inwardly",
    r"laughed inwardly",
    r"cursed inwardly",
    r"mumbled inwardly",
    r"muttered inwardly",
    r"said inwardly",
    r"thought inwardly",
    r"said in (?:his|her|their) heart",
    r"cried in (?:his|her|their) heart",
    r"sneered in (?:his|her|their) heart",
    r"thought to (?:himself|herself|themselves)",
    r"in (?:his|her|their) mind",
    r"inwardly",
    r"silently repeated",
)

_THOUGHT_RE = re.compile(r"\b(?:" + "|".join(_THOUGHT_VERBS) + r")\b", re.IGNORECASE)

# Physical action: a body doing something. Feeds panel generation.
_ACTION_RE = re.compile(
    r"\b(?:walk(?:ed|s|ing)?|ran|run(?:s|ning)?|str(?:ode|ide)|step(?:ped)?|turn(?:ed)?|"
    r"rais(?:ed|ing)|lower(?:ed)?|reach(?:ed)?|grabb?(?:ed)?|seiz(?:ed)?|thrust|swung|"
    r"struck|slash(?:ed)?|stabb(?:ed)?|leap(?:ed|t)?|jump(?:ed)?|fl(?:ew|ies)|land(?:ed)?|"
    r"sat|stood|knelt|bow(?:ed)?|nodd(?:ed)?|shook|smil(?:ed)?|frown(?:ed)?|glanc(?:ed)?|"
    r"look(?:ed)?|star(?:ed)|point(?:ed)?|threw|caught|pull(?:ed)?|push(?:ed)?|"
    r"drew|lift(?:ed)?|placed|handed|struck)\b",
    re.IGNORECASE,
)

# Static visual description: what something looks like. Becomes an image prompt.
_DESCRIPTION_RE = re.compile(
    r"\b(?:was|were|appeared|seemed|looked like|resembled|stood|lay|hung|glowed|"
    r"shimmer(?:ed)?|covered|filled|surrounded|shaped|coloured|colored)\b"
    r"|\b(?:tall|short|thin|thick|huge|massive|tiny|vast|ancient|crimson|azure|golden|"
    r"silver|pale|dark|bright|jade|emerald)\b",
    re.IGNORECASE,
)

# Aphorism / worldbuilding exposition: general truths, not this moment.
_EXPOSITION_RE = re.compile(
    r"\b(?:it (?:is|was) said|legend|in this world|the world|generally|usually|always|"
    r"never|those who|anyone who|whoever|all .{0,20}(?:cultivators|beyonders|gu masters)|"
    r"according to|as everyone knew|it was common knowledge|rumour had it|rumor had it|"
    r"in the past|for centuries|since ancient times)\b",
    re.IGNORECASE,
)

# Short unattributed exclamations. In crowd scenes these arrive in runs and
# must not be forced onto a named speaker.
_CROWD_RE = re.compile(
    r"^[\"“‘']?\s*(?:"
    r"(?:wh?at|huh|hmm?|eh|ah|oh|hey|no|yes|impossible|incredible|amazing|"
    r"unbelievable|damn|heavens|gods?)\b[^.?!]{0,40}"
    r")[?!.…]*\s*[\"”’']?$",
    re.IGNORECASE,
)

_CROWD_MAX_LEN = 60


@dataclass(slots=True)
class RawSpan:
    """A span before typing."""

    start: int
    end: int
    text: str
    is_quoted: bool
    is_emphasised: bool = False


def _quote_runs(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by quoted runs, including the quote marks."""
    runs: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _QUOTE_PAIRS and _is_quote_open(text, i):
            closer = _QUOTE_PAIRS[ch]
            j = _find_closer(text, i + 1, closer)
            end = n if j == -1 else min(j + 1, n)
            runs.append((i, end))
            i = end
            continue
        i += 1
    return runs


def _covered(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    """Whether ``[start, end)`` sits inside any of ``ranges``."""
    return any(s <= start and end <= e for s, e in ranges)


def split_block(text: str, italic_ranges: list[tuple[int, int]] | None = None) -> list[RawSpan]:
    """Split a block into spans at both quote and emphasis boundaries.

    Emphasis is a boundary in its own right, not merely an attribute of a span.
    The reason is concrete: translated volumes routinely put an italicised
    thought and its trailing narration in one paragraph::

        <i>Where am I?</i> Calming himself down, he repeated the question.

    Splitting on quotes alone yields a single span, and the emphasis then
    covers too small a fraction of it to classify as inner monologue -- so the
    structural signal that motivated ingesting EPUB rather than PDF gets thrown
    away at the last step. Splitting on emphasis boundaries keeps it.
    """
    ranges = list(italic_ranges or [])
    quotes = _quote_runs(text)

    points = {0, len(text)}
    for start, end in quotes:
        points.update((start, end))
    for start, end in ranges:
        points.update((max(0, start), min(len(text), end)))

    ordered = sorted(p for p in points if 0 <= p <= len(text))
    spans: list[RawSpan] = []
    for start, end in pairwise(ordered):
        if end <= start or not text[start:end].strip():
            continue
        spans.append(
            RawSpan(
                start=start,
                end=end,
                text=text[start:end],
                is_quoted=_covered(start, end, quotes),
                is_emphasised=_covered(start, end, ranges),
            )
        )
    return spans


def split_quoted(text: str) -> list[RawSpan]:
    """Split on quote boundaries only. Retained for callers with no markup."""
    return split_block(text, None)


def _is_quote_open(text: str, i: int) -> bool:
    """Distinguish an opening quote from an apostrophe.

    Straight quotes are ambiguous, so require that the character either starts
    the block or follows whitespace/punctuation, and is followed by a word
    character. Curly opening quotes are unambiguous and always accepted.
    """
    ch = text[i]
    if ch in "“‘「『«":
        return True
    prev = text[i - 1] if i > 0 else " "
    nxt = text[i + 1] if i + 1 < len(text) else ""
    return (prev.isspace() or prev in "([{—–-" or i == 0) and bool(nxt) and not nxt.isspace()


def _find_closer(text: str, start: int, closer: str) -> int:
    for j in range(start, len(text)):
        if text[j] != closer:
            continue
        if closer in "'\"":
            # A straight closer must not be a mid-word apostrophe.
            nxt = text[j + 1] if j + 1 < len(text) else " "
            if not (nxt.isspace() or nxt in ".,;:!?)]}—–-" or j + 1 == len(text)):
                continue
        return j
    return -1


def classify_span(
    span: RawSpan,
    *,
    block: Block | None = None,
    preceding_text: str = "",
    following_text: str = "",
) -> SpanType:
    """Assign a `SpanType` to one raw span.

    `preceding_text` and `following_text` are the neighbouring narration, which
    is where the attribution verb usually lives -- "he thought" follows the
    quoted thought rather than sitting inside it.
    """
    text = span.text.strip()
    stripped = text.strip("".join(set(_OPEN_QUOTES + _CLOSE_QUOTES))).strip()

    # Source emphasis is the strongest available signal for inner monologue and
    # is trusted over everything else: the translator marked it explicitly,
    # whereas every other cue here is inference.
    if span.is_emphasised:
        return SpanType.INNER_MONOLOGUE

    if span.is_quoted:
        # A quoted run whose attribution is a thought verb is reported thought,
        # not speech. Translated Chinese web fiction quotes thoughts constantly.
        window = f"{preceding_text[-80:]} {following_text[:80]}"
        if _THOUGHT_RE.search(window):
            return SpanType.INNER_MONOLOGUE
        if len(stripped) <= _CROWD_MAX_LEN and _CROWD_RE.match(stripped):
            return SpanType.CROWD_REACTION
        return SpanType.DIALOGUE

    # Unquoted narration.
    if _EXPOSITION_RE.search(stripped):
        return SpanType.NARRATION_EXPOSITION
    if _ACTION_RE.search(stripped):
        return SpanType.NARRATION_ACTION
    if _DESCRIPTION_RE.search(stripped):
        return SpanType.NARRATION_DESCRIPTION
    return SpanType.NARRATION_ACTION


def classify_block_spans(
    block: Block,
    *,
    novel_id: str,
    chapter: float,
) -> list[Span]:
    """Split one block into typed spans."""
    from echotales.core.enums import BlockType

    if block.block_type is BlockType.SYSTEM_WINDOW:
        return [
            Span(
                id=f"{novel_id}:{chapter:g}:{block.index}:0",
                novel_id=novel_id,
                chapter=chapter,
                block_index=block.index,
                start=0,
                end=len(block.text),
                span_type=SpanType.SYSTEM_WINDOW,
                text=block.text,
            )
        ]
    if not block.block_type.is_story_content:
        return [
            Span(
                id=f"{novel_id}:{chapter:g}:{block.index}:0",
                novel_id=novel_id,
                chapter=chapter,
                block_index=block.index,
                start=0,
                end=len(block.text),
                span_type=SpanType.NON_DIEGETIC,
                text=block.text,
            )
        ]

    raw_spans = split_block(block.text, block.italic_ranges)
    out: list[Span] = []
    for i, raw in enumerate(raw_spans):
        preceding = raw_spans[i - 1].text if i > 0 else ""
        following = raw_spans[i + 1].text if i + 1 < len(raw_spans) else ""
        span_type = classify_span(
            raw, block=block, preceding_text=preceding, following_text=following
        )
        markers = (
            []
            if span_type in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE)
            else extract_delivery_markers(raw.text)
        )
        out.append(
            Span(
                id=f"{novel_id}:{chapter:g}:{block.index}:{i}",
                novel_id=novel_id,
                chapter=chapter,
                block_index=block.index,
                start=raw.start,
                end=raw.end,
                span_type=span_type,
                text=raw.text.strip(),
                delivery_markers=[m.text for m in markers],
            )
        )

    return _promote_crowd_runs(out)


def _promote_crowd_runs(spans: list[Span]) -> list[Span]:
    """Re-type isolated short exclamations that appear in runs.

    A single "Impossible!" beside a named speaker is that speaker's line. Three
    in a row with no attribution between them is a crowd, and forcing a speaker
    onto each would invent three attributions from nothing.
    """
    dialogue_idx = [
        i
        for i, s in enumerate(spans)
        if s.span_type in (SpanType.DIALOGUE, SpanType.CROWD_REACTION)
    ]
    run: list[int] = []
    for idx in dialogue_idx:
        short = len(spans[idx].text) <= _CROWD_MAX_LEN
        if short and (not run or idx - run[-1] <= 2):
            run.append(idx)
            continue
        if len(run) >= 3:
            for i in run:
                spans[i].span_type = SpanType.CROWD_REACTION
        run = [idx] if short else []
    if len(run) >= 3:
        for i in run:
            spans[i].span_type = SpanType.CROWD_REACTION
    return spans


def classify_chapter(chapter: Chapter) -> list[Span]:
    """Split every block of a chapter into typed spans."""
    out: list[Span] = []
    for block in chapter.blocks:
        out.extend(
            classify_block_spans(block, novel_id=chapter.novel_id, chapter=chapter.number)
        )
    return out
