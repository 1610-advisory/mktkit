---
name: footage-index
description: >
  Ingest a mounted footage volume into a compiled catalog so planning works
  without the drive. Copies talking-clip .txt into the client repo, writes
  footage-catalog.jsonl, regenerates content-index.md, and optionally
  refreshes the existing broll index. Required last step of /organize-shoot — not optional, not "offer next."
  Also when the user says "ingest footage", "rebuild the footage catalog",
  "update the content index from the SSD", or mounts the footage drive after a shoot.
metadata:
  version: 1.0.0
---

# Footage index ingest

Client-agnostic. **No client names, domains, or footage in this toolkit.** The client repo owns the catalog, social-name map, and copied transcripts.

Per-client contract lives in that silo's `memory/reference_footage-index.md` (or equivalent). Do not cache A-roll or raw stills. Do not write absolute mounts into the catalog. Keys are relative from the footage root.

## Run

From the client marketing repo, after a footage root is mounted:

```
python3 <skill>/scripts/ingest-footage.py \
  --root t7:/path/to/footage-root \
  --catalog tracking/footage-catalog.jsonl \
  --transcripts-out footage/audio \
  --content-index-out tracking/content-index.md \
  --social-map tracking/footage-social-map.json \
  --notes-dir outputs/content \
  --broll-index resources/broll/index.json
```

A client wrapper may pin those paths. Exit 2 if no named root exists — do not invent rows from shoot-day CSV copies.

`--dry-run` prints the walk and writes nothing. `--skip-broll` skips the existing `broll-index.py --update`. Pass `--broll-clip` only when new files need embeddings; default update keeps unchanged CLIP entries.

## Organize-shoot

`/organize-shoot` is **not finished** until ingest exits 0. If the client repo has `scripts/ingest-footage.py`, run that from the client root as the last step. Do not skip, do not hand-edit `content-index.md` instead, do not proceed to shoot-review on a failed ingest.

## Must not

- Put client PII in this toolkit.
- Call `broll-index.py` without re-passing every root already in that index (website stills would drop).
- Copy `.json` word transcripts or media into the client repo.
- Run CLIP / 4K decode jobs in parallel on this machine.
- Treat this skill as something a human has to remember to invoke after a shoot.
