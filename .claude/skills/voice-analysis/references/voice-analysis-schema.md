# Voice Analysis Schema

This is the exact structure of the output file at `clients/[client]/knowledge/voice-analysis.md`. Following this schema is what makes the analysis consistent across clients and reusable by other workflows (caption review, script proofreading, ad copy QA).

---

## File location

`clients/[client]/knowledge/voice-analysis.md`

It is a sibling to `voice-guidelines.md`. The two files have separate jobs and must not be merged.

---

## Required frontmatter

Use the toolkit knowledge file standard. Every field is required.

```yaml
---
title: "Voice Analysis: [Client Name]"
description: "Sentence-level voice evidence for [Client] — signature phrases, rhythm patterns, vocabulary, and what they don't say. All claims cited to source corpus."
category: voice
last_updated: YYYY-MM-DD
status: active
priority: high
---
```

`description` should make the file's job obvious from the index alone. Mention the corpus type (transcripts, blog, etc.) if it's narrow.

---

## Section order (do not reorder)

```
1. Source Corpus
2. Signature Phrases
3. Sentence Patterns
4. Vocabulary
   4a. Used
   4b. Avoided / Conspicuously Absent
5. Tone Variations
6. What They Don't Say
7. Notes on Confidence
8. Archive (only present after a re-run that replaced material)
```

---

## Section: Source Corpus

A table of every file analyzed. Without this, citations are unverifiable.

```markdown
## Source Corpus

| File | Type | Words | Date |
|------|------|-------|------|
| `clients/example-client/transcripts/2026-04-15.txt` | spoken | 4,120 | 2026-04-15 |
| `+/On Trust.md` | blog | 1,850 | 2026-03-02 |
| ... | ... | ... | ... |

**Total:** N files, ~X,XXX words, covering YYYY-MM-DD to YYYY-MM-DD.
```

If a single file contributes more than 30% of the total word count, flag it under "Notes on Confidence" — the analysis may be biased toward that one source.

---

## Section: Signature Phrases

A table sorted by frequency (highest first). At least one citation per phrase. Aim for 8-20 entries; fewer if the corpus is small. Do not pad.

```markdown
## Signature Phrases

| Phrase | Count | Sources | Notes |
|--------|-------|---------|-------|
| "brick by brick" | 7 | `+/On Trust.md:42`, `transcripts/2026-04-15.txt:[00:14:30]`, `+/Planning as a Tool.md:88` | Motif for incremental progress; usually closes a paragraph |
| "open to close" | 5 | `+/Open to Close.md:12`, `transcripts/2026-04-22.txt:[00:08:11]` | Working hours of his dad's shop, used as metaphor for full effort |
| ... | ... | ... | ... |
```

Cite at least 2 distinct sources per phrase. Order citations from highest-context source to lowest. The "Notes" column is one short clause — not a paragraph.

---

## Section: Sentence Patterns

Named structural patterns with cited examples. Each pattern gets a sub-heading, 2-3 quoted examples with citations, and a one-line note on use.

```markdown
## Sentence Patterns

### Short-then-long
A short declarative followed by a long expansive sentence.

- "I don't know." → "What are these old books going to have to do with economics of tomorrow?" (`+/Reading in the Woods.md:14`)
- "It worked." → "Six months later we had three new clients on retainer and one of them was paying twice what we'd quoted." (`+/Client Story.md:30`)

*Use:* Reset rhythm before introducing a new idea.

### Sentence-starting conjunctions
Sentences that begin with "And", "But", "So", "Because" — formal grammar would forbid these.

- "And just lived in that moment." (`+/On Family.md:22`)
- "But the bucket was already empty." (`+/On Trust.md:51`)

*Use:* Continues the prior thought conversationally; ~12% of sentences across the corpus.
```

Patterns to actively look for: short-then-long, sentence-starting conjunctions, parenthetical asides, em-dash use (or absence), one-sentence paragraphs, rule of three, repetition for rhythm, question-answer pairs, list-as-paragraph.

---

## Section: Vocabulary

Two lists. Both must be cited or quantified.

```markdown
## Vocabulary

### Used

| Word/Phrase | Occurrences | Example | Theme |
|-------------|-------------|---------|-------|
| "steward / stewardship" | 14 | "I help business owners steward well." (`knowledge/00-client-overview.md:8`) | Faith-aligned positioning |
| "bucket" | 6 | "Trust is accumulated slowly, like drops of water in a bucket." (`+/On Trust.md:18`) | Metaphor for trust accumulation |
| "open to close" | 5 | (see Signature Phrases) | Work-ethic metaphor |

### Avoided / Conspicuously Absent

Across ~XX,XXX words of corpus, these common AI/marketing terms do NOT appear. This list is the proofreader's checklist when reviewing copy generated for this client.

| Word/Phrase | Corpus Count | Notes |
|-------------|--------------|-------|
| "leverage" | 0 | Says "use" or "with" instead. |
| "unlock" | 0 | Says "find" or names the thing directly. |
| "delve" | 0 | Says "look at" or "talk about". |
| "in today's fast-paced world" | 0 | No throat-clearing openers. |
| em-dash ( — ) | 0 | Uses commas and short sentences for the same beat. |
| "elevate" | 0 | Says "improve" or names the outcome. |
```

