# Canonical Frontmatter Schemas

This is the single source of truth for what the audit script validates against. Every file type the audit covers is defined here with required fields, allowed enum values, optional fields, and validation rules.

When the schemas drift (someone adds a new field, a status value changes, a category is added), update this file AND the equivalent `_FIELD_SETS` in `scripts/audit.py`. Both should change together.

---

## Knowledge files

**Path glob:** `clients/[client]/knowledge/*.md`
**Subfolders:** Skip `_archive/` and any folder starting with `.`

### Required fields

| Field | Type | Allowed values | Notes |
|-------|------|----------------|-------|
| `title` | string | any non-empty | Human-readable title |
| `description` | string | any non-empty | One-line summary, scannable |
| `category` | enum | `strategy`, `voice`, `data`, `workflow`, `research` | Picks which routing slot the file fills |
| `last_updated` | date | `YYYY-MM-DD` | When the content was last meaningfully changed |
| `status` | enum | `active`, `needs-update`, `reference` | `active` = trust it, `needs-update` = stale but useful, `reference` = background |
| `priority` | enum | `high`, `medium`, `low` | `high` = check before any output |

### Optional fields
None standardized at the schema level. Custom fields like `last_review:`, `tags:`, etc. are allowed and should not trigger validation errors.

### Validation rules
1. All six required fields must be present.
2. `category`, `status`, `priority` must match the allowed enums exactly (case-sensitive).
3. `last_updated` must parse as `YYYY-MM-DD`.
4. **Stale flag:** If `status: needs-update` AND `last_updated` is more than 60 days ago, surface as a stale-knowledge issue (not a schema violation, but a separate category).

### Example

```yaml
---
title: "Voice Guidelines"
description: "Brand voice attributes, blog excerpts, tone variations, social translation rules for Dawson's content."
category: voice
last_updated: 2026-04-27
status: active
priority: high
---
```

---

## Content notes

**Path glob:** `clients/[client]/outputs/content/*.md`
**Subfolders:** Skip `_archive/` and any folder starting with `.` or `_`

### Required fields

| Field | Type | Allowed values | Notes |
|-------|------|----------------|-------|
| `content_id` | string | `[CLIENT-PREFIX]-YYYYMMDD-NN` | Must be globally unique within the client |
| `title` | string | any non-empty | Human-readable name |
| `type` | literal | `content-note` | Always exactly this string. Enables Dataview / Kanban filtering. |
| `client` | string | client folder name (e.g., `example-client`) | Must match the folder under `clients/` |
| `status` | enum | `concept`, `pre-production`, `captured`, `editing`, `pre-approval`, `approved`, `scheduled`, `published` | Drives Kanban lane |
| `post_date` | date | `YYYY-MM-DD` | Scheduled post date |
| `platform` | list of strings | non-empty list | Target platforms (Instagram, LinkedIn, X, etc.) |
| `format` | string | any non-empty | E.g., "Reel 60-90s", "Carousel 6-8", "Blog post" |

### Optional fields

| Field | Type | Notes |
|-------|------|-------|
| `brief` | wiki-link string | `"[[YYYY-MM-DD-biweekly-brief]]"` or `""` for ad-hoc. The empty string is allowed; missing entirely is also allowed. |
| `assigned_to` | list of strings | Editors, photographers, etc. |
| `project` | string | Internal project name |
| `project_social_name` | string | Public-facing project name |
| `duration` | string | Target video duration |
| `source_footage` | string | Path from client's footage root |
| `shoot_date` | date | When footage was/will be shot |
| `tags` | list | Obsidian tags |

### Validation rules
1. All eight required fields must be present.
2. `type` must literally equal `content-note`.
3. `status` must match the eight allowed values exactly.
4. `client` should match the client folder name. If it doesn't, that's an auto-fixable issue (the path is ground truth).
5. `content_id` must be unique across all content notes for the client. Duplicates are a structural issue.
6. `brief` field, if present and non-empty, must point to a brief file that exists under `outputs/biweekly-briefs/`, `outputs/weekly-briefs/`, or `outputs/monthly-briefs/`. Match by stripping `[[` and `]]` and looking for a file with that base name.

