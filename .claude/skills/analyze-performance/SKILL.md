---
name: analyze-performance
description: Analyze a client's content performance, identify top performers and patterns, generate revenue attribution reports, and propose updates to the client's `whats-working.md`. Use this skill whenever the user says "analyze performance for [client]", "what's working for [client]", "performance analysis", "update whats-working for [client]", "refresh insights", "revenue report for [client]", "ROI report", "what content is converting", "which posts drove leads", or any time the user wants to look at tracking CSVs (or the Google Sheets equivalent) and turn raw metrics into strategic insight. Trigger even when the user does not say "analyze" explicitly — phrasings like "show me top performers", "what should we do more of", "what's driving revenue", "where are leads coming from", or "review last month's numbers" all belong here. Three sub-modes: (1) performance analysis = patterns + recommendations, (2) update whats-working = refresh the canonical insights file, (3) revenue report = ROI/attribution focus.
metadata:
  version: 1.0.0
---

# Analyze Performance

You are turning a client's tracking data into strategic insight. The user pointed you at a specific client — confirm which one before loading data, then route to one of three sub-modes based on what they asked for.

**Read-only on data files.** You analyze CSVs but never mutate them. The only files you write are the analysis output (`outputs/`) and — with the user's approval — proposed updates to `knowledge/whats-working.md`.

---

## Sub-mode router

| User phrasing | Sub-mode | Output file pattern |
|---|---|---|
| "analyze performance", "what's working", "top performers", "review last month" | **Performance Analysis** | `outputs/performance-analysis-YYYY-MM.md` |
| "update whats-working", "refresh insights", "what's our latest pattern" | **Update What's Working** | edits to `knowledge/whats-working.md` |
| "revenue report", "ROI", "what's driving leads", "attribution report" | **Revenue Report** | `outputs/revenue-report-YYYY-MM.md` |

If the request is ambiguous, ask which one — don't guess. The three outputs are distinct enough that picking wrong wastes the run.

---

## Sub-mode 1: Performance Analysis

1. **Load tracking data:**
   - `clients/[client]/tracking/performance.csv` and `clients/[client]/tracking/content-log.csv`
   - If the client's `CLAUDE.md` declares a Google Sheets tracking source, read from the configured spreadsheet instead.

2. **Identify top performers:** Sort by engagement rate and performance score. Pull the top 5–10 pieces from the analysis period. Note what they share — format, topic, hook type, posting time, CTA.

3. **Find patterns across dimensions:**
   - **Format** — Reels vs. carousels vs. static vs. threads, by engagement
   - **Timing** — best days and times for reach
   - **Hooks** — opening patterns that drive saves and shares
   - **Topics** — which themes resonate
   - **CTAs** — which calls-to-action drive clicks or follows

4. **Identify underperformers.** What's consistently below average? Are there patterns in what doesn't work?

5. **Generate insights with concrete action items.** Frame each as "Do more of X because Y" or "Test Z because data suggests W" — never abstract.

6. **Propose updates to `knowledge/whats-working.md`.** New patterns to add, outdated insights to archive, new hypotheses to test. Surface as a proposal — wait for the user's go-ahead before editing.

**Output format:** follow `references/output-formats.md` (Performance Analysis template). Save to `outputs/performance-analysis-YYYY-MM.md`.

---

## Sub-mode 2: Update What's Working

1. **Pull the last 30 days** of `tracking/performance.csv`, cross-referenced with `tracking/content-log.csv`.

2. **Read current `knowledge/whats-working.md`.** Understand what's already documented; flag what's still accurate vs. outdated.

3. **Identify new patterns:** new hook types performing well, shifts in best posting times, emerging content types or topics, changes in audience behavior.

4. **Propose the diff to the user before writing.** Show: new sections, archived entries, Top 5 changes, Monthly Iteration Log additions, Quick Reference refresh. Wait for sign-off, then edit.

5. **Propose new hypotheses.** What should be tested next? Move resolved hypotheses to results with outcomes. Add new ones to "Up Next" or "Ideas Backlog."

**Triggers for running this:** after a monthly performance review; when a piece goes viral or significantly outperforms; when the user reports an engagement shift; after a deliberate test produces results.

---

## Sub-mode 3: Revenue Report

1. **Read revenue data:** `tracking/revenue-attribution.csv`, cross-referenced with `tracking/content-log.csv` for content details.

2. **Calculate ROI by dimension:**
   - **By content type** — which formats produce the most leads and revenue
   - **By platform** — which channels drive the most business
   - **By campaign** — highest conversion rates
   - **By topic** — which themes attract buying customers

3. **Analyze the attribution chain:**
   - First-touch — what content first brought the lead in
   - Last-touch — what content was the final nudge before conversion
   - Multi-touch — common content journeys, if the data supports it

4. **Identify highest-converting patterns.** Content that consistently produces qualified leads, average time from first touch to lead, conversion rate from lead to closed deal.

5. **Generate recommendations:** double down on revenue-attributed content types, identify gaps (engagement without revenue), propose content mix shifts toward business outcomes.

6. **Save to `outputs/revenue-report-YYYY-MM.md`.**

---

## Reference formulas

**Engagement rate:**
```
(Likes + Comments + Shares + Saves) / Reach × 100
```

**Performance score (1–10):**
- 1–3: Below average for this client's typical content
- 4–6: Average — meeting expectations
- 7–8: Above average — outperforming typical content
- 9–10: Exceptional — viral or significantly outperforming

If a client has no historical baseline yet, fall back to industry benchmarks:
- Instagram — 1–3% average, 3–6% good, 6%+ excellent
- LinkedIn — 2–4% average, 4–8% good, 8%+ excellent
- X — 0.5–1% average, 1–3% good, 3%+ excellent

---

## When to delegate

The CSV scan + pattern extraction is mechanical and parallelizable. For a client with a large tracking history (200+ rows across content-log and performance), spawn a Sonnet agent with the explicit file paths and a "report back" structure — top 10 performers, bottom 5 underperformers, three pattern observations. Keep the strategic recommendation work in the main thread; that's where the voice and context live.

---

## What this skill does not do

- Does not log new data. For "log content / log performance / log lead," use the `log-data` skill.
- Does not generate a new content plan. After an analysis run, suggest a follow-up `/generate-week` or `/generate-biweekly` if the insights warrant it.
- Does not run a competitor or platform-level analysis. That's a separate research task.
