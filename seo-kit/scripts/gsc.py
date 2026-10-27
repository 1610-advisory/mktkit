# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-api-python-client>=2.0.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth>=2.0.0",
#     "httpx>=0.27",
#     "pyyaml>=6",
# ]
# ///
"""
Google Search Console pull for the weekly SEO kit.

Usage:
    uv run gsc.py inspect --config tracking/seo/config.yaml --out gsc-inspect.json
    uv run gsc.py queries --config tracking/seo/config.yaml --out gsc-queries.json
    uv run gsc.py page-two --config tracking/seo/config.yaml --out gsc-page-two.json
    uv run gsc.py all --config tracking/seo/config.yaml --out gsc.json

Authentication (tries in order):
    1. Cached OAuth token (~/.config/google/ga4-token.json), refresh if expired
    2. Service account at GOOGLE_APPLICATION_CREDENTIALS
    3. Interactive OAuth flow (opens a browser, requires --oauth-client)

Environment variables:
    GOOGLE_APPLICATION_CREDENTIALS  path to a service account JSON file
    GA4_OAUTH_CLIENT                path to an OAuth client JSON (or --oauth-client)

The Search Console scope is https://www.googleapis.com/auth/webmasters.readonly.
Property comes from config key gsc_property. Queries cover the last 28 days
ending 3 days ago (Search Console is incomplete for the most recent days).
URL Inspection is limited to 200 URLs per run, 0.2 s apart.

Commands:
    inspect     Sitemap URLs through URL Inspection
    queries     Search Analytics, query + page, plus totals
    page-two    Queries with average position 8 to 20
    all         One gsc.json with inspect, queries, page_two, and summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

TOKEN_PATH = Path.home() / ".config" / "google" / "ga4-token.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
INSPECT_LIMIT = 200
INSPECT_DELAY_S = 0.2
ANALYTICS_ROW_LIMIT = 1000
WINDOW_DAYS = 28
WINDOW_LAG_DAYS = 3
USER_AGENT = "seo-kit/0.1"


def load_client(path: str) -> dict:
    """Import seo_config (owned by the crawl job) and load the client config."""
    try:
        from seo_config import load_config
    except ImportError:
        print(
            "Error: seo-kit/scripts/seo_config.py is missing (it is provided separately).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        return load_config(path)
    except Exception as exc:
        print(f"Error: could not load config: {exc}", file=sys.stderr)
        raise SystemExit(1)


def require_property(config: dict) -> str:
    prop = (config.get("gsc_property") or "").strip()
    if not prop:
        print("Error: config gsc_property is empty.", file=sys.stderr)
        raise SystemExit(1)
    return prop


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(xml_text: str) -> tuple[str, list[str]]:
    """Return ('index' or 'urlset', loc values). Raises ValueError on bad XML."""
    text = xml_text.lstrip("\ufeff").strip()
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"sitemap XML is not parseable: {exc}") from exc
    kind = "index" if _local_name(root.tag) == "sitemapindex" else "urlset"
    locs = []
    for el in root.iter():
        if _local_name(el.tag) == "loc" and el.text and el.text.strip():
            locs.append(el.text.strip())
    return kind, locs


def collect_sitemap_urls(fetch_text, sitemap_url: str, seen: set[str] | None = None) -> list[str]:
    """Expand a sitemap or sitemap index into page URLs. fetch_text(url) -> str."""
    seen = seen if seen is not None else set()
    if sitemap_url in seen:
        return []
    seen.add(sitemap_url)
    kind, locs = parse_sitemap(fetch_text(sitemap_url))
    if kind == "index":
        pages: list[str] = []
        for loc in locs:
            pages.extend(collect_sitemap_urls(fetch_text, loc, seen))
        return pages
    return locs


def fetch_text(url: str, timeout: float = 30) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def analytics_window(today: date | None = None) -> tuple[str, str]:
    """Inclusive 28-day window whose last day is 3 days before today."""
    today = today or date.today()
    end = today - timedelta(days=WINDOW_LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start.isoformat(), end.isoformat()


def build_inspect_body(inspection_url: str, site_url: str) -> dict:
    return {
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": "en-US",
    }


def build_analytics_body(
    start: str,
    end: str,
    dimensions: list[str] | None,
    row_limit: int,
) -> dict:
    body: dict = {
        "startDate": start,
        "endDate": end,
        "rowLimit": row_limit,
        "startRow": 0,
    }
    if dimensions:
        body["dimensions"] = dimensions
    return body


def parse_inspection(url: str, payload: dict) -> dict:
    """Pull the index-status fields the weekly report keeps."""
    idx = (payload.get("inspectionResult") or {}).get("indexStatusResult") or {}
    google = idx.get("googleCanonical")
    user = idx.get("userCanonical")
    return {
        "url": url,
        "verdict": idx.get("verdict"),
        "coverageState": idx.get("coverageState"),
        "indexingState": idx.get("indexingState"),
        "robotsTxtState": idx.get("robotsTxtState"),
        "pageFetchState": idx.get("pageFetchState"),
        "lastCrawlTime": idx.get("lastCrawlTime"),
        "googleCanonical": google,
        "userCanonical": user,
        "canonical_mismatch": google != user,
        "error": None,
    }


def inspection_error(url: str, message: str) -> dict:
    return {
        "url": url,
        "verdict": None,
        "coverageState": None,
        "indexingState": None,
        "robotsTxtState": None,
        "pageFetchState": None,
        "lastCrawlTime": None,
        "googleCanonical": None,
        "userCanonical": None,
        "canonical_mismatch": False,
        "error": message,
    }


def inspect_urls(
    urls: list[str],
    site_url: str,
    inspect_fn,
    *,
    limit: int = INSPECT_LIMIT,
    delay: float = INSPECT_DELAY_S,
    sleep_fn=time.sleep,
) -> list[dict]:
    """Call inspect_fn(url, site_url) for up to `limit` URLs, `delay` seconds apart."""
    chosen = urls[:limit]
    out = []
    for i, url in enumerate(chosen):
        if i and delay:
            sleep_fn(delay)
        try:
            raw = inspect_fn(url, site_url)
            out.append(parse_inspection(url, raw))
        except Exception as exc:  # network/API failure for this URL; keep going
            out.append(inspection_error(url, f"{type(exc).__name__}: {exc}"))
    return out


def parse_analytics_rows(payload: dict) -> list[dict]:
    rows = []
    for row in payload.get("rows") or []:
        keys = row.get("keys") or []
        rows.append(
            {
                "query": keys[0] if len(keys) > 0 else None,
                "page": keys[1] if len(keys) > 1 else None,
                "clicks": int(row.get("clicks") or 0),
                "impressions": int(row.get("impressions") or 0),
                "ctr": round(float(row.get("ctr") or 0), 4),
                "position": round(float(row.get("position") or 0), 1),
                "_position": float(row.get("position") or 0),
            }
        )
    return rows


def parse_totals(payload: dict) -> dict:
    rows = payload.get("rows") or []
    if not rows:
        return {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
    row = rows[0]
    return {
        "clicks": int(row.get("clicks") or 0),
        "impressions": int(row.get("impressions") or 0),
        "ctr": round(float(row.get("ctr") or 0), 4),
        "position": round(float(row.get("position") or 0), 1),
    }


def page_two_rows(rows: list[dict], min_impressions: int) -> list[dict]:
    """Queries whose average position is 8 to 20 inclusive, impressions at or above the floor."""
    picked = []
    for row in rows:
        position = row.get("_position", row.get("position"))
        if position is None:
            continue
        if 8 <= float(position) <= 20 and int(row.get("impressions") or 0) >= min_impressions:
            picked.append({k: v for k, v in row.items() if k != "_position"})
    picked.sort(key=lambda row: (-row["impressions"], row.get("query") or "", row.get("page") or ""))
    return picked


def public_rows(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if k != "_position"} for row in rows]


def build_gsc_summary(totals: dict, inspections: list[dict]) -> dict:
    indexed = sum(1 for row in inspections if row.get("verdict") == "PASS")
    return {
        "clicks": totals.get("clicks", 0),
        "impressions": totals.get("impressions", 0),
        "ctr": totals.get("ctr", 0),
        "position": totals.get("position", 0),
        "indexed": indexed,
        "not_indexed": len(inspections) - indexed,
    }


def _cached_credentials():
    if not TOKEN_PATH.exists():
        return None
    try:
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
            return creds
    except Exception:
        return None
    return None


def _service_account_credentials():
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return None
    if not Path(path).is_file():
        print(f"Error: GOOGLE_APPLICATION_CREDENTIALS file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def get_credentials(oauth_client_path: str | None = None):
    """Cached OAuth, then service account, then interactive flow. Never prints secrets."""
    creds = _cached_credentials()
    if creds is not None:
        return creds
    creds = _service_account_credentials()
    if creds is not None:
        return creds

    client_file = oauth_client_path or os.environ.get("GA4_OAUTH_CLIENT")
    if not client_file:
        print(
            "Error: No Search Console credentials found.\n"
            "\n"
            "Options:\n"
            "  1. Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON file\n"
            "  2. Set GA4_OAUTH_CLIENT or pass --oauth-client for the interactive flow\n"
            "  3. Reuse a cached token at ~/.config/google/ga4-token.json\n"
            "\n"
            "The token must include the webmasters.readonly scope. If you authenticated\n"
            "for Analytics only, re-auth so Search Console is granted.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not Path(client_file).is_file():
        print(f"Error: OAuth client file not found: {client_file}", file=sys.stderr)
        raise SystemExit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token cached at {TOKEN_PATH}", file=sys.stderr)
    return creds


def get_service(oauth_client_path: str | None = None):
    from googleapiclient.discovery import build

    return build("searchconsole", "v1", credentials=get_credentials(oauth_client_path), cache_discovery=False)


def make_inspect_fn(service):
    def inspect_fn(url: str, site_url: str) -> dict:
        body = build_inspect_body(url, site_url)
        return service.urlInspection().index().inspect(body=body).execute()

    return inspect_fn


def fetch_analytics(service, site_url: str, today: date | None = None) -> tuple[list[dict], dict, tuple[str, str]]:
    start, end = analytics_window(today)
    try:
        detail = service.searchanalytics().query(
            siteUrl=site_url,
            body=build_analytics_body(start, end, ["query", "page"], ANALYTICS_ROW_LIMIT),
        ).execute()
        totals_raw = service.searchanalytics().query(
            siteUrl=site_url,
            body=build_analytics_body(start, end, None, 1),
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"Search Analytics request failed: {type(exc).__name__}") from exc
    return parse_analytics_rows(detail), parse_totals(totals_raw), (start, end)


def sitemap_urls(config: dict) -> list[str]:
    sitemap = (config.get("sitemap") or "").strip()
    if not sitemap:
        print("Error: config sitemap is empty.", file=sys.stderr)
        raise SystemExit(1)
    try:
        return collect_sitemap_urls(fetch_text, sitemap)
    except Exception as exc:
        print(f"Error: could not read sitemap: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2)


def _usage_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pull Google Search Console inspection and query data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _error(message: str) -> None:
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)

    parser.error = _error  # type: ignore[method-assign]
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _usage_parser()
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--config", required=True, help="Path to tracking/seo/config.yaml")
    shared.add_argument("--out", required=True, help="JSON output path")
    shared.add_argument("--oauth-client", help="Path to OAuth client secrets JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect", parents=[shared], help="URL Inspection for sitemap URLs")
    sub.add_parser("queries", parents=[shared], help="Search Analytics query + page, plus totals")
    page_two = sub.add_parser("page-two", parents=[shared], help="Position 8 to 20 queries")
    page_two.add_argument("--min-impressions", type=int, default=20)
    all_cmd = sub.add_parser("all", parents=[shared], help="Inspection, queries, and page-two in one file")
    all_cmd.add_argument("--min-impressions", type=int, default=20)
    return parser.parse_args(argv)


def cmd_inspect(args, service, config, prop: str) -> int:
    urls = sitemap_urls(config)
    rows = inspect_urls(urls, prop, make_inspect_fn(service))
    payload = {"generated_at": utc_now(), "property": prop, "inspect": rows}
    write_json(args.out, payload)
    failed = sum(1 for row in rows if row.get("error"))
    indexed = sum(1 for row in rows if row.get("verdict") == "PASS")
    print(
        f"gsc inspect: {len(rows)} urls (of {len(urls)} in sitemap), {indexed} indexed, {failed} failed",
        file=sys.stderr,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 2 if failed else 0


def cmd_queries(args, service, prop: str) -> int:
    try:
        rows, totals, window = fetch_analytics(service, prop)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    payload = {
        "generated_at": utc_now(),
        "property": prop,
        "summary": totals,
        "queries": public_rows(rows),
    }
    write_json(args.out, payload)
    start, end = window
    print(
        f"gsc queries: {start} to {end}, {len(rows)} rows, {totals['clicks']} clicks",
        file=sys.stderr,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


def cmd_page_two(args, service, prop: str) -> int:
    try:
        rows, _totals, window = fetch_analytics(service, prop)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    picked = page_two_rows(rows, args.min_impressions)
    payload = {"generated_at": utc_now(), "property": prop, "page_two": picked}
    write_json(args.out, payload)
    start, end = window
    print(
        f"gsc page-two: {len(picked)} queries, position 8-20, impressions >= {args.min_impressions} ({start} to {end})",
        file=sys.stderr,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


def cmd_all(args, service, config, prop: str) -> int:
    urls = sitemap_urls(config)
    rows = inspect_urls(urls, prop, make_inspect_fn(service))
    try:
        query_rows, totals, window = fetch_analytics(service, prop)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    page_two = page_two_rows(query_rows, args.min_impressions)
    summary = build_gsc_summary(totals, rows)
    payload = {
        "generated_at": utc_now(),
        "property": prop,
        "summary": summary,
        "inspect": rows,
        "queries": public_rows(query_rows),
        "page_two": page_two,
    }
    write_json(args.out, payload)
    failed = sum(1 for row in rows if row.get("error"))
    start, end = window
    print(
        f"gsc all: {summary['clicks']} clicks, {summary['impressions']} impressions, "
        f"{summary['indexed']} indexed, {summary['not_indexed']} not indexed, "
        f"{len(page_two)} page-two queries ({start} to {end})",
        file=sys.stderr,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 2 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_client(args.config)
    prop = require_property(config)
    # Reject a property that is not a Search Console site identifier before any API call.
    if not (prop.startswith("sc-domain:") or urlparse(prop).scheme in ("http", "https")):
        print("Error: gsc_property must be sc-domain:HOST or an http(s) URL.", file=sys.stderr)
        return 1
    try:
        service = get_service(args.oauth_client)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: could not build Search Console client: {type(exc).__name__}", file=sys.stderr)
        return 2
    if args.command == "inspect":
        return cmd_inspect(args, service, config, prop)
    if args.command == "queries":
        return cmd_queries(args, service, prop)
    if args.command == "page-two":
        return cmd_page_two(args, service, prop)
    return cmd_all(args, service, config, prop)


if __name__ == "__main__":
    raise SystemExit(main())
