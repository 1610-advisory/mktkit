---
title: "Choosing an edit route: Resolve or ffmpeg"
description: "How the agent picks between the resolve-reel (DaVinci Resolve) and cut-video (ffmpeg) routes for a cut, and how it helps the user choose."
status: active
last_updated: 2026-09-25
---

# Choosing an edit route: Resolve or ffmpeg

The toolkit has two ways to make a finished vertical video:

| Route | Skill | What it runs on |
|---|---|---|
| **Resolve** | `resolve-reel` | DaVinci Resolve Studio through the Resolve MCP, on the machine where Resolve is open |
| **ffmpeg** | `cut-video` (talking reels, the engine) | Python + ffmpeg anywhere, no screen needed |

Both can reach the same look. On one side-by-side test, a tuned ffmpeg build landed within about 5/255 per shot of the Resolve cut. **The choice is about how the person works, not about quality.** Help them choose. Do not pick silently, and do not ask when the answer is already clear.

## How to decide (in order)

1. **The business already chose.** Read the business's `resources/reel-style.json` → `edit_route`:
   ```json
   "edit_route": { "default": "resolve", "fallback": "ffmpeg", "why": "wants editable projects" }
   ```
   `default` is `resolve`, `ffmpeg` or `ask`. Use it unless a hard limit below rules it out, and say which route you are using in one line. Also check the business's memory for a stated preference.
2. **Hard limits** (these override the preference; say why):
   - Resolve MCP not available, Resolve not running and cannot be launched, or the session is headless (a server, a cloud run, an overnight job with the machine asleep) → **ffmpeg**.
   - The piece is a wordless montage or cinematic cut and the ffmpeg route has no engine for it (cut-video is built for talking reels) → **Resolve**, or a one-off ffmpeg build only if the person asks for one.
3. **Task signals** (when there is no preference, or it is `ask`):

   | Points to Resolve | Points to ffmpeg |
   |---|---|
   | The person will watch the cut and may want to tweak it themselves | Batch of many pieces, a queue (`cut the next N`), parallel runs |
   | They want a project file they can open and edit | Runs unattended: overnight, on a server, machine asleep |
   | Color-critical or cinematic: log footage, a look LUT, a moody grade | Rebuild from a script in git; code-gated regression (`reel-regress`) |
   | GUI finishing later: tracked windows, curves, Magic Mask | No Resolve Studio licence on this machine |
   | One piece, one reviewer | Same cut on several harnesses or models (`reel-bench`) |

4. **Still unclear?** Ask once, in one short question, with a recommendation and the reason first. For example: "I'd cut this in Resolve so you get a project you can open and tweak. The ffmpeg route is better if you want it run overnight. Resolve?" Then write the answer to `edit_route` (or the business's memory) so you do not ask again.

## What each route hands over

- **Resolve:** a new Resolve project per piece, the render, and an exported `.drp` next to the source footage. The person can reopen and change it. Mention this when you deliver.
- **ffmpeg:** the render, the manifest / build script, and QA output. Changes go back through the agent: edit the manifest or script, then re-render.

## ffmpeg route: lessons when it must match a Resolve look

Found when an ffmpeg rebuild of an approved Resolve montage was brought within a few codes of it:

- Anchor exposure with the solver's percentile method (`grade_solve.py` style), not by eye. Gate in code: 99th-percentile luma at or below about 225/255, and the 1st percentile down at the black code.
- Trust automatic white balance unless one colored light is the only source.
- Do not loudness-normalize natural sound up to a voice target: it raises the noise floor by tens of dB. Keep nat sound low under the in-app music bed.
- Composite graphics in RGB with an explicit Rec.709 matrix, or the off-white text shifts.
- Resolve's Fusion vignette (resolve-reel `apply_grade`) measures as a scene-linear drop inside an ellipse sized in image-width units. On a 9:16 frame it reaches the top and bottom thirds and crushes dark shots at the edges. It is spatial, so match it with two LUTs (plain / full vignette) blended through the mask, not by baking it into one LUT.

## Never

- Switch routes in the middle of a piece without saying so.
- Build the same piece on both routes unless the person asks for a comparison. If both exist, give each file a route suffix so neither overwrites the other.
