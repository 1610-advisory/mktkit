# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-analytics-data>=0.18.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth>=2.0.0",
# ]
# ///
"""
GA4 Data Pull — pulls analytics data from Google Analytics 4.

Usage:
    uv run ga4_pull.py [OPTIONS] COMMAND [ARGS]

Authentication (tries in order):
    1. Application Default Credentials (if gcloud is set up)
    2. Cached OAuth token (~/.config/google/ga4-token.json)
    3. Interactive OAuth flow (opens browser, requires --oauth-client)

Environment variables:
    GA4_PROPERTY_ID      — GA4 numeric property ID (or pass --property-id)
    GA4_OAUTH_CLIENT     — path to OAuth client JSON (or pass --oauth-client)

Commands:
    top-pages           Top pages by sessions
    traffic-sources     Sessions by channel/source/medium
    content-perf        Landing pages with engagement metrics
    conversions         Key conversion events
    report              Custom report (specify dimensions/metrics)
    realtime            Active users right now
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    OrderBy,
    RunRealtimeReportRequest,
    RunReportRequest,
)

TOKEN_PATH = Path.home() / ".config" / "google" / "ga4-token.json"
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def get_client(oauth_client_path: str | None = None) -> BetaAnalyticsDataClient:
    """Create an authenticated GA4 client. Tries ADC first, then cached OAuth, then interactive OAuth."""

    # 1. Try Application Default Credentials (gcloud auth application-default login)
    try:
        import google.auth

        creds, _ = google.auth.default(scopes=SCOPES)
        return BetaAnalyticsDataClient(credentials=creds)
    except Exception:
        pass

    # 2. Try cached OAuth token
    if TOKEN_PATH.exists():
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds.valid:
                return BetaAnalyticsDataClient(credentials=creds)
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                return BetaAnalyticsDataClient(credentials=creds)
        except Exception:
            pass

    # 3. Interactive OAuth flow — needs client secrets file
    client_file = oauth_client_path or os.environ.get("GA4_OAUTH_CLIENT")
    if not client_file:
        print(
            "Error: No credentials found.\n"
            "\n"
            "Options:\n"
            "  1. Run: gcloud auth application-default login\n"
            "  2. Set GA4_OAUTH_CLIENT env var to your OAuth client JSON path\n"
            "  3. Pass --oauth-client /path/to/client_secret.json\n"
            "\n"
            "To create OAuth credentials:\n"
            "  GCP Console → APIs & Services → Credentials → Create → OAuth client ID → Desktop app\n"
            "  Download the JSON and pass it here.",
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

    return BetaAnalyticsDataClient(credentials=creds)


def get_property(property_id: str | None = None) -> str:
    """Resolve the GA4 property ID."""
    pid = property_id or os.environ.get("GA4_PROPERTY_ID")
    if not pid:
        print(
            "Error: No property ID. Set GA4_PROPERTY_ID env var or pass --property-id",
            file=sys.stderr,
        )
        sys.exit(1)
    return f"properties/{pid}"


def format_response(response, dimensions_list: list[str], metrics_list: list[str], fmt: str) -> str:
    """Format a GA4 report response as JSON or CSV."""
    rows = []
    for row in response.rows:
        entry = {}
        for i, dim in enumerate(dimensions_list):
            entry[dim] = row.dimension_values[i].value
        for i, met in enumerate(metrics_list):
            val = row.metric_values[i].value
            try:
                entry[met] = int(val)
            except ValueError:
                try:
                    entry[met] = round(float(val), 4)
                except ValueError:
                    entry[met] = val
        rows.append(entry)

    if fmt == "csv":
        if not rows:
            return ""
        headers = list(rows[0].keys())
        lines = [",".join(headers)]
        for row in rows:
            lines.append(",".join(str(row.get(h, "")) for h in headers))
        return "\n".join(lines)
    else:
        return json.dumps(rows, indent=2)


def run_report(client, prop, dimensions, metrics, days, limit, order_by_metric=None):
    """Run a GA4 report and return the response."""
    end = date.today()
    start = end - timedelta(days=days)

    request = RunReportRequest(
        property=prop,
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=limit,
    )

    if order_by_metric:
        request.order_bys = [
            OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_by_metric), desc=True)
        ]

    return client.run_report(request)


# --- Commands ---


def cmd_top_pages(client, prop, args):
    dims = ["pagePath", "pageTitle"]
    mets = ["sessions", "screenPageViews", "activeUsers", "engagementRate", "averageSessionDuration"]
    resp = run_report(client, prop, dims, mets, args.days, args.limit, order_by_metric="sessions")
    print(format_response(resp, dims, mets, args.format))


def cmd_traffic_sources(client, prop, args):
    dims = ["sessionDefaultChannelGrouping", "sessionSource", "sessionMedium"]
    mets = ["sessions", "activeUsers", "engagementRate", "conversions"]
    resp = run_report(client, prop, dims, mets, args.days, args.limit, order_by_metric="sessions")
    print(format_response(resp, dims, mets, args.format))


def cmd_content_perf(client, prop, args):
    dims = ["landingPagePlusQueryString"]
    mets = [
        "sessions",
        "activeUsers",
        "bounceRate",
        "engagementRate",
        "averageSessionDuration",
        "screenPageViews",
        "conversions",
    ]
    resp = run_report(client, prop, dims, mets, args.days, args.limit, order_by_metric="sessions")
    print(format_response(resp, dims, mets, args.format))


def cmd_conversions(client, prop, args):
    dims = ["eventName"]
    mets = ["eventCount", "totalUsers"]
    resp = run_report(client, prop, dims, mets, args.days, args.limit, order_by_metric="eventCount")
    print(format_response(resp, dims, mets, args.format))


def cmd_report(client, prop, args):
    dims = [d.strip() for d in args.dimensions.split(",")]
    mets = [m.strip() for m in args.metrics.split(",")]
    order_metric = mets[0] if mets else None
    resp = run_report(client, prop, dims, mets, args.days, args.limit, order_by_metric=order_metric)
    print(format_response(resp, dims, mets, args.format))


def cmd_realtime(client, prop, args):
    dims = ["unifiedScreenName"]
    mets = ["activeUsers"]

    request = RunRealtimeReportRequest(
        property=prop,
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in mets],
        limit=args.limit,
    )
    resp = client.run_realtime_report(request)

    rows = []
    for row in resp.rows:
        entry = {}
        for i, dim in enumerate(dims):
            entry[dim] = row.dimension_values[i].value
        for i, met in enumerate(mets):
            val = row.metric_values[i].value
            try:
                entry[met] = int(val)
            except ValueError:
                entry[met] = val
        rows.append(entry)

    total = sum(r.get("activeUsers", 0) for r in rows)
    print(f"Active users right now: {total}")
    if args.format == "csv":
        if rows:
            headers = list(rows[0].keys())
            print(",".join(headers))
            for row in rows:
                print(",".join(str(row.get(h, "")) for h in headers))
    else:
        print(json.dumps(rows, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Pull data from Google Analytics 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--property-id", help="GA4 property ID (numeric)")
    parser.add_argument("--oauth-client", help="Path to OAuth client secrets JSON")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    # Shared args added to every subcommand so they work before OR after the command name
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--days", type=int, default=30, help="Lookback period in days (default: 30)")
    shared.add_argument("--limit", type=int, default=25, help="Max rows returned (default: 25)")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("top-pages", parents=[shared], help="Top pages by sessions")
    sub.add_parser("traffic-sources", parents=[shared], help="Traffic by channel/source/medium")
    sub.add_parser("content-perf", parents=[shared], help="Landing page engagement metrics")
    sub.add_parser("conversions", parents=[shared], help="Event conversion counts")
    sub.add_parser("realtime", parents=[shared], help="Active users right now")

    rp = sub.add_parser("report", parents=[shared], help="Custom report")
    rp.add_argument("--dimensions", required=True, help="Comma-separated dimension names")
    rp.add_argument("--metrics", required=True, help="Comma-separated metric names")

    args = parser.parse_args()

    client = get_client(args.oauth_client)
    prop = get_property(args.property_id)

    commands = {
        "top-pages": cmd_top_pages,
        "traffic-sources": cmd_traffic_sources,
        "content-perf": cmd_content_perf,
        "conversions": cmd_conversions,
        "report": cmd_report,
        "realtime": cmd_realtime,
    }

    commands[args.command](client, prop, args)


if __name__ == "__main__":
    main()
