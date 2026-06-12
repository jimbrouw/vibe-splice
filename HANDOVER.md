# HANDOVER.md — vibe-splice

AI multi-cam podcast editor: UXP panel inside Adobe Premiere Pro that applies a
VAD-driven angle-switched cut map to a synced, stacked multi-camera timeline.

---

## Repo layout

```
vibe-splice/
├── adapters/premiere/spike/   # UXP panel (spike/throwaway, fully functional)
│   ├── manifest.json
│   ├── index.html
│   └── spike.js               # all panel logic (~600 LOC)
├── sidecar/                   # Python FastAPI audio analysis service
│   ├── app.py                 # POST /analyze endpoint
│   ├── cutengine/
│   │   ├── engine.py          # VAD→cut-map algorithm
│   │   └── schema.py          # CutMap / Cut dataclasses + validation
│   └── dsp/
│       ├── extract.py         # ffmpeg mono extraction (piped, no temp files)
│       └── vad.py             # energy-gate VAD with hysteresis + offset align
├── tests/
│   ├── fixtures/
│   │   ├── generate_fixture.py   # generates cam1/2/3.mp4 + speech_schedule.json
│   │   ├── cutmap.json           # 12-cut hand-written map (checkpoints 450/8991/17500)
│   │   └── speech_schedule.json  # 50-segment ground truth schedule
│   ├── test_cutengine.py      # 10 pytest tests (all green)
│   └── test_api.py
├── CLAUDE.md                  # hard rules + architecture decisions (READ FIRST)
├── CONTEXT.md                 # decisions log + M0 spike report
├── BANANAS.md                 # UXP gotchas E1–E8
└── TASK.md                    # milestone tracker
```

---

## Environment setup

### Python sidecar

```bash
cd /Users/standard/Developer/Vibe-splice
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn numpy
# for fixture generation only:
.venv/bin/pip install opencv-python-headless
```

Run the sidecar:
```bash
cd sidecar
../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Health check:
```bash
curl http://localhost:8765/health
```

Run tests:
```bash
.venv/bin/python -m pytest tests/test_cutengine.py tests/test_api.py -v
```

### Panel in Premiere

1. Install UXP Developer Tools (UDT) from Adobe.
2. Open Premiere 25.6+, enable developer mode: **Settings → Plugins → Enable UXP Developer Mode** → restart.
3. In UDT: **Add Plugin** → point at `adapters/premiere/spike/manifest.json`.
4. Click **Load** (not Reload — manifest changes require Unload then Load).
5. Open panel: **Window → Extensions → M0 Timeline-Write Spike**.

Log file (tailed for debugging):
```
~/Library/Application\ Support/Adobe/UXP/PluginsStorage/PPRO/25/Developer/com.vibesplice.m0spike/PluginData/spike-log.txt
```

---

## Using the panel

The panel has 9 buttons:

| # | Button | What it does |
|---|--------|-------------|
| 0 | Probe API surface | Logs API availability; run first |
| 1 | Build synced 3-cam test sequence | Imports fixtures, builds synced stack |
| 2 | Test split primitive | (fails by design — Method B/C abandoned) |
| 3a | Method A — segmented overwrite | Core write primitive, verified zero-drift |
| 3b/c | Methods B/C | Abandoned; kept for reference |
| 4 | Verify drift | Checks all placed clips against cut map |
| 5 | Playhead to checkpoint | Jumps to 450/8991/17500 for spot-check |
| 6 | FULL PIPELINE | POST /analyze → apply via Method A |
| 7 | Detect sources | Reads cameras/paths/offsets from active sequence |
| 8 | PIPELINE from detected | Button 7 + 6, no hardcoded paths |

**Button 8 is the primary workflow.** Open a synced multi-cam sequence, click 8.

---

## Architecture summary

```
Premiere sequence (stacked cams V1/V2/V3, assembly target V4+)
    │
    ▼  (button 7: detect sources)
source list: [{path, offsetFrames, mediaEndFrame, fps}]
    │
    ▼  (button 8: POST /analyze)
