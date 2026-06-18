# Output Format Templates

Complete templates for monthly plans, weekly plans, and performance reports. Use these exact structures when generating outputs.

## Monthly Plan Template

```markdown
# Monthly Content Strategy: [Client Name]
[Month Year]

## Monthly Theme
[Overarching theme/campaign focus for the month]

## Strategic Objectives
- [Objective 1 tied to 90-day goals]
- [Objective 2]
- [Objective 3]

## Content Mix This Month
| Content Type | Quantity | Focus |
|--------------|----------|-------|
| [Format 1] | [#] | [Theme/topic focus] |
| [Format 2] | [#] | [Theme/topic focus] |
| [Format 3] | [#] | [Theme/topic focus] |

---

## Week 1: [Date Range]
**Theme:** [Weekly theme]

**Content Focus:**
- [Topic 1]
- [Topic 2]
- [Topic 3]

**Content Types:**
- [X] [Format 1]
- [X] [Format 2]

**Hypothesis to Test:** [What we're trying to learn this week]

---

## Week 2: [Date Range]
**Theme:** [Weekly theme]

**Content Focus:**
- [Topic 1]
- [Topic 2]

**Content Types:**
- [X] [Format 1]
- [X] [Format 2]

**Hypothesis to Test:** [What we're trying to learn]

---

## Week 3: [Date Range]
**Theme:** [Weekly theme]

**Content Focus:**
- [Topic 1]
- [Topic 2]

**Content Types:**
- [X] [Format 1]
- [X] [Format 2]

**Hypothesis to Test:** [What we're trying to learn]

---

## Week 4: [Date Range]
**Theme:** [Weekly theme]

**Content Focus:**
- [Topic 1]
- [Topic 2]

**Content Types:**
- [X] [Format 1]
- [X] [Format 2]

**Hypothesis to Test:** [What we're trying to learn]

---

## Production Planning

**Shoot Days Needed:** [#]

**Key Assets to Capture:**
- [Asset 1]
- [Asset 2]
- [Asset 3]

**B-Roll Library Gaps:**
- [What's missing that we need]

---

## Metrics to Track This Month

| Metric | Current | Target | Why |
|--------|---------|--------|-----|
| [Metric 1] | [#] | [#] | [Reason] |
| [Metric 2] | [#] | [#] | [Reason] |

---

## Tests to Run

### Test 1: [Name]
- **Hypothesis:** [What we think will happen]
- **How to Test:** [What content we'll create]
- **Success Metric:** [How we'll know if it worked]

### Test 2: [Name]
- **Hypothesis:** [What we think will happen]
- **How to Test:** [What content we'll create]
- **Success Metric:** [How we'll know if it worked]

---

## Key Messages This Month
[Aligned with messaging pillars from voice-guidelines.md]

1. [Message 1]
2. [Message 2]
3. [Message 3]

---

## Month-End Review Checklist
- [ ] Update performance.csv with all content metrics
- [ ] Run `analyze performance for [client]`
- [ ] Update whats-working.md with learnings
- [ ] Document test results
- [ ] Generate next month's plan
```

---

## Weekly Plan Template

Each content piece is created as an atomic note in `outputs/content/`. The brief links to them. See `references/content-notes.md` for the content note schema.

```markdown
# Weekly Content Plan: [Client Name]
Week of [Date]

## This Week's Focus
[Theme/campaign focus based on goals]

## Content Pieces

| # | Title | Format | Status | Link |
|---|-------|--------|--------|------|
| 1 | [Title] | [Format] | concept | [[YYYY-MM-DD-PREFIX-01-slug]] |
| 2 | [Title] | [Format] | concept | [[YYYY-MM-DD-PREFIX-02-slug]] |

---

## Production Shot List

Combine all video content into one efficient shoot day:

| Shot | Content Piece | Setup | Notes |
|------|--------------|-------|-------|
| 1 | | | |
| 2 | | | |

---

## Key Messages This Week
[Aligned with messaging pillars from voice-guidelines.md]

## Metrics to Watch
[Specific KPIs for this week]
```

---

## Content Note Template

Each content piece is its own file in `outputs/content/`. See `references/content-notes.md` for the full schema, naming convention, and status workflow.

```yaml
---
content_id: "PREFIX-YYYYMMDD-NN"
title: "[Content Piece Title]"
client: "[client-folder-name]"
brief: "[[brief-filename]]"
status: concept
post_date: YYYY-MM-DD
platform:
  - Instagram
format: "[Reel 30-60s | Carousel 6-8 | etc.]"
project: "[Internal project name]"
project_social_name: "[Public-facing name]"
duration: ""
source_footage: ""
shoot_date: YYYY-MM-DD
tags: []
---
```

Body sections: `## Concept`, `## Script` (or `## Carousel Structure`), `## Caption`, `## Shot List`, `## Edit Notes`, `## Revision History`

---

## Performance Analysis Template

```markdown
# Performance Analysis: [Client Name]
Period: [Date Range]

## Top Performers
| Rank | Content | Platform | Key Metric | Why It Worked |
|------|---------|----------|------------|---------------|
| 1 | | | | |

## Patterns Identified
- **Format:** [what's working]
- **Timing:** [best days/times]
- **Topics:** [resonating themes]
- **Hooks:** [effective patterns]

## Recommendations
[Specific action items]

## Proposed Updates to whats-working.md
[Changes to make]
```
