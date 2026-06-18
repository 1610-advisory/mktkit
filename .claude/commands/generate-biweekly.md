---
description: Generate a two-week content plan with 10-14 pieces, performance data pull, and platform research
argument-hint: [client-name]
---

# Generate Bi-Weekly Plan

The user wants a bi-weekly content plan. Read `references/biweekly.md` for the full procedure, and `references/planning.md` for general planning principles.

**Arguments:** The user may specify a client name.

**Process:**
1. Identify the client (ask if ambiguous)
2. Read the client's `CLAUDE.md` and all knowledge files
3. **Pre-brief research (run in parallel):**
   a. Pull fresh performance data from platform APIs (if configured)
   b. Research current platform best practices and trends
4. **BRAINSTORM AND CONFIRM (mandatory gate — do not skip):**
   a. Share the proposed plan in conversation: shoot cadence, post count per week, what's fresh capture vs banked, which banked items go where, which strategic pivots vs last cycle, open risks
   b. Ask clarifying questions about anything genuinely uncertain (shoot-day count, talent availability, banked-content blockers, projects closed/inaccessible, volume targets)
   c. **Wait for explicit sign-off or corrections before writing any files.** Iterate the plan in conversation until the user approves it.
   - **Why:** A brief was generated end-to-end with wrong shoot cadence assumed (two days vs. actual one day); 10 content notes + brief + 2 shoot-day docs had to be revised or deleted. The brainstorm step costs 2 messages; skipping it costs 10-15 file rewrites.
5. Generate 10-14 content pieces across two weeks (only after Step 4 sign-off)
6. **Create atomic content notes** for each piece in `outputs/content/` (see `references/content-notes.md` for schema)
7. Build the brief with a Content Pieces table linking to each note via `[[wiki-links]]`
8. Include performance snapshot, tests to run, master shot list (consolidated by location)
9. Save markdown brief to `outputs/biweekly-briefs/`
10. If Google Sheets template is configured, copy and fill the template
