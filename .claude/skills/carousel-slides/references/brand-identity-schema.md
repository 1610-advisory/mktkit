# Brand Identity Schema

Each toolkit client should have a `knowledge/brand-identity.md` file that the `carousel-slides` skill (and any future visual skills) can read to apply brand-consistent typography and color. The skill creates this file interactively the first time it runs for a client.

## File Location

`clients/[client-name]/knowledge/brand-identity.md`

## Required Schema

```yaml
---
title: "Brand Identity — [Client Name]"
description: "Color palette, typography, logo, and visual usage rules for any branded output."
category: voice
last_updated: YYYY-MM-DD
status: active
priority: high
---

# Brand Identity — [Client Name]

## Color Palette

| Token | Hex | Use |
|-------|-----|-----|
| `background` | `#FAF8F3` | Default surface (ivory/paper) |
| `surface` | `#F5F0E8` | Card backgrounds, lighter accents |
| `surface-warm` | `#EDE6D9` | Tertiary surface |
| `primary` | `#5C2A2A` | Primary brand mark, buttons |
| `primary-dark` | `#3A1A1A` | Darker primary, deep accents |
| `accent` | `#B8965A` | Highlights, italic accent words |
| `accent-soft` | `#D4B884` | Lighter accent for text on dark photos |
| `foreground` | `#2C2C2C` | Body text on light surfaces |
| `foreground-on-dark` | `#FAF8F3` | Body text on dark photo overlays |

## Typography

| Role | Family | Weights used | Source |
|------|--------|--------------|--------|
| Serif | `Playfair Display` | 400, 500, 600 + italic | Google Fonts |
| Sans | `Source Sans 3` | 300, 400, 500 + italic | Google Fonts |
| Mono (optional) | `JetBrains Mono` | 400 | Google Fonts |

## Photo Overlay

When using photos as backgrounds with text on top, apply:

- **Default**: vertical gradient `rgba(20, 15, 12, 0.55)` top → `rgba(20, 15, 12, 0.78)` bottom
- **Light photos** (sky, snow, bright outdoor): bump to `0.62 → 0.85`
- **Dark photos** (interiors, night): reduce to `0.40 → 0.65`
- Add a radial vignette: `radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.55) 100%)`

## Voice on Visuals

- **Accent usage**: italic + accent-color on 1-3 most important phrases per slide, never full sentences
- **Em dashes**: [allowed | disallowed] (mirror the rule in `voice-guidelines.md`)
- **Curly vs straight quotes**: `“ ”` and `’` (always curly)
- **Number formatting**: e.g. `4:30 a.m.` not `4:30AM`

## Logo & Marks (optional)

| Asset | Path | Use |
|-------|------|-----|
| Wordmark | `assets/wordmark.svg` | Footer of decks, signature |
| Glyph | `assets/glyph.svg` | Small lockup, watermark |

## Handle / Watermark

- **Public handle for slide footer**: `@yourhandle`
- **Domain to surface in CTA slides**: `yourdomain.com`

---

## Source

[Where these values came from — e.g. "Pulled from globals.css of yourdomain.com Next.js repo on YYYY-MM-DD" or "Established via Brand Discovery interview with Client on YYYY-MM-DD"]
```

## Editing rules

- The skill reads this file every time it generates a carousel — keep it current
- When the client's brand evolves (new colors, font swap, logo update), update this file FIRST, then re-render any active carousels
- Hex values only — no `oklch()`, `hsl()`, or named colors. Convert at write time so tools (Playwright, ImageMagick) handle them consistently
- If a value is genuinely missing or unknown, leave it blank rather than guessing — the skill will ask the user the next time it runs
