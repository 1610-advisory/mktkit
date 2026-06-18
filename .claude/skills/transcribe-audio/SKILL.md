---
name: transcribe-audio
description: Transcribe audio files (m4a, mp3, wav, mp4 audio) with mlx-whisper on the Apple Silicon GPU and route the output to the right place — meeting notes get a Transcript section plus a 200-300 word YAML summary, shoot-folder audio gets sibling .txt + .json files for each clip, and ad-hoc audio prints to stdout or a user-specified path. Use this skill whenever the user says "transcribe this audio", "transcribe the m4a", "summarize this meeting recording", "process the shoot audio", "fill in the meeting summary", "transcribe and summarize", or any time the conversation involves running Whisper on a recording, ingesting a meeting transcript, or batch-processing a folder of shoot clips. Trigger even if the user does not name Whisper explicitly — if the request is "turn this audio into text" or "I just dropped a recording, can you summarize it", this is the skill.
metadata:
  version: 1.0.0
---

# Transcribe Audio

You are processing audio recordings with **mlx-whisper** (Apple Silicon GPU) and placing the output where it actually belongs in this Obsidian/1610 Marketing Toolkit system. The script (`scripts/transcribe.py`) does the raw transcription. **Your job is to detect what kind of audio this is, route the result correctly, and never destroy existing transcripts or summaries.**

The Whisper environment is already set up. Concrete commands, model selection, and gotchas live in `references/whisper-usage.md` — read that file before you run anything for the first time in a session.

---

## Step 1 — Detect the input flow

Look at what the user gave you and pick exactly one flow. If it's ambiguous, ask one clarifying question rather than guessing.

| Signal | Flow |
|--------|------|
| A path under `Calendar/Meetings/*.md`, or the user says "this meeting", "fill in the summary", "summarize this recording" | **Meeting flow** |
| A folder path containing `.m4a` files, especially under `clients/*/content/shoots/.../Audio/` or any path the user calls a "shoot" | **Shoot flow** |
| A single audio file path with no meeting note and no shoot folder context | **Ad-hoc flow** |

