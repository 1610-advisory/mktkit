# 1610 Marketing Toolkit Quick Reference

Copy-paste these prompts into Claude Code. Replace `[bracketed items]` with your info.

---

## Getting Started

Open Claude Code in the repo root directory. Claude will automatically read `CLAUDE.md` and understand the system.

---

## Available Actions

| Action                 | Command                             | When to Use                                     |
| ---------------------- | ----------------------------------- | ----------------------------------------------- |
| Onboard new client     | `new client [name]`                 | Starting with a new client                      |
| **Brief me on client** | `brief me on [client]`              | Learn what's set up, onboard team members       |
| **Monthly planning**   | `monthly plan for [client]`         | Start of each month - strategic overview        |
| Weekly planning        | `weekly plan for [client]`          | Monday planning sessions                        |
| Analyze performance    | `analyze performance for [client]`  | Monthly reviews                                 |
| Update insights        | `update whats working for [client]` | After performance analysis                      |
| Update strategy        | `update strategy for [client]`      | Changing content mix, goals, voice, preferences |
| Revenue report         | `revenue report for [client]`       | Proving ROI, monthly/quarterly                  |
| Log content            | `log content for [client]`          | After scheduling posts                          |
| Log metrics            | `log performance for [client]`      | 7 days after posting                            |
| Log lead               | `log lead for [client]`             | When new lead comes in                          |

---

## 1. New Client Onboarding

**When:** Starting work with a new client

**Prompt:**
```
new client [client-name]

Industry: [industry]
Location: [city, state]
Website: [url]

Walk me through the onboarding process.
```

Claude will:
1. Create the client folder structure
2. Ask discovery questions one section at a time
3. Fill in knowledge files as you answer
4. Generate the client's CLAUDE.md file at the root

---

## 2. Brief Me On Client

**When:** Learning what's set up for a client, onboarding team members, refreshing your memory, or asking questions about strategy

**Prompt:**
```
brief me on [client]
```

Claude will read all knowledge files and provide a summary of:
- Company overview and positioning
- Target audience segments
- Brand voice and messaging
- Current goals and KPIs
- Content mix and what's working
- Current priorities

**Follow-up questions:**
After the initial brief, you can ask follow-up questions conversationally:

```
What's their content mix?
Who are their target personas?
What hooks work best for them?
What's their posting schedule?
How do they handle the pricing objection?
What vendors do they work with?
```

Claude will reference the knowledge files to answer without making changes.

---

## 3. Monthly Planning

**When:** Start of each month (last week of previous month or first few days)

**Prompt:**
```
monthly plan for [client]

Month: [Month Year]
Priority themes: [any specific focus areas]
Upcoming events/dates: [holidays, launches, seasonal events]
Tests from last month: [what we learned]
```

Claude will:
1. Review all knowledge files and recent performance
2. Generate a month-level strategic plan including:
   - Monthly theme and objectives
   - 4-week breakdown with themes and content types
   - Content mix recommendations (formats, quantities)
   - Hypotheses to test each week
   - Production planning overview
   - Key metrics to track
3. Save to `outputs/monthly-briefs/`

**Monthly plan sets the strategy, weekly plans drill into specifics.**

---

## 4. Weekly Planning

**When:** Monday planning sessions

**Prompt:**
```
weekly plan for [client]

Week of: [date]
Last week's notes: [any context, or "none"]
Current priority: [what we're focused on]
Upcoming dates: [any relevant dates this week]
```

Claude will:
1. Check for current monthly plan in `outputs/monthly-briefs/` (aligns weekly with monthly strategy)
2. Review all knowledge files
3. Check what's working
4. Generate 5 content pieces with:
   - Platform, format, topic, hook, CTA
   - Video scripts (if applicable)
   - Combined shot list
   - Caption starting points
5. Save to `outputs/weekly-briefs/`

**Note:** Weekly plans automatically align with the monthly plan when one exists.

---

## 5. Performance Analysis

**When:** Monthly reviews, investigating patterns

**Prompt:**
```
analyze performance for [client]

Period: [last 30 days / last quarter / specific dates]
Focus: [any specific questions, or "general analysis"]
```

Claude will:
1. Analyze all tracking CSVs
2. Identify top performers and patterns
3. Provide specific recommendations
4. Propose updates to whats-working.md

---

## 6. Update What's Working

**When:** After performance analysis, after a big win or loss

**Prompt:**
```
update whats working for [client]

Recent wins: [any standout content]
Recent misses: [anything that flopped]
```

Claude will:
1. Review recent performance data
2. Update the whats-working.md file
3. Archive outdated insights
4. Propose new tests

---

## 7. Update Strategy

**When:** Changing client preferences, content mix, posting cadence, goals, voice, or other strategic elements

**Prompt:**
```
update strategy for [client]

Change: [describe what you want to update]
```

**Examples:**
```
update strategy for your-client

Change: Add monthly partner highlight posts - feature one vendor/partner company per month as a carousel
```

```
update strategy for your-client

Change: Update content mix to include 2 blog posts per month (1 educational, 1 partner-focused) repurposed as carousels
```

```
update strategy for your-client

Change: Shift primary audience focus from roofing to custom homes and large remodels
```

Claude will:
1. Identify which knowledge file(s) need updating (voice-guidelines.md, goals-and-benchmarks.md, whats-working.md, etc.)
2. Read the current state of those files
3. Make the appropriate updates
4. Confirm changes made and which files were modified

