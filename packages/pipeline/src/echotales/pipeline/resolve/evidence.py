"""Structured evidence scoring (plans.md §6 Phase 6, step 2).

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
- **`first_attested_soft_prior` is weak on purpose** (plans.md §4.4). A hard
  first-appearance constraint would forbid the exact reveal the system exists
  to handle — a late chapter disclosing that a binding held from the start.
"""

from __future__ import annotations

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
    vector.declaration_match = declaration

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
            best_containment = max(best_containment, name_containment(mention.text, alias))
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
    if (
        candidate.label in ctx.co_present
        and comparison_key(mention.text) != comparison_key(candidate.label)
        and candidate.label not in ctx.concurrent_personas
        and vector.name_containment < NAME_CONTAINMENT_FLOOR
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
