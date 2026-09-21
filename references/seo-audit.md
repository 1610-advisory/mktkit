
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

### ⚠️ Important: The Collapsed-Content Trap

**Content inside accordions, tabs, "read more" toggles and modals is frequently absent from the served HTML entirely — not hidden, absent.**

Most headless UI libraries (Radix, Headless UI, Reach and the components built on them) do not render the content of a *closed* panel at all. It never enters the server-rendered HTML. The page looks complete to a human, who clicks and sees the text appear, while a crawler is served only the headings.

This is invisible to standard site auditors, which report the page as healthy: the status code is 200, the title and meta are fine, there are no broken links. Nothing in a crawl report says "most of this page's body copy does not exist."

**FAQ sections are the usual casualty**, which is expensive twice over — that content is both the most likely to earn a featured snippet and the most likely to be quoted by an assistant.

**The compounding failure:** the page often *also* ships `FAQPage` structured data declaring every question and answer. That puts it in breach of Google's requirement that FAQ content be visible on the page, because the schema asserts answers the HTML never contained.

**How to check:**

```bash
curl -s https://example.com/faq | python3 -c "
import sys, re
h = sys.stdin.read()
s = re.sub(r'<script.*?</script>', '', h, flags=re.S)   # drop hydration payload + JSON-LD
s = re.sub(r'<[^>]+>', ' ', s)
print('visible words:', len(s.split()))
print('answer present:', 'a distinctive phrase from an answer' in s)
"
```

If a known answer string appears in the file **only** inside `<script>` tags, it does not count — that is the hydration payload, not rendered content.

**Check once per template**, not just the FAQ page: the same component usually appears on service pages and homepage sections too.

**The fix** is to force the content to mount and hide the closed state with CSS instead of unmounting it (in Radix, `forceMount` plus a `data-[state=closed]:hidden` class). It is typically a few lines in one shared component and can recover thousands of words across a site. Leave a comment explaining why, or the next person will "clean it up."

### ⚠️ Verify before you conclude — fetch the URL, don't infer it

Audit data tells you what *was* true when it was collected. It does not tell you what the site does right now.

Search Console in particular reports on a lag and keeps showing old URLs through a migration, so a report full of legacy paths reads like a site full of dead links when those paths may redirect perfectly. **Deciding a URL is broken because it appears in an export, without requesting it, produces confident wrong findings** — and a remediation plan aimed at a problem that does not exist.

Rule: **every claim about what a URL returns must be backed by a request you actually made.** One `curl` per claim. Where a finding rests on inference rather than a check, label it as inference in the report.

The same applies to agent- or subagent-produced findings: treat them as claims to verify, not results. A subagent auditing a site mid-deploy will report a page as missing that is live a minute later.

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

**Post-Migration Redirect Audit**

After any replatform or redesign, audit the *old* URL inventory against the live site directly.
Redirect maps written during a migration are frequently built against **guessed** old URLs rather
than the real ones, and the gap does not surface until link equity has already been dropping into
404s for weeks.

Get the real inventory from the old sitemap, an archive crawl, the analytics platform's historical
page report, and Search Console — then request every one of them:

```bash
while read -r u; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-redirs 5 "https://example.com$u")
  echo "$code $u"
done < old-urls.txt | sort | uniq -c
```

Things this catches that a redirect map review does not:

- **Nested vs flat paths.** A silo like `/category/service-name` guessed as `/service-name` produces
  redirects that match nothing. Both forms sometimes existed; check rather than assume.
- **Duplicate addresses for one article.** Legacy CMSs often exposed the same post at a dated path,
  a bare slug, and a category path. Each is a separate URL that needs its own rule.
- **Trailing-slash handling.** Many frameworks normalise `/x/` to `/x` *before* redirects run, in
  which case listing both forms is redundant. Verify which way the framework behaves instead of
  doubling every rule.
- **Redirect ordering.** Where rules are evaluated first-match-wins, specific rules (pagination,
  individual pages) must precede wildcard or catch-all rules. Test a URL from each group.

**Set a target and re-measure.** State the expected dead count after the fix, including the URLs
that should *stay* 404 by design — internal tooling, ops pages, legacy CMS attack surface — and
re-run the loop to confirm. "Dead count went from N to the expected M" is a verifiable claim;
"redirects added" is not.

**Redirecting many URLs to one empty page is a soft-404 pattern.** Pointing a legacy blog archive
at an index page with no posts on it means the equity is discarded rather than passed. Either
populate the destination or redirect to the closest genuinely relevant page.

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

