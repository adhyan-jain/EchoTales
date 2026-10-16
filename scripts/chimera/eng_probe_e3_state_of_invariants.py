"""E3. Adversarial invariants of `state_of` on synthetic stores. Pre-declaration:
docs/research/ENGINEERING_NOVELTY_PROBE/E3_state_of_invariants.md (written before this ran).

LABEL PROVENANCE: SYNTHETIC (expected values come from the documented spec sentences quoted per check, not from the code
under test). In-memory stores only; no database file is opened; no novel text.

    python scripts/chimera/eng_probe_e3_state_of_invariants.py --out data/eval/chimera/eng_probe_E3_state_of.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
from pathlib import Path

from echotales.core.enums import (
    OBSERVER_READER,
    OBSERVER_SYSTEM,
    AliasType,
    Canonicity,
    TargetKind,
    TruthStatus,
)
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    MAIN_TIMELINE,
    AliasBinding,
    Attribute,
    DiscoursePosition,
    NarrativeSegment,
    Observation,
    Persona,
    Relation,
    Self,
    SelfPersonaBinding,
)
from echotales.core.readset import observable_ref
from echotales.core.state import StateResolver
from echotales.core.store import Store

N = "n"
DP = DiscoursePosition


def new_store() -> Store:
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "generic")
    for sid in ("S1", "S2"):
        s.add_self(Self(id=sid, novel_id=N, canonical_label=sid, first_attested_pos=DP(chapter=1)))
    s.add_persona(Persona(id="P1", novel_id=N, body_label="P1", first_attested_pos=DP(chapter=1)))
    return s


def alias(s: Store, name: str, *, learned=(3, 0), iv=None, truth=TruthStatus.TRUE, observer=OBSERVER_READER,
          retracted=None, tl=MAIN_TIMELINE, target="S1") -> int:
    return s.add_alias_binding(N, AliasBinding(
        alias=name, alias_type=AliasType.RIGID_NAME, target_kind=TargetKind.SELF, target_id=target, timeline_id=tl,
        interval=iv or FuzzyInterval.open_ended(1), learned_at_pos=DP(chapter=learned[0], offset=learned[1]),
        observer_id=observer, truth_status=truth,
        retracted_at=None if retracted is None else DP(chapter=retracted[0], offset=retracted[1])))


def attr(s: Store, key: str, value: str, *, learned=(3, 0), iv=None, truth=TruthStatus.TRUE,
         observer=OBSERVER_READER, retracted=None, tl=MAIN_TIMELINE, target="P1", kind=TargetKind.PERSONA) -> int:
    return s.add_attribute(N, Attribute(
        target_kind=kind, target_id=target, key=key, value=value, timeline_id=tl,
        interval=iv or FuzzyInterval.open_ended(1), learned_at_pos=DP(chapter=learned[0], offset=learned[1]),
        observer_id=observer, truth_status=truth,
        retracted_at=None if retracted is None else DP(chapter=retracted[0], offset=retracted[1])))


def rel(s: Store, *, learned=(3, 0), iv=None, truth=TruthStatus.TRUE, observer=OBSERVER_READER, retracted=None) -> int:
    return s.add_relation(N, Relation(
        src_self="S1", dst_self="S2", type="knows", interval=iv or FuzzyInterval.open_ended(1),
        learned_at_pos=DP(chapter=learned[0], offset=learned[1]), observer_id=observer, truth_status=truth,
        retracted_at=None if retracted is None else DP(chapter=retracted[0], offset=retracted[1])))


def binding(s: Store, *, learned=(3, 0), iv=None, truth=TruthStatus.TRUE, tl=MAIN_TIMELINE) -> None:
    s.add_self_persona_binding(SelfPersonaBinding(
        self_id="S1", persona_id="P1", timeline_id=tl, interval=iv or FuzzyInterval.open_ended(1),
        learned_at_pos=DP(chapter=learned[0], offset=learned[1]), observer_id=OBSERVER_READER, truth_status=truth))


def sees(s: Store, kind: str, *, p: float, observer: str = OBSERVER_READER, k: DP | None = None, tl=MAIN_TIMELINE) -> bool:
    r = StateResolver(s, N).state_of("S1", position=p, observer_id=observer, knowledge_pos=k, timeline_id=tl)
    return {"alias": bool(r.aliases), "attribute": False, "relation": bool(r.relationships),
            "persona": bool(r.persona_ids)}[kind] if kind != "attribute" else bool(
        StateResolver(s, N).state_of("P1", target_kind=TargetKind.PERSONA, position=p, observer_id=observer,
                                     knowledge_pos=k, timeline_id=tl).attributes)


ADD = {"alias": lambda s, **kw: alias(s, "Xname", **kw), "attribute": lambda s, **kw: attr(s, "hair", "white", **kw),
       "relation": lambda s, **kw: rel(s, **kw), "persona": lambda s, **kw: binding(s, **kw)}


def check_retraction_vs_interval_end() -> dict:
    """I3. architecture.md Section 5: retract = 'was never true', still believed before the reveal; close = 'was true, then stopped'."""
    out = {}
    for kind in ("alias", "attribute", "relation", "persona"):
        res = {}
        # retraction at ch10 (offset 0): visible while the reader stands before it, hidden from it on
        s = new_store()
        try:
            ADD[kind](s, retracted=(10, 0)) if kind != "persona" else binding(s)
            res["retracted_visible_at_ch9"] = sees(s, kind, p=9)
            res["retracted_hidden_at_ch10"] = not sees(s, kind, p=10)
            res["retracted_hidden_at_ch30"] = not sees(s, kind, p=30)
            res["retracted_hidden_story5_know30"] = not sees(s, kind, p=5, k=DP(chapter=30))
            res["retraction_representable"] = kind != "persona"
        except TypeError as e:  # no way to express retraction
            res["retraction_representable"] = False
            res["error"] = str(e)[:80]
        # closed interval: story time ends at 10, visible at story 5 from any later reading position
        s = new_store()
        iv = FuzzyInterval.point_known(1, 10)
        ADD[kind](s, iv=iv)
        res["closed_visible_story5_know30"] = sees(s, kind, p=5, k=DP(chapter=30))
        res["closed_hidden_story12_know30"] = not sees(s, kind, p=12, k=DP(chapter=30))
        out[kind] = res
    return out


def check_false_hidden_in_world() -> dict:
    """I4. state_of docstring 'Truth status': FALSE facts are hidden from in-world observers, visible to SYSTEM."""
    out = {}
    for kind in ("alias", "attribute", "relation", "persona"):
        s = new_store()
        ADD[kind](s, truth=TruthStatus.FALSE)
        out[kind] = dict(
            hidden_from_reader=not sees(s, kind, p=20),
            visible_to_system=sees(s, kind, p=20, observer=OBSERVER_SYSTEM),
        )
    return out


def check_retraction_is_observer_global() -> dict:
    """I5. architecture.md Section 5: a character observer does not inherit the reader's knowledge.

    The reader is told at ch20 that a claim (stamped READER, learned ch3) was false. Character C witnessed the claim
    at ch5 and, in the story, is never told. Nothing in the data model can say 'C learned of the retraction'.
    """
    s = new_store()
    bid = alias(s, "Xname", retracted=(20, 0))
    ref = observable_ref(s.get_aliases_for(TargetKind.SELF, "S1")[0])
    s.add_observation(Observation(observer_id="C", fact_ref=ref, learned_at_pos=DP(chapter=5)))
    res = StateResolver(s, N)
    c_at_15 = bool(res.state_of("S1", position=15, observer_id="C", knowledge_pos=DP(chapter=15)).aliases)
    c_at_30 = bool(res.state_of("S1", position=30, observer_id="C", knowledge_pos=DP(chapter=30)).aliases)
    return dict(
        c_believes_at_ch15=c_at_15,
        c_still_believes_at_ch30_when_never_told=c_at_30,
        verdict_if_false="C is made to know the reader's retraction (reader knowledge inherited by a character)",
        binding_id=bid,
    )


def check_reader_knowledge_off_main_timeline() -> dict:
    """I6. state_of docstring: 'Without [knowledge time] the narration spoils every reveal'."""
    s = new_store()
    alias(s, "Xname", tl="DREAM_X", iv=FuzzyInterval.open_ended(0), learned=(30, 0))
    r = StateResolver(s, N)
    default = bool(r.state_of("S1", timeline_id="DREAM_X", position=2.0).aliases)
    explicit = bool(r.state_of("S1", timeline_id="DREAM_X", position=2.0, knowledge_pos=DP(chapter=10)).aliases)
    main = new_store()
    alias(main, "Xname", learned=(30, 0))
    main_default = bool(StateResolver(main, N).state_of("S1", position=10.0).aliases)
    return dict(
        dream_fact_learned_ch30_visible_to_reader_with_default_args=default,
        dream_fact_visible_when_knowledge_pos_ch10_passed=explicit,
        main_timeline_fact_learned_ch30_visible_at_ch10_default=main_default,
    )


def check_canonicity() -> dict:
    """I7. module docstring 'Canonicity': facts inside VOIDED segments are excluded, others are not."""
    out = {}
    s = new_store()
    alias(s, "Xname")
    s.add_segments([NarrativeSegment(
        id="seg1", novel_id=N, chapter_from=5, offset_from=0, chapter_to=6, offset_to=0, timeline_id="ILLUSION_1",
        story_seq_from=0, story_seq_to=1, canonicity=Canonicity.CANONICAL)])
    s.void_span(["seg1"])
    out["voided_separate_timeline_does_not_hide_main_fact"] = bool(StateResolver(s, N).state_of("S1", position=10).aliases)
    s2 = new_store()
    alias(s2, "Xname")
    alias(s2, "Yname", iv=FuzzyInterval.point_known(5, 6), learned=(5, 0))
    s2.add_segments([NarrativeSegment(
        id="segM", novel_id=N, chapter_from=5, offset_from=0, chapter_to=6, offset_to=0, timeline_id=MAIN_TIMELINE,
        story_seq_from=5, story_seq_to=6, canonicity=Canonicity.CANONICAL)])
    s2.void_span(["segM"])
    r = StateResolver(s2, N).state_of("S1", position=10)
    out["voided_main_segment_ch5_6__fact_outside_segment_still_visible"] = "Xname" in r.aliases
    out["voided_main_segment__aliases_returned"] = len(r.aliases)
    out["pipeline_callers_of_void_span"] = 0  # grep-verified in the note; the segmenter never emits VOIDED
    return out


def check_tie_order_dependence() -> dict:
    """I8. state_of must be a function of the graph, not of row insertion order."""
    out = {}
    for case, (l1, l2) in {"same_chapter_same_offset": ((5, 0), (5, 0)), "same_chapter_diff_offset": ((5, 10), (5, 400))}.items():
        winners = []
        for order in itertools.permutations(["black", "white"]):
            s = new_store()
            for v in order:
                attr(s, "hair", v, learned=l1 if v == "black" else l2)
            r = StateResolver(s, N).state_of("P1", target_kind=TargetKind.PERSONA, position=10)
            winners.append(r.attributes.get("hair"))
        out[case] = dict(winners_by_insertion_order=winners, order_dependent=len(set(winners)) > 1)
    return out


def check_chapter_lag() -> dict:
    """E4b in miniature: a fact learned at (c, offset>0) is invisible at position c, visible at c+1."""
    s = new_store()
    alias(s, "Xname", learned=(5, 120))
    r = StateResolver(s, N)
    return dict(
        visible_at_p5=bool(r.state_of("S1", position=5.0).aliases),
        visible_at_p5_9=bool(r.state_of("S1", position=5.9).aliases),
        visible_at_p6=bool(r.state_of("S1", position=6.0).aliases),
        visible_with_explicit_end_of_chapter_knowledge=bool(
            r.state_of("S1", position=5.0, knowledge_pos=DP(chapter=5, offset=10**6)).aliases),
    )


# ---- randomised metamorphic relations --------------------------------------------------------


def rand_iv(rng: random.Random) -> FuzzyInterval:
    a = rng.choice([1, 2, 3, 5, 8])
    kind = rng.choice(["open", "closed", "since", "fuzzy"])
    if kind == "open":
        return FuzzyInterval.open_ended(a)
    if kind == "closed":
        return FuzzyInterval.point_known(a, a + rng.choice([2, 5, 9]))
    if kind == "since":
        return FuzzyInterval.since_before(a)
    return FuzzyInterval(from_lb=a, from_ub=a + 2, to_lb=a + 4, to_ub=a + 9)


def build_random(rng: random.Random, n_facts: int) -> list[tuple]:
    facts = []
    for i in range(n_facts):
        kind = rng.choice(["alias", "attribute", "relation", "persona"])
        learned = (rng.randint(1, 12), rng.choice([0, 0, rng.randint(1, 900)]))
        retr = None
        if kind != "persona" and rng.random() < 0.3:
            retr = (learned[0] + rng.randint(0, 6), rng.choice([0, rng.randint(1, 900)]))
        truth = TruthStatus.FALSE if (kind != "persona" and retr is None and rng.random() < 0.15) else TruthStatus.TRUE
        facts.append((kind, dict(learned=learned, iv=rand_iv(rng), retracted=retr, truth=truth,
                                 name=f"n{i % 4}", key=rng.choice(["hair", "attire"]), val=f"v{i}")))
    return facts


def materialise(facts: list[tuple]) -> Store:
    s = new_store()
    for kind, kw in facts:
        kw = dict(kw)
        name, key, val = kw.pop("name"), kw.pop("key"), kw.pop("val")
        if kind == "alias":
            alias(s, name, **kw)
        elif kind == "attribute":
            attr(s, key, val, **kw)
        elif kind == "relation":
            rel(s, **kw)
        else:
            kw.pop("retracted")
            binding(s, **kw)
    return s


def answer(s: Store, p: float, k: DP | None, observer: str = OBSERVER_READER) -> tuple:
    res = StateResolver(s, N)
    a = res.state_of("S1", position=p, observer_id=observer, knowledge_pos=k)
    b = res.state_of("P1", target_kind=TargetKind.PERSONA, position=p, observer_id=observer, knowledge_pos=k)
    return (tuple(sorted(a.aliases)), tuple(sorted(a.relationships)), tuple(sorted(a.persona_ids)),
            tuple(sorted(b.attributes.items())), a.certainty)


def metamorphic(n_stores: int, seed: int) -> dict:
    rng = random.Random(seed)
    i1 = i1_n = i2 = i2_n = 0
    i2_examples = []
    i2_cls = {"attribute_only": 0, "tie_on_a_key": 0}
    for _ in range(n_stores):
        facts = build_random(rng, rng.randint(4, 14))
        full = materialise(facts)
        for p, ch in itertools.product([2.0, 5.5, 9.0, 14.0], [3, 6, 10, 13]):
            k = DP(chapter=ch, offset=0)
            # I1: drop every fact learned after k; the answer at (p, k) must not change
            kept = [(kd, kw) for kd, kw in facts if DP(chapter=kw["learned"][0], offset=kw["learned"][1]) <= k]
            trunc = materialise(kept)
            i1_n += 1
            if answer(full, p, k) != answer(trunc, p, k):
                i1 += 1
        # I2: insertion-order invariance
        perm = list(facts)
        rng.shuffle(perm)
        shuffled = materialise(perm)
        for p in (2.0, 5.5, 9.0, 14.0):
            i2_n += 1
            a_full, a_shuf = answer(full, p, None), answer(shuffled, p, None)
            if a_full != a_shuf:
                i2 += 1
                only_attr = a_full[:3] == a_shuf[:3] and a_full[4] == a_shuf[4]
                admissible = StateResolver(full, N).resolve_admissible_attributes("P1", position=p, include_plausible=True)
                # recompute the full admissible candidate list to find a tie on the contested key
                res = StateResolver(full, N)
                cands = {}
                for at in full.get_attributes(TargetKind.PERSONA, "P1"):
                    if res.state_of  and at.interval.contains(p).is_possible and at.learned_at_pos <= DP(chapter=int(p)) and not (
                            (at.retracted_at is not None and DP(chapter=int(p)) >= at.retracted_at) or (
                            at.retracted_at is None and at.truth_status is TruthStatus.FALSE)):
                        cands.setdefault(at.key, []).append((at.learned_at_pos.chapter, at.learned_at_pos.offset, at.value))
                tie = any(len([c for c in v if c[:2] == max(x[:2] for x in v)]) > 1 for v in cands.values())
                i2_cls["attribute_only"] += int(only_attr)
                i2_cls["tie_on_a_key"] += int(tie)
                if len(i2_examples) < 3:
                    i2_examples.append(dict(p=p, only_attribute_differs=only_attr, tie_on_learned_at=tie))
    return dict(seed=seed, stores=n_stores, I1_prefix_truncation=dict(queries=i1_n, violations=i1),
                I2_insertion_order=dict(queries=i2_n, violations=i2, classified=i2_cls, examples=i2_examples))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--stores", type=int, default=300)
    args = ap.parse_args()
    out = dict(
        probe="E3 state_of invariants (synthetic, spec-derived expectations)", label_provenance="SYNTHETIC",
        I3_retraction_vs_interval_end=check_retraction_vs_interval_end(),
        I4_false_hidden_in_world=check_false_hidden_in_world(),
        I5_retraction_observer_global=check_retraction_is_observer_global(),
        I6_reader_knowledge_off_main=check_reader_knowledge_off_main_timeline(),
        I7_canonicity=check_canonicity(),
        I8_tie_order_dependence=check_tie_order_dependence(),
        E4b_chapter_lag_miniature=check_chapter_lag(),
        metamorphic=metamorphic(args.stores, 20261016),
    )
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
