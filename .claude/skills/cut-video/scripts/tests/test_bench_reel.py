#!/usr/bin/env python3
"""Tests for bench-reel.py. No live harness binaries, no real footage."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image


SCRIPTS = Path(__file__).resolve().parent.parent
BENCH = SCRIPTS / "bench-reel.py"
SKILL_DIR = SCRIPTS.parent
PY = sys.executable


def load_bench():
    spec = importlib.util.spec_from_file_location("bench_reel", BENCH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import bench-reel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_cli(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(BENCH), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_workspace() -> dict[str, Path]:
    root = Path(tempfile.mkdtemp(prefix="bench-ws-"))
    cwd = root / "repo"
    cwd.mkdir()
    note = cwd / "NOTE.md"
    note.write_text("# synthetic note\n", encoding="utf-8")
    style = cwd / "style.json"
    write_json(style, {"cover": {"text": "SYNTHETIC"}})
    output_root = cwd / "out"
    output_root.mkdir()
    return {
        "root": root,
        "cwd": cwd,
        "note": note,
        "style": style,
        "output_root": output_root,
        "skill_dir": SKILL_DIR,
    }


def base_config(ws: dict[str, Path], harnesses: list[dict]) -> dict:
    return {
        "schema": "reel-bench/1",
        "cwd": str(ws["cwd"]),
        "task": {
            "note": str(ws["note"]),
            "style": str(ws["style"]),
            "output_root": str(ws["output_root"]),
            "skill_dir": str(ws["skill_dir"]),
            "mode": "proxy",
            "extra_instructions": "keep punches under three seconds",
        },
        "concurrency": 1,
        "timeout_min": 1,
        "harnesses": harnesses,
    }


def test_help_exits_zero() -> None:
    r = run_cli(["--help"])
    assert r.returncode == 0, r.stderr
    out = r.stdout.lower()
    assert "exit" in out or "0" in out
    assert "--config" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--report-only" in r.stdout
    assert "--verifier-cmd" in r.stdout
    assert "--grades" in r.stdout
    assert "broll_index" in r.stdout
    assert "deliver_to" in r.stdout
    assert "verifier" in r.stdout.lower()
    doc = BENCH.read_text(encoding="utf-8")
    assert "Exit codes" in doc
    assert "pi" in doc and "claude" in doc
    assert "qa_verdict" in doc or "QA" in doc
    assert "stray_writes" in doc or "stray writes" in doc


def test_missing_note_exits_two() -> None:
    ws = make_workspace()
    try:
        cfg = base_config(
            ws,
            [{"id": "pi-a", "kind": "pi", "provider": "xai", "model": "grok-4.6"}],
        )
        cfg["task"]["note"] = str(ws["cwd"] / "no-such-note.md")
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        r = run_cli(["--config", str(cfg_path)])
        assert r.returncode == 2, r.stdout + r.stderr
        assert "note" in (r.stderr + r.stdout).lower()
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def test_duplicate_ids_exits_two() -> None:
    ws = make_workspace()
    try:
        cfg = base_config(
            ws,
            [
                {"id": "same", "kind": "pi", "provider": "xai", "model": "grok-4.6"},
                {"id": "same", "kind": "claude", "model": "claude-fable-5-1"},
            ],
        )
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        r = run_cli(["--config", str(cfg_path)])
        assert r.returncode == 2, r.stdout + r.stderr
        assert "duplicate" in (r.stderr + r.stdout).lower()
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def test_template_rendering() -> None:
    bench = load_bench()
    text = bench.render_task_text(
        note="/path/to/NOTE.md",
        style="/path/to/style.json",
        output_dir="/path/to/out/harness-a",
        skill_dir="/path/to/skill",
        mode="proxy",
        harness_id="harness-a",
        extra="do not invent punches",
    )
    for name in bench.PLACEHOLDERS:
        assert "{" + name + "}" not in text, name
    assert "/path/to/out/harness-a" in text
    assert "do NOT modify any file outside" in text
    assert "/path/to/NOTE.md" in text
    assert "proxy" in text
    assert "do not invent punches" in text
    assert "Read `/path/to/skill/SKILL.md`" in text or "SKILL.md" in text


def test_adapter_command_construction() -> None:
    bench = load_bench()
    pi_cmd = bench.build_pi_cmd(
        pi_run="pi-run",
        cwd="/path/to/repo",
        provider="xai",
        model="grok-4.6",
        thinking="high",
        harness_id="pi-grok46-high",
        timeout_s=2700,
        task_file="/path/to/out/task.md",
    )
    pi_s = " ".join(pi_cmd)
    assert "--provider xai" in pi_s
    assert "--model grok-4.6" in pi_s
    assert "--thinking high" in pi_s
    assert "--isolation none" in pi_s
    assert "--json" in pi_s
    assert "--role generic" in pi_s
    assert "--spec-file" in pi_s

    claude_cmd = bench.build_claude_cmd(
        model="claude-fable-5-1",
        effort="high",
        skill_dir="/path/to/skill",
        task_text="cut the reel",
    )
    claude_s = " ".join(claude_cmd)
    assert "--model claude-fable-5-1" in claude_s
    assert "--effort high" in claude_s
    assert "--output-format json" in claude_s
    assert "-p" in claude_cmd
    assert "--permission-mode" in claude_cmd
    assert "--add-dir" in claude_cmd


def _write_fabricated_harness(
    out_dir: Path,
    *,
    hid: str = "fake-pi",
    model: str = "grok-4.6",
    provider: str = "xai",
    punches: list[dict] | None = None,
    write_runnotes: bool = False,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if punches is None:
        punches = [
            {
                "at_final": 1.0,
                "dur": 2.0,
                "kind": "clip",
                "line": "hello world",
                "shows": "a talking face",
                "path": "/tmp/a.mp4",
            },
            {
                "at_final": 4.0,
                "dur": 3.5,
                "kind": "still",
                "line": "then this",
                "shows": "a still of a wall",
                "path": "/tmp/b.jpg",
            },
        ]
    broll = []
    for p in punches:
        broll.append(
            {
                "kind": p.get("kind") or "clip",
                "path": p.get("path") or "",
                "at": p.get("at", p.get("at_final") or 0),
                "dur": p.get("dur") or 2.0,
                "line": p.get("line") or "",
                "shows": p.get("shows") or "",
            }
        )
    write_json(
        out_dir / "X.reel.json",
        {
            "schema": "reel-manifest/1",
            "id": "XX-20260101-01",
            "slug": "bench-synthetic",
            "output_dir": str(out_dir),
            "duration_window": [4, 12],
            "source": {
                "video": "/path/to/missing.mp4",
                "transcript_json": "/path/to/missing.json",
            },
            "spine": {"ranges": [{"start": 0.4, "end": 7.5, "quote": "hello ... clip"}]},
            "hook": {"mode": "none"},
            "cover": {"text": "SYNTHETIC COVER", "case": "as-is"},
            "broll": broll,
        },
    )
    write_json(
        out_dir / "X.qa.json",
        {
            "verdict": "pass",
            "fails": [],
            "checks": [
                {
                    "id": "video.join_uncovered",
                    "status": "pass",
                    "detail": "joins covered",
                }
            ],
        },
    )
    write_json(
        out_dir / "X.timeline.json",
        {
            "hook": {"mode": "none", "present": False},
            "cover": {"text": "SYNTHETIC COVER"},
            "punches": punches,
            "joins": [],
            "captions": {"count": 0},
            "duration_s": 8.0,
        },
    )
    write_json(
        out_dir / "harness.json",
        {
            "id": hid,
            "kind": "pi",
            "provider": provider,
            "model": model,
            "thinking": "high",
            "started": "2026-01-01T00:00:00Z",
            "ended": "2026-01-01T00:01:00Z",
            "wall_s": 12.5,
            "exit": 0,
            "cost_usd": 0.01,
            "tokens_in": 100,
            "tokens_out": 50,
            "notes": [],
            "skipped": False,
            "timeout": False,
        },
    )
    write_text(
        out_dir / "harness.log",
        "[render-reel] Preflight\n"
        "| check | status | detail |\n"
        "[render-reel] Preflight\n",
    )
    img = Image.new("RGB", (40, 60), (20, 20, 20))
    img.save(out_dir / "X.sheet.jpg", "JPEG")
    if write_runnotes:
        write_text(
            out_dir / "X-RUNNOTES.md",
            "# RUNNOTES\n\nSynthetic bench fixture.\n\n## Known deviations\n\nnone\n",
        )


def test_scoring_report_only() -> None:
    ws = make_workspace()
    try:
        hid = "fake-pi"
        out_dir = ws["output_root"] / hid
        _write_fabricated_harness(out_dir)
        cfg = base_config(
            ws,
            [
                {
                    "id": hid,
                    "kind": "pi",
                    "provider": "xai",
                    "model": "grok-4.6",
                    "thinking": "high",
                }
            ],
        )
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        md = ws["root"] / "bench-report.md"
        html = ws["root"] / "bench-report.html"
        r = run_cli(
            [
                "--config",
                str(cfg_path),
                "--report-only",
                "--report",
                str(md),
                "--html",
                str(html),
            ]
        )
        assert md.is_file(), r.stdout + r.stderr
        assert html.is_file(), r.stdout + r.stderr
        json_path = md.with_name("bench-report.json")
        assert json_path.is_file(), r.stdout + r.stderr
        data = json.loads(json_path.read_text(encoding="utf-8"))
        row = data["table"][0]
        harness = data["harnesses"][0]
        assert harness["dry_runs"] == 2, harness
        assert harness["qa_verdict"] == "pass", harness
        assert len(harness["punches"]) == 2, harness
        assert row["punches"] == 2
        md_text = md.read_text(encoding="utf-8")
        assert "fake-pi" in md_text
        assert "How to read this" in md_text
        html_text = html.read_text(encoding="utf-8")
        assert "prefers-color-scheme" in html_text
        assert "fake-pi" in html_text
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def test_stray_write_detection() -> None:
    bench = load_bench()
    root = Path(tempfile.mkdtemp(prefix="bench-git-"))
    try:
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "bench@example.com"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Bench"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        (root / "README.md").write_text("init\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        output_root = root / "out"
        output_root.mkdir()
        before = bench.git_porcelain(root)
        (root / "stray.txt").write_text("touched\n", encoding="utf-8")
        (output_root / "inside.txt").write_text("ok\n", encoding="utf-8")
        after = bench.git_porcelain(root)
        stray = bench.stray_writes(
            before, after, cwd=root, output_root=output_root
        )
        assert any("stray.txt" in s for s in stray), stray
        assert not any("inside.txt" in s for s in stray), stray
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_missing_codex_binary_skipped() -> None:
    ws = make_workspace()
    try:
        cfg = base_config(
            ws,
            [{"id": "codex-missing", "kind": "codex", "model": "gpt-5"}],
        )
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"
        r = run_cli(["--config", str(cfg_path)], env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        harness_json = ws["output_root"] / "codex-missing" / "harness.json"
        assert harness_json.is_file(), r.stdout + r.stderr
        rec = json.loads(harness_json.read_text(encoding="utf-8"))
        assert rec.get("skipped") is True
        notes = " ".join(str(n) for n in rec.get("notes") or [])
        assert "binary not found" in notes.lower()
        combined = (r.stdout + r.stderr).lower()
        assert "skipped" in combined or "binary not found" in combined
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def _write_verifier_stub(path: Path, mode: str) -> None:
    if mode == "rank":
        body = '''#!/usr/bin/env python3
import json, sys
text = sys.stdin.read()
if "same-kind-hallway" in text:
    doc = {
        "punches": [{"index": 0, "grade": "category", "sees": "a hallway", "reason": "same kind"}],
        "unpunched": [{"beat": "the named object", "should_have_punched": True, "reason": "sheet shows it"}],
    }
else:
    doc = {
        "punches": [{"index": 0, "grade": "exact", "sees": "the named object", "reason": "literal"}],
        "unpunched": [{"beat": "aside", "should_have_punched": False, "reason": "nothing exact"}],
    }
print(json.dumps(doc))
'''
    else:
        body = '''#!/usr/bin/env python3
import json, sys
sys.stdin.read()
doc = {
    "punches": [
        {"index": 0, "grade": "exact", "sees": "object a", "reason": "match"},
        {"index": 1, "grade": "exact", "sees": "object b", "reason": "match"},
        {"index": 2, "grade": "category", "sees": "nearby kind", "reason": "same kind"},
    ],
    "unpunched": [{"beat": "aside", "should_have_punched": False, "reason": "nothing exact"}],
}
print(json.dumps(doc))
'''
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_template_ladder_and_index() -> None:
    bench = load_bench()
    text = bench.render_task_text(
        note="/path/to/NOTE.md",
        style="/path/to/style.json",
        output_dir="/path/to/out/harness-a",
        skill_dir="/path/to/skill",
        mode="proxy",
        harness_id="harness-a",
    )
    low = text.lower()
    assert "punch ladder" in low
    assert "never a same-category picture" in low
    assert "at most two stills" in low
    assert "0.3" in text
    assert "`line`" in text and "`shows`" in text
    assert "broll-search.py" not in text
    with_idx = bench.render_task_text(
        note="/path/to/NOTE.md",
        style="/path/to/style.json",
        output_dir="/path/to/out/harness-a",
        skill_dir="/path/to/skill",
        mode="proxy",
        harness_id="harness-a",
        index="/path/to/index.json",
    )
    assert (
        "broll-search.py --index /path/to/index.json --lines-from-manifest"
        in with_idx
    )
    assert "look at the sheet" in with_idx.lower()


def test_verifier_family_selection() -> None:
    bench = load_bench()
    cfg = {
        "kind": "pi",
        "provider": "openai-codex",
        "model": "gpt-6-astra",
        "thinking": "high",
        "alternate": {
            "kind": "pi",
            "provider": "anthropic",
            "model": "claude-opus-5",
        },
    }
    gpt = bench.choose_verifier(
        {"model": "gpt-6-astra", "provider": "openai-codex"}, cfg
    )
    assert gpt is not None
    assert gpt["model"] == "claude-opus-5"
    grok = bench.choose_verifier({"model": "grok-4.6", "provider": "xai"}, cfg)
    assert grok is not None
    assert grok["model"] == "gpt-6-astra"
    assert grok["provider"] == "openai-codex"


def test_verifier_cmd_grades_and_ranking() -> None:
    ws = make_workspace()
    try:
        exact_id = "exact-pi"
        cat_id = "category-pi"
        _write_fabricated_harness(
            ws["output_root"] / exact_id,
            hid=exact_id,
            punches=[
                {
                    "at_final": 1.0,
                    "dur": 2.0,
                    "kind": "clip",
                    "line": "the named object",
                    "shows": "the named object",
                    "path": "/tmp/a.mp4",
                }
            ],
        )
        _write_fabricated_harness(
            ws["output_root"] / cat_id,
            hid=cat_id,
            punches=[
                {
                    "at_final": 1.0,
                    "dur": 2.5,
                    "kind": "still",
                    "line": "same-kind-hallway",
                    "shows": "a hallway",
                    "path": "/tmp/b.jpg",
                }
            ],
        )
        cfg = base_config(
            ws,
            [
                {
                    "id": exact_id,
                    "kind": "pi",
                    "provider": "xai",
                    "model": "grok-4.6",
                    "thinking": "high",
                },
                {
                    "id": cat_id,
                    "kind": "pi",
                    "provider": "xai",
                    "model": "grok-4.6",
                    "thinking": "high",
                },
            ],
        )
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        stub = ws["root"] / "verifier-stub.py"
        _write_verifier_stub(stub, "rank")
        md = ws["root"] / "bench-report.md"
        html = ws["root"] / "bench-report.html"
        r = run_cli(
            [
                "--config",
                str(cfg_path),
                "--report-only",
                "--verifier-cmd",
                f"{PY} {stub}",
                "--report",
                str(md),
                "--html",
                str(html),
            ]
        )
        assert md.is_file(), r.stdout + r.stderr
        exact_grades = ws["output_root"] / exact_id / "X.grades.json"
        cat_grades = ws["output_root"] / cat_id / "X.grades.json"
        assert exact_grades.is_file(), r.stdout + r.stderr
        assert cat_grades.is_file(), r.stdout + r.stderr
        exact_doc = json.loads(exact_grades.read_text(encoding="utf-8"))
        assert exact_doc["punches"][0]["grade"] == "exact"
        assert exact_doc["punches"][0]["by"] == "verifier"
        assert exact_doc["punches"][0]["index"] == 0
        cat_doc = json.loads(cat_grades.read_text(encoding="utf-8"))
        assert cat_doc["punches"][0]["grade"] == "category"
        assert cat_doc["punches"][0]["by"] == "verifier"
        vjson = ws["output_root"] / exact_id / "verifier.json"
        assert vjson.is_file()
        vrec = json.loads(vjson.read_text(encoding="utf-8"))
        assert "raw" in vrec
        assert "wall_s" in vrec
        report = json.loads(
            md.with_name("bench-report.json").read_text(encoding="utf-8")
        )
        by_id = {row["id"]: row for row in report["table"]}
        assert by_id[exact_id]["exact"] == 1
        assert by_id[exact_id]["category"] == 0
        assert by_id[exact_id]["wrong"] == 0
        assert by_id[exact_id]["unpunched_ok"] == 1
        assert by_id[exact_id]["missed"] == 0
        assert by_id[cat_id]["category"] == 1
        assert by_id[cat_id]["exact"] == 0
        assert by_id[cat_id]["missed"] == 1
        assert report["table"][0]["id"] == exact_id
        assert report["table"][1]["id"] == cat_id
        md_text = md.read_text(encoding="utf-8")
        assert "zero wrong and zero category" in md_text.lower() or "Ranking:" in md_text
        html_text = html.read_text(encoding="utf-8")
        assert "verifier" in html_text.lower()
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def test_owner_grades_agreement() -> None:
    ws = make_workspace()
    try:
        hid = "agree-pi"
        _write_fabricated_harness(
            ws["output_root"] / hid,
            hid=hid,
            punches=[
                {
                    "at_final": 1.0,
                    "dur": 2.0,
                    "kind": "clip",
                    "line": "one",
                    "shows": "one",
                    "path": "/tmp/a.mp4",
                },
                {
                    "at_final": 3.0,
                    "dur": 2.0,
                    "kind": "clip",
                    "line": "two",
                    "shows": "two",
                    "path": "/tmp/b.mp4",
                },
                {
                    "at_final": 5.0,
                    "dur": 2.0,
                    "kind": "still",
                    "line": "three",
                    "shows": "three",
                    "path": "/tmp/c.jpg",
                },
            ],
        )
        cfg = base_config(
            ws,
            [
                {
                    "id": hid,
                    "kind": "pi",
                    "provider": "xai",
                    "model": "grok-4.6",
                    "thinking": "high",
                }
            ],
        )
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        stub = ws["root"] / "verifier-stub.py"
        _write_verifier_stub(stub, "agree")
        owner = {
            hid: {
                "punches": [
                    {"index": 0, "grade": "exact"},
                    {"index": 1, "grade": "exact"},
                    {"index": 2, "grade": "exact"},
                ]
            }
        }
        grades_path = ws["root"] / "owner-grades.json"
        write_json(grades_path, owner)
        md = ws["root"] / "bench-report.md"
        r = run_cli(
            [
                "--config",
                str(cfg_path),
                "--report-only",
                "--verifier-cmd",
                f"{PY} {stub}",
                "--grades",
                str(grades_path),
                "--report",
                str(md),
            ]
        )
        combined = r.stdout + r.stderr
        assert "0.67" in combined or "2/3" in combined, combined
        merged_path = md.with_name("grades-merged.json")
        assert merged_path.is_file(), combined
        merged = json.loads(merged_path.read_text(encoding="utf-8"))
        assert merged["overall"] == 0.67
        assert merged["matched"] == 2
        assert merged["graded"] == 3
        html = md.with_name("bench-report.html")
        html_text = html.read_text(encoding="utf-8")
        assert "owner" in html_text.lower()
        assert "exact" in html_text.lower()
        assert "category" in html_text.lower()
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def test_deliver_to_copies_prefixed_files() -> None:
    ws = make_workspace()
    try:
        hid = "deliver-pi"
        _write_fabricated_harness(
            ws["output_root"] / hid, hid=hid, write_runnotes=True
        )
        dest = ws["root"] / "review"
        cfg = base_config(
            ws,
            [
                {
                    "id": hid,
                    "kind": "pi",
                    "provider": "xai",
                    "model": "grok-4.6",
                    "thinking": "high",
                }
            ],
        )
        cfg["task"]["deliver_to"] = str(dest)
        cfg_path = ws["root"] / "bench.json"
        write_json(cfg_path, cfg)
        md = ws["root"] / "bench-report.md"
        html = ws["root"] / "bench-report.html"
        r = run_cli(
            [
                "--config",
                str(cfg_path),
                "--report-only",
                "--report",
                str(md),
                "--html",
                str(html),
            ]
        )
        assert dest.is_dir(), r.stdout + r.stderr
        names = sorted(p.name for p in dest.iterdir() if p.is_file())
        assert any(n.startswith(hid + "-") and n.endswith(".jpg") for n in names), names
        assert any("RUNNOTES" in n and n.startswith(hid + "-") for n in names), names
        assert any(n.startswith(hid + "-") and n.endswith(".md") for n in names), names
        assert any(n.startswith(hid + "-") and n.endswith(".html") for n in names), names
    finally:
        shutil.rmtree(ws["root"], ignore_errors=True)


def main() -> int:
    tests = [
        test_help_exits_zero,
        test_missing_note_exits_two,
        test_duplicate_ids_exits_two,
        test_template_rendering,
        test_template_ladder_and_index,
        test_adapter_command_construction,
        test_scoring_report_only,
        test_stray_write_detection,
        test_missing_codex_binary_skipped,
        test_verifier_family_selection,
        test_verifier_cmd_grades_and_ranking,
        test_owner_grades_agreement,
        test_deliver_to_copies_prefixed_files,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
            import traceback

            traceback.print_exc()
        else:
            print(f"ok   {fn.__name__}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
