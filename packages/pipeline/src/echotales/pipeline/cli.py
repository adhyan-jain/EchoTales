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
        help="extracted voice-bank root (default: data/voice)",
    )
    p_voice.add_argument(
        "--bank-kind",
        default="vctk",
        choices=["vctk", "cremad"],
        help=(
            "vctk is read speech (110 speakers, clean, lifeless); cremad is "
            "91 actors performing six emotions, which lets a shouted line be "
            "prompted with an actually angry recording"
        ),
    )
    p_voice.add_argument("--out", default="data/RI/audio")
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
    p_render.add_argument("--panel-dir", default="data/RI/panels")
    p_render.add_argument("--motion-dir", default="data/RI/motion")
    p_render.add_argument(
        "--voice-dir", default="data/RI/audio", help="must already hold `echotales voice`'s output"
    )
    p_render.add_argument("--out", default="data/RI/video")
    p_render.add_argument(
        "--image-engine", default="stub", choices=["stub", "sdxl", "manga", "illustrious", "animagine", "noobai", "refined", "gemini", "openrouter"],
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
    # **Portrait by default, at 2:3.** The output format is a 9:16 phone
    # reel, and a square panel in that frame is a small box with bars above
    # and below it. 2:3 rather than 9:16 on the *panel* is deliberate: the
    # source is then slightly wider than the frame, which is what gives a
    # horizontal pan room to travel instead of panning across empty space.
    p_render.add_argument("--width", type=int, default=832)
    p_render.add_argument("--height", type=int, default=1248)
    p_render.add_argument(
        "--video-width", type=int, default=1080,
        help="composed video frame (default 1080x1920, phone-native vertical)",
    )
    p_render.add_argument("--video-height", type=int, default=1920)
    p_render.add_argument(
        "--palette", default="colour", choices=["colour", "ink", "accent"],
        help="colour restraint, applied after generation where it cannot "
        "fail (a checkpoint ignores a prompt asking for a discipline it "
        "does not have). ink = greyscale with a contrast curve; accent = "
        "ink except where the hue is near --accent-hue, which is the "
        "single-red-robe-against-grey look most of the reference art uses",
    )
    p_render.add_argument(
        "--accent-hue", type=float, default=0.0,
        help="hue kept under --palette accent, in degrees: 0 cinnabar red "
        "(xianxia's signature), 45 gold, 140 jade green",
    )
    p_render.add_argument(
        "--no-captions", action="store_true",
        help="do not burn the spoken line on screen. The on-screen prose is "
        "the point of this format, so this is an escape hatch, not a toggle "
        "you want by default",
    )
    p_render.add_argument(
        "--speed", type=float, default=1.0,
        help="uniform playback speed on the finished video (default 1.0x). "
        "Natural narration pace produces a 15+ minute video per chapter, "
        "far longer than the reels this format is modelled on; 1.0 disables "
        "it. Applied to picture and audio together, after captions are "
        "burned, so sync is exact at any speed",
    )
    p_render.add_argument("--seed", type=int, default=20260812)
    p_render.add_argument(
        "--clips-per-chapter", type=int, default=2,
        help="hard cap on motion-clip cutaways per chapter (default: 2). "
        "A chapter gets this many or zero, never a clip inserted for its own sake",
    )
    p_render.add_argument(
        "--max-panels", type=int, default=70,
        help="panels per chapter (default: 70, roughly 60%% of a manhwa's "
        "panel density -- author instruction, HANDOFF 4.37 item 6). One "
        "per narrative beat, not per paragraph. 5x the panels is roughly "
        "5x the render wall-clock on the same GPU",
    )
    p_render.add_argument(
        "--no-director",
        action="store_true",
        help="skip the LLM art-director pass and assemble prompts mechanically",
    )
    p_render.add_argument(
        "--block-range", default=None, metavar="LO-HI",
        help="restrict panel generation to blocks LO-HI (inclusive) of every "
        "requested chapter, e.g. '0-45' for roughly the first half. Panel "
        "cost is set by --max-panels, not chapter length, so testing a "
        "whole chapter to tune a few panels wastes GPU time; use this to "
        "iterate on one portion (an opening, a confrontation) without first "
        "classifying where a 'scene' begins and ends",
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
    pe_ref.add_argument("--out", default="data/RI/references")
    pe_ref.add_argument(
        "--top", type=int, default=None,
        help="limit to the N most-mentioned eligible characters",
    )
    pe_ref.add_argument(
        "--engine", default="stub", choices=["stub", "sdxl", "manga", "illustrious", "animagine", "noobai", "refined", "gemini", "openrouter"],
        help="manga is the intended backend; stub writes placeholders",
    )
    pe_ref.add_argument("--principals-only", action="store_true")
    pe_ref.add_argument("--seed", type=int, default=20260812)

    pe_wiki = pe_sub.add_parser(
        "wiki-canon",
        help="import character appearance from the novel's fandom wiki",
    )
    pe_wiki.add_argument("--novel", required=True)
    pe_wiki.add_argument(
        "--top", type=int, default=40,
        help="limit to the N most-mentioned characters (default: 40)",
    )
    pe_wiki.add_argument(
        "--data-root", default="data",
        help="where the cached wiki canon is written",
    )
    pe_wiki.add_argument(
        "--dry-run", action="store_true",
        help="print what would be imported without writing the cache",
    )

    p_rel = sub.add_parser(
        "relevance", help="score rendered panels against the blocks they play under"
    )
    p_rel.add_argument("--novel", required=True)
    p_rel.add_argument("--manifest", default="data/RI/panels/manifest.jsonl")
    p_rel.add_argument("--worst", type=int, default=10)

    p_graph = sub.add_parser(
        "graph", help="render the knowledge graph as one self-contained HTML page"
    )
    p_graph.add_argument("--novel", required=True)
    p_graph.add_argument("--out", default="data/webview/graph.html")
    p_graph.add_argument("--top", type=int, default=60)

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
