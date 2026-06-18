# Bi-Weekly Plan Procedures

Detailed procedures for generating bi-weekly content plans. Bi-weekly plans are a middle ground between weekly execution and monthly strategy — they provide 10-14 content pieces across two weeks with more tactical detail than a monthly plan.

## When to Use Bi-Weekly Instead of Weekly

Bi-weekly plans work best when:
- The client has a regular production schedule (shoot days every 2 weeks)
- Content requires coordination across team members
- The client prefers batch planning for efficiency
- There's a Google Sheets or team-facing template for handoff

Weekly plans are better when:
- Content is reactive or trend-driven
- The client posts at a lower cadence (3x/week or less)
- No batch production workflow exists

## Process

### Pre-Brief: Data & Research (Run in Parallel)

Before writing the brief, run these two steps simultaneously:

#### Step 1: Pull Fresh Performance Data

If the client has platform API access configured (e.g., Meta Graph API for Instagram, analytics exports):

1. Pull post-level insights for the period since the last brief
2. Save raw data to `tracking/` (platform-specific CSV)
3. Identify top 3 and bottom 3 performers
4. Check if previous tests showed results
5. Update `knowledge/whats-working.md` with new patterns
6. Reference specific data points in the brief's performance section

If no API access, review manually-logged data in `tracking/performance.csv`.

#### Step 2: Research Current Platform Best Practices

Search for what's working on social media right now — not just the primary platform, but cross-platform trends:

- Algorithm changes and updates (last 30 days)
- Content format trends and best practices (current month)
- Hooks and editing styles performing well
- New platform features
- Cross-platform trend migration (e.g., TikTok trends → Instagram Reels)
- Caption and SEO strategy updates
- Posting frequency and timing data

**What to do with the research:**
1. Save research doc to `outputs/platform-research-YYYY-MM.md`
2. Extract 3-5 specific, actionable tactics to test this cycle
3. Update `knowledge/whats-working.md` if anything contradicts existing advice
4. Include a "What We're Testing This Cycle" section in the brief

**Sources to prioritize:** Buffer, Hootsuite, Later, Social Media Examiner, Sprout Social, Kapwing, platform-specific official announcements. Prefer data-backed findings over opinion pieces.

#### Step 2b: Pull Ahrefs SEO Data (if configured)

If the client has `knowledge/ahrefs-config.md`, pull fresh keyword and competitor data. See `references/ahrefs-integration.md` for API details.

1. **Metrics refresh** — check for organic traffic shifts since last brief:
   ```bash
   curl -s "https://api.ahrefs.com/v3/site-explorer/metrics?target=${DOMAIN}&date=$(date +%Y-%m-%d)&country=us" \
     -H "Authorization: Bearer $AHREFS_API_KEY"
   ```

2. **Keyword position changes** — pull top 100 organic keywords and compare to last brief's data (saved in `tracking/ahrefs/`):
   ```bash
   curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=${DOMAIN}&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume,sum_traffic,keyword_difficulty&limit=100&order_by=sum_traffic:desc" \
     -H "Authorization: Bearer $AHREFS_API_KEY"
   ```

3. **Topic inspiration** — pull a key competitor's top keywords for fresh ideas:
   ```bash
   curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=competitor.com&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume,sum_traffic&limit=100&order_by=sum_traffic:desc" \
     -H "Authorization: Bearer $AHREFS_API_KEY"
   ```

4. **Validate planned topics** — batch-check keyword metrics for the topics you're considering:
   ```bash
   curl -s "https://api.ahrefs.com/v3/keywords-explorer/overview?country=us&keywords=topic+one,topic+two&select=keyword,volume,difficulty,traffic_potential" \
     -H "Authorization: Bearer $AHREFS_API_KEY"
   ```

**What to do with the data:**
- Save raw responses to `tracking/ahrefs/biweekly-YYYY-MM-DD.json`
- Note any keywords that jumped or dropped significantly since last brief
- Flag quick wins (positions 5-20 with decent volume) as candidates for optimization content
- Use competitor keyword data to inform topic selection
- Include keyword data in the brief's content piece rationale

**Cost:** ~1,250 API units per biweekly cycle. See `references/ahrefs-integration.md` for budget details.

#### Step 3: Mine Recent Meeting Notes for Content Material (if applicable)

If the client has a meeting-notes corpus configured (check `CLAUDE.md` for `meeting_notes_path` or equivalent):

1. List meeting notes since the prior biweekly cycle (or ~6 weeks back if no prior cycle)
2. Use Bash + grep/awk to extract YAML `summary:` fields for fast triage — don't read every file
3. Identify 5-10 content-worthy moments. Prioritize the **Near Past** bucket from the client's content-ideation framework (specific moments with clear lessons)
4. **Anonymization is mandatory.** Strip:
   - Company names (use "a [industry] client")
   - Person names (use "an owner I work with," "a founder")
   - Identifying dollar amounts (round, or generalize)
   - Geographic identifiers
   - Anything that uniquely identifies the relationship
