"""Phase 8: render a novel's script to audio.

Consumes exactly what §4.13's script view already shows a human -- every span
in reading order, its speaker, and how confident that attribution is -- which
is the point `4b` step 5 makes: the script view is not a debugging tool that
happens to resemble the TTS input, it *is* the TTS input.

**Three speaker categories, three different treatments**, because conflating
them is what makes machine-read fiction sound wrong:

1. **A resolved character** gets their cast voice (`voice/casting.py`).
2. **An anonymous slot** (`speakers/runner.py::_assign_anonymous_slots`) gets a
   random bank voice of the right gender where known, stable for the run.
   These are real people with no name, not errors.
3. **Unattributed narration** gets the narrator voice.

**An unresolved dialogue line is a decision point, not a silent default.**
It is rendered in the narrator voice and counted in
`VoiceReport.unattributed_lines`, so the number is visible in the run output
rather than hidden inside plausible-sounding audio.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from echotales.core.enums import AttributionMethod, SpanType
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.persona import load_trait_profiles
from echotales.pipeline.voice.bank import VoiceBank, pick_mob_voice
from echotales.pipeline.voice.casting import DEFAULT_SEED, cast_voices
from echotales.pipeline.voice.delivery import pace_text, settings_for
from echotales.pipeline.voice.engine import SynthesisRequest, TTSEngine, get_engine

#: Span types that reach audio. `NARRATION_EXPOSITION` is included (it is
#: read aloud even though panels skip it -- `SpanType.is_renderable_visually`
#: draws that distinction); `NON_DIEGETIC` is excluded because a translator's
#: note is not part of the story.
_AUDIBLE = (
    SpanType.DIALOGUE,
    SpanType.INNER_MONOLOGUE,
    SpanType.NARRATION_ACTION,
    SpanType.NARRATION_DESCRIPTION,
    SpanType.NARRATION_EXPOSITION,
    SpanType.CROWD_REACTION,
    SpanType.SYSTEM_WINDOW,
)


@dataclass(slots=True)
class AudioLine:
    """One rendered line, and every decision behind it."""

    chapter: float
    block_index: int
    span_id: str
    span_type: str
    speaker_id: str
    speaker_label: str
    voice: str
    exaggeration: float
    cfg_weight: float
    rationale: str
    text: str
    audio_path: str = ""


@dataclass(slots=True)
class VoiceReport:
    novel_id: str
    lines: int = 0
    chapters: int = 0
    character_lines: int = 0
    anonymous_lines: int = 0
    narrator_lines: int = 0
    unattributed_lines: int = 0
    voices_used: set[str] = field(default_factory=set)
    engine: str = "stub"

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.lines:,} lines over {self.chapters} chapters "
            f"({self.engine})\n"
            f"  character={self.character_lines:,}  anonymous={self.anonymous_lines:,}  "
            f"narrator={self.narrator_lines:,}\n"
            f"  dialogue with no identity (read as narrator): "
            f"{self.unattributed_lines:,}\n"
            f"  distinct reference voices used: {len(self.voices_used)}"
        )


def speaker_index(store: Store, novel_id: str) -> dict[str, str]:
    """Map an attribution's speaker *label* to a resolved entity id.

    `Span.speaker_self_id` does not hold a `Self` id despite the name: the
    attribution ladder (`speakers/attribution.py`) extracts a capitalised
    surface from narration ("Fang Yuan said"), so what lands there is a
    surface form, and resolution never revisits it. Casting is keyed by
    entity, so the two have to be joined somewhere, and here is the cheapest
    place -- one pass over already-resolved mentions.

    Keyed on `comparison_key`, not raw text, so the possessive and honorific
    variants that reach this column ("Fang Yuan's", "Elder Wang") land on the
    same entity as the bare form rather than being read as unknown speakers.
    """
    from echotales.pipeline.ingest.normalize import comparison_key

    index: dict[str, str] = {}
    for row in store.conn.execute(
        "SELECT text, target_id, COUNT(*) AS n FROM mention"
        " WHERE novel_id=? AND target_id IS NOT NULL"
        " GROUP BY text, target_id ORDER BY n",
        (novel_id,),
    ):
        # Ascending count, so the most frequent binding for a surface wins by
        # overwriting the rarer ones.
        if key := comparison_key(row["text"]):
            index[key] = row["target_id"]

    for entity in store.all_selves(novel_id):
        if entity.kind.is_person and (key := comparison_key(entity.canonical_label)):
            index.setdefault(key, entity.id)
    return index


def _narrator_voice(bank: VoiceBank) -> str:
    """A stable narrator voice.

    Picked as the first adult voice by speaker id rather than at random, so
    the narrator does not change between runs -- it is the one voice a
    listener hears in every chapter, and the one whose consistency matters
    most.
    """
    adults = sorted(
        (v for v in bank.voices if v.age_band == "adult"), key=lambda v: v.speaker_id
    )
    pool = adults or sorted(bank.voices, key=lambda v: v.speaker_id)
    return pool[0].speaker_id if pool else "narrator"


def render_novel(
    novel_id: str,
    store: Store,
    bank: VoiceBank,
    *,
    out_dir: str | Path = "data/audio",
    engine: TTSEngine | None = None,
    chapters: list[float] | None = None,
    seed: int = DEFAULT_SEED,
    synthesize: bool = True,
) -> VoiceReport:
    """Cast the novel, build its script, and render it.

    `synthesize=False` writes the manifest without touching a model, which is
    how casting decisions are reviewed before spending GPU time on them.
    """
    engine = engine or get_engine("stub")
    out_dir = Path(out_dir) / novel_id
    report = VoiceReport(novel_id=novel_id, engine=engine.name)

    profiles = load_trait_profiles(novel_id, store)
    assignments, casting = cast_voices(
        novel_id, profiles, bank, store=store, seed=seed
    )
    labels = speaker_index(store, novel_id)
    narrator = _narrator_voice(bank)
    rng = random.Random(seed)
    #: Anonymous slots keep one voice for the whole run rather than being
    #: re-rolled per line -- the slot exists precisely so two unnamed
    #: speakers stay distinguishable.
    anon_voices: dict[str, str] = {}

    manifest: list[AudioLine] = []
    wanted = chapters if chapters is not None else store.chapter_numbers(novel_id)

    for chapter in wanted:
        report.chapters += 1
        for span in store.get_spans(novel_id, chapter):
            if span.span_type not in _AUDIBLE or not span.text.strip():
                continue

            raw_speaker = span.speaker_self_id or ""
            # Anonymous slots are already ids, not labels, and must not be
            # looked up as surfaces.
            speaker_id = raw_speaker
            if (
                raw_speaker
                and span.attribution_method is not AttributionMethod.ANONYMOUS_SLOT
                and raw_speaker not in assignments
            ):
                speaker_id = labels.get(comparison_key(raw_speaker), raw_speaker)

            profile = profiles.get(speaker_id)
            label = "narrator"

            if speaker_id and speaker_id in assignments:
                voice = assignments[speaker_id].speaker_id
                label = assignments[speaker_id].label
                report.character_lines += 1
            elif span.attribution_method is AttributionMethod.ANONYMOUS_SLOT:
                if speaker_id not in anon_voices:
                    picked = pick_mob_voice(bank, "unknown", "adult", rng=rng)
                    anon_voices[speaker_id] = picked.speaker_id if picked else narrator
                voice = anon_voices[speaker_id]
                label = f"Unknown Speaker {speaker_id.rsplit(':', 1)[-1]}"
                report.anonymous_lines += 1
            else:
                voice = narrator
                report.narrator_lines += 1
                if span.span_type is SpanType.DIALOGUE:
                    report.unattributed_lines += 1

            settings = settings_for(
                span_type=span.span_type,
                polarity=None,
                profile=profile,
                text=span.text,
            )
            text = pace_text(span.text, span_type=span.span_type)

            line = AudioLine(
                chapter=chapter,
                block_index=span.block_index,
                span_id=span.id,
                span_type=span.span_type.value,
                speaker_id=speaker_id,
                speaker_label=label,
                voice=voice,
                exaggeration=settings.exaggeration,
                cfg_weight=settings.cfg_weight,
                rationale=settings.rationale,
                text=text,
            )

            if synthesize:
                clip = next(
                    (v.reference_clip for v in bank.voices if v.speaker_id == voice), None
                )
                path = out_dir / f"ch{chapter:g}" / f"{span.id.replace(':', '_')}.wav"
                engine.synthesize(
                    SynthesisRequest(
                        text=text,
                        out_path=path,
                        reference_clip=clip,
                        exaggeration=settings.exaggeration,
                        cfg_weight=settings.cfg_weight,
                    )
                )
                line.audio_path = str(path)

            manifest.append(line)
            report.voices_used.add(voice)
            report.lines += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.jsonl").write_text(
        "\n".join(json.dumps(asdict(line)) for line in manifest) + "\n",
        encoding="utf-8",
    )
    (out_dir / "casting.txt").write_text(casting.summary() + "\n", encoding="utf-8")
    return report
