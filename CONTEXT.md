# CONTEXT.md — decisions log

Newest first. Every entry: what changed, why.

## 2026-06-11 — Fixture is OpenCV-rendered, not drawtext
Both FFmpeg builds on this machine (Intel /usr/local and Homebrew 8.1.1) lack
the freetype-dependent `drawtext` filter. Frame counters are rendered with
OpenCV `putText` and piped to FFmpeg as rawvideo with `-r 30000/1001` so the
stream timebase stays an exact rational. Generator: `tests/fixtures/generate_fixture.py`.

## 2026-06-11 — Fixture rate is 29.97 (30000/1001) on purpose
Non-integer NTSC rate is the harshest screen for float-seconds drift, which is
the failure M0 exists to catch. One frame = exactly 8,475,667,200 ticks
(254016000000 / 30000 × 1001), so frame→TickTime can stay in integer math.

## 2026-06-11 — Spike panel written against [Unverified] API guesses
spike.js encodes the call patterns from CLAUDE.md + uxp-premiere-pro-samples
but marks every unconfirmed signature [Unverified]. Button 0 (probe) dumps the
live API surface; the panel gets corrected against that output before the
A/B/C runs count for anything.

## 2026-06-11 — Method A assembles onto V4, sources stay on V1–V3
Keeps the stacked sources intact so all three methods can run against
duplicates of one built sequence, and verify can compare like-for-like.

---

## M0 spike report — RESOLVED 2026-06-11 (live run, Premiere 25.6.3, macOS)

**Winning method: A — segmented overwrite assembly via 3-point edit.**

Exact API call sequence, per interval in the cut map:
```js
const ppro = require("premierepro");
const t = (frame) => ppro.TickTime.createWithTicks(String(frame * 8475667200)); // 29.97 only
const clip = ppro.ClipProjectItem.cast(camProjectItem);
const editor = await ppro.SequenceEditor.getEditor(sequence);

// inside project.lockedAccess(() => project.executeTransaction(cb)):
clip.createSetInOutPointsAction(t(iv.start), t(iv.end));        // source in/out FIRST
editor.createOverwriteItemAction(camProjectItem, t(iv.start),    // then place
                                 /*vTrack*/ 3, /*aTrack*/ -1);
// afterwards: clip.createClearInOutPointsAction() per camera
```
Each action ran in its own transaction; all 24 transactions succeeded with zero
errors on the 12-cut map.

Drift result (10-min 3-cam 29.97 fixture, burned-in frame counters):
| checkpoint | API readback | program monitor |
|---|---|---|
| early, frame 450 | startTicks % ticksPerFrame = 0, boundary exactly 450 | CAM2 / FRAME 450 |
| middle, frame 8991 | exact | CAM1 / FRAME 8991 (lands on the 300 s flash marker) |
| late, frame 17500 | exact | CAM3 / FRAME 17500 |
Worst sub-frame error across all 12 boundaries: **0.000**. No growing drift.

Split primitive: **clone+trim FAILED** ("Invalid parameter" on trimming the
clone) — which kills methods B (disable) and C (remove) as specified, since
both depend on in-place segmentation. Not pursued further: A passed the
acceptance bar and needs no split primitive at all. Removal machinery itself
works (used to clear V4): build a selection via `sequence.getSelection()`,
`sel.addItem(ti)`, then `editor.createRemoveItemsAction(sel, false, mediaType, false)`.
Note `TrackItemSelection.createEmptySelection(sequence)` throws Illegal
Parameter — use `sequence.getSelection()` instead.

Two traps found (recorded in BANANAS.md):
1. **Sequence timebase trap.** On a 25 fps sequence every placement snapped to
   the 25 fps grid (errors up to 0.45 frames, NOT growing). The apply adapter
   MUST verify the sequence timebase matches the footage before writing, or
   create the sequence itself (sequence created via "New Sequence From Clip"
   on cam1 was exactly 29.97 and gave the zero-drift result).
2. **Never trim after placement.** `trackItem.createSetInPointAction` on a
   placed item MOVES the item (start shifted by the in-point delta) instead of
   slipping content. Source in/out must be set on the ClipProjectItem before
   the overwrite (3-point edit model).

## 2026-06-11 — Other live-API findings
- `TickTime.createWithFrameAndFrameRate` and `createWithTicks` both exist;
  integer tick math (8,475,667,200 ticks/frame at 29.97) roundtrips exactly.
- Bins come back as plain `ProjectItem`; recurse with `ppro.FolderItem.cast`.
- `ClipProjectItem` exposes `createSetInOutPointsAction`,
  `createClearInOutPointsAction`, `getInPoint/getOutPoint`.
- `sequence.setPlayerPosition(tickTime)` works for programmatic playhead moves
  (used for checkpoint verification).
- UDT "Load & Watch" hot-reloads both JS and HTML on save.
