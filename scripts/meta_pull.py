#!/usr/bin/env python3
"""
Meta (Instagram + Facebook) insights pull — Graph API.

Mirrors the ga4_pull.py / gads_pull.py pattern: client-agnostic, configured by
per-client env vars, JSON/CSV output. NO client names in this file (public repo).

Env vars (suffix = --client, uppercased; default suffix from $META_CLIENT):
    META_LONG_TOKEN_<CLIENT>   long-lived Page access token (from meta_setup.py)
    META_IG_ID_<CLIENT>        Instagram Business account id (numeric)
    META_PAGE_ID_<CLIENT>      Facebook Page id (numeric)   [optional, FB metrics]

Usage:
    python3 meta_pull.py --client ACME media --days 30 --format csv
    python3 meta_pull.py --client ACME account --days 30
    python3 meta_pull.py --client ACME media --format json > out.json

Commands:
    media     Recent IG posts with per-post insights (reach, likes, comments,
              saves, shares, views, total_interactions). The "how did content do" view.
    account   IG account-level insights over the period (reach, profile views,
              follower count, website taps).

No external deps — uses urllib (run with system python3).
"""
import argparse, json, os, sys, urllib.parse, urllib.request, urllib.error
from datetime import date, timedelta

GRAPH = "https://graph.facebook.com/v21.0"


def env(name, client):
    v = os.environ.get(f"{name}_{client}")
    if not v:
        sys.exit(f"Error: env var {name}_{client} not set. Run meta_setup.py first "
                 f"(or check the client's knowledge/meta-config.md).")
    return v


def get(path, params):
    url = f"{GRAPH}/{path}?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"_http_error": e.code, "_body": body}


def die_on_error(resp, ctx):
    if isinstance(resp, dict) and resp.get("error"):
        sys.exit(f"Graph API error during {ctx}: {json.dumps(resp['error'])}")
    if isinstance(resp, dict) and resp.get("_http_error"):
        sys.exit(f"HTTP {resp['_http_error']} during {ctx}: {resp['_body'][:400]}")


def out(rows, fmt):
    if fmt == "csv":
        if not rows:
            print(""); return
        headers = list(rows[0].keys())
        print(",".join(headers))
        for r in rows:
            print(",".join('"%s"' % str(r.get(h, "")).replace('"', "'").replace("\n", " ")
                           if isinstance(r.get(h), str) else str(r.get(h, "")) for h in headers))
    else:
        print(json.dumps(rows, indent=2))


# Per-media insight metrics differ by media type. Request a tolerant set; on error
# fall back to the always-available subset. like_count/comments_count come from the
# media object itself (always present), so insights only adds reach/saves/shares/views.
REEL_METRICS = "reach,saved,shares,total_interactions,views,ig_reels_avg_watch_time"
POST_METRICS = "reach,saved,shares,total_interactions,views"
FALLBACK_METRICS = "reach,saved,total_interactions"


def media_insights(media_id, product_type, token):
    metrics = REEL_METRICS if product_type == "REELS" else POST_METRICS
    resp = get(f"{media_id}/insights", {"metric": metrics, "access_token": token})
    if isinstance(resp, dict) and (resp.get("error") or resp.get("_http_error")):
        resp = get(f"{media_id}/insights", {"metric": FALLBACK_METRICS, "access_token": token})
    vals = {}
    for m in (resp.get("data", []) if isinstance(resp, dict) else []):
        v = m.get("values", [{}])
        vals[m["name"]] = v[0].get("value") if v else None
    return vals


def cmd_media(args, token):
    ig = env("META_IG_ID", args.client)
    since = (date.today() - timedelta(days=args.days)).isoformat()
    fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
    resp = get(f"{ig}/media", {"fields": fields, "limit": args.limit,
                               "since": since, "access_token": token})
    die_on_error(resp, "list media")
    rows = []
    for m in resp.get("data", []):
        ins = media_insights(m["id"], m.get("media_product_type"), token)
        cap = (m.get("caption") or "").replace("\n", " ")
        rows.append({
            "date": m.get("timestamp", "")[:10],
            "type": m.get("media_product_type") or m.get("media_type"),
            "caption": cap[:80],
            "reach": ins.get("reach"),
            "views": ins.get("views"),
            "likes": m.get("like_count"),
            "comments": m.get("comments_count"),
            "saves": ins.get("saved"),
            "shares": ins.get("shares"),
            "total_interactions": ins.get("total_interactions"),
            "avg_watch_s": round(ins["ig_reels_avg_watch_time"] / 1000, 1)
                           if ins.get("ig_reels_avg_watch_time") else None,  # API returns ms
            "permalink": m.get("permalink"),
        })
    out(rows, args.format)


def cmd_account(args, token):
    ig = env("META_IG_ID", args.client)
    # follower count (snapshot) + period insights
    prof = get(ig, {"fields": "followers_count,media_count,username", "access_token": token})
    die_on_error(prof, "account profile")
    since = (date.today() - timedelta(days=args.days)).isoformat()
    until = date.today().isoformat()
    ins = get(f"{ig}/insights", {"metric": "reach,profile_views,website_clicks",
                                 "period": "day", "since": since, "until": until,
                                 "metric_type": "total_value", "access_token": token})
    period = {}
    for m in (ins.get("data", []) if isinstance(ins, dict) else []):
        tv = m.get("total_value", {})
        period[m["name"]] = tv.get("value") if isinstance(tv, dict) else None
    row = [{
        "username": prof.get("username"),
        "followers_count": prof.get("followers_count"),
        "media_count": prof.get("media_count"),
        f"reach_{args.days}d": period.get("reach"),
        f"profile_views_{args.days}d": period.get("profile_views"),
        f"website_clicks_{args.days}d": period.get("website_clicks"),
    }]
    out(row, args.format)


def main():
    p = argparse.ArgumentParser(description="Pull Instagram/Facebook insights via Meta Graph API")
    p.add_argument("--client", default=os.environ.get("META_CLIENT", ""),
                   help="Client env-var suffix (e.g. ACME). Or set $META_CLIENT.")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--format", choices=["json", "csv"], default="json")
    p.add_argument("command", choices=["media", "account"])
    args = p.parse_args()
    if not args.client:
        sys.exit("Error: --client SUFFIX required (or set $META_CLIENT).")
    args.client = args.client.upper()
    token = env("META_LONG_TOKEN", args.client)
    {"media": cmd_media, "account": cmd_account}[args.command](args, token)


if __name__ == "__main__":
    main()
