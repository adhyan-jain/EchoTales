"""EXPERIMENTAL clan-surname disambiguation features -- NOT wired into `score.py`.

Investigation task (2026-09-10): the scorer's existing five `SCORED_FEATURES`
cannot separate distinct clan members sharing a surname ("six-Wang, six-Chi",
EVOLUTION.md Section 2 / 4.1b -- "Chi Chen/Chi Lian/Mo Chen/Chi Shan/Chi
She/Chi Zhong collapse into one entity"). `_ambiguous_tokens`
(`resolve/runner.py`) already addresses this correctly as a **negative**
signal: it knows a bare "Wang"/"Chi" token is shared by several people and
therefore *withholds* evidence, which is why `name_containment`'s single-token
branch does not fire on it. What it cannot do is *positively* pick the right
sibling once the token is known to be ambiguous -- and per HANDOFF's own
4.1 note ("no new pre-filter feature suggested itself from reading the
code"), nothing in the codebase currently tries.

This module is that attempt: five NEW candidate features, each targeting a
different kind of positive disambiguating context a clan-surname collision
mention might carry. **None of these are imported by `score.py`,
`evidence.py`, or any production call path.** See
`/tmp/.../scratchpad/clan_feature_eval.py` (this session's scratch harness,
not committed) for the standalone measurement against a synthetic-but-
corpus-derived collision set, and the session report for the numbers and
the honest verdict on whether any of them clears the 0.85 precision bar.

Each function mirrors the signature shape of `evidence.py`'s detectors: pure,
no I/O, returns a float in [0, 1] (or `None` when the signal cannot be judged
for this pair, following `_audience_scope`'s null-not-zero convention --
a feature that defaults to a constant on most instances is indistinguishable
from noise but gets weighted as though it were evidence).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable

# ---------------------------------------------------------------------------
# 1. Nearby given-name evidence
# ---------------------------------------------------------------------------


def given_name_proximity(
    context: str, mention_span: tuple[int, int], candidate_given_names: Iterable[str]
) -> float | None:
    """Whether one of the candidate's own given names sits near the bare surname.

    "Wang" alone is ambiguous across six siblings; "Wang... his brother Da"
    two clauses later, or a dangling honorific-stripped "Da" earlier in the
    same sentence that the mention is standing in for, is not. This is
    distinct from `name_containment`'s FORCE_LINK case (a *single* mention
    contains both tokens, e.g. "Wang Da") -- here the two tokens are split
    across separate mentions in the same window, which `name_containment`
    never sees because it compares one mention's text to one alias string.

    Graded by distance: a given name three words away is stronger evidence
    than one at the edge of the context window, because in this corpus a
    clan scene routinely names the *other* siblings once each in an
    introduction paragraph before settling into bare surnames.
    """
    given_names = [g for g in candidate_given_names if g]
    if not context or not given_names:
        return None
    start, end = mention_span
    best = 0.0
    for name in given_names:
        for m in re.finditer(rf"(?<!\w){re.escape(name)}(?!\w)", context, re.IGNORECASE):
            gap = max(start - m.end(), m.start() - end, 0)
            # Decays to ~0 past 80 chars -- roughly one sentence in translated
            # web-fiction prose (measured informally against RI's short-clause
            # style, HANDOFF's "short-clause scene" naming convention).
            best = max(best, math.exp(-gap / 40.0))
    return best if best > 0.0 else 0.0


# ---------------------------------------------------------------------------
# 2. Role/title collocation
# ---------------------------------------------------------------------------

#: Rank and role markers this corpus actually uses for sibling/clan
#: disambiguation (grepped from EVOLUTION's own worked examples and the
#: hardcases gold notes -- "eldest," "second," "the hunter," "the tribute
#: disciple" -- rather than written from intuition, per Section 3's rule).
_ROLE_MARKERS: tuple[str, ...] = (
    "eldest", "second", "third", "fourth", "fifth", "sixth", "youngest",
    "elder brother", "younger brother", "elder sister", "younger sister",
    "hunter", "tribute disciple", "gu master", "elder", "young master",
)


def role_collocation_match(context: str, candidate_role_tags: Iterable[str]) -> float | None:
    """Whether a role/rank word attested for this specific candidate appears nearby.

    Distinguishes siblings by function in the scene rather than by name at
    all -- "the second brother" and "the hunter" pick out different Wangs
    even when neither is ever named in the passage. `candidate_role_tags`
    is meant to be populated the same way `EntityProfile.context_terms`
    already is: accumulated from `_ROLE_MARKERS` seen co-occurring with a
    *disambiguated* (already-linked) mention of that candidate earlier in
    the volume, not hand-curated per character.
    """
    tags = {t.casefold() for t in candidate_role_tags if t}
    if not context or not tags:
        return None
    lowered = context.casefold()
    hits = [marker for marker in _ROLE_MARKERS if marker in tags and marker in lowered]
    return 1.0 if hits else 0.0


# ---------------------------------------------------------------------------
# 3. Relationship-neighbor overlap
# ---------------------------------------------------------------------------


def relationship_neighbor_overlap(
    context_names: Iterable[str], candidate_neighbors: Iterable[str]
) -> float | None:
    """Jaccard overlap between who else is in this scene and who this candidate is known to interact with.

    Each Wang sibling in this corpus keeps company with a distinct subset of
    the cast (one runs with Fang Yuan's hunting party, another only ever
    appears next to the clan elders). `context_names` is whatever other
    capitalized surface forms retrieval/NER already found in the same
    context window -- no new extraction needed, since `EvidenceContext`
    already threads `co_present` for the co-presence blocker. Reuses that
    plumbing rather than adding a new one, per Section 3's "don't add a
    third mechanism" convention (data pipeline read there, applied here to
    features).
    """
    ctx = {c.casefold() for c in context_names if c}
    neighbors = {n.casefold() for n in candidate_neighbors if n}
    if not ctx or not neighbors:
        return None
    shared = ctx & neighbors
    union = ctx | neighbors
    return len(shared) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# 4. Recency-decayed last confirmed mention
# ---------------------------------------------------------------------------


def recency_decayed_last_mention(
    mention_chapter: float, candidate_last_chapter: float, *, half_life_chapters: float = 3.0
) -> float:
    """Favors whichever same-surname candidate the narrative was most recently attending to.

    Web-fiction scenes in this corpus tend to hold one clan member's
    thread for several consecutive chapters before cutting to a sibling
    ("the six-Wang" pattern is introduced once, then one Wang carries the
    next few chapters' scenes) -- so recency is a real, if weak, prior on
    *which* same-surname candidate a fresh bare mention continues. Distinct
    from `first_attested_soft_prior`, which only ever penalises a candidate
    whose *first* sighting postdates the mention; this instead rewards
    whichever candidate's *most recent* sighting is closest, so it can favor
    a candidate introduced chapters ago over one introduced yesterday if the
    scene has moved back to the older one.

    Always defined (never `None`) since every retrieved candidate has been
    observed at least once, unlike the context-dependent features above.
    """
    gap = max(0.0, mention_chapter - candidate_last_chapter)
    return 0.5 ** (gap / half_life_chapters)


# ---------------------------------------------------------------------------
# 5. Scene/location co-presence pattern (sharper than `_audience_scope`)
# ---------------------------------------------------------------------------


def scene_location_match(scene_location: str, candidate_locations: Iterable[str]) -> float | None:
    """Whether the candidate has ever been attested at this specific scene location.

    Deliberately keyed to a fine-grained location string (e.g. "the Wang
    family's east courtyard"), not the coarse region/faction tag
    `_audience_scope` already uses -- coarse region is nearly always shared
    by every member of one clan (they all live in the same village), which
    is exactly why `audience_scope_compatibility` was already found not
    discriminative enough to ship (`evidence.py`'s own note: excluded from
    `SCORED_FEATURES`, kept only for diagnostics). This is the same idea at
    a finer grain, which is the only way it could possibly help with a
    same-clan collision specifically.
    """
    locations = {l.casefold() for l in candidate_locations if l}
    if not scene_location or not locations:
        return None
    tag = scene_location.casefold()
    if tag in locations:
        return 1.0
    return 0.0
