"""Chapter page URL to a folder of page images, for the comic -> motion-comic pipeline (`echotales comic fetch`).

Generic on purpose: no per-site adapters. The page's `<img>` tags are read in document order (plain `src`, the
lazy-load attributes sites use to defer images, `srcset`, `<noscript>` fallbacks), with image URLs inside script/JSON
blobs as a fallback for pages that build the reader in JavaScript. A headless browser (Playwright, optional) can render
and scroll the page when the markup alone has too few images.

What this module will not do, by design: solve CAPTCHAs or challenge pages, log in, replay cookies, get past a
paywall, or descramble protected images. A page that refuses the request, or a chapter that is locked, is reported
as such. Using the downloaded images is the user's responsibility (`source.json` records the user's own rights
confirmation next to the URL).

The Studio calls this from its job queue with a URL typed by whoever can reach the Studio, so every hop is treated as
hostile input:

* http/https only; the host is resolved and every address must be public (`PublicOnlyGuard`), re-checked on every
  redirect hop and for every image URL. Redirects are followed by hand for that reason.
* After connecting, the peer address is checked again, which narrows the window a DNS answer that changes between the
  lookup and the connect (rebinding) would otherwise have. It does not close it entirely: the request line has been
  sent by then, only its response is refused.
* Per-image, total and count caps; every saved file is decoded by Pillow first and named `0001.jpg` by position, never
  from the remote name.

The guard is an argument so a test can reach a local server; there is no environment switch for it, so nothing a Studio
user can set turns it off.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import json
import re
import shutil
import socket
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx
from PIL import Image

from echotales.pipeline.comic.ingest import IMAGE_SUFFIXES, natural_key

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_TOTAL_BYTES = 500 * 1024 * 1024
MAX_IMAGES = 400
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5
#: Narrower than this is a logo, avatar or ad; a webtoon strip or manga page is far wider. Measured on the Pepper & Carrot
#: pages (1,000+ px); sites that serve small thumbnails to browsers still offer a wide original in `srcset`/`data-src`.
MIN_PAGE_WIDTH = 400
#: A tracking pixel or a spacer GIF; no page image is this small once compressed.
MIN_PAGE_BYTES = 1024
#: Height over width below this is a banner strip, not a page.
MIN_ASPECT = 0.3
#: Images this close to the dominant width belong to the chapter; an ad or a related-series cover rarely matches it.
WIDTH_TOLERANCE = 0.10
INSTALL_HINT = (
    "Rendering a page needs Playwright, which is optional and not installed: "
    "pip install playwright && playwright install chromium (or: uv sync --extra browser)"
)
_RETRY_STATUS = {429, 500, 502, 503, 504}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
_PIL_EXT = {"JPEG": "jpg", "MPO": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp"}
_NOISE_NAME = re.compile(
    r"(^|[^a-z])(logo|icon|avatar|favicon|sprite|emoji|spinner|loader|loading|placeholder|blank|pixel|badge)([^a-z]|$)"
)
_NOISE_DIRS = {"avatar", "avatars", "icon", "icons", "emoji", "emojis", "ads", "ad", "adserver", "sprites", "logos"}
_LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-url", "data-lazy", "data-echo")


class FetchError(ValueError):
    """The fetch is refused or failed; the message is plain language, safe to show the person who asked."""


class _TooLarge(Exception):
    pass


# --- SSRF guard --------------------------------------------------------------------------------------------------

class PublicOnlyGuard:
    """Allows a URL only when it is http(s) and every address its host resolves to is a public one."""

    def ip_allowed(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return ip.is_global and not ip.is_multicast

    def _refuse(self, host: str) -> FetchError:
        return FetchError(f"{host} is not allowed: it points at a private, local or reserved address")

    def check_url(self, url: str) -> None:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https"):
            raise FetchError(f"only http and https links are allowed, not {parts.scheme or 'a bare path'}:")
        try:
            host, _ = parts.hostname, parts.port
        except ValueError as exc:
            raise FetchError("that link is not a valid address") from exc
        if not host:
            raise FetchError("that link has no host name")
        if parts.username or parts.password:
            raise FetchError("links with a user name or password in them are not allowed")
        try:
            literals = [ipaddress.ip_address(host)]
        except ValueError:
            try:
                infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
            except OSError as exc:
                raise FetchError(f"could not find the host {host}") from exc
            literals = [ipaddress.ip_address(str(info[4][0]).split("%")[0]) for info in infos]
        if not literals or not all(self.ip_allowed(ip) for ip in literals):
            raise self._refuse(host)

    def check_peer(self, address: str) -> None:
        try:
            ip = ipaddress.ip_address(address.split("%")[0])
        except ValueError:
            return
        if not self.ip_allowed(ip):
            raise self._refuse(address)


_DEFAULT_GUARD = PublicOnlyGuard()


def default_guard() -> PublicOnlyGuard:
    """The guard every real fetch uses; the Studio route checks a link with it before queueing the job."""
    return _DEFAULT_GUARD


# --- HTML extraction ---------------------------------------------------------------------------------------------

def _largest_srcset(value: str) -> str | None:
    best, best_w = None, -1.0
    for item in value.split(","):
        bits = item.strip().split()
        if not bits or bits[0].startswith("data:"):
            continue
        weight = 1.0
        if len(bits) > 1 and bits[1][:-1].replace(".", "", 1).isdigit():
            weight = float(bits[1][:-1])
        if weight > best_w:
            best, best_w = bits[0], weight
    return best


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[str] = []
        self.script_text: list[str] = []
        self.base: str | None = None
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "").strip() for k, v in attrs}
        if tag == "script":
            self._in_script = True
        elif tag == "base" and self.base is None and a.get("href"):
            self.base = a["href"]
        elif tag == "img":
            # An <img> declared tiny (a pixel, an icon) is noise whatever its file is called.
            if any(a.get(d, "").isdigit() and int(a[d]) < 100 for d in ("width", "height")):
                return
            pick = _largest_srcset(a.get("data-srcset") or a.get("srcset") or "")
            for key in _LAZY_ATTRS:
                if not pick and a.get(key) and not a[key].startswith("data:"):
                    pick = a[key]
            if not pick and a.get("src") and not a["src"].startswith("data:"):
                pick = a["src"]
            if pick:
                self.images.append(pick)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.script_text.append(data)


_SCRIPT_ABS = re.compile(r"(?:https?:)?//[^\s\"'<>\\)]+?\.(?:jpe?g|png|webp|gif)(?:\?[^\s\"'<>\\)]*)?", re.I)
_SCRIPT_REL = re.compile(r"[\"'](/[^\"'\s<>\\]+\.(?:jpe?g|png|webp|gif)(?:\?[^\"'\s<>]*)?)[\"']", re.I)


def _looks_like_noise(url: str) -> bool:
    path = urlparse(url).path.lower()
    name = unquote(path.rsplit("/", 1)[-1])
    if path.endswith((".svg", ".ico")) or _NOISE_NAME.search(name):
        return True
    return any(seg in _NOISE_DIRS for seg in path.split("/")[:-1])


def extract_image_urls(html: str, page_url: str) -> list[str]:
    """Absolute image URLs in reading order, deduplicated. Markup first; image URLs found in script/JSON text are used
    only when the markup has fewer than two (a page that builds its reader in JavaScript)."""
    parser = _Page()
    parser.feed(html)
    base = urljoin(page_url, parser.base) if parser.base else page_url
    found = list(parser.images)
    markup = [u for u in dict.fromkeys(urljoin(base, u).split("#")[0] for u in found) if not _looks_like_noise(u)]
    if len(markup) >= 2:
        return markup
    blob = "".join(parser.script_text).replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&")
    in_scripts = [m.group(0) for m in _SCRIPT_ABS.finditer(blob)] + [m.group(1) for m in _SCRIPT_REL.finditer(blob)]
    merged = markup + [u for u in dict.fromkeys(urljoin(base, u).split("#")[0] for u in in_scripts) if not _looks_like_noise(u)]
    return list(dict.fromkeys(merged))


def default_comic_id(url: str) -> str:
    """`example.com-ep-12` from the host and the last path segment: a readable folder name, never from the query."""
    parts = urlparse(url)
    host = (parts.hostname or "comic").removeprefix("www.")
    last = re.sub(r"\.(html?|php|aspx?)$", "", next((s for s in reversed(parts.path.split("/")) if s), ""), flags=re.I)
    raw = f"{host}-{last}" if last else host
    return re.sub(r"[^A-Za-z0-9._-]", "_", raw).lstrip(".")[:80] or "comic"


# --- HTTP --------------------------------------------------------------------------------------------------------

def _status_message(code: int) -> str:
    if code in (401, 403):
        return (
            f"The site refused the request (HTTP {code}). The chapter may need a login or the site may block "
            "automated downloads; this tool does not work around either."
        )
    if code == 404:
        return "Not found (HTTP 404): check the link."
    if code == 429:
        return "The site says there were too many requests (HTTP 429). Try again later or raise the delay."
    return f"The site answered with an error (HTTP {code})."


def _get(
    client: httpx.Client, url: str, *, referer: str | None, guard: PublicOnlyGuard, limit: int,
    retries: int, backoff: float, sleep: Callable[[float], None],
) -> tuple[bytes, str]:
    """GET with manual redirects (each hop guarded), retries on 429/5xx, and a hard byte cap. Returns (body, final url)."""
    headers = {"Referer": referer} if referer else {}
    hops = 0
    attempt = 0
    while True:
        guard.check_url(url)
        try:
            with client.stream("GET", url, headers=headers) as resp:
                stream = resp.extensions.get("network_stream")
                peer = stream.get_extra_info("server_addr") if stream is not None else None
                if peer:
                    guard.check_peer(str(peer[0]))
                if resp.status_code in _REDIRECT_STATUS and resp.headers.get("location"):
                    hops += 1
                    if hops > MAX_REDIRECTS:
                        raise FetchError("too many redirects")
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code in _RETRY_STATUS and attempt < retries:
                    wait = resp.headers.get("retry-after", "")
                    attempt += 1
                    sleep(min(30.0, float(wait)) if wait.isdigit() else backoff * 2 ** (attempt - 1))
                    continue
                if resp.status_code != 200:
                    raise FetchError(_status_message(resp.status_code))
                declared = resp.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > limit:
                    raise _TooLarge
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limit:
                        raise _TooLarge
                return bytes(body), url
        except httpx.TransportError as exc:
            if attempt < retries:
                attempt += 1
                sleep(backoff * 2 ** (attempt - 1))
                continue
            raise FetchError(f"could not reach {urlparse(url).hostname}: {type(exc).__name__}") from exc


# --- rendering (optional) ----------------------------------------------------------------------------------------

def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def _render(url: str, guard: PublicOnlyGuard, timeout: float) -> tuple[str, str]:
    """The page after its scripts ran and it was scrolled to the end (lazy images load on scroll). Every request the
    browser makes, redirects and sub-resources included, goes through the guard."""
    from playwright.sync_api import Error as PlaywrightError, sync_playwright  # type: ignore[import-not-found,unused-ignore]  # noqa: I001

    def gate(route) -> None:  # type: ignore[no-untyped-def]
        target = route.request.url
        if urlparse(target).scheme not in ("data", "blob", "about"):
            try:
                guard.check_url(target)
            except FetchError:
                route.abort()
                return
        route.continue_()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                page = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}).new_page()
                page.route("**/*", gate)
                page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
                steady = 0
                for _ in range(300):
                    before = page.evaluate("document.documentElement.scrollHeight")
                    page.evaluate("window.scrollBy(0, 900)")
                    page.wait_for_timeout(250)
                    at_end = page.evaluate("window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2")
                    grew = page.evaluate("document.documentElement.scrollHeight") != before
                    steady = steady + 1 if at_end and not grew else 0
                    if steady >= 3:
                        break
                return page.content(), page.url
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise FetchError(
            f"The browser could not render the page ({str(exc).splitlines()[0][:160]}). "
            "If the browser itself is missing, run: playwright install chromium"
        ) from exc


# --- the fetch ---------------------------------------------------------------------------------------------------

@dataclass(slots=True)
class FetchResult:
    out_dir: Path
    images: list[Path]
    dims: list[tuple[int, int]]
    skipped: list[dict[str, str]] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rendered: bool = False
    source_json: Path | None = None


@dataclass(slots=True)
class _Got:
    index: int
    url: str
    path: Path | None = None
    width: int = 0
    height: int = 0
    size: int = 0
    skip: str | None = None
    drop: str | None = None


def fetch_chapter(
    url: str, out_dir: Path | str, *, rights_confirmed: bool = False, render: bool = False, delay: float = 0.4,
    retries: int = 3, backoff: float = 1.0, concurrency: int = 1, timeout: float = 20.0,
    min_width: int = MIN_PAGE_WIDTH, max_images: int = MAX_IMAGES, max_image_bytes: int = MAX_IMAGE_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES, guard: PublicOnlyGuard | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Download the chapter's page images into `out_dir` as `0001.jpg`, `0002.png`, ... plus `source.json`.

    `out_dir` is replaced only when the fetch succeeds. `rights_confirmed` is recorded, never enforced."""
    guard = guard or _DEFAULT_GUARD
    out = Path(out_dir)
    guard.check_url(url)
    notes: list[str] = []
    rendered = False
    with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.8"}, timeout=timeout,
                      follow_redirects=False, trust_env=False) as client:
        def fetch(target: str, referer: str | None, limit: int) -> tuple[bytes, str]:
            return _get(client, target, referer=referer, guard=guard, limit=limit, retries=retries,
                        backoff=backoff, sleep=sleep)

        if render and not playwright_available():
            raise FetchError(INSTALL_HINT)
        try:
            body, page_url = fetch(url, None, MAX_PAGE_BYTES)
        except _TooLarge as exc:
            raise FetchError("that page is larger than 8 MB; it is probably not a chapter page") from exc
        candidates = extract_image_urls(body.decode("utf-8", "replace"), page_url)
        if render or len(candidates) < 2:
            if playwright_available():
                html, page_url = _render(url, guard, timeout * 3)
                rendered_urls = extract_image_urls(html, page_url)
                if render or len(rendered_urls) > len(candidates):
                    candidates, rendered = rendered_urls, True
            elif candidates:
                notes.append(
                    f"Only {len(candidates)} image was found in the page's own markup. If the chapter has more, "
                    f"retry with --render ({INSTALL_HINT})."
                )
        if not candidates:
            hint = "" if rendered else f" If the site loads its pages with JavaScript, retry with --render. {INSTALL_HINT}."
            raise FetchError(
                "no page images found on that page. The chapter may be locked behind a login or paywall, which this "
                "tool does not get around." + hint
            )
        if len(candidates) > max_images:
            raise FetchError(f"the page lists {len(candidates)} images; the limit is {max_images}")
        return _publish(
            out, candidates, fetch=fetch, referer=page_url, delay=delay, concurrency=concurrency, min_width=min_width,
            max_image_bytes=max_image_bytes, max_total_bytes=max_total_bytes, sleep=sleep,
            info={"url": url, "final_url": page_url, "rights_confirmed": bool(rights_confirmed), "rendered": rendered},
            notes=notes, rendered=rendered,
        )