5. Skip anything too personal, strategically sensitive, or non-anonymizable: acquisitions in flight, hiring/firing decisions, founder personal-life decisions, confidential strategy work, sensitive financials, anything that could embarrass a client
6. Surface candidates to the user — do **NOT** auto-write content notes. Each candidate gets:
   - Anonymized one-line framing (the usable content)
   - Original source/context (for the client's memory only)
   - Suggested bucket + awareness level
7. After user selection, append to the client's configured content-ideas inbox (e.g., `+/Content Ideas — Running.md`)

If no meeting notes corpus is configured, skip this step.

### Generate the Bi-Weekly Brief

1. **Read client context:**
   - Client's `CLAUDE.md`
   - All files in `knowledge/`

2. **Check for a current monthly plan:**
   - Look in `outputs/monthly-briefs/` for this month's plan
   - Align the bi-weekly plan with the current month's themes and objectives

3. **Structure the brief:**

   **Performance Snapshot:**
   - Top/bottom posts from last cycle with analysis of why
   - Test results from previous cycle

   **Two-Week Overview:**
   - Date range and theme
   - Posting schedule with dates, formats, platforms
   - Production/shoot planning

   **Content Pieces (10-14):**
   For each piece, generate the full detail (platform, format, topic, hook, script, caption, CTA, shot list, edit notes, why this works), then **create an atomic content note** for it:

   a. Generate `content_id`: `[CLIENT_PREFIX]-[YYYYMMDD of post_date]-[NN]`
   b. Generate filename: `YYYY-MM-DD-PREFIX-NN-slug.md` (slug = lowercase hyphenated title, max 40 chars)
   c. Create the file at `clients/[client]/outputs/content/[filename]`
   d. Fill YAML frontmatter (content_id, title, client, brief, status: concept, post_date, platform, format, project, project_social_name, duration, shoot_date, tags)
   e. Fill body sections in this order:
      - **Editor Brief** (placeholder for `status: concept` — just Deliverable + Duration + blockquote "Footage not yet captured. This section will be populated after the shoot." For content bank pieces already at `status: captured`, fully populate using the client's footage path convention from `CLAUDE.md`)
      - `---` separator
      - Concept, Script (or Carousel Structure), Caption, Shot List, Edit Notes, Revision History

   **IMPORTANT — Already-shot content (content bank pieces, carried-over footage):**
   When writing Concept, Caption, Script, or Editor Brief for any piece that has already been filmed, you MUST read the actual transcript (`.txt` file in the shoot folder's `Audio/` subfolder) before writing content direction. Do not infer what was said from the filename or file-mapping summary. The transcript is the ground truth for what the speaker actually said on camera. If no transcript file exists, flag it rather than guessing.
   f. See `references/content-notes.md` for the full schema, Editor Brief structure, and naming convention

   After creating all content notes, **replace inline content details in the brief** with a linked table:
   ```
   ## Content Pieces
   | # | Title | Format | Status | Link |
   |---|-------|--------|--------|------|
   | 1 | [Title] | [Format] | concept | [[filename-without-extension]] |
   ```

   The brief keeps the master shot list (consolidated by location) but individual piece shot lists live in each content note. Captions live in content notes — the brief links to them.

   **What We're Testing This Cycle:**
   - 3-5 specific tactics from research
   - How to measure success

   **Shot List:**
   - Combined production plan for all video content
   - Locations, setups, and notes

   **Checklists:**
   - Pre-shoot preparation
   - Post-shoot editing and publishing

4. **Save the plan:**
   - Content notes: already saved to `outputs/content/` (step 3)
   - Markdown brief: `outputs/biweekly-briefs/YYYY-MM-DD-biweekly-brief.md`
   - If client has Google Sheets template configured, copy and fill it
   - If client has Google Drive configured, save to shared folder

### Planning Principles for Bi-Weekly Plans

- Every content piece needs a clear "why" — connect to data, goals, or a specific test
- Balance proven approaches (70%) with experimental tactics (30%)
- Group similar content for production efficiency (batch shoot days)
- Scripts should be concise — the team adapts during filming
- Include platform research findings as actionable tests, not just FYI
- Hook lines are the most important element — reference proven patterns
- Caption direction > final copy — give the human team room to adapt

### Markdown Formatting Guidelines

Optimize for mobile reading and narrow screens:

- **Captions:** Individual blocks per post, not wide tables
- **Scripts:** Simple tables (Section | Time | Visual | Audio)
- **Tables:** Keep columns narrow with short labels
- **Remove clutter:** No change logs, no checked-off checklists, no redundant sections
- **Footer:** Single line with created/updated dates and content period
