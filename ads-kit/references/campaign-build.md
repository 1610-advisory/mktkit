<!-- Vendored from https://github.com/Midnight-Farmer/boring-marketing-skills (fork of https://github.com/boringmarketer/boring-marketing-skills, commit 7c6678c), skills/paid-ads/SKILL.md. MIT License, Copyright (c) 2026 Boring Marketing, LLC. See ../THIRD_PARTY_NOTICES.md. Excerpt: the section "Mode 1: CAMPAIGN BUILD (default)" only; text unmodified. -->

> **ads-kit note:** read this as a playbook. In ads-kit the measure is the CRM-qualified lead (cost per qualified lead from the business's own records), not the platform's conversion count.
> The ads-engineer never writes to an ad account itself: money changes go only through the mktdata change queue (`propose_change`), see `change-queue.md`.
> Paths like `./campaigns/<name>/` map to `tracking/ads/campaigns/<name>/` in the business repo. The ads-kit naming rule (`naming.md`) overrides the UTM table here: `utm_content` is the content_id.
> Slash-command names (`/performance-review`, `/creative` and the like) and paths such as `references/...` point at the source library's skills, which ads-kit does not ship.

## Mode 1: CAMPAIGN BUILD (default)

### Phase 1: The matrix is the plan

Read `./campaigns/<name>/ad-matrix.json` (and `ad-matrix.md` for the human-readable
detail). This is the shared contract (`start-here/references/schemas/ad-matrix.schema.json`):

- **Cells** `MA-H{1-4}-{A-C}`: hooks H1 `direct`, H2 `question`, H3 `proof`,
  H4 `contrarian`; formats A `static`, B `video`, C `carousel`. Each cell carries hook
  text, a visual concept, primary text, and a CTA.
- **Never rename or invent cell IDs.** The ID is the thread that connects matrix →
  copy → asset filename → UTM → /performance-review. Tolerate field-name variants in
  older matrix files; the IDs are non-negotiable.

If no matrix exists, two routes:

- **Stakes are real** (new product, meaningful budget, positioning unsettled) → route to
  `/positioning-angles`. Angles built from competitive research and VoC beat angles
  improvised here; the matrix it saves is better fuel.
- **Speed matters and positioning.md has a chosen angle** → build a quick matrix inline:
  derive the 4 hook rows from the chosen angle, pick 2 formats the budget supports
  (usually static + video), and **save it** as `ad-matrix.json` + `ad-matrix.md` under
  `./campaigns/<name>/` using the same taxonomy and cell IDs before writing any copy.
  An unsaved matrix breaks the downstream contract.

**Cell selection.** Load `references/ads-judgment.md` now; the budget math there
decides how many cells this account can honestly test. Default is NOT all 12. Under
roughly $50/day, pick 4-6 cells. We test in this order: angles (the reason to buy), then
formats, then hooks. We settle what the ad says before how it is packaged, and save hook
rewrites for tuning an ad that already works. If the angle is unproven and the budget is
small (under roughly $50/day), round 1 puts one angle in each hook row and holds one
format so the read is clean, a documented deviation in the matrix's `test_plan`; the
batch's other formats ship in round 2 behind the winning angle. With budget for the full
batch (the diversity rule in creative step 3), run the mixed batch and read results by
angle first, then by format, and say in the plan that round 1 mixes the two. With a proven angle, cover at least 3 hook types before adding a second
format of the same hook. The batch plan and its format mix, mapped onto cell IDs, are in
`${CLAUDE_SKILL_DIR}/../creative/modes/ad-creative.md` (step 3), and the formats themselves in
`${CLAUDE_SKILL_DIR}/../creative/references/ad-formats.md`. Write
which angles, hooks and formats go first, and why, into the plan in plain words; mark
the rest `planned` in `ad-matrix.json` for the next round.

### Phase 2: Campaign structure

Structure follows budget, not org-chart ambition. In the Advantage+/Performance Max
era, consolidation beats fragmentation: the algorithm learns per ad set, and an ad set
split too thin never exits learning. The table below is a starting structure; judgment
adjusts it for the offer and the account's history.

| Daily budget | Structure |
|---|---|
| Under $50/day | 1 campaign, 1-2 ad sets, 3 ads each (4-6 cells total) |
| $50-150/day | 1 campaign, 2-3 ad sets, 3-4 ads each (6-9 cells) |
| Over $150/day | 2 campaigns max (prospecting + retargeting); resist further splits |

### Small budgets: one campaign that can learn

This section applies to any account with fewer than about 30 conversions a month per
campaign, local or online. Load the "Small-budget structure" section of
`references/ads-judgment.md` for the detail.

Bid strategies learn mostly from each campaign's own conversions. Split a small account
into several campaigns and every piece sits below what it needs to learn, permanently.
The default is one campaign that can learn; split only when two pieces truly need separate
budgets and each would still reach about 30 conversions a month.

- **Local case.** A low-volume local business ran one broad campaign covering all its towns. Split into three town-by-town campaigns, the same money cost several times as much per conversion. The split was reverted.
- **Online example (illustrative).** A store at say 40 purchases a month splits into
  four product-line campaigns: about 10 each, none able to learn. One campaign with the
  product lines as ad groups (Search) or asset groups (Performance Max) pools the signal.
- **Ad groups don't split the learning; campaigns do.** Themes, services and product
  lines belong in ad groups. Campaigns are for budgets that must be controlled separately.
- **Read impression share before blaming structure.** If the one campaign loses a large
  share of impressions to budget, the constraint is money, not targeting.

Before launch, check the account counts real leads (`/google-ads-tracking`, or `/meta-ads`
section 7 for Meta). A campaign optimizing toward a broken or rare signal fails whatever
the structure.

**Audience guidance.** Broad targeting + creative-as-targeting is the default: the hook
selects the audience, and the platform's delivery system finds the people who respond.
Interest-stack micro-targeting fights the delivery system and fragments signal. The
exceptions that still earn a constraint: LinkedIn firmographics (job title/company size is
the product there), retargeting audiences, and hard geo/language limits. See
`references/ads-judgment.md` for the current platform doctrine.

**Search is different.** Google Search and PMax key on intent, not audience, and the
matrix's format axis collapses: a Search campaign tests hooks only. Map cells to hook
rows (`MA-H1` … `MA-H4`) and write one RSA per ad group theme, with headline groups
carrying the hook variants.

**UTM conventions.** These are what let /performance-review map results back:

| Parameter | Value |
|---|---|
| utm_source | `meta` / `google` / `linkedin` / `tiktok` |
| utm_medium | `paid` |
| utm_campaign | `<campaign-slug>` (matches the `./campaigns/<name>/` slug) |
| utm_content | `<cell-id>-v<n>` (e.g. `MA-H2-B-v1`; Search uses `MA-H2-v1`) |
| utm_term | search keyword (Google Search only) |

Name the ads inside each platform by cell ID too. Exports then map to cells even when
UTMs get stripped.

### Phase 3: Platform copy per cell

Load `references/platform-specs.md` first and check its freshness header; if stale,
refresh per its instruction before writing. Apply `voice-profile#voice-summary`. Ad copy
compresses the voice but never contradicts it. Pull verbatim audience pain/desire
language from `audience.md` (and positioning.md's VoC bank). The hook in the
customer's own words pre-tests itself.

For each selected cell, write:

- **Meta**: primary text at two lengths (a short version where the hook lands inside
  the ~125 visible characters, and a longer ~300-500 character version for readers who
  expand), 2 headline options (≤40 chars; the claim compressed, not a label), optional
  description (~30 chars). The cell's hook_type governs the opening line, not the
  product name.
- **Google RSA**: 15 headlines (≤30 chars) written in four interchangeable groups:
  hook/keyword, benefit, proof, CTA. Google assembles up to 3, so every headline must
  combine sensibly with any other. 4 descriptions (≤90 chars). **Pinning strategy:**
  default unpinned (maximizes ad strength and combinations); pin only when a line MUST
  appear (brand or compliance language to position 1) and give any pinned position
  2-3 alternatives so it still rotates. Two display paths (≤15 chars each).
- **LinkedIn**: intro text with the insight in the first ~150 characters (the
  truncation point), headline ≤70 chars, outcome-focused, zero hype words. If the cell
  is carousel format, 45-char card headlines with a progressive argument.
- **TikTok**: a native-feel script, not copy: spoken hook + on-screen text for seconds
  0-2 (the cell's hook verbatim or sharpened), a 15-30s body beat list, a spoken CTA.
  Plus ad text ≤100 chars. If it reads like an ad transplanted from Meta, rewrite it.

### Phase 4: Creative briefs per cell

One brief per selected cell, saved to
`./campaigns/<name>/ads/creative-briefs/<cell-id>.md`, each containing: the format, named
from the creative formats file (review static, us vs them, customer UGC, hands demo;
`${CLAUDE_SKILL_DIR}/../creative/references/ad-formats.md`),
the visual concept from the matrix cell, the hook as on-asset text (≤6 words), ratios
needed for the chosen placements, safe-zone notes from platform-specs, and the asset
naming contract: `<cell-id>-<ratio>-v<n>.<ext>` (e.g. `MA-H2-B-9x16-v1.mp4`). Hand to
`/creative`, which reads the same matrix and names assets by cell ID. A video cell cut
from the business's own or generated footage, with captions, review cards and an end card,
is edited in code by `/creative`'s motion-ads mode, free; say so in the brief.

### Phase 5: Quality check (silent)

Score each cell's copy 1-10 on five dimensions: hook fidelity (does the copy deliver
THIS cell's hook_type, or did it drift generic), specificity, platform-nativeness,
landing congruence (the ad's promise is the landing page's headline, see
ads-judgment), and policy cleanliness. Below 7 on any dimension (the default bar;
override either way with a stated reason) → rewrite that dimension → rescore, up to ~3
iterations. Scores and history stay out of the deliverable (keep them in `notes.md` if
useful); the client sees only copy that passes. A weakness that can't be fixed (the
page can't carry the promise) gets one line in the note. Finish with an inline POLICY
CHECK pass (Mode 2 rules) on the final copy: fix what it finds, and surface only what the
client must act on, such as a special ad category to declare.

Missing inputs (landing page, tracking, target CPA) get one line each in the note. Never
audit a placeholder URL or domain.

### Output (CAMPAIGN BUILD)

Length: the ads plus a short test plan. The plan is one page, not a strategy document.

Write before summarizing in chat:

- `./campaigns/<name>/ads/copy/<platform>.md`: one file per platform, one section per ad
  headed by hook and format ("Proof hook, video"), every field within platform limits, and
  the ad name for the upload (cell ID and version) on one line
- `./campaigns/<name>/ads/campaign-plan.md`: the short test plan. Structure and why,
  budget split, audience settings, which hooks and formats go first and why, what each
  test answers, the kill and scale rule in numbers, the UTM pattern once, launch checklist
- `./campaigns/<name>/ads/creative-briefs/<cell-id>.md`: per selected cell
- Update `ad-matrix.json`: selected cells → `status: "copy-ready"`
- `./campaigns/<name>/notes.md`: score history, priors applied, routing and tool output.
  Saved, never pasted
- Append one line per file to `./brand/assets.md`

Chat, in the order the client will use it: header; sample ads for the lead hook (the full
set is in the files); the test plan in a few lines; one Sources and assumptions note
(what the copy rests on, the assumed CPA and budget, what is missing, anything to
confirm); files saved; what's next. No score table, matrix status, or script and tool
output.