def _publish(
    out: Path, candidates: list[str], *, fetch: Callable[[str, str | None, int], tuple[bytes, str]],
    referer: str | None, delay: float, concurrency: int, min_width: int, max_image_bytes: int, max_total_bytes: int,
    sleep: Callable[[float], None], info: dict, notes: list[str], rendered: bool,
) -> FetchResult:
    """Validate, filter and name the candidates, then replace `out` only when something usable was kept. Shared by the
    network fetch and the local import so both apply the same size, shape and width rules."""
    tmp = out.parent / f".{out.name}.fetching"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        got = _download_all(
            candidates, tmp, fetch=fetch, referer=referer, delay=delay, concurrency=concurrency,
            min_width=min_width, max_image_bytes=max_image_bytes, max_total_bytes=max_total_bytes, sleep=sleep,
        )
        kept = _dominant_width([g for g in got if g.path is not None and g.drop is None])
        for g in got:
            if g.path is not None and g not in kept:
                g.drop = g.drop or "width differs from the rest of the chapter"
                g.path.unlink(missing_ok=True)
        if not kept:
            reasons = "; ".join(sorted({g.skip or g.drop or "" for g in got})[:3])
            raise FetchError(f"none of the {len(candidates)} images on the page looked like a comic page ({reasons})")
        final: list[tuple[Path, _Got]] = []
        for n, g in enumerate(kept, 1):
            assert g.path is not None
            dest = tmp / f"{n:04d}{g.path.suffix}"
            g.path.rename(dest)
            final.append((dest, g))
        info = {
            **info, "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "image_count": len(final),
            "images": [{"file": d.name, "width": g.width, "height": g.height, "bytes": g.size} for d, g in final],
            "skipped": [{"url": g.url, "reason": g.skip} for g in got if g.skip],
            "dropped_as_noise": len([g for g in got if g.drop]),
        }
        (tmp / "source.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        shutil.rmtree(out, ignore_errors=True)
        tmp.replace(out)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return FetchResult(
        out_dir=out, images=[out / d.name for d, _ in final], dims=[(g.width, g.height) for _, g in final],
        skipped=[{"url": g.url, "reason": g.skip} for g in got if g.skip],
        dropped=[{"url": g.url, "reason": g.drop} for g in got if g.drop],
        notes=notes, rendered=rendered, source_json=out / "source.json",
    )


# --- local import (no network) -----------------------------------------------------------------------------------

#: `urljoin` needs a base, and the references of a saved page are relative to its folder. This stand-in directory is
#: never touched; a joined reference is local only if it still sits under it, so `..` and absolute paths fall outside.
_LOCAL_ROOT = "/saved/"
_LOCAL_PAGE_EXT = {".html", ".htm", ".xhtml"}
_SAVED_FROM = re.compile(r"<!--\s*saved from url=(?:\(\d+\))?\s*(\S+?)\s*-->", re.I)


class _PageUrl(HTMLParser):
    """The canonical link and og:url of a saved page, for pages whose browser left no `saved from url` comment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: str | None = None
        self.og_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "").strip() for k, v in attrs}
        if tag == "link" and "canonical" in a.get("rel", "").lower().split() and a.get("href"):
            self.canonical = self.canonical or a["href"]
        elif tag == "meta" and a.get("property", "").lower() == "og:url" and a.get("content"):
            self.og_url = self.og_url or a["content"]


def saved_page_url(html: str) -> str | None:
    """The address a saved page came from: the browser's `saved from url` comment, else canonical, else og:url."""
    stamp = _SAVED_FROM.search(html[:4096])
    parser = _PageUrl()
    parser.feed(html)
    for found in (stamp.group(1) if stamp else None, parser.canonical, parser.og_url):
        if found and urlparse(found).scheme in ("http", "https"):
            return found
    return None


def default_local_id(source: Path | str) -> str:
    """A folder name from a saved page's file name or a folder's name, as `default_comic_id` does for a link."""
    path = Path(source)
    return re.sub(r"[^A-Za-z0-9._-]", "_", path.name if path.is_dir() else path.stem).lstrip(".")[:80] or "comic"


def _local_target(rel: str, root: Path) -> Path | str:
    """The file `rel` names under `root`, or the plain-language reason it cannot be used. Resolving first means a
    symlink or a percent-encoded `..` that leads out of `root` is refused the same way a plain `..` is."""
    try:
        target = (root / rel).resolve()
        target.relative_to(root)
    except ValueError:
        return "outside the page's folder; refused"
    except OSError:
        return "could not be read"
    return target if target.is_file() else "file not found"


def fetch_local(
    source: Path | str, out_dir: Path | str, *, rights_confirmed: bool = False, min_width: int = MIN_PAGE_WIDTH,
    max_images: int = MAX_IMAGES, max_image_bytes: int = MAX_IMAGE_BYTES, max_total_bytes: int = MAX_TOTAL_BYTES,
) -> FetchResult:
    """Import page images from disk instead of a link: a browser-saved page (`page.html` plus its `page_files/`) or a
    folder of images. Same validation, caps, noise and width filtering, naming and `source.json` as `fetch_chapter`;
    it never opens a socket. A reference to a remote image the browser did not save is reported, not fetched, and every
    file must resolve to somewhere inside the page's (or the folder's) own directory."""
    src = Path(source)
    if not src.exists():
        raise FetchError(f"no such file or folder: {src}")
    table: dict[str, Path | str] = {}
    page_url: str | None = None
    if src.is_dir():
        kind, root = "folder", src.resolve()
        names = sorted(
            (p.name for p in src.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and not p.is_dir()), key=natural_key
        )
        for name in names:
            table[name] = _local_target(name, root)
    elif src.is_file() and src.suffix.lower() in _LOCAL_PAGE_EXT:
        kind, root = "saved_page", src.resolve().parent
        if src.stat().st_size > MAX_PAGE_BYTES:
            raise FetchError("that page is larger than 8 MB; it is probably not a chapter page")
        html = src.read_text(encoding="utf-8", errors="replace")
        page_url = saved_page_url(html)
        for ref in extract_image_urls(html, f"file://{_LOCAL_ROOT}{src.name}"):
            parts = urlparse(ref)
            if parts.scheme != "file" or parts.netloc:
                shown = ref if parts.scheme in ("http", "https") else f"//{parts.netloc}{parts.path}"
                table[shown] = "remote image, not saved with the page; local mode never downloads"
            elif parts.path.startswith(_LOCAL_ROOT):
                rel = unquote(parts.path[len(_LOCAL_ROOT):])
                table[rel] = _local_target(rel, root)
            else:
                table[unquote(parts.path)] = "outside the page's folder; refused"
    else:
        raise FetchError("a local source must be a saved page (.html) or a folder of images")
    if not table:
        raise FetchError("no page images found in " + ("that folder" if kind == "folder" else "that saved page"))
    if len(table) > max_images:
        raise FetchError(f"the {kind.replace('_', ' ')} lists {len(table)} images; the limit is {max_images}")

    def read(key: str, referer: str | None, limit: int) -> tuple[bytes, str]:
        target = table[key]
        if isinstance(target, str):
            raise FetchError(target)
        with target.open("rb") as fh:
            data = fh.read(limit + 1)
        if len(data) > limit:
            raise _TooLarge
        return data, key

    res = _publish(
        Path(out_dir), list(table), fetch=read, referer=None, delay=0, concurrency=1, min_width=min_width,
        max_image_bytes=max_image_bytes, max_total_bytes=max_total_bytes, sleep=lambda _s: None,
        info={"source": kind, "url": page_url, "final_url": page_url, "origin_name": src.name,
              "rights_confirmed": bool(rights_confirmed), "rendered": False},
        notes=[], rendered=False,
    )
    if any(isinstance(t, str) and t.startswith("remote") for t in table.values()):
        res.notes.append(
            "Some images the page refers to were not saved with it. Scroll the chapter to the end so lazy images load, "
            "then save it again with 'Webpage, Complete'."
        )
    return res


def _download_all(
    urls: list[str], tmp: Path, *, fetch: Callable[[str, str | None, int], tuple[bytes, str]], referer: str,
    delay: float, concurrency: int, min_width: int, max_image_bytes: int, max_total_bytes: int,
    sleep: Callable[[float], None],
) -> list[_Got]:
    lock = threading.Lock()
    total = 0
    stop = threading.Event()

    def one(index: int, url: str) -> _Got:
        nonlocal total
        got = _Got(index=index, url=url)
        if stop.is_set():
            got.skip = "not downloaded: the download limit was reached"
            return got
        if delay:
            sleep(delay)
        try:
            data, _ = fetch(url, referer, max_image_bytes)
        except _TooLarge:
            got.skip = f"larger than the {max_image_bytes:,}-byte per-image limit"
            return got
        except FetchError as exc:
            got.skip = str(exc)
            return got
        with lock:
            total += len(data)
            if total > max_total_bytes:
                stop.set()
                raise FetchError(f"the chapter is larger than the {max_total_bytes // (1024 * 1024)} MB total limit")
        try:
            with Image.open(BytesIO(data)) as im:
                im.verify()
            with Image.open(BytesIO(data)) as im:
                fmt, (got.width, got.height) = im.format or "", im.size
        except Exception:  # Pillow raises many types, including its decompression-bomb error
            got.skip = "not a readable image"
            return got
        ext = _PIL_EXT.get(fmt)
        if ext is None:
            got.skip = f"not a supported page image type ({fmt or 'unknown'})"
            return got
        got.size = len(data)
        if got.size < MIN_PAGE_BYTES or got.width < min_width or got.height < got.width * MIN_ASPECT:
            got.drop = f"{got.width}x{got.height}, {got.size} bytes: too small or the wrong shape for a page"
            return got
        got.path = tmp / f"c{index:04d}.{ext}"
        got.path.write_bytes(data)
        return got

    with ThreadPoolExecutor(max_workers=max(1, min(3, concurrency))) as pool:
        return list(pool.map(lambda a: one(*a), enumerate(urls)))


def _dominant_width(items: list[_Got]) -> list[_Got]:
    """Keep the images whose width is within `WIDTH_TOLERANCE` of the most common width. Pages of one chapter share a
    width (a webtoon strip exactly); a stray cover, ad or thumbnail of another width does not. Applied only when that
    width covers at least half the images and at least two, so a chapter of mixed page sizes is not thinned."""
    if len(items) < 3:
        return items
    best: list[_Got] = []
    for anchor in items:
        group = [g for g in items if abs(g.width - anchor.width) <= anchor.width * WIDTH_TOLERANCE]
        if len(group) > len(best):
            best = group
    return best if len(best) >= 2 and len(best) * 2 >= len(items) else items
