---
name: seo-fix
description: >
  Turn SEO findings into pull requests on the business's site repo, or build a
  new search-led page (calculator, comparison, question page) as a PR. Never
  merges. After a person merges and the change is live, pings IndexNow for the
  changed URLs. Use when someone says "fix the SEO issues", "open PRs for the
  report", "fix the schema / titles / sitemap / speed", "build the comparison
  page", "build a calculator page", or when the seo-engineer agent gets a fix
  or page job.
metadata:
  version: 0.1.0
---

# SEO fix

Input: findings from a loop report (or a person), or a page brief. Output: PRs. `<kit>` = this plugin's root. `<site>` = the site repo (config `site_repo`, or ask).

## Before any edit

1. `git -C <site> remote -v` and read `<site>`'s `CLAUDE.md` / `AGENTS.md` / `README` for its branch, PR and deploy rules. They beat this file.
2. Update the default branch, then `git -C <site> checkout -b <type>/seo-<short-name>`. Types: `fix/` for bugs, `content/` for copy, `feat/` for new pages or tools.
3. One PR per coherent batch (for example "schema entity cleanup", "sitemap + canonical headers"). Do not mix a new page with unrelated fixes.

## Fix patterns

| Finding | Usual fix | Proof after |
|---|---|---|
| Sitemap lists non-HTML, redirects, noindex | Generate the sitemap from the real indexable routes only; `lastmod` from content dates, not build time | Re-crawl: no `sitemap_*` issues |
| Canonical missing or mismatched | One canonical per page = its final URL; alternate formats (markdown, PDF) send `Link: <html-url>; rel="canonical"` | Re-crawl |
| Duplicate entities in JSON-LD | One `Organization` with a stable `@id` (`<site>/#organization`); every other node refers to it; add `logo`, `sameAs`, `founder` only from the pack | Re-crawl JSON-LD types and ids |
| Title / description length or duplicates | Rewrite in the business voice, keep the main search term early | Re-crawl |
| Orphan or thin inbound | Add contextual links from 2 to 3 related pages, not footer dumps | Re-crawl inbound count |
| Slow LCP (lab) | Find the LCP element in `lighthouse.json`; common causes: hero fade-in from opacity 0, unoptimized hero image, render-blocking third-party script, short image cache | Lighthouse same settings, before vs after |
| Server or CDN header issue | Write the change and the exact command for a person; do not change servers yourself | Header check with curl |

Run the site's own lint and build before you push. A failing build is not a PR.

## New page (search-led)

1. The page has one job: answer one search a persona really makes. Get the term from `tracking/seo/keyword-map.md` (or run `keyword-map`). No volume data: say "volume not measured".
2. Read the playbook for the type in `<kit>/references/`: `competitors.md` (alternatives and "vs" pages), `free-tools.md` (calculators, generators), `programmatic-seo.md` (templated pages at scale; small sites rarely need it). Then `ai-visibility-audit.md` → content that gets cited: cite sources, give real figures from the facts file, quote a named person from the business.
3. Build it the way the site builds pages (read two existing pages first). Add: title, description, canonical, one H1, JSON-LD that refers to the business `@id`, sitemap entry, 2 to 3 internal links in, and its entry in `llms.txt` if the site has one.
4. Copy rules: the business voice file, the facts file for every number, run the `humanizer` skill if installed. Competitor pages: only facts you can source with a link; never disparage.

## PR

- Title: what changed. Body: `## Summary`, `## Changes`, `## Proof` (before numbers now, the re-check to run after deploy), `## Needs a person` (if any).
- Never merge. Report the PR link.

## After a person merges and it is live

1. Re-run the crawl (and Lighthouse if speed changed) and log the after numbers in the business memory results table.
2. IndexNow (only if the site hosts a key file and config has `indexnow_key_url`): `uv run <kit>/scripts/indexnow.py --config <biz>/tracking/seo/config.yaml --key-file-url <url> --urls <changed urls>` prints a dry run; add `--send` only after that check. Changed URLs only, never the whole site.
3. Search Console: for a new or important page, tell the person to click "Request indexing" in the URL Inspection tool. No API does that for normal pages.
