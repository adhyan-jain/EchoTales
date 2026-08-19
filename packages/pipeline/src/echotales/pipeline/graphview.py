"""A browsable picture of what the graph actually holds.

`webview.py` renders the *text* view -- chapters, spans, who was attributed
to what. This renders the **shape**: entities as nodes, the evidence that
binds them as edges, and every fact dated to the position it was learned at.
It exists because the graph is the part of this project worth defending and
the part nobody can see; a claim like "facts are position-filtered, so
chapter 1 does not know chapter 500" is abstract until you drag a slider and
watch the nodes appear.

**Everything is computed from the store and inlined.** One HTML file, no CDN,
no build step, no server -- open it from disk. The layout is a small
force simulation in plain JS rather than a library, for the same reason
`render/motion.py` writes PNG frames instead of adding a video dependency:
the alternative pulls in a toolchain to draw a few hundred circles.

**The position slider is the point.** Every node and edge carries the
chapter it was first attested in, so moving the slider re-renders the graph
*as it was known then*. That is the one property of this store that a
static diagram cannot show.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from echotales.core.enums import TargetKind
from echotales.core.store import Store


@dataclass(slots=True)
class GraphNode:
    id: str
    label: str
    kind: str
    chapter: float
    mentions: int = 0
    facts: list[list[str]] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GraphEdge:
    source: str
    target: str
    kind: str
    chapter: float
    weight: int = 1


def build_graph(
    store: Store, novel_id: str, *, top: int = 60, through_chapter: float | None = None
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Entities, their dated facts, and co-occurrence between them.

    **Co-occurrence, not relations**, and the distinction is deliberate: the
    `relation` table is empty for every novel processed so far, so drawing
    only relations would render an accurate picture of nothing. Two entities
    mentioned in the same block is real, attested evidence -- it is simply
    weaker evidence than a typed relation, and the viewer says so.
    """
    entities = {e.id: e for e in store.all_selves(novel_id)}
    counts = {eid: store.mention_count_for(novel_id, eid) for eid in entities}
    keep = sorted(counts, key=lambda e: -counts[e])[:top]
    kept = set(keep)

    nodes: list[GraphNode] = []
    for eid in keep:
        entity = entities[eid]
        facts: list[list[str]] = []
        for attr in store.get_attributes(TargetKind.SELF, eid):
            chapter = getattr(attr.learned_at_pos, "chapter", 0.0) or 0.0
            if through_chapter is not None and chapter > through_chapter:
                continue
            facts.append([attr.key, str(attr.value), f"ch{chapter:g}"])
        nodes.append(
            GraphNode(
                id=eid,
                label=entity.canonical_label,
                kind=entity.kind.value,
                chapter=float(getattr(entity.first_attested_pos, "chapter", 0.0) or 0.0),
                mentions=counts[eid],
                facts=sorted(facts)[:12],
            )
        )

    pairs: dict[tuple[str, str], tuple[int, float]] = {}
    for chapter in store.chapter_numbers(novel_id):
        if through_chapter is not None and chapter > through_chapter:
            continue
        by_block: dict[int, set[str]] = {}
        for mention in store.get_mentions(novel_id, chapter):
            if mention.target_id in kept:
                by_block.setdefault(mention.block_index, set()).add(mention.target_id)
        for present in by_block.values():
            ordered = sorted(present)
            for i, a in enumerate(ordered):
                for b in ordered[i + 1 :]:
                    weight, first = pairs.get((a, b), (0, chapter))
                    pairs[(a, b)] = (weight + 1, min(first, chapter))

    edges = [
        GraphEdge(source=a, target=b, kind="co-occurs", chapter=first, weight=weight)
        # A single shared block is noise at novel scale; two is a pattern.
        for (a, b), (weight, first) in pairs.items()
        if weight > 1
    ]
    return nodes, edges


