# Status Evidence Rules

The exact mapping of "what file evidence triggers which status advance" with examples and edge cases. The SKILL.md gives you the summary table; this file gives you the reasoning so you can handle the cases the table doesn't anticipate.

---

## Why these rules exist

Auto-advancing status is a one-way trust transaction. If the rule is too loose and the skill advances a piece that shouldn't have moved, the user has to manually walk it back AND reconfirm every other change you made. If the rule is too tight, the user has to keep flipping statuses manually, which is the exact friction we're trying to remove.

The rules below are calibrated for **conservative confidence**: the evidence has to point clearly at the new status. Ambiguous cases get surfaced for the user to decide, not auto-advanced.

---

## The status workflow

```
concept → pre-production → captured → editing → pre-approval → approved → scheduled → published
                                        ↑                          |
                                        └──── (revision needed) ───┘
```

This skill auto-advances through the **production statuses only**: `concept` → `pre-production` → `captured` → `editing`. Everything from `pre-approval` forward represents a human decision (the editor saying "ready", the client saying "approved", the user saying "scheduled", the platform saying "published") and gets surfaced as a suggestion, never an auto-advance.

---

## Rule 1 — `concept` → `pre-production`

**Move when:** the piece has crossed from "idea on paper" into "we're going to shoot this."

