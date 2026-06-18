# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-ads>=25.0.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth>=2.0.0",
# ]
# ///
"""
Google Ads Data Pull — pulls campaign performance data from Google Ads.

Usage:
    uv run gads_pull.py [OPTIONS] COMMAND [ARGS]

Authentication:
    Uses the same OAuth token as ga4_pull.py (~/.config/google/ga4-token.json).
    If no token exists, runs interactive OAuth flow.

Environment variables:
    GOOGLE_ADS_DEVELOPER_TOKEN    — Developer token from MCC API Center
    GOOGLE_ADS_MCC_ID             — Manager account ID (XXX-XXX-XXXX)
    GOOGLE_ADS_CUSTOMER_ID        — Client account ID (XXX-XXX-XXXX), or pass --customer-id
    GA4_OAUTH_CLIENT              — Path to OAuth client JSON (for first-time auth)

Commands:
    campaigns         Campaign-level performance (spend, clicks, impressions, CTR, CPC)
    ad-groups         Ad group performance within campaigns
    keywords          Keyword performance with search terms
    search-terms      Actual search queries triggering ads
    ads               Individual ad performance
    report            Custom GAQL query
"""

import argparse
import json
import os
import sys
from pathlib import Path

TOKEN_PATH = Path.home() / ".config" / "google" / "ga4-token.json"
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
]


def get_credentials(oauth_client_path: str | None = None):
    """Get OAuth credentials, reusing the GA4 token if possible."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    # Try cached token
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            if creds.valid:
                return creds
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                return creds
        except Exception:
            pass

    # Interactive OAuth flow
    client_file = oauth_client_path or os.environ.get("GA4_OAUTH_CLIENT")
    if not client_file:
        print(
            "Error: No credentials found.\n"
            "Set GA4_OAUTH_CLIENT env var or pass --oauth-client /path/to/client_secret.json",
            file=sys.stderr,
        )
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"Token cached at {TOKEN_PATH}", file=sys.stderr)
    return creds


def get_client(oauth_client_path: str | None = None):
    """Create an authenticated Google Ads client."""
    from google.ads.googleads.client import GoogleAdsClient

    dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN")
    mcc_id = os.environ.get("GOOGLE_ADS_MCC_ID", "").replace("-", "")

    if not dev_token:
        print("Error: Set GOOGLE_ADS_DEVELOPER_TOKEN env var", file=sys.stderr)
        sys.exit(1)

    creds = get_credentials(oauth_client_path)

    client = GoogleAdsClient(
        credentials=creds,
        developer_token=dev_token,
        login_customer_id=mcc_id if mcc_id else None,
    )
    return client


def run_query(client, customer_id: str, query: str) -> list[dict]:
    """Run a GAQL query and return results as list of dicts."""
    service = client.get_service("GoogleAdsService")
    cid = customer_id.replace("-", "")

    rows = []
    response = service.search(customer_id=cid, query=query)

    for row in response:
        entry = {}
        # Serialize to dict — handle both proto-plus and raw protobuf
        from google.protobuf.json_format import MessageToDict
        pb = row._pb if hasattr(row, '_pb') else row
        if not hasattr(pb, 'DESCRIPTOR'):
            # proto-plus object — use type() helper
            pb = type(row).pb(row)
        d = MessageToDict(pb, preserving_proto_field_name=True)
        for top_key, top_val in d.items():
            if isinstance(top_val, dict):
                for sub_key, sub_val in top_val.items():
                    key = f"{top_key}.{sub_key}"
                    if ("micros" in sub_key or sub_key in ("average_cpc", "cost_per_conversion")) and isinstance(sub_val, (int, float, str)):
                        entry[key.replace("_micros", "")] = round(float(sub_val) / 1_000_000, 2)
                    elif isinstance(sub_val, list):
                        entry[key] = ", ".join(str(v) for v in sub_val)
                    else:
                        entry[key] = sub_val
            else:
                entry[top_key] = top_val
        rows.append(entry)

    return rows


def format_output(rows: list[dict], fmt: str) -> str:
    """Format results as JSON or CSV."""
    if not rows:
        return "No data returned."

    if fmt == "csv":
        headers = list(rows[0].keys())
        lines = [",".join(headers)]
        for row in rows:
            lines.append(",".join(str(row.get(h, "")) for h in headers))
        return "\n".join(lines)
    else:
        return json.dumps(rows, indent=2, default=str)


# --- Commands ---


def cmd_campaigns(client, customer_id, args):
    query = f"""
        SELECT
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date DURING LAST_{args.days}D
            {'' if args.all else 'AND campaign.status != "REMOVED"'}
        ORDER BY metrics.cost_micros DESC
        LIMIT {args.limit}
    """
    # GAQL doesn't support arbitrary LAST_ND, use date range instead
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=args.days)
    query = f"""
        SELECT
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
            {'' if args.all else 'AND campaign.status != "REMOVED"'}
        ORDER BY metrics.cost_micros DESC
        LIMIT {args.limit}
    """
    rows = run_query(client, customer_id, query)
    print(format_output(rows, args.format))


def cmd_ad_groups(client, customer_id, args):
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=args.days)
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group.status,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group
        WHERE segments.date BETWEEN '{start}' AND '{end}'
            AND campaign.status != 'REMOVED'
            {'' if args.all else 'AND ad_group.status != "REMOVED"'}
        ORDER BY metrics.cost_micros DESC
        LIMIT {args.limit}
    """
    rows = run_query(client, customer_id, query)
    print(format_output(rows, args.format))


