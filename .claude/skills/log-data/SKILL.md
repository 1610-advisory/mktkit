---
name: log-data
description: Append content publishes, performance metrics, or lead/revenue records to a client's tracking CSVs (or the Google Sheets equivalent if the client uses that). Use this skill whenever the user says "log content for [client]", "log this post", "log performance for [client]", "log metrics for [post]", "log lead for [client]", "log a new lead", "log revenue", "log this conversion", "track this post", "add to content log", "update tracking", or any phrase that means "write a row to one of the tracking files." Trigger even without the word "log" — phrasings like "we just published X, record it", "got a new inquiry from LinkedIn", "this post hit 50k views", "Acme Corp closed for $5k" all belong here. Three sub-modes routed by what data the user has: (1) content = new publish, (2) performance = metrics on an existing piece, (3) lead = inquiry or revenue attribution. Supports bulk entries.
metadata:
  version: 1.0.0
---

# Log Data

You are appending a row to one of three tracking files for a client. Confirm the client and the sub-mode (content, performance, lead) before writing anything, then collect the required fields. If something is missing, ask once for the gaps — don't fabricate values.

**Always write to the client's configured storage.** If the client's `CLAUDE.md` declares Google Sheets as the tracking surface, append there instead of the CSV. CSV is the default.

---

## Sub-mode router

| User intent | Sub-mode | File |
|---|---|---|
| "we just published X" / "log content" | **Log Content** | `tracking/content-log.csv` |
| "this post got X views" / "log performance" | **Log Performance** | `tracking/performance.csv` |
| "got a new lead" / "this lead closed" / "log revenue" | **Log Lead** | `tracking/revenue-attribution.csv` |

---

## Sub-mode 1: Log Content

Gather (ask for what's not provided):

- **Platform** — Instagram, LinkedIn, TikTok, X, Facebook, YouTube, etc.
- **Format** — Reel, carousel, static, story, thread, long-form post, blog
- **Title / description** — brief description of the piece
- **URL** — link to the published content, if available
- **Theme / topic** — what it's about
- **Hook used** — opening line or visual concept
- **CTA type** — follow, comment, DM, link click, save, share, none
- **Created by** — who made it
- **Date published** — defaults to today if unspecified
- **Status** — published, scheduled, draft

**CSV schema:**

```csv
content_id,date_published,platform,format,title_description,content_url,theme_topic,hook_used,cta_type,created_by,status,notes
```

**Content ID format:** `[CLIENT-PREFIX]-[YYYYMMDD]-[SEQ]` — e.g., `AC-20260215-01` for a fictional Acme Corp. Pull the client's prefix from their `CLAUDE.md`; if none exists, propose one and ask the user to confirm.

**Content note linkage:** if a content note exists under `outputs/content/` with a matching `content_id`, flip its `status:` frontmatter to `published` and append a Revision History entry. This keeps the Kanban in sync with reality.

**Bulk mode:** if the user supplies a table or list of multiple pieces, parse all rows and append in a single write. Confirm the parsed list back to the user before committing.

---

## Sub-mode 2: Log Performance

Gather:

- **Content ID** — reference from `content-log.csv`, or identify by description + date if the user doesn't have the ID handy
- **Date measured** — defaults to today
- **Views** — total view count
- **Reach** — unique accounts reached
- **Likes**, **Comments**, **Shares**, **Saves**
- **Link clicks** — if applicable
- **New follows** — followers gained from this piece, if trackable
- **Notes** — context ("went viral from hashtag X", "boosted post", etc.)

**CSV schema:**

```csv
content_id,date_measured,views,reach,likes,comments,shares,saves,link_clicks,follows,engagement_rate,performance_score,notes
```

**Engagement rate (calculate before appending):**

```
(Likes + Comments + Shares + Saves) / Reach × 100
```

**Performance score (1–10):**
- 1–3: below average for this client
- 4–6: average — meeting expectations
- 7–8: above average — outperforming typical content
- 9–10: exceptional / viral

Score relative to the client's historical average if you have one. If not, use industry benchmarks: IG 1–3% avg / 6%+ excellent, LinkedIn 2–4% / 8%+, X 0.5–1% / 3%+.

**Tracking cadence guideline:** log performance ~7 days after publishing for most content. For time-sensitive content (trending topics, events), log at 24–48 hours instead.

---

## Sub-mode 3: Log Lead

Gather:

- **Lead name** — who reached out
- **Lead date** — first contact, defaults to today
- **Source** — Social DM, comment, website form, referral, Google, event, etc.
- **Platform** — Instagram, LinkedIn, etc., if social
- **Content ID** — which piece drove the lead, if known
- **First touch** — first content interaction, if trackable
- **Last touch** — most recent interaction before converting
- **How they described finding you** — in their own words
- **Lead status** — New, Contacted, Quoted, Won, Lost
- **Project type** — what they're inquiring about
- **Close date** — if Won/Lost, when it closed
- **Revenue** — if Won, the deal value
- **Notes** — additional context

**CSV schema:**

```csv
lead_id,lead_date,lead_name,lead_source,platform,content_id,first_touch,last_touch,lead_status,close_date,project_type,revenue,notes
```

**Lead ID format:** `[CLIENT-PREFIX]-L-[YYYYMMDD]-[SEQ]` — the `L-` segment distinguishes leads from content IDs.

---

## Attribution model reminder

When the data feeds into a revenue report later, three models apply:

- **First touch** — credit to the first content the lead interacted with. Good for understanding what attracts new audience.
- **Last touch** — credit to the final piece before converting. Good for understanding what drives action.
- **Multi-touch** — distributes credit across touchpoints. Most accurate but needs more data.

Default to first + last touch unless the client has enough volume for multi-touch.

---

## What this skill does not do

- Does not analyze the data. For "what's working" / "revenue report" / "performance analysis," use the `analyze-performance` skill.
- Does not create content notes. For new content planning, use `/generate-week` or `/generate-biweekly`.
- Does not invent values. If a field is unknown, ask the user or leave it blank — never fabricate metrics.
