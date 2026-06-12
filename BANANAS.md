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

## E5 — Sequence timebase mismatch quantises every edit (hit 2026-06-11)
Symptom: cut boundaries land off by ≤0.5 frame with NO growth over time;
raw start ticks are exact multiples of a DIFFERENT frame duration (e.g. 1/25 s).
Cause: the sequence timebase differs from the footage rate; Premiere snaps all
placements to the sequence grid. Guard: apply adapter must check
`sequence.getTimebase()` against the footage rate (or create the sequence from
the footage) before writing a single edit.

## E6 — createSetInPointAction on a placed item MOVES it (hit 2026-06-11)
Symptom: segments appear at ~2× the intended position (e.g. 35000 for a cut
at 17500), order scrambled. Cause: trimming source-in on a trackItem already
in a sequence shifts the item rather than slipping content. Guard: 3-point
edit only — set in/out on the ClipProjectItem, then overwrite-place.

## E7 — API factory methods with undocumented required params (hit 2026-06-11)
Symptom: "Not Enough Parameters" / "Illegal Parameter type" from a documented
factory (`TrackItemSelection.createEmptySelection`). Guard: wrap every factory
in try/catch with a fallback path (`sequence.getSelection()` worked); log which
path was live.

## E8 — UXP network permission rejects explicit localhost domains (hit 2026-06-11)
Symptom: fetch throws "Plugin is not permitted to access the network apis"
despite a `network.domains` array in the manifest. Cause: entries like
"http://127.0.0.1:8765" are not accepted; and manifest changes are NOT picked
up by UDT Reload. Guard: use `"domains": "all"` for the localhost sidecar and
do UDT Unload + Load after any manifest edit.

## E4 — Stale trackItem handles after a transaction
Symptom: action on an item fetched before a clone/remove acts on the wrong
item or throws. [Inference, unconfirmed] Guard: re-query getTrackItems()
after every mutating transaction; never reuse pre-transaction handles.

## E9 — UXP JS runtime is missing modern web APIs (hit 2026-06-12)
Symptom: a feature silently never works (sidecar health dot stayed red while
the sidecar was demonstrably up). Cause: `AbortSignal.timeout()` does not
exist in Premiere's UXP runtime — the call throws inside a try/catch and the
handler swallows it. Same family: `Entry.getNativePath()` is not a function;
the native path is the `nativePath` PROPERTY on UXP storage entries.
Guard: never assume a web API exists in UXP. For fetch timeouts, race a
setTimeout promise. For native paths, read `.nativePath`. When a try/catch
wraps an API probe, log the caught error at least once instead of swallowing.

## E10 — shell.openPath needs launchProcess permission + per-user consent (hit 2026-06-12)
Symptom: `uxp.shell.openPath(path)` rejects with `undefined` as the error.
Cause: manifest lacked `requiredPermissions.launchProcess`. After adding
`"launchProcess": { "schemes": ["file"], "extensions": [".command"] }`
(and UDT Unload+Load — see E8), Premiere shows a "Request For Permission"
dialog naming the exact path, with Allow/Block and "Remember my choice".
Guard: ship the permission in the manifest, and document the first-run
dialog in user-facing setup steps — the panel's Start button does nothing
visible if the user blocked it once with "remember" ticked.
