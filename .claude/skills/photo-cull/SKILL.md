---
name: photo-cull
description: >
  Review any photo shoot and cull a large pool of stills down to a tight curated
  set staged for the edit pass. Works for project/remodel reveals, weddings,
  brand/corporate events, real-estate and interiors, portraits, or a custom path.
  Use when the user wants to pick keepers, narrow a big folder to the best N,
  decide which shots to edit, choose carousel/reveal stills, select a wedding
  gallery, pick listing photos, or build a background library. Triggers: "review
  the photos from the shoot", "which of these should we edit", "pick the best
  shots", "cull the shoot", "narrow this down to the top 20", "go through the
  gallery", "choose the listing photos", "select the gallery". Reach for it after
  organize-shoot or before carousel-slides.
metadata:
  version: 2.0.0
---

# Photo Cull

You are a photo editor culling a shoot. The input is a folder with too many images to eyeball one by one — sometimes 50 finished JPEGs, sometimes 3,000 raws you can't even open. The output is a smaller, curated set staged so a human can do the final edit pass, plus a clear record of why each frame made the cut.

The mechanics (rendering, contact sheets, staging) are the same for every shoot. **What changes by shoot type is the judgment** — what "best" means, whether order matters, how many to keep, how hard to dedup, what to flag. That lives in a per-shoot-type **profile** (`references/*.md`). You read the shared loop here, pick the profile, and load only that one file.

This complements `organize-shoot` (which transcribes/renames/catalogs a whole shoot day) — reach for `photo-cull` when you specifically need to *choose stills*. It hands off to the human edit pass, then to `carousel-slides` (rendering) or a straight gallery/post delivery.

The scripts do the file shuffling. The hard part is judgment: which N of M frames earn a slot, and (when it matters) in what order. Don't outsource that to filename or filesize.

---

## Why you can't cull from a listing

You cannot cull from a file listing. RAW files (`.CR3`, `.NEF`, `.ARW`, `.DNG`) aren't viewable as-is, and even JPEGs tell you nothing from their names. Picking "by filename" or trusting a mapping CSV produces confident, wrong selections — a blink and the keeper next to it have adjacent names. **Always render contact sheets and actually read them.** The whole skill is built around making that fast.

---

## Step 0 — Pick the profile and the target count

Two things decide everything downstream. Settle them first.

**1. Which profile?** Infer from context (client type, folder name, the content note, what the user said), then confirm. Read the matching reference file and follow its curation logic:

| Shoot type | Profile | Output shape |
|------------|---------|--------------|
| Remodel / build / project reveal | `references/project-reveal.md` | **Ordered** narrative carousel |
| Wedding | `references/wedding.md` | **Unordered** representative gallery, by-moment; tiered at scale |
| Corporate / brand event | `references/event.md` | Hero moments for a recap |
| Real-estate / interiors / listing | `references/real-estate.md` | Full room coverage, walkthrough order |
| Anything else | `references/custom.md` | You ask the user to define goal, order, count |

If two could fit, ask. If none fit, use `custom.md` — don't force a shoot into the wrong profile.

**2. What's the target count?** If the user gave a number ("top 20", "best 12"), use it. **If they didn't, ask before culling** — the count changes how aggressively you cut, and re-culling to a different number is wasted work. For weddings and large galleries, ask whether the target is a *total* or *per-segment* (e.g. "50 total" vs "the best of each: prep, ceremony, portraits, reception"). The profile gives sensible defaults to offer.

**3. Is there a taste guide? (optional, but use it when it exists.)** The profiles encode *generic* good-photo logic. The person culling almost always has a more specific eye — frames they always cut, a look they reach for, a one-line creed. Let them supply it, in any of three forms, and weight it heavily:

- **Inline** — a quote or a few lines in the request ("I hate anything centered; give me window light and negative space; candid beats posed every time").
- **A file** — a path to a markdown file describing what a good picture is to them (their rubric, sample hero shots, hard nos). Read it.
- **A per-client default** — check the client's `knowledge/photo-taste.md` and auto-load it if present. If a client keeps asking you to re-explain their eye, offer to write what you've learned to that file so it persists.

A taste guide is a **high-priority overlay on the profile**: when the guide and the generic logic disagree, the guide wins — it's the user's eye and brand, not yours. Cite it when you justify a pick ("kept #12 over the sharper #14 because your guide favors the candid moment over the posed one"). If no taste guide exists, fall back to the profile's defaults and say so.

---

## The loop

### 1. Resolve the source folder (and the edit policy)

Find the folder of candidates. If a photographer already culled+edited into a finals/`edits/` subfolder, prefer it — those are stronger starting frames than the full raw dump (unless the task is explicitly "which raws should I edit", where you want the raws).

Then check the **client's edit policy** — the one per-client variable, recorded in the client's `CLAUDE.md` (and `memory/reference_carousel_flow.md` where present):

- **Edit-always** clients: every still gets a human edit pass before it ships. Your job ends at *staging the picks*; the human edits them into `_edited/`; downstream builds read from `_edited/`.
- **Never-edit** clients: stills ship as shot. Your picks are the finals; hand them off directly.

If the policy isn't recorded for this client, ask once and write the answer to their `CLAUDE.md`.

### 2. Build contact sheets

```bash
bash scripts/contact-sheets.sh --src "<photo-folder>" [--out <workdir>] [--batch 18] [--recurse]
```

