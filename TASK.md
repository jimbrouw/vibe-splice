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

## Next milestone: M1 (per CLAUDE.md architecture)
Suggested first tasks, pending PM confirmation:
1. Swap stand-in fixture for real 3-cam podcast footage (arriving week of
   2026-06-15) and re-run the A-method spike once as regression
2. Start the Python sidecar skeleton: FastAPI + FFmpeg per-track audio
   extraction + VAD activity blocks (cheap tier, no model)
3. Define the NLE-agnostic cut-map JSON contract (frames + fps rational +
   camera index, as in tests/fixtures/cutmap.json)

## Blocked on
- Real footage (next week)
- PM go-ahead for M1 scope
