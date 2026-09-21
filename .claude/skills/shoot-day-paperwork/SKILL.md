---
name: shoot-day-paperwork
description: Generate a comprehensive shoot-day call sheet from a toolkit biweekly or weekly brief by reading every linked content note and consolidating their shot lists, props, talent, and locations into a single editor- and crew-facing document. Use whenever the user says "build the shoot day", "make the call sheet", "consolidate shots for the shoot", "shoot paperwork for [brief]", "what do we need on shoot day", "prep shoot day docs", or asks for any pre-shoot consolidation across multiple content notes. Also trigger when a brief is finalized and the user is about to step into a 2-3 hour shoot — without consolidation they will end up flipping between 10-14 individual notes on set.
metadata:
  version: 1.0.0
---

# Shoot Day Paperwork

You are a producer. Your job is to turn a finalized brief and its 10-14 atomic content notes into one document the on-set crew can hold in their hand during a 2.5-3 hour shoot day. No more flipping between notes. No more guessing which shot goes with which piece. Every line on the call sheet is tagged back to the source content piece so on-set decisions trace cleanly to the strategy.

This skill operates on briefs and content notes — it does not modify them, it consolidates them. Run `mkt-kit` if the call sheet will carry on-screen words or brand marks; missing DESIGN.md / voice: ask and log to `knowledge/_intake-log.md`.

---

## Why preflight matters (read this before you skip it)

The most expensive failure mode for this skill is generating a polished call sheet against the wrong assumptions. In an early client cycle, a shoot-day doc was generated assuming a two-shoot cadence (5/4 + 5/18); the actual cadence was one shoot day. The brief plus 10 content notes plus 2 shoot-day docs all needed surgery. The fix took an order of magnitude longer than the preflight conversation would have.

The preflight is not bureaucracy. It is the difference between a useful artifact and rework. **Do not generate the call sheet until you have explicit confirmation on the four questions in `references/preflight-checklist.md`.** Read that file before you start.

---

## Inputs

The user gives you a brief, or signals one. Resolve to a single brief file path before continuing:

- Explicit path or filename → use it
- "the most recent biweekly" / "this cycle's brief" / vague → look in `clients/[client]/outputs/biweekly-briefs/` and `clients/[client]/outputs/weekly-briefs/`, sort by date, pick the most recent active brief, and **confirm** with the user ("Going off `2026-05-13-biweekly-brief.md` — same one?")
- The client should be inferable from the working directory or recent context. If ambiguous, ask.

Briefs live at:
- `clients/[client]/outputs/biweekly-briefs/YYYY-MM-DD-biweekly-brief.md`
- `clients/[client]/outputs/weekly-briefs/YYYY-MM-DD-weekly-plan.md`

Content notes referenced by the brief live at:
- `clients/[client]/outputs/content/YYYY-MM-DD-PREFIX-NN-slug.md`

The brief's "Content Pieces" table contains `[[wiki-links]]` to each note. Resolve every wiki-link to its file path.

---

## Procedure

### Step 1 — Read the brief

Read the entire brief. Note:
- The period and theme (for the call sheet header)
- The Content Pieces table (your list of notes to read)
- The Master Shot List section, if present (often consolidated by location already — useful as a prior, not a source of truth)
- Posting Schedule (which gives format and platform per piece)
- Any "shoot day" or shoot-cadence language in the brief that hints at expected shoot count

If the brief references multiple shoot days, that's a flag for the preflight conversation, not a license to assume.

### Step 2 — Run the preflight (mandatory)

Open `references/preflight-checklist.md` and walk the four questions with the user. Do not generate the call sheet yet. The user's answers feed directly into the frontmatter and header of the output file.

If the user pushes back ("just generate it, I'll tell you what's wrong"), gently redirect: the preflight is two messages; rework is fifteen file edits. Cite the lesson if needed.

### Step 3 — Read every in-scope content note

For each content_id the user confirmed is in scope this shoot day:

1. Open the content note file
2. Extract from frontmatter:
   - `content_id`
   - `title`
   - `format` (reel, carousel, BTS, photo, etc.)
   - `shoot_date` (sanity check — does it match the confirmed shoot day?)
   - `assigned_to` (talent or crew)
   - `project` / `project_social_name` (location grouping hint)
   - `duration` (per-piece time budget on set)
