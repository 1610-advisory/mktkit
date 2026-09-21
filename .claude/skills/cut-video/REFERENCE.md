# cut-video: engines, flags, traps

Companion to `SKILL.md`. Read when a render misbehaves or when you must call an engine directly. Normal work goes through `render-reel.py` and a manifest; the flag tables below are what the renderer drives for you.

## render-reel.py (the one command you run)

`render-reel.py --manifest reel.json [--proxy] [--style STYLE.json] [--version N] [--dry-run] [--strict] [--no-deliver] [--no-qa] [--lock-file PATH] [--work-dir DIR] [--keep-work] [--ledger PATH | --no-ledger]`

Exit codes: 0 rendered · 2 manifest or input problem (invalid manifest, missing file, transcript without words, unsourced punch, `--strict` preflight warning) · 3 a downstream script failed · 4 rendered but the QA gate reported FAIL (file exists; read the report) · 5 render lock timeout.

Order of work: validate against the schema → preflight (files, words, quote lint, hard-out is a word end, duration estimate) → version → color detection per clip (`signalstats` YMIN: about 31 to 33 in 8-bit means log, single digits means Rec.709; the renderer prints the value) → hook lift → hard out → spine (`cut-video.py --emit-json`) → joins from the spine timeline → stills (`stills-to-broll.py`) → pre-grade mixed sources → inserts → finish (`finish-reel.py`, flags feature-detected from `--help`) → QA (`qa-reel.py`) → RUNNOTES → deliver → one summary JSON line on stdout.

Files beside the output `<id>_<slug>_v<N>.mp4` (or `_v<N>-proxy.mp4`): `.reel.json` (resolved manifest with provenance), `-RUNNOTES.md`, `.ass` and `.srt` (captions), `.cover.jpg` (title frame for the thumbnail), `.timeline.json` (finish timeline: hook, punches, joins, captions, loudness), `.qa.json`, `.sheet.jpg`. Intermediates live in `.work/<id>_v<N>/` and are removed on success unless `--keep-work`.

The render lock (`~/.cache/reel-factory/render.lock` by default) serializes every encode on the machine. Two renderers never run at once; the second waits and says so. Parallel 4K encodes once pushed swap past 15 GB.

## Manifest semantics the renderer applies

- `version: "auto"` picks the next free `_vN`; proxies are `_vN-proxy` and never consume a final number. Nothing is ever overwritten.
- `hook.mode: prepend` with `lift_from_spine: true` removes the hook range from the spine (splitting the range it sits in). The line plays once. A hook from a different file lifts nothing.
- `spine.hard_out` clamps the last range. It must be a word END from the JSON; the preflight lint warns when it is not.
- `joins: "auto"` = every coarse-range boundary on the output clock, read from the spine timeline. finish-reel covers each join with the nearest punch.
- `source.color: auto` and `broll[].color: auto` are measured per clip; stills are Rec.709 by definition. Log spine with log clips: `--lut` for everything. Log spine with any Rec.709 punch (stills, phone clips): the A-roll and hook keep the LUT in finish-reel, log B-roll clips are pre-graded in the work dir, and finish-reel runs with `--broll-no-lut --broll-no-eq` so Rec.709 punches are left alone. Rec.709 spine with log clips: log clips pre-graded, `--skip-lut`. The first model bench (2026-09-05) crushed the stills in all four runs before this rule; `qa-reel` now warns on a punch/A-roll saturation mismatch (`video.grade_mismatch`).
- `source.eq: "none"` → `--no-eq`. `broll[].eq: "none"` on every punch → `--broll-no-eq`.
- `broll[].kind: still` (or an image extension) → `stills-to-broll.py` first; `dur` defaults 3.5; with a `super` at least 3.5.
- `inserts[]`: the spine is split at `after_word_end`; part A (cover, hook), the insert (its own audio, optional super), part B (punches recomputed) are finished separately and concatenated with a re-encode.
- `render.mode: proxy` or `--proxy`: 540x960, hardware encoder when available, every other step unchanged. Iterate on proxies.

## cut-video.py (spine)

