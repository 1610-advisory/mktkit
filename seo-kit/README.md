# seo-kit

An SEO engineer for a small-business website, as a Claude Code plugin. It runs a weekly loop, finds what holds the site back in Google, Bing and AI answers, and opens fix pull requests in your site repo for a person to review and merge.

It pairs with the **ai-cmo** plugin in this repo: the CMO decides what the business says and to whom; the engineer makes the site get found, indexed and cited. It also works alone.

```
/plugin marketplace add 1610-advisory/mktkit
/plugin install seo-kit@mktkit
```

## What it does

| Loop step | How | Needs |
|---|---|---|
| Crawl: titles, descriptions, canonicals, H1s, JSON-LD, sitemap, robots, llms.txt, internal links, redirects, orphans | `scripts/site_crawl.py` | Nothing |
| Speed (lab): Lighthouse scores, LCP, CLS, TBT per page | `scripts/lighthouse_run.py` | Chrome, Node |
| Index state, queries, page-2 list | `scripts/gsc.py` (Search Console API, read-only) | Search Console access |
| Bing queries, pages, crawl issues | `scripts/bing.py` | Bing Webmaster API key |
| AI answers: is the business named, where, which sites are cited, which dollar figures to check | `scripts/ai_visibility.py` | an OpenRouter key, or a key per engine |
| Week-over-week report | `scripts/seo_diff.py` | Last week's snapshot |
| Tell Bing and others about changed URLs | `scripts/indexnow.py` (dry run unless `--send`) | A key file on the site |

Skills: `seo-loop` (the weekly run), `seo-fix` (findings or a page brief → PR), `keyword-map` (which search each page should win), `ai-visibility` (the AI question battery). Agent: `seo-engineer`.

Playbooks in `references/`: SEO audit and AI-visibility audit, plus competitor/alternative pages, free tools, programmatic SEO, directory submissions and link building (adapted from [marketingskills](https://github.com/coreyhaines31/marketingskills), MIT; see `THIRD_PARTY_NOTICES.md`).

## What stays with a person, by design

- Merging PRs and deploying.
- Granting Search Console and Bing access, and setting API keys (environment variables only).
- Directory and listing forms, link outreach, any email or post. The engineer drafts them; a person sends.
- Clicking "Request indexing" in Search Console for a new page. Google has no API for that on normal pages.

## Files it keeps in your business repo

```
tracking/seo/
  config.yaml            site, sitemap, brand, domains, competitors, facts file, engines
  prompts.yaml           the fixed AI question battery
  ai-visibility.jsonl    every AI answer, append-only
  keyword-map.md
  snapshots/YYYY-MM-DD/  crawl.json, lighthouse.json, gsc.json, bing.json, ai.json, diff.md
  reports/YYYY-MM-DD.md  the weekly report
```

Start: copy `templates/config.yaml` and `templates/prompts.yaml` into `tracking/seo/`, fill them in, then ask the agent for a "weekly loop".

## Run it weekly

Point any scheduler (cron, launchd, a hosted agent runner) at: run the `seo-engineer` agent in the business repo with the job "weekly loop". Scheduled runs write the report and stop before opening PRs unless your decisions file pre-approves that kind of fix.

## Costs

The crawl, Lighthouse, Search Console, Bing and IndexNow are free. AI answers cost API fees per call (prompts × engines × runs); run `--dry-run` to see the call count first. Keyword volume data is optional and paid (DataForSEO, Ahrefs, or a Keyword Planner export).

## Honest limits

- Lighthouse is lab data, not what real visitors get.
- API answers with web search approximate, but do not equal, what people see in ChatGPT, Google AI Overviews or Copilot.
- llms.txt has no measured effect on AI citations so far. The kit checks it is present; it does not sell it as a lever.
- Most SEO audit checks are things a capable model finds without help. The value here is the loop: same checks every week, saved baselines, fixes as PRs, and numbers that show whether they worked.