Enumerates every image (raws rendered via `sips`), writes a labeled thumbnail per frame, batches them into readable contact sheets, and writes `manifest.tsv` mapping each on-sheet index `#N` back to the original full-res file. Use `--recurse` when the shoot is split across subfolders (common for weddings/events). For very large galleries, see the tiered approach in `wedding.md` before rendering everything at full review depth.

**Then Read every sheet.** This is the actual review — don't shortcut it. Build a catalog as you go: for each `#N`, the subject, the moment/zone, is it sharp, is it a keeper.

### 3. Curate — per the active profile

Pick the keepers by their `#N` labels, applying the active profile's logic. A few principles are **universal across profiles**:

- **You must have looked.** Every pick traces to a frame you actually saw on a sheet.
- **Dedup.** Near-identical frames waste slots. Pick the better one. (How aggressive depends on the profile — a wedding kills dupes hard; a reveal keeps two angles of a hero feature.)
- **Honor the target.** Hit the count the user asked for, and do the math when one photo becomes two slides (e.g. a split-hero opener — see `project-reveal.md`).
- **Name what you benched and why.** One line per notable cut lets the user overrule you cheaply.
- **Ordering is profile-dependent.** A reveal is an ordered narrative (no adjacent duplicate angles). A wedding gallery is chronological/by-segment, not a story. Real-estate is a walkthrough. The profile says which.
- **The taste guide overrides the generic.** If a taste guide was supplied in Step 0, it outranks the profile's default sense of "best." Curate to the user's eye, not yours, and reference the guide when a pick would otherwise look surprising.

Show the user your picks before staging — ideally a contact sheet of just the chosen set. They're about to spend real time editing these; a 30-second confirm beats re-editing the wrong set.

### 4. Stage the picks

```bash
bash scripts/stage-picks.sh --manifest <workdir>/manifest.tsv \
  --picks "11,3,44,9,..." --dest "<staging-folder>"
```

`--picks` is your ordered `#N` list. The script copies each full-res original into the dest as `01_<name>`, `02_<name>`, … in that order, records `_pick-order.tsv`, and sweeps the `._*` AppleDouble sidecars that copying to exFAT/network drives leaves behind. For unordered deliveries (weddings), the slot numbers are just a stable sequence; for by-segment delivery, run it once per segment into a per-segment subfolder.

### 5. Hand off to the edit pass (edit-always clients)

Tell the user exactly which files to edit and flag anything orientation-sensitive. They edit into a sibling `_edited/` folder. Wait for that before building anything downstream.

### 6. Rebuild the deliverable (optional, ordered profiles)

For a carousel opener with the "swipe to reveal one continuous image" effect, split the hero landscape into two seamless halves:

```bash
bash scripts/split-hero.sh --src "<edited>/01_<hero>.jpg" --dest "<post-folder>"
```

Writes `01.jpg` + `02.jpg` (each a clean 4:5 panel that lines up edge-to-edge) plus a `.seam-check.jpg` — **Read the seam check** and confirm the join is invisible and nothing important is bisected. Then place the remaining edited photos as `03.jpg…` in order. For full branded text-over-photo slides, hand off to `carousel-slides`.

---

## The scripts (generic, client- and shoot-type-agnostic)

| Script | Does | Key gotchas it handles for you |
|--------|------|-------------------------------|
| `contact-sheets.sh` | thumbnails + contact sheets + manifest | renders unviewable RAW via `sips`; macOS ImageMagick has **no default font** so annotate/montage need an explicit `-font` (baked in); `--recurse` for multi-folder shoots; filters `._*`; bash-3.2 portable |
| `stage-picks.sh` | copies chosen full-res files in order | resolves `#N`→original via manifest; slot-numbers in pick order; sweeps `._*` |
| `split-hero.sh` | seamless 4:5 split of a landscape hero | exact distortion-free crop; seam-check image; refuses non-landscape input |

Run with `bash scripts/<name>.sh` (no chmod needed). Every argument is documented in each script's header comment. They take paths as arguments and hardcode no client or shoot-type values.

---

## When this is NOT the right tool

- **Processing a whole shoot day** (audio, transcripts, renames, catalog) → `organize-shoot`. This skill only selects stills.
- **Rendering branded text-over-photo slides** → `carousel-slides`. This picks the photos; that designs the slides.
- **One known photo, no choosing** → just edit it; no contact sheets needed.
- **Video frame selection** → out of scope.

---

## Profiles

Read the one matching the shoot. Each defines what "best" and "order" mean, target-count defaults, dedup aggressiveness, what to flag, and output structure:

- `references/project-reveal.md` — remodel/build reveal → ordered narrative carousel (split-hero opener, zone walk)
- `references/wedding.md` — large gallery → unordered representative best-of, by-moment, tiered Haiku pre-pass at scale
- `references/event.md` — corporate/brand event → hero moments for a recap
- `references/real-estate.md` — interiors/listing → full room coverage, walkthrough order
- `references/custom.md` — anything else → you elicit goal, order, count, and must-haves from the user, then apply the universal loop

The canonical end-to-end carousel loop this plugs into is documented per-client (e.g. a client's `memory/reference_carousel_flow.md`). This skill is the "cull candidate photos" stretch of that loop, generalized across shoot types.
