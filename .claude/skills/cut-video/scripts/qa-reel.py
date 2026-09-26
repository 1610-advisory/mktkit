#!/usr/bin/env python3
"""Machine-checkable QA gate for a finished talking reel.

Reads a 1080x1920 phone file plus optional manifest, timeline JSON, and ASS
captions. Writes a JSON report and (optionally) downscaled frames plus one
contact sheet so a model looks at one JPEG instead of dozens of full-res
frames.

Checks (ids are stable):
  container.resolution, container.pix_fmt, container.video_codec,
  container.audio_codec, container.sample_rate, container.fps,
  container.faststart, container.bitrate,
  duration.window, duration.platform_max,
  audio.integrated_loudness, audio.true_peak, audio.lra,
  audio.silence_gaps, audio.clipping, audio.tail,
  video.black_frames, video.frozen_frames, video.orientation_sanity,
  video.static_gap,
  captions.safe_zone, captions.timing,
  text.cover_words, text.banned_words, hook.once,
  broll.verified, broll.durations, broll.density,
  broll.stills_cap, broll.consecutive_stills, broll.shows_missing,
  broll.exactness

Proxy files (timeline proxy=true, manifest render.mode=proxy, a -proxy
stem, or --proxy): container.resolution accepts half the canvas (540x960)
or --proxy-size WxH; container.bitrate is NA. Report JSON includes
"proxy": true. The table header says (proxy).

freezedetect uses n=0.001 (ffmpeg default noise floor) so a locked-off
camera with sensor noise is not called frozen. A freeze inside any punch
window WARNs; a freeze outside every punch and outside the first 0.15 s
FAILs.

Final stdout line (stable, grep-able):
  qa-reel: <pass|warn|fail> (<n_fail> fail, <n_warn> warn) <report path>

Timeline keys consumed (all optional, from finish-reel.py --emit-json):
  hook.duration_s, spine_offset_s,
  punches[] (at_final, dur, path, kind, line),
  joins[] (final timeline seconds),
  captions.count, captions.ass,
  loudness.input_i, loudness.output_i

ASS default path: <video_stem>.ass beside the mp4.

Exit codes:
  0  all checks pass (WARN allowed unless --strict)
  2  bad inputs
  3  at least one FAIL
  4  only WARNs, and --strict was set
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CHECK_IDS = (
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
)

FINISH_TIMELINE_KEYS = ("punches", "hook", "joins", "captions")
FREEZEDETECT_N = 0.001

BOTTOM_ALIGNMENTS = {1, 2, 3}
DEFAULT_PLATFORMS = ("instagram_reels", "youtube_shorts")
WORD_RE = re.compile(r"[A-Za-z0-9']+")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def notice(msg: str) -> None:
    eprint(f"notice: {msg}")


@dataclass
class Check:
    id: str
    status: str
    measured: Any = None
    expected: Any = None
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "measured": self.measured,
            "expected": self.expected,
            "detail": self.detail,
        }


@dataclass
class Cue:
    start: float
    end: float
    text: str
    raw: str
    margin_l: int | None = None
    margin_r: int | None = None
    margin_v: int | None = None
    has_override: bool = False
    pos: tuple[float, float] | None = None


@dataclass
class AssFile:
    play_res_x: int = 1080
    play_res_y: int = 1920
    alignment: int = 2
    margin_l: int = 0
    margin_r: int = 0
    margin_v: int = 0
    cues: list[Cue] = field(default_factory=list)
    override_note: str = ""


def resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources"


def sibling(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        eprint(f"ERROR: file not found: {path}")
        raise SystemExit(2)
    except json.JSONDecodeError as exc:
        eprint(f"ERROR: invalid JSON {path}: {exc}")
        raise SystemExit(2)


def parse_fraction(raw: str | None) -> float | None:
    if not raw or raw in ("0/0", "N/A"):
        return None
    try:
        if "/" in raw:
            a, b = raw.split("/", 1)
            denom = float(b)
            if denom == 0:
                return None
            return float(a) / denom
        return float(raw)
    except (TypeError, ValueError):
        return None


def run_cmd(cmd: list[str], dry: bool) -> subprocess.CompletedProcess[str]:
    pretty = " ".join(cmd)
    print(f"[qa-reel] {'DRY ' if dry else ''}{pretty}")
    if dry:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(cmd, capture_output=True, text=True)


def which_or_exit(name: str) -> None:
    from shutil import which

    if which(name) is None:
        eprint(f"ERROR: {name} not found on PATH")
        raise SystemExit(2)


def probe_media(video: Path, dry: bool) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_streams", "-show_format", "-of", "json",
        str(video),
    ]
    r = run_cmd(cmd, dry)
    if dry:
        return {}
    if r.returncode != 0:
        tail = (r.stderr or "").strip().splitlines()
        eprint(f"ERROR: ffprobe failed: {tail[-1] if tail else 'unknown error'}")
        raise SystemExit(2)
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        eprint("ERROR: ffprobe returned invalid JSON")
        raise SystemExit(2)


def stream_of(probe: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for s in probe.get("streams") or []:
        if s.get("codec_type") == kind:
            return s
    return None


def as_float(value: Any) -> float | None:
    if value is None or value == "N/A":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value: Any) -> int | None:
    if value is None or value == "N/A":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def moov_before_mdat(path: Path) -> bool | None:
    """True if moov appears before mdat in the first 1 MB."""
    data = path.read_bytes()[: 1024 * 1024]
    pos = 0
    moov_pos: int | None = None
    mdat_pos: int | None = None
    n = len(data)
    while pos + 8 <= n:
        size = int.from_bytes(data[pos : pos + 4], "big")
        typ = data[pos + 4 : pos + 8]
        if size == 1:
            if pos + 16 > n:
                break
            size = int.from_bytes(data[pos + 8 : pos + 16], "big")
        elif size == 0:
            size = n - pos
        if size < 8:
            break
        if typ == b"moov":
            moov_pos = pos
        elif typ == b"mdat":
            mdat_pos = pos
        if moov_pos is not None and mdat_pos is not None:
            break
        pos += size
    if moov_pos is None:
        return False
    if mdat_pos is None:
        return True
    return moov_pos < mdat_pos


def load_platform_specs(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict) or "platforms" not in data:
        eprint(f"ERROR: platform-specs missing platforms: {path}")
        raise SystemExit(2)
    return data


def merge_platforms(specs: dict[str, Any], names: list[str]) -> dict[str, Any]:
    plats = specs.get("platforms") or {}
    missing = [n for n in names if n not in plats]
    if missing:
        eprint(f"ERROR: unknown platform: {missing[0]}")
        raise SystemExit(2)
    chosen = [plats[n] for n in names]
    safe = {
        "top": max(p["safe_zone_px"]["top"] for p in chosen),
        "bottom": max(p["safe_zone_px"]["bottom"] for p in chosen),
        "left": max(p["safe_zone_px"]["left"] for p in chosen),
        "right": max(p["safe_zone_px"]["right"] for p in chosen),
    }
    fps: list[float] = []
    seen: set[float] = set()
    for p in chosen:
        for rate in p.get("fps_allowed") or []:
            if rate not in seen:
                seen.add(rate)
                fps.append(rate)
    return {
        "names": names,
        "max_duration_s": min(p["max_duration_s"] for p in chosen),
        "video_codec": chosen[0].get("video_codec", "h264"),
        "audio_codec": chosen[0].get("audio_codec", "aac"),
        "audio_sample_rate": chosen[0].get("audio_sample_rate", 48000),
        "loudness_target_i": chosen[0].get("loudness_target_i", -14),
        "loudness_tolerance_lu": min(p["loudness_tolerance_lu"] for p in chosen),
        "true_peak_max_dbtp": min(p["true_peak_max_dbtp"] for p in chosen),
        "safe_zone_px": safe,
        "fps_allowed": fps,
        "delivery": specs.get("delivery") or {},
        "captions": specs.get("captions") or {},
        "cover": specs.get("cover") or {},
        "broll": specs.get("broll") or {},
    }


def parse_ass_time(raw: str) -> float:
    parts = raw.strip().split(":")
    if len(parts) != 3:
        raise ValueError(raw)
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def _csv_fields(line: str) -> list[str]:
    return [p.strip() for p in line.split(",")]


def parse_ass(path: Path) -> AssFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    ass = AssFile()
    style_keys: list[str] = []
    event_keys: list[str] = []
    section = ""
    override_count = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.strip("[]").strip().lower()
            continue
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        key_l = key.strip().lower()
        rest = rest.strip()
        if section in ("script info", "scriptinfo"):
            if key_l == "playresx":
                ass.play_res_x = as_int(rest) or ass.play_res_x
            elif key_l == "playresy":
                ass.play_res_y = as_int(rest) or ass.play_res_y
        elif section.startswith("v4"):
            if key_l == "format":
                style_keys = [k.strip().lower() for k in rest.split(",")]
            elif key_l == "style":
                vals = _csv_fields(rest)
                fields = dict(zip(style_keys, vals))
                ass.alignment = as_int(fields.get("alignment")) or ass.alignment
                ass.margin_l = as_int(fields.get("marginl")) or 0
                ass.margin_r = as_int(fields.get("marginr")) or 0
                ass.margin_v = as_int(fields.get("marginv")) or 0
        elif section == "events":
            if key_l == "format":
                event_keys = [k.strip().lower() for k in rest.split(",")]
            elif key_l == "dialogue":
                # Text may contain commas: split using the format width.
                n = len(event_keys)
                if n == 0:
                    continue
                parts = rest.split(",", n - 1)
                fields = dict(zip(event_keys, parts))
                try:
                    start = parse_ass_time(fields.get("start", "0:00:00.00"))
                    end = parse_ass_time(fields.get("end", "0:00:00.00"))
                except ValueError:
                    continue
                raw_text = fields.get("text", "")
                ml = as_int(fields.get("marginl"))
                mr = as_int(fields.get("marginr"))
                mv = as_int(fields.get("marginv"))
                pos = None
                has_ov = False
                if "{" in raw_text:
                    has_ov = True
                    override_count += 1
                    m = re.search(r"\\pos\(([^,]+),([^)]+)\)", raw_text)
                    if m:
                        try:
                            pos = (float(m.group(1)), float(m.group(2)))
                        except ValueError:
                            pos = None
                visible = re.sub(r"\{[^}]*\}", "", raw_text)
                visible = visible.replace(r"\N", "\n").replace(r"\n", "\n")
                ass.cues.append(
                    Cue(
                        start=start,
                        end=end,
                        text=visible,
                        raw=raw_text,
                        margin_l=ml if ml else None,
                        margin_r=mr if mr else None,
                        margin_v=mv if mv else None,
                        has_override=has_ov,
                        pos=pos,
                    )
                )
    if override_count:
        ass.override_note = f"{override_count} dialogue lines have override tags or \\pos"
    return ass


def parse_ebur128(stderr: str) -> dict[str, float]:
    idx = stderr.rfind("Summary:")
    block = stderr[idx:] if idx >= 0 else stderr
    out: dict[str, float] = {}
    m = re.search(r"\bI:\s*([+-]?\d+(?:\.\d+)?)\s*LUFS", block)
    if m:
        out["I"] = float(m.group(1))
    m = re.search(r"\bLRA:\s*([+-]?\d+(?:\.\d+)?)\s*LU", block)
    if m:
        out["LRA"] = float(m.group(1))
    tp = None
    m = re.search(
        r"True peak:.*?Peak:\s*([+-]?\d+(?:\.\d+)?)\s*dB",
        block,
        re.S | re.I,
    )
    if m:
        tp = float(m.group(1))
    else:
        peaks = re.findall(r"\bPeak:\s*([+-]?\d+(?:\.\d+)?)\s*dB", block)
        if peaks:
            tp = float(peaks[-1])
    if tp is not None:
        out["true_peak"] = tp
    return out


def parse_astats(stderr: str) -> dict[str, float]:
    out: dict[str, float] = {}
    m = re.search(r"Peak level dB:\s*([+-]?\d+(?:\.\d+|inf)?)", stderr, re.I)
    if m:
        try:
            out["peak_dbfs"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"Flat factor:\s*([+-]?\d+(?:\.\d+)?)", stderr, re.I)
    if m:
        out["flat_factor"] = float(m.group(1))
    return out


def parse_silence(stderr: str) -> list[tuple[float, float]]:
    starts: dict[int, float] = {}
    events: list[tuple[float, float]] = []
    for line in stderr.splitlines():
        m = re.search(r"silence_start:\s*([+-]?\d+(?:\.\d+)?)", line)
        if m:
            starts[0] = float(m.group(1))
            continue
        m = re.search(
            r"silence_end:\s*([+-]?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*([+-]?\d+(?:\.\d+)?)",
            line,
        )
        if m:
            end = float(m.group(1))
            dur = float(m.group(2))
            start = starts.pop(0, end - dur)
            events.append((start, end))
    if 0 in starts:
        # open-ended silence through EOF is closed by the caller
        events.append((starts[0], math.inf))
    return events


def parse_black(stderr: str) -> list[tuple[float, float]]:
    events = []
    for line in stderr.splitlines():
        m = re.search(
            r"black_start:\s*([+-]?\d+(?:\.\d+)?)\s+black_end:\s*([+-]?\d+(?:\.\d+)?)",
            line,
        )
        if m:
            events.append((float(m.group(1)), float(m.group(2))))
            continue
        m = re.search(r"black_start:\s*([+-]?\d+(?:\.\d+)?)", line)
        if m:
            events.append((float(m.group(1)), math.inf))
    return events


def parse_freeze(stderr: str) -> list[tuple[float, float]]:
    starts: list[float] = []
    events: list[tuple[float, float]] = []
    for line in stderr.splitlines():
        m = re.search(r"freeze_start:\s*([+-]?\d+(?:\.\d+)?)", line)
        if m:
            starts.append(float(m.group(1)))
            continue
        m = re.search(r"freeze_end:\s*([+-]?\d+(?:\.\d+)?)", line)
        if m and starts:
            events.append((starts.pop(0), float(m.group(1))))
            continue
        m = re.search(r"freeze_duration:\s*([+-]?\d+(?:\.\d+)?)", line)
        if m and starts and not events:
            s = starts[-1]
            events.append((s, s + float(m.group(1))))
            starts.pop()
    for s in starts:
        events.append((s, math.inf))
    return events


def parse_signalstats(text: str) -> dict[str, float]:
    """Read YAVG/YMIN/YMAX from signalstats metadata print or log lines.

    Prefers lavfi.signalstats.KEY=value from metadata=print:file=-.
    Falls back to KEY: value on the same line.
    """
    out: dict[str, float] = {}
    if not text:
        return out
    for key in ("YAVG", "YMIN", "YMAX", "YDIF"):
        matches = re.findall(
            rf"(?:lavfi\.signalstats\.)?{key}[=:]\s*([+-]?\d+(?:\.\d+)?)",
            text,
        )
        if matches:
            try:
                out[key] = float(matches[-1])
            except ValueError:
                pass
    return out


def analyze_av(video: Path, has_audio: bool, dry: bool) -> str:
    # n=0.001 is ffmpeg's default noise floor. A higher n treats sensor
    # noise on a locked-off camera as a freeze. Keep n=0.001.
    vf = f"blackdetect=d=0.3:pix_th=0.10,freezedetect=n={FREEZEDETECT_N}:d=0.7"
    if has_audio:
        af = (
            "ebur128=peak=true,"
            "astats=measure_overall=Peak_level+Flat_factor:measure_perchannel=none,"
            "silencedetect=n=-45dB:d=0.8"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-i", str(video),
            "-filter_complex", f"[0:v]{vf}[v];[0:a]{af}[a]",
            "-map", "[v]", "-map", "[a]", "-f", "null", "-",
        ]
    else:
        cmd = [
            "ffmpeg", "-hide_banner", "-i", str(video),
            "-vf", vf, "-f", "null", "-",
        ]
    r = run_cmd(cmd, dry)
    if dry:
        return ""
    return (r.stderr or "") + (r.stdout or "")


def analyze_first_frame(video: Path, dry: bool) -> str:
    cmd = [
        "ffmpeg", "-hide_banner", "-ss", "0", "-i", str(video),
        "-frames:v", "1",
        "-vf", "signalstats,metadata=print:file=-",
        "-f", "null", "-",
    ]
    r = run_cmd(cmd, dry)
    if dry:
        return ""
    return (r.stderr or "") + (r.stdout or "")


def analyze_tail_peak(video: Path, start: float, dry: bool) -> float | None:
    if start < 0:
        start = 0.0
    cmd = [
        "ffmpeg", "-hide_banner", "-ss", f"{start:.3f}", "-i", str(video),
        "-map", "0:a:0",
        "-af", "astats=measure_overall=Peak_level:measure_perchannel=none",
        "-f", "null", "-",
    ]
    r = run_cmd(cmd, dry)
    if dry:
        return None
    stats = parse_astats((r.stderr or "") + (r.stdout or ""))
    return stats.get("peak_dbfs")


def sibling_help_flags(script: Path) -> set[str]:
    if not script.exists():
        return set()
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
    )
    return set(re.findall(r"--[a-z0-9-]+", r.stdout or ""))


def scale_vf(max_px: int) -> str:
    return (
        f"scale='if(gte(iw,ih),min(iw,{max_px}),-2)':"
        f"'if(gt(ih,iw),min(ih,{max_px}),-2)'"
    )


def join_time(join: Any) -> float | None:
    if isinstance(join, (int, float)):
        return float(join)
    if isinstance(join, str):
        return as_float(join)
    if isinstance(join, dict):
        for key in ("at_final", "t", "time", "at"):
            val = as_float(join.get(key))
            if val is not None:
                return val
    return None


def collect_timestamps(duration: float, timeline: dict[str, Any] | None) -> list[tuple[float, str]]:
    items: list[tuple[float, str]] = [(0.0, "first"), (1.0, "cover")]
    if timeline:
        hook = timeline.get("hook") if isinstance(timeline.get("hook"), dict) else {}
        hook_dur = as_float((hook or {}).get("duration_s")) or 0.0
        if hook_dur > 0:
            items.append((hook_dur + 0.4, "hook_end"))
        for i, punch in enumerate(timeline.get("punches") or [], start=1):
            if not isinstance(punch, dict):
                continue
            at = as_float(punch.get("at_final"))
            dur = as_float(punch.get("dur")) or 0.0
            if at is None:
                continue
            items.append((at + dur / 2.0, f"punch{i}"))
        for i, join in enumerate(timeline.get("joins") or [], start=1):
            t = join_time(join)
            if t is None:
                continue
            items.append((t - 0.3, f"join{i}"))
            items.append((t + 0.3, f"join{i}"))
    else:
        t = 5.0
        while t < duration - 0.25:
            items.append((t, "tick"))
            t += 5.0
    items.append((max(0.0, duration - 0.2), "last"))
    out: list[tuple[float, str]] = []
    seen: set[tuple[float, str]] = set()
    for t, lab in items:
        if duration <= 0:
            t = 0.0
        else:
            t = min(max(0.0, t), max(0.0, duration - 0.04))
        key = (round(t, 2), lab)
        if key in seen:
            continue
        seen.add(key)
        out.append((t, lab))
    return out


def thin_timestamps(
    items: list[tuple[float, str]], cap: int = 24
) -> tuple[list[tuple[float, str]], int]:
    n = len(items)
    if n <= cap:
        return items, 0
    if cap <= 1:
        return items[:1], n - 1
    idxs = [round(i * (n - 1) / (cap - 1)) for i in range(cap)]
    seen: set[int] = set()
    out: list[tuple[float, str]] = []
    for i in idxs:
        if i in seen:
            continue
        seen.add(i)
        out.append(items[i])
    return out, n - len(out)


def safe_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")
    return cleaned or "frame"


def extract_qa_frame(
    video: Path, t: float, dest: Path, max_px: int, dry: bool
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1",
        "-vf", scale_vf(max_px),
        "-q:v", "4",
        str(dest),
    ]
    r = run_cmd(cmd, dry)
    if dry:
        return
    if r.returncode != 0 or not dest.exists():
        tail = (r.stderr or "").strip().splitlines()
        eprint(f"ERROR: could not extract frame at t={t:.3f}s: {tail[-1] if tail else 'no file'}")
        raise SystemExit(2)


def jpeg_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:
        pass
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0 and r.stdout.strip():
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    return (0, 0)


def ranges_overlap(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


def whole_word_hit(text: str, terms: list[str]) -> str | None:
    if not text or not terms:
        return None
    for term in terms:
        term = term.strip()
        if not term:
            continue
        if re.search(r"\b" + re.escape(term) + r"\b", text, re.I):
            return term
    return None


def load_banned(path: Path) -> list[str]:
    terms = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        bit = line.strip()
        if not bit or bit.startswith("#"):
            continue
        terms.append(bit)
    return terms


def punch_windows(punches: list[Any]) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for punch in punches:
        if not isinstance(punch, dict):
            continue
        ps = as_float(punch.get("at_final"))
        if ps is None:
            continue
        pe = ps + (as_float(punch.get("dur")) or 0.0)
        windows.append((ps, pe))
    return windows


def freeze_in_punch(
    start: float, end: float, windows: list[tuple[float, float]]
) -> bool:
    """True when at least half of [start, end] sits inside any punch window.

    Clip and still punches both count. Static B-roll is not a freeze defect.
    """
    span = max(0.0, end - start)
    if span <= 0:
        return False
    for ps, pe in windows:
        overlap = max(0.0, min(end, pe) - max(start, ps))
        if overlap >= span * 0.5:
            return True
    return False


def is_finish_timeline(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    return any(key in data for key in FINISH_TIMELINE_KEYS)


def parse_wxh(raw: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)[xX](\d+)", raw.strip())
    if not m:
        raise argparse.ArgumentTypeError("expected WxH such as 540x960")
    return int(m.group(1)), int(m.group(2))


def detect_proxy(
    *,
    flag: bool,
    timeline: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    video: Path,
) -> bool:
    if flag:
        return True
    if isinstance(timeline, dict) and timeline.get("proxy") is True:
        return True
    if isinstance(manifest, dict):
        render = manifest.get("render")
        if isinstance(render, dict) and str(render.get("mode") or "").lower() == "proxy":
            return True
    if video.stem.endswith("-proxy"):
        return True
    return False


def discover_timeline(
    video: Path, explicit: Path | None
) -> tuple[Path | None, dict[str, Any] | None]:
    """Pick a finish-reel timeline. Skip spine-only JSON.

    Order: --timeline explicit, <video>.timeline.json (foo.mp4.timeline.json),
    <stem>.timeline.json (foo.timeline.json), <stem>.finish.json.
    A file is accepted only if it has punches, hook, joins, or captions.
    """
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    candidates.append(Path(str(video) + ".timeline.json"))
    candidates.append(video.with_name(video.stem + ".timeline.json"))
    candidates.append(video.with_name(video.stem + ".finish.json"))
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            if explicit is not None and path == explicit:
                eprint(f"ERROR: timeline not found: {path}")
                raise SystemExit(2)
            continue
        data = load_json(path)
        if is_finish_timeline(data):
            print(f"[qa-reel] timeline {path}")
            return path, data
        notice(f"skipping {path.name}: no punches/hook/joins/captions")
    return None, None


def discover_ass(
    video: Path, explicit: Path | None, timeline: dict[str, Any] | None
) -> Path | None:
    if explicit is not None:
        if not explicit.exists():
            eprint(f"ERROR: ASS not found: {explicit}")
            raise SystemExit(2)
        print(f"[qa-reel] ass {explicit}")
        return explicit
    for path in (
        video.with_name(video.stem + ".ass"),
        Path(str(video) + ".ass"),
    ):
        if path.exists():
            print(f"[qa-reel] ass {path}")
            return path
    if isinstance(timeline, dict) and isinstance(timeline.get("captions"), dict):
        extra = timeline["captions"].get("ass")
        if extra and Path(extra).exists():
            found = Path(extra)
            print(f"[qa-reel] ass {found}")
            return found
    return None


def close_open(events: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    out = []
    for s, e in events:
        if math.isinf(e):
            e = duration
        out.append((s, e))
    return out


def add(
    checks: dict[str, Check],
    cid: str,
    status: str,
    measured: Any = None,
    expected: Any = None,
    detail: str = "",
) -> None:
    checks[cid] = Check(cid, status, measured, expected, detail)


def check_container(
    checks: dict[str, Check],
    probe: dict[str, Any],
    video: Path,
    plat: dict[str, Any],
    dry: bool,
    proxy: bool = False,
    proxy_size: tuple[int, int] | None = None,
) -> tuple[float, bool]:
    delivery = plat.get("delivery") or {}
    v = stream_of(probe, "video") or {}
    a = stream_of(probe, "audio")
    fmt = probe.get("format") or {}
    width = as_int(v.get("width"))
    height = as_int(v.get("height"))
    want_w = as_int(delivery.get("width")) or 1080
    want_h = as_int(delivery.get("height")) or 1920
    half = (want_w // 2, want_h // 2)
    if proxy:
        allowed = {half}
        if proxy_size is not None:
            allowed.add(proxy_size)
        got = (width, height) if width and height else None
        expected_s = " or ".join(f"{w}x{h}" for w, h in sorted(allowed))
        if got in allowed:
            add(
                checks, "container.resolution", "pass",
                f"{width}x{height}", expected_s,
                "frame size matches proxy canvas",
            )
        else:
            add(
                checks, "container.resolution", "fail",
                f"{width}x{height}" if width and height else None,
                expected_s,
                "frame size is not the proxy canvas",
            )
    elif width == want_w and height == want_h:
        add(
            checks, "container.resolution", "pass",
            f"{width}x{height}", f"{want_w}x{want_h}",
            "frame size matches delivery",
        )
    else:
        add(
            checks, "container.resolution", "fail",
            f"{width}x{height}" if width and height else None,
            f"{want_w}x{want_h}",
            "frame size is not the delivery canvas",
        )

    pix = v.get("pix_fmt")
    allowed_pix = delivery.get("pix_fmt") or ["yuv420p", "yuvj420p"]
    if pix in allowed_pix:
        add(checks, "container.pix_fmt", "pass", pix, allowed_pix, "pixel format is allowed")
    else:
        add(
            checks, "container.pix_fmt", "fail", pix, allowed_pix,
            "pixel format is not in the delivery list",
        )

    vcodec = v.get("codec_name")
    want_vc = plat.get("video_codec", "h264")
    if vcodec == want_vc:
        add(checks, "container.video_codec", "pass", vcodec, want_vc, "video codec matches")
    else:
        add(
            checks, "container.video_codec", "fail", vcodec, want_vc,
            "video codec is not h264",
        )

    if a is None:
        add(
            checks, "container.audio_codec", "fail", None, plat.get("audio_codec", "aac"),
            "no audio stream",
        )
        add(
            checks, "container.sample_rate", "fail", None, plat.get("audio_sample_rate", 48000),
            "no audio stream",
        )
        has_audio = False
    else:
        acodec = a.get("codec_name")
        want_ac = plat.get("audio_codec", "aac")
        if acodec == want_ac:
            add(checks, "container.audio_codec", "pass", acodec, want_ac, "audio codec matches")
        else:
            add(
                checks, "container.audio_codec", "fail", acodec, want_ac,
                "audio codec is not aac",
            )
        rate = as_int(a.get("sample_rate"))
        want_rate = as_int(plat.get("audio_sample_rate")) or 48000
        if rate == want_rate:
            add(
                checks, "container.sample_rate", "pass", rate, want_rate,
                "sample rate matches",
            )
        else:
            add(
                checks, "container.sample_rate", "fail", rate, want_rate,
                "sample rate is not 48000",
            )
        has_audio = True

    fps = parse_fraction(v.get("avg_frame_rate")) or parse_fraction(v.get("r_frame_rate"))
    allowed_fps = plat.get("fps_allowed") or []
    if fps is None:
        add(checks, "container.fps", "fail", None, allowed_fps, "could not read frame rate")
    elif any(abs(fps - allowed) <= 0.01 for allowed in allowed_fps):
        add(checks, "container.fps", "pass", round(fps, 4), allowed_fps, "frame rate is allowed")
    else:
        add(
            checks, "container.fps", "fail", round(fps, 4), allowed_fps,
            "frame rate is not within 0.01 of an allowed rate",
        )

    if dry:
        add(
            checks, "container.faststart", "na", None, True,
            "skipped in dry-run",
        )
    else:
        fast = moov_before_mdat(video)
        if fast:
            add(
                checks, "container.faststart", "pass", True, True,
                "moov atom is before mdat in the first 1 MB",
            )
        else:
            add(
                checks, "container.faststart", "warn", False, True,
                "moov atom is not before mdat in the first 1 MB",
            )

    v_br = as_float(v.get("bit_rate"))
    if v_br is None:
        v_br = as_float(fmt.get("bit_rate"))
    min_kbps = as_float(delivery.get("min_video_bitrate_kbps")) or 6000
    kbps = (v_br / 1000.0) if v_br else None
    if proxy:
        add(
            checks, "container.bitrate", "na",
            round(kbps, 1) if kbps is not None else None,
            None,
            "bitrate not checked on a proxy file",
        )
    elif kbps is None:
        add(
            checks, "container.bitrate", "warn", None, f">={min_kbps} kbps",
            "could not read video bitrate",
        )
    elif kbps < min_kbps:
        add(
            checks, "container.bitrate", "warn", round(kbps, 1), f">={min_kbps} kbps",
            "video bitrate is below the delivery minimum",
        )
    else:
        add(
            checks, "container.bitrate", "pass", round(kbps, 1), f">={min_kbps} kbps",
            "video bitrate meets the delivery minimum",
        )

    duration = as_float(fmt.get("duration"))
    if duration is None:
        duration = as_float(v.get("duration")) or 0.0
    return duration or 0.0, has_audio


def check_duration(
    checks: dict[str, Check],
    duration: float,
    window: tuple[float, float] | None,
    plat: dict[str, Any],
) -> None:
    if window is None:
        add(
            checks, "duration.window", "na", round(duration, 3), None,
            "no --duration-window and no manifest duration_window",
        )
    else:
        lo, hi = window
        if lo <= duration <= hi:
            add(
                checks, "duration.window", "pass", round(duration, 3), [lo, hi],
                "duration is inside the window",
            )
        else:
            add(
                checks, "duration.window", "fail", round(duration, 3), [lo, hi],
                "duration is outside the window",
            )
    max_s = as_float(plat.get("max_duration_s"))
    if max_s is None:
        add(checks, "duration.platform_max", "na", round(duration, 3), None, "no platform max")
    elif duration <= max_s + 1e-6:
        add(
            checks, "duration.platform_max", "pass", round(duration, 3), max_s,
            "duration is within the strictest platform max",
        )
    else:
        add(
            checks, "duration.platform_max", "fail", round(duration, 3), max_s,
            "duration is longer than the strictest platform max",
        )


def check_audio(
    checks: dict[str, Check],
    has_audio: bool,
    duration: float,
    audio_dur: float | None,
    stderr: str,
    plat: dict[str, Any],
    manifest: dict[str, Any] | None,
    video: Path,
    dry: bool,
) -> None:
    if not has_audio:
        for cid, why in (
            ("audio.integrated_loudness", "no audio stream"),
            ("audio.true_peak", "no audio stream"),
            ("audio.lra", "no audio stream"),
            ("audio.silence_gaps", "no audio stream"),
            ("audio.clipping", "no audio stream"),
            ("audio.tail", "no audio stream"),
        ):
            add(checks, cid, "na", None, None, why)
        return
    if dry:
        for cid in (
            "audio.integrated_loudness",
            "audio.true_peak",
            "audio.lra",
            "audio.silence_gaps",
            "audio.clipping",
            "audio.tail",
        ):
            add(checks, cid, "na", None, None, "skipped in dry-run")
        return

    ebu = parse_ebur128(stderr)
    stats = parse_astats(stderr)
    silences = close_open(parse_silence(stderr), duration)

    platform_target = plat.get("loudness_target_i", -14)
    target = platform_target
    source = "platform"
    manifest_target = None
    audio_block = (manifest or {}).get("audio") if isinstance(manifest, dict) else None
    if isinstance(audio_block, dict) and "target_i" in audio_block:
        try:
            manifest_target = float(audio_block["target_i"])
            target = manifest_target
            source = "manifest"
        except (TypeError, ValueError):
            manifest_target = None
    plat_tol = float(plat.get("loudness_tolerance_lu") or 2)
    if source == "manifest":
        warn_lu, fail_lu = 1.0, 2.0
    else:
        warn_lu, fail_lu = plat_tol, plat_tol + 1.0
    measured_i = ebu.get("I")
    expected_loud = {
        "target": target,
        "manifest_target": manifest_target,
        "platform_target": platform_target,
        "warn_lu": warn_lu,
        "fail_lu": fail_lu,
        "source": source,
    }
    if measured_i is None:
        add(
            checks, "audio.integrated_loudness", "warn", None, expected_loud,
            "could not parse ebur128 integrated loudness",
        )
    else:
        delta = abs(measured_i - target)
        if delta > fail_lu:
            add(
                checks, "audio.integrated_loudness", "fail", measured_i, expected_loud,
                f"I={measured_i:.2f} LUFS is outside {target} ± {fail_lu} ({source})",
            )
        elif delta > warn_lu:
            add(
                checks, "audio.integrated_loudness", "warn", measured_i, expected_loud,
                f"I={measured_i:.2f} LUFS is outside {target} ± {warn_lu} ({source})",
            )
        else:
            add(
                checks, "audio.integrated_loudness", "pass", measured_i, expected_loud,
                f"I={measured_i:.2f} LUFS is within {target} ± {warn_lu} ({source})",
            )

    tp_max = float(plat.get("true_peak_max_dbtp") or -1.0)
    tp = ebu.get("true_peak")
    if tp is None:
        add(
            checks, "audio.true_peak", "warn", None, f"<={tp_max} dBTP",
            "could not parse ebur128 true peak",
        )
    elif tp > tp_max:
        add(
            checks, "audio.true_peak", "fail", tp, f"<={tp_max} dBTP",
            "true peak is above the platform cap",
        )
    else:
        add(
            checks, "audio.true_peak", "pass", tp, f"<={tp_max} dBTP",
            "true peak is within the platform cap",
        )

    lra = ebu.get("LRA")
    add(
        checks, "audio.lra", "na", lra, None,
        "LRA is informational for short-form (EBU R128 s1)",
    )

    body0, body1 = 0.5, max(0.5, duration - 0.5)
    worst = "pass"
    gaps = []
    for s, e in silences:
        clipped_s, clipped_e = max(s, body0), min(e, body1)
        gap = clipped_e - clipped_s
        if gap >= 2.0:
            worst = "fail"
            gaps.append(f"{s:.2f}-{e:.2f}s ({gap:.2f}s)")
        elif gap >= 0.8:
            if worst != "fail":
                worst = "warn"
            gaps.append(f"{s:.2f}-{e:.2f}s ({gap:.2f}s)")
    if worst == "pass":
        add(
            checks, "audio.silence_gaps", "pass", 0, "no gap >=0.8s in body",
            "no long silence inside the body",
        )
    else:
        add(
            checks, "audio.silence_gaps", worst, gaps,
            "WARN >=0.8s, FAIL >=2.0s in body",
            "silence gaps in the body: " + ", ".join(gaps),
        )

    peak = stats.get("peak_dbfs")
    flat = stats.get("flat_factor")
    clip_hit = (flat is not None and flat > 0) or (peak is not None and peak >= -0.1)
    add(
        checks, "audio.clipping",
        "warn" if clip_hit else "pass",
        {"peak_dbfs": peak, "flat_factor": flat},
        "Flat_factor=0 and Peak < -0.1 dBFS",
        "clipping indicators present" if clip_hit else "no clipping indicators",
    )

    if audio_dur is not None and audio_dur + 0.25 < duration:
        add(
            checks, "audio.tail", "fail",
            {"audio_s": round(audio_dur, 3), "video_s": round(duration, 3)},
            "audio length within 0.25s of video",
            "audio stream is shorter than video by more than 0.25 s",
        )
        return
    tail_start = max(0.0, duration - 0.7)
    tail_peak = analyze_tail_peak(video, tail_start, dry=False)
    if tail_peak is not None and tail_peak <= -45:
        add(
            checks, "audio.tail", "warn",
            {"tail_peak_dbfs": tail_peak},
            "last 0.7s not silent",
            "last 0.7 s is silence (dropped closer)",
        )
    else:
        add(
            checks, "audio.tail", "pass",
            {"tail_peak_dbfs": tail_peak, "audio_s": audio_dur},
            "last 0.7s not silent",
            "tail has audio",
        )


def check_picture(
    checks: dict[str, Check],
    duration: float,
    stderr: str,
    first_stderr: str,
    timeline: dict[str, Any] | None,
    dry: bool,
) -> None:
    if dry:
        for cid in ("video.black_frames", "video.frozen_frames", "video.orientation_sanity"):
            add(checks, cid, "na", None, None, "skipped in dry-run")
        return

    blacks = close_open(parse_black(stderr), duration)
    bad_black = []
    for s, e in blacks:
        cs, ce = max(s, 0.1), min(e, duration)
        run = ce - cs
        if run >= 0.3:
            bad_black.append({"start": round(s, 3), "end": round(e, 3), "dur": round(run, 3)})
    if bad_black:
        add(
            checks, "video.black_frames", "fail", bad_black, "no black run >=0.3s after 0.1s",
            "black run of at least 0.3 s outside the first 0.1 s",
        )
    else:
        add(
            checks, "video.black_frames", "pass", [], "no black run >=0.3s after 0.1s",
            "no qualifying black run",
        )

    punches = []
    if isinstance(timeline, dict):
        punches = list(timeline.get("punches") or [])
    windows = punch_windows(punches)
    freezes = close_open(parse_freeze(stderr), duration)
    fail_fr = []
    warn_fr = []
    for s, e in freezes:
        cs = max(s, 0.15)
        run = e - cs
        if run < 0.7:
            continue
        rec = {"start": round(s, 3), "end": round(e, 3), "dur": round(run, 3)}
        if timeline and freeze_in_punch(cs, e, windows):
            warn_fr.append(rec)
        else:
            fail_fr.append(rec)
    if fail_fr:
        add(
            checks, "video.frozen_frames", "fail", fail_fr,
            "no freeze >=0.7s outside a punch window and after 0.15s",
            "freeze of at least 0.7 s outside every punch window"
            + ("" if timeline else " (no timeline, so no punch-window exception)"),
        )
    elif warn_fr:
        add(
            checks, "video.frozen_frames", "warn", warn_fr,
            f"freezedetect n={FREEZEDETECT_N}",
            "static B-roll or still inside a punch window",
        )
    else:
        detail = "no freeze of 0.7 s or more outside a punch window"
        if timeline is None:
            detail += " (no timeline; punch-window exception not applied)"
        add(
            checks, "video.frozen_frames", "pass", [],
            f"freezedetect n={FREEZEDETECT_N}; no freeze >=0.7s outside a punch",
            detail,
        )

    sig = parse_signalstats(first_stderr)
    ymin, ymax = sig.get("YMIN"), sig.get("YMAX")
    spread = None if ymin is None or ymax is None else ymax - ymin
    if spread is None:
        add(
            checks, "video.orientation_sanity", "na", sig or None,
            "YMAX - YMIN >= 24",
            "signalstats unavailable",
        )
    elif spread < 24:
        add(
            checks, "video.orientation_sanity", "warn",
            {"YMIN": ymin, "YMAX": ymax, "YAVG": sig.get("YAVG"), "spread": spread},
            "YMAX - YMIN >= 24",
            "first-frame luma spread is under 24 (near-blank first frame)",
        )
    else:
        add(
            checks, "video.orientation_sanity", "pass",
            {"YMIN": ymin, "YMAX": ymax, "YAVG": sig.get("YAVG"), "spread": spread},
            "YMAX - YMIN >= 24",
            "first frame has luma variation",
        )


SATAVG_RE = re.compile(r"(?:lavfi\.signalstats\.)?SATAVG[=:]\s*([+-]?\d+(?:\.\d+)?)")


def frame_satavg(video: Path, t: float) -> float | None:
    """Mean chroma saturation (signalstats SATAVG) of the frame at t."""
    cmd = [
        "ffmpeg", "-hide_banner", "-ss", f"{max(t, 0.0):.3f}", "-i", str(video),
        "-frames:v", "1", "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-",
    ]
    r = run_cmd(cmd, False)
    text = (r.stderr or "") + (r.stdout or "")
    m = SATAVG_RE.search(text)
    return float(m.group(1)) if m else None


def check_grade(
    checks: dict[str, Check],
    video: Path,
    duration: float,
    timeline: dict[str, Any] | None,
    dry: bool,
) -> None:
    """Punches should sit in the same grade as the A-roll.

    Compares median saturation of punch midpoints against A-roll frames
    (first, cover, hook end, last, and the frame after each punch). The
    most-recurring defect in the ledger is a LUT applied to Rec.709 stills
    (orange, crushed) or log B-roll left ungraded (flat, grey); both move the
    ratio far from 1. WARN outside 0.6 to 1.6; NA without punches.
    """
    cid = "video.grade_mismatch"
    if dry:
        add(checks, cid, "na", None, "punch/A-roll saturation ratio 0.6 to 1.6", "skipped in dry-run")
        return
    punches = [p for p in ((timeline or {}).get("punches") or []) if isinstance(p, dict)]
    windows: list[tuple[float, float]] = []
    for p in punches:
        at = as_float(p.get("at_final"))
        if at is None:
            continue
        windows.append((at, at + (as_float(p.get("dur")) or 0.0)))
    if not windows:
        add(checks, cid, "na", None, "punch/A-roll saturation ratio 0.6 to 1.6", "no punches")
        return
    punch_ts = [a + (b - a) / 2.0 for a, b in windows if b - a > 0.3]
    hook = (timeline or {}).get("hook") if isinstance((timeline or {}).get("hook"), dict) else {}
    hook_dur = as_float((hook or {}).get("duration_s")) or 0.0
    aroll_ts = [0.3, 1.0, max(duration - 0.4, 0.0)]
    if hook_dur > 0:
        aroll_ts.append(hook_dur + 0.4)
    for _a, b in windows:
        aroll_ts.append(b + 0.6)

    def in_punch(t: float) -> bool:
        return any(a - 0.1 <= t <= b + 0.1 for a, b in windows)

    aroll_ts = [t for t in aroll_ts if 0 <= t < duration and not in_punch(t)]
    p_vals = [v for v in (frame_satavg(video, t) for t in punch_ts[:8]) if v is not None]
    a_vals = [v for v in (frame_satavg(video, t) for t in aroll_ts[:8]) if v is not None]
    if not p_vals or not a_vals:
        add(checks, cid, "na", None, "punch/A-roll saturation ratio 0.6 to 1.6", "signalstats unavailable")
        return
    p_med = sorted(p_vals)[len(p_vals) // 2]
    a_med = sorted(a_vals)[len(a_vals) // 2]
    ratio = (p_med / a_med) if a_med > 1e-6 else float("inf")
    measured = {"punch_satavg": round(p_med, 1), "aroll_satavg": round(a_med, 1), "ratio": round(ratio, 2)}
    if ratio > 1.6:
        add(checks, cid, "warn", measured, "ratio 0.6 to 1.6",
            "punches far more saturated than the A-roll: a LUT on Rec.709 stills or clips, or A-roll left flat")
    elif ratio < 0.6:
        add(checks, cid, "warn", measured, "ratio 0.6 to 1.6",
            "punches far less saturated than the A-roll: log B-roll left ungraded")
    else:
        add(checks, cid, "pass", measured, "ratio 0.6 to 1.6", "punches sit in the A-roll grade")


def check_cadence(
    checks: dict[str, Check],
    duration: float,
    timeline: dict[str, Any] | None,
    plat: dict[str, Any],
    dry: bool,
) -> None:
    bspec = plat.get("broll") or {}
    try:
        max_gap = float(bspec.get("max_static_gap_s") if bspec.get("max_static_gap_s") is not None else 7.0)
    except (TypeError, ValueError):
        max_gap = 7.0
    try:
        max_ppm = float(bspec.get("max_punches_per_minute") if bspec.get("max_punches_per_minute") is not None else 10)
    except (TypeError, ValueError):
        max_ppm = 10.0
    if dry:
        add(checks, "video.static_gap", "na", None, f"<= {max_gap}s", "skipped in dry-run")
        add(checks, "video.join_uncovered", "na", None, "every join inside a punch", "skipped in dry-run")
        add(checks, "broll.density", "na", None, f"<= {max_ppm}/min", "skipped in dry-run")
        return
    if not timeline:
        add(checks, "video.static_gap", "na", None, f"<= {max_gap}s", "no timeline")
        add(checks, "video.join_uncovered", "na", None, "every join inside a punch", "no timeline")
        add(checks, "broll.density", "na", None, f"<= {max_ppm}/min", "no timeline")
        return

    # A spine join (an A-roll splice) should sit inside a punch window so the
    # cut is hidden. Found on fixture A, 2026-09-05: the second join played as a
    # visible jump because the nearest punch ended two seconds earlier.
    join_pad = 0.15
    punch_windows: list[tuple[float, float]] = []
    for punch in timeline.get("punches") or []:
        if not isinstance(punch, dict):
            continue
        at = as_float(punch.get("at_final"))
        if at is None:
            continue
        punch_windows.append((at, at + (as_float(punch.get("dur")) or 0.0)))
    uncovered: list[float] = []
    join_count = 0
    for join in timeline.get("joins") or []:
        t = join_time(join)
        if t is None:
            continue
        join_count += 1
        if not any(a - join_pad <= t <= b + join_pad for a, b in punch_windows):
            uncovered.append(round(t, 2))
    if join_count == 0:
        add(checks, "video.join_uncovered", "na", [], "every join inside a punch", "no spine joins")
    elif uncovered:
        add(
            checks, "video.join_uncovered", "warn", uncovered, "every join inside a punch",
            "A-roll splice visible at " + ", ".join(f"{t:.2f}s" for t in uncovered)
            + "; move or add a punch so its window straddles the join",
        )
    else:
        add(checks, "video.join_uncovered", "pass", [], "every join inside a punch", f"{join_count} join(s) covered")

    events: list[float] = [0.0, 2.0]
    hook = timeline.get("hook") if isinstance(timeline.get("hook"), dict) else {}
    hook_dur = as_float((hook or {}).get("duration_s")) or 0.0
    if hook_dur > 0:
        events.append(hook_dur)
    for punch in timeline.get("punches") or []:
        if not isinstance(punch, dict):
            continue
        at = as_float(punch.get("at_final"))
        if at is None:
            continue
        dur = as_float(punch.get("dur")) or 0.0
        events.append(at)
        events.append(at + dur)
    for join in timeline.get("joins") or []:
        t = join_time(join)
        if t is not None:
            events.append(t)
    events.append(max(duration, 0.0))
    uniq = sorted({round(t, 3) for t in events if t is not None})
    gaps = []
    for a, b in zip(uniq, uniq[1:]):
        gap = b - a
        if gap > max_gap:
            gaps.append({"from": a, "to": b, "gap_s": round(gap, 3)})
    static_note = (
        " (informational: a line with no exact asset correctly stays on the speaker)"
    )
    if gaps:
        add(
            checks, "video.static_gap", "warn", gaps, f"<= {max_gap}s",
            "static gaps longer than max_static_gap_s: "
            + ", ".join(f"{g['from']:.2f}-{g['to']:.2f}s" for g in gaps)
            + static_note,
        )
    else:
        add(
            checks, "video.static_gap", "pass", [], f"<= {max_gap}s",
            "no static gap longer than max_static_gap_s" + static_note,
        )

    punches = [p for p in (timeline.get("punches") or []) if isinstance(p, dict)]
    minutes = max(duration, 1e-6) / 60.0
    ppm = len(punches) / minutes
    measured = {"punches": len(punches), "per_minute": round(ppm, 2)}
    if len(punches) and ppm > max_ppm:
        add(
            checks, "broll.density", "warn", measured, f"<= {max_ppm}/min",
            f"{len(punches)} punches is {ppm:.1f} per minute (max {max_ppm})",
        )
    else:
        add(
            checks, "broll.density", "pass", measured, f"<= {max_ppm}/min",
            "punch density is within max_punches_per_minute",
        )


def _qa_policy_num(value: Any, default):
    if value is None:
        return default
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def still_policy(manifest: dict[str, Any] | None, plat: dict[str, Any]) -> dict[str, Any]:
    bspec = plat.get("broll") or {}
    qa = {}
    if isinstance(manifest, dict) and isinstance(manifest.get("qa"), dict):
        qa = manifest["qa"]
    return {
        "max_stills": _qa_policy_num(
            qa.get("max_stills"),
            _qa_policy_num(bspec.get("max_stills_per_reel"), 2),
        ),
        "max_consecutive_stills": _qa_policy_num(
            qa.get("max_consecutive_stills"),
            _qa_policy_num(bspec.get("max_consecutive_stills"), 1),
        ),
    }


def timeline_still_windows(timeline: dict[str, Any] | None) -> list[tuple[int, float, float]]:
    out: list[tuple[int, float, float]] = []
    if not timeline:
        return out
    for i, punch in enumerate(timeline.get("punches") or []):
        if not isinstance(punch, dict):
            continue
        if str(punch.get("kind") or "").lower() != "still":
            continue
        at = as_float(punch.get("at_final"))
        if at is None:
            continue
        dur = as_float(punch.get("dur")) or 0.0
        out.append((i, at, at + dur))
    out.sort(key=lambda x: x[1])
    return out


def load_exactness_grades(
    manifest: dict[str, Any] | None,
    video: Path,
) -> list[dict[str, Any]]:
    grades: dict[int, dict[str, Any]] = {}
    if isinstance(manifest, dict):
        for i, entry in enumerate(manifest.get("broll") or []):
            if not isinstance(entry, dict):
                continue
            g = str(entry.get("grade") or "ungraded")
            if g in {"exact", "category", "wrong"}:
                grades[i] = {
                    "index": i,
                    "grade": g,
                    "by": entry.get("graded_by"),
                }
    gpath = video.with_name(video.stem + ".grades.json")
    if gpath.is_file():
        try:
            blob = json.loads(gpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            notice(f"grades.json unreadable: {exc}")
            blob = None
        if isinstance(blob, dict):
            for item in blob.get("punches") or []:
                if not isinstance(item, dict):
                    continue
                try:
                    idx = int(item["index"])
                except (KeyError, TypeError, ValueError):
                    continue
                g = str(item.get("grade") or "")
                if g in {"exact", "category", "wrong"}:
                    grades[idx] = {
                        "index": idx,
                        "grade": g,
                        "by": item.get("by"),
                    }
    return [grades[k] for k in sorted(grades)]


def check_broll_policy(
    checks: dict[str, Check],
    manifest: dict[str, Any] | None,
    timeline: dict[str, Any] | None,
    plat: dict[str, Any],
    video: Path,
    dry: bool,
) -> None:
    policy = still_policy(manifest, plat)
    max_stills = int(policy["max_stills"])
    max_run = int(policy["max_consecutive_stills"])
    if dry:
        add(checks, "broll.stills_cap", "na", None, f"<= {max_stills}", "skipped in dry-run")
        add(checks, "broll.consecutive_stills", "na", None, f"gap >= 1.0s or run <= {max_run}", "skipped in dry-run")
        add(checks, "broll.shows_missing", "na", None, "shows on every sourced punch", "skipped in dry-run")
        add(checks, "broll.exactness", "na", None, "every graded punch exact", "skipped in dry-run")
        return

    stills = timeline_still_windows(timeline)
    if not timeline:
        add(checks, "broll.stills_cap", "na", None, f"<= {max_stills}", "no timeline")
        add(checks, "broll.consecutive_stills", "na", None, "gap >= 1.0s", "no timeline")
    else:
        n = len(stills)
        measured = {"stills": n, "max": max_stills}
        if n > max_stills:
            add(
                checks, "broll.stills_cap", "warn", measured, f"<= {max_stills}",
                f"{n} stills; policy allows {max_stills}",
            )
        else:
            add(
                checks, "broll.stills_cap", "pass", measured, f"<= {max_stills}",
                f"{n} still punches within the cap",
            )
        longest = 1 if stills else 0
        run = 1
        pairs: list[dict[str, Any]] = []
        for prev, cur in zip(stills, stills[1:]):
            gap = cur[1] - prev[2]
            if gap < 1.0:
                run += 1
                longest = max(longest, run)
                pairs.append({"a": prev[0], "b": cur[0], "gap_s": round(gap, 3)})
            else:
                run = 1
        if pairs and longest > max_run:
            add(
                checks, "broll.consecutive_stills", "warn", pairs, "gap >= 1.0s",
                "adjacent stills (gap under 1.0 s): "
                + ", ".join(f"punch {p['a']}+{p['b']}" for p in pairs),
            )
        else:
            add(
                checks, "broll.consecutive_stills", "pass", pairs, "gap >= 1.0s",
                "no adjacent still punches",
            )

    if not isinstance(manifest, dict):
        add(checks, "broll.shows_missing", "na", None, "shows on every sourced punch", "no manifest")
    else:
        missing: list[dict[str, Any]] = []
        for i, entry in enumerate(manifest.get("broll") or []):
            if not isinstance(entry, dict):
                continue
            if (entry.get("path") or "") == "":
                continue
            if not str(entry.get("shows") or "").strip():
                missing.append({"index": i, "line": entry.get("line")})
        if missing:
            add(
                checks, "broll.shows_missing", "warn", missing,
                "shows on every sourced punch",
                "sourced punches with no shows: "
                + ", ".join(f"broll[{m['index']}]" for m in missing),
            )
        else:
            add(
                checks, "broll.shows_missing", "pass", [],
                "shows on every sourced punch",
                "every sourced punch has shows",
            )

    graded = load_exactness_grades(manifest, video)
    counts = {"exact": 0, "category": 0, "wrong": 0}
    for item in graded:
        g = item.get("grade")
        if g in counts:
            counts[g] += 1
    if not graded:
        add(checks, "broll.exactness", "na", counts, "every graded punch exact", "nothing is graded")
    elif counts["wrong"]:
        add(
            checks, "broll.exactness", "fail", counts, "every graded punch exact",
            f"{counts['wrong']} punch(es) graded wrong",
        )
    elif counts["category"]:
        add(
            checks, "broll.exactness", "warn", counts, "every graded punch exact",
            f"{counts['category']} punch(es) graded category",
        )
    else:
        add(
            checks, "broll.exactness", "pass", counts, "every graded punch exact",
            "every graded punch is exact",
        )


def check_captions(
    checks: dict[str, Check],
    ass: AssFile | None,
    plat: dict[str, Any],
    cover_text: str | None,
) -> None:
    if ass is None:
        add(checks, "captions.safe_zone", "na", None, None, "no ASS file")
        add(checks, "captions.timing", "na", None, None, "no ASS file")
        return
    safe = plat.get("safe_zone_px") or {}
    bottom = int(safe.get("bottom") or 0)
    left = int(safe.get("left") or 0)
    right = int(safe.get("right") or 0)
    play_y = ass.play_res_y
    band_bottom = play_y - ass.margin_v
    limit = play_y - bottom
    problems = []
    if ass.alignment in BOTTOM_ALIGNMENTS and band_bottom > limit:
        problems.append(
            f"bottom band at y={band_bottom} sits inside the {bottom}px safe zone"
        )
    if ass.margin_l < left:
        problems.append(f"MarginL {ass.margin_l} < left safe {left}")
    if ass.margin_r < right:
        problems.append(f"MarginR {ass.margin_r} < right safe {right}")
    measured = {
        "alignment": ass.alignment,
        "MarginL": ass.margin_l,
        "MarginR": ass.margin_r,
        "MarginV": ass.margin_v,
        "PlayResY": play_y,
    }
    expected = {"safe_zone_px": safe}
    detail = ass.override_note or "style margins checked against the strictest platform"
    if problems:
        add(
            checks, "captions.safe_zone", "fail", measured, expected,
            "; ".join(problems) + (f" ({ass.override_note})" if ass.override_note else ""),
        )
    else:
        add(checks, "captions.safe_zone", "pass", measured, expected, detail)

    cap = plat.get("captions") or {}
    min_cue = float(cap.get("min_cue_s") or 0.8)
    max_cue = float(cap.get("max_cue_s") or 2.8)
    max_chars = int(cap.get("max_chars_per_line") or 32) * int(cap.get("max_lines") or 2)
    warns = []
    fail_cues = []
    cover_has_slash_n = bool(cover_text) and (r"\N" in cover_text or r"\n" in cover_text)
    for cue in ass.cues:
        dur = cue.end - cue.start
        if dur < min_cue or dur > max_cue:
            warns.append(f"cue {cue.start:.2f}-{cue.end:.2f}s lasts {dur:.2f}s")
        visible_len = len(cue.text.replace("\n", ""))
        if visible_len > max_chars:
            warns.append(f"cue at {cue.start:.2f}s has {visible_len} chars")
        leftover = ("\\N" in cue.text) or ("\\n" in cue.text)
        if leftover or (cover_has_slash_n and (r"\N" in cue.raw or r"\n" in cue.raw)):
            fail_cues.append((cue.text or cue.raw)[:80])
    if fail_cues:
        add(
            checks, "captions.timing", "fail", fail_cues,
            {"min_cue_s": min_cue, "max_cue_s": max_cue, "max_chars": max_chars},
            "cue text contains a literal \\N sequence (drawtext leftover): "
            + repr(fail_cues[0]),
        )
    elif warns:
        add(
            checks, "captions.timing", "warn", warns,
            {"min_cue_s": min_cue, "max_cue_s": max_cue, "max_chars": max_chars},
            "; ".join(warns[:4]),
        )
    else:
        add(
            checks, "captions.timing", "pass",
            {"cues": len(ass.cues)},
            {"min_cue_s": min_cue, "max_cue_s": max_cue, "max_chars": max_chars},
            "cue lengths and character counts are inside the platform limits",
        )


def check_text(
    checks: dict[str, Check],
    manifest: dict[str, Any] | None,
    ass: AssFile | None,
    plat: dict[str, Any],
    banned_path: Path | None,
    timeline: dict[str, Any] | None,
) -> None:
    cover = None
    if isinstance(manifest, dict):
        cover = (manifest.get("cover") or {}).get("text") if isinstance(manifest.get("cover"), dict) else None
    max_words = int((plat.get("cover") or {}).get("max_words") or 7)
    if cover is None:
        add(checks, "text.cover_words", "na", None, f"<={max_words} words, no backslash", "no cover text")
        cover_text = None
    else:
        words = [w for w in str(cover).split() if w]
        problems = []
        if len(words) > max_words:
            problems.append(f"{len(words)} words > {max_words}")
        if "\\" in str(cover):
            problems.append("literal backslash in cover text")
        status = "fail" if problems else "pass"
        add(
            checks, "text.cover_words", status,
            {"text": cover, "words": len(words)},
            f"<={max_words} words, no backslash",
            "; ".join(problems) if problems else "cover word count and escapes are clean",
        )
        cover_text = str(cover)

    if banned_path is None:
        add(checks, "text.banned_words", "na", None, None, "no banned-words list")
    else:
        terms = load_banned(banned_path)
        haystacks = []
        if cover_text:
            haystacks.append(("cover", cover_text))
        if isinstance(manifest, dict):
            for i, entry in enumerate(manifest.get("broll") or []):
                if not isinstance(entry, dict):
                    continue
                if entry.get("line"):
                    haystacks.append((f"broll[{i}].line", str(entry["line"])))
                super_obj = entry.get("super")
                if isinstance(super_obj, dict) and super_obj.get("text"):
                    haystacks.append((f"broll[{i}].super", str(super_obj["text"])))
            for i, entry in enumerate(manifest.get("inserts") or []):
                if isinstance(entry, dict) and entry.get("super"):
                    haystacks.append((f"inserts[{i}].super", str(entry["super"])))
        if ass is not None:
            for i, cue in enumerate(ass.cues):
                haystacks.append((f"ass[{i}]", cue.text))
        hits = []
        for where, text in haystacks:
            term = whole_word_hit(text, terms)
            if term:
                hits.append({"where": where, "term": term})
        if hits:
            add(
                checks, "text.banned_words", "fail", hits, f"{len(terms)} terms",
                f"banned term '{hits[0]['term']}' in {hits[0]['where']}",
            )
        else:
            add(
                checks, "text.banned_words", "pass", [], f"{len(terms)} terms",
                "no banned term in cover, supers, captions, or broll lines",
            )

    # hook.once
    hook_status = "na"
    hook_detail = "no manifest hook and no ASS file"
    hook_measured: Any = None
    if isinstance(manifest, dict) and isinstance(manifest.get("hook"), dict):
        hook = manifest["hook"]
        mode = hook.get("mode") or "none"
        lift = hook.get("lift_from_spine")
        if lift is None:
            lift = False
        src_video = (manifest.get("source") or {}).get("video") if isinstance(manifest.get("source"), dict) else None
        hook_src = hook.get("source")
        same_src = hook_src in (None, "", src_video)
        rng = hook.get("range") or []
        ranges = []
        if isinstance(manifest.get("spine"), dict):
            ranges = list((manifest["spine"].get("ranges") or []))
        if mode != "prepend":
            hook_status = "na"
            hook_detail = f"hook.mode is {mode}, not prepend"
        elif not same_src:
            hook_status = "pass"
            hook_detail = "hook source is not the spine source"
        elif not lift:
            hook_status = "pass"
            hook_detail = "lift_from_spine is false, overlap is allowed"
        elif not (isinstance(rng, list) and len(rng) == 2):
            hook_status = "na"
            hook_detail = "hook.range missing"
        else:
            hs, he = float(rng[0]), float(rng[1])
            overlaps = []
            for entry in ranges:
                if not isinstance(entry, dict):
                    continue
                try:
                    rs, re_ = float(entry["start"]), float(entry["end"])
                except (KeyError, TypeError, ValueError):
                    continue
                if ranges_overlap(rs, re_, hs, he):
                    overlaps.append({"spine": [rs, re_], "hook": [hs, he]})
            hook_measured = overlaps
            if overlaps:
                hook_status = "fail"
                hook_detail = "spine range overlaps hook.range; the renderer should have lifted it"
            else:
                hook_status = "pass"
                hook_detail = "hook range does not overlap remaining spine ranges"
    if ass is not None and ass.cues:
        first = ass.cues[0]
        seq = WORD_RE.findall(first.text.lower())
        if len(seq) >= 4:
            hook_end = first.end
            if isinstance(timeline, dict) and isinstance(timeline.get("hook"), dict):
                hd = as_float(timeline["hook"].get("duration_s"))
                if hd:
                    hook_end = hd
            repeats = []
            n = len(seq)
            for cue in ass.cues[1:]:
                if cue.start < hook_end + 1.0:
                    continue
                hay = WORD_RE.findall(cue.text.lower())
                for i in range(0, len(hay) - n + 1):
                    if hay[i : i + n] == seq:
                        repeats.append({"at": cue.start, "text": cue.text[:80]})
                        break
            # A prepended hook that stays in the spine repeats once by design.
            by_design = hook_detail == "lift_from_spine is false, overlap is allowed"
            if by_design and len(repeats) <= 1:
                hook_measured = repeats
                hook_detail = "hook repeats once in the full edit, by design" if repeats else hook_detail
            elif repeats and hook_status != "fail":
                hook_status = "warn"
                hook_measured = repeats
                hook_detail = "hook line may repeat" + (" more than once" if by_design else "")
            elif repeats and hook_status == "fail":
                hook_detail += "; hook line may also repeat in captions"
    if hook_status == "na" and not (
        isinstance(manifest, dict) and isinstance(manifest.get("hook"), dict)
    ) and ass is None:
        hook_detail = "no manifest hook and no ASS file"
    add(checks, "hook.once", hook_status, hook_measured, "hook opens the cut; repeats at most once, only by design", hook_detail)

    if not isinstance(manifest, dict):
        add(checks, "broll.verified", "na", None, None, "no manifest")
        add(checks, "broll.durations", "na", None, None, "no manifest")
        return

    broll = list(manifest.get("broll") or [])
    unverified = []
    for i, entry in enumerate(broll):
        if not isinstance(entry, dict):
            continue
        if entry.get("verified") is False or "verified" not in entry:
            # schema default is false
            if entry.get("verified") is not True:
                unverified.append({"index": i, "path": entry.get("path"), "line": entry.get("line")})
    if not broll:
        add(checks, "broll.verified", "pass", [], "verified true", "no broll entries")
    elif unverified:
        add(
            checks, "broll.verified", "warn", unverified, "verified true",
            "relevance not confirmed by a vision check: "
            + ", ".join(str(u.get("path") or u["index"]) for u in unverified),
        )
    else:
        add(checks, "broll.verified", "pass", [], "verified true", "every broll entry is verified")

    bspec = plat.get("broll") or {}
    clip_max = float(bspec.get("clip_max_s") or 3.0)
    text_min = float(bspec.get("with_text_min_s") or 3.5)
    dur_warns = []
    for i, entry in enumerate(broll):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "auto").lower()
        dur = as_float(entry.get("dur"))
        if dur is None:
            dur = 2.5
        has_super = isinstance(entry.get("super"), dict) and bool(entry["super"].get("text"))
        is_still = kind == "still"
        if not is_still and dur > clip_max and not has_super:
            dur_warns.append(
                f"broll[{i}] clip punch {dur}s > {clip_max}s without a super"
            )
        if has_super and dur < text_min:
            dur_warns.append(
                f"broll[{i}] punch with super is {dur}s < {text_min}s"
            )
    if not broll:
        add(checks, "broll.durations", "pass", [], {"clip_max_s": clip_max, "with_text_min_s": text_min}, "no broll entries")
    elif dur_warns:
        add(
            checks, "broll.durations", "warn", dur_warns,
            {"clip_max_s": clip_max, "with_text_min_s": text_min},
            "; ".join(dur_warns),
        )
    else:
        add(
            checks, "broll.durations", "pass", [],
            {"clip_max_s": clip_max, "with_text_min_s": text_min},
            "punch durations sit inside the platform limits",
        )


def build_contact_sheet(
    frames: list[dict[str, Any]],
    out: Path,
    max_px: int,
    dry: bool,
) -> Path | None:
    script = sibling("contact-sheet.py")
    if not script.exists():
        notice("contact-sheet.py not found; skipping sheet")
        return None
    flags = sibling_help_flags(script)
    out_flag = "--out" if "--out" in flags else ("--output" if "--output" in flags else None)
    if out_flag is None:
        notice("contact-sheet.py --help has no --out/--output; skipping sheet")
        return None
    cmd = [sys.executable, str(script), out_flag, str(out)]
    paths = [str(f["path"]) for f in frames]
    labels = [f"t={f['t']:.1f}s {f['label']}" for f in frames]
    if "--frames" in flags:
        cmd += ["--frames", *paths]
    else:
        notice("contact-sheet.py has no --frames; skipping sheet")
        return None
    if "--labels" in flags:
        cmd += ["--labels", *labels]
    else:
        notice("contact-sheet.py has no --labels; labels omitted")
    if "--cols" in flags:
        cmd += ["--cols", "4"]
    elif "--columns" in flags:
        cmd += ["--columns", "4"]
    if "--max-px" in flags:
        cmd += ["--max-px", str(max_px)]
    if "--tile-width" in flags:
        cmd += ["--tile-width", "400"]
    if dry and "--dry-run" in flags:
        cmd.append("--dry-run")
    r = run_cmd(cmd, dry=False if not dry else False)
    # Always invoke (even dry-run: pass through). run_cmd already printed.
    # Re-run logic: we passed dry through the child flag, not by skipping.
    if dry:
        return out
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip().splitlines()
        notice(f"contact-sheet.py failed: {tail[-1] if tail else r.returncode}")
        return None
    return out


def print_table(
    checks: list[Check],
    quiet: bool,
    verdict: str,
    summary: dict[str, int],
    report_path: Path,
    proxy: bool,
) -> None:
    line = (
        f"qa-reel: {verdict} ({summary['fail']} fail, {summary['warn']} warn) "
        f"{report_path}"
    )
    if not quiet:
        header = "id                           status measured                     expected"
        if proxy:
            print("qa-reel (proxy)")
        print(header)
        order = {"fail": 0, "warn": 1, "pass": 2, "na": 3}
        rows = sorted(
            checks,
            key=lambda c: (
                order.get(c.status, 9),
                CHECK_IDS.index(c.id) if c.id in CHECK_IDS else 99,
            ),
        )
        for c in rows:
            meas = c.measured
            if isinstance(meas, (dict, list)):
                meas_s = json.dumps(meas, ensure_ascii=True)
            else:
                meas_s = "" if meas is None else str(meas)
            exp = c.expected
            if isinstance(exp, (dict, list)):
                exp_s = json.dumps(exp, ensure_ascii=True)
            else:
                exp_s = "" if exp is None else str(exp)
            if len(meas_s) > 28:
                meas_s = meas_s[:25] + "..."
            print(f"{c.id:<28} {c.status:<6} {meas_s:<28} {exp_s}")
    print(line)


def parse_window(raw: str) -> tuple[float, float]:
    parts = raw.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected MIN,MAX")
    try:
        lo, hi = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected MIN,MAX as numbers") from exc
    if hi < lo:
        raise argparse.ArgumentTypeError("duration window max must be >= min")
    return lo, hi


def parse_platforms(raw: str) -> list[str]:
    names = [p.strip() for p in raw.split(",") if p.strip()]
    if not names:
        raise argparse.ArgumentTypeError("need at least one platform")
    return names


def resolve_maybe(path_str: str | None, manifest_path: Path | None) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str)
    if path.is_absolute():
        return path
    if manifest_path is not None:
        return (manifest_path.parent / path).resolve()
    return path


def main(argv: list[str] | None = None) -> int:
    default_specs = resources_dir() / "platform-specs.json"
    p = argparse.ArgumentParser(
        description=(
            "QA gate for a finished talking reel. Prints a table, writes JSON, "
            "and optionally extracts a small contact sheet."
        ),
        epilog=(
            "Checks: " + ", ".join(CHECK_IDS) + ". "
            "Exit 0 pass (WARN ok), 2 bad input, 3 FAIL, 4 WARN with --strict. "
            "Timeline keys: hook.duration_s, spine_offset_s, punches[], joins[], "
            "captions.count, captions.ass, loudness.input_i, loudness.output_i."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--video", type=Path, required=True, help="Finished mp4")
    p.add_argument("--manifest", type=Path, help="reel-manifest/1 JSON")
    p.add_argument(
        "--timeline", type=Path,
        help=(
            "finish-reel --emit-json timeline. Discovery order if omitted: "
            "<video>.timeline.json, <stem>.timeline.json, <stem>.finish.json. "
            "A file is used only when it has punches, hook, joins, or captions."
        ),
    )
    p.add_argument(
        "--ass", type=Path,
        help="Burned captions ASS (default: <stem>.ass then <video>.ass)",
    )
    p.add_argument(
        "--proxy", action="store_true",
        help="Treat the file as a 540x960 (or --proxy-size) proxy render",
    )
    p.add_argument(
        "--proxy-size", type=parse_wxh, default=None, metavar="WxH",
        help="Proxy frame size when --proxy (default: half the delivery canvas)",
    )
    p.add_argument("--platform-specs", type=Path, default=default_specs)
    p.add_argument(
        "--platforms",
        type=parse_platforms,
        default=None,
        help="Comma-separated platform keys (default: manifest or instagram_reels,youtube_shorts)",
    )
    p.add_argument("--report", type=Path, help="JSON report path (default: <video_stem>.qa.json)")
    p.add_argument("--frames-dir", type=Path, help="Write downscaled JPEG frames here")
    p.add_argument("--contact-sheet", type=Path, help="Write one contact sheet JPEG here")
    p.add_argument("--max-px", type=int, default=540, help="Longest side of QA frames")
    p.add_argument("--banned-words", type=Path, help="One term per line")
    p.add_argument("--duration-window", type=parse_window, help="MIN,MAX seconds")
    p.add_argument("--strict", action="store_true", help="Treat WARN as a non-zero exit (code 4)")
    p.add_argument("--quiet", action="store_true", help="Print only the verdict line")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ffmpeg/ffprobe commands and exit 0 without writing media",
    )
    args = p.parse_args(argv)

    if not args.video.exists():
        eprint(f"ERROR: video not found: {args.video}")
        return 2
    which_or_exit("ffprobe")
    which_or_exit("ffmpeg")

    manifest = None
    if args.manifest is not None:
        if not args.manifest.exists():
            eprint(f"ERROR: manifest not found: {args.manifest}")
            return 2
        manifest = load_json(args.manifest)
        if not isinstance(manifest, dict):
            eprint("ERROR: manifest is not an object")
            return 2

    if not args.platform_specs.exists():
        eprint(f"ERROR: platform-specs not found: {args.platform_specs}")
        return 2
    specs = load_platform_specs(args.platform_specs)

    platform_names = args.platforms
    if platform_names is None:
        if isinstance(manifest, dict) and manifest.get("platforms"):
            platform_names = list(manifest["platforms"])
        else:
            platform_names = list(DEFAULT_PLATFORMS)
    plat = merge_platforms(specs, platform_names)

    try:
        timeline_path, timeline = discover_timeline(args.video, args.timeline)
    except SystemExit:
        raise
    if timeline is not None and not isinstance(timeline, dict):
        eprint("ERROR: timeline is not an object")
        return 2

    try:
        ass_path = discover_ass(args.video, args.ass, timeline)
    except SystemExit:
        raise
    ass = parse_ass(ass_path) if ass_path is not None else None

    is_proxy = detect_proxy(
        flag=bool(args.proxy),
        timeline=timeline,
        manifest=manifest,
        video=args.video,
    )
    proxy_size = args.proxy_size

    banned_path = args.banned_words
    if banned_path is None and isinstance(manifest, dict):
        qa = manifest.get("qa") if isinstance(manifest.get("qa"), dict) else None
        if qa and qa.get("banned_words_file"):
            banned_path = resolve_maybe(str(qa["banned_words_file"]), args.manifest)
    if banned_path is not None and not banned_path.exists():
        eprint(f"ERROR: banned-words file not found: {banned_path}")
        return 2

    window = args.duration_window
    if window is None and isinstance(manifest, dict) and manifest.get("duration_window"):
        dw = manifest["duration_window"]
        if isinstance(dw, list) and len(dw) == 2:
            try:
                window = (float(dw[0]), float(dw[1]))
            except (TypeError, ValueError):
                eprint("ERROR: manifest duration_window is not two numbers")
                return 2

    report_path = args.report or args.video.with_name(args.video.stem + ".qa.json")
    want_frames = args.frames_dir is not None or args.contact_sheet is not None
    sheet_path = args.contact_sheet
    if want_frames and sheet_path is None:
        sheet_path = args.video.with_suffix(".sheet.jpg")
    frames_dir = args.frames_dir
    if want_frames and frames_dir is None:
        frames_dir = args.video.parent / (args.video.stem + ".frames")

    if args.dry_run:
        probe_media(args.video, dry=True)
        analyze_av(args.video, has_audio=True, dry=True)
        analyze_first_frame(args.video, dry=True)
        if want_frames:
            print(f"[qa-reel] DRY frames -> {frames_dir}")
            print(f"[qa-reel] DRY contact sheet -> {sheet_path}")
        print(f"[qa-reel] DRY report -> {report_path}")
        return 0

    probe = probe_media(args.video, dry=False)
    checks: dict[str, Check] = {}
    duration, has_audio = check_container(
        checks, probe, args.video, plat, dry=False,
        proxy=is_proxy, proxy_size=proxy_size,
    )
    audio_stream = stream_of(probe, "audio")
    audio_dur = as_float((audio_stream or {}).get("duration")) if audio_stream else None
    if audio_dur is None and audio_stream is not None:
        # some muxes omit stream duration; treat as video duration
        audio_dur = duration

    check_duration(checks, duration, window, plat)

    av_err = analyze_av(args.video, has_audio, dry=False)
    first_err = analyze_first_frame(args.video, dry=False)
    check_audio(
        checks, has_audio, duration, audio_dur, av_err, plat, manifest,
        args.video, dry=False,
    )
    check_picture(checks, duration, av_err, first_err, timeline, dry=False)
    check_cadence(checks, duration, timeline, plat, dry=False)
    check_grade(checks, args.video, duration, timeline, dry=False)

    cover_text = None
    if isinstance(manifest, dict) and isinstance(manifest.get("cover"), dict):
        cover_text = manifest["cover"].get("text")
    check_captions(checks, ass, plat, cover_text if isinstance(cover_text, str) else None)
    check_text(checks, manifest, ass, plat, banned_path, timeline)
    check_broll_policy(checks, manifest, timeline, plat, args.video, dry=False)

    missing = [cid for cid in CHECK_IDS if cid not in checks]
    for cid in missing:
        add(checks, cid, "na", None, None, "check not run")

    frame_records: list[dict[str, Any]] = []
    contact_sheet_out: str | None = None
    if want_frames:
        stamps, dropped = thin_timestamps(collect_timestamps(duration, timeline), 24)
        if dropped:
            notice(f"dropped {dropped} frame timestamps to stay at 24")
        assert frames_dir is not None
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i, (t, lab) in enumerate(stamps):
            dest = frames_dir / f"{i:02d}_{safe_label(lab)}_{t:.3f}.jpg"
            extract_qa_frame(args.video, t, dest, args.max_px, dry=False)
            frame_records.append({"t": round(t, 3), "label": lab, "path": str(dest)})
        if sheet_path is not None and frame_records:
            built = build_contact_sheet(frame_records, sheet_path, args.max_px, dry=False)
            if built is not None and built.exists():
                contact_sheet_out = str(built)
                print(f"[qa-reel] contact sheet {built}")

    ordered = [checks[cid] for cid in CHECK_IDS if cid in checks]
    n_pass = sum(1 for c in ordered if c.status == "pass")
    n_fail = sum(1 for c in ordered if c.status == "fail")
    n_warn = sum(1 for c in ordered if c.status == "warn")
    n_na = sum(1 for c in ordered if c.status == "na")
    if n_fail:
        verdict = "fail"
    elif n_warn:
        verdict = "warn"
    else:
        verdict = "pass"
    summary = {
        "pass": n_pass,
        "fail": n_fail,
        "warn": n_warn,
        "na": n_na,
        "verdict": verdict,
    }
    report = {
        "video": str(args.video),
        "generated_by": "qa-reel.py",
        "proxy": bool(is_proxy),
        "verdict": verdict,
        "fails": [c.id for c in ordered if c.status == "fail"],
        "platforms": platform_names,
        "summary": summary,
        "checks": [c.as_dict() for c in ordered],
        "frames": frame_records,
        "contact_sheet": contact_sheet_out,
        "timeline": str(timeline_path) if timeline_path else None,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print_table(ordered, args.quiet, verdict, summary, report_path, is_proxy)

    if n_fail:
        return 3
    if n_warn and args.strict:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
