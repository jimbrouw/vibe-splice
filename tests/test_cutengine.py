"""Cut engine benchmark against a synthetic 3-mic conversation.

Builds per-channel RMS for a known speaking schedule (speech-band noise
bursts + low noise floor), runs the engine, and asserts the cut map matches
the schedule within one hop of tolerance per boundary.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "sidecar"))

from cutengine.engine import build_cut_map  # noqa: E402
from cutengine.schema import CutMap  # noqa: E402
from dsp.vad import HOP_S, align_to_timeline, detect_activity, rms_per_hop  # noqa: E402

SR = 16000
FPS = (30000, 1001)

# (start_s, end_s, speaker 1-based) — non-overlapping baseline conversation
SCHEDULE = [
    (0.0, 8.0, 1),
    (8.0, 14.0, 2),
    (14.0, 25.0, 3),
    (25.0, 31.0, 1),
    (31.0, 45.0, 2),
    (45.0, 60.0, 3),
]
DURATION_S = 60.0


def synth_channels(schedule, duration_s, seed=7):
    """Three mono channels: speech-band noise when speaking, faint floor otherwise."""
    rng = np.random.default_rng(seed)
    n = int(duration_s * SR)
    chans = [rng.normal(0, 0.004, n).astype(np.float32) for _ in range(3)]
    for start_s, end_s, spk in schedule:
        s, e = int(start_s * SR), int(end_s * SR)
        burst = rng.normal(0, 0.25, e - s).astype(np.float32)
        # amplitude-modulate at syllable-ish rate so it is not a flat gate
        t = np.arange(e - s) / SR
        burst *= 0.6 + 0.4 * np.sin(2 * np.pi * 4.0 * t).astype(np.float32) ** 2
        chans[spk - 1][s:e] += burst
    return chans


@pytest.fixture(scope="module")
def channel_rms():
    return [rms_per_hop(c, SR, HOP_S) for c in synth_channels(SCHEDULE, DURATION_S)]


def test_vad_finds_speech_blocks(channel_rms):
    blocks = detect_activity(channel_rms[0])
    # speaker 1 talks twice: 0-8s and 25-31s
    assert len(blocks) == 2
    spans_s = [(b.start_hop * HOP_S, b.end_hop * HOP_S) for b in blocks]
    assert abs(spans_s[0][0] - 0.0) <= 0.3 and abs(spans_s[0][1] - 8.0) <= 0.5
    assert abs(spans_s[1][0] - 25.0) <= 0.3 and abs(spans_s[1][1] - 31.0) <= 0.5


def test_cut_map_matches_schedule(channel_rms):
    total_frames = round(DURATION_S * FPS[0] / FPS[1])
    m = build_cut_map(channel_rms, *FPS, total_frames)
    m.validate()

    assert [c.camera for c in m.cuts] == [s[2] for s in SCHEDULE]
    for cut, (start_s, _, _) in zip(m.cuts, SCHEDULE):
        expected_frame = round(start_s * FPS[0] / FPS[1])
        # within 0.5 s of the scheduled boundary (VAD hysteresis adds latency)
        assert abs(cut.frame - expected_frame) <= round(0.5 * FPS[0] / FPS[1]), (
            f"cut to cam{cut.camera} at frame {cut.frame}, expected ~{expected_frame}"
        )


def test_crosstalk_louder_speaker_wins():
    # two speakers overlap 10-20s; speaker 2 is clearly louder there
    schedule = [(0.0, 20.0, 1), (10.0, 20.0, 2)]
    rng = np.random.default_rng(3)
    n = int(20.0 * SR)
    c1 = rng.normal(0, 0.004, n).astype(np.float32)
    c2 = rng.normal(0, 0.004, n).astype(np.float32)
    c3 = rng.normal(0, 0.004, n).astype(np.float32)
    c1[: int(20 * SR)] += rng.normal(0, 0.08, int(20 * SR)).astype(np.float32)
    c2[int(10 * SR) :] += rng.normal(0, 0.4, n - int(10 * SR)).astype(np.float32)
    rms = [rms_per_hop(c, SR, HOP_S) for c in (c1, c2, c3)]
    m = build_cut_map(rms, *FPS, round(20.0 * FPS[0] / FPS[1]))
    cams = [c.camera for c in m.cuts]
    assert cams[0] == 1
    assert 2 in cams, "louder overlapping speaker should win the crosstalk"
    assert 3 not in cams, "silent camera must never be cut to"


def test_min_shot_absorbs_flicker():
    # speaker 2 interjects for 0.6 s — shorter than min_shot 1.5 s — must not cut
    schedule = [(0.0, 10.0, 1), (5.0, 5.6, 2), (10.0, 20.0, 3)]
    chans = synth_channels(schedule, 20.0, seed=11)
    rms = [rms_per_hop(c, SR, HOP_S) for c in chans]
    m = build_cut_map(rms, *FPS, round(20.0 * FPS[0] / FPS[1]), min_shot_s=1.5)
    assert [c.camera for c in m.cuts] == [1, 3]


def test_offset_alignment_recovers_schedule(channel_rms):
    """Separately recorded audio with known offsets must yield the same map.

    Channel 2's recorder started 3 s late (audio t=0 = timeline frame +90ish);
    channel 3's was rolling 2 s early (negative offset). After alignment the
    engine must still reproduce the schedule.
    """
    late_frames = round(3.0 * FPS[0] / FPS[1])     # +3 s
    early_frames = -round(2.0 * FPS[0] / FPS[1])   # -2 s
    late_hops = round(3.0 / HOP_S)
    early_hops = round(2.0 / HOP_S)

    # Simulate the recordings: late recorder is missing its first 3 s of
    # audio; early recorder has 2 s of extra room tone at the front.
    rng = np.random.default_rng(9)
    ch1 = channel_rms[0]
    ch2_rec = channel_rms[1][late_hops:]
    ch3_rec = np.concatenate([rng.uniform(0.003, 0.005, early_hops), channel_rms[2]])

    aligned = [
        align_to_timeline(ch1, 0, *FPS),
        align_to_timeline(ch2_rec, late_frames, *FPS),
        align_to_timeline(ch3_rec, early_frames, *FPS),
    ]
    total_frames = round(DURATION_S * FPS[0] / FPS[1])
    m = build_cut_map(aligned, *FPS, total_frames)
    assert [c.camera for c in m.cuts] == [s[2] for s in SCHEDULE]
    for cut, (start_s, _, _) in zip(m.cuts, SCHEDULE):
        expected = round(start_s * FPS[0] / FPS[1])
        assert abs(cut.frame - expected) <= round(0.5 * FPS[0] / FPS[1])


def test_schema_round_trip(channel_rms):
    total_frames = round(DURATION_S * FPS[0] / FPS[1])
    m = build_cut_map(channel_rms, *FPS, total_frames)
    again = CutMap.from_dict(m.to_dict())
    assert again.to_dict() == m.to_dict()


def test_schema_rejects_bad_maps():
    base = {"fps_numerator": 30000, "fps_denominator": 1001, "total_frames": 100}
    with pytest.raises(ValueError):
        CutMap.from_dict({**base, "cuts": []})
    with pytest.raises(ValueError):
        CutMap.from_dict({**base, "cuts": [{"frame": 5, "camera": 1}]})  # not at 0
    with pytest.raises(ValueError):
        CutMap.from_dict({**base, "cuts": [{"frame": 0, "camera": 1}, {"frame": 0, "camera": 2}]})
    with pytest.raises(ValueError):
        CutMap.from_dict({**base, "cuts": [{"frame": 0, "camera": 0}]})  # 0-based camera
    with pytest.raises(ValueError):
        CutMap.from_dict({**base, "cuts": [{"frame": 0, "camera": 1}, {"frame": 100, "camera": 2}]})
