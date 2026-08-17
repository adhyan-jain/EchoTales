"""Character appearance pulled from a novel's fandom wiki.

`canon.py` states the case for hand-authored canon: a reader beats an
extractor, because extraction can only report what the sampled sentences
happened to say, and for a novel's most recognisable characters that is a
poor substitute for what a reader already knows. The weakness of that table
is that a human has to type it, one character at a time, and a 199-chapter
novel has hundreds of named characters.

A fandom wiki is the same knowledge already written down by readers. This
module fetches it and fills the same slots (`appearance_extract.
APPEARANCE_KEYS`), so a wiki-sourced trait is indistinguishable downstream
from a hand-typed one -- except in precedence, where it sits between the
two: **hand-authored canon > wiki > extraction**. A person who edited the
table meant it; a wiki is written by many hands and can be wrong or stale;
extraction is a guess from a handful of sentences.

**Spoilers are the real hazard, and the containment is structural.** The
graph is bitemporal precisely so chapter 1 does not know chapter 500 -- and
a wiki page knows the whole novel, opening with the character's eventual
title and fate. Two rules keep that out:

1. Only the appearance/description sections are read. Plot, History and
   Relationships are discarded unparsed, and those are where the spoilers
   live.
2. Every imported trait is dated to the character's *first appearance*
   chapter, never to chapter 0, so a query positioned before that point
   does not see it.

Network access is injected (`fetch`), never imported: the tests run the
whole parse path against fixture text with no network, and a run without
connectivity degrades to "no wiki canon" rather than failing the pipeline.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import quote

log = logging.getLogger(__name__)

#: novel_id -> fandom wiki subdomain. Adding a novel is one line; a novel
#: absent from here simply has no wiki canon, which is not an error.
WIKI_SOURCES: dict[str, str] = {
    "reverend-insanity": "reverend-insanity",
    "lord-of-the-mysteries": "lordofthemysteries",
    "omniscient-readers-viewpoint": "omniscient-readers-viewpoint",
}

#: Section headings worth reading. Everything else on the page is skipped
#: without being parsed -- see the module docstring on spoilers.
_WANTED_SECTIONS = ("appearance", "description", "physical description", "looks")

#: Section headings that end the wanted region. Listed explicitly rather
#: than "any following heading" because wikis nest sub-headings inside
#: Appearance (e.g. "Appearance == After the rebirth") that should be read.
_SPOILER_SECTIONS = (
    "history",
    "plot",
    "synopsis",
    "story",
    "relationships",
    "abilities",
    "powers",
    "trivia",
    "gallery",
    "references",
    "quotes",
)

#: Identifies this project to the wiki, as MediaWiki etiquette asks. A
#: generic or absent agent is refused outright (403).
USER_AGENT = "EchoTales/0.1 (novel-adaptation pipeline; contact via repository)"

#: Seconds between page requests, and before the single retry. See the loop
#: in `build_wiki_canon` for the measured failure these prevent.
_REQUEST_PAUSE = 0.4
_RETRY_PAUSE = 2.0
#: Retries per page. Fandom's drops are transient and uncorrelated -- a
#: page that fails twice in a row usually succeeds on the third try -- and
#: a lost page is silent, indistinguishable from "no such character".
_RETRIES = 3

_HEADING_RE = re.compile(r"^\s*(={2,6})\s*(?P<title>[^=]+?)\s*\1\s*$", re.MULTILINE)


class WikiFetch(Protocol):
    """Fetches one wiki page's wikitext. Injected so tests never hit the network."""

    def __call__(self, wiki: str, title: str) -> str | None: ...


def api_fetch(wiki: str, title: str, *, timeout: float = 15.0) -> str | None:
    """Fetch a page's raw wikitext through the MediaWiki API.

    Uses `action=raw` rather than the JSON API: it is one request, needs no
    parsing to reach the content, and fandom serves it without a key.
    """
    import urllib.error
    import urllib.request

    url = f"https://{wiki}.fandom.com/wiki/{quote(title.replace(' ', '_'))}?action=raw"
    # **A User-Agent is not optional here.** Fandom answers urllib's default
    # (`Python-urllib/3.x`) with a blanket 403, which looked exactly like
    # "this novel has no wiki" -- every character came back empty.
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT}  # noqa: S310
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # A missing page and an unreachable network are the same thing to
        # the caller: this character has no wiki canon this run.
        log.info("wiki fetch failed for %s/%s: %s", wiki, title, exc)
        return None


