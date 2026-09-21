#!/usr/bin/env python3
"""Tests for cut-video.py --emit-json.

No pytest required. Run:

    python3 tests/test_cut_video_emit_json.py

Synthetic 5s 540x960 testsrc2 + sine. No client names or real footage.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent.parent
CUT_VIDEO = SCRIPTS / "cut-video.py"
PY = sys.executable


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [PY, str(CUT_VIDEO), *args],
        capture_output=True,
        text=True,
    )
    if check and r.returncode != 0:
        raise AssertionError(
            f"cut-video.py exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


def make_video(path: Path, duration: float = 5.0) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=540x960:rate=24:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-t", str(duration),
        "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:v", "libx264", "-c:a", "aac", "-ar", "48000",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"ffmpeg failed:\n{r.stderr}")
    assert path.is_file()


def make_transcript(path: Path, duration: float = 5.0, step: float = 0.4) -> None:
    words = []
    vocab = ["the", "quick", "brown", "fox", "um", "jumps", "over"]
    t = 0.0
    i = 0
    while t < duration - 0.3:
        tok = vocab[i % len(vocab)]
        words.append({"word": tok, "start": round(t, 3), "end": round(t + 0.28, 3)})
        t += step
        i += 1
    payload = {
        "segments": [{
            "start": 0.0,
            "end": duration,
            "text": " ".join(w["word"] for w in words),
            "words": words,
        }]
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def assert_timeline(data: dict, source: Path) -> None:
    for key in ("source", "coarse_ranges", "segments", "removed_fillers", "duration_s", "params"):
        assert key in data, f"missing {key}"
    assert Path(data["source"]).name == source.name
    assert data["coarse_ranges"], "coarse_ranges empty"
    for cr in data["coarse_ranges"]:
        for k in ("start", "end", "out_start", "out_end"):
            assert k in cr, f"coarse missing {k}"
        assert cr["end"] > cr["start"]
        assert cr["out_end"] >= cr["out_start"]
    assert data["segments"], "segments empty"
    for seg in data["segments"]:
        for k in ("src_start", "src_end", "out_start", "out_end", "kind"):
            assert k in seg, f"segment missing {k}"
        assert seg["kind"] in {"speech", "pause", "lead", "tail"}
    last = data["segments"][-1]["out_end"]
    assert abs(float(data["duration_s"]) - last) < 1e-6
    assert isinstance(data["removed_fillers"], list)
    ums = [f for f in data["removed_fillers"] if "um" in str(f.get("word", "")).lower()]
    assert ums, "expected removed filler 'um'"
    params = data["params"]
    assert params["filler_removal"] is True
    assert params["pause_compression"] is True


def test_help() -> None:
    r = run(["--help"])
    assert r.returncode == 0
    assert "--emit-json" in r.stdout


def test_emit_json_dry_and_real() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cut-emit-"))
    try:
        src = tmp / "src.mp4"
        js = tmp / "words.json"
        out = tmp / "spine.mp4"
        side = tmp / "spine.timeline.json"
        make_video(src, 5.0)
        make_transcript(js, 5.0)
        common = [
            "--source", str(src),
            "--json", str(js),
            "--output", str(out),
            "--range", "0.4:2.2",
            "--range", "2.8:4.6",
            "--max-pause", "0.85",
            "--keep-tail", "0.20",
            "--keep-lead", "0.08",
            "--join-fade", "0.06",
            "--preset", "ultrafast",
            "--crf", "28",
            "--emit-json", str(side),
        ]
        r = run([*common, "--dry-run"])
        assert r.returncode == 0
        assert side.is_file(), "dry-run should still write --emit-json"
        data = json.loads(side.read_text(encoding="utf-8"))
        assert_timeline(data, src)
        assert not out.exists(), "dry-run must not write media"
        side.unlink()
        r = run(common)
        assert r.returncode == 0
        assert out.is_file()
        assert side.is_file()
        data2 = json.loads(side.read_text(encoding="utf-8"))
        assert_timeline(data2, src)
        assert abs(data2["duration_s"] - data["duration_s"]) < 1e-6
        assert len(data2["coarse_ranges"]) == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    tests = [test_help, test_emit_json_dry_and_real]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    sys.exit(1 if failed else 0)
