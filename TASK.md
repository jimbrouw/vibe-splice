# TASK.md — current milestone

## Milestone: M0 timeline-write spike — DONE 2026-06-11

The one question is answered: **Method A (segmented overwrite via 3-point
edit) writes an angle-switched cut with zero drift** on the 10-minute 3-cam
29.97 fixture. Full report in CONTEXT.md; status block in CLAUDE.md updated;
new error classes E5–E7 in BANANAS.md.

Run artifacts:
- Spike panel: `adapters/premiere/spike/` (loaded via UDT "Load & Watch")
- Verified live in Premiere 25.6.3 on macOS, project "test 1", sequence
  created via New Sequence From Clip on cam1 (29.97p, 1280×720)
- Methods B/C not pursued: their shared dependency (in-place split via
  clone+trim) throws "Invalid parameter", and A passed the acceptance bar

## Milestone: M1 sidecar — IN PROGRESS (started 2026-06-11)

Done:
- Cut-map contract formalised: `sidecar/cutengine/schema.py` (frames + fps
  rational, validated; same wire shape as tests/fixtures/cutmap.json)
- DSP cheap tier, no model: `sidecar/dsp/` — ffmpeg mono extraction (piped
  s16le, no temp files) + energy-gate VAD with hysteresis (50 ms hops)
- Cut engine: `sidecar/cutengine/engine.py` — active-channel switching,
  loudest-wins crosstalk, hold-last-on-silence, min-shot flicker absorption
- FastAPI sidecar: `sidecar/app.py` — POST /analyze (paths in, cut map out)
- 9 tests green (`.venv/bin/python -m pytest tests/test_cutengine.py
  tests/test_api.py`): VAD blocks, schedule reproduction, crosstalk,
  min-shot, schema rejection, end-to-end HTTP with real ffmpeg decode

Done (later same day) — END-TO-END PIPELINE PROVEN:
- Fixtures regenerated with per-cam mic audio (AAC in each cam mp4) following
  a 50-segment speaking schedule (`tests/fixtures/speech_schedule.json`)
- Panel button 6 / `runPipeline()`: POST /analyze to the sidecar
  (localhost:8765), apply the returned map via the Method A path
- Live result in Premiere: 50 cuts applied, worst sub-frame error 0.000,
  V4 segment starts match the sidecar cut map exactly
- Manifest gotchas: UXP network permission needs `"domains": "all"` (explicit
  localhost entries rejected), and manifest changes need UDT Unload+Load,
  not Reload

Done (hardening pass, same day):
- Per-source sync offsets: `/analyze` accepts `offset_frames` for separately
  recorded audio (positive = recorder started late, negative = early);
  alignment in `dsp/vad.py:align_to_timeline`, covered by test (10 green)
- E5 timebase guard in the apply path: live-verified BOTH ways — 29.97
  sequence accepted, 25 fps sequence refused with a clear error
- Hard rule 4 honoured: apply now clones the active sequence
  (`sequence.createCloneAction`, clone found by diffing sequence guids),
  writes into the clone, and makes it active via `project.setActiveSequence`.
  Live result on "cam1 Copy": 50 segments, zero sub-frame error, source
  sequence untouched

Done (source detection, same day):
- Panel buttons 7/8: detect cameras from the active sequence — consecutive
  single-clip video tracks from V1 are cameras (media path via
  `ClipProjectItem.getMediaFilePath`, offset = startTicks − inPointTicks),
  the track above the camera stack is the assembly target, fps derived from
  `sequence.getTimebase()` as a reduced rational, length from `getEndTime()`
- Live-verified: 3 cams detected with paths+offsets, 50 cuts via sidecar
  with `offset_frames`, clone-applied, zero sub-frame error, exact match
- Nothing about the fixture (paths, rate, length, track count) is
  hardcoded in the detected path anymore

Done (offset edge cases, same day):
- Found+fixed a real bug in the apply path: source in/out were set to
  TIMELINE frames, only correct at offset 0. Now source = timeline − offset,
  clamped to the media span ([0, mediaEndFrame]), intervals with no media
  skipped with a logged warning
- Live-verified with a rigged sequence: cam2 trimmed-in (inPoint 60) AND
  placed at frame 150 (offset +90). Detection reported offset 90f; every
  cam2 segment placed at frame F reads source F−90 (checked across the
  transaction log); zero sub-frame error, exact map match

Next:
1. Real 3-cam footage regression (footage arrives week of 2026-06-15) —
   the detected path (button 8) should work on it unchanged
2. Promote spike learnings into /panel + /adapters/premiere proper (M2):
   React+Spectrum panel, sidecar lifecycle management, progress UI
3. Known cosmetic gap: `setActiveSequence` changes the API-active sequence
   but does NOT open its timeline/program monitor — M2 panel should tell
   the user to open the new sequence (or find an open-timeline API)

## Blocked on
- Real footage (next week)
