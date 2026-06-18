---
description: Generate weekly content from a blog post and/or transcript, create Typefully drafts for X and LinkedIn
argument-hint: [blog-url] [transcript-path]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, WebFetch, AskUserQuestion]
---

# Generate Weekly Content + Typefully Drafts

The user wants to generate this week's social content from source material and push drafts to Typefully.

## Arguments

User provided: $ARGUMENTS

Parse for:
- A URL to a blog post or article
- A file path to a transcript (optional)
- Any additional context or notes

**Client detection:** Determine the active client from the current working directory (`clients/[client-name]/`). If ambiguous, ask.

If no arguments provided, ask the user:
1. "Do you have a new blog post URL to work from?"
2. "Do you have a video transcript to work from? (file path or paste it)"
3. "Any specific themes, events, or things on your mind this week?"

---

## Workflow

### Step 1: Gather Source Material

**If blog URL provided:**
- Fetch the blog content using WebFetch
- Extract the full article text, title, key themes, and quotable passages
- Identify 5-10 potential social post angles from the content

**If transcript path provided:**
- Read the transcript file
- Extract key insights, quotable moments, and themes

**If neither provided:**
- Proceed with existing knowledge files only (this is acceptable)
- Ask the user what they want the week's content to focus on

### Step 2: Log New Source Material

If new blog or transcript content was provided:
- Check `clients/[client]/content/our-content/` for existing logs
- Save a summary of the new content to `clients/[client]/content/our-content/YYYY-MM-DD-slug.md` with:
  - Title
  - Source URL or transcript path
  - Key themes
  - Quotable passages
  - Social post angles identified

### Step 3: Read All Client Knowledge

Read these files to build full context:
1. `clients/[client]/CLAUDE.md`
2. `clients/[client]/knowledge/00-client-overview.md`
3. `clients/[client]/knowledge/voice-guidelines.md`
4. `clients/[client]/knowledge/personas-storybrand.md`
5. `clients/[client]/knowledge/goals-and-benchmarks.md`
6. `clients/[client]/knowledge/whats-working.md`
7. `clients/[client]/knowledge/typefully-config.md`
8. Check `clients/[client]/outputs/monthly-briefs/` for current month's plan - if one exists, align the weekly plan with the monthly strategy

### Step 4: Generate Weekly Content Plan

Create 5-7 content pieces for the week. For each piece include:

- **Title:** Descriptive name for the draft
- **Platform(s):** X, LinkedIn, or both
- **Content Pillar:** match to the client's pillars from voice-guidelines.md or goals-and-benchmarks.md
- **Tag:** Typefully tag matching the pillar (if Typefully is configured)
- **Source:** Which blog post / transcript / knowledge this came from
- **Hook:** Opening line (platform-specific if cross-platform)
- **Key Message:** The core point in one sentence

Then provide the full draft text for each platform:

**X version:**
- 280 characters max per post
- If it needs more space, write it as a thread (multiple posts)
- Punchy, direct, conversational
- Match the voice in voice-guidelines.md

**LinkedIn version (if cross-platform):**
- Hook line that stops the scroll
- White space between paragraphs (use line breaks)
- Body that delivers value
- CTA at the end
- Up to 3,000 characters but aim for 500-1,500
- Slightly more professional framing than X, still warm and direct

**Content mix for the week (align with goals-and-benchmarks.md and whats-working.md):**
- 2-3 pieces from the blog post or transcript (if provided) — pull different angles, don't just rehash
- 1-2 thought leadership / educational pieces (match to client's content pillars)
- 1 personal/brand story piece
- 0-1 behind-the-scenes or community piece

### Step 5: Present Plan for Review

Show the complete weekly plan with all draft content to the user in a clean format.

Then ask: **"Ready to push these to Typefully as unpublished drafts? You'll be able to review, edit, and schedule them in the Typefully app."**

**Do NOT proceed to Typefully API calls until the user confirms.**

### Step 6: Create Typefully Drafts

Read the social_set_id from `clients/[client]/knowledge/typefully-config.md`.

For each approved content piece, create a Typefully draft using curl. Use the templates from typefully-config.md.

**Important implementation notes:**
- Write the JSON payload to a temporary file first to avoid shell escaping issues: write JSON to `/tmp/typefully-draft-N.json`, then use `curl -d @/tmp/typefully-draft-N.json`
- Always omit `publish_at` so drafts are unpublished
- Use the content pillar as the tag
- Use the descriptive title as `draft_title`
- Check each curl response for errors (non-2xx status codes)
- Log the draft ID and private_url from each successful response

### Step 7: Save Weekly Brief

Save the complete weekly plan to:
`clients/[client]/outputs/weekly-briefs/YYYY-MM-DD-weekly-plan.md`

Use the weekly plan format from the system CLAUDE.md but add a **Typefully Drafts** section at the bottom:

```markdown
## Typefully Drafts

| # | Title | Platforms | Tag | Draft URL |
|---|-------|-----------|-----|-----------|
| 1 | ... | X + LinkedIn | builder | [link] |
| 2 | ... | X | builder | [link] |
```

### Step 8: Summary

Report to the user:
- Number of drafts created
- Links to review each draft in Typefully
- Reminder: "Review and schedule these in Typefully. They're saved as unpublished drafts."
- Reminder: "After content goes live, run `log content for [client]` to track performance."
