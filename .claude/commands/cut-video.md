---
description: Read a content note's editor brief + source transcript, propose a transcript-driven cut, render via ffmpeg on approval
argument-hint: /path/to/content-note.md
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
---

# Cut Video From Content Note + Transcript

Produce a rough cut for a content piece by reading its content note (Editor Brief + Script), locating the source video and Whisper JSON transcript, proposing a brief-faithful cut plan, and rendering with the existing filler-removal + pause-compression engine.

**This is a strategic + technical workflow.** You read the brief, decide what to keep, surface gaps to the user, and only render after they approve. You do not silently jump to ffmpeg.

## Arguments

User provided: $ARGUMENTS

Parse for the content note path. If none provided, ask:
1. "Which content note? (path under `clients/[client]/outputs/content/`)"

---

## Workflow

### Step 1: Read the content note

Read the full note. Capture from frontmatter and the Editor Brief / Script sections:

- `source_footage` — locate the source video and its sibling Whisper JSON. If the field references a clip filename, look for it under the shoot folder and find `Audio/<basename>.json`.
- `duration` / target length — usually "45-60s" or "Reel 45-60s" or similar.
- `format` — aspect ratio (vertical 9:16, square, landscape).
- `Editor Brief` → `What to Make` — the strategic intent of the piece.
- `Editor Brief` → `Edit Direction` — opening shot, chyron timing, B-roll usage, closer, end frame.
- `Script` section — the actual words wanted, broken into sections with target durations.
- `Voice notes` — lines that must not be cut, candidate alternates for missing lines.

If `source_footage` is vague or the file can't be found, **ask the user for the path before continuing.** Do not guess.

### Step 2: Locate transcript JSON

The JSON is produced by `/organize-shoot` and lives next to the audio file. Verify it exists and has word-level timestamps:

```bash
test -s "/path/to/Audio/<basename>.json" && \
  /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -c "
import json,sys
d=json.load(open('/path/to/Audio/<basename>.json'))
seg=d['segments'][0]
print('words present:', 'words' in seg)
"
```

If `words` is not in segments, the transcript was generated without `--word-timestamps True`. Re-run the transcription using the mlx-whisper invocation from `/organize-shoot` Step 5 before continuing.

### Step 3: Map brief sections to transcript segments

For each section in the Script (e.g. `[0:00 Intro, 12s]`):

1. Identify the **keywords or phrasing** from the script.
2. Search the transcript text for the matching utterance.
3. Find the **start word** (start of section) and **end word** (end of section, before the next question or filler).
4. Record `(start_seconds, end_seconds)` as a **coarse keep range**.
5. Flag any script section that has **no matching content** in the transcript. Surface to the user.

Keep transcript order when possible. If the brief asks for content in a different order than the recording, note it — small reorderings can be done with multiple coarse ranges in any sequence, but only do this if the brief explicitly asks for the reordering.

### Step 4: Propose the cut plan to the user

Before rendering, post a structured proposal in chat:

```
## Proposed Cut: [Content piece title]

**Target:** [duration from brief]
**Source:** [path to source video]
**Transcript:** [path to JSON]

### Section map (brief → source)
| § | Brief section | Source range | Notes |
|---|---|---|---|
| 1 | Intro (12s) — "My name is..." | 14.40–29.55s | ✅ matches |
| 2 | Tenure + service area (10s) | 33.10–47.32s | ✅ matches; transcript order is service-area-then-tenure (brief flips them — keeping transcript order for natural flow) |
| 3 | Mission (20s) | 75.22–99.85s | ✅ matches |
| 4 | Close (8s) — "Glad you're here" | ❌ not in source | Skip; §3 ends naturally on "from start to finish" |

### Processing
- Filler removal: on (uh/um/er)
- Pause compression: gaps > 0.40s → 0.15s
- Estimated final length: ~46s (within 50±5 target)

### Output
`[shoot-folder]/Edits/<content_id>-<slug>.mp4`

**Approve?** Reply "render it" to proceed, or tell me what to change.
```

Wait for user approval before running ffmpeg.

### Step 5: Render

