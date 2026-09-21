#!/usr/bin/env python3
"""Tests for regress.py. Pure functions plus CLI dry-run / renderer-missing.

No pytest required. Run:

    python3 tests/test_regress.py

Synthetic media (when the renderer is present) is 540x960, ultrafast,
sequential encodes, 8s spine + 2s B-roll.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import regress  # noqa: E402

REGRESS = SCRIPTS / "regress.py"
RENDERER = SCRIPTS / "render-reel.py"


def run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REGRESS), *args],
        capture_output=True,
        text=True,
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def write_tiny_fixture(
    root: Path,
    *,
    name: str = "synthetic",
    spine: str = "/path/to/spine.mp4",
    transcript: str = "/path/to/words.json",
    broll: str = "/path/to/broll.mp4",
) -> None:
    """PII-free fixture pair. Paths may be placeholders."""
    write_json(
        root / f"{name}.fixture.json",
        {
            "schema": "reel-fixture/1",
            "name": name,
            "manifest": f"{name}.reel.json",
            "gold": None,
            "expect": {
                "duration_window": [4, 12],
                "punch_count": 1,
                "hook_present": False,
                "cover_text": "synthetic cover",
                "qa_verdict": "pass",
            },
            "notes": "synthetic regress fixture",
        },
    )
    write_json(
        root / f"{name}.reel.json",
        {
            "schema": "reel-manifest/1",
            "id": "XX-20260101-01",
            "slug": "regress-synthetic",
            "version": "auto",
            "output_dir": "/path/to/ignored",
            "duration_window": [4, 12],
            "source": {
                "video": spine,
                "transcript_json": transcript,
                "color": "rec709",
            },
            "spine": {
                "ranges": [
                    {"start": 0.3, "end": 7.5, "quote": "hello ... clip"}
                ]
            },
            "hook": {"mode": "none"},
            "cover": {"text": "synthetic cover", "case": "as-is"},
            "captions": {"enabled": False},
            "broll": [
                {
                    "kind": "clip",
                    "path": broll,
                    "at": 1.0,
                    "dur": 2.0,
                    "line": "hello world",
                }
            ],
            "render": {"mode": "proxy", "preset": "ultrafast"},
        },
    )


def encode_clip(path: Path, seconds: float, size: str = "540x960") -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000",
        "-t",
        str(seconds),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "1",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout or "ffmpeg failed")


def write_word_json(path: Path) -> None:
    write_json(
        path,
        {
            "segments": [
                {
                    "start": 0.0,
                    "end": 8.0,
                    "text": "hello world this is a test clip",
                    "words": [
                        {"word": "hello", "start": 0.4, "end": 0.8},
                        {"word": "world", "start": 0.9, "end": 1.3},
                        {"word": "this", "start": 1.5, "end": 1.8},
                        {"word": "is", "start": 1.9, "end": 2.1},
                        {"word": "a", "start": 2.2, "end": 2.3},
                        {"word": "test", "start": 2.4, "end": 2.8},
                        {"word": "clip", "start": 3.0, "end": 3.5},
                    ],
                }
            ]
        },
    )


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def test_ssim_parser() -> None:
    sample = (
        "n:1 Y:0.900000 U:0.800000 V:0.700000 All:0.850000 (8.239)\n"
        "[Parsed_ssim_0 @ 0x1] SSIM Y:0.91 U:0.81 V:0.71 All:0.861234 (8.54)\n"
    )
    assert regress.parse_ssim_all(sample) == 0.861234
    assert regress.parse_ssim_all("no ssim here") is None
    assert regress.parse_ssim_all("") is None
    inf = "n:1 Y:1.000000 U:1.000000 V:1.000000 All:1.000000 (inf)\n"
    assert regress.parse_ssim_all(inf) == 1.0


def test_expectation_evaluator() -> None:
    ok = regress.evaluate_expectations(
        {
            "duration_window": [4, 12],
            "punch_count": 1,
            "hook_present": False,
            "cover_text": "HELLO",
            "qa_verdict": "pass",
        },
        duration_s=8.0,
        punch_count=1,
        hook_present=False,
        cover_text="HELLO",
        qa_verdict="pass",
    )
    assert ok, ok
    assert all(c["ok"] for c in ok)

    bad = regress.evaluate_expectations(
        {"duration_window": [4, 12], "qa_verdict": "pass", "punch_count": 1},
        duration_s=20.0,
        punch_count=0,
        hook_present=None,
        cover_text=None,
        qa_verdict="fail",
    )
    failed_ids = {c["id"] for c in bad if not c["ok"]}
    assert "duration" in failed_ids
    assert "punch_count" in failed_ids
    assert "qa_verdict" in failed_ids

    # pass >= warn >= fail
    ranked = regress.evaluate_expectations(
        {"qa_verdict": "warn"},
        qa_verdict="pass",
    )
    assert ranked[0]["ok"] is True
    ranked = regress.evaluate_expectations(
        {"qa_verdict": "pass"},
        qa_verdict="warn",
    )
    assert ranked[0]["ok"] is False

    assert regress.apply_cover_case("hello World", "upper") == "HELLO WORLD"
    assert regress.apply_cover_case("HELLO WORLD", "sentence") == "Hello world"
    assert regress.apply_cover_case("Hello World", "as-is") == "Hello World"

    empty = regress.evaluate_expectations({})
    assert empty == []

    gold_ok = regress.evaluate_gold(
        {"duration_s": 8.0, "ssim_min": 0.45},
        duration_s=52.0,
        gold_duration_s=50.5,
        ssim_min_measured=0.62,
    )
    assert all(c["ok"] for c in gold_ok)
    gold_bad = regress.evaluate_gold(
        {"duration_s": 1.0, "ssim_min": 0.90},
        duration_s=52.0,
        gold_duration_s=50.5,
        ssim_min_measured=0.62,
    )
    assert not all(c["ok"] for c in gold_bad)
    advisory = regress.evaluate_gold(
        {},
        duration_s=52.0,
        gold_duration_s=40.0,
        ssim_min_measured=0.1,
    )
    assert advisory == []

    null_floor = regress.evaluate_gold(
        {"ssim_min": None, "duration_s": None},
        duration_s=52.0,
        gold_duration_s=40.0,
        ssim_min_measured=0.12,
    )
    assert null_floor, null_floor
    assert all(c["ok"] for c in null_floor)
    ssim_row = next(c for c in null_floor if c["id"] == "gold_ssim")
    assert "0.1200" in ssim_row["detail"] or "0.12" in ssim_row["detail"]


def test_help_exits_zero() -> None:
    r = run_cli(["--help"])
    assert r.returncode == 0, r.stderr
    text = r.stdout + r.stderr
    assert "--fixtures" in text
    assert "--dry-run" in text
    assert "--allow-qa-fail" in text


def test_dry_run() -> None:
    root = Path(tempfile.mkdtemp(prefix="regress-dry-"))
    try:
        write_tiny_fixture(root, name="synthetic")
        r = run_cli(["--fixtures", str(root), "--dry-run"])
        assert r.returncode == 0, r.stderr
        combined = r.stdout + r.stderr
        assert "synthetic" in combined
        assert "would:" in combined or "manifest=" in combined
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_renderer_missing_or_present() -> None:
    root = Path(tempfile.mkdtemp(prefix="regress-fx-"))
    run_dir = Path(tempfile.mkdtemp(prefix="regress-run-"))
    report = Path(tempfile.mkdtemp(prefix="regress-out-")) / "report.md"
    json_out = report.with_suffix(".json")
    try:
        if RENDERER.is_file():
            media = Path(tempfile.mkdtemp(prefix="regress-media-"))
            spine = media / "spine.mp4"
            broll = media / "broll.mp4"
            words = media / "words.json"
            encode_clip(spine, 8)
            encode_clip(broll, 2)
            write_word_json(words)
            write_tiny_fixture(
                root,
                name="synthetic",
                spine=str(spine),
                transcript=str(words),
                broll=str(broll),
            )
            r = run_cli(
                [
                    "--fixtures",
                    str(root),
                    "--run-dir",
                    str(run_dir),
                    "--proxy",
                    "--report",
                    str(report),
                    "--json",
                    str(json_out),
                    "--timeout-min",
                    "2",
                ]
            )
            assert r.returncode in (0, 3), r.stderr + r.stdout
            assert json_out.is_file(), r.stdout + r.stderr
            data = json.loads(json_out.read_text(encoding="utf-8"))
            assert len(data["fixtures"]) == 1
            assert report.is_file()
            md = report.read_text(encoding="utf-8")
            assert "synthetic" in md
            if data.get("ok"):
                assert r.returncode == 0
            else:
                assert r.returncode == 3
            shutil.rmtree(media, ignore_errors=True)
        else:
            write_tiny_fixture(root, name="synthetic")
            r = run_cli(["--fixtures", str(root), "--run-dir", str(run_dir)])
            assert r.returncode == 2, r.stderr + r.stdout
            combined = (r.stderr + r.stdout).lower()
            assert "renderer missing" in combined
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(report.parent, ignore_errors=True)


def test_finish_timeline_punch_count() -> None:
    root = Path(tempfile.mkdtemp(prefix="regress-tl-"))
    run_dir = Path(tempfile.mkdtemp(prefix="regress-tl-run-"))
    json_out = Path(tempfile.mkdtemp(prefix="regress-tl-out-")) / "out.json"
    try:
        write_tiny_fixture(root, name="synthetic")
        fx_dir = run_dir / "synthetic"
        fx_dir.mkdir(parents=True, exist_ok=True)
        video = fx_dir / "out.mp4"
        encode_clip(video, 5)
        spine = video.with_name(video.stem + ".timeline.json")
        write_json(
            spine,
            {
                "coarse_ranges": [{"start": 0, "end": 5}],
                "segments": [],
                "duration_s": 5.0,
            },
        )
        finish = Path(str(video) + ".timeline.json")
        write_json(
            finish,
            {
                "hook": {"present": False, "duration_s": 0},
                "punches": [
                    {"at_final": 1.0, "dur": 2.0, "kind": "clip"},
                ],
                "joins": [],
                "captions": {"count": 0},
            },
        )
        desc = json.loads((root / "synthetic.fixture.json").read_text())
        desc["expect"] = {"punch_count": 1, "hook_present": False}
        write_json(root / "synthetic.fixture.json", desc)
        r = run_cli(
            [
                "--fixtures", str(root),
                "--run-dir", str(run_dir),
                "--skip-render",
                "--json", str(json_out),
            ]
        )
        assert json_out.is_file(), r.stdout + r.stderr
        data = json.loads(json_out.read_text(encoding="utf-8"))
        rec = data["fixtures"][0]
        assert rec["punches"] == 1, rec
        punch_checks = [c for c in rec["checks"] if c["id"] == "punch_count"]
        assert punch_checks and punch_checks[0]["ok"], rec["checks"]
        assert rec["result"] == "PASS", rec
        assert r.returncode == 0, r.stderr + r.stdout
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(json_out.parent, ignore_errors=True)


def test_allow_qa_fail_bitrate() -> None:
    root = Path(tempfile.mkdtemp(prefix="regress-allow-"))
    run_dir = Path(tempfile.mkdtemp(prefix="regress-allow-run-"))
    json_out = Path(tempfile.mkdtemp(prefix="regress-allow-out-")) / "out.json"
    json_out2 = json_out.with_name("out2.json")
    try:
        write_tiny_fixture(root, name="synthetic")
        desc = json.loads((root / "synthetic.fixture.json").read_text())
        desc["expect"] = {"qa_verdict": "pass"}
        write_json(root / "synthetic.fixture.json", desc)
        fx_dir = run_dir / "synthetic"
        fx_dir.mkdir(parents=True, exist_ok=True)
        video = fx_dir / "out.mp4"
        encode_clip(video, 5)
        write_json(
            fx_dir / "out.qa.json",
            {
                "verdict": "fail",
                "proxy": True,
                "fails": ["container.bitrate"],
                "checks": [
                    {
                        "id": "container.bitrate",
                        "status": "fail",
                        "measured": 800,
                        "expected": ">=6000 kbps",
                        "detail": "video bitrate is below the delivery minimum",
                    }
                ],
            },
        )
        r_fail = run_cli(
            [
                "--fixtures", str(root),
                "--run-dir", str(run_dir),
                "--skip-render",
                "--json", str(json_out),
            ]
        )
        assert r_fail.returncode == 3, r_fail.stderr + r_fail.stdout
        r_pass = run_cli(
            [
                "--fixtures", str(root),
                "--run-dir", str(run_dir),
                "--skip-render",
                "--allow-qa-fail", "container.bitrate",
                "--json", str(json_out2),
            ]
        )
        assert json_out2.is_file(), r_pass.stdout + r_pass.stderr
        data = json.loads(json_out2.read_text(encoding="utf-8"))
        rec = data["fixtures"][0]
        assert rec["result"] == "PASS", rec
        assert r_pass.returncode == 0, r_pass.stderr + r_pass.stdout
        assert rec.get("note") and "container.bitrate" in rec["note"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(json_out.parent, ignore_errors=True)


def main() -> int:
    tests = [
        test_ssim_parser,
        test_expectation_evaluator,
        test_help_exits_zero,
        test_dry_run,
        test_finish_timeline_punch_count,
        test_allow_qa_fail_bitrate,
        test_renderer_missing_or_present,
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
