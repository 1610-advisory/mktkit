# 1610 Marketing Toolkit — Agent Reference

Detail layer for `./CLAUDE.md`. Moved here 2026-07-28 for the 10,000-character agent-rules cap (Grok truncates rules files at 10k).
Operating rules live in `CLAUDE.md`; this file holds the tables, walkthroughs, examples, and rationale that `CLAUDE.md` points to.

---

## Folder Structure

```
mktkit/                   # Project root
├── CLAUDE.md                        # System-wide instructions (Obsidian-visible)
├── AGENTS-REFERENCE.md              # This file — detail layer for CLAUDE.md
├── .claude/                         # Claude Code config (hidden from Obsidian)
│   ├── commands/                    # Workflow playbooks (slash commands)
│   ├── skills/                      # Skills
│   └── settings.json                # Claude Code settings
├── references/                      # On-demand knowledge library
├── scripts/                         # Automation scripts
├── templates/                       # Client onboarding templates
├── docs/                            # Setup guides and documentation
├── clients/                         # One folder per client (private, not in git)
│   └── [client-name]/
│       ├── CLAUDE.md                # Client-specific instructions (Obsidian-visible)
│       ├── .claude/                 # Per-client commands/skills/settings (optional, hidden)
│       ├── knowledge/               # Strategy documents with YAML frontmatter
│       ├── tracking/                # CSVs, content index, shoot log
│       ├── content/                 # Published content + competitors
│       ├── transcripts/             # Call recordings, interviews
│       ├── memory/                  # Operational memory (persists across sessions)
│       │   ├── MEMORY.md            # Curated summaries (<200 lines)
│       │   └── logs/                # Daily session logs (YYYY-MM-DD.md)
│       └── outputs/
│           ├── monthly-briefs/
│           ├── weekly-briefs/
│           ├── biweekly-briefs/
│           └── content/             # Atomic content notes (Kanban-trackable)
```

