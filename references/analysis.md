# Analysis Procedures

Detailed procedures for performance analysis, revenue reporting, and updating strategic insights.

## Performance Analysis

When the user says "analyze performance for [client]":

### Process

1. **Load tracking data:**
   - Read `tracking/performance.csv` and `tracking/content-log.csv`
   - If the client uses Google Sheets for tracking, load from the configured spreadsheet instead

2. **Identify top performers:**
   - Sort by engagement rate and performance score
   - Identify the top 5-10 pieces from the analysis period
   - Note what they have in common (format, topic, hook type, posting time, CTA)

3. **Find patterns across dimensions:**
   - **Format:** Which content types (Reels, carousels, static, threads) get the best engagement?
   - **Timing:** Which days and times produce the highest reach and engagement?
   - **Hooks:** Which opening patterns drive the most saves and shares?
   - **Topics:** Which themes resonate most with the audience?
   - **CTAs:** Which call-to-action types drive the most link clicks or follows?

4. **Identify underperformers:**
   - What's consistently below average?
   - Are there patterns in what doesn't work?

5. **Generate insights with specific action items:**
   - Each insight should lead to a concrete recommendation
   - Frame recommendations as: "Do more of X because Y" or "Test Z because data suggests W"

6. **Propose updates to `knowledge/whats-working.md`:**
   - Identify new patterns to add
   - Flag outdated insights to archive
   - Suggest new hypotheses based on the data

### Output Format

Use the Performance Analysis format from `output-formats.md`. Save to `outputs/` with a descriptive filename like `performance-analysis-YYYY-MM.md`.

---

## Update What's Working

When the user says "update whats working for [client]":

### Process

1. **Review recent performance data:**
   - Last 30 days of `tracking/performance.csv`
   - Cross-reference with `tracking/content-log.csv` for context

2. **Read current `knowledge/whats-working.md`:**
   - Understand what's already documented
   - Identify what's still accurate vs. outdated

3. **Identify new patterns:**
   - New hook types that are performing well
   - Shifts in best posting times
   - Emerging content types or topics
   - Changes in audience behavior

4. **Update the file:**
   - Add new insights to appropriate sections (content type performance, hook patterns, topics, timing)
   - Move outdated insights to a "Previously Worked" or archive section
   - Update the Top 5 All-Time if new entries qualify
   - Add entries to the Monthly Iteration Log
   - Refresh the Quick Reference Summary at the bottom

5. **Propose new hypotheses:**
   - Based on emerging patterns, what should be tested next?
   - Move tested hypotheses to results (with outcomes)
   - Add new hypotheses to the "Up Next" or "Ideas Backlog" sections

### Triggers for Updates
- After completing a monthly performance review
- When a piece of content goes viral or significantly outperforms
- When the user reports a noticeable shift in engagement
- After running a deliberate test and getting results

---

## Revenue Report

When the user says "revenue report for [client]":

### Process

1. **Read revenue data:**
   - Load `tracking/revenue-attribution.csv`
   - Cross-reference with `tracking/content-log.csv` for content details

2. **Calculate ROI by dimension:**
   - **By content type:** Which formats produce the most leads and revenue?
   - **By platform:** Which platform drives the most business?
   - **By campaign:** Which campaigns have the highest conversion rates?
   - **By topic:** Which content themes attract buying customers?

3. **Analyze the attribution chain:**
   - First-touch attribution: What content first brought the lead in?
   - Last-touch attribution: What content was the final nudge before conversion?
   - If multi-touch data exists, identify the most common content journeys

4. **Identify highest-converting patterns:**
   - Which content consistently produces qualified leads?
   - What's the average time from first content touch to lead?
   - What's the conversion rate from lead to closed deal?

5. **Generate recommendations:**
   - Double down on content types with highest revenue attribution
   - Identify gaps — content that gets engagement but not revenue
   - Propose shifts in content mix to optimize for business outcomes

6. **Save report** to `outputs/` with filename like `revenue-report-YYYY-MM.md`
