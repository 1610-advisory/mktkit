---
name: ads-library
description: >
  Keep the ad creative library for one business: every ad creative as a
  content note with a content_id and an ad: block, which are approved, which
  are live, fatigue signs, and the hook × format grid of spend vs qualified
  leads. Use when someone says "ad library", "which creatives are approved",
  "what ads do we have", "creative fatigue", "hook by format", "approve this
  creative for ads", "what should we make next for ads", or the ads-engineer
  gets a "library" job.
metadata:
  version: 0.1.0
---

# Ads library

One run = an up-to-date `tracking/ads/library.md` and a list of what to make next. `<kit>` = this plugin's root. `<biz>` = the business repo root.

The files are the source. Content notes (`outputs/content/`) hold each creative under its note id (the note's `content_id` field, `AP-20261201-03`). When mktdata is live it indexes them: `content.note_ref` = the note id, mapped to its content UUID; unmatched note ids sit on its "to match" list. Read `<kit>/references/naming.md` (ids, `ad:` block, asset names) and the "Creative volume, cadence and fatigue" part of `ads-judgment.md`.

## Steps

1. **Index.** Find every content note with an `ad:` block. For each: `content_id`, cell, status, platforms, ratios, assets, approved by/on. A note used in a live ad without an `ad:` block: list it as a gap.
2. **Check assets.** Each asset named `<content_id>-<ratio>-v<n>.<ext>` and present where the note says. Missing or misnamed: list it.
3. **Results per creative.** mktdata live: `spend_by_content` + CRM `parties_by_content`. Else: the newest `tracking/ads/reviews/` file. Per creative: spend, qualified leads, cost per qualified lead, frequency trend, days live.
4. **Fatigue.** Flag a creative whose cost per qualified lead climbs while frequency climbs, or that the platform labels creative-limited or fatigued. Fatigue → REFRESH (new creative, same angle) in the next review.
5. **Hook × format grid.** Rows hooks H1 to H4 (direct, question, proof, contrarian); columns formats A to C (static, video, carousel). Each cell: creatives, spend, qualified leads, cost per qualified lead, or "untested". This grid is what the mktdata creative screen shows; use the same numbers.
6. **Approvals.** Only a person approves a creative. When a person says "approve <content_id>", set `ad.status: approved`, `approved_by`, `approved_on` in the note. You never approve on your own. Only approved creatives can go into `create_ad`.
7. **Next to make.** From the grid: untested cells next to a winner, and refreshes for fatigued winners. Write briefs for `reel-editor` or `carousel-slides`; the CMO decides.

## Output

`<biz>/tracking/ads/library.md`: status counts, the table of creatives, the hook × format grid, gaps (missing `ad:` blocks, misnamed assets), fatigue flags, next to make.

## Rules

- One creative, one `content_id`, everywhere.
- Facts and claims in a creative follow the business's pack; never invent proof.
