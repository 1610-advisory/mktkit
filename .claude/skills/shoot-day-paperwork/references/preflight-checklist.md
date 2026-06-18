# Preflight Checklist

Four questions. Ask them all before you generate anything. Every one of them comes from a real failure mode that cost real rework.

---

## Why this exists

On (early production), a shoot-day document was generated for a client assuming a two-shoot cadence (5/4 + 5/18). The actual cadence was one shoot day. By the time the assumption was caught:

- The brief had to be revised
- 10 content notes had to be edited
- 2 shoot-day documents had to be deleted

That is fifteen-plus file mutations to fix something a two-message clarification would have prevented. The lesson — promoted to early-cycle incident notes as a pinned correction — is: **brainstorm and confirm before generating.**

A polished call sheet built on wrong assumptions is more expensive than no call sheet at all. The crew shows up expecting one thing, the script assumes another, and someone notices halfway through the shoot. Or worse, no one notices and the editing pipeline absorbs the error.

The preflight is two messages. Run it.

---

## The four questions

Ask all four. If the user answers some but not all, ask for the rest before continuing. If the user gets impatient, gently note: "Two messages here saves fifteen file edits later — lesson from past production."

### 1. Shoot date(s) — confirm exact dates

**What to ask:**
> "Which date(s) is this shoot covering? I want to make sure I'm not assuming a cadence the brief doesn't actually have."

**Why it matters:**
- Briefs sometimes hint at multiple shoot days; the actual operating model may be one
- Content notes' `shoot_date:` frontmatter may be aspirational, not confirmed
- Weather, talent availability, or logistics can collapse a planned two-day shoot into one

**What to do with the answer:**
- Use this date for the output filename and frontmatter
- Use this date to filter content notes — only include notes whose `shoot_date` matches
- If the brief implies a different cadence, flag the discrepancy in "Gaps to resolve" so it gets reconciled

### 2. Content IDs in scope this shoot day

**What to ask:**
> "Of the [N] pieces in the brief, which content_ids are actually being captured this shoot day? Anything getting banked, swapped, or skipped?"

**Why it matters:**
- A 12-piece brief doesn't always mean 12 pieces shoot in one day
- Some pieces may already have footage from a prior shoot or content bank
- Some pieces may be photo-only, BTS, or ad-hoc and not need a formal shoot block
- Some pieces may be flagged "swap if time" — those go in Backup, not the main shot list

**What to do with the answer:**
- Read only the in-scope notes' shot lists for the consolidated list
- Put deliberately-not-captured pieces in the Backup section with one-line context
- If a piece's `shoot_date` matches the day but the user excluded it, note that in Gaps so the content note's frontmatter can be updated post-shoot

### 3. On-camera talent

**What to ask:**
> "Who's on camera? Just [founder / primary talent], or anyone else (kids, partner, guest, second shooter as B-cam subject)?"

**Why it matters:**
- Briefs often default to "the founder is available." That's not always true.
- Family content (kids, spouse) requires availability and consent on the day, not just in the plan
- A guest or partner appearing on camera changes the call time, props, and possibly location

**What to do with the answer:**
- Populate the Talent Call Sheet section with names, call times, and what they're needed for
- If a content note implied talent that the user excluded ("no, my kids aren't around that day"), move that piece to Backup or flag in Gaps

### 4. Locations — locked vs. flexible

**What to ask:**
> "Locations: which are locked (this piece HAS to shoot at [X])? Anything flexible we can group?"

**Why it matters:**
- Some pieces are location-locked (e.g., RITW = wooden chair in the woods, project walkthroughs = the project site)
- Others are flexible (to-camera reflections can shoot anywhere with decent light)
- Grouping by location is what makes the shoot run on time — but you can only group correctly if you know what's locked

**What to do with the answer:**
- Use locked-location notes as anchors in the Suggested Order
- Slot flexible-location notes around the anchors to minimize travel and setup
- The Shot List grouping should respect locked locations as scene boundaries

---

## After preflight, before generating

Read back what you heard, in one short paragraph:

> "Confirming: shooting [date], capturing [N] pieces ([list of content_ids]), [talent names] on camera, locations are [list]. [M] pieces from the brief moved to Backup ([reason]). Sound right?"

Wait for explicit yes. Then build the call sheet.

If the user changes anything in the readback, redo the readback with the change. The cost of one more confirmation message is zero. The cost of generating against a wrong readback is a rewrite.
