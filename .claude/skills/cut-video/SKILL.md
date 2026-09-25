---
name: cut-video
description: >
  Cut a talking reel from an editor brief + word-level transcript to a
  phone-ready 1080x1920 file for Instagram Reels, YouTube Shorts, TikTok and
  Facebook Reels: fill a reel manifest, source B-roll that matches the spoken
  line, render through the engine, pass the machine QA gate, deliver a watch
  pack. Use when the user says "cut this reel", "edit the video", "in-house
  cut", "cut-video", "rough cut from the brief", "edit lab", "overnight cut",
  "execute the edit lab", "finish this reel", "render the talking cut", or
  runs the queue ("cut the next N"). This is the ffmpeg route: when the tool
  is not named, pick between it and resolve-reel with references/edit-route.md
  (batches and unattended runs point here; editable projects point to Resolve).
metadata:
  version: 2.2.0
---

# Cut Video: the reel factory

You turn a brief and a transcript into a finished vertical reel. **You decide what is said and what is shown. The scripts decide everything about ffmpeg.** Never run ffmpeg by hand for a deliverable and never edit a render with a one-off command: every defect that was fixed by a rule instead of a code gate came back (see `CHECKLIST.md`, "Why the gate is code").

This skill is model-agnostic and harness-agnostic: plain files, Python 3.10+, ffmpeg, Pillow. Optional extras (`open_clip` + `torch` for image search) degrade gracefully.

## Files in this skill

| Path | Role |
|---|---|
| `resources/reel-manifest.schema.json` | The contract. One JSON per reel: source, spine ranges, hook, cover, captions, punches, inserts, audio, render, qa. |
| `resources/manifest.example.json` | Filled example to copy. |
| `resources/style.example.json` | A business's house style (fonts, colors, LUT, eq, caption size). Pass with `--style`; the manifest wins on conflicts. |
| `resources/platform-specs.json` + `.md` | Safe zones, delivery specs, loudness, caption timing, pacing, with sources. |
| `CHECKLIST.md` | Definition of done, frame-review questions, the incident-to-fixture rule. |
| `REFERENCE.md` | Engine flags, orientation tree, traps. Read when a render misbehaves. |
| `scripts/render-reel.py` | Executes a manifest: preflight lint → spine → stills → pre-grade → finish → QA → RUNNOTES → deliver. Holds the render lock. |
| `scripts/qa-reel.py` | Machine QA gate: container, duration, loudness, black/frozen frames, caption safe zone and timing, banned words, hook-once, contact sheet. Exit 3 on FAIL. |
| `scripts/broll-index.py`, `scripts/broll-search.py` | Index a footage/photo library; rank candidates for a spoken line; write verified subjects back. |
| `scripts/regress.py` | Re-render the fixture reels and compare to gold. Run after any engine change. |
| `scripts/bench-reel.py` | Run the same note through several harnesses and models (pi with any provider, Claude Code, codex, grok, cursor) and compare manifests, QA, punches, cost and time in one report. Sibling skill `reel-bench`. |
| `scripts/cut-video.py`, `finish-reel.py`, `stills-to-broll.py` | Engines. render-reel.py calls them; you normally do not. |

Building the reel inside DaVinci Resolve instead (color-managed grade, look LUTs, look-review pages)? Sibling skill `resolve-reel`; it reuses this skill's caption, safe-zone and QA code.

**Pick the route before you cut.** Read `references/edit-route.md` (toolkit root): the business's `edit_route` preference, the hard limits (headless → ffmpeg; wordless montage → Resolve), and the task signals. Recommend one route with the reason; ask once only when it is unclear.

Client-specific inputs live in the **client's** repo, never here: LUT and crop recipe (`resources/video-pipeline/README.md`), fonts and colors (`knowledge/DESIGN.md`), a style profile, a banned-words list, fixtures.

## Mode

**Unattended is the default** when the user says edit lab, overnight, queue, or "cut the next N": render without asking. **Interactive**: stop after step 5 (dry run), show the manifest summary and the preflight table, wait for approval, then continue. Unattended never waits for "render it".

## Steps