Add or remove rows based on what's actually absent. Do not include words you didn't check — false negatives mislead later workflows. The default check list should include at least: leverage, unlock, delve, elevate, robust, seamless, navigate, in today's, em-dash, ellipsis, exclamation marks (frequency).

---

## Section: Tone Variations

How the voice shifts across contexts. One sub-heading per context where you have material. If a context has no source, omit it entirely (do not invent).

```markdown
## Tone Variations

### Long-form (blog)
- Average sentence length: 18 words
- First-person frequency: high (≈40% of sentences begin with "I")
- Opens with story 70% of the time, claim 30% of the time
- Example: "[exact opening sentence]" (`+/On Trust.md:1`)

### Short-form (social)
- Average sentence length: 11 words
- First-person frequency: high
- Punchier rhythm, more sentence-starting conjunctions
- Example: "[exact post]" (`outputs/content/2026-04-10-DS-02.md:18`)

### Spoken (transcripts)
- More incomplete sentences and self-corrections
- Repetitions for emphasis are more frequent ("brick by brick by brick")
- Example: "[exact transcribed line]" (`transcripts/2026-04-15.txt:[00:14:32]`)
```

Cite at least one example per context. The numbers (sentence length, etc.) should be computed from the corpus, not estimated. If you can't compute them, say "approximate" and explain why.

---

## Section: What They Don't Say

The most useful section for downstream proofreading. Each item is "*Word/phrase X does NOT appear*" with a one-line note on what they say instead, citing the substitute.

```markdown
## What They Don't Say

- **"Leverage"** does not appear. Says "use" instead: "use the planning meeting to..." (`+/Planning as a Tool.md:24`).
- **"Unlock"** does not appear. Names the thing directly: "the planning meeting changes how you see the year" (`+/Planning as a Tool.md:31`).
- **Em-dashes** ( — ) are not used. Uses commas and short sentences for the same beat: "It worked. Six months later we had three new clients..." (`+/Client Story.md:30`).
- **Throat-clearing openers** ("In today's fast-paced world", "It's no secret that") do not appear. Opens with a concrete moment instead: "We closed the shop the day before my wedding..." (`+/Coffee Shop.md:1`).
- **Exclamation points** appear only N times in XX,XXX words (rate: 0.0X per 1000 words). Effectively absent.
```

This list should grow over time as you find more "avoided" patterns. When merging a new run, add to this list rather than replacing it.

---

## Section: Notes on Confidence

Honest appraisal of the analysis quality. Helps future readers know how much to trust it.

```markdown
## Notes on Confidence

- **Corpus size:** XX files, XX,XXX words. Above the 5,000-word minimum.
- **Source balance:** Y% blog, Z% transcripts, W% social.
- **Gaps:**
  - No long-form spoken material from before 2026-02-01
  - Only 2 social captions in corpus — short-form tone notes are tentative
- **Run history:**
  - 2026-05-08 (initial) — seven blog posts + one transcript
  - 2026-06-15 (append) — added six new transcripts
- **Confidence:** Medium-high for blog patterns; lower for spoken/social until corpus grows.
```

---

## Section: Archive (only on re-runs)

If the user chose **Replace** or **Merge** mode, the previous analysis content goes here under a dated heading. Do not delete prior work — file it.

```markdown
## Archive

### 2026-05-08 — Original analysis (replaced 2026-06-15)

(Original content here, indented under the heading.)
```

---

## Append-mode rules

When `voice-analysis.md` already exists and the user chose **Append**:

1. Do not modify any existing sections.
2. Add a new top-level section named `## New Findings — YYYY-MM-DD` immediately above `## Notes on Confidence`.
3. Inside that section, repeat the sub-structure (Signature Phrases, Sentence Patterns, Vocabulary, etc.) — but populate only with NEW evidence not already present.
4. Update the `## Source Corpus` table to add the new files (mark them with the run date).
5. Update `last_updated` in frontmatter.
6. Add an entry under "Run history" in `## Notes on Confidence`.

## Merge-mode rules

When the user chose **Merge**:

1. For each existing signature phrase, update the count and append new citations.
2. For new signature phrases, insert them in frequency-sorted order.
3. For new sentence patterns, add a new sub-heading. Do not rewrite existing pattern descriptions.
4. For vocabulary, add new rows; do not remove existing rows.
5. Update `last_updated` and add an entry to "Run history".
6. Move any signature phrase whose count drops to <3 across the merged corpus to a "Demoted" subsection rather than deleting.

## Replace-mode rules

When the user chose **Replace**:

1. Move the entire current file content (everything except frontmatter) into `## Archive` with a dated heading.
2. Write the new analysis fresh above the archive.
3. Update `last_updated` and add an entry to "Run history".
