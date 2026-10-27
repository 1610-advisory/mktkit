# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Compare two SEO snapshot directories and write a short markdown diff.

Usage:
    uv run seo_diff.py --prev tracking/seo/snapshots/2026-10-20 --curr tracking/seo/snapshots/2026-10-27 --out tracking/seo/snapshots/2026-10-27/diff.md

Each directory may contain crawl.json, lighthouse.json, gsc.json, and ai.json.
Missing files are skipped with one line. If --prev is missing or has none of
those files, the report is a first baseline of the current snapshot.

Issues match on code + url. Search diffs the gsc summary keys clicks,
impressions, ctr, position, indexed, not_indexed. AI diffs per-engine
mention_rate and citation_rate.

Environment variables:
    none

Commands:
    (single action; no subcommands)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

SNAPSHOT_FILES = ("crawl.json", "lighthouse.json", "gsc.json", "ai.json")
GSC_KEYS = ("clicks", "impressions", "ctr", "position", "indexed", "not_indexed")
SEV_RANK = {"high": 0, "medium": 1, "low": 2}
GSC_LABELS = {
    "clicks": "Clicks",
    "impressions": "Impressions",
    "ctr": "CTR",
    "position": "Average position",
    "indexed": "Indexed",
    "not_indexed": "Not indexed",
}


def load_snapshot(path: Path) -> dict:
    found = {}
    if not path.is_dir():
        return found
    for name in SNAPSHOT_FILES:
        file_path = path / name
        if file_path.is_file():
            found[name] = json.loads(file_path.read_text(encoding="utf-8"))
    return found


def is_baseline(prev_path: Path) -> bool:
    return not load_snapshot(prev_path)


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_num(value, digits: int) -> str:
    if value is None:
        return "n/a"
    if digits == 0:
        return str(int(round(value)))
    return f"{value:.{digits}f}"


def _with_delta(curr, prev, digits: int) -> str:
    text = _fmt_num(curr, digits)
    if curr is None or prev is None:
        return text
    delta = curr - prev
    if digits == 0:
        shown = f"{int(round(delta)):+d}"
    else:
        shown = f"{delta:+.{digits}f}"
    if shown in ("+0", "-0", "+0.0", "-0.0", "+0.00", "-0.00", "+0.000", "-0.000"):
        shown = "0"
    return f"{text} ({shown})"