### Example

```yaml
---
content_id: "DS-20260513-01"
title: "Open to Close — launch announcement"
type: content-note
client: "example-client"
brief: "[[2026-05-13-biweekly-brief]]"
status: scheduled
post_date: 2026-05-13
platform:
  - X
  - LinkedIn
format: "Long-form post"
---
```

---

## Briefs (biweekly, weekly, monthly)

**Path globs:**
- `clients/[client]/outputs/biweekly-briefs/*.md`
- `clients/[client]/outputs/weekly-briefs/*.md`
- `clients/[client]/outputs/monthly-briefs/*.md`

**Subfolders:** Skip `_archive/` and any folder starting with `.` or `_`

### Required fields

| Field | Type | Allowed values | Notes |
|-------|------|----------------|-------|
| `title` | string | any non-empty | Human-readable title |
| `client` | string | client folder name | Must match the folder under `clients/` |
| `period_start` | date | `YYYY-MM-DD` | First day of the brief's coverage window |
| `period_end` | date | `YYYY-MM-DD` | Last day of the brief's coverage window |
| `status` | enum | `active`, `archived` | Briefs in flight are `active`; old briefs get downgraded to `archived` |

### Optional fields

| Field | Type | Notes |
|-------|------|-------|
| `theme` | string | Strategic theme for the period |
| `pieces_count` | integer | Number of content pieces planned |
| `published_count` | integer | Pieces actually published |

### Validation rules
1. All five required fields must be present.
2. `period_start` and `period_end` must parse as `YYYY-MM-DD`. `period_end >= period_start`.
3. `status` must be `active` or `archived`.
4. **Wiki-link integrity:** Briefs typically include a Content Pieces table with `[[YYYY-MM-DD-PREFIX-NN-slug]]` references. The audit walks the body text for these and checks that each target file exists under `outputs/content/`. Broken links are flagged as structural issues.

### Example

```yaml
---
title: "Biweekly Brief — May 13-26, 2026"
client: "example-client"
period_start: 2026-05-13
period_end: 2026-05-26
status: active
---
```

---

## Structural rules (not field-level)

These don't validate frontmatter directly — they validate folder structure and cross-file references.

### No orphan files at `outputs/` root

Every file under `clients/[client]/outputs/` must be inside a subfolder. Files at the root level (e.g., `outputs/random-doc.md`) are violations. The user must move them into the right subfolder or archive them.

**Exception:** Files starting with `.` (hidden) and `README.md`-style index files at the root are allowed.

### Brief references must resolve

For every content note with a non-empty `brief:` field, the linked brief file must exist somewhere under `outputs/biweekly-briefs/`, `outputs/weekly-briefs/`, or `outputs/monthly-briefs/`. Match by base filename — strip `[[` and `]]`, append `.md` if missing, then search.

### Wiki-links from briefs must resolve

For every brief, scan the body text for `[[...]]` patterns that look like content note references (pattern: `YYYY-MM-DD-` prefix, ending in a slug). Each must resolve to an actual `.md` file under `outputs/content/`. Broken links typically mean the content note was renamed or the brief was generated against pieces that never got created.

### Content IDs must be unique

Within a single client, no two content notes may share a `content_id`. Duplicates usually mean a copy-paste error during brief generation. The fix is manual — the user picks which one to renumber.

### Stale `needs-update` knowledge

Knowledge files with `status: needs-update` older than 60 days (`last_updated` more than 60 days before today) are flagged. Not a schema violation — a process signal. The user should either update the file or downgrade `status:` to `reference`.

---

## Severity levels

The script tags every issue with one of three severities:

| Severity | Meaning | Examples |
|----------|---------|----------|
| `error` | Breaks downstream tooling. Must fix. | Missing required field, invalid enum value, duplicate `content_id`, unparseable YAML |
| `warning` | Doesn't break tooling but signals drift. | `client:` field doesn't match folder name (auto-fixable), `last_updated:` missing on a knowledge file (auto-fixable from mtime) |
| `info` | Heads-up only, no action required by default. | Stale `needs-update` knowledge file, optional field missing where it's commonly used |
