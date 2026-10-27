import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seo_diff

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _bullets(text: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index("## Headline") + 1
    bullets = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("- "):
            bullets.append(line[2:])
    return bullets


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.index(marker) + len(marker)
    rest = text[start:]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def test_fixture_diff_new_and_resolved(tmp_path):
    code = seo_diff.main(
        [
            "--prev",
            str(FIXTURES / "prev"),
            "--curr",
            str(FIXTURES / "curr"),
            "--out",
            str(tmp_path / "diff.md"),
        ]
    )
    assert code == 0
    text = (tmp_path / "diff.md").read_text(encoding="utf-8")
    assert "\u2014" not in text
    assert "\u2013" not in text
    bullets = _bullets(text)
    assert 3 <= len(bullets) <= 5
    new = _section(text, "New issues")
    resolved = _section(text, "Resolved issues")
    assert "broken_internal_link" in new
    assert "missing_description" in resolved
    assert "title_too_long" not in new
    assert "title_too_long" not in resolved
    speed = _section(text, "Speed")
    assert "| / | mobile | 85 (+15) | 2100 (-900) | 0.040 (-0.060) |" in speed
    search = _section(text, "Search")
    assert "Clicks: 140 (+40)" in search
    assert "Average position: 9.5 (-2.5)" in search
    ai = _section(text, "AI answers")
    assert "openai: mention rate 0.50 (+0.30), citation rate 0.30 (+0.20)" in ai
    assert "perplexity: mention rate 0.00 (0), citation rate 0.00 (0)" in ai


def test_missing_prev_is_baseline(tmp_path):
    code = seo_diff.main(
        [
            "--prev",
            str(tmp_path / "no-such-snapshot"),
            "--curr",
            str(FIXTURES / "curr"),
            "--out",
            str(tmp_path / "base.md"),
        ]
    )
    assert code == 0
    text = (tmp_path / "base.md").read_text(encoding="utf-8")
    assert "First baseline" in text
    assert "Previous snapshot: none" in text
    bullets = _bullets(text)
    assert 3 <= len(bullets) <= 5
    assert "broken_internal_link" in _section(text, "New issues")
    assert "nothing to resolve" in _section(text, "Resolved issues")


def test_empty_prev_dir_is_baseline(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    text = seo_diff.render_diff(
        {},
        seo_diff.load_snapshot(FIXTURES / "curr"),
        baseline=True,
        prev_label="empty",
        curr_label="curr",
    )
    assert seo_diff.is_baseline(empty)
    assert "First baseline" in text


def test_missing_file_is_one_line(tmp_path):
    curr = tmp_path / "curr"
    prev = tmp_path / "prev"
    curr.mkdir()
    prev.mkdir()
    (curr / "lighthouse.json").write_text((FIXTURES / "curr" / "lighthouse.json").read_text(encoding="utf-8"), encoding="utf-8")
    (prev / "crawl.json").write_text((FIXTURES / "prev" / "crawl.json").read_text(encoding="utf-8"), encoding="utf-8")
    (prev / "lighthouse.json").write_text((FIXTURES / "prev" / "lighthouse.json").read_text(encoding="utf-8"), encoding="utf-8")
    text = seo_diff.render_diff(
        seo_diff.load_snapshot(prev),
        seo_diff.load_snapshot(curr),
        baseline=False,
        prev_label="prev",
        curr_label="curr",
    )
    assert "crawl.json is missing from the current snapshot." in _section(text, "New issues")
    assert "gsc.json is missing from the current snapshot." in _section(text, "Search")
    assert "ai.json is missing from the current snapshot." in _section(text, "AI answers")


def test_main_missing_curr(tmp_path):
    assert seo_diff.main(["--prev", str(tmp_path), "--curr", str(tmp_path / "nope"), "--out", str(tmp_path / "x.md")]) == 1


def test_main_without_prev_writes_baseline(tmp_path):
    curr = tmp_path / "2026-01-08"
    curr.mkdir()
    (curr / "crawl.json").write_text('{"pages": {}, "issues": [], "counts": {"pages": 0, "html_pages": 0}}')
    out = tmp_path / "diff.md"
    assert seo_diff.main(["--curr", str(curr), "--out", str(out)]) == 0
    assert "Previous snapshot: none" in out.read_text()
