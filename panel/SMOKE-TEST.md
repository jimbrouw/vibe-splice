# Vibe Splice panel — smoke-test plan

Repeatable checklist for verifying the M2 panel after any change.
First full pass: 2026-06-12, all steps green (see TASK.md).

## Prereqs
- Premiere 25.x with UXP developer mode on, project with a synced stacked
  multicam sequence active (fixtures: `tests/fixtures/cam1..3.mp4` on V1–V3).
- Plugin loaded in UDT (`panel/manifest.json`, Load & Watch).
- `.venv` exists at repo root with `sidecar/requirements.txt` installed.
- Sidecar NOT running (the test starts it via the panel).

## Checklist

### 1. Boot
- [ ] Panel opens via Window ▸ Extensions ▸ Vibe Splice (or auto-opens on load)
- [ ] Log shows "Vibe Splice M2 panel loaded." and the 3 usage steps
- [ ] `panel-log.txt` created under
      `~/Library/Application Support/Adobe/UXP/PluginsStorage/PPRO/25/Developer/com.vibesplice.panel/PluginData/`
- [ ] Dot is RED "Sidecar offline"; Analyze & Apply is DISABLED

### 2. Sidecar lifecycle (Start button)
- [ ] Click Start → Terminal opens running `sidecar/start.command`
      (first run: Premiere shows a Request For Permission dialog naming
      `<repo>/sidecar/start.command` — Allow. See BANANAS E10.)
- [ ] Within ~5 s the dot flips GREEN "Sidecar online" with no user action
- [ ] Analyze & Apply becomes ENABLED

### 3. Detection
- [ ] Click Detect Sources → camera list fills: C1/C2/C3 badges, clip names,
      per-cam offsets in frames
- [ ] Log shows camera count, total frames, target track, FPS rational
- [ ] Offsets match the sequence (trimmed/shifted cam shows non-zero offset)
- [ ] Negative test: activate a non-multicam sequence → clear error "need ≥2
      synced single-clip video tracks", no crash.
      NOTE (2026-06-12): "04 Music" is NOT a valid negative case — it is the
      25 fps 3-cam rig from the M0 E5 test and detects as a multicam. Build a
      true negative (e.g. New Sequence From Clip on audio_bed.wav).

### 4. Pipeline (Analyze & Apply)
- [ ] Progress bar animates: indeterminate during detect/analyze, then
      per-cut percentage during apply
- [ ] A NEW sequence appears in the Project panel (item count +1);
      the source sequence is untouched
- [ ] Log: cut count, "timebase: … (expected …)" matching, clone name,
      final OK line
- [ ] Green hint box: "✓ Done — <name> is ready. Double-click it in the
      Project panel to open the timeline."
- [ ] Open the clone: assembly track holds the cut segments; spot-check a
      burned-in frame number against the playhead (fixtures only)
- [ ] Mixed-rate run (PASSED 2026-06-12): a 25 fps multicam sequence with
      29.97 media runs end-to-end correctly — the panel derives fps from the
      sequence, so the whole pipeline is consistent at the sequence rate.
      Bonus finding: the audio bed outlasting the video media exercised the
      tail-clamp/skip path organically (clamped intervals logged, impossible
      intervals skipped with ERR, run completed).
      NOTE: the E5 guard cannot fire in the panel flow (fps comes FROM the
      active sequence); it protects only the detect→apply race where the
      user switches sequences mid-run. Don't write a test expecting E5 to
      refuse a 25 fps sequence — that was spike-era behaviour with a
      hardcoded 29.97 cut map.

### 5. Resilience
- [ ] Kill the sidecar (`pkill -f "uvicorn app:app"`) → dot returns to RED
      within ~5 s; Analyze & Apply disables
- [ ] Click Analyze & Apply mid-flight twice → second click ignored
      (state.running guard)
- [ ] Clear log button empties the log pane

## Known footguns (don't re-debug these)
- Manifest edits need UDT **Unload + Load**, not Reload (E8).
- JS edits hot-reload via Watch — but the panel state resets (camera list
  clears); re-detect before re-running.
- `AbortSignal.timeout`, `Entry.getNativePath()` do not exist in UXP (E9).
- If Start does nothing and no dialog appears, the user may have clicked
  Block + "Remember my choice" once (E10) — reset in Premiere's plugin
  permission settings.
