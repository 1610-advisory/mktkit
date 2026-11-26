---
name: ads-build
description: >
  Build a paid campaign for one business from an ad matrix: pick the cells the
  budget can test, write platform copy per cell (Google RSA, Meta), write
  creative briefs for reel-editor or carousel-slides, set names and UTMs, and
  propose the launch (inside the standing limit or queued for a person). Use
  when someone says "build a campaign", "launch ads for", "write the ads",
  "ad copy for", "turn this into ads", "new Google / Meta campaign", "round 2
  creative", or the ads-engineer gets a "build campaign" job.
metadata:
  version: 0.1.0
---

# Ads build

One run = one campaign folder ready for launch, plus launch proposals. `<kit>` = this plugin's root. `<biz>` = the business repo root. Campaign folder: `<biz>/tracking/ads/campaigns/<slug>/`.

Read first: `<kit>/references/campaign-build.md` (the method: matrix, structure by budget, copy per cell, briefs, quality check), `ads-judgment.md` (budget math, small-budget structure, fatigue), `policy-check.md`, `naming.md`. The ad-matrix contract is `ad-matrix.schema.json`.

## Steps

1. **Inputs.** Config has caps, target cost per qualified lead and a verified lead path (`ads-tracking-check` passed). If not, stop: "tracking first". Load `mkt-kit` for voice, personas, offer.
2. **Matrix.** Read or write `ad-matrix.json` + `ad-matrix.md` in the campaign folder (cells `MA-H{1-4}-{A-C}`). Never rename a cell id.
3. **Cells the budget can test.** Use the budget math in `ads-judgment.md`. Under about $50 a day: 4 to 6 cells, one campaign that can learn. Write why in `plan.md`.
4. **Creatives.** Each selected cell needs a content piece: reuse an approved one from the library (`ads-library`) or write a brief. New creative → content note with an `ad:` block (`naming.md`), status `draft`, and a brief to `reel-editor` (video) or `carousel-slides` (carousel). You do not make the asset.
5. **Copy per cell, per platform.** Google RSA: 15 headlines (≤30 chars), 4 descriptions (≤90), unpinned by default. Meta: primary text short and long, 2 headlines (≤40). Copy in the business's voice; facts only from the pack. Save `copy/<platform>.md`; each ad's name per `naming.md`.
6. **Policy pass.** Run `policy-check.md` on the final copy. Fix what it finds; list only what a person must act on (special ad category, regulated claims).
7. **Plan.** `plan.md`, one page: structure and why, daily budget, audiences (broad by default), which cells go first, the verdict rule in numbers (no verdict before ~2× target cost per qualified lead; none on data under 3 days), UTM pattern, launch checklist.
8. **Launch proposals.** Read `<kit>/references/change-queue.md`. A new campaign, new creative or new audience is **always queued** for a person. Inside the limit only: `create_ad` from an already-approved creative into an existing ad set. Total daily budget never over `caps.daily_cap_cents`. Campaigns launch paused until a person approves.
9. **Humanize.** Run `humanizer` on all copy a client or customer reads.

## Output

```
tracking/ads/campaigns/<slug>/
  ad-matrix.json, ad-matrix.md
  plan.md
  copy/google.md, copy/meta.md
  briefs/<content_id>.md
  policy-review.md
```

Plus proposals (mktdata or `tracking/ads/proposals/<date>.md`) and the agent report.

## Rules

- No live API writes from this skill. Upload-ready files and proposals only.
- Every ad has a `content_id`; no exceptions.
- No invented numbers, prices or reviews in copy. A missing fact: ask.
