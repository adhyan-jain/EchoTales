"""Romanization normalization and translator-handoff detection.

Two related problems, both specific to translated web fiction.

**Romanization drift.** The same name arrives spelled several ways: spacing
("Fang Yuan" / "FangYuan"), hyphenation ("Shi-Cheng" / "Shi Cheng"), diacritics
("Lü" / "Lu"), and apostrophes ("Xi'an" / "Xian"). These are not different
names, and letting them reach the resolver as distinct surface forms wastes the
evidence budget on a problem that a normalisation pass solves outright.

**Translator handoffs.** Long fan translations change hands. When they do, a
large batch of names re-romanises simultaneously at a chapter boundary. That
looks, to an entity resolver, exactly like a cast of new characters arriving at
once -- which is why it is detected explicitly and reported rather than left
for Phase 6 to be confused by.

The normalised form is a *matching key*, never a display form. The original
surface string is always what gets stored and shown; normalisation only decides
whether two strings should be compared as the same name.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from echotales.core.store import Store

# Honorifics and rank prefixes that attach to names in these genres. Stripped
# only when building a *comparison* key -- the resolver still scores the full
# surface form, because "Elder Wang" and "Wang" carry different evidence.
# Owner 2026-11-26: known narrative markers used for a comparison key only, not the semantic name recogniser.
# Do not extend the honorific lists as a substitute for model-backed NER.
_HONORIFIC_PREFIXES = (
    "elder",
    "senior",
    "junior",
    "master",
    "grandmaster",
    "young master",
    "young miss",
    "lady",
    "lord",
    "sir",
    "miss",
    "mister",
    "mr",
    "mrs",
    "ms",
    "uncle",
    "aunt",
    "brother",
    "sister",
    "patriarch",
    "matriarch",
    "sect master",
    "peak lord",
    "hall master",
    "grand elder",
    "supreme elder",
    "first seat",
    "first elder",
    # Western ranks and nicknames (LOTM, 2026-09-27): "Old Neil" (128
    # mentions) and "Neil" (15), "Senior Associate Professor Quentin Cohen"
    # and "Quentin Cohen", "King George III" and "George III" each resolved as
    # two people because only Chinese-genre ranks were stripped.
    "old",
    "king",
    "queen",
    "prince",
    "princess",
    "professor",
    "associate professor",
    "assistant professor",
    "doctor",
    "dr",
    "captain",
    "madam",
)

_HONORIFIC_SUFFIXES = (
    "-san",
    "-sama",
    "-kun",
    "-chan",
    "-senpai",
    "-shi",
    "-nim",
    "-ssi",
    "-ge",
    "-jie",
    "-di",
    "-mei",
)

# An optional trailing period is essential, not cosmetic: abbreviated titles
# are written "Mr. Fool", so a pattern demanding `mr\s+` never fires and every
# abbreviated form silently fails to normalise. That split "Mr. Fool" from
# "Fool" while "Miss Justice" (no period) collapsed correctly -- an
# inconsistency that is very hard to spot by eye.
_PREFIX_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(h.rstrip(".")) for h in sorted(_HONORIFIC_PREFIXES, key=len, reverse=True))
    + r")\.?\s+",
    re.IGNORECASE,
)

# Leading determiners. Stripped for *matching* only. Alias typing still sees
# the raw surface, where article-led-ness is what separates an epithet
# ("the Crimson Emperor") from a generic descriptor ("the innkeeper") -- so
# removing it here does not weaken that distinction.
_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

_SUFFIX_RE = re.compile(
    r"(?:" + "|".join(re.escape(s) for s in _HONORIFIC_SUFFIXES) + r")$",
    re.IGNORECASE,
)

_PUNCT = re.compile(r"['’\-–—.·]")
_WS = re.compile(r"\s+")


def strip_diacritics(text: str) -> str:
    """Fold accented characters to ASCII: "Lü" -> "Lu"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_romanization(name: str) -> str:
    """Build a comparison key for a name.

    Folds case, diacritics, internal punctuation and whitespace, so that
    "Shi-Cheng", "Shi Cheng" and "ShiCheng" collapse together.

    Note this removes *all* spacing, which is aggressive on purpose: Chinese
    given names are romanised with inconsistent word breaks and the spacing
    carries no information. It would be wrong for European names, so this is
    applied per-source rather than globally.
    """
    text = strip_diacritics(name).casefold()
    text = _PUNCT.sub("", text)
    text = _WS.sub("", text)
    return text


