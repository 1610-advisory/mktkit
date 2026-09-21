# Film board — lookup

Why the first boards failed, what the 2026-08-28 sitting proved, and the rules a second model can apply without the chat history.

## Why v1–v2 failed and the sitting worked

| Miss | What happened | What works |
|---|---|---|
| Shape | Landscape three-column stats, empty ivory in the *middle* | 9:16. Type in the **safe band**. Empty well at the **bottom** for camera. |
| Chrome | Sticky 1610 header at `top: 0`; eyebrows sat under IG username | No sticky top bar. `--safe-top: 16vh` so the eyebrow clears Reels/Shorts UI. `--safe-right: 76px` for the like column. `--safe-bottom: 40vh` for captions + face. |
| Units | Bar labeled 69¢ / 31¢ on a $100,000 month | Say the unit you show. $69,000 to deliver, $31,000 left. |
| Chart | New bar each frame | **Accumulate.** Same bar, one new slice, one new color. The through-line *is* the lesson. |
| Copy | Punchlines, "six isn't magic", invented 35% margin goal | Client voice file + humanizer. No fake universal targets. "A contractor and a software shop shouldn't use the same target." |
| Cash | $18k leftover labeled cash flow | Leftover after overhead ≠ what the bank did. Principal, owner pay, a truck still leave. |
| Runway | Bank ÷ overhead only (52 ÷ 13 = 4 months) | Bank ÷ (overhead + **other cash that still leaves**). 52 ÷ 27 ≈ 2 months. |
| Cursor | System pointer in every frame | `cursor: none` on the page **and** hide cursor in Cap. |
| Camera | Circle bubble, bottom-right | Camera in the face well, **bottom-left**. Right is IG buttons. |
| Ground | Full-bleed ivory 9:16 | Ivory **page** on a peaceful photo **ground** (field, trees). Square page, not Cap's round card, no drop shadow. |

A 4:36 Cap take of this walk is a **source file**. Instagram Explore still prefers 15–90s. Do not reshoot to chase a clock. Atomize with `cut-video`. YouTube Shorts max 3:00; LinkedIn can take the full walk.

## Brand (read the client; 1610 defaults below)

From `knowledge/DESIGN.md` / `brand-identity.md`. 1610 live CSS (2026-08-27), not `/brand-guide` drifted swatches:

| Role | Hex | Use |
|---|---|---|
| Ivory page | `#FAF8F3` | Board surface |
| Cream | `#F5F0E8` | Leftover / bank sliver (outline so it reads) |
| Cream-warm | `#EDE6D9` | "Other cash" slice (owner pay, principal) |
| Hunter | `#2D4A3E` | Cost to deliver; figures |
| Sage | `#8B9E8B` | Overhead |
| Gold | `#B8965A` | 40px × 1px rule only. Never a fill. |
| Gold-ink | `#806436` | Mono eyebrows |
| Charcoal | `#1A2B23` | Body |
| Muted | `#66706B` | Secondary copy |
| Outline | `#E0DDD5` | Hairline on ivory. On a photo, charcoal at ~20% if cream vanishes. |

Type: Cormorant Garamond display, Source Sans 3 body, JetBrains Mono labels. Sentence case. Square corners. No Playfair on live 1610 pages.

## Ledger (worked example, dummy, 2026-08-28)

One month. Teaching only. Not a client's books.

```
Revenue                         100,000
Cost to deliver                  69,000   → 31% gross margin
Overhead (rent, software, admin) 13,000
Left after overhead              18,000   → P&L leftover, not cash
Other cash (principal, owner)    14,000   → 8,000 + 6,000 if you name them
What the bank did                +4,000   → cash flow
Cash in bank                     52,000
Monthly cash that still leaves   27,000   → 13 + 14
Runway                           ~2 mo    → 52 / 27
```

Checkable: 69+13+14+4 = 100. 18−14 = 4. 13+14 = 27.

## Graph rules

- **Stacked bar of one whole** (the month, the dollar). Widths = percentages of that whole.
- **Hairline ledger** for the paper frame.
- One new color = one new concept. Hunter → sage → cream-warm → cream.
- Labels live *under* the bar, not on sage/gold-muted fills.
- A 4% sliver will not hold a tick label; put dollars in the key.
- Skip the chart if a sentence is clearer.

## Frame recipe (CSS)

```css
html { scroll-snap-type: y mandatory; }
.frame {
  min-height: 100dvh;
  scroll-snap-align: start;
  scroll-snap-stop: always;
  padding: 16vh 76px 40vh 22px;
}
* { cursor: none !important; }
```

Eyebrow (mono, gold-ink, uppercase tracking) → one Cormorant line → 40px gold rule → the chart or table → one muted aside. Then empty well.

## Voice on the board

Short. He talks; the page is the prop. I-voice on founder boards, we-voice on firm boards. Contractions. No em dashes. No "thank you." No "it's not X, it's Y" closes. Banned words from the client file (1610: consulting/consultant, scorecard, scoreboard, clarity call).

## Cap

1080×1920 (or 1216×2160 class). Capture the page, not the whole desktop, unless the photo ground is the desktop and the ivory is a window — both are valid. Hide cursor. Camera in the well, bottom-left.
