"""Phase 6 orchestration: incremental global resolution.

For each local mention group, in discourse order, ask: is this an existing
entity or someone new? Retrieve, score, gate, and either link, create, or
defer. Deferred cases are revisited at window boundaries, when the accumulated
evidence has grown.

Order is not an implementation detail. Processing strictly in discourse order
is what makes the knowledge-time axis meaningful: an entity profile at chapter
40 contains only what had been read by chapter 40, so a link made there cannot
be justified by evidence from chapter 190. Reveals reach backwards through the
event log instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from echotales.core.enums import (
    OBSERVER_READER,
    AliasType,
    AssertedBy,
    Decision,
    EventType,
    ResolutionMethod,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding,
    Candidate,
    Mention,
    ResolutionEvent,
    ResolutionOutcome,
    Self,
)
from echotales.core.readset import ReadSetRecorder, entity_ref
from echotales.core.store import Store
from echotales.pipeline.config import Settings, get_settings
from echotales.pipeline.corrections import Correction, CorrectionLog, CorrectionType
from echotales.pipeline.ingest.normalize import display_label, name_tokens
from echotales.pipeline.llm import LLMRouter
from echotales.pipeline.mentions.lexicon import Lexicon
from echotales.pipeline.resolve.adjudicate import AdjudicationRequest, adjudicate
from echotales.pipeline.resolve.detectors import run_detectors
from echotales.pipeline.resolve.evidence import EvidenceContext, score_evidence
from echotales.pipeline.resolve.gate import ConformalGate, DeferredCase, DeferredQueue
from echotales.pipeline.resolve.retrieve import CandidateRetriever
from echotales.pipeline.resolve.score import ScoringModel

log = logging.getLogger(__name__)

#: Characters of surrounding text supplied as evidence context.
_CONTEXT_WINDOW = 400

#: Section 5.1: alias types that never found a new entity on their own. A
#: relational deictic ("this one") always refers to someone named
#: elsewhere; a transferable title ("the clan head") names a *position*,
#: not an individual, and outlives whoever currently holds it -- minting an
#: entity from either mints a duplicate with no retrievable identity.
_NON_FOUNDING_ALIAS_TYPES = frozenset({AliasType.RELATIONAL_DEICTIC, AliasType.TRANSFERABLE_TITLE})

#: Section 2.2: fraction of a novel's entities with a raw-NULL `kind` column
#: (never positively typed, backfill included) above which the SELF default
#: is standing in for "unknown" often enough to be a pipeline gap, not
#: individually-fine unknowns. Calibrated against the real production RI
#: database (`data/webview-working/reverend-insanity.db`), which sits at 78%
#: post-backfill and is HANDOFF-documented as spot-checked mostly-correct
#: (2/15 real gaps) -- so this warns well below that, but does not treat
#: RI's own current, known, partially-typed state as fatal.
_KIND_UNKNOWN_WARN_THRESHOLD = 0.30


@dataclass(slots=True)
class ResolveReport:
    novel_id: str
    groups: int = 0
    linked: int = 0
    created: int = 0
    deferred: int = 0
    adjudicated: int = 0
    recovered_from_deferral: int = 0
    unresolved: int = 0
    #: Groups that never used a naming mention, so could not found an entity.
    deictic_only: int = 0
    entities: int = 0
    contradictions: int = 0
    splits: int = 0
    contradiction_kinds: dict[str, int] = field(default_factory=dict)
    #: Entities typed as something other than a person (Section 10 item 5). Counted
    #: separately from `entities` rather than subtracted from it: they are
    #: real resolved entities, they just must never be cast a voice.
    by_kind: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)
    detector_hits: dict[str, int] = field(default_factory=dict)
    events: int = 0
    #: Section 2.2: entities whose raw `self_entity.kind` column is still
    #: NULL/empty after the unconditional backfill runs -- i.e. nobody has
    #: ever positively typed them, so `Store.get_self()`'s SELF default is
    #: standing in for "unknown," not "confirmed person." Kept distinct from
    #: `by_kind` (which only counts entities *positively* typed non-person):
    #: a novel can have zero `by_kind` entries and still be mostly untyped.
    kind_unknown: int = 0

    @property
    def defer_rate(self) -> float:
        return self.deferred / self.groups if self.groups else 0.0

    @property
    def kind_unknown_fraction(self) -> float:
        return self.kind_unknown / self.entities if self.entities else 0.0

    def summary(self) -> str:
        methods = ", ".join(f"{k}={v}" for k, v in sorted(self.by_method.items())) or "none"
        detectors = (
            ", ".join(f"{k}={v}" for k, v in sorted(self.detector_hits.items())) or "none"
        )
        non_person = ", ".join(f"{k}={v}" for k, v in sorted(self.by_kind.items())) or "none"
        kind_line = (
            f"  kind coverage: {self.entities - self.kind_unknown:,}/{self.entities:,} typed "
            f"({self.kind_unknown:,} unknown, {self.kind_unknown_fraction:.0%}) "
            f"{'-- SEE WARNING ABOVE' if self.kind_unknown_fraction > _KIND_UNKNOWN_WARN_THRESHOLD else ''}\n"
        )
        return (
            f"{self.novel_id}: {self.groups:,} groups -> {self.entities:,} entities\n"
            f"  linked={self.linked:,}  created={self.created:,}  "
            f"deferred={self.deferred:,} ({self.defer_rate:.1%})  "
            f"recovered={self.recovered_from_deferral:,}  unresolved={self.unresolved:,}\n"
            f"  deictic-only groups (no entity created): {self.deictic_only:,}\n"
            f"  non-person entities (not voice-cast): {non_person}\n"
            f"{kind_line}"
            f"  methods: {methods}\n"
            f"  detectors: {detectors}\n"
            f"  contradictions: {self.contradictions} -> {self.splits} split(s)\n"
            f"  events logged: {self.events:,}"
        )


def _context_for(mention: Mention, chapter_text: str) -> str:
    """Text around a mention, for declarations and context similarity."""
    centre = chapter_text.find(mention.text)
    if centre < 0:
        return chapter_text[:_CONTEXT_WINDOW]
    lo = max(0, centre - _CONTEXT_WINDOW // 2)
    return chapter_text[lo : lo + _CONTEXT_WINDOW]


class GlobalResolver:
    """Incremental entity resolution with evidence accumulation.

    Explicitly not clustering (non-negotiable #1): each mention group is
    resolved against the entities established so far, and the decision is
    recorded as an event with the evidence that produced it.
    """

    def __init__(
        self,
        novel_id: str,
        store: Store,
        *,
        lexicon: Lexicon | None = None,
        model: ScoringModel | None = None,
        gate: ConformalGate | None = None,
        router: LLMRouter | None = None,
        settings: Settings | None = None,
        corrections_log: CorrectionLog | None = None,
    ) -> None:
        self.novel_id = novel_id
        self.store = store
        self.lexicon = lexicon or Lexicon()
        self.model = model or ScoringModel()
        self.settings = settings or get_settings()
        self.gate = gate or ConformalGate(alpha=self.settings.conformal_alpha)
        self.router = router
        self.retriever = CandidateRetriever()
        self.queue = DeferredQueue()
        self.report = ResolveReport(novel_id=novel_id)
        self._next_entity = 0
        #: When set, a newly-created entity founded mostly on mentions NER
        #: itself labeled "location"/"organization" rather than "character"
        #: gets an automatic review flag -- see `_maybe_flag_non_character`.
        #: `None` by default so every existing caller keeps today's behaviour.
        self.corrections_log = corrections_log

    def _ambiguous_tokens(self) -> frozenset[str]:
        """Name components shared by two or more entities seen so far.

        Feeds `normalize.name_containment`'s single-token case (Section 4.15's
        `Dokja`/`Kim Dokja` gap): a token that only ever appears in one
        entity's aliases identifies that entity specifically (a given name);
        one that recurs across several is a bare surname or title and must
        not merge unrelated people on its own (Section 4.5). Recomputed per call
        rather than cached — `EntityProfile.aliases` grows as resolution
        proceeds, and the corpus is small enough (a few hundred entities at
        most) that this costs nothing next to retrieval/scoring.
        """
        counts: dict[str, set[str]] = {}
        for profile in self.retriever.profiles.values():
            for alias in profile.aliases:
                for token in name_tokens(alias):
                    counts.setdefault(token, set()).add(profile.target_id)
        return frozenset(token for token, ids in counts.items() if len(ids) > 1)

    # ---- entity lifecycle ---------------------------------------------

    #: NER's own label vocabulary -> the entity kind it implies. "character"
    #: is absent on purpose: it maps to the `TargetKind.SELF` default, and
    #: listing it would invite a caller to treat this dict as exhaustive.
    _KIND_BY_LABEL = {
        "location": TargetKind.LOCATION,
        "organization": TargetKind.ORGANIZATION,
        "item": TargetKind.ITEM,
    }

    def _entity_kind(self, founding_mentions: list[Mention]) -> TargetKind:
        """Type a new entity from the NER labels its founding mentions carry.

        **Unanimous, not majority**, and identical in spirit to
        `_maybe_flag_non_character`: any mention NER did call "character" is
        enough to stay a person. A wrong `SELF` costs a spurious row in the
        cast list (visible, correctable); a wrong `LOCATION` silently removes
        a real character from voice casting and panel casting at once, which
        is both worse and much harder to notice.
        """
        labels = [m.entity_label for m in founding_mentions if m.entity_label]
        if not labels or any(label == "character" for label in labels):
            return TargetKind.SELF
        kinds = {self._KIND_BY_LABEL.get(label) for label in labels}
        if len(kinds) == 1 and (only := kinds.pop()) is not None:
            return only
        return TargetKind.SELF

    def _create_entity(
        self, mention: Mention, label: str, kind: TargetKind = TargetKind.SELF
    ) -> str:
        self._next_entity += 1
        target_id = f"{self.novel_id}:self{self._next_entity}"
        self.store.add_self(
            Self(
                id=target_id,
                novel_id=self.novel_id,
                canonical_label=label,
                first_attested_pos=mention.position,
                kind=kind,
            )
        )
        self.report.created += 1
        if kind is not TargetKind.SELF:
            self.report.by_kind[kind.value] = self.report.by_kind.get(kind.value, 0) + 1
        return target_id

    def _maybe_flag_non_character(
        self, target_id: str, label: str, founding_mentions: list[Mention]
    ) -> None:
        """Auto-flag an entity founded entirely on non-"character" NER labels.

        Not a filter -- see `mentions/runner.py`'s `rejected()` docstring on
        why a blunt kind filter over-deletes real entities like a clan name
        or a central plot item, which this project has already been burned
        by once. This only leaves a review note on entities that would
        otherwise silently join the voice-cast list as if they were people.
        Unanimous rather than majority: any mention NER did call "character"
        is enough signal to stay quiet rather than risk a false flag.
        """
        if self.corrections_log is None:
            return
        labels = [m.entity_label for m in founding_mentions if m.entity_label]
        if not labels or any(label_name == "character" for label_name in labels):
            return
        if not all(label_name in ("location", "organization") for label_name in labels):
            return
        kind = labels[0] if len(set(labels)) == 1 else "/".join(sorted(set(labels)))
        self.corrections_log.add(
            Correction(
                novel_id=self.novel_id,
                type=CorrectionType.FLAG,
                payload={
                    "span_id": None,
                    "target_id": target_id,
                    "note": (
                        f"Auto-flagged: every founding mention of {label!r} was NER-labeled "
                        f"{kind!r}, not 'character' -- likely a location/organization rather "
                        f"than a person. Review before it's treated as a voice-cast character."
                    ),
                    "source": "agent:pipeline",
                },
            )
        )

    def _bind_alias(
        self,
        mention: Mention,
        target_id: str,
        *,
        truth_status: TruthStatus = TruthStatus.TRUE,
        asserted_by: AssertedBy = AssertedBy.NARRATOR,
        evidence: str = "",
        confidence: float = 1.0,
    ) -> None:
        """Persist an alias binding.

        Generic descriptors are rejected by `AliasBinding` itself, so nothing
        here needs to remember the rule.
        """
        if not mention.alias_type.enters_graph:
            return
        self.store.add_alias_binding(
            self.novel_id,
            AliasBinding(
                alias=mention.text,
                alias_type=mention.alias_type,
                target_kind=TargetKind.SELF,
                target_id=target_id,
                # Open-ended from this position, with evidence up to here. The
                # interval decays to PLAUSIBLE beyond the last sighting rather
                # than asserting the binding holds forever.
                interval=FuzzyInterval.open_ended(
                    mention.chapter, last_evidence=mention.chapter
                ),
                learned_at_pos=mention.position,
                observer_id=OBSERVER_READER,
                asserted_by=asserted_by,
                truth_status=truth_status,
                evidence=evidence[:200],
                confidence=confidence,
            ),
        )

    def _log(
        self,
        event_type: EventType,
        mention: Mention,
        payload: dict[str, object],
        *,
        method: ResolutionMethod | None = None,
        confidence: float = 1.0,
        read_set: list[str] | None = None,
    ) -> None:
        recorder = ReadSetRecorder()
        recorder.record_many(read_set or [])
        self.store.append_event(
            ResolutionEvent(
                id=f"{self.novel_id}:{mention.id}:{event_type.value}:{self.store.next_seq()}",
                seq=self.store.next_seq(),
                type=event_type,
                payload=payload,
                cause_pos=mention.position,
                read_set_hash=recorder.digest,
                method=method,
                confidence=confidence,
            )
        )
        self.report.events += 1

    # ---- the decision ---------------------------------------------------

    def resolve_group(
        self,
        mentions: list[Mention],
        chapter_text: str,
        *,
        co_present: frozenset[str] = frozenset(),
        speaker: str | None = None,
    ) -> ResolutionOutcome:
        """Resolve one local mention group."""
        head = mentions[0]
        label = display_label(m.text for m in mentions)
        context = _context_for(head, chapter_text)

        candidates = self.retriever.retrieve(head.text, context)

        # Section 5.1: a title/relational mention never resolves through
        # surface similarity -- "the clan head" and "Fang Yuan" share no
        # tokens, so `retrieve()` above cannot surface the right candidate
        # no matter how it's tuned (confirmed empirically, Section 1.2's
        # recall@k gate: 0% retrieval on TRANSFERABLE_TITLE/
        # RELATIONAL_DEICTIC). Widen the candidate list instead with every
        # already-resolved entity this chapter has established as
        # physically present -- relationship context, not surface text, is
        # the query for these alias types.
        sole_copresent_target_id: str | None = None
        if any(
            m.alias_type in (AliasType.RELATIONAL_DEICTIC, AliasType.TRANSFERABLE_TITLE)
            for m in mentions
        ):
            seen_ids = {c.target_id for c in candidates}
            for profile in self.retriever.profiles.values():
                if profile.label in co_present and profile.target_id not in seen_ids:
                    candidates.append(
                        Candidate(
                            target_kind=profile.target_kind,
                            target_id=profile.target_id,
                            label=profile.label,
                            retrieval_score=0.0,
                        )
                    )
                    seen_ids.add(profile.target_id)
            copresent = [c for c in candidates if c.label in co_present]
            # Exactly one, never a tie -- two rival co-present candidates is
            # precisely the six-Wang case Section 5.3 guards against, and
            # must defer rather than guess between them.
            if len(copresent) == 1:
                sole_copresent_target_id = copresent[0].target_id

        ctx = EvidenceContext(
            context=context,
            co_present=co_present,
            speaker=speaker,
            sole_copresent_target_id=sole_copresent_target_id,
            lexicon=self.lexicon,
            ambiguous_tokens=self._ambiguous_tokens(),
        )
        for candidate in candidates:
            candidate.evidence = score_evidence(
                head, candidate, self.retriever.profiles.get(candidate.target_id), ctx
            )
        candidates = self.model.score_candidates(candidates)

        decision, best, rationale = self.gate.decide(candidates)
        group_id = head.local_group_id or head.id

        if decision is Decision.DEFER:
            self.queue.add(
                DeferredCase(
                    group_id=group_id,
                    chapter=head.chapter,
                    surface=head.text,
                    context=context,
                    candidates=candidates,
                    reason=rationale,
                )
            )
            self.report.deferred += 1
            return ResolutionOutcome(
                group_id=group_id,
                decision=Decision.DEFER,
                candidates=candidates,
                rationale=rationale,
            )

        if decision is Decision.LINK and best is not None:
            self._apply_link(mentions, best.target_id, context, ResolutionMethod.SCORED)
            return ResolutionOutcome(
                group_id=group_id,
                decision=Decision.LINK,
                target_kind=TargetKind.SELF,
                target_id=best.target_id,
                probability=best.probability,
                method=ResolutionMethod.SCORED,
                candidates=candidates,
                rationale=rationale,
            )

        # A group that never once said a name cannot found an entity. "sir",
        # "Grandpa", "this one" refer to someone who is named elsewhere, and
        # (Section 5.1) so does a bare title like "the clan head" -- the
        # position outlives whoever holds it, so a title-only group minting
        # its own entity would found a person keyed to a role, not an
        # individual, and orphan it the moment the title changes hands.
        # Minting an entity here creates a duplicate of a real character
        # *and* an entity with no retrievable identity either way. Leaving
        # it unresolved is the honest outcome — the sole-co-present-
        # candidate path above may still bind it; anaphora or a later
        # window may too.
        if not any(m.alias_type.enters_graph and m.alias_type not in _NON_FOUNDING_ALIAS_TYPES
                   for m in mentions):
            self.report.deictic_only += 1
            return ResolutionOutcome(
                group_id=group_id,
                decision=Decision.DEFER,
                candidates=candidates,
                rationale="deictic/title-only group: no naming mention to found an entity on",
            )

        target_id = self._create_entity(head, label, self._entity_kind(mentions))
        self._maybe_flag_non_character(target_id, label, mentions)
        self._apply_link(mentions, target_id, context, ResolutionMethod.SCORED, new=True)
        return ResolutionOutcome(
            group_id=group_id,
            decision=Decision.NEW,
            target_kind=TargetKind.SELF,
            target_id=target_id,
            method=ResolutionMethod.SCORED,
            candidates=candidates,
            rationale=rationale,
        )

    def _apply_link(
        self,
        mentions: list[Mention],
        target_id: str,
        context: str,
        method: ResolutionMethod,
        *,
        new: bool = False,
    ) -> None:
        head = mentions[0]
        label = display_label(m.text for m in mentions)

        for mention in mentions:
            mention.target_kind = TargetKind.SELF
            mention.target_id = target_id
            mention.method = method
            self.retriever.observe(
                target_id,
                mention.text,
                context,
                mention.chapter,
                label=label,
            )
            self._bind_alias(mention, target_id, evidence=context[:120])

        self.store.add_mentions(mentions)
        if not new:
            self.report.linked += 1
        self.report.by_method[method.value] = self.report.by_method.get(method.value, 0) + 1
        self._log(
            EventType.NEW_ENTITY if new else EventType.LINK,
            head,
            {"target_id": target_id, "label": label, "mentions": len(mentions)},
            method=method,
            read_set=[entity_ref(TargetKind.SELF, target_id)],
        )

    # ---- deferred re-resolution -------------------------------------------

    def retry_deferred(self) -> int:
        """Re-resolve deferred cases against accumulated evidence.

        This is what makes deferral worth its cost: a case that was ambiguous
        at chapter 40 is often trivial by chapter 90, because the gazetteer has
        grown and the entity profiles carry far more context.
        """
        recovered = 0
        for case in self.queue.pop_ready():
            candidates = self.retriever.retrieve(case.surface, case.context)
            if not candidates:
                continue
            ctx = EvidenceContext(
                context=case.context,
                lexicon=self.lexicon,
                ambiguous_tokens=self._ambiguous_tokens(),
            )
            for candidate in candidates:
                candidate.evidence = score_evidence(
                    _synthetic_mention(case), candidate,
                    self.retriever.profiles.get(candidate.target_id), ctx,
                )
            candidates = self.model.score_candidates(candidates)
            decision, best, _ = self.gate.decide(candidates)
            if decision is Decision.LINK and best is not None:
                self.queue.remove(case.group_id)
                recovered += 1
                self.report.recovered_from_deferral += 1
                self.report.by_method[ResolutionMethod.DEFERRED_RERESOLVED.value] = (
                    self.report.by_method.get(
                        ResolutionMethod.DEFERRED_RERESOLVED.value, 0
                    )
                    + 1
                )
        return recovered

    def adjudicate_remaining(self) -> int:
        """Send exhausted deferrals to the LLM.

        Only reached after re-resolution has failed repeatedly, which keeps the
        expensive tier on the cases that genuinely need it.
        """
        if self.router is None:
            return 0
        count = 0
        for case in self.queue.exhausted():
            outcome = adjudicate(
                AdjudicationRequest(
                    group_id=case.group_id,
                    surface=case.surface,
                    context=case.context,
                    chapter=case.chapter,
                    candidates=case.candidates,
                ),
                self.router,
                self.retriever.profiles,
                self.model,
                novel_id=self.novel_id,
            )
            count += 1
            self.report.adjudicated += 1
            if outcome.decision is not Decision.DEFER:
                self.queue.remove(case.group_id)
                self.report.by_method[ResolutionMethod.LLM_ADJUDICATED.value] = (
                    self.report.by_method.get(ResolutionMethod.LLM_ADJUDICATED.value, 0) + 1
                )
        return count

    # ---- contradiction sweep -----------------------------------------------

    def sweep_contradictions(self, *, window: int = 0) -> int:
        # A window boundary is exactly the point Section 4.2 nominates for clearing
        # the retriever's cached prominence ranking: enough mentions have
        # accumulated since the last rebuild that the drift it tolerates is
        # worth discarding.
        self.retriever.refresh_prominent()
        """Re-check committed links against evidence accumulated since.

        The gazetteer compounds wrong decisions as readily as right ones: a bad
        link adds a surface form, the automaton then exact-matches it forever,
        and the pre-filter force-links on it. Nothing in the forward pass can
        undo that, so this backward pass exists.

        Affected entities are returned to the deferred queue rather than being
        repaired here — the detector proposes, adjudication disposes.
        """
        from echotales.pipeline.resolve.contradiction import sweep

        found, report = sweep(
            self.novel_id, self.store, self.retriever.profiles, window=window
        )
        self.report.contradictions += report.contradictions
        self.report.splits += report.splits_emitted
        for kind, count in report.by_kind.items():
            self.report.contradiction_kinds[kind] = (
                self.report.contradiction_kinds.get(kind, 0) + count
            )

        for contradiction in found:
            profile = self.retriever.profiles.get(contradiction.target_id)
            if profile is None:
                continue
            self.queue.add(
                DeferredCase(
                    group_id=f"contradiction:{contradiction.target_id}:{window}",
                    chapter=profile.last_chapter,
                    surface=contradiction.surfaces[0] if contradiction.surfaces else profile.label,
                    context=" ".join(
                        t for t, _ in profile.context_terms.most_common(40)
                    ),
                    reason=f"{contradiction.kind.value}: {contradiction.detail}",
                )
            )
        return report.splits_emitted

    # ---- detectors ---------------------------------------------------------

    def run_detectors_on(self, text: str, mention: Mention) -> None:
        """Emit events for transfers, deceptions, reveals, deaths, reputation."""
        for hit in run_detectors(text, self.lexicon):
            self.report.detector_hits[hit.kind.value] = (
                self.report.detector_hits.get(hit.kind.value, 0) + 1
            )
            self._log(
                hit.event_type,
                mention,
                {
                    "detector": hit.kind.value,
                    "subject": hit.subject,
                    "object": hit.object,
                    "evidence": hit.evidence[:160],
                    "truth_status": hit.truth_status.value if hit.truth_status else None,
                },
                confidence=hit.confidence,
            )


def _synthetic_mention(case: DeferredCase) -> Mention:
    """Rebuild a mention stand-in for re-scoring a deferred case."""
    from echotales.core.enums import ReferenceMode, SpanType

    return Mention(
        id=case.group_id,
        novel_id="",
        segment_id="",
        chapter=case.chapter,
        offset=0,
        text=case.surface,
        alias_type=AliasType.RIGID_NAME,
        span_type=SpanType.NARRATION_ACTION,
        reference_mode=ReferenceMode.PRESENT,
    )


def resolve_novel(
    novel_id: str,
    store: Store,
    *,
    lexicon: Lexicon | None = None,
    model: ScoringModel | None = None,
    gate: ConformalGate | None = None,
    router: LLMRouter | None = None,
    settings: Settings | None = None,
    use_llm: bool = False,
    commit_every: int = 10,
    corrections_log: CorrectionLog | None = None,
    strict_kind_check: bool = False,
) -> ResolveReport:
    """Run global resolution over a whole novel, in discourse order."""
    # Prevent UNIQUE constraint violations by clearing existing resolution state for this novel
    store.conn.execute("DELETE FROM resolution_event WHERE id LIKE ?", (f"{novel_id}:%",))
    store.conn.execute("DELETE FROM alias_binding WHERE novel_id=?", (novel_id,))
    store.conn.execute("DELETE FROM self_entity WHERE novel_id=?", (novel_id,))
    store.conn.execute("DELETE FROM self_persona_binding WHERE self_id LIKE ?", (f"{novel_id}:%",))
    store.conn.execute("UPDATE mention SET target_kind=NULL, target_id=NULL, method=NULL WHERE novel_id=?", (novel_id,))
    store.conn.commit()

    cfg = settings or get_settings()
    resolver = GlobalResolver(
        novel_id,
        store,
        lexicon=lexicon,
        model=model,
        gate=gate,
        router=router if use_llm else None,
        settings=cfg,
        corrections_log=corrections_log,
    )

    for i, chapter in enumerate(store.iter_chapters(novel_id), start=1):
        mentions = store.get_mentions(novel_id, chapter.number)
        if not mentions:
            continue
        chapter_text = chapter.story_text

        # Group by the local group id from Phase 5; ungrouped mentions resolve
        # individually rather than being silently dropped.
        groups: dict[str, list[Mention]] = {}
        for mention in mentions:
            groups.setdefault(mention.local_group_id or mention.id, []).append(mention)

        co_present = frozenset(
            m.text for m in mentions if m.reference_mode.is_physically_present
        )

        for group in groups.values():
            resolver.resolve_group(group, chapter_text, co_present=co_present)
            resolver.report.groups += 1

        if mentions:
            resolver.run_detectors_on(chapter_text, mentions[0])

        # Window boundary: re-check committed links, then retry deferrals.
        #
        # Order matters. The contradiction sweep runs first so that a link
        # withdrawn this window is back in the deferred queue before the retry
        # pass considers it -- otherwise a wrong link survives an extra window
        # and keeps attracting mentions through the gazetteer.
        if i % cfg.window_size == 0:
            resolver.sweep_contradictions(window=i // cfg.window_size)
            resolver.retry_deferred()

        if i % commit_every == 0:
            store.conn.commit()

    # Final sweep: the last partial window never hit a boundary.
    resolver.sweep_contradictions(window=-1)
    resolver.retry_deferred()
    if use_llm and router is not None:
        resolver.adjudicate_remaining()

    resolver.report.unresolved = len(resolver.queue)
    resolver.report.entities = len(resolver.retriever)

    # Legacy-kind backfill, always run (EVOLUTION 4.54): `_entity_kind`
    # above only types entities minted *this* run. A novel resolved before
    # that classification existed left `self_entity.kind` NULL, which reads
    # back as SELF (a person) -- see kind_backfill.py's docstring for the
    # measured defect this closes. Cheap and a no-op when everything is
    # already typed, so it costs nothing to run unconditionally.
    from echotales.pipeline.resolve.kind_backfill import backfill_kinds

    backfill_stats = backfill_kinds(
        store, novel_id, Path(cfg.lexicon_path) / f"{novel_id}-ner-cache.json"
    )
    if backfill_stats["checked"]:
        log.info(
            "kind backfill: checked=%d classified=%d left_default=%d",
            backfill_stats["checked"],
            backfill_stats["classified"],
            backfill_stats["left_default"],
        )

    # Section 2.2 startup assertion: raw-NULL kind, checked *after* backfill
    # so this counts only what evidence genuinely could not resolve, not what
    # the (cheap, always-run) backfill above would have fixed anyway.
    still_unknown = len(store.unset_kind_self_ids(novel_id))
    resolver.report.kind_unknown = still_unknown
    if resolver.report.entities and resolver.report.kind_unknown_fraction > _KIND_UNKNOWN_WARN_THRESHOLD:
        message = (
            f"KIND COVERAGE WARNING: {still_unknown}/{resolver.report.entities} "
            f"({resolver.report.kind_unknown_fraction:.0%}) of {novel_id}'s entities have "
            "no positive kind classification (self_entity.kind is raw-NULL) even after "
            "the backfill ran. Store.get_self() reads that back as TargetKind.SELF, so "
            "these will be treated as people (voice-cast, panel-cast, webview) with zero "
            "evidence either way -- this is the exact shape of the Qing Mao Mountain "
            "defect (EVOLUTION 4.56) recurring at scale. Likely cause: entity_label was "
            "never written (Layer-1 NER pass didn't run) or the NER cache at "
            f"{Path(cfg.lexicon_path) / f'{novel_id}-ner-cache.json'} is missing/empty for "
            "this novel. A 15-row spot-check is not a substitute for this number being "
            "high on a *new* novel -- RI's own 78% is HANDOFF-documented and spot-checked; "
            "an unfamiliar novel at this level has not been checked at all."
        )
        if strict_kind_check:
            raise RuntimeError(message)
        log.warning(message)
        print(f"\n{'=' * 70}\n{message}\n{'=' * 70}\n")

    store.conn.commit()
    return resolver.report