@lru_cache(maxsize=65536)
def strip_honorifics(name: str, *, strip_articles: bool = False) -> str:
    """Remove leading rank prefixes and trailing honorific suffixes.

    Applied repeatedly, since stacked honorifics ("Senior Brother Wang") are
    ordinary in this genre.

    `strip_articles` additionally removes a leading determiner. Off by default
    because the raw article matters to alias typing; on for comparison keys,
    where "The Justice" and "Miss Justice" must reach the same key.
    """
    text = name.strip()
    changed = True
    while changed:
        changed = False
        for pattern in (_PREFIX_RE, _SUFFIX_RE) + ((_ARTICLE_RE,) if strip_articles else ()):
            stripped = pattern.sub("", text)
            if stripped != text:
                text, changed = stripped, True
    return text.strip()


#: Possessive suffixes, straight and curly. Both occur in the same volume.
_POSSESSIVE_RE = re.compile(r"['’]s\b|s['’]$", re.IGNORECASE)


#: Footnote markers a translator glues to the last letter of a name ("Dokja¹", "Reader-nim³"; also plain digits,
#: "Sangah-ssi2"). The superscripts are alphanumeric to `str.isalnum`, so they also made the gazetteer refuse "Dokja"
#: in "Dokja¹" as a fragment of a longer word.
_SUPERSCRIPTS = "\u00b2\u00b3\u00b9\u2070\u2074\u2075\u2076\u2077\u2078\u2079"
FOOTNOTE_MARK_AT = re.compile(rf"(?:[{_SUPERSCRIPTS}]+|\d{{1,3}})(?!\w)")
_FOOTNOTE_TAIL = re.compile(rf"(?<=[^\W\d_])(?:[{_SUPERSCRIPTS}]+|\d+)$")
_POSSESSIVE_TAIL = re.compile(r"['’]s$", re.IGNORECASE)


def strip_name_tail(surface: str) -> str:
    """A detected name span without the possessive `'s` / `’s` and glued footnote markers that rode along.

    GLiNER and spaCy return the clitic with the name: "Fang Zhi’s" became the surface of RI's Fang Zhi (2 mentions),
    so the entity existed only as a broken form; the same pass kept "Yoo Sangah-ssi²" and "Reader-nim³" on ORV. The
    footnote rule needs a capitalised last word glued to the digits, so "tls123" (a username) and "Rank 5" are left
    alone. Both curly and straight apostrophes, as `strip_morphology` already does for matching.
    """
    out = surface.rstrip()
    while True:
        prev = out
        out = _POSSESSIVE_TAIL.sub("", out)
        last = out.rsplit(None, 1)[-1] if out else ""
        if last[:1].isupper():
            out = _FOOTNOTE_TAIL.sub("", out)
        if out == prev:
            return out


def strip_morphology(name: str, *, plural: bool = True) -> str:
    """Remove possessive and plural inflection.

    Without this, "<name>" and "<name>'s" become two entities. Measured on one
    volume that cost 121 redundant entities, including the protagonist's
    possessive form accumulating 863 mentions of its own.

    Plural stripping is applied only to multi-character stems and never when
    the result would collide with a shorter distinct name, because English
    plural `-s` is indistinguishable from a name that simply ends in `s`.
    """
    text = _POSSESSIVE_RE.sub("", name).strip()
    # Only strip a trailing plural when the stem is long enough that the `s`
    # is unlikely to be part of the name itself.
    if plural and len(text) > 4 and text.endswith(("s", "S")) and not text.endswith(("ss", "us", "is")):
        text = text[:-1]
    return text.strip()


