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
  version: 0.2.0
---

# Ads build

One run = one campaign folder ready for launch, plus launch proposals. `<kit>` = this plugin's root. `<biz>` = the business repo root. Campaign folder: `<biz>/tracking/ads/campaigns/<slug>/`.

Read first: `<kit>/references/campaign-build.md` (the method: matrix, structure by budget, copy per cell, briefs, quality check), `ads-judgment.md` (budget math, small-budget structure, fatigue), `policy-check.md`, `naming.md`. The ad-matrix contract is `ad-matrix.schema.json`. With mktdata live: `mktdata-requests.md`.

## Steps

1. **Inputs.** Config has caps, target cost per qualified lead and a verified lead path (`ads-tracking-check` passed). If not, stop: "tracking first". mktdata live: the caps and the standing limit come from `get_config`; no caps there = stop and list it for the owner. Load `mkt-kit` for voice, personas, offer.
2. **Matrix.** Read or write `ad-matrix.json` + `ad-matrix.md` in the campaign folder (cells `MA-H{1-4}-{A-C}`). Never rename a cell id.
3. **Cells the budget can test.** Use the budget math in `ads-judgment.md`. Under about $50 a day: 4 to 6 cells, one campaign that can learn. Write why in `plan.md`.
4. **Creatives.** Each selected cell needs a content piece: reuse an approved one from the library (`ads-library`; mktdata live: `list_content {library_status: approved}`) or write a brief. New creative → content note with an `ad:` block (`naming.md`), status `draft`, and a brief to `reel-editor` (video) or `carousel-slides` (carousel). mktdata live: index the new note with `upsert_content` (`path`, `title`, `kind: ad`, `note_ref` = the note id, `hook`, `format`); it starts `draft`. You do not make the asset, and you never approve it.
5. **Copy per cell, per platform.** Google RSA: 15 headlines (≤30 chars), 4 descriptions (≤90), unpinned by default. Meta: primary text short and long, 2 headlines (≤40). Copy in the business's voice; facts only from the pack. Save `copy/<platform>.md`; each ad's name per `naming.md`.
6. **Policy pass.** Run `policy-check.md` on the final copy. Fix what it finds; list only what a person must act on (special ad category, regulated claims).
7. **Plan.** `plan.md`, one page: structure and why, daily budget, audiences (broad by default), which cells go first, the verdict rule in numbers (exactly: no verdict before ~2× target cost per qualified lead (`targets.cost_per_qualified_lead_cents`, qualified = CRM-qualified per `conversions.qualified`), or on data < 3 days; give the dollar line for this campaign), UTM pattern, launch checklist.
8. **Launch proposals.** Read `<kit>/references/change-queue.md`. A new campaign, new creative or new audience is **always a person's**: mktdata has no request for a new campaign or audience, so write it in `plan.md` and `needs_a_person`. Into an existing ad set: `list_proposals` first (no duplicate), then `propose_change` `create_ad {campaign_id: <ad group / ad set id from list_campaigns>, content_id: <library piece>, landing_url: <https URL>}`. It runs inside the limit only when the piece is approved, the limit allows new ads and the landing host is on the owner's list; else it waits for a person on the Changes screen. Budgets: `set_budget` on the row that holds the budget. Total daily budget never over the daily cap. Campaigns launch paused until a person approves. Without mktdata: the proposal file.
9. **Humanize.** Run `humanizer` on all copy a client or customer reads.

## Output

```
tracking/ads/campaigns/<slug>/
  ad-matrix.json, ad-matrix.md
  plan.md
  copy/google.md, copy/meta.md
  briefs/<note id>.md
  policy-review.md
```

Plus proposals (mktdata or `tracking/ads/proposals/<date>.md`) and the agent report.

## Rules

- No live API writes from this skill. Upload-ready files and proposals only. Screen-only mktdata requests (`set_content_status`, `decide_change`, ...) are never yours.
- Every ad has a content-note id in its name and `utm_content`; no exceptions. If the landing page has a mktdata content UUID, put it in `<meta name="content-id">` (UUID only; see `naming.md`).
- No invented numbers, prices or reviews in copy. A missing fact: ask.
