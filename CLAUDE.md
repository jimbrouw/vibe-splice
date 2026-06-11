# CLAUDE.md
## Standing context for Claude Code (model: Fable 5)

Read this in full at the start of every session. It is the ground truth for this repo. Where this file and the PRD addendum disagree, this file wins.

---

## Project

An AI multi-cam podcast editor that runs as a UXP panel inside Adobe Premiere Pro. It takes synced, stacked camera tracks for a 2 to 4 person podcast and produces a finished angle-switched cut. A deterministic local engine does the base switching from per-channel audio. An optional bring-your-own-token (BYOT) "Director" layer refines crosstalk and reaction shots.

- v1: Premiere Pro (UXP).
- v2: DaVinci Resolve (reuses the engine, new apply adapter).
- Build tool: Claude Code, Fable 5 model.
- Repo lives at a local path (for example C:\Projects\multicam-editor). Not on Google Drive. node_modules and Drive sync conflict.

---

## Hard rules (do not regenerate the PRD's mistakes)

1. **No scripted native multicam.** Premiere's native multicam angle switching is not scriptable in UXP or ExtendScript as of early 2026 (confirmed by Adobe staff). Do not build around "rewrite Active Camera Index" on a nested multicam clip. v1 uses stacked, synced camera tracks instead.

2. **Tick-accurate time only.** Build every edit point once as a `TickTime` snapped to a frame boundary. Never pass float seconds around the timeline write path. Float seconds are the source of sync drift, not the act of cutting.

3. **Cheap tier is pure DSP, no LLM.** One mic per person is the 80% case. "Who is active" is voice-activity detection. Do not call any model to decide the base switch. The LLM appears only in the Director tier (crosstalk, reaction shots).

4. **Non-destructive output.** Always write to a new or duplicated sequence. Never mutate the user's source sequence.

5. **Send audio or text, never video.** The Director tier and any cloud call receive low-bitrate mono audio or transcript text only. Source video never leaves the machine.

---

## Confirmed UXP API building blocks (Premiere 25.0+)

Entry: `const ppro = require("premierepro");`

Time:
- `ppro.TickTime.createWithSeconds(s)` builds a TickTime. Convert frame-snapped seconds to TickTime once, reuse it.
- `trackItem.getDuration()`, `getEndTime()` return TickTime.

TrackItem actions (on VideoClipTrackItem):
- `createSetDisabledAction(disabled: boolean)` enables or disables a trackItem.
- `createSetInPointAction(tickTime)`, `createSetOutPointAction(tickTime)` trim source in/out.
- `createSetStartAction(tickTime)`, `createSetEndAction(tickTime)` set position in sequence.
- `createMoveAction(tickTime)` shifts the inPoint.

Sequence editing (get editor: `ppro.SequenceEditor.getEditor(sequence)`):
- `createOverwriteItemAction(projectItem, time, vTrackIndex, aTrackIndex)`
- `createInsertProjectItemAction(projectItem, time, vTrackIndex, aTrackIndex, limitShift)` (creates a track if index exceeds existing)
- `createCloneTrackItemAction(trackItem, timeOffset, vOffset, aOffset, alignToVideo, isInsert)`
- `createRemoveItemsAction(trackItemSelection, ripple, mediaType, shiftOverLapping)`
- `getTrackItems(trackItemType, includeEmptyTrackItems)`

Known sharp edges:
- These action calls can throw "Script Action failed to execute" on bad params. Treat each as fragile and wrap with logging.
- No UXP method to add or rename tracks, and no documented vertical track-move, as of early 2026.
- All of the above is to be re-confirmed in the M0 spike before the product is built on it.

---

## Architecture

```
UXP Panel (React + Spectrum)
   | localhost HTTP + WebSocket
Python Sidecar (FastAPI)
   - FFmpeg: per-track audio from source media
   - VAD per channel -> activity blocks   (cheap tier, no model)
   - Whisper local -> transcript           (Director only)
   - pyannote OR Gemma 4 audio -> diarise  (20% mono case)
   - Cut engine -> NLE-agnostic cut map
   - BYOT gateway -> Director refinements
   | cut map (frame-accurate JSON)
Premiere Apply Adapter (UXP) -> new sequence
```

Sidecar is Python because FFmpeg, VAD, Whisper, pyannote, and Ollama are Python-native. No C++ Hybrid in v1.

---

## Repo map

```
CLAUDE.md            this file
TASK.md              current milestone + task + definition of done
CONTEXT.md           decisions log: what changed, why
BANANAS.md           error classes + ralph-loop scan
/panel               UXP plugin (React + Spectrum)
/sidecar             Python FastAPI
  /dsp /asr /diarize /director /cutengine
/adapters
  /premiere          apply adapter (depends on M0 spike)
  /resolve           v2 stub
/tests
  /fixtures          3 benchmark clips
  benchmark.py       speed + correction-rate harness
```

---

## Model choices (June 2026)

- Cheap tier switch: VAD only, no model.
- Transcription: Whisper local default, or BYO Deepgram/AssemblyAI key.
- Diarisation (20% case): pyannote, or Gemma 4 E4B/12B audio (chunk 30s).
- Director reasoning: Gemma 4 via Ollama (Apache 2.0, local) default, or BYO OpenAI/Gemini/Anthropic key. Director receives text, so Gemma 4's 30s audio limit does not apply there.

---

## BYOT contract

The Director never owns timecodes. The DSP base map owns them. The LLM receives transcript chunks with `segment_id`, speaker, and the proposed angle, and returns decisions keyed to `segment_id`. Deterministic code maps each decision back to the TickTime the DSP already computed.

LLM behaviour (crosstalk and reaction detection) is probabilistic and varies by model, audio quality, and accent. It is a suggestion layer the user reviews, not a guaranteed result. Build the review UI on that assumption.

---

## Session protocol

- Commit / resume / bananas. Each task ends with a working commit and a TASK.md update.
- New error classes go in BANANAS.md. Run a ralph-loop scan before moving on.
- Update CONTEXT.md whenever a decision changes, with the reason.

---

## How to work in this repo

- Start with the answer or the change, not preamble.
- Label uncertain claims: [Inference], [Speculation], [Unverified]. Do not chain inferences.
- Avoid the words Prevent, Guarantee, Will never, Fixes, Eliminates, Ensures, unless quoting a source.
- For any claim about model behaviour, add an uncertainty note.
- Simplify ruthlessly. Iterate on real output. Read git history before large changes.
- Structure for fast scanning: short lines, bullets, no dense walls of text.

---

## Spike status

M0 timeline-write spike: UNRESOLVED. Do not build the product until this is filled in.

Winning apply method: (to be set)
Exact API call sequence: (to be set)
Drift result on 10-minute 3-cam fixture: (to be set)
