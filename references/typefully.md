# Typefully Integration

Procedures for creating and managing social media drafts via the Typefully v2 API.

## Prerequisites

- API key stored as environment variable (e.g., `TYPEFULLY_API_KEY` in user's shell config)
- The env var may not be loaded in Claude Code's shell by default. Always source the shell config first:
  ```bash
  source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null
  ```
- Client's `knowledge/typefully-config.md` must have their `social_set_id` configured
- Base URL: `https://api.typefully.com/v2`
- Auth: Bearer token from the env var

## API Essentials

- Drafts are created via `POST /v2/social-sets/{social_set_id}/drafts`
- Multi-platform support: X + LinkedIn in a single draft using the `platforms` object
- Drafts are always created as **unpublished** so the user reviews and schedules in Typefully
- Always write JSON payloads to temp files to avoid shell escaping issues
- Tags must be created manually in the Typefully app before they can be used via API — omit the `"tags"` field unless the user confirms tags exist

---

## Generate Week

The full weekly content generation workflow. Triggered by "generate week", `/generate-week`, or `/generate-week [blog-url] [transcript-path]`.

### Step 1: Gather Source Material

Parse arguments for:
- **Blog URL:** If provided, fetch the content using WebFetch
- **Transcript path:** If provided, read the file from the client's `transcripts/` folder
- **Neither:** Ask the user what source material to work from, or generate from knowledge files alone

If source material is provided, log it:
- Check `content/our-content/` for existing source log
- Save a summary of the source material with date and origin

### Step 2: Read All Client Knowledge

Read these files in the client's directory:
1. `CLAUDE.md`
2. `knowledge/00-client-overview.md`
3. `knowledge/voice-guidelines.md`
4. `knowledge/personas-storybrand.md`
5. `knowledge/goals-and-benchmarks.md`
6. `knowledge/whats-working.md`
7. `knowledge/typefully-config.md`
8. Check `outputs/monthly-briefs/` for the current month's plan

### Step 3: Generate Weekly Content Plan

Create 5-7 content pieces. For each piece include:
- **Title** (descriptive, for internal reference)
- **Platform(s)** (X, LinkedIn, or both)
- **Content Pillar / Tag** (aligned with the client's content pillars)
- **Source** (which blog/transcript/idea this comes from)
- **Hook** (the opening line — this is the most important element)
- **Key Message** (the core point being made)
- **CTA** (what action to take)

**Platform-specific formatting:**
- **X:** 280 characters max per tweet. Can be a thread (multiple tweets separated by clear breaks). Punchy, direct, conversational.
- **LinkedIn:** 500-1,500 characters. Hook line, body with value, CTA. More narrative and professional.

**Content mix guidelines** (adapt based on client's content pillars):
- 2-3 pieces pulled from source material (blog/transcript)
- 1-2 thought leadership or educational pieces
- 1 personal/values piece
- 0-1 behind-the-scenes or community piece

### Step 4: Present Plan for Review

Show the complete weekly plan to the user with all content pieces, hooks, and messages. Ask: "Does this look good? Any changes before I create the Typefully drafts?"

Wait for user confirmation before proceeding.

### Step 5: Create Typefully Drafts

For each approved content piece:

1. Read the `social_set_id` from `knowledge/typefully-config.md`
2. Build the JSON payload:

```json
{
  "content": "The full post text for the primary platform",
  "platforms": {
    "x": {
      "content": "X-specific version (280 char max per tweet)"
    },
    "linkedin": {
      "content": "LinkedIn-specific version (longer narrative)"
    }
  },
  "draft_title": "Descriptive title for organization"
}
```

3. Write the JSON to a temp file:
```bash
cat > /tmp/typefully-draft.json << 'ENDJSON'
{ ... payload ... }
ENDJSON
```

4. Create the draft:
```bash
curl -s -X POST "https://api.typefully.com/v2/social-sets/${SOCIAL_SET_ID}/drafts" \
  -H "Authorization: Bearer ${TYPEFULLY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d @/tmp/typefully-draft.json
```

5. Check the response for success (should return draft ID and URL)
6. Log each draft's ID and URL

**Important:**
- Never include `publish_at` — all drafts are unpublished for user review
- Omit `"tags"` unless the user has confirmed tags exist in Typefully
- If curl fails, check that the env var is loaded and the social_set_id is correct

### Step 6: Save Weekly Brief

Save the complete weekly plan to `outputs/weekly-briefs/YYYY-MM-DD-weekly-plan.md`.

Include a "Typefully Drafts" section at the bottom with:
- Draft titles
- Draft IDs
- Private URLs for review

### Step 7: Report Summary

Tell the user:
- How many drafts were created
- Links to review them in Typefully
- Any errors that occurred
- Reminder to review and schedule in Typefully

---

## Create Drafts

Ad-hoc draft creation without the full weekly workflow. Triggered by "create typefully drafts" or `/create-typefully-drafts <content>`.

### Process

1. Read `knowledge/typefully-config.md` for `social_set_id`
2. Read `knowledge/voice-guidelines.md` for voice reference
3. Parse the provided content (inline text, file path, or reference to a weekly brief)
4. Ask the user:
   - Which platform(s)? (X, LinkedIn, or both)
   - Should it be adapted differently per platform?
   - Content pillar/tag?
   - Descriptive title?
5. If multi-platform, create platform-specific versions (X: concise and punchy, LinkedIn: longer narrative)
6. Show the draft content for user confirmation
7. Write JSON payload to `/tmp/typefully-draft.json`
8. Create via curl (same as Generate Week Step 5)
9. Report the draft ID, private URL, and any errors

---

## Check Status

Check recent Typefully drafts. Triggered by "typefully status" or `/typefully-status [scheduled|published]`.

### Process

1. Read `knowledge/typefully-config.md` to get `social_set_id`
2. Source the shell config for the API key
3. Fetch drafts:
```bash
curl -s "https://api.typefully.com/v2/social-sets/${SOCIAL_SET_ID}/drafts" \
  -H "Authorization: Bearer ${TYPEFULLY_API_KEY}"
```
4. Filter by status if the user specified "scheduled" or "published"
5. Display in a clean table:

| # | Title | Status | Platforms | Scheduled | Preview | URL |
|---|-------|--------|-----------|-----------|---------|-----|

6. Provide a summary:
   - Total drafts found
   - Breakdown by status (draft, scheduled, published)
   - Highlights for this week
7. If published drafts are shown, remind the user to log performance data
