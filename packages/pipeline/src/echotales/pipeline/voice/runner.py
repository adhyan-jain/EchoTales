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
from echotales.core.models import Span
from echotales.core.store import Store
from echotales.pipeline.ingest.normalize import comparison_key
from echotales.pipeline.persona import load_trait_profiles
from echotales.pipeline.persona.traits import gender_from_pronouns
from echotales.pipeline.spans.delivery import (
    DeliveryPolarity,
    dominant_polarity,
    extract_delivery_markers,
)
from echotales.pipeline.voice.bank import VoiceBank, pick_mob_voice
from echotales.pipeline.voice.casting import DEFAULT_SEED, cast_voices
from echotales.pipeline.voice.delivery import pace_text, settings_for
from echotales.pipeline.voice.engine import SynthesisRequest, TTSEngine, get_engine
from echotales.pipeline.voice.pitch import ffmpeg_available, shift_pitch

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
    pitch_semitones: float = 0.0
    audio_path: str = ""


@dataclass(slots=True)
class VoiceReport:
    novel_id: str
    lines: int = 0
    chapters: int = 0
    character_lines: int = 0
    anonymous_lines: int = 0
    #: A role-title speaker (`AttributionMethod.EPITHET_SLOT`, e.g. "the
    #: clan head") -- has a real, if unnamed, identity, so counted
    #: separately from a plain anonymous slot rather than folded into
    #: either `character_lines` or `anonymous_lines`.
    epithet_lines: int = 0
    narrator_lines: int = 0
    unattributed_lines: int = 0
    voices_used: set[str] = field(default_factory=set)
    engine: str = "stub"
    #: Set once the first pitch-shift call finds no ffmpeg on PATH, so the
    #: note prints once per run, not once per affected line.
    pitch_shift_unavailable_warned: bool = False

    def summary(self) -> str:
        return (
            f"{self.novel_id}: {self.lines:,} lines over {self.chapters} chapters "
            f"({self.engine})\n"
            f"  character={self.character_lines:,}  epithet={self.epithet_lines:,}  "
            f"anonymous={self.anonymous_lines:,}  narrator={self.narrator_lines:,}\n"
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
    out_dir = Path(out_dir)
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

    _SLOT_METHODS = (AttributionMethod.ANONYMOUS_SLOT, AttributionMethod.EPITHET_SLOT)

    for chapter in wanted:
        report.chapters += 1
        chapter_spans = list(store.get_spans(novel_id, chapter))
        chapter_obj = store.get_chapter(novel_id, chapter)
        block_text = {b.index: b.text for b in chapter_obj.blocks} if chapter_obj else {}

        # Gender evidence for anonymous/epithet speakers, pooled across every
        # line the same slot speaks in this chapter -- one line's narration
        # neighbourhood rarely clears `gender_from_pronouns`'s floor, a whole
        # chapter's worth usually does. Without this, every slot fell back to
        # a gender-blind pool and a male character had roughly even odds of
        # being cast with a female reference clip (confirmed by ear on RI
        # ch1's clan head -- HANDOFF 4.37 item 1).
        slot_gender_cache: dict[str, str | None] = {}

        # Every voice already spoken for in this chapter -- the narrator,
        # plus every named character who actually has a line here. Anonymous
        # and epithet slots are cast preferring a voice outside this set, so
        # "no voice repeated in a chapter" (HANDOFF 4.37 item 3) holds for
        # narrator-vs-anonymous *and* named-vs-anonymous collisions, not
        # just the one case that was caught by ear.
        chapter_voices_used: set[str] = {narrator}
        for s in chapter_spans:
            sid = s.speaker_self_id or ""
            if sid and s.attribution_method not in _SLOT_METHODS and sid not in assignments:
                sid = labels.get(comparison_key(sid), sid)
            if sid in assignments:
                chapter_voices_used.add(assignments[sid].speaker_id)

        def slot_gender(speaker_id: str) -> str | None:
            if speaker_id not in slot_gender_cache:
                # The block where the slot is *speaking* is usually a short
                # quoted line -- rarely a pronoun in sight. The pronoun
                # evidence lives in the narration around it, so pull a wide
                # neighbourhood around each occurrence, not just the exact
                # block. Measured against RI ch1's clan head: a +/-1 window
                # around his two epithet-tagged lines cleared only 1-4
                # pronouns (below the 6 floor, no call); +/-5 cleared 6/6 and
                # 8/8, unanimously, because the whole surrounding scene is
                # about him and there's no other-character noise to dilute
                # it. Wider than `line_polarity`'s window deliberately --
                # gender only needs a majority *anywhere* nearby, so it can
                # afford to look further than a delivery tag can.
                passages: list[str] = []
                for s in chapter_spans:
                    if s.speaker_self_id != speaker_id:
                        continue
                    idx = s.block_index
                    passages.extend(
                        block_text[i]
                        for i in range(idx - 5, idx + 6)
                        if i in block_text
                    )
                gender, _ = gender_from_pronouns(passages)
                slot_gender_cache[speaker_id] = gender
            return slot_gender_cache[speaker_id]

        def line_polarity(span: Span) -> DeliveryPolarity | None:
            # A marker on the line's own text first (mostly hits narration,
            # which carries its own adverbs); dialogue rarely does, so fall
            # back to the immediately surrounding blocks, which is where a
            # postposed speech tag ("...,\" he said calmly.") actually lives.
            own = dominant_polarity(extract_delivery_markers(span.text))
            if own is not None:
                return own
            if span.span_type not in (SpanType.DIALOGUE, SpanType.INNER_MONOLOGUE):
                return None
            idx = span.block_index
            window = " ".join(
                block_text.get(i, "") for i in (idx - 1, idx, idx + 1) if i in block_text
            )
            return dominant_polarity(extract_delivery_markers(window))

        for span in chapter_spans:
            if span.span_type not in _AUDIBLE or not span.text.strip():
                continue

            raw_speaker = span.speaker_self_id or ""
            # Anonymous/epithet slots are already ids, not labels, and must
            # not be looked up as surfaces.
            speaker_id = raw_speaker
            if (
                raw_speaker
                and span.attribution_method not in _SLOT_METHODS
                and raw_speaker not in assignments
            ):
                speaker_id = labels.get(comparison_key(raw_speaker), raw_speaker)

            profile = profiles.get(speaker_id)
            label = "narrator"

            if speaker_id and speaker_id in assignments:
                voice = assignments[speaker_id].speaker_id
                label = assignments[speaker_id].label
                report.character_lines += 1
            elif span.attribution_method in _SLOT_METHODS:
                if speaker_id not in anon_voices:
                    # A genuinely unresolved gender is coin-flipped, not
                    # left to the bank's raw population. VCTK is 63 female
                    # / 47 male overall -- passing "unknown" straight to
                    # `nearest_bucket` falls back to every adult voice
                    # regardless of gender, and an `rng.choice` over that
                    # mixed pool is implicitly weighted toward whichever
                    # gender the corpus happens to have more of. That is
                    # backwards: a speaker whose gender the text simply
                    # never states should get even odds, not odds shaped by
                    # a recording corpus's own imbalance. Real pronoun
                    # evidence (`slot_gender` resolving to an actual value)
                    # still wins outright -- this only fires when the text
                    # gave no signal at all.
                    gender = slot_gender(speaker_id) or rng.choice(("male", "female"))
                    # Prefer a voice nobody else in this chapter is already
                    # using -- narrator, a named character, or another
                    # anonymous/epithet slot -- so "no voice repeated in a
                    # chapter" (HANDOFF 4.37 item 3) holds generally, not
                    # just for the one narrator collision caught by ear.
                    # `male:adult` is only 6 speakers wide in VCTK and one RI
                    # chapter can need all 6 at once (narrator, a named
                    # principal, and 4+ anonymous/epithet slots) -- widen to
                    # the same gender at *any* age before accepting a repeat;
                    # a decade-off voice is a far smaller compromise than two
                    # different people sounding identical.
                    pool = bank.nearest_bucket(gender, "adult")
                    candidates = [v for v in pool if v.speaker_id not in chapter_voices_used]
                    if not candidates and gender in ("male", "female"):
                        candidates = [
                            v for v in bank.voices
                            if v.gender == gender and v.speaker_id not in chapter_voices_used
                        ]
                    if not candidates:
                        candidates = [v for v in pool if v.speaker_id != narrator]
                    picked = (
                        rng.choice(candidates)
                        if candidates
                        else pick_mob_voice(bank, gender, "adult", rng=rng)
                    )
                    anon_voices[speaker_id] = picked.speaker_id if picked else narrator
                    chapter_voices_used.add(anon_voices[speaker_id])
                voice = anon_voices[speaker_id]
                if span.attribution_method is AttributionMethod.EPITHET_SLOT:
                    label = speaker_id.rsplit(":", 1)[-1].replace("-", " ").title()
                    report.epithet_lines += 1
                else:
                    label = f"Unknown Speaker {speaker_id.rsplit(':', 1)[-1]}"
                    report.anonymous_lines += 1
            elif span.span_type is SpanType.CROWD_REACTION:
                # A crowd shouting in unison is not the narrator -- it was
                # falling into the narrator branch by default before this
                # (no `speaker_self_id` at all, so nothing else matched).
                # One stable "crowd" voice per chapter, same reasoning as
                # `anon_voices`: distinguishable from surrounding lines, not
                # claiming to model the crowd's actual composition.
                # Gender: the block's own text if it states one ("a crowd
                # of men roared"), otherwise the same 50/50 coin flip as an
                # unresolved individual speaker -- explicit author
                # instruction (HANDOFF), not a guess, since VCTK's male
                # deficit would otherwise bias crowds female too.
                if "crowd" not in anon_voices:
                    crowd_gender, _ = gender_from_pronouns(
                        [block_text.get(span.block_index, "")]
                    )
                    crowd_gender = crowd_gender or rng.choice(("male", "female"))
                    pool = bank.nearest_bucket(crowd_gender, "adult")
                    candidates = [v for v in pool if v.speaker_id not in chapter_voices_used]
                    picked = rng.choice(candidates) if candidates else rng.choice(pool or bank.voices)
                    anon_voices["crowd"] = picked.speaker_id
                    chapter_voices_used.add(anon_voices["crowd"])
                voice = anon_voices["crowd"]
                label = "Crowd"
                report.anonymous_lines += 1
            else:
                voice = narrator
                report.narrator_lines += 1
                if span.span_type is SpanType.DIALOGUE:
                    report.unattributed_lines += 1

            settings = settings_for(
                span_type=span.span_type,
                polarity=line_polarity(span),
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
                pitch_semitones=settings.pitch_semitones,
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
                if settings.pitch_semitones:
                    shift_pitch(path, settings.pitch_semitones)
                    if not ffmpeg_available() and not report.pitch_shift_unavailable_warned:
                        print(
                            "note: ffmpeg not found -- register-based pitch shifting "
                            "(voice/pitch.py) is a no-op this run"
                        )
                        report.pitch_shift_unavailable_warned = True
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
