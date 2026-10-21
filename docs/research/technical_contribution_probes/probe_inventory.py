"""CPU-only, read-only probes behind docs/research/RESEARCH_RECORD.md.

In-memory stores, no model, no network, no writes to data/. Each probe prints
one observation line keyed P1..P9; the inventory cites these keys.
Run: .venv/bin/python docs/research/technical_contribution_probes/probe_inventory.py
"""
from echotales.core.enums import OBSERVER_READER, TargetKind
from echotales.core.interval import FuzzyInterval
from echotales.core.models import (
    AliasBinding, Attribute, DiscoursePosition, Observation, Persona, Self, SelfPersonaBinding,
)
from echotales.core.enums import AliasType
from echotales.core.readset import observable_ref
from echotales.core.state import StateResolver
from echotales.core.store import Store
from echotales.core.visual_memory import (
    DisclosurePolicy, FactProvenance, VisualAssetKind, VisualAssetRecord, VisualAssetRegistry,
    VisualMemorySelector, VisualRequest,
)
from echotales.pipeline.render.plan_builder import compile_render_state
from echotales.pipeline.world.context import _facts_as_of

N = "n"
OPEN = lambda a: FuzzyInterval.open_ended(a, last_evidence=1e6)  # noqa: E731
DP = lambda c: DiscoursePosition(chapter=c)  # noqa: E731


def mk():
    s = Store(":memory:")
    s.add_novel(N, "T", "x.epub", "t")
    s.add_self(Self(id="s1", novel_id=N, canonical_label="Hero", first_attested_pos=DP(1)))
    s.add_persona(Persona(id="p1", novel_id=N, body_label="b", first_attested_pos=DP(1)))
    s.add_self_persona_binding(SelfPersonaBinding(
        self_id="s1", persona_id="p1", interval=OPEN(1), learned_at_pos=DP(1), observer_id=OBSERVER_READER))
    return s


def attr(s, key, val, learned, *, observer=OBSERVER_READER, retracted=None, iv=None, target="p1"):
    s.add_attribute(N, Attribute(
        target_kind=TargetKind.PERSONA if target.startswith("p") else TargetKind.SELF,
        target_id=target, key=key, value=val, interval=iv or OPEN(1), learned_at_pos=DP(learned),
        observer_id=observer, retracted_at=DP(retracted) if retracted else None))
    s.conn.commit()


def drawn(g):
    t = g.targets[0] if g.targets else None
    return dict(t.persona_attributes[0][1]) if t and t.persona_attributes else None


# P1: character observer -- is anyone drawn at all? (persona bindings are READER-stamped)
s = mk()
attr(s, "hair_color", "black", 1)
s.add_observation(Observation(observer_id="WU", fact_ref="attr:p1:hair_color:black", learned_at_pos=DP(2)))
s.conn.commit()
g_r = compile_render_state(s, N, ["s1"], position=5.0, observer_id=OBSERVER_READER)
g_w = compile_render_state(s, N, ["s1"], position=5.0, observer_id="WU")
print("P1 persona_ids reader=%s  WU=%s  | drawn attrs reader=%s WU=%s" % (
    g_r.persona_bindings, g_w.persona_bindings, drawn(g_r), drawn(g_w)))

# P2: attribute private to a character (observer_id=WU) -- does it reach a READER panel?
s = mk()
attr(s, "hair_color", "black", 1)
attr(s, "distinguishing_features", "secret tattoo (known only to WU)", 1, observer="WU")
g = compile_render_state(s, N, ["s1"], position=5.0, observer_id=OBSERVER_READER)
sr = StateResolver(s, N).state_of("p1", target_kind=TargetKind.PERSONA, position=5.0)
print("P2 reader panel attrs=%s | state_of(reader).attributes=%s" % (drawn(g), sr.attributes))

# P3: director-brief fact reader (world/context._facts_as_of) -- retraction / knowledge time
s = mk()
attr(s, "status", "alive", 1, retracted=50)       # believed ch1..49, retracted ch50
attr(s, "rank", "novice", 3, iv=OPEN(3))
attr(s, "scar", "left cheek", 100, iv=OPEN(3))   # happened ch3, narrated ch100
print("P3 brief facts @ch20=%s  @ch60=%s  | state_of retraction@ch20=%s" % (
    _facts_as_of(s, TargetKind.PERSONA, "p1", 20), _facts_as_of(s, TargetKind.PERSONA, "p1", 60),
    StateResolver(s, N).state_of("p1", target_kind=TargetKind.PERSONA, position=20.0).attributes))

# P4: resolve_alias for a character observer holding an explicit observation
s = mk()
b = AliasBinding(alias="Sect Master", alias_type=AliasType.TRANSFERABLE_TITLE, target_kind=TargetKind.SELF,
                 target_id="s1", interval=OPEN(1), learned_at_pos=DP(1), observer_id=OBSERVER_READER)
