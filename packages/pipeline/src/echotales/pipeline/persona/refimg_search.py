"""Reference-image candidate search for a named character.

Finds *candidates*, never a single answer. This module is deliberately
inert on its own -- it returns `RefImageCandidate` rows with `selected`
always False and never touches persona/prompt/render tables. Turning a
selected candidate into generation conditioning (IP-Adapter or similar) is
explicitly a separate, not-yet-built step; see HANDOFF 4.47 for why an
*automatically selected single reference image* contaminated renders and
was removed, and `core/models.py::RefImageCandidate` for why this table
exists without repeating that.

Network access is injected (`SearchBackend`), same pattern as
`persona/wiki_canon.py::fetch`: the default backend does a real HTTP call,
but every caller can substitute a fixture backend, and a run with no
connectivity degrades to "no candidates found" rather than failing the
pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 5


@dataclass(frozen=True)
class RawHit:
    """One search result, before it is turned into a stored candidate."""

    source_url: str
    thumbnail_url: str = ""
    title: str = ""
    source_page: str = ""


class SearchBackend(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list[RawHit]: ...


class DuckDuckGoImageBackend:
    """Best-effort image search against DuckDuckGo's public `i.js` endpoint.

    Unofficial and undocumented as an API, but it needs no key and no
    account, which is what makes it usable at all inside this pipeline --
    every keyed image-search API (Bing, Google CSE, SerpAPI) requires
    credentials this environment does not have. DuckDuckGo's flow is two
    requests: an HTML search page yields a `vqd` token, then `i.js` is
    queried with that token for the actual image hits. Both requests are
    real network calls, not stubs; a network failure here degrades to an
    empty candidate list (logged), never an exception the caller has to
    handle specially -- same contract as `wiki_canon.fetch`.
    """

    name = "duckduckgo-images"

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    def _get(self, url: str) -> str:
        req = urllib.request.Request(url, headers=self._HEADERS)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def search(self, query: str, max_results: int) -> list[RawHit]:
        try:
            html = self._get(
                "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
            )
            m = re.search(r"vqd=['\"]?([\d-]+)['\"]?", html)
            if not m:
                # DuckDuckGo occasionally serves the token from a different
                # page shape; fall back to the dedicated token endpoint.
                token_html = self._get(
                    "https://duckduckgo.com/?q=" + urllib.parse.quote(query)
                )
                m = re.search(r"vqd=['\"]?([\d-]+)['\"]?", token_html)
            if not m:
                log.warning("refimg_search: no vqd token for query %r", query)
                return []
            vqd = m.group(1)
            js_url = (
                "https://duckduckgo.com/i.js?q="
                + urllib.parse.quote(query)
                + f"&vqd={vqd}&o=json&p=1"
            )
            payload = json.loads(self._get(js_url))
        except Exception as exc:
            log.warning("refimg_search: DuckDuckGo lookup failed for %r: %s", query, exc)
            return []

        hits: list[RawHit] = []
        for item in payload.get("results", [])[:max_results]:
            hits.append(
                RawHit(
                    source_url=item.get("image", ""),
                    thumbnail_url=item.get("thumbnail", ""),
                    title=item.get("title", ""),
                    source_page=item.get("url", ""),
                )
            )
        return [h for h in hits if h.source_url]


def default_backend() -> SearchBackend:
    return DuckDuckGoImageBackend()


def build_query(novel_title: str, character_label: str) -> str:
    """Anchor the query on the novel, not just the character name.

    A bare character name collides across fandoms constantly (protagonists
    are disproportionately named things like "Yuan" or "Feng"); pairing it
    with the novel title is the cheapest precision gain available and is
    still not a guarantee -- see the verification notes in HANDOFF for
    which results still needed a human "wrong series" flag anyway.
    """
    return f"{character_label} {novel_title} character art"


def search_candidates(
    novel_id: str,
    novel_title: str,
    self_id: str,
    character_label: str,
    *,
    backend: SearchBackend | None = None,
    max_results: int = DEFAULT_MAX_RESULTS,
    query: str | None = None,
):
    """Search for reference-image candidates for one character.

    Returns `RefImageCandidate` objects with `selected=False` -- this
    function only finds and shapes results, it never writes to the store
    and never selects anything. Callers that want them persisted call
    `store.add_ref_image_candidate` on each (see
    `persona/refimg.py::search_and_store` for the CLI path that does both).
    """
    from echotales.core.models import RefImageCandidate

    backend = backend or default_backend()
    query = query or build_query(novel_title, character_label)
    hits = backend.search(query, max_results)
    found_at = time.time()

    candidates = []
    for i, hit in enumerate(hits[:max_results]):
        digest = hashlib.sha1(hit.source_url.encode()).hexdigest()[:10]
        candidates.append(
            RefImageCandidate(
                id=f"{self_id}:{backend.name}:{digest}",
                novel_id=novel_id,
                self_id=self_id,
                character_label=character_label,
                source_url=hit.source_url,
                thumbnail_url=hit.thumbnail_url,
                title=hit.title,
                source_page=hit.source_page,
                query=query,
                backend=backend.name,
                found_at=found_at + i * 1e-6,  # stable, monotonic tie-break
                user_uploaded=False,
                selected=False,
            )
        )
    return candidates
