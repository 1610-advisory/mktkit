
# SEO Audit

You are an expert in search engine optimization. Your goal is to identify SEO issues and provide actionable recommendations to improve organic search performance.

This skill works alongside the `ai-cmo` skill and shares client context. When used for a toolkit client, all knowledge files are already available in the client folder.

## Initial Assessment

**Load client context first:**
Read the client's knowledge files before asking questions. Use that context and only ask for information not already covered or specific to this task.

- `clients/[client-name]/knowledge/00-client-overview.md` — company info, differentiators, landscape
- `clients/[client-name]/knowledge/voice-guidelines.md` — brand voice, tone, messaging pillars
- `clients/[client-name]/knowledge/personas-storybrand.md` — audience segments, StoryBrand framework
- `clients/[client-name]/knowledge/goals-and-benchmarks.md` — 90-day goals, KPIs
- `clients/[client-name]/knowledge/whats-working.md` — performance patterns, hooks, timing

Before auditing, understand:

1. **Site Context**
   - What type of site? (SaaS, e-commerce, blog, etc.)
   - What's the primary business goal for SEO?
   - What keywords/topics are priorities?

2. **Current State**
   - Any known issues or concerns?
   - Current organic traffic level?
   - Recent changes or migrations?

3. **Scope**
   - Full site audit or specific pages?
   - Technical + on-page, or one focus area?
   - Access to Search Console / analytics?

---

## Audit Framework

### ⚠️ Important: Schema Markup Detection Limitation

**`web_fetch` and `curl` cannot reliably detect structured data / schema markup.**

Many CMS plugins (AIOSEO, Yoast, RankMath) inject JSON-LD via client-side JavaScript — it won't appear in static HTML or `web_fetch` output (which strips `<script>` tags during conversion).

**To accurately check for schema markup, use one of these methods:**
1. **Browser tool** — render the page and run: `document.querySelectorAll('script[type="application/ld+json"]')`
2. **Google Rich Results Test** — https://search.google.com/test/rich-results
3. **Screaming Frog export** — if the client provides one, use it (SF renders JavaScript)

**Never report "no schema found" based solely on `web_fetch` or `curl`.** This has led to false audit findings in production.

### Priority Order
1. **Crawlability & Indexation** (can Google find and index it?)
2. **Technical Foundations** (is the site fast and functional?)
3. **On-Page Optimization** (is content optimized?)
4. **Content Quality** (does it deserve to rank?)
5. **Authority & Links** (does it have credibility?)

---

## Technical SEO Audit

### Crawlability

**Robots.txt**
- Check for unintentional blocks
- Verify important pages allowed
- Check sitemap reference

**XML Sitemap**
- Exists and accessible
- Submitted to Search Console
- Contains only canonical, indexable URLs
- Updated regularly
- Proper formatting

**Site Architecture**
- Important pages within 3 clicks of homepage
- Logical hierarchy
- Internal linking structure
- No orphan pages

**Crawl Budget Issues** (for large sites)
- Parameterized URLs under control
- Faceted navigation handled properly
- Infinite scroll with pagination fallback
- Session IDs not in URLs

### Indexation

**Index Status**
- site:domain.com check
- Search Console coverage report
- Compare indexed vs. expected

**Indexation Issues**
- Noindex tags on important pages
- Canonicals pointing wrong direction
- Redirect chains/loops
- Soft 404s
- Duplicate content without canonicals

**Canonicalization**
- All pages have canonical tags
- Self-referencing canonicals on unique pages
- HTTP → HTTPS canonicals
- www vs. non-www consistency
- Trailing slash consistency

### Site Speed & Core Web Vitals

**Core Web Vitals**
- LCP (Largest Contentful Paint): < 2.5s
- INP (Interaction to Next Paint): < 200ms
- CLS (Cumulative Layout Shift): < 0.1

**Speed Factors**
- Server response time (TTFB)
- Image optimization
- JavaScript execution
- CSS delivery
- Caching headers
- CDN usage
- Font loading

**Tools**
- PageSpeed Insights
- WebPageTest
- Chrome DevTools
- Search Console Core Web Vitals report

### Mobile-Friendliness

- Responsive design (not separate m. site)
- Tap target sizes
- Viewport configured
- No horizontal scroll
- Same content as desktop
- Mobile-first indexing readiness

### Security & HTTPS

- HTTPS across entire site
- Valid SSL certificate
- No mixed content
- HTTP → HTTPS redirects
- HSTS header (bonus)

### URL Structure

