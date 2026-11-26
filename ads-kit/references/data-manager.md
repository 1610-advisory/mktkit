# Sending CRM outcomes back to Google and Meta (parked in v1)

ads-kit's own text (MIT). Facts checked 2026-11; vendor APIs change, so check the linked docs before any build.

**Status: parked.** Send-back starts only after the vendor app reviews pass and `send_back.enabled` is true in `tracking/ads/config.yaml`. Until then, reports use all three steps (lead, qualified, won) from our own records, and the platforms learn from the site tag only.

## What we send, and why

- Raw leads stay on the site tag (Google tag + Meta pixel, one shared event id) for a fast signal.
- **Qualified** and **won (with amount)** go back from the CRM, so bidding learns which clicks become real work.
- Hashed email or phone only when `hashed_data_consent.allowed: true` (the owner's one-time yes). Otherwise click ids only.

## Google: Data Manager API only

Since 2026-06-15 the Google Ads API refuses **new** callers of offline click conversion import and Enhanced Conversions for Leads upload. New callers use the Data Manager API. Every older guide (and older copies of borrowed text) that says "upload click conversions with the Google Ads API" is out of date.

- Endpoint: `datamanager.googleapis.com/v1/events:ingest`.
- OAuth scope: `https://www.googleapis.com/auth/datamanager`. Ask for it on its own, apart from the read scopes, so reporting does not wait for its slower consent review.
- **No developer token.** Google sunset developer tokens on 2026-09-09. Access level belongs to the Google Cloud project that issues the OAuth credentials.
- Click ids `gclid`, `gbraid`, `wbraid` go in `adIdentifiers`. Hashed (SHA-256, normalized) email/phone go in user data for Enhanced Conversions for Leads, only with consent.
- Consent per event: `ad_user_data` and `ad_personalization`.
- Dedupe with `transactionId` (use the CRM's opportunity id plus the step, for example `<opportunity_id>:qualified`).
- **No partial failure.** One bad row rejects the whole batch. Validate every row before you send.
- Results come back later through diagnostics, not in the response. Read them on the next run.
- Windows: 90 days from the click (63 days for Enhanced Conversions for Leads). The conversion must also fall inside the conversion action's click window. Auto-tagging must be on.

Docs: Data Manager "send events" guide (developers.google.com/data-manager), Google Ads help "upgrade to Data Manager".

## Meta: Conversions API for CRM

- One event per lead stage, `action_source=system_generated`, `event_source=crm`.
- Best key: Meta `lead_id` (Lead Ads). Else `fbc` / `fbp` from the lead's attribution keys `_fbc` / `_fbp` (`capture.js`), plus hashed email/phone only with consent.
- `event_time` at most 7 days back.
- Needs Business Verification and App Review for the ads permissions.

## Who sends

The mktdata tool, on a timer or from the owner's screen. Never the ads-engineer, never from a chat. The agent's part is to check readiness (`ads-tracking-check`) and to report what send-back would add.
