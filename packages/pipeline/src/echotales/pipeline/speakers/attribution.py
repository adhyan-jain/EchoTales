"""Phase 4: speaker attribution by four-tier escalation (plans.md §6 Phase 4).

Each tier is cheaper and more precise than the next, so a line is only handed
down when the tier above it cannot answer:

1. **Explicit** -- an attribution verb names the speaker ("Li Wei said").
   Near-perfect precision, and the bulk of lines in this genre.
2. **Proximal** -- the dialogue abuts a character's action in the same block.
   ~85%. The hard part is split sentences.
3. **Turn-taking** -- a two-party exchange alternates. ~80%.
4. **Contextual** -- everything left, escalated to the LLM.

Two outcomes are first-class results rather than failures:

- **Joint attribution** -- "X and Y both replied" has two speakers, and forcing
  one would silently discard the other.
- **Unattributed chorus** -- a run of crowd reactions has no speaker at all.
  Attributing them to whoever spoke last invents attributions from nothing,
  and those inventions propagate into voice casting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from echotales.core.enums import AttributionMethod, SpanType
from echotales.core.models import Mention, Span
from echotales.pipeline.ingest.normalize import comparison_key

# Verbs that introduce or follow speech. Deliberately broad: in translated web
# fiction the attribution verb carries the delivery marker too, and both are
# wanted.
_SPEECH_VERBS = (
    r"said|says|spoke|speaks|replied|replies|answered|answers|asked|asks|"
    r"shouted|shouts|yelled|yells|screamed|screams|roared|roars|whispered|"
    r"whispers|murmured|murmurs|muttered|mutters|mumbled|mumbles|called|calls|"
    r"cried|cries|exclaimed|exclaims|declared|declares|continued|continues|"
    r"added|adds|responded|responds|retorted|retorts|snapped|snaps|"
    r"laughed|laughs|chuckled|chuckles|sighed|sighs|sneered|sneers|"
    r"scoffed|scoffs|snorted|snorts|urged|urges|explained|explains|"
    r"interrupted|interrupts|interjected|interjects|greeted|greets|"
    r"repeated|repeats|stated|states|remarked|remarks|noted|notes|"
    r"agreed|agrees|admitted|admits|confessed|confesses|warned|warns|"
    r"ordered|orders|commanded|commands|announced|announces|hollered|"
    r"instructed|instructs"
)

_NAME = r"[A-Z][\w’'\-]*(?:\s+[A-Z][\w’'\-]*){0,3}"

# "Li Wei said" / "Li Wei said coldly"
_NAME_THEN_VERB = re.compile(
    rf"\b(?P<name>{_NAME})\s+(?:\w+\s+){{0,2}}?(?:{_SPEECH_VERBS})\b"
)

# "said Li Wei"
_VERB_THEN_NAME = re.compile(rf"\b(?:{_SPEECH_VERBS})\s+(?P<name>{_NAME})\b")

# "X and Y both replied" / "X and Y responded"
_JOINT = re.compile(
    rf"\b(?P<first>{_NAME})\s+and\s+(?P<second>{_NAME})\s+"
    rf"(?:both\s+|immediately\s+|together\s+)?(?:{_SPEECH_VERBS})\b"
)

# A name performing a physical action, used by the proximal tier.
_NAME_THEN_ACTION = re.compile(
    rf"\b(?P<name>{_NAME})\s+(?:\w+\s+){{0,2}}?"
    r"(?:nodded|frowned|smiled|turned|looked|glanced|stepped|walked|raised|"
    r"lowered|shook|bowed|paused|hesitated|sighed|stood|sat|leaned|gestured|"
    r"pointed|waved|shrugged|blinked|stared)\b"
)

# Pronoun subjects; resolved by the anaphora layer, not here.
_PRONOUN_SUBJECT = re.compile(r"\b(?:he|she|they|it)\s+(?:\w+\s+){0,2}?(?:" + _SPEECH_VERBS + r")\b", re.IGNORECASE)

#: Role titles worth matching as a speaker tag even with no proper name
#: attached -- "the clan head instructed" is exactly as much of a speaker
#: tag as "Fang Yuan instructed", just naming the speaker by role instead of
#: name. Deliberately a single verified phrase, not a broad guessed
#: vocabulary: RI ch1's ancestral-hall scene repeats "the clan head"/"the
#: Gu Yue clan head" as its speaker tag four separate times and none of them
#: were ever resolved (§4.34); extend this list only against other real,
#: checked chapters, not speculatively -- see EVOLUTION.md on the combat-
#: vocabulary mechanism that scored zero from guessing instead of measuring.
_ROLE_EPITHETS = ("clan head",)

_EPITHET = (
    r"(?:the\s+)(?:[A-Z][\w'\-]*\s+){0,3}?(?:" + "|".join(_ROLE_EPITHETS) + r")"
)

# "the clan head instructed" / "the Gu Yue clan head said"
_EPITHET_THEN_VERB = re.compile(
    rf"\b(?P<epithet>{_EPITHET})\s+(?:\w+\s+){{0,2}}?(?:{_SPEECH_VERBS})\b",
    re.IGNORECASE,
)

# "said the clan head"
_VERB_THEN_EPITHET = re.compile(
    rf"\b(?:{_SPEECH_VERBS})\s+(?P<epithet>{_EPITHET})\b", re.IGNORECASE
)


@dataclass(slots=True)
class Attribution:
    """The outcome of attributing one dialogue span."""

    span_id: str
    speaker: str | None
    method: AttributionMethod
    confidence: float
    co_speakers: list[str] = field(default_factory=list)
    evidence: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.speaker is not None or self.method is AttributionMethod.UNATTRIBUTED_CHORUS


def _known(name: str, names: frozenset[str]) -> bool:
    """Whether a captured name is a character we have seen.

    Without this the regexes happily attribute speech to any capitalised token,
    including place names and sentence-initial words.

    Matching is on the honorific-stripped, romanisation-folded comparison key
    rather than on string equality. Exact matching rejected "Wang" against a
    stored "Elder Wang" and cost roughly 13 points of coverage -- the surface
    form a speaker is named by very often differs from the form the mention
    detector happened to record.

    The caller is expected to pass a set accumulated across the whole novel so
    far, not one chapter: a character introduced in chapter 5 still speaks in
    chapter 12 whether or not the detector re-fired on them there.
    """
    if not names:
        return True
    if name in names:
        return True
    key = comparison_key(name)
    if not key:
        return False
    return key in names


def attribute_explicit(
    span: Span,
    *,
    preceding: str,
    following: str,
    known_names: frozenset[str] = frozenset(),
) -> Attribution | None:
    """Tier 1: an attribution verb names the speaker.

    Checks the *following* text before the preceding text: "…," he said is far
    more common than He said, "…" in this prose, and checking the wrong side
    first picks up the previous line's speaker.
    """
    for window in (following, preceding):
        if not window:
            continue

        joint = _JOINT.search(window)
        if joint:
            first, second = joint.group("first"), joint.group("second")
            if _known(first, known_names) and _known(second, known_names):
                return Attribution(
                    span_id=span.id,
                    speaker=first,
                    method=AttributionMethod.JOINT,
                    confidence=0.9,
                    co_speakers=[second],
                    evidence=joint.group(0),
                )

        for pattern in (_NAME_THEN_VERB, _VERB_THEN_NAME):
            match = pattern.search(window)
            if match and _known(match.group("name"), known_names):
                return Attribution(
                    span_id=span.id,
                    speaker=match.group("name"),
                    method=AttributionMethod.EXPLICIT,
                    confidence=0.95,
                    evidence=match.group(0),
                )
    return None


def attribute_epithet(
    span: Span,
    *,
    following: str,
) -> Attribution | None:
    """Tier 1.5: a role-title speaker tag with no proper name attached.

    Same adjacency requirement as `attribute_explicit` -- the epithet must
    sit directly beside a speech verb, not just appear somewhere nearby --
    so this only fires on genuine speaker tags ("the clan head instructed"),
    never on an epithet that happens to be mentioned in the same paragraph
    for some other reason. `speaker` is the matched epithet text itself; the
    caller mints a stable id from it (`_assign_epithet_speakers`), never a
    graph `Self` -- a title is not a permanent identity and must stay able
    to transfer to someone else later without this tier caring.

    `following` only, deliberately -- unlike `attribute_explicit`, which
    checks both directions. A postposed tag ("'...,' the clan head
    instructed.") sits in the *next* block's text once the block boundary is
    crossed, and `preceding` there is the whole previous block, which still
    contains that same tag verbatim. Checking `preceding` here attributed
    the elders' own reply in the very next line to "the clan head" too,
    because their line's preceding window still held the clan head's tag
    from the line before it -- a real, caught regression, not a hypothetical
    one. A preceding-side epithet tag would need same-block-only text to be
    safe, which the caller does not currently distinguish from a full
    cross-block window; left for that case to actually appear in real text
    rather than built for a case that hasn't.
    """
    if not following:
        return None
    for pattern in (_EPITHET_THEN_VERB, _VERB_THEN_EPITHET):
        match = pattern.search(following)
        if match:
            return Attribution(
                span_id=span.id,
                speaker=match.group("epithet").strip(),
                method=AttributionMethod.EPITHET_SLOT,
                confidence=0.55,
                evidence=match.group(0),
            )
    return None


#: Any mention of a bounded role epithet, speech-verb-adjacent or not --
#: used to track "who does a bare pronoun refer to right now", not to
#: attribute a line by itself. Deliberately looser than `_EPITHET_THEN_VERB`
#: for that reason: `attribute_epithet_mentioned` only updates a chapter-
#: scoped "current epithet holder" pointer, it never assigns a speaker.
_EPITHET_MENTIONED = re.compile(_EPITHET, re.IGNORECASE)


def epithet_mentioned(text: str) -> str | None:
    """The role epithet a block's narration is currently about, if any.

    Called on every block regardless of whether it contains dialogue --
    "the Gu Yue clan head curled up his lips" (no speech verb) still tells
    `attribute_pronoun_epithet` who a following bare "he said" belongs to.
    """
    match = _EPITHET_MENTIONED.search(text)
    return match.group(0).strip() if match else None


def attribute_pronoun_epithet(
    span: Span,
    *,
    preceding: str,
    following: str,
    current_epithet: str | None,
) -> Attribution | None:
    """Tier 1.6: a bare pronoun speech tag, resolved via the chapter's
    current epithet holder rather than the anaphora layer `_PRONOUN_SUBJECT`
    was originally written for (module note above it) -- the anaphora layer
    resolves pronouns to *named* entities, and this speaker has no name in
    this chapter to resolve to. `current_epithet` is threaded in by the
    caller (`speakers/runner.py::attribute_chapter`), which tracks it from
    `epithet_mentioned` and clears it whenever a different named character
    is confidently established as the current speaker -- see that caller
    for the actual state machine; this function only consumes the pointer.

    Lower confidence than `attribute_epithet`'s direct match (0.45 vs 0.55):
    a bare pronoun is weaker evidence than the title stated outright, and
    this only fires when the stronger tiers have already failed.
    """
    if current_epithet is None:
        return None
    for window in (following, preceding):
        if not window:
            continue
        if _PRONOUN_SUBJECT.search(window):
            return Attribution(
                span_id=span.id,
                speaker=current_epithet,
                method=AttributionMethod.EPITHET_SLOT,
                confidence=0.45,
                evidence=f"pronoun tag, current epithet: {current_epithet}",
            )
    return None


def attribute_proximal(
    span: Span,
    *,
    preceding: str,
    following: str,
    known_names: frozenset[str] = frozenset(),
) -> Attribution | None:
    """Tier 2: the speaker is the character acting next to the line.

    The failure mode plans.md calls out is the split sentence: in "Wu Liao
    excused himself, but Wu An hesitated and said softly:" the speaker is Wu
    An, not Wu Liao. So the *last* name before the line wins, not the first --
    proximity is measured from the quote outward.
    """
    for window, take_last in ((preceding, True), (following, False)):
        if not window:
            continue
        matches = list(_NAME_THEN_ACTION.finditer(window))
        matches = [m for m in matches if _known(m.group("name"), known_names)]
        if not matches:
            continue
        match = matches[-1] if take_last else matches[0]
        return Attribution(
            span_id=span.id,
            speaker=match.group("name"),
            method=AttributionMethod.PROXIMAL,
            confidence=0.75,
            evidence=match.group(0),
        )
    return None


def attribute_turn_taking(
    span: Span,
    recent_speakers: list[str],
) -> Attribution | None:
    """Tier 3: a two-party exchange alternates.

    Only applied when the recent history contains exactly two distinct
    speakers. With three or more the alternation assumption is unfounded, and
    guessing would produce confident wrong answers -- worse than deferring.
    """
    if len(recent_speakers) < 2:
        return None
    distinct = list(dict.fromkeys(recent_speakers[-4:]))
    if len(distinct) != 2:
        return None
    # The speaker is whoever did not speak last.
    speaker = distinct[0] if recent_speakers[-1] == distinct[1] else distinct[1]
    return Attribution(
        span_id=span.id,
        speaker=speaker,
        method=AttributionMethod.TURN_TAKING,
        confidence=0.6,
        evidence=f"alternating with {recent_speakers[-1]}",
    )


def attribute_span(
    span: Span,
    *,
    preceding: str = "",
    following: str = "",
    recent_speakers: list[str] | None = None,
    known_names: frozenset[str] = frozenset(),
    pov_holder: str | None = None,
) -> Attribution:
    """Run the ladder over one span, stopping at the first tier that answers."""
    if span.span_type is SpanType.CROWD_REACTION:
        # No forced speaker. Attributing a crowd to the last named character
        # invents attributions that propagate into voice casting.
        return Attribution(
            span_id=span.id,
            speaker=None,
            method=AttributionMethod.UNATTRIBUTED_CHORUS,
            confidence=1.0,
        )

    if span.span_type is SpanType.INNER_MONOLOGUE and pov_holder:
        # Inner monologue belongs to whoever's head we are in.
        return Attribution(
            span_id=span.id,
            speaker=pov_holder,
            method=AttributionMethod.POV_INFERRED,
            confidence=0.7,
        )

    if span.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE):
        return Attribution(
            span_id=span.id, speaker=None, method=AttributionMethod.UNRESOLVED, confidence=0.0
        )

    explicit = attribute_explicit(
        span, preceding=preceding, following=following, known_names=known_names
    )
    if explicit:
        return explicit

    epithet = attribute_epithet(span, following=following)
    if epithet:
        return epithet

    proximal = attribute_proximal(
        span, preceding=preceding, following=following, known_names=known_names
    )
    if proximal:
        return proximal

    turn = attribute_turn_taking(span, recent_speakers or [])
    if turn:
        return turn

    return Attribution(
        span_id=span.id, speaker=None, method=AttributionMethod.UNRESOLVED, confidence=0.0
    )


def detect_pov_holder(
    mentions: list[Mention], spans: list[Span], *, min_ratio: float = 0.02
) -> str | None:
    """Guess whose viewpoint a chapter is told from.

    Uses inner-monologue proximity rather than first-person pronoun density:
    this content is overwhelmingly third-person limited, so the POV holder is
    whoever the narration reports thoughts *for*, not whoever says "I".
    """
    inner = [s for s in spans if s.span_type is SpanType.INNER_MONOLOGUE]
    if not inner:
        return None

    counts: dict[str, int] = {}
    for span in inner:
        nearby = [
            m
            for m in mentions
            if abs(m.offset - span.start) < 400 and m.alias_type.name == "RIGID_NAME"
        ]
        for mention in nearby:
            counts[mention.text] = counts.get(mention.text, 0) + 1

    if not counts:
        return None
    best, best_count = max(counts.items(), key=lambda kv: kv[1])
    total = sum(counts.values())
    return best if total and best_count / total >= min_ratio else None
