"""Command-line entry point.

Subcommands are wired up as each pipeline phase lands. Kept importable with no
optional dependencies installed so `--help` works on a bare checkout.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="echotales",
        description="Bitemporal narrative knowledge graphs for web-novel adaptation.",
    )
    parser.add_argument("--db", default="data/echotales.db", help="path to the SQLite graph")
    parser.add_argument("-v", "--verbose", action="store_true", help="print each stage's report")
    sub = parser.add_subparsers(dest="command", required=True)

    # The verb most people want: every phase, in dependency order.
    p_run = sub.add_parser("run", help="run the whole pipeline end to end")
    p_run.add_argument("--novel", required=True)
    p_run.add_argument("--chapters", default=None, help="range, e.g. 1-199 (default: sources.toml)")
    p_run.add_argument("--sources", default="data/sources.toml")
    p_run.add_argument(
        "--no-llm",
        action="store_true",
        help="force the deterministic path even when a model backend is configured",
    )
    p_run.add_argument(
        "--llm-attribution-chapters",
        type=float,
        default=3.0,
        help=(
            "run tier-4 LLM speaker attribution on chapters up to and including this "
            "number, where the deterministic tiers have no established context yet "
            "(default: 3; 0 disables tier 4 entirely)"
        ),
    )

    p_review = sub.add_parser("review", help="human-readable review of what the run produced")
    p_review.add_argument("--novel", required=True)
    p_review.add_argument("--top", type=int, default=30, help="entities to show in the console")
    p_review.add_argument("--samples", type=int, default=3, help="evidence citations per entity")
    p_review.add_argument("--out", default="data/review", help="directory for HTML and JSONL")
    p_review.add_argument("--no-files", action="store_true", help="console output only")
    p_review.add_argument(
        "--script",
        default=None,
        help="chapter range for the line-by-line speaker/reference view, e.g. 1-5",
    )

    p_ingest = sub.add_parser("ingest", help="Phase 0: parse a source into chapters and blocks")
    p_ingest.add_argument("--novel", required=True)
    p_ingest.add_argument("--chapters", default=None, help="range, e.g. 1-199")
    p_ingest.add_argument("--sources", default="data/sources.toml")

    p_resolve = sub.add_parser("resolve", help="Phases 1-6: spans, mentions, identity resolution")
    p_resolve.add_argument("--novel", required=True)
    p_resolve.add_argument("--chapters", default=None)

    p_query = sub.add_parser("query", help="query the graph")
    q_sub = p_query.add_subparsers(dest="query_command", required=True)
    q_state = q_sub.add_parser("state-of", help="resolve an entity's state at a position")
    q_state.add_argument("--novel", required=True)
    q_state.add_argument("--target", required=True)
    q_state.add_argument("--chapter", type=float, required=True)
    q_state.add_argument("--observer", default="READER")
    q_state.add_argument("--timeline", default="MAIN_TIMELINE")
    q_state.add_argument("--kind", default="SELF", choices=["SELF", "PERSONA"])

    p_eval = sub.add_parser("eval", help="run the evaluation harness")
    p_eval.add_argument("--novel", required=True)
    p_eval.add_argument("--report", action="store_true")

    p_export = sub.add_parser("export", help="emit the annotation dataset")
    p_export.add_argument("--novel", required=True)
    p_export.add_argument("--out", default="data/gold")
    p_export.add_argument("--samples", type=int, default=3)

    p_webview = sub.add_parser(
        "webview", help="build the browsable coref/attribution viewer across novels"
    )
    p_webview.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="DB_PATH:NOVEL_ID[:LABEL]",
        help="one novel's data; repeat for each novel shown in the viewer",
    )
    p_webview.add_argument("--out", default="data/webview")
    p_webview.add_argument(
        "--format",
        choices=["static", "react"],
        default="static",
        help="static: standalone HTML, open with file:// directly. "
        "react: JSON only, for webview/public/data (needs `npm start` or a served build)",
    )

    p_webserver = sub.add_parser(
        "webview-server",
        help="backend for the interactive (React) viewer -- corrections, live payload",
    )
    p_webserver.add_argument(
        "--source",
        action="append",
        required=True,
        metavar="DB_PATH:NOVEL_ID[:LABEL]",
        help="one novel's data; repeat for each novel the backend serves",
    )
    p_webserver.add_argument("--host", default="127.0.0.1")
    p_webserver.add_argument("--port", type=int, default=8787)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from echotales.pipeline.commands import dispatch

    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
