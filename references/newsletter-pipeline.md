# Newsletter Pipeline & Anti-Slop Copy Protocol

A client-agnostic framework for producing segmented, tape-grounded email newsletters that sound like real people talking and pass adversarial quality reviews.

---

## 1. Operating Model & Philosophy

### Markdown as Source of Truth
- The email marketing platform (Buttondown, Resend, Mailchimp, HubSpot) is delivery plumbing, not the home of the content.
- All newsletter issues live as version-controlled markdown notes in `outputs/newsletter/YYYY-MM-NL-NN-<slug>.md`.
- One note holds all segment variants for that issue, keeping messaging aligned while tailoring the angle to distinct audiences.

### The Tape Rule (Strict Factual Grounding)
- **A newsletter draft must never be written from memory, imagination, or uncommitted notes.**
- Every issue must cite committed transcript files under `transcripts/`.
- If the founder or subject-matter expert did not say it on tape, it cannot appear as a quote, diagnostic mechanism, or company policy.

### Senders Match Relationships
- Send from real humans or functional company addresses, not "The Marketing Team."
- B2B/contractor/partner lists should come from the business development or sales lead (e.g. the sales lead by name).
- Consumer/retail lists should come from the founder or company service address (e.g. the owner by name, or a service desk address).

---

## 2. The 5-Layer Anti-Slop Quality Stack

AI models naturally drift toward generic newsletter tropes: dramatic single-word openers, staccato punchlines, script-style dialogue tags, and formulaic transitions. To prevent this, every marketing repository runs a 5-layer enforcement stack:

```
[Write/Edit Copy] ──► [Layer 1: PostToolUse Hook Alert]
                              │
                      [Layer 2: 2-Step Humanizer Audit Loop]
                              │
                      [Layer 3: Deterministic lint-copy.py]
                              │
                      [Layer 4: Git Pre-Commit Hook]
                              │
                      [Layer 5: Adversarial Review (second model)] ──► Ready for Sign-Off
```

### Layer 1: PostToolUse Copy-Guard Hooks
- An optional PostToolUse-style hook in your harness (Claude Code hooks, a pi extension, or equivalent) detects edits to client-facing copy paths (`outputs/content/`, `outputs/newsletter/`, `outputs/blog/`, `outputs/email/`, `landing-pages/`).
- Injects a non-blocking prompt reminder forcing the model to run voice checks, execute the Humanizer audit, and run the linter before committing.

### Layer 2: The 2-Step Humanizer Audit Loop
Single-pass "make it human" prompts always fail because the model simply substitutes one AI trope for another. The model must run the adversarial 2-step audit loop:
1. **Audit Prompt:** *"What makes the below so obviously AI generated?"* (Forces the model to identify its own tells: em dashes, conversational formulas, symmetrical contrasts, rhetorical setups).
2. **Revision Prompt:** *"Now make it not obviously AI generated."* (Forces the model to strip the identified tropes and write with authentic human soul).

### Layer 3: Deterministic Copy Linter (`lint-copy.py`)
Never trust an LLM to self-police punctuation or vocabulary. The shared toolkit script `scripts/lint-copy.py` deterministically scans copy blocks for:
- **Em dashes (`—`):** Banned across client marketing copy (use commas, colons, or periods).
- **Script dialogue tags:** `Name: "..."` inside body text.
- **Essay quote introductions:** `In his words: "..."`
- **AI conversational formulas:** `"here is where things stand"`, `"here is how they actually run"`, `"here is a thing about"`, `"that's the whole story/email"`, `"this month:"`.
- **Symmetrical templates:** `"Whether X or Y"`, `"not only... but also"`.
- **Rhetorical question setups:** `"How much?"`, `"Planning a project?"`.
- **Banned AI vocabulary:** `delve`, `testament`, `pivotal`, `crucial`, `vital`, `robust`, `seamless`, `landscape` (abstract), `tapestry`, `holistic`, `foster`, `bolster`, etc.

Run it anytime:
```bash
python3 "$MKTKIT"/scripts/lint-copy.py outputs/newsletter/   # MKTKIT = your toolkit clone
```

### Layer 4: Git Pre-Commit Hook
Every client repository configures `.githooks/pre-commit` to run `lint-copy.py` against all staged copy in `outputs/newsletter/`, `outputs/content/`, and `outputs/blog/`. If any banned word or trope is detected, the commit is blocked with line numbers and snippets.

### Layer 5: Adversarial Review Seat (a second model family)
Before sending or requesting client sign-off, run a read-only adversarial review using a different model family (e.g. Grok or GPT through the pi agent, or any second harness you have):
- Audits tape fidelity (detects hallucinated diagnostics, unhedged numbers, or misattributed statements).
- Checks voice authenticity (verifies whether the writer sounds like the actual person on tape).

