"""Command-line entry point.

Subcommands are wired up as each pipeline phase lands. Kept importable with no
optional dependencies installed so `--help` works on a bare checkout.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="echotales",
        description="Bitemporal narrative knowledge graphs for web-novel adaptation.",
    )
    parser.add_argument(
        "--db", default=None,
        help="path to the SQLite graph (default: data/db/<novel>.db, see pipeline/paths.py)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print each stage's report")
    parser.add_argument(
        "--seed",
        dest="global_seed",
        type=int,
        default=20260923,
        help=(
            "seed for every sampling decision that is not a render seed: "
            "bootstrap resampling in `eval`, task shuffling in `annotate`. "
            "Named `global_seed` internally so it never collides with "
            "`render --seed`, which is an image seed and a different thing."
        ),
    )
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
        "--skip-reader",
        action="store_true",
        help="skip the 6b chapter reader pass (speakers, appearance, ages, new names; ~15-60 s of local model "
        "time per chapter)",
    )
    p_run.add_argument(
        "--recover-pronoun-speakers",
        action="store_true",
        help=(
            "let Phase 5 attribute 'he said' lines through pronoun antecedents. "
            "Off by default: measured right 2 times in 15 on RI (EVOLUTION 4.88)"
        ),
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
    p_run.add_argument(
        "--force-rewipe",
        action="store_true",
        help="see `resolve --force-rewipe` -- required to re-run the whole "
        "pipeline (which re-resolves) against a canonical DB that already "
        "has resolution state.",
    )

    p_review = sub.add_parser("review", help="human-readable review of what the run produced")
    p_review.add_argument("--novel", required=True)
    p_review.add_argument("--top", type=int, default=30, help="entities to show in the console")
    p_review.add_argument("--samples", type=int, default=3, help="evidence citations per entity")
    p_review.add_argument("--out", default="data/exports/review", help="directory for HTML and JSONL")
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
    p_resolve.add_argument(
        "--title-holders-only",
        action="store_true",
        help=(
            "Skip full re-resolution; only link title mentions (\"the clan head\") "
            "to the holder the volume names, including in chapters before the "
            "name is given. Safe to run on an existing database."
        ),
    )
    p_resolve.add_argument(
        "--kinds-only",
        action="store_true",
        help=(
            "Skip full re-resolution; only backfill self_entity.kind for entities "
            "still unset, from the on-disk NER cache (EVOLUTION 4.54). Use this "
            "against an existing database instead of a full resolve rerun -- "
            "resolve_novel deletes and rebuilds self_entity from scratch, which "
            "would lose mentions.entity_label evidence that no longer exists for "
            "a novel whose mentions stage predates it."
        ),
    )
    p_resolve.add_argument(
        "--strict-kind-check",
        action="store_true",
        help=(
            "Raise instead of warn when >30%% of entities have no positive kind "
            "classification after the backfill (Section 2.2 startup assertion). "
            "Off by default because the real production RI database sits at 78%% "
            "and is HANDOFF-documented as spot-checked mostly-correct; use this "
            "on a fresh novel to catch a missing NER-cache/entity_label pipeline "
            "gap before it silently reaches voice/panel casting."
        ),
    )
    p_resolve.add_argument(
        "--capture-evidence",
        action="store_true",
        help=(
            "Write every scored (mention, candidate) evidence vector to the "
            "scoring_evidence table, so `echotales ablate` can re-score them "
            "instead of re-resolving the volume per condition. Off by default: "
            "RI alone captures tens of thousands of rows."
        ),
    )
    p_resolve.add_argument(
        "--evidence-run-tag",
        default="",
        help="label this capture so several can coexist in one database",
    )
    p_resolve.add_argument(
        "--force-rewipe",
        action="store_true",
        help=(
            "Required to resolve against a canonical DB (registered in "
            "data/canonical_dbs.json, e.g. data/db/*.db) that "
            "already has resolution state -- resolve_novel refuses to run "
            "without it (Core Pipeline Hardening #6) since it deletes and "
            "rebuilds self_entity from scratch and a canonical DB is the run "
            "of record. Not needed against a scratch/experimental --db."
        ),
    )

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
    p_eval.add_argument(
        "--gold",
        default=None,
        help=(
            "annotation file (default: data/gold/<novel>.jsonl). `cmd_eval` has "
            "read this via getattr() since it was written, but no flag ever set "
            "it, so the corpus's one alias-type-diverse file "
            "(reverend-insanity-hardcases.jsonl -- the only source of "
            "TRANSFERABLE_TITLE / EPITHET / RELATIONAL_DEICTIC records) was "
            "unreachable from the CLI, and every printed recall@k breakdown was "
            "100% RIGID_NAME by construction."
        ),
    )
    p_eval.add_argument(
        "--validate-gold",
        action="store_true",
        help=(
            "structurally validate the annotation file (colliding keys, malformed "
            "spans, impossible targets, prefix collisions) and exit without scoring"
        ),
    )

    p_faith = sub.add_parser(
        "faithfulness",
        help="check that what a reader at chapter k is shown depends only on chapters <= k (exit 1 if not)",
    )
    p_faith.add_argument("--novel", required=True)
    p_faith.add_argument(
        "--cuts",
        default=None,
        help="comma-separated chapters to cut after (default: a tenth, a quarter and half of the book)",
    )
    p_faith.add_argument(
        "--whole-volume-personas",
        action="store_true",
        help=(
            "check the legacy whole-volume persona build instead of the prefix-causal one "
            "(persona.prefix_causal); it is expected to fail, which is what the default fixes"
        ),
    )
    p_faith.add_argument("--work-dir", default=None, help="where the throwaway copies go (default: data/scratch/faithfulness/<novel>)")
    p_faith.add_argument("--out", default=None, help="also write the result as JSON here")

    p_ablate = sub.add_parser(
        "ablate",
        help="re-score the cached evidence under each ablation condition",
    )
    p_ablate.add_argument("--novel", required=True)
    p_ablate.add_argument(
        "--run-tag",
        default="",
        help="which capture to read (matches `resolve --evidence-run-tag`)",
    )
    p_ablate.add_argument(
        "--condition",
        action="append",
        default=None,
        help=(
            "run only this condition (repeatable). Default: every condition. "
            "See eval/ablate.py::CONDITIONS, and REQUIRES_RERESOLVE for the "
            "conditions that cannot honestly be answered from the cache."
        ),
    )
    p_ablate.add_argument("--link-threshold", type=float, default=0.8)
    p_ablate.add_argument(
        "--out",
        default=None,
        help=(
            "also write the rows as JSON here. Stdout-only output left the "
            "report's ablation figure citing a CSV that never existed."
        ),
    )

    p_blind = sub.add_parser(
        "annotate",
        help="write/read a BLIND annotation file (the reviewer never sees the system's answer)",
    )
    p_blind.add_argument("--novel", required=True)
    p_blind.add_argument(
        "--tasks", required=True, help="JSONL path: written by --emit, read back otherwise"
    )
    p_blind.add_argument(
        "--emit", action="store_true", help="write tasks instead of reading answers"
    )
    p_blind.add_argument("--chapters", default=None, help="range, e.g. 1-5")
    p_blind.add_argument(
        "--sample",
        type=int,
        default=0,
        help=(
            "cap the task count. Applied AFTER shuffling, so a subset is a "
            "random sample of the volume rather than its first N mentions -- "
            "early chapters are the easy case and annotating only those would "
            "overstate agreement."
        ),
    )
    p_blind.add_argument("--seed", type=int, default=20260923)
    p_blind.add_argument(
        "--confirmed-by",
        default="",
        help="required when reading answers back: the person who adjudicated",
    )
    p_blind.add_argument("--out", default=None, help="gold JSONL to write when reading back")

    p_obs = sub.add_parser(
        "observations",
        help="record who witnessed each reveal, populating the observer axis",
    )
    p_obs.add_argument("--novel", required=True)
    p_obs.add_argument(
        "--include-revealed-self",
        action="store_true",
        help=(
            "also record the revealed character as having learned their own "
            "identity at the reveal. Off by default: they already knew, and "
            "dating their self-knowledge to when someone *else* found out is "
            "the Self-vs-Persona confusion non-negotiable #3 exists to prevent."
        ),
    )

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
        choices=["vctk", "cremad", "ears"],
        help=(
            "vctk is read speech (110 speakers, clean, lifeless); cremad is "
            "91 actors performing six emotions, which lets a shouted line be "
            "prompted with an actually angry recording"
        ),
    )
    p_voice.add_argument("--out", default=None, help="default: data/novels/<CODE>/audio")
    p_voice.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_voice.add_argument(
        "--m4b", action="store_true",
        help="also write <out>/<novel>.m4b: every chapter track, loudness-normalised, with chapter markers",
    )
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
    p_voice.add_argument(
        "--min-character-confidence", type=float, default=0.7,
        help="attribution confidence below which a line is not voiced as the named character "
             "(0 restores the old behaviour)",
    )

    p_render = sub.add_parser(
        "render",
        help="Phase 9: render panel images, build the motion-clip library, "
        "and composite per-chapter videos",
    )
    p_render.add_argument("--novel", required=True)
    p_render.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_render.add_argument("--panel-dir", default=None, help="default: data/novels/<CODE>/panels")
    p_render.add_argument("--motion-dir", default=None, help="default: data/novels/<CODE>/motion")
    p_render.add_argument(
        "--voice-dir", default=None,
        help="must already hold `echotales voice`'s output (default: data/novels/<CODE>/audio)"
    )
    p_render.add_argument("--out", default=None, help="default: data/novels/<CODE>/video")
    p_render.add_argument(
        "--image-engine", default=None, choices=["stub", "sdxl", "manga", "illustrious", "noobai", "refined", "gemini", "openrouter", "runpod"],
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
        "--observer",
        default="READER",
        help=(
            "whose knowledge the panels depict. READER (default) is the "
            "omniscient-to-the-page view every render before 2026-09-23 "
            "produced; a character's entity id renders the scene as that "
            "character believes it, so a concealed identity they never "
            "witnessed is not drawn under its true name. Populate the axis "
            "first with `echotales observations --novel <id>`."
        ),
    )
    p_render.add_argument(
        "--clips-per-chapter", type=int, default=2,
        help="hard cap on motion-clip cutaways per chapter (default: 2). "
        "A chapter gets this many or zero, never a clip inserted for its own sake",
    )
    p_render.add_argument(
        "--version-suffix", default="",
        help="short descriptive name appended to the version directory (v4 -> v4_<suffix>). The convention is to name "
        "every version; `next_version` cannot, so this is how a CLI render gets one",
    )
    p_render.add_argument(
        "--max-panels", type=int, default=None,
        help="scenes per chapter, each drawn with one to three images (10 scenes made 33 images on LotM ch1). "
        "Default: the tier's -- 70 for a full chapter (HANDOFF 4.37 item 6) and 3 for a preview, which is what "
        "ECHOTALES_COMPUTE=local-low renders unless told otherwise. 5x the scenes is roughly 5x the wall-clock",
    )
    p_render.add_argument(
        "--tier", choices=["preview", "full"], default=None,
        help="preview (a handful of panels) or full (the whole chapter); default follows ECHOTALES_COMPUTE",
    )
    p_render.add_argument(
        "--ignore-resource-guard", action="store_true",
        help="render even if the memory, GPU or credentials check refuses (ECHOTALES_COMPUTE, pipeline/compute.py)",
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

    p_reader = sub.add_parser(
        "reader",
        help="chapter reader pass: a model shown the cast names the speaker of every quoted line "
        "(decisions D11); run after speakers, before personas",
    )
    p_reader.add_argument("--novel", required=True)
    p_reader.add_argument("--chapters", help="range, e.g. 1-5; default: all")
    p_reader.add_argument(
        "--passes", default=None,
        help="comma-separated subset of speakers,facts,delivery (default: all three); delivery alone labels line "
        "emotions on a book already read without re-running speaker attribution",
    )

    p_persona = sub.add_parser("persona", help="persona-level operations")
    pe_sub = p_persona.add_subparsers(dest="persona_command", required=True)
    pe_ref = pe_sub.add_parser(
        "reference", help="generate one cached reference sheet per prominent character"
    )
    pe_ref.add_argument("--novel", required=True)
    pe_ref.add_argument("--out", default=None, help="default: data/novels/<CODE>/references")
    pe_ref.add_argument(
        "--top", type=int, default=None,
        help="limit to the N most-mentioned eligible characters",
    )
    pe_ref.add_argument(
        "--engine", default="stub", choices=["stub", "sdxl", "manga", "illustrious", "noobai", "refined", "gemini", "openrouter"],
        help="manga is the intended backend; stub writes placeholders",
    )
    pe_ref.add_argument("--principals-only", action="store_true")
    pe_ref.add_argument("--seed", type=int, default=20260812)
    pe_ref.add_argument(
        "--reference-transition-mode", default="txt2img", choices=["txt2img", "img2img"],
        help="experimental, opt-in only (default: txt2img, unchanged behaviour). "
        "img2img generates a split character's second-and-later body as an "
        "img2img transform of the previous body's own reference image, "
        "instead of an independent txt2img draw -- see "
        "persona/reference_gen.py::generate_references docstring",
    )

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

    # refimg: opt-in reference-image candidate search/review. Backend-only --
    # see persona/refimg.py module docstring. Nothing here auto-conditions
    # generation; "select"/"register" only update the candidate table and
    # its selection log.
    pe_search = pe_sub.add_parser(
        "refimg-search",
        help="search for reference-image candidates for prominent characters "
        "(does not select or apply anything -- review queue only)",
    )
    pe_search.add_argument("--novel", required=True)
    pe_search.add_argument("--title", help="novel title used in the search query; "
        "defaults to the novel row's stored title")
    pe_search.add_argument("--character", action="append", dest="characters",
        help="self id to search (repeatable); default: every PRINCIPAL/RECURRING character")
    pe_search.add_argument("--max-results", type=int, default=5)

    pe_list = pe_sub.add_parser(
        "refimg-list", help="list stored reference-image candidates for a character"
    )
    pe_list.add_argument("--novel", required=True)
    pe_list.add_argument("--character", required=True, help="self id")

    pe_select = pe_sub.add_parser(
        "refimg-select",
        help="mark one already-found candidate as selected (user override, "
        "logged; does not touch generation)",
    )
    pe_select.add_argument("--novel", required=True)
    pe_select.add_argument("--character", required=True, help="self id")
    pe_select.add_argument("--candidate", required=True, help="candidate id from refimg-list")
    pe_select.add_argument("--actor", default="user")
    pe_select.add_argument("--note", default="")

    pe_register = pe_sub.add_parser(
        "refimg-register",
        help="register a user-supplied local image as the reference for a "
        "character (selected immediately; does not touch generation)",
    )
    pe_register.add_argument("--novel", required=True)
    pe_register.add_argument("--character", required=True, help="self id")
    pe_register.add_argument("--path", required=True, help="local image path")
    pe_register.add_argument("--actor", default="user")
    pe_register.add_argument("--note", default="")

    pe_sheets = pe_sub.add_parser(
        "refimg-sheets",
        help="list reference sheets for a character or the entire novel with approval status",
    )
    pe_sheets.add_argument("--novel", required=True)
    pe_sheets.add_argument("--character", help="optional self id")
    pe_sheets.add_argument("--persona", help="optional persona id")

    pe_approve = pe_sub.add_parser(
        "refimg-approve",
        help="approve a reference sheet candidate to condition generation",
    )
    pe_approve.add_argument("--novel", required=True)
    pe_approve.add_argument("--character", required=True, help="self id")
    pe_approve.add_argument("--candidate", required=True, help="candidate id from refimg-sheets")
    pe_approve.add_argument("--actor", default="user")
    pe_approve.add_argument("--note", default="")

    pe_reject = pe_sub.add_parser(
        "refimg-reject",
        help="reject (revoke approval of) a reference sheet candidate",
    )
    pe_reject.add_argument("--novel", required=True)
    pe_reject.add_argument("--character", required=True, help="self id")
    pe_reject.add_argument("--candidate", required=True, help="candidate id from refimg-sheets")
    pe_reject.add_argument("--actor", default="user")
    pe_reject.add_argument("--note", default="")

    p_rel = sub.add_parser(
        "relevance", help="score rendered panels against the blocks they play under"
    )
    p_rel.add_argument("--novel", required=True)
    p_rel.add_argument("--manifest", default=None, help="default: data/novels/<CODE>/panels/manifest.jsonl")
    p_rel.add_argument("--worst", type=int, default=10)

    p_graph = sub.add_parser(
        "graph", help="render the knowledge graph as one self-contained HTML page"
    )
    p_graph.add_argument("--novel", required=True)
    p_graph.add_argument("--out", default="data/exports/webview/graph.html")
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
    p_webview.add_argument("--out", default="data/exports/webview")
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
    p_webserver.add_argument(
        "--static-dir",
        default=None,
        help="also serve a built frontend (webview/build) from this server, with SPA fallback",
    )
    p_webserver.add_argument(
        "--corrections-dir",
        default="data/corrections",
        help="where correction logs are written; point at a scratch dir for QA runs",
    )

    return parser


#: `(command, attribute) -> asset kind` for outputs that belong to one novel.
_PER_NOVEL_OUTPUTS = {
    ("voice", "out"): "audio",
    ("render", "panel_dir"): "panels",
    ("render", "motion_dir"): "motion",
    ("render", "voice_dir"): "audio",
    ("render", "out"): "video",
    ("persona", "out"): "references",
}


def _fill_path_defaults(args: argparse.Namespace) -> None:
    """Resolve path defaults from the novel, via `pipeline/paths.py`.

    Defaults used to be literals, several hard-coded to `data/RI/...`, so
    `echotales voice --novel lord-of-the-mysteries` wrote into Reverend
    Insanity's audio folder unless `--out` was given (docs/EVOLUTION.md 4.94).
    """
    from echotales.pipeline import paths

    novel = getattr(args, "novel", None)
    if args.db is None:
        args.db = str(paths.db_path(novel))
    for (command, attr), kind in _PER_NOVEL_OUTPUTS.items():
        if args.command == command and getattr(args, attr, "") is None and novel:
            setattr(args, attr, str(paths.asset_dir(novel, kind)))
    if args.command == "relevance" and args.manifest is None:
        args.manifest = str(paths.asset_dir(novel, "panels") / "manifest.jsonl")


def main(argv: Sequence[str] | None = None) -> int:
    # Lower scheduling priority so a long pipeline run (mention detection,
    # CPU-offloaded SDXL passes -- render/panels.py's SDXLEngine deliberately
    # shuttles most of the model to CPU because the 8GB card OOMs otherwise)
    # yields to whatever else is running on the same machine, rather than
    # competing with it. os.nice() only ever raises niceness here (lowers
    # priority), which needs no privileges and never fails for a positive
    # delta. GPU work itself is unaffected -- this only affects CPU
    # scheduling, and Ollama/diffusers already put what they can on the GPU.
    with contextlib.suppress(OSError):
        os.nice(10)

    parser = build_parser()
    args = parser.parse_args(argv)
    _fill_path_defaults(args)

    from echotales.pipeline.commands import dispatch

    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
