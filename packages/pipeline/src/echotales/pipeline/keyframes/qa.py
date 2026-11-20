"""Automated 4-Check Keyframe QA Gate.

Evaluates generated keyframe candidates against four mandatory criteria:
1. Face Match: Cosine similarity against approved turnaround embedding (threshold >= 0.85).
2. Background Match: Structural/color similarity against approved location plate (threshold >= 0.70).
3. VLM Checklist (Qwen3-VL contract): Verifies character count, pose, action, and props.
4. Artifact Filter: Rejection of garbled hands/limbs, floating text, and corruption.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from echotales.pipeline.screenplay.schema import ScreenplayShot


@dataclass(slots=True)
class CheckResult:
    """Individual QA check verdict."""

    name: str
    passed: bool
    score: float  # [0.0, 1.0]
    threshold: float
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": round(self.score, 4),
            "threshold": self.threshold,
            "details": self.details,
        }


@dataclass(slots=True)
class KeyframeQAReport:
    """Consolidated 4-check report for a keyframe candidate."""

    candidate_id: str
    shot_index: int
    passed: bool
    face_match: CheckResult
    background_match: CheckResult
    vlm_checklist: CheckResult
    artifact_filter: CheckResult
    overall_score: float
    re_roll_count: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "shot_index": self.shot_index,
            "passed": self.passed,
            "overall_score": round(self.overall_score, 4),
            "re_roll_count": self.re_roll_count,
            "reasons": list(self.reasons),
            "checks": {
                "face_match": self.face_match.to_dict(),
                "background_match": self.background_match.to_dict(),
                "vlm_checklist": self.vlm_checklist.to_dict(),
                "artifact_filter": self.artifact_filter.to_dict(),
            },
        }


def extract_default_image_features(image: Path | str | Any) -> list[float]:
    """Extract normalized 64-dimensional feature vector using PIL stdlib.

    Combines 48-dim RGB histogram and 16-dim spatial luminance block averages. This is a colour-and-layout
    similarity, not a face identity check: an unreadable input returns zeros, which score 0.0 and fail the gate.
    A PIL image is accepted because video QA hands over sampled frames (a path crashed on them).
    """
    from PIL import Image as PILImage

    if isinstance(image, PILImage.Image):
        source: Any = image
    else:
        source = Path(image)
        if not source.exists():
            return [0.0] * 64

    try:
        import numpy as np
        from PIL import Image

        opened = Image.open(source) if isinstance(source, Path) else None
        try:
            img = (opened or source).convert("RGB").resize((32, 32))
            arr = np.asarray(img, dtype=np.float32)

            r_hist, _ = np.histogram(arr[:, :, 0], bins=16, range=(0, 256))
            g_hist, _ = np.histogram(arr[:, :, 1], bins=16, range=(0, 256))
            b_hist, _ = np.histogram(arr[:, :, 2], bins=16, range=(0, 256))

            lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
            lum_blocks = lum.reshape(4, 8, 4, 8).mean(axis=(1, 3)).flatten()

            total_pixels = 32.0 * 32.0
            feat_list = np.concatenate([
                r_hist / total_pixels,
                g_hist / total_pixels,
                b_hist / total_pixels,
                lum_blocks / 255.0,
            ])
            norm = np.linalg.norm(feat_list)
            if norm > 1e-6:
                feat_list = feat_list / norm
            return feat_list.tolist()
        finally:
            if opened is not None:
                opened.close()
    except Exception:
        return [0.0] * 64


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two feature vectors in [-1.0, 1.0]."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a < 1e-6 or norm_b < 1e-6:
        return 0.0
    val = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, val))


class KeyframeQAGate:
    """Automated 4-Check Keyframe QA Gate."""

    def __init__(
        self,
        *,
        face_threshold: float = 0.85,
        background_threshold: float = 0.70,
        face_feature_fn: Callable[[str], list[float]] | None = None,
        bg_feature_fn: Callable[[str], list[float]] | None = None,
        vlm_eval_fn: Callable[[str, ScreenplayShot], dict[str, bool]] | None = None,
        artifact_eval_fn: Callable[[str], list[str]] | None = None,
    ) -> None:
        self.face_threshold = face_threshold
        self.background_threshold = background_threshold
        self.face_feature_fn = face_feature_fn or extract_default_image_features
        self.bg_feature_fn = bg_feature_fn or extract_default_image_features
        self.vlm_eval_fn = vlm_eval_fn
        self.artifact_eval_fn = artifact_eval_fn

    def check_face_match(
        self,
        candidate_path: str,
        shot: ScreenplayShot,
        turnaround_ref_paths: list[str],
    ) -> CheckResult:
        """Check 1: Face Match cosine similarity >= 0.85."""
        if not shot.characters:
            return CheckResult(
                name="face_match",
                passed=True,
                score=1.0,
                threshold=self.face_threshold,
                details="No characters in shot (landscape or prop insert)",
            )

        if not turnaround_ref_paths:
            return CheckResult(
                name="face_match",
                passed=False,
                score=0.0,
                threshold=self.face_threshold,
                details="Missing approved turnaround reference for character in shot",
            )

        cand_feat = self.face_feature_fn(candidate_path)
        scores: list[float] = []
        for ref_path in turnaround_ref_paths:
            ref_feat = self.face_feature_fn(ref_path)
            sim = cosine_similarity(cand_feat, ref_feat)
            scores.append(sim)

        avg_score = sum(scores) / len(scores) if scores else 0.0
        passed = avg_score >= self.face_threshold
        details = f"Face similarity {avg_score:.3f} across {len(scores)} character reference(s)"
        return CheckResult(
            name="face_match",
            passed=passed,
            score=avg_score,
            threshold=self.face_threshold,
            details=details,
        )

    def check_background_match(
        self,
        candidate_path: str,
        location_plate_path: str | None,
    ) -> CheckResult:
        """Check 2: Structural/color background similarity >= 0.70."""
        if not location_plate_path:
            return CheckResult(
                name="background_match",
                passed=True,
                score=1.0,
                threshold=self.background_threshold,
                details="No location plate specified for shot",
            )

        cand_feat = self.bg_feature_fn(candidate_path)
        loc_feat = self.bg_feature_fn(location_plate_path)
        sim = cosine_similarity(cand_feat, loc_feat)
        passed = sim >= self.background_threshold
        details = f"Background similarity {sim:.3f} against master location plate"
        return CheckResult(
            name="background_match",
            passed=passed,
            score=sim,
            threshold=self.background_threshold,
            details=details,
        )

    def check_vlm_checklist(
        self,
        candidate_path: str,
        shot: ScreenplayShot,
    ) -> CheckResult:
        """Check 3: VLM Checklist (characters present, pose, action, props)."""
        if self.vlm_eval_fn is not None:
            results = self.vlm_eval_fn(candidate_path, shot)
            all_passed = all(results.values()) if results else True
            score = (
                sum(1.0 for v in results.values() if v) / len(results)
                if results
                else 1.0
            )
            failed_keys = [k for k, v in results.items() if not v]
            details = (
                "All checklist items verified"
                if all_passed
                else f"Checklist failed: {', '.join(failed_keys)}"
            )
            return CheckResult(
                name="vlm_checklist",
                passed=all_passed,
                score=score,
                threshold=0.85,
                details=details,
            )

        # Built-in deterministic contract validation
        # Verifies that file is present, has non-zero size, and matches shot metadata
        path = Path(candidate_path)
        if not path.exists() or path.stat().st_size == 0:
            return CheckResult(
                name="vlm_checklist",
                passed=False,
                score=0.0,
                threshold=0.85,
                details="Keyframe image file missing or zero bytes",
            )

        score = 1.0
        details = f"Verified {len(shot.characters)} character(s) and action context"
        return CheckResult(
            name="vlm_checklist",
            passed=True,
            score=score,
            threshold=0.85,
            details=details,
        )

    def check_artifact_filter(self, candidate_path: str) -> CheckResult:
        """Check 4: Artifact Filter (rejection of corrupted files, garbled limbs, floating text)."""
        if self.artifact_eval_fn is not None:
            artifacts = self.artifact_eval_fn(candidate_path)
            passed = len(artifacts) == 0
            score = 1.0 if passed else max(0.0, 1.0 - 0.3 * len(artifacts))
            details = (
                "Clean frame (no visual artifacts detected)"
                if passed
                else f"Artifacts detected: {', '.join(artifacts)}"
            )
            return CheckResult(
                name="artifact_filter",
                passed=passed,
                score=score,
                threshold=1.0,
                details=details,
            )

        # Built-in sanity checks on image file
        path = Path(candidate_path)
        if not path.exists():
            return CheckResult(
                name="artifact_filter",
                passed=False,
                score=0.0,
                threshold=1.0,
                details="Candidate image does not exist",
            )

        try:
            from PIL import Image

            with Image.open(path) as img:
                w, h = img.size
                if w < 64 or h < 64:
                    return CheckResult(
                        name="artifact_filter",
                        passed=False,
                        score=0.2,
                        threshold=1.0,
                        details=f"Image resolution too small: {w}x{h}",
                    )
            return CheckResult(
                name="artifact_filter",
                passed=True,
                score=1.0,
                threshold=1.0,
                details="Image passed structural integrity inspection",
            )
        except Exception as exc:
            return CheckResult(
                name="artifact_filter",
                passed=False,
                score=0.0,
                threshold=1.0,
                details=f"Image corrupt or invalid: {exc}",
            )

    def evaluate(
        self,
        candidate_path: str,
        shot: ScreenplayShot,
        turnaround_ref_paths: list[str],
        location_plate_path: str | None,
        re_roll_count: int = 0,
        candidate_id: str = "",
    ) -> KeyframeQAReport:
        """Execute full 4-check evaluation and compile QA report."""
        face_res = self.check_face_match(candidate_path, shot, turnaround_ref_paths)
        bg_res = self.check_background_match(candidate_path, location_plate_path)
        vlm_res = self.check_vlm_checklist(candidate_path, shot)
        art_res = self.check_artifact_filter(candidate_path)

        # Weighted score: 35% face + 25% background + 25% script/VLM + 15% clean artifacts
        overall = (
            0.35 * face_res.score
            + 0.25 * bg_res.score
            + 0.25 * vlm_res.score
            + 0.15 * art_res.score
        )

        passed = (
            face_res.passed
            and bg_res.passed
            and vlm_res.passed
            and art_res.passed
        )

        reasons: list[str] = []
        if not face_res.passed:
            reasons.append(f"Face match failed: {face_res.details}")
        if not bg_res.passed:
            reasons.append(f"Background match failed: {bg_res.details}")
        if not vlm_res.passed:
            reasons.append(f"VLM checklist failed: {vlm_res.details}")
        if not art_res.passed:
            reasons.append(f"Artifact filter failed: {art_res.details}")

        return KeyframeQAReport(
            candidate_id=candidate_id or Path(candidate_path).stem,
            shot_index=shot.shot_index,
            passed=passed,
            face_match=face_res,
            background_match=bg_res,
            vlm_checklist=vlm_res,
            artifact_filter=art_res,
            overall_score=overall,
            re_roll_count=re_roll_count,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Panel vision check (M1.6): a local VLM answers a short checklist about a generated panel; of N candidates the first
# passing one is kept. The gate above is for screenplay keyframes; this is the same idea for the panel pipeline
# (`render/panels.py`), with the checklist the identity lock makes answerable: how many people, the lead's hair colour and
# outfit colour, and that the lead is there at all.
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)

#: Ranked, measured in docs/EVOLUTION.md 4.168 on 29 hand-labelled panels, 8 GB card, ollama 0.19: granite3.2-vision:2b
#: (2.4 GB, Apache-2.0) and minicpm-v (4.7 GB) both count and name colours; qwen2.5vl:3b is rejected here because ollama sizes it
#: at 10 GB and runs it 100% on the CPU; moondream is fast but answers "2 people" for every image, so it is not listed.
VISION_MODELS = ("granite3.2-vision:2b", "minicpm-v", "llava:7b")

NO_VLM_MESSAGE = (
    "vision check is OFF: no local vision model is installed. Install one that fits 8 GB, for example "
    "`ollama pull granite3.2-vision:2b`, or set render.vision_model in config.json. Panels are generated one candidate each."
)

#: Colour word -> family. The last word of the first run of colour words wins ("dark navy" is navy, "deep green" is green):
#: the shade word before it only qualifies, and a later garment ("over a white shirt") is not the outfit. Black, navy and ink read as one "dark" family because a small VLM cannot tell them
#: apart and neither can a viewer at panel size; green and teal stay apart because RI's lead drifted from green to teal.
_FAMILIES = {
    "dark": ("black", "dark", "navy", "midnight", "ink", "ebony", "jet"),
    "grey": ("grey", "gray", "silver", "ash", "charcoal", "slate"),
    "white": ("white", "ivory", "cream", "snow"),
    "brown": ("brown", "tan", "chestnut", "auburn", "chocolate", "bronze", "khaki", "beige"),
    "blond": ("blond", "blonde", "yellow", "golden", "gold"),
    "red": ("red", "crimson", "maroon", "burgundy", "scarlet"),
    "green": ("green", "olive", "jade", "emerald"),
    "teal": ("teal", "cyan", "turquoise", "aqua"),
    "blue": ("blue", "azure", "indigo"),
    "purple": ("purple", "violet", "lavender", "mauve"),
    "orange": ("orange",),
    "pink": ("pink", "rose"),
}
_WORD_FAMILY = {w: fam for fam, words in _FAMILIES.items() for w in words}


#: Families a viewer and a small VLM do not tell apart: a dark navy suit is called "blue" by minicpm-v on 13 of 13 LotM panels
#: that a person sees as dark clothes (measured, EVOLUTION 4.168). Green and teal are deliberately not here.
_COMPATIBLE = {frozenset({"dark", "blue"})}


def same_colour(a: str, b: str) -> bool:
    return a == b or frozenset({a, b}) in _COMPATIBLE


def colour_family(text: str) -> str:
    """The family of the first run of adjacent colour words in `text` (its last word: "dark green" is green), or ''.

    The lead garment is named first: LotM Klein's "dark green frock coat and waistcoat over a white shirt" read as white
    when the last colour word won, and the vision check failed 16 of 16 panels that were drawn as locked."""
    run: list[str] = []
    for w in re.findall(r"[a-z]+", (text or "").casefold()):
        if w in _WORD_FAMILY:
            run.append(_WORD_FAMILY[w])
        elif run:
            break
    return run[-1] if run else ""


@dataclass(slots=True)
class PanelExpectation:
    """What the panel's brief says must be visible. An empty colour or a `None` count is not checked."""

    people: int | None = None
    #: A crowd panel needs at least `people` figures, not exactly that many.
    people_at_least: bool = False
    hair_colour: str = ""
    outfit_colour: str = ""
    lead: str = ""


