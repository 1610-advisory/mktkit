# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
Run Lighthouse and write a small JSON summary.

Usage:
    uv run lighthouse_run.py --config tracking/seo/config.yaml --out tracking/seo/snapshots/2026-10-27/lighthouse.json

For each lighthouse.pages x form_factors entry, runs Lighthouse once per
config runs (median performance score wins when runs > 1). Uses the
lighthouse binary on PATH when present, otherwise npx lighthouse@13.5.0.
Raw reports stay in a temp directory, not the repo.

Desktop runs add --preset=desktop. Mobile is the Lighthouse default.
Scores are 0-100. Timing metrics are milliseconds. CLS is unitless.

Environment variables:
    none (Chrome is discovered by Lighthouse)

Commands:
    (single action; no subcommands)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_config import load_config

LIGHTHOUSE_PIN = "lighthouse@13.5.0"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
METRIC_AUDITS = {
    "lcp_ms": "largest-contentful-paint",
    "cls": "cumulative-layout-shift",
    "tbt_ms": "total-blocking-time",
    "fcp_ms": "first-contentful-paint",
    "speed_index_ms": "speed-index",
}


class LighthouseError(Exception):
    """Lighthouse or Chrome failed. CLI exits 2."""


def default_prefix() -> list[str]:
    if shutil.which("lighthouse"):
        return ["lighthouse"]
    return ["npx", "--yes", LIGHTHOUSE_PIN]


def lighthouse_argv(url: str, form_factor: str, output_path: Path, prefix: list[str] | None = None) -> list[str]:
    """Build the Lighthouse command. Desktop is the only form factor that adds a preset."""
    cmd = list(prefix if prefix is not None else default_prefix())
    cmd.extend(
        [
            url,
            "--output=json",
            f"--output-path={output_path}",
            "--quiet",
            "--chrome-flags=--headless=new",
            "--only-categories=" + ",".join(CATEGORIES),
        ]
    )
    if form_factor == "desktop":
        cmd.append("--preset=desktop")
    return cmd


def page_url(site: str, page: str) -> str:
    if page.startswith("http://") or page.startswith("https://"):
        return page
    if not page.startswith("/"):
        page = "/" + page
    return site.rstrip("/") + page


def _round_metric(value, digits: int):
    if value is None:
        return None
    number = float(value)
    if digits == 0:
        return int(round(number))
    return round(number, digits)


def _first_snippet(audit: dict | None) -> str | None:
    if not isinstance(audit, dict):
        return None
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            snippet = node.get("snippet")
            if isinstance(snippet, str) and snippet.strip():
                found.append(snippet)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(audit.get("details"))
    return found[0] if found else None


def extract_lcp_snippet(audits: dict) -> str | None:
    """Lighthouse 13 names the element audit lcp-breakdown-insight. Older builds use largest-contentful-paint-element."""
    for key in ("largest-contentful-paint-element", "lcp-breakdown-insight"):
        snippet = _first_snippet((audits or {}).get(key))
        if snippet:
            return snippet
    return None


def estimated_savings_ms(audit: dict) -> int:
    details = audit.get("details") or {}
    raw = details.get("overallSavingsMs")
    if not raw:
        # Lighthouse 13 sometimes puts the estimate only in metricSavings.
        metric = details.get("metricSavings") or audit.get("metricSavings") or {}
        if isinstance(metric, dict):
            nums = [float(value) for value in metric.values() if isinstance(value, (int, float))]
            raw = max(nums) if nums else 0
    return int(round(float(raw or 0)))


def top_opportunities(audits: dict, limit: int = 3) -> list[dict]:
    items = []
    for audit_id, audit in (audits or {}).items():
        if not isinstance(audit, dict):
            continue
        details = audit.get("details") or {}
        if details.get("type") != "opportunity":
            continue
        score = audit.get("score")
        if score is None or score >= 1:
            continue
        items.append(
            {
                "id": audit.get("id") or audit_id,
                "title": audit.get("title") or audit_id,
                "savings_ms": estimated_savings_ms(audit),
            }
        )
    items.sort(key=lambda item: (-item["savings_ms"], item["id"]))
    return items[:limit]


