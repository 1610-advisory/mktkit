---
name: carousel-slides
description: Generate Instagram/LinkedIn carousel slides (1080x1350 PNGs) for any toolkit client, using the client's photos as backgrounds with a darkened overlay and on-brand typography. Use when the user asks to "make slides", "create a carousel", "build the carousel for X", "design IG/LinkedIn slides", or any time a content note specifies a carousel deliverable. The skill verifies brand identity and photo library are established before rendering, asking the user only for what's missing.
metadata:
  version: 1.0.0
---

# Carousel Slides Generator

You are a designer-engineer that produces on-brand IG/LinkedIn carousel slides for any toolkit client. Each carousel is a folder of HTML/CSS/JS plus rendered 1080x1350 PNGs. The HTML doubles as a proof grid: open it in a browser to see all slides at once; run `node render.js` to export PNGs.

The skill works alongside `mkt-kit` and shares client context. **Strategy and copy come from the client's content note.** This skill handles visual execution only. Run the `mkt-kit` pack first (`DESIGN.md` / `brand-identity.md`, voice). Missing file: ask, append `knowledge/_intake-log.md`. Fonts not on disk: fetch per `mkt-kit/REFERENCE.md` before render.

---

## Where this fits in the standard carousel flow

Rendering (this skill) is step 4 of a fuller loop run every time: (1) source & concept, (2) identify candidate photos, (3) **photo handling — a per-client policy**, (4) build slides [this skill], (5) caption + humanizer, (6) assemble a single-file review and publish via `publish-share`, (7) revise to the same slug, (8) on approval render PNGs + package/schedule.

**Photo handling is a per-client policy, not a per-run question — read the client's CLAUDE.md.** Some clients always edit stills before use (pattern: stage candidate raws → human edits into an `_edited/` folder → build from edited); others never edit and you use photos as-is. If a client's policy isn't recorded, ask once and write it to their CLAUDE.md. A client's `memory/reference_carousel_flow.md` is the reference pattern for the full loop.

---

## Hard preflight gates

**Do not generate any slides until both gates pass.** If a gate fails, run the recovery flow for that gate, then continue.

1. **Brand identity is loaded.** You must have these values resolved before opening the template:
   - Color palette (background/ivory, surface/cream, primary, accent, foreground)
   - Serif font (for quotes/titles)
   - Sans font (for eyebrow/body/footer)
   - Photo overlay opacity (default 0.55-0.78 vertical gradient — adjust per client)
   - Optional: logo path, watermark/handle text

2. **Photo library is reachable.** You must have a list of candidate photo paths that exist on disk. At least 1 photo per slide is required — if there are fewer photos than slides, you may either reuse photos or fall back to a `text-only` slide variant.

---

## Brand fidelity — the failure mode that gets carousels rejected

A slide that "looks like a nice generic template" is a failure. The test is: *could this be any other business in the category?* If yes, it's not done. These rules prevent the most common rejection (learned the hard way on an early client build):

1. **Derive brand from the client's LIVE website, not a guess or a provisional doc.** If `brand-identity.md` is marked provisional/needs-update, or if it disagrees with the site, read the actual site first: `globals.css`/`tailwind.config` for exact color hex + design tokens, the font loader (`layout.tsx`, `<link>`, `@font-face`) for the real font family, and `public/`/`assets/` for logo files. Then update `brand-identity.md` with the real values. Guessing colors and fonts produces off-brand slides.
2. **Put the logo on every slide.** No logo = no brand recognition. Pull the real logo asset (light variant on dark/photo slides, dark variant on light slides; badge/seal for the CTA). Copy it into the carousel's `assets/`.
3. **Match the client's real emphasis convention — do NOT default to italic + accent-color on a word.** Italic-highlighting a single word is a classic AI tell and is off-brand for most trade/industrial clients. Check how the site emphasizes: most use **bold weight in the same color**, or an underline/rule in the accent color. Use that. Reserve the accent color for structural elements (eyebrows, numerals, rules, CTA), not inline word-coloring, unless the site does otherwise.
4. **Match the site's typographic posture** — all-caps vs sentence case, letter-spacing, serif vs sans. An editorial serif (e.g. Playfair) on a workmanlike trade brand reads wrong even if it's "pretty."

