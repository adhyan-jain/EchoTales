"""Token-compositional renaming pi (PREREG_T4, section 3).

Why compositional at the token level: the resolver decides links through
containment ("Yuan" inside "Fang Yuan"), shared family tokens and surface
similarity. A renaming that mapped the whole string "Fang Yuan" and the string
"Yuan" independently would break exactly those relations and make renaming
look like it destroys evidence for a reason unrelated to memorisation. So pi
renames *tokens* and applies the same token map everywhere; strings are never
renamed as units.

Renamed text changes length, so character offsets move. `rename_with_map`
returns a monotone offset map and `map_offset` applies it; `inverse` makes
the whole thing reversible, which is how the round-trip property is tested.
No randomness outside the seeded generator in `Renamer.build`.
"""

from __future__ import annotations

import bisect
import random
import re
from dataclasses import dataclass, field

TOKEN = re.compile(r"[A-Za-z]+")

# Fixed syllable inventory: pronounceable, no real English word is produced
# on purpose, and `build` rejects any collision with a word already in the text.
_ONSETS = ["b", "d", "f", "g", "h", "j", "k", "l", "m", "n", "p", "r", "s", "t", "v", "z", "br", "dr", "gr", "kr", "tr", "sh", "th", "vr"]
_VOWELS = ["a", "e", "i", "o", "u", "ae", "ei", "ou"]
_CODAS = ["", "", "n", "r", "l", "s", "k", "th", "m"]

def s_class(token: str) -> bool:
    """True when the repo's `strip_morphology` would strip this token's final "s".

    Mirrors `ingest/normalize.py::strip_morphology`'s plural rule (the length
    condition is applied there to the whole surface, which exact-length
    replacement preserves): a final "s" that is not part of "ss", "us" or "is".
    """
    return token.endswith(("s", "S")) and not token.lower().endswith(("ss", "us", "is"))


PRONOUNS = {"I", "He", "She", "It", "We", "They", "You", "His", "Her", "Their", "My", "Your", "Our", "This", "That"}


