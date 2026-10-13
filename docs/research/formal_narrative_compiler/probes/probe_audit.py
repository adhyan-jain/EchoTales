"""Read-only audit probes against the real compile path (in-memory store, no production edits)."""
from echotales.core.enums import *
from echotales.core.interval import FuzzyInterval
from echotales.core.models import *
from echotales.core.state import StateResolver, compile_generation_state
from echotales.core.store import Store
from echotales.pipeline.persona.reference_gen import appearance_of
from echotales.pipeline.render.plan_builder import compile_render_state

N = "n"
def mk():
    s = Store(":memory:"); s.add_novel(N, "T", "x.epub", "t")
    s.add_self(Self(id="s1", novel_id=N, canonical_label="Hero", first_attested_pos=DiscoursePosition(chapter=1)))
    s.add_persona(Persona(id="p1", novel_id=N, body_label="b", first_attested_pos=DiscoursePosition(chapter=1)))
    s.add_self_persona_binding(SelfPersonaBinding(self_id="s1", persona_id="p1",
        interval=FuzzyInterval.open_ended(1, last_evidence=1e6), learned_at_pos=DiscoursePosition(chapter=1), observer_id=OBSERVER_READER))
    return s

def attr(s, key, val, iv, learned, retracted=None, target="p1"):
    s.add_attribute(N, Attribute(target_kind=TargetKind.PERSONA if target.startswith("p") else TargetKind.SELF,
        target_id=target, key=key, value=val, interval=iv,
        learned_at_pos=DiscoursePosition(chapter=learned), observer_id=OBSERVER_READER,
        retracted_at=DiscoursePosition(chapter=retracted) if retracted else None))
    s.conn.commit()

def drawn(s, pos):
    g = compile_render_state(s, N, ["s1"], position=pos)
    return dict(g.targets[0].persona_attributes[0][1]) if g.targets[0].persona_attributes else {}, g

# ---- Probe A: retrospective reveal (scar acquired ch3, narrated first at ch100) -> panel at ch5
s = mk()
attr(s, "hair_color", "black", FuzzyInterval.open_ended(1, last_evidence=1e6), 1)
before, g0 = drawn(s, 5.0)
attr(s, "distinguishing_features", "scar across left cheek", FuzzyInterval.open_ended(3, last_evidence=1e6), 100)
after, g1 = drawn(s, 5.0)
print("A  ch5 reader panel attrs BEFORE ch100 fact exists:", before)
print("A  ch5 reader panel attrs AFTER  ch100 fact added :", after)
print("A  digest changed (spec depends on a post-cutoff fact):", g0.digest() != g1.digest())
# the same fact through state_of on the SELF-side path IS cutoff-correct:
attr(s, "role", "secret heir", FuzzyInterval.open_ended(3, last_evidence=1e6), 100, target="s1")
r = StateResolver(s, N).state_of("s1", position=5.0)
print("A' state_of(self attrs) at ch5 includes ch100-learned fact:", "role" in r.attributes)

# ---- Probe B: retraction vs historical belief (wig: 'white hair' believed ch1..49, retracted ch50)
s = mk()
attr(s, "hair_color", "white", FuzzyInterval.open_ended(1, last_evidence=1e6), 1, retracted=50)
r = StateResolver(s, N).state_of("p1", target_kind=TargetKind.PERSONA, position=20.0)
print("B  state_of(persona) at ch20 hair:", r.attributes.get("hair_color"), "(positional retraction: believed)")
d, _ = drawn(s, 20.0)
print("B  compiled/drawn persona attrs at ch20:", d, "(is_standing drops retracted rows at ALL positions)")
