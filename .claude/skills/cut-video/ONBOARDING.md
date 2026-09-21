# Setting up the reel factory for a new business

What a business must provide, where it lives, and the first-hour checklist. Everything business-specific stays in that business's own repo; this toolkit stays generic.

## What the business's repo holds

| Item | Path (suggested) | Used by |
|---|---|---|
| Grade and framing notes | `resources/video-pipeline/README.md` with the locked 3D LUT (`luts/*.cube`) if the camera shoots log, and the portrait-in-wide-container crop recipe if any | manifest `source.lut`; the model when filling `source.color` and `orient` |
| Fonts | `resources/fonts/<Family>/*.ttf` (display serif for covers, sans for captions); license file beside them | manifest `cover.font`, `captions.font`; style profile |
| Design pack | `knowledge/DESIGN.md` or `brand-identity.md`: brand colors, cover casing, caption style | style profile |
| Style profile | `resources/reel-style.json` (copy `resources/style.example.json` from this skill) | `render-reel.py --style`: fills every manifest gap with the house look |
| Banned words | `resources/public-safe-banned-words.txt`, one term per line: client surnames, street names, anything that must never appear on screen | manifest `qa.banned_words_file`; the QA gate |
| B-roll index | `resources/broll-index.json` + a thumbs folder (or a cache dir) built from job folders, website images, archive photos | `broll-search.py` |
| Fixtures | `outputs/edit-lab/fixtures/*.reel.json` + `*.fixture.json` + a `gold/` folder with reviewer-approved renders | `regress.py` |
| Defects ledger | `efforts/<pipeline>/defects.csv` | the incident-to-fixture rule |
| Content notes | wherever the business keeps editor briefs; each needs: deliverable name, duration window, public-safe cover line, hook quote + timecode, keep ranges with quoted words, hard-out, B-roll wishes | the model filling the manifest |
| Review folder | a cloud-synced folder the reviewer opens on a phone (`Pilot Cuts <date>/`) | manifest `deliver.copy_to` |

## Machine prerequisites

- macOS or Linux with `ffmpeg` and `ffprobe` on PATH (8.x tested; hardware encoder `h264_videotoolbox` is used for proxies when present).
- Python 3.10+ with Pillow. Optional: `torch` + `open_clip_torch` in the same Python for image-embedding search (`broll-index.py --clip`); on Apple Silicon it runs on `mps`.
- A word-level transcription tool (the examples use `mlx-whisper` with `--word-timestamps True`). Output JSON must have `segments[].words[]` with `start`/`end`.
- Enough disk for a `.work/` folder beside each render (intermediates are removed on success).

## First hour

1. Copy `resources/style.example.json` to the business repo as `resources/reel-style.json`; fill fonts, colors, LUT path, caption size, platforms. Keys starting with `_` (for example `_about`) are ignored by the renderer, so the file can carry its own notes.
2. Write `resources/public-safe-banned-words.txt`.
3. Index the library: `broll-index.py --root <job folders> --root <website assets> --captions-from-alt <website page sources> --project-from prefix:3 --thumbs <dir> --out resources/broll-index.json [--clip]`.
4. Pick one approved reel (or cut one with the reviewer in the loop) and turn it into fixture `A`: its resolved `.reel.json` plus a descriptor with expectations and the approved render as gold. Run `regress.py --only A --proxy`; it must pass.
5. Cut the second reel unattended through the skill; the reviewer watches the sheet and the file; every note they make that the gate missed becomes a check or a fixture (`CHECKLIST.md`, "Incident to fixture").
6. From then on: notes → manifests → proxies → final → QA → review folder. Run `regress.py` after any engine change.

## What stays generic (do not fork the toolkit per business)

- Scripts, schema, platform specs, checklists, and this guide. A business's look, words, footage, fixtures, and index live in its own repo and are passed in by path.
- If a business needs behavior the engine lacks, add a flag or a manifest field here with a default that preserves current output, add a test, and re-run the fixtures of every business that uses the toolkit.
