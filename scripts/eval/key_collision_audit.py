"""Which gold surfaces share a comparison_key while denoting different gold identities?

Measurement behind the "normalisation must not silently merge" requirement: if two
distinct gold identities fold to one `comparison_key`, any code that treats key
equality as identity (the gazetteer-exact pre-filter in resolve/score.py) merges
them without the evidence gate. Gold here is model-drafted silver (provenance
"model", unconfirmed), so counts are indicative, not a human-verified rate.

    PYTHONPATH=packages/core/src:packages/pipeline/src python scripts/eval/key_collision_audit.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from echotales.pipeline.ingest.normalize import comparison_key, token_set_key

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "eval" / "ner" / "key_collisions.json"
#: Alias types that name a role or epithet, not a person: sharing a key is expected and
#: structurally unsafe to link on.
ROLE_TYPES = {"TRANSFERABLE_TITLE", "RELATIONAL_DEICTIC", "EPITHET", "PATHWAY_TITLE", "TAROT_TITLE"}


def audit(path: Path) -> dict:
    by_key: dict[str, dict[str, dict]] = defaultdict(dict)
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        surface, identity = rec.get("surface", ""), rec.get("identity", "")
        if not surface or not identity or rec.get("kind") not in (None, "character"):
            continue
        key = comparison_key(surface)
        if not key:
            continue
        n += 1
        slot = by_key[key].setdefault(identity, {"surfaces": set(), "alias_types": set(), "mentions": 0})
        slot["surfaces"].add(surface)
        slot["alias_types"].add(rec.get("alias_type", ""))
        slot["mentions"] += 1
    shared = {k: v for k, v in by_key.items() if len(v) > 1}

    # Same measurement for the retrieval-only order-insensitive key: how many extra
    # identity pairs would token_set_key surface as candidates that comparison_key does not.
    by_tsk: dict[str, set[str]] = defaultdict(set)
    for ids in by_key.values():
        for identity, slot in ids.items():
            for s in slot["surfaces"]:
                if tsk := token_set_key(s):
                    by_tsk[tsk].add(identity)
    tsk_shared = {k: sorted(v) for k, v in by_tsk.items() if len(v) > 1}

    def example(k: str, ids: dict) -> dict:
        return {
            "key": k,
            "identities": {
                i: {"surfaces": sorted(s["surfaces"])[:4], "alias_types": sorted(s["alias_types"]), "mentions": s["mentions"]}
                for i, s in sorted(ids.items(), key=lambda kv: -kv[1]["mentions"])[:5]
            },
        }

    role = [k for k, ids in shared.items() if any(set(s["alias_types"]) & ROLE_TYPES for s in ids.values())]
    return {
        "mentions": n,
        "distinct_keys": len(by_key),
        "keys_shared_by_multiple_identities": len(shared),
        "of_which_role_or_epithet_alias_types": len(role),
        "mentions_under_shared_keys": sum(s["mentions"] for ids in shared.values() for s in ids.values()),
        "examples": [example(k, shared[k]) for k in sorted(shared, key=lambda k: -sum(s["mentions"] for s in shared[k].values()))[:15]],
        "token_set_key_shared_identity_keys": len(tsk_shared),
        "token_set_key_examples": dict(list(sorted(tsk_shared.items()))[:10]),
    }


def main() -> int:
    result = {
        "caveat": "Gold files are model-drafted silver (provenance=model, confirmed=false); not human-verified.",
        "ner_romanized": "skipped: those spans carry no identity field, so key sharing across identities is undefined.",
        "files": {},
    }
    for path in sorted((ROOT / "data" / "gold").glob("*.jsonl")):
        result["files"][path.name] = audit(path)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for name, r in result["files"].items():
        print(f"{name}: {r['keys_shared_by_multiple_identities']}/{r['distinct_keys']} keys shared "
              f"({r['of_which_role_or_epithet_alias_types']} role-type), mentions under shared keys {r['mentions_under_shared_keys']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