## Reading Search Console Before Prescribing

Three misreadings produce confident, wrong recommendations often enough to be worth naming. Each
has cost real audit credibility.

### Low CTR at a low average position is not a titles problem

The instinct on seeing a poor click-through rate is to rewrite titles and meta descriptions. Check
the average position first.

Expected CTR falls off a cliff with position. At an average position in the mid-20s, roughly page
three, an expected CTR is a fraction of a percent — so a site sitting at, say, 1.8% is *out*-performing
its position, not underperforming. Rewriting those titles wins nothing, because almost nobody is
seeing them.

**Titles are a lever around positions 5–10, where a better snippet wins the click from a neighbour.
They are not a lever at position 25.** At position 25 the problem is position. Fix ranking first,
then revisit titles once the impressions are actually being seen.

### Page-1 rankings with zero clicks usually means SERP features, not a bad page

When a query shows a strong average position — top ten, sometimes top three — and produces no
clicks at meaningful impression volume, the likely cause is that organic results are pushed below
the fold by a map pack, ads, an AI overview, or a "people also ask" block.

This is especially pronounced on "near me" and bare-category queries in local search, where the map
pack plus ads can occupy the entire first screen.

**Consequence for the audit: this is not a website finding.** No amount of on-page work converts
these impressions. The fix lives in the business profile, review volume and category selection.
Say so explicitly, because otherwise the reader assumes the page is at fault and spends effort in
the wrong place.

**Diagnostic:** a cluster of queries at position ≤10 with a near-zero click rate, while brand
queries at similar positions convert normally, is close to conclusive.

### Distinguish brand from non-brand before quoting any headline metric

Split the query export into branded and non-branded and compute the metrics separately. The
combined numbers are almost always flattering and almost always useless: brand queries convert at a
high rate and drag the average CTR up, hiding a non-brand click rate that may be near zero.

The split is usually the single most clarifying table in the report — it reframes "we get some
search traffic" as "we are found by people who already know the name, and by nobody else."

Also strip geographically irrelevant impressions (same-name places elsewhere, similar business
names) before drawing conclusions — but **check whether removing them actually changes the
picture** rather than assuming it does. Frequently it does not, and reporting the check is more
credible than reporting the assumption.

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
- **Duplicate business profiles** — splits reviews and ranking signals between two listings so
  neither performs as well as one would. Also a common way a private address ends up public. Only
  the profile owner can merge them, so this is an ask, not a task.
- **Absent from the aggregator layer** — for trades and local services, assistants (and many
  searchers) answer "best X in [city]" from directories and listicles, not from the business's own
  site. Check whether the client appears at all. See `ai-visibility-audit.md`.

**The page-count problem, specifically.** Small local service sites plateau because they have too
few pages, not because the pages are too short. A site with a handful of service pages will see the
homepage absorb the large majority of impressions, because nothing else targets the category.

Before recommending "longer content," check the actual distribution:

- **Word count against page-1 competitors.** Frequently the client's pages are already inside the
  competitive band, and length is not the constraint.
- **Page count against page-1 competitors.** This is usually where the gap is, and it is often
  large — a competitor ranking on a weak domain with no reviews but several times the page count is
  a common and instructive finding.
- **Multi-service pages.** One page covering several distinct services tends to rank worse than a
  single-topic page, while attracting the most impressions — it is simultaneously the biggest
  opportunity and the worst performer. Splitting it into dedicated pages is usually a
  split-and-expand of copy that already exists, not new writing.
- **Demand with no matching page.** Cross-reference the query export against the sitemap. Query
  clusters with real impressions and no page targeting them are the highest-confidence page ideas
  available, because the demand is already measured.

**On location pages: build few, and build them real.** Competitor location pages are often spun
boilerplate — verify by comparing two of them and counting genuinely unique words. Prioritise towns
with measured demand *and* no competitor page; skip the saturated ones and any that belong to a
different metro. Four honest pages outperform twenty templated ones and carry none of the
thin-content risk.

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
- **ai-visibility-audit**: Answer-engine / GEO visibility — whether assistants can find, parse and
  recommend the business. Run alongside this audit; they overlap less than expected, and for local
  service businesses the binding constraint is often there rather than here.
- **content-strategy**: For content planning informed by SEO insights
- **analytics-tracking**: For measuring SEO performance and conversion tracking
- **marketing-psychology**: For on-page persuasion and conversion optimization
