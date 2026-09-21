---
description: >
  Slash entry for the cut-video skill. Cut a talking reel from an editor
  brief + transcript to a phone-ready 1080x1920 file, or run the queue
  (--next N) over eligible content notes. Not for cinematic or wordless cuts.
argument-hint: /path/to/content-note.md | --next N
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash]
---

**The skill is the source of truth:** `.claude/skills/cut-video/SKILL.md` (steps), `CHECKLIST.md` (definition of done and frame questions), `REFERENCE.md` (engine flags and traps). This command only decides WHICH note to cut and in which mode, then follows the skill.

# Cut Video

User provided: $ARGUMENTS

## Select the work

**A content note path** → cut that note. **`--next N`** (default 3) → queue mode. **Nothing** → ask for one of the two, once.

Queue mode selects, without asking:
1. Scan the current client's `outputs/content/*.md` for notes with `status: captured` or `pre-production` whose Editor Brief names a `source_footage` file that exists on disk, and whose `Deliver as:` filename does not yet exist (any `_vN`) in the shoot folder `Edits/`. Skip BANKED notes and anything `on hold`.
2. Order by `post_date`, take the first N. Print the list (content_id, title, source) before cutting anything.
3. Fewer than N eligible: say so and cut what is eligible. Never write a content note from queue mode; notes come from the brief brainstorm.

## Mode

Queue mode and any "edit lab", "overnight", or "unattended" phrasing = **unattended**: no approval stop. A single note without those words = **interactive**: stop after the dry run with the manifest summary and preflight table, wait for approval, then continue exactly as the skill says.

## Per note

Follow `SKILL.md` steps 1 to 10. In short:

1. Read the note's Editor Brief and Script. Read the client's `resources/video-pipeline/README.md` (LUT, crop) and `knowledge/DESIGN.md` (fonts, colors). Load `resources/reel-style.json` from the client repo if it exists (`--style`).
2. Write the reel manifest beside the render target: `<shoot>/Edits/<content_id>.reel.json` (copy `resources/manifest.example.json`). Ranges on word boundaries with quotes; hard-out on a word end; hook once; public-safe cover; a `line` on every punch; `deliver.copy_to` = the client's review folder for this date.
3. Source B-roll by the ladder (`reel-broll` skill): same job first, then the indexed library with a sheet look and a `--confirm` write-back; `verified: true` only after looking.
4. `render-reel.py --manifest … --dry-run` until the preflight table is clean.
5. `render-reel.py --manifest … --proxy` → read the QA verdict and the contact sheet → fix → repeat. Then the final render.
6. Independent verify from the sheet and the CHECKLIST questions.
7. Delivery happens through the manifest. Append the note's Revision History (version, duration, what changed, QA verdict, path). Flip `captured` → `pre-approval`. Report per note: file, duration, punches (what each shows), QA verdict, known deviations.

## Hard rules

- One encode at a time; the renderer's lock enforces it. Do not launch renders in parallel by hand.
- Never overwrite a `_vN`; the renderer picks the next number.
- Never publish, schedule, or set `approved`.
- A missing file stops that note with a clear message; no substitutes.
- Cinematic / wordless: stop and say it is not this skill.
