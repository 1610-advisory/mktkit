---
description: Create Typefully drafts from provided content for X and/or LinkedIn
argument-hint: <content-or-file-path>
allowed-tools: [Read, Bash, Glob, AskUserQuestion]
---

# Create Typefully Drafts

Push content directly to Typefully as drafts without running the full weekly workflow.

## Arguments

User provided: $ARGUMENTS

This can be:
- Inline content to post (text provided directly)
- A path to a file containing post content
- A reference to a weekly brief file to push drafts from

## Process

1. Detect the active client from the current working directory (`clients/[client-name]/`). If ambiguous, ask.
2. Read `clients/[client]/knowledge/typefully-config.md` to get the social_set_id and curl templates
3. Read `clients/[client]/knowledge/voice-guidelines.md` for voice reference
4. Parse the provided content

5. Ask the user:
   - Which platform(s): X only, LinkedIn only, or both?
   - If both: should the content be adapted per platform or posted as-is?
   - What content pillar/tag? (check the client's voice guidelines or typefully config for tags)
   - A descriptive title for the draft

5. If adapting for multiple platforms:
   - X version: 280 char max, punchy, direct
   - LinkedIn version: longer narrative, hook/body/CTA structure

6. Show the draft content to the user and confirm before pushing

7. Write the JSON payload to a temporary file (`/tmp/typefully-draft.json`) to avoid shell escaping issues

8. Create the draft via curl using the appropriate template from typefully-config.md:
   ```bash
   curl -s -X POST "https://api.typefully.com/v2/social-sets/SOCIAL_SET_ID/drafts" \
     -H "Authorization: Bearer $TYPEFULLY_API_KEY" \
     -H "Content-Type: application/json" \
     -d @/tmp/typefully-draft.json
   ```

9. Check the response for success (2xx status) or errors
10. Report the draft ID and private URL to the user

## Important Notes

- Always create as unpublished drafts (omit `publish_at`) unless the user explicitly asks to schedule
- Use `draft_title` for organization in Typefully
- Always write JSON to a temp file rather than inline in the curl command to avoid escaping issues
- Report success/failure clearly
