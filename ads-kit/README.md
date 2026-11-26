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

Plain browser JavaScript, no dependencies, no network calls. It saves click ids, UTM tags, landing page, referrer and first-seen time in two first-party cookies on your domain (first touch kept, last touch updated), reads Meta's `_fbc` / `_fbp`, and writes the first touch into hidden fields on your forms.

It sends no names, emails or phone numbers, but **click ids, `_fbc` and `_fbp` are identifiers**: they tie a browser to an ad click. So it runs **only with consent**: you must give a consent hook, and with no hook it captures nothing.

```html
<!-- optional: the page's mktdata content_id (a UUID; any other value is ignored) -->
<meta name="content-id" content="0193a7c2-4b1e-7d3a-9f00-00000000c0de">
<script>
  window.adsCaptureOptions = {
    // Required. Return true only after the visitor agreed to marketing cookies.
    // Example: your consent banner saves "consent=marketing" in a cookie.
    consent: function () {
      return /(?:^|;\s*)consent=[^;]*marketing/.test(document.cookie);
    }
  };
  // When the visitor accepts in the banner, capture at once:
  //   onAccept: function () { window.AdsCapture.run(); }
  // When the visitor withdraws consent:
  //   onWithdraw: function () { window.AdsCapture.clear(); }
</script>
<script src="/capture.js" defer></script>
```

**Hidden field names = the CRM intake's attribution keys**, nothing else by default: `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`, `ttclid`, `li_fat_id`, `_fbc`, `_fbp`, `landing_page`, `referrer`, `content_id` (only when the page's `content-id` meta tag holds a 36-character UUID), `first_seen_at` (ISO-8601 UTC, ends in `Z`).

What it keeps of the URLs: `landing_page` drops the fragment and every query parameter except the capture keys (`utm_*` and click ids), so form data or emails in a URL are not stored. `referrer` keeps no query and no fragment, at most 500 characters.

**Server relay.** The CRM reads only `{attribution: {...}}`, not flat form fields, and refuses unknown keys. In the browser, `AdsCapture.attribution(form)` returns the CRM keys from that form, non-empty values only (without a form, from the stored touch). The relay posts that object as `attribution`. On the server, keep only the keys above.

**Last touch (`lastTouch: true`).** Adds `last_*` fields (`last_gclid`, `last_utm_source`, ..., `last_seen`). Off by default: turn it on only after the CRM accepts `last_*` keys (pending os-arch). `attribution()` never includes them.

Things to know:

- **First touch = the first tagged visit.** A visit with no click id and no UTM only holds the first-touch slot until a tagged visit comes; that visit replaces it (the earliest `first_seen_at` is kept). Once a tagged touch is stored, it stays: the first tagged visit wins. So an organic visit followed by an ad click posts the ad's click id. A lead that never came through a tagged link has only `landing_page`, `referrer` and `first_seen_at`.
- **What remains:** a second, different ad click (for example a Google click, then a week later a Meta click) is kept only in the `last_*` fields, which are off until the CRM accepts them. Send-back that needs the newest click will read `last_*` then.
- **Consent withdrawn:** cookies already set stay until they expire. Call `AdsCapture.clear()` from your consent tool: it deletes `_adsc_ft`, `_adsc_lt`, `_fbc` and `_fbp`. The Meta pixel often sets `_fbc` / `_fbp` on the parent domain (`.example.com`); set `cookieDomain` to that domain so `clear()` reaches them, and stop the pixel too.
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
