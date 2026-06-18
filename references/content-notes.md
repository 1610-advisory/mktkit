# Content Notes System

Each content piece generated in a biweekly or weekly brief is saved as its own atomic markdown note. This enables Kanban board tracking, per-piece status management, and clickable navigation from briefs to individual content details.

Monthly plans do NOT create content notes — they remain strategic documents.

---

## Status Workflow

```
concept → pre-production → captured → editing → pre-approval → approved → scheduled → published
                                        ↑                          |
                                        └──── (revision needed) ───┘
```

| Status | Meaning |
|--------|---------|
| `concept` | Initial idea from brief generation. Has hook, format, platform defined. |
| `pre-production` | Shot list finalized, shoot day scheduled, talent/location confirmed. |
| `captured` | Footage/photos taken. `source_footage` field populated. |
| `editing` | Editor is assembling the piece. |
| `pre-approval` | Edit complete, awaiting client/team review. |
| `approved` | Approved with no changes needed. |
| `scheduled` | Captions finalized, post scheduled in platform or Typefully. |
| `published` | Live on platform. |

**Revision loop:** If changes are needed at `pre-approval`, set status back to `editing` and append revision notes to the `## Revision History` section.

---

## File Location & Naming

**Location:** `clients/[client]/outputs/content/` (flat folder, no subfolders)

**Naming pattern:** `YYYY-MM-DD-PREFIX-NN-slug.md`

- `YYYY-MM-DD` = scheduled post date
- `PREFIX` = client abbreviation (e.g., `AB` for Acme Builders, `PP` for client name initials)
- `NN` = sequential number within the brief (01, 02, 03...)
- `slug` = lowercase hyphenated title (max 40 chars)

**Examples:**
- `2026-04-15-AB-01-kitchen-final-reveal.md`
- `2026-04-17-AB-02-kitchen-walkthrough.md`
- `2026-03-05-PP-01-origin-story-reel.md`

**Content ID format:** `PREFIX-YYYYMMDD-NN` (matches filename without the slug)
- `AB-20260415-01`
- `PP-20260305-01`

---

## YAML Frontmatter Schema

```yaml
---
content_id: "AB-20260415-01"       # Unique ID, maps to content-log.csv
title: "Kitchen Final Reveal"      # Human-readable name
type: content-note                 # Always "content-note" — enables Dataview queries and Kanban filtering
client: "acme-builders"            # Client folder name
brief: "[[brief-filename]]"       # Wiki-link to source brief (empty string for ad-hoc)
status: concept                    # Current workflow status
assigned_to:                       # List of people assigned to this piece (e.g., editor, photographer)
  - ""
post_date: 2026-04-15             # Scheduled post date
platform:                          # Target platforms (list)
  - Instagram
  - Facebook
format: "Carousel 6-8"            # Content format
project: "Mitchell"                # Internal project name (if applicable)
project_social_name: "Vintage Kitchen" # Public-facing project name
duration: ""                       # Target duration for video (e.g., "60-90s")
source_footage: ""                 # Full path from client's footage root (see client CLAUDE.md → Footage & Drive Convention)
shoot_date: 2026-04-06            # When footage was/will be shot
tags: [reveal, carousel]           # Obsidian tags for filtering
---
```

**Required fields:** content_id, title, type, client, status, post_date, platform, format
**Optional fields:** brief, assigned_to, project, project_social_name, duration, source_footage, shoot_date, tags

---

## Body Sections

### `## Editor Brief`

**First section after frontmatter. This is the editor handoff — everything an outside editor needs to start work without asking questions.** Followed by a `---` separator to visually divide from internal planning sections.

**This is what renders in the Obsidian Kanban modal.** Other sections (Concept, Script, Caption, etc.) are for strategic/internal use and are not shown to the editor on the board. If it's information the editor needs, it MUST live inside `## Editor Brief`.

**Every populated Editor Brief (status `captured` or later) MUST contain these four blocks, in order:**
1. **Deliverable + Footage + Key Files + Duration** (the logistics header)
2. **What to Make** — 2-3 plain sentences describing the piece, the story it tells, and any series context. No strategy jargon.
3. **Edit Direction** — bulleted list: text overlays (exact text), 3-second hook description, end card, trim targets, pacing/music notes, anything take-specific.
4. **Brief** — wiki-link back to the source brief.

Missing blocks 2 or 3 is the most common drift. Do not ship a captured note without both.

**When to populate:**
- At brief generation (`status: concept`): placeholder with Deliverable + Duration only
- At shoot-review (`status: captured`): fully populated with all four blocks above

**Video content:**
```markdown
## Editor Brief

**Deliverable:** Reel 60-90s — Instagram, Facebook, YouTube Shorts
**Footage:** `[footage root] / [project folder] / [shoot date]`
**Key Files:** ARoll-Project-Description.MP4 (113s) + 2 supplementary takes
**Duration:** 60-90s

**What to Make:**
2-3 plain sentences. What the piece IS, what story it tells, any series context. No strategy language.

**Edit Direction:**
- Text overlays (exact text)
- Transitions, music, pacing notes
- Trim targets, what to cut/keep

**Script:** See full timing breakdown below.

---
```

**Carousel/photo content:**
```markdown
## Editor Brief

**Deliverable:** Carousel 6-8 slides — Instagram, Facebook, Pinterest
**Photos:** `[footage root] / [project folder] / [shoot date]`
**Slides:** 6-8

**What to Make:**
What the carousel shows, slide flow, any before/after matching.

**Edit Direction:**
- Slide-specific notes
- Text overlays, branding

**Slide Breakdown:** See carousel structure below.

---
```

**Placeholder (pre-shoot):**
```markdown
## Editor Brief

> Footage not yet captured. This section will be populated after the shoot.

**Deliverable:** Reel 60-90s — Instagram, Facebook, YouTube Shorts
**Duration:** 60-90s

---
```

