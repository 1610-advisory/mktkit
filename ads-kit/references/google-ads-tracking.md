<!-- Vendored from https://github.com/coreyhaines31/marketingskills (commit 8fd2fca), skills/conversion-tracking/references/google-ads.md. MIT License, Copyright (c) 2025 Corey Haines. See ../THIRD_PARTY_NOTICES.md. Excerpt: "Part B: diagnostic reference" to end of file. Category G rewritten in full by ads-kit for the Google Data Manager API; other offline-upload sentences and one GTM placeholder edited, each marked with an ads-kit comment; rest unmodified. -->

> **ads-kit note:** read this as a playbook. In ads-kit the measure is the CRM-qualified lead (cost per qualified lead from the business's own records), not the platform's conversion count.
> The ads-engineer never writes to an ad account itself: money changes go only through the mktdata change queue (`propose_change`), see `change-queue.md`.
> For Google, CRM-qualified leads go back to the account only as offline conversion upload through the Data Manager API, see `data-manager.md`.
> References to other files (for example `../assets/snippets/`, `../scripts/build_recipe.py`, Part A) point at the source repo, not ads-kit.

## Part B: diagnostic reference

Compiled August 2026 from Google Ads Help documentation, practitioner blogs (Analytics Mania, Adalysis, Adnan Agic, PPC Land, Cometly, TagFly, Elevar, ConversionTracking.io), and community threads.

**Fix assets.** From-zero setup steps are in Part A above. Missing or wrong triggers are usually fixed by this skill's tested assets: `../assets/snippets/`, `../assets/gtm-recipes/`, merged and ID-injected by `../scripts/build_recipe.py`.

### Part B.1: Diagnostic Surfaces (check these first, in this order)

### 1.1 Conversion action status - Goals > Conversions > Summary

The "Status" column per conversion action is the single highest-value diagnostic signal:

| Status | Meaning | Implication |
|---|---|---|
| **Unverified** | Google has never seen the tag fire for this action. Normal for a few hours (up to 48h) after setup; if it persists for days, the tag was never installed, has the wrong ID/label, or fires on a page nobody visits | Broken setup - tag never fired once |
| **Recording conversions** | Tag seen and conversions recorded in last 7 days | Healthy |
| **No recent conversions** | Tag IS detected, but zero conversions in last 7 days | Tag works; either no conversions actually happened, low volume, or the event snippet page is unreachable. Not necessarily broken |
| **Tag inactive** / **Inactive** | Google no longer sees the tag AND no conversions in 7 days. UI shows last-detected date and last-conversion date | Tag was removed/broken on a specific date - correlate with site redesigns, GTM publishes, plugin updates |
| **Needs attention** | Active but has errors (commonly enhanced-conversions data problems) | Partially working; open Diagnostics |
| **Removed** | Conversion action deleted/disabled in the account | Re-enable the action |

**Three more statuses the table above misses.** Harvested from Google's own status
documentation, and each means something different from the four above:

- **Misconfigured.** Conversions have stopped recording *entirely* because of a setup error
  or a broken tag. This is the most urgent status there is and it is not the same as
  Unverified: Unverified means never seen, Misconfigured means it worked and now does not.
- **Awaiting conversions.** No conversions in 7 days, expected when the action was created
  under 48 hours ago, the campaigns are paused, or traffic is too low to produce one. Do not
  diagnose a tag problem from this without first checking whether campaigns are even running.
- **Removed (deleted or archived).** Distinct from the disabled "Removed" row above: the action
  was manually deleted or archived. Nothing is broken; someone did this on purpose, possibly a
  previous agency. Ask before recreating it.

Separately, Tag Diagnostics grades tags **excellent / good / needs attention / urgent**, and
there are three distinct enhanced-conversions diagnostic reports (web tag, web API, and
leads). A user saying "diagnostics says there's a problem" could mean any of them, so ask
which screen they are looking at before interpreting it.

The **last detected date** on Tag inactive dates the breakage - ask "what changed on the site/GTM/plugins on that date?"

### 1.2 Built-in Troubleshoot flow / Tag Assistant
Hovering an "Unverified"/"Tag inactive"/"Needs attention" status shows a **Troubleshoot** link that launches Google Tag Assistant (tagassistant.google.com).

### 1.3 Diagnostics tab (enhanced conversions)
Goals > Summary > Diagnostics: grades Excellent / Good / Needs attention / No recent data / Urgent, plus alerts (missing user_data fields, formatting errors, low match rate).

### 1.4 Auto-tagging setting
Admin > Account settings > Auto-tagging - must be ON for gclid attribution and any offline conversion upload (Data Manager API). <!-- ads-kit edit -->

### 1.5 Other account-level surfaces
- "Maintain your Google tag" - surfaces "Website redirects are losing click data" warning
- Conversion action settings: count (One/Every), click-through window (default 30d), attribution model, Primary/Secondary
- Segment > Conversions > Conversion action on campaign tables - reveals WHICH action generated the numbers (catches double counting)
- "by conv. time" columns - conversions are otherwise reported against click date, not conversion date

### Part B.2: Tag anatomy

### 2.1 Google tag (gtag.js)
```html
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-XXXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'AW-XXXXXXXXXX');
</script>
```
IDs: `AW-` Google Ads, `G-` GA4, `GTM-` container, `DC-` Floodlight. A page with only `G-`/`GTM-` can still work if Ads conversions run through GTM - check container contents before declaring missing.

### 2.2 Event snippet
```html
gtag('event', 'conversion', {'send_to': 'AW-XXXXXXXXXX/AbCdEfGhIj0123456789', 'value': 0.0, 'currency': 'USD'});
```
`send_to` = `AW-CONVERSION_ID/CONVERSION_LABEL`. Google offers "page load" (thank-you page) or "click" (`gtag_report_conversion(url)`) variants.

### 2.3 GTM pattern
`GTM-<container-id>` <!-- ads-kit edit --> snippet in head + noscript iframe. Inside: a Google Ads Conversion Tracking tag (ID + Label) plus a Conversion Linker tag on All Pages.

### 2.4 Network requests that prove a conversion fired
- Classic ping: `googleadservices.com/pagead/conversion/{ID}/?...label={LABEL}`
- Consent-aware paths: `google.com/pagead/1p-conversion/...` and `.../ccm/collect`
- `gcs` param encodes consent (`G111` granted, `G100` denied); `gcd` = Consent Mode v2 state. `gcs=G100` on the ping = conversion modeled at best, not recorded.

### 2.5 gclid lifecycle
1. Auto-tagging appends `?gclid=` at click time (iOS/privacy contexts use `gbraid`/`wbraid`)
2. gclid must survive every redirect to the tagged page
3. Google tag / Conversion Linker stores it in first-party cookies: `_gcl_aw` (gclid), `_gcl_gb` (wbraid/gbraid), `_gcl_dc` (dclid). Linker must fire on ALL pages, before conversion tags.
4. Event snippet reads the cookie and sends it with the ping
5. Google keeps gclid 90 days; offline conversion uploads (Data Manager API) referencing older clicks fail. <!-- ads-kit edit --> Conversion must land inside the action's click window (default 30d).

Chain test: visit `landingpage?gclid=TEST123` → confirm survives redirects → check cookies for `_gcl_aw` containing TEST123 → submit form → look for conversion ping in Network.

### Part B.3: Failure catalog

### Category A - Tag missing or never firing
- **A1. Tag never installed / wrong pages** (VERY COMMON): status stuck Unverified; spend with zero conversions ever. Check landing AND thank-you page source for `AW-`/`GTM-`.
- **A2. Tag removed during redesign/migration/theme or plugin update** (VERY COMMON): was Recording, now Tag inactive; conversions flatline on a date. Correlate last-detected date with deploys.
- **A3. GTM changes never published** (VERY COMMON): tags exist only in an unpublished workspace draft. Check GTM Versions.
- **A4. Wrong Conversion ID or Label** (COMMON): GTM Preview shows tag firing, Ads records nothing. Compare GTM values against the action's Tag setup character-for-character.
- **A5. Tag from the wrong account / MCC confusion** (OCCASIONAL, agency-specific): conversions land in a previous agency's account, or MCC cross-account tracking conflicts. Compare on-page AW- ID with the account's conversion tracking ID.
- **A6. Performance/caching layers blocking the tag** (OCCASIONAL): Cloudflare Rocket Loader/APO, WP Rocket JS-delay, CSP blocks. Console errors; no request to googletagmanager.com.

### Category B - Tag fires but the conversion moment is missed (heart of lead-gen audits)
- **B1. GTM Form Submission trigger doesn't fire** (VERY COMMON): AJAX forms without standard submit events, misconfigured validation/conditions, broken dataLayer. Fix: thank-you pageview, Element Visibility on success message, platform callback, or dataLayer push.
- **B2. Form in a cross-origin iframe** (VERY COMMON): Typeform, Calendly, HubSpot, Jotform. Parent GTM can't see submissions; iframe can't see parent's `_gcl_aw`. Fix: postMessage listeners, provider redirect to first-party thank-you, or capture gclid to hidden field + offline conversion upload (Data Manager API). <!-- ads-kit edit -->
- **B3. Conversion fires on a page that redirects before ping completes** (COMMON): browser kills the request in flight. Fix: thank-you page firing or gtag_report_conversion callback.
- **B4. Thank-you page URL changed / trigger mismatch** (VERY COMMON): trigger matches `/thank-you`, page became `/thanks`; trailing-slash or query-string breaking "equals" conditions.
- **B5. No thank-you page at all, inline success message** (COMMON): Element Visibility trigger or provider callback needed.
- **B6. Overcounting: wrong page / per-pageview / double implementation** (COMMON): snippet on every page; thank-you reload recounts (Count=Every); hardcoded gtag AND GTM tag both firing; website tag AND imported GA4 key event both Primary.

### Category C - Click ID / attribution chain broken
- **C1. Auto-tagging disabled** (COMMON): tag verified, conversions near zero; no gclid in landing URLs; GA4 shows Ads traffic as organic.
- **C2. gclid stripped by redirects** (VERY COMMON, invisible): http→https, non-www→www, trailing slash, geo redirects, shorteners. Test: `curl -IL "https://landingpage?gclid=TEST123"` and watch each hop. Fix: final URLs in ads, or forward query strings (Apache QSA, Nginx `$is_args$args`).
- **C3. Conversion Linker missing** (COMMON in GTM setups): no `_gcl_aw` cookie; heavy undercount especially Safari.
- **C4. Cross-domain journey** (COMMON): `_gcl_aw` scoped to first domain. Fix: Linker cross-domain linking or pass gclid in URL.
- **C5. gclid mutated** (RARE): CMS/scripts lowercase or truncate the gclid - Google treats as different ID.
- **C6. No ad click in the test path** (COMMON false alarm): website conversions only count after an ad click. Direct test submissions never appear in Ads.

### Category D - Consent & privacy
- **D1. Consent Mode misconfigured** (VERY COMMON in EEA/UK): conversions drop 30-90% after CMP install; CMP never flips ad_storage/ad_user_data to granted. Confirm: Tag Assistant Consent tab; `gcs=G100` persisting after accept. Since March 2024 Google requires ad_user_data/ad_personalization for EEA; stricter enforcement from July 2025 has been widely reported (not a formal Google announcement).
- **D2. Consent denied traffic + modeling gaps**: denied conversions dropped or modeled; Ads and GA4 model independently. URL passthrough (`url_passthrough: true`) partially recovers.
- **D3. Ad blockers / ITP baseline loss** (ALWAYS PRESENT): typically 10–30% never track client-side, depending on audience. Mitigate with enhanced conversions / server-side.

### Category E - Account configuration
- **E1. Action set to Secondary** (VERY COMMON confusion): only counts in "All conversions", not "Conversions"; doesn't drive Smart Bidding. Inverse: two Primaries for same event = double counting.
- **E2. Conversion window too short / lag misread** (COMMON): conversions back-dated to click date; recent days fill in retroactively; processing hours to 72h (gbraid/wbraid); GA4 imports +1-2 days. Don't judge the last 3 days.
- **E3. Count Every vs One** (COMMON): leads should be One.
- **E4. Campaign-level goal exclusions**: campaign uses custom goals excluding the action.

### Category F - GA4-imported conversions
- **F1. GA4 key event not imported** (VERY COMMON): not marked Key event, never imported, accounts not linked, or data-sharing disabled. Import only counts forward.
- **F2. GA4 vs Ads numbers "don't match"** (CONSTANT, not a bug): click-date vs event-date, double counting when both Primary, different attribution models, Ads counts view-through/cross-device, separate consent modeling, lag, timezone. 10-30% divergence is normal. Pick ONE source of truth per action; demote the other to Secondary.

<!-- ads-kit: rewritten for Data Manager API, not from source -->
### Category G - Offline / CRM conversion upload (Data Manager API) & enhanced conversions
Since 2026-06-15 the Data Manager API is the only path for a new adopter to send offline (CRM) conversions to Google Ads. The older Google Ads API offline click import and the Enhanced Conversions for Leads upload are closed to new callers. Send events with `POST https://datamanager.googleapis.com/v1/events:ingest`, OAuth scope `https://www.googleapis.com/auth/datamanager`. Access belongs to the Google Cloud project that owns the OAuth client; no Google Ads developer token is involved.

- **G1. Built on the old upload path**: code or a tool calls the Google Ads API click-conversion upload or the old leads upload, and a new caller is refused. Move the sender to `events:ingest`.
- **G2. Click id never captured into the CRM** (VERY COMMON root failure): no hidden field on the form, the field reads only the landing URL (lost on multi-page journeys; read the `_gcl_aw` / `_gcl_gb` cookie instead), or a multi-step form drops it. With no click id and no consented hashed identifiers, the event has nothing to match.
- **G3. Click id in the wrong place or changed**: gclid, gbraid and wbraid go in `adIdentifiers`, each in its own field. A spreadsheet step that truncates the id, changes its case or turns it into a number makes an unknown click. So does sending to a conversion action in a different account from the click, or to an action that is not set up for offline (uploaded) conversions.
- **G4. Whole batch rejected**: there is no partial failure. One bad row (a time with no time zone, an unknown conversion action, a badly hashed identifier, missing consent) rejects every row in the request. Validate each row before you send, keep batches small enough to retry, and record which rows were in which request.
- **G5. Success read from the wrong place**: the ingest call only accepts the request. Results per event come back later, async, through diagnostics. Do not report a conversion as arrived until the diagnostics for that request say so.
- **G6. Outside the window**: the conversion must be sent within 90 days of the click (63 days for Enhanced Conversions for Leads), and the conversion time must also fall inside the conversion action's click-through window (default 30 days). A click from only minutes ago may not be matchable yet; send it again later.
- **G7. Counted twice**: each event needs a stable `transactionId` (for example the CRM record id plus the stage) so a re-send is deduplicated. Without it, every retry and every re-run of the sync adds another conversion. Also check that a browser tag is not reporting the same moment to the same action.
- **G8. Consent missing or assumed**: each event carries `ad_user_data` and `ad_personalization` consent. Set them from the consent the lead actually gave. Never default them to granted.
- **G9. Enhanced Conversions for Leads identifiers wrong** (COMMON): hashed email and phone are sent only when the business owner has agreed to send customer data. Normalize first (trim spaces, lowercase the email, phone in E.164), then hash with SHA-256. Raw or not-normalized values do not match. The site tag must capture the same identifiers at form submit, and the customer data terms must be accepted in the account.
- **G10. Auto-tagging off at click time**: those clicks never had a gclid, so no upload can match them. Turn auto-tagging on (1.4); only clicks after that point can be matched.
- **G11. Enhanced conversions (web) sends no user data** (COMMON): the setting is on, but the tag sends no user data because the field mapping is missing, a CSS selector broke, or the format is wrong. Check in Tag Assistant that the conversion ping carries hashed `em` / `pn`.
- **G12. Lead form assets (Google-hosted)**: Google counts these itself, and website tags do not apply. The leads stay in the account for 30 days only, unless a webhook or CRM integration collects them.
<!-- /ads-kit -->

### Category H - Phone-call conversions
Google forwarding number or website call conversions (number swap). Failures: number hardcoded as image/formatted differently so swap fails; call trackers (CallRail) replacing after Google's snippet; minimum call length filters.

### Part B.4: Ranked prevalence
1. Tag/trigger never fires for the real form flow (B1/B2/B4)
2. Tag removed or GTM unpublished after site changes (A2/A3)
3. Secondary vs Primary / column misreading (E1)
4. Consent Mode misconfiguration post-CMP (D1)
5. gclid chain broken (C1-C3)
6. Wrong ID/label or wrong account (A4/A5)
7. GA4-import confusion and mismatch panic (F1/F2)
8. Timing misreads (E2)
9. Duplicate counting (B6)
10. Offline conversion upload (Data Manager API) and EC failures (G1-G12) - lower volume, highest per-case complexity <!-- ads-kit edit -->

### Part B.5: Suggested audit order
1. Account surface first: statuses + last-detected dates; Primary/Secondary; counts; windows; auto-tagging; campaign goals; Diagnostics; segment by action
2. Date correlation: flatline date vs deploys/GTM versions/CMP installs
3. Page source: AW-/GTM- on landing + thank-you pages; duplicates; consent defaults
4. Live walk: `?gclid=TEST` → redirect survival → `_gcl_aw` → submit → conversion ping + gcs value; Tag Assistant
5. Attribution back-end: GA4 link/import; CRM gclid capture; offline conversion upload (Data Manager API) diagnostics; EC diagnostics <!-- ads-kit edit -->
6. Only then conclude "tracking is fine, the campaign just isn't converting"

Key sources: support.google.com/google-ads (answers 7548399, 15629968, 13321563, 11956168, 15713840, 10989978), analyticsmania.com (28 reasons; form triggers; conversion linker), adalysis.com top-10 mistakes, adnanagic.com gclid redirects, ppc.land consent mode v2 enforcement, nicelookingdata.com GA4 vs Ads, conversiontracking.io iframes, cometly.com, tagfly.io, freak.marketing inactive tags, playhouse.digital gclid hidden field, pemavor.com offline imports.
