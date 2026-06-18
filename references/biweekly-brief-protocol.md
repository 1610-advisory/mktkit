# Bi-Weekly Brief Protocol

Step-by-step protocol for generating bi-weekly briefs. Contains data pull steps, research protocol, Google Sheets template workflow, and output formatting rules.

---

## Pre-Brief: Data & Research (Run in Parallel)

**Every time a bi-weekly brief is generated, run these three steps BEFORE writing the brief. Launch all in parallel for speed.**

### Step 1a: Pull Fresh Social Performance Data

If the client has platform API access configured (check `knowledge/` for integration config files like `meta-api.md`, `ig-api.md`, etc.):

1. Source env vars: `source ~/.zshrc.local`
2. Pull post-level insights for the period since the last brief using the configured API
3. Save raw CSV to `tracking/` (platform-specific file, overwrite with fresh pull)
4. Identify top 3 and bottom 3 performers since the last brief
5. Check if any previous tests showed results
6. Update `knowledge/whats-working.md` with any new patterns
7. Reference specific data points in the brief's performance section

**If the token is expired:** Notify the user and provide instructions for re-authentication. Check the client's integration config file for details.

If no API access, review manually-logged data in `tracking/performance.csv`.

### Step 1b: Pull Fresh Website Analytics Data

If the client has GA4 configured (check for `knowledge/ga4-integration.md`):

1. Source env vars: `source ~/.zshrc.local`
2. Read the client's `knowledge/ga4-integration.md` for property ID and script path
3. Run the standard pulls:
   ```bash
   GA4="uv run [script-path] --property-id $[CLIENT_PROPERTY_ID_VAR]"
   $GA4 top-pages --days 14 --limit 20
   $GA4 traffic-sources --days 14
   $GA4 content-perf --days 14 --limit 20
   ```
4. Save CSV to `tracking/ga4-performance.csv` (overwrite with fresh pull)
5. Identify which pages drive the most sessions and engagement
6. Cross-reference with social content — are social posts driving site visits?
7. Note which traffic sources are growing or declining
8. Reference website performance in the brief's analytics section

**If credentials error:** Check the client's `knowledge/ga4-integration.md` for setup instructions.

If no GA4 configured, skip this step.

### Step 1c: Mine Recent Meeting Notes for Content Material

If the client has a meeting-notes corpus configured in `CLAUDE.md` (look for `meeting_notes_path` or an "External Resources" section):

1. List meeting notes since the prior biweekly cycle (or ~6 weeks back if no prior cycle)
2. Use Bash + grep/awk to extract YAML `summary:` fields for fast triage. Do not read full files at this stage.
3. Identify 5-10 content-worthy moments. Prioritize the **Near Past** bucket from the client's `knowledge/content-ideation.md` (specific moments with clear lessons, dollar amounts, decisions made)
4. **Anonymization is mandatory.** Before surfacing any candidate:
   - Replace company names with industry descriptors ("a construction client," "an ag client," "an outdoor brand")
   - Replace person names with role descriptors ("an owner I work with," "a founder," "a CEO")
   - Round or generalize identifying dollar amounts unless the specificity is the point and the amount is non-identifying
   - Strip geographic identifiers
   - Remove anything that uniquely identifies the relationship to anyone reading
5. **Skip entirely** anything too personal, strategically sensitive, or non-anonymizable:
   - Acquisitions in flight
   - Hiring/firing decisions
   - Founder personal-life decisions (winding down a business, family conflicts, etc.)
   - Confidential strategy work
   - Sensitive financials that could damage the client
   - Anything that could embarrass the client even anonymized
