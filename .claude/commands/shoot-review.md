---
description: Post-organize review — update content notes, surface bonus footage, suggest new content ideas
argument-hint: /path/to/shoot-folder
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, AskUserQuestion]
---

# Post-Shoot Review

Run this **after** `/organize-shoot` has processed a shoot folder. It bridges the gap between raw organized footage and the content pipeline:

1. Updates existing content notes with actual file locations
2. Flags planned content that wasn't captured
3. Surfaces unplanned footage and suggests new content ideas
4. Creates new ad-hoc content notes for anything the user approves

## Arguments

User provided: $ARGUMENTS

Parse for:
- **Path** to the processed shoot folder (the same folder that was passed to `/organize-shoot`)

If no path provided, ask:
1. "Where is the processed shoot folder? (full path — same one you ran /organize-shoot on)"

---

## Workflow

### Step 1: Gather Organize-Shoot Output

Read the master file-mapping from the shoot folder:

```bash
cat "[shoot-folder]/file-mapping.csv"
```

If no `file-mapping.csv` exists at root, look for per-location `file-mapping.txt` files:

```bash
find "[shoot-folder]" -name "file-mapping.txt" -maxdepth 2
```

From the file-mapping, build a list of **all named content pieces**:
- **A-Roll** — files starting with `ARoll-` (or legacy `Post[N]-`). Extract: location, description, duration, transcript summary.
- **Content Bank** — files starting with `CB-`. Extract: location, description, duration, transcript summary.
- **Named B-Roll** — files starting with `BRoll-`. Extract: location, description.
- **Unmatched with speech** — files with transcripts that weren't classified. These are the most interesting for new content ideas.

Also read transcripts from the `Audio/` subfolders — particularly for files that weren't confidently named. The raw transcript text is the richest source for content ideas.

### Step 2: Read the Current Bi-Weekly Brief

Find the most recent biweekly brief:
```
clients/[client]/outputs/biweekly-briefs/
```

Extract:
- Planned content pieces (titles, formats, projects)
- Shot list (what was supposed to be captured)
- Content bank items (shot from previous shoots, planned for this cycle)

### Step 3: Read All Matching Content Notes

Scan `outputs/content/` for content notes that match the projects in this shoot:

```bash
grep -l "project: \"[ProjectName]\"" outputs/content/*.md
```

Also check for content notes whose `shoot_date` matches this shoot's date.

For each matching note, read:
- `content_id`, `title`, `status`, `source_footage`, `project`, `shoot_date`
- The shot list section (to check what was planned)

### Step 4: Match Footage → Content Notes

For each A-Roll and CB piece from the file-mapping:

1. **Find the matching content note** by cross-referencing:
   - Project name in the filename → `project` field in frontmatter
   - Description keywords → `title` or concept text
   - If ambiguous, use the transcript summary to disambiguate

2. **Read the full transcript** for every matched piece (`.txt` file in `Audio/` subfolder). This is mandatory — not optional, not "if ambiguous." The transcript is the ground truth for what was actually said on camera. Filenames and file-mapping summaries are shorthand for identification only. Before writing or updating ANY content direction (Editor Brief, Concept, Caption, Script), verify that the existing content note accurately describes what the speaker said. If the transcript reveals the piece is about something different than the note assumed, rewrite the Concept, Caption, Script, and Editor Brief to match reality.