sidecar FastAPI on localhost:8765
    │  extract_mono() → piped s16le via ffmpeg
    │  rms_per_hop() → 50ms energy windows
    │  detect_activity() → hysteresis gate (open 4×noise, close 2×noise)
    │  align_to_timeline() → apply per-source offset_frames
    │  decide_per_hop() → loudest wins, hold-last on silence
    │  enforce_min_shot() → absorb flicker < min_shot_hops
    │  hops_to_frames() → integer frames, one conversion, never float seconds
    ▼
CutMap JSON: {fps_numerator, fps_denominator, total_frames, cuts: [{frame, camera}]}
    │
    ▼  (Method A apply)
Clone active sequence → write onto assembly track via 3-point edit
    │  assertTimebase() — guard E5: sequence fps must match cut map
    │  cloneToNewSequence() — non-destructive: original never touched
    │  for each interval: srcIn = timeline_frame - offsetFrames (clamped)
    │  createSetInOutPointsAction(srcIn, srcOut) on ClipProjectItem
    │  createOverwriteItemAction(item, placeTickTime, targetTrack)
    ▼
New sequence with angle-switched assembly, zero sub-frame error
```

---

## Key invariants (from CLAUDE.md)

1. All time values are **integer ticks** (`String(frame * TICKS_PER_FRAME)`). No float seconds anywhere.
2. The cut engine operates in hop units; frames are derived once at the edge (`hops_to_frames`).
3. Output is always a **clone** of the input sequence — source is never touched.
4. The **E5 guard** (`assertTimebase`) must pass before any write operation.
5. No video leaves the machine. The sidecar receives audio paths only.

---

## Known issues and gaps

### Cosmetic: setActiveSequence doesn't open timeline in UI
`project.setActiveSequence(clone)` makes the clone API-active but Premiere's program
monitor still shows the original. The user must double-click the new sequence in the
Project panel to open it. No public UXP API to force-open a timeline was found.
M2 panel should display an instruction: "Double-click [sequence name] to open it."

### sidecar/requirements.txt missing
No requirements.txt exists in `sidecar/`. Current deps: `fastapi uvicorn numpy`.
Fixture generation additionally needs `opencv-python-headless`.

### Spike code is not production-ready
`adapters/premiere/spike/` is throwaway spike code. M2 will promote this to a proper
React+Spectrum panel under `/panel` with sidecar lifecycle management (start/stop uvicorn
from within the plugin) and a progress UI.

---

## Next milestones

### Immediate (no code needed)
- **Real footage regression** (footage arrives ~2026-06-15): load real 3-cam recording,
  run button 8. Expected to work unchanged. If VAD params need tuning, adjust
  `open_ratio`/`close_ratio`/`min_shot_s` in the /analyze request body.

### M2 — productization
1. Proper panel under `/panel`: React + Adobe Spectrum components
2. Sidecar lifecycle: start/stop uvicorn from within the panel (UXP `shell.exec` or
   bundled subprocess via Node adapter)
3. Progress UI: streaming log from sidecar during long /analyze calls
4. Cosmetic fix: instruct user to open the cloned sequence (or find open-timeline API)
5. Add `sidecar/requirements.txt`

### M3 — director tier (future)
LLM refinement layer receives transcript (never video), can override cut decisions.
BYOT: user provides their own model/API key. Designed in CLAUDE.md but not started.

---

## Regenerating test fixtures

```bash
cd tests/fixtures
../../.venv/bin/python generate_fixture.py
```

Produces: `cam1.mp4`, `cam2.mp4`, `cam3.mp4`, `audio_bed.wav`, `speech_schedule.json`.
Each mp4 has burned-in frame counter (OpenCV) and per-mic speech audio (AAC, 48kHz).

**Import into Premiere**: drag all 4 files into the Project panel root (not a bin).

---

## Debugging tips

- **Sidecar not reachable**: check it's running on port 8765, and that manifest has `"domains": "all"` (not explicit localhost — see BANANAS E8).
- **Wrong frame placements**: check `offsetFrames` in detection log; verify `srcIn = timeline_frame - offset` in apply path.
- **Sequence timebase error**: create the sequence via New Sequence From Clip on the source footage, not from a preset.
- **Panel changes not visible**: if you edited manifest.json, use UDT Unload → Load (not Reload).
- **`createSetInOutPointsAction` moves clips**: always set in/out on the `ClipProjectItem` BEFORE the overwrite action, never on a placed `TrackItem` (BANANAS E6).
