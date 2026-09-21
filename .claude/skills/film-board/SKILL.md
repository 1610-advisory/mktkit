---
name: film-board
description: >
  Build a 9:16 scroll-snap HTML board an owner talks over in Cap: one claim
  per frame, accumulating charts, a dummy ledger that reconciles, Reels safe
  band, current-client brand tokens. Use when the user says "film board",
  "make the HTML for the reel", "scroll explainer", "Cap board", "talking-head
  HTML", "9:16 board", "educational reel page", or wants a page to walk while
  recording phone-vertical. Also fire before a Cap sitting when the topic is
  a number-story (cash, margin, seats, a process).
metadata:
  version: 1.0.0
---

# Film board

You are building a **phone-vertical talk-over page**: one HTML file, scroll-snap frames, dummy numbers that stay honest, brand from the current client. Record in Cap. Cut later (`cut-video`). Do not film twelve separate shorts.

**Any model.** This file is the whole procedure. No Claude-only tools. Read paths, write HTML, screenshot at 1080×1920.

Canonical look + failure log: `REFERENCE.md`. Worked example (1610, 2026-08-28): the current client's `outputs/film-boards/` if present.

## Preflight

Run `mkt-kit`. Read `DESIGN.md` / `brand-identity.md`, voice, personas, overview. Missing file: ask the pack questions, append `knowledge/_intake-log.md`, continue on those answers for this run. Do not invent a palette. Fonts: if the display/body families are not on disk, fetch into `resources/fonts/` per `mkt-kit/REFERENCE.md` before the HTML `@font-face`.

## Ledger first

Before any HTML, write a **one-month dummy ledger** in the reply (and as an HTML comment). Every later frame is a view of this month. Checkable: every dollar on screen is in the ledger; the leftover, the cash that still leaves, and the bank movement are three different numbers when they are three different things.

Invented industry-wide targets (a 35% margin goal, a magic six months) stay out. A target that depends on the kind of business is said that way, or omitted.

## Pedagogy (the walk)

One topic. Frames in this order, skip only a frame that does not apply:

1. **False belief** — the number people watch that does not answer the question.
2. **The few numbers that do.**
3. **First split** — one chart of the whole (stacked bar of one month, or a three-row ledger).
4. **Accumulate** — same chart, one new slice, one new color. Never replace the chart.
5. **The catch** — what the first statement missed (P&L leftover vs bank, etc.).
6. **The formula** — the division or the walk they can repeat.
7. **Paper** — the same month as a table they could copy.
8. **Monday** — the action. No thank-you.

Graphs: stacked bar of one whole; hairline ledger. No pie, no 3D, no dual axis, no chart that is not the argument.

## HTML

Single file at `outputs/film-boards/YYYY-MM-DD-<slug>.html`. Inline CSS. Google fonts from DESIGN.md. `cursor: none !important` on `*`.

- Canvas: 9:16. Cap window 1080×1920 (or 1080×1920-class).
- **Safe band:** content in `--safe-top: 16vh` / `--safe-bottom: 40vh` / `--safe-right: 76px` / `--safe-left: 22px`. Eyebrow is inside the band on every snap. No sticky header at `top: 0`.
- Each `.frame` is `min-height: 100dvh; scroll-snap-align: start`. One claim. Face well is empty ivory (or photo ground showing through).
- Page is the brand surface (ivory/paper). Optional photo is the **ground** behind/around it, not a full-bleed texture under type. Square corners. Accent is a 40px × 1px rule, never a fill. Border token from DESIGN.md (`#E0DDD5` on 1610).
- Labels in the unit you will say ($69,000 not 69¢ when the month is thousands).

## Done when

- [ ] Ledger comment in the HTML matches every on-screen figure.
- [ ] 1080×1920 screenshot of frame 1: eyebrow fully visible, bottom ~40% empty for camera.
- [ ] Scroll through every frame; nothing sits under where IG chrome/buttons will be.
- [ ] Copy is I-or-we per the client's voice file; humanizer passed; no punchline close.
- [ ] User can record: hide Cap cursor too; camera in the face well; bubble **bottom-left** (IG buttons eat the right).

Do not cut the take in this skill. After a sitting, `cut-video` atomizes. A 4-minute walk is the source, not a failed Reel.