def display_label(surfaces: Iterable[str]) -> str:
    """Pick the label an entity is shown and exported under.

    `comparison_key` is deliberately lossy — it exists to make two forms *meet*,
    not to be read. Labelling an entity from the raw longest surface instead
    means the possessive wins whenever it is the longest variant, which is how
    "<name>'s" ends up at the top of the review table as though it were a
    separate character.

    So: strip the inflection and a leading article for display, but keep
    honorifics and clan prefixes — those carry information a reader auditing the
    graph wants, and unlike inflection they are not noise.
    """
    # Longest wins, tie-broken toward a form that needed no cleaning, so a
    # surface that occurs verbatim in the text beats a reconstructed one.
    # Possessives are always dropped; a trailing "s" only when the shorter form is itself a surface in the text. The
    # plural strip is right for matching ("the Bennets" and "Bennet" meet) but displayed alone it turned James into
    # "Jame", Lucas into "Luca" and Charles into "Charle" (Pride and Prejudice cast, 2026-10-31).
    pairs = [
        (surface, cleaned)
        for surface in surfaces
        if (cleaned := _ARTICLE_RE.sub("", strip_morphology(surface, plural=False)).strip())
    ]
    present = {cleaned for _, cleaned in pairs}
    ranked = []
    for surface, cleaned in pairs:
        shorter = strip_morphology(cleaned)
        shown = shorter if shorter in present else cleaned
        ranked.append((len(shown), shown == surface.strip(), shown))
    return max(ranked)[2] if ranked else ""


def comparison_key(name: str) -> str:
    """The key two surface forms are compared under.

    Strips, in order: honorifics and articles, then possessive and plural
    inflection, then romanisation variance. In this corpus a single referent is
    routinely written "The X", "Mr. X", "Miss X", "X's" and bare "X" — treating
    those as five entities is a large and silent source of over-splitting.
    """
    base = normalize_romanization(strip_morphology(strip_honorifics(name, strip_articles=True)))
    if base in _family_tokens and (title := _family_title(name)):
        return f"{title}:{base}"
    return base


#: Words that are never a person's name however they are capitalised: pronouns, their contractions and
#: interjections. The heuristic detector made "I'm" LotM's second-most-mentioned entity (557 mentions) and "Hahaha" a
#: mention, and the speaker regex stored "I've"/"I'd" as speakers (LotM 14, ORV 33).
_PRONOUNS = frozenset({
    "i", "me", "my", "mine", "myself", "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "it", "its",
    "we", "us", "our", "ours", "they", "them", "their", "theirs", "who", "whom", "what", "this", "that", "these",
    "those",
})
_PRONOUN_CONTRACTION = re.compile(
    r"^(?:i|you|he|she|it|we|they|that|there|here|who|what|let)['’](?:m|re|s|d|ve|ll)$", re.IGNORECASE
)
_INTERJECTIONS = frozenset({
    "oh", "ah", "aha", "ahh", "ohh", "hmm", "hm", "hmph", "huh", "eh", "uh", "um", "ugh", "wow", "hey", "ha", "hah",
    "oops", "alas", "yay", "tsk", "yes", "no", "okay", "ok",
})
_LAUGHTER = re.compile(r"^(?:h[aeo]h?){2,}$", re.IGNORECASE)


def non_name_reason(surface: str) -> str | None:
    """Why a surface can never be a person's name, or None. One predicate for mentions, entities and speakers.

    A bare title ("Mr", "Mr.") is no name either: the speech-tag regex stopped at the abbreviation's period and stored
    "Mr" for "said Mr. Bennet" (Pride and Prejudice: 50 of 1,992 quoted spans)."""
    text = surface.strip().strip(".,;:!?\"“”")
    folded = text.casefold()
    if not folded:
        return "empty"
    if folded in _PRONOUNS or _PRONOUN_CONTRACTION.match(text):
        return "pronoun"
    if folded in _INTERJECTIONS or _LAUGHTER.match(text):
        return "interjection"
    if folded in {h.casefold() for h in _HONORIFIC_PREFIXES}:
        return "bare_title"
    return None


def honorific_title_pattern() -> str:
    """Regex alternation of the single-word titles, capitalised, for speech-tag patterns."""
    words = sorted({h.title() for h in _HONORIFIC_PREFIXES if " " not in h}, key=len, reverse=True)
    return "|".join(re.escape(w) for w in words)


#: Titles that, after a family name, tell members of one family apart (Mr., Mrs., Miss and Lady Bennet are four
#: people). Not the ranks of a cultivation hierarchy ("Elder", "Senior Brother"), which never are.
_FAMILY_TITLES = frozenset({"mr", "mrs", "miss", "ms", "master", "madam", "lady", "lord", "sir"})

#: Name tokens this book uses as family names, set per novel by `refresh_family_tokens` (a process-wide value because
#: `comparison_key` is called from a dozen modules that have no novel in hand; the job queue runs one job at a time).
_family_tokens: frozenset[str] = frozenset()


