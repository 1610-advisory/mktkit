<!-- Vendored from https://github.com/boringmarketer/boring-marketing-skills (commit 7c6678c), skills/paid-ads/SKILL.md. MIT License, Copyright (c) 2026 Boring Marketing, LLC. See ../THIRD_PARTY_NOTICES.md. Excerpt: the section "Mode 3: RESULTS REVIEW" only; text unmodified. -->

> **ads-kit note:** read this as a playbook. In ads-kit the measure is the CRM-qualified lead (cost per qualified lead from the business's own records), not the platform's conversion count.
> The ads-engineer never writes to an ad account itself: money changes go only through the mktdata change queue (`propose_change`), see `change-queue.md`.
> Here a verdict reads cost per qualified lead from the CRM, not the export's conversion column.
> Slash-command names (`/ads-incrementality-check`, `/performance-review`) point at the source library's skills, which ads-kit does not ship; the ads-kit equivalents are `ads-review` and `ads-tracking-check`.

## Mode 3: RESULTS REVIEW

Input: a pasted platform export (Meta Ads Manager / Google Ads CSV) or screenshots,
or, if API keys are present, a read-only pull (see API access below). Also read
`ad-matrix.json` for the cells and the target CPA from campaign-plan.md (or ask for
break-even CPA; without it there is no honest verdict, only vibes).

**Map rows to cells** via ad name or utm_content. Rows that map to no cell get flagged,
not silently dropped: unmapped spend is a naming-discipline bug worth surfacing, in
plain words ("$220 went to ads that don't match the test plan").

**The judgment threshold comes before the verdict.** A cell must spend roughly **2×
target CPA** before it earns any verdict at all. At a $50 target CPA, a cell with $60
spent and zero conversions is "keep running", not "kill". At 2× CPA spend, a
true-at-target cell would have produced ~2 conversions, so zero starts to mean
something. Also check recency: conversions are modeled and report up to ~72h late, so
never kill anything on data less than 3 days old (detail in
`references/ads-judgment.md`).

**Before any verdict, check the conversions are real.** Platform counts are claims. If a
campaign's conversions are mostly Google-hosted local actions ("Business profile" calls,
"Get directions"), branded search, retargeting or view-through, its CPA is the platform's
opinion. For a business where leads phone in, compare against the phone log; for a store,
against new-customer orders. Route a suspect campaign to `/ads-incrementality-check` before
scaling it.

Then, per cell that clears the threshold:

- **KILL**: ≥2× target-CPA spend with zero conversions, or CPA above ~1.5× break-even
  with no improving trend. Show the math in the verdict, not just the label.
- **SCALE**: CPA at or under target with stable trend. Default raise: **+20-30% per
  day**, not doubling; large jumps reset the learning phase and the winner's CPA too.
- **ITERATE**: the diagonal reads: if one hook wins across formats, write new
  formats/creative for that hook; if one format wins across hooks, run the untested
  hooks in that format. From a single winner, two moves: keep the angle and change the
  format, or keep the format and change the hook (the first line or first 3 seconds).
  Name the recommended round-2 cells explicitly (existing `planned` cells from the
  matrix, `-v2` variants of winners, or `var-format-<name>` and `var-hook-<n>` variants).
- **REFRESH**: a winner whose cost per result has climbed. Check the delivery column
  for Meta's "Creative limited" or "Creative fatigue" label and the frequency trend
  ("Creative volume, cadence and fatigue" in `references/ads-judgment.md`). The fix is a
  materially different ad on the same angle, not a recolor or a crop.

Output:

- `./campaigns/<name>/ads/results-<YYYY-MM-DD>.md`: per-ad table (spend, CPA/CTR,
  verdict + math), the hook × format read, round-2 recommendations, then one Sources
  and assumptions note (the export and date range, where the target CPA came from, how
  much of the conversion count is platform-modeled or local-action). Ads are labeled by
  hook and format, and each ad's upload name is in its copy file.
- Update `ad-matrix.json`: per-cell `results` blocks and statuses
  (`live`/`paused`/`completed`)
- **Draft learnings entries** in the structured format, saved under "Draft learnings" in
  `./campaigns/<name>/notes.md` (not pasted):
  `- [YYYY-MM-DD] [paid-ads] hook=proof beat hook=direct on CPA 1.8x (n=6 cells,
  $1,400 spend, source: meta-export)`. `/performance-review` owns `learnings.md` and
  picks them up. Append directly only if the user explicitly says to save them.
