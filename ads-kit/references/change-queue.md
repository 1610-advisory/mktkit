# Change queue: how a money change happens

ads-kit's own text (MIT). Read this before you propose any change to an ad account.

## The rule

The ads-engineer **proposes**. It never executes. A money change is any change to what is spent or shown: pause, restart, budget, bid, new ad, targeting, conversion settings.

| Who | Does what |
|---|---|
| ads-engineer (agent) | Writes one proposal per change with `propose_change`. Then ends its turn. |
| mktdata `limit_runner` (the tool's own timer, with a named human owner) | Executes a proposal **only** when it fits the standing limit in `tracking/ads/config.yaml`. Checks the caps at execute time. Logs the result in the same row. |
| A person (owner or admin) | Approves or rejects every other proposal on the mktdata change-queue screen. The person who proposed cannot approve. An agent never approves. |

Principle: humans stand **beside** the loop as approvers, not inside it as operators.

## Never, at any phase

- Make or close an ad account.
- Touch billing, payment methods or invoices.
- Add, remove or change user access.
- Call a write tool on the Google Ads MCP or the Meta Ads MCP. Use those MCPs for reads only, with write tools turned off.
- Call a vendor API directly.

## Proposal shape

Each proposal is `{request, input}` in the exact shape of the future risky request in mktdata. One executor per request, keyed on the proposal id, so a proposal runs at most once.

| `request` | `input` |
|---|---|
| `pause_ad` | `{campaign_id, ad_id}` |
| `restart_ad` | `{campaign_id, ad_id}` |
| `set_budget` | `{campaign_id, daily_budget_cents}` |
| `create_ad` | `{campaign_id, ...}` — the full field list is in mktdata's `tool.json`; read it before you propose. It always names the approved library creative by `content_id`. |

- `campaign_id` (and `ad_id`) are **mktdata ids** from a mktdata read. Never a vendor id. If you only have a vendor id, look it up in mktdata first; if it is on the "to match" list, say so and do not propose.
- Money is integer cents in the business's currency.

Every proposal also carries the reason fields a person needs to decide fast:

- `before` → `after` (the field and both values)
- `reason`: the verdict and its math (from `ads-review`)
- `expected_effect`: what number should move, by how much, by when
- `evidence`: the rows or report the math came from, with Observed / Reported / Inferred labels

Example (Acme Plumbing, made-up ids):

```json
{
  "request": "set_budget",
  "input": {"campaign_id": "0193a7c2-0000-7000-8000-000000000001", "daily_budget_cents": 6000},
  "before": {"daily_budget_cents": 5000},
  "after": {"daily_budget_cents": 6000},
  "reason": "SCALE: cost per qualified lead $41 vs target $60 over 9 days, 7 qualified leads, stable trend. +20%.",
  "expected_effect": "About 1.2 more qualified leads a week at or under $60 each; read again in 5 days.",
  "evidence": "mktdata spend_by_campaign 2026-12-01..2026-12-09 (Observed); CRM qualified leads by campaign (Observed)"
}
```

The exact wrapper field names come from mktdata's `tool.json`. If they differ from this page, the tool wins.

## Standing limit (starting default; the owner changes it in config)

Act at once, then report, only for:

- Pause an ad or ad set.
- Restart an ad the limit itself paused, within 7 days.
- Budget change of up to ±20 % a day per campaign, with total daily spend at or under the daily cap.
- A new ad, only from a creative already approved in the library, only into an existing ad set.

Always queue for a person: larger budget moves, spend over a cap, new creative, new audience, new campaign, bids or bid strategy, targeting, conversion settings.

Safety:

- The hard monthly cap is never exceeded. The tool refuses a change that would break a cap.
- Every action is in the change table with one-press undo.
- One daily digest of actions and pending proposals.
- Loss rule: if limit actions lose money over the stated window, everything falls back to "queue everything" until a person resets it.

## Before mktdata is live

There is no queue yet. Write proposals, same shape, to `tracking/ads/proposals/YYYY-MM-DD.md` in the business repo (one fenced JSON block per proposal, then a status line `status: proposed`). A person makes the change in the ad platform by hand and edits the status line to `done by <name> <date>` or `rejected`. Nothing runs on its own in this mode: the standing limit needs mktdata.
