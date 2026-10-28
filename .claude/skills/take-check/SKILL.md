---
name: take-check
description: >
  Score raw talking-head takes on the spoken word before any edit, so a bad
  take is flagged at ingest and the best take is the one that gets cut.
  Reads mlx-whisper word JSON (pauses, fillers, restarts, slate chatter,
  hook length) and optionally a model judge that finds the usable windows
  of each take and grades the best one. Use when the user says "check these
  takes", "which take is best", "score the A-roll", "is this take usable",
  "score the takes", "take check", or after organize-shoot transcription
  when Audio JSON is on disk and nothing has been cut yet.
metadata:
  version: 1.1.0
---

# Take check

Scores a raw talking take on what was said. It does not watch the picture, cut the clip, or touch the footage. Run it at ingest, after transcription, and cut the window it names.

Two layers. Layer 1 is deterministic and always runs: speech span, pauses, fillers, immediate repeats, restarts, slate chatter, hook length, whether the last word ends a sentence, low-confidence words, and silence hallucinations. Layer 2 is a model judge. It finds 0 to 3 usable **windows** in the take and the tool grades the **best window**, not the whole raw take. The final verdict is the worse of the hard metrics, the soft metrics measured inside the best window, and the judge verdict after the code enforces the window rules.

## Command

```
python3 <skill>/scripts/take_check.py PATH [PATH ...] \
  --out-dir DIR \
  [--report FILE.md] \
  [--config path/to/reel-style.json] \
  [--context "what this take was meant to be"] \
  [--kind tip|episode|line] \
  [--all | --prefix ARoll-,CB-] \
  [--judge none | --judge-cmd '...'] \
  [--no-judge-cache] \
  [--calibrate labels.json] \
  [--jobs 3] \
  [--fail-on red|yellow]
```

`PATH` is a whisper `.json` file or a shoot folder. A folder is scanned at `**/Audio/*.json`, and an `Audio/` folder is used only when its parent also holds a `Video/` folder (a shoot folder). Stray nested `Audio/` folders, such as `Video/Audio/`, are skipped and named in one line on stderr. By default only stems starting with `ARoll-` or `CB-` are kept. `--all` keeps every Audio JSON. `--prefix` replaces that list (comma-separated, or repeat the flag).

Pass `--context` from the content note's concept, in generic words if you are writing the command into a public file. The judge uses it. The script does not open or edit the content note.

Outputs go only to `--out-dir`: `<stem>.take.json`, a markdown report (default `<out-dir>/take-report.md`), and the judge cache `<out-dir>/.judge-cache/`. A sibling `../Video/<stem>.{MP4,mp4,MOV,mov}` is probed with ffprobe for duration when it exists. A missing ffprobe is skipped. Nothing is written beside the footage.

