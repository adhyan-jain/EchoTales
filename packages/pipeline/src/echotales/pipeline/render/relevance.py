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

from echotales.pipeline.render.beat_canon import beat_canon_for

#: Words that carry no scene content. Kept short: this is a stop list for
#: an overlap score, not a linguistic resource.
_STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or but if then than that this these those of in on at to for
    with without from by as is was were be been being are am do does did have
    has had he she it they them his her its their him us we you your i me my
    not no yes so such very more most much many few own same other another
    all any both each every some there here when where while after before
    during until about into over under again further once who whom which what
    how why can could would should may might must will shall now just also
    only even still yet ever never always one two three
    """.split()
)

#: Prompt fragments that are style scaffolding rather than scene content --
#: quality tags, medium, genre anchors. Counting these as "matched" would
#: score every panel highly for saying "manhwa illustration".
_PROMPT_NOISE: frozenset[str] = frozenset(
    """
    masterpiece best quality aesthetic absurdres highly detailed illustration
    manhwa webtoon anime art style guofeng chinese ink painting xianxia wuxia
    ancient china hanfu robes clothes dramatic lighting cinematic composition
    male focus boy boys girl solo crowd multiple people foreground background
    view shot closeup close up wide establishing scene panel
    """.split()
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

    def line(self) -> str:
        blocks = f"{self.blocks[0]}-{self.blocks[-1]}" if self.blocks else "?"
        shared = ", ".join(sorted(self.matched)[:6]) or "nothing"
        tag = f"[{self.exempt}] " if self.exempt else ""
        return (
            f"{self.score:5.2f}  b{blocks:<9s} {Path(self.image).name:24s} {tag}{shared}"
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
        return (
            f"{self.novel_id}: {len(self.scored)} scored panels "
            f"({exempt} exempt: crowd cuts, hand-authored staging), "
            f"mean scene-word overlap {self.mean:.2f}; "
            f"{weak} below 0.10"
        )


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


def audit(
    manifest_path: str | Path,
    block_text: dict[tuple[float, int], str],
    *,
    novel_id: str = "",
) -> RelevanceReport:
    """Score every panel in a render manifest against its own blocks."""
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

        report.panels.append(
            PanelRelevance(
                image=image,
                blocks=blocks,
                score=score,
                exempt=exempt,
                matched=matched,
                prompt=prompt,
            )
        )
    return report