_TEMPLATE = """<!doctype html>
<meta charset="utf-8"><title>%(title)s</title>
<style>
 :root{--bg:#0f1115;--fg:#e6e6e6;--dim:#8b93a1;--edge:#2c313c;--card:#171a21}
 body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,sans-serif}
 header{padding:12px 16px;border-bottom:1px solid var(--edge);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
 h1{font-size:15px;margin:0;font-weight:600}
 .muted{color:var(--dim)}
 #wrap{display:flex;height:calc(100vh - 58px)}
 canvas{flex:1;display:block}
 aside{width:320px;border-left:1px solid var(--edge);padding:14px;overflow:auto;background:var(--card)}
 aside h2{font-size:14px;margin:0 0 8px}
 table{width:100%%;border-collapse:collapse;font-size:12px}
 td{padding:3px 4px;border-bottom:1px solid var(--edge);vertical-align:top}
 td.k{color:var(--dim);white-space:nowrap}
 input[type=range]{width:220px}
 .legend span{margin-right:12px;font-size:12px}
 .dot{display:inline-block;width:9px;height:9px;border-radius:50%%;margin-right:4px}
</style>
<header>
  <h1>%(title)s</h1>
  <label class="muted">as known at chapter <b id="chv">%(max_chapter)s</b>
    <input id="ch" type="range" min="1" max="%(max_chapter)s" value="%(max_chapter)s"></label>
  <span class="legend">
    <span><i class="dot" style="background:#7aa2f7"></i>character</span>
    <span><i class="dot" style="background:#9ece6a"></i>location</span>
    <span><i class="dot" style="background:#e0af68"></i>organization</span>
    <span><i class="dot" style="background:#bb9af7"></i>item</span>
  </span>
  <span class="muted" id="counts"></span>
</header>
<div id="wrap"><canvas id="c"></canvas><aside id="side"><h2>Click a node</h2>
<p class="muted">Edges are block co-occurrence, not typed relations — the
relation table is empty for this novel, so this shows the evidence that
actually exists. Thickness is how often two entities share a block.</p>
</aside></div>
<script>
const NODES=%(nodes)s, EDGES=%(edges)s;
const COLOR={CHARACTER:'#7aa2f7',LOCATION:'#9ece6a',ORGANIZATION:'#e0af68',ITEM:'#bb9af7'};
const c=document.getElementById('c'),ctx=c.getContext('2d');
let W=0,H=0,cut=%(max_chapter)s,sel=null;
function size(){W=c.width=c.clientWidth*devicePixelRatio;H=c.height=c.clientHeight*devicePixelRatio;}
addEventListener('resize',()=>{size();});size();
const P={};NODES.forEach((n,i)=>{const a=i/NODES.length*Math.PI*2;
  P[n.id]={x:W/2+Math.cos(a)*W/4,y:H/2+Math.sin(a)*H/4,vx:0,vy:0};});
function live(){const ns=NODES.filter(n=>n.chapter<=cut);const ids=new Set(ns.map(n=>n.id));
  return [ns,EDGES.filter(e=>e.chapter<=cut&&ids.has(e.source)&&ids.has(e.target))];}
function step(){const [ns,es]=live();
  for(const n of ns){const p=P[n.id];p.vx+=(W/2-p.x)*0.0006;p.vy+=(H/2-p.y)*0.0006;}
  for(let i=0;i<ns.length;i++)for(let j=i+1;j<ns.length;j++){
    const a=P[ns[i].id],b=P[ns[j].id];let dx=b.x-a.x,dy=b.y-a.y;let d2=dx*dx+dy*dy||1;
    if(d2<400*400){const f=900000/d2;const d=Math.sqrt(d2);dx/=d;dy/=d;
      a.vx-=dx*f/1000;a.vy-=dy*f/1000;b.vx+=dx*f/1000;b.vy+=dy*f/1000;}}
  for(const e of es){const a=P[e.source],b=P[e.target];
    const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;const f=(d-180*devicePixelRatio)*0.0015*Math.min(e.weight,6);
    a.vx+=dx/d*f;a.vy+=dy/d*f;b.vx-=dx/d*f;b.vy-=dy/d*f;}
  for(const n of ns){const p=P[n.id];p.vx*=0.86;p.vy*=0.86;p.x+=p.vx;p.y+=p.vy;
    p.x=Math.max(30,Math.min(W-30,p.x));p.y=Math.max(30,Math.min(H-30,p.y));}
  draw(ns,es);requestAnimationFrame(step);}
function draw(ns,es){ctx.clearRect(0,0,W,H);
  ctx.lineWidth=devicePixelRatio;
  for(const e of es){const a=P[e.source],b=P[e.target];
    ctx.strokeStyle='rgba(120,130,150,'+Math.min(0.08+e.weight/60,0.5)+')';
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();}
  for(const n of ns){const p=P[n.id];const r=(6+Math.sqrt(n.mentions))*devicePixelRatio;
    ctx.fillStyle=COLOR[n.kind]||'#8b93a1';ctx.globalAlpha=sel&&sel!==n.id?0.35:1;
    ctx.beginPath();ctx.arc(p.x,p.y,r,0,7);ctx.fill();
    ctx.globalAlpha=1;ctx.fillStyle='#e6e6e6';ctx.font=(11*devicePixelRatio)+'px sans-serif';
    if(n.mentions>8||sel===n.id)ctx.fillText(n.label,p.x+r+3,p.y+4);}
  document.getElementById('counts').textContent=ns.length+' entities, '+es.length+' co-occurrence edges';}
c.addEventListener('click',ev=>{const r=c.getBoundingClientRect();
  const x=(ev.clientX-r.left)*devicePixelRatio,y=(ev.clientY-r.top)*devicePixelRatio;
  const [ns]=live();let best=null,bd=1e9;
  for(const n of ns){const p=P[n.id];const d=Math.hypot(p.x-x,p.y-y);if(d<bd){bd=d;best=n;}}
  if(best&&bd<40*devicePixelRatio){sel=best.id;show(best);}else{sel=null;}});
function show(n){const rows=n.facts.map(f=>'<tr><td class="k">'+f[0]+'</td><td>'+f[1]+
  ' <span class="muted">'+f[2]+'</span></td></tr>').join('');
  document.getElementById('side').innerHTML='<h2>'+n.label+'</h2>'+
   '<p class="muted">'+n.kind.toLowerCase()+' · first seen ch'+n.chapter+' · '+n.mentions+' mentions</p>'+
   (rows?'<table>'+rows+'</table>':'<p class="muted">No dated facts by this chapter.</p>');}
document.getElementById('ch').addEventListener('input',e=>{cut=+e.target.value;
  document.getElementById('chv').textContent=cut;});
step();
</script>
"""


def write_graphview(
    store: Store, novel_id: str, out_path: str | Path, *, top: int = 60
) -> Path:
    """Render the graph to one self-contained HTML file."""
    nodes, edges = build_graph(store, novel_id, top=top)
    chapters = store.chapter_numbers(novel_id)
    html = _TEMPLATE % {
        "title": f"{novel_id} — knowledge graph",
        "nodes": json.dumps([asdict(n) for n in nodes]),
        "edges": json.dumps([asdict(e) for e in edges]),
        "max_chapter": f"{max(chapters) if chapters else 1:g}",
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
