---
name: reel-regress
description: >
  Re-render the reference reels (fixtures) through the current engine and
  compare each to its gold render and expectations, so an engine change is
  proven before it ships. Use when the user says "run the fixtures", "regress
  the cutter", "did the engine change break anything", "add this as a
  fixture", or after any edit to cut-video.py, finish-reel.py,
  stills-to-broll.py, render-reel.py, or qa-reel.py.
metadata:
  version: 1.0.0
---

# Reel regress

Turns "the skill works" into a command with an exit code. A fixture is a real reel the reviewer once approved, described as a reel manifest plus a descriptor with expectations and an optional gold file. Fixtures live in the **client's** repo (they reference real footage); this toolkit ships only the runner and an example descriptor.

Script: `../cut-video/scripts/regress.py`. Example descriptor: `../cut-video/resources/fixture.example.json`. The runner calls `render-reel.py` and `qa-reel.py` from the same folder and never runs two renders at once.

## Run

```
python3 <skill>/scripts/regress.py --fixtures client/outputs/edit-lab/fixtures \
  --run-dir client/outputs/edit-lab/runs/regress-YYYYMMDD --proxy \
  --report REPORT.md --json REPORT.json --keep
```

- `--proxy` (default) renders 540x960 drafts: minutes per fixture instead of tens of minutes. `--final` for a release check.
- `--only A,B` limits the set. `--skip-render` re-evaluates the newest existing render.
- Exit 0 = every fixture met its expectations; 3 = at least one did not; 2 = setup problem.

Read the report table first (result, render time, duration, QA verdict, punches found vs expected, gold deltas), then the per-fixture failure details. Gold SSIM is advisory unless the descriptor sets `ssim_min`; proxies are compared to gold after scaling both to 540x960, so treat that number as soft.

## When to run

- After any change to an engine script, before committing it.
- After changing `platform-specs.json` (safe zones move captions; loudness targets move the audio check).
- After a reviewer-found defect is turned into a fixture (see `../cut-video/CHECKLIST.md`, "Incident to fixture"): the new fixture must FAIL on the old engine and PASS on the fixed one.

## Add a fixture

1. Pick an approved reel. Copy its resolved `*.reel.json` from beside the render into the fixtures folder as `<name>.reel.json`; keep every path absolute.
2. Write `<name>.fixture.json` (copy the example): expected duration window, punch count, hook present, cover text, QA verdict, and the gold mp4 path if the reviewer signed one off.
3. Run `--only <name>` once and confirm it passes. Commit both files in the client repo.

## Must not

- Edit a fixture to make a failing engine pass. Fix the engine, or record why the expectation changed in the descriptor's `notes`.
- Run with two fixture sets on the same machine at once; the render lock serializes encodes but the reports would interleave.
- Put fixture files (they carry real footage paths and project names) into this toolkit.
