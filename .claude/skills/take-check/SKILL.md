---
name: take-check
description: >
  Score raw talking-head takes on the spoken word before any edit, so a bad
  take is flagged at ingest and the best take is the one that gets cut.
  Reads mlx-whisper word JSON (pauses, fillers, restarts, slate chatter,
  hook length) and optionally a model judge for hook, single idea, and
  payoff. Use when the user says "check these takes", "which take is best",
  "score the A-roll", "is this take usable", "score the takes", "take check",
  or after organize-shoot transcription when Audio JSON is on disk and
  nothing has been cut yet.
metadata:
  version: 1.0.0
---

# Take check

Scores a raw talking take on what was said. It does not watch the picture, cut the clip, or touch the footage. Run it at ingest, after transcription, and cut the take it names.

Two layers. Layer 1 is deterministic and always runs: speech span, pauses, fillers, immediate repeats, restarts, slate chatter, hook length, whether the last word ends a sentence, low-confidence words, and silence hallucinations. Layer 2 is a model judge of structure (hook, one idea, payoff, clean end). The final verdict is the worse of the two.

## Command

```
python3 <skill>/scripts/take_check.py PATH [PATH ...] \
  --out-dir DIR \
  [--report FILE.md] \
  [--config path/to/reel-style.json] \
  [--context "what this take was meant to be"] \
  [--all | --prefix ARoll-,CB-] \
  [--judge none | --judge-cmd 'pi -p --no-tools --no-mcp ...'] \
  [--jobs 3] \
  [--fail-on red|yellow]
```

`PATH` is a whisper `.json` file or a shoot folder. A folder is scanned at `**/Audio/*.json`. By default only stems starting with `ARoll-` or `CB-` are kept. `--all` keeps every Audio JSON. `--prefix` replaces that list (comma-separated, or repeat the flag).

Pass `--context` from the content note's concept, in generic words if you are writing the command into a public file. The judge uses it. The script does not open or edit the content note.

Outputs go only to `--out-dir`: `<stem>.take.json`, plus a markdown report (default `<out-dir>/take-report.md`). A sibling `../Video/<stem>.{MP4,mp4,MOV,mov}` is probed with ffprobe for duration when it exists. A missing ffprobe is skipped. Nothing is written beside the footage.

Thresholds: `resources/take-check.example.json`. `--config` may be that block, or a JSON object with the block under a top-level `take_check` key (a client's `reel-style.json` can carry it). Missing keys fall back to the defaults.

The judge command is `judge_cmd` in that config. Default argv is `pi -p` with tools and MCP off. The prompt is written to the judge's stdin (confirmed: `pi --help` takes a trailing message, and with no message a piped prompt is read from stdin). Put `{prompt}` in an argv element to pass the prompt as an argument instead. `--judge none` skips layer 2. `--jobs` runs judge calls in parallel (default 3).

Exit codes: 0 done, 2 bad input or no takes found, 3 only with `--fail-on red` or `--fail-on yellow` when a take hits that level (`yellow` also fails on red).

## How to read the report

The table is sorted red, then yellow, then green, and within a color by structure score (highest first).

| column | meaning |
|---|---|
| take | transcript stem |
| length | file duration if ffprobe found it, otherwise the transcript end |
| verdict | worse of the metrics verdict and the judge verdict |
| use | what to do with the take (from the judge, or from metrics alone) |
| in-out | suggested source in and out, `mm:ss.s` |
| hook | the hook quote, trimmed to 60 characters |
| top reasons | why it is not green |

Yellow and red takes are repeated below the table. Each problem has a timestamp. "Takes of the same piece" groups stems that differ only by `-TakeN`, `-BCam`, `-PRIMARY`, `-Phone`, or `-False-Start`, and names the best: better verdict, then higher structure score, then fewer fillers. Cut that one. Leave the others.

`clean_in` in the JSON is the first word after slate chatter ("Ready?", "Yep.", "Action") in the first 8 seconds. Start the cut there unless the judge names a later in-point.

## Verdicts

- **green** — the spoken word is usable. `use: cut` when the judge agrees, or when only metrics ran and nothing soft fired.
- **yellow** — cut it only with a trim, or the judge has a note. Soft metrics: fillers over 4 per minute, more than 15% of words under 0.5 probability, a pause over 2.5 s, hook longer than 6 s from `clean_in`, last word does not end a sentence, or a 3- to 5-word restart inside 10 s. Metrics-only `use` is `trim`.
- **red** — do not cut this as the piece. Silent (fewer than 4 words, every segment `no_speech_prob` over 0.6, or the whole text is "thank you" / "thanks for watching" / "you"), speaking span under 4 s, or the judge says red. Silent takes are `use: none` and the judge is not called.

`use` from the judge may also be `reshoot`, `blooper`, or `voiceover`. Those mean the words are not this picture's A-roll, even if you keep the line.

## Must not

- Edit, rename, move, or delete footage, transcripts, or anything in the input folder. This skill only writes to `--out-dir`.
- Publish, schedule, or upload a take.
- Change a content note's status, the kanban, or any brief. Report the score. A person decides what gets cut.
