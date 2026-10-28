import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lighthouse_run as lh

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_extract_report_scores_metrics_and_opportunities():
    report = json.loads((FIXTURES / "lighthouse-report.json").read_text(encoding="utf-8"))
    extracted = lh.extract_report(report)
    assert extracted["scores"] == {
        "performance": 82,
        "accessibility": 96,
        "best-practices": 100,
        "seo": 91,
    }
    assert extracted["metrics"]["lcp_ms"] == 2410
    assert extracted["metrics"]["cls"] == 0.021
    assert extracted["metrics"]["tbt_ms"] == 180
    assert extracted["metrics"]["fcp_ms"] == 991
    assert extracted["metrics"]["speed_index_ms"] == 3100
    assert extracted["lcp_element"] == "<h1>Hello</h1>"
    assert [item["id"] for item in extracted["opportunities"]] == [
        "unused-javascript",
        "modern-image-formats",
        "render-blocking-resources",
    ]
    assert extracted["opportunities"][0]["savings_ms"] == 420


def test_lcp_snippet_from_lighthouse_13_insight():
    report = {
        "categories": {},
        "audits": {
            "lcp-breakdown-insight": {
                "details": {
                    "type": "list",
                    "items": [
                        {"type": "table", "items": []},
                        {"type": "node", "snippet": "<h1 class=\"hero\">", "nodeLabel": "Hello"},
                    ],
                }
            },
            "unused-javascript": {
                "id": "unused-javascript",
                "title": "Reduce unused JavaScript",
                "score": 0,
                "details": {"type": "opportunity", "metricSavings": {"LCP": 150}},
            },
        },
    }
    extracted = lh.extract_report(report)
    assert extracted["lcp_element"] == '<h1 class="hero">'
    assert extracted["opportunities"] == [
        {"id": "unused-javascript", "title": "Reduce unused JavaScript", "savings_ms": 150}
    ]


def test_pick_median_uses_lower_middle_run():
    reports = [
        {"categories": {"performance": {"score": 0.9}}},
        {"categories": {"performance": {"score": 0.5}}},
        {"categories": {"performance": {"score": 0.7}}},
    ]
    assert lh.performance_score(lh.pick_median(reports)) == 0.7
    even = reports[:2]
    assert lh.performance_score(lh.pick_median(even)) == 0.5


def test_command_flags(monkeypatch):
    monkeypatch.setattr(lh, "default_prefix", lambda: ["lighthouse"])
    desktop = lh.lighthouse_argv("https://example.com/", "desktop", Path("/tmp/out.json"))
    mobile = lh.lighthouse_argv("https://example.com/about", "mobile", Path("/tmp/out.json"))
    assert desktop[0] == "lighthouse"
    assert "--output=json" in desktop
    assert "--quiet" in desktop
    assert "--chrome-flags=--headless=new" in desktop
    assert "--preset=desktop" in desktop
    assert "--preset=desktop" not in mobile
    assert "https://example.com/" in desktop


def test_npx_fallback(monkeypatch):
    monkeypatch.setattr(lh.shutil, "which", lambda _name: None)
    assert lh.default_prefix() == ["npx", "--yes", "lighthouse@13.5.0"]


def test_path_prefix_when_installed(monkeypatch):
    monkeypatch.setattr(lh.shutil, "which", lambda name: "/usr/local/bin/lighthouse" if name == "lighthouse" else None)
    assert lh.default_prefix() == ["lighthouse"]


def test_main_rejects_empty_pages(tmp_path, capsys):
    config = tmp_path / "tracking" / "seo" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "site: https://example.com\nsitemap: https://example.com/sitemap.xml\nbrand: Acme Corp\ndomains: [example.com]\n",
        encoding="utf-8",
    )
    code = lh.main(["--config", str(config), "--out", str(tmp_path / "lighthouse.json")])
    assert code == 1
    assert "lighthouse.pages" in capsys.readouterr().err


def test_run_once_deletes_stale_report(tmp_path, monkeypatch):
    stale = tmp_path / "report.json"
    stale.write_text('{"stale": true}', encoding="utf-8")

    def fake_run(cmd, **kwargs):
        assert not stale.exists()
        stale.write_text('{"categories": {}}', encoding="utf-8")

        class Proc:
            returncode = 0
            stderr = ""
            stdout = ""

        return Proc()

    monkeypatch.setattr(lh.subprocess, "run", fake_run)
    assert lh.run_once("https://example.com/", "mobile", stale, 30) == {"categories": {}}


def test_collect_records_page_failure_and_insight_savings(monkeypatch):
    def fake_run_once(url, form_factor, output_path, timeout):
        if url.endswith("/bad"):
            raise lh.LighthouseError("chrome crashed")
        return {"lighthouseVersion": "13.5.0", "categories": {"performance": {"score": 0.9}}, "audits": {}}

    monkeypatch.setattr(lh, "run_once", fake_run_once)
    report = lh.collect(
        {
            "site": "https://example.com",
            "lighthouse": {"pages": ["/bad", "/ok"], "form_factors": ["mobile", "desktop"], "runs": 1},
        }
    )
    assert report["results"][0] == {"page": "/bad", "form_factor": "mobile", "error": "chrome crashed"}
    assert any(row.get("page") == "/ok" and row.get("form_factor") == "desktop" and "scores" in row for row in report["results"])
    items = lh.top_opportunities(
        {
            "legacy-javascript-insight": {
                "id": "legacy-javascript-insight",
                "title": "Legacy JavaScript",
                "score": 0,
                "metricSavings": {"FCP": 0, "LCP": 150},
                "details": {"type": "table", "items": []},
            },
            "cache-insight": {
                "id": "cache-insight",
                "title": "Cache",
                "score": 0.5,
                "metricSavings": {"FCP": 0, "LCP": 0},
                "details": {"type": "table"},
            },
        }
    )
    assert items == [{"id": "legacy-javascript-insight", "title": "Legacy JavaScript", "savings_ms": 150}]