1. **Orient.** Read the brief (deliverable name, duration window, public-safe cover line, hook quote + timecode, keep ranges with quoted words, hard-out, B-roll wishes, orientation notes). Read the client's video-pipeline README and design pack. Load the client style profile if one exists. Read `references/edit-craft.md` (toolkit root): the house edit rules for every business.
2. **Inputs.** Every referenced file must exist; the transcript JSON must have `segments[].words[]`. Missing words: transcribe to a local temp dir (word timestamps on), copy the JSON back. Missing file: stop and say which. Never substitute a clip.
3. **Fill the manifest** (copy `resources/manifest.example.json`). Ranges start and end on WORD boundaries from the JSON, each with a `quote` (first words … last words). `hard_out` = the end time of the last kept word, never an SRT cue end. **Hook rule:** if the take opens on the hook line, `mode: none`; if the hook is a later grab, `mode: prepend` with `lift_from_spine: true` so it plays once. Cover: public-safe, 7 words or fewer, the pack's display font. Captions on unless the brief says otherwise. Every punch gets a `line` (the spoken words it illustrates) and `dur` (clips under 3.0 s; stills 3.5 s; a punch carrying a `super` 3.5 to 4.0 s). `render.mode: proxy` while iterating.
4. **B-roll: exact or nothing, video first.** A punch must literally show the noun phrase spoken under it. The ladder: (1) an exact raw clip from ANY job in the index (the same job first, but an arched opening from another Acme Remodeling job is right for "arched opening" on this reel); a callback that needs the earlier line heard is an `insert`, not a punch. (2) An exact photo, only when no exact clip exists AND the index entry carries a human-confirmed subject that matches the line (`descriptions[].by == "human"`; search with `--confirmed-only` for stills). A model's own read of a photo is not enough to put a still on screen: the owner would rather have no photo than a near miss. (3) Nothing exact: stay on the speaker; a sit-down with no B-roll of its own usually ships with zero or one punch, and that is correct. A same-category picture (a hallway for "a hallway full of doors", any door for "hidden door", a closet slider for "pocket door") is a defect, not a fallback. Trade terms are literal: a pocket door disappears into the wall cavity; a bypass or barn slider on a track is not one; a hidden door is concealed in the wall's finish, not a dark door in matching trim. Search with `broll-search.py --index INDEX --lines-from-manifest reel.json --prefer-project JOB --sheet sheet.jpg`; look at the ONE sheet; for each pick write `broll[].line` (the words spoken) and `broll[].shows` (what the picture literally shows, named after looking: object, setting, material), copy `path` (and `src` for a clip), then `--confirm PATH --subject "<shows>"` so the library learns. Stills: at most two per reel, never back to back, 3.5 s, each starting within 0.3 s of the noun it shows. Check every still at full resolution for house numbers, addresses, or a client name. Never finished reels or another piece's A-roll as B-roll.
5. **Dry run.** `render-reel.py --manifest reel.json --dry-run`. Read the preflight table: quotes vs words near each boundary, hard-out on a word end, estimated duration vs window, unsourced punches. Fix the manifest until it is clean.
6. **Proxy render.** `render-reel.py --manifest reel.json --proxy [--style STYLE]`. The renderer takes the render lock, cuts the spine, builds stills, pre-grades mixed sources, finishes, runs the QA gate, writes RUNNOTES and a contact sheet. Read the verdict line and the sheet (one image, small frames). Answer the frame questions in `CHECKLIST.md`. Fix the manifest, re-render the proxy. Iterate on proxies, not finals.
7. **Final render.** Same command without `--proxy`. QA must be `pass`, or `warn` where every WARN is listed under "Known deviations" in RUNNOTES with a reason.
8. **Independent verify** (unattended path). A fresh context (a new agent or a cleared turn) sees ONLY the contact sheet, the cover line, the hook quote, the punch lines, and the CHECKLIST questions, and returns strict JSON per question. A "verified" produced without looking at the sheet does not count.
9. **Deliver.** `deliver.copy_to` puts the mp4, RUNNOTES and sheet in the review folder. Update the content note's revision history per the client repo's rules. Never publish, schedule, or mark approved.
10. **Close the loop.** File every reviewer note first: craft → `references/edit-craft.md`, this business's taste → its `reel-style.json` or `memory/` (sort table in edit-craft.md). A note that the machine missed becomes a QA check or a fixture BEFORE the fix counts as done. After any engine change run `regress.py --fixtures DIR --proxy`.

## Must

- Hook plays once. Hard-out is a word end. Every punch is exact (it shows the noun phrase spoken under it), video before photo, and carries `line` and `shows`; a line with no exact asset stays on the speaker. Stills: two per reel at most, never consecutive, on the noun.
- Captions on, in the safe zone (the engine reads `platform-specs.json`). Cover public-safe, center-anchored.
- Loudness two-pass, 48 kHz. Join fades on talking spines.
- One encode at a time (the lock). Proxies for iteration, one final.
- QA frames small, one contact sheet; never read dozens of full-resolution frames into context.
- RUNNOTES beside every render; "Known deviations" honest.

## Must not

- Compose ffmpeg by hand for a deliverable, or bypass the engine with a "quick pre-grade".
- Wait for approval in unattended mode. Leave listed punches for "the NLE later".
- Overwrite a `_vN`. Write client names, addresses, drive names or real paths into this repo.
- Burn crew first names on screen.

## Queue mode

`/cut-video --next N` selects eligible content notes and runs steps 1 to 10 per note (details in the slash command). Cinematic or wordless pieces: not this skill; say so and stop.