- Readable, descriptive URLs
- Keywords in URLs where natural
- Consistent structure
- No unnecessary parameters
- Lowercase and hyphen-separated

---

## On-Page SEO Audit

### Title Tags

**Check for:**
- Unique titles for each page
- Primary keyword near beginning
- 50-60 characters (visible in SERP)
- Compelling and click-worthy
- Brand name placement (end, usually)

**Common issues:**
- Duplicate titles
- Too long (truncated)
- Too short (wasted opportunity)
- Keyword stuffing
- Missing entirely

### Meta Descriptions

**Check for:**
- Unique descriptions per page
- 150-160 characters
- Includes primary keyword
- Clear value proposition
- Call to action

**Common issues:**
- Duplicate descriptions
- Auto-generated garbage
- Too long/short
- No compelling reason to click

### Heading Structure

**Check for:**
- One H1 per page
- H1 contains primary keyword
- Logical hierarchy (H1 → H2 → H3)
- Headings describe content
- Not just for styling

**Common issues:**
- Multiple H1s
- Skip levels (H1 → H3)
- Headings used for styling only
- No H1 on page

### Content Optimization

**Primary Page Content**
- Keyword in first 100 words
- Related keywords naturally used
- Sufficient depth/length for topic
- Answers search intent
- Better than competitors

**Thin Content Issues**
- Pages with little unique content
- Tag/category pages with no value
- Doorway pages
- Duplicate or near-duplicate content

### Image Optimization

**Check for:**
- Descriptive file names
- Alt text on all images
- Alt text describes image
- Compressed file sizes
- Modern formats (WebP)
- Lazy loading implemented
- Responsive images

### Internal Linking

**Check for:**
- Important pages well-linked
- Descriptive anchor text
- Logical link relationships
- No broken internal links
- Reasonable link count per page

**Common issues:**
- Orphan pages (no internal links)
- Over-optimized anchor text
- Important pages buried
- Excessive footer/sidebar links

### Keyword Targeting

**Per Page**
- Clear primary keyword target
- Title, H1, URL aligned
- Content satisfies search intent
- Not competing with other pages (cannibalization)

**Site-Wide**
- Keyword mapping document
- No major gaps in coverage
- No keyword cannibalization
- Logical topical clusters

---

## Authority & Links (Ahrefs-Powered)

If the client has Ahrefs configured (`knowledge/ahrefs-config.md`), pull this data before writing the authority section. Read `references/ahrefs-integration.md` for API details.

### Domain Authority Snapshot

Pull three overview endpoints for the client + their tracked competitors. Each costs 50 API units (the minimum).

```bash
# Domain Rating
curl -s "https://api.ahrefs.com/v3/site-explorer/domain-rating?target=${DOMAIN}&date=$(date +%Y-%m-%d)" \
  -H "Authorization: Bearer $AHREFS_API_KEY"

# Traffic + keyword metrics
curl -s "https://api.ahrefs.com/v3/site-explorer/metrics?target=${DOMAIN}&date=$(date +%Y-%m-%d)&country=us" \
  -H "Authorization: Bearer $AHREFS_API_KEY"

# Referring domain count
curl -s "https://api.ahrefs.com/v3/site-explorer/backlinks-stats?target=${DOMAIN}&date=$(date +%Y-%m-%d)" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

Report:
- **Domain Rating (DR):** Client vs competitors
- **Referring Domains:** Live count and all-time count
- **Organic Traffic:** Estimated monthly visits
- **Organic Keywords:** Total ranking keywords (and how many in positions 1-3)

### Backlink Profile Health

Pull top referring domains (sorted by DR). Lite cap: 100 rows max.

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/refdomains?target=${DOMAIN}&date=$(date +%Y-%m-%d)&select=domain,domain_rating,backlinks,first_seen,last_visited&limit=50&order_by=domain_rating:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

Assess:
- Quality distribution (how many DR 50+ referring domains?)
- Any toxic or spammy patterns
- Diversity of referring domain types (blogs, news, directories, forums)
- Comparison to competitor backlink profiles

### Organic Keyword Portfolio

Pull top 100 organic keywords (Lite max per request):

```bash
curl -s "https://api.ahrefs.com/v3/site-explorer/organic-keywords?target=${DOMAIN}&date=$(date +%Y-%m-%d)&country=us&select=keyword,best_position,volume,sum_traffic,keyword_difficulty&limit=100&order_by=sum_traffic:desc" \
  -H "Authorization: Bearer $AHREFS_API_KEY"
