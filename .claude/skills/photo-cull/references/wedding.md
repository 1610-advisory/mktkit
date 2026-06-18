# Profile: Wedding (large gallery)

A wedding is a different beast from a project shoot — not because the mechanics change, but because of **scale** (often 1,000–3,000 frames) and because the deliverable is a **representative gallery, not a narrative.** Nobody swipes a wedding gallery looking for a story arc; they relive the day. Order is chronological/by-segment, not dramatic.

## Segments

Weddings break into moments. Cull within each, not across the whole pile:

- **Getting ready / details** (dress, rings, invitations, prep candids)
- **Ceremony** (processional, vows, ring exchange, first kiss, recessional)
- **Couple / portraits** (the posed and candid couple set)
- **Family & group** (formals — every required grouping must be covered)
- **Reception** (entrances, first dance, toasts, party, exit)

Use `--recurse` on `contact-sheets.sh` if the photographer already foldered by segment; otherwise catalog each frame's segment as you review.

**Chunking a huge flat folder (no copying).** A 3,000-frame wedding is often one flat folder of raws. Don't copy it. Get the sorted file list once (`ls "$SRC"/*.CR3 | sort > all.txt`), slice it into chunks (`sed -n '1,300p' all.txt > chunk-1.txt`), and render each chunk with `contact-sheets.sh --filelist chunk-N.txt --out <dir>`. Because filenames are usually a single chronological camera sequence, each contiguous chunk ≈ one time-span of the day — convenient for segment-by-segment work and for fanning the coarse pass out across chunks in parallel.

## What "best" means

Coverage of the *moments that matter*, not the prettiest 50 frames. A blurry-but-only first-kiss frame beats a gorgeous redundant portrait. Two priorities fight and the first wins: **(1) never miss a key moment, (2) then pick the strongest frames within each moment.**

## Order

Chronological within the delivery, grouped by segment. Not a narrative carousel. Don't apply the "no adjacent duplicates" reveal rule literally — a gallery legitimately holds three near-identical first-dance frames if the expressions differ.

## Target count

Ask: **total or per-segment?** Offer defaults:
- **Highlight gallery / sneak peek:** ~30–75 total, spread across segments.
- **Full delivery:** hundreds — usually expressed as "best of each moment" rather than a single number. Ask roughly how many per segment, or per-hour-of-coverage.

## Scale — the tiered cull (this is where the skill earns its keep)

At 2,000 frames you cannot fine-curate one by one. Go in two passes:

1. **Coarse reject (cheap pass).** Render contact sheets and do a fast rejection sweep — kill obvious blinks, eyes-closed, motion blur, missed focus, and near-identical bursts (keep one of each burst). This is mechanical pattern-spotting; it's a good fit to **delegate to a cheaper/faster model (Haiku)** with a tight rubric, taking 2,000 → ~300. State the rubric explicitly so the pass is reproducible.
2. **Fine select (capable pass).** On the ~300 survivors, do the real editorial cull to the target, weighting the user's taste guide. This needs judgment — keep it on the capable model.

Small weddings (a few hundred frames) skip the coarse pass.

**Rendering speed at scale.** `contact-sheets.sh` extracts the embedded JPEG preview from each raw via `exiftool` (~0.2s/frame), not a full `sips` raw decode (~2.3s/frame) — the difference between ~12 minutes and ~3 hours for 3,000 frames. Install `exiftool` (`brew install exiftool`) before a large run; the script falls back to `sips` if it's missing, but you do not want that fallback on thousands of frames. Rendering is IO-bound on the read of the raws, so a fast disk / not-a-USB-bus helps more than CPU parallelism.

## Dedup

Aggressive within bursts (keep the best frame of a 6-shot burst), gentle across genuinely different expressions of the same moment.

## Flag

- Eyes-closed / mid-blink on otherwise-keeper frames.
- Missing required family groupings (cross-check against a shot list if one exists — flag gaps loudly; a missed formal is unrecoverable).
- Recognizable guests for any frames headed to public marketing (release/consent is the photographer's call — surface it).

## Output

Per-segment subfolders. Run `stage-picks.sh` once per segment into its own dest. Slot numbers are just a stable chronological sequence, not a posting order.
