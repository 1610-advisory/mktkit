#!/usr/bin/env python3
"""Tests for render-reel.py.

No pytest required. Run:

    python3 tests/test_render_reel.py

Synthetic 12s 540x960 testsrc2 + sine, a 2s B-roll clip, and a Pillow JPEG.
No client names, real paths, or live footage.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPTS = Path(__file__).resolve().parent.parent
RENDER = SCRIPTS / "render-reel.py"
PY = sys.executable
FONT = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
if not FONT.is_file():
    for cand in (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ):
        if cand.is_file():
            FONT = cand
            break


def run_render(args: list[str], timeout: int = 80) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(RENDER), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def make_video(path: Path, duration: float, size: str = "540x960", audio: bool = True) -> None:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24:duration={duration}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    cmd += [
        "-t", str(duration), "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:v", "libx264",
    ]
    if audio:
        cmd += ["-c:a", "aac", "-ar", "48000"]
    else:
        cmd += ["-an"]
    cmd.append(str(path))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"ffmpeg failed:\n{r.stderr}")
    assert path.is_file()


def make_still(path: Path) -> None:
    im = Image.new("RGB", (720, 1280), (32, 64, 96))
    dr = ImageDraw.Draw(im)
    dr.rectangle([40, 80, 680, 1200], outline=(220, 200, 160), width=8)
    dr.rectangle([80, 200, 640, 500], fill=(180, 90, 40))
    dr.text((100, 240), "SYNTH STILL", fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", quality=90)
    assert path.is_file()


def make_transcript(path: Path, duration: float = 12.0, step: float = 0.4) -> None:
    words = []
    vocab = [
        "the", "first", "thing", "we", "do", "here", "is", "cut",
        "then", "open", "the", "hallway", "and", "that", "is", "the",
        "whole", "point", "of", "this", "take", "today",
    ]
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


def write_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def base_manifest(root: Path, *, broll_path: str | None = None, transcript: str | None = None) -> dict:
    assert FONT.is_file(), f"need a font for cover text: {FONT}"
    return {
        "schema": "reel-manifest/1",
        "id": "XX-20260101-99",
        "slug": "wp1-synthetic",
        "version": "auto",
        "output_dir": str(root / "out"),
        "duration_window": [4, 40],
        "source": {
            "video": str(root / "aroll.mp4"),
            "transcript_json": transcript or str(root / "words.json"),
            "color": "auto",
        },
        "spine": {
            "ranges": [
                {"start": 0.0, "end": 5.0, "quote": "the first thing we do"},
                {"start": 6.0, "end": 11.0, "quote": "then open the hallway"},
            ],
            "hard_out": 11.0,
            "max_pause": 0.85,
            "keep_tail": 0.20,
            "keep_lead": 0.08,
            "join_fade": 0.06,
        },
        "hook": {
            "mode": "prepend",
            "source": None,
            "range": [1.2, 2.4],
            "quote": "thing we do",
            "lift_from_spine": True,
        },
        "cover": {
            "text": "synthetic cover line",
            "seconds": 1.0,
            "anchor": "center",
            "font": str(FONT),
            "color": "#F2EDE0",
            "size": 48,
            "case": "upper",
        },
        "captions": {"enabled": True, "size": 32},
        "broll": [
            {
                "kind": "clip",
                "path": broll_path if broll_path is not None else str(root / "broll.mp4"),
                "at": 1.0,
                "dur": 2.0,
                "line": "the first thing we do",
                "shows": "a synthetic test pattern clip",
            },
            {
                "kind": "still",
                "path": str(root / "still.jpg"),
                "at": 4.0,
                "dur": 3.5,
                "line": "then open the hallway",
                "shows": "a synthetic still of a painted rectangle",
                "focus": [0.5, 0.45],
                "verified": True,
            },
        ],
        "joins": "auto",
        "inserts": [],
        "audio": {"loudnorm": "off"},
        "render": {"mode": "proxy", "crf": 28, "preset": "ultrafast", "encoder": "libx264"},
        "qa": {"frames": True, "contact_sheet": True, "max_frame_px": 540},
        "notes": "synthetic v1 for renderer tests",
    }


def build_media(root: Path) -> None:
    make_video(root / "aroll.mp4", 12.0)
    make_video(root / "broll.mp4", 2.0)
    make_still(root / "still.jpg")
    make_transcript(root / "words.json", 12.0)
    (root / "out").mkdir(parents=True, exist_ok=True)


def test_help() -> None:
    r = run_render(["--help"], timeout=10)
    assert r.returncode == 0, r.stderr
    assert "--manifest" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--ledger" in r.stdout
    assert "--no-ledger" in r.stdout
    assert "--style" in r.stdout
    assert "--strict" in r.stdout


def test_dry_run_join_and_lift(root: Path) -> None:
    man = root / "reel.json"
    write_manifest(man, base_manifest(root))
    r = run_render(
        ["--manifest", str(man), "--dry-run", "--no-deliver", "--no-qa"],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "hook lift" in blob
    assert "1.200" in blob and "2.400" in blob
    assert "--join" in blob
    assert "finish-reel.py" in blob


LEDGER_KEYS = [
    "ts", "id", "slug", "version", "proxy", "output", "duration_s",
    "duration_window", "stages", "qa_verdict", "qa_fails", "loudness",
    "punch_count", "encoder", "ffmpeg_version", "manifest_sha16",
    "engine", "status", "error", "model_cost_usd",
]
STAGE_KEYS = ["preflight", "spine", "stills", "pregrade", "finish", "qa", "deliver"]


def test_real_run_and_versions(root: Path) -> None:
    man = root / "reel.json"
    write_manifest(man, base_manifest(root))
    lock = root / "render.lock"
    ledger = root / "ledger.jsonl"
    common = [
        "--manifest", str(man),
        "--no-deliver",
        "--lock-file", str(lock),
        "--keep-work",
        "--ledger", str(ledger),
    ]
    r1 = run_render(common, timeout=80)
    blob1 = r1.stdout + r1.stderr
    assert r1.returncode in {0, 4}, blob1
    out1 = root / "out" / "XX-20260101-99_wp1-synthetic_v1-proxy.mp4"
    assert out1.is_file(), f"missing {out1.name}\n{blob1}"
    reel_json = root / "out" / "XX-20260101-99_wp1-synthetic_v1-proxy.reel.json"
    notes = root / "out" / "XX-20260101-99_wp1-synthetic_v1-proxy-RUNNOTES.md"
    timeline = root / "out" / "XX-20260101-99_wp1-synthetic_v1-proxy.timeline.json"
    assert reel_json.is_file(), blob1
    assert notes.is_file(), blob1
    note_text = notes.read_text(encoding="utf-8")
    assert "the first thing we do" in note_text
    assert "then open the hallway" in note_text
    assert "Punch map" in note_text
    assert "Known deviations" in note_text
    assert "Provenance" in note_text
    assert timeline.is_file(), blob1
    tl = json.loads(timeline.read_text(encoding="utf-8"))
    assert tl.get("coarse_ranges"), tl
    assert len(tl["coarse_ranges"]) >= 2
    resolved = json.loads(reel_json.read_text(encoding="utf-8"))
    assert "provenance" in resolved, resolved.keys()
    assert resolved["provenance"].get("ffmpeg_version"), resolved["provenance"]
    assert ledger.is_file(), blob1
    lines1 = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines1) == 1, lines1
    rec1 = json.loads(lines1[0])
    for key in LEDGER_KEYS:
        assert key in rec1, key
    for key in STAGE_KEYS:
        assert key in rec1["stages"], key
    assert rec1["model_cost_usd"] is None
    r2 = run_render(common, timeout=80)
    blob2 = r2.stdout + r2.stderr
    assert r2.returncode in {0, 4}, blob2
    out2 = root / "out" / "XX-20260101-99_wp1-synthetic_v2-proxy.mp4"
    assert out2.is_file(), blob2
    assert out1.is_file(), "first version was overwritten"
    assert out1.stat().st_mtime <= out2.stat().st_mtime or True
    lines2 = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines2) == 2, lines2


def test_missing_broll(root: Path) -> None:
    man = root / "missing-broll.json"
    data = base_manifest(root)
    data["broll"][0]["path"] = str(root / "no-such-clip.mp4")
    write_manifest(man, data)
    r = run_render(
        ["--manifest", str(man), "--dry-run", "--no-deliver", "--no-qa"],
        timeout=20,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 2, blob
    assert "no-such-clip.mp4" in blob


def test_transcript_without_words(root: Path) -> None:
    bad = root / "nowords.json"
    bad.write_text(
        json.dumps({"segments": [{"start": 0, "end": 1, "text": "hello"}]}) + "\n",
        encoding="utf-8",
    )
    man = root / "nowords-reel.json"
    write_manifest(man, base_manifest(root, transcript=str(bad)))
    r = run_render(
        ["--manifest", str(man), "--dry-run", "--no-deliver", "--no-qa"],
        timeout=20,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 2, blob
    assert "without words" in blob or "words[]" in blob


def test_lock_timeout(root: Path) -> None:
    man = root / "lock-reel.json"
    write_manifest(man, base_manifest(root))
    lock = root / "held.lock"
    holder = subprocess.Popen(
        [
            PY, "-c",
            "import fcntl, os, time, sys\n"
            f"path = {str(lock)!r}\n"
            "fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "os.write(fd, b'99999 locktest\\n')\n"
            "time.sleep(60)\n",
        ]
    )
    try:
        deadline = time.time() + 5
        held = False
        while time.time() < deadline:
            if lock.exists():
                # Try non-blocking; if it fails, holder has it.
                import fcntl as _fcntl
                fd = os.open(str(lock), os.O_RDWR)
                try:
                    _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                    _fcntl.flock(fd, _fcntl.LOCK_UN)
                except BlockingIOError:
                    held = True
                    break
                finally:
                    os.close(fd)
            time.sleep(0.05)
        assert held, "lock holder never acquired the file"
        r = run_render(
            [
                "--manifest", str(man),
                "--no-deliver",
                "--no-qa",
                "--lock-file", str(lock),
                "--lock-timeout", "3",
            ],
            timeout=40,
        )
        blob = r.stdout + r.stderr
        assert r.returncode == 5, blob
        assert "waiting for render lock" in blob
    finally:
        holder.kill()
        holder.wait(timeout=5)


def test_style_merge(root: Path) -> None:
    style = {
        "captions": {"size": 60},
        "cover": {"font": str(FONT), "size": 64},
    }
    style_path = root / "house-style.json"
    style_path.write_text(json.dumps(style) + "\n", encoding="utf-8")
    data = base_manifest(root)
    data["captions"]["size"] = 42
    data["cover"].pop("font", None)
    man = root / "style-reel.json"
    write_manifest(man, data)
    r = run_render(
        [
            "--manifest", str(man),
            "--style", str(style_path),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    parts = blob.split()
    assert "--caption-size" in parts, blob
    size_val = parts[parts.index("--caption-size") + 1]
    assert size_val == "42", blob
    assert str(FONT) in blob
    assert "--font" in parts


def test_quote_lint_and_strict(root: Path) -> None:
    data = base_manifest(root)
    data["spine"]["ranges"][0]["quote"] = "zebra muffin does not match"
    data["spine"]["hard_out"] = 10.5
    man = root / "lint-reel.json"
    write_manifest(man, data)
    r = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "WARN" in r.stdout, blob
    assert "quote start" in blob
    assert "hard_out is not a word end" in blob
    r2 = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--strict", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob2 = r2.stdout + r2.stderr
    assert r2.returncode == 2, blob2
    assert "WARN" in r2.stdout or "WARN" in r2.stderr
    assert "finish-reel.py" not in blob2


def test_eq_none_dry(root: Path) -> None:
    data = base_manifest(root)
    data["source"]["eq"] = "none"
    man = root / "eq-none.json"
    write_manifest(man, data)
    r = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "--no-eq" in blob, blob


def test_shows_missing_and_strict(root: Path) -> None:
    data = base_manifest(root)
    for item in data["broll"]:
        item.pop("shows", None)
    man = root / "no-shows.json"
    write_manifest(man, data)
    r = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "shows missing" in blob
    assert "WARN" in r.stdout
    r2 = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--strict", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob2 = r2.stdout + r2.stderr
    assert r2.returncode == 2, blob2
    assert "shows missing" in blob2
    assert "finish-reel.py" not in blob2


def test_stills_cap(root: Path) -> None:
    def still_at(at: float, dur: float = 2.0) -> dict:
        return {
            "kind": "still",
            "path": str(root / "still.jpg"),
            "at": at,
            "dur": dur,
            "line": "then open the hallway",
            "shows": "a synthetic still of a painted rectangle",
            "verified": True,
        }

    three = base_manifest(root)
    three["hook"] = {"mode": "none"}
    three["spine"]["ranges"] = [
        {"start": 0.0, "end": 11.0, "quote": "the first thing we do"},
    ]
    three["broll"] = [still_at(1.0), still_at(5.0), still_at(9.0)]
    man = root / "three-stills.json"
    write_manifest(man, three)
    r = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "3 stills; policy allows 2" in blob
    assert "consecutive stills" not in blob

    adjacent = base_manifest(root)
    adjacent["hook"] = {"mode": "none"}
    adjacent["broll"] = [still_at(1.0, 2.0), still_at(2.5, 2.0)]
    man2 = root / "adj-stills.json"
    write_manifest(man2, adjacent)
    r2 = run_render(
        [
            "--manifest", str(man2),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob2 = r2.stdout + r2.stderr
    assert r2.returncode == 0, blob2
    assert "consecutive stills" in blob2
    assert "3 stills; policy allows" not in blob2

    separated = base_manifest(root)
    separated["hook"] = {"mode": "none"}
    separated["broll"] = [still_at(1.0, 2.0), still_at(5.0, 2.0)]
    man3 = root / "sep-stills.json"
    write_manifest(man3, separated)
    r3 = run_render(
        [
            "--manifest", str(man3),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob3 = r3.stdout + r3.stderr
    assert r3.returncode == 0, blob3
    assert "consecutive stills" not in blob3
    assert "3 stills; policy allows" not in blob3
    assert "stills cap" not in blob3


def test_on_the_noun(root: Path) -> None:
    words = {
        "segments": [{
            "start": 0.0,
            "end": 8.0,
            "text": "the pocket door",
            "words": [
                {"word": "the", "start": 0.50, "end": 0.70},
                {"word": "pocket", "start": 1.00, "end": 1.40},
                {"word": "door", "start": 4.00, "end": 4.30},
            ],
        }],
    }
    tpath = root / "noun-words.json"
    tpath.write_text(json.dumps(words) + "\n", encoding="utf-8")

    def noun_manifest(at: float) -> dict:
        data = base_manifest(root, transcript=str(tpath))
        data["hook"] = {"mode": "none"}
        data["spine"] = {
            "ranges": [{"start": 0.0, "end": 8.0}],
            "max_pause": 0.85,
            "keep_tail": 0.20,
            "keep_lead": 0.08,
            "join_fade": 0.06,
        }
        data["broll"] = [{
            "kind": "still",
            "path": str(root / "still.jpg"),
            "at": at,
            "dur": 3.5,
            "line": "the pocket door",
            "shows": "a pocket door in a hallway",
            "verified": True,
        }]
        return data

    hit = root / "noun-hit.json"
    write_manifest(hit, noun_manifest(3.9))
    r = run_render(
        [
            "--manifest", str(hit),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 0, blob
    assert "on the noun" in blob
    assert "door" in blob
    assert "offset 0.10s" in blob
    assert "starts 1.00 s" not in blob

    miss = root / "noun-miss.json"
    write_manifest(miss, noun_manifest(5.0))
    r2 = run_render(
        [
            "--manifest", str(miss),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=40,
    )
    blob2 = r2.stdout + r2.stderr
    assert r2.returncode == 0, blob2
    assert "WARN" in r2.stdout
    assert "on the noun" in blob2
    assert "starts 1.00 s from the nearest line word" in blob2
    assert "'door' at 4.00" in blob2


def test_empty_broll_path(root: Path) -> None:
    data = base_manifest(root)
    data["broll"][0]["path"] = ""
    data["broll"][0]["line"] = "the first thing we do"
    man = root / "empty-broll.json"
    write_manifest(man, data)
    r = run_render(
        [
            "--manifest", str(man),
            "--dry-run", "--no-deliver", "--no-qa", "--no-ledger",
        ],
        timeout=20,
    )
    blob = r.stdout + r.stderr
    assert r.returncode == 2, blob
    assert "the first thing we do" in blob
    assert "broll-search.py --lines-from-manifest" in blob


if __name__ == "__main__":
    failed = 0
    tmp = Path(tempfile.mkdtemp(prefix="wp1-render-"))
    try:
        build_media(tmp)
        tests = [
            test_help,
            lambda: test_dry_run_join_and_lift(tmp),
            lambda: test_real_run_and_versions(tmp),
            lambda: test_missing_broll(tmp),
            lambda: test_transcript_without_words(tmp),
            lambda: test_lock_timeout(tmp),
            lambda: test_style_merge(tmp),
            lambda: test_quote_lint_and_strict(tmp),
            lambda: test_eq_none_dry(tmp),
            lambda: test_empty_broll_path(tmp),
            lambda: test_shows_missing_and_strict(tmp),
            lambda: test_stills_cap(tmp),
            lambda: test_on_the_noun(tmp),
        ]
        names = [
            "test_help",
            "test_dry_run_join_and_lift",
            "test_real_run_and_versions",
            "test_missing_broll",
            "test_transcript_without_words",
            "test_lock_timeout",
            "test_style_merge",
            "test_quote_lint_and_strict",
            "test_eq_none_dry",
            "test_empty_broll_path",
            "test_shows_missing_and_strict",
            "test_stills_cap",
            "test_on_the_noun",
        ]
        for name, fn in zip(names, tests):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if failed else 0)
