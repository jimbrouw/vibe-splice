# TASK M0: Timeline-Write Spike
## Paste this into Claude Code (Fable 5) as the first work block. Throwaway code. Do not build the product yet.

---

## The one question

What is the viable way, in current Premiere Pro UXP, to write an angle-switched edit to a timeline so that a 3-camera podcast cuts between angles with no audio-to-video drift?

Everything in this project depends on the answer. Resolve it before writing any product code.

---

## Why this matters

Adobe confirmed (late 2025, PPro developer forum) that creating or switching a native multicam clip is not scriptable in UXP or ExtendScript, with no date promised. So the PRD's "rewrite Active Camera Index on a nested multicam clip" method is not available. We must find a different, real method. This spike proves which one survives on real footage.

---

## Setup checklist

- Install the Adobe UXP Developer Tool.
- Enable developer mode in Premiere: Settings, Plugins, Enable developer mode, then restart.
- Clone the official samples: `AdobeDocs/uxp-premiere-pro-samples`. Load the `premiere-api` reference panel and use it to probe the live API.
- Keep the TypeScript declarations open: `adobe/premierepro-types`.
- API reference: developer.adobe.com/premiere-pro/uxp.

---

## Confirmed building blocks (Premiere 25.0+)

Entry: `const ppro = require("premierepro");`

Time:
- `ppro.TickTime.createWithSeconds(s)` builds a TickTime. Snap seconds to the sequence frame boundary first, then build the TickTime once. Reuse it. Do not pass float seconds into edits.

TrackItem actions (VideoClipTrackItem):
- `createSetDisabledAction(disabled)` enable or disable a clip.
- `createSetInPointAction(tickTime)`, `createSetOutPointAction(tickTime)` trim source in/out.
- `createSetStartAction(tickTime)`, `createSetEndAction(tickTime)` set sequence position.

SequenceEditor (`ppro.SequenceEditor.getEditor(sequence)`):
- `createOverwriteItemAction(projectItem, time, vTrackIndex, aTrackIndex)`
- `createCloneTrackItemAction(trackItem, timeOffset, vOffset, aOffset, alignToVideo, isInsert)`
- `createRemoveItemsAction(trackItemSelection, ripple, mediaType, shiftOverLapping)`
- `getTrackItems(trackItemType, includeEmptyTrackItems)`

Note: these action calls are known to throw "Script Action failed to execute" on bad params. Wrap each in try/catch with full logging of the params passed.

---

## First sub-question: the split primitive

There is no obvious single "razor at time T" call. Before testing the three methods, find the reliable way to produce a segment boundary. Candidates to test:
- Clone a clip, then trim the original and the clone to adjacent in/out points.
- Overwrite-place a trimmed source segment at a position.
- Any split exposed on SequenceEditor or trackItem that the reference panel reveals.

Document the one that works cleanly. The three methods below build on it.

---

## The three candidate methods to test

Build a small synced 3-camera test sequence first (3 video tracks, one audio bed, all aligned). Then implement each method against a known cut map (a hand-written list of 8 to 12 angle switches over the clip).

**Method A. Segmented overwrite assembly (single track)**
- For each interval in the cut map, overwrite-place the chosen camera's trimmed segment onto one V track at the interval start.
- Uses `createOverwriteItemAction` plus in/out trims.

**Method B. Stacked plus disable**
- Stack the three cameras on V1, V2, V3.
- Segment each track at the switch points.
- Use `createSetDisabledAction` so exactly one camera is enabled per interval.

**Method C. Stacked plus remove**
- Stack and segment as in B.
- Use `createRemoveItemsAction` to delete the non-chosen segments per interval, leaving the chosen angle.

---

## The drift rule (apply to all three)

- Read the sequence frame rate. Snap every cut point to a whole frame.
- Build each cut point as a TickTime once, from the snapped frame, not from float seconds.
- After applying, verify each segment boundary lands on the intended frame.

---

## Test footage

- A real or stand-in 3-camera podcast clip, at least 10 minutes, all angles synced, with a shared or per-camera audio reference that lets you check sync.
- Put it in `/tests/fixtures`.

---

## How to measure drift

- After applying a method, step the playhead to several known cut points (early, middle, late in the 10 minutes).
- Confirm the video switches on the exact frame the cut map specifies and the audio stays aligned to picture.
- Record any frame offset at each checkpoint. A late-timeline offset that grows is the drift failure we are screening for.

---

## Acceptance criteria

One method produces a correct angle-switched sequence on the 10-minute, 3-camera fixture with zero growing drift, measured at early, middle, and late checkpoints. That method wins.

---

## Deliverables

1. A short spike report in CONTEXT.md: which method won, the exact API call sequence it used, and the drift results at each checkpoint.
2. Fill in the Spike status block in CLAUDE.md (winning method, call sequence, drift result).
3. The throwaway spike code committed under `/adapters/premiere/spike/` so the M2 apply adapter can reuse the proven calls.
4. Any new error classes added to BANANAS.md.

---

## Escalation

If none of A, B, or C reaches the acceptance bar, stop and report to the PM before building further. That outcome means one of:
- Use CEP for the apply layer in v1 while keeping the UXP panel for UI, or
- Wait on Adobe's promised multicam API, or
- Narrow v1 scope to outputting a cut list the user applies by hand.

Better to surface this in week one than to discover it at M2.

---

## Guardrails

- This is throwaway probe code. Do not start the product, the sidecar, or the BYOT gateway in this task.
- Do not call any model. This task is pure timeline-write mechanics.
- Keep the test sequence and cut map simple and hand-checkable.
