# Plan: DESIGN.md as the standard brand source

Status: built on branch `feat/design-md-standard` (2026-10-28). Not pushed.

## The rule

DESIGN.md is the standard brand source for every business that uses this
toolkit. Claude sessions build a claude.ai Design System page from it. Other
agents can build a similar local HTML view of it. The file is the source.
The page and the HTML are views, never edited as the source. If a view and
the file disagree, the file wins.

## What changes

1. **DESIGN.md is required** at `knowledge/DESIGN.md` in every marketing repo,
   in the Google DESIGN.md format (YAML tokens in the frontmatter, rules in
   the prose). `brand-identity.md` stays only as an optional flat twin for
   older skills.
   - Missing: copy `templates/DESIGN.md`, ask the owner the questions in
     `mkt-kit/REFERENCE.md`, log the answers in `_intake-log.md`. Never
     invent a brand fact. Leave a value blank before you guess it.
   - `scripts/init-client.py` now copies the template into `knowledge/`.
2. **One shared script, stdlib only:** `scripts/design_md.py`.
   - `check` lints the file: required keys, colors that parse, `{colors.x}`
     references that resolve, component text contrast per theme.
   - `render` writes one self-contained HTML view of the file (any agent,
     any model, no install).
   - `ds` writes the files for a claude.ai Design System page (tokens.json,
     the brand book README from the prose, one preview per component, a
     cover, and a new index). Claude sends them with the Artifact tool.
   - Generalised from the first business's renderer. It holds no brand
     values: every color, face and word comes from the file it reads.
3. **New step "Design System page"** (Claude sessions only), written in
   `references/design-md.md`:
   - One page per business, built only from that business's DESIGN.md.
     Never two businesses in one page. Name it for the business.
   - Start from the Design System Artifact type, private. Sharing it needs
     the owner's yes.
   - Record the page URL as `design_system_url:` in that business's
     DESIGN.md frontmatter. Never in the toolkit.
   - DESIGN.md changed: run `ds` again and send the changed files to the
     same URL.
4. **Who can read the claude.ai page.** Claude Code sessions and claude.ai
   on the owner's account (and the owner's org). Not pi or Grok, Cursor,
   Codex, scripts, CI, or the business's own team unless the owner shares
   it. So every agent reads DESIGN.md, never only the page.
5. **Docs:** `mkt-kit` skill + REFERENCE, the template, the client
   CLAUDE.md template, the new-client checklist, CLAUDE.md principle 0,
   the reference index, the changelog, a plugin version bump. Every rules
   file stays under 10,000 characters.

## Out of scope

- Repos with no DESIGN.md: the hub opens an issue on each client repo. No
  list in this repo.
- Sharing, publishing or deploying any page.
- Turning `brand-identity.md` users over to DESIGN.md (they keep working).

## Tests

`scripts/tests/test_design_md.py`: the YAML subset reader, references,
contrast, `check`, the HTML view (themes, both-theme tokens, no network
but fonts), and the Design System files (token list shape, names unique,
variants folded into one component, index marker).

## Pilot (first business)

Run the steps on the first business's DESIGN.md, compare the new view with
its own renderer, fold the lessons back in. Findings go in the business's
repo and the branch report, not here.