6. Surface candidates to the user with: (a) anonymized one-line framing, (b) original source/context (for the client's memory only), (c) suggested bucket + awareness level. Be transparent about how many meetings you scanned and why you skipped what you skipped.
7. Do NOT auto-write content notes. After user selection, append chosen candidates to the client's configured content-ideas inbox (e.g., `+/Content Ideas — Running.md`).

**If no meeting notes corpus is configured:** skip this step. Note in the brief output that this pre-brief step was skipped.

### Step 2: Research Current Platform Best Practices

Search the web for what's working on social media RIGHT NOW — not just the primary platform, but cross-platform trends.

**Search for (use Agent tool for thorough research):**
- Algorithm changes and updates (last 30 days)
- Content format trends and best practices (current month)
- Hooks and editing styles performing well across all industries
- New platform features launched recently
- Cross-platform trend migration (e.g., TikTok trends -> Instagram Reels -> Shorts)
- Caption and SEO strategy updates
- Posting frequency and timing data

**What to do with the research:**
1. Save full research doc to `outputs/platform-research-YYYY-MM.md`
2. Extract 3-5 specific, actionable tactics to test this cycle
3. Update `knowledge/whats-working.md` if anything contradicts or updates existing advice
4. Include a "What We're Testing This Cycle" section in the brief with the new tactics
5. Track results of previous cycle's tests in the data pull

**Sources to prioritize:** Buffer, Hootsuite, Later, Social Media Examiner, Sprout Social, Kapwing, official platform announcements. Prefer data-backed findings over opinion pieces.

### How Data & Research Flow Into the Brief

The brief should include:
- **Performance snapshot:** Top/bottom posts from last cycle with why
- **Website snapshot:** Top pages, traffic sources, landing page engagement (if GA4 is configured)
- **Social -> Website connection:** Which social content drove site visits (cross-reference social and GA4 data)
- **What We're Testing This Cycle:** 3-5 specific tactics from fresh research
- **Tracking section:** What to measure to evaluate the tests
- Captions, scripts, and edit notes informed by current best practices

---

## Output: Dual Save

**All content plans are dual-saved and must match:**
1. **Markdown (.md)** -> `outputs/biweekly-briefs/YYYY-MM-DD-biweekly-brief.md` (source of truth)
2. **Google Sheet** -> copied from template via MCP tools (team-facing, editable) — only if the client has a Sheets template configured

Check the client's `CLAUDE.md` for Google Drive folder ID and Sheet template ID.

---

## Google Sheets Template Workflow

**Only run this if the client has a Google Sheets bi-weekly template configured in their `CLAUDE.md` or `knowledge/` files.**

### Step 1: Copy the Template

```
mcp__gdrive__copyFile(
  fileId: "[TEMPLATE_ID from client config]",
  name: "YYYY-MM-DD to MM-DD Bi-Weekly Brief - [Client Name]",
  parentFolderId: "[FOLDER_ID from client config]"
)
```

### Step 2: Fill the Overview Tab

Use `mcp__gdrive__updateGoogleSheet` for all ranges.

**Overview Section (Rows 6-9):**
| Cell | Content |
|------|---------|
| `Overview!B6` | Shooting block date/time |
| `Overview!B7` | Crew members |
| `Overview!B8` | Content period date range |
| `Overview!B9` | Strategic theme |

**Posting Schedule (Rows 13-27, up to 15 posts):**
- Range: `Overview!A13:F{last_row}`
- Columns: Date | Day | Post Title | Type | Platform | Drive Folder

**Caption Review Table (Rows 32-46):**
- Columns A, B, F have **formulas — do NOT overwrite**
- **Fill only C, D, E:** `Overview!C32:E{last_row}`
- Columns: Project/Topic | Caption | Hashtags

**Shot List (Rows 50-89, up to 40 entries):**
- Range: `Overview!A50:D{last_row}`
- Columns: Location | Shot | Notes | FALSE

**Pre-Shoot Checklist (Rows 93-102, up to 10 items):**
- Range: `Overview!A93:D{last_row}`
- Columns: Task | Notes | (empty) | FALSE

**Post-Shoot Checklist (Rows 106-115, up to 10 items):**
- Range: `Overview!A106:D{last_row}`
- Columns: Task | Notes | (empty) | FALSE

**Project Name Reference (Rows 119-128, up to 10 projects):**
- Range: `Overview!A119:D{last_row}`
- Columns: Social Name | Internal Name (Drive Folder) | Year Built | Type

### Step 3: Fill the Post Tabs

Each post tab has formulas that auto-populate from Overview. **Do NOT overwrite** row 1, column A, or auto-populated rows (2, 4-6, 8-9, 28, 31).

**Fill these cells on each post tab:**
| Range | Content |
|-------|---------|
| `'{n}'!C7` | Social Name |
| `'{n}'!B13` | The Concept (1-3 sentences) |
| `'{n}'!B17:E25` | Script table (4 columns, fill only rows needed) |

**Script table columns (Row 16 = headers):**
- B: **Section** — HOOK / BODY / END (reels) or Slide 1, Slide 2, etc. (carousels)
- C: **Time** — timestamp (e.g., "0-3s") or slide text/copy
- D: **Visual** — what appears on screen
- E: **Audio / Text Overlay** — voiceover or text overlay

### Step 4: Hide Unused Rows and Tabs

**General rule:** Count items per section, hide from (last_used_row + 1) to (section_max_row).

| Section | Max rows | Example (7 posts) |
|---------|----------|-------------------|
| Posting schedule | 13-27 | Hide 20-27 |
| Caption table | 32-46 | Hide 39-46 |
| Shot list | 50-89 | Hide (last+1) to 89 |
| Pre-shoot | 93-102 | Hide (last+1) to 102 |
| Post-shoot | 106-115 | Hide (last+1) to 115 |
| Project ref | 119-128 | Hide (last+1) to 128 |
| Post tab scripts | 17-25 | Hide (last+1) to 25 per tab |
| Unused post tabs | — | Hide tabs (N+1) through 15 |

### Known Limitations
- MCP tools can't access Shared Drives (needs `supportsAllDrives` flag — not available)
- Sheet tab names with quotes: `updateGoogleSheet` needs quotes (`'1'!A1`), but formatting tools may not
- Caption review table columns A, B, F have formulas — only fill C, D, E
- Post tab row 1 and column A have formulas — never overwrite
- Always count items per section and hide from (last_used_row + 1) to (section_max_row)

---

## Markdown Output Formatting

Optimize for mobile reading and narrow screens.

**Content Pieces:** Each piece is its own atomic note in `outputs/content/`. The brief contains a linked table, NOT inline content details:
```markdown
## Content Pieces
| # | Title | Format | Status | Link |
|---|-------|--------|--------|------|
| 1 | Title | Carousel 6-8 | concept | [[2026-04-15-CP-01-slug]] |
| 2 | Title | Reel 60-90s | concept | [[2026-04-17-CP-02-slug]] |
```

**Captions:** Live in content notes, not in the brief. The brief can include a summary table linking to each note's Caption section if helpful for team review.

**Master Shot List:** Stays in the brief — it's the consolidated shoot-day production reference. Individual piece shot lists live in each content note.

**Scripts:** Live in content notes. Use consistent simple tables (Section | Time | Visual | Audio).

**Tables:** Keep columns narrow. Use short labels.

**Remove clutter:**
- No change logs / version history
- No checked-off checklists (if everything is [x], delete it)
- No redundant sections — don't repeat info across schedule, content pieces, and recap
- Consolidate shoot recap + folder structure + editor notes into one compact section

**Structure order:** Overview -> Performance Snapshot -> What We're Testing -> Posting Schedule -> Content Pieces (linked table) -> Master Shot List -> Content Bank -> Cross-Platform Notes -> Checklists -> Project Reference

**Footer:** Single line: `*Created: Date . Updated: Date . Content period: Range*`

See `references/content-notes.md` for the full content note schema, naming convention, and status workflow.

---

## Client-Specific Config

Look for these in the client's `CLAUDE.md` or `knowledge/` files:
- **Social API token env var** (e.g., `META_LONG_TOKEN_[CLIENT]`)
- **Social account ID env var** (e.g., `META_IG_ID_[CLIENT]`)
- **GA4 property ID env var** (e.g., `GA4_PROPERTY_ID_[CLIENT]`)
- **GA4 script path** and runner command
- **Google Sheets template ID** for bi-weekly briefs
- **Google Drive folder ID** for saving output files
- **Crew/team member names** for the overview section
- **Project name reference** (social name <-> internal name mapping)