s.add_alias_binding(N, b)
s.add_observation(Observation(observer_id="WU", fact_ref=observable_ref(b), learned_at_pos=DP(2)))
s.conn.commit()
r = StateResolver(s, N)
print("P4 resolve_alias reader=%s  WU(with observation)=%s | state_of(aliases) WU=%s" % (
    [(t, i) for _, i, t in r.resolve_alias("Sect Master", position=5, observer_id=OBSERVER_READER)],
    r.resolve_alias("Sect Master", position=5, observer_id="WU"),
    r.state_of("s1", position=5.0, observer_id="WU").aliases))

# Visual-memory selector probes -------------------------------------------------
def asset(aid, facts=(), parents=(), persona="p1", cutoff=None):
    return VisualAssetRecord(asset_id=aid, asset_kind=VisualAssetKind.CHARACTER_PORTRAIT,
                             self_id="s1", persona_id=persona, story_interval=OPEN(1),
                             source_facts=tuple(facts), parent_asset_ids=tuple(parents),
                             effective_cutoff=cutoff or DP(0), story_pos=7.0, discourse_cutoff=DP(10),
                             observer_id="WU", policy=DisclosurePolicy.RETROSPECTIVE, prompt="p",
                             manifest_path="m.json")

def fp(ref, learned, retracted=None):
    return FactProvenance(fact_ref=ref, learned_at_pos=DP(learned), valid_interval=OPEN(1),
                          retracted_at=DP(retracted) if retracted else None)

# P5: register() rebuild drops fields when the transitive cutoff has to be raised
reg = VisualAssetRegistry()
reg.register(asset("parent", [fp("attr:p1:hair:black", 20)]))
reg.register(asset("child", [fp("attr:p1:eyes:blue", 1)], parents=["parent"]))
c = reg.get("child")
print("P5 child.effective_cutoff=%s | kept story_pos=%s discourse_cutoff=%s observer_id=%s policy=%s prompt=%r manifest_path=%r" % (
    c.effective_cutoff.chapter, c.story_pos, c.discourse_cutoff.chapter, c.observer_id, c.policy.value, c.prompt, c.manifest_path))

# P6: selector reads a registration-time provenance SNAPSHOT; a later store retraction is invisible
s = mk()
attr(s, "hair_color", "black", 1)
reg = VisualAssetRegistry()
reg.register(asset("a1", [fp("attr:p1:hair_color:black", 1)]))   # snapshot: retracted_at=None
sel = VisualMemorySelector(s, novel_id=N)
req = VisualRequest(self_id="s1", story_pos=7.0, discourse_cutoff=DP(30), observer_id=OBSERVER_READER)
before = sel.select(req, reg).status.value
s.conn.execute("UPDATE attribute SET retracted_chapter=20, retracted_offset=0 WHERE key='hair_color'")
s.conn.commit()
after = sel.select(req, reg).status.value
live = StateResolver(s, N).state_of("p1", target_kind=TargetKind.PERSONA, position=7.0,
                                    knowledge_pos=DP(30)).attributes
print("P6 selector status before=%s after store-side retraction@20=%s | live state_of(p=7,k=30).attributes=%s"
      % (before, after, live))

# P7: lineage: missing parent, cycle, diamond
reg = VisualAssetRegistry()
reg.register(asset("orphan", [fp("x", 1)], parents=["ghost"]))
reg.register(asset("A", [fp("x", 1)], parents=["B"]))
reg.register(asset("B", [fp("y", 1)], parents=["A"]))
out = {}
for aid in ("orphan", "A"):
    ev = VisualMemorySelector(mk(), novel_id=N).evaluate_candidate(
        reg.get(aid), VisualRequest(self_id="s1", story_pos=7.0, discourse_cutoff=DP(30)), reg, {"p1"})
    out[aid] = (ev.admissible, ev.rejection_reason.value)
print("P7 missing-parent / 2-cycle evaluation:", out)

# P8: p != k (retrospective): fact true at p=5 but narrated ch100; k=10 vs k=100
s = mk()
attr(s, "distinguishing_features", "scar", 100, iv=OPEN(3))
sel = VisualMemorySelector(s, novel_id=N)
reg = VisualAssetRegistry()
reg.register(asset("scarred", [fp("attr:p1:distinguishing_features:scar", 100)]))
for k in (10, 100):
    res = sel.select(VisualRequest(self_id="s1", story_pos=5.0, discourse_cutoff=DP(k),
                                   observer_id=OBSERVER_READER), reg)
    print("P8 p=5 k=%d -> %s (%s)" % (k, res.status.value, res.reason.value))

# P9: digest ignores observer/position by design -- two observers, same drawn state, same key
s = mk()
attr(s, "hair_color", "black", 1)
d1 = compile_render_state(s, N, ["s1"], position=5.0, observer_id=OBSERVER_READER).digest()
d2 = compile_render_state(s, N, ["s1"], position=6.0, observer_id=OBSERVER_READER).digest()
print("P9 digest(p=5)==digest(p=6) when nothing changed:", d1 == d2)
