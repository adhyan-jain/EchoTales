"""Fail when the ruff or mypy error count on the product packages goes up; never demand a mass clean-up.

Why: the tree carried hundreds of ruff and over a thousand mypy findings (1,397 and 1,166 on 2026-11-13), so a plain
`ruff check` could not gate anything. A ratchet gates the direction instead: the checked-in baseline
(`scripts/maintenance/lint_baseline.json`) is the count today, a change may lower it (then run `--update` and commit the
new number) and may not raise it.

    python scripts/maintenance/lint_ratchet.py            # check both tools (what `make verify` runs)
    python scripts/maintenance/lint_ratchet.py --tool ruff
    python scripts/maintenance/lint_ratchet.py --update   # write the current counts as the new baseline

The mypy count depends on which stubs and optional packages the interpreter has (torch, scipy stubs), so the baseline
records the interpreter's mypy version and the check is skipped, loudly, if it differs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("lint_baseline.json")
RUFF_TARGETS = ["packages"]
MYPY_TARGETS = ["packages/core/src", "packages/pipeline/src"]  # the Makefile's `typecheck` targets


def parse_ruff_count(output: str) -> int:
    """`Found 549 errors.` -> 549; no such line means ruff printed `All checks passed!`."""
    m = re.search(r"Found (\d+) errors?", output)
    if m:
        return int(m.group(1))
    if "All checks passed" in output:
        return 0
    raise ValueError(f"cannot read a ruff error count from: {output[-200:]!r}")


def parse_mypy_count(output: str) -> int:
    m = re.search(r"Found (\d+) errors? in", output)
    if m:
        return int(m.group(1))
    if "Success: no issues found" in output:
        return 0
    raise ValueError(f"cannot read a mypy error count from: {output[-200:]!r}")


def regression(current: int, baseline: int) -> bool:
    return current > baseline


def _run(cmd: list[str]) -> str:
    # ruff and mypy exit 1 when they find anything; the count is what matters here
    done = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return done.stdout + done.stderr


def count_ruff() -> int:
    return parse_ruff_count(_run([sys.executable, "-m", "ruff", "check", *RUFF_TARGETS, "--output-format", "concise"]))


def count_mypy() -> int:
    return parse_mypy_count(_run([sys.executable, "-m", "mypy", *MYPY_TARGETS]))


def mypy_version() -> str:
    return _run([sys.executable, "-m", "mypy", "--version"]).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool", choices=["ruff", "mypy", "both"], default="both")
    ap.add_argument("--update", action="store_true", help="write the current counts as the new baseline")
    args = ap.parse_args(argv)

    base = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    tools = ["ruff", "mypy"] if args.tool == "both" else [args.tool]
    failed = False
    for tool in tools:
        if tool == "mypy" and not args.update and base.get("mypy_version") not in (None, mypy_version()):
            print(f"mypy: skipped, baseline was taken with {base['mypy_version']!r} and this is {mypy_version()!r}")
            continue
        current = count_ruff() if tool == "ruff" else count_mypy()
        if args.update:
            base[tool] = current
            if tool == "mypy":
                base["mypy_version"] = mypy_version()
            print(f"{tool}: baseline set to {current}")
            continue
        old = base[tool]
        if regression(current, old):
            print(f"{tool}: FAIL {current} errors, baseline {old}; fix what you added (`{tool}` output above the count)")
            failed = True
        elif current < old:
            print(f"{tool}: ok, {current} < baseline {old}; run with --update and commit the lower number")
        else:
            print(f"{tool}: ok, {current} (baseline {old})")
    if args.update:
        base["ruff_targets"], base["mypy_targets"] = RUFF_TARGETS, MYPY_TARGETS
        BASELINE.write_text(json.dumps(base, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
