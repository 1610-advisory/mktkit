# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-api-python-client>=2.0.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth>=2.0.0",
# ]
# ///
"""
GSC Data Pull — pulls search performance data from Google Search Console.

Usage:
    uv run gsc_pull.py [OPTIONS] COMMAND [ARGS]

Authentication (tries in order):
    1. Cached OAuth token (~/.config/google/ga4-token.json)
    2. If expired, refresh it
    3. Interactive OAuth flow (opens browser, requires --oauth-client)

Environment variables:
    GSC_SITE_URL         — Search Console site URL (or pass --site-url)
                           e.g. "sc-domain:example.com"
                           or "https://www.example.com/"
    GA4_OAUTH_CLIENT     — path to OAuth client JSON (or pass --oauth-client)

Commands:
    top-queries         Top search queries by clicks
    top-pages           Top pages by clicks
    query-pages         Queries x pages cross-reference
    devices             Device breakdown
    countries           Country breakdown
    report              Custom report (specify dimensions)
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from googleapiclient.discovery import build

TOKEN_PATH = Path.home() / ".config" / "google" / "ga4-token.json"
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]

VALID_DIMENSIONS = {"query", "page", "device", "country", "date"}


def get_service(oauth_client_path: str | None = None):
    """Create an authenticated Search Console service. Tries cached OAuth, then interactive flow."""

    # 1. Try cached OAuth token
    if TOKEN_PATH.exists():
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds.valid:
                return build("searchconsole", "v1", credentials=creds)
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                return build("searchconsole", "v1", credentials=creds)
        except Exception:
            pass

    # 2. Interactive OAuth flow — needs client secrets file
    client_file = oauth_client_path or os.environ.get("GA4_OAUTH_CLIENT")
    if not client_file:
        print(
            "Error: No credentials found.\n"
            "\n"
            "Options:\n"
            "  1. Set GA4_OAUTH_CLIENT env var to your OAuth client JSON path\n"
            "  2. Pass --oauth-client /path/to/client_secret.json\n"
            "\n"
            "To create OAuth credentials:\n"
            "  GCP Console -> APIs & Services -> Credentials -> Create -> OAuth client ID -> Desktop app\n"
            "  Download the JSON and pass it here.\n"
            "\n"
            "Note: Reuses the same token as ga4_pull.py. If you've already authenticated\n"
            "there, you may need to re-auth to add the Search Console scope.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not Path(client_file).exists():
        print(f"Error: OAuth client file not found: {client_file}", file=sys.stderr)
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    creds = flow.run_local_server(port=0)

    # Cache the token for next time
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token cached at {TOKEN_PATH}", file=sys.stderr)

    return build("searchconsole", "v1", credentials=creds)


def get_site_url(site_url: str | None = None) -> str:
    """Resolve the Search Console site URL."""
    url = site_url or os.environ.get("GSC_SITE_URL")
    if not url:
        print(
            "Error: No site URL. Set GSC_SITE_URL env var or pass --site-url\n"
            "\n"
            "Examples:\n"
            '  --site-url "sc-domain:example.com"\n'
            '  --site-url "https://www.example.com/"',
            file=sys.stderr,
        )
        sys.exit(1)
    return url


def query_search_analytics(service, site_url: str, dimensions: list[str], days: int, limit: int) -> dict:
    """Execute a Search Console searchanalytics.query request."""
    end = date.today()
    start = end - timedelta(days=days)

    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "rowLimit": limit,
        "startRow": 0,
    }

    return service.searchanalytics().query(siteUrl=site_url, body=body).execute()


def format_response(response: dict, dimensions: list[str], fmt: str) -> str:
    """Format a Search Console response as JSON or CSV."""
    metrics = ["clicks", "impressions", "ctr", "position"]
    rows_out = []

    for row in response.get("rows", []):
        entry = {}
        for i, dim in enumerate(dimensions):
            entry[dim] = row["keys"][i]
        entry["clicks"] = int(row["clicks"])
        entry["impressions"] = int(row["impressions"])
        entry["ctr"] = round(row["ctr"], 4)
        entry["position"] = round(row["position"], 1)
        rows_out.append(entry)

    if fmt == "csv":
        if not rows_out:
            return ""
        headers = list(rows_out[0].keys())
        lines = [",".join(headers)]
        for row in rows_out:
            val_strs = []
            for h in headers:
                v = str(row.get(h, ""))
                # Quote CSV values that contain commas (e.g. page URLs with query params)
                if "," in v or '"' in v:
                    v = '"' + v.replace('"', '""') + '"'
                val_strs.append(v)
            lines.append(",".join(val_strs))
        return "\n".join(lines)
    else:
        return json.dumps(rows_out, indent=2)


# --- Commands ---


def cmd_top_queries(service, site_url, args):
    dims = ["query"]
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def cmd_top_pages(service, site_url, args):
    dims = ["page"]
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def cmd_query_pages(service, site_url, args):
    dims = ["query", "page"]
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def cmd_devices(service, site_url, args):
    dims = ["device"]
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def cmd_countries(service, site_url, args):
    dims = ["country"]
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def cmd_report(service, site_url, args):
    dims = [d.strip() for d in args.dimensions.split(",")]
    for d in dims:
        if d not in VALID_DIMENSIONS:
            print(
                f"Error: Invalid dimension '{d}'. Valid dimensions: {', '.join(sorted(VALID_DIMENSIONS))}",
                file=sys.stderr,
            )
            sys.exit(1)
    resp = query_search_analytics(service, site_url, dims, args.days, args.limit)
    print(format_response(resp, dims, args.format))


def main():
    parser = argparse.ArgumentParser(
        description="Pull data from Google Search Console",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--site-url", help="Search Console site URL (e.g. sc-domain:example.com)")
    parser.add_argument("--oauth-client", help="Path to OAuth client secrets JSON")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    # Shared args added to every subcommand so they work before OR after the command name
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--days", type=int, default=28, help="Lookback period in days (default: 28)")
    shared.add_argument("--limit", type=int, default=25, help="Max rows returned (default: 25)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("top-queries", parents=[shared], help="Top search queries by clicks")
    sub.add_parser("top-pages", parents=[shared], help="Top pages by clicks")
    sub.add_parser("query-pages", parents=[shared], help="Queries x pages cross-reference")
    sub.add_parser("devices", parents=[shared], help="Device breakdown")
    sub.add_parser("countries", parents=[shared], help="Country breakdown")

    rp = sub.add_parser("report", parents=[shared], help="Custom report with specified dimensions")
    rp.add_argument(
        "--dimensions",
        required=True,
        help="Comma-separated dimensions (query, page, device, country, date)",
    )

    args = parser.parse_args()

    service = get_service(args.oauth_client)
    site_url = get_site_url(args.site_url)

    commands = {
        "top-queries": cmd_top_queries,
        "top-pages": cmd_top_pages,
        "query-pages": cmd_query_pages,
        "devices": cmd_devices,
        "countries": cmd_countries,
        "report": cmd_report,
    }

    commands[args.command](service, site_url, args)


if __name__ == "__main__":
    main()