3. **Update the content note:**
   - Set `source_footage` to the full navigable path from the client's footage root (read the client's `CLAUDE.md` → **Footage & Drive Convention** section for the path pattern and project folder mapping). Example: `Acme Builders / 2026_Jones_Kitchen / 2026-03-23`. For single-file CB pieces, append the filename.
   - Set `status: captured` (only if currently `concept` or `pre-production`)
   - Set `shoot_date` to the actual shoot date (if different from planned)
   - Check off matching items in the `## Shot List` section
   - Append to `## Revision History`:
     ```
     YYYY-MM-DD: Status → captured (shoot-review). Source: [filename] ([duration]s)
     ```
   - **Generate/update the `## Editor Brief` section** (insert after frontmatter, before `## Concept`). This is the editor handoff — everything an outside editor needs to start work without asking questions:
     - **Deliverable:** `{format}` from frontmatter + `{platforms}` as comma-separated list
     - **Footage:** Full path from footage root using the client's convention (e.g., `[Client Name] / [project folder] / [YYYY-MM-DD]`)
     - **Key Files:** Primary A-roll filename + duration from file-mapping.csv. Note supplementary takes and B-roll count.
     - **Duration:** From frontmatter `duration` field
     - **What to Make:** Summarize the `## Concept` section in 2-3 plain sentences for an editor. Strip strategy language, data references, and performance citations. Keep only: what the piece IS, what story it tells, any series context.
     - **Edit Direction:** Convert the `## Edit Notes` section into a bullet list of action items. Include text overlay exact text, transitions, music direction, trim targets.
     - **Script:** If a `## Script` section exists, add "See full timing breakdown below." If it's a carousel, reference the Carousel Structure section instead.
     - End the Editor Brief with a `---` horizontal rule to separate from internal sections.
     - If a placeholder Editor Brief already exists (from brief generation), replace it entirely with the populated version.

4. **Track what was matched** for the summary in Step 6.

### Step 5: Flag Planned but NOT Captured

For content notes that:
- Match a project that was visited on this shoot day
- Have `status: concept` or `pre-production`
- Were NOT matched to any footage in Step 4

Append to their `## Revision History`:
```
YYYY-MM-DD: NOT CAPTURED on [shoot-date] shoot — needs rescheduling
```

Do NOT change their status — they stay as-is for the next shoot.

### Step 6: Identify Unplanned Footage (Bonus Content)

Compare the file-mapping against what was matched in Step 4. Anything that wasn't matched to an existing content note is **bonus footage**.

For each unplanned piece, extract:
- Filename and type (A-Roll, CB, named B-Roll)
- Location/project
- Duration
- Transcript summary (from the file-mapping.csv `transcript_summary` column or from the .txt transcript files)

Group bonus footage by project.

### Step 7: Present the Review

Show a structured summary to the user:

```markdown
## Shoot Review: [Shoot Date]

### Content Notes Updated
| Content Note | Status Change | Source File | Duration |
|--------------|---------------|-------------|----------|
| [[note-filename]] | concept → captured | ARoll-Location-Desc.MP4 | 78s |

### Planned but NOT Captured
| Content Note | Project | Reason |
|--------------|---------|--------|
| [[note-filename]] | [Project] | Not shot on [date] |

### Bonus Footage (Not in Current Pipeline)
| # | Type | Project | File | Duration | What's In It |
|---|------|---------|------|----------|-------------|
| 1 | A-Roll | Waverly | ARoll-Waverly-Addition-Progress.MP4 | 65s | Owner walks the addition — framing complete, windows in, siding started |
| 2 | CB | Morrison | CB-Morrison-Crown-Molding-Detail.MP4 | 38s | "Crown molding is one of those things..." |
| 3 | B-Roll | Henderson | BRoll-Henderson-Ceiling-Beam.MP4 | 8s | Ceiling beam detail shot |

### Unmatched Clips with Speech
| File | Duration | Transcript Excerpt |
|------|----------|--------------------|
| 064A7350.MP4 | 22s | "So this is the issue with the flashing..." |
```

### Step 8: Suggest Content Ideas

For each bonus footage item (especially A-Roll and CB pieces), generate a content idea:

**For each suggestion, provide:**
- **Title** — concise name for the piece
- **Format** — Reel, Carousel, etc. (based on duration and content type)
- **Platform** — Instagram, Facebook, YouTube Shorts, TikTok
- **Why it works** — connect to `whats-working.md` patterns (e.g., "educational reels outperform phase updates," "content bank pieces with strong hooks hit 400+ reach")
- **Hook direction** — 1-2 sentence hook concept based on the transcript
- **One-line caption direction**

Read `knowledge/whats-working.md` before generating suggestions to ground them in actual performance data.

**Present ideas conversationally:**
> "You also captured a 38-second CB piece where the owner talks about crown molding shortcuts. Educational content bank pieces have been your strongest format. Want me to create a content note for this?"

