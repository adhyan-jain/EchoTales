"""The reference-voice bank: real speakers, bucketed for casting (`4b` step 4).

Backed by **CSTR VCTK 0.92** (110 English speakers, ~400 sentences each, 48 kHz,
CC BY 4.0), which is chosen for what casting actually needs rather than for
size: every speaker ships hand-recorded metadata -- age, gender, accent and
region -- so a bucket can be built from stated facts instead of from a
classifier's guess about a voice. `data/voice/` holds it; see `HANDOFF` Section 7 for
why corpora are not committed.

**A bank voice is a reference clip, not a trained model.** Chatterbox clones
from ~5 seconds of audio at synthesis time, so "casting" here means choosing
which speaker's clip conditions a line -- there is no per-character training
step, and adding a character costs nothing.

**Two honest limitations, both structural to VCTK rather than to this code:**

1. **The corpus skews young.** Its speakers are largely students; genuine
   `elder` voices are scarce. `bucket_report()` prints the real distribution
   so a casting run's coverage is visible rather than assumed, and
   `nearest_bucket` degrades age *outward* by one band rather than failing.
2. **VCTK has no register metadata.** Our archetype is
   `gender:age:register` (`persona/traits.py`), but the bank can only speak
   to `gender:age`. Register is therefore not used to *partition* the bank;
   it is carried into synthesis as a delivery parameter instead
   (`voice/delivery.py`). Pretending otherwise would invent a distinction the
   audio does not contain.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path

#: VCTK records a numeric age; casting speaks in bands. Boundaries follow the
#: bands in `persona/traits.py` so a character bucket and a voice bucket are
#: the same vocabulary.
_AGE_BANDS: tuple[tuple[int, str], ...] = (
    (13, "child"),
    (26, "youth"),
    (60, "adult"),
    (200, "elder"),
)


#: Where a request goes when a bank lacks it. Kept to requests the delivery
#: layer can actually make; anything else falls straight to the neutral clip.
_EMOTION_FALLBACK: dict[str, str] = {
    "whisper": "fear",
    "loud": "angry",
    "sad": "neutral",
}


def age_band_for(age: int) -> str:
    for ceiling, band in _AGE_BANDS:
        if age < ceiling:
            return band
    return "elder"


@dataclass(slots=True)
class BankVoice:
    """One reference speaker."""

    speaker_id: str
    gender: str
    age: int
    accent: str = ""
    region: str = ""
    reference_clip: Path | None = None
    #: Emotion label -> a clip of this speaker performing it. Empty for a
    #: read-speech bank like VCTK, which has no emotional recordings at all.
    #: **This is the strongest emotion lever available.** Chatterbox clones
    #: the prosody of its reference clip, so handing it an angry recording
    #: does more for a shouted line than any value of `exaggeration` --
    #: that dial scales intensity around whatever the reference already
    #: sounds like, and a calm read-speech prompt has no anger to scale.
    emotion_clips: dict[str, Path] = field(default_factory=dict)

    def clip_for(self, emotion: str) -> Path | None:
        """This speaker performing `emotion`, or the nearest thing they have.

        Falls back through `_EMOTION_FALLBACK` before the neutral clip, so a
        request a bank cannot satisfy degrades to the closest recording it
        *does* have rather than straight to neutral. That is what lets the
        delivery layer ask for `whisper` (only EARS records it) without
        changing what VCTK or CREMA-D produce for the same line -- they still
        get `fear`, exactly as before whisper existed.
        """
        seen: set[str] = set()
        while emotion and emotion not in seen:
            seen.add(emotion)
            clip = self.emotion_clips.get(emotion)
            if clip is not None:
                return clip
            emotion = _EMOTION_FALLBACK.get(emotion, "")
        return self.reference_clip

    @property
    def age_band(self) -> str:
        return age_band_for(self.age)

    @property
    def bucket(self) -> str:
        """`gender:age_band` -- deliberately without register; see the module docstring."""
        return f"{self.gender}:{self.age_band}"


@dataclass(slots=True)
class VoiceBank:
    voices: list[BankVoice] = field(default_factory=list)

    def by_bucket(self) -> dict[str, list[BankVoice]]:
        out: dict[str, list[BankVoice]] = {}
        for voice in self.voices:
            out.setdefault(voice.bucket, []).append(voice)
        return out

    def nearest_bucket(self, gender: str, age_band: str) -> list[BankVoice]:
        """Voices for this bucket, widening outward only as far as needed.

        Order of concession is deliberate and is a casting judgement, not an
        arbitrary fallback chain: **age is relaxed before gender**, because a
        listener forgives a character sounding a decade off far more readily
        than sounding like the wrong person entirely. Gender is only dropped
        when it is `unknown` to begin with (nothing in the text stated it) or
        when the bank genuinely has no voice of that gender at any age.
        """
        buckets = self.by_bucket()
        if exact := buckets.get(f"{gender}:{age_band}"):
            return exact

        order = ["child", "youth", "adult", "elder"]
        if gender in ("male", "female") and age_band in order:
            index = order.index(age_band)
            for distance in (1, 2, 3):
                for neighbour in (index - distance, index + distance):
                    if 0 <= neighbour < len(order) and (
                        hit := buckets.get(f"{gender}:{order[neighbour]}")
                    ):
                        return hit
            # Same gender at any age beat the right age in the wrong gender.
            if same_gender := [v for v in self.voices if v.gender == gender]:
                return same_gender

        # Gender unstated, or absent from the bank: fall back on age alone so
        # at least the age reads correctly.
        if same_age := [v for v in self.voices if v.age_band == age_band]:
            return same_age
        return list(self.voices)

    def bucket_report(self) -> str:
        counts = {k: len(v) for k, v in sorted(self.by_bucket().items())}
        total = len(self.voices)
        body = ", ".join(f"{k}={v}" for k, v in counts.items()) or "empty"
        return f"{total} reference voices across {len(counts)} buckets: {body}"


_SPEAKER_LINE = re.compile(
    r"^(?P<id>p?\d+|s5)\s+(?P<age>\d+)\s+(?P<gender>[MF])\s+(?P<accent>\S+)\s*(?P<region>.*)$"
)


def parse_speaker_info(text: str) -> list[BankVoice]:
    """Parse VCTK's `speaker-info.txt`.

    Format is whitespace-aligned columns with a header line:
    `ID  AGE  GENDER  ACCENTS  REGION  COMMENTS`.
    """
    out: list[BankVoice] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper().startswith("ID"):
            continue
        m = _SPEAKER_LINE.match(line)
        if not m:
            continue
        out.append(
            BankVoice(
                speaker_id=m.group("id"),
                gender="male" if m.group("gender").upper() == "M" else "female",
                age=int(m.group("age")),
                accent=m.group("accent"),
                region=m.group("region").strip(),
            )
        )
    return out


def load_vctk(root: str | Path, *, reference_utterance: int = 3) -> VoiceBank:
    """Build a bank from an extracted VCTK tree.

    `reference_utterance` picks *which* recording conditions a clone. Not the
    first one: VCTK's opening utterances are the same elicitation paragraph
    for every speaker and often start with a breath or a false start, which a
    5-second cloning window would faithfully reproduce in every line the
    character ever speaks.
    """
    root = Path(root)
    info = root / "speaker-info.txt"
    if not info.exists():
        # The zip nests everything one level down; tolerate both shapes rather
        # than making the caller care which they extracted.
        nested = next(root.glob("*/speaker-info.txt"), None)
        if nested is None:
            raise FileNotFoundError(f"no speaker-info.txt under {root}")
        info = nested
        root = nested.parent

    voices = parse_speaker_info(info.read_text(encoding="utf-8", errors="replace"))
    audio_root = next(
        (
            root / name
            for name in ("wav48_silence_trimmed", "wav48", "wav")
            if (root / name).is_dir()
        ),
        None,
    )
    if audio_root is None:
        return VoiceBank(voices=voices)

    kept: list[BankVoice] = []
    for voice in voices:
        speaker_dir = audio_root / voice.speaker_id
        if not speaker_dir.is_dir():
            continue
        clips = sorted(
            p for p in speaker_dir.iterdir() if p.suffix.lower() in (".flac", ".wav")
        )
        # mic1 is the omnidirectional head-mounted mic; mic2 is a large
        # diaphragm at a distance and carries noticeably more room. Prefer
        # mic1 where both exist, since room tone is exactly what a cloning
        # window would bake into every synthesised line.
        mic1 = [p for p in clips if "_mic1" in p.name]
        clips = mic1 or clips
        if not clips:
            continue
        voice.reference_clip = clips[min(reference_utterance, len(clips) - 1)]
        kept.append(voice)

    return VoiceBank(voices=kept)


def pick_mob_voice(
    bank: VoiceBank, gender: str, age_band: str = "adult", *, rng: random.Random
) -> BankVoice | None:
    """A random bank voice for an unnamed background speaker.

    Random *within the right bucket*, which is the whole requirement: a crowd
    member has no identity worth modelling, but a female guard must not be
    voiced as a man. Takes an explicit `Random` so a run is reproducible --
    re-synthesising one chapter must not silently recast the extras.
    """
    candidates = bank.nearest_bucket(gender, age_band)
    return rng.choice(candidates) if candidates else None


#: CREMA-D encodes its labels in the filename: `1001_DFA_ANG_XX.wav` is
#: actor 1001, sentence DFA, emotion ANG, intensity unspecified.
_CREMAD_EMOTIONS: dict[str, str] = {
    "ANG": "angry",
    "DIS": "disgust",
    "FEA": "fear",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}

#: Loudest first. A reference clip is chosen per (actor, emotion), and where
#: the corpus offers several intensities the strongest one is the most
#: useful prompt -- a barely-angry reference transfers barely any anger.
_CREMAD_INTENSITY_RANK: dict[str, int] = {"HI": 0, "MD": 1, "XX": 2, "LO": 3}


def load_cremad(
    root: str | Path,
    *,
    demographics: str | Path | None = None,
) -> VoiceBank:
    """Load CREMA-D as an emotion-capable voice bank.

    **Why a second bank at all.** VCTK is read speech: 110 speakers reading
    prompt sentences evenly, which is why casting from it sounds correct and
    lifeless, and why a warlord besieging a mountain sounds like a man
    reading a train timetable. CREMA-D is 91 actors performing six emotions
    on purpose, with published age and sex per actor -- so it can be cast
    the same way *and* asked for the right feeling.

    The two are not exclusive: VCTK has the wider voice range and cleaner
    audio, CREMA-D has the performances. `VoiceBank.voices` from either
    slots into the same casting path.
    """
    root = Path(root)
    audio_dir = root / "AudioWAV" if (root / "AudioWAV").is_dir() else root
    if not audio_dir.is_dir():
        raise FileNotFoundError(f"CREMA-D audio directory not found under {root}")

    ages: dict[str, int] = {}
    genders: dict[str, str] = {}
    # **The demographics CSV is not inside the audio archive.** CREMA-D
    # ships `AudioWAV/` in its zip and the actor table separately, so it
    # normally sits one level above the extracted root. Looking only in the
    # root left every actor without an age or sex, and the filter at the end
    # of this function then dropped all 91 -- the bank loaded empty and the
    # narration stage died with "voice bank is empty" one second in.
    candidates = (
        [Path(demographics)]
        if demographics
        else [
            root / "VideoDemographics.csv",
            root.parent / "VideoDemographics.csv",
            audio_dir.parent / "VideoDemographics.csv",
        ]
    )
    demo_path = next((c for c in candidates if c.exists()), candidates[0])
    if demo_path.exists():
        import csv

        with demo_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                actor = str(row["ActorID"]).strip()
                ages[actor] = int(row["Age"])
                genders[actor] = str(row["Sex"]).strip().casefold()

    best: dict[tuple[str, str], tuple[int, Path]] = {}
    for clip in sorted(audio_dir.glob("*.wav")):
        parts = clip.stem.split("_")
        if len(parts) < 4:
            continue
        actor, _sentence, emotion_code, intensity = parts[0], parts[1], parts[2], parts[3]
        emotion = _CREMAD_EMOTIONS.get(emotion_code.upper())
        if emotion is None:
            continue
        rank = _CREMAD_INTENSITY_RANK.get(intensity.upper(), 9)
        key = (actor, emotion)
        if key not in best or rank < best[key][0]:
            best[key] = (rank, clip)

    by_actor: dict[str, dict[str, Path]] = {}
    for (actor, emotion), (_rank, clip) in best.items():
        by_actor.setdefault(actor, {})[emotion] = clip

    voices: list[BankVoice] = []
    for actor, clips in sorted(by_actor.items()):
        voices.append(
            BankVoice(
                speaker_id=f"cremad{actor}",
                # Unknown demographics would silently cast every actor into
                # one bucket, so an actor the CSV does not cover is skipped
                # rather than guessed at.
                gender=genders.get(actor, ""),
                age=ages.get(actor, 0),
                accent="american",
                reference_clip=clips.get("neutral") or next(iter(clips.values())),
                emotion_clips=clips,
            )
        )
    return VoiceBank([v for v in voices if v.gender and v.age])


#: EARS emotion recordings mapped onto the delivery layer's vocabulary
#: (`voice/delivery.py::EMOTION_FOR_POLARITY`). Every EARS emotion is *also*
#: kept under its own name, so a future polarity can request `pride` or
#: `distress` directly; these entries are only the ones asked for today.
#: `contentment` rather than `amusement` for WARM: the polarity marks a warm
#: line, and amusement reads as laughter.
_EARS_TO_PIPELINE: dict[str, str] = {
    "neutral": "neutral",
    "anger": "angry",
    "disgust": "disgust",
    "fear": "fear",
    "contentment": "happy",
    "sadness": "sad",
}
#: Reading-style recordings: the reason this bank exists. A HUSHED line is
#: whispered speech, not frightened speech, and until EARS no bank in this
#: project had a whisper to clone -- `fear` was the least-wrong stand-in.
_EARS_STYLES: dict[str, str] = {
    "whisper": "rainbow_01_whisper",
    "loud": "rainbow_01_loud",
}


def _ears_age(band: str) -> int:
    """Midpoint of an EARS age band (``"36-45"`` -> 40); 0 when undisclosed."""
    try:
        lo, hi = (int(x) for x in band.split("-"))
    except ValueError:
        return 0
    return (lo + hi) // 2


def load_ears(root: str | Path, *, metadata: str | Path | None = None) -> VoiceBank:
    """Load EARS as an emotion- and style-capable voice bank.

    **EARS** (Expressive Anechoic Recordings of Speech; Richter et al.,
    Interspeech 2024): 107 speakers recorded in an anechoic studio at 48 kHz,
    each performing 22 emotions and 7 reading styles (regular, loud, whisper,
    high/low pitch, fast, slow). It replaces the two gaps the older banks
    left: VCTK is read speech with no emotion at all, and CREMA-D has six
    emotions but at 16 kHz and with no whisper or projection.

    **Licence: CC BY-NC 4.0.** Fine for research and coursework; *not* for a
    commercial release. Any product build needs a different bank.

    Speakers whose gender or age band is undisclosed are skipped rather than
    guessed, for the same reason `load_cremad` skips them: an unknown would
    silently cast into one bucket.
    """
    import json

    root = Path(root)
    meta_path = Path(metadata) if metadata else root / "speaker_statistics.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"EARS speaker_statistics.json not found at {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    voices: list[BankVoice] = []
    for speaker_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        info = meta.get(speaker_dir.name)
        if not info:
            continue
        gender = str(info.get("gender", "")).casefold()
        age = _ears_age(str(info.get("age", "")))
        if gender not in ("male", "female") or not age:
            continue
        clips: dict[str, Path] = {}
        for clip in sorted(speaker_dir.glob("emo_*_sentences.wav")):
            ears_emotion = clip.stem.split("_")[1]
            clips[ears_emotion] = clip
            if ears_emotion in _EARS_TO_PIPELINE:
                clips[_EARS_TO_PIPELINE[ears_emotion]] = clip
        for style, stem in _EARS_STYLES.items():
            clip = speaker_dir / f"{stem}.wav"
            if clip.exists():
                clips[style] = clip
        if not clips:
            continue
        regular = speaker_dir / "rainbow_01_regular.wav"
        voices.append(
            BankVoice(
                speaker_id=f"ears{speaker_dir.name}",
                gender=gender,
                age=age,
                accent=str(info.get("native language", "")),
                reference_clip=clips.get("neutral") or (regular if regular.exists() else None),
                emotion_clips=clips,
            )
        )
    return VoiceBank(voices)
