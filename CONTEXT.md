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

## M0 spike report (to be filled by the live run)

Winning method: (pending)
Exact API call sequence: (pending)
Drift at frame 450 / 8991 / 17500: (pending)
Split primitive that worked: (pending)
