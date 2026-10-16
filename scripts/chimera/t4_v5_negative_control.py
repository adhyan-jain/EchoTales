"""T4 v5 negative control, implemented as the pre-registered intent (PREREG_T4 v1 section 4 run N; addendum 1 to v5).

The v5 runner's N' mapped every 'yuan'-containing token with a second CONSISTENT cipher, which is still a function of
the token alone and cannot break containment (a bug against the pre-registered definition). Run N here is the
original definition: "Yuan" is renamed one way when it follows "Fang " and another way when it stands alone
(non-compositional), so the resolver's containment link between "Fang Yuan" and "Yuan" must break. Reports agreement
of O1 vs N under the same comparison as T4; CPU only, no model, no spend, no novel text.

    python scripts/chimera/t4_v5_negative_control.py --base-db <SCRATCH RI copy> --workdir <scratch dir>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import t4_renaming as T4  # noqa: E402
import t4_renaming_v5 as V5  # noqa: E402
from renaming import TOKEN  # noqa: E402


class ContextBrokenRenamer(V5.CipherRenamerV5):
    """'Yuan' after 'Fang ' gets the second cipher; standalone 'Yuan' keeps the first (non-compositional)."""

    def rename(self, text: str) -> str:
        out, pos = [], 0
        for m in TOKEN.finditer(text):
            out.append(text[pos : m.start()])
            w = m.group(0)
            if w.casefold() == "yuan" and text[max(0, m.start() - 5) : m.start()].lower().endswith("fang "):
                out.append(self._cipher(w, self.sigma2))
            else:
                out.append(self._run(w))
            pos = m.end()
        out.append(text[pos:])
        return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-db", required=True)
    ap.add_argument("--workdir", required=True)
    ap.add_argument("--out", default="data/eval/chimera/t4_v5_negative_control.json")
    args = ap.parse_args()
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    pi, protected, vocab, surfaces, existing = V5.build_v5(args.base_db)
    broken = ContextBrokenRenamer(vocab, protected, T4.SEED, existing)
    o1 = T4.run_condition("O1b", args.base_db, work, None, broken=False, smoke=0)
    nn = T4.run_condition("Nctx", args.base_db, work, broken, broken=True, smoke=0)
    con = sqlite3.connect(f"file:{args.base_db}?mode=ro", uri=True)
    mention_text = {mid: t for mid, t in con.execute("select id, text from mention where novel_id=?", (T4.NOVEL,))}
    con.close()
    keys = set(pi.mapping)
    cmp = T4.compare(o1["decisions"], nn["decisions"], broken, nn.get("flags", {}), protected, keys)
    cls = T4.classify(cmp["changed_ids"], mention_text, nn.get("flags", {}), protected, keys, base=o1["decisions"],
                      run=nn["decisions"], ren=broken.rename)
    entry = {k: v for k, v in cmp.items() if k != "changed_ids"}
    entry["changed"] = len(cmp["changed_ids"])
    entry["changed_classification"] = dict(cls)
    res = dict(label_provenance="NO LABELS (system-internal)", note="negative control per PREREG_T4 v1 definition",
               N_context_dependent=entry)
    Path(args.out).write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps({k: entry[k] for k in ("n", "agree", "agreement", "wilson95", "bcubed_f1",
                                            "changed_classification")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