**Common updates:**
- Content mix / posting cadence
- New content types or formats
- Goal changes or KPI updates
- Voice/tone adjustments
- Audience segment priorities
- Campaign themes
- Partner/vendor relationships

---

## 8. Revenue Report

**When:** Proving ROI, monthly/quarterly reviews

**Prompt:**
```
revenue report for [client]

Period: [date range]
Include: [any specific metrics to highlight]
```

Claude will:
1. Analyze revenue-attribution.csv
2. Calculate ROI by platform and content type
3. Identify highest-converting patterns
4. Create a shareable report

---

## Quick Logging

### Log Content (after scheduling)

```
log content for [client]

Platform: [Instagram/LinkedIn/TikTok/etc]
Format: [Reel/Carousel/Static/Story]
Title: [brief description]
URL: [link, if published]
Theme: [topic/campaign]
Hook: [opening line or visual]
CTA: [what we asked them to do]
Posted by: [name]
```

### Log Performance (7 days after posting)

```
log performance for [client]

Content ID: [from content-log, e.g., IG-20250105-01]
Views: [number]
Reach: [number]
Likes: [number]
Comments: [number]
Shares: [number]
Saves: [number]
Link clicks: [number]
New follows: [number]
Notes: [any context]
```

### Log Lead (when lead comes in)

```
log lead for [client]

Name: [lead name/company]
Date: [when they reached out]
Source: [Social DM/Comment/Website/Phone/Referral]
Platform: [if social, which one]
Content: [which piece led them here, if known]
How they found us: [their words]
Status: [New/Contacted/Quoted/Won/Lost]
Project type: [what they need]
Est. value: [if known]
```

---

## Working on a Specific Client

To focus Claude on a specific client:

```
I'm working on [client] today. Read their knowledge base and confirm you're ready.
```

Or just start with any command:
```
weekly plan for [client]
```

Claude will automatically read that client's `CLAUDE.md` and all relevant files.

---

## Bulk Operations

### Log multiple content pieces:
```
log content for [client]

Piece 1:
- Platform: Instagram
- Format: Reel
- Title: [description]
- Theme: [topic]
- Hook: [hook]
- CTA: [cta]

Piece 2:
- Platform: Instagram
- Format: Carousel
[etc.]
```

### Log performance for multiple pieces:
```
log performance for [client]

IG-20250105-01: 1200 views, 890 reach, 45 likes, 12 comments, 3 shares, 28 saves
IG-20250105-02: 3400 views, 2100 reach, 89 likes, 23 comments, 8 shares, 67 saves
[etc.]
```

---

## Integrations

The toolkit can connect to external services. All are optional and configured per-client.

| Integration | What It Does | Setup Required |
|-------------|--------------|----------------|
| **Google Drive** | Store and organize deliverables in shared folders | Drive folder ID in client config |
| **Google Docs** | Create/update briefs and plans as collaborative Google Docs | None (available via MCP) |
| **Google Sheets** | Track content, performance, and revenue in shared spreadsheets (alternative to local CSVs) | Spreadsheet ID in client config |
| **Google Slides** | Generate client presentations, strategy decks, quarterly reviews | None (available via MCP) |
| **Typefully** | Create draft social posts for X and LinkedIn | API key as env var + `typefully-config.md` per client |

See the main `CLAUDE.md` (at project root) for full integration details.

---

## Tips

1. **Be in the right directory** - Claude reads `CLAUDE.md` from your current location (at project or client root)
2. **Client names are folder names** - Use the exact folder name (e.g., `acme-corp` not "Acme Corp")
3. **More context = better output** - Add notes about what's happening when you run weekly planning
4. **Review before accepting** - Claude will often propose changes; review them before confirming
5. **Keep tracking current** - The system works best with recent data in the CSVs

---

## Weekly Workflow

| Day | Action | Prompt |
|-----|--------|--------|
| Monday AM | Review last week | `analyze performance for [client]` |
| Monday PM | Plan this week | `weekly plan for [client]` |
| Tuesday | Prep content | [Manual - review briefs] |
| Wed-Thu | Shoot content | [Manual - use shot list] |
| Friday | Edit + schedule | [Manual] |
| Friday | Log content | `log content for [client]` (for each piece) |
| Following week | Log performance | `log performance for [client]` |

---

## Monthly Workflow

| Task | When | Prompt |
|------|------|--------|
| **Generate monthly plan** | Last week of month or 1st | `monthly plan for [client]` |
| Full performance review | End of month | `analyze performance for [client]` with period: last 30 days |
| Update insights | After review | `update whats working for [client]` |
| Revenue check | End of month | `revenue report for [client]` |
| Goal review | End of month | Review `knowledge/goals-and-benchmarks.md` manually |

### Monthly Planning Flow
1. **End of Month:** Review last month's performance
2. **Update Insights:** Run `update whats working for [client]`
3. **Generate Next Month's Plan:** Run `monthly plan for [client]`
4. **Each Week:** Run `weekly plan for [client]` (aligns with monthly plan)

---

## Troubleshooting

**Claude doesn't know the client:**
- Make sure you're in the repo root directory
- Use the exact folder name from `clients/`

**Output is too generic:**
- Add more context to your prompt
- Make sure knowledge files are filled in
- Run `update whats working` if you have performance data

**Need to correct something:**
- Just tell Claude: "Actually, update that to [correction]"
- Or: "Edit [file] to change [x] to [y]"