You may NEVER scan global locations like `~/Downloads`, `~/Desktop`, or the whole vault for audio. Only operate on paths the user provided (or paths obvious from a meeting note's frontmatter / linked attachments).

---

## Step 2 — Pick the model

Default to **`mlx-community/whisper-large-v3-turbo`** (Apple Silicon GPU, fast, top-tier accuracy). Drop down only with a reason:

- `mlx-community/whisper-tiny` — short identification-only clips (e.g., B-roll naming) where speed matters more than accuracy. Promote back to turbo if anything will actually be edited from the transcript.
- `mlx-community/whisper-medium` — fallback if turbo errors out for some reason; rarely needed.
- `mlx-community/whisper-large-v3` (non-turbo) — only if the user said turbo missed words and asked you to redo with the heaviest model.

Promote tiny → turbo whenever any of these are true:
- File length > 5 minutes
- Meeting recording with multiple voices
- User flagged it as "important" or source material for a blog post / video edit
- Previous run on tiny had obvious errors

mlx-whisper caches models in `~/.cache/huggingface/hub/`. First use of a given model downloads it (turbo is ~800MB). Subsequent runs are instant to start.

If a file is unusually long (>10 min) or you're batching a folder, run in the background. The harness will notify you when it's done.

---

## Step 3 — Run the right flow

### Meeting flow

The goal is to fill in two places on the meeting note: a `# Transcript` section at the bottom, and the `summary:` YAML field.

1. **Read the meeting note** with the Read tool. Capture:
   - Existing YAML frontmatter (especially `summary:`, `type:`, `Links:`, `company:`, `attendees:`)
   - Whether a `# Transcript` section already exists, and whether it has content
2. **Find the audio file.** Check the note for an explicit path or `[[attachment]]` link. If none, ask the user where the audio is. Do not guess.
3. **Refuse-or-confirm gates:**
   - If `# Transcript` exists and has non-trivial content (more than a placeholder line), STOP. Show the user the first ~10 lines of what's there and ask whether to (a) skip transcription, (b) replace, or (c) append below it. Do not silently overwrite.
   - If `summary:` is already populated with non-trivial content, STOP. Show the user what's there and ask whether to keep it, replace it, or refine it after the new transcript lands.
4. **Transcribe** the audio with the chosen model. For meeting flow, write transcript output to a temp file (`/tmp/whisper-<timestamp>.txt`) so the script's stdout doesn't get tangled with bash escaping in long content.
5. **Append the transcript** to the meeting note under `# Transcript`:
   - If the section is missing, add it at the bottom (one blank line above the heading).
   - If the section exists but is empty/placeholder, fill it in.
   - Use the Edit tool with a precise old_string match. Do not rewrite unrelated parts of the file.
6. **Generate the summary** (200-300 words). This is a prompt-driven step done in the agent's main thread (no script):
   - Read the transcript text you just produced.
   - Write 200-300 words covering: who was there, what they decided, key takeaways, open questions, action items, anything that future-you would want to remember at a glance.
   - Match the existing tone of meeting notes in the vault (matter-of-fact, scannable, no marketing fluff).
   - Anonymize nothing in the summary itself — meeting notes are private. (Anonymization rules apply when *mining* meeting notes for content, not when summarizing them in place.)
7. **Update the YAML `summary:` field** using the Edit tool. Quote the value with double quotes, escape internal `"` as needed, keep it on a single line (folded into one paragraph) unless the existing note uses multi-line YAML — preserve whatever style is already there. Touch only the `summary:` line. Leave `type`, `Links`, `company`, `attendees`, and any other fields exactly as they were.
8. **Report what changed:** the meeting note path, model used, transcript word count, summary word count.

### Shoot flow

The goal is to produce a sibling `.txt` for every audio clip in the folder, skipping ones already done, with the user able to walk away while it runs.

1. **Enumerate audio files** in the given folder (and only that folder — don't recurse into siblings unless the user says so). Match `*.m4a`, `*.mp3`, `*.wav`. Note any video files (`.mov`, `.mp4`) — only include them if the user explicitly asked.
2. **Filter out already-done files:** an audio file is done if a sibling `.txt` of the same basename exists AND is non-empty (`-s`, not just `-f`). Stray empty `.txt` files mean a previous run failed; treat those as not-done and overwrite.
3. **Show the user the plan** before running: count of new files, count of skipped files, model choice, estimated runtime if it's large. Wait for go-ahead unless the user already said "process the whole folder".
4. **Run the batch in the background** with a single `nohup` shell loop (template in `references/whisper-usage.md`). Pipe to a log file so completion can be inspected. Use `run_in_background: true` if invoking via Bash tool.
5. **Do NOT write summaries** in shoot flow. Summaries for shoots happen in the `/shoot-review` workflow, which reads the `.txt` files this skill produced.
6. **When the run finishes,** verify with `ls` + `wc -l` that each `.txt` is present and non-empty. Report: total transcribed, total skipped, any failures (look at the log file).

### Ad-hoc flow

User pointed at one audio file outside of a meeting or shoot context. Just transcribe it.

1. **Confirm the destination.** Default is stdout (paste back into chat). If the file is long enough that the transcript would clutter chat (>~500 words), offer to write it next to the audio file as `<basename>.txt` or to a path the user names.
2. **Transcribe** with the chosen model.
3. **Return** the transcript (or the path it was written to).
4. No frontmatter manipulation, no summary, unless the user explicitly asks for one. If they do, write the summary in chat — don't invent a destination file for it.

---

## Hard rules

- **Never overwrite an existing non-empty `# Transcript` section without explicit confirmation.** Show the existing content first.
- **Never overwrite an existing non-empty `summary:` field without explicit confirmation.** Show the existing value first.
- **Never run Whisper on audio outside paths the user provided.** No global Downloads/Desktop scans.
- **For files >10 min or batches of more than a few clips, run in the background** and let the harness notify you on completion. Don't sit on a foreground timeout.
- **Don't touch other YAML fields** in a meeting note (`type`, `Links`, `company`, `attendees`, etc.). Edit only `summary:`.
- **Don't write summaries in shoot flow.** That's `/shoot-review`'s job.
- **Don't change `[[wiki-links]]`** if any appear in a meeting note's body or transcript.

---

## Quick sanity checklist before running

- [ ] Did I confirm the input flow (meeting / shoot / ad-hoc)?
- [ ] Did I pick a model (turbo by default; tiny only for short identification clips) with a reason?
- [ ] If meeting: did I check whether `# Transcript` and `summary:` already have content?
- [ ] If shoot: did I list which files I'll skip vs transcribe, and confirm with the user?
- [ ] For long jobs: did I plan to run in the background?
- [ ] Did I avoid touching anything outside the user's stated paths?

---

## Reporting back

After every run, log:
- Files processed (full paths)
- Model used (and why if it was a non-default choice)
- Output destinations (note path, .txt paths, stdout)
- Skipped files (and why — already-done, unsupported format, user-excluded)
- Any failures, with the log path

This goes in chat. Mirror it into `memory/logs/YYYY-MM-DD.md` if the session is meaningful (e.g., processed a real meeting or a shoot batch).

---

## References

- `references/whisper-usage.md` — model selection table, exact bash commands, background-execution patterns, gotchas (m4a needs ffmpeg, HEIC isn't audio, MPS fallback, etc.). Read this once per session before you invoke the script.
- `scripts/transcribe.py` — single-file transcription. Stdout is the transcript; stderr is progress/errors. Use `--out` to write directly to a file, `--model` to choose size, `--language` to skip detection.