When in doubt, open the client's homepage and a real slide side by side. They should feel like the same company.

## Step 1 — Identify client and source

When invoked, determine the **client folder** (e.g. `clients/example-client/`). If you cannot infer it from the conversation or working directory, ask: *"Which client is this carousel for?"*

Determine the **content source**:
- **Content note path** (preferred): a markdown file in `clients/[client]/outputs/content/` describing carousel slide structure
- **Blog post**: a published or draft post to repurpose into a carousel
- **Ad-hoc concept**: user-supplied slide-by-slide bullets

If the source is a content note, read it to extract:
- Date and slug for the carousel folder name
- Slide count (typically 5-7) and per-slide copy/structure
- Any "Edit Notes" with design preferences

---

## Step 2 — Verify brand identity (Gate 1)

**Read `clients/[client]/knowledge/brand-identity.md`.**

If it exists and has all required fields, parse the values into local variables and continue.

If it is missing or incomplete, run the **Brand Discovery Flow**:

1. Check the client's `CLAUDE.md` for a `Website` or repo path. If found, read `globals.css`, `tailwind.config.ts`, or any obvious brand stylesheet to seed initial values. Show the user what you found and ask for confirmation/corrections.
2. If no website is referenced, ask the user (use `AskUserQuestion` for the small set of choices, free-text for hex codes):
   - Background / paper color (hex)
   - Primary brand color (hex)
   - Accent color for highlights (hex)
   - Foreground / text color on light surfaces (hex)
   - Serif font (Google Fonts name) — *for big quotes and titles*
   - Sans font (Google Fonts name) — *for eyebrow, body, footer*
   - Optional logo file path
   - Default photo overlay strength: light / medium / heavy
3. Write the values to `clients/[client]/knowledge/brand-identity.md` using the schema in `references/brand-identity-schema.md`. Future runs will reuse this file.

---

## Step 3 — Verify photo library (Gate 2)

**Read `clients/[client]/knowledge/visual-library.md`.**

If it exists, you have a list of folders/sources where photos live. Globs into those folders to enumerate candidate photos.

If it is missing or empty, run the **Visual Library Flow**:

1. Ask: *"Where do this client's photos live? Paste any folder paths, separated by newlines. Personal favorites, project shoots, anything I should pull from."*
2. For each path, verify it exists and contains images. If not, push back.
3. Write a `visual-library.md` using the schema in `references/visual-library-schema.md`.

After verification, **enumerate candidate photos** (jpg/png/heic/webp) from the listed sources. Read 3-7 of them via the Read tool to understand their mood (subjects, colors, lighting). Note candidates as `path | brief description | mood tags`.

---

## Step 4 — Plan the carousel

Build a slide plan as a small markdown table before generating:

| # | Type | Photo | Copy summary |
|---|------|-------|--------------|
| 1 | title | `IMG_3037.jpg` (golden field) | "Open to Close" + subtitle |
| 2 | pull-quote | `064A1408.jpg` (work, dawn) | "My dad worked open to close..." |
| ... |

**Slide types available** (see `references/slide-types.md` for full specs):
- `title` — eyebrow + big serif title (with italic accent word) + subtitle
- `pull-quote` — quote-mark glyph + serif quote with gold-italic accent phrases
- `numbered-list` — eyebrow + serif headline + roman-numeral list of items with right-aligned notes
- `stat` — big serif number + short caption underneath
- `cta` — "Read the full essay" style with URL underneath, larger photo room
- `text-only` — solid brand background, no photo (use sparingly, for transitions or punchy single lines)

Show the plan to the user. Wait for approval or edits before rendering. Auto-propose photo→slide mappings, but always allow swaps.

---

## Step 5 — Generate the carousel project

Create the project folder: `clients/[client]/outputs/slides/[YYYY-MM-DD]-[slug]/`

Run the init script (or do it manually):
```
bash scripts/init-carousel.sh "<client-slides-folder>"
```

This copies `references/slide-template.html` and `references/render.js` into the folder.

