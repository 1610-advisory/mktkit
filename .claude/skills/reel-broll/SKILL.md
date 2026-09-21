---
name: reel-broll
description: >
  Find B-roll that shows what is being said: index a business's footage and
  photo library (job folders, website images, archive photos), rank candidates
  for each spoken line (same job first, verified subjects, captions, image
  embeddings), verify them on one contact sheet, and write the verified
  subject back so the library gets smarter. Use when the user says "find
  B-roll for this line", "what photo shows a pocket door", "index the photo
  library", "build the B-roll index", "the punch does not match what he
  says", or a reel manifest has punches with a line but no path.
metadata:
  version: 1.0.0
---

# Reel B-roll

The standard first: **exact or nothing.** A punch must literally show the noun phrase spoken under it. A same-category picture (a hallway for "a hallway full of doors", any door for "hidden door") is a defect, not a fallback; a line with no exact asset stays on the speaker, and that is the correct outcome.

The sourcing ladder, in order. Do not skip a rung.

1. **Video first, from any job.** An exact raw clip anywhere in the index outranks any photo: the same job first (an earlier visit that captured the thing now being described), but a clip from another project is right when it shows the exact thing. When the earlier line itself needs to be heard, that is an `insert` in the reel manifest, not a punch. Never finished reels, never another piece's talking A-roll, never scraps.
2. **Then an exact photo,** only when no exact clip exists AND a person has confirmed that the photo shows that subject (`descriptions[].by == "human"` on the index entry; search with `--confirmed-only`). A model's own read of a photo does not earn a still: the owner would rather have no photo than a near miss (2026-09-07). Stills: at most two per reel, never back to back, 3.5 s, each starting within 0.3 s of the noun it shows. Trade terms are literal: a pocket door disappears into the wall cavity (a closet bypass or barn slider on a track is not one); a hidden door is concealed in the wall's finish, slats or paneling, not a dark door in matching trim.
3. **Write what it shows, then write back.** Every punch carries `line` (the words spoken) and `shows` (what the picture literally shows, named after looking: object, setting, material). `--confirm PATH --subject "<shows>"` records it on the library entry; `--reject` records what a picture does NOT show. The next search finds it directly.
4. **When nothing exact exists,** say so and leave the line un-punched. Propose extending the library (index more footage, the website's images, recent assets) instead of forcing a category match.

Scripts: `../cut-video/scripts/broll-index.py`, `../cut-video/scripts/broll-search.py`, `../cut-video/scripts/contact-sheet.py`. Flag tables: `../cut-video/REFERENCE.md`.

## Build or refresh the index (once per library change)

```
python3 <skill>/scripts/broll-index.py \
  --root /path/to/job-folders --root /path/to/website/public/assets \
  --project-from prefix:3 \
  --captions-from-alt /path/to/website/src/content \
  --captions captions.csv \
  --thumbs /path/to/broll-thumbs --out /path/to/broll-index.json --update [--clip]
```

- Responsive size variants (`-640`, `-1024`) are skipped when the base image exists.
- Captions come from the website's alt text and page titles (`--captions-from-alt`) or a CSV/JSON you provide. Filenames alone carry almost no subject words; without captions or `--clip` embeddings the search has no evidence and says so.
- `--clip` embeds every image with an open-source text-image model when `open_clip` and `torch` are installed (Apple Silicon `mps` or CPU). Run it with the Python that has torch. Cosine scores around 0.30 and above are real matches for this model.
- The index is a JSON file the business owns (keep it in the client repo or a cache dir, never in this toolkit).

## Search for a line

```
python3 <skill>/scripts/broll-search.py --index INDEX.json \
  --query "the hidden door in the hallway" --prefer-project JOB-SLUG \
  --top 8 --sheet /tmp/sheet.jpg --json /tmp/hits.json --explain
```

or for every unsourced punch in a manifest: `--lines-from-manifest reel.json --sheet /tmp/sheet.jpg --json proposals.json`.

Then LOOK at the sheet (one image). For each candidate decide: does the picture show what the line says? Name the object you see before you decide.

- Match: `broll-search.py --index INDEX.json --confirm /abs/path --subject "oak pocket door, hallway" --by vision-check`
- Not a match: `broll-search.py --index INDEX.json --reject /abs/path --subject "hidden door"`

Copy the confirmed path into `broll[].path`, set `verified: true`, and `--exclude-used used.txt` on later searches so a still is not reused in the same reel.

## Public-safe check

Open the chosen still at full resolution once (not into a long transcript; one image) and look for house numbers, mailboxes, street signs, a client's name on paperwork, or a person who could be identified. Any of those: reject and record why.

## Must not

- Pick a still from a filename. Filenames lie; the picture decides.
- Use three stills in a row. Two is the limit before it reads as a montage.
- Put a client surname or address into a `--subject` string; describe the object, not the owner.