| Flag | Role |
|---|---|
| `--source` / `--json` / `--output` | Camera file, word-level JSON, spine mp4 |
| `--range start:end` | Repeat per keep region. **Sorted and merged if they overlap** (the hook trap below) |
| `--max-pause 0.40` · `--keep-tail 0.10` · `--keep-lead 0.05` | Engine defaults. Talking reels: 0.85 / 0.20 / 0.08 (the manifest defaults) |
| `--join-fade SEC` | Audio fade at every kept segment boundary (0.05 to 0.08). Range joins stop clicking |
| `--no-filler-removal` / `--no-pause-compression` | Off switches |
| `--emit-json PATH` | Spine timeline: `coarse_ranges[]` with `out_start/out_end`, `segments[]`, `removed_fillers[]`, `duration_s`. Does not change the render |
| `--force-8bit` | Do **not** use before the LUT. Grade in 10-bit; finish-reel delivers 8-bit |
| `--dry-run` | Print ffmpeg, do not render |

JSON must have `segments[].words[]` with `start`/`end`. Segment-only JSON is not enough.

## finish-reel.py (phone file)

Processing order is locked: extract hook → normalize A-roll (orient → LUT → eq → canvas) → normalize B-roll (orient → LUT → same eq) → `setpts` and overlay on the spine clock → concat hook in front → cover drawtext → dialogue captions (ASS) → loudness → encode.

| Flag | Role |
|---|---|
| `--spine` / `--output` | Input spine, final file |
| `--hook-source` + `--hook-range` / `--hook` | Cold-open clip extracted from the camera file, or a pre-cut clip |
| `--lut` / `--skip-lut` | 3D cube before eq and before text |
| `--eq` / `--no-eq` | A-roll match after LUT. Default `contrast=1.14:saturation=1.35:brightness=-0.015` |
| `--cover-text` · `--cover-seconds 2.0` · `--cover-anchor center|top` · `--cover-case as-is|upper|sentence` · `--cover-darken` | Title card. A backslash in the text is rejected (exit 2); the engine wraps via a textfile. `center` is the IG-safe default; darken dims one frame only |
| `--font` · `--font-color #F2EDE0` · `--font-size 72` | Cover type, absolute font path. Family and color come from the client pack |
| `--broll PATH:at=SEC:dur=SEC[:src=SEC][:kind=clip|still]` | Repeatable. `at` on the cut spine before hook prepend. Omit `src` for a mid-clip in-point |
| `--max-broll-dur 3.0` · `--min-aroll 2.5` · `--join SEC` · `--broll-no-eq` · `--broll-no-lut` | Punch cap; butt punches closer than 2.5 s; cover a spine concat with the nearest punch; B-roll skips the match eq; B-roll skips the LUT (A-roll and hook still take it) |
| `--super TEXT:at=SEC:dur=SEC` · `--super-size 44` | Upper-third annotation below the top safe band |
| `--transcript` + `--spine-range start:end` (repeat) | Burn dialogue captions from kept words only; cues never cross a join; kept words are never dropped |
| `--caption-font` · `--caption-size 42` · `--caption-style phrase|word` · `--caption-min-cue 0.8` · `--caption-max-cue 2.8` · `--caption-max-chars 32` · `--caption-max-lines 2` · `--no-captions` | Caption typography and grouping |
| `--caption-placement safe-lower|safe-center|custom` · `--caption-margin-v` · `--caption-margin-side` · `--platforms LIST` · `--platform-specs PATH` | Placement from the strictest platform safe zone: `safe-lower` = bottom-center with `MarginV = bottom band + 24` (694 px for Reels + Shorts) |
| `--ass-out PATH` | Keep the ASS beside the output (default `<output>.ass`); an SRT is written alongside |
| `--loudnorm-mode two-pass|single|off` · `--loudnorm-i -16` · `--loudnorm-tp -1.5` · `--loudnorm-lra 11` · `--denoise off|light` | Two-pass is the default: measure, then `linear=true`. Keep LRA in the target or linear mode reverts to dynamic. `light` = `afftdn` for phone mics only |
| `--proxy` · `--encoder auto|libx264|h264_videotoolbox` · `--threads N` | 540x960 preview with the hardware encoder; finals stay libx264 CRF 18 |
| `--emit-json PATH` | Finish timeline on the FINAL clock (hook, punches `at_final`, joins, captions, cover, loudness, encoder) |
| `--qa-dir DIR` · `--qa-max-px 540` | Frames: first, cover, hook end, three per punch window, last; exit 3 on a frozen punch. No frame larger than 540 px |
| `--orient auto|none|r5-portrait|landscape-punch|tall-spine` · `--rotate 90|180|270` | Per-clip orientation; `--rotate` only when the brief says so |
| `--width 1080 --height 1920 --crf 18 --preset fast` · `--force` · `--dry-run` | Delivery and safety |