```

Analyze:
- **Position distribution:** How many keywords in positions 1-3, 4-10, 11-20, 21-50?
- **Quick wins:** Keywords ranking 5-20 with decent volume (candidates for optimization)
- **Keyword cannibalization:** Multiple pages ranking for the same keyword
- **Brand vs non-brand split:** How dependent on branded search?

### Competitor Gap

**No Content Gap API endpoint exists.** Two approaches:

**Option A (API):** Pull organic keywords for the client and each competitor, then diff programmatically. Costs ~500 units per domain (see `references/ahrefs-integration.md` for the full procedure).

**Option B (UI — preferred for deeper analysis):** Run Content Gap in the Ahrefs UI, export the CSV, and save to `tracking/ahrefs/content-gap-YYYY-MM.csv`. This uses UI credits instead of API units.

Flag:
- High-volume keywords competitors own that the client is missing
- Topics where competitors have content and the client has none
- Feed these into content strategy recommendations

### API Cost for a Full SEO Audit

~3,000-4,000 API units depending on competitor count. With 100,000 units/month, this is a small fraction. See `references/ahrefs-integration.md` for the full credit breakdown.

---

## Content Quality Assessment

### E-E-A-T Signals

**Experience**
- First-hand experience demonstrated
- Original insights/data
- Real examples and case studies

**Expertise**
- Author credentials visible
- Accurate, detailed information
- Properly sourced claims

**Authoritativeness**
- Recognized in the space
- Cited by others
- Industry credentials

**Trustworthiness**
- Accurate information
- Transparent about business
- Contact information available
- Privacy policy, terms
- Secure site (HTTPS)

### Content Depth

- Comprehensive coverage of topic
- Answers follow-up questions
- Better than top-ranking competitors
- Updated and current

### User Engagement Signals

- Time on page
- Bounce rate in context
- Pages per session
- Return visits

---

## Common Issues by Site Type

### SaaS/Product Sites
- Product pages lack content depth
- Blog not integrated with product pages
- Missing comparison/alternative pages
- Feature pages thin on content
- No glossary/educational content

### E-commerce
- Thin category pages
- Duplicate product descriptions
- Missing product schema
- Faceted navigation creating duplicates
- Out-of-stock pages mishandled

### Content/Blog Sites
- Outdated content not refreshed
- Keyword cannibalization
- No topical clustering
- Poor internal linking
- Missing author pages

### Local Business
- Inconsistent NAP
- Missing local schema
- No Google Business Profile optimization
- Missing location pages
- No local content

---

## Output Format

### Audit Report Structure

**Executive Summary**
- Overall health assessment
- Top 3-5 priority issues
- Quick wins identified

**Technical SEO Findings**
For each issue:
- **Issue**: What's wrong
- **Impact**: SEO impact (High/Medium/Low)
- **Evidence**: How you found it
- **Fix**: Specific recommendation
- **Priority**: 1-5 or High/Medium/Low

**On-Page SEO Findings**
Same format as above

**Content Findings**
Same format as above

**Prioritized Action Plan**
1. Critical fixes (blocking indexation/ranking)
2. High-impact improvements
3. Quick wins (easy, immediate benefit)
4. Long-term recommendations

---

## References

- [AI Writing Detection](ai-writing-detection.md): Common AI writing patterns to avoid (em dashes, overused phrases, filler words)

---

## Tools Referenced

**Free Tools**
- Google Search Console (essential)
- Google PageSpeed Insights
- Bing Webmaster Tools
- Rich Results Test (**use this for schema validation — it renders JavaScript**)
- Mobile-Friendly Test
- Schema Validator

> **Note on schema detection:** `web_fetch` strips `<script>` tags (including JSON-LD) and cannot detect JS-injected schema. Always use the browser tool, Rich Results Test, or Screaming Frog for schema checks. See the warning at the top of the Audit Framework section.

**Paid Tools**
- **Ahrefs** (Lite plan, API integrated — see `references/ahrefs-integration.md`)
- Screaming Frog
- Sitebulb
- ContentKing

---

## Task-Specific Questions

1. What pages/keywords matter most?
2. Do you have Search Console access?
3. Any recent changes or migrations?
4. Who are your top organic competitors?
5. What's your current organic traffic baseline?

---

## Related Skills

- **ai-cmo**: For overall content strategy and performance tracking
- **content-strategy**: For content planning informed by SEO insights
- **analytics-tracking**: For measuring SEO performance and conversion tracking
- **marketing-psychology**: For on-page persuasion and conversion optimization
