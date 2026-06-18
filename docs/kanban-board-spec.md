# Content Pipeline Kanban Board — Build Spec

A live web-based Kanban board that reads content note markdown files from the 1610 Marketing Toolkit, displays them as draggable cards organized by status, and writes status changes back to the files when cards are moved between columns.

---

## What This App Does

The toolkit generates markdown files called **content notes** — one per piece of content (a reel, carousel, photo post, etc.). Each note has YAML frontmatter with a `status` field that tracks where it is in the production pipeline. An outside video editor needs to see which pieces are ready to edit, click into them for instructions, and mark them as in-progress or done.

The Kanban board is the editor's primary interface. They don't use Obsidian. They don't see the vault. They see this board.

---

## File System Structure

```
mktkit/
└── clients/
    └── [client-name]/                    # One folder per client
        ├── CLAUDE.md                     # Client config (has footage path convention)
        └── outputs/
            ├── content/                  # Content notes live here (flat, no subfolders)
            │   ├── 2026-04-01-CP-01-1981-kitchen-part-2.md
            │   ├── 2026-04-03-CP-02-shower-knob-placement.md
            │   └── ...
            ├── biweekly-briefs/          # Brief files (linked from content notes)
            │   ├── 2026-03-30-to-04-11-biweekly-brief.md
            │   └── ...
            └── monthly-briefs/

```

The app needs a **client selector** or a **path input** to know which `clients/[client-name]/outputs/content/` folder to read from. It should support switching between clients.

---

## Content Note Anatomy

Every content note is a markdown file with two parts: YAML frontmatter (structured data) and a markdown body (human-readable content).

### YAML Frontmatter Schema

```yaml
---
content_id: "CP-20260404-03"                    # Unique ID (PREFIX-YYYYMMDD-NN)
title: "Pocket Doors vs Cavity Sliders"         # Human-readable title — displayed on the card
client: "example-client"                   # Client folder name
brief: "[[2026-03-30-to-04-11-biweekly-brief]]" # Wiki-link to source brief (empty string "" for ad-hoc pieces)
status: captured                                 # Current pipeline status — THIS IS WHAT THE KANBAN MOVES
post_date: 2026-04-04                            # Scheduled post date
platform:                                        # Target platforms (list of strings)
  - Instagram
  - Facebook
  - YouTube Shorts
  - TikTok
format: "Reel 45-60s"                           # Content format (see format types below)
project: "Smith"                         # Internal project name (may be empty for non-project content)
project_social_name: "Vintage Addition"             # Public-facing project name (may be empty)
duration: "45-60s"                               # Target duration for video (empty for photo/carousel)
source_footage: "Acme Builders / 2026_Smith_Addition / 2026-03-09 / CB-Smith-PocketDoors-CavitySliders.MP4"
                                                 # Full navigable path to footage from the shared drive root
                                                 # Empty when status is concept or pre-production
shoot_date: 2026-03-09                           # When footage was/will be shot
tags: [educational, reel, content-bank]          # Obsidian tags (array of strings)
---
```

#### Required Fields
| Field | Type | Description |
|-------|------|-------------|
| `content_id` | string | Unique ID: `PREFIX-YYYYMMDD-NN` |
| `title` | string | Human-readable title |
| `client` | string | Client folder name |
| `status` | string | Pipeline status (see Status Workflow below) |
| `post_date` | date | Scheduled post date (YYYY-MM-DD) |
| `platform` | list | Target platforms |
| `format` | string | Content format |

#### Optional Fields
| Field | Type | Description |
|-------|------|-------------|
| `brief` | string | Wiki-link to source brief, or `""` for ad-hoc |
| `project` | string | Internal project name |
| `project_social_name` | string | Public-facing project name |
| `duration` | string | Target duration (e.g., "60-90s") |
| `source_footage` | string | Full path to footage from shared drive root |
| `shoot_date` | date | When footage was/will be shot |
| `tags` | list | Tags for filtering |