def _slash_key(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return url or ""
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{path}{query}"


def _issue_key(issue: dict) -> tuple:
    return (issue.get("code") or "", issue.get("url") or "")


def _issues(crawl: dict | None) -> list[dict]:
    if not crawl:
        return []
    items = crawl.get("issues") or []
    return [item for item in items if isinstance(item, dict)]


def _format_issue(issue: dict) -> str:
    line = f"- {issue.get('severity') or 'unknown'} {issue.get('code')} on {issue.get('url')}"
    detail = (issue.get("detail") or "").strip()
    if detail:
        line += f". {detail}"
    return line


def _sorted_issues(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: (SEV_RANK.get(item.get("severity"), 9), item.get("code") or "", item.get("url") or ""))


def _diff_issues(prev_items: list[dict], curr_items: list[dict]) -> tuple[list[dict], list[dict]]:
    prev_map = {_issue_key(item): item for item in prev_items}
    curr_map = {_issue_key(item): item for item in curr_items}
    new = [curr_map[key] for key in curr_map if key not in prev_map]
    resolved = [prev_map[key] for key in prev_map if key not in curr_map]
    return _sorted_issues(new), _sorted_issues(resolved)


def _severity_counts(items: list[dict]) -> dict:
    counts = {"high": 0, "medium": 0, "low": 0}
    for item in items:
        sev = item.get("severity")
        if sev in counts:
            counts[sev] += 1
    return counts


def _page_label(row: dict) -> str:
    page = row.get("page")
    if page:
        return str(page)
    url = row.get("url") or ""
    path = urlparse(url).path or url
    return path or url


def _speed_rows(prev_lh: dict | None, curr_lh: dict | None) -> list[dict]:
    prev_map = {}
    for row in (prev_lh or {}).get("results") or []:
        if isinstance(row, dict):
            prev_map[(_slash_key(row.get("url") or ""), row.get("form_factor"))] = row
    rows = []
    for row in (curr_lh or {}).get("results") or []:
        if not isinstance(row, dict):
            continue
        key = (_slash_key(row.get("url") or ""), row.get("form_factor"))
        prev = prev_map.get(key)
        curr_scores = row.get("scores") or {}
        prev_scores = (prev or {}).get("scores") or {}
        curr_metrics = row.get("metrics") or {}
        prev_metrics = (prev or {}).get("metrics") or {}
        rows.append(
            {
                "page": _page_label(row),
                "form_factor": row.get("form_factor") or "",
                "perf": _num(curr_scores.get("performance")),
                "prev_perf": _num(prev_scores.get("performance")) if prev else None,
                "lcp": _num(curr_metrics.get("lcp_ms")),
                "prev_lcp": _num(prev_metrics.get("lcp_ms")) if prev else None,
                "cls": _num(curr_metrics.get("cls")),
                "prev_cls": _num(prev_metrics.get("cls")) if prev else None,
                "has_prev": prev is not None,
            }
        )
    rows.sort(key=lambda item: (item["page"], item["form_factor"]))
    return rows


def _gsc_summary(doc: dict | None) -> dict:
    if not doc:
        return {}
    summary = doc.get("summary") or {}
    return summary if isinstance(summary, dict) else {}


def _ai_summary(doc: dict | None) -> dict:
    if not doc:
        return {}
    summary = doc.get("summary") or {}
    if not isinstance(summary, dict):
        return {}
    cleaned = {}
    for engine, stats in summary.items():
        if isinstance(stats, dict):
            cleaned[str(engine)] = stats
    return cleaned


def _headline(prev: dict, curr: dict, *, baseline: bool) -> list[str]:
    bullets: list[tuple[float, str]] = []
    crawl = curr.get("crawl.json")
    issues = _issues(crawl)
    sev = _severity_counts(issues)

    if baseline:
        bullets.append((1000, "First baseline. No previous snapshot to compare."))
        if crawl:
            counts = crawl.get("counts") or {}
            pages = counts.get("pages")
            html_pages = counts.get("html_pages")
            if pages is not None:
                bullets.append((900, f"Crawled {pages} pages, {html_pages if html_pages is not None else 'unknown'} of them HTML."))
            bullets.append(
                (
                    800,
                    f"{len(issues)} issues: {sev['high']} high, {sev['medium']} medium, {sev['low']} low.",
                )
            )
        else:
            bullets.append((800, "crawl.json is missing from the current snapshot."))
        rows = _speed_rows(None, curr.get("lighthouse.json"))
        if rows:
            row = rows[0]
            bullets.append((700, f"{row['form_factor']} performance on {row['page']} is {_fmt_num(row['perf'], 0)}. LCP is {_fmt_num(row['lcp'], 0)} ms."))
        else:
            bullets.append((100, "No Lighthouse results in this snapshot."))
        gsc = _gsc_summary(curr.get("gsc.json"))
        if gsc:
            clicks = gsc.get("clicks")
            impressions = gsc.get("impressions")
            bullets.append((600, f"Search: {clicks} clicks, {impressions} impressions."))
        ai = _ai_summary(curr.get("ai.json"))
        if ai:
            engine = sorted(ai)[0]
            stats = ai[engine]
            bullets.append(
                (
                    500,
                    f"{engine} mention rate {_fmt_num(_num(stats.get('mention_rate')), 2)}, citation rate {_fmt_num(_num(stats.get('citation_rate')), 2)}.",
                )
            )
        ordered = [text for _, text in bullets]
        while len(ordered) < 3:
            ordered.append("No other snapshot files to summarize.")
        return ordered[:5]

    new, resolved = _diff_issues(_issues(prev.get("crawl.json")), issues) if "crawl.json" in curr and "crawl.json" in prev else ([], [])
    if "crawl.json" in curr and "crawl.json" in prev:
        high_new = [item for item in new if item.get("severity") == "high"]
        if high_new:
            bullets.append((1000 + len(high_new), f"{len(high_new)} new high-severity issues."))
        bullets.append((500 + len(new) + len(resolved), f"{len(new)} new issues, {len(resolved)} resolved."))
        if not high_new:
            bullets.append((200, "No new high-severity issues."))
    elif "crawl.json" not in curr:
        bullets.append((400, "crawl.json is missing from the current snapshot."))
    else:
        bullets.append((400, "crawl.json is missing from the previous snapshot."))

    for row in _speed_rows(prev.get("lighthouse.json"), curr.get("lighthouse.json")):
        if row["has_prev"] and row["perf"] is not None and row["prev_perf"] is not None:
            delta = row["perf"] - row["prev_perf"]
            bullets.append(
                (
                    abs(delta) * 10,
                    f"Performance on {row['page']} ({row['form_factor']}) moved from {_fmt_num(row['prev_perf'], 0)} to {_fmt_num(row['perf'], 0)}.",
                )
            )
        if row["has_prev"] and row["lcp"] is not None and row["prev_lcp"] is not None:
            delta = row["lcp"] - row["prev_lcp"]
            if abs(delta) >= 100:
                direction = "down" if delta < 0 else "up"
                bullets.append((abs(delta) / 50, f"LCP on {row['page']} ({row['form_factor']}) is {direction} {abs(int(round(delta)))} ms."))

    prev_gsc = _gsc_summary(prev.get("gsc.json"))
    curr_gsc = _gsc_summary(curr.get("gsc.json"))
    if prev_gsc and curr_gsc:
        for key, weight in (("clicks", 1), ("impressions", 0.01), ("indexed", 5)):
            old = _num(prev_gsc.get(key))
            new_val = _num(curr_gsc.get(key))
            if old is None or new_val is None or old == new_val:
                continue
            bullets.append((abs(new_val - old) * weight, f"{GSC_LABELS[key]} moved from {_fmt_num(old, 0)} to {_fmt_num(new_val, 0)}."))
        old_pos = _num(prev_gsc.get("position"))
        new_pos = _num(curr_gsc.get("position"))
        if old_pos is not None and new_pos is not None and abs(new_pos - old_pos) >= 0.1:
            bullets.append((abs(new_pos - old_pos) * 20, f"Average position moved from {old_pos:.1f} to {new_pos:.1f}."))

    prev_ai = _ai_summary(prev.get("ai.json"))
    curr_ai = _ai_summary(curr.get("ai.json"))
    for engine in sorted(set(prev_ai) & set(curr_ai)):
        old = _num(prev_ai[engine].get("mention_rate"))
        new_val = _num(curr_ai[engine].get("mention_rate"))
        if old is None or new_val is None or old == new_val:
            continue
        bullets.append((abs(new_val - old) * 100, f"{engine} mention rate moved from {old:.2f} to {new_val:.2f}."))

    if not any(name in curr for name in ("lighthouse.json",)):
        bullets.append((50, "No Lighthouse file in the current snapshot."))
    if "gsc.json" not in curr and "gsc.json" not in prev:
        bullets.append((40, "No Search Console file in these snapshots."))
    if "ai.json" not in curr and "ai.json" not in prev:
        bullets.append((30, "No AI answer file in these snapshots."))

    bullets.sort(key=lambda item: -item[0])
    ordered = []
    for _, text in bullets:
        if text not in ordered:
            ordered.append(text)
    fillers = (
        f"Current issue count is {len(issues)}.",
        "Speed section has the page scores.",
        "Search and AI sections note any missing files.",
    )
    for filler in fillers:
        if len(ordered) >= 3:
            break
        if filler not in ordered:
            ordered.append(filler)
    return ordered[:5]


def _issue_section(prev: dict, curr: dict, *, baseline: bool, kind: str) -> list[str]:
    if "crawl.json" not in curr:
        return ["crawl.json is missing from the current snapshot."]
    if baseline:
        if kind == "new":
            lines = ["First baseline. These are the current issues, not changes from last week."]
            items = _sorted_issues(_issues(curr.get("crawl.json")))
            if not items:
                lines.append("No issues in the current crawl.")
            lines.extend(_format_issue(item) for item in items)
            return lines
        return ["No previous snapshot, so nothing to resolve."]
    if "crawl.json" not in prev:
        return ["crawl.json is missing from the previous snapshot."]
    new, resolved = _diff_issues(_issues(prev.get("crawl.json")), _issues(curr.get("crawl.json")))
    items = new if kind == "new" else resolved
    if not items:
        return ["None."]
    return [_format_issue(item) for item in items]


def _speed_section(prev: dict, curr: dict, *, baseline: bool) -> list[str]:
    if "lighthouse.json" not in curr:
        return ["lighthouse.json is missing from the current snapshot."]
    if not baseline and "lighthouse.json" not in prev:
        note = ["lighthouse.json is missing from the previous snapshot."]
    else:
        note = []
    rows = _speed_rows(None if baseline else prev.get("lighthouse.json"), curr.get("lighthouse.json"))
    if not rows:
        return note + ["No Lighthouse results in this snapshot."]
    lines = note + [
        "| Page | Form factor | Perf | LCP (ms) | CLS |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if baseline or not row["has_prev"]:
            perf = _fmt_num(row["perf"], 0)
            lcp = _fmt_num(row["lcp"], 0)
            cls = _fmt_num(row["cls"], 3)
            if not baseline and not row["has_prev"]:
                perf += " (new)"
                lcp += " (new)"
                cls += " (new)"
        else:
            perf = _with_delta(row["perf"], row["prev_perf"], 0)
            lcp = _with_delta(row["lcp"], row["prev_lcp"], 0)
            cls = _with_delta(row["cls"], row["prev_cls"], 3)
        page = str(row["page"]).replace("|", "/")
        lines.append(f"| {page} | {row['form_factor']} | {perf} | {lcp} | {cls} |")
    return lines


def _search_section(prev: dict, curr: dict, *, baseline: bool) -> list[str]:
    if "gsc.json" not in curr:
        return ["gsc.json is missing from the current snapshot."]
    curr_summary = _gsc_summary(curr.get("gsc.json"))
    if not curr_summary:
        return ["gsc.json has no summary."]
    prev_summary = {} if baseline else _gsc_summary(prev.get("gsc.json"))
    if not baseline and "gsc.json" not in prev:
        lines = ["gsc.json is missing from the previous snapshot."]
        prev_summary = {}
    else:
        lines = []
    digits = {"clicks": 0, "impressions": 0, "ctr": 4, "position": 1, "indexed": 0, "not_indexed": 0}
    for key in GSC_KEYS:
        if key not in curr_summary:
            continue
        curr_val = _num(curr_summary.get(key))
        prev_val = _num(prev_summary.get(key)) if key in prev_summary else None
        shown = _fmt_num(curr_val, digits[key]) if prev_val is None else _with_delta(curr_val, prev_val, digits[key])
        lines.append(f"- {GSC_LABELS[key]}: {shown}")
    return lines or ["gsc.json summary has none of the expected keys."]


def _ai_section(prev: dict, curr: dict, *, baseline: bool) -> list[str]:
    if "ai.json" not in curr:
        return ["ai.json is missing from the current snapshot."]
    curr_summary = _ai_summary(curr.get("ai.json"))
    if not curr_summary:
        return ["ai.json has no summary."]
    if not baseline and "ai.json" not in prev:
        lines = ["ai.json is missing from the previous snapshot."]
        prev_summary = {}
    else:
        lines = []
        prev_summary = {} if baseline else _ai_summary(prev.get("ai.json"))
    for engine in sorted(curr_summary):
        stats = curr_summary[engine]
        mention = _num(stats.get("mention_rate"))
        citation = _num(stats.get("citation_rate"))
        prev_stats = prev_summary.get(engine) or {}
        prev_mention = _num(prev_stats.get("mention_rate")) if prev_stats else None
        prev_citation = _num(prev_stats.get("citation_rate")) if prev_stats else None
        mention_txt = _fmt_num(mention, 2) if prev_mention is None else _with_delta(mention, prev_mention, 2)
        citation_txt = _fmt_num(citation, 2) if prev_citation is None else _with_delta(citation, prev_citation, 2)
        lines.append(f"- {engine}: mention rate {mention_txt}, citation rate {citation_txt}")
    return lines


def render_diff(prev: dict, curr: dict, *, baseline: bool, prev_label: str, curr_label: str) -> str:
    """Build the markdown report. prev may be empty when baseline is true."""
    headline = _headline(prev, curr, baseline=baseline)
    sections = [
        "# SEO diff",
        "",
        f"Current snapshot: {curr_label}",
        f"Previous snapshot: {'none' if baseline else prev_label}",
        "",
        "## Headline",
        "",
        *[f"- {line}" for line in headline],
        "",
        "## New issues",
        "",
        *_issue_section(prev, curr, baseline=baseline, kind="new"),
        "",
        "## Resolved issues",
        "",
        *_issue_section(prev, curr, baseline=baseline, kind="resolved"),
        "",
        "## Speed",
        "",
        *_speed_section(prev, curr, baseline=baseline),
        "",
        "## Search",
        "",
        *_search_section(prev, curr, baseline=baseline),
        "",
        "## AI answers",
        "",
        *_ai_section(prev, curr, baseline=baseline),
        "",
    ]
    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write a markdown diff of two SEO snapshots.")
    parser.add_argument("--prev", required=True, help="Previous snapshot directory (may be missing)")
    parser.add_argument("--curr", required=True, help="Current snapshot directory")
    parser.add_argument("--out", required=True, help="Output markdown path")
    args = parser.parse_args(argv)

    curr_path = Path(args.curr)
    prev_path = Path(args.prev)
    if not curr_path.is_dir():
        print(f"Error: current snapshot not found: {curr_path}", file=sys.stderr)
        return 1
    curr = load_snapshot(curr_path)
    if not curr:
        print("Error: current snapshot has no crawl.json, lighthouse.json, gsc.json, or ai.json", file=sys.stderr)
        return 1
    baseline = is_baseline(prev_path)
    prev = {} if baseline else load_snapshot(prev_path)
    text = render_diff(
        prev,
        curr,
        baseline=baseline,
        prev_label=prev_path.name,
        curr_label=curr_path.name,
    )
    if "\u2014" in text or "\u2013" in text:
        print("Error: diff renderer produced a dash that is not a hyphen", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    kind = "baseline" if baseline else "diff"
    print(f"Wrote {out} ({kind})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