Thresholds: `resources/take-check.example.json`. `--config` may be that block, or a JSON object with the block under a top-level `take_check` key (a client's `reel-style.json` can carry it). Missing keys fall back to the defaults.

Exit codes: 0 done, 2 bad input or no takes found, 3 only with `--fail-on red` or `--fail-on yellow` when a take hits that level (`yellow` also fails on red). `--calibrate` never changes the exit code.

## The judge

`judge_cmd` in the config is the judge argv. The default is Claude Code in print mode on Sonnet, with no tools, no MCP servers, no settings sources (so no hooks or CLAUDE.md), no saved session, and a short judge system prompt:

```
claude -p --model claude-sonnet-5-5 --tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --setting-sources "" --disable-slash-commands --no-session-persistence --system-prompt "You are a strict scoring judge. Reply with one JSON object and nothing else."
```

The judge runs with its working directory set to a fresh empty temp dir, so no project instructions load. The prompt is written to stdin. Put `{prompt}` in an argv element to pass the prompt as an argument instead. A reply wrapped in markdown fences is fine; the tool pulls the first JSON object out of it.

Grok through pi is the alternative judge:

```
--judge-cmd 'pi -p --no-tools --no-mcp --model xai/grok-4.7 --thinking low'
```

`--judge none` skips layer 2. `--jobs` runs judge calls in parallel (default 3). A failed or unparseable reply is retried once with "Reply with JSON only"; after that the take falls back to metrics only.

**Cache.** A valid judge reply is saved in `<out-dir>/.judge-cache/<sha256 of prompt + judge_cmd>.json`. A re-run with the same prompt and judge reads it and does not call the judge. A changed prompt template, transcript, context, kind, or judge command misses the cache by itself. `--no-judge-cache` neither reads nor writes it.

## Take kinds

Each take has a kind. It goes into the prompt and changes the rules.

| kind | what it is | rules |
|---|---|---|
| `tip` (default) | a standalone short point for a stranger | stranger hook, one idea, payoff, self-contained. `hook_max_s` soft flag applies. |
| `episode` | walkthrough, progress update, tour: part of a project series the audience follows | references to the project, the client, "this room", or earlier visits are not `context_missing`. The first window opens on a clear line; no stranger hook needed. |
| `line` | a one-liner or reel opener | judged only on whether the line is clean and complete. |

Inference, per take: `line` when the take is not silent and its speaking span is under `min_window_s` (default 8 s). Otherwise `episode` when a stem token (split on `-` and `_`, any case) matches `episode_keywords` (default Walkthrough, Walk, Progress, Update, Tour, Episode, Monthly). Otherwise `tip`. `--kind` sets the kind for every take in the run.

## Windows and verdicts

A window is at least `min_window_s` long, holds one idea, opens on a clear line, and ends on a complete sentence. A take shorter than `min_window_s` cannot hold a full window, so its minimum is its own clean speaking span (from `clean_in` to the last word); such a take is not red for being short. Long takes are expected to hold several windows with rambles between them.

The code, after the reply:

- Snaps every window in/out to word boundaries. Drops a window that is shorter than the minimum (0.5 s slack), and keeps at most 3. Dropped windows are listed in `judge_dropped` with the reason.
- Checks each window's `hook_quote` and `payoff_quote` verbatim against the transcript. A failed quote is nulled and listed in `judge_dropped`; the window stays.
- Picks the best window (highest score, earliest on a tie). `suggested_in` / `suggested_out` are its in and out. `structure_score` is its score (1 when there is no window).
- Enforces the verdict:
  - **red** only when there is no valid window. `use` is then `reshoot`, `blooper`, or `voiceover` (`cut`/`trim` become `reshoot`).
  - A judge **red** with a valid window becomes **yellow**, and `use: reshoot` becomes `trim`.
  - **green** needs a best-window score of 4 or 5 and no judge problem inside the best window; otherwise it becomes yellow. The code never raises a judge yellow to green.
  - Each correction is listed in `judge.corrections`; `judge.claimed_verdict` keeps what the judge said.
- Re-measures the soft metrics on the words inside the best window (`window_flags`). Whole-take soft flags stay in `flags` for reference, but a pause, filler run, or restart outside the best window does not lower the verdict. Problems outside the best window are listed with `in_best_window: false`.

Metric thresholds:

- **Hard (red):** silent (fewer than 4 words, every segment `no_speech_prob` over 0.6, or the whole text is "thank you" / "thanks for watching" / "you"), or speaking span under `min_speech_s` (4 s). Silent takes are `use: none` and the judge is not called.
- **Soft (yellow):** fillers over 4 per minute, more than 15% of words under 0.5 probability, a pause over 2.5 s, last word does not end a sentence, restarts over 3 per minute, and for `tip` only a hook longer than 6 s from the in-point.
- **Restarts:** a run of 4 to 6 words that repeats within 6 s, or a 3-word run said twice back to back ("the reason we the reason we do this"). A run made only of stopwords (I, you, we, it, the, a, to, be, is, going, gonna, ...) never counts, so "it is going to be" said twice is normal speech. Every restart is listed in `metrics.restarts`; the rate is `metrics.restarts_per_min`.

Without a judge, the verdict comes from the whole-take metrics. Metrics-only `use` is `cut` (green), `trim` (yellow), or `none` (red).

`use` from the judge may also be `voiceover` or `blooper`. Those mean the words are not this picture's A-roll, even if you keep the line.

## How to read the report

The table is sorted red, then yellow, then green, and within a color by structure score (highest first).

| column | meaning |
|---|---|
| take | transcript stem |
| kind | tip, episode, or line |
| length | file duration if ffprobe found it, otherwise the transcript end |
| verdict | worse of the hard metrics, the best-window metrics, and the enforced judge verdict |
| use | what to do with the take (from the judge, or from metrics alone) |
| in-out | the best window's source in and out, `mm:ss.s` |
| hook | the best window's hook quote, trimmed to 60 characters |
| top reasons | why it is not green |

Yellow and red takes are repeated below the table with every window (best marked), code corrections, the best-window flags, and judge problems with timestamps. "Takes of the same piece" groups stems that differ only by `-TakeN`, `-BCam`, `-PRIMARY`, `-Phone`, or `-False-Start`, and names the best: better verdict, then higher structure score, then fewer fillers. Cut that one. Leave the others.

`clean_in` in the JSON is the first word after slate chatter ("Ready?", "Yep.", "Action") in the first 8 seconds. Without a judge, start the cut there.

## Calibration

`--calibrate labels.json` checks the tool against what a reviewer did. The file is `{"<stem>": "ok" | "bad"}`: `ok` means a reviewer cut and posted or approved the take; `bad` means rejected, a false start, or a reshoot. After the run the tool prints a Calibration section and adds it to the report:

- counts of ok to green/yellow/red and bad to green/yellow/red;
- every **false red** (ok that came out red) and **false green** (bad that came out green), with the reason;
- stems in the file that were not in this run.

Use it after changing the prompt or thresholds. False reds are the expensive error: a usable take that nobody cuts. Keep the labels file outside the repo if the stems name a real project.

## Must not

- Edit, rename, move, or delete footage, transcripts, or anything in the input folder. This skill only writes to `--out-dir`.
- Publish, schedule, or upload a take.
- Change a content note's status, the kanban, or any brief. Report the score. A person decides what gets cut.
