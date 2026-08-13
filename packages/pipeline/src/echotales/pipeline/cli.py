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
        "--skip-appearance",
        action="store_true",
        help="skip Phase 7b appearance extraction (one model call per prominent "
        "entity); CI and deterministic runs want this",
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
    q_attrs = q_sub.add_parser("attributes", help="list stored attributes for an entity")
    q_attrs.add_argument("--novel", required=True)
    q_attrs.add_argument("--entity", required=True, help="entity id, bare or fully qualified")
    q_attrs.add_argument("--kind", default="PERSONA", choices=["SELF", "PERSONA"])

    p_eval = sub.add_parser("eval", help="run the evaluation harness")
    p_eval.add_argument("--novel", required=True)
    p_eval.add_argument("--report", action="store_true")

    p_voice = sub.add_parser(
        "voice", help="Phase 8: cast voices and render the script to audio"
    )
    p_voice.add_argument("--novel", required=True)
    p_voice.add_argument(
        "--bank",
        default="data/voice",
        help="extracted VCTK root (default: data/voice)",
    )
    p_voice.add_argument("--out", default="data/audio")
    p_voice.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_voice.add_argument(
        "--engine",
        default="stub",
        choices=["stub", "chatterbox"],
        help="stub writes silent WAVs of realistic duration; chatterbox needs a GPU",
    )
    p_voice.add_argument(
        "--dry-run",
        action="store_true",
        help="write the manifest and casting decisions without synthesising",
    )
    p_voice.add_argument("--seed", type=int, default=20260812)

    p_render = sub.add_parser(
        "render",
        help="Phase 9: render panel images, build the motion-clip library, "
        "and composite per-chapter videos",
    )
    p_render.add_argument("--novel", required=True)
    p_render.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_render.add_argument("--panel-dir", default="data/panels")
    p_render.add_argument("--motion-dir", default="data/motion")
    p_render.add_argument(
        "--voice-dir", default="data/audio", help="must already hold `echotales voice`'s output"
    )
    p_render.add_argument("--out", default="data/video")
    p_render.add_argument(
        "--image-engine", default="stub", choices=["stub", "sdxl", "manga", "gemini", "openrouter"],
        help="stub writes solid-colour placeholder panels; sdxl and manga need "
        "a GPU. manga is the one that produces the intended look: an "
        "anime/manga checkpoint plus IP-Adapter reference conditioning so a "
        "character keeps their face between panels",
    )
    p_render.add_argument(
        "--motion-engine", default="stub", choices=["stub", "svd"],
        help="stub writes placeholder frame sequences; svd needs a GPU",
    )
    p_render.add_argument(
        "--compose-engine", default="stub", choices=["stub", "ffmpeg"],
        help="stub concatenates real audio only (no video, no ffmpeg needed); "
        "ffmpeg produces the actual mp4s",
    )
    p_render.add_argument("--width", type=int, default=1024)
    p_render.add_argument("--height", type=int, default=1024)
    p_render.add_argument("--seed", type=int, default=20260812)
    p_render.add_argument(
        "--clips-per-chapter", type=int, default=2,
        help="hard cap on motion-clip cutaways per chapter (default: 2). "
        "A chapter gets this many or zero, never a clip inserted for its own sake",
    )
    p_render.add_argument(
        "--max-panels", type=int, default=14,
        help="panels per chapter (default: 14). One per narrative beat, not "
        "per paragraph -- fewer, better images beat a hundred near-duplicates",
    )
    p_render.add_argument(
        "--no-director",
        action="store_true",
        help="skip the LLM art-director pass and assemble prompts mechanically",
    )
    p_render.add_argument("--skip-panels", action="store_true")
    p_render.add_argument("--skip-motion", action="store_true")
    p_render.add_argument("--skip-compose", action="store_true")

    p_appearance = sub.add_parser(
        "appearance",
        help="extract physical appearance per character into PERSONA attributes "
        "(prerequisite for reference sheets and panel generation)",
    )
    p_appearance.add_argument("--novel", required=True)
    p_appearance.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_appearance.add_argument(
        "--max-chapters", type=int, default=25,
        help="how many chapters of evidence to sample per entity (default: 25)",
    )

    p_persona = sub.add_parser("persona", help="persona-level operations")
    pe_sub = p_persona.add_subparsers(dest="persona_command", required=True)
    pe_ref = pe_sub.add_parser(
        "reference", help="generate one cached reference sheet per prominent character"
    )
    pe_ref.add_argument("--novel", required=True)
    pe_ref.add_argument("--out", default="data/references")
    pe_ref.add_argument(
        "--top", type=int, default=None,
        help="limit to the N most-mentioned eligible characters",
    )
    pe_ref.add_argument(
        "--engine", default="stub", choices=["stub", "sdxl", "manga", "gemini", "openrouter"],
        help="manga is the intended backend; stub writes placeholders",
    )
    pe_ref.add_argument("--principals-only", action="store_true")
    pe_ref.add_argument("--seed", type=int, default=20260812)

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
