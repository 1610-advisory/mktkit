# Shoot Day Template

Use this as the structure for every consolidated call sheet. Replace bracketed placeholders with real values from the brief, content notes, and the preflight conversation. Keep section order — the on-set crew reads top-down during a 2.5-3 hour shoot, so the most time-sensitive info comes first.

---

## File path

```
clients/[client]/outputs/shoot-days/YYYY-MM-DD-shoot-day.md
```

`YYYY-MM-DD` is the **shoot date**, not the date you're generating the file. The folder is `outputs/shoot-days/` (plural). Create the folder if missing. Never write to `outputs/` root.

---

## Template

```markdown
---
title: "Shoot Day — [Date in human form, e.g., 'Monday, May 4, 2026']"
client: "[client-folder-name]"
shoot_date: YYYY-MM-DD
brief: "[[YYYY-MM-DD-biweekly-brief]]"
content_ids:
  - PREFIX-YYYYMMDD-NN
  - PREFIX-YYYYMMDD-NN
locations:
  - "[Location name]"
talent:
  - "[Name] — [role / what they're on camera for]"
expected_duration: "[e.g., 2-3 hours]"
status: planned
created: YYYY-MM-DD
---

# Shoot Day — [Day, Month D, YYYY]

**Source brief:** [[YYYY-MM-DD-biweekly-brief]]

---

## Header

| Field | Value |
|-------|-------|
| Date | [Day, Month D, YYYY] |
| Locations | [comma-separated list, primary first] |
| Talent on camera | [names] |
| Crew | [names + roles, e.g., "Dawson — operator"] |
| Expected duration | [e.g., 2.5 hours including setup/teardown] |
| Pieces being captured | [count, e.g., "3 RITW reels + 1 BTS"] |

---

## Suggested Order

The sequence that minimizes setup/teardown. Locked locations are anchors; flexible scenes slot in around them. Time estimates are wall-clock including transitions.

| # | Time | Scene | Location | Pieces | Notes |
|---|------|-------|----------|--------|-------|
| 1 | 9:00-9:15 | Setup, sound check | [primary location] | — | Tripod, mic check, framing test |
| 2 | 9:15-10:00 | [Scene name] | [Location] | [CONTENT-ID, CONTENT-ID] | [setup or talent note] |
| 3 | 10:00-10:15 | Reset / transition | [Location] | — | [props swap, talent break, lens change] |
| 4 | 10:15-11:00 | [Scene name] | [Location] | [CONTENT-ID] | [note] |
| 5 | 11:00-11:30 | BTS / overflow | [Location] | [CONTENT-ID] | Phone shot, ad-hoc |

---

## Shot List — Grouped by Location & Scene

Every line carries a `[CONTENT-ID]` tag so on-set decisions trace to the piece. Check off as captured.

### Location: [Location name]

#### Scene: [Scene name, e.g., "Wooden chair, woods"]

- [ ] [Shot description] — [N takes] [CONTENT-ID]
- [ ] [Shot description] — [N takes] [CONTENT-ID]
- [ ] [Shot description] — [N takes] [CONTENT-ID]

#### Scene: [Scene name, e.g., "To-camera reflection, same chair"]

- [ ] [Shot description] — [N takes] [CONTENT-ID]
- [ ] [Shot description] — [N takes] [CONTENT-ID]

### Location: [Second location, if any]

#### Scene: [Scene name]

- [ ] [Shot description] — [N takes] [CONTENT-ID]

---

## Talent Call Sheet

| Name | Call Time | On Camera For | Notes |
|------|-----------|---------------|-------|
| [Name] | [time] | [pieces / scenes] | [wardrobe, props they bring, talking-points reminder] |
| [Name] | [time] | [pieces / scenes] | [note] |

If only one talent, keep the table — it doubles as the call-time reference.

---

## Props & Setup Checklist

### [Location 1]
- [ ] [Prop or setup item — e.g., "Wooden chair in position"]
- [ ] [Prop — e.g., "Five Types of Wealth, page flagged at Time chapter"]
- [ ] [Prop — e.g., "The Three Musketeers, brotherhood passage flagged"]
- [ ] [Setup — e.g., "Phone fully charged"]
- [ ] [Setup — e.g., "Lav mic + spare battery"]

### [Location 2, if any]
- [ ] [Prop / setup]
- [ ] [Prop / setup]

### General
- [ ] [Cross-location item — e.g., "Backup phone for B-roll"]
- [ ] [Weather contingency — e.g., "If raining, move to covered porch"]

---

## Backup Pieces

Pieces from the brief NOT being captured this day. Listed in case time opens up. One line of context each.

| Content ID | Title | Why not today | Could capture today if... |
|------------|-------|---------------|---------------------------|
| [CONTENT-ID] | [title] | [reason: banked / location / talent / time] | [condition that would unlock it] |
| [CONTENT-ID] | [title] | [reason] | [condition] |

---

## Gaps to Resolve

Anything flagged during note-reading that needs Dawson's input before or during the shoot. Don't shoot blind on these.

- **[CONTENT-ID]** — [what's missing, e.g., "no `## Shot List` section in note. Need shot direction before capturing."]
- **[CONTENT-ID]** — [what's missing, e.g., "frontmatter `shoot_date: 2026-05-18` but confirmed shoot is 2026-05-04. Update note frontmatter post-shoot."]

If this section is empty, write: "_None — all in-scope notes had complete shot lists and consistent frontmatter._"

---

## Revision History

- YYYY-MM-DD: Created from [[YYYY-MM-DD-biweekly-brief]]
```

---

## Notes on filling the template

### Frontmatter `content_ids` list
Only include content_ids that are **in scope this shoot day** (per preflight question 2). Backup pieces don't go in the frontmatter list — they live in the Backup section of the body.

### Suggested Order timing
Best-effort estimates. Round to 15-minute blocks. Bias slightly long — finishing early is fine, running over forces hard cuts on the last piece.

### Shot list grouping
Group by location, then scene within location. The win is reduced setup time. If two pieces share a scene (e.g., two RITW reels both filmed in the same chair with the same framing), interleave their shots so the camera operator captures both passes back-to-back instead of resetting between pieces.

### Tag format
Use the content_id as written in the note's frontmatter, in square brackets:

```
- [ ] Quote hook to camera, 3 takes [DS-20260515-03]
```

Not parentheses, not curly braces, not just the slug. The brackets make it scannable on set when the document is on a phone screen.

### Props pulled from notes
Look in `## Concept`, `## Edit Notes`, and `## Script` for prop and setup mentions. Common patterns:

- "bring [item]"
- "books to bring: [list]"
- "have [item] on hand"
- "wear [wardrobe]"
- "set up [thing] before talent arrives"
- Named items that are clearly physical (specific book titles, specific tools, specific products)

If a prop is mentioned in two notes, list it once under the appropriate location.

### Weather / contingency
If the brief mentions outdoor shooting and a backup location (e.g., "covered porch if raining"), include the contingency in the Setup checklist. The on-set person should not have to dig through the brief to find the rain plan.
