---
title: "Branded HTML Reports"
description: "Render an analysis as a brand-themed self-contained HTML page, then optionally publish it to a host you configure"
category: workflow
last_updated: 2026-09-21
status: active
priority: medium
---

# Branded HTML Reports

When a client deliverable is substantive enough that a markdown file in the vault doesn't do it justice — Ahrefs baselines, SEO audits, monthly performance reports, brand reviews, content audits — render it as a brand-themed, **self-contained HTML file** saved next to the markdown source. Publishing is optional and uses whatever static host **you** already have.

This procedure is generic. Hostnames, DNS, access-control products, and credentials never belong in this public repo. Client-specific brand tokens and preferred publish URL live in each client's `knowledge/branded-reports.md` (private per-client repo).

---

## When to use this

- **Use** when the artifact would actually get viewed by the client team and benefits from looking like a deliverable instead of a notebook entry. SEO audits, Ahrefs baselines, monthly performance reports, brand audits, content strategy decks.
- **Skip** for internal-only working docs (briefs, content notes, planning), short summaries, or anything the client won't open. Markdown is faster and lives in the vault where edits compound.

The test: "Would I be embarrassed if the client saw this as a markdown file rendered in default note-app styles?" If yes — render it. If no — leave it as `.md`.

---

## Prerequisites

1. **Working analysis already complete** as a markdown file in the client folder (e.g., `research/ahrefs-baseline.md`). The HTML is the rendered presentation layer, not the source of truth.
2. **Client brand identity documented.** Hex colors + font choice. If the client has a brand guide PDF in `resources/`, read the Colors and Typography pages first.
3. **Per-client config file at `knowledge/branded-reports.md`** declaring brand tokens and (optionally) a publish URL pattern. Create it on first render if missing — see the per-client config template at the bottom of this doc.
4. **No operator infrastructure in this repo.** Do not write hostnames, IPs, zone IDs, account IDs, or emails into toolkit files. If you need to publish, read `REPORT_HOST_URL` / `REPORT_PUBLISH_COMMAND` from the environment (see Optional publish).

If brand tokens are missing, stop and resolve before generating HTML. Don't fake the colors.

---

## Output

**Always** write a self-contained HTML file next to the markdown (or under `clients/{slug}/research/{report-slug}.html`):