**Why CLAUDE.md lives at the project root, not in `.claude/`:** Claude Code reads `CLAUDE.md` from either location, but Obsidian (the user's primary visualization tool for this vault) hides any folder starting with `.`. Keeping CLAUDE.md at the root makes it visible and editable from Obsidian; `.claude/commands/`, `.claude/skills/`, etc. only load from `.claude/` and stay there as configuration.

---

## Agent Behavior — recognizing intent and chaining

The `.claude/commands/` folder contains detailed workflow playbooks. These are your tools — you reach for them when the conversation calls for it. You don't wait to be told.

**Recognize intent, then act:**
- If the user says "I just got back from a shoot" → you know to ask for the folder path and run the organize-shoot workflow, then transition into the shoot review.
- If they say "what should we post?" → you check for a current brief, pull performance data, and either review the pipeline or suggest generating a new brief.
- If a workflow finishes → you suggest the logical next step, not a dead end.

**Chain workflows naturally:**
```
shoot happens → organize-shoot → shoot-review → editing priorities → scheduling
monthly cycle → monthly plan → biweekly brief → shoot → organize → review → publish → performance pull → next cycle
```

**Suggest proactively:** When you notice something (stale data, a gap in the pipeline, a project reaching a milestone), say so. You're a CMO — you should be thinking ahead of the user, not waiting for instructions.

---

## Delegation Defaults — use small/fast agents and parallel teams by default

Your time and context window are expensive. Most of the work in this system is mechanical: file edits, frontmatter updates, renames, status flips, table rebuilds, transcript ingestion, draft pushes. **Delegate that work to a smaller model — don't do it yourself in the main thread.**

**Default to delegation when the task is:**
- Mechanical or repetitive (rename N files, update frontmatter on N notes, flip status on N pieces, rebuild a table)
- Large in volume but small in judgment (sweep a folder, generate N atomic notes from a brief, batch-edit captions)
- Parallelizable across independent items (process 20 transcripts, draft 10 Typefully posts, log a CSV in chunks)
- Read-heavy research that would bloat your context (scan all client knowledge files, audit a tracking CSV, survey what's in `outputs/`)

**Default model:**
- **Haiku** for mechanical/parallel work — file edits, renames, frontmatter updates, table rewrites, simple file generation from a clear spec. Spawn via the `Agent` tool with `model: "haiku"` and `subagent_type: "general-purpose"`.
- **Sonnet** for work that needs judgment but is still bounded — drafting captions from a transcript, summarizing a long meeting, generating a content note from a concept.
- **Opus (you, the main thread)** stays focused on strategy, voice calibration, decisions, and conversation. You orchestrate; you don't do the busywork.

**Parallel agent teams are the default for any batch operation.** When work splits cleanly across independent items, spawn multiple agents in a single message rather than one agent doing them in series, or — worse — doing them yourself one by one. Examples:
- 20 content notes need frontmatter updated → one Haiku agent (already a batch operation, no need to split further)
- 10 transcripts need ingestion + summarization → split into 2-3 Sonnet agents in parallel
- A new biweekly brief needs 14 atomic content notes generated from a spec → one Sonnet agent with the full spec, not 14 calls

**Brief delegated agents like a colleague who walked into the room cold:** explicit file paths, exact list of files to touch, exact YAML keys to change, what NOT to touch, and a short "report back" so their summary stays out of your context.

**Verify, don't trust the summary.** When an agent reports it touched files, spot-check one or two with `ls`, `grep`, or `Read` before reporting "done" to the user. Agent summaries describe intent, not always reality.

**When NOT to delegate:** strategic recommendations, voice-sensitive copy direction, blog post proofreading, conversational responses to the user, anything that requires the full client context you've built up in this thread.

---

## Command Routing

When a user asks you to do something, match their request to the right workflow. Read the command file before executing — it has the detailed steps.

| User Says | What to Do | Command File |
|-----------|------------|-------------|
| "brief me on [client]" | Read knowledge, summarize, answer questions | Inline (no command file) |
| "monthly plan for [client]" | Generate monthly strategy | `/generate-month` |
| "weekly plan for [client]" | Generate weekly content plan | `/generate-week` |
| "biweekly plan for [client]" | Generate two-week execution plan | `/generate-biweekly` |
| "analyze performance for [client]" | Review data, find patterns | Read `references/analysis.md` |
| "update whats working for [client]" | Refresh performance insights | Read `references/analysis.md` |
| "revenue report for [client]" | Analyze revenue attribution | Read `references/analysis.md` |
| "new client [name]" | Run guided onboarding | `/new-client` |
| "update strategy for [client]" | Update knowledge files | Inline |
| "log content/performance/lead" | Quick data entry | Read `references/tracking.md` |
| "I just got back from a shoot" | Process footage | `/organize-shoot` → `/shoot-review` |
| "where's the footage for [project]?" | Check asset index | `/index-content` |
| "generate week" or "create typefully drafts" | Social drafts | `/generate-week` or `/create-typefully-drafts` |
| "typefully status" | Check draft status | `/typefully-status` |
| "edit / cut this video" (tool not named) | Pick the Resolve or ffmpeg route, recommend with a reason | `references/edit-route.md` → `resolve-reel` or `cut-video` |
| "cut this reel" / "cut the next N" | Talking reel from brief + transcript | `/cut-video` (a queue points to ffmpeg; see `references/edit-route.md`) |
| "cut it in Resolve" / "I want a project I can edit" | Reel or montage built in DaVinci Resolve | `resolve-reel` skill |
| "QA this reel" | Machine QA on a vertical short | `reel-qa` skill |
| "find B-roll for this line" | Index/search library stills and clips | `reel-broll` skill |
| "ingest footage" | Compiled footage catalog | `footage-index` skill |
| "film board" | 9:16 talk-over HTML board | `film-board` skill |
| "draft a blog from this video" | Search-cluster blog from transcript | `draft-cluster-blog` skill |
| "render this as HTML" | Brand-themed HTML report | `branded-report` skill |
| session start / "you're the AI CMO" | Load DESIGN/voice/personas/overview/goals | `mkt-kit` skill |

---

## Per-client repo setup (privacy boundary mechanics)

**Why the push cadence matters:** diff visibility is the point — local commits with no remote backup defeat the purpose.

**Per-client repo convention:**
- Repo name: `[client-slug]-content` (e.g. `example-client-content`)
- Visibility: **private**
- Owner: same GitHub account that owns the public toolkit repo
- Branch: whatever the client folder was initialized with (commonly `master`)

**When onboarding a new client, after the `new-client` workflow completes:**

```bash
cd clients/[client-slug]
git init  # if not already a repo
gh repo create [client-slug]-content --private --description "Private 1610 Marketing Toolkit client folder for [Client Name]. Knowledge base, content notes, briefs, memory, transcripts. Not for public consumption."
git remote add origin https://github.com/[gh-owner]/[client-slug]-content.git
git add -A && git commit -m "Initial commit"
git push -u origin master  # or main, match the local branch
```

**Per-client `.gitignore` must include at minimum:**
```
.DS_Store
*.swp
.claude/settings.local.json
.claude/worktrees/
**/node_modules/
**/package-lock.json
```

---

## Knowledge File Frontmatter

All knowledge files use YAML frontmatter for scanning without reading full content:

```yaml
---
title: "Human-readable title"
description: "One-line summary of what this file contains"
category: strategy | voice | data | workflow | research
last_updated: YYYY-MM-DD
status: active | needs-update | reference
priority: high | medium | low
---
```

---

## Memory System

Each client has a two-layer operational memory under `memory/`:

**MEMORY.md** — Curated summaries kept under 200 lines. Contains:
- Key people (names, roles, notes)
- Important decisions and their rationale
- Workflow preferences and lessons learned
- API credentials and external resource references

**logs/YYYY-MM-DD.md** — Append-only daily session logs tracking:
- Actions taken and files changed
- Key decisions made
- Data pulled (API calls, metrics)
- Feedback received
- Open threads for follow-up

Update MEMORY.md when you learn something that should persist across sessions. Create a daily log entry at the start of each working session.

---

## Capabilities Reference

### Strategic Capabilities

#### `brief me on [client]`
Read client's `CLAUDE.md` and all knowledge files. Provide a structured summary covering: company overview, target audience, brand voice, current goals, content mix, what's working, current priorities. Stay in conversational mode for follow-up questions.

#### `monthly plan for [client]` → `/generate-month`
Generate month-level strategy with 4-week breakdown, content mix, hypotheses to test, production planning. Reads `references/planning.md`. Saves to `outputs/monthly-briefs/`.

#### `weekly plan for [client]` → `/generate-week`
Generate specific content plan for the week. Aligns with monthly plan if one exists. Creates atomic content notes in `outputs/content/`. Optionally creates Typefully drafts.

#### `biweekly plan for [client]` → `/generate-biweekly`
Two-week execution plan with mandatory performance data pull + platform research. Creates 10-14 content notes. Reads `references/biweekly.md`. Saves to `outputs/biweekly-briefs/`.

#### `analyze performance for [client]`
Load tracking CSVs, identify top performers and patterns, propose updates to `whats-working.md`. Read `references/analysis.md`.

#### `new client [name]` → `/new-client`
Guided ~20 minute onboarding interview. Creates folder structure from `templates/`, populates knowledge files, generates first plans. Read `references/onboarding.md`.

#### `update strategy for [client]`
Parse the requested change, identify which knowledge file(s) need updating, make the updates, confirm what changed.

#### `index content for [client]` → `/index-content`
Scan a content storage folder and update `tracking/content-index.md`. Supports multiple locations — run against different drives/folders. Each run adds or updates one location.

#### `shoot review for [client]` → `/shoot-review`
Post-organize review. Match footage to content notes, flag gaps, surface bonus footage with content ideas, create ad-hoc notes for approved ideas. Requires `/organize-shoot` to have run first.

### Content Production

#### `/organize-shoot [path]`
Process raw shoot footage: extract audio, transcribe with Whisper, rename files, catalog. Last step is `footage-index` ingest (required). Updates shoot log; `content-index.md` is regenerated by ingest.

#### `/cut-video [note | --next N]`
Cut a talking reel from an editor brief + word-level transcript. Skill: `cut-video`.

#### `mkt-kit`
Session loader: read the knowledge pack, ask and log what's missing.

#### `reel-qa` / `reel-broll` / `reel-bench` / `reel-regress`
QA gate, B-roll index/search, harness bake-off, engine fixture re-render.

#### `footage-index`
Compile a mounted footage volume into catalog JSONL + generated `content-index.md`.

#### `film-board`
9:16 scroll-snap HTML board for a talk-over recording.

#### `draft-cluster-blog`
Search-first cluster post from an existing transcript.

#### `branded-report`
Self-contained brand-themed HTML from an existing markdown analysis.

#### `/create-typefully-drafts <content>`
Push specific content to Typefully as unpublished drafts. For ad-hoc posts.

#### `/typefully-status [scheduled|published]`
Check recent Typefully drafts — status, platforms, scheduled dates, preview text.

### Quick Logging

#### `log content for [client]`
Platform, format, title, URL, theme, hook, CTA, created by.

#### `log performance for [client]`
Content ID, views, reach, likes, comments, shares, saves, link clicks, follows.

#### `log lead for [client]`
Lead name, date, source, platform, content piece, status.

---

## Content Notes System

Each content piece from a biweekly or weekly brief is saved as its own atomic markdown note in `outputs/content/`. This enables Kanban board tracking, per-piece status management, and clickable navigation from briefs to individual content details.

**Monthly plans do NOT create content notes** — they remain strategic documents.

### Status Workflow
`concept` → `pre-production` → `captured` → `editing` → `pre-approval` → `approved` → `scheduled` → `published`

Revision loop: `pre-approval` → `editing` (with revision notes appended)

### How Briefs Use Content Notes
- Briefs replace inline content piece details with a linked table: `[[content-note-filename]]`
- Master shot list stays in the brief (consolidated by location)
- Captions, scripts, piece-specific shot lists live in each content note
- See `references/content-notes.md` for the full schema, naming convention, and Kanban setup

### Ad-Hoc Content Notes
One-off content ideas (not tied to a brief) can also be created as content notes with `brief: ""` in frontmatter. They enter the same Kanban pipeline.

---

## Reference Library

The `references/` folder contains on-demand knowledge that you read when the task calls for it. Don't load these preemptively — read them when a specific workflow or question needs the depth.

### Core Procedures
| File | When to Read |
|------|-------------|
| `planning.md` | Generating monthly or weekly plans |
| `biweekly.md` | Generating bi-weekly execution plans |
| `biweekly-brief-protocol.md` | Step-by-step bi-weekly protocol (data pulls, Sheets workflow) |
| `monthly-planning-protocol.md` | Monthly plan protocol (pre-plan review, structure) |
| `analysis.md` | Performance analysis, revenue reports, updating what's working |
| `onboarding.md` | New client onboarding (guided discovery interview) |
| `tracking.md` | Content logging, performance tracking, revenue attribution |
| `output-formats.md` | Templates for monthly plans, weekly plans, performance reports |
| `content-notes.md` | Content note schema, naming convention, Kanban setup |
| `caption-protocol.md` | Writing/finalizing any spokesperson or on-camera caption (hook + expand, BANKED-promotion trap, pre-flight QA) |
| `workflows.md` | Weekly and monthly workflow cadences |
| `edit-route.md` | Any video cut: choosing Resolve (`resolve-reel`) or ffmpeg (`cut-video`), the business's `edit_route` preference, how to ask |

### Marketing Skills
| File | When to Read |
|------|-------------|
| `marketing-psychology.md` | Writing hooks, CTAs, messaging, pricing framing (70+ mental models) |
| `content-strategy.md` | Content planning, topic clusters, buyer journey, prioritization |
| `email-sequence.md` | Email sequences, drip campaigns, lifecycle automation |
| `seo-audit.md` | Technical SEO audits, on-page optimization, diagnostics |
| `analytics-tracking.md` | GA4, GTM, event tracking, UTM frameworks, conversion tracking |
| `copywriting-frameworks.md` | Shared copy structure before client voice |
| `search-cluster-blog-ranking.md` | Ranking factors for transcript-grounded cluster posts |
| `ai-visibility-audit.md` | How assistants cite (or ignore) the site |
| `branded-html-reports.md` | Self-contained HTML deliverable + optional BYO host |
| `platform-backfill.md` | Revive a dormant social catalog without looking automated |
| `newsletter-pipeline.md` | Segmented, tape-grounded newsletters; anti-slop stack; `scripts/lint-copy.py` and `scripts/scaffold-pipeline.py` |

### Integration References
| File | When to Read |
|------|-------------|
| `integrations.md` | Google Workspace setup (Drive, Docs, Sheets, Slides) |
| `typefully.md` | Typefully API integration (drafts, status, social sets) |
| `ga4-integration.md` | GA4 Data API setup and common queries |
| `hubspot-integration.md` | HubSpot CRM API, pipeline management |
| `marketing-dashboard.md` | Live analytics dashboard architecture |
| `hybrid-workflow.md` | AI + freelance + in-house content production system |
| `ahrefs-integration.md` | Ahrefs API setup, endpoints, credit budget, workflow integration |
| `meta-graph.md` | Meta Graph API — pull Instagram/Facebook insights schedulers don't expose (reach, saves, shares, watch time) via `scripts/meta_pull.py` |

### Supporting References
| File | When to Read |
|------|-------------|
| `ai-writing-detection.md` | AI writing patterns to avoid in copy |
| `event-library.md` | Comprehensive GA4 event tracking reference |
| `ga4-implementation.md` | GA4 setup details |
| `ga4-data-api.md` | GA4 Data API documentation |
| `gtm-implementation.md` | Google Tag Manager setup |
| `sequence-templates.md` | Email sequence templates |
| `email-types.md` | Email type reference |
| `copy-guidelines.md` | Email copy and personalization patterns |

---

## Working Principles — rationale

Rationale and full wording for the numbered principles in `CLAUDE.md` → "Working Principles". The rules themselves are there; the detail is here.

**#6 (ground content direction in transcripts, not filenames).** When writing concepts, captions, editor briefs, or scripts for footage that has been shot, always read the actual transcript (`.txt` files in `Audio/` subfolders or `transcripts/`). Never infer what was said from filenames or file-mapping summaries alone — filenames are for identification, transcripts are ground truth for what was actually said on camera. If no transcript exists, say so and flag it rather than guessing.

**#7 (brainstorm and confirm before building any brief).** Before generating a biweekly, weekly, or monthly brief, share the proposed plan in conversation (cadence, post counts, what's fresh capture vs banked, strategic pivots), ask clarifying questions about anything genuinely uncertain, and wait for sign-off. Only then generate files. **Why:** A 2026-05-04 brief was generated end-to-end with the wrong shoot cadence assumed, requiring 10 content notes + the brief + 2 shoot-day docs to be revised or deleted. The brainstorm step costs 2 messages; skipping it costs 10-15 file rewrites.

**#8 (run `humanizer` on all client-facing copy before finalizing).** Applies to captions, briefs, landing pages, social posts, email drafts, anything with written text that will be read by a human outside the toolkit loop. Do not wait for the user to ask. **Why:** AI writing patterns (em-dash overuse, "transformations," "your vision," brochure-y phrasing, rule-of-three openers) undermine credibility immediately. Run the humanizer skill before presenting any client-facing draft. Exception: internal planning documents and the briefs themselves (which are tools, not output). **Enforced:** a global `PostToolUse` hook (`~/.claude/hooks/humanizer-voice-guard.py`) fires across every brand whenever a content note / landing page / email draft is written, reminding you to run the voice-guidelines check + actually invoke the humanizer tool and log the result. The hook is a backstop for the "asserted clean but never ran it" miss — invoke the tool, don't rely on the reminder.

**#9 (run the caption protocol on any spokesperson or on-camera caption).** Hook + expand, never a 1:1 transcript retype; rewrite banked captions before promoting, not after; and run the pre-flight QA (rewrite-vs-cleaned-up test, negative-parallelism count ≤ 1). Full procedure: `references/caption-protocol.md`. **Why:** captions that just retype the video script add nothing beyond watching, and humanizer alone doesn't catch the hook-and-expand miss or stacked negative parallelisms. This is a separate gate from principle 8, not a substitute.

---

## Document Output & Formatting

Plans are saved as markdown to the client's `outputs/` folder. For detailed output templates, read `references/output-formats.md`.

### DOCX Formatting
When a client needs Word format, use pandoc with the client's reference template:

```bash
pandoc "[input.md]" \
  --reference-doc="[client]/outputs/reference-template.docx" \
  -f markdown-auto_identifiers \
  -o "[output-path].docx"
```

- `--reference-doc` = Uses template with proper heading styles (includes `outlineLvl` for collapsible headings)
- `-f markdown-auto_identifiers` = Disables bookmarks — clean headers without internal anchors
- Each client should have a `outputs/reference-template.docx` with heading styles configured

### Client-Specific Output Paths
Each client's `CLAUDE.md` specifies their Google Drive path for .docx files. Check the client instructions before saving.

---

## Integrations

All integrations are optional and configured per-client. See `references/integrations.md` for detailed setup.

| Integration | What It Does | Config Location |
|-------------|-------------|-----------------|
| **Google Drive/Docs/Sheets/Slides** | Store deliverables, collaborative tracking, presentations | Client `CLAUDE.md` |
| **Typefully** | Draft social posts for X and LinkedIn | `knowledge/typefully-config.md` |
| **GA4** | Website analytics and conversion tracking | `knowledge/ga4-integration.md` |
| **HubSpot** | CRM, pipeline management, leads dashboard | `knowledge/hubspot-integration.md` |
| **Ahrefs** | SEO data, keyword research, competitor analysis, backlinks | `knowledge/ahrefs-config.md` |

---

## Metrics Reference

**Engagement Rate:**
```
(Likes + Comments + Shares + Saves) / Reach × 100
```

**Performance Score (1-10):**
- 1-3: Below average for this client
- 4-6: Average
- 7-8: Above average
- 9-10: Exceptional / viral

---

## Extending the System

When you build a new workflow or integration for a specific client, follow this process:

1. **Build it in the client's `knowledge/` folder first.** Get it working. Iterate until it's reliable.
2. **When proven and useful for other clients, split it:**
   - **Generic procedure** → new file in `references/` (strip all client-specific values)
   - **Client config** → stays in the client's `knowledge/` folder (only the values: IDs, URLs, keys)
3. **Update the command routing table** if the new workflow should be triggered by natural language.
4. **Proactively suggest** genericizing workflows that could benefit other clients.

### Naming convention
Reference and client config files use matching names:
- System: `references/ga4-integration.md` (generic procedure)
- Client: `knowledge/ga4-integration.md` (client-specific values)

---

## Getting Started

See `docs/how-to-use.md` for the complete quick reference guide.

To onboard your first client:
```
new client [client-name]
```
