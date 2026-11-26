---
name: ads-setup
description: >
  Set up paid ads for one business: map every lead path, check click capture
  on each form, write tracking/ads/config.yaml (caps, standing limit,
  qualified line, consent flag, platforms, call source), list the sources to
  connect, and fix the naming rule. Use when someone says "set up ads",
  "start running ads for", "onboard ads", "connect Google Ads / Meta Ads",
  "ads config", "what do we need before ads go live", or when the
  ads-engineer finds no tracking/ads/config.yaml.
metadata:
  version: 0.1.0
---

# Ads setup

One run = one config, one lead-path map, one list of what a person must do. `<kit>` = this plugin's root (two levels up from this file). `<biz>` = the business repo root.

Nothing here spends money or changes an ad account. You write files in the business repo and a list for a person.

## Steps

Copy these into the session checklist. Keep a skipped step listed with `skip: <reason>`.

1. **Config file.** If `<biz>/tracking/ads/config.yaml` is missing, copy `<kit>/templates/config.yaml` there. Fill `business`, `content_id_prefix`, `currency`, `timezone` from `knowledge/00-client-overview.md` and existing content notes.
2. **Lead-path map.** List every way a lead reaches the business: each form (page + form name), each phone number on the site and in ads, booking links, chat, Lead Ads forms, walk-ins. Write `<biz>/tracking/ads/lead-paths.md`: one row per path with `path`, `where`, `lands in` (CRM intake, inbox, phone), `capture` (yes / no / unknown), `label` (Observed / Reported / Inferred). A path you cannot see is "unknown", never "no".
3. **Capture check per form.** For each form on the site repo (or the live page): is `capture.js` (`<kit>/scripts/capture.js`) loaded on every page, and do the hidden fields reach the form post? Look in the site code first; then fetch the page. Missing: write the install note (below) into `needs_a_person` or, if the site repo is ours, a branch + PR in the site repo (never merge, never deploy). Record the result in `lead_paths` in config.
4. **Where the form posts.** Each form must post to the CRM intake so attribution lands on the lead record (`opportunity.attribution`). If the business forwards leads to its own CRM too, our lead id goes into their record. Record the answer; do not change a client CRM.
5. **Money lines, from a person only.** Ask for, and do not invent: `caps.monthly_hard_cap_cents`, `caps.daily_cap_cents`, `targets.cost_per_qualified_lead_cents`, `conversions.qualified` (one line), `hashed_data_consent` (default false), `standing_limit.enabled` and its `owner`. Write each answer with who said it and the date in `knowledge/_intake-log.md`. Unanswered: leave 0 / empty and list it.
6. **Call source.** One per business, never two. Options: none, a call service that forwards and records calls and posts each call to the CRM intake as a lead (`source=call`), Google forwarding numbers (Google clicks only, calls over 15 s), or "how did you hear about us" in the CRM. Offer; do not push. Note the recording disclosure rule (some US states need all-party consent).
7. **Sources to connect.** List for a person: Google Ads (official Google Ads MCP, read-only; or mktdata Sources screen), Meta Ads (official Meta Ads MCP, write tools off; or mktdata), the CRM. Never ask for a key or token in chat. No Google developer token is needed (sunset 2026-09-09).
8. **Naming rule.** Read `<kit>/references/naming.md`. Check live ad names (if any) for a `content_id`. List every ad that breaks the rule, with its spend in the last 30 days.
9. **Write and report.** Save config and `lead-paths.md`. Append one line to the business memory log. Return the agent's report with `needs_a_person` full.

## capture.js install note (for the site owner)

```html
<script>
  window.adsCaptureOptions = {
    consent: function () { return true; } // replace with your consent check
  };
</script>
<script src="/capture.js" defer></script>
```

Host `capture.js` on the site's own domain (first-party). It adds hidden fields to every `<form>`, named exactly as the CRM intake's attribution keys: `utm_*`, `gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`, `ttclid`, `li_fat_id`, `_fbc`, `_fbp`, `landing_page`, `referrer`, `first_seen_at`, and `content_id` when the page has `<meta name="content-id" content="...">`. The site relay posts `{attribution: AdsCapture.attribution(form)}` to the CRM intake (flat fields are not read; unknown keys are refused). Keep `lastTouch` off until the CRM accepts `last_*` keys (see the plugin README).

## Rules

- A setup is not done until `ads-tracking-check` proves one test lead end to end.
- Money lines come from a person, in writing. Never fill them from a guess, a benchmark or another business.
- Public kit, private data: account ids, phone numbers and caps live only in the business repo.
