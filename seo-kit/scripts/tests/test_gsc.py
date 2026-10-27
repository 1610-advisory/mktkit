import json
from datetime import date
from pathlib import Path

import gsc

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/a</loc></url>
  <url><loc> https://example.com/b </loc></url>
</urlset>
"""

INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""


def test_parse_sitemap_urlset_and_index():
    kind, locs = gsc.parse_sitemap(SITEMAP)
    assert kind == "urlset"
    assert locs == ["https://example.com/a", "https://example.com/b"]
    kind, locs = gsc.parse_sitemap(INDEX)
    assert kind == "index"
    assert locs == ["https://example.com/sitemap-pages.xml"]


def test_collect_sitemap_urls_expands_index():
    pages = {
        "https://example.com/sitemap.xml": INDEX,
        "https://example.com/sitemap-pages.xml": SITEMAP,
    }

    def fetch(url):
        return pages[url]

    assert gsc.collect_sitemap_urls(fetch, "https://example.com/sitemap.xml") == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_analytics_window_is_28_inclusive_days_ending_3_days_ago():
    start, end = gsc.analytics_window(date(2026, 10, 27))
    assert end == "2026-10-24"
    assert start == "2026-09-27"
    assert (date.fromisoformat(end) - date.fromisoformat(start)).days == 27


def test_build_bodies():
    body = gsc.build_inspect_body("https://example.com/a", "sc-domain:example.com")
    assert body["inspectionUrl"] == "https://example.com/a"
    assert body["siteUrl"] == "sc-domain:example.com"
    detail = gsc.build_analytics_body("2026-09-27", "2026-10-24", ["query", "page"], 1000)
    assert detail["dimensions"] == ["query", "page"]
    assert detail["rowLimit"] == 1000
    totals = gsc.build_analytics_body("2026-09-27", "2026-10-24", None, 1)
    assert "dimensions" not in totals


def test_parse_inspection_canonical_mismatch():
    row = gsc.parse_inspection("https://example.com/widgets", load("gsc_inspect.json"))
    assert row["verdict"] == "PASS"
    assert row["coverageState"] == "Submitted and indexed"
    assert row["indexingState"] == "INDEXING_ALLOWED"
    assert row["robotsTxtState"] == "ALLOWED"
    assert row["pageFetchState"] == "SUCCESSFUL"
    assert row["lastCrawlTime"] == "2026-10-01T12:00:00Z"
    assert row["canonical_mismatch"] is True

    same = gsc.parse_inspection("https://example.com/widgets", {
        "inspectionResult": {"indexStatusResult": {
            "verdict": "PASS",
            "googleCanonical": "https://example.com/widgets",
            "userCanonical": "https://example.com/widgets",
        }}
    })
    assert same["canonical_mismatch"] is False
    empty = gsc.parse_inspection("https://example.com/x", {"inspectionResult": {}})
    assert empty["canonical_mismatch"] is False
    assert empty["verdict"] is None


def test_inspect_urls_caps_and_spaces_calls():
    calls = []

    def inspect_fn(url, site_url):
        calls.append((url, site_url))
        return {"inspectionResult": {"indexStatusResult": {"verdict": "PASS" if url.endswith("/a") else "FAIL"}}}

    slept = []
    rows = gsc.inspect_urls(
        ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        "sc-domain:example.com",
        inspect_fn,
        limit=2,
        delay=0.2,
        sleep_fn=slept.append,
    )
    assert [row["url"] for row in rows] == ["https://example.com/a", "https://example.com/b"]
    assert slept == [0.2]
    assert gsc.INSPECT_LIMIT == 200
    assert gsc.INSPECT_DELAY_S == 0.2
    assert gsc.SCOPES == ["https://www.googleapis.com/auth/webmasters.readonly"]


def test_parse_analytics_and_page_two():
    rows = gsc.parse_analytics_rows(load("gsc_analytics.json"))
    assert rows[0]["query"] == "acme widgets"
    assert rows[0]["page"] == "https://example.com/widgets"
    assert rows[0]["clicks"] == 12
    picked = gsc.page_two_rows(rows, 20)
    queries = [row["query"] for row in picked]
    assert queries == ["acme widgets", "widget cost", "page two edge"]
    assert "page two edge" in queries
    assert "acme widgets" in queries
    assert "widget cost" in queries
    assert "acme brand" not in queries  # impressions 19
    assert "too deep" not in queries  # position 20.1
    assert picked[0]["impressions"] >= picked[-1]["impressions"]
    assert "_position" not in picked[0]


def test_page_two_boundaries_and_sort():
    rows = [
        {"query": "low", "page": "https://example.com/a", "impressions": 20, "position": 8, "_position": 8},
        {"query": "high", "page": "https://example.com/b", "impressions": 21, "position": 20, "_position": 20},
        {"query": "under", "page": "https://example.com/c", "impressions": 100, "position": 7.9, "_position": 7.9},
        {"query": "few", "page": "https://example.com/d", "impressions": 19, "position": 10, "_position": 10},
    ]
    picked = gsc.page_two_rows(rows, 20)
    assert [row["query"] for row in picked] == ["high", "low"]


def test_totals_and_summary_indexed_is_pass_only():
    totals = gsc.parse_totals(load("gsc_totals.json"))
    assert totals == {"clicks": 100, "impressions": 4000, "ctr": 0.025, "position": 12.4}
    assert gsc.parse_totals({})["clicks"] == 0
    inspections = [
        {"verdict": "PASS"},
        {"verdict": "PASS"},
        {"verdict": "FAIL"},
        {"verdict": "NEUTRAL"},
        {"verdict": None, "error": "boom"},
    ]
    summary = gsc.build_gsc_summary(totals, inspections)
    assert summary["indexed"] == 2
    assert summary["not_indexed"] == 3
    assert summary["clicks"] == 100
    assert set(summary) == {"clicks", "impressions", "ctr", "position", "indexed", "not_indexed"}


def test_write_token_is_mode_0600_and_parent_0700(tmp_path):
    path = tmp_path / "google" / "seo-kit-token.json"
    gsc.write_token(path, '{"token": "x"}\n')
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.read_text(encoding="utf-8").startswith("{")
    source = Path(gsc.__file__).read_text(encoding="utf-8")
    assert source.count("write_token(") >= 3
    assert "TOKEN_PATH.write_text" not in source


def test_canonical_mismatch_requires_both_and_pagination(tmp_path):
    only_google = gsc.parse_inspection(
        "https://example.com/a",
        {"inspectionResult": {"indexStatusResult": {"googleCanonical": "https://example.com/a"}}},
    )
    only_user = gsc.parse_inspection(
        "https://example.com/a",
        {"inspectionResult": {"indexStatusResult": {"userCanonical": "https://example.com/a/"}}},
    )
    assert only_google["canonical_mismatch"] is False
    assert only_user["canonical_mismatch"] is False
    assert gsc.ANALYTICS_ROW_CAP == 25000
    calls = []

    def query(body):
        calls.append(body["startRow"])
        count = 1000 if body["startRow"] < 2000 else 4
        return {
            "rows": [
                {
                    "keys": ["q", "https://example.com/"],
                    "clicks": 1,
                    "impressions": 2,
                    "ctr": 0.5,
                    "position": 3,
                }
                for _ in range(count)
            ]
        }

    rows = gsc.paginate_analytics(query, "2026-09-27", "2026-10-24", ["query", "page"])
    assert calls == [0, 1000, 2000]
    assert len(rows) == 2004
    capped = []

    def always_full(body):
        capped.append((body["startRow"], body["rowLimit"]))
        return {
            "rows": [
                {
                    "keys": ["q", "https://example.com/"],
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0,
                    "position": 1,
                }
                for _ in range(body["rowLimit"])
            ]
        }

    limited = gsc.paginate_analytics(
        always_full, "2026-09-27", "2026-10-24", ["query", "page"], row_limit=1000, cap=2500
    )
    assert capped == [(0, 1000), (1000, 1000), (2000, 500)]
    assert len(limited) == 2500
