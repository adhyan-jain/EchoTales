"""Run the reader pass over a novel's chapters in reading order and total the per-chapter reports."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from echotales.core.store import Store
from echotales.pipeline.llm.client import ModelClient
from echotales.pipeline.reader.delivery_pass import DeliveryReport, read_chapter_delivery
from echotales.pipeline.reader.facts_pass import FactsReport, read_chapter_facts
from echotales.pipeline.reader.speakers_pass import SpeakerReport, read_chapter_speakers


@dataclass(slots=True)
class ReaderReport:
    chapters: int = 0
    speakers: SpeakerReport = field(default_factory=SpeakerReport)
    facts: FactsReport = field(default_factory=FactsReport)
    delivery: DeliveryReport = field(default_factory=DeliveryReport)

    def summary(self) -> str:
        s, f = self.speakers, self.facts
        return (
            f"reader pass: {self.chapters} chapters, {s.quotes} quotes read -> {s.attributed} named, "
            f"{s.role_slots} unnamed-by-role ({s.role_resolved} later matched to a name), {s.unknown} unknown ({s.cleared} legacy guesses cleared), {s.not_speech} not speech, {s.unmapped} name not in cast, "
            f"{s.no_span} with no dialogue span; {s.retried_tags} tags re-asked, {s.missing} never answered\n"
            f"facts: {f.appearance} appearance, {f.ages} ages, {f.identities} new names stored from {f.windows} windows; "
            f"rejected {f.rejected_quote} unverifiable quotes, {f.rejected_ungrounded} ungrounded values, "
            f"{f.rejected_character} unknown characters, {f.rejected_key} bad keys, {f.rejected_value} implausible values, {f.rejected_subject} about someone else; {f.duplicates} already known; {f.repaired} quotes repaired to the passage sentence\n"
            f"delivery: {self.delivery.lines} lines and {self.delivery.narration} narration spans labelled from "
            f"{self.delivery.windows} windows, {self.delivery.unknown_labels} off-list labels, {self.delivery.missing} "
            f"never answered; {dict(self.delivery.emotions.most_common(8))}"
        )


#: Every pass, in the order they must run.
PASSES = ("speakers", "facts", "delivery")


def read_novel(
    novel_id: str,
    store: Store,
    client: ModelClient,
    *,
    chapters: Sequence[float] | None = None,
    passes: Sequence[str] = PASSES,
) -> ReaderReport:
    """Chapters run in order because the cast for chapter N only holds what chapters < N attested (no look-ahead).

    `passes` selects a subset, so the delivery pass can be added to a book already read without re-running the
    speaker pass and moving its measured numbers."""
    report = ReaderReport()
    for number in chapters if chapters is not None else store.chapter_numbers(novel_id):
        chapter = store.get_chapter(novel_id, number)
        if chapter is None:
            continue
        report.chapters += 1
        if "speakers" in passes:
            one = read_chapter_speakers(store, client, chapter)
            for name in SpeakerReport.__slots__:
                setattr(report.speakers, name, getattr(report.speakers, name) + getattr(one, name))
        # After speakers: a character the speaker pass minted (Daly) is in the cast for the facts pass.
        if "facts" in passes:
            facts = read_chapter_facts(store, client, chapter)
            for name in FactsReport.__slots__:
                setattr(report.facts, name, getattr(report.facts, name) + getattr(facts, name))
        # After speakers: a line the speaker pass retyped as narration (a scare quote) gets a narration mood.
        if "delivery" in passes:
            d = read_chapter_delivery(store, client, chapter)
            for name in ("windows", "lines", "narration", "unknown_labels", "missing"):
                setattr(report.delivery, name, getattr(report.delivery, name) + getattr(d, name))
            report.delivery.emotions.update(d.emotions)
    return report
