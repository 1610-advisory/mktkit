---
description: Create a new client folder and run the guided onboarding interview (~20 min)
argument-hint: client-name
---

# New Client Onboarding

The user wants to onboard a new client. Read `references/onboarding.md` for the full guided onboarding procedure.

**Arguments:** The user may provide the client name after the command (e.g., `/new-client acme-corp`). If no name is given, ask for one.

**Process:**
1. Run `scripts/init-client.py` to create the folder structure. This also:
   - Copies the `templates/gitignore.template` as `.gitignore`
   - Initializes an isolated git repo inside the client folder
   - Makes an "Initial client setup" commit
   - Note: the parent toolkit repo ignores `clients/*/`, so this repo stays private
2. Follow the onboarding interview in `references/onboarding.md`
3. Populate knowledge files as the user answers
4. Generate the client's `CLAUDE.md`. **Include a "Repository: PRIVATE BACKUP" section at the top** (see `clients/example-client/CLAUDE.md` for the template) so the next session knows where the remote lives and the privacy boundary rules.
5. Generate the first monthly plan and weekly plan
6. Commit progress periodically inside the client folder as work is done (`cd clients/[name] && git add . && git commit -m "..."`)
7. **Set up the private GitHub backup** (skip only if the user explicitly opts out):
   ```bash
   cd clients/[client-slug]
   gh repo create [client-slug]-content --private --description "Private 1610 Marketing Toolkit client folder for [Client Name]. Knowledge base, content notes, briefs, memory, transcripts. Not for public consumption."
   git remote add origin https://github.com/[gh-owner]/[client-slug]-content.git
   git push -u origin "$(git branch --show-current)"
   ```
   See the root `CLAUDE.md` "Privacy boundary" section for the convention. Tell the user the push cadence: at least weekly, ideally at the end of any meaningful session.