_INFOBOX_RE = re.compile(r"\{\{\s*Infobox[ _]?(?P<kind>[A-Za-z ]*)", re.I)
_CATEGORY_RE = re.compile(r"\[\[Category:(?P<name>[^\]|]+)", re.I)

#: Categories and infobox types that mark a page as being about a *person*.
#: "Human" and "Male"/"Female" are here because the RI wiki tags characters
#: that way and does not always give them a Characters category.
_PERSON_MARKERS = frozenset(
    {"character", "characters", "human", "male", "female", "person", "people"}
)


def is_character_page(wikitext: str) -> bool:
    """Whether this page is about a person at all.

    **Entity kind in the graph is not reliable enough to gate on alone.**
    Resolution classified "Iron Skin Gu" and "Stone Skin Gu" as people --
    understandably, since the novel talks about Gu worms the way it talks
    about characters -- and their wiki pages then contributed `skin_tone=
    bronze` to the canon of things that are not characters. The wiki knows
    better than the resolver here: those pages carry `{{Infobox Gu}}` and
    Gu categories, and no person marker anywhere.

    Permissive when the page says nothing either way: a stub with no
    infobox and no categories is more likely a thin character page than a
    mislabelled item, and the trait patterns are conservative regardless.
    """
    markers = {c.strip().casefold() for c in _CATEGORY_RE.findall(wikitext)}
    if markers & _PERSON_MARKERS:
        return True

    infoboxes = {m.strip().casefold() for m in _INFOBOX_RE.findall(wikitext) if m.strip()}
    if infoboxes:
        return bool(infoboxes & _PERSON_MARKERS)
    # No infobox and no person category: only reject if the page is
    # positively categorised as something else.
    return not markers


def appearance_text(wikitext: str) -> str:
    """Just the appearance/description prose, with markup stripped.

    Returns an empty string when the page has no such section, which is the
    common case for minor characters and is not an error.
    """
    headings = list(_HEADING_RE.finditer(wikitext))
    kept: list[str] = []

    for i, heading in enumerate(headings):
        title = heading.group("title").strip().casefold()
        if not any(title.startswith(w) for w in _WANTED_SECTIONS):
            continue
        end = len(wikitext)
        for later in headings[i + 1 :]:
            later_title = later.group("title").strip().casefold()
            # A deeper sub-heading still belongs to this section; a sibling
            # or a spoiler section ends it.
            if len(later.group(1)) > len(heading.group(1)) and not any(
                later_title.startswith(s) for s in _SPOILER_SECTIONS
            ):
                continue
            end = later.start()
            break
        kept.append(wikitext[heading.end() : end])

    if not kept:
        # **Most character pages have no Appearance section at all.** Of RI's
        # top 60 characters only two did; the rest describe the character in
        # the lead paragraph instead ("X is a young man with black hair").
        # The lead is bounded by the first heading, so this reads the
        # description and still never touches Plot or History -- and only
        # typed traits are kept from it either way, so the plot summary a
        # lead often carries is discarded rather than imported.
        lead = wikitext[: headings[0].start()] if headings else wikitext
        kept.append(lead)

    return _strip_markup("\n".join(kept))


def _strip_markup(text: str) -> str:
    """Wikitext -> plain prose, well enough to run keyword patterns over."""
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)          # templates
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]|]*)\]\]", r"\1", text)  # links
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)                  # html
    text = re.sub(r"'{2,}", "", text)                     # bold/italic
    text = re.sub(r"^\s*[*#:;]+", " ", text, flags=re.MULTILINE)
    return re.sub(r"[ \t]+", " ", text).strip()


