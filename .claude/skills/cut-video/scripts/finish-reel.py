#!/usr/bin/env python3
"""Phone-ready finish pass for a talking reel.

Takes a talking spine (usually from cut-video.py), optionally a separate
cold-open hook clip, optional B-roll punch-ins, a 3D LUT, an A-roll match
eq, and burned cover text. Writes 1080x1920 8-bit yuv420p H.264+AAC
(or 540x960 in --proxy mode).

The hook is its own input concatenated in FRONT of the finished spine.
Do not pass an overlapping hook range into cut-video.py. That engine
merges overlapping --ranges and the cold-open disappears.

Client LUT path, crop recipe, and cover line are CLI args. Read the
current client's resources/video-pipeline/README.md for the locked cube
and portrait-in-wide-container recipe. This script is generic.

Processing order is locked: extract hook, normalize A-roll, normalize
B-roll, overlay punches, concat hook, cover, captions, loudnorm, encode.

Exit codes:
  0      success
  2      bad arguments or missing input
  3      QA freeze detected on a B-roll window
  other  ffmpeg return code
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


DEFAULT_EQ = "contrast=1.14:saturation=1.35:brightness=-0.015"
DEFAULT_FONT_COLOR = "#F2EDE0"
MAX_BROLL_DUR = 3.0
NINE_SIXTEEN = 16 / 9
TALL_ASPECT_TOL = 0.01
R5_TALL_CROP = "crop=2160:3840:0:128"
CENTER_916_CROP = "crop=iw:iw*16/9:0:(ih-iw*16/9)/2"
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"
RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
DEFAULT_PLATFORM_SPECS = RESOURCES_DIR / "platform-specs.json"
CANVAS_W = 1080
CANVAS_H = 1920
PROXY_W = 540
PROXY_H = 960

_COMMANDS: list[str] = []
_HAS_VIDEOTOOLBOX: bool | None = None


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def pretty_cmd(cmd: list[str]) -> str:
    return " ".join(f"'{c}'" if any(ch in c for ch in " :") else c for c in cmd)


def run(cmd: list[str], dry: bool, *, allow_fail: bool = False) -> int:
    pretty = pretty_cmd(cmd)
    print(f"[finish-reel] {'DRY ' if dry else ''}{pretty}")
    _COMMANDS.append(pretty)
    if dry:
        return 0
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        eprint("[finish-reel] ffmpeg FAILED")
        eprint(r.stderr[-3000:])
        if allow_fail:
            return r.returncode
        raise SystemExit(r.returncode)
    return 0


def probe_stream(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-show_entries", "stream_tags=rotate",
        "-show_entries", "stream_side_data=rotation",
        "-of", "default=noprint_wrappers=1",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = {"width": None, "height": None, "rotation": 0.0}
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if k == "width" and v.isdigit():
            out["width"] = int(v)
        elif k == "height" and v.isdigit():
            out["height"] = int(v)
        elif k == "rotation":
            try:
                out["rotation"] = float(v)
            except ValueError:
                pass
        elif k == "rotate":
            try:
                out["rotation"] = float(v)
            except ValueError:
                pass
    return out


def is_taller_than_916(w: int, h: int, tol: float = TALL_ASPECT_TOL) -> bool:
    if w <= 0 or h <= 0:
        return False
    return h > w * NINE_SIXTEEN * (1.0 + tol)


def upright_tall_crop(w: int, h: int) -> str | None:
    """9:16 crop for an already-upright clip, or None if no crop is needed."""
    if not is_taller_than_916(w, h):
        return None
    if w == 2160 and h == 4096:
        return R5_TALL_CROP
    return CENTER_916_CROP


def r5_after_transpose_crop(src_w: int, src_h: int) -> str | None:
    """Crop to apply AFTER standing-up transpose. None if already 9:16."""
    if src_w <= 0 or src_h <= 0:
        return R5_TALL_CROP
    post_w, post_h = src_h, src_w
    if post_h * 9 == post_w * 16:
        return None
    if post_h <= post_w * NINE_SIXTEEN:
        return None
    if src_w == 4096:
        return R5_TALL_CROP
    return CENTER_916_CROP


def decide_orient(path: Path, forced: str) -> tuple[str, float, int, int]:
    info = probe_stream(path)
    rot = info["rotation"] or 0.0
    w, h = info["width"] or 0, info["height"] or 0
    if forced != "auto":
        return forced, rot, w, h
    abs_rot = abs(rot)
    wide = w > h
    if wide and abs_rot >= 80:
        return "r5-portrait", rot, w, h
    if h > w:
        if abs_rot < 80 and is_taller_than_916(w, h):
            print(f"[finish-reel] {path.name}: tall-spine-crop ({w}x{h})")
            return "tall-spine", rot, w, h
        print(f"[finish-reel] {path.name}: no-crop ({w}x{h})")
        return "none", rot, w, h
    if wide:
        return "landscape-punch", rot, w, h
    return "none", rot, w, h


def escape_lut_path(path: Path) -> str:
    # lut3d treats ':' as a filter-option separator.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", r"\'")


def normalize_cover_newlines(text: str) -> str:
    """Accept a real newline and the two-character sequence backslash-n."""
    return text.replace("\\n", "\n")


def escape_drawtext(text: str) -> str:
    # Newlines last so they become a single \N, not a double-escaped backslash.
    return (
        text.replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def wrap_cover_text(text: str, font_size: int, frame_w: int) -> str:
    """Honor literal \\n; wrap to two lines if estimated width exceeds 0.86*W."""
    raw = text.strip()
    if "\\n" in raw:
        return raw.replace("\\n", "\n")
    if "\n" in raw:
        return raw
    max_width = 0.86 * frame_w
    px_per_char = (0.86 * 1080 / 18.0) * (font_size / 72.0) if font_size else 0.0
    if font_size <= 0 or len(raw) * px_per_char <= max_width:
        return raw
    mid = max(1, len(raw) // 2)
    sp = raw.rfind(" ", 0, mid + 1)
    if sp <= 0:
        sp = raw.find(" ", mid)
    if sp <= 0:
        return raw
    return raw[:sp].rstrip() + "\n" + raw[sp + 1:].lstrip()


def apply_cover_case(text: str, mode: str) -> str:
    if mode == "upper":
        return text.upper()
    if mode == "sentence":
        t = text.strip()
        if not t:
            return t
        return t[0].upper() + t[1:].lower()
    return text


def parse_super(v: str) -> dict:
    """TEXT:at=SEC:dur=SEC  (at on the spine timeline, like --broll)."""
    if ":at=" not in v:
        raise argparse.ArgumentTypeError(f"Bad --super '{v}': expected TEXT:at=SEC:dur=SEC")
    text, rest = v.split(":at=", 1)
    bits = rest.split(":")
    try:
        at = float(bits[0])
        dur = None
        for bit in bits[1:]:
            k, val = bit.split("=", 1)
            if k == "dur":
                dur = float(val)
        if dur is None or dur <= 0 or at < 0:
            raise ValueError
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Bad --super timing in '{v}'") from exc
    return {"text": text.strip(), "at": at, "dur": dur}


def hex_to_drawtext_color(color: str) -> str:
    c = color.strip()
    if c.startswith("#"):
        c = c[1:]
    if len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return f"0x{c.upper()}"
    return color


def r5_transpose(rotation: float) -> str:
    """Pick the transpose that stands a portrait-in-wide-container clip up.

    ffmpeg reports display-matrix +90 on typical R5 portrait takes. With
    -noautorotate, transpose=1 (90 CW) is upside-down; transpose=2 (90 CCW)
    matches autorotate. A -90 matrix uses transpose=1.
    """
    return "transpose=1" if rotation < 0 else "transpose=2"


def orient_filter(
    mode: str,
    rotate: int | None,
    rotation: float = 0.0,
    src_w: int = 0,
    src_h: int = 0,
) -> str:
    parts: list[str] = []
    # --rotate is for a sideways clip with no display-matrix. The r5-portrait
    # recipe already includes its own transpose, so skip extra rotate there.
    if mode != "r5-portrait" and rotate is not None:
        if rotate == 90:
            parts.append("transpose=1")
        elif rotate == 180:
            parts.append("transpose=1,transpose=1")
        elif rotate in {270, -90}:
            parts.append("transpose=2")
    if mode == "r5-portrait":
        parts.append(r5_transpose(rotation))
        crop = r5_after_transpose_crop(src_w, src_h)
        if crop:
            parts.append(crop)
    elif mode == "tall-spine":
        crop = upright_tall_crop(src_w, src_h)
        if crop:
            parts.append(crop)
        elif src_w <= 0:
            parts.append(R5_TALL_CROP)
    elif mode == "landscape-punch":
        parts.append("crop=ih*9/16:ih:(iw-ih*9/16)/2:0")
    return ",".join(parts)


def parse_range(s: str) -> tuple[float, float]:
    try:
        a, b = s.split(":")
        start, end = float(a), float(b)
        if end <= start:
            raise ValueError("end must be > start")
        return start, end
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"Bad --hook-range '{s}': expected start:end in seconds. {exc}"
        ) from exc


def parse_broll(s: str) -> dict:
    # path:at=SEC:dur=SEC[:src=SEC][:kind=clip|still]
    if ":at=" not in s:
        raise argparse.ArgumentTypeError(
            f"Bad --broll '{s}': expected PATH:at=SEC:dur=SEC[:src=SEC][:kind=clip|still]"
        )
    path_part, rest = s.split(":at=", 1)
    path = Path(path_part)
    fields: dict = {"at": None, "dur": None, "src": None, "kind": "clip"}
    bits = rest.split(":")
    try:
        fields["at"] = float(bits[0])
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Bad --broll at= in '{s}'") from exc
    for bit in bits[1:]:
        if "=" not in bit:
            raise argparse.ArgumentTypeError(f"Bad --broll token '{bit}' in '{s}'")
        k, v = bit.split("=", 1)
        if k == "kind":
            if v not in {"clip", "still"}:
                raise argparse.ArgumentTypeError(
                    f"Bad --broll kind '{v}' in '{s}' (clip or still)"
                )
            fields["kind"] = v
            continue
        if k not in {"dur", "src"}:
            raise argparse.ArgumentTypeError(f"Unknown --broll key '{k}' in '{s}'")
        fields[k] = float(v)
    if fields["dur"] is None:
        raise argparse.ArgumentTypeError(f"--broll missing dur= in '{s}'")
    if fields["dur"] <= 0 or fields["at"] < 0:
        raise argparse.ArgumentTypeError(f"Bad --broll timing in '{s}'")
    return {
        "path": path,
        "at": fields["at"],
        "dur": fields["dur"],
        "src": fields["src"],
        "kind": fields["kind"],
    }


def parse_platform_list(s: str) -> list[str]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("--platforms needs at least one id")
    return parts


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def resolve_broll_src(br: dict) -> dict:
    """If src is omitted, take the punch from the middle of the clip.

    Handheld takes often shake at roll-on. A 10s clip used for 2.5s should
    start around 3.75s, not 0. Explicit src= still wins.
    """
    out = dict(br)
    if out["src"] is not None:
        return out
    clip_dur = probe_duration(out["path"])
    punch = out["dur"]
    if clip_dur > punch + 0.4:
        out["src"] = max(0.0, (clip_dur - punch) / 2.0)
        print(
            f"[finish-reel] {out['path'].name}: src default mid-clip "
            f"{out['src']:.2f}s (clip {clip_dur:.1f}s, punch {punch:.1f}s)"
        )
    else:
        out["src"] = 0.0
    return out


def snap_broll_gaps(clips: list[dict], min_aroll: float) -> list[dict]:
    """If A-roll between two punches is shorter than min_aroll, butt them.

    Returning to A-roll for < 3 s reads as a jump cut. Stay on B-roll.
    """
    if not clips or min_aroll <= 0:
        return clips
    ordered = sorted((dict(c) for c in clips), key=lambda c: c["at"])
    out = [ordered[0]]
    for br in ordered[1:]:
        prev = out[-1]
        prev_end = prev["at"] + prev["dur"]
        gap = br["at"] - prev_end
        if 0 <= gap < min_aroll:
            # Overlap ~3 frames so A-roll cannot flash between punches.
            new_at = max(0.0, prev_end - 0.12)
            print(
                f"[finish-reel] butting B-roll '{br['path'].name}' "
                f"gap {gap:.2f}s < min A-roll {min_aroll:.2f}s → at={new_at:.2f} (overlap)"
            )
            br["at"] = new_at
        out.append(br)
    return out


def cover_spine_joins(
    clips: list[dict], joins: list[float], pre: float = 0.40, late_window: float = 0.70
) -> list[dict]:
    """Pull a punch that starts just AFTER an A-roll join so the splice is under B-roll.

    A flash of the talking-head cut before B-roll means the punch is late.
    """
    if not clips or not joins:
        return clips
    out = [dict(c) for c in clips]
    for br in out:
        for j in joins:
            if j <= br["at"] <= j + late_window:
                new_at = max(0.0, j - pre)
                print(
                    f"[finish-reel] covering join {j:.2f}s with "
                    f"{br['path'].name}: at {br['at']:.2f} → {new_at:.2f}"
                )
                br["at"] = new_at
                break
    return out


def ass_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def words_from_transcript(path: Path) -> list[tuple[float, float, str]]:
    data = json.loads(path.read_text())
    out: list[tuple[float, float, str]] = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            tok = str(w.get("word", "")).strip()
            if not tok:
                continue
            out.append((float(w["start"]), float(w["end"]), tok))
    out.sort()
    return out


def _word_start_in_range(ws: float, start: float, end: float) -> bool:
    """Keep a word only when its start falls inside [start, end)."""
    return start <= ws < end


def map_words_to_output(
    words: list[tuple[float, float, str]],
    hook_range: tuple[float, float] | None,
    spine_ranges: list[tuple[float, float]],
) -> list[tuple[float, float, str, int]]:
    """Project source-time words onto the finished timeline (hook + concat spine).

    Only words whose start falls inside a keep range are kept. Each keep range
    gets its own span id so caption cues do not straddle a join. A word that
    starts inside the range is kept even if it was cut short; its end is
    clamped to the range end.
    """
    keep_ranges: list[tuple[float, float]] = []
    if hook_range is not None:
        keep_ranges.append(hook_range)
    keep_ranges.extend(spine_ranges)
    kept = sum(
        1 for ws, _we, _tok in words
        if any(_word_start_in_range(ws, s, e) for s, e in keep_ranges)
    )
    filtered = len(words) - kept
    print(
        f"[finish-reel] caption words: {kept} kept, {filtered} filtered "
        f"of {len(words)} (start must fall inside a keep range)"
    )

    mapped: list[tuple[float, float, str, int]] = []
    span = 0
    hook_dur = 0.0
    if hook_range is not None:
        hs, he = hook_range
        hook_dur = he - hs
        for ws, we, tok in words:
            if not _word_start_in_range(ws, hs, he):
                continue
            we_c = min(we, he)
            mapped.append((max(0.0, ws - hs), max(0.05, we_c - hs), tok, span))
        span += 1
    cursor = hook_dur
    for s, e in spine_ranges:
        for ws, we, tok in words:
            if not _word_start_in_range(ws, s, e):
                continue
            we_c = min(we, e)
            mapped.append(
                (cursor + max(0.0, ws - s), cursor + max(0.05, we_c - s), tok, span)
            )
        cursor += e - s
        span += 1
    mapped.sort()
    return mapped


def _cue_line_count(text: str, max_chars: int) -> int:
    if not text:
        return 0
    lines = 1
    cur = 0
    for w in text.split():
        add = len(w) if cur == 0 else len(w) + 1
        if cur and cur + add > max_chars:
            lines += 1
            cur = len(w)
        else:
            cur += add
    return lines


def wrap_cue_lines(text: str, max_chars: int, max_lines: int) -> str:
    """Wrap cue text to at most max_lines. Real newlines become ASS \\N later."""
    words = text.split()
    if not words or max_chars <= 0:
        return text
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and len(trial) > max_chars:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    if max_lines > 0 and len(lines) > max_lines:
        head = lines[: max_lines - 1]
        tail = " ".join(lines[max_lines - 1 :])
        lines = head + [tail]
    return "\n".join(lines) if lines else text


def _enforce_min_cue(
    cues: list[tuple[float, float, str, int]],
    min_cue: float,
    merge_gap: float = 0.25,
) -> list[tuple[float, float, str, int]]:
    """Lengthen short cues into the following gap, or merge when the gap is small.

    Never merge across a keep-range join (different span id).
    """
    if min_cue <= 0 or not cues:
        return cues
    out: list[list] = [list(c) for c in cues]
    i = 0
    while i < len(out):
        s, e, text, span = out[i]
        dur = e - s
        if dur + 1e-9 >= min_cue:
            i += 1
            continue
        if i + 1 < len(out):
            ns, ne, ntext, nspan = out[i + 1]
            gap = ns - e
            need = min_cue - dur
            if nspan == span and 0 <= gap < merge_gap:
                out[i] = [s, ne, (text + " " + ntext).strip(), span]
                del out[i + 1]
                continue
            if gap > 0:
                out[i][1] = e + min(need, gap)
                if out[i][1] - s + 1e-9 >= min_cue:
                    i += 1
                    continue
            i += 1
            continue
        out[i][1] = s + min_cue
        i += 1
    return [(float(s), float(e), str(t), int(sp)) for s, e, t, sp in out]


def _group_word_cues(
    words: list[tuple[float, float, str]] | list[tuple[float, float, str, int]],
    min_cue: float,
) -> list[tuple[float, float, str]]:
    items: list[tuple[float, float, str, int]] = []
    for item in words:
        ws, we, tok = item[0], item[1], item[2]
        span = item[3] if len(item) > 3 else 0
        items.append((ws, we, tok, span))
    cues: list[tuple[float, float, str]] = []
    for i, (ws, we, tok, span) in enumerate(items):
        end = max(we, ws + min_cue)
        if i + 1 < len(items):
            nws, _nwe, _ntok, nspan = items[i + 1]
            if nspan != span:
                end = min(end, nws)
        if end <= ws:
            end = we if we > ws else ws + 0.05
        cues.append((ws, end, tok))
    return cues


def group_caption_cues(
    words: list[tuple[float, float, str]] | list[tuple[float, float, str, int]],
    max_chars: int = 32,
    max_dur: float = 2.8,
    min_cue: float = 0.8,
    max_lines: int = 2,
    style: str = "phrase",
) -> list[tuple[float, float, str]]:
    """Pack words into cues. Never let a cue span a keep-range join."""
    if style == "word":
        return _group_word_cues(words, min_cue=min_cue)

    packed: list[tuple[float, float, str, int]] = []
    cur: list[str] = []
    start: float | None = None
    prev_end = 0.0
    cur_span = 0
    for item in words:
        ws, we, tok = item[0], item[1], item[2]
        span = item[3] if len(item) > 3 else 0
        if start is None:
            start = ws
            cur_span = span
        trial = " ".join(cur + [tok])
        crossed = bool(cur) and span != cur_span
        too_long = bool(cur) and (we - start) > max_dur
        too_many_lines = bool(cur) and _cue_line_count(trial, max_chars) > max_lines
        if cur and (crossed or too_long or too_many_lines):
            packed.append((start, prev_end, " ".join(cur), cur_span))
            cur = [tok]
            start = ws
            cur_span = span
        else:
            cur.append(tok)
            cur_span = span
        prev_end = we
    if cur and start is not None:
        packed.append((start, prev_end, " ".join(cur), cur_span))

    packed = _enforce_min_cue(packed, min_cue)
    out: list[tuple[float, float, str]] = []
    for s, e, text, _span in packed:
        out.append((s, e, wrap_cue_lines(text, max_chars, max_lines)))
    return out


def write_ass(
    dest: Path,
    cues: list[tuple[float, float, str]],
    font_name: str,
    font_size: int,
    color: str,
    *,
    alignment: int = 2,
    margin_l: int = 70,
    margin_r: int = 70,
    margin_v: int = 220,
    play_res_x: int = CANVAS_W,
    play_res_y: int = CANVAS_H,
) -> None:
    # ASS BGR hex, alpha prefix. #F2EDE0 -> &H00E0EDF2
    c = color.strip().lstrip("#")
    if len(c) == 6:
        bgr = f"&H00{c[4:6]}{c[2:4]}{c[0:2]}".upper()
    else:
        bgr = "&H00E0EDF2"
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{font_size},{bgr},&H00000000,"
        f"&H80000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,"
        f"{alignment},{margin_l},{margin_r},{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for s, e, text in cues:
        if e <= s:
            continue
        lines.append(
            f"Dialogue: 0,{ass_timestamp(s)},{ass_timestamp(e)},Default,,0,0,0,,"
            f"{escape_ass_text(text)}"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    whole = int(s)
    ms = int(round((s - whole) * 1000.0))
    if ms >= 1000:
        whole += 1
        ms -= 1000
    if whole >= 60:
        whole -= 60
        m += 1
    if m >= 60:
        m -= 60
        h += 1
    return f"{h:02d}:{m:02d}:{whole:02d},{ms:03d}"


def cue_plain_text(text: str) -> str:
    """ASS \\N (and a literal backslash-N) become a real line break."""
    return text.replace("\\N", "\n").replace("\\n", "\n")


def write_srt(dest: Path, cues: list[tuple[float, float, str]]) -> None:
    lines: list[str] = []
    n = 1
    for s, e, text in cues:
        if e <= s:
            continue
        lines.append(str(n))
        lines.append(f"{srt_timestamp(s)} --> {srt_timestamp(e)}")
        lines.append(cue_plain_text(text))
        lines.append("")
        n += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def frame_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def qa_scale_filter(max_px: int) -> str:
    return (
        f"scale='if(gt(iw,ih),min(iw,{max_px}),-2)':"
        f"'if(gt(iw,ih),-2,min(ih,{max_px}))'"
    )


def extract_frame(
    src: Path,
    t: float,
    dest: Path,
    max_px: int | None = None,
    *,
    from_end: bool = False,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if from_end:
        cmd += ["-sseof", f"-{max(0.04, t):.3f}"]
    else:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", str(src), "-frames:v", "1", "-q:v", "3", "-an"]
    vf_parts: list[str] = []
    if max_px and max_px > 0:
        vf_parts.append(qa_scale_filter(max_px))
    vf_parts.append("format=yuvj420p")
    cmd += ["-vf", ",".join(vf_parts)]
    cmd.append(str(dest))
    run(cmd, dry=False)


def qa_broll_motion(
    output: Path,
    windows: list[tuple[float, float]],
    qa_dir: Path,
    max_px: int = 540,
) -> None:
    """Fail if a punch-in window is a freeze (identical frames)."""
    qa_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for i, (start, end) in enumerate(windows):
        dur = end - start
        if dur < 0.4:
            continue
        times = [start + 0.08, start + dur * 0.5, max(start + 0.08, end - 0.12)]
        hashes: list[str] = []
        for j, t in enumerate(times):
            frame = qa_dir / f"broll{i:02d}_{j}_{t:.2f}.jpg"
            extract_frame(output, t, frame, max_px=max_px)
            hashes.append(frame_hash(frame))
        if len(set(hashes)) == 1:
            eprint(
                f"[finish-reel] QA FAIL: B-roll window {start:.2f}-{end:.2f}s "
                f"is a freeze (identical frames). Overlay timestamps are wrong."
            )
            failed += 1
        else:
            print(f"[finish-reel] QA motion ok broll[{i}] {start:.2f}-{end:.2f}")
    if failed:
        raise SystemExit(3)


def extract_qa_stills(
    output: Path,
    qa_dir: Path,
    *,
    hook_dur: float,
    max_px: int,
) -> None:
    """Write first, cover (1.0s), hook_end, and last frames, capped on the long side."""
    qa_dir.mkdir(parents=True, exist_ok=True)
    dur = probe_duration(output)
    extract_frame(output, 0.0, qa_dir / "first.jpg", max_px=max_px)
    if dur > 1.0:
        extract_frame(output, 1.0, qa_dir / "cover.jpg", max_px=max_px)
    if hook_dur > 0 and dur > hook_dur:
        extract_frame(
            output, max(0.0, hook_dur - 0.04), qa_dir / "hook_end.jpg", max_px=max_px
        )
    if dur > 0.08:
        extract_frame(
            output, 0.08, qa_dir / "last.jpg", max_px=max_px, from_end=True
        )


def build_vf(
    *,
    orient_mode: str,
    rotate: int | None,
    rotation: float = 0.0,
    lut: Path | None,
    eq: str | None,
    width: int,
    height: int,
    src_w: int = 0,
    src_h: int = 0,
) -> str:
    chunks: list[str] = []
    of = orient_filter(orient_mode, rotate, rotation, src_w, src_h)
    if of:
        chunks.append(of)
    if lut is not None:
        chunks.append(f"lut3d={escape_lut_path(lut)}")
    if eq:
        chunks.append(f"eq={eq}")
    chunks.append(f"scale={width}:{height}:flags=lanczos:force_original_aspect_ratio=disable")
    chunks.append("setsar=1")
    chunks.append("fps=30000/1001")
    chunks.append("format=yuv420p")
    return ",".join(chunks)


def thread_args(n: int, *, filter_complex: bool = False) -> list[str]:
    if not n or n <= 0:
        return []
    out = ["-threads", str(n)]
    if filter_complex:
        out += ["-filter_complex_threads", str(n)]
    return out


def has_videotoolbox() -> bool:
    global _HAS_VIDEOTOOLBOX
    if _HAS_VIDEOTOOLBOX is None:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True,
        )
        _HAS_VIDEOTOOLBOX = bool(re.search(r"\bh264_videotoolbox\b", r.stdout or ""))
    return _HAS_VIDEOTOOLBOX


def resolve_encoder(choice: str, proxy: bool) -> str:
    if choice == "libx264":
        return "libx264"
    if choice == "h264_videotoolbox":
        if has_videotoolbox():
            return "h264_videotoolbox"
        eprint("[finish-reel] h264_videotoolbox not listed; using libx264")
        return "libx264"
    # auto
    if proxy and has_videotoolbox():
        print("[finish-reel] encoder auto: h264_videotoolbox")
        return "h264_videotoolbox"
    if proxy:
        print("[finish-reel] encoder auto: libx264 (h264_videotoolbox not listed)")
    return "libx264"


def video_encode_args(
    encoder: str, *, crf: int, preset: str, proxy: bool
) -> list[str]:
    if encoder == "h264_videotoolbox":
        return [
            "-c:v", "h264_videotoolbox",
            "-b:v", "12M", "-maxrate", "14M", "-bufsize", "24M",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
        ]
    if proxy:
        return [
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-pix_fmt", "yuv420p",
        ]
    return [
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p",
    ]


def normalize(
    src: Path,
    dest: Path,
    *,
    vf: str,
    noautorotate: bool,
    ss: float | None,
    t: float | None,
    audio: bool,
    crf: int,
    preset: str,
    dry: bool,
    threads: int = 0,
    proxy: bool = False,
) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    cmd += thread_args(threads)
    if noautorotate:
        cmd.append("-noautorotate")
    if ss is not None:
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", str(src)]
    if t is not None:
        cmd += ["-t", f"{t:.3f}"]
    cmd += ["-vf", vf]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    else:
        cmd += ["-an"]
    # Intermediates stay libx264 so later filter_complex always has a software file.
    inter_encoder = "libx264"
    cmd += video_encode_args(inter_encoder, crf=crf, preset=preset, proxy=proxy)
    cmd += [
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        str(dest),
    ]
    run(cmd, dry)
    if not dry and not dest.exists():
        raise SystemExit(f"normalize produced no file: {dest}")


def load_platform_specs(path: Path) -> dict:
    if not path.exists():
        eprint(f"ERROR: platform specs not found: {path}")
        raise SystemExit(2)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        eprint(f"ERROR: platform specs are not JSON: {path} ({exc})")
        raise SystemExit(2) from exc


def max_safe_zones(specs: dict, platforms: list[str]) -> dict[str, int]:
    zones = {"top": 0, "bottom": 0, "left": 0, "right": 0}
    plats = specs.get("platforms", {})
    for name in platforms:
        if name not in plats:
            eprint(f"ERROR: unknown platform '{name}'")
            raise SystemExit(2)
        z = plats[name].get("safe_zone_px", {})
        for k in zones:
            try:
                zones[k] = max(zones[k], int(z.get(k, 0)))
            except (TypeError, ValueError):
                pass
    return zones


def caption_layout(
    placement: str,
    safe: dict[str, int],
    margin_v: int | None,
    margin_side: int | None,
) -> dict[str, int]:
    if placement == "custom":
        if margin_v is None or margin_side is None:
            eprint(
                "ERROR: --caption-placement custom requires "
                "--caption-margin-v and --caption-margin-side"
            )
            raise SystemExit(2)
        return {
            "alignment": 2,
            "margin_v": int(margin_v),
            "margin_l": int(margin_side),
            "margin_r": int(margin_side),
        }
    side_l = safe["left"] + 16
    side_r = safe["right"] + 16
    bottom_v = safe["bottom"] + 24
    if placement == "safe-center":
        return {
            "alignment": 5,
            "margin_v": bottom_v,
            "margin_l": side_l,
            "margin_r": side_r,
        }
    return {
        "alignment": 2,
        "margin_v": bottom_v,
        "margin_l": side_l,
        "margin_r": side_r,
    }


def scale_px(px: int, height: int, canvas_h: int = CANVAS_H) -> int:
    if height == canvas_h:
        return int(px)
    return max(0, round(px * height / canvas_h))


def as_float(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def parse_loudnorm_json(blob: str) -> dict | None:
    start = blob.rfind("{")
    end = blob.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(blob[start:end + 1])
    except json.JSONDecodeError:
        return None
    needed = ["input_i", "input_tp", "input_lra", "input_thresh", "target_offset"]
    if not all(k in data for k in needed):
        return None
    return data


def measure_loudnorm(
    wav: Path, i: float, tp: float, lra: float, dry: bool
) -> dict | None:
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", str(wav),
        "-af", f"loudnorm=I={i}:TP={tp}:LRA={lra}:print_format=json",
        "-f", "null", "-",
    ]
    pretty = pretty_cmd(cmd)
    print(f"[finish-reel] {'DRY ' if dry else ''}{pretty}")
    _COMMANDS.append(pretty)
    if dry:
        return None
    r = subprocess.run(cmd, capture_output=True, text=True)
    blob = (r.stderr or "") + (r.stdout or "")
    parsed = parse_loudnorm_json(blob)
    if parsed is None:
        eprint("[finish-reel] loudnorm measurement produced no JSON")
    return parsed


def two_pass_loudnorm_filter(
    i: float, tp: float, lra: float, measured: dict | None
) -> str:
    if measured is None:
        return (
            f"loudnorm=I={i}:TP={tp}:LRA={lra}:measured_I=<pass1>:"
            f"measured_TP=<pass1>:measured_LRA=<pass1>:measured_thresh=<pass1>:"
            f"offset=<pass1>:linear=true:print_format=summary,aresample=48000"
        )
    return (
        f"loudnorm=I={i}:TP={tp}:LRA={lra}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true:print_format=summary"
        f",aresample=48000"
    )


def single_pass_loudnorm_filter(i: float, tp: float, lra: float) -> str:
    return f"loudnorm=I={i}:TP={tp}:LRA={lra},aresample=48000"


def render_mix_wav(
    spine_norm: Path,
    hook_norm: Path | None,
    denoise: str,
    dest: Path,
    dry: bool,
    threads: int,
) -> bool:
    """Audio-only mix of hook+spine (B-roll is silent). Returns False on failure."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    cmd += thread_args(threads)
    cmd += ["-i", str(spine_norm)]
    if hook_norm is not None:
        cmd += ["-i", str(hook_norm)]
        fc = "[1:a][0:a]concat=n=2:v=0:a=1[a0]"
        lbl = "[a0]"
    else:
        fc = "[0:a]anull[a0]"
        lbl = "[a0]"
    if denoise == "light":
        fc += f";{lbl}afftdn=nf=-25[a1]"
        lbl = "[a1]"
    cmd += [
        "-filter_complex", fc, "-map", lbl, "-vn",
        "-c:a", "pcm_s16le", "-ar", "48000",
        str(dest),
    ]
    rc = run(cmd, dry, allow_fail=True)
    return rc == 0


