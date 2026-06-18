---
name: frontmatter-audit
description: Audit a client's knowledge files, content notes, and briefs for YAML frontmatter integrity and structural issues. Validates required fields, allowed enum values, broken `[[wiki-links]]` between briefs and content notes, broken `brief:` references, duplicate `content_id`s, orphan files at the `outputs/` root, and stale `needs-update` knowledge files older than 60 days. Use this skill whenever the user says "audit frontmatter", "validate the YAML", "check for orphan files", "are there schema issues", "frontmatter audit for [client]", "audit content notes structure", "check the kanban for broken pieces", "what's wrong with the content folder", or whenever something downstream is misbehaving (Kanban filters not working, proofread-blog can't find voice context, briefs missing pieces) and a schema drift is the likely cause. Trigger even if the user does not say "frontmatter" explicitly — anything about validating, auditing, or finding broken references in a client's `knowledge/` or `outputs/` folders should pull this skill.
metadata:
  version: 1.0.0
---

# Frontmatter Audit

You are auditing a client's `knowledge/`, `outputs/content/`, and `outputs/*-briefs/` folders for YAML frontmatter integrity and the structural rules that keep the Kanban, briefs, and proofreading workflows working. **Read-only by default.** You only mutate files after the user explicitly approves a list of fixes.

The heavy lifting is done by `scripts/audit.py`, which walks the folders, parses frontmatter, validates fields against the canonical schemas in `references/schemas.md`, and emits a JSON report. Your job is to invoke the script, summarize the findings clearly, classify what can be auto-fixed, and orchestrate the (optional) batch-fix step.

---

## Why this matters

Multiple clients have hard rules that frontmatter integrity supports:

- The Kanban board (Obsidian) groups content notes by `status:`. Invalid status values silently drop pieces off the board.
- The proofread-blog flow loads `voice-guidelines.md` based on `category:` — wrong category, no voice context.
- Briefs link to content notes via `[[wiki-link]]`. If the link target was renamed or deleted, the brief's "Content Pieces" table breaks.
- Content notes link back to a brief via `brief: "[[YYYY-MM-DD-biweekly-brief]]"`. If the brief was renamed or archived, the chain of custody is broken.
- Some clients have an explicit "no files in outputs/ root" rule. Any orphan there is a violation.
- Knowledge files marked `needs-update` quietly become stale. After 60 days they should be either updated or downgraded to `reference`.

Without periodic audits, this drift accumulates. The audit catches it.

---

## Step 1 — Identify the client

If the user named a client, use that. Otherwise:

1. Check the current working directory. If you are inside `clients/[name]/...`, infer that name.
2. If still ambiguous, list the client folders and ask:
   ```bash
   ls $AI_CMO_ROOT/clients/
   ```
3. The client folder must contain `CLAUDE.md` and a `knowledge/` directory. If it doesn't, abort with a clear error.

The client root path you'll pass to the script is the absolute path to `clients/[name]/`.

---

## Step 2 — Run the audit script

Invoke the script with the client root path:

```bash
Set AI_CMO_ROOT to the absolute path of your toolkit repo root before running these commands.

python3 $AI_CMO_ROOT/.claude/skills/frontmatter-audit/scripts/audit.py \
  --client-root $AI_CMO_ROOT/clients/[client-name] \
  --today 2026-05-08
```

