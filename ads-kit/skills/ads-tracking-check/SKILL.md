---
name: ads-tracking-check
description: >
  Prove ad tracking end to end for one business: click id and UTMs land on
  the page, survive redirects, reach the hidden form fields, arrive on the CRM
  lead record, and the platform tags fire once on confirmed success. Every
  finding labelled Observed, Reported or Inferred. Use when someone says
  "check ad tracking", "is tracking working", "conversions missing", "leads
  but no conversions", "too many conversions", "test the form capture",
  "prove attribution", before ads go live, or after a site or form change.
metadata:
  version: 0.1.0
---

# Ads tracking check

One run = one dated check file with a status per link in the chain. `<kit>` = this plugin's root. `<biz>` = the business repo root.

Read first: `<kit>/references/conversion-tracking-rules.md` (evidence labels, verdict rules, verification discipline). Platform detail when needed: `google-ads-tracking.md`, `meta-tracking.md`, `discrepancies.md`.

## The chain (check in this order)

| # | Link | How to check | Pass when |
|---|---|---|---|
| 1 | Ad URL carries the tags | Ad's final URL / URL parameters (MCP read, export or a person's screenshot) | Auto-tagging on (Google); UTMs per `naming.md`; `utm_content` = `content_id` |
| 2 | Landing keeps them | Fetch the landing URL with a test `gclid=TEST-<date>` and the UTMs; follow redirects | Final URL still has every parameter |
| 3 | capture.js runs | Page source has the script on every lead page; same domain | Script present; no CSP block |
| 4 | Hidden fields filled | Open the page with the test parameters in a browser (or a person does); inspect the form | Every capture field present with the test values |
| 5 | Form post carries them | Site code: the handler passes the fields to the CRM intake unchanged | Fields named in the post body |
| 6 | Lead record has them | Submit ONE test lead (needs a yes, see below); read the CRM lead | `opportunity.attribution` shows the test values |
| 7 | Tags fire on success | Google tag + Meta pixel fire on confirmed success, once, with one shared event id | One event per real submit; none on a failed submit |
| 8 | Platform receives | A person checks Meta Test Events / Google conversion diagnostics | Reported arrival |

## Rules

- **Label every row** Observed / Reported / Inferred. A fake test click id proves transport only, never attribution: say so.
- **A test lead needs a yes in this run**, with the exact URL. It fires a real conversion into a real account. Use a marked test email (`test+ads-<date>@<business domain>` or what the business uses) and ask a person to delete the test lead after.
- **Diagnose; do not change.** Name the cause and the exact fix, then stop. Site fixes go to a branch + PR in the site repo, never merged by you.
- **Platform numbers never match ours exactly.** Use the verdict rules before calling a gap a bug.
- **Send-back readiness** (parked in v1): note whether the lead record holds `gclid`/`gbraid`/`wbraid` and `fbc`/`fbp`, which send-back will need (`data-manager.md`).

## Output

`<biz>/tracking/ads/tracking-checks/<YYYY-MM-DD>.md`:

- One table: the 8 links, status (pass / fail / unknown / n/a), label, evidence (what you saw, where).
- Status line: built / installed / firing confirmed / arrival confirmed / arrival pending + the one check that closes it.
- Fixes: each with where, what, who.

Update `lead_paths[].capture` in config to `verified` only for paths that passed links 3 to 6 as Observed.
