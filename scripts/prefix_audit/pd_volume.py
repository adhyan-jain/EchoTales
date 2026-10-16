"""Build EchoTales stores from public-domain Gutenberg text for the second-domain test (docs/research/PREFIX_FAITHFULNESS/PREREG_PD.md).

    PYTHONPATH=<worktree>/packages/core/src:<worktree>/packages/pipeline/src \
      python scripts/prefix_audit/pd_volume.py

Not the resolver: chapters come from the Gutenberg headings, one block per paragraph, narration and dialogue spans from the
quotation marks, and mention-to-character assignments from a name gazetteer (whole-word, case-sensitive; ambiguous bare surnames
are left out). The persona stage that is audited runs unchanged on the result. Source text is read-only and never copied
into the repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from echotales.core.enums import AliasType, BlockType, ReferenceMode, SpanType, TargetKind  # noqa: E402
from echotales.core.models import Block, Chapter, DiscoursePosition, Mention, Self, Span  # noqa: E402
from echotales.core.store import Store  # noqa: E402

GUT = Path("/home/adhyan/Desktop/EchoTales/data/raw/pd_gutenberg")
OUT_DIR = WT / "data" / "scratch" / "pd_db"

BOOKS: dict[str, dict] = {
    "oliver-twist": dict(gid="730", title="Oliver Twist", entities={
        "Oliver Twist": [r"Oliver"], "Fagin": [r"Fagin"], "Bill Sikes": [r"Sikes"], "Nancy": [r"Nancy"],
        "Rose Maylie": [r"Miss Maylie", r"Rose"], "Monks": [r"Monks"], "Jack Dawkins": [r"Dodger", r"Dawkins"],
        "Charley Bates": [r"Bates", r"Charley"], "Noah Claypole": [r"Claypole", r"Bolter", r"Noah"],
        "Toby Crackit": [r"Crackit", r"Toby"], "Brittles": [r"Brittles"], "Giles": [r"Giles"],
        "Harry Maylie": [r"Harry Maylie", r"Harry"], "Mrs. Maylie": [r"Mrs\. Maylie"], "Mr. Bumble": [r"Bumble"],
        "Mr. Brownlow": [r"Brownlow"], "Barney": [r"Barney"], "Blathers": [r"Blathers"], "Duff": [r"Duff"],
        "Charlotte": [r"Charlotte"], "Dick": [r"Dick"], "Mr. Grimwig": [r"Grimwig"], "Dr. Losberne": [r"Losberne"],
        "Mrs. Bedwin": [r"Bedwin"], "Mrs. Corney": [r"Corney"]}),
    "three-musketeers": dict(gid="1257", title="The Three Musketeers", entities={
        "d'Artagnan": [r"[Dd]['’]Artagnan"], "Athos": [r"Athos"], "Porthos": [r"Porthos"], "Aramis": [r"Aramis"],
        "Milady": [r"Milady"], "Felton": [r"Felton"], "Planchet": [r"Planchet"], "Buckingham": [r"Buckingham"],
        "Constance Bonacieux": [r"Madame Bonacieux", r"Mme\.? Bonacieux", r"Constance"],
        "Monsieur Bonacieux": [r"Monsieur Bonacieux", r"M\. Bonacieux"], "Kitty": [r"Kitty"], "Grimaud": [r"Grimaud"],
        "Bazin": [r"Bazin"], "Mousqueton": [r"Mousqueton"], "Rochefort": [r"Rochefort"], "Richelieu": [r"Richelieu"],
        "Lord de Winter": [r"Lord de Winter"], "Laporte": [r"Laporte"], "Treville": [r"Tr[ée]ville"],
        "Anne of Austria": [r"Anne of Austria"]}),
}
HEADING = re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(?:[IVXLC]+|\d+)\b[^\n]*$", re.M)
QUOTE = re.compile(r'"[^"]*"|“[^”]*”')


def body_of(gid: str) -> str:
    t = (GUT / f"pg{gid}.txt").read_text(encoding="utf-8").replace("\r", "")
    s, e = t.find("*** START"), t.find("*** END")
    return t[t.find("\n", s) + 1: e]


def chapters_of(body: str) -> list[str]:
    heads = list(HEADING.finditer(body))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        if end - h.end() > 800:  # a table-of-contents line is followed by another heading at once
            out.append(body[h.end():end])
    return out


def spans_of(para: str) -> list[tuple[int, int, SpanType]]:
    out, pos = [], 0
    for q in QUOTE.finditer(para):
        if para[pos:q.start()].strip():
            out.append((pos, q.start(), SpanType.NARRATION_ACTION))
        out.append((q.start(), q.end(), SpanType.DIALOGUE))
        pos = q.end()
    if para[pos:].strip():
        out.append((pos, len(para), SpanType.NARRATION_ACTION))
    return out


def build(nid: str, spec: dict) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{nid}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    store = Store(str(path))
    store.add_novel(nid, spec["title"], "x.epub", "generic")
    pats = {lab: re.compile(r"(?<![\w'’])(?:" + "|".join(alts) + r")(?!\w)") for lab, alts in spec["entities"].items()}
    ids = {lab: f"{nid}:self{i}" for i, lab in enumerate(spec["entities"])}
    first: dict[str, tuple[int, int]] = {}
    n_sp = n_m = n_par = 0
    for c, chap in enumerate(chapters_of(body_of(spec["gid"])), start=1):
        paras = [" ".join(ln.strip() for ln in p.splitlines()).replace("_", "") for p in chap.split("\n\n")]
        paras = [p for p in paras if len(p) > 2 and not p.isupper()]
        spans, mentions = [], []
        for bi, para in enumerate(paras):
            n_par += 1
            sp = spans_of(para)
            for s, e, ty in sp:
                n_sp += 1
                spans.append(Span(id=f"sp{n_sp}", novel_id=nid, chapter=float(c), block_index=bi, start=s, end=e, span_type=ty, text=para[s:e]))
            for lab, pat in pats.items():
                for m in pat.finditer(para):
                    cont = next((x for x in sp if x[0] <= m.start() < x[1]), None)
                    if cont is None:
                        continue
                    n_m += 1
                    first.setdefault(lab, (c, m.start()))
                    mentions.append(Mention(id=f"m{n_m}", novel_id=nid, segment_id="s", chapter=float(c), offset=m.start(), block_index=bi,
                                            text=m.group(0), alias_type=AliasType.RIGID_NAME, span_type=cont[2],
                                            reference_mode=ReferenceMode.PRESENT, target_kind=TargetKind.SELF, target_id=ids[lab]))
        store.add_chapter(Chapter(novel_id=nid, number=float(c), title="T", source_href=f"{c}.html",
                                  blocks=[Block(index=i, block_type=BlockType.PROSE, text=p) for i, p in enumerate(paras)]))
        store.add_spans(spans)
        store.add_mentions(mentions)
    for lab, (fc, off) in first.items():
        store.add_self(Self(id=ids[lab], novel_id=nid, canonical_label=lab,
                            first_attested_pos=DiscoursePosition(chapter=float(fc), offset=off), kind=TargetKind.SELF))
    store.conn.commit()
    store.close()
    return dict(novel=nid, chapters=c, paragraphs=n_par, spans=n_sp, mentions=n_m, characters=len(first), dropped=sorted(set(ids) - set(first)))


def main() -> None:
    for nid, spec in BOOKS.items():
        print(build(nid, spec), flush=True)


if __name__ == "__main__":
    main()
