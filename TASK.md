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

Next:
1. Real 3-cam footage regression (footage arrives week of 2026-06-15):
   spike re-run + /analyze on real per-mic audio
2. UXP panel -> sidecar wiring: panel collects source paths, calls /analyze,
   feeds the returned cut map to the proven Method A apply path
3. Apply adapter hardening: timebase check (E5), sequence creation from
   footage, write to a NEW sequence (hard rule 4)

## Blocked on
- Real footage (next week)
