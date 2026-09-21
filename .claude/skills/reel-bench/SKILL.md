---
name: reel-bench
description: >
  Run the same reel task through several harnesses and models, then compare
  the manifests, QA verdicts, punch fit, cost, and wall time. Use when the
  user says "bench this reel", "compare models on this cut", "run the reel
  bench", "which model cuts this better", "model bake-off for this reel",
  or wants one comparison across pi / Claude / other harnesses on the same
  content note.
metadata:
  version: 1.1.0
---

# Reel bench

The factory makes a model comparison fair: every harness does the same
judgment work (read the brief, fill the manifest, choose punches) while
the render and the QA gate are identical code. What differs is the
manifest, how many dry runs it took to a clean preflight, the QA verdict,
whether the punches fit the spoken lines, cost, and wall time.

Script: `../cut-video/scripts/bench-reel.py`.
Task template: `../cut-video/resources/bench-task.template.md`.
Example config: `../cut-video/resources/bench.example.json`.

## When to run

- Before you trust a new model or harness on overnight cuts.
- When two models disagree on hook / cover / punches and you want one page
  of contact sheets, not six chat logs.
- After a skill or engine change, to see whether judgment quality moved
  (regress.py covers the engine; this covers the model).

Do not run this against live client footage from this toolkit repo. The
config `cwd` and `note` live in the client repo. This toolkit ships only
the runner, the template, and a placeholder config.

## Punch ladder (locked)

The task text tells every harness the same sourcing rule:

1. Video first from any raw clip in the index. Never a finished reel or
   another piece's A-roll.
2. Then an exact photo. Else stay on the speaker.
3. Never a same-category picture.
4. At most two stills, never back to back. Each still starts within 0.3 s
   of the noun it shows.
5. Every punch carries `line` (spoken words) and `shows` (what the picture
   literally shows, written after looking at it).
6. Lines left un-punched on purpose are listed in the final summary with
   the reason. Leaving a line un-punched because nothing exact exists is
   correct.

Set `task.broll_index` to the library index path. The task then tells the
model to search with `broll-search.py --index {index} --lines-from-manifest`
and to look at the sheet before choosing. When that key is unset, the
search line is omitted.

## Run

Copy the example config. Point `cwd`, `note`, `style`, `output_root`, and
`skill_dir` at real paths. Keep `deliver.copy_to` unset; the task text
forbids writing outside `output_root`.

```
python3 <skill>/scripts/bench-reel.py --config bench.json \
  --concurrency 2 \
  --report DIR/bench-report.md \
  --html DIR/bench-report.html
```

- `--only id,id` limits the set.
- `--concurrency` bounds model sessions (default 2, or the config value).
  Encodes already serialize on the render lock.
- `--dry-run` writes each `task.md` and prints the exact commands. It does
  not launch a harness.
- `--report-only` scores whatever is already in the output dirs.
- `--verifier-cmd CMD` overrides the verifier stage. The command reads the
  prompt on stdin and must print the JSON.
- `--grades FILE` is the owner's grades, keyed by harness id. Computes
  verifier agreement and writes `grades-merged.json`.
- Exit 0 = every harness produced a scorable render (a missing optional
  binary is skipped, not a failure). Exit 3 = at least one harness failed
  to render or timed out. Exit 2 = config problem.

Adapters: run the same task through each harness you have installed.
The runner knows `pi` (via `$PI_RUN` or `pi-run` on PATH), `claude`, and
best-effort shells for `codex`, `grok`, and `cursor`. Skip any binary that
is not installed.

Config keys beyond the harness list: `task.broll_index` (optional index
path), `task.deliver_to` (optional review folder), `verifier` (kind,
provider, model, thinking, alternate).

## Verifier stage

After each harness is scored, a fresh-context verifier grades punches from
the contact sheet. It sees the sheet path, the punch table (index, time,
kind, `line`, `shows`, file basename), the un-punched transcript beats, and
the rubric. Nothing else. It does not search the library and it does not
edit the harness manifest.

Rubric:

- `exact`: the picture literally shows the noun phrase in `line`.
- `category`: the same kind of thing but not what the line names (a hallway
  for "hallway full of doors", a door for "hidden door").
- `wrong`: something else.

Un-punched beats get `should_have_punched: true|false` judged only from
that run's `shows` texts or the visible sheet.

Default verifier config (in the example):

```
"verifier": {
  "kind": "pi",
  "provider": "openai-codex",
  "model": "gpt-6-astra",
  "thinking": "high",
  "alternate": {
    "kind": "pi",
    "provider": "anthropic",
    "model": "claude-opus-5"
  }
}
```

If the harness under test is the same model family as the verifier
(provider match, or a model prefix of `gpt`, `claude`, `grok`, `gemini`,
`muse`), the alternate is used. Example command shape (read-only; your
harness binary may differ):

```
<harness> --cwd {cwd} --provider P --model M --thinking T --tools read --json --spec-file …
```

`--verifier-cmd` replaces that whole stage.

Output:

- `<stem>.grades.json` beside the render:
  `{"punches": [{"index": 0, "grade": "exact|category|wrong", "by": "verifier"}]}`
- `verifier.json` in the harness dir (raw output, model, cost, wall).

Verifier cost and wall time are their own report columns. They are never
folded into the harness cost.

## How to read the report

Open `bench-report.md` or the HTML. Rows are ranked: zero `wrong` and zero
`category` first; then fewest `missed`; then gate fails 0, preflight warns
0, stray writes 0; then cost, then wall. `video.static_gap` is listed in
fails but never scored.

Columns: produced, QA, fail/warn ids, duration, punch count, `exact`,
`category`, `wrong`, `unpunched_ok` (beats correctly left alone), `missed`
(beats the verifier says should have had a punch), `stills`,
`video_punches`, remaining preflight warns, renders, dry runs, stray
writes, wall, cost, verifier wall, verifier cost.

Then read one section per harness: cover line, hook decision, the punch
table (time, kind, file, spoken line, `shows`, verifier grade, owner grade
when `--grades` was passed), QA details, known deviations, stray writes,
and the contact sheet. The HTML embeds every sheet on one page so you can
compare them side by side.

`--grades FILE` shape:
`{"<harness id>": {"punches": [{"index": 0, "grade": "exact|category|wrong"}]}}`.
Owner grades are ground truth. Agreement is matching grades over graded
punches, printed per harness and overall.

`task.deliver_to`, when set, copies each harness's newest proxy, RUNNOTES,
sheet, and the report (md + html) into that folder with the harness id
prefixed on the filenames. Skip the key when you do not want a review
folder copy.

## Must not

- Put client names, real footage paths, or dollar figures from a live
  bench into this toolkit. Reports stay in the client `output_root`.
- Revert stray writes. The bench only reports them.
- Raise concurrency until the machine is swapping. Two at a time is the
  intended default.
