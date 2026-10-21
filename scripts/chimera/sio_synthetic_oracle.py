"""SIO runner: synthetic identity-reveal oracle (implements PREREG_SIO_synthetic_identity_oracle.md v1).

Worlds are generated from a spec; the oracle reads ONLY the spec (never a Store,
state_of or resolver output). The repo's deterministic resolver (no LLM) is run
on the whole world (F) and on prefixes (P_c). Mentions are supplied with exact
offsets, so detection is perfect by construction.

Scope: properties of the resolver mechanism on synthetic input. Not real-world
performance. See docs/research/NOVELTY_SUPPORT.md for how
ambiguities in the frozen prereg were resolved.

    python scripts/chimera/sio_synthetic_oracle.py --out data/eval/chimera/sio_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import defaultdict
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path

os.environ["ECHOTALES_LLM_MODE"] = "stub"

from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType  # noqa: E402
from echotales.core.models import Block, Chapter, Mention  # noqa: E402
from echotales.core.store import Store  # noqa: E402
from echotales.pipeline.resolve import resolve_novel  # noqa: E402
from echotales.pipeline.resolve.detect_reveals import REVEAL_PATTERNS  # noqa: E402

N_WORLDS = 40
N_CHAPTERS = 12
GIVEN = ["Torvin", "Lessa", "Marek", "Ondrel", "Pyra", "Quillon", "Savrik", "Tamsin", "Ulvane", "Verrin",
         "Wystan", "Yorrel", "Zelka", "Brannoch", "Cadrel", "Delvin"]
FAMILY = ["Ashkel", "Dornwick", "Evermar", "Fenholt", "Garrow", "Hollin", "Ilvane", "Jorrick"]
PLACES = ["the harbour", "the mill", "the east gate", "the library", "the market square"]
ALIASES = ["the masked guest", "the stranger"]
TITLE = "the clan head"

P = ReferenceMode.PRESENT
NR = ReferenceMode.NARRATOR_REFERENCE


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (c - r) / d), min(1.0, (c + r) / d)


# ---------------------------------------------------------------- world spec
@dataclass
class MSpec:
    id: str
    chapter: int
    offset: int
    text: str
    alias_type: AliasType
    mode: ReferenceMode
    kind: str  # control | pre_alias | post_alias | title_pre | title_post
    reader: str | None  # reader-warranted referent label; None = UNDETERMINED
    omni: str
    group: str = ""


@dataclass
class World:
    seed: int
    names: list[str]
    chapters: dict[int, str] = field(default_factory=dict)
    mentions: list[MSpec] = field(default_factory=list)
    reveals: list[dict] = field(default_factory=list)
    title: dict = field(default_factory=dict)
    reveal_sentences: list[str] = field(default_factory=list)


class _Ch:
    def __init__(self, world: World, number: int):
        self.w, self.n, self.buf, self.k = world, number, "", 0

    def text(self, s: str) -> None:
        self.buf += s

    def men(self, surface: str, atype: AliasType, mode: ReferenceMode, kind: str, reader, omni) -> None:
        self.k += 1
        mid = f"w{self.w.seed}-c{self.n}-m{self.k}"
        self.w.mentions.append(
            MSpec(mid, self.n, len(self.buf), surface, atype, mode, kind, reader, omni, group=f"g-{mid}")
        )
        self.buf += surface

    def done(self) -> None:
        self.w.chapters[self.n] = self.buf.strip()


def make_world(seed: int) -> World:
    rng = random.Random(seed)
    givens = rng.sample(GIVEN, 6)
    fams = rng.sample(FAMILY, 5)
    # C0,C1 share a family (containment relations); C2,C3 unique families; C4,C5 single token.
    names = [f"{givens[0]} {fams[0]}", f"{givens[1]} {fams[0]}", f"{givens[2]} {fams[1]}",
             f"{givens[3]} {fams[2]}", givens[4], givens[5]]
    w = World(seed=seed, names=names)

    d0 = 2 + seed % 3           # reveal 0 distance 2..4, a0 = 3 -> r0 in 5..7
    d1 = 2 + (seed // 3) % 2    # reveal 1 distance 2..3, a1 = 9 -> r1 in 11..12
    a = [3, 9]
    r = [a[0] + d0, a[1] + d1]
    pool = [0, 1, 2, 3]  # named in ch1-2, usable as Y/Z
    y0 = rng.choice(pool)
    z0 = rng.choice([c for c in pool if c != y0])
    y1 = rng.choice([c for c in pool if c != y0])
    z1 = rng.choice([c for c in pool if c != y1])
    reveals = [dict(alias=ALIASES[0], a=a[0], r=r[0], d=d0, y=y0, z=z0),
               dict(alias=ALIASES[1], a=a[1], r=r[1], d=d1, y=y1, z=z1)]
    w.reveals = reveals
    retro = seed % 2 == 0   # even seeds: bare-title mentions PRECEDE the holder being named
    h1, h2 = 5, 4           # holders: C5 first, C4 from ch5 (C5 is introduced late in retro worlds)
    w.title = dict(retro=retro, h1=h1, h2=h2)

    alias_pre: dict[int, int] = {}
    post_ch: dict[int, int] = {}
    for i, rv in enumerate(reveals):
        for c in range(rv["a"], rv["r"]):
            alias_pre[c] = i
        for c in (rv["r"], rv["r"] + 1):
            if c <= N_CHAPTERS and c not in alias_pre:
                post_ch[c] = i
    lone = set(alias_pre) | set(post_ch)  # chapters whose only PRESENT named mention must be Z

    def place() -> str:
        return rng.choice(PLACES)

    def named(ch: _Ch, idx: int, mode=P):
        ch.men(names[idx], AliasType.RIGID_NAME, mode, "control", names[idx], names[idx])

    for n in range(1, N_CHAPTERS + 1):
        ch = _Ch(w, n)
        if n in lone:
            i = alias_pre.get(n, post_ch.get(n))
            rv = reveals[i]
            z = rv["z"]
            if n in alias_pre:
                named(ch, z)
                ch.text(" spoke quietly with ")
                ch.men(rv["alias"], AliasType.RELATIONAL_DEICTIC, P, "pre_alias", None, names[rv["y"]])
                ch.text(f" near {place()}. ")
            else:
                if n == rv["r"]:
                    sent_start = len(ch.buf)
                    ch.men(rv["alias"].capitalize(), AliasType.RELATIONAL_DEICTIC, P, "post_alias",
                           names[rv["y"]], names[rv["y"]])
                    ch.text(", in truth, was ")
                    ch.men(names[rv["y"]], AliasType.RIGID_NAME, NR, "control", names[rv["y"]], names[rv["y"]])
                    ch.text(". ")
                    w.reveal_sentences.append(ch.buf[sent_start:].strip())
                named(ch, z)
                ch.text(" met ")
                ch.men(rv["alias"], AliasType.RELATIONAL_DEICTIC, P, "post_alias",
                       names[rv["y"]], names[rv["y"]])
                ch.text(f" near {place()}. ")
        elif n == 1:
            idxs = [0, 1, 2] + ([5] if not retro else [])
            for idx in idxs:
                named(ch, idx)
                ch.text(f" waited at {place()}. ")
        elif n == 2:
            for idx in [3, 4]:
                named(ch, idx)
                ch.text(f" waited at {place()}. ")
        else:
            for idx in rng.sample([0, 1, 2, 3, 4], 3):
                named(ch, idx)
                ch.text(f" crossed {place()}. ")

        # --- title stream (only in chapters without an alias window) -------
        if n in (1, 2):
            if not retro:
                ch.text(f"Clan head {names[h1]} rose from the dais. ")
                ch.text("Everyone watched ")
                ch.men(TITLE, AliasType.TRANSFERABLE_TITLE, P, "title_post", names[h1], names[h1])
                ch.text(" closely. ")
            else:
                ch.text("Everyone watched ")
                ch.men(TITLE, AliasType.TRANSFERABLE_TITLE, P, "title_pre", None, names[h1])
                ch.text(" closely. ")
        if retro and n in (3, 4):
            if n == 3:
                ch.text("Soon after, ")
                ch.men(names[h1], AliasType.RIGID_NAME, NR, "control", names[h1], names[h1])
                ch.text(" was named as head of the clan. ")
            ch.text(f"Clan head {names[h1]} rose from the dais. ")
        if n in (5, 6):
            if n == 5:
                ch.text("Soon after, ")
                ch.men(names[h2], AliasType.RIGID_NAME, NR, "control", names[h2], names[h2])
                ch.text(" took the seat. ")
            ch.text(f"Clan head {names[h2]} rose from the dais. ")
        if n == 8:
            ch.text("Everyone watched ")
            ch.men(TITLE, AliasType.TRANSFERABLE_TITLE, P, "title_post", names[h2], names[h2])
            ch.text(" closely. ")
        ch.done()
    return w


# ------------------------------------------------------------------ running
def build_store(w: World, upto: int) -> Store:
    s = Store(":memory:")
    nid = f"w{w.seed}"
    s.add_novel(nid, nid, "x.epub", "generic")
    for n in range(1, upto + 1):
        s.add_chapter(Chapter(novel_id=nid, number=float(n), title="T", source_href=f"{n}.html",
                              blocks=[Block(index=0, block_type=BlockType.PROSE, text=w.chapters[n])]))
    ments = []
    for m in w.mentions:
        if m.chapter > upto:
            continue
        assert w.chapters[m.chapter][m.offset:m.offset + len(m.text)] == m.text, (m.id, m.text)
        ments.append(Mention(id=m.id, novel_id=nid, segment_id="s", chapter=float(m.chapter), offset=m.offset,
                             text=m.text, alias_type=m.alias_type, span_type=SpanType.NARRATION_ACTION,
                             reference_mode=m.mode, block_index=0, local_group_id=m.group))
    s.add_mentions(ments)
    s.conn.commit()
    return s


def run(w: World, upto: int) -> dict[str, str | None]:
    s = build_store(w, upto)
    resolve_novel(f"w{w.seed}", s)
    out: dict[str, str | None] = {}
    for n in range(1, upto + 1):
        for m in s.get_mentions(f"w{w.seed}", float(n)):
            if m.target_id is None:
                out[m.id] = None
            else:
                se = s.get_self(m.target_id)
                out[m.id] = se.canonical_label if se else f"?{m.target_id}"
    s.conn.close()
    return out


def title_event_probe(w: World) -> list[dict]:
    """Exploratory: for each title mention linked in F, compare the LINK event's cause_pos chapter with the
    chapter of the first declaration that names the holder (the binding's learned_at_pos)."""
    from echotales.core.enums import EventType

    s = build_store(w, N_CHAPTERS)
    resolve_novel(f"w{w.seed}", s)
    first_decl: dict[str, int] = {}
    for b in s.all_aliases(f"w{w.seed}"):
        if b.alias == "the clan head":
            first_decl[b.target_id] = b.learned_at_pos.chapter
    mention_chapter = {m.id: m.chapter for m in w.mentions}
    out = []
    for ev in s.iter_events():
        pl = ev.payload
        if ev.type is EventType.LINK and pl.get("title") and pl.get("mention_id") in mention_chapter:
            out.append(dict(mention=pl["mention_id"], event_cause_chapter=ev.cause_pos.chapter,
                            holder_binding_learned_chapter=first_decl.get(pl["target_id"])))
    s.conn.close()
    return out


def cuts(w: World) -> list[int]:
    c = {4, 5}
    for rv in w.reveals:
        c |= {rv["r"] - 1, rv["r"]}
    return sorted(x for x in c if 1 <= x < N_CHAPTERS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--worlds", type=int, default=N_WORLDS)
    args = ap.parse_args()

    m1_pairs = [0, 0]
    m1_worlds = [0, 0]
    m1_examples: list[dict] = []
    m2 = dict(F=[0, 0], P=[0, 0])
    m3 = [0, 0]
    m4 = dict(F=[0, 0], P=[0, 0])
    m4_pre_named = [0, 0]
    x_any_link = dict(F=[0, 0], P=[0, 0])
    x_to_z = [0, 0]
    x_ctrl = [0, 0]
    x_post_any = [0, 0]
    x_title_post = [0, 0]
    x_reveal_regex = dict(frozen=[0, 0], repo_form=[0, 0])
    x_event_early = [0, 0]  # title LINK events stamped before the holder was first declared
    by_distance: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    per_world = []

    for seed in range(args.worlds):
        w = make_world(seed)
        names = w.names
        F = run(w, N_CHAPTERS)
        F2 = run(w, N_CHAPTERS)
        assert F == F2, f"nondeterministic resolver on world {seed}"
        world_violation = False
        P_by_cut = {c: run(w, c) for c in cuts(w)}
        for c, Pc in P_by_cut.items():
            for mid, lab in Pc.items():
                m1_pairs[1] += 1
                if F[mid] != lab:
                    m1_pairs[0] += 1
                    world_violation = True
                    if len(m1_examples) < 25:
                        ms = next(x for x in w.mentions if x.id == mid)
                        m1_examples.append(dict(seed=seed, cut=c, mention=mid, text=ms.text, chapter=ms.chapter,
                                                kind=ms.kind, prefix=lab, full=F[mid]))
        m1_worlds[1] += 1
        m1_worlds[0] += int(world_violation)

        rv_by_alias = {rv["alias"]: rv for rv in w.reveals}
        for m in w.mentions:
            if m.kind in ("pre_alias", "post_alias"):
                rv = rv_by_alias[m.text.lower()]
                y = names[rv["y"]]
                z = names[rv["z"]]
                if m.kind == "pre_alias":
                    assert m.reader is None  # oracle: UNDETERMINED
                    hit = F[m.id] == y
                    m2["F"][1] += 1
                    m2["F"][0] += hit
                    by_distance[rv["d"]][1] += 1
                    by_distance[rv["d"]][0] += hit
                    x_any_link["F"][1] += 1
                    x_any_link["F"][0] += F[m.id] is not None
                    x_to_z[1] += 1
                    x_to_z[0] += F[m.id] == z
                    Pc = P_by_cut[rv["r"] - 1]
                    m2["P"][1] += 1
                    m2["P"][0] += Pc[m.id] == y
                    x_any_link["P"][1] += 1
                    x_any_link["P"][0] += Pc[m.id] is not None
                else:
                    m3[1] += 1
                    m3[0] += F[m.id] != y
                    x_post_any[1] += 1
                    x_post_any[0] += F[m.id] is not None
            elif m.kind == "title_pre":
                h = names[w.title["h1"]]
                assert m.reader is None
                m4["F"][1] += 1
                m4["F"][0] += F[m.id] == h
                Pc = P_by_cut[4]
                m4["P"][1] += 1
                m4["P"][0] += Pc[m.id] == h
            elif m.kind == "title_post":
                if m.chapter <= 2:
                    h = names[w.title["h1"]]
                    m4_pre_named[1] += 1
                    m4_pre_named[0] += F[m.id] == h
                else:
                    h = names[w.title["h2"]]
                    x_title_post[1] += 1
                    x_title_post[0] += F[m.id] == h
            elif m.kind == "control" and m.mode is P:
                x_ctrl[1] += 1
                x_ctrl[0] += F[m.id] == m.omni
        for ev in title_event_probe(w):
            if ev["holder_binding_learned_chapter"] is not None:
                x_event_early[1] += 1
                x_event_early[0] += ev["event_cause_chapter"] < ev["holder_binding_learned_chapter"]
        for s_ in w.reveal_sentences:
            x_reveal_regex["frozen"][1] += 1
            x_reveal_regex["frozen"][0] += any(p.search(s_) for p in REVEAL_PATTERNS)
        per_world.append(dict(seed=seed, retro=w.title["retro"],
                              reveals=[(rv["a"], rv["r"], rv["d"]) for rv in w.reveals]))

    for tmpl in ("This was none other than {n}.", "It was {n}, of course."):
        x_reveal_regex["repo_form"][1] += 1
        x_reveal_regex["repo_form"][0] += any(p.search(tmpl.format(n="Marek Ashkel")) for p in REVEAL_PATTERNS)

    def row(k_n):
        k, n = k_n
        lo, hi = wilson(k, n)
        return dict(k=k, n=n, rate=(k / n if n else None), wilson95=[lo, hi])

    res = dict(
        preregistration="PREREG_SIO_synthetic_identity_oracle.md v1 (sha256 df93ef3a...)",
        worlds=args.worlds,
        determinism="resolve_novel run twice on every full world; outputs identical (asserted)",
        M1_prefix_invariance_violation_pooled_mention_cut_pairs=row(m1_pairs),
        M1_worlds_with_any_violation=row(m1_worlds),
        M1_examples=m1_examples,
        M2_premature_resolution_F=row(m2["F"]),
        M2_premature_resolution_P_before_reveal=row(m2["P"]),
        M2_F_by_reveal_distance={str(d): row(v) for d, v in sorted(by_distance.items())},
        M3_post_reveal_miss_F=row(m3),
        M4_retro_title_link_F=row(m4["F"]),
        M4_retro_title_link_P_cut4=row(m4["P"]),
        control_title_after_naming_linked_to_holder_F=row(m4_pre_named),
        exploratory_not_preregistered=dict(
            pre_reveal_alias_linked_to_any_entity_F=row(x_any_link["F"]),
            pre_reveal_alias_linked_to_any_entity_P=row(x_any_link["P"]),
            pre_reveal_alias_linked_to_co_present_Z_F=row(x_to_z),
            post_reveal_alias_linked_to_any_entity_F=row(x_post_any),
            title_in_H2_tenure_linked_to_H2_F=row(x_title_post),
            present_named_controls_resolved_to_own_label_F=row(x_ctrl),
            title_link_event_cause_pos_earlier_than_holder_binding_learned_at_pos=row(x_event_early),
            frozen_reveal_sentence_matches_repo_REVEAL_PATTERNS=row(x_reveal_regex["frozen"]),
            repo_stock_phrases_match_REVEAL_PATTERNS=row(x_reveal_regex["repo_form"]),
        ),
        worlds_spec=per_world,
    )
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("worlds_spec", "M1_examples")}, indent=2, default=str))


if __name__ == "__main__":
    main()