def _title_and_token(surface: str) -> tuple[str, str] | None:
    """("mr", "Bennet") for "Mr. Bennet" / "Mr Bennet's"; None unless it is exactly one title and one word."""
    words = _ARTICLE_RE.sub("", surface.strip()).replace(".", " ").split()
    if len(words) == 2 and words[0].casefold() in _FAMILY_TITLES:
        return words[0].casefold(), words[1]
    return None


def _family_title(surface: str) -> str:
    parsed = _title_and_token(surface)
    return parsed[0] if parsed else ""


def set_family_tokens(tokens: Iterable[str]) -> None:
    global _family_tokens
    _family_tokens = frozenset(tokens)


def derive_family_tokens(surfaces: Iterable[str]) -> frozenset[str]:
    """Which name tokens are family names, from the surfaces the book itself uses.

    After a surname the title says who: "Mr. Bennet", "Mrs. Bennet" and "Miss Bennet" are a husband, a wife and a
    daughter, and stripping the title merged them (Pride and Prejudice: Mrs. Bennet voiced as Mr. Bennet). After a
    first name or a codename it says nothing: "Mr. Fool" and "Fool" are one person (Lord of the Mysteries). The text
    tells the two apart: a token that appears under two different titles is a family name, and "Fool" never does."""
    titles: dict[str, set[str]] = {}
    for surface in surfaces:
        parsed = _title_and_token(surface)
        if parsed is not None:
            token = normalize_romanization(strip_morphology(strip_honorifics(parsed[1])))
            titles.setdefault(token, set()).add(parsed[0])
    return frozenset(token for token, seen in titles.items() if token and len(seen) >= 2)


def refresh_family_tokens(store: object, novel_id: str) -> frozenset[str]:
    """Derive this novel's family tokens from its detected mentions and make `comparison_key` use them.

    Called at the start of every stage that compares names. A database with no mentions yet (before detection) has no
    family tokens, so keys are exactly what they were."""
    rows = store.conn.execute(  # type: ignore[attr-defined]
        "SELECT DISTINCT text FROM mention WHERE novel_id=?", (novel_id,)
    ).fetchall()
    tokens = derive_family_tokens(r[0] for r in rows)
    set_family_tokens(tokens)
    return tokens


def name_containment(
    a: str, b: str, *, ambiguous_tokens: frozenset[str] | None = None, given_name_first: bool = False
) -> float:
    """Evidence that one name is the other with a leading name component dropped.

    In this corpus a character is written "Gu Yue Mo Bei" on introduction and
    "Mo Bei" thereafter. Character-level similarity cannot see that: Jaro-Winkler
    is prefix-weighted, so the two score around 0.5 and fall under the
    similarity floor, and the pair becomes two entities. Measured on 40 chapters
    of the primary novel that was three duplicated characters out of 39.

    **The >= 2-token case** (house-prefixed names, e.g. "Gu Yue Mo Bei" ->
    "Mo Bei") needs no corpus knowledge: the shared part is required to be
    **at least two tokens**, and that is the whole safety property (Section 4.5
    restated) — a shared *single* token is usually a bare surname, which
    identifies a *family* rather than a person, so "Elder Wang" and
    "Xiao Wang" must not merge on the strength of "Wang" alone. No clan list
    is involved — the rule is structural and transfers to a novel whose
    houses this code has never seen.

    **The 1-token case** (a dropped given name, e.g. Korean family-name-first
    "Kim Dokja" -> "Dokja", Section 4.15) is the same shape wearing the opposite
    risk: here the *specific* component is the one that survives, and the
    *ambiguous* one (the surname, "Kim") is what's dropped. The 2-token floor
    alone can't tell these apart by token count -- it needs to know which
    component is actually ambiguous *in this novel's cast*. `ambiguous_tokens`
    supplies that: a lowercased token attested as a name component across two
    or more distinct entities (built by the caller from the corpus's own
    profiles — see `resolve/runner.py`). A single surviving token is treated
    as a genuine dropped-given-name match only when it is *not* itself one of
    those ambiguous components — i.e. it uniquely identifies one entity in
    this cast, the same property "Dokja" has and "Wang" does not. Callers
    that don't supply `ambiguous_tokens` (the default, `None`) get the old,
    strictly-2-token-or-nothing behaviour — a caller-supplied *empty*
    frozenset is a real answer ("this corpus has no ambiguous components")
    and is not the same thing as `None` ("this caller has no opinion").

    **Name order.** Everything above assumes the family name comes first, so
    the surviving short form is the *tail*. A Western-order novel (LOTM:
    "Klein Moretti", then "Klein" for the next 400 mentions) shortens to the
    *head*, and the suffix rule split every such character in two -- Klein,
    Dunn, Audrey and Alger on LOTM ch1-20 (2026-09-27). `given_name_first`
    (from `sources.toml`'s `name_order`) flips which end must match; the
    one-token ambiguity guard is unchanged, so a bare surname shared by a
    family ("Moretti") still merges no one.

    Returns 0.0 when the containment does not hold, so callers can `max()` it
    against a character-level score without diluting either.
    """
    short, long_ = sorted((name_tokens(a), name_tokens(b)), key=len)
    if not short or len(short) == len(long_):
        return 0.0
    # The shorter form must be a **suffix**, not merely a substring. In this
    # naming convention the house/surname comes first and the personal name
    # last, so the form that survives abbreviation is the tail. Requiring a
    # suffix is what stops the clan name itself — "Gu Yue", also two tokens —
    # from matching every one of its members and merging the whole family.
    kept = long_[: len(short)] if given_name_first else long_[-len(short) :]
    if kept != short:
        return 0.0
    if len(short) == 1:
        if ambiguous_tokens is None or short[0] in ambiguous_tokens:
            return 0.0
    # Confidence falls as the dropped prefix grows: sharing 2 of 3 tokens is
    # stronger evidence than sharing 2 of 6.
    return 0.80 + 0.15 * (len(short) / len(long_))


