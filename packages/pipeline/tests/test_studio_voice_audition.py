"""The Studio's voice audition: the audition job, the routes that list and choose, and the config.json write.

Real `HTTPServer` and the stub TTS engine (silent WAVs), over a tiny synthetic voice bank under the temporary
working directory's `data/voice`, so nothing needs a GPU or a downloaded corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from echotales.pipeline import config as config_module
from test_studio_wiring_routes import _upload_voice, _wav, srv  # noqa: F401  (srv is a fixture)

SR = 16000


def _voiced(f0: float, seconds: float = 10.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    carrier = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 8))
    env = 0.5 * (1 + np.sin(2 * np.pi * 4.0 * t - np.pi / 2)) ** 2
    rng = np.random.default_rng(0)
    return (0.2 * carrier * env + 0.0005 * rng.standard_normal(len(t))).astype("float32")


@pytest.fixture
def bank(srv):  # noqa: F811
    """Two Hi-Fi TTS speakers (92 female, 6097 male) as FLAC clips in `data/voice/hifitts`."""
    for speaker, f0 in (("92", 200.0), ("6097", 110.0)):
        folder = srv.root / "data" / "voice" / "hifitts" / "audio" / f"{speaker}_clean" / "1"
        folder.mkdir(parents=True)
        sf.write(str(folder / "a.flac"), _voiced(f0), SR)
    return srv


def _narrator_job(harness, **extra):
    return harness.run_job("voice_audition", {"target": "narrator", "engine": "stub", **extra})


def test_the_narrator_job_voices_one_sample_per_shortlisted_candidate(bank) -> None:
    job = _narrator_job(bank)
    assert job["status"] == "SUCCEEDED", job
    status, body = bank.call("GET", "/api/projects/t/voices/audition")
    assert status == 200
    ids = sorted(c["voice_id"] for c in body["candidates"])
    assert len(ids) == 2 and all(i.startswith("hifitts") for i in ids)
    for c in body["candidates"]:
        assert c["licence"] == "CC BY 4.0" and c["sample"] == f"audition/narrator/{c['voice_id']}/p1_dark.wav"
        status, raw = bank.call("GET", f"/api/novels/t/output/file?path={c['sample']}")
        assert status == 200 and raw[:4] == b"RIFF"
    assert not (bank.root / "data" / "novels" / "t" / "audition" / "narrator" / ids[0] / "p2_pride.wav").exists()
    assert str(bank.root) not in json.dumps(body)


def test_no_audition_yet_lists_no_candidates(srv) -> None:  # noqa: F811
    status, body = srv.call("GET", "/api/projects/t/voices/audition")
    assert status == 200 and body["candidates"] == []


def test_a_narrator_job_without_any_bank_fails_with_a_message(srv) -> None:  # noqa: F811
    job = _narrator_job(srv)
    assert job["status"] == "FAILED" and "voice bank" in job["error_summary"]


def test_choosing_a_narrator_writes_only_that_key_of_config_json(bank, tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"gateway": {"host": "h"}, "voice": {"narrator": "old", "other": 1}}), encoding="utf-8")
    monkeypatch.setattr(config_module, "_CONFIG_JSON", cfg)
    assert _narrator_job(bank)["status"] == "SUCCEEDED"
    _, listed = bank.call("GET", "/api/projects/t/voices/audition")
    pick = listed["candidates"][0]["voice_id"]

    status, body = bank.call("POST", "/api/projects/t/voices/narrator", {"voice_id": pick})
    assert status == 200 and body == {"narrator": pick}
    assert json.loads(cfg.read_text(encoding="utf-8")) == {
        "gateway": {"host": "h"}, "voice": {"narrator": pick, "other": 1},
    }
    assert config_module.get_settings().voice_narrator == pick
    assert bank.call("GET", "/api/projects/t/voices/audition")[1]["narrator"] == pick
    assert not list(tmp_path.glob("config.json.tmp"))


def test_a_voice_outside_the_audition_cannot_become_the_narrator(bank, tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "_CONFIG_JSON", cfg)
    assert _narrator_job(bank)["status"] == "SUCCEEDED"
    for bad in ("", "../../etc/passwd", "vctk_p227", None, 7):
        status, _ = bank.call("POST", "/api/projects/t/voices/narrator", {"voice_id": bad})
        assert status == 400, bad
    assert not cfg.exists()


def test_an_uploaded_voice_can_be_the_narrator(srv, tmp_path, monkeypatch) -> None:  # noqa: F811
    monkeypatch.setattr(config_module, "_CONFIG_JSON", tmp_path / "config.json")
    assert _upload_voice(srv, _wav(5))[0] == 201
    status, _ = srv.call("POST", "/api/projects/t/voices/narrator", {"voice_id": "project:my-voice"})
    assert status == 200


def test_a_line_sample_is_voiced_in_the_assigned_voice_and_found_again(bank) -> None:
    params = {"target": "line", "engine": "stub", "voice_id": "hifitts92", "text": "Get out.", "emotion": "anger"}
    q = "voice_id=hifitts92&emotion=anger&text=Get%20out."
    assert bank.call("GET", f"/api/projects/t/voices/sample?{q}")[0] == 404
    assert bank.run_job("voice_audition", params)["status"] == "SUCCEEDED"
    status, found = bank.call("GET", f"/api/projects/t/voices/sample?{q}")
    assert status == 200 and found["path"].startswith("audition/lines/") and found["path"].endswith(".wav")
    assert bank.call("GET", f"/api/novels/t/output/file?path={found['path']}")[1][:4] == b"RIFF"
    # Another emotion is another sample.
    assert bank.call("GET", "/api/projects/t/voices/sample?voice_id=hifitts92&emotion=fear&text=Get%20out.")[0] == 404


def test_a_stub_line_sample_is_not_reused_for_a_real_engine(bank, monkeypatch) -> None:
    """The sample file name has no engine in it; a silent stub take was served for good (EVOLUTION 4.183)."""
    import echotales.pipeline.voice as voice_pkg

    class _Fake:
        name = "fake"

        def synthesize(self, req):
            Path(req.out_path).write_bytes(b"RIFFreal")
            return req.out_path

    params = {"target": "line", "voice_id": "hifitts92", "text": "Get out.", "emotion": "anger"}
    q = "voice_id=hifitts92&emotion=anger&text=Get%20out."
    assert bank.run_job("voice_audition", {**params, "engine": "stub"})["status"] == "SUCCEEDED"
    # The route only lets "stub" and "chatterbox" through, so the second request still says "stub" while another
    # engine answers: the same situation as a real engine asking for the line the stub already made.
    monkeypatch.setattr(voice_pkg, "get_engine", lambda name="stub", **kw: _Fake())
    assert bank.run_job("voice_audition", {**params, "engine": "stub"})["status"] == "SUCCEEDED"
    path = bank.call("GET", f"/api/projects/t/voices/sample?{q}")[1]["path"]
    assert bank.call("GET", f"/api/novels/t/output/file?path={path}")[1] == b"RIFFreal"


def test_a_line_can_be_voiced_in_an_uploaded_voice(srv) -> None:  # noqa: F811
    assert _upload_voice(srv, _wav(5))[0] == 201
    params = {"target": "line", "engine": "stub", "voice_id": "project:my-voice", "text": "Hello there."}
    assert srv.run_job("voice_audition", params)["status"] == "SUCCEEDED"
    q = "voice_id=project%3Amy-voice&emotion=neutral&text=Hello%20there."
    assert srv.call("GET", f"/api/projects/t/voices/sample?{q}")[0] == 200


def test_a_line_in_an_unknown_voice_fails_without_writing_a_sample(srv) -> None:  # noqa: F811
    job = srv.run_job("voice_audition", {"target": "line", "engine": "stub", "voice_id": "nobody", "text": "Hi."})
    assert job["status"] == "FAILED" and "nobody" in job["error_summary"]
    assert not (srv.root / "data" / "novels" / "t" / "audition").exists()


@pytest.mark.parametrize(
    "params",
    [
        {"target": "other"},
        {"target": "line", "voice_id": "x", "text": ""},
        {"target": "line", "voice_id": "x", "text": "a" * 401},
        {"target": "line", "voice_id": "", "text": "hi"},
        {"target": "line", "voice_id": "x", "text": "hi", "emotion": "bogus"},
        {"target": "line", "voice_id": "x", "text": "hi", "engine": "xtts"},
    ],
)
def test_bad_audition_requests_are_refused_before_queueing(srv, params) -> None:  # noqa: F811
    status, body = srv.call("POST", "/api/projects/t/voice_audition", params)
    assert status == 400, body
    assert srv.call("GET", "/api/projects/t/jobs")[1] == []


def test_a_client_cannot_choose_the_bank_folder(bank) -> None:
    elsewhere = bank.root / "elsewhere"
    job = _narrator_job(bank, bank=str(elsewhere))
    assert job["status"] == "SUCCEEDED"  # the server's own data/voice was used, not the path from the request


def test_the_uploaded_voice_list_carries_a_playable_clip_path(srv) -> None:  # noqa: F811
    assert _upload_voice(srv, _wav(5))[0] == 201
    voice = srv.call("GET", "/api/projects/t/voices")[1]["voices"][0]
    assert voice["clip"] == "voices/my-voice.wav"
    assert srv.call("GET", f"/api/novels/t/output/file?path={voice['clip']}")[1][:4] == b"RIFF"


def test_set_voice_narrator_creates_the_file_and_refuses_a_non_object(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "c.json"
    config_module.set_voice_narrator("hifitts92", cfg)
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"voice": {"narrator": "hifitts92"}}
    cfg.write_text("[1]", encoding="utf-8")
    with pytest.raises(ValueError):
        config_module.set_voice_narrator("x", cfg)
    assert cfg.read_text(encoding="utf-8") == "[1]"


def test_the_sample_helper_picks_the_emotion_recording_the_audiobook_run_would(tmp_path: Path) -> None:
    from echotales.pipeline.voice.audition import synthesize_line
    from echotales.pipeline.voice.bank import BankVoice
    from echotales.pipeline.voice.engine import SynthesisRequest

    neutral, angry = tmp_path / "n.wav", tmp_path / "a.wav"
    for p in (neutral, angry):
        sf.write(str(p), _voiced(150.0, 3.0), SR)
    voice = BankVoice(speaker_id="v", gender="male", age=35, reference_clip=neutral, emotion_clips={"anger": angry})
    seen: list[SynthesisRequest] = []

    class Spy:
        name, sample_rate = "spy", SR

        def synthesize(self, request: SynthesisRequest) -> Path:
            seen.append(request)
            return request.out_path

    synthesize_line(voice, Spy(), tmp_path / "o.wav", "Get out.", "anger")
    synthesize_line(voice, Spy(), tmp_path / "o2.wav", "Hello.", "neutral")
    assert seen[0].reference_clip == angry and seen[1].reference_clip == neutral
    assert seen[0].exaggeration > seen[1].exaggeration
