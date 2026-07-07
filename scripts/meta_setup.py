#!/usr/bin/env python3
"""
Meta Graph one-time setup — exchange a short-lived token for a long-lived Page
token, auto-discover the Page id + Instagram Business account id, and emit the
per-client env vars meta_pull.py needs. Client-agnostic (no client names here).

You run this in YOUR terminal. The token never needs to be pasted into a chat.

Prereqs (done once in the browser, as the Meta admin of the Page):
  1. A Meta Developer app (reuse one across clients). Note its App ID + Secret.
  2. The Instagram account must be a Business/Creator account LINKED to a
     Facebook Page you administer.
  3. Graph API Explorer (developers.facebook.com/tools/explorer):
       - pick the app, User token,
       - add permissions: instagram_basic, instagram_manage_insights,
         pages_show_list, pages_read_engagement, read_insights, business_management
       - Generate Access Token, copy it (this is the SHORT-lived token).

Then:
    python3 meta_setup.py --client ACME \
        --app-id <APP_ID> --app-secret <APP_SECRET> \
        --short-token <SHORT_TOKEN> [--page-name "Acme Co"] [--write]

  --page-name   substring to auto-pick the Page (else it lists them to choose).
  --write       append the export lines to ~/.zshrc.local (idempotent).
                Without it, the lines are printed for you to add yourself.

No external deps (urllib).
"""
import argparse, json, os, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path

GRAPH = "https://graph.facebook.com/v21.0"


def get(path, params):
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Graph API HTTP {e.code}: {e.read().decode()[:500]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--client", required=True, help="env suffix, e.g. ACME")
    p.add_argument("--app-id", default=os.environ.get("META_APP_ID"))
    p.add_argument("--app-secret", default=os.environ.get("META_APP_SECRET"))
    p.add_argument("--short-token", required=True)
    p.add_argument("--page-name", help="substring to auto-pick the Page")
    p.add_argument("--write", action="store_true", help="append to ~/.zshrc.local")
    a = p.parse_args()
    client = a.client.upper()
    if not a.app_id or not a.app_secret:
        sys.exit("Need --app-id and --app-secret (or env META_APP_ID / META_APP_SECRET).")

    # 1. short -> long-lived user token
    exch = get("oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": a.app_id,
        "client_secret": a.app_secret, "fb_exchange_token": a.short_token})
    long_user = exch.get("access_token")
    if not long_user:
        sys.exit(f"Token exchange failed: {json.dumps(exch)}")
    print("✓ exchanged for long-lived user token", file=sys.stderr)

    # 2. pages the user administers (page tokens here are long-lived)
    pages = get("me/accounts", {"fields": "name,id,access_token", "access_token": long_user})
    data = pages.get("data", [])
    if not data:
        sys.exit("No Pages found for this user. Confirm Page admin + pages_show_list scope.")
    if a.page_name:
        match = [pg for pg in data if a.page_name.lower() in pg["name"].lower()]
        if len(match) != 1:
            print("Pages found:", file=sys.stderr)
            for pg in data:
                print(f"  {pg['id']}  {pg['name']}", file=sys.stderr)
            sys.exit(f"--page-name '{a.page_name}' matched {len(match)} pages; refine it.")
        page = match[0]
    elif len(data) == 1:
        page = data[0]
    else:
        print("Multiple Pages — pass --page-name to pick one:", file=sys.stderr)
        for pg in data:
            print(f"  {pg['id']}  {pg['name']}", file=sys.stderr)
        sys.exit(1)
    page_id, page_token = page["id"], page["access_token"]
    print(f"✓ Page: {page['name']} ({page_id})", file=sys.stderr)

    # 3. linked IG Business account
    ig = get(page_id, {"fields": "instagram_business_account{id,username}", "access_token": page_token})
    iba = ig.get("instagram_business_account")
    if not iba:
        sys.exit("No instagram_business_account linked to this Page. In the IG app: "
                 "Settings → convert to Business/Creator → link to this Facebook Page.")
    ig_id, ig_user = iba["id"], iba.get("username", "?")
    print(f"✓ Instagram: @{ig_user} ({ig_id})", file=sys.stderr)

    lines = [
        f'export META_PAGE_ID_{client}={page_id}',
        f'export META_IG_ID_{client}={ig_id}',
        f'export META_LONG_TOKEN_{client}={page_token}',
    ]
    if a.write:
        rc = Path.home() / ".zshrc.local"
        existing = rc.read_text() if rc.exists() else ""
        with rc.open("a") as f:
            f.write(f"\n# Meta Graph — {client} (added by meta_setup.py)\n")
            for ln in lines:
                key = ln.split("=", 1)[0].replace("export ", "")
                if key in existing:
                    print(f"  (skip {key}; already in ~/.zshrc.local — update manually)", file=sys.stderr)
                    continue
                f.write(ln + "\n")
        print(f"✓ wrote env vars to {rc} — run: source {rc}", file=sys.stderr)
    else:
        print("\n# add these to ~/.zshrc.local, then `source ~/.zshrc.local`:")
        print("\n".join(lines))
    print(f"\nThen test:  python3 meta_pull.py --client {client} account", file=sys.stderr)


if __name__ == "__main__":
    main()
