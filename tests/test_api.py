"""End-to-end API test: WAV files on disk -> /analyze -> valid cut map.

Generates three tiny per-mic WAVs with a known schedule, exercises the real
extraction path (ffmpeg decode), VAD, engine, and HTTP layer together.
"""

import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "sidecar"))

from app import app  # noqa: E402

SR = 16000
SCHEDULE = [(0.0, 5.0, 1), (5.0, 12.0, 2), (12.0, 20.0, 3)]
DURATION_S = 20.0


def write_wav(path: Path, samples: np.ndarray):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


@pytest.fixture(scope="module")
def wav_paths(tmp_path_factory):
    folder = tmp_path_factory.mktemp("mics")
    rng = np.random.default_rng(5)
    n = int(DURATION_S * SR)
    paths = []
    for cam in (1, 2, 3):
        sig = rng.normal(0, 0.004, n).astype(np.float32)
        for start_s, end_s, spk in SCHEDULE:
            if spk == cam:
                s, e = int(start_s * SR), int(end_s * SR)
                sig[s:e] += rng.normal(0, 0.25, e - s).astype(np.float32)
        p = folder / f"mic{cam}.wav"
        write_wav(p, sig)
        paths.append(str(p))
    return paths


def test_health():
    assert TestClient(app).get("/health").json()["ok"] is True


def test_analyze_end_to_end(wav_paths):
    total_frames = round(DURATION_S * 30000 / 1001)
    resp = TestClient(app).post("/analyze", json={
        "audio_paths": wav_paths,
        "fps_numerator": 30000,
        "fps_denominator": 1001,
        "total_frames": total_frames,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [c["camera"] for c in body["cuts"]] == [1, 2, 3]
    assert body["cuts"][0]["frame"] == 0


def test_analyze_rejects_missing_file():
    resp = TestClient(app).post("/analyze", json={
        "audio_paths": ["/nope/a.wav", "/nope/b.wav"],
        "fps_numerator": 30000,
        "fps_denominator": 1001,
        "total_frames": 100,
    })
    assert resp.status_code == 422


def test_director_endpoint_mock_roundtrip():
    """/director with the mock provider on the fixture schedule, then
    /director/merge with everything accepted -> a valid, changed cut map."""
    client = TestClient(app)
    schedule_path = str(Path(__file__).parent / "fixtures" / "speech_schedule.json")
    cuts = [{"frame": 0, "camera": 1}, {"frame": 450, "camera": 2},
            {"frame": 1200, "camera": 3}]
    body = {
        "cuts": cuts, "total_frames": 17982,
        "fps_numerator": 30000, "fps_denominator": 1001,
        "n_cameras": 3, "provider": "mock",
        "transcript_source": "synthetic", "schedule_path": schedule_path,
    }
    r = client.post("/director", json=body)
    assert r.status_code == 200, r.text
    sugs = r.json()["suggestions"]
    assert sugs, "mock should suggest something on the fixture schedule"

    r2 = client.post("/director/merge", json={
        "cuts": cuts, "total_frames": 17982,
        "fps_numerator": 30000, "fps_denominator": 1001,
        "accepted": sugs,
    })
    assert r2.status_code == 200, r2.text
    merged = r2.json()
    frames = [c["frame"] for c in merged["cuts"]]
    assert frames == sorted(frames) and frames[0] == 0


def test_director_whisper_not_implemented():
    r = TestClient(app).post("/director", json={
        "cuts": [{"frame": 0, "camera": 1}], "total_frames": 100,
        "fps_numerator": 30000, "fps_denominator": 1001, "n_cameras": 2,
        "provider": "mock", "transcript_source": "whisper",
    })
    assert r.status_code == 501
