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

Done (offset edge cases, same day):
- Found+fixed a real bug in the apply path: source in/out were set to
  TIMELINE frames, only correct at offset 0. Now source = timeline − offset,
  clamped to the media span ([0, mediaEndFrame]), intervals with no media
  skipped with a logged warning
- Live-verified with a rigged sequence: cam2 trimmed-in (inPoint 60) AND
  placed at frame 150 (offset +90). Detection reported offset 90f; every
  cam2 segment placed at frame F reads source F−90 (checked across the
  transaction log); zero sub-frame error, exact map match

Done (handover, same day):
- HANDOVER.md written: repo layout, env setup, panel load instructions,
  architecture summary, key invariants, known issues, next milestones

## Milestone: M2 productization — IN PROGRESS (started 2026-06-11)

Done:
- `/panel/` created: clean Spectrum-styled HTML panel (no build step),
  production-quality JS replacing throwaway spike code
  - Sidecar health indicator (green/red dot, polls /health every 3 s)
  - Start Sidecar button: opens `sidecar/start.command` in Terminal via
    `uxp.shell.openPath()`, navigating to the repo root from plugin folder
  - Detect Sources button: reads cameras/offsets/fps from active sequence
  - Analyze & Apply button: POST /analyze → Method A apply with progress bar
  - Full offset-corrected apply path ported from spike (srcIn = timeline − offset)
  - All hard rules honoured: tick-accurate time, non-destructive clone, E5 guard
- Cosmetic gap fixed (task 3): after apply, both the new panel and spike.js
  show an explicit "double-click '[name]' in the Project panel" instruction.
  Panel shows a persistent green hint box; spike logs an info line.
- `sidecar/start.command` created (macOS double-click to start uvicorn in Terminal)
- `sidecar/requirements.txt` was already present (fastapi, uvicorn, numpy, pytest, httpx)

Done (live smoke test, 2026-06-12) — M2 PANEL VERIFIED IN PREMIERE:
- Loaded via UDT (com.vibesplice.panel), full pass of panel/SMOKE-TEST.md:
  boot, health poll, Detect Sources (3 cams incl. 90f offset), Analyze &
  Apply (50 cuts, E5 pass, clone created, source untouched), done-hint box,
  Start-button sidecar launch with auto-green dot
- 3 real bugs found+fixed live (new BANANAS classes E9, E10):
  - `AbortSignal.timeout` doesn't exist in UXP → health poll always failed;
    replaced with a Promise.race timeout
  - `Entry.getNativePath()` is not a function → use `.nativePath` property
  - `shell.openPath` rejects with `undefined` without `launchProcess`
    manifest permission; first run shows a Premiere Allow/Block dialog
- Smoke-test checklist written: panel/SMOKE-TEST.md (negative tests for
  detection + E5 not yet exercised this pass — run on next session)

Next:
1. **Real footage regression** (~2026-06-15): load real 3-cam recording,
   run Analyze & Apply in the new panel. Expected to work unchanged; tune
   `min_shot_s` / VAD ratios via request body if needed.
2. **Run SMOKE-TEST.md negative tests**: non-multicam sequence detection
   error, 25 fps E5 refusal. (Double-click guard: race found and fixed
   2026-06-12 — queued clicks bypass `disabled`; state check added.)
3. **Verify clone rename live**: coded via
   `sequence.getProjectItem().createSetNameAction(name)` (API confirmed by
   proto probe) but the call itself not yet exercised — run one pipeline
   pass and check the hint box says "<source> — Vibe Splice".
4. **Sidecar stop**: no UXP API to kill a process; consider bundling a stop
   script or documenting that the Terminal window must be closed manually.
5. **Find open-timeline API**: confirm no UXP method exists to open a sequence
   in the program monitor; update BANANAS.md if confirmed.

## Blocked on
- Real footage (~2026-06-15)