### Status Workflow (Kanban Columns)

These are the possible values for the `status` field. Each becomes a column on the Kanban board.

```
concept → pre-production → captured → editing → pre-approval → approved → scheduled → published
```

| Status | Column Label | What It Means | Who Acts |
|--------|-------------|---------------|----------|
| `concept` | Concept | Idea exists, hook/format defined. No footage yet. | AI CMO / Content Manager |
| `pre-production` | Pre-Production | Shot list finalized, shoot scheduled, talent confirmed. | Content Manager |
| `captured` | Ready to Edit | Footage/photos captured. Editor Brief populated. **Editor starts here.** | Editor |
| `editing` | Editing | Editor is actively assembling the piece. | Editor |
| `pre-approval` | Review | Edit complete, awaiting team review. | Content Manager |
| `approved` | Approved | Approved, no changes needed. | Content Manager |
| `scheduled` | Scheduled | Captions finalized, post scheduled on platform. | Content Manager |
| `published` | Published | Live on platform. | — |

**Revision loop:** A card can move backward from `pre-approval` to `editing` (with revision notes appended to the Revision History section in the note body).

**Important for the board:** The editor primarily works with `captured` → `editing` → `pre-approval`. The other columns exist for visibility but the editor rarely interacts with them.

### Content Format Types

The `format` field describes what kind of content this is. Common values:

| Format | Description |
|--------|-------------|
| `Reel 30-45s` | Short-form vertical video, 30-45 seconds |
| `Reel 45-60s` | Medium-form vertical video |
| `Reel 60-90s` | Longer vertical video |
| `Carousel 6-8` | Multi-slide image post (6-8 slides) |
| `Carousel 4-6` | Shorter carousel |
| `Photo` | Single photo post |
| `Story` | Instagram/Facebook story |

The format is free-text but follows these patterns. Parse the first word to determine the content type (Reel = video, Carousel = photos, Photo = single image).

### Content Note Types

There are three logical types of content notes. They all use the same schema — the type is inferred from the combination of fields:

| Type | How to Identify | Description |
|------|----------------|-------------|
| **Brief-generated** | `brief` field has a wiki-link (e.g., `"[[brief-filename]]"`) | Created as part of a biweekly or weekly content plan. Tied to a specific brief cycle with a planned post date. |
| **Ad-hoc** | `brief` field is `""` (empty string) | One-off content idea not tied to a brief. Created from shoot-review when bonus footage is captured, or from a spontaneous idea. Enters the same pipeline. |
| **Content bank** | Has `content-bank` in `tags` and `source_footage` points to a `CB-` prefixed file | Pre-shot footage sitting in the bank, waiting to be scheduled. Often educational clips shot opportunistically. |

All three types use the same Kanban workflow. The only difference is where they came from and whether they have a `brief` link.

---

## Body Structure (Markdown After Frontmatter)

The body has a fixed section order. The Editor Brief is always first.

### Section Order

```
## Editor Brief          ← EDITOR READS THIS (the only section they need to start work)
---                      ← visual separator
## Concept               ← internal: why this piece exists (strategy context)
## Script                ← timing breakdown for video (or ## Carousel Structure for photo)
## Caption               ← social media caption text
## Shot List             ← checklist of shots (checked off after capture)
## Edit Notes            ← working draft of edit instructions (Editor Brief consolidates this)
## Revision History      ← append-only log of all status changes
```

### The Editor Brief Section (What the Editor Sees)

This is the most important section for the Kanban board. When an editor clicks into a card, **this is what they need to see first** — and ideally, this is all they need.