3. Extract from body:
   - Full `## Shot List` checklist
   - Any prop / wardrobe / setup mentions in `## Concept`, `## Edit Notes`, or `## Script` (look for: "bring", "have on hand", "books to bring", "wear", "set up", "location:", or specific named items)
   - Any talent context (who's on camera, references to "[talent] reads", "[talent] holds", "kids in frame", etc.)

If a note has **no `## Shot List` section**, do not invent shots. Flag it under "Gaps to resolve before shoot" in the output and continue. Inventing shots is worse than flagging gaps — the on-set crew can ask the operator; they cannot un-shoot a fabricated shot.

If `shoot_date` on a note disagrees with the confirmed shoot date, flag it. Don't silently override.

### Step 4 — Group by location and scene

Group the consolidated shot list by location, then by scene within location. The right grouping minimizes setup/teardown time. For example:

- All "wooden chair in woods" shots batch together regardless of which content piece they belong to
- All "to camera reflections" might happen at one spot, then move
- BTS or environmental photos slot in during natural breaks

Each line in the consolidated shot list must carry the `[CONTENT-ID]` tag so the on-set person knows which piece they're capturing for. Example:

```
- [ ] Quote hook to camera, 3 takes [DS-20260515-03]
- [ ] Quote hook to camera, 3 takes [DS-20260520-07]
- [ ] Reading passage in chair, 2-3 takes [DS-20260515-03]
- [ ] Reading passage in chair, 2-3 takes [DS-20260520-07]
```

### Step 5 — Build the call sheet

Use `references/shoot-day-template.md` as the structure. Every section in the template is required unless the brief or preflight makes it irrelevant (e.g., no second talent → omit the second talent row, but keep the section).

Required sections in order:
1. **Frontmatter** (date, brief reference, content_ids covered, status: planned)
2. **Header** — date, locations, expected total duration, who's on (talent + crew)
3. **Source brief citation** — wiki-link back to the brief at the very top of the body
4. **Suggested order / timing** — best sequence to minimize teardown/setup, with rough time estimates per scene
5. **Shot list grouped by location → scene** — each line tagged with source `[CONTENT-ID]`
6. **Talent call sheet** — names, call times, what they're needed for
7. **Props / setup checklist** — bullet list per location
8. **Backup pieces** — pieces from the brief NOT being captured this day, listed with one-line context (in case time opens up)
9. **Gaps to resolve before shoot** — content notes missing shot lists, frontmatter mismatches, anything you flagged
10. **Revision history** — `YYYY-MM-DD: Created from [[brief-filename]]`

### Step 6 — Write the file

**Output path:** `clients/[client]/outputs/shoot-days/YYYY-MM-DD-shoot-day.md`

- The folder is `shoot-days/` (plural). Create it if it doesn't exist.
- Filename uses the **shoot date**, not today's date.
- If a file already exists for that shoot date, do not silently overwrite. Show the user the existing file and ask: append, overwrite, or save with `-v2` suffix.

**Hard rule from past production:** never write to `outputs/` root. The skill's output folder is `outputs/shoot-days/` only.

### Step 7 — Suggest next steps

After writing, surface the obvious follow-ups in your response:
- "Confirm with [talent name(s)] that [call time] still works"
- "Share with [editor / cinematographer / second shooter] — file is at [path]"
- "Two notes flagged as gaps: [content_ids]. Want me to draft shot lists for them?"
- "If any pieces moved out of scope during preflight, the brief still lists them as scheduled — want to update those notes' status to `pre-production` -> banked or revise the brief's posting schedule?"

Don't dead-end the conversation. The skill exists inside a workflow; show the user where the next step is.

---

## Hard rules

- **No call sheet without preflight confirmation.** Two messages of clarification beats fifteen file edits.
- **Every shot line carries its source `[CONTENT-ID]` tag.** This is the load-bearing decision in the whole skill — without it, on-set choices can't trace back to the brief.
- **Output goes only in `outputs/shoot-days/`.** No orphan files at `outputs/` root.
- **Don't invent shots.** If a content note has no `## Shot List`, flag it as a gap.
- **Don't modify the brief or content notes.** This skill reads them; it does not edit them. If the user wants a content note's status updated post-shoot, that's the `organize-shoot` workflow, not this one.
- **Cite the source brief** at the top of the call sheet body (wiki-link).
- **Confirm shoot date and in-scope content_ids before generating.** These two values determine everything else.

---

## Reference files

- `references/preflight-checklist.md` — the four mandatory verification questions and why they matter (with the the early-cycle incident as cited reason). Read before starting.
- `references/shoot-day-template.md` — the markdown template for the output file. Read when assembling the file.
