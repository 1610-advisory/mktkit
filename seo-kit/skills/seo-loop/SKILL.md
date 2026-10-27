---
name: seo-loop
description: >
  Weekly SEO loop for one business site: crawl, Lighthouse, Search Console,
  Bing and AI-answer checks, compare with last week, write the report and a
  ranked fix list, and log results to the business memory. Use when someone
  says "run the SEO loop", "weekly SEO check", "how is SEO doing", "what
  changed in search", when a scheduled SEO run fires, or when the
  seo-engineer agent gets the weekly job.
metadata:
  version: 0.1.0
---

# SEO loop

One run = one dated snapshot, one report, one memory row. The business repo holds the data; this plugin holds the scripts. `<kit>` = this plugin's root (two levels up from this file). `<biz>` = the business repo root.

## Steps

Copy these into the session checklist. Keep a skipped step listed with `skip: <reason>`.

1. **Config.** `<biz>/tracking/seo/config.yaml` exists and has `site`, `sitemap`, `brand`, `domains`. Else stop and ask (the seo-engineer agent's Start step 1).
2. **Snapshot dir.** `S=<biz>/tracking/seo/snapshots/$(date +%F)`. `P` = the newest older dir in `snapshots/` (may be none).
3. **Crawl.** `uv run <kit>/scripts/site_crawl.py --config <biz>/tracking/seo/config.yaml --out $S/crawl.json`
4. **Links (optional, fast).** `npx --yes linkinator <site> --recurse --skip "<each skip_links entry>" --format json > $S/links.json`. Only if `linkinator` is wanted; the crawl already catches broken internal links.
5. **Speed.** `uv run <kit>/scripts/lighthouse_run.py --config ... --out $S/lighthouse.json`. Lab numbers. Needs Chrome.
6. **Search Console.** If a token or service account exists: `uv run <kit>/scripts/gsc.py all --config ... --out $S/gsc.json`. Else `skip: no Search Console access` and add "grant Search Console" to `needs_a_person`.
7. **Bing.** If `BING_WEBMASTER_API_KEY` is set: `uv run <kit>/scripts/bing.py all --config ... --out $S/bing.json`. Else skip with the reason.
8. **AI answers.** If `tracking/seo/prompts.yaml` exists and at least one engine is enabled with a key: load the `ai-visibility` skill and run it into `$S/ai.json`. First run of the month or no budget note: run `--dry-run` first and show the call count.
9. **Diff.** `uv run <kit>/scripts/seo_diff.py --prev $P --curr $S --out $S/diff.md`
10. **Rank the fixes.** Read `diff.md` and `crawl.json` issues. Rank by: (a) blocks indexing (non-200 or noindex in sitemap, canonical mismatch, robots blocks), (b) loses a page that earns impressions (Search Console page-two list, falling pages), (c) speed on money pages (the offer and contact paths), (d) entity and schema gaps, (e) the rest. Ten items max. Each: what, where, proof (the number), effort (S/M/L), and whether a person must act.
11. **Report.** Write `<biz>/tracking/seo/reports/<date>.md`: the `diff.md` Headline, the ranked list, `needs_a_person`, and the one next action. Short lines, the business's voice rules for anything a client reads.
12. **Memory.** Append one row to the SEO results table the business memory points to (or `memory/MEMORY.md` → a new `project-seo.md` in the business's memory style): date, 3 to 5 key numbers, report path. Log the session in `memory/logs/<date>.md`.
13. **Hand off.** Fixes the business already approved in its decisions file: load `seo-fix` and open the PRs. New kinds of fixes: list them and ask.

## Rules

- Same settings each week (pages, form factors, runs, prompts) so numbers compare. A settings change is a decision: log it.
- Never fail the whole loop for one source. Skip, say why, keep going.
- Snapshots are data: commit them in the business repo with the report. Raw Lighthouse reports stay out of git.
- No source data for a claim → it is a hypothesis; label it so.

## Scheduling

The loop is built to run unattended once a week (cron, launchd, or any agent runner): run the seo-engineer agent with the job "weekly loop" in the business repo. Scheduled runs do steps 1 to 12 and stop before opening PRs unless the decisions file says a fix type is pre-approved.
