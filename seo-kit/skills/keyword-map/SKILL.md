---
name: keyword-map
description: >
  Build or refresh the business's keyword map: which search each page should
  win, which searches have no page yet, and which pages sit on page 2 and are
  worth a push. Uses Search Console first (free, real data), personas and the
  offer second, and paid keyword data only if configured. Use when someone
  says "keyword map", "what should we rank for", "what pages should we
  build", "page 2 to page 1", "content gaps", or before planning search-led
  content.
metadata:
  version: 0.1.0
---

# Keyword map

Output: `<biz>/tracking/seo/keyword-map.md`. One row per target search. The CMO's monthly plan and the content pipeline read it.

## Sources, in order

1. **Search Console** (`gsc.json` from the newest snapshot, or `uv run <kit>/scripts/gsc.py all ...`): real queries, pages, positions. `page_two` = the push list.
2. **The pack:** `personas-storybrand.md` (the problems people search for, in their words), `offer.md` (what each page must sell toward), `goals-and-benchmarks.md` (what matters this period).
3. **Paid volume data, only if configured:** DataForSEO (`dataforseo` MCP server or API, pay as you go), Ahrefs, or a Keyword Planner export the person hands you. No source → write "not measured", never a guessed number. An estimate must say "estimate".

## Steps

1. List 15 to 40 candidate searches: Search Console queries with impressions, plus persona questions, plus "<service> cost", "<service> vs <alternative>", "how to <job the business does>", and branded searches.
2. Group searches that one page can answer (same intent). One group → one page. Two pages chasing one group = cannibalization: pick one, link or redirect the other.
3. For each group: target page (existing URL or "new"), intent (learn / compare / cost / hire), persona, which door or offer it leads to, current position and impressions (Search Console or "none"), volume and its source, next action (keep / improve / build / merge).
4. Rank "build" rows by: fits the offer, persona pain is strong, we can say something true and specific (facts file), effort. Top 3 go to the CMO as page proposals.
5. Page-two rows: the page exists and ranks 8 to 20 with impressions. Actions: tighten title to the query, add the missing sub-answers, add internal links from strong pages, add a cited figure. These are cheap wins; list them first.

## Table format

| Search group | Page | Intent | Persona | Leads to | Pos / impr (GSC, dates) | Volume (source) | Action |
|---|---|---|---|---|---|---|---|

Date the file. Keep the last version's rows that still apply; mark changed rows. Log the refresh in the business memory.