**Evidence (any one is sufficient):**
- Frontmatter has `pre_production_complete: true` (explicit signal from the user or a prior workflow)
- The note's `## Shot List` section is populated with non-placeholder content (i.e., specific shots are listed, not the template's `- [ ] Shot description`)
- `shoot_date:` is filled AND falls within the next 14 days (we're imminently shooting it)
- `assigned_to:` includes a photographer/videographer name AND `shoot_date:` is filled

**Evidence string for Revision History:**
- `"shoot_date 2026-05-12 within next 14 days"`
- `"shot list populated with 5 specific shots"`
- `"pre_production_complete: true in frontmatter"`

**Edge cases:**
- A `shoot_date` more than 14 days out is NOT enough — it's just a placeholder calendar entry. The piece is still a concept.
- If a `shoot_date` is in the *past* and the note is still `concept`, this is a stuck piece, not a candidate for advance. Flag it, don't move it.

---

## Rule 2 — `concept` or `pre-production` → `captured`

**Move when:** footage or transcripts exist on disk that can plausibly be matched to this piece.

**Evidence (any one is sufficient):**
- A transcript file exists in `clients/[client]/transcripts/` whose filename or contents reference the content_id, the slug, or the project name. Examples:
  - `transcripts/DS-20260415-01.txt` matches content_id `DS-20260415-01`
  - `transcripts/2026-04-15-5-types-of-wealth.txt` matches a note with slug `5-types-of-wealth`
- `source_footage:` is non-empty AND the file exists on disk at the resolved path (use the client's footage root from `CLAUDE.md`)
- A subfolder under the project's footage tree contains a file whose timestamp matches the note's `shoot_date` (within ±1 day) AND the project name matches

**Evidence string for Revision History:**
- `"transcript file at transcripts/DS-20260415-01.txt"`
- `"source_footage file exists: T7-D01/5-types-of-wealth/Edits/ARoll-Intro.mp4"`
- `"shoot folder T7-D01/2026-04-15/ contains 7 files matching project"`

**Edge cases:**
- If `source_footage:` is filled but the file does NOT exist at the resolved path, this is a missing-input flag, not an advance. The note thinks it's been captured but the disk disagrees.
- If the footage root is on an unmounted external drive, treat existence as **unknown** and DO NOT advance based on `source_footage` alone. Use only transcripts (which are typically local) as the trigger. Flag the unmounted drive in the report.
- If multiple transcripts could match (ambiguous filename), prefer not to advance — flag for manual review.

---

## Rule 3 — `captured` → `editing`

**Move when:** the piece has been handed off to an editor.

**Evidence (BOTH must be true):**
- `assigned_to:` contains a non-empty editor name (not the placeholder `""`, not an empty list, not `[ ]`)
- `shoot_date:` is in the past (we're not assigning an editor before the shoot — that's pre-production)

**Evidence string for Revision History:**
- `"assigned to <editor name>, shoot_date 2026-04-10 in the past"`

**Edge cases:**
- If `assigned_to:` is filled but `shoot_date:` is in the future, this is unusual — flag for review, don't advance.
- If `assigned_to:` lists multiple people (e.g., a photographer and an editor), use the presence of any plausible editor name as the trigger. The user uses the same field for both roles.

---

## Rule 4 — Suggested advances (NEVER auto-apply)

These are surfaced in the report's "Suggestions for human decision" section. The skill never modifies the file based on these.

### `editing` → `pre-approval`

**Suggest when:**
- The note has been in `editing` for >5 days AND the Revision History contains a line like "edit v1 ready" or similar editor-supplied marker
- A file in the project's edit folder has a name like `*_v1.mp4`, `*_final.mp4`, `*_approved.mp4` and a timestamp newer than the last "Status → editing" line in Revision History

**Why we don't auto-advance:** The editor saying "ready" is a social signal, not a file signal. We can guess from filenames but we'd be wrong often enough to break trust.

### `pre-approval` → `approved`

**Suggest when:** the user mentions in conversation or in a Revision History entry that the piece is approved, OR a file with `_approved` in the name appears.

**Why we don't auto-advance:** Approval is the moment of human commitment. Inferring it is the highest-cost mistake on this list.

### `approved` → `scheduled`

**Suggest when:**
- A Typefully draft URL appears in the note (search for `typefully.com/draft`)
- The note's `## Revision History` mentions Typefully draft creation

**Why we don't auto-advance:** A Typefully draft might be unscheduled (Dawson's default — see his client `CLAUDE.md`). Creating a draft is not the same as scheduling.

### `scheduled` → `published`

**Suggest when:**
- A row exists in `tracking/content-log.csv` with the matching `content_id` AND a non-empty `date_published` AND `status: published`
- The `post_date` in the note frontmatter is in the past AND the user has logged any performance data referencing this content_id

**Why we don't auto-advance:** A row in the log is strong evidence, but the timing of the `published` flip matters for analytics windows. The user owns the moment.

---

## Stuck-piece detection (flag, never advance)

These checks produce items for the "Stuck pieces" section of the report.

| Condition | Probable cause | Days threshold |
|-----------|---------------|----------------|
| `status: scheduled` AND `post_date` in the past | Post date passed without the user logging it as published, OR the post was rescheduled and the note wasn't updated | 0 (any past date) |
| `status: pre-approval` for >7 days | Approver is the bottleneck — needs a nudge | 7 |
| `status: editing` for >14 days | Editor stalled, piece abandoned, or revisions never made it back | 14 |
| `status: captured` for >14 days with `assigned_to:` empty | Footage exists but no editor was ever assigned — gap in the handoff | 14 |
| `status: concept` for >30 days with no `shoot_date:` | Ghost concept — should be archived or scheduled | 30 |
| `status: pre-production` for >21 days with no transcript/footage match | Shoot didn't happen as planned | 21 |

**How to compute "days stuck":** Look at the most recent line in `## Revision History` matching the current status. Use the date there. If no Revision History exists, fall back to the file's mtime (last modified). If even that isn't available, use `post_date` as a rough proxy and note the imprecision in the report.

---

## Missing-input detection (flag, never advance)

These are notes where the status implies inputs that aren't present.

- `status: captured` or later, but `source_footage:` is empty → "claims captured but no footage referenced"
- `status: editing` or later, but no transcript file exists where one would be expected → "missing transcript — editor brief may be ungrounded"
- `status: editing` or later, but `assigned_to:` is empty/placeholder → "in editing but no editor assigned"
- `status: scheduled` or later, but `post_date:` is empty → "scheduled with no post date"

---

## CSV / note discrepancy detection

Run after all per-note checks are done. For each row in `clients/[client]/tracking/content-log.csv`:

1. **Logged content has no content note:** the CSV row has a `content_id` that doesn't match any note in `outputs/content/`. Most often this is older content logged before notes were created — flag as informational, not urgent.
2. **Note disagrees with log:** the CSV row has `date_published` filled and a published `status`, but the matching note's `status:` is not `published`. Suggest the published advance.
3. **Published note not logged:** a content note has `status: published` but no matching row exists in the CSV. Suggest logging via `log content` workflow.
4. **Status mismatch (non-published):** the CSV `status` field doesn't match the note's `status:`. The note is the source of truth for the production pipeline; the CSV is the source of truth for analytics. Mismatches are usually informational unless it's a published mismatch.

---

## What this skill explicitly does NOT do

- Does not infer voice or tone from a piece (out of scope; see `voice-analysis` skill)
- Does not regenerate Editor Briefs even when status advances (that's `shoot-review`'s job)
- Does not create new content notes (that's `generate-week` / `generate-biweekly`)
- Does not modify the CSV files (that's `tracking.md` workflows: `log content`, `log performance`)
- Does not push notifications to editors or approvers (suggest a chase list, but don't act on it)
- Does not delete notes, even if they look like ghost concepts. Archive is a human decision.

Keeping this scope tight is what makes the skill safe to run unattended on a regular cadence.