### Step 9: Interactive Conversation

After presenting the review and suggestions, **ask the user what they want to do:**

> "Any of these bonus pieces you want to add to the content pipeline? I can create content notes for them right now. You can also tell me to skip all of them or adjust the ideas."

Wait for the user's response. They may:
- **Approve specific pieces** — "Yes, do 1 and 3"
- **Modify an idea** — "The crown molding one, but frame it as a mistakes-to-avoid piece"
- **Skip all** — "None of these, we're good"
- **Ask questions** — "What's the transcript on #2?" — read and share the full transcript

Continue the conversation until the user is done.

### Step 10: Create Ad-Hoc Content Notes

For each approved idea, create a content note in `outputs/content/`:

**Filename:** `YYYY-MM-DD-[PREFIX]-NN-slug.md`
- `YYYY-MM-DD` = target post date. If no brief cycle is active, use 7 days from today as a placeholder. Ask the user if they have a preferred date.
- `[PREFIX]` = client's prefix (e.g., `AB` for Acme Builders — check existing content notes for the pattern)
- `NN` = next available number (check existing files in `outputs/content/`)
- `slug` = lowercase hyphenated title

**Frontmatter:**
```yaml
---
content_id: "CP-YYYYMMDD-NN"
title: "[Title from approved idea]"
client: "[client-folder-name]"
brief: ""
status: captured
post_date: YYYY-MM-DD
platform:
  - Instagram
  - Facebook
format: "[Format]"
project: "[Project name]"
project_social_name: "[Social name]"
duration: "[Duration from footage]"
source_footage: "[Full path from client footage root per CLAUDE.md convention]"
shoot_date: [actual shoot date]
tags: [relevant tags]
---
```

**Key differences from brief-generated notes:**
- `brief: ""` — ad-hoc, not tied to a brief
- `status: captured` — footage already exists
- `source_footage` — already populated with the actual file

**Body sections to generate (in this order):**
- `## Editor Brief` — fully populated (ad-hoc notes start at `status: captured`). Use the client's footage path convention from `CLAUDE.md`. Include: Deliverable, Footage path, Key Files, Duration, What to Make, Edit Direction, Script reference. End with `---` separator.
- `## Concept` — why this content works, data backing from whats-working.md
- `## Script` — if A-roll, note the existing footage duration and key talking points from transcript. Direction for trimming/editing.
- `## Caption` — full draft caption following voice-guidelines.md and blog-voice-analysis.md
- `## Shot List` — all items checked (footage exists)
- `## Edit Notes` — text overlays, trim targets, music direction
- `## Revision History` — initial entry:
  ```
  YYYY-MM-DD: Created from shoot-review (ad-hoc). Source: [filename] ([duration]s)
  ```

Read `knowledge/voice-guidelines.md` and `knowledge/blog-voice-analysis.md` before writing captions.

### Step 11: Update Shoot Log

After all content notes are created/updated, update the shoot log entry for this shoot date in `tracking/shoot-log.md`:

- Add any new content pieces to the **Content Pieces** or **Content Bank** tables
- Update edit status for pieces that were matched to content notes
- Note any pieces the user chose to skip

---

## Notes

- **This command is read-heavy, write-light.** The bulk of the work is reading and cross-referencing. Only writes happen to content notes, and only with user approval for new ones.
- **Organize-shoot must run first.** This command depends on file-mapping.csv/txt, renamed files, and transcripts. If these don't exist, tell the user to run `/organize-shoot` first.
- **Named B-Roll typically doesn't get its own content note** — it's supplementary footage for A-Roll pieces. But if a B-Roll clip has an unusually interesting narration or captures something noteworthy, suggest it.
- **Transcripts are the gold mine.** The most interesting content ideas come from things the owner said off-the-cuff while being filmed — side explanations, reactions, teaching moments. Read the full transcripts for unmatched clips, not just the file-mapping summary.
- **Multiple projects per shoot are normal.** A single shoot day often covers 3-4 project sites. Group everything by project in the review.
- **Content bank pieces are the easiest wins.** They don't need a brief cycle, they're already shot, and educational CB pieces consistently outperform. Lean into suggesting these.