## stills-to-broll.py

`--image IN --output OUT.mp4 [--dur 3.5] [--zoom 1.10] [--direction in|out] [--focus fx,fy] [--eq ...] [--engine auto|pil|zoompan]`. Pillow per-frame sub-pixel resample is the default; ffmpeg `zoompan` is the fallback because it steps on whole pixels and a slow push jitters (measured with `signalstats` YDIF). EXIF upright, 9:16 crop around the focus point, no audio.

## Orientation decision tree

Probe each clip. Do not trust a 4096x2160 container.

1. Display-matrix or `rotate` tag ±90 **and** width > height → `r5-portrait` with `-noautorotate`. **Transpose follows the matrix sign**: `+90` → `transpose=2`, `-90` → `transpose=1`. Then crop from the standing frame: `2160:3840:0:128` when the container was 4096 wide, else a centered 9:16 crop.
2. Already upright (height > width, no rotation): within 1% of 9:16 → scale only; taller → crop to 9:16 before scale.
3. True landscape that must become 9:16 → `landscape-punch`: `crop=ih*9/16:ih:(iw-ih*9/16)/2:0`.
4. Sideways B-cam with no flag → `--rotate` only when the brief says so.

Never hand-roll a pre-grade or pre-rotate outside the engine: that path re-introduced the upside-down hook once already. If a source needs handling the engine lacks, add it to the engine with a test.

## Traps

- **Hook merge.** `cut-video.py` merges overlapping ranges; a hook passed as a range disappears into the spine. The manifest handles this (`lift_from_spine`).
- **B-roll stills freeze.** Overlays must be `setpts` onto the spine clock or the last frame repeats. The engine does this; `--qa-dir` catches a regression.
- **LUT on Rec.709** double-grades orange. Measure, do not eyeball; the renderer prints YMIN per clip.
- **SRT cue end as hard-out** lands half a sentence late. Use the word end.
- **Full-resolution QA frames** in a model's context killed a session (70 frames, 52 MB). Frames are capped at 540 px; look at the one contact sheet.
- **Parallel encodes** blew swap. The lock serializes them.

## Naming

`<id>_<slug>_v<N>.mp4`, proxies `_v<N>-proxy.mp4`. Sidecars share the stem. Never overwrite a version; `finish-reel.py` exits 2 when `--output` exists unless `--force`, and the renderer never passes `--force`.

## Changelog

2.1.0: `bench-reel.py` and the `reel-bench` sibling skill: the same note through several harnesses and models, scored on manifest, QA, punches, stray writes, cost and time; `video.join_uncovered` QA check; preflight lint tokenizes quotes per spoken word; style files may carry `_` keys.
2.0.0: manifest-driven `render-reel.py` (preflight lint, hook lift, color measurement, mixed-source pre-grade, inserts, render lock, RUNNOTES, ledger, provenance, style profile); `qa-reel.py` gate with contact sheets; `broll-index.py` / `broll-search.py` (job-first ranking, captions from alt text, optional CLIP, write-back); `regress.py` fixtures; finish-reel two-pass loudness, safe-zone captions, caption timing, proxy encoder, SRT + cover frame, timeline JSON, 540 px QA frames; platform specs with sources; sibling skills `reel-qa`, `reel-broll`, `reel-regress`.
1.2.3: stills-to-broll sub-pixel engine; text punches hold 3.5 to 4 s.
1.2.2: `--max-broll-dur`, `--super`, `cut-video --join-fade`, insert recipe.
1.2.1: stills-to-broll.py; caption words clamped to range end.
1.2.0: upright tall-spine crop, wide-container hook crop, loudnorm stage, cover wrap via textfile, caption cues limited to kept words, mixed-grade recipe, hard-out from the word JSON.