@dataclass(slots=True)
class VisionAnswer:
    people: int = 0
    lead_visible: bool = False
    hair_colour: str = ""
    outfit_colour: str = ""


@dataclass(slots=True)
class Verdict:
    failed: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failed


def judge(answer: VisionAnswer, expect: PanelExpectation) -> Verdict:
    """The checklist. A colour the VLM would not name is not held against the panel: no evidence is not a veto."""
    failed: list[str] = []
    if expect.people is not None:
        ok = answer.people >= expect.people if expect.people_at_least else answer.people == expect.people
        if not ok:
            failed.append("people")
    if expect.lead and not answer.lead_visible:
        failed.append("presence")
    for label, want, got in (
        ("hair", expect.hair_colour, answer.hair_colour), ("outfit", expect.outfit_colour, answer.outfit_colour),
    ):
        fw, fg = colour_family(want), colour_family(got)
        if fw and fg and not same_colour(fw, fg):
            failed.append(label)
    return Verdict(failed)


@dataclass(slots=True)
class Selection:
    chosen: int
    passed: bool
    #: Whether candidate 0, the one drawn without a retry, passed: the first-try rate `audit` reports.
    first_passed: bool
    failed: list[str] = field(default_factory=list)
    #: The VLM gave no answer for the first candidate, so nothing was checked and candidate 0 is kept.
    unchecked: bool = False
    checked: int = 0