On approval, call the cut engine:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  $AI_CMO_ROOT/scripts/cut-video.py \
  --source "/path/to/source.MOV" \
  --json   "/path/to/transcript.json" \
  --output "/path/to/Edits/<content_id>-<slug>.mp4" \
  --range 14.40:29.55 \
  --range 33.10:47.32 \
  --range 75.22:99.85
```

The engine handles filler removal, pause compression, and the ffmpeg render. Defaults: `--max-pause 0.40 --keep-tail 0.10 --keep-lead 0.05`. Override only if the user asked for a different feel (snappier or more relaxed).

Run in the background if estimated render time > 1 min.

### Step 6: Report back

After the render lands, post:

```
Rendered: /path/to/output.mp4
Length: [X.X]s
Specs: [width]×[height] @ [fps] · H.264/AAC

Cuts inserted: [N]
Sections from brief: [list]
Skipped/missing: [list any §s flagged]

Next:
- Watch and tell me what to tweak
- If a section's join sounds rough, I can [add a 200ms audio crossfade / loosen the pause threshold]
- If the brief calls for B-roll inserts, add them in your NLE — this cut is the spine
```

### Step 7: Update the content note

Append a short entry to the `## Revision History` section of the content note:

```markdown
- **YYYY-MM-DD** — Rough cut v1 rendered at `Edits/<filename>.mp4` (X.Xs, brief-faithful, no closer §4 — not in source).
```

Do not modify any other section of the note unless the user asks.

---

## Iteration

Common follow-up requests and how to handle:

| User says | Adjust |
|---|---|
| "tighter" / "punchier" | `--max-pause 0.30 --keep-tail 0.05 --keep-lead 0.03` |
| "more breathing room" | `--max-pause 0.55 --keep-tail 0.15 --keep-lead 0.10` |
| "keep the fillers" | `--no-filler-removal` |
| "don't compress pauses" | `--no-pause-compression` |
| "cut section X" / "drop the [topic] part" | Re-map the coarse ranges to exclude that section, re-propose, re-render |
| "include [phrase] from later in the interview" | Grep the JSON for the phrase, add its range to the coarse list (keeping it in transcript-time order or in the order the user asked for) |
| "join at [time] sounds rough" | Loosen pause params OR add a 150-200ms crossfade with a follow-up ffmpeg step (`afade` + `xfade`) |

---

## Hard rules

- **Always propose before rendering.** Even on iteration. The proposal step is what makes this cheap to redirect.
- **Always surface gaps between brief and source.** If the brief asks for a line Garrett never said, flag it — don't fabricate or stretch other content to fill the gap.
- **Never modify the content note beyond appending to Revision History.** Editor Brief, Script, and other sections belong to the user / strategy layer.
- **Never overwrite a previous render.** If `<content_id>-<slug>.mp4` exists, suffix the new one with `-v2`, `-v3`, etc. The user A/Bs versions; don't destroy history.
- **Run `humanizer` on any client-facing text you generate** (revision history entry, caption rewrites, etc.). This is direction, not deliverable, so the bar is low — but apply it to anything that would be read by someone outside the toolkit loop.

---

## Technical Reference

### Engine
`scripts/cut-video.py` — see file header for full args. Key knobs:

- `--range start:end` — repeat for each coarse keep region (in source seconds)
- `--max-pause` — gap threshold for compression (seconds). Default 0.40.
- `--keep-tail` / `--keep-lead` — silence preserved on each side of a cut (seconds). Default 0.10 / 0.05.
- `--no-filler-removal` — keep uh/um/er
- `--no-pause-compression` — only the coarse ranges drive cuts (one cut per range boundary)
- `--dry-run` — print the ffmpeg command without running

### Filler list (default)
`uh, um, umm, uhh, er, erm`

Not currently included: `like`, `you know`, `I mean`. These often change meaning when removed. If the user explicitly asks to strip them, modify `DEFAULT_FILLERS` in the script for that run (or just propose a follow-up cut after the first pass).

### Aspect ratio
The engine preserves the source's native aspect. For vertical 9:16 source (phone on dash mount), output is 1080×1920. For 16:9, output is 1920×1080. The engine does not crop or reframe — that belongs in the NLE.

### Audio
Re-encoded to AAC 192 kbps. Source audio is preserved verbatim within each kept range; only the timeline changes.
