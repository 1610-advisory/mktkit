# Platform Backfill (Reviving a Dormant Social Account)

Generic procedure for back-posting a client's existing Instagram catalog to a platform that went dormant (TikTok, YouTube Shorts, a neglected Facebook page), using the Meta Graph API as the source of truth and Post Bridge as the scheduler. First executed July 2026 (a large back-catalog over several months). **Client-specific values — account IDs, tokens, restricted-content rules — live in the client's repo, never here** (see CLAUDE.md § Public-Repo Safety).

The shape: **inventory → exclude → schedule → execute → verify**, with a paper trail in the client repo at every step.

## 1. Inventory — find the gap

1. Find the target platform's **last post date** (scroll the profile; sort by Latest).
2. Pull the full source catalog via the Meta Graph API: `GET /{ig-user-id}/media?fields=id,timestamp,media_type,media_product_type,caption,permalink&limit=100`, following `paging.next`. Filter to `media_product_type == REELS` (or whatever you're porting).
3. The gap = everything newer than the target's last post. Report counts by year — the client decides scope (full gap vs. recent era), pacing, and ordering. **Get sign-off on scope/pace/order before creating anything.**
4. Fetch download links in batches: `GET /?ids=<50 comma-separated ids>&fields=id,media_url`. `media_url` is a CDN link to the owned media file — this is official API access to your own content, not scraping. **A missing `media_url` usually means licensed music / rights restrictions — auto-exclude those; you can't legally re-post that audio anyway.**

## 2. Exclusion passes (run ALL of these before scheduling)

Programmatic caption scans over the gap list:

| Pass | Looking for | Action |
|---|---|---|
| Brand-safety blocklist | Projects/subjects the client has restricted (every client has some — check their repo rules) | Hard-exclude; when a caption pattern is ambiguous, exclude conservatively and list for rescue |
| PII / naming rules | Client surnames, addresses, anything violating the client's public-naming policy | Exclude (or fix) — old posts predate current rules |
| Dated content | Holidays ("Happy 4th…"), one-off events, merch/promo deadlines | Exclude — a 2024 holiday post reposted in 2026 reads as botlike |
| Pure-CTA posts | "Link in bio" ads with no standalone content | Exclude — the link doesn't exist on the new platform |
| Duplicates | Same caption posted twice at the source | Keep first occurrence |
| Caption-less | Can't verify content programmatically | Hold for human review — never post blind |

**Caption surgery:** posts kept despite a "link in bio" line get that sentence stripped (the new platform's bio may have no link). Track a `caption_modified` flag in the manifest. Otherwise reuse source captions verbatim — they already shipped once.

## 3. Scheduling — look human, not cron

- **Order:** chronological **oldest-first**, so project arcs (demo → progress → reveal) replay in narrative order on the new grid.
- **Pace:** ~2/day is safe and clears ~180 posts in 3 months. The bot-flag risk is **bursts and machine-stamped times**, not steady volume.
- **Slots:** two platform-normal local times (e.g. ~10am + ~6:30pm local) with **per-post random jitter of ±20 min, seeded** so the schedule is reproducible.
- Skip slots that collide with already-scheduled fresh content on day one.
- New content keeps flowing on top — add the revived platform to the client's standing fan-out at the same time.

## 4. Execution — resume-safe runner

Per post: download `media_url` → `POST /v1/media/create-upload-url` → `PUT` bytes → `POST /v1/posts` with `{caption, media:[id], social_accounts:[<target-id>], is_draft:false, scheduled_at}` → delete local file.

Runner requirements (all learned the useful way):

- **Progress journal** (append-only JSONL keyed by source media id) so a crash resumes where it left off — never re-creates posts already made.
- Validate the download (min byte size) before uploading — an expired `media_url` yields a tiny error body, not an MP4.
- Retry each post once on failure; **abort after ~5 consecutive failures** (systemic problem) rather than plowing through the catalog.
- ~3s sleep between posts; the transfer time dominates anyway (~15s/post for 20-80 MB reels).
- Run it in the background; monitor the log, not the terminal.
- **Test ONE post through the full pipeline first** and confirm it lands as `status: scheduled` before batching the rest.

## 5. Verify + leave the paper trail

- Count scheduled posts targeting the account: page through `GET /v1/posts?status=scheduled&limit=100`. Expect exactly your manifest count (+ any pre-existing). Parse with a **lenient JSON decoder** — captions can carry raw control characters that strict parsers reject.
- Watch the first day's publishes via `GET /v1/post-results` — a revived account's connection isn't proven until something actually publishes.
- Commit to the **client's** repo: `manifest.csv` (per-post: source id/date/permalink, slot, caption, modified flag), `excluded.md` (every exclusion + reason, rescue instructions), `postbridge-post-ids.csv` (the retry handle if a slot fails).

## Gotchas

- `PATCH /v1/posts/{id}` can return **HTTP 500 while still applying the change** — GET to verify before retrying, or you'll double-apply.
- `GET /v1/social-accounts` silently truncates at `limit=10` — always request `?limit=50`+ and check `meta`.
- Every uploaded file **persists in the Post Bridge media library with a reusable `media_id`** — a completed backfill doubles as a media archive for throwback posts, story cut-downs, and re-runs with zero re-downloading.
- Profile prep (bio, etc.) is part of the revival — do it before the first post lands, and get client sign-off on the copy.