Then **edit `slides.html`** to:
1. Replace the `:root` CSS variables with this client's brand values
2. Replace placeholder photo URLs with `file://` paths to the chosen photos
3. Author each `<section class="slide">` with the right slide-type structure (copy from `references/slide-types.md` blocks)
4. Update the proof-grid header with carousel title and date
5. Update slide labels (`01 · Title`, `02 · The Hours`, etc.)

**Style discipline:**
- Use 1080×1350 (Instagram portrait 4:5). Same aspect works for LinkedIn.
- Default overlay: dark gradient `rgba(20,15,12,0.55)` top → `rgba(20,15,12,0.78)` bottom + radial vignette
- For lighter photos (sky, snow): bump overlay to 0.62/0.85
- For already-dark photos: lighter overlay 0.40/0.65
- Body padding: 96px top/bottom, 88px left/right
- Type sizes (1080-wide canvas):
  - Title: 168px serif / 38px serif italic subtitle
  - Pull-quote: 76px serif (or 64px `tighter` for longer quotes)
  - Numbered-list headline: 64px / item names: 50px / notes: 24px italic
  - CTA: 124px serif / 30px sans link
  - Eyebrow: 22px sans uppercase 0.32em letterspacing
  - Footer: 18px sans uppercase 0.4em letterspacing

**Copy discipline:**
- Use accent color sparingly — italic + gold on the 1-3 most important phrases per slide, not entire sentences
- Each pull-quote should fit on one screen at the chosen size — if it doesn't, switch to `tighter` (64px) or break into two slides
- Footer pattern: `0X · Carousel Name` left, `@handle` right
- Read the client's `voice-guidelines.md` for any voice rules (e.g. no em dashes, use commas)

---

## Step 6 — Render PNGs

Install Playwright in the carousel folder (one-time per folder; or symlink a shared `node_modules` later):
```
cd "<client-slides-folder>" && npm init -y && npm install playwright && npx playwright install chromium
```

Render:
```
node render.js
```

This writes `slide-1.png` through `slide-N.png` at 2160×2700 (deviceScaleFactor: 2 for retina exports). Verify file sizes are non-trivial (each slide is typically 4-8 MB at 2x).

---

## Step 7 — Proof and iterate

Open `slides.html` in any browser to see all slides at once on the proof grid. Read each rendered PNG via the Read tool to verify text legibility, photo overlay strength, and brand color rendering.

Show the user the proof grid (or one or two key slides) and ask:
- Any copy edits?
- Any photo swaps?
- Overlay too dark / too light on any slide?
- Want a square (1080×1080) version for grid cross-posting?

Iterate by editing `slides.html` only. Re-run `node render.js` to refresh PNGs.

---

## Output structure

```
clients/[client]/outputs/slides/[YYYY-MM-DD]-[slug]/
├── slides.html         # Single source — proof grid + render targets
├── render.js           # Playwright export script
├── package.json        # playwright dep
├── slide-1.png         # 2160×2700 (1080×1350 @ 2x)
├── slide-2.png
└── ...
```

---

## Conventions across clients

- **One brand-identity.md per client** — version-controlled in the client folder
- **One visual-library.md per client** — paths to photo sources, refreshed when shoots happen
- **Carousels live under `outputs/slides/[YYYY-MM-DD]-[slug]/`** — same date convention as other outputs
- **The .html file is the source of truth** — never edit PNGs directly; re-render from HTML
- **Never commit `node_modules`** — add to client `.gitignore` if needed

---

## When this skill is NOT the right tool

- **Single static graphics** (one quote card, not a multi-slide carousel) — simpler to edit one slide template directly
- **Animated/video reels** — out of scope; use a video editor
- **Interactive web components** — this renders flat PNGs only

---

## References

- `references/brand-identity-schema.md` — schema for `clients/[client]/knowledge/brand-identity.md`
- `references/visual-library-schema.md` — schema for `clients/[client]/knowledge/visual-library.md`
- `references/slide-template.html` — master HTML template with proof-grid + all slide types
- `references/slide-types.md` — per-type HTML blocks to copy into slides.html
- `references/render.js` — universal Playwright render script
- `scripts/init-carousel.sh` — scaffolds a new carousel project folder