def name_tokens(name: str) -> list[str]:
    """Lowercase-comparable name components, for both `name_containment` and
    corpus-wide token-ambiguity tables built from `EntityProfile.aliases`.

    Memoised (a fresh list per call): `name_containment` retokenised the same few thousand
    aliases per candidate per group, 19 s of a 57 s ORV ch1-40 run. Depends only on module
    constants, not on `_family_tokens` (unlike `comparison_key`, deliberately not cached)."""
    return list(_name_tokens(name))


@lru_cache(maxsize=65536)
def _name_tokens(name: str) -> tuple[str, ...]:
    return tuple(
        token.casefold()
        for raw in strip_morphology(strip_honorifics(name)).split()
        if (token := normalize_romanization(raw))
    )


@lru_cache(maxsize=65536)
def token_set_key(name: str) -> str:
    """Order-insensitive name key: "Gojo Satoru" and "Satoru Gojo" meet.

    **A retrieval feature, never an identity test.** Equal keys only mean "worth scoring
    against each other": two different people can share a token set ("Wang Li" / "Li Wang"
    are both ordinary names), so no code may link, merge or assign on this equality; the
    evidence gate decides (non-negotiables #1 and #9). Honorifics and inflection are
    stripped as in `comparison_key`; per-token folding is `normalize_romanization`."""
    return " ".join(sorted(_name_tokens(name)))


#: Vowel digraphs and consonant clusters that differ between romanisation schemes of one sound,
#: applied in order. Deliberately tiny: each rule is a generic alternation seen between Hangul
#: (RR / McCune-Reischauer / ad hoc: "Yoo"/"Yu", "Joong"/"Jung", "hyeok"/"hyuk") or Chinese
#: (pinyin / Wade-Giles: "Xiao Yan"/"Hsiao Yen") romanisations, not a name list.
_SKELETON_RULES: tuple[tuple[str, str], ...] = (
    ("hs", "x"),
    ("ch", "j"),
    ("eo", "u"),
    ("oo", "u"),
    ("ou", "u"),
    ("ee", "i"),
)
_VOWELS = re.compile(r"[aeiou]+")
_REPEAT = re.compile(r"(.)\1+")
#: Under this length the skeleton is too lossy to retrieve on ("Li" -> "l" would pull in every L-name).
_MIN_SKELETON = 3