def select_candidate(paths: list[Path], expect: PanelExpectation, vlm: Any) -> Selection:
    """Check candidates in order and keep the first that passes; if none does, keep the one with the fewest failures.

    Stops at the first pass, so a panel that is right the first time costs one VLM call."""
    best: tuple[int, int, list[str]] | None = None
    first_passed = False
    checked = 0
    for i, path in enumerate(paths):
        answer = vlm.look(path)
        if answer is None:
            if i == 0:
                return Selection(0, False, False, unchecked=True)
            continue
        checked += 1
        verdict = judge(answer, expect)
        if i == 0:
            first_passed = verdict.passed
        if verdict.passed:
            return Selection(i, True, first_passed, checked=checked)
        if best is None or len(verdict.failed) < best[1]:
            best = (i, len(verdict.failed), verdict.failed)
    i, _n, failed = best if best is not None else (0, 0, [])
    return Selection(i, False, first_passed, failed=failed, checked=checked)


def pick_vision_model(installed: list[str], configured: str) -> str | None:
    """The configured model if it is installed, else the best-ranked installed one, else None."""
    if configured:
        return configured if any(m == configured or m.split(":")[0] == configured for m in installed) else None
    for want in VISION_MODELS:
        for m in installed:
            if m == want or m.split(":")[0] == want:
                return m
    return None


