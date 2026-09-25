# Resolve Reel — reference

Read before the first build on a new machine or a new camera. The business's own values (look, face target, fonts) come from its `reel-style.json` `resolve.grade` block and look profile; this file explains the machinery.

## 1. Project color settings

| Setting | Value | Note |
|---|---|---|
| `colorScienceMode` | `davinciYRGBColorManagedv2` | |
| `separateColorSpaceAndGamma` | `1` | see clip input gotcha |
| Timeline | `DaVinci WG` / `DaVinci Intermediate` | "DaVinci Wide Gamut" is rejected by the API |
| Output | `Rec.709` / `Gamma 2.4` | |
| Output tone mapping | `None` | the look LUT carries the curve |
| Output gamut mapping | `None` | |
| Resolution / rate | 1080 × 1920, 29.97 | set before import |

With tone and gamut mapping off, the output step is plain math (DI decode → DWG→709 matrix → encode), so `dwg_look.to_display()` reproduces the Resolve render; checked at about 0.3 of an 8-bit code. That is what makes stills previews trustworthy.

**Clip input color space** is per camera, from the business's `grade.camera_input`. Canon C-Log3: `Canon Cinema Gamut/Canon Log 3`. Rec.709 graphics: `Rec.709 Gamma 2.4`. A new camera changes only this; the look is camera-agnostic because it works in DWG/DI.

## 2. Node 1 on every graded clip

1. **CDL** (`TimelineItem.SetCDL`, NodeIndex 1) from `grade_solve.py`:
   - **Slope** = contrast in log around DI 0.40. The solver picks the slope (0.75–2.0) that puts the 1st-percentile luma at the black code.
   - **Offset R G B** = white balance + exposure. In DI a log offset is a linear gain, so this is a physically correct balance. WB reference = brightest, unclipped, low-chroma pixels; target from `wb_target_709`.
   - **Saturation** about 0.68: log slope multiplies chroma by about the slope, and skin / saturated prints go hot without it.
2. **LUT** in the same node (`Graph.SetLUT(1, path relative to Resolve's LUT folder)`). Resolve applies the node CDL before the node LUT (verified).
3. **Vignette** (optional) in Fusion, before the color page: `BrightnessContrast` (Brightness = −vignette / slope, i.e. a log-space exposure drop) masked by an inverted soft `EllipseMask` (W 1.35, H 0.95, SoftEdge 0.45). Center unchanged; corners about 8–11 codes darker at 0.035.

### Exposure anchor

Exposure is set from the **face**: the 98th percentile of luma in a face box lands at the business's `face_ire` (default 55; the "brightest part of the face" rule). Shots without a face `match_wall` to an earlier face shot. A clip whose light changes (door → window) gets two stills and one CDL that averages both faces. Measure raw source IRE as `code / 1023` on full-range 10-bit files when someone asks whether footage is over- or underexposed; graded and raw IRE are different numbers.

## 3. Why the looks work (and what failed first)

Failures on the first builds, in order:
- **A log-in LUT from ffmpeg-era pipelines** lifted the image but kept log-flat contrast: "looks like log".
- **A Rec.709-space look** (convert to 709, then an S-curve, luma-ratio contrast, HSV saturation) was clean but "not striking": contrast after the display transform bends an already-compressed image, luma-ratio contrast makes color swell and fade with brightness, HSV band edits hit already-saturated colors hardest. No real black point: the 1st percentile sat at 36–57 of 255.

