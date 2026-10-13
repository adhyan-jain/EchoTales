"""Differential test of P1 (cutoff faithfulness): compile(S,k) == compile(S|<=k, k), random stores.
S|<=k drops facts learned after chapter k and un-retracts facts whose retraction lands after k.
Read-only audit; uses the real compile_render_state (the image path) -- no production edits."""
import random, collections
from echotales.core.enums import *
from echotales.core.interval import FuzzyInterval
from echotales.core.models import *
from echotales.core.store import Store
from echotales.pipeline.render.plan_builder import compile_render_state
N="n"; KEYS=["hair_color","eye_color","distinguishing_features","typical_attire"]
def build(facts, keep):
    s=Store(":memory:"); s.add_novel(N,"T","x.epub","t")
    s.add_self(Self(id="s1",novel_id=N,canonical_label="Hero",first_attested_pos=DiscoursePosition(chapter=1)))
    s.add_persona(Persona(id="p1",novel_id=N,body_label="b",first_attested_pos=DiscoursePosition(chapter=1)))
    s.add_self_persona_binding(SelfPersonaBinding(self_id="s1",persona_id="p1",interval=FuzzyInterval.open_ended(1,last_evidence=1e6),learned_at_pos=DiscoursePosition(chapter=1),observer_id=OBSERVER_READER))
    for f in facts:
        r=keep(f)
        if r is None: continue
        s.add_attribute(N,Attribute(target_kind=f["tk"],target_id=f["tid"],key=f["key"],value=f["val"],
            interval=FuzzyInterval.open_ended(f["start"],last_evidence=1e6),learned_at_pos=DiscoursePosition(chapter=f["learned"]),
            observer_id=OBSERVER_READER,retracted_at=DiscoursePosition(chapter=r) if r else None,
            truth_status=TruthStatus.FALSE if r else TruthStatus.TRUE))
    s.conn.commit(); return s
def sig(g): return (g.targets, g.allowed_facts)
random.seed(7); viol=collections.Counter(); total=0; any_v=0
for trial in range(300):
    facts=[]
    for i in range(random.randint(3,8)):
        learned=random.randint(1,20); start=random.randint(1,learned)  # retrospective: start<=learned
        ret=random.randint(learned+1,25) if random.random()<.3 else 0
        tk=random.choice([TargetKind.PERSONA,TargetKind.SELF]); 
        facts.append(dict(tk=tk,tid="p1" if tk is TargetKind.PERSONA else "s1",key=random.choice(KEYS),val=f"v{i}",start=start,learned=learned,ret=ret))
    full=build(facts,lambda f:f["ret"] or 0)
    for k in range(1,21):
        trunc=build(facts,lambda f,k=k: None if f["learned"]>k else (0 if f["ret"]>k or f["ret"]==0 else f["ret"]))
        a=compile_render_state(full,N,["s1"],position=k+.5); b=compile_render_state(trunc,N,["s1"],position=k+.5)
        total+=1
        if sig(a)!=sig(b):
            any_v+=1
            ta,tb=a.targets[0],b.targets[0]
            if ta.persona_attributes!=tb.persona_attributes: viol["persona_attributes(drawn)"]+=1
            if ta.persona_facts!=tb.persona_facts: viol["persona_facts"]+=1
            if ta.self_attributes!=tb.self_attributes: viol["self_attributes"]+=1
            if a.digest()!=b.digest(): viol["digest_differs"]+=1
print(f"queries={total} cutoff-faithfulness violations={any_v} ({100*any_v/total:.1f}%)"); print(dict(viol))