---

## 3. Tape Fidelity: The Rules of Authentic Quoting

Adversarial reviews consistently catch two major writing defects:

### Defect A: "Terrified Quote-Splicing"
When writers are told never to misquote the client, they often resort to chopping up transcript sentences and dropping them into quotes inside normal narrative paragraphs:
- *Bad (script tag):* `Owner: "They're next day inspections, we can schedule those right away."`
- *Bad (essay tag):* `In his words: "That way there's no surprises and our price is our price."`
- *Bad (stranded quote):* `The estimator builds his numbers from the site. "We're going out and we're doing site visits."`
- *Good (woven prose):* `When the owner estimates a job, he starts with a full takeoff from the plans. His rule is simple: that way there are no surprises, and our price is our price.`

### Defect B: "Forensic Fabrication"
Writers often invent ungrounded technical details to make copy sound "punchy" or "forensic" (e.g. claiming breakers tripped instantly, inventing specific wire types, or adding unmentioned schedule hold-ups).
- **Rule:** If the expert didn't name the mechanism on tape, do not invent it.
- **Preserve Hedges:** If the founder said *"I haven't done that math in a long time, but it's probably around 70%"*, keep the hedge. Stripping the hedge into a flat corporate claim (*"cuts power draw by 70%"*) destroys reader trust.

---

## 4. Setup Runbook for a New Marketing Client

Follow these steps to stand up this pipeline for any new client:

### Step 1: Initialize the Newsletter Directory & Template
In the client's marketing repo:
```bash
mkdir -p outputs/newsletter
cp "$MKTKIT"/templates/newsletter-note.md outputs/newsletter/_template.md
# or let the scaffolder do steps 1-3: python3 "$MKTKIT"/scripts/scaffold-pipeline.py newsletter
```

### Step 2: Create Client-Specific Configuration
Create `knowledge/newsletter-pipeline.md` in the client repository defining the client-specific values:
```markdown
---
title: Newsletter Pipeline Configuration
client: "[client-slug]"
category: strategy
status: active
---

# Newsletter Pipeline Configuration: [Client Name]

Reference: $MKTKIT/references/newsletter-pipeline.md

## Audience Segments
- **[segment-1-id]** ([Segment Name]): [Target audience description, pain points, core offers]
- **[segment-2-id]** ([Segment Name]): [Target audience description, pain points, core offers]

## Senders & Voices
- **[Sender 1 Name]** (<email@domain.com>): [Voice profile, relationship to list, topics covered]
- **[Sender 2 Name]** (<email@domain.com>): [Voice profile, relationship to list, topics covered]

## Review & Publishing Protocol
- Review channel: [Gated dashboard share link / Google Doc / etc.]
- Sending tool: [Buttondown / Resend / Mailchimp]
- Sign-off requirement: [Founder + Account Lead approval required before send]
```

### Step 3: Wire the Pre-Commit Hook
In the client's marketing repo:
```bash
mkdir -p .githooks
cat > .githooks/pre-commit << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

STAGED_COPY=()
while IFS= read -r f; do
  [ -z "$f" ] && continue
  base="$(basename "$f")"
  case "$base" in README*|_template*|TEMPLATE*) continue ;; esac
  case "$f" in
    outputs/newsletter/*.md|outputs/blog/*.md|outputs/content/*.md)
      STAGED_COPY+=("$f")
      ;;
  esac
done < <(git diff --cached --name-only --diff-filter=ACM)

if [ ${#STAGED_COPY[@]} -gt 0 ]; then
  LINTER="${MKTKIT:-$HOME/mktkit}/scripts/lint-copy.py"
  if [ -f "$LINTER" ]; then
    echo "Running anti-slop copy linter on staged files..."
    python3 "$LINTER" "${STAGED_COPY[@]}"
  fi
fi
exit 0
EOF
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

### Step 4: Issue Production Workflow
For every newsletter issue:
1. **Identify Source Tape:** Pin the committed transcript under `transcripts/`.
2. **Draft Issue:** Copy `outputs/newsletter/_template.md` to `outputs/newsletter/YYYY-MM-NL-NN-<slug>.md` and draft each segment variant.
3. **Run Humanizer 2-Step Loop:** Ask *"What makes this obviously AI generated?"*, then revise with *"Now make it not obviously AI generated."*
4. **Run Linter:** Execute `python3 "$MKTKIT"/scripts/lint-copy.py outputs/newsletter/<file>.md`.
5. **Run Adversarial Review:** Dispatch a read-only review to a second model family to verify tape fidelity.
6. **Publish a Review Link:** Render clean HTML and share it through whatever review surface the client already uses.
7. **Client Sign-Off:** Review with client lead before hitting send.
