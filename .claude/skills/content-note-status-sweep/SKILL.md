---
name: content-note-status-sweep
description: Walk every content note in a client's `outputs/content/` folder, read frontmatter, check on-disk evidence (transcripts, source footage, tracking CSV rows, post dates), and advance the `status:` field where evidence makes it obvious. Surface stuck pieces, missing inputs, and CSV/note discrepancies in a structured report. Use whenever the user says "sweep statuses", "advance content statuses", "what's stuck", "audit content pipeline", "update kanban", "where are we on content", "status sweep for [client]", or any time the Kanban board has likely drifted from on-disk reality (after a shoot, after a publish day, before a planning session, when the user can't tell what's actually in flight). Always run this BEFORE generating a new biweekly or weekly brief, so the planning input reflects what's actually shipped versus stuck. The skill is conservative: it auto-advances only through the production statuses (concept → pre-production → captured → editing) and never into approved/scheduled/published, which require human signoff.
metadata:
  version: 1.0.0
---

# Content Note Status Sweep

You are auditing the content pipeline. The user has explicitly delegated content-note `status:` management to the agent because manually flipping select fields in Obsidian is friction they want removed. Your job is to keep the Kanban board honest by reconciling every content note with the file evidence on disk and the tracking CSVs, then producing a structured report so the user can see what moved, what's stuck, and what needs their attention.

This skill exists because, without periodic sweeps, the board drifts: pieces that have been captured stay marked `concept`, published pieces still show `scheduled`, an editor finished work two weeks ago but the note still says `editing`. When the board stops matching reality, the user stops trusting it, then stops using it. A reliable Kanban is worth more than a perfect one — your job is to keep it reliable.

---

## Hard rules

These protect the user's trust in the system. Treat them as non-negotiable.

1. **Never auto-advance into `approved`, `scheduled`, or `published`.** Those statuses represent human decisions (client approval, scheduling intent, the moment of publishing). Inferring them from file evidence is a high-cost mistake — a piece marked `published` that isn't actually live becomes invisible to the planning cycle. If the evidence suggests one of those, surface it as a *suggestion* in the report and let the user confirm.
2. **Never modify a note without appending to its `## Revision History` section.** A silent status change is unauditable. The line you append is the evidence trail: `- YYYY-MM-DD: status advanced from X to Y by status-sweep (evidence: transcript file present at <path>)`.
3. **Never delete or rename notes.** This skill only edits the `status:` field and appends to Revision History. Anything else is out of scope.
4. **Skip any note where `status_lock: true` appears in frontmatter.** This is the user's escape hatch — when they want a piece to sit in a status while they think, they set the lock and you respect it. Note the skipped pieces in the report so the user knows they were considered.
5. **Show the report BEFORE writing changes, then ask for confirmation.** The user must see what you intend to do before you touch any file. After they confirm, apply all changes in a single batch. Never advance and report after-the-fact.
6. **Skip the `_archive/` subfolder.** Archived pieces are out of the pipeline by definition.

---

## Step 1 — Identify the client

If the conversation hasn't told you which client to sweep, ask once:

> *"Which client should I sweep? (or 'all' to sweep every client)"*

Resolve to one or more folders like `clients/[client-name]/outputs/content/`. If the user is in a client-specific subfolder (`cwd` under `clients/[client]/`), default to that client and confirm.

For multi-client sweeps, run the procedure once per client and produce one report per client. Do not interleave them.

---

## Step 2 — Gather inputs

For each client you're sweeping, collect:

1. **All content notes:** `clients/[client]/outputs/content/*.md` (skip `_archive/` and any non-`.md` files).
2. **The content log:** `clients/[client]/tracking/content-log.csv` if it exists. Read every row; you'll need the `content_id`, `status`, and `date_published` columns to cross-check against notes.
3. **The transcripts folder:** `clients/[client]/transcripts/` — note which files exist. You're matching by content_id or by date or by filename slug, whichever the client uses (check the client's `CLAUDE.md` for footage/transcript conventions).
4. **The footage root** referenced by the client's `CLAUDE.md` (the "Footage & Drive Convention" or similar section). You'll use this to verify `source_footage:` paths point to real files when possible. If the footage root is on an external drive that isn't mounted, treat the existence check as "unknown" rather than "missing" — flag it in the report instead of advancing status based on a false negative.
5. **Today's date.** You need it for "stuck for >N days" calculations and for the Revision History line.

Read every content note's frontmatter. Build a working table in your head (or a scratch file if the client has >50 notes) with: `filename, content_id, current_status, post_date, shoot_date, assigned_to, source_footage, status_lock`.

---

## Step 3 — Check evidence per note

For each note, walk through the evidence checks in order. The first check that triggers an advance wins; record the evidence string for the Revision History line.

The detailed evidence-to-status mapping lives in `references/status-evidence-rules.md`. Read that file before doing the actual checks — it has examples and edge cases that this overview deliberately omits to stay scannable.

**Summary of advances this skill will make automatically:**

| Current status | Evidence on disk | New status |
|----------------|------------------|------------|
| `concept` | `pre_production_complete: true` in frontmatter, OR shot list section is non-placeholder, OR shoot_date is set and within next 14 days | `pre-production` |
| `concept` or `pre-production` | A transcript file exists matching content_id/slug, OR `source_footage` is filled and the file exists on disk | `captured` |
| `captured` | `assigned_to:` has a non-empty editor name AND shoot_date is in the past | `editing` |