def cmd_keywords(client, customer_id, args):
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=args.days)
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM keyword_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
            AND campaign.status != 'REMOVED'
        ORDER BY metrics.impressions DESC
        LIMIT {args.limit}
    """
    rows = run_query(client, customer_id, query)
    print(format_output(rows, args.format))


def cmd_search_terms(client, customer_id, args):
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=args.days)
    query = f"""
        SELECT
            campaign.name,
            search_term_view.search_term,
            search_term_view.status,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM search_term_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
            AND campaign.status != 'REMOVED'
        ORDER BY metrics.impressions DESC
        LIMIT {args.limit}
    """
    rows = run_query(client, customer_id, query)
    print(format_output(rows, args.format))


def cmd_ads(client, customer_id, args):
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=args.days)
    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_ad.ad.type,
            ad_group_ad.ad.final_urls,
            ad_group_ad.status,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{start}' AND '{end}'
            AND campaign.status != 'REMOVED'
        ORDER BY metrics.impressions DESC
        LIMIT {args.limit}
    """
    rows = run_query(client, customer_id, query)
    print(format_output(rows, args.format))


def cmd_report(client, customer_id, args):
    rows = run_query(client, customer_id, args.query)
    print(format_output(rows, args.format))


def main():
    parser = argparse.ArgumentParser(
        description="Pull data from Google Ads",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--customer-id", help="Google Ads customer ID (XXX-XXX-XXXX)")
    parser.add_argument("--oauth-client", help="Path to OAuth client secrets JSON")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="Output format")

    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--days", type=int, default=30, help="Lookback period in days (default: 30)")
    shared.add_argument("--limit", type=int, default=25, help="Max rows returned (default: 25)")
    shared.add_argument("--all", action="store_true", help="Include removed/paused items")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("campaigns", parents=[shared], help="Campaign performance (spend, clicks, CTR)")
    sub.add_parser("ad-groups", parents=[shared], help="Ad group performance")
    sub.add_parser("keywords", parents=[shared], help="Keyword performance")
    sub.add_parser("search-terms", parents=[shared], help="Actual search queries triggering ads")
    sub.add_parser("ads", parents=[shared], help="Individual ad performance")

    rp = sub.add_parser("report", parents=[shared], help="Custom GAQL query")
    rp.add_argument("--query", required=True, help="GAQL query string")

    args = parser.parse_args()

    customer_id = args.customer_id or os.environ.get("GOOGLE_ADS_CUSTOMER_ID")
    if not customer_id:
        print("Error: No customer ID. Set GOOGLE_ADS_CUSTOMER_ID env var or pass --customer-id", file=sys.stderr)
        sys.exit(1)

    client = get_client(args.oauth_client)

    commands = {
        "campaigns": cmd_campaigns,
        "ad-groups": cmd_ad_groups,
        "keywords": cmd_keywords,
        "search-terms": cmd_search_terms,
        "ads": cmd_ads,
        "report": cmd_report,
    }

    commands[args.command](client, customer_id, args)


if __name__ == "__main__":
    main()
