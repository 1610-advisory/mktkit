# Integration Setup

Detailed configuration for external services. All integrations are optional and configured per-client.

## Google Workspace

The system accesses Google Workspace via MCP tools. No API keys are needed — authentication is handled by the MCP server connection.

### Google Drive

**What it does:** Store deliverables (monthly briefs, weekly plans) in shared client folders.

**Setup per client:**
- Get the Google Drive folder ID from the folder URL (the long string after `/folders/`)
- Add to client's `CLAUDE.md`:
  ```
  **Google Drive Folder ID:** [folder-id]
  **Google Drive Path:** [descriptive path like "Client Name/Marketing/Content Plans"]
  ```

**Usage:**
- After generating a plan as markdown, convert to DOCX and upload to Drive
- Use the MCP Google Drive tools to search, create, upload, and organize files

### Google Sheets

**What it does:** Alternative to local CSV files for collaborative tracking. Useful when multiple team members need access to content logs and performance data.

**Setup per client:**
- Create spreadsheets for content-log, performance, and/or revenue-attribution
- Get spreadsheet IDs from the URLs
- Add to client's `CLAUDE.md`:
  ```
  **Content Log Sheet ID:** [spreadsheet-id]
  **Performance Sheet ID:** [spreadsheet-id]
  **Revenue Sheet ID:** [spreadsheet-id]
  ```

**Usage:**
- When logging data, write to Google Sheets instead of local CSV
- Use the MCP Google Sheets tools for reading, writing, and formatting
- Can apply conditional formatting for visual dashboards

### Google Docs

**What it does:** Create briefs and plans directly as Google Docs (alternative to markdown + pandoc).

**Setup per client:**
- Specify in `CLAUDE.md` if the client prefers Google Docs over markdown/DOCX
- Plans will be created directly in the configured Drive folder

### Google Slides

**What it does:** Create presentations for client reviews, quarterly summaries, or strategy decks.

**Setup:** No special configuration needed beyond the Drive folder ID. Slides are created ad-hoc when requested.

---

## Typefully

**What it does:** Creates draft social posts for X and LinkedIn via the Typefully v2 API. Drafts are always unpublished — the user reviews and schedules them in Typefully.

### Setup

1. **API Key:**
   - Get your Typefully API key from your Typefully account settings
   - Store it as an environment variable in your shell config:
     ```bash
     export TYPEFULLY_API_KEY="your-api-key-here"
     ```
   - Add to `~/.zshrc` or `~/.bashrc` for persistence

2. **Social Set ID:**
   - Each Typefully workspace has a social set ID
   - Find it in Typefully settings or via the API
   - Create `knowledge/typefully-config.md` for each client that uses Typefully:
     ```markdown
     # Typefully Configuration

     ## Social Set
     - **Social Set ID:** [your-social-set-id]

     ## Platforms
     - X: @handle
     - LinkedIn: profile-name

     ## Curl Templates

     ### Create Draft
     ```bash
     source ~/.zshrc 2>/dev/null
     curl -s -X POST "https://api.typefully.com/v2/social-sets/SOCIAL_SET_ID/drafts" \
       -H "Authorization: Bearer ${TYPEFULLY_API_KEY}" \
       -H "Content-Type: application/json" \
       -d @/tmp/typefully-draft.json
     ```

     ### List Drafts
     ```bash
     source ~/.zshrc 2>/dev/null
     curl -s "https://api.typefully.com/v2/social-sets/SOCIAL_SET_ID/drafts" \
       -H "Authorization: Bearer ${TYPEFULLY_API_KEY}"
     ```
     ```

### Important Notes

- Always `source ~/.zshrc` before making API calls — the env var may not be loaded in the current shell
- Write JSON payloads to `/tmp/typefully-draft.json` to avoid shell escaping nightmares
- Never include `publish_at` — all drafts are for review only
- Tags must be created in the Typefully app first before they can be used via API
- If the API returns an error, check: is the env var loaded? Is the social_set_id correct? Is the JSON valid?
