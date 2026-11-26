---
name: ads-review
description: >
  Daily or weekly paid-ads review for one business: pull spend and CRM
  outcomes, map spend to content_id, give each ad a KILL / SCALE / ITERATE /
  REFRESH verdict with the math (or "keep running" when it is too early), and
  propose changes through the mktdata change queue. Use when someone says
  "review the ads", "kill or scale", "how are the ads doing", "daily ads
  check", "weekly ads review", "what should we pause", "should we raise the
  budget", when a scheduled ads run fires, or when the ads-engineer gets a
  review job.
metadata:
  version: 0.1.0
---

# Ads review

One run = one dated review file + zero or more proposals. `<kit>` = this plugin's root. `<biz>` = the business repo root.

Read first: `<kit>/references/results-review.md` (verdict method), `ads-judgment.md` (fatigue, signal loss), `change-queue.md` (how to propose), `audit-guardrails.md` (facts vs hypotheses, MISSING inputs).

## Steps

1. **Window.** Daily: last 7 days, reported per day, ending yesterday. Weekly: last 7 full days vs the 7 before. Match the windows of spend and outcomes; never divide full-period spend by part-period results.
2. **Spend.** mktdata live: `spend_by_content` and `spend_by_campaign`. Else: Google Ads MCP and Meta Ads MCP reads (ad level: date, spend, impressions, clicks, platform conversions), saved to `tracking/ads/snapshots/<date>/<platform>.json`.
3. **Outcomes from our records.** mktdata live: CRM `opportunities_by_campaign` and `parties_by_content` (leads, qualified, won + amount). Else: `tracking/revenue-attribution.csv`. Platform conversions go beside them as "platform claim".
4. **Map spend to `content_id`.** By ad name, then `utm_content`. Unmapped spend: list each ad with its amount ("$220 went to ads with no content_id"). It is a naming bug.
5. **Threshold before verdict.** The rule, exactly: no verdict before ~2× target cost per qualified lead (`targets.cost_per_qualified_lead_cents`, qualified = CRM-qualified per `conversions.qualified`), or on data < 3 days. Per ad (cell): below either line the status is "keep running", with the spend so far and the days of data shown. No target in config: no verdicts at all; say so.
6. **Verdicts with math** (measure = cost per qualified lead):
   - **KILL**: ≥ 2× target spent and zero qualified leads, or cost per qualified lead > ~1.5× break-even with no better trend.
   - **SCALE**: at or under target, stable trend. Raise +20 % a day at most.
   - **ITERATE**: name the round-2 cells (same hook new format, or same format new hook).
   - **REFRESH**: a winner whose cost climbs with frequency or a fatigue label. New creative on the same angle.
7. **Caps check.** Month-to-date spend vs `caps.monthly_hard_cap_cents` and today's pace vs `caps.daily_cap_cents`. On pace to break a cap: propose the cuts that keep spend under it, first.
8. **Propose.** One proposal per change (`change-queue.md`), `campaign_id` = mktdata id. Mark each "inside limit" or "needs a person". KILL → `pause_ad`. SCALE → `set_budget` (≤ +20 %). REFRESH / ITERATE → briefs + queued `create_ad` or a library request; new creative always waits for a person.
9. **Loss rule.** If config's loss rule would trip (limit-made changes over the window lose money vs target), say so at the top; propose nothing inside the limit; everything queues.
10. **Write.** `<biz>/tracking/ads/reviews/<YYYY-MM-DD>.md`: headline (3 lines), table per ad (content_id, cell, spend, leads, qualified, won, cost per qualified lead, platform claim, verdict + math), unmapped spend, caps status, proposals, sources and labels. Append one row to the business ads memory table.

## Rules

- The business's own record beats the platform's count. Say how much of the platform claim is modeled or local actions.
- Every number carries its source and label (Observed / Reported / Inferred). A missing input is MISSING, not a guess.
- Same-day numbers move for ~72 h. Never act on today.
- No direct changes. MCP write tools stay off.

## Scheduling

Built to run unattended once a day: run the ads-engineer agent with the job "daily review" in the business repo. Scheduled runs write the review and the proposals and stop.