What the presets do instead (sources: Steve Yedlin's display-prep writing, Cullen Kelly, Juan Melara's print-film notes, Mixing Light on custom ODTs and saturation, Frame.io on log vs linear grading and Resolve's saturation tools):
- **Per-channel log-logistic curve on scene-linear** (toe + shoulder, scene 18% grey → `grey`), the way film and good ODTs behave; highlights desaturate naturally.
- **Subtractive saturation in OkLab**: chroma up, lightness down by `sub`, and only on pixels above the `neutral` chroma, so white walls and grey cabinetry stay clean.
- **Split tone**: cool shadows, warm highlights weighted toward colorful pixels, a little extra warmth on orange hues (skin, wood).
- The per-shot CDL, not the look, owns exposure and contrast (Cullen Kelly: keep exposure out of look development).

Preset parameters: `resources/looks.presets.json`. A business look = `base` preset + `params` overrides in its look profile. To tune: change params, `review_looks.py --looks base,path/to/candidate.json`, compare, commit only after the owner picks.

Scriptable vs GUI: CDL, LUT, color management, Fusion comps, render — scriptable. Tracked windows, curves, OFX parameters (Film Look Creator, ColorSlice), node creation — GUI only. A subject window (+⅓ to ½ stop on the person, walls down) is the biggest win left for the GUI.

## 4. Graphics

`house_graphics.py` imports cut-video's `finish-reel.py` and uses its `group_caption_cues`, `write_ass`, `caption_layout` and `max_safe_zones`, so Resolve captions equal the ffmpeg pipeline's. Placement `safe-lower` = bottom of the union safe zone of the listed platforms (IG + Shorts + TikTok: MarginV 696, sides 81 / 156). ASS font sizes render smaller than the number suggests (libass scales by ascender + descender); on a phone 42 read too small, so the default is 56 and a business may go higher.

Word edges: whisper word times drift. A word that starts up to `lead_frames` before a keep is pulled into it (it is audible); a word that starts in the last `tail_frames` of a keep is dropped (it is not). Check each edge against the audio and record exceptions in `edit.json` `_edges`.

## 5. Gotchas

- **Still images ignore API start/end frames** (5 s default; they import at 24 fps). Graphics go in as frame-exact ProRes 4444 alpha clips.
- **libass on a transparent source writes alpha 0**: the clip shows nothing in Resolve. Fixed in `house_graphics.py` by a white matte + `alphamerge` + `unpremultiply`.
- **Fusion:** `tool.EffectMask = mask.Output` silently does not connect. Use `ConnectInput`. The default EllipseMask name is `Ellipse1`.
- **Clip input names:** combined names are accepted only with `separateColorSpaceAndGamma = 0`, and a gamut name alone can pick the wrong gamma silently (`Canon Cinema Gamut` → Canon Log 2). `set_clip_input` toggles and reads back.
- **`AppendToTimeline` endFrame is exclusive.** `end - 1` leaves one-frame gaps.
- **Jump cuts:** when two spine segments from the same camera angle meet, alternate the framing: punch the next segment in about 10-15% (`ZoomX`/`ZoomY` on that timeline item, then `Pan`/`Tilt` so the eyes stay on the same spot). It reads as a second angle. Check a still on each side of the cut, and check the source has the resolution headroom. Not needed at a cut to B-roll or another camera.
  - Measured 2026-09-24 (Resolve Studio 21, rotated +90 clip): Pan +1 moves the picture +1 px, but Tilt +1 moves it only about −0.3 px, so tilt is not in pixels. Calibrate on a still before solving. A Fusion Transform runs before the Inspector rotation, so on a rotated clip Fusion x shows as vertical on screen and y as horizontal.
  - A tight segment between two wide ones must match the eyes at both ends. If the head moves a lot, match the first cut with pan/tilt and add a slow keyframed Fusion Transform drift (about 2 px/s) to match the second.
- **Rotation:** many phone-held or portrait-flagged camera files are honoured by Resolve automatically (rotation 0, zoom 1.067 fills a 2160×4096 frame into 1080×1920 by width). Some cards are not (−90 / 1.91). Always check one still for bars.
- **Data Level:** leave Auto for full-range HEVC. Video level crushes blacks.
- **Flat footage is usually the room, not the file.** A 10-bit 4:2:2 source with a correct black code still has no deep blacks when the scene is white and flat-lit; the grade has to build them.
- **Single-color light** (work lights, one lamp) defeats the automatic neutral: set `manual_wb` for that shot.
- **Headroom:** Resolve cannot limit through the API. Keep its export at or under −1.5 dBTP with the voice gain; the loudness finish does the rest. `finish-reel.py` refuses to overwrite an existing `_vN` output.
- **`run_script_unsafe` times out at 60 s:** start the render in one call and poll `IsRenderingInProgress` in the next.
- **QA loudness warn** near −16 LUFS is the platform −14 comparison; the house target is the business's choice.