#### Video Content Editor Brief
```markdown
## Editor Brief

**Deliverable:** Reel 60-90s — Instagram, Facebook, YouTube Shorts, TikTok
**Footage:** `Acme Builders / 2026_Jones_Kitchen / 2026-03-23`
**Key Files:** ARoll-Jones-Kitchen-DemoToFraming.MP4 (113s) + 2 supplementary takes
**Duration:** 60-90s

**What to Make:**
Alex walks the gutted kitchen showing demo results and framing changes. Part 2 of a series.

**Edit Direction:**
- Text overlay at start: "1981 KITCHEN | PART 2"
- No slow intro or logo bumper — straight into gutted kitchen
- Follow Alex's movement, insert B-roll for detail shots

**Script:** See full timing breakdown below.

**Brief:** [[2026-03-30-to-04-11-biweekly-brief]]

---
```

#### Carousel/Photo Editor Brief
```markdown
## Editor Brief

**Deliverable:** Carousel 6-8 slides — Instagram, Facebook, Pinterest
**Photos:** `Acme Builders / 2026_Brown_Kitchen / 2026-04-13`
**Slides:** 6-8

**What to Make:**
Before/after final reveal. Slide 1 is before, Slide 2 is after from same angle. Slides 3-7 detail shots. Slide 8 text slide.

**Edit Direction:**
- Match before/after angles exactly
- Text slide: "Vintage Kitchen Remodel | Acme Builders | [City, State]"

**Slide Breakdown:** See carousel structure below.

**Brief:** [[2026-04-20-to-05-02-biweekly-brief]]

---
```

#### Placeholder (Pre-Shoot — Not Ready for Editor)
```markdown
## Editor Brief

> Footage not yet captured. This section will be populated after the shoot.

**Deliverable:** Reel 60-90s — Instagram, Facebook, YouTube Shorts
**Duration:** 60-90s

**Brief:** [[2026-04-20-to-05-02-biweekly-brief]]

---
```

### Editor Brief Fields Reference

| Field | Present When | Description |
|-------|-------------|-------------|
| **Deliverable** | Always | Format + platforms in one line. What the editor is creating. |
| **Footage** / **Photos** | `status: captured` or later | Full navigable path from shared drive root to the footage folder. Editor clicks through this path to find files. |
| **Key Files** | `status: captured` or later | Specific filenames within the footage folder. Primary A-roll + duration, plus count of supplementary takes. |
| **Duration** | Video content | Target duration for the finished piece. |
| **Slides** | Carousel content | Target slide count. |
| **What to Make** | `status: captured` or later | 2-3 plain sentences. No strategy language — just what the piece IS. |
| **Edit Direction** | `status: captured` or later | Bullet list: text overlays (exact text), transitions, music, trim targets, pacing. |
| **Script** / **Slide Breakdown** | When applicable | Reference to the Script or Carousel Structure section lower in the note. |
| **Brief** | When tied to a brief | Wiki-link to the source biweekly/weekly brief. The editor can click this for more context. |

---

## Kanban Board Behavior

### Card Display

Each card on the board shows:

**Card front (collapsed — visible on the board):**
- **Title** (from `title` field)
- **Format badge** (e.g., "Reel 60-90s" or "Carousel 6-8")
- **Project name** (from `project_social_name` if available, otherwise `project`)
- **Shoot date** (from `shoot_date` — for sorting and age indication)
- **Platform icons** (from `platform` list)

**Card expanded (when clicked — detail view):**
- Everything from the card front
- The full **Editor Brief** section rendered as formatted markdown
- The **Script** or **Carousel Structure** section (if it exists)
- A link to the **Brief** file (from the `brief` frontmatter field)
- The `source_footage` path (clickable or copyable)
- Current `status` with ability to change it

### Sorting Within Columns

Within each column, cards are sorted by `shoot_date` ascending — **oldest footage at the top, newest at the bottom.** This ensures the editor works on the most overdue content first.

If `shoot_date` is empty (some concept-stage notes), sort those to the bottom of the column and use `post_date` as a secondary sort.

### Drag-and-Drop Behavior

When a card is dragged from one column to another:

