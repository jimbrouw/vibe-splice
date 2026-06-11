# TASK.md — current milestone

## Milestone: M0 timeline-write spike
Status: code ready, awaiting live run in Premiere

## The one question
Which UXP write method (A overwrite / B disable / C remove) produces an
angle-switched 3-cam cut with zero growing drift on a 10-minute fixture?

## Done so far (2026-06-11)
- Repo wired to github.com/jimbrouw/vibe-splice
- Stand-in fixture generator: `tests/fixtures/generate_fixture.py`
  (3 × 10 min @ 29.97, burned-in frame counters, 30s flash+beep sync markers)
- Hand-written cut map: `tests/fixtures/cutmap.json` (12 switches, 3 checkpoints)
- Spike panel: `adapters/premiere/spike/` (probe + build + split + A/B/C + verify)

## Next (needs Premiere open — user or screen access)
1. Load panel via UXP Developer Tool (see spike README)
2. Run button 0 (probe), paste output back — resolves all [Unverified] API guesses
3. Fix spike.js against real API surface
4. Run methods A/B/C each on a fresh duplicate of the test sequence
5. Record drift at frames 450 / 8991 / 17500

## Definition of done
- One method passes: correct angle per interval, zero growing drift at
  early/middle/late checkpoints
- Spike report in CONTEXT.md (winning method, exact call sequence, drift table)
- Spike status block in CLAUDE.md filled in
- New error classes in BANANAS.md
- If NO method passes: stop, report to PM (CEP fallback / wait on Adobe / cut-list-only v1)

## Blocked on
- Real 3-cam footage: arriving week of 2026-06-15 (stand-in fixture in use meanwhile)