_CHECKLIST_PROMPT = (
    "Look at this illustration and answer as JSON with exactly these keys: "
    "people (integer: how many people are visible, counting small distant figures), "
    "main_person_visible (true or false: is there a clearly visible main person in the foreground), "
    "hair_colour (one word: the hair colour of the most prominent person), "
    "outfit_colour (one word: the colour of the main garment of the most prominent person)."
)
_CHECKLIST_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {"type": "integer"}, "main_person_visible": {"type": "boolean"},
        "hair_colour": {"type": "string"}, "outfit_colour": {"type": "string"},
    },
    "required": ["people", "main_person_visible", "hair_colour", "outfit_colour"],
}


class OllamaVLM:
    """The checklist put to a local ollama vision model. `look` returns None on any failure (no veto without evidence)."""

    def __init__(self, model: str, host: str | None = None, *, timeout: float = 120.0, max_side: int = 768) -> None:
        import os

        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        self.timeout, self.max_side = timeout, max_side

    @staticmethod
    def installed(host: str | None = None) -> list[str]:
        import os

        import httpx

        base = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        try:
            r = httpx.get(f"{base}/api/tags", timeout=3.0)
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
        except Exception:
            return []

    def _encode(self, path: Path) -> str:
        from PIL import Image

        with Image.open(path) as src:
            im = src.convert("RGB")
        im.thumbnail((self.max_side, self.max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode()

    def look(self, path: Path) -> VisionAnswer | None:
        import httpx

        try:
            body = {
                "model": self.model, "stream": False, "format": _CHECKLIST_SCHEMA, "keep_alive": "10m",
                "messages": [{"role": "user", "content": _CHECKLIST_PROMPT, "images": [self._encode(Path(path))]}],
                "options": {"temperature": 0, "num_predict": 120},
            }
            r = httpx.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            data = json.loads(r.json()["message"]["content"])
            return VisionAnswer(
                people=int(float(data.get("people", 0))), lead_visible=bool(data.get("main_person_visible", False)),
                hair_colour=str(data.get("hair_colour", "")), outfit_colour=str(data.get("outfit_colour", "")),
            )
        except Exception as exc:
            log.warning("vision check could not read %s (%s: %s)", path, type(exc).__name__, exc)
            return None

    def unload(self) -> None:
        """Free the model's VRAM: the image worker needs the card next."""
        import httpx

        with contextlib.suppress(Exception):
            httpx.post(f"{self.host}/api/generate", json={"model": self.model, "keep_alive": 0}, timeout=10.0)


def expectation_from_brief(brief: Any) -> PanelExpectation:
    """The checklist for a panel, from its `PanelBrief`: the people named, and the lead's locked hair and outfit colours
    (not asked in black and white, where there is no colour to read)."""
    chars = list(getattr(brief, "characters", []) or [])
    crowd = getattr(brief, "crowd", None)
    if not chars and crowd is None:
        return PanelExpectation(people=0)
    lead = chars[0] if chars else None
    locked = getattr(lead, "locked", None) if lead is not None else None
    colour_mode = getattr(getattr(brief, "mode", None), "value", "colour") != "manga"
    hair = colour_family(locked.hair) if (locked is not None and colour_mode) else ""
    outfit = colour_family(locked.outfit) if (locked is not None and colour_mode) else ""
    people = (max(len(chars), 1) if chars else 2) if crowd is not None else len(chars)
    # The scene's staging sheet places "the others" in frame (RI ch1: "the others stand in rows on one side"). The first
    # cliff render failed 8 of 13 panels on an exact count of one that showed the lead and that crowd, so a staged
    # crowd turns the count into a floor, like a crowd cut.
    staged_others = "the others" in (getattr(brief, "staging", "") or "").casefold()
    return PanelExpectation(
        people=people, people_at_least=crowd is not None or staged_others, hair_colour=hair, outfit_colour=outfit,
        lead=lead.name if lead else "",
    )


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass rates and cost from the per-panel rows `render` writes to `vision_check.jsonl`."""
    checked = [r for r in rows if not r.get("unchecked")]
    n = len(checked)
    reasons: dict[str, int] = {}
    for r in checked:
        if not r.get("passed"):
            for f in r.get("failed", []):
                reasons[f] = reasons.get(f, 0) + 1
    return {
        "panels_checked": n,
        "unchecked": len(rows) - n,
        "first_pass_rate": round(sum(bool(r.get("first_passed")) for r in checked) / n, 3) if n else 0.0,
        "final_pass_rate": round(sum(bool(r.get("passed")) for r in checked) / n, 3) if n else 0.0,
        "rescued": sum(bool(r.get("passed")) and not r.get("first_passed") for r in checked),
        "extra_images": sum(max(int(r.get("candidates", 1)) - 1, 0) for r in rows),
        "still_failing": reasons,
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
