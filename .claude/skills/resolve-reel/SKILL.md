---
name: resolve-reel
description: >
  Cut, grade, caption and deliver a vertical reel inside DaVinci Resolve Studio
  through the Resolve MCP, with a color-managed DWG/DI grade, a generated film-style
  look LUT, face-anchored per-shot exposure, and the business's house captions and
  cover. Also builds numbered look-review pages so a new look is picked from stills
  before it is committed. Use when the user says "edit it in Resolve", "cut this in
  Resolve", "new Resolve project", "grade it", "it looks like log", "not striking",
  "build a LUT", "show me LUT options", "compare looks", "color grade this reel",
  "I want a project I can edit", "make a montage", or wants a Resolve-built version of
  a cut-video reel. When the tool is not named, pick between this and cut-video
  with references/edit-route.md.
metadata:
  version: 1.1.0
---

# Resolve Reel

The Resolve twin of `cut-video`. You decide what is said and shown; Resolve does the cut, grade, audio and render through the MCP; these scripts do the color math and the graphics so every result is repeatable and checkable. Proven end to end: the helpers rebuild a delivered reel pixel for pixel.

**Right route?** Resolve suits a piece the person will watch and may tweak (they get an editable project), color-critical and cinematic cuts, and wordless montages. The ffmpeg route (`cut-video`) suits batches, unattended or headless runs, and script-rebuildable cuts. Decide with `references/edit-route.md` (toolkit root), honoring the business's `edit_route` preference, and say which route in one line. On delivery, name the Resolve project and the exported `.drp`.

Load the business's pack first (`mkt-kit`). Then read the business's files below. **Everything that makes a reel look like that business lives in the business's repo, never here.**

## What comes from the business (read these first)

| Need | Where it lives in the client repo | If it is missing |
|---|---|---|
| Fonts, colors, caption size, cover spec, platforms | `resources/reel-style.json` (shape: `../cut-video/resources/style.example.json`) | Ask; fonts from `knowledge/DESIGN.md` (no stock-font fallback) |
| Grade choices: camera input, look, face IRE, WB target, vignette, voice gain; cover shadow | `reel-style.json` → `resolve.grade` block (+ `resolve.cover_shadow`) | Skill defaults (below) and say so |
| The look itself | `grade.look_profile`, e.g. `resources/video-pipeline/look.json` (shape: `resources/look.example.json`) | Run a look review (step 0) |
| The LUT file Resolve loads | `grade.lut_resolve` (inside Resolve's LUT folder) + the repo copy under `resources/video-pipeline/luts/` | Generate it: `dwg_look.py write` |
| Business-specific notes, decisions, hashes | `resources/video-pipeline/RESOLVE-PLAYBOOK.md` or `README.md` | None needed |
| Banned public words | `resources/public-safe-banned-words.txt` | Skip the check and say so |
| Brief + transcript | content note Editor Brief; word JSON next to the footage | Stop: transcripts are ground truth |

`grade.*` below means `resolve.grade.*` in the business's `reel-style.json` (cut-video's renderer ignores the `resolve` block).

**Defaults (the middle, used only when the business has not set a value):** look `clean`, face highlight 55 IRE, black point code 14, CDL saturation 0.68, WB target Rec.709 lin 1.02 : 1 : 0.97 (slightly warm), vignette 0.035, captions 56 px, cover shadow 0 2px 24px 45%, platforms IG Reels + Shorts + TikTok.

## Files

| Path | Role |
|---|---|
| `scripts/dwg_look.py` | Look engine: presets → `.cube` (DWG/DI in/out); `to_display()` = Resolve's output math, so previews are exact |
| `resources/looks.presets.json` | Six parametric presets: clean, rich, bold, warm-print, bright-air, moody |
| `scripts/grade_solve.py` | Per-shot CDL (slope / offset / sat) from DWG/DI stills: face-anchored exposure, auto neutral WB, black point |
| `scripts/review_looks.py` | Numbered look-review page (HTML + JPEG) on real frames |
| `scripts/house_graphics.py` | House captions + cover as ProRes 4444 alpha, via cut-video's own cue/ASS/safe-zone code |
| `scripts/resolve_ops.py` | Resolve helpers to `exec` inside `run_script_unsafe` |
| `resources/*.example.json` | `edit`, `grade`, `look` shapes |
| `REFERENCE.md` | Color settings, node recipe, why the looks work, every gotcha. Read before the first build. |

## Steps

0. **New look?** Export DWG/DI stills from two or three real shots (two jobs if you can), write a `grade.json`, run `review_looks.py … --style <reel-style.json>`, put the HTML + JPEG where the owner reviews on a phone. They pick a number; write it to the business's `look.json` and generate the LUT. Never commit a look without that review.
1. **Read** the brief and the word JSON. Contact-sheet the source.
2. **Cut points** from word times, each edge moved into a measured audio valley; every word complete.
3. **Build** (`run_script_unsafe`, `exec` resolve_ops): `new_project`, import, `set_clip_input(…, grade.camera_input)`, `build_timeline` (spine V1/A1, punches V2). Check one still for rotation / side bars.
4. **Stills** `export_di_stills` (one per shot; two if the light changes inside a clip).
5. **Solve** `grade_solve.py grade.json --style <reel-style.json>`; preview; faces should read the target ±1.5 IRE.
6. **Apply** `apply_grade(item, cdl[shot], grade.lut_resolve, grade.vignette)` per clip; verify one Resolve still against the preview (about 1 code mean).
7. **Graphics** `house_graphics.py edit.json OUT --style <reel-style.json>`; `add_graphics`.
8. **Audio** `voice_chain(tl, grade.voice_gain_db)`; aim the Resolve export near −1.5 dBTP.
9. **Render** `render(…)`, then loudness only: `../cut-video/scripts/finish-reel.py --spine <render> --output <id>_vN.mp4 --skip-lut --no-eq --no-captions --orient none --cover-text "" --loudnorm-mode two-pass`.
10. **QA** `../cut-video/scripts/qa-reel.py … --ass <captions.ass>`; read the contact sheet yourself.
11. **Deliver for review** per the business's rules (review folder, run notes, content-note history, issue comment). Export the `.drp`. Never publish, schedule, or mark approved.
