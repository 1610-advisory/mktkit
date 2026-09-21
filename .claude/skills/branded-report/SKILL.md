---
name: branded-report
description: >
  Render a client analysis as a brand-themed self-contained HTML report
  (optional publish to a host the operator already has). Use when the user
  says "render this as HTML", "make a branded report", "publish this audit",
  "host this as a deliverable", "ship this to the client portal", "deploy the
  report", "make this look like a deck", "I want a client-facing version of
  this", or a markdown analysis (Ahrefs baseline, SEO audit, brand audit,
  monthly performance, content strategy) is substantive enough a client would
  open the link. Also "this needs to look like an actual deliverable" or "we
  should send this to the team". Skip internal-only working docs (briefs,
  content notes, planning docs). Procedure is in
  `references/branded-html-reports.md`.
metadata:
  version: 1.1.0
---

# Branded Report

You are turning a client-facing analysis into a brand-themed HTML deliverable. The source of truth is the existing markdown analysis in the client's folder; the HTML is the rendered presentation layer. Publishing to a URL is optional.

Run `mkt-kit` first. Tokens and type from `knowledge/DESIGN.md` / `brand-identity.md`. Missing: ask and append `knowledge/_intake-log.md`. Do not invent a palette.

**Read `references/branded-html-reports.md` before doing anything else.** That file has the full procedure — HTML structure, brand token pattern, optional publish env vars, the per-client config template, and known gotchas. This skill's job is to recognize the trigger and route you there.

---

## Pre-flight check (do this every time)

Before generating HTML, confirm:

1. **Working analysis already complete** as a markdown file under `clients/[client]/research/` (or the appropriate subfolder). The HTML renders that — it is not the source of truth.
2. **Client brand identity documented.** Hex colors + typography choice. If the client has a brand guide PDF under their `resources/`, read the Colors and Typography pages first.
3. **Per-client config at `knowledge/branded-reports.md`** declaring brand tokens (and optionally a publish URL pattern). If missing, create it from the template at the bottom of `references/branded-html-reports.md` before publishing.
4. **No operator infrastructure in this repo.** Hostnames, IPs, zone IDs, account IDs, and emails do not belong in toolkit files. Optional publish reads `REPORT_HOST_URL` / `REPORT_PUBLISH_COMMAND` from the environment.

If brand tokens are missing, stop and resolve before generating HTML. Don't fake the brand colors.

---

## The "would I send this?" test

The reference file frames it bluntly — apply this before kicking off the workflow:

> "Would I be embarrassed if the client saw this as a markdown file rendered in default note-app styles?"
>
> If yes — render it. If no — leave it as `.md`.

If the user asked you to render something that fails this test, push back. Markdown in the vault is faster, edits compound, and most client deliverables genuinely don't need to be HTML. Reserve this skill for the substantive ones: SEO audits, Ahrefs baselines, monthly performance summaries the client team will actually open, brand audits, multi-page strategy decks.

---

## Public-repo security boundary (critical)

This toolkit repo is public; only `clients/*/` is gitignored. When working in this skill:

- **Never write specific IPs, zone IDs, account IDs, email addresses, or hostnames** into anything under `.claude/skills/` or `references/`.
- The per-client `knowledge/branded-reports.md` lives inside `clients/[client]/`, which IS gitignored — that's the right place for brand tokens and any publish URL the operator wants recorded.
- If you find yourself about to write a specific infra value into a public-repo file, stop and put it in env or in the client's private folder instead.

---

## High-level workflow

The full procedure lives in `references/branded-html-reports.md`. The rough shape:

1. **Read the reference file** end-to-end first time, or skim the section headings on subsequent runs.
2. **Find a canonical working example** — list `clients/*/research/*.html` and read one. Copy-and-swap-tokens beats build-from-template.
3. **Render the HTML** to a local file next to the markdown — match the proven structure (banner, sticky nav, dark/light alternating sections, numbered eyebrows, metric grid, brand-tinted tables, callouts, footer). Inline SVG logo. `<meta name="robots" content="noindex, nofollow">` always. Self-contained: no remote CSS, fonts, or images.
4. **Optional publish** only if the operator asked for a URL **and** `REPORT_PUBLISH_COMMAND` (or an equivalent they specify) is set. Otherwise hand them the local path.
5. **Record the local path** (and URL if published) in the client's `knowledge/branded-reports.md`.

Each step has gotchas documented in the reference. Read it; don't improvise.

---

## When to delegate

The HTML rendering itself is mechanical once the brand tokens and content structure are decided. After the strategic decisions are made (which precedent to copy, which sections to include, what the executive summary findings are), delegate the mechanical pass to a cheaper model if your harness supports subagents; otherwise run it inline. Keep the editorial decisions in the main thread.

---

## What this skill does not do

- Does not write the underlying analysis. That should already exist as markdown before you trigger this skill.
- Does not provision hosting, DNS, TLS, or access-control apps. Bring your own static host, or leave the file local.
- Does not require a URL. Local HTML is a complete deliverable.
