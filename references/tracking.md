# Data Tracking Procedures

How to log content, performance metrics, and leads/revenue attribution.

## Log Content

When the user says "log content for [client]":

Gather this information (ask for anything not provided):
- **Platform:** Instagram, LinkedIn, TikTok, X, Facebook, YouTube, etc.
- **Format:** Reel, carousel, static image, story, thread, long-form post, blog, etc.
- **Title/description:** Brief description of the content
- **URL:** Link to the published content (if available)
- **Theme/topic:** What the content is about
- **Hook used:** The opening line or visual concept
- **CTA type:** What action was requested (follow, comment, DM, link click, save, share, none)
- **Created by:** Who made this content
- **Date published:** When it went live (default to today if not specified)
- **Status:** Published, scheduled, draft

Then append a row to `tracking/content-log.csv`:

```csv
content_id,date_published,platform,format,title_description,content_url,theme_topic,hook_used,cta_type,created_by,status,notes
```

**Content ID format:** `[CLIENT-PREFIX]-[YYYYMMDD]-[SEQ]` (e.g., `AC-20260215-01` for Acme Corp)

**Content note linkage:** If a content note exists in `outputs/content/` with a matching `content_id`, update its `status` to `published` and append to its `## Revision History` when logging.

If the client uses Google Sheets instead of CSV, append to the configured spreadsheet.

### Bulk Content Logging

If the user wants to log multiple pieces at once, gather all entries and append them in a single operation. You can also accept data in a table format and parse it into CSV rows.

---

## Log Performance

When the user says "log performance for [client]":

Gather this information:
- **Content ID:** Reference from content-log (or identify by description/date)
- **Date measured:** When metrics were captured (default to today)
- **Views:** Total view count
- **Reach:** Unique accounts reached
- **Likes:** Like/heart count
- **Comments:** Comment count
- **Shares:** Share/repost count
- **Saves:** Save/bookmark count
- **Link clicks:** Click-through count (if applicable)
- **New follows:** Followers gained from this content (if trackable)
- **Notes:** Any context (e.g., "went viral from hashtag", "boosted post")

Then calculate and append to `tracking/performance.csv`:

```csv
content_id,date_measured,views,reach,likes,comments,shares,saves,link_clicks,follows,engagement_rate,performance_score,notes
```

**Engagement Rate calculation:**
```
(Likes + Comments + Shares + Saves) / Reach × 100
```

**Performance Score guidelines:**
- 1-3: Below average for this client's typical content
- 4-6: Average — meeting expectations
- 7-8: Above average — outperforming typical content
- 9-10: Exceptional — viral or significantly outperforming

Assign the performance score based on the engagement rate relative to the client's historical average. If there's no history yet, use industry benchmarks:
- Instagram: 1-3% is average, 3-6% is good, 6%+ is excellent
- LinkedIn: 2-4% is average, 4-8% is good, 8%+ is excellent
- X/Twitter: 0.5-1% is average, 1-3% is good, 3%+ is excellent

### Tracking Timing

Log performance metrics 7 days after publishing for most content. For time-sensitive content (trending topics, event coverage), log at 24-48 hours instead.

---

## Log Lead

When the user says "log lead for [client]":

Gather this information:
- **Lead name:** Who reached out
- **Lead date:** When they first contacted (default to today)
- **Source:** How they found the client (Social DM, comment, website form, referral, Google, event, etc.)
- **Platform:** Which platform if social (Instagram, LinkedIn, etc.)
- **Content ID:** Which content piece drove this lead (if known, reference from content-log)
- **First touch:** First content interaction (if trackable)
- **Last touch:** Most recent content interaction before converting
- **How they described finding you:** In their own words
- **Lead status:** New, Contacted, Quoted, Won, Lost
- **Project type:** What they're inquiring about
- **Close date:** If won/lost, when it closed
- **Revenue:** If won, the deal value
- **Notes:** Any additional context

Append to `tracking/revenue-attribution.csv`:

```csv
lead_id,lead_date,lead_name,lead_source,platform,content_id,first_touch,last_touch,lead_status,close_date,project_type,revenue,notes
```

**Lead ID format:** `[CLIENT-PREFIX]-L-[YYYYMMDD]-[SEQ]` (e.g., `CP-L-20260215-01`)

### Attribution Models

When analyzing revenue data, three attribution models are useful:

- **First Touch:** Credit goes to the first content the lead interacted with. Useful for understanding what attracts new audience.
- **Last Touch:** Credit goes to the content they engaged with right before converting. Useful for understanding what drives action.
- **Multi-Touch:** Distribute credit across all touchpoints. Most accurate but requires more tracking data.

Default to first-touch and last-touch unless the client has enough data for multi-touch analysis.
