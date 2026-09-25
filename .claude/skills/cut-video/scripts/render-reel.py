#!/usr/bin/env python3
"""Execute a reel manifest from cut through finish, QA, notes, and delivery.

Usage:
    render-reel.py --manifest reel.json [--proxy] [--version N] [--dry-run]
                   [--no-deliver] [--no-qa] [--lock-file PATH] [--work-dir DIR]
                   [--keep-work] [--ledger PATH] [--no-ledger] [--style PATH]
                   [--strict]

Exit codes:
    0  rendered
    2  manifest or input problem (invalid manifest, missing file, transcript
       without words, unsourced broll, or --strict preflight lint)
    3  a downstream script failed
    4  rendered but the QA gate reported a FAIL (the file exists; RUNNOTES
       say what failed)
    5  lock timeout

Steps, in order:
    1. Load and validate the manifest; apply schema defaults; resolve paths.
    2. Preflight (every referenced file, words[], ffmpeg/ffprobe, output_dir).
    3. Pick a version; refuse to overwrite.
    4. Color detection (YMIN) for source.color auto and broll color auto.
    5. Hook lift (subtract a same-source prepend hook from spine ranges).
    6. Hard out (clamp the last range).
    7. Spine via cut-video.py --emit-json.
    8. Joins from the timeline JSON, or an explicit list.
    9. Stills via stills-to-broll.py (sequential).
    10. Mixed-grade pregrade when log and rec709 are in the same cut.
    11. Inserts (zero or one) split the spine, finish each part, concat.
    12. Finish via finish-reel.py.
    13. Render lock wraps steps 7 and 9 to 12.
    14. QA gate via qa-reel.py when present.
    15. RUNNOTES beside the output.
    16. Deliver copies (unless --no-deliver).
    17. One JSON summary line on stdout.

--dry-run does steps 1 to 6 for real and prints the commands for 7 to 16
without encoding media.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
RESOURCES = SCRIPTS.parent / "resources"
SCHEMA_PATH = RESOURCES / "reel-manifest.schema.json"
TEMPLATE_PATH = RESOURCES / "runnotes.template.md"
CUT_VIDEO = SCRIPTS / "cut-video.py"
FINISH_REEL = SCRIPTS / "finish-reel.py"
STILLS_TO_BROLL = SCRIPTS / "stills-to-broll.py"
QA_REEL = SCRIPTS / "qa-reel.py"

STILL_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"}
DEFAULT_LOCK = Path.home() / ".cache" / "reel-factory" / "render.lock"
DEFAULT_LEDGER = Path.home() / ".cache" / "reel-factory" / "ledger.jsonl"
DEFAULT_EQ = "contrast=1.14:saturation=1.35:brightness=-0.015"
YMIN_LOG_THRESHOLD = 20.0
ENGINE_SCRIPTS = ("cut-video.py", "finish-reel.py", "stills-to-broll.py")
WORD_TOKEN_RE = re.compile(r"[a-z0-9]+")


class RenderError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def pretty_cmd(cmd: list[str]) -> str:
    parts: list[str] = []
    for c in cmd:
        if any(ch in c for ch in " \n:'"):
            parts.append("'" + c.replace("'", "'\\''") + "'")
        else:
            parts.append(c)
    return " ".join(parts)


def help_text(script: Path) -> str:
    if not script.is_file():
        return ""
    r = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
    )
    return (r.stdout or "") + (r.stderr or "")


def help_has(text: str, flag: str) -> bool:
    return re.search(rf"(?:^|\s){re.escape(flag)}(?:\s|=|,|$)", text) is not None


def notice_omit(flag: str, script: str) -> None:
    print(f"[render-reel] {script} has no {flag}; omitting", flush=True)


def apply_defaults(instance, schema):
    """Fill schema defaults so later code reads one fully-resolved dict."""
    if not isinstance(schema, dict):
        return instance
    if instance is None and "default" in schema:
        instance = copy.deepcopy(schema["default"])
    props = schema.get("properties")
    if isinstance(instance, dict) and isinstance(props, dict):
        for key, sub in props.items():
            if key not in instance:
                if isinstance(sub, dict) and "default" in sub:
                    instance[key] = copy.deepcopy(sub["default"])
            if key in instance and isinstance(sub, dict):
                instance[key] = apply_defaults(instance[key], sub)
        return instance
    items = schema.get("items")
    if isinstance(instance, list) and isinstance(items, dict):
        return [apply_defaults(item, items) for item in instance]
    return instance


def minimal_validate(data: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    required = schema.get("required") or []
    for key in required:
        if key not in data:
            errors.append(f"missing required key '{key}'")
    allowed = set((schema.get("properties") or {}).keys())
    if schema.get("additionalProperties") is False and isinstance(data, dict):
        extra = sorted(set(data.keys()) - allowed)
        for key in extra:
            errors.append(f"unknown top-level key '{key}'")
    if data.get("schema") != "reel-manifest/1":
        errors.append("schema must be reel-manifest/1")
    slug = data.get("slug")
    if isinstance(slug, str) and not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug):
        errors.append(f"slug '{slug}' is not kebab-case")
    window = data.get("duration_window")
    if not (
        isinstance(window, list)
        and len(window) == 2
        and all(isinstance(x, (int, float)) and x >= 1 for x in window)
    ):
        errors.append("duration_window must be [min_s, max_s] with both >= 1")
    enums = {
        ("source", "color"): {"auto", "log", "rec709"},
        ("source", "orient"): {"auto", "none", "r5-portrait", "landscape-punch", "tall-spine"},
        ("hook", "mode"): {"none", "prepend"},
        ("cover", "anchor"): {"center", "top"},
        ("cover", "case"): {"as-is", "upper", "sentence"},
        ("captions", "style"): {"phrase", "word"},
        ("captions", "placement"): {"safe-lower", "safe-center", "custom"},
        ("render", "mode"): {"final", "proxy"},
        ("audio", "loudnorm"): {"two-pass", "single", "off"},
        ("audio", "denoise"): {"off", "light"},
    }
    for path, allowed_vals in enums.items():
        cur: object = data
        ok = True
        for part in path:
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur[part]
        if ok and cur is not None and cur not in allowed_vals:
            errors.append(f"{'.'.join(path)} must be one of {sorted(allowed_vals)}")
    ranges = ((data.get("spine") or {}).get("ranges")) if isinstance(data.get("spine"), dict) else None
    if not isinstance(ranges, list) or not ranges:
        errors.append("spine.ranges must be a non-empty list")
    else:
        for i, rng in enumerate(ranges):
            if not isinstance(rng, dict):
                errors.append(f"spine.ranges[{i}] must be an object")
                continue
            start, end = rng.get("start"), rng.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                errors.append(f"spine.ranges[{i}] start/end must be numbers")
            elif end <= start:
                errors.append(f"spine.ranges[{i}] end must be > start")
    version = data.get("version", "auto")
    if version != "auto" and not (isinstance(version, int) and version >= 1):
        errors.append("version must be 'auto' or an integer >= 1")
    joins = data.get("joins", "auto")
    if joins != "auto" and not (
        isinstance(joins, list) and all(isinstance(x, (int, float)) for x in joins)
    ):
        errors.append("joins must be 'auto' or a list of numbers")
    return errors


def validate_manifest(data: dict, schema: dict) -> None:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        eprint("jsonschema not installed; using built-in manifest checks")
        errors = minimal_validate(data, schema)
        if errors:
            raise RenderError("invalid manifest: " + "; ".join(errors), 2)
        return
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise RenderError(f"invalid manifest: {exc.message}", 2) from exc


def resolve_path(value, manifest_dir: Path):
    if value is None or value == "":
        return value
    path = Path(str(value))
    if not path.is_absolute():
        path = (manifest_dir / path).resolve()
    else:
        path = path.resolve()
    return str(path)


def resolve_manifest_paths(manifest: dict, manifest_dir: Path) -> None:
    manifest["output_dir"] = resolve_path(manifest["output_dir"], manifest_dir)
    deliver = manifest.get("deliver") or {}
    if "copy_to" in deliver and isinstance(deliver["copy_to"], list):
        deliver["copy_to"] = [
            resolve_path(p, manifest_dir) for p in deliver["copy_to"]
        ]
        manifest["deliver"] = deliver
    src = manifest["source"]
    src["video"] = resolve_path(src["video"], manifest_dir)
    src["transcript_json"] = resolve_path(src["transcript_json"], manifest_dir)
    if src.get("lut"):
        src["lut"] = resolve_path(src["lut"], manifest_dir)
    hook = manifest.get("hook") or {}
    if hook.get("source"):
        hook["source"] = resolve_path(hook["source"], manifest_dir)
    if hook.get("transcript_json"):
        hook["transcript_json"] = resolve_path(hook["transcript_json"], manifest_dir)
    cover = manifest.get("cover") or {}
    if cover.get("font"):
        cover["font"] = resolve_path(cover["font"], manifest_dir)
    captions = manifest.get("captions") or {}
    if captions.get("font"):
        captions["font"] = resolve_path(captions["font"], manifest_dir)
    for item in manifest.get("broll") or []:
        if item.get("path"):
            item["path"] = resolve_path(item["path"], manifest_dir)
    for item in manifest.get("inserts") or []:
        if item.get("source"):
            item["source"] = resolve_path(item["source"], manifest_dir)
        if item.get("transcript_json"):
            item["transcript_json"] = resolve_path(item["transcript_json"], manifest_dir)
    qa = manifest.get("qa") or {}
    if qa.get("banned_words_file"):
        qa["banned_words_file"] = resolve_path(qa["banned_words_file"], manifest_dir)


def transcript_has_words(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for seg in data.get("segments") or []:
        words = seg.get("words")
        if isinstance(words, list) and words:
            return True
    return False


def is_still_item(item: dict) -> bool:
    kind = item.get("kind") or "auto"
    if kind == "still":
        return True
    if kind == "clip":
        return False
    return Path(str(item.get("path") or "")).suffix.lower() in STILL_EXTS


def preflight(manifest: dict) -> list[str]:
    problems: list[str] = []
    if shutil.which("ffmpeg") is None:
        problems.append("ffmpeg not on PATH")
    if shutil.which("ffprobe") is None:
        problems.append("ffprobe not on PATH")
    needed: list[tuple[str, str]] = [
        (manifest["source"]["video"], "source.video"),
        (manifest["source"]["transcript_json"], "source.transcript_json"),
    ]
    lut = manifest["source"].get("lut")
    if lut:
        needed.append((lut, "source.lut"))
    hook = manifest.get("hook") or {}
    if (hook.get("mode") or "none") == "prepend":
        hook_src = hook.get("source") or manifest["source"]["video"]
        needed.append((hook_src, "hook.source"))
        if hook.get("transcript_json"):
            needed.append((hook["transcript_json"], "hook.transcript_json"))
    cover = manifest.get("cover") or {}
    if cover.get("text"):
        font = cover.get("font") or os.environ.get("FINISH_REEL_FONT")
        if font:
            needed.append((font, "cover.font"))
        else:
            problems.append("cover.text is set but cover.font is missing")
    captions = manifest.get("captions") or {}
    if captions.get("font"):
        needed.append((captions["font"], "captions.font"))
    for i, item in enumerate(manifest.get("broll") or []):
        path = item.get("path") or ""
        if path == "":
            continue
        needed.append((path, f"broll[{i}].path"))
    for i, item in enumerate(manifest.get("inserts") or []):
        needed.append((item.get("source") or "", f"inserts[{i}].source"))
        needed.append((item.get("transcript_json") or "", f"inserts[{i}].transcript_json"))
    qa = manifest.get("qa") or {}
    if qa.get("banned_words_file"):
        needed.append((qa["banned_words_file"], "qa.banned_words_file"))
    for path_s, label in needed:
        path = Path(str(path_s))
        if not path_s or not path.exists():
            problems.append(f"missing {label}: {path_s}")
    tpath = Path(manifest["source"]["transcript_json"])
    if tpath.exists() and not transcript_has_words(tpath):
        problems.append(
            f"transcript without words: {tpath} (need segments[].words[])"
        )
    for i, item in enumerate(manifest.get("inserts") or []):
        ip = Path(str(item.get("transcript_json") or ""))
        if ip.exists() and not transcript_has_words(ip):
            problems.append(f"inserts[{i}] transcript without words: {ip}")
    out_dir = Path(manifest["output_dir"])
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".render-reel-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        problems.append(f"output_dir not writable: {out_dir} ({exc})")
    return problems


def scan_next_final_version(output_dir: Path, ident: str, slug: str) -> int:
    pat = re.compile(rf"^{re.escape(ident)}_{re.escape(slug)}_v(\d+)\.mp4$")
    found: list[int] = []
    if output_dir.is_dir():
        for child in output_dir.iterdir():
            m = pat.match(child.name)
            if m:
                found.append(int(m.group(1)))
    return (max(found) if found else 0) + 1


def pick_version(
    output_dir: Path,
    ident: str,
    slug: str,
    proxy: bool,
    forced: int | None,
    manifest_version,
) -> int:
    if forced is not None:
        return int(forced)
    if manifest_version not in (None, "auto"):
        return int(manifest_version)
    n = scan_next_final_version(output_dir, ident, slug)
    if not proxy:
        return n
    # A proxy never consumes a final number. If vN-proxy already exists, walk
    # forward so the second auto proxy is vN+1-proxy instead of overwriting.
    while (output_dir / target_name(ident, slug, n, True)).exists():
        n += 1
    return n


def target_name(ident: str, slug: str, version: int, proxy: bool) -> str:
    base = f"{ident}_{slug}_v{version}"
    return f"{base}-proxy.mp4" if proxy else f"{base}.mp4"


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float((r.stdout or "").strip())
    except ValueError:
        return 0.0


def probe_specs(path: Path) -> dict:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,pix_fmt,codec_name",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "pix_fmt": stream.get("pix_fmt"),
        "codec": stream.get("codec_name"),
        "duration": fmt.get("duration"),
    }


def sample_ymin(path: Path) -> float | None:
    dur = probe_duration(path)
    if dur <= 0:
        times = [0.0]
    else:
        times = [dur * 0.2, dur * 0.5, dur * 0.8]
    ymins: list[float] = []
    for t in times:
        cmd = [
            "ffmpeg", "-hide_banner", "-nostats",
            "-ss", f"{t:.3f}", "-i", str(path),
            "-frames:v", "1",
            "-vf", "signalstats,metadata=print",
            "-f", "null", "-",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        blob = (r.stderr or "") + (r.stdout or "")
        found = re.findall(r"lavfi\.signalstats\.YMIN(?:\.den)?\s*[:=]\s*([0-9.]+)", blob)
        if not found:
            found = re.findall(r"\bYMIN(?:\.den)?\s*[:=]\s*([0-9.]+)", blob)
        if found:
            ymins.append(float(found[-1]))
    if not ymins:
        return None
    return sum(ymins) / len(ymins)


def classify_color(label: str, declared: str, path: Path | None, still: bool) -> tuple[str, float | None]:
    if still:
        print(f"[render-reel] color {label}: still -> rec709")
        return "rec709", None
    if declared in {"log", "rec709"}:
        print(f"[render-reel] color {label}: declared {declared}")
        return declared, None
    if path is None or not path.exists():
        print(f"[render-reel] color {label}: missing file, assuming rec709")
        return "rec709", None
    ymin = sample_ymin(path)
    if ymin is None:
        print(f"[render-reel] color {label}: YMIN unreadable, assuming rec709")
        return "rec709", None
    decision = "log" if ymin >= YMIN_LOG_THRESHOLD else "rec709"
    print(f"[render-reel] color {label}: YMIN={ymin:.1f} -> {decision}")
    return decision, ymin


def subtract_hook(ranges: list[dict], hook_start: float, hook_end: float) -> list[dict]:
    out: list[dict] = []
    for rng in ranges:
        s = float(rng["start"])
        e = float(rng["end"])
        quote = rng.get("quote")
        if e <= hook_start or s >= hook_end:
            out.append(dict(rng))
            continue
        if s < hook_start:
            piece = {"start": s, "end": min(e, hook_start)}
            if quote:
                piece["quote"] = quote
            if piece["end"] > piece["start"]:
                out.append(piece)
        if e > hook_end:
            piece = {"start": max(s, hook_end), "end": e}
            if quote:
                piece["quote"] = quote
            if piece["end"] > piece["start"]:
                out.append(piece)
    return out


def apply_hard_out(ranges: list[dict], hard_out: float | None) -> list[dict]:
    if hard_out is None or not ranges:
        return ranges
    out = [dict(r) for r in ranges]
    out[-1]["end"] = min(float(out[-1]["end"]), float(hard_out))
    if out[-1]["end"] <= float(out[-1]["start"]):
        out.pop()
    return out


def format_ranges(ranges: list[dict]) -> str:
    return "  ".join(f"{r['start']:.3f}:{r['end']:.3f}" for r in ranges)


def estimate_joins(ranges: list[dict]) -> list[float]:
    joins: list[float] = []
    cursor = 0.0
    for i, rng in enumerate(ranges):
        cursor += float(rng["end"]) - float(rng["start"])
        if i < len(ranges) - 1:
            joins.append(cursor)
    return joins


def joins_from_timeline(timeline: dict) -> list[float]:
    crs = timeline.get("coarse_ranges") or []
    return [float(crs[i]["out_end"]) for i in range(len(crs) - 1)]


def src_time_to_out(timeline: dict, src_t: float) -> float | None:
    for seg in timeline.get("segments") or []:
        s, e = float(seg["src_start"]), float(seg["src_end"])
        if s <= src_t <= e:
            span = e - s
            if span <= 0:
                return float(seg["out_start"])
            frac = (src_t - s) / span
            return float(seg["out_start"]) + frac * (float(seg["out_end"]) - float(seg["out_start"]))
    return None


def apply_cover_case(text: str, case: str) -> str:
    if not text:
        return text
    if case == "upper":
        return text.upper()
    if case == "sentence":
        stripped = text.strip()
        if not stripped:
            return stripped
        return stripped[0].upper() + stripped[1:]
    return text


def punch_duration(item: dict, original: dict) -> float:
    still = is_still_item(item)
    if "dur" in original:
        dur = float(original["dur"])
    else:
        dur = 3.5 if still else float(item.get("dur") or 2.5)
    if item.get("super"):
        dur = max(dur, 3.5)
    return dur


def load_finish_reel():
    path = FINISH_REEL
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_finish_reel_wp1", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        eprint(f"could not import finish-reel.py helpers: {exc}")
        return None
    return mod


def pregrade_clip(
    src: Path,
    dest: Path,
    lut: Path | None,
    eq: str | None,
    width: int,
    height: int,
    rotate: int | None,
    dry: bool,
    commands: list[list[str]],
    fr_mod,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dry:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-vf", f"pregrade,scale={width}:{height}",
            str(dest),
        ]
        commands.append(cmd)
        print("[render-reel] DRY " + pretty_cmd(cmd), flush=True)
        return
    if fr_mod is not None:
        mode, rot, w, h = fr_mod.decide_orient(src, "auto")
        vf = fr_mod.build_vf(
            orient_mode=mode,
            rotate=rotate,
            rotation=rot,
            lut=lut,
            eq=eq,
            width=width,
            height=height,
            src_w=w,
            src_h=h,
        )
        fr_mod.normalize(
            src,
            dest,
            vf=vf,
            noautorotate=(mode == "r5-portrait"),
            ss=None,
            t=None,
            audio=True,
            crf=18,
            preset="ultrafast",
            dry=False,
        )
        commands.append(["ffmpeg", "-i", str(src), "-vf", vf, str(dest)])
        if not dest.exists():
            raise RenderError(f"pregrade produced no file: {dest}", 3)
        return
    vf_parts: list[str] = []
    if lut is not None:
        lut_s = str(lut).replace("\\", "\\\\").replace(":", "\\:")
        vf_parts.append(f"lut3d={lut_s}")
    if eq:
        vf_parts.append(f"eq={eq}")
    vf_parts.append(
        "crop=min(iw\\,ih*9/16):min(ih\\,iw*16/9):(iw-ow)/2:(ih-oh)/2"
    )
    vf_parts.append(f"scale={width}:{height}:flags=lanczos")
    vf_parts.append("format=yuv420p")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src), "-vf", ",".join(vf_parts),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000",
        str(dest),
    ]
    commands.append(cmd)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        eprint((r.stderr or "")[-2000:])
        raise RenderError(f"pregrade failed: {src}", 3)


def read_lock_pid(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8").strip().split()
        return text[0] if text else "unknown"
    except OSError:
        return "unknown"


def acquire_lock(path: Path, timeout_s: float, manifest_id: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.time() + max(0.0, timeout_s)
    last_notice = 0.0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            now = time.time()
            if now >= deadline:
                os.close(fd)
                raise RenderError(f"lock timeout: {path}", 5)
            if last_notice == 0.0 or now - last_notice >= 15.0:
                pid = read_lock_pid(path)
                print(
                    f"waiting for render lock held by PID {pid} …",
                    flush=True,
                )
                last_notice = now
            sleep_for = min(15.0, max(0.05, deadline - now))
            time.sleep(sleep_for)
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {manifest_id}\n".encode("utf-8"))
    try:
        os.fsync(fd)
    except OSError:
        pass
    return fd


def release_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def run_python(
    script: Path,
    argv: list[str],
    dry: bool,
    commands: list[list[str]],
    label: str,
) -> int:
    cmd = [sys.executable, str(script), *argv]
    commands.append(cmd)
    prefix = "DRY " if dry else ""
    print(f"[render-reel] {prefix}{pretty_cmd(cmd)}", flush=True)
    if dry:
        return 0
    r = subprocess.run(cmd)
    if r.returncode != 0:
        eprint(f"{label} failed (exit {r.returncode})")
    return r.returncode


def run_ffmpeg(cmd: list[str], dry: bool, commands: list[list[str]]) -> None:
    commands.append(cmd)
    prefix = "DRY " if dry else ""
    print(f"[render-reel] {prefix}{pretty_cmd(cmd)}", flush=True)
    if dry:
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        eprint((r.stderr or "")[-2000:])
        raise RenderError("ffmpeg failed", 3)


def fill_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def build_cut_video_args(
    *,
    source: Path,
    transcript: Path,
    output: Path,
    ranges: list[dict],
    spine: dict,
    emit_json: Path | None,
    help_cut: str,
    preset: str,
    crf: int,
) -> list[str]:
    argv = [
        "--source", str(source),
        "--json", str(transcript),
        "--output", str(output),
    ]
    for rng in ranges:
        argv += ["--range", f"{float(rng['start']):.3f}:{float(rng['end']):.3f}"]
    argv += [
        "--max-pause", str(spine.get("max_pause", 0.85)),
        "--keep-tail", str(spine.get("keep_tail", 0.20)),
        "--keep-lead", str(spine.get("keep_lead", 0.08)),
        "--join-fade", str(spine.get("join_fade", 0.06)),
        "--preset", preset,
        "--crf", str(crf),
    ]
    if not spine.get("filler_removal", True):
        argv.append("--no-filler-removal")
    if not spine.get("pause_compression", True):
        argv.append("--no-pause-compression")
    if emit_json is not None:
        if help_has(help_cut, "--emit-json"):
            argv += ["--emit-json", str(emit_json)]
        else:
            notice_omit("--emit-json", "cut-video.py")
    return argv


def build_finish_argv(
    *,
    help_fr: str,
    spine: Path,
    output: Path,
    manifest: dict,
    ranges: list[dict],
    hook_path: Path | None,
    hook_range: list[float] | None,
    lut: Path | None,
    skip_lut: bool,
    eq: str | None,
    no_eq: bool,
    broll_no_eq: bool,
    broll_no_lut: bool = False,
    broll_specs: list[dict],
    joins: list[float],
    supers: list[str],
    cover_text: str,
    width: int,
    height: int,
    crf: int,
    preset: str,
    proxy: bool,
    qa_dir: Path | None,
    emit_json: Path | None,
    ass_out: Path | None,
    captions_on: bool,
) -> list[str]:
    src = manifest["source"]
    cover = manifest.get("cover") or {}
    captions = manifest.get("captions") or {}
    audio = manifest.get("audio") or {}
    render = manifest.get("render") or {}
    qa = manifest.get("qa") or {}
    argv = ["--spine", str(spine), "--output", str(output)]
    if hook_path is not None and hook_range is not None:
        argv += [
            "--hook-source", str(hook_path),
            "--hook-range", f"{hook_range[0]:.3f}:{hook_range[1]:.3f}",
        ]
    if skip_lut and help_has(help_fr, "--skip-lut"):
        argv.append("--skip-lut")
    elif lut is not None:
        argv += ["--lut", str(lut)]
    if no_eq and help_has(help_fr, "--no-eq"):
        argv.append("--no-eq")
    elif eq:
        argv += ["--eq", eq]
    if broll_no_eq and help_has(help_fr, "--broll-no-eq"):
        argv.append("--broll-no-eq")
    if broll_no_lut:
        if help_has(help_fr, "--broll-no-lut"):
            argv.append("--broll-no-lut")
        else:
            eprint("finish-reel lacks --broll-no-lut; B-roll will take the LUT (update the engine)")
    if cover_text:
        argv += ["--cover-text", cover_text]
        argv += ["--cover-seconds", str(cover.get("seconds", 2.0))]
        if help_has(help_fr, "--cover-anchor"):
            argv += ["--cover-anchor", str(cover.get("anchor") or "center")]
        if cover.get("font"):
            argv += ["--font", str(cover["font"])]
        if cover.get("color"):
            argv += ["--font-color", str(cover["color"])]
        if cover.get("size"):
            argv += ["--font-size", str(cover["size"])]
        if cover.get("darken") and help_has(help_fr, "--cover-darken"):
            if re.search(r"--cover-darken\s+\S+", help_fr):
                argv += ["--cover-darken", "0.04"]
            else:
                argv.append("--cover-darken")
    for spec in broll_specs:
        token = f"{spec['path']}:at={spec['at']}:dur={spec['dur']}"
        if spec.get("src") is not None:
            token += f":src={spec['src']}"
        argv += ["--broll", token]
    durs = [float(s["dur"]) for s in broll_specs]
    if durs and max(durs) > 3.0 and help_has(help_fr, "--max-broll-dur"):
        argv += ["--max-broll-dur", f"{max(durs) + 0.01:.3f}"]
    elif durs and max(durs) > 3.0:
        notice_omit("--max-broll-dur", "finish-reel.py")
    for j in joins:
        argv += ["--join", f"{j:.3f}"]
    for super_s in supers:
        argv += ["--super", super_s]
    if captions_on:
        argv += ["--transcript", str(src["transcript_json"])]
        for rng in ranges:
            argv += ["--spine-range", f"{float(rng['start']):.3f}:{float(rng['end']):.3f}"]
        if captions.get("font"):
            argv += ["--caption-font", str(captions["font"])]
        if captions.get("size"):
            argv += ["--caption-size", str(captions["size"])]
        if help_has(help_fr, "--caption-placement"):
            argv += ["--caption-placement", str(captions.get("placement") or "safe-lower")]
        else:
            notice_omit("--caption-placement", "finish-reel.py")
        if help_has(help_fr, "--caption-style"):
            argv += ["--caption-style", str(captions.get("style") or "phrase")]
        else:
            notice_omit("--caption-style", "finish-reel.py")
        if help_has(help_fr, "--caption-min-cue"):
            argv += ["--caption-min-cue", str(captions.get("min_cue_s", 0.8))]
        else:
            notice_omit("--caption-min-cue", "finish-reel.py")
        if help_has(help_fr, "--caption-max-cue"):
            argv += ["--caption-max-cue", str(captions.get("max_cue_s", 2.8))]
        else:
            notice_omit("--caption-max-cue", "finish-reel.py")
        if help_has(help_fr, "--caption-max-chars"):
            argv += ["--caption-max-chars", str(captions.get("max_chars_per_line", 32))]
        else:
            notice_omit("--caption-max-chars", "finish-reel.py")
    elif help_has(help_fr, "--no-captions"):
        argv.append("--no-captions")
    if help_has(help_fr, "--platforms") and manifest.get("platforms"):
        argv += ["--platforms", ",".join(manifest["platforms"])]
    else:
        if manifest.get("platforms"):
            notice_omit("--platforms", "finish-reel.py")
    loudnorm = audio.get("loudnorm", "two-pass")
    if loudnorm == "off":
        if help_has(help_fr, "--no-loudnorm"):
            argv.append("--no-loudnorm")
    else:
        if help_has(help_fr, "--loudnorm-mode"):
            argv += ["--loudnorm-mode", str(loudnorm)]
        else:
            notice_omit("--loudnorm-mode", "finish-reel.py")
        if help_has(help_fr, "--loudnorm-i"):
            argv += ["--loudnorm-i", str(audio.get("target_i", -16))]
        else:
            notice_omit("--loudnorm-i", "finish-reel.py")
        if help_has(help_fr, "--loudnorm-tp"):
            argv += ["--loudnorm-tp", str(audio.get("true_peak", -1.5))]
        else:
            notice_omit("--loudnorm-tp", "finish-reel.py")
        if help_has(help_fr, "--loudnorm-lra"):
            argv += ["--loudnorm-lra", str(audio.get("lra", 11))]
        else:
            notice_omit("--loudnorm-lra", "finish-reel.py")
    if audio.get("denoise") == "light":
        if help_has(help_fr, "--denoise"):
            argv += ["--denoise", "light"]
        else:
            notice_omit("--denoise", "finish-reel.py")
    orient = src.get("orient") or "auto"
    if help_has(help_fr, "--orient"):
        argv += ["--orient", str(orient)]
    if src.get("rotate") is not None and help_has(help_fr, "--rotate"):
        argv += ["--rotate", str(src["rotate"])]
    if help_has(help_fr, "--width"):
        argv += ["--width", str(width)]
    if help_has(help_fr, "--height"):
        argv += ["--height", str(height)]
    argv += ["--crf", str(crf), "--preset", preset]
    if proxy and help_has(help_fr, "--proxy"):
        argv.append("--proxy")
    elif proxy:
        notice_omit("--proxy", "finish-reel.py")
    encoder = render.get("encoder") or "auto"
    if encoder != "auto":
        if help_has(help_fr, "--encoder"):
            argv += ["--encoder", str(encoder)]
        else:
            notice_omit("--encoder", "finish-reel.py")
    threads = render.get("threads") or 0
    if threads:
        if help_has(help_fr, "--threads"):
            argv += ["--threads", str(threads)]
        else:
            notice_omit("--threads", "finish-reel.py")
    if qa_dir is not None and help_has(help_fr, "--qa-dir"):
        argv += ["--qa-dir", str(qa_dir)]
    if help_has(help_fr, "--qa-max-px"):
        argv += ["--qa-max-px", str(qa.get("max_frame_px", 540))]
    else:
        notice_omit("--qa-max-px", "finish-reel.py")
    if emit_json is not None:
        if help_has(help_fr, "--emit-json"):
            argv += ["--emit-json", str(emit_json)]
        else:
            notice_omit("--emit-json", "finish-reel.py")
    if ass_out is not None:
        if help_has(help_fr, "--ass-out"):
            argv += ["--ass-out", str(ass_out)]
        else:
            notice_omit("--ass-out", "finish-reel.py")
    return argv


def split_ranges_at(ranges: list[dict], t: float) -> tuple[list[dict], list[dict]]:
    part_a: list[dict] = []
    part_b: list[dict] = []
    for rng in ranges:
        s, e = float(rng["start"]), float(rng["end"])
        quote = rng.get("quote")
        if e <= t:
            part_a.append(dict(rng))
        elif s >= t:
            part_b.append(dict(rng))
        else:
            a = {"start": s, "end": t}
            b = {"start": t, "end": e}
            if quote:
                a["quote"] = quote
                b["quote"] = quote
            if a["end"] > a["start"]:
                part_a.append(a)
            if b["end"] > b["start"]:
                part_b.append(b)
    return part_a, part_b


def write_runnotes(
    dest: Path,
    values: dict[str, str],
) -> None:
    if TEMPLATE_PATH.is_file():
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = "\n".join(f"{{{{" + k + "}}}}" for k in values)
        template = "# RUNNOTES\n\n" + "\n\n".join(
            f"## {k}\n\n{{{{{k}}}}}" for k in values
        )
    old_h = (
        "| spine time | final time | file | kind | dur | line | verified | super |"
    )
    new_h = (
        "| spine time | final time | file | kind | dur | line | shows | "
        "grade | verified | super |"
    )
    if old_h in template:
        template = template.replace(old_h, new_h, 1)
        template = template.replace(
            "|---|---|---|---|---|---|---|---|",
            "|---|---|---|---|---|---|---|---|---|---|",
            1,
        )
    dest.write_text(fill_template(template, values), encoding="utf-8")


def sha16_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def sha16_file(path: Path | str | None) -> str | None:
    if path is None or path == "":
        return None
    p = Path(path)
    if not p.is_file():
        return None
    return sha16_bytes(p.read_bytes())


def sha16_media(path: Path | str | None) -> str | None:
    """First 1 MB of the file plus its size in bytes."""
    if path is None or path == "":
        return None
    p = Path(path)
    if not p.is_file():
        return None
    size = p.stat().st_size
    with p.open("rb") as fh:
        chunk = fh.read(1024 * 1024)
    return sha16_bytes(chunk + str(size).encode("ascii"))


def ffmpeg_version_line() -> str | None:
    r = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True
    )
    blob = r.stdout or r.stderr or ""
    lines = blob.splitlines()
    return lines[0].strip() if lines else None


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def append_ledger(path: Path, record: dict) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, ensure_ascii=True) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, payload)
        try:
            os.fsync(fd)
        except OSError:
            pass
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def deep_merge_under(style: dict, manifest: dict) -> dict:
    """Style fills gaps. Manifest always wins, including nested keys."""
    if not isinstance(style, dict):
        return copy.deepcopy(manifest)
    out = copy.deepcopy(style)

    def overlay(dst: dict, src: dict) -> None:
        for key, val in src.items():
            if key not in dst or dst[key] is None:
                dst[key] = copy.deepcopy(val)
            elif isinstance(dst.get(key), dict) and isinstance(val, dict):
                overlay(dst[key], val)
            elif val is not None:
                dst[key] = copy.deepcopy(val)

    overlay(out, manifest)
    return out


def apply_broll_defaults(manifest: dict, defaults: dict | None) -> None:
    if not defaults or not isinstance(defaults, dict):
        return
    for item in manifest.get("broll") or []:
        if not isinstance(item, dict):
            continue
        still = is_still_item(item)
        if "dur" not in item:
            if still and "dur_still" in defaults:
                item["dur"] = defaults["dur_still"]
            elif not still and "dur_clip" in defaults:
                item["dur"] = defaults["dur_clip"]
        if "zoom" not in item and "zoom" in defaults:
            item["zoom"] = defaults["zoom"]
        if "direction" not in item and "direction" in defaults:
            item["direction"] = defaults["direction"]


def load_style(path: Path) -> tuple[dict, dict | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RenderError(f"style is not JSON: {exc}", 2) from exc
    if not isinstance(data, dict):
        raise RenderError("style must be a JSON object", 2)
    # Keys starting with "_" are documentation for humans ("_about", "_source")
    # and never reach the manifest merge, so a business can annotate its style.
    for key in [k for k in data if str(k).startswith("_")]:
        data.pop(key, None)
    # "resolve" holds settings only the resolve-reel skill reads (grade, cover shadow);
    # the manifest schema does not allow them, so they never reach the merge.
    data.pop("resolve", None)
    # "edit_route" is the business's Resolve-vs-ffmpeg preference (references/edit-route.md),
    # read by the agent, never by the engine.
    data.pop("edit_route", None)
    defaults = data.pop("broll_defaults", None)
    if defaults is not None and not isinstance(defaults, dict):
        raise RenderError("style broll_defaults must be an object", 2)
    return data, defaults


def tokenize_words(text: str) -> list[str]:
    return WORD_TOKEN_RE.findall(text.lower())


def load_transcript_words(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    words: list[dict] = []
    for seg in data.get("segments") or []:
        for w in seg.get("words") or []:
            raw = str(w.get("word") or "").strip()
            toks = tokenize_words(raw)
            token = toks[0] if toks else raw.lower()
            if not token:
                continue
            try:
                start = float(w["start"])
                end = float(w["end"])
            except (KeyError, TypeError, ValueError):
                continue
            words.append({"word": token, "raw": raw, "start": start, "end": end})
    return words


def quote_tokens(text: str) -> list[str]:
    """One token per spoken word, matching how transcript words are tokenized.

    "here's" must become ["here"], not ["here", "s"], or a quote can never
    match the JSON word it was copied from.
    """
    out: list[str] = []
    for word in text.split():
        toks = tokenize_words(word)
        if toks:
            out.append(toks[0])
    return out


def quote_edge_words(quote: str) -> tuple[list[str], list[str]]:
    if "..." in quote:
        before, after = quote.split("...", 1)
        start_words = quote_tokens(before)
        end_words = quote_tokens(after)
    else:
        toks = quote_tokens(quote)
        start_words = toks
        end_words = toks
    first_two = start_words[:2]
    last_two = end_words[-2:] if len(end_words) >= 2 else end_words
    return first_two, last_two


def words_near(words: list[dict], t: float, which: str, window: float = 1.0) -> list[dict]:
    key = "start" if which == "start" else "end"
    return [w for w in words if abs(float(w[key]) - t) <= window]


def check_quote_edge(
    quote: str,
    start: float,
    end: float,
    words: list[dict],
    label: str,
) -> list[dict]:
    rows: list[dict] = []
    first_two, last_two = quote_edge_words(quote)
    if first_two:
        near = words_near(words, start, "start", 1.0)
        found = {w["word"] for w in near}
        missing = [w for w in first_two if w not in found]
        if missing:
            shown = ", ".join(w["word"] for w in near) or "(none)"
            rows.append({
                "check": f"{label} quote start",
                "status": "WARN",
                "detail": (
                    f"expected {' '.join(first_two)!r} near start {start:.3f}s; "
                    f"missing {missing}; found: {shown}"
                ),
            })
        else:
            rows.append({
                "check": f"{label} quote start",
                "status": "ok",
                "detail": " ".join(first_two),
            })
    if last_two:
        near = words_near(words, end, "end", 1.0)
        found = {w["word"] for w in near}
        missing = [w for w in last_two if w not in found]
        if missing:
            shown = ", ".join(w["word"] for w in near) or "(none)"
            rows.append({
                "check": f"{label} quote end",
                "status": "WARN",
                "detail": (
                    f"expected {' '.join(last_two)!r} near end {end:.3f}s; "
                    f"missing {missing}; found: {shown}"
                ),
            })
        else:
            rows.append({
                "check": f"{label} quote end",
                "status": "ok",
                "detail": " ".join(last_two),
            })
    return rows


def unsourced_broll_lines(manifest: dict) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i, item in enumerate(manifest.get("broll") or []):
        if (item.get("path") or "") == "":
            line = str(item.get("line") or "").strip()
            out.append((i, line or f"broll[{i}]"))
    return out


def brief_preflight_lint(manifest: dict) -> list[dict]:
    """Quote, hard_out, duration, and broll-at checks. Warnings only."""
    rows: list[dict] = []
    src = manifest.get("source") or {}
    tpath = Path(str(src.get("transcript_json") or ""))
    words = load_transcript_words(tpath) if tpath.is_file() else []
    ranges = [dict(r) for r in ((manifest.get("spine") or {}).get("ranges") or [])]
    for i, rng in enumerate(ranges):
        quote = rng.get("quote") or ""
        if not quote:
            continue
        rows.extend(
            check_quote_edge(
                quote, float(rng["start"]), float(rng["end"]), words, f"spine[{i}]"
            )
        )
    hook = manifest.get("hook") or {}
    hook_mode = hook.get("mode") or "none"
    hook_range = hook.get("range")
    hook_quote = hook.get("quote") or ""
    hook_dur = 0.0
    hook_path = hook.get("source")
    spine_video = src.get("video")
    hook_same = hook_path in (None, "", "null") or (
        spine_video and Path(str(hook_path)).resolve() == Path(str(spine_video)).resolve()
    )
    if hook_mode == "prepend" and hook_range:
        hs, he = float(hook_range[0]), float(hook_range[1])
        hook_dur = max(0.0, he - hs)
        if hook_quote:
            if hook_same:
                hwords = words
            else:
                ht = hook.get("transcript_json")
                hwords = load_transcript_words(Path(str(ht))) if ht else []
            rows.extend(check_quote_edge(hook_quote, hs, he, hwords, "hook"))
        lift = bool(hook.get("lift_from_spine", True))
        if hook_same and lift:
            ranges = subtract_hook(ranges, hs, he)
    hard_out = (manifest.get("spine") or {}).get("hard_out")
    if hard_out is not None:
        ho = float(hard_out)
        hit = any(abs(float(w["end"]) - ho) <= 0.05 for w in words)
        if hit:
            rows.append({
                "check": "hard_out word end",
                "status": "ok",
                "detail": f"{ho:.3f}s",
            })
        else:
            rows.append({
                "check": "hard_out word end",
                "status": "WARN",
                "detail": "hard_out is not a word end",
            })
        ranges = apply_hard_out(ranges, ho)
    sum_dur = sum(float(r["end"]) - float(r["start"]) for r in ranges) if ranges else 0.0
    estimate = sum_dur * 0.88 + hook_dur
    spine_est = sum_dur * 0.88
    window = manifest.get("duration_window") or [0, 0]
    lo, hi = float(window[0]), float(window[1])
    outside = estimate < lo * 0.85 or estimate > hi * 1.15
    rows.append({
        "check": "duration estimate",
        "status": "WARN" if outside else "ok",
        "detail": (
            f"{estimate:.2f}s vs window [{lo:g}, {hi:g}]"
            + (" (outside by more than 15 %)" if outside else "")
        ),
    })
    for i, item in enumerate(manifest.get("broll") or []):
        try:
            at = float(item.get("at"))
        except (TypeError, ValueError):
            continue
        inside = 0.0 <= at <= spine_est + 1e-6
        rows.append({
            "check": f"broll[{i}] at",
            "status": "ok" if inside else "WARN",
            "detail": (
                f"{at:.2f}s inside estimated spine {spine_est:.2f}s"
                if inside
                else f"{at:.2f}s is outside estimated spine {spine_est:.2f}s"
            ),
        })
    rows.extend(shows_missing_rows(manifest))
    rows.extend(stills_cap_rows(manifest, load_broll_policy(manifest)))
    return rows


def load_platform_broll() -> dict:
    path = RESOURCES / "platform-specs.json"
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    bspec = blob.get("broll") if isinstance(blob, dict) else None
    return bspec if isinstance(bspec, dict) else {}


def _policy_num(value, default):
    if value is None:
        return default
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def load_broll_policy(manifest: dict) -> dict:
    specs = load_platform_broll()
    qa = manifest.get("qa") if isinstance(manifest.get("qa"), dict) else {}
    clip_on = specs.get("clip_on_noun_s")
    return {
        "max_stills": _policy_num(
            qa.get("max_stills"), _policy_num(specs.get("max_stills_per_reel"), 2)
        ),
        "max_consecutive_stills": _policy_num(
            qa.get("max_consecutive_stills"),
            _policy_num(specs.get("max_consecutive_stills"), 1),
        ),
        "still_on_noun_s": _policy_num(
            qa.get("still_on_noun_s"),
            _policy_num(specs.get("still_on_noun_s"), 0.3),
        ),
        "clip_on_noun_s": _policy_num(clip_on, 0.8),
    }


def shows_missing_rows(manifest: dict) -> list[dict]:
    missing: list[int] = []
    for i, item in enumerate(manifest.get("broll") or []):
        if not isinstance(item, dict):
            continue
        if (item.get("path") or "") == "":
            continue
        if not str(item.get("shows") or "").strip():
            missing.append(i)
    if not missing:
        return []
    listed = ", ".join(f"broll[{i}]" for i in missing)
    return [{
        "check": "shows missing",
        "status": "WARN",
        "detail": f"{listed} have path but no shows",
    }]


def stills_cap_rows(manifest: dict, policy: dict) -> list[dict]:
    rows: list[dict] = []
    stills: list[tuple[int, float, float]] = []
    for i, item in enumerate(manifest.get("broll") or []):
        if not isinstance(item, dict) or not is_still_item(item):
            continue
        try:
            at = float(item.get("at"))
        except (TypeError, ValueError):
            continue
        try:
            dur = float(item.get("dur") or 3.5)
        except (TypeError, ValueError):
            dur = 3.5
        stills.append((i, at, at + dur))
    max_stills = policy.get("max_stills")
    if max_stills is None:
        max_stills = 2
    else:
        max_stills = int(max_stills)
    n = len(stills)
    if n > max_stills:
        rows.append({
            "check": "stills cap",
            "status": "WARN",
            "detail": f"{n} stills; policy allows {max_stills}",
        })
    stills.sort(key=lambda x: x[1])
    max_run = policy.get("max_consecutive_stills")
    if max_run is None:
        max_run = 1
    else:
        max_run = int(max_run)
    longest = 1 if stills else 0
    run = 1
    pairs: list[tuple[int, int, float]] = []
    for prev, cur in zip(stills, stills[1:]):
        gap = cur[1] - prev[2]
        if gap < 1.0:
            run += 1
            longest = max(longest, run)
            pairs.append((prev[0], cur[0], gap))
        else:
            run = 1
    if pairs and longest > max_run:
        bits = ", ".join(
            f"broll[{a}] and broll[{b}] (gap {g:.2f}s)" for a, b, g in pairs
        )
        rows.append({
            "check": "stills cap",
            "status": "WARN",
            "detail": f"consecutive stills: {bits}",
        })
    return rows


def fabricate_coarse_timeline(ranges: list[dict]) -> dict:
    cursor = 0.0
    coarse = []
    for r in ranges:
        dur = float(r["end"]) - float(r["start"])
        coarse.append({
            "start": float(r["start"]),
            "end": float(r["end"]),
            "out_start": cursor,
            "out_end": cursor + dur,
        })
        cursor += dur
    return {"coarse_ranges": coarse, "segments": [], "duration_s": cursor}


def spine_at_to_source(timeline: dict, at: float) -> float | None:
    """Map a cut-spine time back to source time via coarse_ranges."""
    ranges = list(timeline.get("coarse_ranges") or [])
    for rng in ranges:
        try:
            out_start = float(rng["out_start"])
            out_end = float(rng["out_end"])
            start = float(rng["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if out_start <= at <= out_end + 1e-6:
            return start + (at - out_start)
    return None


def on_the_noun_lint(
    manifest: dict,
    timeline: dict,
    words: list[dict],
    policy: dict,
) -> list[dict]:
    """Warn when a punch start is far from a spoken line word."""
    rows: list[dict] = []
    if not (timeline.get("coarse_ranges") or []):
        return rows
    still_w = float(policy.get("still_on_noun_s") if policy.get("still_on_noun_s") is not None else 0.3)
    clip_w = float(policy.get("clip_on_noun_s") if policy.get("clip_on_noun_s") is not None else 0.8)
    for i, item in enumerate(manifest.get("broll") or []):
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        try:
            at = float(item.get("at"))
        except (TypeError, ValueError):
            continue
        src_t = spine_at_to_source(timeline, at)
        if src_t is None:
            rows.append({
                "check": "on the noun",
                "status": "WARN",
                "detail": (
                    f"punch {i} ('{line}') starts off the spine "
                    f"(at {at:.2f}s has no coarse range)"
                ),
            })
            continue
        token_set = set(quote_tokens(line))
        window = still_w if is_still_item(item) else clip_w
        best: tuple[float, dict] | None = None
        for w in words:
            if w["word"] not in token_set:
                continue
            offset = abs(float(w["start"]) - src_t)
            if best is None or offset < best[0]:
                best = (offset, w)
        if best is None:
            rows.append({
                "check": "on the noun",
                "status": "WARN",
                "detail": (
                    f"punch {i} ('{line}') starts with no matching line word "
                    f"in the transcript"
                ),
            })
            continue
        offset, w = best
        word = w["word"]
        t = float(w["start"])
        if offset <= window + 1e-9:
            rows.append({
                "check": "on the noun",
                "status": "ok",
                "detail": (
                    f"punch {i} ('{line}') word '{word}' at {t:.2f}s "
                    f"(offset {offset:.2f}s)"
                ),
            })
        else:
            rows.append({
                "check": "on the noun",
                "status": "WARN",
                "detail": (
                    f"punch {i} ('{line}') starts {offset:.2f} s from the "
                    f"nearest line word ('{word}' at {t:.2f})"
                ),
            })
    return rows


def format_preflight_table(rows: list[dict]) -> str:
    if not rows:
        return "(none)"
    lines = [
        f"{'check':<28} {'status':<6} detail",
        f"{'-' * 28} {'-' * 6} {'-' * 40}",
    ]
    for row in rows:
        lines.append(f"{row['check']:<28} {row['status']:<6} {row['detail']}")
    return "\n".join(lines)


def format_preflight_markdown(rows: list[dict]) -> str:
    if not rows:
        return "(none)"
    lines = [
        "| check | status | detail |",
        "|---|---|---|",
    ]
    for row in rows:
        detail = str(row["detail"]).replace("|", "\\|")
        lines.append(f"| {row['check']} | {row['status']} | {detail} |")
    return "\n".join(lines)


def print_preflight_table(rows: list[dict]) -> None:
    print("[render-reel] Preflight", flush=True)
    print(format_preflight_table(rows), flush=True)
    for row in rows:
        if row["status"] == "WARN":
            print(f"WARN  {row['check']}: {row['detail']}", flush=True)


def build_provenance(
    manifest: dict,
    *,
    style_path: Path | None,
    style_sha: str | None,
    manifest_path: Path,
) -> dict:
    src = manifest.get("source") or {}
    lut = src.get("lut")
    fonts: list[dict] = []
    cover_font = (manifest.get("cover") or {}).get("font")
    cap_font = (manifest.get("captions") or {}).get("font")
    for label, fpath in (("cover", cover_font), ("captions", cap_font)):
        if fpath:
            fonts.append({
                "role": label,
                "path": str(fpath),
                "sha16": sha16_file(fpath),
            })
    video = src.get("video")
    video_bytes = None
    if video and Path(str(video)).is_file():
        video_bytes = Path(str(video)).stat().st_size
    broll_prov: list[dict] = []
    for i, item in enumerate(manifest.get("broll") or []):
        p = item.get("path") or ""
        if not p:
            continue
        size = Path(p).stat().st_size if Path(p).is_file() else None
        broll_prov.append({
            "index": i,
            "path": p,
            "sha16": sha16_media(p),
            "bytes": size,
        })
    engine = {}
    for name in ENGINE_SCRIPTS:
        engine[name] = sha16_file(SCRIPTS / name)
    return {
        "ffmpeg_version": ffmpeg_version_line(),
        "lut": {"path": lut, "sha16": sha16_file(lut) if lut else None},
        "fonts": fonts,
        "source_video": {
            "path": video,
            "sha16": sha16_media(video),
            "bytes": video_bytes,
        },
        "broll": broll_prov,
        "engine": engine,
        "style": {
            "path": str(style_path) if style_path else None,
            "sha16": style_sha,
        },
        "manifest_sha16": sha16_file(manifest_path),
    }


def format_provenance(prov: dict) -> str:
    lines = [
        f"ffmpeg: {prov.get('ffmpeg_version') or '(unknown)'}",
        f"manifest sha16: {prov.get('manifest_sha16')}",
    ]
    lut = prov.get("lut") or {}
    if lut.get("path"):
        lines.append(f"lut sha16: {lut.get('sha16')} ({lut.get('path')})")
    else:
        lines.append("lut: none")
    for font in prov.get("fonts") or []:
        lines.append(f"font {font.get('role')}: sha16 {font.get('sha16')}")
    srcv = prov.get("source_video") or {}
    lines.append(
        f"source video sha16: {srcv.get('sha16')} ({srcv.get('bytes')} bytes)"
    )
    for item in prov.get("broll") or []:
        lines.append(f"broll[{item.get('index')}] sha16: {item.get('sha16')}")
    engine = prov.get("engine") or {}
    for name, digest in engine.items():
        lines.append(f"engine {name}: {digest}")
    style = prov.get("style") or {}
    if style.get("path"):
        lines.append(f"style sha16: {style.get('sha16')} ({style.get('path')})")
    else:
        lines.append("style: none")
    return "\n".join(lines)


def collect_deviations(
    *,
    duration_s: float,
    window: list,
    punch_rows: list[dict],
    cover_text: str,
    proxy: bool,
    qa_verdict: str,
    qa_fails: list,
    qa_warns: list,
    preflight_rows: list[dict],
) -> list[str]:
    items: list[str] = []
    lo, hi = float(window[0]), float(window[1])
    if duration_s and (duration_s < lo or duration_s > hi):
        items.append(
            f"duration {duration_s:.2f}s outside window [{lo:g}, {hi:g}]"
        )
    for row in punch_rows:
        if not row.get("verified"):
            items.append(f"broll {row.get('file')} verified: false")
        kind = row.get("kind")
        dur = float(row.get("dur") or 0)
        super_text = row.get("super") or ""
        if kind == "clip" and dur > 3.0 and not super_text:
            items.append(
                f"clip punch {row.get('file')} {dur:.1f}s without a super"
            )
        if super_text and dur < 3.5:
            items.append(
                f"super punch {row.get('file')} {dur:.1f}s shorter than 3.5s"
            )
    cover_words = [w for w in cover_text.split() if w]
    if len(cover_words) > 7:
        items.append(f"cover text is {len(cover_words)} words (over 7)")
    if proxy:
        items.append("proxy mode")
    if str(qa_verdict).lower() == "fail":
        ids = qa_fails or ["(unspecified)"]
        items.append("QA FAIL: " + ", ".join(str(x) for x in ids))
    elif str(qa_verdict).lower() == "warn":
        ids = qa_warns or qa_fails or ["(unspecified)"]
        items.append("QA WARN: " + ", ".join(str(x) for x in ids))
    for row in preflight_rows:
        if row.get("status") == "WARN":
            items.append(f"preflight {row['check']}: {row['detail']}")
    return items


def loudness_from_timeline(blob: dict | None) -> dict | None:
    if not isinstance(blob, dict):
        return None
    ln = blob.get("loudness")
    if not isinstance(ln, dict):
        return None
    return {
        "measured": {
            "i": ln.get("measured_i"),
            "tp": ln.get("measured_tp"),
            "lra": ln.get("measured_lra"),
        },
        "output": {
            "i": ln.get("output_i"),
            "tp": ln.get("output_tp"),
            "lra": ln.get("output_lra"),
        },
        "mode": ln.get("mode"),
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Execute a reel manifest end to end (cut, stills, finish, QA, "
            "RUNNOTES, deliver)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes: 0 rendered; 2 manifest or input problem; 3 downstream "
            "script failed; 4 rendered but QA FAIL; 5 lock timeout.\n"
            "Steps: validate, style merge, preflight lint, version, color, hook "
            "lift, hard out, spine, joins, stills, mixed grade, inserts, finish, "
            "lock, QA, RUNNOTES, deliver, ledger, summary JSON."
        ),
    )
    p.add_argument("--manifest", type=Path, required=True, help="Reel manifest JSON")
    p.add_argument("--proxy", action="store_true", help="Force proxy (540x960) output")
    p.add_argument("--version", type=int, default=None, help="Force output version N")
    p.add_argument("--dry-run", action="store_true", help="Validate and print later commands")
    p.add_argument("--no-deliver", action="store_true", help="Skip copy_to delivery")
    p.add_argument("--no-qa", action="store_true", help="Skip qa-reel.py")
    p.add_argument("--lock-file", type=Path, default=None, help="Exclusive render lock path")
    p.add_argument("--work-dir", type=Path, default=None, help="Working directory for intermediates")
    p.add_argument("--keep-work", action="store_true", help="Do not delete the work dir")
    p.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Append one JSONL run record (default ~/.cache/reel-factory/ledger.jsonl)",
    )
    p.add_argument("--no-ledger", action="store_true", help="Do not write a ledger line")
    p.add_argument(
        "--style",
        type=Path,
        default=None,
        help="Style profile JSON (or REEL_STYLE). Manifest wins; style fills gaps.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Treat brief-preflight lint warnings as errors (exit 2)",
    )
    p.add_argument("--lock-timeout", type=float, default=3600, help=argparse.SUPPRESS)
    args = p.parse_args()

    commands: list[list[str]] = []
    lock_fd: int | None = None
    work: Path | None = None
    failed = True
    exit_code = 2
    qa_verdict = "skipped"
    qa_fails: list = []
    qa_warns: list = []
    sheet_path: Path | None = None
    runnotes_path: Path | None = None
    target: Path | None = None
    version_n = 0
    duration_s = 0.0
    color_notes: list[str] = []
    hook_note = "none"
    mixed_note = "not mixed"
    preflight_rows: list[dict] = []
    punch_rows: list[dict] = []
    provenance: dict = {}
    ident = ""
    slug = ""
    proxy = False
    encoder_name = "auto"
    punch_count = 0
    error_s: str | None = None
    ledger_enabled = not bool(args.no_ledger)
    ledger_path = Path(args.ledger).expanduser() if args.ledger else DEFAULT_LEDGER
    ledger_ready = False
    stages = {
        "preflight": 0.0,
        "spine": 0.0,
        "stills": 0.0,
        "pregrade": 0.0,
        "finish": 0.0,
        "qa": 0.0,
        "deliver": 0.0,
    }
    stage_t0: dict[str, float] = {}

    def stage_start(name: str) -> None:
        stage_t0[name] = time.monotonic()

    def stage_stop(name: str) -> None:
        t0 = stage_t0.pop(name, None)
        if t0 is not None:
            stages[name] = round(time.monotonic() - t0, 3)

    try:
        if not args.manifest.exists():
            raise RenderError(f"manifest not found: {args.manifest}", 2)
        try:
            raw = json.loads(args.manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RenderError(f"manifest is not JSON: {exc}", 2) from exc
        if not isinstance(raw, dict):
            raise RenderError("manifest must be a JSON object", 2)
        if not SCHEMA_PATH.is_file():
            raise RenderError(f"schema not found: {SCHEMA_PATH}", 2)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        style_path: Path | None = args.style
        if style_path is None:
            env_style = os.environ.get("REEL_STYLE")
            if env_style:
                style_path = Path(env_style)
        style_sha: str | None = None
        if style_path is not None:
            if not style_path.is_file():
                raise RenderError(f"style not found: {style_path}", 2)
            style_sha = sha16_file(style_path)
            style_data, broll_defaults = load_style(style_path)
            raw = deep_merge_under(style_data, raw)
            apply_broll_defaults(raw, broll_defaults)
            print(f"[render-reel] style {style_path} sha16={style_sha}")
        validate_manifest(raw, schema)
        original_broll = [dict(x) for x in (raw.get("broll") or [])]
        manifest = apply_defaults(copy.deepcopy(raw), schema)
        manifest_dir = args.manifest.parent.resolve()
        resolve_manifest_paths(manifest, manifest_dir)

        unsourced = unsourced_broll_lines(manifest)
        if unsourced:
            eprint("ERROR: unsourced broll (empty path):")
            for _i, line in unsourced:
                eprint(f"  {line}")
            eprint(
                "Propose candidates: broll-search.py --lines-from-manifest "
                + str(args.manifest)
            )
            raise RenderError("unsourced broll path", 2)

        stage_start("preflight")
        problems = preflight(manifest)
        if problems:
            eprint("ERROR: preflight failed:")
            for item in problems:
                eprint(f"  {item}")
            raise RenderError("preflight failed", 2)
        preflight_rows = brief_preflight_lint(manifest)
        print_preflight_table(preflight_rows)
        stage_stop("preflight")
        if args.strict and any(r["status"] == "WARN" for r in preflight_rows):
            raise RenderError("preflight lint failed (--strict)", 2)

        ident = str(manifest["id"])
        slug = str(manifest["slug"])
        output_dir = Path(manifest["output_dir"])
        proxy = bool(args.proxy) or ((manifest.get("render") or {}).get("mode") == "proxy")
        version_n = pick_version(
            output_dir,
            ident,
            slug,
            proxy,
            args.version,
            manifest.get("version"),
        )
        tname = target_name(ident, slug, version_n, proxy)
        target = output_dir / tname
        if target.exists():
            raise RenderError(f"output exists (will not overwrite): {target}", 2)
        stem = target.stem
        print(f"[render-reel] version {version_n} -> {target.name}")
        ident = str(manifest["id"])
        slug = str(manifest["slug"])
        encoder_name = str((manifest.get("render") or {}).get("encoder") or "auto")
        ledger_ready = True

        if args.work_dir is not None:
            work = args.work_dir
        else:
            work = output_dir / ".work" / f"{ident}_v{version_n}"
        work.mkdir(parents=True, exist_ok=True)

        src = manifest["source"]
        spine_src = Path(src["video"])
        transcript = Path(src["transcript_json"])
        spine_color, spine_ymin = classify_color(
            "source", src.get("color") or "auto", spine_src, still=False
        )
        ymin_s = "n/a" if spine_ymin is None else f"{spine_ymin:.1f}"
        color_notes.append(f"source {spine_color} YMIN={ymin_s}")

        broll_colors: list[tuple[str, float | None]] = []
        for i, item in enumerate(manifest.get("broll") or []):
            still = is_still_item(item)
            path = Path(item["path"]) if item.get("path") else None
            decision, ymin = classify_color(
                f"broll[{i}]", item.get("color") or "auto", path, still=still
            )
            broll_colors.append((decision, ymin))
            ymin_s = "n/a" if ymin is None else f"{ymin:.1f}"
            color_notes.append(f"broll[{i}] {decision} YMIN={ymin_s}")

        ranges = [dict(r) for r in manifest["spine"]["ranges"]]
        ranges.sort(key=lambda r: float(r["start"]))
        hook = manifest.get("hook") or {}
        hook_mode = hook.get("mode") or "none"
        hook_range = hook.get("range")
        hook_source_val = hook.get("source")
        if hook_source_val in (None, "", "null"):
            hook_path = spine_src
            hook_same = True
        else:
            hook_path = Path(hook_source_val)
            hook_same = hook_path.resolve() == spine_src.resolve()
        lift = bool(hook.get("lift_from_spine", True))
        if hook_mode == "prepend" and hook_same and lift and hook_range:
            hs, he = float(hook_range[0]), float(hook_range[1])
            ranges = subtract_hook(ranges, hs, he)
            print(
                f"[render-reel] hook lift: removed {hs:.3f}-{he:.3f} from spine"
            )
            print(f"[render-reel] ranges: {format_ranges(ranges)}")
            hook_note = (
                f"prepend {hs:.3f}-{he:.3f} from same source; lifted from spine"
            )
        elif hook_mode == "prepend" and hook_range:
            hs, he = float(hook_range[0]), float(hook_range[1])
            print(
                f"[render-reel] hook from other file; spine ranges unchanged"
            )
            print(f"[render-reel] ranges: {format_ranges(ranges)}")
            hook_note = f"prepend {hs:.3f}-{he:.3f} from {hook_path.name}"
        else:
            hook_path = None
            hook_range = None
            print(f"[render-reel] ranges: {format_ranges(ranges)}")
            hook_note = "none (take opens on its own hook)"

        hard_out = manifest["spine"].get("hard_out")
        ranges = apply_hard_out(ranges, hard_out)
        if hard_out is not None:
            print(f"[render-reel] hard out {hard_out}; ranges: {format_ranges(ranges)}")
        if not ranges:
            raise RenderError("no spine ranges left after hook lift / hard out", 2)
        manifest["spine"]["ranges"] = ranges

        render = manifest.get("render") or {}
        width, height = (540, 960) if proxy else (1080, 1920)
        crf = int(render.get("crf") or 18)
        preset = str(render.get("preset") or "fast")
        if proxy and preset == "fast":
            preset = "ultrafast"
        cover = manifest.get("cover") or {}
        cover_text = apply_cover_case(cover.get("text") or "", cover.get("case") or "as-is")
        captions_on = bool((manifest.get("captions") or {}).get("enabled", True))
        help_cut = help_text(CUT_VIDEO)
        help_fr = help_text(FINISH_REEL)
        help_stills = help_text(STILLS_TO_BROLL)
        help_qa = help_text(QA_REEL) if QA_REEL.is_file() else ""

        dry = bool(args.dry_run)
        if dry:
            est_joins = (
                list(manifest["joins"])
                if isinstance(manifest.get("joins"), list)
                else estimate_joins(ranges)
            )
            print("[render-reel] DRY RUN: commands for steps 7-16")

        lock_path = args.lock_file or DEFAULT_LOCK
        if not dry:
            lock_fd = acquire_lock(lock_path, args.lock_timeout, ident)

        spine_mp4 = work / "spine.mp4"
        spine_json = work / "spine.timeline.json"
        cut_argv = build_cut_video_args(
            source=spine_src,
            transcript=transcript,
            output=spine_mp4,
            ranges=ranges,
            spine=manifest["spine"],
            emit_json=spine_json,
            help_cut=help_cut,
            preset=preset,
            crf=crf,
        )
        stage_start("spine")
        rc = run_python(CUT_VIDEO, cut_argv, dry, commands, "cut-video.py")
        stage_stop("spine")
        if rc != 0:
            raise RenderError("cut-video.py failed", 3)

        timeline: dict = {}
        if not dry and spine_json.is_file():
            timeline = json.loads(spine_json.read_text(encoding="utf-8"))
            out_timeline = output_dir / f"{stem}.timeline.json"
            shutil.copy2(spine_json, out_timeline)
        elif dry:
            timeline = fabricate_coarse_timeline(ranges)
        if not (timeline.get("coarse_ranges") or []):
            timeline = fabricate_coarse_timeline(ranges)

        policy = load_broll_policy(manifest)
        noun_words = load_transcript_words(transcript) if transcript.is_file() else []
        noun_rows = on_the_noun_lint(manifest, timeline, noun_words, policy)
        if noun_rows:
            preflight_rows.extend(noun_rows)
            print("[render-reel] Preflight", flush=True)
            print(format_preflight_table(noun_rows), flush=True)
            for row in noun_rows:
                if row["status"] == "WARN":
                    print(f"WARN  {row['check']}: {row['detail']}", flush=True)
        if args.strict and any(r.get("status") == "WARN" for r in noun_rows):
            raise RenderError("preflight lint failed (--strict)", 2)

        if isinstance(manifest.get("joins"), list):
            joins = [float(x) for x in manifest["joins"]]
        elif timeline:
            joins = joins_from_timeline(timeline)
        else:
            joins = estimate_joins(ranges)
        print(f"[render-reel] joins: {', '.join(f'{j:.3f}' for j in joins) or '(none)'}")

        broll_specs: list[dict] = []
        supers: list[str] = []
        punch_rows = []
        still_eq = None
        src_eq = src.get("eq")
        if src_eq and src_eq != "none":
            still_eq = src_eq

        stage_start("stills")
        for i, item in enumerate(manifest.get("broll") or []):
            orig = original_broll[i] if i < len(original_broll) else {}
            dur = punch_duration(item, orig)
            at = float(item["at"])
            path = Path(item["path"])
            kind = "still" if is_still_item(item) else "clip"
            used = path
            if kind == "still":
                still_out = work / f"still_{i}.mp4"
                s_argv = [
                    "--image", str(path),
                    "--output", str(still_out),
                    "--dur", str(dur),
                    "--width", str(width),
                    "--height", str(height),
                    "--crf", str(min(crf + 4, 28)),
                ]
                if help_has(help_stills, "--zoom"):
                    s_argv += ["--zoom", str(item.get("zoom") or 1.10)]
                if help_has(help_stills, "--direction"):
                    s_argv += ["--direction", str(item.get("direction") or "in")]
                if item.get("focus") and help_has(help_stills, "--focus"):
                    fx, fy = item["focus"]
                    s_argv += ["--focus", f"{fx},{fy}"]
                b_eq = item.get("eq")
                if b_eq and b_eq != "none" and help_has(help_stills, "--eq"):
                    s_argv += ["--eq", str(b_eq)]
                elif still_eq and help_has(help_stills, "--eq"):
                    pass
                rc = run_python(
                    STILLS_TO_BROLL, s_argv, dry, commands, "stills-to-broll.py"
                )
                if rc != 0:
                    raise RenderError("stills-to-broll.py failed", 3)
                used = still_out
            spec = {"path": str(used), "at": at, "dur": dur, "src": item.get("src")}
            broll_specs.append(spec)
            super_obj = item.get("super")
            super_text = ""
            if super_obj:
                super_text = str(super_obj.get("text") or "")
                sdur = super_obj.get("dur")
                if sdur is None:
                    sdur = dur
                supers.append(f"{super_text}:at={at}:dur={sdur}")
            punch_rows.append({
                "at": at,
                "file": path.name,
                "kind": kind,
                "dur": dur,
                "line": item.get("line") or "",
                "shows": str(item.get("shows") or ""),
                "grade": str(item.get("grade") or "ungraded"),
                "verified": bool(item.get("verified")),
                "super": super_text,
            })
        stage_stop("stills")
        punch_count = len(punch_rows)

        lut_path = Path(src["lut"]) if src.get("lut") else None
        video_broll_colors = [
            broll_colors[i][0]
            for i, item in enumerate(manifest.get("broll") or [])
            if not is_still_item(item)
        ]
        # Stills are finished photography: Rec.709 by definition. A log spine with
        # any Rec.709 B-roll (stills or phone clips) is a mixed grade. The first
        # model bench (2026-09-05) put the LUT on the stills in all four runs
        # because only video B-roll was counted here.
        still_present = any(is_still_item(item) for item in (manifest.get("broll") or []))
        broll_colors_all = list(video_broll_colors) + (["rec709"] if still_present else [])
        mixed = bool(broll_colors_all) and any(c != spine_color for c in broll_colors_all)
        skip_lut = spine_color == "rec709"
        no_eq = src_eq == "none"
        eq_val = None if (not src_eq or src_eq == "none") else str(src_eq)
        broll_no_eq = False
        orig_eqs = [o.get("eq") for o in original_broll]
        if original_broll and all(e == "none" for e in orig_eqs):
            broll_no_eq = True
        elif any(e == "none" for e in orig_eqs):
            print(
                "[render-reel] some broll entries set eq=none but not all; "
                "--broll-no-eq not applied (engine flag is global)",
                flush=True,
            )
        finish_lut = lut_path if (spine_color == "log" and lut_path) else None
        fr_mod = None
        broll_no_lut = False

        if mixed and spine_color == "log" and lut_path is not None:
            # Keep the LUT in finish-reel for the A-roll and the hook; pre-grade
            # only the log B-roll clips here; leave Rec.709 clips and stills
            # untouched and switch the LUT and the match eq off for B-roll.
            mixed_note = (
                "mixed grade: spine log (LUT in finish-reel); broll "
                + ",".join(broll_colors_all)
                + ": log clips pre-graded, Rec.709 clips and stills untouched, B-roll LUT and eq off"
            )
            print(f"[render-reel] {mixed_note}")
            fr_mod = load_finish_reel()
            pre_eq = eq_val or DEFAULT_EQ
            stage_start("pregrade")
            for i, item in enumerate(manifest.get("broll") or []):
                if is_still_item(item) or broll_colors[i][0] != "log":
                    continue
                graded_b = work / f"pregraded_{i}.mp4"
                src_clip = Path(broll_specs[i]["path"])
                pregrade_clip(
                    src_clip, graded_b, lut_path, pre_eq,
                    width, height, None, dry, commands, fr_mod,
                )
                broll_specs[i]["path"] = str(graded_b)
            stage_stop("pregrade")
            broll_no_lut = True
            broll_no_eq = True
        elif mixed:
            mixed_note = (
                f"mixed grade: spine {spine_color}, broll "
                + ",".join(broll_colors_all)
            )
            print(f"[render-reel] {mixed_note}")
            fr_mod = load_finish_reel()
            pre_eq = eq_val or DEFAULT_EQ
            stage_start("pregrade")
            if spine_color == "log" and lut_path is not None:
                graded = work / "spine_pregraded.mp4"
                pregrade_clip(
                    spine_mp4, graded, lut_path, pre_eq,
                    width, height, src.get("rotate"), dry, commands, fr_mod,
                )
                spine_mp4 = graded
            for i, item in enumerate(manifest.get("broll") or []):
                if is_still_item(item):
                    continue
                color_i = broll_colors[i][0]
                clip_lut = lut_path if color_i == "log" else None
                graded_b = work / f"pregraded_{i}.mp4"
                src_clip = Path(broll_specs[i]["path"])
                pregrade_clip(
                    src_clip, graded_b, clip_lut, pre_eq,
                    width, height, None, dry, commands, fr_mod,
                )
                broll_specs[i]["path"] = str(graded_b)
            skip_lut = True
            finish_lut = None
            broll_no_eq = True
            no_eq = True
            stage_stop("pregrade")
        elif spine_color == "rec709":
            skip_lut = True
            finish_lut = None
            mixed_note = "spine rec709; LUT skipped"
        else:
            mixed_note = "spine log; LUT applied in finish-reel"
            if lut_path is None:
                eprint("source classified log but source.lut is empty; skipping LUT")
                skip_lut = True

        inserts = list(manifest.get("inserts") or [])
        if len(inserts) > 1:
            raise RenderError("this renderer accepts at most one insert", 2)

        qa_dir = work / "qa"
        finish_emit = output_dir / f"{target.name}.timeline.json"
        ass_out = output_dir / f"{stem}.ass"
        insert_used = False
        finish_out = target

        def finish_call(
            *,
            spine_file: Path,
            out_file: Path,
            part_ranges: list[dict],
            part_joins: list[float],
            part_broll: list[dict],
            part_supers: list[str],
            with_hook: bool,
            with_cover: str,
            extra_argv: list[str] | None = None,
        ) -> None:
            argv = build_finish_argv(
                help_fr=help_fr,
                spine=spine_file,
                output=out_file,
                manifest=manifest,
                ranges=part_ranges,
                hook_path=hook_path if with_hook else None,
                hook_range=hook_range if with_hook else None,
                lut=finish_lut,
                skip_lut=skip_lut,
                eq=eq_val,
                no_eq=no_eq,
                broll_no_eq=broll_no_eq,
                broll_no_lut=broll_no_lut,
                broll_specs=part_broll,
                joins=part_joins,
                supers=part_supers,
                cover_text=with_cover,
                width=width,
                height=height,
                crf=crf,
                preset=preset,
                proxy=proxy,
                qa_dir=qa_dir if out_file == target else None,
                emit_json=finish_emit if out_file == target else None,
                ass_out=ass_out if out_file == target else None,
                captions_on=captions_on,
            )
            if extra_argv:
                argv += extra_argv
            rc_local = run_python(FINISH_REEL, argv, dry, commands, "finish-reel.py")
            if rc_local != 0:
                raise RenderError("finish-reel.py failed", 3)

        stage_start("finish")
        if inserts:
            insert = inserts[0]
            insert_used = True
            split_t_src = float(insert["after_word_end"])
            split_t = src_time_to_out(timeline, split_t_src) if not dry else None
            if split_t is None:
                # Fall back: estimate from coarse ranges.
                split_t = 0.0
                acc = 0.0
                for rng in ranges:
                    s, e = float(rng["start"]), float(rng["end"])
                    if split_t_src <= s:
                        split_t = acc
                        break
                    if split_t_src >= e:
                        acc += e - s
                        split_t = acc
                    else:
                        split_t = acc + (split_t_src - s)
                        break
            print(f"[render-reel] insert after source {split_t_src:.3f}s -> spine {split_t:.3f}s")
            part_a_ranges, part_b_ranges = split_ranges_at(ranges, split_t_src)
            part_a_mp4 = work / "spine_part_a.mp4"
            part_b_mp4 = work / "spine_part_b.mp4"
            if dry:
                print("[render-reel] DRY split spine at " + f"{split_t:.3f}s")
            else:
                run_ffmpeg(
                    [
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", str(spine_mp4), "-t", f"{split_t:.3f}",
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", "-ar", "48000",
                        str(part_a_mp4),
                    ],
                    dry, commands,
                )
                run_ffmpeg(
                    [
                        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{split_t:.3f}", "-i", str(spine_mp4),
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", "-ar", "48000",
                        str(part_b_mp4),
                    ],
                    dry, commands,
                )
            insert_cut = work / "insert_cut.mp4"
            insert_json = work / "insert.timeline.json"
            ins_ranges = [{"start": insert["range"][0], "end": insert["range"][1]}]
            ins_argv = build_cut_video_args(
                source=Path(insert["source"]),
                transcript=Path(insert["transcript_json"]),
                output=insert_cut,
                ranges=ins_ranges,
                spine=manifest["spine"],
                emit_json=insert_json,
                help_cut=help_cut,
                preset=preset,
                crf=crf,
            )
            rc = run_python(CUT_VIDEO, ins_argv, dry, commands, "cut-video.py")
            if rc != 0:
                raise RenderError("cut-video.py failed on insert", 3)
            broll_a = [b for b in broll_specs if float(b["at"]) < split_t]
            broll_b = []
            for b in broll_specs:
                if float(b["at"]) >= split_t:
                    nb = dict(b)
                    nb["at"] = float(b["at"]) - split_t
                    broll_b.append(nb)
            joins_a = [j for j in joins if j < split_t]
            joins_b = [j - split_t for j in joins if j >= split_t]
            supers_a = []
            supers_b = []
            for s in supers:
                # TEXT:at=SEC:dur=SEC
                if ":at=" not in s:
                    continue
                text, rest = s.split(":at=", 1)
                at_s = float(rest.split(":")[0])
                dur_bit = rest.split("dur=")[-1] if "dur=" in rest else "1"
                if at_s < split_t:
                    supers_a.append(s)
                else:
                    supers_b.append(f"{text}:at={at_s - split_t}:dur={dur_bit}")
            finished_a = work / "finished_a.mp4"
            finished_ins = work / "finished_insert.mp4"
            finished_b = work / "finished_b.mp4"
            extra_ins = ["--orient", "auto"]
            if insert.get("rotate") is not None:
                extra_ins += ["--rotate", str(insert["rotate"])]
            if insert.get("super"):
                extra_ins += ["--super", f"{insert['super']}:at=0:dur=3.5"]
            finish_call(
                spine_file=part_a_mp4,
                out_file=finished_a,
                part_ranges=part_a_ranges,
                part_joins=joins_a,
                part_broll=broll_a,
                part_supers=supers_a,
                with_hook=True,
                with_cover=cover_text,
            )
            finish_call(
                spine_file=insert_cut,
                out_file=finished_ins,
                part_ranges=ins_ranges,
                part_joins=[],
                part_broll=[],
                part_supers=[],
                with_hook=False,
                with_cover="",
                extra_argv=extra_ins,
            )
            finish_call(
                spine_file=part_b_mp4,
                out_file=finished_b,
                part_ranges=part_b_ranges,
                part_joins=joins_b,
                part_broll=broll_b,
                part_supers=supers_b,
                with_hook=False,
                with_cover="",
            )
            concat_list = work / "concat.txt"
            lines = (
                f"file '{finished_a}'\n"
                f"file '{finished_ins}'\n"
                f"file '{finished_b}'\n"
            )
            if not dry:
                concat_list.write_text(lines, encoding="utf-8")
            run_ffmpeg(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000",
                    "-movflags", "+faststart",
                    str(target),
                ],
                dry, commands,
            )
        else:
            finish_call(
                spine_file=spine_mp4,
                out_file=target,
                part_ranges=ranges,
                part_joins=joins,
                part_broll=broll_specs,
                part_supers=supers,
                with_hook=hook_mode == "prepend",
                with_cover=cover_text,
            )
        stage_stop("finish")

        release_lock(lock_fd)
        lock_fd = None

        provenance = build_provenance(
            manifest,
            style_path=style_path,
            style_sha=style_sha,
            manifest_path=args.manifest,
        )
        resolved_path = output_dir / f"{stem}.reel.json"
        resolved = copy.deepcopy(manifest)
        resolved["version"] = version_n
        resolved["provenance"] = provenance
        if not dry:
            resolved_path.write_text(
                json.dumps(resolved, indent=2) + "\n", encoding="utf-8"
            )

        if not dry and target.is_file():
            duration_s = probe_duration(target)
        elif dry:
            duration_s = float((timeline or {}).get("duration_s") or 0.0)
            if hook_mode == "prepend" and hook_range:
                duration_s += float(hook_range[1]) - float(hook_range[0])

        qa_summary = "skipped"
        qa_report_path: Path | None = Path(str(target) + ".qa.json") if target else None
        stage_start("qa")
        if dry:
            if QA_REEL.is_file() and not args.no_qa:
                print(
                    "[render-reel] DRY "
                    + pretty_cmd([
                        sys.executable, str(QA_REEL),
                        "--video", str(target),
                        "--manifest", str(resolved_path),
                    ])
                )
            qa_verdict = "skipped"
        elif args.no_qa:
            qa_verdict = "skipped"
            qa_summary = "skipped (--no-qa)"
        elif not QA_REEL.is_file():
            qa_verdict = "skipped"
            qa_summary = "skipped (qa-reel.py not present)"
            print("[render-reel] qa-reel.py not beside this script; skipping QA")
        else:
            qa_report = Path(str(target) + ".qa.json")
            frames_dir = work / "qa-frames"
            sheet_path = output_dir / f"{stem}.sheet.jpg"
            qa_argv = ["--video", str(target)]
            if help_has(help_qa, "--manifest"):
                qa_argv += ["--manifest", str(resolved_path)]
            else:
                notice_omit("--manifest", "qa-reel.py")
            if help_has(help_qa, "--timeline"):
                tl = output_dir / f"{stem}.timeline.json"
                qa_argv += ["--timeline", str(tl)]
            else:
                notice_omit("--timeline", "qa-reel.py")
            if help_has(help_qa, "--report"):
                qa_argv += ["--report", str(qa_report)]
            else:
                notice_omit("--report", "qa-reel.py")
            if help_has(help_qa, "--frames-dir"):
                qa_argv += ["--frames-dir", str(frames_dir)]
            else:
                notice_omit("--frames-dir", "qa-reel.py")
            if help_has(help_qa, "--contact-sheet"):
                qa_argv += ["--contact-sheet", str(sheet_path)]
            else:
                notice_omit("--contact-sheet", "qa-reel.py")
            if help_has(help_qa, "--max-px"):
                qa_argv += ["--max-px", str((manifest.get("qa") or {}).get("max_frame_px", 540))]
            else:
                notice_omit("--max-px", "qa-reel.py")
            qa_rc = run_python(QA_REEL, qa_argv, False, commands, "qa-reel.py")
            if qa_report.is_file():
                try:
                    qdata = json.loads(qa_report.read_text(encoding="utf-8"))
                    qa_verdict = str(
                        qdata.get("verdict") or qdata.get("qa_verdict") or "warn"
                    )
                    raw_fails = qdata.get("fails") or qdata.get("fail_ids") or []
                    qa_fails = []
                    for item in raw_fails:
                        if isinstance(item, dict):
                            qa_fails.append(str(item.get("id") or item.get("name") or item))
                        else:
                            qa_fails.append(str(item))
                    raw_warns = qdata.get("warns") or qdata.get("warnings") or []
                    qa_warns = [str(x) for x in raw_warns]
                    qa_summary = json.dumps(qa_fails or qa_verdict)
                    if qdata.get("contact_sheet"):
                        sheet_path = Path(qdata["contact_sheet"])
                except json.JSONDecodeError:
                    qa_verdict = "warn"
                    qa_summary = "qa report was not JSON"
            if qa_rc == 3:
                qa_verdict = "fail"
                qa_summary = "qa-reel.py exit 3"
                exit_code = 4
            elif qa_rc != 0 and qa_verdict == "skipped":
                qa_verdict = "warn"
                qa_summary = f"qa-reel.py exit {qa_rc}"
            elif qa_rc == 0 and qa_verdict == "skipped":
                qa_verdict = "pass"
                qa_summary = "pass"
        stage_stop("qa")

        hook_dur = 0.0
        if hook_mode == "prepend" and hook_range:
            hook_dur = float(hook_range[1]) - float(hook_range[0])
        window = manifest["duration_window"]
        dur_note = (
            f"{duration_s:.2f}s vs window [{window[0]}, {window[1]}]"
        )
        if duration_s and (duration_s < float(window[0]) or duration_s > float(window[1])):
            dur_note += " (outside window)"
        else:
            dur_note += " (inside window)" if duration_s else " (not measured)"

        loudness_note = "not measured"
        for candidate in (
            Path(str(target) + ".timeline.json") if target else None,
            output_dir / f"{stem}.timeline.json" if target else None,
            Path(str(target) + ".qa.json") if target else None,
        ):
            if candidate is None or not candidate.is_file():
                continue
            try:
                blob = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for key in ("loudness", "loudnorm", "input_i", "output_i"):
                if key in blob:
                    loudness_note = json.dumps(blob.get(key))
                    break
            meas = blob.get("measurements") or blob.get("audio") or {}
            if isinstance(meas, dict) and (
                "input_i" in meas or "i" in meas or "loudness" in meas
            ):
                loudness_note = json.dumps(meas)

        specs_note = "not measured"
        if target is not None and target.is_file():
            specs = probe_specs(target)
            specs_note = (
                f"{specs.get('width')}x{specs.get('height')} "
                f"pix_fmt={specs.get('pix_fmt')} codec={specs.get('codec')} "
                f"duration={specs.get('duration')}"
            )

        table_lines: list[str] = []
        if not punch_rows:
            table_lines.append("|  |  |  |  |  |  |  |  |  |  |")
        for row in punch_rows:
            final_t = float(row["at"]) + hook_dur
            table_lines.append(
                f"| {row['at']:.2f} | {final_t:.2f} | {row['file']} | "
                f"{row['kind']} | {row['dur']:.2f} | {row['line']} | "
                f"{row.get('shows') or ''} | {row.get('grade') or 'ungraded'} | "
                f"{str(row['verified']).lower()} | {row['super']} |"
            )
        punch_table = "\n".join(table_lines)
        joins_note = (
            ", ".join(f"{j:.2f}s" for j in joins) if joins else "none"
        )
        if joins:
            joins_note = "covered at " + joins_note
        artifacts = [
            str(target) if target else "",
            str(resolved_path),
        ]
        if (output_dir / f"{stem}.timeline.json").is_file():
            artifacts.append(str(output_dir / f"{stem}.timeline.json"))
        srt_path = target.with_suffix(".srt") if target else None
        cover_frame_path = target.with_suffix(".cover.jpg") if target else None
        if srt_path and srt_path.is_file():
            artifacts.append(str(srt_path))
        if cover_frame_path and cover_frame_path.is_file():
            artifacts.append(str(cover_frame_path))
        runnotes_path = output_dir / f"{stem}-RUNNOTES.md"
        sheet_s = str(sheet_path) if sheet_path and sheet_path.exists() else (
            str(sheet_path) if sheet_path else "(none)"
        )
        deviation_items = collect_deviations(
            duration_s=duration_s,
            window=window,
            punch_rows=punch_rows,
            cover_text=cover_text,
            proxy=proxy,
            qa_verdict=qa_verdict,
            qa_fails=qa_fails,
            qa_warns=qa_warns,
            preflight_rows=preflight_rows,
        )
        deviations_s = "\n".join(f"- {x}" for x in deviation_items) if deviation_items else "None."
        if not dry:
            write_runnotes(
                runnotes_path,
                {
                    "id": ident,
                    "slug": slug,
                    "version": str(version_n),
                    "mode": "proxy" if proxy else "final",
                    "notes": str(manifest.get("notes") or "(none)"),
                    "preflight": format_preflight_markdown(preflight_rows),
                    "deviations": deviations_s,
                    "punch_table": punch_table,
                    "joins": joins_note,
                    "hook": hook_note,
                    "color": "; ".join(color_notes) + ". " + mixed_note,
                    "loudness": loudness_note,
                    "duration": dur_note,
                    "specs": specs_note,
                    "qa": qa_summary,
                    "commands": "\n".join(pretty_cmd(c) for c in commands),
                    "artifacts": "\n".join(a for a in artifacts if a),
                    "sheet": sheet_s,
                    "provenance": format_provenance(provenance) if provenance else "(none)",
                },
            )
            print(f"[render-reel] wrote {runnotes_path}")
        else:
            print("[render-reel] DRY would write " + str(runnotes_path))

        stage_start("deliver")
        if dry:
            print("[render-reel] DRY skip deliver")
        elif args.no_deliver:
            print("[render-reel] --no-deliver; skip copy_to")
        else:
            copies = ((manifest.get("deliver") or {}).get("copy_to")) or []
            for dest_s in copies:
                dest_dir = Path(dest_s)
                dest_dir.mkdir(parents=True, exist_ok=True)
                if target and target.is_file():
                    shutil.copy2(target, dest_dir / target.name)
                if runnotes_path and runnotes_path.is_file():
                    shutil.copy2(runnotes_path, dest_dir / runnotes_path.name)
                if sheet_path and sheet_path.is_file():
                    shutil.copy2(sheet_path, dest_dir / sheet_path.name)
                print(f"[render-reel] delivered to {dest_dir}")
        stage_stop("deliver")

        if dry:
            failed = False
            exit_code = 0
        elif exit_code == 4:
            failed = True
        else:
            failed = False
            exit_code = 0

        finish_tl = None
        if target is not None:
            for cand in (
                Path(str(target) + ".timeline.json"),
                output_dir / f"{stem}.timeline.json",
            ):
                if cand.is_file():
                    try:
                        finish_tl = json.loads(cand.read_text(encoding="utf-8"))
                        break
                    except json.JSONDecodeError:
                        continue
        loudness_info = loudness_from_timeline(finish_tl)
        if finish_tl and finish_tl.get("encoder"):
            encoder_name = str(finish_tl.get("encoder"))

        stills_n = sum(
            1 for it in (manifest.get("broll") or [])
            if isinstance(it, dict) and is_still_item(it)
        )
        shows_missing_n = sum(
            1 for it in (manifest.get("broll") or [])
            if isinstance(it, dict)
            and (it.get("path") or "")
            and not str(it.get("shows") or "").strip()
        )
        on_noun_misses = sum(
            1 for r in preflight_rows
            if r.get("check") == "on the noun" and r.get("status") == "WARN"
        )
        summary = {
            "output": str(target) if target else None,
            "version": version_n,
            "duration_s": duration_s,
            "qa_verdict": qa_verdict,
            "timeline": str(output_dir / f"{stem}.timeline.json"),
            "qa": str(qa_report_path) if qa_report_path else None,
            "runnotes": str(runnotes_path) if runnotes_path else None,
            "sheet": str(sheet_path) if sheet_path and sheet_path.exists() else None,
            "srt": str(srt_path) if srt_path else None,
            "cover_frame": str(cover_frame_path) if cover_frame_path else None,
            "ledger": str(ledger_path) if ledger_enabled else None,
            "stills": stills_n,
            "shows_missing": shows_missing_n,
            "on_noun_misses": on_noun_misses,
        }
        print(json.dumps(summary), flush=True)

        return exit_code

    except RenderError as exc:
        eprint(f"ERROR: {exc}")
        exit_code = exc.code
        failed = True
        error_s = str(exc)
        return exit_code
    except BrokenPipeError:
        return 0
    finally:
        if ledger_enabled and ledger_ready:
            if exit_code == 0:
                status = "ok"
            elif exit_code == 4:
                status = "qa_fail"
            else:
                status = "error"
            window_val = None
            try:
                window_val = list(manifest.get("duration_window") or [])
            except Exception:
                window_val = None
            engine = {}
            for name in ENGINE_SCRIPTS:
                engine[name] = sha16_file(SCRIPTS / name)
            finish_tl = None
            if target is not None:
                cand = Path(str(target) + ".timeline.json")
                if cand.is_file():
                    try:
                        finish_tl = json.loads(cand.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        finish_tl = None
            loudness_info = loudness_from_timeline(finish_tl)
            rec = {
                "ts": iso_now(),
                "id": ident or None,
                "slug": slug or None,
                "version": version_n or None,
                "proxy": bool(proxy),
                "output": str(target) if target else None,
                "duration_s": duration_s,
                "duration_window": window_val,
                "stages": dict(stages),
                "qa_verdict": qa_verdict,
                "qa_fails": list(qa_fails),
                "loudness": loudness_info,
                "punch_count": punch_count,
                "encoder": encoder_name,
                "ffmpeg_version": (provenance or {}).get("ffmpeg_version")
                or ffmpeg_version_line(),
                "manifest_sha16": (provenance or {}).get("manifest_sha16")
                or sha16_file(args.manifest),
                "engine": engine,
                "status": status,
                "error": error_s,
                "model_cost_usd": None,
            }
            try:
                append_ledger(ledger_path, rec)
            except OSError as exc:
                eprint(f"ERROR: ledger write failed: {exc}")
        release_lock(lock_fd)
        if work is not None and work.exists():
            keep = bool(args.keep_work) or failed
            if not keep:
                shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
