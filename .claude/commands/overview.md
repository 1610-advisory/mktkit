---
description: Get a structured overview of a client's strategy and enter conversational Q&A mode
argument-hint: [client-name]
---

# Client Overview

The user wants a summary of a client's marketing strategy. This is the same as "brief me on [client]" but as a slash command.

**Arguments:** The user may specify a client name.

**Process:**
1. Identify the client (ask if ambiguous)
2. Read the client's `CLAUDE.md` and all files in `knowledge/`
3. Provide a structured summary covering:
   - Company overview and positioning
   - Target audience segments
   - Brand voice and messaging
   - Current goals and KPIs
   - Content mix and what's working
   - Current priorities and campaigns
4. Stay in conversational mode — answer follow-up questions by referencing knowledge files (read-only)