#: Trait -> the patterns that state it. Deliberately conservative: a pattern
#: that fires on the wrong sentence writes a wrong fact into canon, which
#: then *outranks* the extractor's correct one. Silence is the cheaper error.
_TRAIT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "hair_color": (
        re.compile(
            r"\b(?P<v>jet[- ]black|midnight black|black|white|silver|grey|gray|golden|"
            r"blonde|blond|brown|red|azure|blue|green|purple)\s+hair\b",
            re.I,
        ),
        re.compile(r"\bhair\s+(?:is|was)\s+(?P<v>[a-z][a-z -]{2,20}?)(?:[.,;]|\s+and\b)", re.I),
    ),
    "hair_style": (
        # The texture word between length and "hair" is optional and common
        # ("waist-length straight hair"), so it is matched and skipped
        # rather than blocking the pattern.
        re.compile(
            r"\b(?P<v>(?:waist|shoulder|hip)[- ]length|long straight|long|short|braided|"
            r"tied[- ]up|dishevelled|disheveled)(?:\s+(?:straight|wavy|curly|silky))?"
            r"\s+hair\b",
            re.I,
        ),
    ),
    "eye_color": (
        re.compile(
            r"\b(?P<v>jet[- ]black|black|dark|brown|blue|green|golden|grey|gray|red|"
            r"amber|violet)\s+eyes\b",
            re.I,
        ),
        re.compile(r"\beyes\s+(?:are|were)\s+(?P<v>[a-z][a-z -]{2,20}?)(?:[.,;]|\s+and\b)", re.I),
    ),
    "skin_tone": (
        re.compile(r"\b(?P<v>pale|fair|tan|tanned|dark|olive|bronze)\s+skin\b", re.I),
        re.compile(r"\bskin\s+(?:is|was)\s+(?P<v>[a-z][a-z -]{2,20}?)(?:[.,;]|\s+and\b)", re.I),
    ),
    "height_build": (
        re.compile(r"\b(?P<v>\d{2,3}\s?cm(?:\s+tall)?)\b", re.I),
        re.compile(
            r"\b(?P<v>tall and lean|tall and thin|lean|slender|slim|muscular|burly|"
            r"stocky|petite|short)\b(?=[^.]{0,40}\b(?:build|figure|frame|stature|man|woman)\b)",
            re.I,
        ),
    ),
    "typical_attire": (
        re.compile(
            r"\b(?P<v>(?:black|white|green|blue|red|azure|golden|grey|gray|purple)\s+"
            r"(?:robes?|hanfu|gown|dress|armou?r))\b",
            re.I,
        ),
    ),
}

#: Traits that describe a moment rather than a person. A wiki sentence about
#: a character being wounded in one arc must never become their standing
#: appearance -- the same distinction `appearance_extract.py::TRANSIENT_KEYS`
#: draws, applied at the source here.
_SKIP_KEYS = ("current_condition",)

#: Words the open-ended "hair is X" / "eyes are X" patterns match that are
#: not colours. Measured: Bai Ning Bing's page gave `hair_color=shiny`,
#: which is not wrong about the hair and is useless in a prompt.
_NOT_A_COLOUR = frozenset(
    {
        "shiny", "silky", "long", "short", "straight", "wavy", "curly",
        "messy", "beautiful", "lovely", "thick", "thin", "soft", "smooth",
        "tied", "loose", "neat", "wild",
    }
)


#: How much of an appearance section to read, in characters.
#:
#: **A long appearance section is a chronology, not a description.** Fang
#: Yuan's runs 6,700 characters and covers his original body, a stolen
#: immortal body thousands of chapters later, and a six-metre eight-armed
#: zombie form. Reading all of it would let a late-story body overwrite the
#: one being drawn. Earliest text wins for the same reason a first pattern
#: match wins below: the top of the section describes the character as the
#: reader first meets them, which is where an adaptation starts.
_MAX_APPEARANCE_CHARS = 1200


def parse_appearance(text: str, *, max_chars: int = _MAX_APPEARANCE_CHARS) -> dict[str, str]:
    """Typed appearance attributes stated by this prose."""
    text = text[:max_chars]
    out: dict[str, str] = {}
    for key, patterns in _TRAIT_PATTERNS.items():
        if key in _SKIP_KEYS:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match is None:
                continue
            value = " ".join(match.group("v").split()).strip().lower()
            if key in ("hair_color", "eye_color") and value.split()[0] in _NOT_A_COLOUR:
                continue
            if value and len(value) <= 40:
                out[key] = value
                break
    return out


