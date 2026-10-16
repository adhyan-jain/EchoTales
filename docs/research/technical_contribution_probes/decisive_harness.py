"""Decisive experiment harness: B1 / B2 / B2x / B3 / T against an independent oracle.

CPU-only, deterministic, no model / network / GPU / API key. In-memory SQLite only.
Protocol (oracle semantics, systems, kill criteria) is fixed in PREREGISTRATION.md,
written before this file existed. Nothing under packages/ is modified.

    .venv/bin/python docs/research/technical_contribution_probes/decisive_harness.py

writes DECISIVE_EXPERIMENT_RESULTS.json next to this file.

Layout: world spec -> (oracle reads the spec only) / (systems read a Store built from
the spec). The oracle never touches a Store, `state_of` or `RowPolicy`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from echotales.core.enums import OBSERVER_READER, AliasType, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding, Attribute, DiscoursePosition, Observation, Persona, Relation, Self,
    SelfPersonaBinding,
)
from echotales.core.readset import fact_ref, observable_ref
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.core.visual_memory import (
    FactProvenance, VisualAssetKind, VisualAssetRecord, VisualAssetRegistry,
    VisualMemorySelector, VisualRequest,
)
from echotales.pipeline.render.plan_builder import compile_render_state
from echotales.pipeline.resolve.appearance_extract import APPEARANCE_KEYS, TRANSIENT_KEYS
from echotales.pipeline.world.context import _facts_as_of

N = "n"
R = OBSERVER_READER
CHARS = ("WU", "LI")
APP_KEYS = tuple(k for k in APPEARANCE_KEYS if k not in TRANSIENT_KEYS)
SELF_KEYS = ("status", "rank", "realm")
#: Registrar signing key for the T prototype's manifest tags. A fixed test constant, not a credential.
REGISTRAR_KEY = b"decisive-experiment-registrar-test-constant"
OUT_JSON = Path(__file__).with_name("DECISIVE_EXPERIMENT_RESULTS.json")

CLASS_SEEDS = range(0, 40)
FUZZ_SEEDS = range(1000, 1300)


# --------------------------------------------------------------------------- spec
@dataclass(frozen=True)
class F:
    """One fact in the world spec. `value` is a unique token for attrs so outputs map back to ids."""
    fid: str
    kind: str            # attr | alias | rel
    target: str          # p1 | s1 | s2   (rel: source)
    key: str
    value: str
    start: float
    end: float | None
    learned: int
    observer: str = R
    retracted: int | None = None
    witness: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class A:
    """Derived artifact: ground truth (true_*), what the registrar signed (issued_*), what is stored (stored_*)."""
    aid: str
    kind: str                       # image | text
    true_facts: tuple[str, ...]
    true_parents: tuple[str, ...]
    issued_facts: tuple[str, ...]
    issued_parents: tuple[str, ...]
    stored_facts: tuple[str, ...]
    stored_parents: tuple[str, ...]
    content: str = ""
    present: bool = True
    flaw: str | None = None         # None | missing_parent | cycle | tampered | underdeclared
    snap: tuple[tuple[str, F], ...] = ()   # registration-time snapshot of stored_facts (what B3 and A6 see)


@dataclass(frozen=True)
class W:
    facts: tuple[F, ...]
    bindings: tuple[tuple[str, int], ...] = ((R, 1), ("WU", 1), ("LI", 1))
    assets: tuple[A, ...] = ()

    def fact(self, fid: str) -> F:
        for f in self.facts:
            if f.fid == fid:
                return f
        raise KeyError(fid)


Query = tuple[float, int, str]   # (p, k, o)


@dataclass
class Case:
    cid: str
    cls: str
    seed: int
    world: W
    queries: list[Query]
    consumers: tuple[str, ...]
    #: (fid, retraction chapter) applied to the store/spec after registration (X8).
    mutation: tuple[str, int] | None = None
    scored: bool = True             # False = policy-ambiguous class, reported descriptively


class Build:
    def __init__(self) -> None:
        self.facts: list[F] = []
        self.n = 0

    def _tok(self) -> str:
        self.n += 1
        return f"v{self.n}"

    def attr(self, target, key, start, end, learned, obs=R, ret=None, wit=()) -> str:
        v = self._tok()
        fid = f"a:{target}:{key}:{v}"
        self.facts.append(F(fid, "attr", target, key, v, start, end, learned, obs, ret, tuple(wit)))
        return fid

    def alias(self, target, text, start, end, learned, obs=R, ret=None, wit=()) -> str:
        fid = f"l:{target}:{text}"
        self.facts.append(F(fid, "alias", target, "alias", text, start, end, learned, obs, ret, tuple(wit)))
        return fid

    def rel(self, src, typ, dst, start, end, learned, obs=R, ret=None, wit=()) -> str:
        fid = f"r:{src}:{typ}:{dst}"
        self.facts.append(F(fid, "rel", src, typ, dst, start, end, learned, obs, ret, tuple(wit)))
        return fid

    def value(self, fid: str) -> str:
        return next(f.value for f in self.facts if f.fid == fid)


def retract_in_spec(w: W, fid: str, r: int) -> W:
    return replace(w, facts=tuple(replace(f, retracted=r) if f.fid == fid else f for f in w.facts))


# --------------------------------------------------------------------------- oracle
def o_fact(f: F, p: float, k: int, o: str) -> bool:
    """Spec-only admissibility of one fact (PREREGISTRATION.md section 1, rules 1-4)."""
    if not (f.start <= p and (f.end is None or p < f.end)):
        return False
    wit = dict(f.witness)
    if o == R:
        if f.observer != R:
            return False
        eff = f.learned
    elif f.observer == o:
        eff = f.learned
    elif f.observer == R and o in wit:
        eff = wit[o]
    else:
        return False
    if eff > k:
        return False
    if f.retracted is not None and k >= f.retracted:
        return False
    return True


def o_persona_ok(w: W, k: int, o: str) -> bool:
    return any(b == o and learned <= k for b, learned in w.bindings)


def in_view(f: F, consumer: str) -> bool:
    if consumer == "ATTR":
        return f.kind == "attr" and f.target == "p1" and f.key in APP_KEYS
    if consumer == "BRIEF":
        return f.kind == "attr" and f.target in ("p1", "s1") and not f.key.startswith("x")
    if consumer in ("ALIAS", "RESOLVE"):
        return f.kind == "alias"
    if consumer == "REL":
        return f.kind == "rel"
    raise ValueError(consumer)


def o_admissible(w: W, consumer: str, p: float, k: int, o: str) -> set[str]:
    pok = o_persona_ok(w, k, o)
    out = set()
    for f in w.facts:
        if not in_view(f, consumer):
            continue
        if f.target == "p1" and not pok:
            continue
        if o_fact(f, p, k, o):
            out.add(f.fid)
    return out


def group_of(f: F) -> str:
    return f"g:{f.target}:{f.key}" if f.kind == "attr" else f"f:{f.fid}"


def score_set(w: W, exposed: set[str], adm: set[str]) -> tuple[list[str], list[str], int]:
    by = {f.fid: f for f in w.facts}
    exposures = sorted(exposed - adm)
    groups = {group_of(by[x]) for x in adm}
    covered = {group_of(by[x]) for x in (exposed & adm)}
    return exposures, sorted(groups - covered), len(groups)


def o_true_closure(w: W, aid: str) -> tuple[set[str], set[str]]:
    """Ground-truth transitive facts and artifact ids (follows true_parents, including deleted records)."""
    by = {a.aid: a for a in w.assets}
    facts: set[str] = set()
    seen: set[str] = set()
    stack = [aid]
    while stack:
        x = stack.pop()
        if x in seen or x not in by:
            continue
        seen.add(x)
        facts |= set(by[x].true_facts)
        stack.extend(by[x].true_parents)
    return facts, seen


def o_asset_verdict(w: W, a: A, p: float, k: int, o: str) -> str:
    facts, ids = o_true_closure(w, a.aid)
    by = {a2.aid: a2 for a2 in w.assets}
    if not o_persona_ok(w, k, o) or not all(o_fact(w.fact(x), p, k, o) for x in facts):
        return "FORBID"
    if any(by[i].flaw in ("missing_parent", "cycle", "tampered") for i in ids):
        return "UNVERIFIABLE"
    return "ADMIT"


# --------------------------------------------------------------------------- store
def _iv(f: F) -> FuzzyInterval:
    if f.end is not None:
        return FuzzyInterval.point_known(f.start, f.end)
    return FuzzyInterval.open_ended(f.start, last_evidence=1e6)


def _dp(c: int) -> DiscoursePosition:
    return DiscoursePosition(chapter=c)


def build_store(w: W) -> Store:
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "t")
    for sid in ("s1", "s2"):
        s.add_self(Self(id=sid, novel_id=N, canonical_label=sid, first_attested_pos=_dp(1)))
    s.add_persona(Persona(id="p1", novel_id=N, body_label="b", first_attested_pos=_dp(1)))
    for obs, learned in w.bindings:
        s.add_self_persona_binding(SelfPersonaBinding(
            self_id="s1", persona_id="p1", interval=FuzzyInterval.open_ended(1, last_evidence=1e6),
            learned_at_pos=_dp(learned), observer_id=obs))
    for f in sorted(w.facts, key=lambda x: x.learned):
        common = dict(interval=_iv(f), learned_at_pos=_dp(f.learned), observer_id=f.observer,
                      retracted_at=_dp(f.retracted) if f.retracted is not None else None)
        if f.kind == "attr":
            m = Attribute(target_kind=TargetKind.PERSONA if f.target == "p1" else TargetKind.SELF,
                          target_id=f.target, key=f.key, value=f.value, **common)
            s.add_attribute(N, m)
        elif f.kind == "alias":
            m = AliasBinding(alias=f.value, alias_type=AliasType.TRANSFERABLE_TITLE,
                             target_kind=TargetKind.SELF, target_id=f.target, **common)
            s.add_alias_binding(N, m)
        else:
            m = Relation(src_self=f.target, dst_self=f.value, type=f.key, **common)
            s.add_relation(N, m)
        for obs, pos in f.witness:
            s.add_observation(Observation(observer_id=obs, fact_ref=observable_ref(m), learned_at_pos=_dp(pos)))
    s.conn.commit()
    return s


def apply_retraction_to_store(store: Store, w: W, fid: str, r: int) -> None:
    f = w.fact(fid)
    assert f.kind == "attr"
    store.conn.execute("UPDATE attribute SET retracted_chapter=?, retracted_offset=0 WHERE value=?", (r, f.value))
    store.conn.commit()


def _fid_attr(t: str, k: str, v: str) -> str:
    return f"a:{t}:{k}:{v}"


def fid_of_model(m) -> str:
    if isinstance(m, Attribute):
        return _fid_attr(m.target_id, m.key, m.value)
    if isinstance(m, AliasBinding):
        return f"l:{m.target_id}:{m.alias}"
    return f"r:{m.src_self}:{m.type}:{m.dst_self}"


def _attr_ok(consumer: str, target: str, key: str) -> bool:
    if consumer == "ATTR":
        return target == "p1" and key in APP_KEYS
    if consumer == "BRIEF":
        return target in ("p1", "s1") and not key.startswith("x")
    return False


# --------------------------------------------------------------------------- B1: production path
def b1(store: Store, w: W, consumer: str, p: float, k: int, o: str) -> set[str]:
    """Production functions, called with the only coordinates production can express (no k; brief has no o)."""
    out: set[str] = set()
    if consumer == "ATTR":
        g = compile_render_state(store, N, ["s1"], position=p, observer_id=o)
        t = g.targets[0] if g.targets else None
        if t and t.persona_attributes:
            for key, val in dict(t.persona_attributes[0][1]).items():
                if _attr_ok("ATTR", "p1", key):
                    out.add(_fid_attr("p1", key, val))
    elif consumer == "BRIEF":
        for kind, tid in ((TargetKind.SELF, "s1"), (TargetKind.PERSONA, "p1")):
            for key, val in _facts_as_of(store, kind, tid, p).items():
                if _attr_ok("BRIEF", tid, key):
                    out.add(_fid_attr(tid, key, val))
    elif consumer in ("ALIAS", "REL"):
        for sid in ("s1", "s2"):
            g = compile_render_state(store, N, [sid], position=p, observer_id=o)
            for fa in g.allowed_facts:
                if consumer == "ALIAS" and fa.startswith("alias:"):
                    out.add(f"l:{sid}:{fa[6:]}")
                if consumer == "REL" and fa.startswith("rel:"):
                    _, typ, dst = fa.split(":", 2)
                    out.add(f"r:{sid}:{typ}:{dst}")
    elif consumer == "RESOLVE":
        res = StateResolver(store, N)
        for text in sorted({f.value for f in w.facts if f.kind == "alias"}):
            for _, tid, _c in res.resolve_alias(text, position=p, observer_id=o, knowledge_pos=_dp(k)):
                out.add(f"l:{tid}:{text}")
    return out


# --------------------------------------------------------------------------- B2: state_of per consumer
def _so(store: Store, tid: str, kind: TargetKind, p: float, k: int, o: str):
    return StateResolver(store, N).state_of(tid, target_kind=kind, position=p, observer_id=o, knowledge_pos=_dp(k))


def b2(store: Store, w: W, consumer: str, p: float, k: int, o: str) -> set[str]:
    out: set[str] = set()
    if consumer in ("ATTR", "BRIEF"):
        s1 = _so(store, "s1", TargetKind.SELF, p, k, o)
        if consumer == "BRIEF":
            for key, val in s1.attributes.items():
                if _attr_ok("BRIEF", "s1", key):
                    out.add(_fid_attr("s1", key, val))
        if s1.persona_ids:
            pr = _so(store, s1.persona_ids[0], TargetKind.PERSONA, p, k, o)
            for key, val in pr.attributes.items():
                if _attr_ok(consumer, "p1", key):
                    out.add(_fid_attr("p1", key, val))
    elif consumer == "ALIAS":
        for sid in ("s1", "s2"):
            for a in _so(store, sid, TargetKind.SELF, p, k, o).aliases:
                out.add(f"l:{sid}:{a}")
    elif consumer == "REL":
        for sid in ("s1", "s2"):
            for typ, dst in _so(store, sid, TargetKind.SELF, p, k, o).relationships:
                out.add(f"r:{sid}:{typ}:{dst}")
    elif consumer == "RESOLVE":
        texts = sorted({f.value for f in w.facts if f.kind == "alias"})
        for sid in ("s1", "s2"):
            have = {a.casefold() for a in _so(store, sid, TargetKind.SELF, p, k, o).aliases}
            for t in texts:
                if t.casefold() in have:
                    out.add(f"l:{sid}:{t}")
    return out


# --------------------------------------------------------------------------- T: RowPolicy (shared admission)
@dataclass(frozen=True)
class Flags:
    k: bool = True
    story: bool = True
    retract: str = "positional"      # positional | interval_end | none
    observer: bool = True
    lineage: str = "transitive"      # transitive | own
    live: bool = True


@dataclass(frozen=True)
class FV:
    """Fact view the policy evaluates: from a live store row, or from a registration-time snapshot."""
    start: float
    end: float
    learned: int
    observer: str
    retracted: int | None
    ref: str


class RowPolicy:
    """The one admission function every T consumer and artifact check shares (own code over store rows)."""

    def __init__(self, store: Store, flags: Flags = Flags()) -> None:
        self.store, self.fl = store, flags
        self._obs: dict[str, dict] = {}

    def obs(self, o: str) -> dict:
        if o not in self._obs:
            self._obs[o] = ({} if o == R else
                            {ref: pos.chapter for ref, pos in self.store.observations_for(o).items()})
        return self._obs[o]

    def admit(self, v: FV, p: float, k: int, o: str) -> bool:
        if self.fl.story and not (v.start <= p < v.end):
            return False
        eff = v.learned
        if self.fl.observer:
            if o == R:
                if v.observer != R:
                    return False
            elif v.observer == o:
                pass
            elif v.observer == R:
                seen = self.obs(o).get(v.ref)
                if seen is None:
                    return False
                eff = seen
            else:
                return False
        if self.fl.k and eff > k:
            return False
        if v.retracted is not None:
            if self.fl.retract == "interval_end":
                return False
            if self.fl.retract == "positional" and k >= v.retracted:
                return False
        return True

    def persona_ok(self, k: int, o: str) -> bool:
        for b in self.store.get_self_persona_bindings(self_id="s1"):
            if self.fl.observer and b.observer_id != o:
                continue
            if self.fl.k and b.learned_at_pos.chapter > k:
                continue
            return True
        return False

    def view_of(self, m) -> FV:
        iv = m.interval
        return FV(iv.from_lb, iv.to_ub, m.learned_at_pos.chapter, m.observer_id,
                  m.retracted_at.chapter if m.retracted_at is not None else None, observable_ref(m))

    def admit_model(self, m, p, k, o) -> bool:
        return self.admit(self.view_of(m), p, k, o)


def t_consumer(store: Store, w: W, consumer: str, p: float, k: int, o: str, flags: Flags = Flags()) -> set[str]:
    rp = RowPolicy(store, flags)
    pok = rp.persona_ok(k, o)
    out: set[str] = set()

    def take(models) -> None:
        for m in models:
            if rp.admit_model(m, p, k, o):
                out.add(fid_of_model(m))

    if consumer == "ATTR" and pok:
        take(a for a in store.get_attributes(TargetKind.PERSONA, "p1") if _attr_ok("ATTR", "p1", a.key))
    elif consumer == "BRIEF":
        take(a for a in store.get_attributes(TargetKind.SELF, "s1") if _attr_ok("BRIEF", "s1", a.key))
        if pok:
            take(a for a in store.get_attributes(TargetKind.PERSONA, "p1") if _attr_ok("BRIEF", "p1", a.key))
    elif consumer in ("ALIAS", "RESOLVE"):
        for sid in ("s1", "s2"):
            take(store.get_aliases_for(TargetKind.SELF, sid))
    elif consumer == "REL":
        for sid in ("s1", "s2"):
            take(store.get_relations(sid))
    return out


# --------------------------------------------------------------------------- derived artifacts
@dataclass(frozen=True)
class Rec:
    aid: str
    kind: str
    facts: tuple[str, ...]
    parents: tuple[str, ...]
    content: str
    tag: str


def sign(aid: str, kind: str, facts: Iterable[str], parents: Iterable[str], content: str) -> str:
    body = json.dumps([aid, kind, sorted(facts), sorted(parents), hashlib.sha256(content.encode()).hexdigest()])
    return hmac.new(REGISTRAR_KEY, body.encode(), hashlib.sha256).hexdigest()


def registry_of(w: W) -> dict[str, Rec]:
    """What is stored: stored_* lineage, with the tag the registrar issued over issued_* lineage."""
    return {a.aid: Rec(a.aid, a.kind, a.stored_facts, a.stored_parents, a.content,
                       sign(a.aid, a.kind, a.issued_facts, a.issued_parents, a.content))
            for a in w.assets if a.present}


def _parse_attr(fid: str) -> tuple[str, str, str]:
    _, t, key, val = fid.split(":", 3)
    return t, key, val


def _state_has(store, fid, p, k, o) -> bool:
    t, key, val = _parse_attr(fid)
    kind = TargetKind.PERSONA if t == "p1" else TargetKind.SELF
    return _so(store, t, kind, p, k, o).attributes.get(key) == val


def _persona_gate_state(store, p, k, o) -> bool:
    return "p1" in _so(store, "s1", TargetKind.SELF, p, k, o).persona_ids


def art_b2(store, reg, w, p, k, o) -> set[str]:
    """Own declared facts re-checked live through state_of; embodiment gate; no parent traversal."""
    if not _persona_gate_state(store, p, k, o):
        return set()
    return {aid for aid, r in reg.items() if all(_state_has(store, f, p, k, o) for f in r.facts)}


def art_b2x(store, reg, w, p, k, o) -> set[str]:
    """B2 + naive transitive walk over declared parents (missing parent rejected at any depth)."""
    if not _persona_gate_state(store, p, k, o):
        return set()
    memo: dict[str, bool] = {}

    def fact_ok(f: str) -> bool:
        if f not in memo:
            memo[f] = _state_has(store, f, p, k, o)
        return memo[f]

    out = set()
    for aid in reg:
        seen: set[str] = set()
        stack = [aid]
        good = True
        while stack and good:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            if x not in reg:
                good = False
                break
            good = all(fact_ok(f) for f in reg[x].facts)
            stack.extend(reg[x].parents)
        if good:
            out.add(aid)
    return out


def art_b2xs(store, reg, w, p, k, o) -> set[str]:
    """POST-HOC DIAGNOSTIC (not pre-registered): B2x plus a content scan, without tags or cycle checks.

    Added after the first results showed T's edge over B2x on under-declared text, to test whether that
    edge needs T's machinery or only a scan any engineer could add. Same scan rule as T's, but admission
    asked of state_of instead of RowPolicy.
    """
    base = art_b2x(store, reg, w, p, k, o)
    rows = _attr_rows(store)
    out = set()
    for aid in base:
        seen: set[str] = set()
        stack = [aid]
        words: set[str] = set()
        declared: set[str] = set()
        while stack:
            x = stack.pop()
            if x in seen or x not in reg:
                continue
            seen.add(x)
            declared |= set(reg[x].facts)
            if reg[x].kind == "text":
                words |= set(reg[x].content.split())
            stack.extend(reg[x].parents)
        if all(fid in declared or m.value not in words or _state_has(store, fid, p, k, o)
               for fid, m in rows.items()):
            out.add(aid)
    return out


def art_b3(store, w: W, p, k, o) -> set[str]:
    """The existing, unwired VisualMemorySelector over a registration-time snapshot registry."""
    reg = VisualAssetRegistry()
    scope = frozenset({R, "SYSTEM", *CHARS})
    for a in w.assets:
        if not a.present:
            continue
        provs = tuple(FactProvenance(
            fact_ref=fact_ref("attr", f.target, f.key, f.value), learned_at_pos=_dp(f.learned),
            valid_interval=_iv(f), retracted_at=_dp(f.retracted) if f.retracted is not None else None,
            observer_id=f.observer) for _, f in a.snap)
        reg.register(VisualAssetRecord(
            asset_id=a.aid, asset_kind=VisualAssetKind.CHARACTER_PORTRAIT, self_id="s1", persona_id="p1",
            story_interval=FuzzyInterval.open_ended(1, last_evidence=1e6), source_facts=provs,
            parent_asset_ids=a.stored_parents, observer_scope=scope))
    sel = VisualMemorySelector(store, novel_id=N)
    res = sel.select(VisualRequest(self_id="s1", story_pos=p, discourse_cutoff=_dp(k), observer_id=o), reg)
    return {ev.asset_id for ev in res.candidate_evaluations if ev.admissible}


def _attr_rows(store) -> dict[str, Attribute]:
    rows = list(store.get_attributes(TargetKind.PERSONA, "p1")) + list(store.get_attributes(TargetKind.SELF, "s1"))
    return {fid_of_model(m): m for m in rows}


def art_t(store, reg, w, p, k, o, flags: Flags = Flags(), scan: bool = True) -> set[str]:
    """Shared policy, live revalidation, explicit-stack transitive closure, fail closed.

    Rejects on: missing parent, cycle, registrar-tag mismatch on any visited artifact, a declared fact
    that is absent from the store or inadmissible, and (text content only) an *inferred* dependency --
    a store fact whose token appears in the content but not in the declared closure -- that is
    inadmissible. An inferred dependency that is admissible does not reject (no over-suppression).
    """
    rp = RowPolicy(store, flags)
    if not rp.persona_ok(k, o):
        return set()
    rows = _attr_rows(store)
    by_id = {a.aid: a for a in w.assets}
    return {aid for aid in reg if _t_one(aid, reg, rows, rp, p, k, o, flags, scan, by_id)}


def _t_one(aid, reg, rows, rp, p, k, o, flags, scan, by_id) -> bool:
    def fact_ok(fid: str, owner: str) -> bool:
        if flags.live:
            m = rows.get(fid)
            return m is not None and rp.admit_model(m, p, k, o)
        f = dict(by_id[owner].snap).get(fid)
        if f is None:
            return False
        iv = _iv(f)
        return rp.admit(FV(iv.from_lb, iv.to_ub, f.learned, f.observer, f.retracted,
                           fact_ref("attr", f.target, f.key, f.value)), p, k, o)

    order: list[str] = []
    state: dict[str, int] = {}                  # 1 = on current path, 2 = done
    stack: list[tuple[str, bool]] = [(aid, False)]
    while stack:
        x, leaving = stack.pop()
        if leaving:
            state[x] = 2
            continue
        if x not in reg:
            return False                        # missing parent
        if state.get(x) == 2:
            continue
        if state.get(x) == 1:
            return False                        # cycle
        r = reg[x]
        if not hmac.compare_digest(r.tag, sign(r.aid, r.kind, r.facts, r.parents, r.content)):
            return False                        # manifest differs from what the registrar signed
        state[x] = 1
        order.append(x)
        stack.append((x, True))
        if flags.lineage == "own":
            continue
        for ppid in r.parents:
            if state.get(ppid) == 1:
                return False
            stack.append((ppid, False))
    declared: set[str] = set()
    for x in order:
        declared |= set(reg[x].facts)
        if not all(fact_ok(f, x) for f in reg[x].facts):
            return False
    if scan:
        words: set[str] = set()
        for x in order:
            if reg[x].kind == "text":
                words |= set(reg[x].content.split())
        for fid, m in rows.items():
            if m.value in words and fid not in declared and not rp.admit_model(m, p, k, o):
                return False                    # inferred inadmissible dependency
    return True


# --------------------------------------------------------------------------- class generators
def rng_of(cls: str, seed: int) -> random.Random:
    return random.Random(f"{cls}:{seed}")


def _base(b: Build) -> None:
    b.attr("p1", "hair_color", 1, None, 1)
    b.attr("s1", "status", 1, None, 1)


def gen_x1(seed):
    r = rng_of("X1", seed); b = Build(); _base(b)
    t, L = r.randint(2, 8), r.randint(30, 100)
    p = r.randint(t, t + 5)
    b.attr("p1", "distinguishing_features", t, None, L)
    b.attr("s1", "rank", t, None, L)
    return b, [(p, p, R), (p, L - 1, R), (p, L, R), (p, L + 5, R)], ("ATTR", "BRIEF")


def gen_x2(seed):
    r = rng_of("X2", seed); b = Build(); _base(b)
    f0, learned = r.randint(20, 50), r.randint(2, 10)
    p = r.randint(learned, f0 - 1)
    b.attr("p1", "skin_tone", f0, None, learned)
    b.attr("s1", "realm", f0, None, learned)
    return b, [(p, p, R), (p, f0 + 2, R), (f0 + 1, f0 + 1, R)], ("ATTR", "BRIEF")


def gen_x3(seed):
    r = rng_of("X3", seed); b = Build(); _base(b)
    rr = r.randint(30, 60)
    b.attr("p1", "eye_color", 1, None, 1, ret=rr)
    b.attr("p1", "eye_color", rr, None, rr)
    b.attr("s1", "rank", 1, None, 1, ret=rr)
    b.attr("s1", "rank", rr, None, rr)
    return b, [(rr - 10, rr - 10, R), (rr - 10, rr + 5, R), (rr + 5, rr + 5, R), (rr - 1, rr - 1, R)], ("ATTR", "BRIEF")


def gen_x4(seed):
    r = rng_of("X4", seed); b = Build(); _base(b)
    L, wp = r.randint(10, 40), r.randint(5, 40)
    b.attr("p1", "hair_style", 1, None, L, wit=(("WU", wp),))                  # reader fact, WU saw it at wp
    b.attr("p1", "typical_attire", 1, None, 2)                                   # reader fact, nobody witnessed
    b.attr("p1", "height_build", 1, None, 3, obs="WU")                           # WU-private
    b.attr("p1", "distinguishing_features", 1, None, 3, obs="LI")                # LI-private
    b.attr("s1", "rank", 1, None, 4, wit=(("LI", wp + 3),))
    ks = sorted({max(1, wp - 1), wp, L - 1, L, L + 5, 60})
    return b, [(5, kk, o) for kk in ks for o in (R, "WU", "LI")], ("ATTR", "BRIEF")


def gen_xp(seed):
    b = Build(); _base(b)
    b.attr("p1", "hair_style", 1, None, 2, wit=(("WU", 4),))
    b.attr("s1", "rank", 1, None, 2, wit=(("WU", 4),))
    return b, [(10, 10, "WU"), (10, 30, "WU"), (10, 10, R)], ("ATTR", "BRIEF")


def gen_x5(seed):
    r = rng_of("X5", seed); b = Build()
    sw, wp = r.randint(30, 50), r.randint(5, 30)
    b.alias("s1", "Sect Master", 1, sw, 1)
    b.alias("s2", "Sect Master", sw, None, sw)
    b.alias("s1", "Black Fox", 1, None, 5, obs="WU")
    b.alias("s2", "Old Ghost", 1, None, wp + 5, wit=(("WU", wp),))
    b.rel("s1", "mentor", "s2", 1, None, 3, wit=(("WU", wp),))
    b.rel("s2", "rival", "s1", sw, None, 60)
    ks = sorted({max(1, wp - 1), wp, wp + 6, sw, 70})
    return b, [(pp, kk, o) for pp in (sw - 5, sw + 5) for kk in ks for o in (R, "WU", "LI")], ("ALIAS", "REL", "RESOLVE")


def gen_xb(seed):
    r = rng_of("XB", seed); b = Build(); _base(b)
    b.attr("p1", "eye_color", 1, None, 2)
    b.attr("s1", "rank", 1, None, 3)
    b.alias("s1", "Sect Master", 1, None, 2)
    b.rel("s1", "mentor", "s2", 1, None, 2)
    p = r.randint(10, 30)
    return b, [(p, p, R), (p, p + 5, R), (p + 7, p + 7, R)], ("ATTR", "BRIEF", "ALIAS", "REL", "RESOLVE")


def gen_fz(seed):
    r = rng_of("FZ", seed); b = Build()
    obs_pool = [R] * 7 + list(CHARS)

    def common():
        st = r.randint(1, 40)
        en = None if r.random() < 0.6 else st + r.randint(3, 30)
        ln = r.randint(1, 60)
        ob = r.choice(obs_pool)
        ret = r.randint(ln, ln + 40) if r.random() < 0.2 else None
        wit = ((r.choice(CHARS), r.randint(1, 60)),) if (ob == R and r.random() < 0.3) else ()
        return dict(start=st, end=en, learned=ln, obs=ob, ret=ret, wit=wit)

    for _ in range(r.randint(6, 12)):
        b.attr("p1", r.choice(APP_KEYS[:3]), **common())
    for _ in range(r.randint(3, 5)):
        b.attr("s1", r.choice(SELF_KEYS), **common())
    pool, used = ["Sect Master", "Black Fox", "Old Ghost"], set()
    for _ in range(r.randint(3, 5)):
        t, tx = r.choice(("s1", "s2")), r.choice(pool)
        if (t, tx) not in used:
            used.add((t, tx))
            b.alias(t, tx, **common())
    for typ, (a, c) in (("mentor", ("s1", "s2")), ("rival", ("s2", "s1"))):
        if r.random() < 0.7:
            b.rel(a, typ, c, **common())
    qs = []
    for _ in range(10):
        p = float(r.randint(1, 60)) + (0.5 if r.random() < 0.2 else 0)
        k = int(p) if r.random() < 0.4 else r.randint(1, 80)
        qs.append((p, k, r.choice((R, *CHARS))))
    return b, qs, ("ATTR", "BRIEF", "ALIAS", "REL", "RESOLVE")


def _mk_assets(b: Build, specs: list[dict]) -> tuple[A, ...]:
    by_fact = {f.fid: f for f in b.facts}
    out = []
    for s in specs:
        parents = s.get("parents", ())
        issued_f = s.get("issued_facts", s["declared"])
        stored_f = s.get("stored_facts", issued_f)
        issued_p = s.get("issued_parents", parents)
        stored_p = s.get("stored_parents", issued_p)
        content = s.get("content")
        if content is None:
            content = (" ".join(sorted({by_fact[x].value for x in s["true"]}))
                       if s["kind"] == "text" else f"IMG#{s['aid']}")
        out.append(A(
            aid=s["aid"], kind=s["kind"], true_facts=tuple(s["true"]), true_parents=tuple(s.get("true_parents", ())),
            issued_facts=tuple(issued_f), issued_parents=tuple(issued_p),
            stored_facts=tuple(stored_f), stored_parents=tuple(stored_p),
            content=content, present=s.get("present", True), flaw=s.get("flaw"),
            snap=tuple((x, by_fact[x]) for x in stored_f)))
    return tuple(out)


ART_CLASSES = ("X7-chain-clean", "X7-late-in-parent", "X7-diamond", "X7-depth3", "X9-derived-text",
               "XT-missing-parent", "XT-missing-parent-late", "XT-cycle", "XT-tamper-drop-parent",
               "XT-tamper-drop-fact", "XT-tamper-in-parent", "XT-underdeclared-text",
               "XT-underdeclared-image", "X8-stale-retraction", "X7-observer-witness", "X2-forward-asset")


def gen_art(case: str, seed: int) -> Case:
    r = rng_of(case, seed); b = Build(); _base(b)
    late_at = r.randint(30, 80)
    e1 = b.attr("p1", "x1", 1, None, r.randint(1, 4))
    e2 = b.attr("p1", "x2", 1, None, r.randint(1, 4))
    late = b.attr("p1", "x3", 1, None, late_at)
    p = r.randint(5, 20)
    qs: list[Query] = [(p, kk, R) for kk in (p, late_at - 1, late_at, late_at + 10)]
    mut = None
    img = lambda aid, true, **kw: dict(aid=aid, kind="image", true=true, declared=true, **kw)  # noqa: E731
    if case == "X7-chain-clean":
        S = [img("a1", [e1]), img("a2", [e2], parents=["a1"], true_parents=["a1"])]
    elif case == "X7-late-in-parent":
        S = [img("a1", [e1, late]), img("a2", [e2], parents=["a1"], true_parents=["a1"])]
    elif case == "X7-diamond":
        S = [img("root", [late]),
             img("m1", [e1], parents=["root"], true_parents=["root"]),
             img("m2", [e2], parents=["root"], true_parents=["root"]),
             img("leaf", [e1], parents=["m1", "m2"], true_parents=["m1", "m2"])]
    elif case == "X7-depth3":
        S = [img("d0", [late]), img("d1", [e1], parents=["d0"], true_parents=["d0"]),
             img("d2", [e1], parents=["d1"], true_parents=["d1"]), img("d3", [e2], parents=["d2"], true_parents=["d2"])]
    elif case == "X9-derived-text":
        S = [img("img", [late]),
             dict(aid="txt", kind="text", true=[e1], declared=[e1], parents=["img"], true_parents=["img"],
                  content=f"{b.value(e1)} {b.value(late)}")]
    elif case == "XT-missing-parent":
        S = [img("g", [e1], present=False, flaw="missing_parent"),
             img("mid", [e2], parents=["g"], true_parents=["g"]),
             img("leaf", [e1], parents=["mid"], true_parents=["mid"])]
    elif case == "XT-missing-parent-late":
        S = [img("g", [late], present=False, flaw="missing_parent"),
             img("mid", [e2], parents=["g"], true_parents=["g"]),
             img("leaf", [e1], parents=["mid"], true_parents=["mid"])]
    elif case == "XT-cycle":
        S = [img("ca", [e1], parents=["cb"], flaw="cycle"),
             img("cb", [e2], parents=["ca"], true_parents=["ca"], flaw="cycle")]
    elif case == "XT-tamper-drop-parent":
        S = [img("root", [late]),
             img("kid", [e1], issued_parents=["root"], stored_parents=[], true_parents=["root"], flaw="tampered")]
    elif case == "XT-tamper-drop-fact":
        S = [dict(aid="kid", kind="image", true=[e1, late], declared=[e1, late],
                  issued_facts=[e1, late], stored_facts=[e1], flaw="tampered")]
    elif case == "XT-tamper-in-parent":
        S = [dict(aid="root", kind="image", true=[late], declared=[late],
                  issued_facts=[late], stored_facts=[e1], flaw="tampered"),
             img("kid", [e2], parents=["root"], true_parents=["root"])]
    elif case in ("XT-underdeclared-text", "XT-underdeclared-image"):
        kind = "text" if case.endswith("text") else "image"
        S = [dict(aid="u", kind=kind, true=[e1, late], declared=[e1], flaw="underdeclared",
                  content=f"{b.value(e1)} {b.value(late)}" if kind == "text" else "IMG#u")]
    elif case == "X8-stale-retraction":
        rr = r.randint(25, 60)
        S = [img("s", [e1, e2])]
        mut = (e1, rr)
        qs = [(p, rr - 3, R), (p, rr, R), (p, rr + 5, R)]
    elif case == "X7-observer-witness":
        wp = r.randint(5, 25)
        wa = b.attr("p1", "x4", 1, None, 2, wit=(("WU", wp),))
        S = [img("w", [wa])]
        qs = [(p, kk, o) for kk in (wp - 1, wp, 60) for o in (R, "WU", "LI")]
    elif case == "X2-forward-asset":
        f0 = r.randint(30, 50)
        fa = b.attr("p1", "x5", f0, None, 2)
        S = [img("f", [fa])]
        qs = [(p, p, R), (p, f0 + 3, R), (f0 + 1, f0 + 1, R)]
    else:
        raise ValueError(case)
    return Case(f"{case}-s{seed}", case, seed, W(tuple(b.facts), assets=_mk_assets(b, S)), qs, ("ART",), mutation=mut)


def gen_cache(seed):
    """X8-cache: key before/after a retraction. Oracle = did the ATTR admissible set change?"""
    r = rng_of("X8c", seed); b = Build(); _base(b)
    fx = b.attr("p1", "hair_style", 1, None, 2)
    b.attr("p1", "eye_color", 1, None, 3)
    late = b.attr("p1", "skin_tone", 1, None, 60)            # learned after k: never admissible at k
    p = r.randint(10, 20)
    rr = r.choice([p - 3, p + 5, 70])    # <=k changes the admissible set; >k does not (positional)
    return b, [(p, p, R)], ("CACHE",), (r.choice([fx, late]), rr)


CONS_CLASSES = {"X1": gen_x1, "X2": gen_x2, "X3": gen_x3, "X4": gen_x4, "X5": gen_x5, "XB": gen_xb, "XP": gen_xp}


def build_cases() -> list[Case]:
    cases: list[Case] = []
    for cls, g in CONS_CLASSES.items():
        for s in CLASS_SEEDS:
            b, qs, cons = g(s)
            cases.append(Case(f"{cls}-s{s}", cls, s, W(tuple(b.facts)), qs, cons, scored=(cls != "XP")))
    for cls in ART_CLASSES:
        cases.extend(gen_art(cls, s) for s in CLASS_SEEDS)
    for s in CLASS_SEEDS:
        b, qs, cons, mut = gen_cache(s)
        cases.append(Case(f"X8c-s{s}", "X8-cache", s, W(tuple(b.facts)), qs, cons, mutation=mut))
    for s in FUZZ_SEEDS:
        b, qs, cons = gen_fz(s)
        cases.append(Case(f"FZ-s{s}", "FZ", s, W(tuple(b.facts)), qs, cons))
    return cases


# --------------------------------------------------------------------------- runner
SYS_CONS = {"B1": b1, "B2": b2, "T": t_consumer}
ART_SYSTEMS = ("B2", "B2x", "B2xs", "B3", "T")
SOURCE_TAG = {
    "B1": "production_path (RESOLVE consumer = unwired StateResolver.resolve_alias)",
    "B2": "synthetic_adapter over production state_of",
    "B2x": "synthetic_adapter (naive transitive check)",
    "B2xs": "synthetic_adapter (B2x + content scan; POST-HOC diagnostic, not pre-registered)",
    "B3": "unwired_component (VisualMemorySelector) on synthetic lineage",
    "T": "synthetic_prototype",
}


def _cache_keys(store, w, p, k, o):
    dg = compile_render_state(store, N, ["s1"], position=p, observer_id=o).digest()
    s1 = _so(store, "s1", TargetKind.SELF, p, k, o)
    attrs = sorted(_so(store, s1.persona_ids[0], TargetKind.PERSONA, p, k, o).attributes.items()) if s1.persona_ids else []
    return {"B1": dg,
            "B2": hashlib.sha256(json.dumps(attrs).encode()).hexdigest(),
            "T": hashlib.sha256(json.dumps(sorted(t_consumer(store, w, "ATTR", p, k, o))).encode()).hexdigest()}


def _art_systems(store, reg, w, w_eval, p, k, o, timers) -> dict:
    verdicts = {a.aid: o_asset_verdict(w_eval, a, p, k, o) for a in w.assets if a.present}
    out = {}
    for name in ART_SYSTEMS:
        t0 = time.perf_counter()
        try:
            acc = {"B2": lambda: art_b2(store, reg, w_eval, p, k, o),
                   "B2x": lambda: art_b2x(store, reg, w_eval, p, k, o),
                   "B2xs": lambda: art_b2xs(store, reg, w_eval, p, k, o),
                   "B3": lambda: art_b3(store, w, p, k, o),
                   "T": lambda: art_t(store, reg, w_eval, p, k, o)}[name]()
            err = None
        except Exception as e:  # noqa: BLE001 -- recorded in the output, never swallowed
            acc, err = set(), f"{type(e).__name__}: {e}"
        timers[name] += time.perf_counter() - t0
        out[name] = {"ART": {
            "exposures": sorted(a for a in acc if verdicts.get(a) == "FORBID"),
            "unverified": sorted(a for a in acc if verdicts.get(a) == "UNVERIFIABLE"),
            "omissions": sorted(a for a, v in verdicts.items() if v == "ADMIT" and a not in acc),
            "n_admissible": sum(v == "ADMIT" for v in verdicts.values()), "error": err}}
    return out, verdicts


def run_case(c: Case, timers: dict[str, float]) -> dict:
    row: dict = {"cid": c.cid, "class": c.cls, "seed": c.seed, "scored": c.scored, "queries": []}
    w = c.world
    store = build_store(w)
    w_eval = w
    if c.mutation and "CACHE" not in c.consumers:
        apply_retraction_to_store(store, w, *c.mutation)
        w_eval = retract_in_spec(w, *c.mutation)
    for (p, k, o) in c.queries:
        q: dict = {"p": p, "k": k, "o": o, "reachable": (k == int(p)), "systems": {}}
        if "ART" in c.consumers:
            q["systems"], q["verdicts"] = _art_systems(store, registry_of(w), w, w_eval, p, k, o, timers)
        elif "CACHE" in c.consumers:
            before = _cache_keys(store, w, p, k, o)
            w2 = retract_in_spec(w, *c.mutation)
            apply_retraction_to_store(store, w, *c.mutation)
            after = _cache_keys(store, w2, p, k, o)
            changed = o_admissible(w, "ATTR", p, k, o) != o_admissible(w2, "ATTR", p, k, o)
            for name in ("B1", "B2", "T"):
                kc = before[name] != after[name]
                q["systems"][name] = {"CACHE": {
                    "oracle_changed": changed, "key_changed": kc, "stale_serve": changed and not kc,
                    "over_invalidation": kc and not changed, "exposures": [], "omissions": [], "error": None}}
        else:
            for cons in c.consumers:
                adm = o_admissible(w, cons, p, k, o)
                for name, fn in SYS_CONS.items():
                    t0 = time.perf_counter()
                    try:
                        exp, err = fn(store, w, cons, p, k, o), None
                    except Exception as e:  # noqa: BLE001
                        exp, err = set(), f"{type(e).__name__}: {e}"
                    timers[name] += time.perf_counter() - t0
                    ex, om, n = score_set(w, exp, adm)
                    q["systems"].setdefault(name, {})[cons] = {"exposures": ex, "omissions": om,
                                                               "n_admissible": n, "error": err}
        row["queries"].append(q)
    return row


def run_all(cases: list[Case] | None = None) -> dict:
    cases = cases if cases is not None else build_cases()
    timers: dict[str, float] = defaultdict(float)
    rows = [run_case(c, timers) for c in cases]
    return {"timers_s": {k: round(v, 3) for k, v in timers.items()}, "cases": rows}


# --------------------------------------------------------------------------- ablations (T only)
ABLATIONS = {
    "A1-no-knowledge-time": Flags(k=False),
    "A2-no-story-interval": Flags(story=False),
    "A3-retraction-as-interval-end": Flags(retract="interval_end"),
    "A4-no-observer-door": Flags(observer=False),
    "A5-own-facts-only-lineage": Flags(lineage="own"),
    "A6-snapshot-not-live": Flags(live=False),
}


def run_ablations(cases: list[Case] | None = None) -> dict:
    cases = cases if cases is not None else build_cases()
    variants = {"T": Flags(), **ABLATIONS}
    res: dict = {n: defaultdict(lambda: defaultdict(int)) for n in variants}
    for c in cases:
        if c.cls in ("FZ", "X8-cache", "XP"):
            continue
        w = c.world
        store = build_store(w)
        w_eval = w
        if c.mutation:
            apply_retraction_to_store(store, w, *c.mutation)
            w_eval = retract_in_spec(w, *c.mutation)
        reg = registry_of(w)
        for (p, k, o) in c.queries:
            if "ART" in c.consumers:
                verd = {a.aid: o_asset_verdict(w_eval, a, p, k, o) for a in w.assets if a.present}
                for name, fl in variants.items():
                    acc = art_t(store, reg, w_eval, p, k, o, flags=fl)
                    d = res[name][c.cls]
                    d["exposures"] += sum(verd.get(a) == "FORBID" for a in acc)
                    d["unverified"] += sum(verd.get(a) == "UNVERIFIABLE" for a in acc)
                    d["omissions"] += sum(v == "ADMIT" and a not in acc for a, v in verd.items())
                continue
            for cons in c.consumers:
                adm = o_admissible(w, cons, p, k, o)
                for name, fl in variants.items():
                    ex, om, _ = score_set(w, t_consumer(store, w, cons, p, k, o, fl), adm)
                    d = res[name][c.cls]
                    d["exposures"] += len(ex)
                    d["omissions"] += len(om)
    return {n: {cls: dict(v) for cls, v in d.items()} for n, d in res.items()}


# --------------------------------------------------------------------------- differential
def differential(seeds: Iterable[int]) -> dict:
    """oracle vs RowPolicy (exact set equality) and oracle vs state_of (per-group) on fuzz worlds."""
    bad_t: list[dict] = []
    bad_b2: list[dict] = []
    n = 0
    for s in seeds:
        b, qs, cons = gen_fz(s)
        w = W(tuple(b.facts))
        store = build_store(w)
        for (p, k, o) in qs:
            for c in cons:
                n += 1
                adm = o_admissible(w, c, p, k, o)
                te = t_consumer(store, w, c, p, k, o)
                if te != adm:
                    bad_t.append({"seed": s, "q": [p, k, o], "consumer": c,
                                  "t_minus_o": sorted(te - adm), "o_minus_t": sorted(adm - te)})
                ex, om, _ = score_set(w, b2(store, w, c, p, k, o), adm)
                if ex or om:
                    bad_b2.append({"seed": s, "q": [p, k, o], "consumer": c, "exposures": ex, "omissions": om})
    return {"n_comparisons": n, "oracle_vs_rowpolicy_mismatches": bad_t, "oracle_vs_state_of_mismatches": bad_b2}


# --------------------------------------------------------------------------- summary
def summarize(res: dict) -> dict:
    """'class|subset|system' -> counts. subset: all | reachable (k==int(p)) | p_ne_k."""
    out: dict = {}
    subsets = (("all", lambda q: True), ("reachable", lambda q: q["reachable"]), ("p_ne_k", lambda q: not q["reachable"]))
    for row in res["cases"]:
        for q in row["queries"]:
            for tag, sel in subsets:
                if not sel(q):
                    continue
                for sysname, cons in q["systems"].items():
                    for cname, r in cons.items():
                        d = out.setdefault((row["class"], tag, sysname), defaultdict(int))
                        d["consumer_calls"] += 1
                        d["exposures"] += len(r["exposures"])
                        d["omissions"] += len(r.get("omissions", []))
                        d["admissible_groups"] += r.get("n_admissible", 0)
                        d["unverified"] += len(r.get("unverified", []))
                        d["errors"] += 1 if r["error"] else 0
                        d["stale_serve"] += 1 if r.get("stale_serve") else 0
                        d["over_invalidation"] += 1 if r.get("over_invalidation") else 0
                        d["failed_calls"] += 1 if (r["exposures"] or r.get("omissions") or r.get("unverified")
                                                   or r.get("stale_serve") or r.get("over_invalidation")) else 0
    return {f"{k[0]}|{k[1]}|{k[2]}": dict(v) for k, v in sorted(out.items())}


def main() -> int:
    t0 = time.perf_counter()
    cases = build_cases()
    res = run_all(cases)
    ab = run_ablations(cases)
    diff = differential(FUZZ_SEEDS)
    payload = {
        "protocol": "docs/research/technical_contribution_probes/PREREGISTRATION.md",
        "seeds": {"classes": [CLASS_SEEDS.start, CLASS_SEEDS.stop - 1], "fuzz": [FUZZ_SEEDS.start, FUZZ_SEEDS.stop - 1]},
        "source_tags": SOURCE_TAG,
        "n_cases": len(res["cases"]),
        "summary": summarize(res),
        "ablations": ab,
        "differential": {"n": diff["n_comparisons"],
                         "n_oracle_vs_rowpolicy": len(diff["oracle_vs_rowpolicy_mismatches"]),
                         "n_oracle_vs_state_of": len(diff["oracle_vs_state_of_mismatches"]),
                         "examples_state_of": diff["oracle_vs_state_of_mismatches"][:10],
                         "examples_rowpolicy": diff["oracle_vs_rowpolicy_mismatches"][:10]},
        "timers_s": res["timers_s"],
        "wall_s": round(time.perf_counter() - t0, 2),
        "cases": res["cases"],
    }
    OUT_JSON.write_text(json.dumps(payload, default=str), encoding="utf-8")
    print(f"wrote {OUT_JSON.name} ({OUT_JSON.stat().st_size / 1e6:.1f} MB), {payload['n_cases']} cases, {payload['wall_s']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