**Footage path convention:** Each client's `CLAUDE.md` defines their footage root and folder structure. When populating `source_footage` and the Editor Brief's Footage field, use the client's path convention (e.g., `Client Name / project_folder / YYYY-MM-DD`). For single-file content bank pieces, append the filename to the path.

---

### `## Concept`
Why this content exists. What story it tells. Data support from `whats-working.md`. Connection to goals.

**If the footage has been shot:** Read the actual transcript (`.txt` file in `Audio/` subfolder) before writing this section. The concept must describe what was actually said and shown on camera — not what you infer from the filename or file-mapping summary. Use the speaker's real talking points, materials mentioned, and framing. If no transcript exists, flag it rather than guessing.

### `## Script` (for video content)
| Section | Time | Visual | Audio |
|---------|------|--------|-------|
| HOOK | 0-3s | ... | ... |
| BODY | 3-30s | ... | ... |
| CLOSE | 30-60s | ... | ... |

### `## Carousel Structure` (for carousel content, replaces Script)
Slide-by-slide breakdown:
1. **Slide 1:** [description]
2. **Slide 2:** [description]

### `## Caption`
Full caption text with hook, body, CTA, and hashtags.

### `## Shot List`
Checklist of shots needed specifically for this piece:
- [ ] Shot description

### `## Edit Notes`
Text overlays, transitions, music direction, duration targets, any editor-facing instructions. When the `## Editor Brief` is populated (after shoot-review), the Edit Direction field in the Editor Brief consolidates this section's content for the editor. `## Edit Notes` remains in the note as the working draft area — the Editor Brief pulls from it, not the other way around.

### `## Revision History`
Append-only log. Every status change or significant update gets a line:
- `YYYY-MM-DD: Created from [[brief-filename]]`
- `YYYY-MM-DD: Status → captured (organize-shoot). Source: ARoll-Mitchell-Reveal.MP4`
- `YYYY-MM-DD: Status → editing. Assigned to [editor]`
- `YYYY-MM-DD: Status → pre-approval. Edit v1 ready`
- `YYYY-MM-DD: Status → editing (revision). Feedback: shorten intro, add text overlay at 0:15`
- `YYYY-MM-DD: Status → approved`
- `YYYY-MM-DD: Status → scheduled. Typefully draft created`
- `YYYY-MM-DD: Status → published`

---

## How Briefs Reference Content Notes

When a biweekly or weekly brief is generated, inline content piece details are replaced with a linked table:

```markdown
## Content Pieces

| # | Title | Format | Status | Link |
|---|-------|--------|--------|------|
| 1 | Vintage Kitchen Final Reveal | Carousel 6-8 | concept | [[2026-04-15-CP-01-example-kitchen-final-reveal]] |
| 2 | Kitchen Final Walkthrough | Reel 60-90s | concept | [[2026-04-17-CP-02-example-kitchen-final-walkthrough]] |
```

The brief retains:
- Overview, performance snapshot, testing section
- Master shot list (consolidated by location for shoot-day efficiency)
- Posting schedule table
- Cross-platform notes, checklists

Each content note has the full detail: concept, script/carousel structure, caption, piece-specific shot list, edit notes.

---

## Ad-Hoc Content Notes

For one-off content ideas not tied to a brief:
- Set `brief: ""` in frontmatter
- Fill all other applicable YAML fields
- The note enters the same Kanban pipeline and can be tracked identically
- Use the same naming convention: `YYYY-MM-DD-PREFIX-NN-slug.md` (use the target post date and next available number)

---

## Integration with Other Workflows

### organize-shoot / shoot-review
After matching footage to content pieces:
1. Find matching content notes in `outputs/content/`
2. **Read the transcript** (`.txt` file in `Audio/` subfolder) for every matched piece before writing or updating any content direction. This is mandatory — do not skip it.
3. Set `status: captured`
4. Set `source_footage` to the full navigable path from the client's footage root (see client `CLAUDE.md` → Footage & Drive Convention). For single-file pieces, append the filename.
5. Generate/update the `## Editor Brief` section with footage path, key files, deliverable, duration, what to make, and edit direction. **The "What to Make" and "Edit Direction" must reflect what was actually said in the transcript**, not what the filename or concept originally assumed. If the transcript reveals the piece is about something different than planned, rewrite the Concept, Caption, and Script sections to match reality.
6. Append to Revision History: `YYYY-MM-DD: Status → captured. Source: [filename]`
7. For pieces NOT captured: append `YYYY-MM-DD: NOT CAPTURED — needs rescheduling`

### Content logging
When logging published content (`log content`):
- `content_id` in `tracking/content-log.csv` should match the content note's `content_id`
- Update the matching content note's status to `published`

### Typefully drafts
When creating Typefully drafts from content notes:
- Update `status: scheduled` after draft creation
- Append to Revision History with draft URL

---

## Obsidian Kanban Board Setup

To track content notes on a Kanban board in Obsidian:

1. Install the **Kanban** plugin (if not already installed)
2. Create a new Kanban board in `clients/[client]/outputs/`
3. Create lanes matching the status values: concept, pre-production, captured, editing, pre-approval, approved, scheduled, published
4. Add content notes as cards — dragging between lanes updates the note's `status` frontmatter property

Alternatively, use **Dataview** to create a live status dashboard:

```dataview
TABLE status, format, post_date, platform
FROM "clients/your-client-name/outputs/content"
WHERE status != "published"
SORT post_date ASC
```

Group by status:
```dataview
TABLE WITHOUT ID file.link AS "Content", format, post_date
FROM "clients/your-client-name/outputs/content"
WHERE status = "editing"
SORT post_date ASC
```
