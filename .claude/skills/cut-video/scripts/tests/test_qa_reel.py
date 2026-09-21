#!/usr/bin/env python3
"""Tests for qa-reel.py. Synthetic ffmpeg sources only. No live footage."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parent.parent
QA = SCRIPTS / "qa-reel.py"

ALL_IDS = {
    "container.resolution",
    "container.pix_fmt",
    "container.video_codec",
    "container.audio_codec",
    "container.sample_rate",
    "container.fps",
    "container.faststart",
    "container.bitrate",
    "duration.window",
    "duration.platform_max",
    "audio.integrated_loudness",
    "audio.true_peak",
    "audio.lra",
    "audio.silence_gaps",
    "audio.clipping",
    "audio.tail",
    "video.black_frames",
    "video.frozen_frames",
    "video.orientation_sanity",
    "video.static_gap",
    "video.join_uncovered",
    "video.grade_mismatch",
    "captions.safe_zone",
    "captions.timing",
    "text.cover_words",
    "text.banned_words",
    "hook.once",
    "broll.verified",
    "broll.durations",
    "broll.density",
    "broll.stills_cap",
    "broll.consecutive_stills",
    "broll.shows_missing",
    "broll.exactness",
}

VERDICT_RE = re.compile(r"^qa-reel: (pass|warn|fail) \(\d+ fail, \d+ warn\) .+")


def run_ffmpeg(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + (r.stderr or r.stdout or "")[-2000:])


def run_qa(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(QA), *args],
        capture_output=True,
        text=True,
    )


def status_of(report: dict, cid: str) -> str:
    for row in report["checks"]:
        if row["id"] == cid:
            return row["status"]
    raise AssertionError(f"missing check {cid}")


def write_ass(path: Path, margin_v: int) -> None:
    path.write_text(
        "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                "PlayResX: 1080",
                "PlayResY: 1920",
                "",
                "[V4+ Styles]",
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding",
                "Style: Default,Arial,42,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
                f"0,0,0,0,100,100,0,0,1,2,0,2,80,200,{margin_v},1",
                "",
                "[Events]",
                "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
                "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,this is the opening hook line here",
                "Dialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,and then we keep talking on",
                "",
            ]
        ),
        encoding="utf-8",
    )


def make_good(path: Path) -> None:
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=10",
            "-filter_complex", "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000",
            "-movflags", "+faststart",
            "-t", "10",
            str(path),
        ]
    )


def make_bad(path: Path, work: Path) -> None:
    video = work / "bad_v.mp4"
    audio = work / "bad_a.m4a"
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=size=1080x1080:rate=30:duration=10",
            "-f", "lavfi", "-i", "color=c=black:s=1080x1080:d=10:r=30",
            "-filter_complex", "[0:v][1:v]overlay=enable='between(t,3,4)'[v]",
            "-map", "[v]",
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            str(video),
        ]
    )
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=8.5",
            "-c:a", "aac", "-ar", "44100",
            str(audio),
        ]
    )
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video), "-i", str(audio),
            "-c", "copy",
            str(path),
        ]
    )


def load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_qa_mod():
    spec = importlib.util.spec_from_file_location("qa_reel", QA)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["qa_reel"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_proxy(path: Path, seconds: float = 5.0) -> None:
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=540x960:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000",
            "-movflags", "+faststart",
            "-t", str(seconds),
            str(path),
        ]
    )


def make_static(path: Path, seconds: float = 6.0) -> None:
    run_ffmpeg(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=red:s=540x960:d={seconds}:r=30",
            "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000",
            "-t", str(seconds),
            str(path),
        ]
    )


def write_finish_timeline(path: Path, **extra: object) -> None:
    payload = {
        "hook": {"present": False, "duration_s": 0},
        "punches": extra.get("punches", []),
        "joins": extra.get("joins", []),
        "captions": extra.get("captions", {"count": 0}),
        "proxy": extra.get("proxy", False),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_help_exits_zero() -> None:
    r = run_qa(["--help"])
    assert r.returncode == 0, r.stderr
    assert "container.resolution" in r.stdout
    assert "--dry-run" in r.stdout
    assert "--proxy" in r.stdout
    assert "--proxy-size" in r.stdout
    assert "hook.duration_s" in r.stdout or "hook.duration_s" in (r.stdout + r.stderr)


def test_suite() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        good = tmp_p / "good.mp4"
        bad = tmp_p / "bad.mp4"
        make_good(good)
        make_bad(bad, tmp_p)

        ass220 = tmp_p / "m220.ass"
        ass700 = tmp_p / "m700.ass"
        write_ass(ass220, 220)
        write_ass(ass700, 700)

        banned = tmp_p / "banned.txt"
        banned.write_text("smith\n", encoding="utf-8")

        # Good file with safe ASS, frames, contact sheet.
        frames_dir = tmp_p / "frames"
        sheet = tmp_p / "good.sheet.jpg"
        report_good = tmp_p / "good.qa.json"
        r = run_qa(
            [
                "--video", str(good),
                "--ass", str(ass700),
                "--platforms", "instagram_reels",
                "--report", str(report_good),
                "--frames-dir", str(frames_dir),
                "--contact-sheet", str(sheet),
                "--max-px", "540",
            ]
        )
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        data = load_report(report_good)
        ids = {c["id"] for c in data["checks"]}
        assert ids == ALL_IDS, sorted(ALL_IDS - ids)
        assert data["generated_by"] == "qa-reel.py"
        assert data["summary"]["fail"] == 0
        assert status_of(data, "captions.safe_zone") == "pass"
        jpegs = list(frames_dir.glob("*.jpg"))
        assert jpegs, "no frames written"
        for jpg in jpegs:
            with Image.open(jpg) as im:
                assert im.size[1] <= 540, (jpg.name, im.size)
        assert sheet.exists()
        with Image.open(sheet) as im:
            assert im.size[0] <= 1600, im.size

        # Bad file: resolution, sample rate, black frames, short audio tail.
        report_bad = tmp_p / "bad.qa.json"
        r = run_qa(
            [
                "--video", str(bad),
                "--platforms", "instagram_reels",
                "--report", str(report_bad),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_bad)
        assert status_of(data, "container.resolution") == "fail"
        assert status_of(data, "container.sample_rate") == "fail"
        assert status_of(data, "video.black_frames") == "fail"
        assert status_of(data, "audio.tail") == "fail"

        # ASS MarginV 220 sits inside the Instagram bottom band.
        report_low = tmp_p / "low.qa.json"
        r = run_qa(
            [
                "--video", str(good),
                "--ass", str(ass220),
                "--platforms", "instagram_reels",
                "--report", str(report_low),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_low)
        assert status_of(data, "captions.safe_zone") == "fail"

        # Banned whole word in cover text.
        man_banned = tmp_p / "banned.json"
        man_banned.write_text(
            json.dumps(
                {
                    "schema": "reel-manifest/1",
                    "id": "XX-00000000-01",
                    "slug": "qa-banned",
                    "output_dir": str(tmp_p),
                    "duration_window": [5, 15],
                    "source": {"video": "unused.mp4", "transcript_json": "unused.json"},
                    "spine": {"ranges": [{"start": 0.0, "end": 8.0}]},
                    "cover": {"text": "THE SMITH HOUSE"},
                }
            ),
            encoding="utf-8",
        )
        report_ban = tmp_p / "ban.qa.json"
        r = run_qa(
            [
                "--video", str(good),
                "--manifest", str(man_banned),
                "--banned-words", str(banned),
                "--platforms", "instagram_reels",
                "--report", str(report_ban),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_ban)
        assert status_of(data, "text.banned_words") == "fail"

        # Hook range still overlapping a spine range.
        man_hook = tmp_p / "hook.json"
        man_hook.write_text(
            json.dumps(
                {
                    "schema": "reel-manifest/1",
                    "id": "XX-00000000-02",
                    "slug": "qa-hook",
                    "output_dir": str(tmp_p),
                    "duration_window": [5, 15],
                    "source": {"video": "unused.mp4", "transcript_json": "unused.json"},
                    "spine": {"ranges": [{"start": 10.0, "end": 20.0}]},
                    "hook": {
                        "mode": "prepend",
                        "source": None,
                        "range": [12.0, 16.0],
                        "lift_from_spine": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        report_hook = tmp_p / "hook.qa.json"
        r = run_qa(
            [
                "--video", str(good),
                "--manifest", str(man_hook),
                "--platforms", "instagram_reels",
                "--report", str(report_hook),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_hook)
        assert status_of(data, "hook.once") == "fail"


def test_collect_timestamps_labels() -> None:
    mod = load_qa_mod()
    timeline = {
        "hook": {"duration_s": 2.0},
        "punches": [
            {"at_final": 3.0, "dur": 2.0, "kind": "clip"},
            {"at_final": 8.0, "dur": 1.0, "kind": "still"},
        ],
        "joins": [4.5],
    }
    stamps = mod.collect_timestamps(12.0, timeline)
    labels = [lab for _, lab in stamps]
    assert "first" in labels
    assert "cover" in labels
    assert "hook_end" in labels
    assert "punch1" in labels
    assert "punch2" in labels
    assert "join1" in labels
    assert "last" in labels


def test_proxy_resolution_lra_verdict() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        video = tmp_p / "clip-proxy.mp4"
        make_proxy(video, 5.0)
        report = tmp_p / "clip-proxy.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--platforms", "instagram_reels",
                "--report", str(report),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report)
        assert data.get("proxy") is True
        assert status_of(data, "container.resolution") == "pass"
        assert status_of(data, "container.bitrate") == "na"
        lra = next(c for c in data["checks"] if c["id"] == "audio.lra")
        assert lra["status"] == "na"
        assert isinstance(lra["measured"], (int, float))
        lines = [ln for ln in r.stdout.splitlines() if VERDICT_RE.match(ln)]
        assert lines, r.stdout


def test_freeze_inside_punch_warn_outside_fail() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        video = tmp_p / "freeze-proxy.mp4"
        make_static(video, 6.0)

        inside = tmp_p / "inside.timeline.json"
        write_finish_timeline(
            inside,
            punches=[{"at_final": 0.0, "dur": 6.0, "kind": "clip"}],
            proxy=True,
        )
        report_in = tmp_p / "inside.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--timeline", str(inside),
                "--platforms", "instagram_reels",
                "--report", str(report_in),
            ]
        )
        data = load_report(report_in)
        assert status_of(data, "video.frozen_frames") == "warn", r.stdout + r.stderr
        row = next(c for c in data["checks"] if c["id"] == "video.frozen_frames")
        assert "static B-roll or still inside a punch window" in (row.get("detail") or "")

        outside = tmp_p / "outside.timeline.json"
        write_finish_timeline(
            outside,
            punches=[{"at_final": 2.0, "dur": 0.4, "kind": "clip"}],
            proxy=True,
        )
        report_out = tmp_p / "outside.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--timeline", str(outside),
                "--platforms", "instagram_reels",
                "--report", str(report_out),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_out)
        assert status_of(data, "video.frozen_frames") == "fail"


def test_timeline_discovery_and_frame_labels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        video = tmp_p / "disc-proxy.mp4"
        make_proxy(video, 8.0)
        spine = video.with_name(video.stem + ".timeline.json")
        spine.write_text(
            json.dumps({"coarse_ranges": [{"start": 0, "end": 8}], "segments": []}),
            encoding="utf-8",
        )
        finish = Path(str(video) + ".timeline.json")
        write_finish_timeline(
            finish,
            punches=[{"at_final": 3.0, "dur": 2.0, "kind": "clip"}],
            joins=[4.0],
            proxy=True,
        )
        frames_dir = tmp_p / "frames"
        report = tmp_p / "disc.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--platforms", "instagram_reels",
                "--report", str(report),
                "--frames-dir", str(frames_dir),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report)
        used = data.get("timeline") or ""
        assert used.endswith(".mp4.timeline.json"), used
        labels = [f.get("label") for f in data.get("frames") or []]
        assert any(lab == "punch1" for lab in labels), labels
        assert any(lab == "join1" for lab in labels), labels
        assert "first" in labels and "cover" in labels and "last" in labels


def _tiny_manifest(tmp: Path, **extra: object) -> Path:
    payload = {
        "schema": "reel-manifest/1",
        "id": "XX-00000000-13",
        "slug": "qa-wp13",
        "output_dir": str(tmp),
        "duration_window": [3, 20],
        "source": {"video": "unused.mp4", "transcript_json": "unused.json"},
        "spine": {"ranges": [{"start": 0.0, "end": 8.0}]},
    }
    payload.update(extra)
    path = tmp / "wp13.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_broll_stills_shows_exactness() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        video = tmp_p / "wp13-proxy.mp4"
        make_proxy(video, 5.0)

        three = tmp_p / "three.timeline.json"
        write_finish_timeline(
            three,
            punches=[
                {"at_final": 0.2, "dur": 1.0, "kind": "still"},
                {"at_final": 1.5, "dur": 1.0, "kind": "still"},
                {"at_final": 3.0, "dur": 1.0, "kind": "still"},
            ],
            proxy=True,
        )
        report_cap = tmp_p / "cap.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--timeline", str(three),
                "--platforms", "instagram_reels",
                "--report", str(report_cap),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report_cap)
        assert status_of(data, "broll.stills_cap") == "warn"
        assert status_of(data, "broll.consecutive_stills") == "warn"

        man_missing = _tiny_manifest(
            tmp_p,
            broll=[{
                "path": str(tmp_p / "still.jpg"),
                "at": 1.0,
                "dur": 3.5,
                "kind": "still",
                "line": "the pocket door",
            }],
        )
        report_show = tmp_p / "shows.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--manifest", str(man_missing),
                "--platforms", "instagram_reels",
                "--report", str(report_show),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report_show)
        assert status_of(data, "broll.shows_missing") == "warn"

        grades_wrong = video.with_name(video.stem + ".grades.json")
        grades_wrong.write_text(
            json.dumps({
                "punches": [{"index": 0, "grade": "wrong", "by": "verifier"}],
            }),
            encoding="utf-8",
        )
        report_wrong = tmp_p / "wrong.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--platforms", "instagram_reels",
                "--report", str(report_wrong),
            ]
        )
        assert r.returncode == 3, r.stdout + "\n" + r.stderr
        data = load_report(report_wrong)
        assert status_of(data, "broll.exactness") == "fail"
        measured = next(c for c in data["checks"] if c["id"] == "broll.exactness")["measured"]
        assert measured["wrong"] == 1

        grades_wrong.write_text(
            json.dumps({
                "punches": [{"index": 0, "grade": "exact", "by": "verifier"}],
            }),
            encoding="utf-8",
        )
        report_ok = tmp_p / "exact.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--platforms", "instagram_reels",
                "--report", str(report_ok),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report_ok)
        assert status_of(data, "broll.exactness") == "pass"

        grades_wrong.unlink()
        report_na = tmp_p / "na.qa.json"
        r = run_qa(
            [
                "--video", str(video),
                "--platforms", "instagram_reels",
                "--report", str(report_na),
            ]
        )
        assert r.returncode in (0, 3, 4), r.stdout + "\n" + r.stderr
        data = load_report(report_na)
        assert status_of(data, "broll.exactness") == "na"


def main() -> int:
    tests = [
        test_help_exits_zero,
        test_collect_timestamps_labels,
        test_suite,
        test_proxy_resolution_lra_verdict,
        test_freeze_inside_punch_warn_outside_fail,
        test_timeline_discovery_and_frame_labels,
        test_broll_stills_shows_exactness,
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
