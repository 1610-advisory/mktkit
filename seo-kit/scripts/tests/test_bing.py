import json
from datetime import datetime, timezone
from pathlib import Path

import bing

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_bing_date_offset_is_not_applied_twice():
    plain = bing.parse_bing_date("/Date(1700000000000)/")
    offset = bing.parse_bing_date("/Date(1700000000000-0700)/")
    plus = bing.parse_bing_date("/Date(1700000000000+0000)/")
    assert plain == offset == plus
    stamp = datetime.fromisoformat(plain)
    assert int(stamp.timestamp() * 1000) == 1700000000000
    assert stamp.tzinfo == timezone.utc
    assert bing.parse_bing_date("2026-01-01") == "2026-01-01"
    assert bing.parse_bing_date(None) is None


def test_documented_query_date_is_utc():
    parsed = bing.parse_bing_date("/Date(1316156400000-0700)/")
    assert parsed.startswith("2011-09-16T07:00:00")


def test_parse_query_page_crawl_and_url_info():
    queries = bing.parse_query_stats(load("bing_query_stats.json"))
    assert queries[0]["query"] == "widget maker"
    assert queries[0]["clicks"] == 15
    assert queries[0]["impressions"] == 100
    assert queries[0]["date"].startswith("2011-09-16")
    assert queries[1]["date"] == bing.parse_bing_date("/Date(1700000000000)/")

    pages = bing.parse_page_stats(load("bing_page_stats.json"))
    assert pages[0]["page"] == "https://example.com/widgets"
    assert pages[0]["clicks"] == 9

    issues = bing.parse_crawl_issues(load("bing_crawl_issues.json"))
    assert issues == [{
        "url": "https://example.com/missing",
        "http_code": 404,
        "issues": 32,
        "in_links": 2,
    }]

    info = bing.parse_url_info(load("bing_url_info.json"))
    assert info["url"] == "https://example.com/widgets"
    assert info["http_status"] == 200
    assert info["is_page"] is True
    assert info["last_crawled"].startswith("2011-09-")
    assert info["anchor_count"] == 50


def test_null_d_and_single_object_d():
    assert bing.parse_query_stats({"d": None}) == []
    assert bing.rows_of({"d": {"Query": "only"}}) == [{"Query": "only"}]


def test_assemble_report_sums_query_clicks():
    queries = bing.parse_query_stats(load("bing_query_stats.json"))
    pages = bing.attach_url_info(
        bing.parse_page_stats(load("bing_page_stats.json")),
        [bing.parse_url_info(load("bing_url_info.json"))],
    )
    report = bing.assemble_report(queries, pages, bing.parse_crawl_issues(load("bing_crawl_issues.json")), "2026-10-27T00:00:00Z")
    assert report["summary"] == {"clicks": 18, "impressions": 125}
    assert set(report) == {"generated_at", "summary", "queries", "pages", "crawl_issues"}
    assert pages[0]["url_info"]["url"] == "https://example.com/widgets"


def test_build_url_uses_json_endpoints_and_redacts():
    url = bing.build_bing_url("GetQueryStats", "https://example.com", "test-key")
    assert url.startswith("https://ssl.bing.com/webmaster/api.svc/json/GetQueryStats?")
    assert "siteUrl=https%3A%2F%2Fexample.com" in url
    assert "apikey=test-key" in url
    info = bing.build_bing_url("GetUrlInfo", "https://example.com", "test-key", {"url": "https://example.com/widgets"})
    assert "/json/GetUrlInfo?" in info
    assert "url=https%3A%2F%2Fexample.com%2Fwidgets" in info
    assert "test-key" not in bing.redact(url, "test-key")


def test_urls_for_info_caps_and_includes_site():
    pages = [{"page": f"https://example.com/{i}"} for i in range(30)]
    chosen = bing.urls_for_info("https://example.com", pages, cap=5)
    assert chosen[0] == "https://example.com"
    assert len(chosen) == 5


def test_missing_key_exits_before_config(monkeypatch, capsys):
    monkeypatch.delenv("BING_WEBMASTER_API_KEY", raising=False)
    code = bing.main(["all", "--config", "unused.yaml", "--out", "unused.json"])
    assert code == 1
    err = capsys.readouterr().err
    assert "BING_WEBMASTER_API_KEY is not set" in err
    assert "test-key" not in err


def test_pull_all_uses_injected_fetcher_only():
    fixtures = {
        "GetQueryStats": load("bing_query_stats.json"),
        "GetPageStats": load("bing_page_stats.json"),
        "GetCrawlIssues": load("bing_crawl_issues.json"),
        "GetUrlInfo": load("bing_url_info.json"),
    }
    seen = []

    def get_json(url):
        seen.append(url.split("?")[0].rsplit("/", 1)[-1])
        return fixtures[seen[-1]]

    report = bing.pull_all("https://example.com", "test-key", get_json=get_json)
    assert seen[:3] == ["GetQueryStats", "GetPageStats", "GetCrawlIssues"]
    assert "GetUrlInfo" in seen
    assert report["summary"]["clicks"] == 18
    assert all("test-key" not in item for item in seen)
