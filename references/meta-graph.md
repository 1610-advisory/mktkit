# Meta Graph Insights (Instagram + Facebook)

Pull per-post and account-level IG/FB insights (reach, saves, shares, views, watch
time, profile views, website taps, followers) that scheduling tools don't expose.
This is the generic procedure. **Client-specific values — env-var suffix, account
ids — live in the client's `knowledge/meta-config.md`, never here** (this repo is
public; see CLAUDE.md § Public-Repo Safety). No client names in this file.

## Tooling

| Script | Purpose |
|--------|---------|
| `scripts/meta_setup.py` | One-time: short-lived token → long-lived **Page** token, auto-discovers Page id + IG Business id, writes the env vars. |
| `scripts/meta_pull.py` | `media` (per-post insights) · `account` (account-level). `--client <SUFFIX> --days N --format json\|csv`. |

## Env vars (per client, in `~/.zshrc.local`, never committed)

```
META_PAGE_ID_<CLIENT>      # FB Page id
META_IG_ID_<CLIENT>        # IG Business account id
META_LONG_TOKEN_<CLIENT>   # long-lived PAGE access token (page-scoped)
```

## Prereqs (once, in the browser, as the Page admin)

1. A Meta Developer app — **reuse one app across clients** (App ID + Secret). One app can authorize many Pages.
2. The Instagram account must be **Business/Creator** and **linked to a Facebook Page** the user administers.
3. Graph API Explorer → pick the app → *User Token* → scopes: `instagram_basic, instagram_manage_insights, pages_show_list, pages_read_engagement, read_insights, business_management` → Generate → copy the short-lived token.

## THE token-add method (standard — Dawson's preferred, 2026-06-30)

Enter the three values at **interactive prompts** so secrets never land on the
command line, in shell history, or in a chat. `read -s` hides input. Then one-line
the setup so multi-line backslash pastes can't split:

```zsh
read "META_APP_ID?App ID: "
read -s "META_APP_SECRET?App Secret: "; echo
read -s "SHORT_TOKEN?Short-lived token: "; echo
export META_APP_ID META_APP_SECRET
python3 scripts/meta_setup.py --client <CLIENT> --short-token "$SHORT_TOKEN" --page-name "<Page name substring>" --write
```

`--write` appends the three `META_*_<CLIENT>` lines to `~/.zshrc.local` (idempotent).
Then `source ~/.zshrc.local` and test: `python3 scripts/meta_pull.py --client <CLIENT> account`.

Use this same flow for **any** token-add (it's the general pattern: prompt + `read -s` + single-line). App IDs are public; App Secrets and tokens are not — never paste the latter into a chat.

## Gotchas

- **A user token can be granted access to multiple clients' Pages at once.** That's fine — `me/accounts` lists them all, but `--page-name` isolates the one you want, and the script stores that **Page** token, which is page-scoped (can't read other Pages). So a stored `META_LONG_TOKEN_<CLIENT>` is siloed to one client even if the originating user token was broad.
- **Store the Page token, not the user token.** Page tokens derived from a long-lived user token are themselves long-lived (effectively non-expiring until password change / revoke). `meta_setup.py` already does this.
- If `--page-name` matches 0 or >1 Pages, the script lists them and stops — refine the substring.
- If no `instagram_business_account` is linked, the IG account isn't a Business account linked to that Page — fix in the IG app (Settings → linked Facebook Page) before retrying.
- Per-media insight metrics vary by media type; `meta_pull.py` requests a reels/post-appropriate set and falls back to the always-available subset on error. `like_count`/`comments_count` come from the media object (always present).
- Graph API version is pinned in the scripts (`v21.0`); bump together when Meta deprecates.

## Per-client config (store in client `knowledge/meta-config.md`)

- Env-var suffix, the IG/Page ids (after setup), pull cadence, and which metrics matter for that client. Mirror `ahrefs-config.md`.
