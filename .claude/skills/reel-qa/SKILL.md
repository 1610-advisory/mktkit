---
name: reel-qa
description: >
  Run the machine QA gate on any vertical short-form video and read the
  result: container and delivery specs, duration window, loudness and true
  peak, black or frozen frames, caption safe zone and timing, banned words,
  hook-once, plus one small contact sheet for a visual check. Use when the
  user says "QA this reel", "check this video before it ships", "is this
  safe for Reels/Shorts", "run the gate", "why did QA fail", or hands you an
  mp4 and asks whether it is ready to post.
metadata:
  version: 1.0.0
---

# Reel QA

A standalone entry to the QA gate that `cut-video` runs automatically. Use it on files that did not come out of the renderer (an editor's delivery, an older cut, a re-export) or to re-check one after a manual change.

Script: `../cut-video/scripts/qa-reel.py`. Specs it reads: `../cut-video/resources/platform-specs.json` (see `platform-specs.md` for sources). Review questions: `../cut-video/CHECKLIST.md`.

## Steps

1. Identify the file and, if they exist beside it, the manifest (`*.reel.json`), the finish timeline (`*.timeline.json`), and the captions (`*.ass`). Ask nothing if the file alone is given; the gate works with less and marks the rest `na`.
2. Run the gate, always with a contact sheet and small frames:

   ```
   python3 <skill>/scripts/qa-reel.py --video FILE.mp4 \
     [--manifest FILE.reel.json] [--platforms instagram_reels,youtube_shorts] \
     [--duration-window MIN,MAX] [--banned-words client/resources/public-safe-banned-words.txt] \
     --report FILE.qa.json --contact-sheet FILE.sheet.jpg --frames-dir ./qa-frames --max-px 540
   ```

   Exit 0 = pass (warnings allowed), 3 = at least one FAIL, 4 = warnings with `--strict`, 2 = bad input.
3. Read the report table (FAILs first) and then look at the ONE contact sheet. Answer the frame questions in `CHECKLIST.md` for the frames shown. Do not extract additional full-resolution frames into context; ask for a specific frame with `contact-sheet.py --video FILE --times T` at `--max-px 540` if one is needed.
4. Report: the verdict line, each FAIL with measured vs expected in one sentence, each WARN in one line, and the visual answers. State plainly what must change before the file can ship. For an editor's delivery, phrase the notes as timestamped requests (`mm:ss what is wrong, what it should be`).

## Interpreting common results

- `container.resolution` FAIL on a 540x960 file: it is a proxy, not a delivery; render the final.
- `captions.safe_zone` FAIL: caption bottom sits inside the platform UI band; re-render with `--caption-placement safe-lower` (the engine default) or move the burned captions up in the NLE.
- `audio.integrated_loudness` outside tolerance: normalize (two-pass loudnorm) rather than raising the gain by ear.
- `video.frozen_frames` WARN inside a punch: a static tripod shot or a still; fine. FAIL outside a punch: a real freeze, usually a B-roll overlay whose timestamps were not shifted onto the spine clock.
- `hook.once` WARN: the opening line appears again more often than designed (one repeat is expected when `lift_from_spine` is false); check whether the take says its hook twice.
- `text.banned_words` FAIL: a client name or address is on screen or in the caption text. The file cannot ship.

## Must not

- Call a file "verified" without the report AND a look at the sheet.
- Read more than one contact sheet or any frame larger than 540 px into context.
- Publish, schedule, or change a content note's status; this skill only reports.
