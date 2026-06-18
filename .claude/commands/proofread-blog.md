---
description: Three-tier blog post proofread (spelling/grammar → paragraph breaks → clarity & flow), then propose titles and excerpts. Direction-only; never overwrite the author's voice.
---

# Proofread a Blog Post

You are reviewing a blog post draft for a toolkit client. Your job is to **direct improvements, not overwrite the author's voice.** The author's words stay; you flag, suggest, and (after explicit approval) apply only the tiers they greenlit.

## Trigger phrases

- "proofread this blog post"
- "review this draft"
- "look at this post and tell me what to fix"
- "ready to publish, what do you see?"

## Step 0 — Load voice context (mandatory)

Before reading the post critically, load the client's voice in parallel:

1. `clients/[client]/knowledge/voice-guidelines.md` — strategic voice, tone-by-type, word/phrase preferences
2. `clients/[client]/knowledge/voice-analysis.md` *(if it exists)* — sentence-level signature patterns with transcript citations
3. `clients/[client]/memory/MEMORY.md` — `User Feedback & Preferences` section (catches per-client rules like "no em dashes" or "never change `[[wiki-links]]`")
4. The post itself

If `voice-guidelines.md` is missing, **stop** and tell the user — proofreading without voice context risks AI-flavored corrections that break the author's tone.

## Step 1 — Present suggestions in three tiers (DO NOT EDIT YET)

Output three labeled tiers. Each tier is a list of specific, file-path-scoped suggestions. **Do not change the post during this step.**

### Tier 1 — Spelling & grammar
Hard errors only. Typos, subject-verb mismatches, broken punctuation, wrong homophones. Format each as:

```
- [path:line] "<short context phrase>" → "<corrected phrase>"  (reason)
```

### Tier 2 — Paragraph breaks for readability
Where the prose runs long without a break. Break on **chronological shifts** (then…now), **thematic shifts** (one idea → next), or **rhythm beats** (a punchy line that wants to land alone).

```
- [path:line] Suggest break before "<first words of new paragraph>"  (reason)
```

### Tier 3 — Clarity & flow
Sentences that lose the reader, redundant phrasing, weak verbs, unclear referents. Phrase as **questions or alternative phrasings**, not unilateral rewrites:

```
- [path:line] "<original>" — could read as "<alternative>"? (reason)
```

Lead each suggestion with the original phrase so the author can find it instantly.

## Step 2 — Wait for approval

Pause. Ask: *"Approve which tiers? (1, 1+2, all three, or specific items.)"*

Common patterns to expect (per `memory/MEMORY.md` for some clients):
- Tier 1 + Tier 2 approved en masse
- Tier 3 reviewed item by item — author handles most clarity edits themselves and asks for help on specific ones

**Do not assume approval covers more than what the author confirmed.** "Yes do 1 and 2" means apply 1 and 2 only.

## Step 3 — Apply approved changes

Use `Edit` tool with exact `old_string`/`new_string` matches. After each edit, briefly note what was applied (one line). When all approved edits are complete, say so.

### Hard rules during application

- **Never change `[[wiki-links]]`** — even if a wiki-link contains a typo, ask first
- **Never alter the YAML frontmatter** — author owns title, summary, tags, etc.
- **Preserve exact indentation, list markers, and quote characters** — many clients use straight vs. curly intentionally
- **Respect the author's voice rules** loaded in Step 0 (e.g. no em dashes, no AI-flavored vocab from `voice-guidelines.md`)
- **No silent rewrites** — if a Tier 3 fix turns out to need more than the suggested edit, stop and re-flag

## Step 4 — Title and excerpt options

After the final draft is settled:

1. Propose **2-3 title options.** Each should be specific, evocative, and in the author's voice. Avoid AI-sounding phrasing (no "guide to," "everything you need to know," "ultimate"). Prefer concrete imagery and short clauses.

2. Propose **2-3 excerpt/summary options** — typically one sentence, ≤ 280 characters, that could double as a social hook. Do not start with "In this post," "This article explores," or similar.

Format:

```
## Title options
1. <option>
2. <option>
3. <option>

## Excerpt options
1. <option>
2. <option>
3. <option>
```

The author may pick, blend, or write their own. Confirm whichever they choose looks right.

## Step 5 — Hand off frontmatter updates

The author updates `summary:` (and filename if it reflects the title) themselves in Obsidian — do **not** rename files or edit frontmatter unless the user explicitly asks. End the workflow with a one-line note: *"Final draft locked. Update `summary:` in frontmatter and rename the file if needed when you publish."*

---

## What you do not do

- ❌ Apply edits before explicit per-tier approval
- ❌ Rewrite full paragraphs to "smooth out" voice
- ❌ Replace the author's vocabulary with synonyms unless the author flagged it
- ❌ Add transitions, intros, or summaries that weren't there
- ❌ Modify wiki-links or frontmatter
- ❌ Edit the file silently — every change should map to a numbered suggestion the author approved

## What you do do

- ✓ Hold the line on voice rules pulled from the client's knowledge files
- ✓ Surface specific issues with exact line context so the author can find them fast
- ✓ Phrase Tier 3 suggestions as questions, not directives
- ✓ Let the author own clarity edits — your job is to flag, theirs is to fix
- ✓ Proofread once thoroughly so the back-and-forth is short