@lru_cache(maxsize=65536)
def romanization_skeleton(name: str) -> str:
    """Lossy consonant skeleton for alternate romanisations; "" when too short to be useful.

    Yoo Joonghyuk / Yu Jung-hyeok -> "yjnghyk" and Xiao Yan / Hsiao Yen -> "xyn" on both
    sides. It also equates distinct names that differ only in vowels ("Wen"/"Wan"), so it is a
    **recall-only retrieval signal**: it may add a candidate for scoring, never a link, and
    `comparison_key` is untouched. Spacing is dropped (as in `comparison_key`), so unlike
    `token_set_key` it is name-order sensitive."""
    text = normalize_romanization(strip_morphology(strip_honorifics(name, strip_articles=True)))
    for old, new in _SKELETON_RULES:
        text = text.replace(old, new)
    text = _REPEAT.sub(r"\1", _VOWELS.sub("", text))
    return text if len(text) >= _MIN_SKELETON else ""


def are_variants(a: str, b: str) -> bool:
    """Whether two surface forms are romanization variants of one name."""
    return bool(a and b) and comparison_key(a) == comparison_key(b)


# ---------------------------------------------------------------------------
# Translator handoff detection
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class HandoffReport:
    """A chapter boundary where the translation appears to change hands."""

    chapter: float
    changed_forms: int
    detail: str
    #: old surface form -> new surface form, for the confirmation prompt.
    mapping: dict[str, str]


_CAPITALISED = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")

# Words that are capitalised for position rather than because they are names.
_STOPWORDS = frozenset(
    {
        "The", "A", "An", "He", "She", "It", "They", "We", "You", "I", "His", "Her",
        "But", "And", "Or", "If", "When", "After", "Before", "This", "That", "These",
        "Those", "There", "Then", "However", "Although", "Because", "While", "Chapter",
    }
)


def _candidate_names(text: str, limit: int = 400) -> Counter[str]:
    """Rough proper-noun frequency for a chapter.

    Capitalisation-based and deliberately crude -- this runs before NER and
    only needs to detect a *mass* shift in spelling, not to identify entities.
    """
    counts: Counter[str] = Counter()
    for match in _CAPITALISED.finditer(text):
        token = match.group(0)
        if token.split()[0] in _STOPWORDS:
            continue
        if len(token) < 3:
            continue
        counts[token] += 1
        if len(counts) > limit * 4:
            break
    return counts


def detect_translator_handoffs(
    store: Store,
    novel_id: str,
    *,
    min_changed: int = 20,
    window: int = 5,
) -> list[HandoffReport]:
    """Find chapter boundaries where many surface forms re-romanise at once.

    The signal is a batch of names that vanish and are simultaneously replaced
    by romanization variants of themselves. One name changing is noise; twenty
    changing together at a single boundary is a new translator.

    `min_changed` follows docs/design/plans.md Section 6 Phase 0 (20+ simultaneous changes).
    """
    chapters = list(store.iter_chapters(novel_id))
    if len(chapters) < window * 2:
        return []

    reports: list[HandoffReport] = []
    for i in range(window, len(chapters) - window):
        before: Counter[str] = Counter()
        after: Counter[str] = Counter()
        for ch in chapters[i - window : i]:
            before.update(_candidate_names(ch.story_text))
        for ch in chapters[i : i + window]:
            after.update(_candidate_names(ch.story_text))

        vanished = {n for n in before if n not in after and before[n] >= 2}
        appeared = {n for n in after if n not in before and after[n] >= 2}
        if not vanished or not appeared:
            continue

        # Pair each vanished form with an appeared form that normalises the
        # same way. Unpaired changes are ordinary cast turnover, not a handoff.
        appeared_by_key: dict[str, str] = {comparison_key(n): n for n in appeared}
        mapping = {
            old: appeared_by_key[key]
            for old in vanished
            if (key := comparison_key(old)) in appeared_by_key
        }

        if len(mapping) >= min_changed:
            reports.append(
                HandoffReport(
                    chapter=chapters[i].number,
                    changed_forms=len(mapping),
                    detail=f"{len(mapping)} surface forms re-romanised simultaneously",
                    mapping=mapping,
                )
            )

    # Collapse neighbouring detections: one handoff triggers several adjacent
    # windows, and reporting each would misstate how many there were.
    deduped: list[HandoffReport] = []
    for report in reports:
        if deduped and report.chapter - deduped[-1].chapter <= window:
            if report.changed_forms > deduped[-1].changed_forms:
                deduped[-1] = report
            continue
        deduped.append(report)
    return deduped