**Advances this skill will NEVER make automatically (suggest instead):**

- `editing` → `pre-approval` (requires the editor saying the cut is ready; you can't infer this from disk)
- `pre-approval` → `approved` (human signoff)
- `approved` → `scheduled` (intent — Typefully draft creation is a signal, but the user owns the decision)
- `scheduled` → `published` (a row in `content-log.csv` with `status: published` is strong evidence — surface it, but require confirmation because timing matters)

**Stuck-piece detection** — flag (do not advance) any of these:

- `status: scheduled` AND `post_date` is in the past → "should be published or rescheduled"
- `status: pre-approval` for >7 days (use note's most recent Revision History entry, or file mtime as fallback) → "approval is bottleneck"
- `status: editing` for >14 days → "editor stalled or piece abandoned"
- `status: captured` for >14 days with no `assigned_to:` → "needs editor assignment"
- `status: concept` for >30 days with no `shoot_date:` → "ghost concept — should be archived or scheduled"

**Missing-input detection** — flag any of these:

- Status is `captured` or later but `source_footage:` is empty
- Status is `editing` or later but no transcript exists where one would be expected
- `assigned_to:` is the literal placeholder `""` or empty list when status is `editing` or later

**CSV/note discrepancies** — for each row in `content-log.csv`:

- If the row has a `content_id` and no matching note exists in `outputs/content/`, flag as "logged content has no content note"
- If a content note has `status: published` but no row in `content-log.csv`, flag as "published note not logged"
- If a row has `date_published` set but the matching note's status is not `published`, flag as "log says published, note disagrees" — this is where the auto-advance to `published` is *suggested* (not made)

---

## Step 4 — Produce the report

Use the template at `references/sweep-report-template.md`. Read it first. The template defines the exact section order and headers — keep them so the user can scan the same shape every time.

Output the report inline in the conversation. Do NOT write it to a file unless the user asks (they usually don't — the value is the conversation, not the artifact).

The report has these sections, in this order:

1. **Summary line** — one sentence: "Swept N notes for [client]. M auto-advances proposed. K stuck pieces. J discrepancies."
2. **Auto-advances proposed** — table of pieces this skill will advance, with old → new status and the evidence that triggered each advance. This is what the user is approving when they confirm.
3. **Suggestions for human decision** — pieces where the evidence points to `approved` / `scheduled` / `published`, but the skill won't act unilaterally. The user can confirm each one or address them later.
4. **Stuck pieces** — table with title, current status, days stuck, probable cause.
5. **Missing inputs** — pieces that should have transcripts/footage/editors but don't.
6. **CSV / note discrepancies** — mismatches between `content-log.csv` and the notes.
7. **Skipped (status_lock)** — pieces that had `status_lock: true` and were not considered.
8. **No action needed** — count only, not a full list (it's noise). Optionally list them if the user asks.

End the report with: *"Confirm to apply the auto-advances above. The suggestions and flags need your decisions separately."*

---

## Step 5 — Apply changes after confirmation

When the user confirms, apply changes in a single batch. For each note in the auto-advances table:

1. Use the `Edit` tool to change the `status:` field in frontmatter from old to new.
2. Use the `Edit` tool to append a line to the `## Revision History` section. If the section doesn't exist, add it at the end of the note. Format:

   ```
   - YYYY-MM-DD: status advanced from <old> to <new> by status-sweep (evidence: <short evidence string>)
   ```

   Use today's date. The evidence string should be concrete and short — `"transcript file at transcripts/2026-04-15-DS-01.txt"` not `"transcript exists"`.

3. Do NOT touch any other field. Do NOT reformat the file. Do NOT regenerate sections. The user trusts the sweep precisely because it has a small, predictable footprint.

For batches of >5 notes, consider delegating the mechanical Edit work to a Haiku subagent with a precise spec (filename, exact old `status:` line, exact new `status:` line, exact Revision History line to append). That keeps the main thread focused on the strategic conversation that usually follows a sweep ("now let's plan the next biweekly").

After applying, report back briefly:

> *"Applied N auto-advances. The flags above still need your decisions when you're ready."*

---

## Step 6 — Suggest the next move

A status sweep usually surfaces one of three follow-up actions. Pick the most relevant and offer it:

- **If many pieces just advanced to `captured`** → suggest a shoot review session: *"Three pieces just moved to captured. Want to walk the new footage and finalize editor briefs?"*
- **If many pieces are stuck in `pre-approval` or `editing`** → suggest a chase list: *"Five pieces are stuck in pre-approval. Want me to draft check-in messages for the editors / approvers?"*
- **If the suggested `published` advances are pending** → suggest logging performance: *"Four pieces look like they published but aren't logged. Want me to walk through and log them?"*

Don't push if the user is already moving on. Just plant the seed.

---

## Reference files

Read these when the situation calls for them. Don't load preemptively.

| File | Read when |
|------|-----------|
| `references/status-evidence-rules.md` | Doing the actual evidence checks in Step 3. Has the full mapping with examples and edge cases. |
| `references/sweep-report-template.md` | Producing the report in Step 4. Has the markdown template the user expects. |