def punch_super_text(br: dict, supers: list[dict]) -> str | None:
    start = br["at"]
    end = br["at"] + br["dur"]
    for sp in supers:
        if start <= sp["at"] < end:
            return sp["text"]
    return None


def main() -> int:
    global _COMMANDS
    _COMMANDS = []

    p = argparse.ArgumentParser(
        description=(
            "Finish a talking reel: LUT, A-roll eq, 9:16, B-roll punch-ins, "
            "hook concat, cover text, 1080x1920 yuv420p."
        )
    )
    p.add_argument("--spine", type=Path, required=True, help="Talking spine (cut-video.py output)")
    p.add_argument("--output", type=Path, required=True, help="Final phone-ready mp4")
    p.add_argument("--hook-source", type=Path, help="Camera file to extract the hook from")
    p.add_argument("--hook-range", type=parse_range, help="Hook start:end on --hook-source")
    p.add_argument("--hook", type=Path, help="Already-extracted hook clip (alternative to --hook-source)")
    p.add_argument("--lut", type=Path, help="3D LUT cube. Applied before text and before eq.")
    p.add_argument("--skip-lut", action="store_true", help="Skip LUT even if --lut is passed")
    p.add_argument("--eq", default=DEFAULT_EQ, help=f"A-roll eq AFTER LUT (default {DEFAULT_EQ})")
    p.add_argument("--no-eq", action="store_true", help="Do not apply A-roll match eq")
    p.add_argument("--cover-text", default="", help="Public-safe cover line, burned first N seconds")
    p.add_argument("--cover-seconds", type=float, default=2.0, help="Cover text duration (default 2.0)")
    p.add_argument(
        "--cover-case",
        choices=["as-is", "upper", "sentence"],
        default="as-is",
        help="Cover text casing (default as-is).",
    )
    p.add_argument("--font", type=Path, help="Font file (or set FINISH_REEL_FONT)")
    p.add_argument("--font-color", default=DEFAULT_FONT_COLOR, help="Cover color (default #F2EDE0)")
    p.add_argument("--font-size", type=int, default=72, help="Cover font size (default 72)")
    p.add_argument(
        "--broll",
        action="append",
        default=[],
        type=parse_broll,
        help="PATH:at=SEC:dur=SEC[:src=SEC][:kind=clip|still] on the spine timeline (before hook). Repeatable. dur < --max-broll-dur.",
    )
    p.add_argument(
        "--max-broll-dur",
        type=float,
        default=MAX_BROLL_DUR,
        help="Longest allowed punch-in in seconds (default 3.0; slow-push stills read well at 3.5 to 4).",
    )
    p.add_argument(
        "--super",
        action="append",
        default=[],
        type=parse_super,
        dest="supers",
        help="TEXT:at=SEC:dur=SEC on the spine timeline (before hook). Small annotation in the caption font, upper third. Repeatable.",
    )
    p.add_argument("--super-size", type=int, default=44, help="Super font size at 1080x1920 (default 44)")
    p.add_argument(
        "--broll-no-eq",
        action="store_true",
        help="Do not apply the A-roll match eq to B-roll. Default is to match.",
    )
    p.add_argument(
        "--broll-no-lut",
        action="store_true",
        help=(
            "Apply --lut to the A-roll and hook only; B-roll keeps its own color. "
            "For a log spine with Rec.709 stills or phone clips as punches."
        ),
    )
    p.add_argument(
        "--transcript",
        type=Path,
        help="Word-level whisper JSON. Burns dialogue captions on the finished timeline.",
    )
    p.add_argument(
        "--spine-range",
        type=parse_range,
        action="append",
        default=[],
        help="Source keep range 'start:end' matching cut-video.py --range. Repeat. Required with --transcript.",
    )
    p.add_argument(
        "--caption-font",
        type=Path,
        help="Font file for dialogue captions (or FINISH_REEL_CAPTION_FONT). Sans, not the cover serif.",
    )
    p.add_argument(
        "--caption-font-name",
        default="Arial",
        help="ASS Fontname (default Arial). Must match --caption-font family.",
    )
    p.add_argument(
        "--caption-size",
        type=int,
        default=42,
        help="Dialogue caption font size at 1080x1920 (default 42).",
    )
    p.add_argument(
        "--caption-style",
        choices=["phrase", "word"],
        default="phrase",
        help="phrase (default) packs 1-2 line cues; word writes one Dialogue per word (min 0.35s).",
    )
    p.add_argument(
        "--caption-min-cue",
        type=float,
        default=0.8,
        help="Minimum cue duration in seconds (default 0.8). Word style uses 0.35 unless this flag is passed.",
    )
    p.add_argument(
        "--caption-max-cue",
        type=float,
        default=2.8,
        help="Maximum phrase-cue duration in seconds (default 2.8).",
    )
    p.add_argument(
        "--caption-max-chars",
        type=int,
        default=32,
        help="Wrap a cue onto a second line above this many characters (default 32).",
    )
    p.add_argument(
        "--caption-max-lines",
        type=int,
        default=2,
        help="Maximum lines per cue (default 2).",
    )
    p.add_argument(
        "--caption-placement",
        choices=["safe-lower", "safe-center", "custom"],
        default="safe-lower",
        help="Caption position (default safe-lower).",
    )
    p.add_argument(
        "--caption-margin-v",
        type=int,
        default=None,
        help="Custom MarginV in px from the bottom (placement=custom).",
    )
    p.add_argument(
        "--caption-margin-side",
        type=int,
        default=None,
        help="Custom MarginL/MarginR in px (placement=custom).",
    )
    p.add_argument(
        "--platforms",
        type=parse_platform_list,
        default="instagram_reels,youtube_shorts",
        help="Comma-separated platform ids (default instagram_reels,youtube_shorts).",
    )
    p.add_argument(
        "--platform-specs",
        type=Path,
        default=DEFAULT_PLATFORM_SPECS,
        help=f"Platform safe-zone JSON (default {DEFAULT_PLATFORM_SPECS}).",
    )
    p.add_argument(
        "--no-captions",
        action="store_true",
        help="Skip burned dialogue captions even if --transcript is passed.",
    )
    p.add_argument(
        "--ass-out",
        type=Path,
        default=None,
        help="Keep the ASS file here. Default: <output>.ass when captions are on.",
    )
    p.add_argument(
        "--srt-out",
        type=Path,
        default=None,
        help="Write an SRT sidecar from the same cues as the ASS. Default: <output>.srt when captions are on.",
    )
    p.add_argument(
        "--cover-frame",
        type=Path,
        default=None,
        help="JPEG of the title frame at 0.5s, full output size, quality 3. Default: <output>.cover.jpg.",
    )
    p.add_argument(
        "--qa-dir",
        type=Path,
        help="Write motion-check frames here. Exit 3 if a B-roll window is a freeze.",
    )
    p.add_argument(
        "--qa-max-px",
        type=int,
        default=540,
        help="Longest side of any QA frame in px (default 540).",
    )
    p.add_argument(
        "--min-aroll",
        type=float,
        default=3.0,
        help="If A-roll between two B-roll punches is shorter than this, butt the punches (default 3.0).",
    )
    p.add_argument(
        "--join",
        type=float,
        action="append",
        default=[],
        help="Spine time of an A-roll jump (cut-video concat). Repeat. Nearby B-roll is pulled earlier to cover it.",
    )
    p.add_argument(
        "--cover-anchor",
        choices=["top", "center"],
        default="center",
        help="Cover text vertical placement. Default center = Instagram cover frame.",
    )
    p.add_argument(
        "--cover-darken",
        type=float,
        default=0.0,
        help="Dim the picture so cream cover text reads (0–0.5). 0 = off.",
    )
    p.add_argument(
        "--cover-darken-seconds",
        type=float,
        default=0.04,
        help="How long to dim. Default one frame (~0.04s) for an IG cover still. Not the whole cover title.",
    )
    p.add_argument(
        "--orient",
        choices=["auto", "none", "r5-portrait", "landscape-punch", "tall-spine"],
        default="auto",
        help="Per-clip orientation. auto probes display-matrix / rotate / WxH.",
    )
    p.add_argument(
        "--loudnorm-mode",
        choices=["two-pass", "single", "off"],
        default="two-pass",
        help="Loudness pass: two-pass (default), single, or off.",
    )
    p.add_argument(
        "--loudnorm-i",
        type=float,
        default=-16.0,
        help="loudnorm integrated target I (default -16).",
    )
    p.add_argument(
        "--loudnorm-tp",
        type=float,
        default=-1.5,
        help="loudnorm true peak TP (default -1.5).",
    )
    p.add_argument(
        "--loudnorm-lra",
        type=float,
        default=11.0,
        help="loudnorm LRA (default 11).",
    )
    p.add_argument(
        "--loudnorm",
        action="store_true",
        help="Alias: keep loudness on (two-pass unless --loudnorm-mode says otherwise).",
    )
    p.add_argument(
        "--no-loudnorm",
        action="store_true",
        help="Alias for --loudnorm-mode off.",
    )
    p.add_argument(
        "--denoise",
        choices=["off", "light"],
        default="off",
        help="light inserts afftdn=nf=-25 before loudnorm. For phone or distant mics only. Default off.",
    )
    p.add_argument(
        "--proxy",
        action="store_true",
        help="540x960 preview. Same grade, captions, cover, punches, loudness. Encoder auto.",
    )
    p.add_argument(
        "--encoder",
        choices=["auto", "libx264", "h264_videotoolbox"],
        default="auto",
        help="Video encoder (default auto). Proxy auto prefers h264_videotoolbox.",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=0,
        help="Pass -threads N and -filter_complex_threads N to ffmpeg (0 = default).",
    )
    p.add_argument(
        "--emit-json",
        type=Path,
        default=None,
        help="Write a timeline JSON (final-timeline times) to this path.",
    )
    p.add_argument(
        "--rotate",
        type=int,
        choices=[90, 180, 270, -90],
        help="Extra rotate for a sideways clip the brief said to rotate. Do not guess.",
    )
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--crf", type=int, default=18)
    p.add_argument("--preset", default="fast")
    p.add_argument("--force", action="store_true", help="Allow overwriting --output")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.cover_text and "\\" in args.cover_text:
        eprint(
            "ERROR: --cover-text contains a backslash. "
            "The engine wraps long lines; do not pass escape sequences."
        )
        return 2

    if args.no_loudnorm:
        args.loudnorm_mode = "off"
    elif args.loudnorm and args.loudnorm_mode == "off":
        args.loudnorm_mode = "two-pass"

    if args.caption_style == "word":
        passed_min = any(
            a == "--caption-min-cue" or a.startswith("--caption-min-cue=")
            for a in sys.argv
        )
        if not passed_min:
            args.caption_min_cue = 0.35

    if isinstance(args.platforms, str):
        args.platforms = parse_platform_list(args.platforms)

    if args.proxy:
        args.width = PROXY_W
        args.height = PROXY_H

    encoder = resolve_encoder(args.encoder, args.proxy)
    norm_preset = "ultrafast" if args.proxy else args.preset
    norm_crf = 28 if args.proxy else max(14, args.crf - 2)

    specs = load_platform_specs(args.platform_specs)
    safe = max_safe_zones(specs, list(args.platforms))
    cap_layout = caption_layout(
        args.caption_placement, safe, args.caption_margin_v, args.caption_margin_side
    )

    for br in args.broll:
        if br["dur"] >= args.max_broll_dur:
            eprint(
                f"ERROR: --broll {br['path'].name} dur={br['dur']} >= --max-broll-dur {args.max_broll_dur}"
            )
            return 2

    if not args.spine.exists():
        eprint(f"ERROR: spine not found: {args.spine}")
        return 2
    if args.hook_source and not args.hook_range:
        eprint("ERROR: --hook-source requires --hook-range")
        return 2
    if args.hook_range and not args.hook_source and not args.hook:
        eprint("ERROR: --hook-range requires --hook-source")
        return 2
    if args.hook and not args.hook.exists():
        eprint(f"ERROR: hook clip not found: {args.hook}")
        return 2
    if args.hook_source and not args.hook_source.exists():
        eprint(f"ERROR: hook source not found: {args.hook_source}")
        return 2
    for br in args.broll:
        if not br["path"].exists():
            eprint(f"ERROR: b-roll not found: {br['path']}")
            return 2
    lut = None if args.skip_lut else args.lut
    if lut is not None and not lut.exists():
        eprint(f"ERROR: LUT not found: {lut}")
        return 2

    if args.output.exists() and not args.force:
        eprint(f"ERROR: output exists (will not overwrite vN): {args.output}")
        eprint("Bump the _vN in the filename, or pass --force.")
        return 2

    font = args.font
    if font is None:
        env_font = os.environ.get("FINISH_REEL_FONT")
        if env_font:
            font = Path(env_font)
    if args.cover_text and (font is None or not font.exists()):
        eprint("ERROR: --cover-text requires --font or FINISH_REEL_FONT pointing at a real file")
        return 2
    captions_on = bool(args.transcript and not args.no_captions)
    if captions_on:
        if not args.transcript.exists():
            eprint(f"ERROR: transcript not found: {args.transcript}")
            return 2
        if not args.spine_range:
            eprint("ERROR: --transcript requires --spine-range (the cut-video.py keep ranges)")
            return 2
        if args.ass_out is None:
            args.ass_out = args.output.with_suffix(".ass")
        if args.srt_out is None:
            args.srt_out = args.output.with_suffix(".srt")
    if args.cover_frame is None:
        args.cover_frame = args.output.with_suffix(".cover.jpg")

    eq = None if args.no_eq else args.eq
    args.broll = snap_broll_gaps(
        cover_spine_joins(
            [resolve_broll_src(br) for br in args.broll], list(args.join)
        ),
        args.min_aroll,
    )
    work = Path(tempfile.mkdtemp(prefix="finish-reel-"))
    print(f"[finish-reel] work {work}")

    hook_dur = 0.0
    if args.hook_range:
        hook_dur = args.hook_range[1] - args.hook_range[0]
    elif args.hook:
        hook_dur = probe_duration(args.hook)

    cover_font_size = args.font_size
    super_font_size = args.super_size
    if args.width != CANVAS_W and CANVAS_W:
        scale = args.width / CANVAS_W
        cover_font_size = max(8, int(round(args.font_size * scale)))
        super_font_size = max(8, int(round(args.super_size * scale)))

    loudness_mode = args.loudnorm_mode
    measured: dict | None = None
    cues: list[tuple[float, float, str]] = []
    ass_path: Path | None = args.ass_out if captions_on else None
    srt_path: Path | None = args.srt_out if captions_on else None
    cover_frame_path: Path | None = args.cover_frame

    try:
        # --- hook ---
        hook_norm = None
        if args.hook_source and args.hook_range:
            hs, he = args.hook_range
            mode, probed_rot, src_w, src_h = decide_orient(args.hook_source, args.orient)
            print(
                f"[finish-reel] hook-source orient={mode} "
                f"matrix={probed_rot} rotate={args.rotate} src={src_w}x{src_h}"
            )
            vf = build_vf(
                orient_mode=mode, rotate=args.rotate, rotation=probed_rot,
                lut=lut, eq=eq, width=args.width, height=args.height,
                src_w=src_w, src_h=src_h,
            )
            hook_norm = work / "hook.mp4"
            normalize(
                args.hook_source, hook_norm,
                vf=vf, noautorotate=(mode == "r5-portrait"),
                ss=hs, t=he - hs, audio=True,
                crf=norm_crf, preset=norm_preset, dry=args.dry_run,
                threads=args.threads, proxy=args.proxy,
            )
        elif args.hook:
            mode, probed_rot, src_w, src_h = decide_orient(args.hook, args.orient)
            print(
                f"[finish-reel] hook-clip orient={mode} "
                f"matrix={probed_rot} rotate={args.rotate} src={src_w}x{src_h}"
            )
            vf = build_vf(
                orient_mode=mode, rotate=args.rotate, rotation=probed_rot,
                lut=lut, eq=eq, width=args.width, height=args.height,
                src_w=src_w, src_h=src_h,
            )
            hook_norm = work / "hook.mp4"
            normalize(
                args.hook, hook_norm,
                vf=vf, noautorotate=(mode == "r5-portrait"),
                ss=None, t=None, audio=True,
                crf=norm_crf, preset=norm_preset, dry=args.dry_run,
                threads=args.threads, proxy=args.proxy,
            )

        # --- spine (A-roll: LUT + eq) ---
        spine_mode, spine_rot, spine_w, spine_h = decide_orient(args.spine, args.orient)
        print(
            f"[finish-reel] spine orient={spine_mode} "
            f"matrix={spine_rot} rotate={args.rotate} src={spine_w}x{spine_h}"
        )
        spine_vf = build_vf(
            orient_mode=spine_mode, rotate=args.rotate, rotation=spine_rot,
            lut=lut, eq=eq, width=args.width, height=args.height,
            src_w=spine_w, src_h=spine_h,
        )
        spine_norm = work / "spine.mp4"
        normalize(
            args.spine, spine_norm,
            vf=spine_vf, noautorotate=(spine_mode == "r5-portrait"),
            ss=None, t=None, audio=True,
            crf=norm_crf, preset=norm_preset, dry=args.dry_run,
            threads=args.threads, proxy=args.proxy,
        )

        # --- b-roll (LUT + same match eq as A-roll, unless --broll-no-eq) ---
        broll_eq = None if args.broll_no_eq else eq
        broll_lut = None if args.broll_no_lut else lut
        if args.broll_no_lut and lut is not None:
            print("[finish-reel] B-roll: LUT off (--broll-no-lut); A-roll and hook still graded")
        broll_norm: list[tuple[dict, Path]] = []
        for i, br in enumerate(args.broll):
            mode, probed_rot, src_w, src_h = decide_orient(br["path"], args.orient)
            print(
                f"[finish-reel] broll[{i}] {br['path'].name} "
                f"orient={mode} matrix={probed_rot} "
                f"at={br['at']:.2f} dur={br['dur']:.2f} src={br['src']:.2f} "
                f"eq={'off' if broll_eq is None else broll_eq} kind={br.get('kind', 'clip')}"
            )
            vf = build_vf(
                orient_mode=mode, rotate=args.rotate, rotation=probed_rot,
                lut=broll_lut, eq=broll_eq, width=args.width, height=args.height,
                src_w=src_w, src_h=src_h,
            )
            dest = work / f"broll_{i:02d}.mp4"
            normalize(
                br["path"], dest,
                vf=vf, noautorotate=(mode == "r5-portrait"),
                ss=br["src"], t=br["dur"], audio=False,
                crf=norm_crf, preset=norm_preset, dry=args.dry_run,
                threads=args.threads, proxy=args.proxy,
            )
            broll_norm.append((br, dest))

        # --- overlay + concat + cover ---
        args.output.parent.mkdir(parents=True, exist_ok=True)
        inputs: list[str] = ["-i", str(spine_norm)]
        idx = 1
        b_labels = []
        for _, dest in broll_norm:
            inputs += ["-i", str(dest)]
            b_labels.append(idx)
            idx += 1
        hook_idx = None
        if hook_norm is not None:
            inputs += ["-i", str(hook_norm)]
            hook_idx = idx

        video_fc: list[str] = []
        audio_fc: list[str] = []
        current = "0:v"
        for i, ((br, _), in_idx) in enumerate(zip(broll_norm, b_labels)):
            out_lbl = f"ov{i}"
            shifted = f"b{i}"
            start, end = br["at"], br["at"] + br["dur"]
            video_fc.append(
                f"[{in_idx}:v]setpts=PTS-STARTPTS+{start:.3f}/TB[{shifted}]"
            )
            video_fc.append(
                f"[{current}][{shifted}]overlay=0:0:"
                f"enable='gte(t,{start:.3f})*lt(t,{end:.3f})':repeatlast=0[{out_lbl}]"
            )
            current = out_lbl
        video_after_overlay = f"[{current}]" if current != "0:v" else "[0:v]"
        audio_spine = "[0:a]"

        if hook_idx is not None:
            video_fc.append(
                f"[{hook_idx}:v]{video_after_overlay}concat=n=2:v=1:a=0[catv]"
            )
            audio_fc.append(
                f"[{hook_idx}:a]{audio_spine}concat=n=2:v=0:a=1[cata]"
            )
            v_lbl, a_lbl = "[catv]", "[cata]"
        else:
            video_fc.append(f"{video_after_overlay}null[catv]")
            audio_fc.append(f"{audio_spine}anull[cata]")
            v_lbl, a_lbl = "[catv]", "[cata]"

        if args.cover_text:
            cased = apply_cover_case(args.cover_text.strip(), args.cover_case)
            wrapped = wrap_cover_text(cased, cover_font_size, args.width)
            if "\n" in wrapped:
                print(
                    "[finish-reel] cover wrap: "
                    + " | ".join(wrapped.split("\n"))
                )
            if "\n" in wrapped:
                cover_txt = work / "cover.txt"
                if not args.dry_run:
                    cover_txt.write_text(wrapped + "\n", encoding="utf-8")
                text_opt = f"textfile={escape_lut_path(cover_txt)}"
            else:
                text_opt = f"text='{escape_drawtext(wrapped)}'"
            color = hex_to_drawtext_color(args.font_color)
            fontfile = escape_lut_path(font)
            if args.cover_anchor == "center":
                y_expr = "(h-text_h)/2"
            else:
                top_y = scale_px(safe["top"], args.height) + scale_px(24, args.height)
                y_expr = str(top_y)
            src = v_lbl
            if args.cover_darken > 0:
                dim = min(args.cover_darken, 0.5)
                dim_t = max(0.03, min(args.cover_darken_seconds, args.cover_seconds))
                video_fc.append(
                    f"{src}eq=brightness=-{dim:.3f}:"
                    f"enable='lt(t,{dim_t:.3f})'[dimv]"
                )
                src = "[dimv]"
            video_fc.append(
                f"{src}drawtext=fontfile={fontfile}:{text_opt}:"
                f"fontcolor={color}:fontsize={cover_font_size}:"
                f"x=(w-text_w)/2:y={y_expr}:text_align=C:"
                f"enable='between(t,0,{args.cover_seconds:.3f})'[covv]"
            )
            v_lbl = "[covv]"

        if args.supers:
            sup_font = args.caption_font
            if sup_font is None and os.environ.get("FINISH_REEL_CAPTION_FONT"):
                sup_font = Path(os.environ["FINISH_REEL_CAPTION_FONT"])
            if sup_font is None or not Path(sup_font).exists():
                sup_font = font
            sup_fontfile = escape_lut_path(Path(sup_font))
            sup_color = hex_to_drawtext_color(args.font_color)
            sup_y = max(
                int(args.height * 0.12),
                scale_px(safe["top"], args.height) + scale_px(24, args.height),
            )
            for i, sp in enumerate(args.supers):
                sup_txt = work / f"super_{i:02d}.txt"
                if not args.dry_run:
                    sup_txt.write_text(sp["text"] + "\n", encoding="utf-8")
                t0 = hook_dur + sp["at"]
                t1 = t0 + sp["dur"]
                video_fc.append(
                    f"{v_lbl}drawtext=fontfile={sup_fontfile}:textfile={escape_lut_path(sup_txt)}:"
                    f"fontcolor={sup_color}:fontsize={super_font_size}:"
                    f"box=1:boxcolor=black@0.38:boxborderw=16:"
                    f"x=(w-text_w)/2:y={sup_y}:text_align=C:"
                    f"enable='between(t,{t0:.3f},{t1:.3f})'[sup{i}]"
                )
                v_lbl = f"[sup{i}]"
                print(f"[finish-reel] super[{i}] {t0:.2f}-{t1:.2f} '{sp['text']}'")

        caption_font = args.caption_font
        if caption_font is None:
            env_cf = os.environ.get("FINISH_REEL_CAPTION_FONT")
            if env_cf:
                caption_font = Path(env_cf)
        v_map = v_lbl
        if captions_on:
            words = words_from_transcript(args.transcript)
            mapped = map_words_to_output(words, args.hook_range, list(args.spine_range))
            cues = group_caption_cues(
                mapped,
                max_chars=args.caption_max_chars,
                max_dur=args.caption_max_cue,
                min_cue=args.caption_min_cue,
                max_lines=args.caption_max_lines,
                style=args.caption_style,
            )
            print(f"[finish-reel] captions {len(cues)} cues from {len(mapped)} words")
            if ass_path is not None and not args.dry_run:
                write_ass(
                    ass_path, cues, args.caption_font_name, args.caption_size, args.font_color,
                    alignment=cap_layout["alignment"],
                    margin_l=cap_layout["margin_l"],
                    margin_r=cap_layout["margin_r"],
                    margin_v=cap_layout["margin_v"],
                )
                if srt_path is not None:
                    write_srt(srt_path, cues)
                    print(f"[finish-reel] wrote {srt_path}")
                ass_esc = escape_lut_path(ass_path)
                extra = ""
                if caption_font is not None and caption_font.exists():
                    extra = f":fontsdir={escape_lut_path(caption_font.parent)}"
                video_fc.append(f"{v_lbl}subtitles={ass_esc}{extra}[capv]")
                v_map = "[capv]"
            elif ass_path is not None and args.dry_run:
                ass_esc = escape_lut_path(ass_path)
                extra = ""
                if caption_font is not None and caption_font.exists():
                    extra = f":fontsdir={escape_lut_path(caption_font.parent)}"
                video_fc.append(f"{v_lbl}subtitles={ass_esc}{extra}[capv]")
                v_map = "[capv]"

        if args.denoise == "light":
            audio_fc.append(f"{a_lbl}afftdn=nf=-25[dena]")
            a_lbl = "[dena]"
            print("[finish-reel] denoise=light (afftdn=nf=-25) before loudnorm")

        a_map = a_lbl
        wav_path = work / "mix.wav"

        if loudness_mode == "two-pass":
            ok = render_mix_wav(
                spine_norm, hook_norm, args.denoise, wav_path, args.dry_run, args.threads
            )
            if args.dry_run:
                measured = None
            elif ok:
                measured = measure_loudnorm(
                    wav_path, args.loudnorm_i, args.loudnorm_tp, args.loudnorm_lra, args.dry_run
                )
            if not args.dry_run and measured is None:
                eprint("[finish-reel] loudnorm measurement failed; falling back to single-pass")
                loudness_mode = "single"

        if loudness_mode == "two-pass":
            wav_idx = sum(1 for x in inputs if x == "-i")
            inputs += ["-i", str(wav_path)]
            ln = two_pass_loudnorm_filter(
                args.loudnorm_i, args.loudnorm_tp, args.loudnorm_lra, measured
            )
            # Mix WAV already has denoise if requested. Video graph only.
            fc_all = list(video_fc)
            fc_all.append(f"[{wav_idx}:a]{ln}[outa]")
            a_map = "[outa]"
            filter_str = ";".join(fc_all)
        elif loudness_mode == "single":
            fc_all = list(video_fc) + list(audio_fc)
            ln = single_pass_loudnorm_filter(
                args.loudnorm_i, args.loudnorm_tp, args.loudnorm_lra
            )
            fc_all.append(f"{a_lbl}{ln}[outa]")
            a_map = "[outa]"
            filter_str = ";".join(fc_all)
        else:
            fc_all = list(video_fc) + list(audio_fc)
            a_map = a_lbl
            filter_str = ";".join(fc_all)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *thread_args(args.threads, filter_complex=True),
            *inputs,
            "-filter_complex", filter_str,
            "-map", v_map, "-map", a_map,
            *video_encode_args(encoder, crf=args.crf, preset=args.preset, proxy=args.proxy),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(args.output),
        ]
        run(cmd, args.dry_run)
        duration_s = 0.0
        if not args.dry_run:
            print(f"[finish-reel] wrote {args.output}")
            duration_s = probe_duration(args.output)
            if cover_frame_path is not None and args.output.is_file():
                extract_frame(args.output, 0.5, cover_frame_path, max_px=None)
                print(f"[finish-reel] wrote {cover_frame_path}")
            if args.qa_dir:
                if args.broll:
                    windows = [
                        (hook_dur + br["at"], hook_dur + br["at"] + br["dur"])
                        for br in args.broll
                    ]
                    qa_broll_motion(
                        args.output, windows, args.qa_dir, max_px=args.qa_max_px
                    )
                extract_qa_stills(
                    args.output, args.qa_dir, hook_dur=hook_dur, max_px=args.qa_max_px
                )
            if args.emit_json:
                punches = []
                for br in args.broll:
                    punches.append({
                        "at_spine": br["at"],
                        "at_final": hook_dur + br["at"],
                        "dur": br["dur"],
                        "path": str(br["path"]),
                        "kind": br.get("kind", "clip"),
                        "src": br.get("src"),
                        "super": punch_super_text(br, list(args.supers)),
                    })
                payload = {
                    "output": str(args.output),
                    "hook": {"present": hook_norm is not None, "duration_s": hook_dur},
                    "spine_offset_s": hook_dur,
                    "punches": punches,
                    "joins": [hook_dur + j for j in args.join],
                    "captions": {
                        "count": len(cues),
                        "ass": str(ass_path) if ass_path else None,
                        "srt": str(srt_path) if srt_path else None,
                        "style": args.caption_style,
                        "margin_v": cap_layout["margin_v"],
                        "margin_l": cap_layout["margin_l"],
                        "margin_r": cap_layout["margin_r"],
                        "alignment": cap_layout["alignment"],
                    },
                    "cover": {
                        "text": args.cover_text,
                        "seconds": args.cover_seconds,
                        "anchor": args.cover_anchor,
                        "frame": str(cover_frame_path) if cover_frame_path else None,
                    },
                    "loudness": {
                        "mode": loudness_mode,
                        "measured_i": as_float(measured["input_i"]) if measured else None,
                        "measured_tp": as_float(measured["input_tp"]) if measured else None,
                        "measured_lra": as_float(measured["input_lra"]) if measured else None,
                        "output_i": as_float(measured.get("output_i")) if measured else None,
                        "output_tp": as_float(measured.get("output_tp")) if measured else None,
                        "output_lra": as_float(measured.get("output_lra")) if measured else None,
                        "target_i": args.loudnorm_i,
                    },
                    "encoder": encoder,
                    "proxy": bool(args.proxy),
                    "duration_s": duration_s,
                    "commands": list(_COMMANDS),
                }
                args.emit_json.parent.mkdir(parents=True, exist_ok=True)
                args.emit_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                print(f"[finish-reel] wrote {args.emit_json}")
        return 0
    finally:
        if not args.dry_run:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
