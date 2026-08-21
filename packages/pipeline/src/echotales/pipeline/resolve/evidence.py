"""Structured evidence scoring (plans.md Section 6 Phase 6, step 2).

Ten signals are computed per (mention, candidate) pair. A **vector**, not a
scalar similarity, because the two failure directions on this content need
different signals to catch them:

- Two aliases of one character sharing no surface form. Only declaration
  evidence and context similarity can link them.
- Two unrelated holders of one title sharing every character. Only temporal
  validity and co-presence can separate them.

A single similarity number cannot express both, which is why clustering fails
here in both directions at once.

**Only five of the ten are scored** (`models.SCORED_FEATURES`). Three are hard
pre-filters or blockers handled in `score.prefilter()` before scoring is
reached — see that module for why treating them as weighted features caused
runaway over-merging. The remaining two are computed for diagnostics.

Two of the scored five behave distinctively, deliberately:

- **`temporal_validity`** doubles as the pre-filter's hard exclusion: an
  invalid binding is removed from consideration, not merely penalised.
- **`first_attested_soft_prior` is weak on purpose** (plans.md Section 4.4). A hard
  first-appearance constraint would forbid the exact reveal the system exists
  to handle — a late chapter disclosing that a binding held from the start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from echotales.core.enums import AliasType
from echotales.core.interval import Certainty
from echotales.core.models import Candidate, EvidenceVector, Mention
from echotales.pipeline.ingest.normalize import (
    comparison_key,
    name_containment,
    strip_honorifics,
)
from echotales.pipeline.mentions.lexicon import Lexicon
from echotales.pipeline.resolve.retrieve import EntityProfile, _terms
from echotales.pipeline.resolve.score import NAME_CONTAINMENT_FLOOR


def jaro_winkler(a: str, b: str) -> float:
    """Jaro-Winkler similarity.

    Chosen over edit distance because it weights a shared prefix, and
    romanised names of one person overwhelmingly agree at the start and drift
    at the end ("Shi Cheng" / "Shi Chen").
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    match_window = max(len(a), len(b)) // 2 - 1
    match_window = max(match_window, 0)

    a_matched = [False] * len(a)
    b_matched = [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        lo = max(0, i - match_window)
        hi = min(i + match_window + 1, len(b))
        for j in range(lo, hi):
            if b_matched[j] or b[j] != ch:
                continue
            a_matched[i] = b_matched[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0

    transpositions = 0
    k = 0
    for i, matched in enumerate(a_matched):
        if not matched:
            continue
        while not b_matched[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    jaro = (
        matches / len(a) + matches / len(b) + (matches - transpositions) / matches
    ) / 3.0

    prefix = 0
    for x, y in zip(a, b, strict=False):
        if x != y or prefix == 4:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


@dataclass(slots=True)
class EvidenceContext:
    """Everything the scorer needs beyond the mention and candidate themselves."""

    #: Text around the mention, for declaration detection and context similarity.
    context: str = ""
    #: Whether the candidate's alias binding is temporally valid here.
    temporal_certainty: Certainty = Certainty.CERTAIN
    #: Surface forms present in the same scene, for the co-presence check.
    co_present: frozenset[str] = frozenset()
    #: Personas known to have concurrent bindings; suppresses co-presence.
    concurrent_personas: frozenset[str] = frozenset()
    #: The speaker of the span containing the mention.
    speaker: str | None = None
    #: Region or faction of the current scene, for audience scoping.
    scene_scope: str = ""
    #: Every region/faction tag known to the graph. Empty means the novel
    #: has no region taxonomy, so scope comparison is meaningless rather
    #: than merely unknown.
    known_scopes: frozenset[str] = frozenset()
    lexicon: Lexicon | None = None
    #: Name components (surname, title) attested across two or more distinct
    #: entities in this novel's cast so far -- see
    #: `resolve/runner.py::GlobalResolver._ambiguous_tokens`. `None` (the
    #: default) means the caller has no opinion, which keeps
    #: `name_containment`'s old strictly-2-token behaviour; a real (possibly
    #: empty) frozenset opts into the single-token dropped-given-name case.
    ambiguous_tokens: frozenset[str] | None = None


def detect_declaration(context: str, lexicon: Lexicon | None) -> tuple[float, str]:
    """Look for an explicit identity assertion near the mention.

    Near-perfect precision and extremely common in web fiction, which is why
    this carries the highest weight in the model. "His true name was X" is not
    evidence *for* a link; it *is* the link.
    """
    if lexicon is None or not lexicon.identity_declarations:
        return 0.0, ""
    lowered = context.casefold()
    for phrase in lexicon.identity_declarations:
        if phrase.casefold() in lowered:
            return 1.0, phrase
    return 0.0, ""


#: Structural identity-continuity assertions, as regexes rather than lexicon
#: phrases (Section 4.15's LOTM transmigration case).
#:
#: `detect_declaration`'s lexicon phrases are flat substrings, which cannot
#: express "memories" and "flooding" separated by an arbitrary verb phrase
#: ("memories *began* flooding him"). They also run in the opposite temporal
#: direction from this class: "his true name was X" is a *new name revealing
#: an old identity*, whereas transmigration is an *existing identity
#: acquiring a new name and backstory*. Same evidential strength, different
#: shape, so a different matcher -- but deliberately feeding the same
#: `declaration_match` feature, because HANDOFF Section 4.15 identifies these as one
#: class of signal and Section 4.1 makes the pre-filter the only path to a link.
#:
#: Kept structural (no novel-specific vocabulary) so this transfers to a book
#: whose reincarnation idiom this code has never seen -- the same design call
#: `normalize.name_containment` makes about house prefixes.
_CONTINUITY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bmemor(?:y|ies)\b[^.!?]{0,60}?\b(?:flood|surg|surfac|return|rush|pour|emerg)"),
        "memories of another identity surfacing",
    ),  # vetoed by _MEMORIES_ALREADY_OWNED -- see detect_identity_continuity
    (
        re.compile(r"\bthis (?:the )?(?:present|current|new) (?:me|body|self)\b"),
        "present-self identification",
    ),
    # Deliberately the *transitive* forms only ("transmigrated into X"), never
    # the bare noun. Measured on LOTM, whose premise is transmigration: the
    # bare word appears as ordinary topic vocabulary throughout ("his
    # transmigration", "a transmigration senior", "transmigrate back") and
    # fired on three unrelated pairs -- merging a *country* (`Loen Kingdom`)
    # and a faction (`Beyonders`) into the protagonist. A word that is the
    # subject matter of the book cannot also be a discriminator within it.
    (
        re.compile(r"\b(?:transmigrat|reincarnat)(?:ed|ing)\s+(?:into|as|in)\b"),
        "transitive transmigration/reincarnation",
    ),
    (
        re.compile(
            r"\b(?:took over|occupied|inhabit(?:ed|ing)|possess(?:ed|ing)) "
            r"(?:the |this |another )?body\b"
        ),
        "body occupation",
    ),
)


#: Vetoes the memory pattern above. The semantic difference between
#: transmigration and ordinary recollection is *who already owns the
#: memories*: "memories began flooding him" describes memories arriving from
#: outside the subject, while "his childhood memories came flooding back"
#: describes memories he always had. A pronoun or a life-stage adjective in
#: front of "memories" marks the second reading.
#:
#: A *name*-possessive is deliberately not vetoed ("Klein Moretti's memories
#: began flooding him") -- that is the transmigration shape stated even more
#: explicitly, not a counterexample to it.
_MEMORIES_ALREADY_OWNED = re.compile(
    r"\b(?:his|her|their|my|our|your|its|own|childhood|fond|painful|happy|"
    r"distant|old|past|earlier|previous)\s+(?:\w+\s+)?memor(?:y|ies)\b"
)


#: How far a continuity phrase may sit from *each* of the two names it is
#: claimed to link. The assertion is a single clause ("Zhou Mingrui ...
#: memories began flooding him ... Klein Moretti" spans ~120 characters in
#: the real LOTM text); a name at the far end of the 400-character context
#: window is simply elsewhere in the paragraph, not part of the claim.
_CONTINUITY_PROXIMITY = 150


def _word_spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Whole-surface occurrences. Both arguments must already be casefolded.

    Word-boundary matched, not `in`: a substring test lets a short surface
    match inside an unrelated word (a bare "a" is present in "came"), which
    silently defeats the two-name guard `detect_identity_continuity`'s
    precision rests on. Same defect class as the gazetteer's `_is_boundary`
    (Section 4.4).
    """
    return [
        m.span() for m in re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack)
    ]


def detect_identity_continuity(
    context: str, surface_a: str, surface_b: str
) -> tuple[float, str]:
    """Identity continuity across a *name change*, not a name reveal.

    **Both surfaces must appear in the context window**, and that requirement
    is the whole precision story. "Memories flooded back" is ordinary prose
    about someone merely remembering something; it only asserts an identity
    link when two different names are sitting next to it, because that is the
    only configuration in which there is a link to assert. Without this guard
    the pattern would FORCE_LINK a mention to whatever retrieval ranked first
    every time a character recalled their childhood -- and per Section 4.1 a
    pre-filter verdict is not outvoteable by other evidence, so a false
    positive here is unrecoverable rather than merely noisy.

    Returns `(1.0, rationale)` or `(0.0, "")`, matching `detect_declaration`.
    """
    if not context or not surface_a or not surface_b:
        return 0.0, ""
    lowered = context.casefold()
    a, b = surface_a.casefold(), surface_b.casefold()
    # Two *different* names. One name matching itself is a repetition, not a
    # continuity assertion, and would fire on every ordinary mention.
    if a == b:
        return 0.0, ""
    spans_a, spans_b = _word_spans(lowered, a), _word_spans(lowered, b)
    if not spans_a or not spans_b:
        return 0.0, ""

    memories_owned = _MEMORIES_ALREADY_OWNED.search(lowered) is not None
    for index, (pattern, rationale) in enumerate(_CONTINUITY_PATTERNS):
        for hit in pattern.finditer(lowered):
            # Index 0 is the memory pattern, the only one with an ownership
            # reading to get wrong. Vetoing on *any* owned-memory phrase in
            # the window (rather than only the matched one) errs toward not
            # linking, which is the cheaper failure here: over-splitting is
            # recoverable by a later merge, an unrecoverable FORCE_LINK is
            # not (Section 4.1).
            if index == 0 and memories_owned:
                continue
            if _near(hit.span(), spans_a) and _near(hit.span(), spans_b):
                return 1.0, rationale
    return 0.0, ""


def _near(hit: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    """Whether any occurrence in `spans` is within the proximity budget of `hit`."""
    return any(
        max(start, hit[0]) - min(end, hit[1]) <= _CONTINUITY_PROXIMITY
        for start, end in spans
    )


def _audience_scope(
    ctx: EvidenceContext, profile: EntityProfile | None
) -> float | None:
    """Region/faction compatibility, or `None` when it cannot be judged.

    `None` means "this feature has nothing to say about this pair" and the
    caller must exclude it, rather than substituting a neutral value. A feature
    that defaults to a constant on most instances is indistinguishable from
    noise but is weighted as though it were evidence.
    """
    if not ctx.scene_scope or profile is None:
        return None
    if not ctx.known_scopes:
        # No entity in the graph carries region tags, so the taxonomy does not
        # exist for this novel and the comparison is meaningless.
        return None

    tag = ctx.scene_scope.casefold()
    if tag in profile.context_terms:
        return 1.0
    # The scene is tagged and this candidate has never appeared under that tag:
    # a weak negative, not a hard exclusion. Characters travel.
    return 0.25


def score_evidence(
    mention: Mention,
    candidate: Candidate,
    profile: EntityProfile | None,
    ctx: EvidenceContext,
) -> EvidenceVector:
    """Build the evidence vector for one (mention, candidate) pair."""
    vector = EvidenceVector()

    declaration, _ = detect_declaration(ctx.context, ctx.lexicon)
    # Same feature, different shape and opposite temporal direction -- see
    # `detect_identity_continuity`. Kept in its own variable because it also
    # suppresses the co-presence blocker below, which a lexicon declaration
    # deliberately does *not* do.
    continuity, _ = detect_identity_continuity(ctx.context, mention.text, candidate.label)
    vector.declaration_match = max(declaration, continuity)

    surface_key = comparison_key(mention.text)
    if profile is not None and surface_key and surface_key in profile.alias_keys:
        vector.gazetteer_exact_match = 1.0

    # Compare honorific-stripped forms so "Elder Wang" and "Wang" score high
    # while remaining distinguishable at the binding level.
    bare_mention = strip_honorifics(mention.text).casefold()
    best_surface = 0.0
    best_containment = 0.0
    if profile is not None:
        for alias in profile.aliases:
            best_surface = max(
                best_surface, jaro_winkler(bare_mention, strip_honorifics(alias).casefold())
            )
            # Character-level similarity is blind to a dropped house prefix:
            # "Mo Bei" against "Gu Yue Mo Bei" scores ~0.5 and falls under the
            # floor, so the pair splits into two entities. Kept in its own
            # feature so it can be pre-filtered without a merely-similar pair
            # of distinct names riding along on a high Jaro-Winkler score.
            best_containment = max(
                best_containment,
                name_containment(mention.text, alias, ambiguous_tokens=ctx.ambiguous_tokens),
            )
    vector.surface_similarity = best_surface
    vector.name_containment = best_containment

    if profile is not None and ctx.context:
        from collections import Counter

        from echotales.pipeline.resolve.retrieve import _cosine

        vector.context_embedding_similarity = _cosine(
            Counter(_terms(ctx.context)), profile.context_terms
        )

    if ctx.speaker and profile is not None:
        partners = profile.speech_partners
        if partners:
            vector.speech_partner_compatibility = min(
                1.0, partners.get(ctx.speaker, 0) / max(sum(partners.values()), 1) * 4
            )

    # Filter, not scorer: an excluded candidate is removed upstream of the
    # model rather than being outvoted by other features.
    vector.temporal_validity = {
        Certainty.CERTAIN: 1.0,
        Certainty.PLAUSIBLE: 0.5,
        Certainty.EXCLUDED: 0.0,
    }[ctx.temporal_certainty]

    # Co-presence is negative evidence between *personas*. Suppressed when the
    # candidate is known to hold concurrent persona bindings, because for a
    # clone or sustained disguise simultaneous presence is the expected shape.
    #
    # Also suppressed when one form contains the other as a name suffix. A
    # chapter that introduces "Gu Yue Mo Bei" and then calls him "Mo Bei" three
    # lines later puts both surfaces in the same scene, which reads to the raw
    # check as two people standing together. That fired before the containment
    # pre-filter could merge them, so the pair split every time — the blocker
    # was hiding the fix.
    #
    # The identity test is on the comparison key, not the raw string. Two
    # spellings of one name — "Fang Yuan" and its hyphenated spelling — are trivially
    # co-present with each other, and a raw `!=` read that as two people.
    # Also suppressed by an identity-continuity assertion, for the same reason
    # in a sharper form (Section 4.15's LOTM transmigration). Two names occupying one
    # scene is not incidental to transmigration, it *is* transmigration: the
    # old name and the newly-acquired one are necessarily in the same
    # paragraph, because that paragraph is where the acquisition is narrated.
    # Co-presence's premise ("simultaneously present doing different things")
    # is therefore exactly inverted here, so it must not blocker-veto the
    # pre-filter it would otherwise pre-empt.
    #
    # Deliberately keyed on the *continuity* signal only, not on
    # `declaration_match` generally: `score.prefilter`'s docstring makes the
    # blocker-beats-declaration precedence a considered choice ("far more
    # likely to be a detector error than a genuine identity"), and that
    # general rule is left standing.
    if (
        candidate.label in ctx.co_present
        and comparison_key(mention.text) != comparison_key(candidate.label)
        and candidate.label not in ctx.concurrent_personas
        and vector.name_containment < NAME_CONTAINMENT_FLOOR
        and continuity < 1.0
    ):
        vector.co_presence_violation = 1.0

    # Explicit region/faction tags only, or null.
    #
    # The earlier definition ("computed by replaying events") was unbounded:
    # the text rarely states who witnessed what, so replay yielded nothing and
    # the feature silently collapsed to a constant 0.5 on nearly every pair —
    # adding noise to every decision while appearing to contribute.
    #
    # Now: a weak negative only when the scene carries an explicit tag AND the
    # candidate has no appearances under it. When either side is untagged the
    # feature is *null* and excluded from that scoring instance. Absence of
    # evidence is not evidence of absence.
    #
    # Note this feature is currently not in `SCORED_FEATURES` (see review #5),
    # so it is computed for diagnostics but does not affect the decision. The
    # null semantics are correct here so that re-enabling it is safe.
    scope = _audience_scope(ctx, profile)
    vector.audience_scope_compatibility = 0.0 if scope is None else scope

    # A relational deictic resolves relative to the speaker, never globally,
    # so it only scores when a speaker is actually known.
    if mention.alias_type is AliasType.RELATIONAL_DEICTIC and ctx.speaker:
        vector.relationship_deictic_resolution = 0.5

    # Soft and overridable: a hard constraint would forbid the reveal case.
    if profile is not None and profile.first_chapter > mention.chapter:
        vector.first_attested_soft_prior = -1.0

    return vector
