"""Director tier: segments, mock provider, validation, merge.

Everything here is deterministic — the mock provider stands in for the LLM.
Live-provider behaviour is probabilistic and is exercised manually from the
panel, not asserted in CI.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sidecar"))

from director.gateway import _extract_json_array, suggest
from director.merge import apply_suggestions
from director.segments import (TranscriptLine, build_segments,
                               synthetic_transcript)

FPS = (30000, 1001)
SPF = FPS[1] / FPS[0]


def _cuts():
    # 3 segments: 0-300 cam1, 300-600 cam2, 600-1500 cam3 (long: 30s)
    return [
        {"frame": 0, "camera": 1},
        {"frame": 300, "camera": 2},
        {"frame": 600, "camera": 3},
    ]


def _transcript():
    return [
        TranscriptLine(0.0, 9.5, 1, "intro line"),
        TranscriptLine(10.2, 19.5, 2, "reply"),
        TranscriptLine(11.0, 12.0, 1, "brief interjection"),  # crosstalk
        TranscriptLine(20.5, 49.0, 3, "long monologue"),
    ]


def test_build_segments_assigns_lines_by_overlap():
    segs = build_segments(_cuts(), 1500, *FPS, _transcript())
    assert [s.segment_id for s in segs] == ["seg-0000", "seg-0001", "seg-0002"]
    assert segs[0].speakers() == [1]
    assert sorted(segs[1].speakers()) == [1, 2]      # crosstalk lands in seg 1
    assert segs[2].speakers() == [3]
    assert segs[2].duration_s == pytest.approx(900 * SPF, abs=0.01)


def test_synthetic_transcript_matches_fixture_schedule():
    sched = json.loads(
        (Path(__file__).parent / "fixtures" / "speech_schedule.json").read_text()
    )
    lines = synthetic_transcript(sched)
    assert len(lines) == 50
    assert all(ln.text for ln in lines)
    assert lines[0].speaker == 1


def test_mock_provider_suggests_reaction_and_crosstalk_switch():
    segs = build_segments(_cuts(), 1500, *FPS, _transcript())
    res = suggest(segs, n_cameras=3, provider="mock")
    actions = {s["action"] for s in res["suggestions"]}
    assert "reaction" in actions          # 30s monologue
    # frames mapped by US from segment ids, not by the model
    for s in res["suggestions"]:
        assert s["frame"] in {0, 300, 600}
        assert 1 <= s["new_camera"] <= 3


def test_validation_drops_garbage(monkeypatch):
    import director.gateway as gw
    garbage = json.dumps([
        {"segment_id": "seg-9999", "action": "switch", "camera": 2, "reason": ""},
        {"segment_id": "seg-0000", "action": "explode", "camera": 2, "reason": ""},
        {"segment_id": "seg-0000", "action": "switch", "camera": 99, "reason": ""},
        {"segment_id": "seg-0000", "action": "switch", "camera": 1, "reason": "no-op"},
        {"segment_id": "seg-0000", "action": "switch", "camera": 2, "reason": "ok"},
    ])
    monkeypatch.setitem(gw._PROVIDERS, "mock", lambda p, k, m: garbage)
    segs = build_segments(_cuts(), 1500, *FPS, _transcript())
    res = suggest(segs, n_cameras=3, provider="mock")
    assert res["dropped"] == 4
    assert len(res["suggestions"]) == 1
    assert res["suggestions"][0]["new_camera"] == 2


def test_extract_json_array_tolerates_prose_and_fences():
    assert _extract_json_array('Sure! ```json\n[{"a": 1}]\n```') == [{"a": 1}]
    with pytest.raises(ValueError):
        _extract_json_array("no array here")


def test_merge_switch_recolours_segment():
    accepted = [{"frame": 300, "end_frame": 600, "action": "switch",
                 "old_camera": 2, "new_camera": 1}]
    cm, skipped = apply_suggestions(_cuts(), 1500, *FPS, accepted)
    assert skipped == 0
    # seg 0 (cam1) and recoloured seg 1 (cam1) collapse into one run
    assert [(c.frame, c.camera) for c in cm.cuts] == [(0, 1), (600, 3)]


def test_merge_reaction_inserts_cutaway_and_returns():
    accepted = [{"frame": 600, "end_frame": 1500, "action": "reaction",
                 "old_camera": 3, "new_camera": 1}]
    cm, skipped = apply_suggestions(_cuts(), 1500, *FPS, accepted)
    assert skipped == 0
    frames = [(c.frame, c.camera) for c in cm.cuts]
    r0 = 600 + round(900 * 0.4)            # 960
    r1 = r0 + round(2.0 * FPS[0] / FPS[1])  # +60 frames at 29.97
    assert (r0, 1) in frames and (r1, 3) in frames
    cm.validate()  # still a legal map


def test_merge_reaction_skipped_when_segment_too_short():
    accepted = [{"frame": 0, "end_frame": 300, "action": "reaction",
                 "old_camera": 1, "new_camera": 2}]
    # 300 frames = 10s; shoulders 4s/6s-ish OK... use min_shot large enough to block
    cm, skipped = apply_suggestions(_cuts(), 1500, *FPS, accepted, min_shot_s=5.0)
    assert skipped == 1
    assert [(c.frame, c.camera) for c in cm.cuts] == [
        (0, 1), (300, 2), (600, 3)]


def test_merge_stale_suggestion_skipped():
    accepted = [{"frame": 12345, "end_frame": 12400, "action": "switch",
                 "old_camera": 1, "new_camera": 2}]
    cm, skipped = apply_suggestions(_cuts(), 1500, *FPS, accepted)
    assert skipped == 1
    assert len(cm.cuts) == 3
