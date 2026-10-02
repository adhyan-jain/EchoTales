"""Project Dialogism Novel Corpus (Vishnubhotla, Hammond & Hirst, LREC 2022).

Public-domain English novels with human annotation of every quotation's
speaker, addressees and quote type (explicit / anaphoric / implicit), plus a
character list with gender. It is the arena's source of *independent* gold:
the copyrighted web novels the product targets have only LLM-drafted silver
labels, and speaker labels for them do not exist at all (EVOLUTION 4.88).

**Licence: unclear -- treat as restrictive.** Search results describe it as
CC BY-NC-ND, but neither GitHub repository carries a licence file (API:
`license: null`); the novel texts themselves are Gutenberg public domain.
Used for non-commercial research only; the corpus is read
from the gitignored cache (`data/cache/research/pdnc`) and never committed, and
derived sets (e.g. error-injected scripts) are regenerated from code rather
than redistributed -- "no derivatives" is honoured by shipping the transform,
not its output.
"""

from __future__ import annotations

import ast
import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from echotales.pipeline.paths import RESEARCH_CACHE_DIR

PDNC_ROOT = RESEARCH_CACHE_DIR / "pdnc"


@dataclass(frozen=True, slots=True)
class Character:
    id: str
    name: str
    aliases: tuple[str, ...]
    gender: str  # PDNC codes; "M"/"F" where annotated, else "U"/"X"
    category: str


@dataclass(slots=True)
class Quote:
    id: str
    novel: str
    text: str
    speaker: str
    addressees: list[str]
    quote_type: str
    start: int  # char offset of the first sub-quotation in text.txt
    end: int
    index: int  # position in the novel's quote sequence


@dataclass(slots=True)
class Novel:
    name: str
    text: str
    characters: dict[str, Character]
    quotes: list[Quote] = field(default_factory=list)

    def gender_of(self, name: str) -> str:
        c = self.characters.get(name)
        return c.gender if c else "U"


def _parse_list(raw: str) -> list:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        val = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return [raw]
    return list(val) if isinstance(val, (list, tuple, set)) else [val]


#: The repository renamed its files between releases (LREC 2022 repo vs the
#: maintained one); accept both rather than pin a commit.
_QUOTE_FILES = ("quotation_info.csv", "quotations.csv")
_TEXT_FILES = ("novel_text.txt", "text.txt")


def _first(d: Path, names: tuple[str, ...]) -> Path | None:
    for n in names:
        if (d / n).exists():
            return d / n
    return None


def available(root: Path = PDNC_ROOT) -> list[str]:
    data = root / "data"
    if not data.is_dir():
        return []
    return sorted(p.name for p in data.iterdir() if _first(p, _QUOTE_FILES))


def load_novel(name: str, root: Path = PDNC_ROOT) -> Novel:
    d = root / "data" / name
    text = _first(d, _TEXT_FILES).read_text(encoding="utf-8", errors="replace")
    chars: dict[str, Character] = {}
    with (d / "character_info.csv").open(encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            nm = (row.get("Main Name") or "").strip()
            if not nm:
                continue
            aliases = tuple(str(a).strip() for a in _parse_list(row.get("Aliases", "")) if a)
            chars[nm] = Character(
                id=str(row.get("Character ID", nm)).strip(), name=nm, aliases=aliases,
                gender=(row.get("Gender") or "U").strip() or "U",
                category=(row.get("Category") or "").strip(),
            )
    quotes: list[Quote] = []
    with _first(d, _QUOTE_FILES).open(encoding="utf-8", errors="replace") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            spans = _parse_list(row.get("quoteByteSpans", ""))
            try:
                start, end = (int(spans[0][0]), int(spans[-1][1])) if spans else (-1, -1)
            except (TypeError, ValueError, IndexError):
                start, end = -1, -1
            quotes.append(Quote(
                id=str(row.get("quoteID") or row.get("quoteId") or i), novel=name,
                text=(row.get("quoteText") or "").strip(),
                speaker=(row.get("speaker") or "").strip(),
                addressees=[str(a).strip() for a in _parse_list(row.get("addressees", ""))],
                quote_type=(row.get("quoteType") or "").strip(),
                start=start, end=end, index=i,
            ))
    return Novel(name=name, text=text, characters=chars, quotes=quotes)


def synthetic_novel(seed: int = 0, n_quotes: int = 120) -> Novel:
    """A deterministic stand-in with PDNC's shape, for `--stub` runs and CI.

    Explicit quotes carry a `said <Name>` tag so the product's tier-1 regex
    fires; anaphoric ones a `she said`; implicit ones nothing -- reproducing the
    three PDNC quote types so stub-mode metrics exercise every code path.
    """
    rng = random.Random(seed)
    cast = [("Anna", "F"), ("Ben", "M"), ("Clara", "F"), ("David", "M")]
    chars = {n: Character(id=n, name=n, aliases=(n,), gender=g, category="major") for n, g in cast}
    parts: list[str] = []
    quotes: list[Quote] = []
    pos = 0
    for i in range(n_quotes):
        spk, adr = rng.sample(cast, 2)
        kind = rng.choice(["explicit", "anaphoric", "implicit"])
        body = f"{adr[0]}, line number {i} is spoken here"
        q = f"“{body}.”"
        tail = {"explicit": f" said {spk[0]}.", "anaphoric":
                f" {'she' if spk[1] == 'F' else 'he'} said.", "implicit": ""}[kind]
        lead = f"{spk[0]} turned. " if kind == "anaphoric" else ""
        chunk = f"{lead}{q}{tail}\n\n"
        start = pos + len(lead)
        quotes.append(Quote(id=f"S{i}", novel="synthetic", text=body + ".", speaker=spk[0],
                            addressees=[adr[0]], quote_type=kind, start=start,
                            end=start + len(q), index=i))
        parts.append(chunk)
        pos += len(chunk)
    return Novel(name="synthetic", text="".join(parts), characters=chars, quotes=quotes)
