# Visual Library Schema

Each toolkit client should have a `knowledge/visual-library.md` file listing where their photos live. The `carousel-slides` skill (and `organize-shoot`, future visual skills) reads this to know where to pull background imagery from.

## File Location

`clients/[client-name]/knowledge/visual-library.md`

## Schema

```yaml
---
title: "Visual Library — [Client Name]"
description: "Catalog of photo source folders the carousel-slides skill (and other visual skills) draw from."
category: workflow
last_updated: YYYY-MM-DD
status: active
priority: medium
---

# Visual Library — [Client Name]

## Photo Sources

Listed in priority order. The skill enumerates images from each folder when picking slide backgrounds.

| Source | Path | Mood / Use | Last refreshed |
|--------|------|------------|----------------|
| Personal favorites | `/Users/[username]/Pictures/favorites` | Hand-curated, mixed subjects, portrait + landscape | 2026-04-15 |
| 2026 Spring shoot | `/path/to/repo/clients/[client]/content/shoots/YYYY-MM-shoot-slug/` | Outdoor, coffee, BTS | 2026-04-22 |
| Family / fatherhood | `/Users/[username]/Pictures/[family-content-restricted]` | Permission-cleared family photos for stewardship-pillar content | 2026-03-30 |

## Conventions

- **Absolute paths only** — relative paths break when the renderer launches a headless browser
- **JPEGs preferred over HEIC** — Playwright/Chromium handles JPEG natively; HEIC needs conversion
- **Keep landscape AND portrait sources** — IG portrait carousel (4:5) crops differently from square (1:1)
- **Tag mood loosely** — when picking photos, the skill matches mood to slide intent (e.g. "dawn" photo for "4:30 a.m." pull-quote)

## Permission notes

[Anything the skill must NOT use without explicit approval — e.g. "Don't use any photo with kids' faces in promotional content unless I've added it to the family-content-only folder"]

## Source

[How this list was assembled — e.g. "Established via Visual Library interview on YYYY-MM-DD"]
```

## Editing rules

- Update the **Last refreshed** date when a folder gets new shoots
- Add new shoot folders at the top of the table after each shoot, in addition to filing the photos
- Remove sources that no longer exist on disk — broken paths fail silently and surface as missing photos in render
- The `Permission notes` section is load-bearing — a misuse here is the difference between a strong visual and a relationship-damaging post
