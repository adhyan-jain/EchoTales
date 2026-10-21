"""Run the reader pass over a novel's chapters in reading order and total the per-chapter reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.reader.speakers_pass import SpeakerReport, read_chapter_speakers


@dataclass(slots=True)
class ReaderReport:
    chapters: int = 0
    speakers: SpeakerReport = field(default_factory=SpeakerReport)

    def summary(self) -> str:
        s = self.speakers
        return (
            f"reader pass: {self.chapters} chapters, {s.quotes} quotes read -> {s.attributed} named, "
            f"{s.unknown} unknown ({s.cleared} legacy guesses cleared), {s.not_speech} not speech, {s.unmapped} name not in cast, "
            f"{s.no_span} with no dialogue span; {s.retried_tags} tags re-asked, {s.missing} never answered"
        )


def read_novel(
    novel_id: str, store: Store, client: ModelClient, *, chapters: Sequence[float] | None = None
) -> ReaderReport:
    """Chapters run in order because the cast for chapter N only holds what chapters < N attested (no look-ahead)."""
    report = ReaderReport()
    for number in chapters if chapters is not None else store.chapter_numbers(novel_id):
        chapter = store.get_chapter(novel_id, number)
        if chapter is None:
            continue
        one = read_chapter_speakers(store, client, chapter)
        report.chapters += 1
        for name in SpeakerReport.__slots__:
            setattr(report.speakers, name, getattr(report.speakers, name) + getattr(one, name))
    return report