- Inline CSS. No CDN, no webfonts by URL, no images by URL, no `fetch`. Hosts (and this toolkit's own share hosts) often block those.
- `<meta name="robots" content="noindex, nofollow">` on every report unless the client asked for a public page.
- Inline SVG logo (or a typographic wordmark).

The markdown stays the source of truth. If insights change, update the `.md` first, then re-render the HTML.

---

## Optional publish (bring your own static host)

Rendering does not require a host. If the operator wants a URL, they set env vars locally (never committed):

| Var | Purpose |
|---|---|
| `REPORT_HOST_URL` | Base URL where reports should appear, e.g. `https://reports.example.com` or `https://{client-slug}.example.com` |
| `REPORT_PUBLISH_COMMAND` | A command that receives the HTML path. Example: `scp "$1" user@host:/var/www/reports/` or a small wrapper script. The skill substitutes the rendered file path. |

Suggested command shape:

```bash
# After the HTML exists locally:
if [ -n "${REPORT_PUBLISH_COMMAND:-}" ]; then
  # $1 = path to the self-contained HTML
  eval "$REPORT_PUBLISH_COMMAND" "clients/{slug}/research/{report-name}.html"
fi
```

URL after publish (if `REPORT_HOST_URL` is set):

| Pattern | When |
|---|---|
| `{REPORT_HOST_URL}/{report-slug}/` | Default. Each report is a subpath. |
| `{REPORT_HOST_URL}/` | First / only report for that client, if the host is already client-scoped. |
| A URL the operator pastes | When they already have a share host, object store, or CDN in mind. |

Do **not** provision DNS, TLS, reverse proxies, or access-control apps from this skill. Gate the page however your host already gates it (login, signed URL, obscure path). If those pieces are not set up, leave the file local and hand the operator the path.

---

## Canonical working example

To find a precedent, list `clients/*/research/*.html` and read the first one returned. Both the HTML and `knowledge/branded-reports.md` live in the client's private repo (gitignored from this public toolkit).

**When adapting for a new client, copy a working precedent and swap the brand tokens.** Building from a known-good file beats building from an abstract template — every block is already proven to render correctly with brand colors and respond on mobile.

---

## HTML structure conventions

The proven pattern. All client reports follow this:

```
<head>
  - System stack or locally-licensed faces (no remote font requests)
  - <meta name="robots" content="noindex, nofollow"> — these are private, never index
  - Inline <style> with CSS custom properties for brand tokens (see Brand Token Pattern below)
</head>
<body>
  <div class="banner">Internal · Team preview</div>
  <nav class="nav">
    - sticky, dark brand-color background, brand mark + section anchors + report date stamp
  </nav>
  <header class="hero" id="top">
    - dark-brand-color hero with eyebrow + h1 + dek + 4-cell metadata grid (Pulled / Refresh / Units / Scope)
  </header>
  <section id="summary" class="is-light">
    - executive summary: 5 numbered findings, max
  </section>
  <!-- alternating is-dark / is-light sections -->
  <!-- each section has: numbered eyebrow (01/09), h2, lede, then content (tables, metric grids, callouts) -->
  <footer>
    - dark-brand-color, brand mark + report stamp
  </footer>
</body>
```

### Required section components

- **Section header:** numbered eyebrow (`01 / 09`), h2 (uppercase), lede paragraph
- **Metric grid:** 4–6 KPI tiles for the snapshot section (Domain Rating, Traffic, etc.)
- **Tables:** brand-tinted thead, hover-tinted rows, `.is-self` row for highlighting the client's own data, `.num` class for right-aligned numerics
- **Callouts:** left-bordered with brand accent, used for "the single biggest finding" moments
- **Recommendations:** numbered list with KD/priority chips on the right side of each title

### Alternating dark/light pattern

Sections alternate `is-dark` (brand primary dark color background, light text) and `is-light` (brand cream/off-white background, dark text). This mirrors most modern brand guides' page-flow rhythm and gives natural visual chapter breaks without needing dividers.

---

## Brand token pattern

Every client gets six core CSS custom properties + their semantic aliases. Pull the exact values from the client's brand guide.

```css
:root {
  /* Primary brand */
  --brand-dark:       /* primary dark color — bodies/nav/footer background */
  --brand-dark-80:    /* 80% tint for borders on dark backgrounds */
  --brand-accent:     /* primary accent color — eyebrows, links, highlights, chips */
  --brand-accent-80:  /* 80% tint for on-dark accent text */
  --brand-secondary:  /* secondary brand color — for "medium priority" chips, links on light */
  --brand-light:      /* off-white / cream — light section background */
  --brand-light-deep: /* slightly darker version of light — callout background, table thead */

  /* Semantic aliases — never change these names, only the values they point to */
  --bg-canvas:       var(--brand-light);
  --bg-canvas-alt:   var(--brand-dark);
  --bg-surface:      var(--brand-light-deep);
  --fg-primary:      var(--brand-dark);
  --fg-on-dark:      var(--brand-light);
  --accent:          var(--brand-accent);
  --link:            var(--brand-secondary);
  --border-subtle:   /* a creme-deep / tan tone */
  --border-on-dark:  /* a 25% lighter brand-dark */

  /* Typography — Montserrat is the safe free default; substitute if the client has a paid display face */
  --ff-display: 'Montserrat', system-ui, sans-serif;
  --ff-body:    'Montserrat', system-ui, sans-serif;
}
```

If the HTML must stay self-contained for a strict CSP, either subset the face into a local `@font-face` (file already on disk) or use a system stack. Do not request fonts from a CDN.

Bold uppercase Montserrat 700–800 stands in cleanly for most paid display faces. If the client's body font is a serif, swap to a licensed or system serif.

**Logo as inline SVG.** Don't host PNG/SVG files for the brand mark. Inline an SVG in the nav and footer — fewer requests, scales cleanly, recolors trivially via `fill`. If the brand has a complex logo, fall back to a typographic wordmark (`{Client Name}` in display font + a secondary tagline in the accent color).

---

## Per-client config — `knowledge/branded-reports.md`

Each client using this pattern gets one config file. Template:

````markdown
---
title: "Branded HTML Reports Configuration"
description: "Brand tokens and optional publish notes for client-hosted HTML deliverables"
category: workflow
last_updated: YYYY-MM-DD
status: active
priority: medium
---

# {Client Name} — Branded HTML Reports

## Deployment

- **Local path:** `research/{report-slug}.html`
- **Publish URL pattern (optional):** `{REPORT_HOST_URL}/{report-slug}/` — only if the operator has set the env var
- **Access:** whatever the operator's host already uses. Do not invent a new gate from this file.

## Brand tokens

From {client brand guide source, e.g., "ClientBrandGuide.pdf in resources/"}.

```css
--brand-dark:       #XXXXXX;  /* Name from brand guide */
--brand-dark-80:    #XXXXXX;
--brand-accent:     #XXXXXX;
--brand-accent-80:  #XXXXXX;
--brand-secondary:  #XXXXXX;
--brand-light:      #XXXXXX;
--brand-light-deep: #XXXXXX;
```

## Typography

- **Display:** {Brand display font, e.g., "Fieldwork"}
- **Display free alternative (use this):** {e.g., "Montserrat"}
- **Body:** same family
- **Weights needed:** 400, 500, 600, 700, 800

## Logo

Inline SVG in nav + footer. Pattern from this client:

```svg
<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <!-- client-specific paths, using brand colors -->
</svg>
```

## Voice for HTML content

- Headlines: sentence case or all caps? (Reference voice-guidelines.md)
- Banned constructions: (carry over from voice-guidelines.md)
- Run all client-facing copy through `humanizer` before finalizing per project standard

## Reports rendered

| Date | Report | Local file | Source |
|---|---|---|---|
| YYYY-MM-DD | First report name | research/first-report.html | research/source.md |
````

---

## Anti-patterns

- **Don't generate HTML before reading the brand guide.** Stock-feeling colors and a generic system font undermine the whole reason to do this. If there's no brand guide, ask before generating.
- **Don't publish by default.** Local HTML is the deliverable. A URL is extra, and only if `REPORT_PUBLISH_COMMAND` (or an explicit operator request) says so.
- **Don't index the page.** `<meta name="robots" content="noindex, nofollow">` belongs in every report. These shouldn't surface in search.
- **Don't render the HTML in place of updating the markdown.** The markdown is the source of truth. If insights change, update the `.md` first, then re-render the HTML.
- **Don't hardcode credentials, hostnames, IPs, or zone IDs** into this repo or into the HTML.
- **Don't pull remote CSS, fonts, or images.** Self-contained or it will fail on a strict host.

---

## Cross-references

- `clients/{slug}/research/{report-slug}.html` — working examples (private per-client repo; list `clients/*/research/*.html` to find one)
- `clients/{slug}/knowledge/branded-reports.md` — first client config (private per-client repo, use as a template)
- Skill: `.claude/skills/branded-report/SKILL.md`
