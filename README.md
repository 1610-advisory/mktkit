# 1610 Marketing Toolkit (`mktkit`)

Your AI marketing strategist. Clone it, open it in Claude Code, start talking.

The 1610 Marketing Toolkit is a strategic marketing advisor that acts as an AI Chief Marketing Officer for your clients — managing content strategy, planning, and performance tracking across all of them. It directs strategy — it doesn't create final content. You get data-driven content plans, brand voice guidelines, performance tracking, and an operational memory that gets smarter over time.

## Quick Start

```bash
git clone https://github.com/1610-advisory/mktkit.git
cd mktkit
```

Open the folder in [Claude Code](https://claude.ai/claude-code) (CLI, desktop app, or IDE extension). Then just say:

```
new client my-business
```

This runs a guided ~20 minute interview that builds your complete marketing profile. You'll leave with your first monthly and weekly content plans ready to execute.

### Or install it as a plugin

The repo is also a plugin marketplace, so the skills work in any folder.

In Claude Code:

```
/plugin marketplace add 1610-advisory/mktkit
/plugin install ai-cmo@mktkit
```

In the Claude Desktop app, no terminal needed: open **Customize → Plugins**, add the marketplace `1610-advisory/mktkit`, then install **ai-cmo**. Planning, drafting, logging, and analysis skills work there. The media pipeline (transcription, reel cutting, carousel rendering) needs a local Mac with the tools below, so run those from Claude Code.

**Requirements:** Claude Code or Claude Desktop with a Claude Pro or Max plan.

**Requirements for the media pipeline:** `ffmpeg` and `ffprobe` on PATH, Python 3.11+. Optional: Playwright for `carousel-slides` PNG export; whisper (`mlx-whisper`) for shoot transcription.

## How It Works

The toolkit is conversational, not transactional. You don't need to memorize commands or invoke workflows in a specific order. Just talk to it like a colleague:

- "What should we post this week?"
- "How are we doing on Instagram?"
- "I just got back from a shoot, footage is on the drive"
- "The kitchen project is done — we need a reveal post"

The agent recognizes what you're saying, reads the right knowledge files, runs the right workflows, and suggests the next step. Workflows chain naturally — a shoot leads to organizing, which leads to a content review, which leads to editing priorities.

## What You Get After Setup

- **Brand voice guidelines** extracted from your actual writing
- **Customer personas** using the StoryBrand framework
- **Monthly content strategies** with 4-week breakdowns and experiments
- **Bi-weekly execution plans** with performance data pulls and platform research
- **Weekly content plans** with hooks, scripts, shot lists, and caption direction
- **Performance tracking** that feeds back into smarter plans
- **Operational memory** that persists decisions and context across sessions
- **Content asset index** tracking footage across any number of storage locations

## Available Workflows

These are available as slash commands and as natural language triggers:

| What You Say | What Happens |
|-------------|-------------|
| "brief me on [client]" | Structured strategy summary + conversational Q&A |
| "monthly plan for [client]" | Month-level strategy with weekly themes |
| "biweekly plan for [client]" | Two-week execution plan with performance data |
| "weekly plan for [client]" | Specific content pieces with scripts and captions |
| "analyze performance" | Pattern identification from tracking data |
| "update whats working" | Refresh performance insights |
| "I just got back from a shoot" | Process and organize footage, then review for content ideas |
| "where's the footage for [project]?" | Check the content asset index |
| "new client [name]" | Guided onboarding interview |
| "update strategy" | Change goals, voice, content mix, or other strategy elements |
| "log content / performance / lead" | Quick data entry |
| "you're the AI CMO" / session start | Load the knowledge pack (`mkt-kit`) |
| "cut this reel" / "cut the next N" | Talking-head reel from brief + transcript (`cut-video`) |
| "QA this reel" | Machine gate on a vertical short (`reel-qa`) |
| "edit it in Resolve" / "grade it" / "show me LUT options" | Resolve-built reel: DWG/DI grade, look LUTs, look-review page (`resolve-reel`) |
| "find B-roll for this line" | Index/search library stills and clips (`reel-broll`) |
| "ingest footage" / after a shoot | Compiled footage catalog (`footage-index`) |
| "film board" | 9:16 talk-over HTML board (`film-board`) |
| "draft a blog from this video" | Search-cluster blog from transcript (`draft-cluster-blog`) |
| "render this as HTML" | Brand-themed HTML report (`branded-report`) |

## Reference Library

In addition to the core workflows, the toolkit includes specialized marketing knowledge that it pulls from when relevant:

| Reference | What's In It |
|-----------|-------------|
| **Marketing Psychology** | 70+ mental models for hooks, CTAs, messaging, and pricing |
| **Content Strategy** | Topic clusters, buyer journey mapping, content prioritization |
| **Email Sequences** | Drip campaigns, lifecycle automation, copy guidelines |
| **SEO Audit** | 7-dimension technical SEO audit framework |
| **Analytics Tracking** | GA4, GTM, event tracking, UTM frameworks |
| **Copywriting Frameworks** | Shared copy structure before client voice is applied |
| **Search Cluster Blog Ranking** | Ranking factors for transcript-grounded cluster posts |
| **AI Visibility Audit** | How assistants cite (or ignore) the site |
| **Branded HTML Reports** | Self-contained HTML deliverable + optional BYO host |
| **Platform Backfill** | Revive a dormant social catalog without looking automated |
| **Newsletter Pipeline** | Segmented, tape-grounded newsletters, a copy linter (`scripts/lint-copy.py`), and a pipeline scaffolder (`scripts/scaffold-pipeline.py`) |

## Client Folder Structure

Each client gets an isolated folder:

```
clients/your-client/
├── CLAUDE.md                 # Client-specific instructions and context
├── knowledge/                # Strategy documents (voice, personas, goals, what's working)
├── tracking/                 # CSVs and content indexes
├── content/                  # Published content + competitors
├── transcripts/              # Call recordings, interviews
├── memory/                   # Operational memory across sessions
│   ├── MEMORY.md             # Curated summaries
│   └── logs/                 # Daily session logs
└── outputs/                  # Generated plans, briefs, and content notes
```

Client data stays local — it's never tracked by git.

## Weekly Workflow

| When | What | Time |
|------|------|------|
| Monday | Log metrics, generate weekly plan | 30-45 min |
| Tue-Thu | Create and publish content | Your pace |
| Friday | Log content, quick metrics check | 15 min |
| Monthly | Review performance, generate next month's strategy | 30 min |

## Optional Integrations

| Integration | What It Does |
|-------------|-------------|
| **Typefully** | Draft social posts for X + LinkedIn |
| **Google Drive/Sheets/Docs** | Collaborative tracking and deliverables |
| **GA4 / Search Console** | Website analytics and search data |
| **HubSpot** | CRM and lead pipeline management |

All integrations are optional. The system works fully with local markdown and CSV files.

## Recommended: Humanizer

The 1610 Marketing Toolkit directs strategy — when you need Claude to write or polish copy, pair it with [Humanizer](https://github.com/blader/humanizer). It strips common AI writing patterns so your captions and scripts sound like a person wrote them.

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Open a pull request against `main`

## Credits

The marketing skills (email-sequence, content-strategy, marketing-psychology, seo-audit, analytics-tracking) are adapted from [marketingskills](https://github.com/coreyhaines31/marketingskills) by [Corey Haines](https://corey.co). Licensed under MIT.

## License

MIT
