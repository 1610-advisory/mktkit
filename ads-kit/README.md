# ads-kit

A paid-ads engineer for a small business, as a Claude Code plugin. It maps every way a lead reaches you, proves your ad clicks are captured on your forms, builds Google and Meta campaigns from an ad matrix, judges results by the leads your own records call qualified, and writes reports you can send.

It **proposes** every money change. A person approves it, or the standing limit you set runs it in the marketing data tool. It never touches billing, user access or new ad accounts.

It pairs with the **ai-cmo** plugin in this repo: the CMO decides what the business says and to whom; the ads engineer makes paid ads bring in qualified leads at a known cost. It also works alone.

```
/plugin marketplace add 1610-advisory/mktkit
/plugin install ads-kit@mktkit
```

## What it does

| Skill | Job |
|---|---|
| `ads-setup` | Lead-path map, capture check per form, `tracking/ads/config.yaml` (caps, standing limit, qualified line, consent, platforms, call source), sources to connect, naming rule |
| `ads-tracking-check` | Proves click id → page → form → CRM lead → platform, each step labelled Observed, Reported or Inferred |
| `ads-build` | Ad matrix → campaign plan, copy per cell, creative briefs for `reel-editor` / `carousel-slides`, launch proposals |
| `ads-review` | Daily or weekly KILL / SCALE / ITERATE / REFRESH with the math, then proposals |
| `ads-library` | Creative ids, approvals, fatigue, the hook × format grid |
| `ads-report` | Weekly or monthly markdown report → branded HTML (`branded-report`) |

Agent: `ads-engineer` (one business per run). Script: `scripts/capture.js`.

## The rules it works by

- **Qualified leads are the measure.** Three steps from your own records: lead, qualified lead (one line you set), won. What the platforms claim shows beside them, labelled "platform claim".
- **No verdict too early.** An ad gets no verdict before it spends about 2× your target cost per qualified lead, and never on data under 3 days old.
- **One string joins everything.** Each ad name starts with its `content_id`, and `utm_content` is that `content_id` (`references/naming.md`).
- **Caps are law.** A monthly hard cap and a daily cap in config, never exceeded.
- **Standing limit.** Inside it (pause, restart its own pause within 7 days, budget ±20 % a day under the cap, a new ad from an approved creative into an existing ad set) the tool acts and reports after. Everything else waits for a person. If limit actions lose money over the window, everything waits.

Detail: `references/change-queue.md`.

## Click capture: `scripts/capture.js`

Plain browser JavaScript, no dependencies, no network calls. It saves `gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`, `ttclid`, `li_fat_id`, `utm_*`, landing page, referrer and first-seen time in two first-party cookies on your domain (first touch kept, last touch updated), reads Meta's `_fbc` / `_fbp`, and writes all of it into hidden fields on your forms. It respects a consent hook.

```html
<script>window.adsCaptureOptions = { consent: function () { return true; } };</script>
<script src="/capture.js" defer></script>
```

Things to know:

- **First touch may have no click id.** It is the first visit we saw, which can be organic: then it holds only `landing_page`, `referrer` and `first_seen`. Ad attribution and the planned send-back read the `last_*` click ids (`last_gclid`, `last_gbraid`, `last_wbraid`, `last_fbclid`, ...), the newest ad click before the form.
- **Consent withdrawn:** cookies already set stay until they expire. Call `AdsCapture.clear()` from your consent tool to delete them.
- **Changing `cookieDomain`** can leave two cookies with the same name (one for the host, one for the domain). Call `AdsCapture.clear()` once after the change; it deletes both.
- **Cookies blocked:** the fields filled on page load are kept on submit; nothing is remembered across pages.

Tests: `node --test "ads-kit/scripts/tests/*.test.js"` (Node 18+).

## Where the data comes from

- **With the mktdata tool** (the marketing data store behind the 1610 OS): named reads for spend, content and the funnel; CRM reads for outcomes; `propose_change` for money changes.
- **Without it:** the official Google Ads MCP and Meta Ads MCP for reads (turn their write tools off), plus files in `tracking/ads/` and `tracking/revenue-attribution.csv`. Proposals go to `tracking/ads/proposals/` for a person to do by hand.

No Google developer token is needed (Google retired them in 2026). Sending qualified and won leads back to Google (Data Manager API) and Meta (Conversions API) is planned, not on in this version: `references/data-manager.md`.

## Files it keeps in your business repo

```
tracking/ads/
  config.yaml              caps, limit, targets, qualified line, consent, platforms, call source
  lead-paths.md            every way a lead reaches you, and whether capture works
  tracking-checks/<date>.md
  campaigns/<slug>/        ad-matrix.json, plan.md, copy/, briefs/, policy-review.md
  library.md
  snapshots/<date>/        platform reads when mktdata is not live
  reviews/<date>.md
  proposals/<date>.md      when mktdata is not live
  reports/<period>.md      + the branded HTML
```

Start: copy `templates/config.yaml` to `tracking/ads/config.yaml`, then ask the agent for "setup".

## What stays with a person, by design

- Caps, the standing limit, the qualified line, consent for hashed data: you set them.
- Approving money changes outside the limit, and approving creatives for ads.
- Granting ad-account access and connecting sources. Never paste a key or token into chat.
- Billing, user access, new ad accounts: never the agent's job.

## Honest limits

- Platform numbers never match your records exactly. The kit tells you which gap is normal.
- Small budgets learn slowly. Expect "keep running" for the first weeks.
- Without the mktdata tool, nothing runs on its own: every change is done by a person.

Borrowed text in `references/` is MIT, from [boring-marketing-skills](https://github.com/boringmarketer/boring-marketing-skills) and [marketingskills](https://github.com/coreyhaines31/marketingskills); see `THIRD_PARTY_NOTICES.md`.
