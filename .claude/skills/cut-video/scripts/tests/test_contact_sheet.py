#!/usr/bin/env python3
"""Tests for contact-sheet.py. Synthetic stills only. No live footage."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parent.parent
SHEET = SCRIPTS / "contact-sheet.py"


def run_sheet(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SHEET), *args],
        capture_output=True,
        text=True,
    )


def test_help_exits_zero() -> None:
    r = run_sheet(["--help"])
    assert r.returncode == 0, r.stderr
    assert "--out" in r.stdout
    assert "--output" in r.stdout
    assert "--frames" in r.stdout
    assert "--columns" in r.stdout
    assert "--dry-run" in r.stdout


def test_no_frames_exits_two() -> None:
    r = run_sheet(["--out", "/tmp/no-such-sheet.jpg"])
    assert r.returncode == 2
    assert "ERROR" in r.stderr


def test_dry_run_exits_zero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        frame = tmp_p / "a.jpg"
        Image.new("RGB", (80, 140), (40, 80, 120)).save(frame, format="JPEG")
        out = tmp_p / "sheet.jpg"
        r = run_sheet(["--out", str(out), "--frames", str(frame), "--dry-run"])
        assert r.returncode == 0, r.stderr
        assert not out.exists()


def test_sheet_from_stills_size() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        frames = []
        labels = []
        colors = [
            (200, 40, 40),
            (40, 200, 40),
            (40, 40, 200),
            (200, 200, 40),
            (40, 200, 200),
            (200, 40, 200),
        ]
        for i, color in enumerate(colors):
            path = tmp_p / f"f{i}.jpg"
            Image.new("RGB", (120, 200), color).save(path, format="JPEG", quality=85)
            frames.append(str(path))
            labels.append(f"t={i}.0s tile{i}")
        out = tmp_p / "sheet.jpg"
        r = run_sheet(
            [
                "--out", str(out),
                "--frames", ",".join(frames),
                "--labels", ",".join(labels),
                "--cols", "4",
                "--tile-width", "400",
                "--quality", "85",
            ]
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert out.exists()
        with Image.open(out) as im:
            w, h = im.size
        assert w <= 1600, w
        assert h > 28
        assert str(out) in r.stdout
        assert f"{w}x{h}" in r.stdout


def test_missing_frame_exits_two() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sheet.jpg"
        r = run_sheet(["--out", str(out), "--frames", str(Path(tmp) / "missing.jpg")])
        assert r.returncode == 2
        assert "not found" in r.stderr


def _two_stills(tmp_p: Path) -> tuple[Path, Path]:
    a = tmp_p / "a.jpg"
    b = tmp_p / "b.jpg"
    Image.new("RGB", (80, 140), (200, 40, 40)).save(a, format="JPEG")
    Image.new("RGB", (80, 140), (40, 200, 40)).save(b, format="JPEG")
    return a, b


def test_nargs_frames_and_hash_labels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        a, b = _two_stills(tmp_p)
        out = tmp_p / "sheet-nargs.jpg"
        r = run_sheet(
            [
                "--out", str(out),
                "--frames", str(a), str(b),
                "--labels", "#1 x", "#2 y",
            ]
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert out.exists()


def test_comma_joined_frames_and_labels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        a, b = _two_stills(tmp_p)
        out = tmp_p / "sheet-csv.jpg"
        r = run_sheet(
            [
                "--out", str(out),
                "--frames", f"{a},{b}",
                "--labels", "#1 x,#2 y",
            ]
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert out.exists()


def test_output_columns_aliases() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        a, b = _two_stills(tmp_p)
        out = tmp_p / "sheet-alias.jpg"
        r = run_sheet(
            [
                "--output", str(out),
                "--frames", str(a), str(b),
                "--labels", "#1 x", "#2 y",
                "--columns", "2",
            ]
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert out.exists()
        with Image.open(out) as im:
            assert im.size[0] <= 1600


def test_label_count_pads_basename() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        a, b = _two_stills(tmp_p)
        out = tmp_p / "sheet-pad.jpg"
        r = run_sheet(
            [
                "--out", str(out),
                "--frames", str(a), str(b),
                "--labels", "only-one",
            ]
        )
        assert r.returncode == 0, r.stderr + r.stdout
        assert "notice" in r.stderr.lower()
        assert out.exists()


def main() -> int:
    tests = [
        test_help_exits_zero,
        test_no_frames_exits_two,
        test_dry_run_exits_zero,
        test_sheet_from_stills_size,
        test_missing_frame_exits_two,
        test_nargs_frames_and_hash_labels,
        test_comma_joined_frames_and_labels,
        test_output_columns_aliases,
        test_label_count_pads_basename,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"ok  {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        print(f"{failed} failed")
        return 1
    print("all passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