1. **Read the markdown file** from `clients/[client]/outputs/content/[filename].md`
2. **Parse the YAML frontmatter** (everything between the opening `---` and closing `---`)
3. **Update the `status` field** to the new column's status value
4. **Append a line to the `## Revision History` section** in the body:
   ```
   YYYY-MM-DD: Status → [new status]
   ```
   Use today's date. If moving to `editing`, append: `Status → editing`. If moving to `pre-approval`, append: `Status → pre-approval. Edit v1 ready`.
5. **Write the file back** — preserve all other frontmatter fields and body content exactly as-is. Do not modify anything except the `status` field and the Revision History append.

**Critical:** The YAML frontmatter must be written back with the same formatting — same field order, same quoting style, same list format. Use a YAML parser that preserves structure (not one that re-serializes and reorders fields).

### File Watching

The app should watch the `outputs/content/` directory for changes. Content notes are created and modified by the AI CMO agent (Claude), by Obsidian, and by this Kanban board. The board should:

- **Detect new files** and add them to the appropriate column
- **Detect modified files** (e.g., status changed by the AI CMO agent) and move cards accordingly
- **Detect deleted files** and remove cards
- **Not conflict** with external edits — if the file was modified externally while the board is open, the board should reload the file's current state, not overwrite it with stale data

### Filtering

