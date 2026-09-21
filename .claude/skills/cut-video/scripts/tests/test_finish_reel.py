#!/usr/bin/env python3
"""Synthetic tests for finish-reel.py WP3 upgrades.

No client names, no real footage. Clips are ffmpeg testsrc2 + sine.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "finish-reel.py"
PYTHON = sys.executable
FONT_CANDIDATES = [
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/System/Library/Fonts/Helvetica.ttc"),
    Path("/Library/Fonts/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]


def load_mod():
    spec = importlib.util.spec_from_file_location("finish_reel", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def find_font() -> Path:
    for p in FONT_CANDIDATES:
        if p.exists():
            return p
    raise SystemExit("no test font found on this machine")


def run_finish(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    cmd = [PYTHON, str(SCRIPT), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def make_clip(path: Path, seconds: float, w: int = 540, h: int = 960, audio: bool = True) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration={seconds}",
    ]
    if audio:
        cmd += [
            "-f", "lavfi", "-i",
            f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
        ]
    else:
        cmd += ["-an"]
    cmd += [
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-t", str(seconds), str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg make_clip failed: {r.stderr[-1000:]}")


def write_words(path: Path, duration: float = 8.0, step: float = 0.4) -> int:
    words = []
    t = 0.0
    i = 0
    while t < duration - 1e-9:
        words.append({
            "word": f"w{i:02d}",
            "start": round(t, 3),
            "end": round(min(duration, t + 0.30), 3),
        })
        t += step
        i += 1
    path.write_text(json.dumps({"segments": [{"words": words}]}), encoding="utf-8")
    return i


def probe_streams(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffprobe failed: {r.stderr}")
    return json.loads(r.stdout)


def image_wh(path: Path) -> tuple[int, int]:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffprobe image failed for {path}: {r.stderr}")
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


def parse_ass_time(s: str) -> float:
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def ass_dialogues(text: str) -> list[tuple[float, float, str]]:
    out = []
    for line in text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        bits = line.split(",", 9)
        out.append((parse_ass_time(bits[1]), parse_ass_time(bits[2]), bits[-1]))
    return out


def ass_style_margins(text: str) -> tuple[int, int, int, int]:
    for line in text.splitlines():
        if line.startswith("Style: Default"):
            parts = line.split(",")
            alignment = int(parts[18])
            margin_l = int(parts[19])
            margin_r = int(parts[20])
            margin_v = int(parts[21])
            return alignment, margin_l, margin_r, margin_v
    raise AssertionError("no Style: Default line")


def ebur128_i(path: Path) -> float:
    r = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
            "-filter:a", "ebur128", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    blob = (r.stderr or "") + (r.stdout or "")
    matches = re.findall(r"I:\s+([-\d.]+)", blob)
    if not matches:
        raise AssertionError(f"no ebur128 I: in ffmpeg output:\n{blob[-1500:]}")
    return float(matches[-1])


def test_help() -> None:
    r = run_finish(["--help"])
    assert r.returncode == 0, r.stderr
    text = r.stdout + r.stderr
    needed = [
        "--loudnorm-mode",
        "--loudnorm-i",
        "--loudnorm-tp",
        "--loudnorm-lra",
        "--denoise",
        "--platforms",
        "--platform-specs",
        "--caption-placement",
        "--caption-margin-v",
        "--caption-margin-side",
        "--caption-style",
        "--caption-min-cue",
        "--caption-max-cue",
        "--caption-max-chars",
        "--caption-max-lines",
        "--proxy",
        "--encoder",
        "--threads",
        "--emit-json",
        "--ass-out",
        "--qa-max-px",
        "--cover-case",
        "--no-loudnorm",
        "--srt-out",
        "--cover-frame",
    ]
    missing = [f for f in needed if f not in text]
    assert not missing, f"help missing flags: {missing}"
    assert "two-pass" in text
    assert "safe-lower" in text


def test_cover_backslash() -> None:
    r = run_finish([
        "--spine", "/tmp/missing-spine.mp4",
        "--output", "/tmp/missing-out.mp4",
        "--cover-text", "BAD\\nTEXT",
    ])
    assert r.returncode == 2, r.stderr + r.stdout
    assert "backslash" in (r.stderr + r.stdout).lower()


def test_group_and_map_unit() -> None:
    fr = load_mod()
    words = [(i * 0.4, i * 0.4 + 0.3, f"w{i:02d}", 0) for i in range(20)]
    phrase = fr.group_caption_cues(
        words, max_chars=32, max_dur=2.8, min_cue=0.8, max_lines=2, style="phrase"
    )
    word = fr.group_caption_cues(
        words, max_chars=32, max_dur=2.8, min_cue=0.35, max_lines=2, style="word"
    )
    assert phrase, "phrase cues empty"
    assert all(e - s >= 0.8 - 1e-6 for s, e, _t in phrase), phrase
    assert len(word) > len(phrase)

    src_words = [(7.9, 8.4, "tail")]
    mapped = fr.map_words_to_output(src_words, None, [(0.0, 8.0)])
    assert len(mapped) == 1, mapped
    assert mapped[0][2] == "tail"
    assert mapped[0][1] <= 8.0 + 1e-6

    br = fr.parse_broll("/tmp/x.mp4:at=2.0:dur=2.0:kind=still")
    assert br["kind"] == "still"
    br2 = fr.parse_broll("/tmp/x.mp4:at=2.0:dur=2.0")
    assert br2["kind"] == "clip"

    tmp = Path(tempfile.mkdtemp(prefix="srt-unit-"))
    try:
        srt = tmp / "cues.srt"
        fr.write_srt(srt, [(0.0, 1.5, "hello\\Nworld"), (1.5, 2.0, "one line")])
        text = srt.read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:01,500" in text
        assert "hello\nworld" in text
        assert "one line" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_loudnorm_off_dry(spine: Path, tmp: Path) -> None:
    out = tmp / "dry.mp4"
    common = [
        "--spine", str(spine),
        "--output", str(out),
        "--skip-lut", "--no-eq",
        "--preset", "ultrafast",
        "--width", "540", "--height", "960",
        "--force", "--dry-run",
    ]
    r = run_finish(common + ["--loudnorm-mode", "off"])
    assert r.returncode == 0, r.stderr
    printed = r.stdout + r.stderr
    assert "loudnorm" not in printed.lower() or "loudnorm-mode" in printed
    # The printed ffmpeg command must not include a loudnorm filter.
    ffmpeg_lines = [ln for ln in printed.splitlines() if "ffmpeg" in ln and "-filter_complex" in ln]
    for ln in ffmpeg_lines:
        assert "loudnorm=" not in ln, ln

    r2 = run_finish(common + ["--no-loudnorm"])
    assert r2.returncode == 0, r2.stderr
    printed2 = r2.stdout + r2.stderr
    ffmpeg_lines2 = [ln for ln in printed2.splitlines() if "ffmpeg" in ln and "-filter_complex" in ln]
    for ln in ffmpeg_lines2:
        assert "loudnorm=" not in ln, ln


def test_main_proxy_render(tmp: Path, font: Path) -> None:
    spine = tmp / "spine.mp4"
    broll = tmp / "broll.mp4"
    hook = tmp / "hook.mp4"
    words = tmp / "words.json"
    out = tmp / "out.mp4"
    ass = tmp / "out.ass"
    timeline = tmp / "timeline.json"
    qa = tmp / "qa"
    make_clip(spine, 8)
    make_clip(broll, 3, audio=False)
    make_clip(hook, 1)
    write_words(words, 8.0, 0.4)

    r = run_finish([
        "--spine", str(spine),
        "--output", str(out),
        "--hook", str(hook),
        "--proxy",
        "--cover-text", "TWO LINE COVER TEXT HERE",
        "--font", str(font),
        "--transcript", str(words),
        "--spine-range", "0:8",
        "--broll", f"{broll}:at=2.0:dur=2.0",
        "--join", "4.0",
        "--emit-json", str(timeline),
        "--ass-out", str(ass),
        "--qa-dir", str(qa),
        "--qa-max-px", "300",
        "--caption-placement", "safe-lower",
        "--platforms", "instagram_reels,tiktok",
        "--skip-lut", "--no-eq",
        "--force",
    ])
    combined = r.stdout + "\n" + r.stderr
    assert r.returncode == 0, combined[-4000:]
    assert out.exists()
    streams = probe_streams(out)
    v = next(s for s in streams["streams"] if s["codec_type"] == "video")
    a = next(s for s in streams["streams"] if s["codec_type"] == "audio")
    assert v["width"] == 540 and v["height"] == 960, v
    assert v["pix_fmt"] in {"yuv420p", "yuvj420p"}, v["pix_fmt"]
    assert v["codec_name"] == "h264"
    assert a["codec_name"] == "aac"
    assert int(a.get("sample_rate", 0)) == 48000

    assert ass.exists(), "ASS file missing"
    ass_text = ass.read_text(encoding="utf-8")
    alignment, _ml, mr, mv = ass_style_margins(ass_text)
    assert alignment == 2, alignment
    # Expected margins come from platform-specs.json (strictest of the two
    # platforms passed above), not from hardcoded numbers that go stale when
    # the specs are re-sourced.
    specs_path = Path(__file__).resolve().parents[2] / "resources" / "platform-specs.json"
    specs = json.loads(specs_path.read_text(encoding="utf-8"))["platforms"]
    exp_bottom = max(specs[p]["safe_zone_px"]["bottom"] for p in ("instagram_reels", "tiktok"))
    exp_right = max(specs[p]["safe_zone_px"]["right"] for p in ("instagram_reels", "tiktok"))
    assert mv >= exp_bottom + 24, (mv, exp_bottom)
    assert mr >= exp_right + 16, (mr, exp_right)
    for s, e, _t in ass_dialogues(ass_text):
        assert e - s >= 0.8 - 1e-6, (s, e)

    data = json.loads(timeline.read_text(encoding="utf-8"))
    assert data["punches"], data
    assert "at_final" in data["punches"][0]
    assert data["joins"], data["joins"]
    assert data["captions"]["count"] > 0
    assert data["loudness"]["mode"] == "two-pass", data["loudness"]
    assert isinstance(data["loudness"]["measured_i"], (int, float))
    srt = tmp / "out.srt"
    cover = tmp / "out.cover.jpg"
    assert srt.is_file(), "SRT sidecar missing"
    assert cover.is_file(), "cover frame missing"
    srt_text = srt.read_text(encoding="utf-8")
    assert "-->" in srt_text
    assert data["captions"].get("srt"), data["captions"]
    assert Path(data["captions"]["srt"]).is_file()
    assert data["cover"].get("frame"), data["cover"]
    assert Path(data["cover"]["frame"]).is_file()
    cw, ch = image_wh(cover)
    assert (cw, ch) == (540, 960), (cw, ch)

    frames = list(qa.glob("*.jpg"))
    assert frames, "no QA frames"
    for f in frames:
        w, h = image_wh(f)
        assert max(w, h) <= 300, (f.name, w, h)

    loud = ebur128_i(out)
    assert abs(loud - (-16.0)) <= 1.5, f"integrated loudness {loud} LUFS"

    # Word style should emit more Dialogue lines than phrase.
    word_ass = tmp / "word.ass"
    word_out = tmp / "word.mp4"
    r2 = run_finish([
        "--spine", str(spine),
        "--output", str(word_out),
        "--proxy",
        "--transcript", str(words),
        "--spine-range", "0:8",
        "--caption-style", "word",
        "--ass-out", str(word_ass),
        "--loudnorm-mode", "off",
        "--skip-lut", "--no-eq",
        "--force",
    ])
    assert r2.returncode == 0, r2.stderr[-2000:]
    word_n = len(ass_dialogues(word_ass.read_text(encoding="utf-8")))
    phrase_n = len(ass_dialogues(ass_text))
    assert word_n > phrase_n, (word_n, phrase_n)


def test_old_style(spine: Path, tmp: Path) -> None:
    out = tmp / "old.mp4"
    r = run_finish([
        "--spine", str(spine),
        "--output", str(out),
        "--width", "540",
        "--height", "960",
        "--preset", "ultrafast",
        "--crf", "28",
        "--skip-lut",
        "--no-eq",
        "--no-loudnorm",
        "--force",
    ])
    assert r.returncode == 0, r.stderr[-2000:]
    assert out.exists()
    streams = probe_streams(out)
    v = next(s for s in streams["streams"] if s["codec_type"] == "video")
    assert v["width"] == 540 and v["height"] == 960


def main() -> int:
    test_help()
    print("ok help")
    test_cover_backslash()
    print("ok cover backslash")
    test_group_and_map_unit()
    print("ok unit grouping")

    tmp = Path(tempfile.mkdtemp(prefix="test-finish-reel-"))
    try:
        font = find_font()
        spine = tmp / "spine_shared.mp4"
        make_clip(spine, 8)
        test_loudnorm_off_dry(spine, tmp)
        print("ok loudnorm off dry-run")
        test_main_proxy_render(tmp, font)
        print("ok proxy render + word style")
        test_old_style(spine, tmp)
        print("ok old-style call")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("all passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
