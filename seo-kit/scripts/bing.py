# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pyyaml>=6",
# ]
# ///
"""
Bing Webmaster Tools pull for the weekly SEO kit.

Usage:
    uv run bing.py all --config tracking/seo/config.yaml --out bing.json

Reads BING_WEBMASTER_API_KEY from the environment. The key is sent as the
apikey query parameter and is never printed, not even in errors.

Endpoints (JSON):
    https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats
    https://ssl.bing.com/webmaster/api.svc/json/GetPageStats
    https://ssl.bing.com/webmaster/api.svc/json/GetCrawlIssues
    https://ssl.bing.com/webmaster/api.svc/json/GetUrlInfo

siteUrl comes from config key site. Bing dates like /Date(1700000000000)/
are converted to UTC ISO timestamps. The number is UTC milliseconds; the
optional timezone suffix is not applied again.

Commands:
    all     Write bing.json with summary, queries, pages, and crawl_issues
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

API_ROOT = "https://ssl.bing.com/webmaster/api.svc/json"
KEY_ENV = "BING_WEBMASTER_API_KEY"
# GetUrlInfo is one call per URL. A weekly run should not fan out across every page row.
URL_INFO_CAP = 20
DATE_RE = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def load_client(path: str) -> dict:
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


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def require_api_key() -> str | None:
    key = os.environ.get(KEY_ENV, "")
    if not key.strip():
        print(f"Error: {KEY_ENV} is not set.", file=sys.stderr)
        return None
    return key


def redact(text: str, secret: str) -> str:
    if secret:
        return text.replace(secret, "[redacted]")
    return text


def parse_bing_date(value):
    """Turn /Date(ms)/ or /Date(ms-0700)/ into a UTC ISO timestamp. Other values pass through."""
    if not isinstance(value, str):
        return value
    match = DATE_RE.fullmatch(value)
    if not match:
        return value
    millis = int(match.group(1))
    stamp = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
    return stamp.isoformat()


def build_bing_url(endpoint: str, site_url: str, api_key: str, extra: dict | None = None) -> str:
    params = {"siteUrl": site_url, "apikey": api_key}
    if extra:
        params.update(extra)
    return f"{API_ROOT}/{endpoint}?{urlencode(params)}"


def rows_of(payload: dict) -> list:
    if not isinstance(payload, dict):
        return []
    data = payload.get("d")
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _stat_row(row: dict, label_key: str) -> dict:
    return {
        label_key: row.get("Query"),
        "clicks": row.get("Clicks"),
        "impressions": row.get("Impressions"),
        "avg_click_position": row.get("AvgClickPosition"),
        "avg_impression_position": row.get("AvgImpressionPosition"),
        "date": parse_bing_date(row.get("Date")),
    }


def parse_query_stats(payload: dict) -> list[dict]:
    return [_stat_row(row, "query") for row in rows_of(payload)]


def parse_page_stats(payload: dict) -> list[dict]:
    """GetPageStats reuses QueryStats; the Query field holds the page URL."""
    pages = []
    for row in rows_of(payload):
        item = _stat_row(row, "page")
        if not item["page"]:
            item["page"] = row.get("Url")
        pages.append(item)
    return pages


def parse_crawl_issues(payload: dict) -> list[dict]:
    issues = []
    for row in rows_of(payload):
        issues.append(
            {
                "url": row.get("Url"),
                "http_code": row.get("HttpCode"),
                "issues": row.get("Issues"),
                "in_links": row.get("InLinks"),
            }
        )
    return issues


def parse_url_info(payload: dict) -> dict:
    data = payload.get("d") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = {}
    return {
        "url": data.get("Url"),
        "anchor_count": data.get("AnchorCount"),
        "discovery_date": parse_bing_date(data.get("DiscoveryDate")),
        "document_size": data.get("DocumentSize"),
        "http_status": data.get("HttpStatus"),
        "is_page": data.get("IsPage"),
        "last_crawled": parse_bing_date(data.get("LastCrawledDate")),
        "total_child_url_count": data.get("TotalChildUrlCount"),
    }


def attach_url_info(pages: list[dict], infos: list[dict]) -> list[dict]:
    """Copy url-info onto page rows whose URL matches. Does not add a new top-level key."""
    by_url = {}
    for info in infos:
        url = info.get("url")
        if url:
            by_url[_norm(url)] = info
    attached = []
    for page in pages:
        item = dict(page)
        info = by_url.get(_norm(page.get("page") or ""))
        if info:
            item["url_info"] = info
        attached.append(item)
    return attached


def _norm(url: str) -> str:
    return url.strip().rstrip("/")


def assemble_report(queries: list[dict], pages: list[dict], crawl_issues: list[dict], generated_at: str) -> dict:
    clicks = sum(int(row.get("clicks") or 0) for row in queries)
    impressions = sum(int(row.get("impressions") or 0) for row in queries)
    return {
        "generated_at": generated_at,
        "summary": {"clicks": clicks, "impressions": impressions},
        "queries": queries,
        "pages": pages,
        "crawl_issues": crawl_issues,
    }


def fetch_json(url: str, timeout: float = 60) -> dict:
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        raise RuntimeError("response was not JSON") from exc


def urls_for_info(site: str, pages: list[dict], cap: int = URL_INFO_CAP) -> list[str]:
    seen = set()
    ordered = []
    for candidate in [site, *[page.get("page") or "" for page in pages]]:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
        if len(ordered) >= cap:
            break
    return ordered


def pull_all(site: str, api_key: str, get_json=fetch_json) -> dict:
    """Fetch the four endpoints and assemble the report. get_json is injectable for tests."""
    endpoints = {
        "GetQueryStats": build_bing_url("GetQueryStats", site, api_key),
        "GetPageStats": build_bing_url("GetPageStats", site, api_key),
        "GetCrawlIssues": build_bing_url("GetCrawlIssues", site, api_key),
    }
    payloads = {}
    for name, url in endpoints.items():
        try:
            payloads[name] = get_json(url)
        except Exception as exc:
            message = redact(str(exc), api_key)
            raise RuntimeError(f"{name} failed: {message}") from exc
    queries = parse_query_stats(payloads["GetQueryStats"])
    pages = parse_page_stats(payloads["GetPageStats"])
    issues = parse_crawl_issues(payloads["GetCrawlIssues"])
    infos = []
    for page_url in urls_for_info(site, pages):
        url = build_bing_url("GetUrlInfo", site, api_key, {"url": page_url})
        try:
            infos.append(parse_url_info(get_json(url)))
        except Exception as exc:
            message = redact(str(exc), api_key)
            raise RuntimeError(f"GetUrlInfo failed: {message}") from exc
    return assemble_report(queries, attach_url_info(pages, infos), issues, utc_now())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pull Bing Webmaster Tools query, page, and crawl data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _error(message: str) -> None:
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)

    parser.error = _error  # type: ignore[method-assign]
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = _parser()
    sub = parser.add_subparsers(dest="command", required=True)
    all_cmd = sub.add_parser("all", help="Write bing.json from the Webmaster API")
    all_cmd.add_argument("--config", required=True, help="Path to tracking/seo/config.yaml")
    all_cmd.add_argument("--out", required=True, help="JSON output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # Check the key before loading config or touching the network so a missing key
    # cannot leak into a later exception, and so tests can fail closed.
    api_key = require_api_key()
    if not api_key:
        return 1
    config = load_client(args.config)
    site = (config.get("site") or "").strip()
    if not site:
        print("Error: config site is empty.", file=sys.stderr)
        return 1
    try:
        report = pull_all(site, api_key)
    except RuntimeError as exc:
        print(f"Error: {redact(str(exc), api_key)}", file=sys.stderr)
        return 2
    write_json(args.out, report)
    summary = report["summary"]
    print(
        f"bing: {summary['clicks']} clicks, {summary['impressions']} impressions, "
        f"{len(report['crawl_issues'])} crawl issues",
        file=sys.stderr,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
