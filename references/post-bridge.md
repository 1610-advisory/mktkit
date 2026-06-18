# Post Bridge Integration (Social Scheduling)

Post Bridge ([post-bridge.com](https://post-bridge.com)) schedules posts to multiple social platforms (Instagram, Facebook, X, LinkedIn, YouTube, TikTok, etc.) through one API. This is the generic procedure. **Client-specific values — API key env var, connected social-account IDs — live in the client's `knowledge/` folder, never here** (this repo is public; see CLAUDE.md § Public-Repo Safety).

## Auth & base

- **Base URL:** `https://api.post-bridge.com/v1`
- **Header:** `Authorization: Bearer <API_KEY>` (+ `Content-Type: application/json` for JSON calls)
- **API key:** per-client, stored in the operator's `~/.zshrc.local` as an env var (e.g. `$POSTBRIDGE_API_KEY_<CLIENT>`). Get the key from the Post Bridge dashboard.
- ⚠️ **A key is account-wide.** `GET /v1/social-accounts` returns *every* connected account on that Post Bridge login (potentially multiple brands). **Always pin posts to the specific account IDs you mean** — never assume the key is scoped to one client.

## Endpoints used

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/v1/social-accounts` | List connected accounts → `{data:[{id, platform, username}]}`. `id` is a **number**. Paginated — `meta.next` holds the next page URL; page through it so you don't miss accounts past the default limit. |
| POST | `/v1/media/create-upload-url` | Request a signed upload URL for one file. |
| PUT | `<upload_url>` | Upload the raw file bytes to the returned signed URL (Supabase storage). |
| POST | `/v1/posts` | Create a post (instant or scheduled). |
| GET | `/v1/posts/{id}` | Verify a post's status/media/accounts. |
| GET | `/v1/posts` | List posts (`{data, meta}`, paginated via `meta.next`). |

## Media upload (two steps, per file)

1. `POST /v1/media/create-upload-url` with body `{ "mime_type", "size_bytes", "name" }`.
   - `mime_type` ∈ `image/png`, `image/jpeg`, `video/mp4`, `video/quicktime`, `application/pdf`.
   - **Returns `201`** (not 200) with `{ media_id, upload_url, name }`. Accept both 200 and 201.
2. `PUT` the file bytes to `upload_url` with header `Content-Type: <mime_type>` (must match). Expect `200/204`.
   - The signed URL is Supabase storage; large videos upload fine via `curl --upload-file`.
3. Keep `media_id` for the post.

## Create a scheduled post

`POST /v1/posts`:

```json
{
  "caption": "post text + hashtags",
  "social_accounts": [<ACCOUNT_ID>, ...],
  "scheduled_at": "2026-06-06T09:30:00-05:00",
  "media": ["<media_id>", "<media_id>", ...]
}
```

- **Required:** `caption`, `social_accounts` (array of numeric IDs).
- **`scheduled_at`:** ISO-8601 date-time. Send a local time **with explicit offset** (e.g. `-05:00` for US Central during DST) — the API stores/returns it in UTC, so `09:30-05:00` comes back as `14:30:00+00:00`. Omit/null to **post instantly**. Cannot combine with `use_queue`.
- **`media`:** array of `media_id`s. **Carousel = multiple image media_ids in display order.** Video = one media_id. (`media_urls` is an alternative for publicly-hosted files; ignored if `media` is set.)
- **`processing_enabled`** (default `true`): Post Bridge transcodes video so it posts reliably. Leave on for video.
- **`use_queue`**: `true` (or `{timezone}`) auto-slots into your saved queue instead of `scheduled_at`.
- Response includes `status` ∈ `scheduled | processing | posted | failed`, plus `warnings` (e.g. platforms that publish drafts immediately).

## Verify

`GET /v1/posts/{id}` and confirm `status: "scheduled"`, the right `scheduled_at` (UTC), `social_accounts`, and `media`. Scheduled posts sit in the future, so there's a safety window to fix mistakes before they publish.

## Gotchas (learned in practice)

- **Account IDs drift — pull `GET /v1/social-accounts` fresh before targeting.** The IDs a client's `knowledge/` file records are a convenience cache, not a contract. Disconnecting and reconnecting an account mints a **new** ID, and new brands get added to the login over time, so a documented ID can silently point at nothing (or at the wrong handle). Confirm the current ID/username from a live pull at the start of any posting session, then update the client doc if it drifted. Treat the stored IDs as "probably right, verify" — never paste them into a `social_accounts` array unchecked.
- `create-upload-url` returns **201**, not 200 — don't treat that as failure.
- `scheduled_at` round-trips to UTC; send an explicit offset so you're not off by the timezone.
- The key sees all brands on the login — pin `social_accounts` explicitly every time.
- Instagram/Facebook carousels: pass image `media_id`s in order; the array order is the swipe order.
- Don't re-run a create step blindly — each `create-upload-url` mints a new (harmless, orphan) media record, but re-running `POST /v1/posts` creates a duplicate scheduled post.

## Per-client config (store in client `knowledge/`)

- API key env var name
- Connected social-account IDs + which platform/handle each is
- Default posting cadence/times and timezone
- Whether scheduling is via Post Bridge vs. native vs. Typefully (per client)