The board should support filtering by:
- **Client** (required — selects which `clients/[client]/outputs/content/` folder to read)
- **Status range** (e.g., show only `captured` through `pre-approval` — the editor's working columns)
- **Project** (filter by `project` field)
- **Format** (filter by format type: Reel, Carousel, Photo)
- **Brief** (filter by which brief cycle a piece belongs to)

### Brief Links

The `brief` field contains an Obsidian wiki-link like `"[[2026-03-30-to-04-11-biweekly-brief]]"`. To resolve this to a file path:

1. Strip the `[[` and `]]` brackets
2. The file lives at `clients/[client]/outputs/biweekly-briefs/[brief-name].md`
3. Display the brief content as rendered markdown when the editor clicks the link

---

## How the Editor Uses This

The editor's workflow:

1. **Open the board.** They see all content across all columns. The `captured` column has the pieces ready for them.
2. **Look at the `captured` column.** Cards are sorted oldest-first — the piece at the top has been waiting longest.
3. **Click a card.** The Editor Brief expands. They read: what to make, where the footage is, how to edit it.
4. **Navigate to the footage.** They copy the `Footage:` path, open it on the shared drive (Google Drive or SSD), and find the files listed under `Key Files:`.
5. **Drag the card to `editing`.** The app updates the markdown file's `status` to `editing` and logs the change.
6. **Edit the video/carousel.** They follow the Edit Direction and Script.
7. **When done, drag the card to `pre-approval`.** The app updates `status` to `pre-approval`.
8. **If revisions are needed**, the content manager drags it back to `editing` — the editor sees it reappear.

The editor should never need to open Obsidian, read strategy documents, or ask the content manager "where's the footage?" or "what do I do with this?"

---

## Parsing Notes for Implementation

### Reading YAML Frontmatter from Markdown

Content notes use standard YAML frontmatter delimited by `---`:

```
---
key: value
list:
  - item1
  - item2
---

## Markdown body starts here
```

Use a markdown frontmatter parser. In JavaScript: `gray-matter`. In Python: `python-frontmatter`. The body is everything after the second `---`.

### Extracting the Editor Brief Section

The Editor Brief is always the first `## ` heading in the body. To extract it:

1. Find `## Editor Brief` in the body
2. Capture everything until the next `---` (horizontal rule) or the next `## ` heading, whichever comes first
3. Render as markdown

### Writing Status Changes Back

When updating a file:

1. Read the entire file
2. Parse frontmatter and body separately
3. Update `status` in the frontmatter object
4. Find `## Revision History` in the body
5. Append a new line at the end of that section (before the next section or EOF)
6. Re-serialize: frontmatter (between `---` delimiters) + body
7. Write the file atomically (write to temp file, then rename — prevents corruption if the app crashes mid-write)

### Wiki-Link Format

Wiki-links look like `"[[filename-without-extension]]"` in YAML (quoted string with brackets). To resolve:
- Strip quotes, strip `[[` and `]]`
- Append `.md`
- Look in the appropriate `outputs/` subfolder

---

## Example: Complete Content Note

```markdown
---
content_id: CP-20260404-03
title: "Pocket Doors vs Cavity Sliders"
client: example-client
brief: "[[2026-03-30-to-04-11-biweekly-brief]]"
status: captured
post_date: 2026-04-04
platform:
  - Instagram
  - Facebook
  - YouTube Shorts
  - TikTok
format: "Reel 45-60s"
project: "Smith"
project_social_name: "Vintage Addition"
duration: "45-60s"
source_footage: "Acme Builders / 2026_Smith_Addition / 2026-03-09 / CB-Smith-PocketDoors-CavitySliders.MP4"
shoot_date: 2026-03-09
tags: [educational, reel, content-bank, comparison]
---

## Editor Brief

**Deliverable:** Reel 45-60s — Instagram, Facebook, YouTube Shorts, TikTok
**Footage:** `Acme Builders / 2026_Smith_Addition / 2026-03-09 / CB-Smith-PocketDoors-CavitySliders.MP4`
**Duration:** 45-60s (raw is 52s)

**What to Make:**
Alex explains why standard pocket doors fail and shows the aluminum cavity slider alternative. Comparison/educational piece.

**Edit Direction:**
- Trim to 45-60s
- Text overlay for comparison: "Pocket Door vs Cavity Slider"
- Text-heavy for sound-off viewers
- End with: "Send this to someone building right now"
- 3-second hook: door sliding motion + text "POCKET DOORS SUCK"

**Brief:** [[2026-03-30-to-04-11-biweekly-brief]]

---

## Concept

Content bank piece. Alex explains why standard pocket doors fail and shows the aluminum cavity slider alternative. Strong educational content with a "better way" message.

## Script

Already shot (52s, shot 3/9). Trim to 45-60s.

## Caption

Pocket doors are one of those ideas that sounds great until you live with one.

They rattle. They jump the track. The hardware is hidden inside the wall, so when something breaks -- and something always breaks -- you're opening up drywall to fix it.

There's a better version. Aluminum cavity sliders. Same concept, door disappears into the wall, but the track system is engineered to actually last.

Send this to someone building or remodeling right now.

`#AcmeBuilders #RemodelingTips #DesignBuild`

## Shot List

- [x] Already captured (content bank, shot 3/9)

## Edit Notes

Trim to 45-60s. Add text overlay for comparison: "Pocket Door vs Cavity Slider." Text-heavy for sound-off viewers.

## Revision History

- 2026-03-23: Created from [[2026-03-30-to-04-11-biweekly-brief]]
- 2026-03-09: Footage captured at Smith. Source: CB-Smith-PocketDoors-CavitySliders.MP4
```

---

## Tech Recommendations

This is a local-first app that reads/writes files on disk. Good approaches:

- **Electron + React** — Desktop app with full filesystem access. Best for local file watching.
- **Next.js + local API** — Web UI with a Node.js backend that reads/writes the vault files. Can run as `localhost`.
- **Tauri + Svelte/React** — Lightweight desktop app alternative to Electron.
- **Python (Flask/FastAPI) + vanilla JS** — Simple backend that serves files, simple frontend with drag-and-drop.

The simplest viable approach: a Node.js server that watches the content folder and serves a static HTML page with a Kanban UI. The page uses fetch() to read notes and POST to update status. The server handles file I/O.

For drag-and-drop: use a library like SortableJS or dnd-kit (React).

For markdown rendering in the detail view: use marked.js or markdown-it.

For YAML parsing that preserves formatting: use `yaml` (js-yaml) with `keepBlobsInJSON` or `gray-matter` for reading. For writing back, use string manipulation on the raw frontmatter rather than full YAML re-serialization to preserve field order and formatting.
