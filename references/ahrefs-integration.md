
# Ahrefs Integration

API-first integration with Ahrefs for SEO data, keyword research, competitor analysis, and backlink monitoring. Used across SEO audits, content strategy, and planning workflows.

**Plan:** Lite ($129/month)
**Key limits:** 500 credits/month (UI), 100,000 API units/month, 100 rows per request (hard cap, no pagination), 5 projects, 750 tracked keywords, 6 months backlink/keyword history. No Content Explorer (Standard+ only).

---

## Setup

### API Key

1. Log into Ahrefs → [app.ahrefs.com/account/api-keys](https://app.ahrefs.com/account/api-keys)
2. Create an API key (workspace owner/admin only). Keys expire after 1 year.
3. Store as environment variable:

```bash
# Add to ~/.zshrc.local
export AHREFS_API_KEY="your-api-key-here"
```

### Per-Client Config Template

Create `knowledge/ahrefs-config.md` in each client folder that uses Ahrefs:

```yaml
---
title: "Ahrefs Configuration"
description: "Ahrefs tracked domains, competitor list, and priority keywords"
category: workflow
last_updated: YYYY-MM-DD
status: active
priority: high
---
```

```markdown
## Ahrefs Config

- **Primary Domain:** example.com

## Tracked Competitors

| Domain | Why |
|--------|-----|
| competitor1.com | Direct competitor, similar audience |
| competitor2.com | Content leader in space |
| competitor3.com | Ranks for our target keywords |

## Priority Keywords (for tracking and planning)

| Keyword | Current Position | Target | Notes |
|---------|-----------------|--------|-------|
| [keyword] | [pos] | [target] | [context] |
```

---

## API Reference

**Base URL:** `https://api.ahrefs.com/v3`
**Auth:** `Authorization: Bearer $AHREFS_API_KEY`
**Format:** JSON (also supports `csv`, `xml` via `output` param)
**Rate limit:** 60 requests/minute

### Unit Costs

Each API request costs a minimum of **50 units**, even for single-value endpoints.

For list endpoints, cost = `max(50, per_field_cost × num_rows)`. Each field in `select` costs 1 unit per row by default (some premium fields cost 5-10). Always specify only the fields you need via `select` to avoid paying for all fields.

**Example costs:**
- Domain Rating (single value): 50 units
- Metrics overview (single value): 50 units
- 100 organic keywords × 5 fields at 1 unit: max(50, 500) = 500 units
- 20 organic competitors × 4 fields: max(50, 80) = 80 units

**Cache:** Repeated identical requests cost 0 units (check `x-api-cache: hit` response header). Structure queries to be cache-friendly.

### Key Endpoints

#### 1. Domain Rating

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/domain-rating?target=example.com&date=$(date +%Y-%m-%d)" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns:** `domain_rating`, `ahrefs_rank`
**Cost:** 50 units

#### 2. Domain Metrics (Traffic + Keywords)

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/metrics?target=example.com&date=$(date +%Y-%m-%d)&country=us" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns:** `org_keywords`, `org_keywords_1_3`, `org_traffic`, `org_cost`, `paid_keywords`, `paid_traffic`
**Cost:** 50 units

#### 3. Backlinks Stats

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/backlinks-stats?target=example.com&date=$(date +%Y-%m-%d)" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns:** `live` (backlinks count), `live_refdomains`, `all_time`, `all_time_refdomains`
**Cost:** 50 units

#### 4. Organic Keywords (Top 100)

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=example.com&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume,sum_traffic,keyword_difficulty&limit=100&order_by=sum_traffic:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns per row:** `keyword`, `best_position`, `volume`, `sum_traffic`, `keyword_difficulty`
**Cost:** max(50, 5 fields × 100 rows) = 500 units
**Lite limit:** 100 rows max, no pagination

#### 5. Organic Competitors

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/organic-competitors?target=example.com&date=$(date +%Y-%m-%d)&country=us&select=competitor_domain,domain_rating,keywords_common,traffic&limit=20&order_by=keywords_common:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns per row:** `competitor_domain`, `domain_rating`, `keywords_common`, `traffic`
**Cost:** max(50, 4 × 20) = 80 units

#### 6. Referring Domains (Backlink Profile)

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/refdomains?target=example.com&date=$(date +%Y-%m-%d)&select=domain,domain_rating,backlinks,first_seen,last_visited&limit=50&order_by=domain_rating:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns per row:** `domain`, `domain_rating`, `backlinks`, `first_seen`, `last_visited`
**Cost:** max(50, 5 × 50) = 250 units

#### 7. Keyword Overview (Volume + Difficulty)

Batch lookup for specific keywords.

```bash
curl -s "https://api.ahrefs.com/v3/keywords-explorer/overview?country=us&keywords=keyword+one,keyword+two,keyword+three&select=keyword,volume,difficulty,cpc,traffic_potential,global_volume" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

**Returns per keyword:** `keyword`, `volume`, `difficulty` (0-100), `cpc`, `traffic_potential`, `parent_topic`
**Cost:** max(50, fields × keyword_count)

---

## Content Gap (Manual Build)

**There is no Content Gap API endpoint.** The Content Gap tool is UI-only.

**Workaround:** Pull organic keywords for your domain and each competitor, then diff programmatically.

```bash
# 1. Pull client's top 100 keywords
curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=client.com&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume&limit=100&order_by=sum_traffic:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY" > /tmp/client_keywords.json

# 2. Pull competitor's top 100 keywords
curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=competitor.com&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume&limit=100&order_by=sum_traffic:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY" > /tmp/competitor_keywords.json

# 3. Diff to find gaps (keywords competitor has that client doesn't)
```

**Cost:** 500 units per domain (100 rows × 5 fields). For client + 2 competitors = ~1,500 units.

**Alternative:** Use the Ahrefs UI Content Gap tool (consumes UI credits, not API units) for deeper analysis. Save the export CSV to `tracking/ahrefs/content-gap-YYYY-MM.csv` and reference it in planning workflows.

---

## Credit Budget Strategy

With 100,000 API units/month, the budget is generous. Here's allocation by workflow:

### Full Domain Snapshot (~800 units)
Pull once per month per client domain. Reuse cached data for the rest of the month.
- Domain Rating: 50 units
- Metrics: 50 units
- Backlinks Stats: 50 units
- Top 100 organic keywords: 500 units
- Top 50 referring domains: 250 units
- **Subtotal: ~900 units** per domain

### Monthly Planning Cycle (~4,000 units)
- Domain snapshot for client: 900 units
- Domain snapshot for 3 competitors (DR + metrics only): 300 units (50+50 each)
- Top 100 keywords per competitor (×3): 1,500 units
- Organic competitors list (20): 80 units
- Keyword overview for 50 planned targets: 300 units
- **Subtotal: ~3,080 units**

### Biweekly Brief Research (~1,500 units)
- Client metrics refresh: 50 units
- Top 100 keywords refresh (check position changes): 500 units
- Competitor keywords for 1 key competitor: 500 units
- Keyword validation for 30 brief topics: 200 units
- **Subtotal: ~1,250 units**

### SEO Audit (~3,000 units)
- Full domain snapshot: 900 units
- Competitor snapshots (×3): 2,700 units
- Extra referring domain pulls if needed: 250 units
- **Subtotal: ~3,850 units**

### Multi-Client Math
At ~5,000 units per active client per month (1 monthly plan + 2 biweekly briefs), you can support ~15-20 clients comfortably. Most months you'll have headroom for ad-hoc keyword research, new prospect analysis, and deeper competitor dives.

---

## Workflow Integration Points

### When Running an SEO Audit
Read `references/seo-audit.md` — the "Authority & Links (Ahrefs-Powered)" section:
1. Domain overview (DR, referring domains, organic traffic baseline)
2. Backlink profile (top referring domains by DR)
3. Organic keyword portfolio (position distribution, quick wins)
4. Competitor comparison (DR and traffic vs top organic competitors)

### When Building Content Strategy
Read `references/content-strategy.md` — the "Keyword Research with Ahrefs" section:
1. Pull organic keywords to see what's already ranking
2. Build content gap manually (or use UI export)
3. Validate keyword ideas with volume + difficulty data
4. Identify quick wins (ranking 5-20 with decent volume)

### When Generating Monthly Plans
Read `references/monthly-planning-protocol.md` — the competitor analysis step:
1. Pull client's DR and organic traffic (vs last month's cached data)
2. Pull organic competitors list for new entrants
3. Build content gap for topic ideas
4. Feed keyword data into the month's content themes

### When Generating Biweekly Briefs
Read `references/biweekly.md` — the Ahrefs pre-brief step:
1. Metrics refresh (any traffic shifts)
2. Check keyword position changes vs last pull
3. Pull competitor keywords for topic inspiration
4. Validate planned topics with keyword data

---

## Practical Tips

- **Always use `select`.** Omitting it returns all fields and you pay for all of them. Only request the fields you actually need.
- **Always include `date`.** Site Explorer endpoints require it. Use `$(date +%Y-%m-%d)` for current data.
- **Batch queries at the start of a workflow.** Don't pull data ad-hoc throughout a session. Pull everything upfront, save to temp files, and reference throughout.
- **Cache domain overviews.** DR and referring domain counts don't change fast. One pull per month per domain is enough. Save to `tracking/ahrefs/domain-snapshot-YYYY-MM.json`.
- **100-row cap is hard.** You cannot paginate past it on Lite. Sort by the metric that matters most (`sum_traffic:desc` for keywords, `domain_rating:desc` for referring domains) to get the most valuable rows.
- **Leverage API cache.** Identical queries within the cache window cost 0 units. If you need the same data twice in a session, don't worry about re-fetching.
- **Use Content Gap in the UI.** The API doesn't have this endpoint. Run it in the Ahrefs UI, export the CSV, and save to `tracking/ahrefs/content-gap-YYYY-MM.csv`.
- **Save raw responses.** Store in `tracking/ahrefs/` for month-over-month comparison without re-pulling.
