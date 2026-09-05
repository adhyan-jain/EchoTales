"""Does this panel depict the blocks it plays under?

Every relevance failure so far was found by a person opening a PNG and
saying "that is not what is happening". That does not scale to 199
chapters, and worse, it gives no way to tell whether a change helped: two
of the three fixes in this area were justified by counting things
(`22 panels for 92 blocks`, `7 of 48 panels assert a crowd`) and the third
by opening images one at a time.

So this scores a panel against its own source text: how much of the
picture's content is drawn from what the narration actually says. It is a
cheap lexical measure, and deliberately so -- it cannot tell a good
composition from a bad one, and it is not trying to. What it catches is the
failure that has actually been happening: a prompt describing a moment that
is not in these blocks.

**A low score is a lead, not a verdict.** A panel whose beat is stated in
words the prompt paraphrases ("bloodstains" for "his blood had dried") will
score low while being right. Read it as a ranking to inspect, top of the
list first, which is how a 199-chapter novel gets reviewed at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from echotales.pipeline.render.beat_canon import beat_canon_for

if TYPE_CHECKING:
    from echotales.core.store import Store

#: Narrated physical-state cues (EVOLUTION 4.51: "a beat's own narrated
#: physical state -- torn robes, blood, disheveled hair -- actually
#: appearing on screen"). Deliberately a cheap curated list, same spirit as
#: `_PROMPT_NOISE` above: this is a lexical lead, not an NLP extractor, and
#: it only needs to catch the shape of condition language this corpus uses.
_CONDITION_CUES: frozenset[str] = frozenset(
    [
        "blood", "bloody", "bleeding", "bled", "wound", "wounded", "torn",
        "tattered", "ragged", "bruise", "bruised", "scar", "scarred",
        "disheveled", "dishevelled", "drenched", "soaked", "bandage",
        "bandaged", "gore", "mangled", "mutilated", "crippled", "pale",
        "sweat", "sweaty", "exhausted", "dirt", "dirty", "dust", "dusty",
        "mud", "muddy", "singed", "burn", "burned", "burnt", "scorched",
        "grime", "grimy", "sallow", "haggard", "gaunt", "trembling",
        "shaking", "limping", "broken", "shattered", "charred",
    ]
)

#: Words that carry no scene content. Kept short: this is a stop list for
#: an overlap score, not a linguistic resource.
_STOPWORDS: frozenset[str] = frozenset(
    ["a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those", "of", "in", "on", "at", "to", "for", "with", "without", "from", "by", "as", "is", "was", "were", "be", "been", "being", "are", "am", "do", "does", "did", "have", "has", "had", "he", "she", "it", "they", "them", "his", "her", "its", "their", "him", "us", "we", "you", "your", "i", "me", "my", "not", "no", "yes", "so", "such", "very", "more", "most", "much", "many", "few", "own", "same", "other", "another", "all", "any", "both", "each", "every", "some", "there", "here", "when", "where", "while", "after", "before", "during", "until", "about", "into", "over", "under", "again", "further", "once", "who", "whom", "which", "what", "how", "why", "can", "could", "would", "should", "may", "might", "must", "will", "shall", "now", "just", "also", "only", "even", "still", "yet", "ever", "never", "always", "one", "two", "three"]
)

#: Prompt fragments that are style scaffolding rather than scene content --
#: quality tags, medium, genre anchors. Counting these as "matched" would
#: score every panel highly for saying "manhwa illustration".
_PROMPT_NOISE: frozenset[str] = frozenset(
    ["masterpiece", "best", "quality", "aesthetic", "absurdres", "highly", "detailed", "illustration", "manhwa", "webtoon", "anime", "art", "style", "guofeng", "chinese", "ink", "painting", "xianxia", "wuxia", "ancient", "china", "hanfu", "robes", "clothes", "dramatic", "lighting", "cinematic", "composition", "male", "focus", "boy", "boys", "girl", "solo", "crowd", "multiple", "people", "foreground", "background", "view", "shot", "closeup", "close", "up", "wide", "establishing", "scene", "panel"]
)

_WORD_RE = re.compile(r"[a-z]+")


def _content_words(text: str) -> set[str]:
    words = set()
    for raw in _WORD_RE.findall(text.casefold()):
        if len(raw) < 3 or raw in _STOPWORDS:
            continue
        # Crude singularisation, enough to match "warriors"/"warrior" and
        # "eyes"/"eye" without a stemmer dependency.
        if raw.endswith("ies") and len(raw) > 4:
            raw = raw[:-3] + "y"
        elif raw.endswith("es") and len(raw) > 4:
            raw = raw[:-2]
        elif raw.endswith("s") and len(raw) > 3:
            raw = raw[:-1]
        words.add(raw)
    return words


@dataclass(slots=True)
class PanelRelevance:
    image: str
    blocks: list[int]
    score: float
    #: Why a low score here is expected and not a defect: a crowd cut is a
    #: fixed template with no beat by design, and a hand-authored staging
    #: (`render/beat_canon.py`) exists precisely because the prose was not
    #: the picture wanted. Both would otherwise sit permanently at the top
    #: of the worst list and bury the real failures.
    exempt: str = ""
    matched: list[str] = field(default_factory=list)
    prompt: str = ""

    #: Section 1.3 signals -- `None` when no ground truth was available to
    #: check against (no `store` passed to `audit`, or nothing to check:
    #: an empty expected cast, no condition cues in the source text).
    #: `cast_expected`/`cast_missing` are display labels from the *same*
    #: `get_panel_cast` path panels.py itself calls, so a mismatch here means
    #: the delivered prompt drifted from what rendering decided to cast, not
    #: that this harness computed presence differently.
    cast_expected: list[str] = field(default_factory=list)
    cast_missing: list[str] = field(default_factory=list)
    cast_recall: float | None = None
    headcount_match: bool | None = None
    condition_expected: list[str] = field(default_factory=list)
    condition_missing: list[str] = field(default_factory=list)
    condition_recall: float | None = None

    def line(self) -> str:
        blocks = f"{self.blocks[0]}-{self.blocks[-1]}" if self.blocks else "?"
        shared = ", ".join(sorted(self.matched)[:6]) or "nothing"
        tag = f"[{self.exempt}] " if self.exempt else ""
        extra = ""
        if self.cast_missing:
            extra += f"  MISSING CAST: {', '.join(self.cast_missing)}"
        if self.condition_missing:
            extra += f"  DROPPED CONDITION: {', '.join(self.condition_missing)}"
        return (
            f"{self.score:5.2f}  b{blocks:<9s} {Path(self.image).name:24s} {tag}{shared}{extra}"
        )


@dataclass(slots=True)
class RelevanceReport:
    novel_id: str
    panels: list[PanelRelevance] = field(default_factory=list)

    @property
    def scored(self) -> list[PanelRelevance]:
        """Panels the score is meaningful for -- see `PanelRelevance.exempt`."""
        return [p for p in self.panels if not p.exempt]

    @property
    def mean(self) -> float:
        scored = self.scored
        return sum(p.score for p in scored) / len(scored) if scored else 0.0

    def worst(self, n: int = 10) -> list[PanelRelevance]:
        return sorted(self.scored, key=lambda p: p.score)[:n]

    def summary(self) -> str:
        weak = sum(1 for p in self.scored if p.score < 0.10)
        exempt = len(self.panels) - len(self.scored)
        lines = [
            f"{self.novel_id}: {len(self.scored)} scored panels "
            f"({exempt} exempt: crowd cuts, hand-authored staging), "
            f"mean scene-word overlap {self.mean:.2f}; "
            f"{weak} below 0.10"
        ]

        cast_checked = [p for p in self.panels if p.cast_recall is not None]
        if cast_checked:
            mean_recall = sum(p.cast_recall for p in cast_checked) / len(cast_checked)  # type: ignore[misc]
            dropped = sum(1 for p in cast_checked if p.cast_missing)
            head_checked = [p for p in cast_checked if p.headcount_match is not None]
            head_wrong = sum(1 for p in head_checked if not p.headcount_match)
            lines.append(
                f"  cast survival: {len(cast_checked)} panels with a ground-truth "
                f"cast, mean recall {mean_recall:.0%}; {dropped} panel(s) dropped "
                f"at least one expected name; headcount mismatch on "
                f"{head_wrong}/{len(head_checked)}"
            )
        else:
            lines.append("  cast survival: untested -- no store passed to audit()")

        cond_checked = [p for p in self.panels if p.condition_recall is not None]
        if cond_checked:
            mean_cond = sum(p.condition_recall for p in cond_checked) / len(cond_checked)  # type: ignore[misc]
            dropped = sum(1 for p in cond_checked if p.condition_missing)
            lines.append(
                f"  condition-tag survival: {len(cond_checked)} panels whose "
                f"blocks narrate a physical-state cue, mean recall {mean_cond:.0%}; "
                f"{dropped} panel(s) dropped at least one narrated condition"
            )
        else:
            lines.append(
                "  condition-tag survival: untested -- no store passed, or no "
                "panel's blocks narrated a recognised condition cue"
            )
        return "\n".join(lines)


def score_panel(prompt: str, source_text: str) -> tuple[float, list[str]]:
    """Share of the prompt's scene words that the source text also uses.

    Scored over the *prompt's* content words rather than the text's: a
    panel is wrong when it depicts something the blocks do not contain,
    which is a claim about the prompt. The reverse direction -- how much of
    the passage made it into the picture -- would penalise every close-up
    for not drawing the whole scene.
    """
    prompt_words = _content_words(prompt) - _PROMPT_NOISE
    if not prompt_words:
        return 0.0, []
    source_words = _content_words(source_text)
    shared = sorted(prompt_words & source_words)
    return len(shared) / len(prompt_words), shared


def _name_survives(name: str, prompt_lower: str) -> bool:
    """Whether a cast display label still has some trace in the final prompt.

    Not an exact-substring requirement: a full label ("Fang Yuan") usually
    degrades to a bare given/clan name under `fit_to_budget`'s truncation
    (Section 6's token-budget bug), and that degraded survival is still a
    win worth counting -- only a name with none of its tokens left counts as
    dropped.
    """
    tokens = [t for t in re.findall(r"[a-z]+", name.casefold()) if len(t) > 2]
    if not tokens:
        return name.casefold() in prompt_lower
    return any(t in prompt_lower for t in tokens)


def _expected_cast(
    store: Store, novel_id: str, chapter_number: float, blocks: list[int]
) -> list[str]:
    """Ground-truth foreground cast for a block range, via panels.py's own path.

    Reuses `persona.runner.get_panel_cast` rather than re-deriving presence,
    so a disagreement this harness finds means the *delivered prompt*
    diverged from what rendering itself decided to cast -- not that this
    check used a different notion of "present in frame."
    """
    from echotales.pipeline.persona.runner import get_panel_cast

    chapter = store.get_chapter(novel_id, chapter_number)
    if chapter is None or not blocks:
        return []
    mentions = store.get_mentions(novel_id, chapter_number)
    segments = store.get_segments(novel_id, chapter_number)
    spans = store.get_spans(novel_id, chapter_number)
    cast = get_panel_cast(
        novel_id,
        chapter,
        blocks[0],
        mentions=mentions,
        segments=segments,
        spans=spans,
        store=store,
        block_window=(blocks[0], blocks[-1]),
    )
    return [c.self_label for c in cast.foreground_characters]


def audit(
    manifest_path: str | Path,
    block_text: dict[tuple[float, int], str],
    *,
    novel_id: str = "",
    store: Store | None = None,
) -> RelevanceReport:
    """Score every panel in a render manifest against its own blocks.

    `store`, when given, unlocks the Section 1.3 ground-truth checks (cast
    survival, headcount, condition-tag survival) alongside the scene-word
    overlap score. Omitting it keeps the original text-only behaviour.
    """
    report = RelevanceReport(novel_id=novel_id)
    rows = [
        json.loads(line)
        for line in Path(manifest_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    by_image: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_image.setdefault(str(row["image_path"]), []).append(row)

    for image, group in by_image.items():
        blocks = sorted(int(r["block_index"]) for r in group)
        chapter = float(group[0]["chapter"])
        source = " ".join(block_text.get((chapter, b), "") for b in blocks)
        prompt = str(group[0]["prompt"])
        score, matched = score_panel(prompt, source)

        exempt = ""
        if "_crowd" in Path(image).name:
            exempt = "crowd cut"
        elif novel_id and any(
            beat_canon_for(novel_id, chapter, b) is not None for b in blocks
        ):
            exempt = "staged"

        panel = PanelRelevance(
            image=image,
            blocks=blocks,
            score=score,
            exempt=exempt,
            matched=matched,
            prompt=prompt,
        )

        if store is not None and novel_id and not exempt:
            prompt_lower = prompt.casefold()

            expected = _expected_cast(store, novel_id, chapter, blocks)
            if expected:
                found = [n for n in expected if _name_survives(n, prompt_lower)]
                panel.cast_expected = expected
                panel.cast_missing = [n for n in expected if n not in found]
                panel.cast_recall = len(found) / len(expected)
                panel.headcount_match = len(found) == len(expected)

            cues = sorted(_content_words(source) & _CONDITION_CUES)
            if cues:
                found_cues = [c for c in cues if c in prompt_lower]
                panel.condition_expected = cues
                panel.condition_missing = [c for c in cues if c not in found_cues]
                panel.condition_recall = len(found_cues) / len(cues)

        report.panels.append(panel)
    return report