`--today` is optional (defaults to today's date). Pass it explicitly if the user is auditing as of a different date or if you want deterministic output.

The script emits a single JSON object on stdout. The schema is documented at the top of `scripts/audit.py` and in `references/audit-report-template.md`. Capture stdout into a variable or file so you can render it cleanly.

If the script exits non-zero, surface the stderr verbatim — it likely means a path is wrong or a file has unparseable YAML, both of which the user needs to know about.

---

## Step 3 — Summarize the findings for the user

Read `references/audit-report-template.md` once for the report layout, then translate the JSON into that markdown report. The template is what the user sees — the JSON is just the raw data.

Key things to surface, in order:

1. **Headline counts** — total files audited, total issues, auto-fixable count, manual count.
2. **Schema violations** — grouped by file, showing field, expected, actual, severity. Lead with `error` severity.
3. **Structural issues** — orphan files at `outputs/` root, broken `brief:` references, broken `[[wiki-links]]` from briefs to content notes, duplicate `content_id`s.
4. **Stale knowledge** — files with `status: needs-update` older than 60 days, with `last_updated` and the staleness in days.
5. **Auto-fixable list** — exactly what would change if you applied fixes, file by file, key by key, old → new.

If the audit comes back clean, say so plainly. Don't fabricate issues.

---

## Step 4 — Classify each issue

Every issue lands in one of three buckets. The script does the first pass; you adjust if you have judgment the script doesn't.

| Bucket | What qualifies | Examples |
|--------|---------------|----------|
| **Auto-fixable** | The correct value is unambiguous and inferable from context. | `client:` field missing on a content note (path tells us the client), `type: content-note` missing on a file under `outputs/content/`, `last_updated:` missing on a knowledge file edited today (use file mtime), trailing whitespace, single-vs-double-quote inconsistencies that break parsing. |
| **User decision needed** | A required field is missing and the correct value isn't inferable. | A knowledge file with no `category:` (could be strategy, voice, data, workflow, or research — only the user knows), a content note with no `format:`, a brief with no `period_start`/`period_end`. |
| **Manual cleanup** | The fix isn't a frontmatter edit. | Orphan files at `outputs/` root (must be moved/archived by the user), duplicate `content_id`s (must rename one), broken `brief:` references (the linked brief was renamed or deleted — user must decide whether to relink or null it), broken `[[wiki-links]]` from briefs to content notes (same — the content note may have been renamed or never created). |

When in doubt, escalate to **User decision needed** rather than guessing. Inventing field values is a hard no.

---

## Step 5 — Offer to apply auto-fixes

After presenting the report, ask the user:

> "I found N auto-fixable issues. Want me to apply them? I'll show you the diff before saving."

If the user says yes:

1. Run the script again with `--apply-auto-fixes`:
   ```bash
   python3 $AI_CMO_ROOT/.claude/skills/frontmatter-audit/scripts/audit.py \
     --client-root $AI_CMO_ROOT/clients/[client-name] \
     --apply-auto-fixes
   ```
2. The script writes the changes and emits a JSON object listing every file touched and every key changed.
3. Show the user a short summary: `N files updated, K keys changed`. If they want detail, render the per-file diff from the JSON.

If the user says no, leave everything untouched and just summarize what they'd need to fix manually.

**Never apply auto-fixes without explicit approval in this session.** The user might be running the audit just to scope work, not to clean up yet.

---

## Hard rules

These are non-negotiable. Violating any of these breaks the user's trust in the audit.

- **Read-only by default.** The default invocation does not write. The `--apply-auto-fixes` flag only runs after the user approves.
- **Never delete files.** Orphan files get flagged. The user moves or archives them.
- **Never invent field values.** If a required field is missing AND uninferable, surface it as a user decision. Don't pick "strategy" because it sounds plausible.
- **Never modify body content.** Frontmatter only. The body of the markdown file is not your concern.
- **Skip `_archive/` entirely.** Files under `outputs/content/_archive/` (or any `_archive/` subfolder) are intentionally out of pipeline. The script already filters these — confirm that before debugging.
- **Don't run the audit without confirming the client root.** Running against the wrong client wastes time and surfaces noise.

---

## Common scenarios

### "Audit frontmatter for example-client"

Identify client → run script → render report → offer fixes. This is the canonical path.

### "Why is my Kanban missing pieces?"

Likely cause: invalid `status:` values or missing `type: content-note`. Run the audit, focus the report on schema violations under `outputs/content/`, point to the offending files.

### "I renamed a brief — did I break anything?"

Likely cause: content notes still reference the old brief name. Run the audit, focus on the **broken `brief:` references** section. The fix is manual (relink or null), so this is a flag-and-explain, not an auto-fix.

### "Are there orphan files in outputs?"

Run the audit, jump straight to the structural issues section. Orphan files are always manual cleanup — list them with their paths and let the user decide where they belong.

### Audit returns clean

Tell the user plainly. Resist the temptation to surface low-severity nits as if they were issues. A clean audit is a real outcome.

---

## Output formatting

Use the markdown template in `references/audit-report-template.md`. It has stable section headers so the user can scan the same shape every time. Don't reinvent the layout per run.

If the audit catches more than ~20 issues, the report can get long. Collapse the per-file detail into a fenced code block under each section heading rather than bulleting every line — long bullet lists at the top level are harder to scan than a code block the user can read at their own pace.