@dataclass
class Renamer:
    mapping: dict[str, str] = field(default_factory=dict)
    # lower-case variant map, derived from `mapping` (PREREG_T4 v3 section 1 item 3)
    _lower: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._lower = {k.lower(): v.lower() for k, v in self.mapping.items() if k.lower() != k}

    # -- construction ------------------------------------------------------
    @classmethod
    def build(
        cls,
        vocabulary: set[str],
        *,
        protected_lower: set[str],
        existing_lower: set[str],
        seed: int,
        common_lower: set[str] | frozenset[str] = frozenset(),
    ) -> Renamer:
        """Bijective capitalised-token map (PREREG_T4 v3 section 1).

        `vocabulary`: capitalised tokens taken from names, aliases and labels.
        `protected_lower`: lower-case forms never renamed (titles, roles,
        kinship, ambiguity blocklist, stop words, honorifics). `common_lower`:
        lower-case words frequent as ordinary lower-case text ("may", "great"),
        never renamed because `comparison_key` casefolds them into the same
        key as their capitalised form. `existing_lower`: every lower-cased
        token already in the corpus, so a fresh token never collides with a
        real word or a name already in use.

        Inflection closure: a plural token `t + "s"` maps to `pi(t) + "s"`, and
        is protected whenever `t` is, so `strip_morphology`'s plural folding
        still joins the pair after renaming.
        """
        rng = random.Random(seed)
        used = set(existing_lower)
        guard = set(protected_lower) | set(common_lower)

        def protected(tok: str) -> bool:
            if tok in PRONOUNS or tok.lower() in guard or not tok[:1].isupper() or len(tok) < 2:
                return True
            return s_class(tok) and tok[:-1].lower() in guard

        has_plural = {t[:-1] for t in vocabulary if s_class(t) and t[:-1] in vocabulary}
        out: dict[str, str] = {}
        for tok in sorted(vocabulary, key=lambda t: (len(t), t)):  # bases before their plurals
            if protected(tok):
                continue
            base = tok[:-1]
            if s_class(tok) and base in out:
                new = out[base] + "s"
                if new.lower() in used:  # pragma: no cover - a real word would have to equal base+"s"
                    raise RuntimeError(f"plural of {base!r} collides with an existing word: {new!r}")
                used.add(new.lower())
                out[tok] = new
                continue
            for _ in range(10_000):
                new = cls._invent(rng, len(tok), s_class(tok), plural_safe=tok in has_plural)
                if new.lower() not in used:
                    used.add(new.lower())
                    out[tok] = new
                    break
            else:  # pragma: no cover - the inventory is far larger than any novel's names
                raise RuntimeError(f"could not invent a replacement for {tok!r}")
        return cls(out)

    @staticmethod
    def _invent(rng: random.Random, length: int, strippable: bool, plural_safe: bool = False) -> str:
        """Token of EXACTLY `length` letters in the same morphology class.

        PREREG_T4 v2 section 1: exact length keeps every `len(text) > 4`
        predicate in `strip_morphology` unchanged, and the class rule keeps a
        final "s" folded (or not) exactly when the original was. v1 allowed
        +/- 2 letters and any ending, and a smoke run showed the resolver
        turning "Brom Das" into "Brom Da".
        """
        word = ""
        while len(word) < length:
            word += rng.choice(_ONSETS) + rng.choice(_VOWELS) + rng.choice(_CODAS)
        word = word[:length]
        if strippable:
            prev = rng.choice("aenorlkmt") if length >= 2 else ""
            word = word[:-2] + prev + "s" if length >= 2 else word
        elif word[-1] in "sS" or plural_safe:
            # A base that has a plural in the vocabulary must end so that
            # base + "s" is still strippable (not ss/us/is): end in a letter
            # from this set.
            word = word[:-1] + rng.choice("aenorlkmt")
        return word.capitalize()

    # -- application -------------------------------------------------------
    def _new(self, m: re.Match, text: str) -> str | None:
        """Replacement for a matched token, or None to leave it. A hook so the
        T4 negative control can be context-dependent while sharing all other code."""
        tok = m.group(0)
        hit = self.mapping.get(tok)
        if hit is not None:
            return hit
        # All-lower-case variant of a renamed name ("fang" for "Fang"); mixed
        # and all-upper variants are left alone and counted by the runner.
        return self._lower.get(tok) if tok.islower() else None

    def rename(self, text: str) -> str:
        return self.rename_with_map(text)[0]

    def rename_with_map(self, text: str) -> tuple[str, "OffsetMap"]:
        out: list[str] = []
        starts: list[int] = []  # old end positions of replacements, ascending
        deltas: list[int] = []  # cumulative length change after each replacement
        pos, delta = 0, 0
        for m in TOKEN.finditer(text):
            new = self._new(m, text)
            if new is None:
                continue
            out.append(text[pos : m.start()])
            out.append(new)
            pos = m.end()
            delta += len(new) - len(m.group(0))
            starts.append(m.end())
            deltas.append(delta)
        out.append(text[pos:])
        return "".join(out), OffsetMap(starts, deltas)

    def inverse(self) -> Renamer:
        inv = {v: k for k, v in self.mapping.items()}
        if len(inv) != len(self.mapping):  # pragma: no cover - build() guarantees a bijection
            raise ValueError("mapping is not one-to-one")
        return Renamer(inv)


@dataclass
class BrokenYuanRenamer(Renamer):
    """T4 negative control (PREREG_T4 section 4, run N): NON-compositional.

    "Yuan" gets one replacement when it follows "Fang " and a *different* one
    when it stands alone, so "Fang Yuan" no longer contains the renamed
    "Yuan". The resolver's containment link between the two forms must
    therefore break; if T4's agreement does not fall under this renaming, the
    comparison is insensitive and T4 is inconclusive.
    """

    full_form_token: str = "Qeth"

    def _new(self, m: re.Match, text: str) -> str | None:
        if m.group(0) == "Yuan" and text[: m.start()].endswith("Fang "):
            return self.full_form_token
        return super()._new(m, text)


@dataclass
class OffsetMap:
    """Monotone old->new offset map for one renamed string."""

    ends: list[int]
    deltas: list[int]

    def map_offset(self, pos: int) -> int:
        """New offset of old position `pos` (a token start or any unchanged char)."""
        i = bisect.bisect_right(self.ends, pos)  # replacements fully before `pos`
        return pos + (self.deltas[i - 1] if i else 0)
