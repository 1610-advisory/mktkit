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
