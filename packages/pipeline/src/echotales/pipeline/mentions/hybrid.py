"""Hybrid mention detector: encoder votes, a gazetteer, and an LLM only for the doubtful ones (decisions D69).

Why it exists. The LLM-only vocabulary pass (`QwenNerDetector`) asks a 7B model about every window of every chapter
and then trusts whatever comes back with one fixed score (0.85), so a hallucinated name and a certain one are
indistinguishable downstream. Here several cheap sources vote, every vote is kept (`candidate.py`), and the model
is asked only about the candidates the votes could not settle. The measured numbers that choose between this and the
legacy path come from the D69 bake-off; until then `mentions.detector` defaults to "llm" and nothing here runs.

Passes are decoupled on purpose. The 8 GB card cannot hold GLiNER and ollama's model together (same constraint as
render's direction-first split), so GLiNER runs over ALL the text first and is unloaded before spaCy, the
gazetteer pass and any classifier call. `precompute` does that once for a whole volume; `detect_candidates` on text
it has not seen runs the same order on that text alone.

Routing, in order (`_route`):
  accept     a confirmed gazetteer alias voted;
  reject     one source only and its score is below `tau_low`;
  classifier the surface is a common word (a blocklisted word, a pronoun, an interjection, or the optional
             `is_wordlike` predicate) -- "Will", "Hope", "Light" score high as names precisely when they are not;
  accept     a GLiNER vote scored >= `tau_high`;
  accept     two independent sources agree on the label;
  classifier everything else (one mid-score vote, or sources that disagree on the label).
With no classifier (stub / offline) the classifier route REJECTS: precision over recall (non-negotiable 9), and the
rejected surface still reaches the graph the day a model-backed run confirms it.

Fast mode (`fast=True`, `mentions.detector = "fast"`): GLiNER alone at `FAST_GLINER_THRESHOLD`, no spaCy vote and no
classifier. Measured on the romanized gold (boundary F1, production filters): GLiNER-medium at 0.4 alone scores 0.881 on
test against the full hybrid's 0.903 (precision .916 vs .918, recall .848 vs .888) at about 8 s per 1k tokens against
55-64 s. Routing there is: confirmed gazetteer alias accepts, any GLiNER vote at the threshold accepts, nothing else does
(a seed-only or rule-only candidate is rejected: precision over recall). Word-like surfaces are accepted per occurrence
only and `may_promote` keeps them out of the confirmed aliases, exactly as in the hybrid.

DEVIATION from the brief, flagged: the brief lists the word-like test after the accepts. Applied there it would never
fire for a high-scoring "Will", which is the case it exists for, so it runs before the score accept. A gazetteer
alias still wins over it (that alias was confirmed by evidence, not by the encoder).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from echotales.core.enums import AliasType
from echotales.pipeline.ingest.normalize import non_name_reason, strip_name_tail
from echotales.pipeline.mentions.candidate import (
    ClassifiedCandidate,
    NameCandidate,
    Route,
    Vote,
)
from echotales.pipeline.mentions.gazetteer import AMBIGUITY_BLOCKLIST, Gazetteer
from echotales.pipeline.mentions.gliner_ner import GlinerDetector
from echotales.pipeline.mentions.ner import MentionDetector, NerSpan, SpanProvenance
from echotales.pipeline.mentions.ner_classify import Verdict
from echotales.pipeline.mentions.spacy_ner import SpacyDetector

log = logging.getLogger(__name__)

#: PROVISIONAL until the D69 bake-off picks them from measured precision/recall on the romanized gold.
TAU_HIGH = 0.7
TAU_LOW = 0.3

#: Rule-based votes have no calibrated probability. A confirmed alias is the strongest evidence the pipeline has; a
#: Layer-0 seed (speech-attribution regex) is deliberately mid, so a seed alone goes to the classifier rather than in.
#: The threshold GLiNER-medium is run at in fast mode: the dev-set optimum of the D69 bake-off (0.881 boundary F1 on
#: test). It is a measured constant, not a setting: a second knob would be a third tuning mechanism for one number.
FAST_GLINER_THRESHOLD = 0.4

GAZETTEER_VOTE_SCORE = 1.0
SEED_VOTE_SCORE = 0.5

_MODEL_SOURCES = ("gliner", "spacy")

Classifier = Callable[..., "list[Verdict | None]"]


def _is_common_word(surface: str) -> bool:
    """The existing machinery only: the gazetteer's ambiguity blocklist, plus `non_name_reason` (pronoun,
    interjection, bare title). No new word list -- the brief forbade one, and a hand-written list is what
    `commonness.py` explains does not generalise across novels."""
    return surface.casefold() in AMBIGUITY_BLOCKLIST or non_name_reason(surface) is not None


@dataclass(frozen=True, slots=True)
class _RawVote:
    span: NerSpan
    source: str
    model_id: str | None
    model_version: str | None


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _trimmed(span: NerSpan) -> NerSpan | None:
    """The span without a trailing possessive or glued footnote marker; None when nothing name-like is left.

    Real-data check (NER_ROMANIZED.md): the encoders return "Fang Zhi’s" (2 RI mentions, so the entity existed only as a
    broken surface) and "Yoo Sangah-ssi²" / "Reader-nim³" on ORV. The cut is applied to the end offset, so the mention
    keeps pointing at the text it came from.
    """
    surface = strip_name_tail(span.text)
    if surface == span.text:
        return span
    return replace(span, text=surface, end=span.start + len(surface)) if len(surface) >= 2 else None


class HybridDetector(MentionDetector):
    def __init__(
        self,
        *,
        gliner: GlinerDetector | None = None,
        spacy: SpacyDetector | None = None,
        known_aliases: Iterable[str] = (),
        seed_names: Iterable[str] = (),
        classifier: Classifier | None = None,
        tau_high: float = TAU_HIGH,
        tau_low: float = TAU_LOW,
        is_wordlike: Callable[[str], bool] | None = None,
        fast: bool = False,
    ) -> None:
        self.fast = fast
        self.gliner = gliner
        self.spacy = spacy
        self.known_aliases = tuple(known_aliases)
        self.seed_names = tuple(seed_names)
        self.classifier = classifier
        self.tau_high = tau_high
        self.tau_low = tau_low
        self.is_wordlike = is_wordlike
        self._model_votes: dict[str, list[_RawVote]] = {}
        self.route_counts: Counter[str] = Counter()

    @property
    def name(self) -> str:
        parts = [v.name for v in (self.gliner, self.spacy) if v is not None]
        return ("fast(" if self.fast else "hybrid(") + "+".join(parts) + ")"

    # ---- model passes ---------------------------------------------------

    def precompute(self, texts: Sequence[str]) -> None:
        """Run every model voter over `texts` before anything else touches the GPU.

        Separate from detection so a volume pays one GLiNER load, not one per chapter, and so GLiNER is gone from
        VRAM by the time the first classifier call reaches ollama.
        """
        todo = [t for t in dict.fromkeys(texts) if _digest(t) not in self._model_votes]
        if not todo:
            return
        found: dict[str, list[_RawVote]] = {_digest(t): [] for t in todo}
        if self.gliner is not None:
            try:
                for t in todo:
                    found[_digest(t)] += self._raw(self.gliner.detect(t), "gliner", self.gliner)
            finally:
                # Before spaCy, and before ollama: the two must never be resident together.
                self.gliner.unload()
        if self.spacy is not None:
            for t in todo:
                found[_digest(t)] += self._raw(self.spacy.detect(t), "spacy", self.spacy)
        self._model_votes.update(found)

    @staticmethod
    def _raw(spans: list[NerSpan], source: str, voter: GlinerDetector | SpacyDetector) -> list[_RawVote]:
        mid = getattr(voter, "model_id", None) or getattr(voter, "model_name", None)
        # Read after the pass: both detectors learn their version only once the model has loaded.
        return [_RawVote(t, source, mid, voter.model_version) for s in spans if (t := _trimmed(s)) is not None]

    # ---- merge ----------------------------------------------------------

    def _rule_votes(self, text: str, known_names: Iterable[str]) -> list[tuple[int, int, Vote]]:
        out: list[tuple[int, int, Vote]] = []
        for names, source, score in (
            (list(self.known_aliases) + list(known_names), "gazetteer", GAZETTEER_VOTE_SCORE),
            (self.seed_names, "seed", SEED_VOTE_SCORE),
        ):
            gaz = Gazetteer()
            for n in names:
                gaz.add(n, AliasType.RIGID_NAME)
            for hit in gaz.find(text):
                out.append((hit.start, hit.end, Vote(source, "", score)))
        return out

    def candidates(self, text: str, known_names: Iterable[str] = ()) -> list[NameCandidate]:
        """Models, then rules, merged: overlapping spans become one candidate carrying all their votes."""
        if _digest(text) not in self._model_votes:
            self.precompute([text])
        votes: list[tuple[int, int, Vote]] = [
            (r.span.start, r.span.end, Vote(r.source, r.span.label, r.span.score, r.model_id, r.model_version))
            for r in self._model_votes[_digest(text)]
        ]
        votes += self._rule_votes(text, known_names)
        votes.sort(key=lambda v: (v[0], v[1]))

        clusters: list[list[tuple[int, int, Vote]]] = []
        end = -1
        for item in votes:
            if clusters and item[0] < end:
                clusters[-1].append(item)
                end = max(end, item[1])
            else:
                clusters.append([item])
                end = item[1]

        out: list[NameCandidate] = []
        for cluster in clusters:
            by_span: dict[tuple[int, int], list[Vote]] = {}
            for s, e, v in cluster:
                by_span.setdefault((s, e), []).append(v)
            # Most votes, then highest score, then longest: the span the most sources point at is the one least
            # likely to be a boundary slip by one of them.
            (s, e), _ = max(
                by_span.items(),
                key=lambda kv: (len(kv[1]), max(v.score for v in kv[1]), kv[0][1] - kv[0][0]),
            )
            out.append(NameCandidate.build(text[s:e], s, e, tuple(v for _s, _e, v in cluster)))
        return out

    # ---- routing --------------------------------------------------------

    def _wordlike(self, surface: str) -> bool:
        return _is_common_word(surface) or (self.is_wordlike is not None and self.is_wordlike(surface))

    @staticmethod
    def _label(c: NameCandidate, prefer: str | None = None) -> str:
        labelled = [v for v in c.votes if v.label]
        if prefer is not None and any(v.label == prefer for v in labelled):
            return prefer
        return max(labelled, key=lambda v: v.score).label if labelled else "character"

    def _route(self, c: NameCandidate) -> ClassifiedCandidate:
        def done(route: Route, why: str, label: str | None = None) -> ClassifiedCandidate:
            return ClassifiedCandidate(c, label or self._label(c), route == "accept", route, why)

        sources = c.sources
        if "gazetteer" in sources:
            return done("accept", "confirmed gazetteer alias")
        if self.fast:
            # No classifier to consult and no second voter: one GLiNER vote at the measured threshold is the whole
            # decision. A candidate only a rule voted for (a Layer-0 seed) is not enough on its own.
            gliner = [v for v in c.votes if v.source == "gliner" and v.score >= FAST_GLINER_THRESHOLD]
            if gliner:
                best = max(gliner, key=lambda v: v.score)
                return done("accept", f"fast: gliner {best.score:.2f} >= {FAST_GLINER_THRESHOLD}", best.label)
            return done("reject", "fast: no gliner vote at the threshold")
        if len(sources) == 1 and c.max_score < self.tau_low:
            return done("reject", f"single source {next(iter(sources))} scored {c.max_score:.2f} < tau_low {self.tau_low}")
        # Before the tau_high accept on purpose: a common word scores high as a "name" exactly when it is not one
        # ("Will it hold?"), so a confident vote must not skip the sentence-context check.
        if self._wordlike(c.surface):
            return done("classifier", "surface is a common word")
        gliner = [v for v in c.votes if v.source == "gliner"]
        if gliner and (best := max(gliner, key=lambda v: v.score)).score >= self.tau_high:
            return done("accept", f"gliner {best.score:.2f} >= tau_high {self.tau_high}", best.label)
        labelless = {v.source for v in c.votes if not v.label}
        for label in sorted({v.label for v in c.votes if v.label}):
            agreeing = {v.source for v in c.votes if v.label == label} | labelless
            if len(agreeing) >= 2:
                return done("accept", f"{'+'.join(sorted(agreeing))} agree on {label}", label)
        if len({v.label for v in c.votes if v.label}) > 1:
            return done("classifier", "sources disagree on the label")
        return done("classifier", "one mid-score vote")

    def detect_candidates(
        self, text: str, known_names: Iterable[str] = (), *, chapter: float | None = None
    ) -> list[ClassifiedCandidate]:
        """Every candidate with its route, so provenance survives to the caller (rejects included)."""
        routed = [self._route(c) for c in self.candidates(text, known_names)]
        asking = [i for i, r in enumerate(routed) if r.route == "classifier"]
        if asking:
            verdicts: list[Verdict | None] = [None] * len(asking)
            if self.classifier is not None:
                verdicts = self.classifier(text, [routed[i].candidate for i in asking], chapter=chapter)
            for i, verdict in zip(asking, verdicts, strict=True):
                r = routed[i]
                if self.classifier is None:
                    routed[i] = ClassifiedCandidate(
                        r.candidate, r.label, False, "classifier", f"{r.evidence}; no classifier, rejected"
                    )
                elif verdict is None:
                    routed[i] = ClassifiedCandidate(
                        r.candidate, r.label, False, "classifier", f"{r.evidence}; classifier gave no verdict"
                    )
                else:
                    routed[i] = ClassifiedCandidate(
                        r.candidate,
                        verdict.label if verdict.is_name else r.label,
                        verdict.is_name,
                        "classifier",
                        f"{r.evidence}; classifier: {verdict.reason or ('name' if verdict.is_name else 'not a name')}",
                    )
        for r in routed:
            self.route_counts[r.route if r.route != "classifier" else f"classifier_{'accept' if r.accepted else 'reject'}"] += 1
        return routed

    # ---- MentionDetector ------------------------------------------------

    def may_promote(self, surface: str, evidence_json: str | None) -> bool:
        """Whether an accepted hybrid mention may be fed back as a confirmed alias for later chapters.

        A common-word surface accepted only by the classifier would otherwise become a gazetteer voter next chapter
        and be accepted at every "will" with no context check, compounding one false positive into many. Those
        stay out until the review/gazetteer confirmation path confirms them. Non-word-like names are unaffected.
        """
        if not self._wordlike(surface):
            return True
        try:
            sources = {v["source"] for v in json.loads(evidence_json or "{}").get("votes", [])}
        except (ValueError, TypeError, KeyError):
            return False
        return "gazetteer" in sources

    def detect_with_context(
        self, text: str, known_names: list[str], *, chapter: float | None = None
    ) -> list[NerSpan]:
        # `known_names` is the runner's roster of names already seen: for this detector those are the "confirmed
        # aliases" (the runner's own gazetteer matches them exactly with or without us).
        return [
            _to_span(r, positional=self._wordlike(r.candidate.surface), detector="fast" if self.fast else "hybrid")
            for r in self.detect_candidates(text, known_names, chapter=chapter)
            if r.accepted
        ]

    def detect(self, text: str) -> list[NerSpan]:
        return self.detect_with_context(text, [])


def _to_span(r: ClassifiedCandidate, *, positional: bool = False, detector: str = "hybrid") -> NerSpan:
    c = r.candidate
    model_votes = [v for v in c.votes if v.source in _MODEL_SOURCES]
    best = max(model_votes, key=lambda v: v.score, default=None)
    evidence = json.dumps(
        {
            "route": r.route,
            "evidence": r.evidence,
            "votes": [
                {"source": v.source, "label": v.label, "score": round(v.score, 4),
                 "model_id": v.model_id, "model_version": v.model_version}
                for v in c.votes
            ],
        },
        sort_keys=True,
    )
    return NerSpan(
        text=c.surface,
        start=c.start,
        end=c.end,
        label=r.label,
        score=c.max_score,
        positional=positional,
        provenance=SpanProvenance(
            detector=detector,
            model_id=best.model_id if best else None,
            model_version=best.model_version if best else None,
            ner_score=best.score if best else None,
            evidence_json=evidence,
        ),
    )


def _importable(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _spacy_ready(model_name: str) -> bool:
    """spaCy and its model both installed: the package without the model fails on the first sentence, mid-run."""
    if not _importable("spacy"):
        return False
    try:
        import spacy

        return bool(spacy.util.is_package(model_name))
    except Exception:
        return False


def build_hybrid_detector(
    settings: object,
    *,
    client: object | None,
    classifier: Classifier | None = None,
    seed_names: Iterable[str] = (),
    is_wordlike: Callable[[str], bool] | None = None,
    fast: bool = False,
) -> HybridDetector | None:
    """The configured hybrid (or, with `fast`, GLiNER-only) detector, or None when it must not be built (the caller
    then runs the legacy path).

    None, with a warning, when the run is a stub run or GLiNER is not importable. Stub runs are the CI and offline
    iteration mode and must never download or load a model; an install without the `ml` extra must still run.
    spaCy is optional: without it (or its model) GLiNER votes alone.
    """
    from echotales.pipeline.config import LLMMode, ModelBackend

    kind = "fast" if fast else "hybrid"

    stub = getattr(settings, "llm_mode", None) is LLMMode.STUB or getattr(client, "backend", None) is ModelBackend.STUB
    if stub:
        log.warning("mentions.detector=%s ignored in stub mode (no models are loaded); using the legacy path", kind)
        return None
    if not _importable("gliner"):
        log.warning("mentions.detector=%s needs the `ml` extra (gliner is not importable); using the legacy path", kind)
        return None
    model = str(getattr(settings, "mentions_gliner_model", "urchade/gliner_medium-v2.1"))
    if fast:
        return HybridDetector(
            gliner=GlinerDetector(model, threshold=FAST_GLINER_THRESHOLD), is_wordlike=is_wordlike, fast=True,
        )
    tau_high = float(getattr(settings, "mentions_tau_high", TAU_HIGH))
    tau_low = float(getattr(settings, "mentions_tau_low", TAU_LOW))
    # GLiNER's own cut is tau_low, not its 0.5 default: a vote it drops never reaches routing, which would make the
    # reject band and the two-source agreement rule unreachable below 0.5.
    gliner = GlinerDetector(model, threshold=tau_low)
    spacy = None
    if _spacy_ready("en_core_web_sm"):
        spacy = SpacyDetector("en_core_web_sm")
    else:
        log.warning("spaCy or en_core_web_sm is missing; the hybrid detector runs on GLiNER and the gazetteer alone")
    return HybridDetector(
        gliner=gliner,
        spacy=spacy,
        seed_names=seed_names,
        classifier=classifier,
        tau_high=tau_high,
        tau_low=tau_low,
        is_wordlike=is_wordlike,
    )
