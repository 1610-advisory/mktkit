# Sweep Report Template

The exact markdown template for the structured report you output to the user after a sweep. The shape matters — the user is going to scan this same structure repeatedly, and consistency lets them spot what's new vs. what's the same as last time.

Keep section order, section headers, and table column order exactly as shown. Skip a section entirely if it has no items (e.g., omit "Skipped (status_lock)" if no notes had the lock); don't print empty headers.

---

## Template

```markdown
# Status Sweep — [client name] — YYYY-MM-DD

Swept N notes. M auto-advances proposed. K stuck pieces. J discrepancies.

---

## Auto-advances proposed (M)

These will be applied if you confirm. Each modifies one `status:` field and appends one line to that note's `## Revision History`.

| Note | Old → New | Evidence |
|------|-----------|----------|
| `[[2026-04-15-DS-01-five-types-intro]]` | `concept` → `captured` | transcript file at `transcripts/DS-20260415-01.txt` |
| `[[2026-04-17-DS-02-walkthrough]]` | `captured` → `editing` | assigned to Mike, shoot_date 2026-04-10 in the past |
| `[[2026-04-20-DS-03-revenue-not-scoreboard]]` | `concept` → `pre-production` | shoot_date 2026-05-12 within next 14 days |

---

## Suggestions for human decision (S)

These look like they should advance, but the moves require your call. Confirm each one or leave them and address later.

| Note | Current → Suggested | Why I'm not advancing |
|------|---------------------|----------------------|
| `[[2026-04-08-DS-04-stewardship]]` | `scheduled` → `published` | Row exists in content-log.csv with date_published 2026-04-08 |
| `[[2026-04-12-DS-05-ritw-elon]]` | `editing` → `pre-approval` | File `5-types-pt2_v1.mp4` exists, dated after editing started |

---

## Stuck pieces (K)

Pieces that haven't moved in too long given their status. Most need a nudge to a person, not a file change.

| Note | Status | Days stuck | Probable cause |
|------|--------|-----------|----------------|
| `[[2026-03-22-DS-06-builder-essay]]` | `pre-approval` | 12 | Approval is bottleneck |
| `[[2026-04-01-DS-07-faithful-with-little]]` | `editing` | 18 | Editor stalled or piece abandoned |
| `[[2026-04-05-DS-08-mitchell-walkthrough]]` | `scheduled` | 4 | post_date 2026-04-04 passed — published or rescheduled? |

---

## Missing inputs (I)

Notes whose current status implies inputs that aren't on disk.

| Note | Status | Missing |
|------|--------|---------|
| `[[2026-04-09-DS-09-coffee-shop]]` | `captured` | source_footage field empty |
| `[[2026-04-11-DS-10-three-musketeers]]` | `editing` | no transcript file found, editor brief may be ungrounded |

---

## CSV / note discrepancies (J)

Mismatches between `tracking/content-log.csv` and the notes in `outputs/content/`.

| Issue | Detail |
|-------|--------|
| Logged content has no content note | content-log row `DS-20260301-01` (5-types-of-wealth-intro) — no matching note |
| Published note not logged | `[[2026-03-28-DS-01-five-types-intro]]` has `status: published` but no row in content-log.csv |
| Note disagrees with log | `[[2026-04-08-DS-04-stewardship]]` is `scheduled` but log says published — see suggestion above |

---

## Skipped (status_lock) (P)

These had `status_lock: true` and were not considered. Listing here so you know they were seen.

- `[[2026-04-22-DS-11-1610-launch]]` — status `concept`, locked

---

## No action needed

23 notes are already at the status the evidence supports. Not listed (would be noise). Ask if you want them.

---

**Confirm to apply the auto-advances above.** The suggestions and flags need your decisions separately.
```

---

## Notes on filling the template

**Counts in section headers (M, K, I, J, P):** always include the count even if zero — except the section is omitted entirely when zero. The summary line at the top has the canonical numbers.

**Wiki-link format:** use `[[filename-without-extension]]` so the user can click through in Obsidian. Don't include the `.md` extension. The vault treats these as wiki-links.

**Evidence strings:** keep them short and concrete. Bad: "transcript exists". Good: "transcript file at transcripts/DS-20260415-01.txt". The evidence string is what gets written to Revision History — the user reads it later as an audit trail, so it has to mean something on its own.

**Days stuck:** integer days. If the timestamp source was the file mtime (not Revision History), append `(via file mtime)` to the count so the user knows the precision is rougher.

**Probable cause:** short, action-oriented. The user is scanning to figure out what to *do*, not to read a story. "Approval is bottleneck" is good. "The piece has been waiting for some time and may need attention" is bad.

**Don't inflate the report.** If only one section has items, the report is shorter — that's fine. The sweep is about reliability, not spectacle.

---

## Multi-client sweeps

When the user asks for a sweep across all clients, produce one report per client, separated by `---` and a clear `# Status Sweep — [next-client]` header. Don't try to combine them into a single mega-table — clients have different prefixes, different cadences, different norms, and combining destroys the per-client context.

After all per-client reports, add a short cross-client summary:

```markdown
---

# Cross-client summary

| Client | Notes swept | Auto-advances | Stuck | Discrepancies |
|--------|-------------|---------------|-------|---------------|
| example-client | 47 | 3 | 4 | 2 |
| acme-builders | 28 | 1 | 0 | 1 |

Confirm to apply the auto-advances for each client (or specify which to apply).
```
