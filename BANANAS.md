# BANANAS.md — error classes

Known failure classes and how to recognise them. Run a ralph-loop scan
(re-read this file, grep the codebase for each class) before closing a task.

## E1 — Float seconds in the write path
Symptom: cuts land a frame off, error grows toward the end of the timeline.
Cause: seconds-as-float passed to TickTime per edit point instead of integer
frame→tick math done once. Guard: only `frameToTickTime()` builds TickTimes.

## E2 — "Script Action failed to execute"
Symptom: opaque throw from any create*Action call. Cause: bad params (wrong
track index, time outside item bounds, wrong object type). Guard: every action
goes through `safe()` with params logged before the call.

## E3 — FFmpeg build missing drawtext
Symptom: `No such filter: 'drawtext'` (hit 2026-06-11 on both local builds).
Guard: fixture generation renders text with OpenCV instead; any future
drawtext use must probe `ffmpeg -filters` first.

## E4 — Stale trackItem handles after a transaction
Symptom: action on an item fetched before a clone/remove acts on the wrong
item or throws. [Inference, unconfirmed] Guard: re-query getTrackItems()
after every mutating transaction; never reuse pre-transaction handles.
