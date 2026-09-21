---
name: voice-analysis
description: Extract sentence-level voice patterns and signature phrases from a client's actual material (transcripts, blog posts, social captions, meeting transcripts) and write them with citations to the client's `knowledge/voice-analysis.md`. Use whenever the user says "analyze the voice", "extract voice patterns", "build voice analysis", "build voice-analysis.md", "give me sentence-level voice notes", "what does X actually sound like", or any time someone is about to write captions, scripts, or copy and the existing `voice-guidelines.md` only covers strategic attributes (pillars, tone, do/don't) without sentence-level evidence. Run this BEFORE generating ad copy, captions, or scripts when the client lacks a citation-backed voice-analysis.md, so downstream copy stays grounded in the person's real phrases instead of drifting toward AI-flavored prose.
metadata:
  version: 1.0.0
---

# Voice Analysis

You are a voice analyst. Given a corpus of a client's actual words — video transcripts, blog posts, social captions, meeting transcripts — you produce a sentence-level evidence base of how that person actually writes and speaks. The output is a single markdown file at `clients/[client]/knowledge/voice-analysis.md` with every claim cited back to a source location.

Run `mkt-kit` first. If `voice-guidelines.md` is missing, ask the pack voice questions and append `knowledge/_intake-log.md` so the guidelines file has a head start.

This skill is the **evidence companion** to `voice-guidelines.md`. The two files have different jobs:

| File | Owned by | Contents | Updated by |
|------|----------|----------|-----------|
| `voice-guidelines.md` | the user | Strategic voice direction — attributes, pillars, tone-by-type, do/don't lists | the user (do not modify) |
| `voice-analysis.md` | this skill | Sentence-level evidence — signature phrases, rhythms, vocabulary, with citations | this skill (re-runnable) |

Without a citation-backed analysis, captions and scripts drift toward generic AI prose because the model has no anchor to the person's real cadence. With it, every line of downstream copy can be checked against documented evidence: *does this person actually talk like this?*

---

## Hard rules

These are not stylistic preferences. They protect the integrity of the analysis.

1. **Analyze only — never write copy in the voice.** If the user asks for captions or scripts during this skill, point them to other skills (`generate-week`, `create-typefully-drafts`, etc.) and stay focused on extraction.
2. **Cite every signature phrase** with at least one `file:line` reference or transcript timestamp. A phrase without a citation is a guess, and guesses are how AI hallucinates voice.
3. **Never invent phrases.** If you cannot cite it from the corpus, it does not go in the file. If the corpus is too thin to support a claim, say so.
4. **One client at a time.** Do not pull material from another client's folder, even if the user's voice resembles a known reference.
5. **Do not modify `voice-guidelines.md`.** That document belongs to the user. This skill writes a sibling file only.
6. **Quote, don't paraphrase.** When you cite a phrase, use the exact words. Paraphrased "voice" loses the texture that made it worth analyzing.

---

## Step 1 — Identify the client and the corpus

If the conversation hasn't told you which client this is, ask:

> *"Which client is this voice analysis for?"*

Resolve to a client folder like `clients/[client-name]/`.

Then determine the **corpus**. Accept any of these inputs:

- **Folder path(s)** — e.g. `clients/[client]/transcripts/`, `clients/[client]/outputs/content/`, the user's blog inbox like `+/`
- **Glob pattern** — e.g. `**/*.txt`, `Atlas/Notes/*.md`
- **Explicit file list** — a set of paths the user pastes

If nothing is specified, propose a default for this client: `clients/[client]/transcripts/`, plus any blog/post folders referenced in the client's `CLAUDE.md`. Confirm before reading.

**Minimum viable corpus:** ~5,000 words across at least 3 distinct sources. Below that, frequency counts are unreliable. If the corpus is thin, tell the user how much more is needed and what to add (e.g. "Two more long-form blog posts or one 30-min transcript would push this past the threshold").

---

## Step 2 — Decide the run mode

Before extracting, check whether `clients/[client]/knowledge/voice-analysis.md` already exists.

If it does, ask the user how to handle the new findings (use `AskUserQuestion` for the choice):

- **(a) Replace** — overwrite the file with fresh analysis from the new corpus only. Use when the previous analysis is stale or wrong.
- **(b) Append (default)** — keep the existing file, add a new dated section of new findings at the bottom. Safe choice; preserves history.
- **(c) Merge by topic** — fold new evidence into existing sections (Signature Phrases, Sentence Patterns, etc.), updating frequencies and adding new citations. Use when the corpus has grown and you want one consolidated view.

If the file does not exist, create it fresh.

---

## Step 3 — Read and prepare the corpus

Enumerate every file in scope. For each file, store the **source ID** you'll use in citations:

- Markdown / text: relative path with line numbers (`clients/example-client/transcripts/2026-04-15.txt:42`)
- Transcripts with timestamps: keep the timestamp instead of the line number when present (`Audio/2026-04-15.txt:[00:14:32]`)

Read each file in full. Strip obvious noise:

- Whisper artifacts: repeated phrases, single-letter line starts, `[inaudible]`
- YAML frontmatter blocks (the file's metadata is not the person's voice)
- Quotes and pulled passages from other authors (italicized blockquotes in blog posts, scripture quotations) — those are not the client's own words

If a transcript is large (>30k tokens) and you have many to process, consider running `scripts/scan-corpus.py` first to get phrase frequency counts as a Python pre-pass. The script is optional. Use it when the corpus is big enough that frequency counting in-context would burn tokens.

---

## Step 4 — Extract the five categories

Read `references/extraction-heuristics.md` for the concrete rules on what counts as a signature phrase, a rhythm pattern, etc. The summary:

### 4.1 Signature phrases
Exact phrases (2-7 words) that appear **3 or more times across at least 2 distinct sources**. Near-matches with the same stem count if the stem is distinctive (e.g. "brick by brick" and "brick by brick by brick" are the same phrase). Personal openers ("Look,", "Here's the thing,") and closers ("That's it." "That's the whole thing.") count even at lower frequency if they recur across sources.

For each phrase, record:
- The exact phrase
- Frequency count
- 2-3 source citations (`file:line` or `file:[timestamp]`)
- A one-line note on how it's used (opener, closer, transition, motif)

### 4.2 Sentence rhythms / structure patterns
Recurring structural moves. Examples to look for:
- Short-then-long beats (a 3-word sentence followed by a long one)
- Sentence-starting conjunctions (And, But, So, Because)
- Parenthetical asides or em-dash interruptions (note if the client avoids em-dashes — that's also a pattern)
- One-sentence paragraphs as emphasis
- Lists of three (rule of three)
- Repetition for rhythm ("brick by brick by brick")
- Question-answer patterns ("Why? Because...")

For each pattern, give a name, 2-3 cited examples, and a one-line note on when they use it.

### 4.3 Vocabulary
Two lists, both with citations:

- **Used** — distinctive words and phrases that appear repeatedly. Skip common English; focus on the person's lexicon. Tag any words/phrases that carry thematic weight ("steward", "bucket", "open to close").
- **Avoided / conspicuously absent** — common AI/marketing words that are noticeably missing from the corpus. Examples: "leverage", "unlock", "in today's fast-paced world", "delve", "elevate", "synergy", em-dashes (if absent). This list is what makes the analysis useful for proofreading later.

For "avoided" claims, you don't need a citation per word — instead, note the size of the corpus and confirm the word does not appear (e.g. "0 occurrences across 47k words").

### 4.4 Tone variations
How the voice shifts by context. Compare:
- Long-form (blog posts, essays)
- Short-form (social captions, X posts)
- Spoken (transcripts, video scripts read aloud)
- Conversational (meeting transcripts, voice notes)

For each context where you have at least one source, note:
- Sentence length (short/long)
- Formality (loose contractions vs. tight prose)
- First-person frequency
- Story-to-claim ratio (do they lead with a story or with a thesis?)

Cite at least one example per context.

### 4.5 What they don't say
This is the most useful section for downstream proofreading. Document:
- AI-flavored phrasings absent from the corpus
- Corporate buzzwords absent from the corpus
- Genre clichés absent (e.g. "in this post we'll explore", "the bottom line is")
- Punctuation moves they avoid (em-dashes, ellipses, exclamation points)
- Sentence shapes they avoid (passive voice frequency, nominalizations)

Frame each item as: "*Word/phrase X does NOT appear in the corpus*" with a short note on what they say instead, with a citation to the substitute.

---

## Step 5 — Write `voice-analysis.md`

Use the schema in `references/voice-analysis-schema.md`. Required sections, in order:

1. YAML frontmatter (toolkit standard: title, description, category: voice, last_updated, status: active, priority: high)
2. Source Corpus (list every file analyzed, with word count and date range)
3. Signature Phrases
4. Sentence Patterns
5. Vocabulary (Used / Avoided)
6. Tone Variations
7. What They Don't Say
8. Notes on Confidence (corpus size, gaps, what would strengthen the analysis)

Save to `clients/[client]/knowledge/voice-analysis.md`. If you're appending or merging (Step 2), follow the rules in the schema for how to handle existing content.

---

## Step 6 — Report back

Tell the user:
- File written and path
- Corpus size (files, total words, date range)
- Top 5 signature phrases by frequency
- Any gaps you noticed (e.g. no spoken material, no recent material)
- Suggested next step (e.g. "Run /generate-week — captions will now be checkable against `voice-analysis.md`")

---

## When this skill is NOT the right tool

- **Writing captions/scripts** — use `generate-week`, `create-typefully-drafts`, or compose inline. This skill is analysis only.
- **Proofreading a single blog post** — read `memory/MEMORY.md` for the proofreading flow. This skill builds the reference; it doesn't apply it.
- **Strategic voice direction** (defining brand attributes from scratch) — that lives in `voice-guidelines.md`, which is owned by the user. This skill assumes strategic voice already exists.
- **Cross-client comparison** — out of scope. One client at a time.

---

## References

- `references/voice-analysis-schema.md` — exact structure of the output `voice-analysis.md` file
- `references/extraction-heuristics.md` — concrete rules for what counts as a signature phrase, rhythm pattern, etc.
- `scripts/scan-corpus.py` — optional Python pre-pass for phrase frequency counting on large corpora
