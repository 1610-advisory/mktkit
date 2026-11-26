# Change queue: how a money change happens

ads-kit's own text (MIT). Read this before you propose any change to an ad account.

## The rule

The ads-engineer **proposes**. It never executes. A money change is any change to what is spent or shown: pause, restart, budget, bid, new ad, targeting, conversion settings.

| Who | Does what |
|---|---|
| ads-engineer (agent) | Writes one proposal per change with mktdata `propose_change`. Then ends its turn. |
| mktdata `limit_runner` (the tool's own timer, with a named human owner) | Runs a proposal **only** when it fits the standing limit the owner set in mktdata Settings. Checks the caps at execute time. Logs the result. |
| A person (owner or admin) | Approves or rejects every other proposal on the mktdata Changes screen (`decide_change`). The person who proposed cannot approve. An agent never approves. |

Principle: humans stand **beside** the loop as approvers, not inside it as operators.

## Never, at any phase

- Make or close an ad account.
- Touch billing, payment methods or invoices.
- Add, remove or change user access.
- Call a write tool on the Google Ads MCP or the Meta Ads MCP. Use those MCPs for reads only, with write tools turned off.
- Call a vendor API directly.

## Proposal shape

One `propose_change` call per change. Its body has exactly these fields (mktdata refuses any other field):

| Field | What |
|---|---|
| `request` | `pause_ad`, `restart_ad`, `set_budget` or `create_ad` |
| `input` | The exact input of that request (table below) |
| `reason` | The verdict and its math (from `ads-review`), with `before` → `after` in words. Up to 1000 characters |
| `expected_effect` | What number should move, by how much, by when. Up to 500 characters |
| `evidence` | The reads the math came from, each with its date range and an Observed / Reported / Inferred label. Up to 4000 characters |

The tool records the state before the change itself (`before_state`), so `before` is not a field: put it in `reason`.

| `request` | `input` |
|---|---|
| `pause_ad` | `{campaign_id, ad_id}`: `ad_id` is an ad-level row under `campaign_id` |
| `restart_ad` | `{campaign_id, ad_id}` |
| `set_budget` | `{budget_target_id, budget_level, daily_budget_minor, currency}`: `budget_target_id` is the row that holds the budget (`sources_status` shows each account's budget level); `budget_level` is `campaign` or `ad_set` (mktdata's `ad_group` level); `currency` is the config currency |
| `create_ad` | `{campaign_id, content_id, landing_url}`: `campaign_id` is an existing ad group / ad set; `content_id` is a library piece (`list_content`, status `approved` for it to run inside the limit); `landing_url` starts `https://` |

- **No ad-set pause request.** There is no `pause_adset` and you must not invent one. To stop a whole ad set, propose `pause_ad` for each ad in it, or write the ad-set pause as a human action in `needs_a_person`. The standing limit's "pause an ad set" line runs only as per-ad pauses until mktdata adds an ad-set request.
- **No new campaign, audience, bid or targeting request.** mktdata cannot propose those. Write them as a person's action (in `needs_a_person` and the review), never as `propose_change`.
- Every id is a **mktdata id** from a mktdata read (`list_campaigns`, `list_content`). Never a vendor id. If you only have a vendor id or a name, look it up with `list_campaigns` `q`; if the row is on `to_match_list`, say so and do not propose.
- Money is integer minor units (cents for USD) in the config currency.
- One open proposal per change: check `list_proposals` (and `campaign_id`) before you propose. A proposal not decided in 7 days expires.

Example (Acme Plumbing, made-up ids):

```json
{
  "request": "set_budget",
  "input": {
    "budget_target_id": "0193a7c2-0000-7000-8000-000000000001",
    "budget_level": "campaign",
    "daily_budget_minor": 6000,
    "currency": "USD"
  },
  "reason": "SCALE: daily budget $50 -> $60 (+20%). Cost per qualified lead $41 vs target $60 over 9 days, 7 qualified leads, stable trend.",
  "expected_effect": "About 1.2 more qualified leads a week at or under $60 each; read again in 5 days.",
  "evidence": "mktdata spend_by_campaign 2026-12-01..2026-12-09 (Observed); mktdata outcomes_by_campaign same range, outcome_source crm (Observed)"
}
```

After a proposal: `list_proposals` and `get_proposal` show its status (`proposed`, `approved`, `rejected`, `expired`, `executing`, `done`, `failed`, `unknown`); `list_actions` shows what ran and what the tool refused (`cap_refused`, `limit_refused`). You never decide, undo or settle a change: those are a person's buttons on the Changes screen (`mktdata-requests.md` "Screen only").

## Standing limit (starting default; the owner sets it in mktdata Settings, mirrored in config)

Act at once, then report, only for:

- Pause an ad or ad set (in M1: per-ad `pause_ad` only; see "No ad-set pause request" above).
- Restart an ad the limit itself paused, within 7 days.
- Budget change of up to ±20 % a day per campaign, with total daily spend at or under the daily cap.
- A new ad, only from a creative already approved in the library, only into an existing ad set.

Always queue for a person: larger budget moves, spend over a cap, new creative, new audience, new campaign, bids or bid strategy, targeting, conversion settings.

Safety:

- The hard monthly cap is never exceeded. The caps are the owner's mktdata Settings (`get_config`); the tool checks them itself at execute time and refuses a change that would break one. Your proposal still never plans spend over a cap.
- Every action is in the action log (`list_actions`), with one-press undo for a person on the Changes screen.
- One daily digest of actions and pending proposals.
- Loss rule: if limit actions lose money over the stated window, everything falls back to "queue everything" (`get_config` `fallback.active`) until a person resets it.

## Before mktdata is live

Use this when `data.mktdata.live` is `false` or the connector has no mktdata tool (`mktdata-requests.md` "Without mktdata"). There is no queue. Write proposals to `tracking/ads/proposals/YYYY-MM-DD.md` in the business repo: one fenced JSON block per proposal with the same `request`, `reason`, `expected_effect` and `evidence`. There are no mktdata ids in this mode, so `input` names the platform object instead (`platform`, the ad or campaign name and its id from the MCP read), and the budget is in the config currency's minor units. Then a status line `status: proposed`. A person makes the change in the ad platform by hand and edits the status line to `done by <name> <date>` or `rejected`. Nothing runs on its own in this mode: the standing limit needs mktdata. Caps come from `tracking/ads/config.yaml`.