def extract_report(report: dict) -> dict:
    """Pull scores, metrics, LCP snippet, and top failing opportunities from a raw report."""
    categories = report.get("categories") or {}
    audits = report.get("audits") or {}

    def score(name: str):
        raw = (categories.get(name) or {}).get("score")
        if raw is None:
            return None
        return int(round(float(raw) * 100))

    metrics = {}
    for key, audit_id in METRIC_AUDITS.items():
        raw = (audits.get(audit_id) or {}).get("numericValue")
        digits = 3 if key == "cls" else 0
        metrics[key] = _round_metric(raw, digits)

    return {
        "scores": {name: score(name) for name in CATEGORIES},
        "metrics": metrics,
        "lcp_element": extract_lcp_snippet(audits),
        "opportunities": top_opportunities(audits, 3),
    }


def performance_score(report: dict) -> float:
    raw = ((report.get("categories") or {}).get("performance") or {}).get("score")
    if raw is None:
        return -1.0
    return float(raw)


def pick_median(reports: list[dict]) -> dict:
    """Pick the run whose performance score is the median. Does not average metrics.

    Even counts use the lower of the two middle runs.
    """
    if not reports:
        raise LighthouseError("no Lighthouse reports to summarize")
    ordered = sorted(reports, key=performance_score)
    return ordered[(len(ordered) - 1) // 2]


def run_once(url: str, form_factor: str, output_path: Path, timeout: int) -> dict:
    cmd = lighthouse_argv(url, form_factor, output_path)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise LighthouseError(f"lighthouse timed out after {timeout}s for {url}") from exc
    except FileNotFoundError as exc:
        raise LighthouseError(f"could not run {cmd[0]}") from exc
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        tail = err[-1500:] if err else "no error output"
        raise LighthouseError(f"lighthouse exited {proc.returncode} for {url}: {tail}")
    if not output_path.is_file():
        raise LighthouseError(f"lighthouse wrote no report for {url}")
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LighthouseError(f"lighthouse report was not JSON for {url}: {exc}") from exc


def collect(
    config: dict,
    *,
    pages: list[str] | None = None,
    form_factors: list[str] | None = None,
    runs: int | None = None,
    timeout: int = 300,
) -> dict:
    block = config.get("lighthouse") or {}
    pages = list(pages if pages is not None else (block.get("pages") or []))
    form_factors = list(form_factors if form_factors is not None else (block.get("form_factors") or ["mobile"]))
    if not pages:
        raise ValueError("Config lighthouse.pages is empty")
    if runs is None:
        runs = int(block.get("runs") or 1)
    else:
        runs = int(runs)
    if runs < 1:
        raise ValueError("Config lighthouse.runs must be at least 1")
    allowed = {"mobile", "desktop"}
    unknown = [item for item in form_factors if item not in allowed]
    if unknown or not form_factors:
        raise ValueError("lighthouse.form_factors must be mobile and/or desktop")

    results = []
    tool_version = None
    with tempfile.TemporaryDirectory(prefix="seo-kit-lighthouse-") as tmp:
        tmp_path = Path(tmp)
        for page in pages:
            url = page_url(config["site"], page)
            for form_factor in form_factors:
                reports = []
                for run_index in range(runs):
                    out = tmp_path / f"report-{run_index}.json"
                    reports.append(run_once(url, form_factor, out, timeout))
                chosen = pick_median(reports)
                tool_version = tool_version or chosen.get("lighthouseVersion")
                row = {
                    "url": url,
                    "page": page,
                    "form_factor": form_factor,
                    "runs": runs,
                }
                row.update(extract_report(chosen))
                results.append(row)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": tool_version or "unknown",
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Lighthouse and write a JSON summary.")
    parser.add_argument("--config", required=True, help="Path to tracking/seo/config.yaml")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--pages", help="Comma-separated page paths, overrides config")
    parser.add_argument("--form-factors", help="Comma-separated mobile,desktop, overrides config")
    parser.add_argument("--runs", type=int, help="Runs per page, overrides config")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds per Lighthouse run")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    pages = [p.strip() for p in args.pages.split(",") if p.strip()] if args.pages else None
    factors = [p.strip() for p in args.form_factors.split(",") if p.strip()] if args.form_factors else None
    try:
        report = collect(
            config,
            pages=pages,
            form_factors=factors,
            runs=args.runs,
            timeout=args.timeout,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except LighthouseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for row in report["results"]:
        perf = row["scores"]["performance"]
        lcp = row["metrics"]["lcp_ms"]
        print(f"{row['form_factor']} {row['page']}: perf {perf}, LCP {lcp} ms", file=sys.stderr)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
