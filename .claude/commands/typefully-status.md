---
description: Check recent Typefully drafts (scheduled, published, or all)
argument-hint: [scheduled|published]
allowed-tools: [Read, Bash]
---

# Typefully Draft Status

Check recent drafts in Typefully.

## Arguments

User provided: $ARGUMENTS

- If "scheduled" - show only scheduled drafts
- If "published" - show only published drafts
- If empty - show recent drafts (all statuses)

## Process

1. Detect the active client from the current working directory (`clients/[client-name]/`). If ambiguous, ask.

2. Read `clients/[client]/knowledge/typefully-config.md` to get the social_set_id

2. Fetch drafts from Typefully:
   ```bash
   curl -s "https://api.typefully.com/v2/social-sets/SOCIAL_SET_ID/drafts?limit=10" \
     -H "Authorization: Bearer $TYPEFULLY_API_KEY"
   ```

3. Parse the JSON response and display results in a clean table:

   | # | Title | Status | Platforms | Scheduled | Preview | URL |
   |---|-------|--------|-----------|-----------|---------|-----|
   | 1 | ... | draft/scheduled/published | X, LinkedIn | date or -- | first 80 chars... | link |

4. Provide a summary:
   - Total drafts found
   - How many are unpublished/scheduled/published
   - Any drafts that are scheduled for today or this week

5. If published drafts are shown, remind the user: "Don't forget to log performance data with `log performance for [client]`"
