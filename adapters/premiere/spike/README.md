# M0 spike panel — load instructions

Throwaway probe code. Do not reuse as product structure; the M2 apply adapter
reuses only the *proven call sequences* recorded in CONTEXT.md.

## Load

1. Premiere 25.0+, developer mode enabled (Settings → Plugins), restarted.
2. Open the **UXP Developer Tool** → Add Plugin → select this folder's
   `manifest.json` → Load.
3. In Premiere: Window → UXP Plugins → M0 Spike (if not auto-shown).

[Unverified] `host.app` value in manifest.json is `"premierepro"`. If UDT
rejects it, check the value used in `AdobeDocs/uxp-premiere-pro-samples`
manifests and correct it.

## Prepare the project (manual, once)

1. Run `python3 tests/fixtures/generate_fixture.py` (already done if
   cam1/2/3.mp4 + audio_bed.wav exist).
2. New Premiere project. Import the 4 fixture files into the **root bin**
   (the panel finds them by exact name there).
3. Create an empty sequence: 1280×720, **29.97 fps** (30000/1001). Make it
   the active sequence.

## Run order

| Button | What it does | What to check |
|---|---|---|
| 0 Probe | Dumps live API surface | Paste output back into the Claude session — it resolves every [Unverified] in spike.js |
| 1 Build | Stacks cam1/2/3 on V1/V2/V3 + bed on A1 | All four clips start at 0, fully synced |
| 2 Split | Splits V1 at frame 450 via clone+trim | Two items, boundary exactly at burned-in FRAME 450 |
| 3a/3b/3c | The three candidate methods | Each on a FRESH copy of the built sequence (duplicate it first) |
| 4 Verify | Reads back item boundaries vs cut map | Zero sub-frame error; then eyeball frames 450 / 8991 / 17500 |

The burned-in FRAME counter is ground truth. The 30 s white-flash/beep pair
checks audio-to-video alignment late in the timeline.
