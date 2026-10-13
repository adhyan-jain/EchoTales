"""An ideal-observer listener for multi-voice narration (H-IOL).

Why a model at all: H-COST as first designed was an effect hunt -- "do errors
hurt more under a full cast?" -- and C17 (a theory of it) was killed as the
tautology "distinct outputs are more distinguishable". A listener who *learns*
which voice belongs to which character makes predictions that tautology does
not: an error can cost comprehension on lines that were rendered correctly
(it corrupts the learned map), and an error on a line whose speaker the text
names may cost more over time than one on an untagged line, because the tag
teaches the wrong map exactly when the listener trusts it. Those are the
predictions the human study can falsify.

The model, per passage (all deterministic, pure Python):

- The listener knows who is present (the cast of the passage) but not which
  voice is whose. ``counts[voice][char]`` is a Dirichlet-style tally, prior
  ``alpha``.
- Hearing voice ``v`` is perceptually confusable with every voice heard so
  far: ``K(v, u) = exp(-d(v, u) / tau)``, with ``d`` the speaker-embedding
  cosine distance the arena already uses (voice_geometry.py). ``tau`` is the
  psychometric free parameter; categorical identity perception (Latinus &
  Belin 2012) is the small-``tau`` end of the range.
- A *tagged* line (PDNC Explicit; Anaphoric with reliability ``rho``) tells
  the listener the speaker: comprehension is that reliability, and the tag
  updates ``counts[v][tagged speaker]`` -- with a misattributed voice, this
  is the poisoning step.
- An *implicit* line is inferred from the voice and a turn-taking prior
  (``lam_alt`` on the speaker two turns back, the "alternation default"
  every attributor uses); comprehension is the posterior mass on the true
  speaker. With ``w_self > 0`` the listener also learns from its own
  inference (self-training), which lets an early error cascade.
- Narrator voice: one voice for everyone, so it carries no identity
  information and the posterior falls back to the prior -- the baseline the
  full cast must beat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

NARRATOR = "__narrator__"


@dataclass(frozen=True, slots=True)
class ListenerParams:
    tau: float = 0.06  # perceptual confusability scale (embedding cosine distance)
    rho: float = 0.9  # reliability of an anaphoric tag ("she said")
    lam_alt: float = 0.3  # weight of the turn-alternation prior
    w_self: float = 0.0  # self-training weight on implicit lines
    alpha: float = 0.2  # Dirichlet prior on each voice's character map


@dataclass(frozen=True, slots=True)
class Line:
    speaker: str  # gold speaker
    voice: str  # the voice actually rendered (NARRATOR for narration policy)
    tag: str  # "explicit" | "anaphoric" | "implicit"


@dataclass(frozen=True, slots=True)
class LineOutcome:
    comprehension: float  # P(listener attributes the line to its gold speaker)
    #: For tagged lines: 1 - P_voice(tagged speaker | voice) -- how strongly the
    #: voice contradicts the text, i.e. how noticeable a conflict is. 0 when
    #: the listener has no map for the voice yet.
    surprise: float


def simulate(lines: list[Line], cast: list[str], dist, params: ListenerParams) -> list[LineOutcome]:
    """Run the listener over one passage. `dist(u, v)` gives voice distance
    (0 for u == v); NARRATOR is treated like any other voice."""
    p = params
    idx = {c: i for i, c in enumerate(cast)}
    n = len(cast)
    counts: dict[str, list[float]] = {}
    heard: list[str] = []
    history: list[int] = []  # listener's own best guess per line (for the prior)
    out: list[LineOutcome] = []
    kcache: dict[tuple[str, str], float] = {}

    def k(u: str, v: str) -> float:
        key = (u, v) if u <= v else (v, u)
        if key not in kcache:
            kcache[key] = math.exp(-dist(u, v) / p.tau)
        return kcache[key]

    def voice_post(v: str) -> list[float]:
        # P(char | heard v) = sum_u K(v,u) P(char | u) / sum_u K(v,u) over
        # voices already heard. A not-yet-heard voice also contributes one
        # uniform vector: it could be anyone, weighted like a single voice
        # so it never swamps an established map.
        acc = [0.0] * n
        z = 0.0
        for u in heard:
            w = k(v, u)
            row = counts[u]
            s = sum(row) + p.alpha * n
            for j in range(n):
                acc[j] += w * (row[j] + p.alpha) / s
            z += w
        if v not in counts:
            for j in range(n):
                acc[j] += 1.0 / n
            z += 1.0
        return [a / z for a in acc]

    def prior() -> list[float]:
        pr = [1.0 / n] * n
        if p.lam_alt > 0 and len(history) >= 2 and history[-2] != history[-1]:
            pr = [(1 - p.lam_alt) * x for x in pr]
            pr[history[-2]] += p.lam_alt
        return pr

    for ln in lines:
        v = ln.voice
        gold = idx[ln.speaker]
        vp = voice_post(v)
        post = _normalise([a * b for a, b in zip(vp, prior())])
        surprise = 0.0
        if ln.tag in ("explicit", "anaphoric"):
            rel = 1.0 if ln.tag == "explicit" else p.rho
            if v in counts:
                surprise = 1.0 - vp[gold]
            # Trust the tag with its reliability, else fall back to voice +
            # prior like an implicit line.
            comp = rel + (1 - rel) * post[gold]
            row = counts.setdefault(v, [0.0] * n)
            row[gold] += rel  # the tag teaches: this voice is that speaker
            if rel < 1.0:
                for j in range(n):
                    row[j] += (1 - rel) * post[j]
            guess = gold
        else:
            comp = post[gold]
            guess = max(range(n), key=lambda j: post[j])
            if p.w_self > 0:
                row = counts.setdefault(v, [0.0] * n)
                for j in range(n):
                    row[j] += p.w_self * post[j]
        if v not in heard:
            heard.append(v)
            counts.setdefault(v, [0.0] * n)
        history.append(guess)
        out.append(LineOutcome(comprehension=comp, surprise=surprise))
    return out


def _normalise(xs: list[float]) -> list[float]:
    s = sum(xs)
    return [x / s for x in xs] if s > 0 else [1.0 / len(xs)] * len(xs)


def param_grid() -> list[ListenerParams]:
    """The 24-setting sensitivity grid pre-registered for H-IOL."""
    return [ListenerParams(tau=t, rho=r, lam_alt=la, w_self=w)
            for t in (0.03, 0.06, 0.12) for r in (0.7, 0.95)
            for la in (0.0, 0.4) for w in (0.0, 0.5)]
