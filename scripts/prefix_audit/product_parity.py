"""Does turning on the prefix-causal persona build change anything a whole-novel consumer reads?

    python scripts/prefix_audit/product_parity.py

LABEL PROVENANCE: SYSTEM-INTERNAL (no labels). Deterministic persona path, stub LLM mode, CPU only.

Builds each serial's persona stage twice (default, and `prefix_causal=True`) and compares what the product's readers
get: voice casting's trait profiles (`load_trait_profiles`), the reference sheet's demographics (`_demographics`, no
position), and the character dashboard's traits. The repair adds revisions stamped by evidence horizon; a consumer that
wants the whole-novel value must still read the final one. Any difference is reported per consumer. Also reports the
reader-position view (`standing_values(known_by=end of chapter k)`) at the audit cuts, which is what is meant to change.
Writes data/eval/prefix_audit/product_parity.json (ids, closed-vocabulary values and counts only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit as A  # noqa: E402
import common as C  # noqa: E402
from echotales.core.models import DiscoursePosition as DP  # noqa: E402
from echotales.pipeline.persona.build import load_trait_profiles  # noqa: E402
from echotales.pipeline.persona.reference_gen import _demographics  # noqa: E402
from echotales.pipeline.persona.split import persona_at, standing_values  # noqa: E402
from echotales.pipeline.webview import build_character_dashboard  # noqa: E402

SERIALS = ("lord-of-the-mysteries", "omniscient-readers-viewpoint", "reverend-insanity")


def snapshot(store, nid):
    prof = {e: {k: str(getattr(p, k)) for k in ("gender", "age_band", "register", "archetype", "extraversion")}
            for e, p in load_trait_profiles(nid, store).items()}
    people = [s for s in store.all_selves(nid) if s.kind.is_person]
    demo = {s.id: list(_demographics(store, persona_at(store, s.id), novel_id=nid, entity_id=s.id)) for s in people}
    dash = {row["self_id"]: sorted((t["key"], t["value"]) for t in row["traits"] if t["key"] in ("gender", "age_band", "register"))
            for row in build_character_dashboard(store, nid)["characters"]}
    return prof, demo, dash, people


def main() -> None:
    out = dict(audit="product-parity", label_provenance="SYSTEM-INTERNAL, no labels", serials={})
    for nid in SERIALS:
        src = C.snapshot_source(nid)
        res, stores = {}, {}
        for repair in (False, True):
            store, secs = A.build(nid, src, f"parity_{'on' if repair else 'off'}", None, repair)
            stores[repair] = store
            res[repair] = snapshot(store, nid) + (secs,)
        (p0, d0, b0, people, s0), (p1, d1, b1, _, s1) = res[False], res[True]

        def diff(a, b):
            return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))

        reader = {}
        for k in C.CUTS[nid]:
            kn = DP(chapter=k, offset=10**6)
            reader[str(k)] = sum(
                standing_values(stores[False], persona_at(stores[False], s.id), known_by=kn).get("gender")
                != standing_values(stores[True], persona_at(stores[True], s.id), known_by=kn).get("gender")
                for s in people)
        out["serials"][nid] = dict(
            people=len(people), persona_seconds_off=round(s0, 2), persona_seconds_on=round(s1, 2),
            voice_profiles_differ=diff(p0, p1), reference_demographics_differ=diff(d0, d1), dashboard_traits_differ=diff(b0, b1),
            dashboard_rows_off=sum(len(v) for v in b0.values()), dashboard_rows_on=sum(len(v) for v in b1.values()),
            reader_view_gender_changes_by_cut=reader)
        for st in stores.values():
            st.close()
        o = out["serials"][nid]
        print(nid, "voice diff", len(o["voice_profiles_differ"]), "reference diff", len(o["reference_demographics_differ"]),
              "dashboard diff", len(o["dashboard_traits_differ"]), "rows", o["dashboard_rows_off"], o["dashboard_rows_on"],
              "reader-view gender changes", reader, flush=True)
    path = C.RESULTS / "product_parity.json"
    path.write_text(json.dumps(out, indent=1))
    print("wrote", path)


if __name__ == "__main__":
    main()