@dataclass(slots=True)
class WikiCanonReport:
    novel_id: str
    wiki: str = ""
    requested: int = 0
    fetched: int = 0
    with_appearance: int = 0
    traits: int = 0
    entries: dict[str, dict[str, str]] = field(default_factory=dict)
    #: Characters whose page could not be fetched at all -- reported rather
    #: than silently folded into "no appearance", since the two want
    #: different responses (retry the run vs. edit the wiki).
    missing: list[str] = field(default_factory=list)
    #: Pages that exist but are not about people (see `is_character_page`).
    skipped_not_a_character: int = 0

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.with_appearance}/{self.requested} characters "
            f"with wiki appearance ({self.traits} traits) from {self.wiki or 'no wiki'}\n"
            f"  no page found: {len(self.missing)}; "
            f"not a character: {self.skipped_not_a_character}"
        )


def build_wiki_canon(
    novel_id: str,
    labels: list[str],
    *,
    fetch: WikiFetch | Callable[[str, str], str | None] | None = None,
) -> WikiCanonReport:
    """Fetch and parse appearance for each named character."""
    wiki = WIKI_SOURCES.get(novel_id, "")
    report = WikiCanonReport(novel_id=novel_id, wiki=wiki, requested=len(labels))
    if not wiki:
        return report

    fetch = fetch or api_fetch
    for position, label in enumerate(labels):
        # **Fandom drops requests under a fast sequential loop.** Measured:
        # the same Fang Yuan page that fetches fine on its own came back
        # empty inside a 60-character run, and the failure is silent -- it
        # looks exactly like "this character has no page". One retry after a
        # pause recovers it; the pause between requests keeps the run polite
        # enough that the retry is rarely needed.
        if position:
            time.sleep(_REQUEST_PAUSE)
        raw = fetch(wiki, label)
        for attempt in range(_RETRIES):
            if raw:
                break
            time.sleep(_RETRY_PAUSE * (attempt + 1))
            raw = fetch(wiki, label)
        if not raw:
            report.missing.append(label)
            continue
        report.fetched += 1
        if not is_character_page(raw):
            report.skipped_not_a_character += 1
            continue
        traits = parse_appearance(appearance_text(raw))
        if not traits:
            continue
        report.with_appearance += 1
        report.traits += len(traits)
        report.entries[label] = traits
    return report


def canon_path(novel_id: str, *, data_root: str | Path = "data") -> Path:
    """Where this novel's wiki canon is cached.

    Written to disk rather than the graph on purpose: it is *input*, like
    `data/scene-references/`, re-derivable at any time, and keeping it out
    of the store means a bad wiki edit can never corrupt attested facts.
    """
    from echotales.pipeline.paths import novel_root

    return novel_root(novel_id, data_root=Path(data_root)) / "canon" / "wiki-appearance.json"


def save_wiki_canon(report: WikiCanonReport, *, data_root: str | Path = "data") -> Path:
    """Merge this run's entries into the cache.

    **Merged, not overwritten.** Fetches fail per-character and per-run; a
    run that loses Fang Yuan's page to a dropped request must not delete the
    entry a previous run got. Re-fetching a character does replace their
    entry, so a wiki correction still propagates.
    """
    path = canon_path(report.novel_id, data_root=data_root)
    merged = load_wiki_canon(report.novel_id, data_root=data_root)
    merged.update(report.entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_wiki_canon(novel_id: str, *, data_root: str | Path = "data") -> dict[str, dict[str, str]]:
    """Previously fetched wiki canon, or an empty dict.

    Never fetches. A pipeline run must not depend on a network call
    succeeding, so importing is an explicit command and rendering only ever
    reads what that command already wrote.
    """
    path = canon_path(novel_id, data_root=data_root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("unreadable wiki canon at %s: %s", path, exc)
        return {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
