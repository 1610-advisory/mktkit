#!/usr/bin/env python3
"""Regression runner for reel fixtures.

Renders every fixture in a directory (proxy mode by default), runs the QA
gate, checks expectations, and optionally compares against a gold mp4.
Turns "the skill works" into a command with an exit code.

Fixture layout (client-side, never in this repo)
------------------------------------------------
A fixtures directory holds, per fixture:

  <name>.reel.json       full reel manifest (schema reel-manifest/1).
                         output_dir is ignored; the runner overrides it.
  <name>.fixture.json    descriptor (schema reel-fixture/1). See
                         resources/fixture.example.json.

Descriptor shape::

    {
      "schema": "reel-fixture/1",
      "name": "A",
      "manifest": "A.reel.json",
      "gold": "/path/to/gold.mp4" or null,
      "expect": {
        "duration_window": [45, 60],
        "punch_count": 5,
        "hook_present": true,
        "cover_text": "EXAMPLE COVER",
        "qa_verdict": "pass"
      },
      "gold_tolerance": {"duration_s": 8.0, "ssim_min": 0.45},
      "notes": "why this fixture exists"
    }

Exit codes
----------
0  every fixture met its expectations
3  at least one fixture failed
2  setup problem (no fixtures, missing manifest, renderer missing)

Usage
-----
    regress.py --fixtures DIR [--only A,B] [--run-dir DIR]
               [--proxy|--final] [--report out.md] [--json out.json]
               [--skip-render] [--dry-run] [--keep] [--timeout-min 40]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent
RENDERER = SCRIPTS_DIR / "render-reel.py"
QA_SCRIPT = SCRIPTS_DIR / "qa-reel.py"

EXIT_OK = 0
EXIT_SETUP = 2
EXIT_FAIL = 3

DEFAULT_TIMEOUT_MIN = 40
REQUIRED_MANIFEST_KEYS = (
    "schema",
    "id",
    "slug",
    "output_dir",
    "duration_window",
    "source",
    "spine",
)
VERDICT_RANK = {"pass": 2, "warn": 1, "fail": 0}
SSIM_ALL_RE = re.compile(r"\bAll:([0-9]+(?:\.[0-9]+)?|\.[0-9]+)")
SSIM_NOTE = (
    "SSIM is measured after scaling both files to 540x960. "
    "A proxy against a full-res gold is comparable but soft."
)


class SetupError(Exception):
    """Preflight failure. Maps to exit 2."""


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def die(msg: str, code: int = EXIT_SETUP) -> None:
    eprint(f"[regress] {msg}")
    raise SystemExit(code)


def pretty_cmd(cmd: list[str]) -> str:
    parts = []
    for c in cmd:
        s = str(c)
        if any(ch in s for ch in ' \t\n:"\''):
            parts.append("'" + s.replace("'", "'\\''") + "'")
        else:
            parts.append(s)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Pure functions (tested without ffmpeg)
# ---------------------------------------------------------------------------

def parse_ssim_all(text: str) -> float | None:
    """Return the last All: value from ffmpeg ssim stderr, or None."""
    if not text:
        return None
    matches = SSIM_ALL_RE.findall(text)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except ValueError:
        return None


def parse_last_json_line(text: str) -> dict | None:
    """Parse the last stdout line that is a JSON object."""
    if not text:
        return None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line[0] != "{":
            continue
        try:
            val = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(val, dict):
            return val
    return None


def parse_summary_json(text: str) -> dict | None:
    """Last JSON line, or the whole stdout if it is one object."""
    last = parse_last_json_line(text)
    if last is not None:
        return last
    stripped = (text or "").strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            val = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(val, dict):
            return val
    return None


def has_flag(help_text: str, flag: str) -> bool:
    """True if --help text documents this flag as its own token."""
    if not help_text or not flag:
        return False
    return re.search(rf"(?:^|\s){re.escape(flag)}(?:\s|,|$|=)", help_text) is not None


def apply_cover_case(text: str, case: str | None) -> str:
    """Apply manifest cover.case to cover.text."""
    if text is None:
        return ""
    mode = (case or "as-is").lower()
    if mode == "upper":
        return text.upper()
    if mode == "sentence":
        if not text:
            return text
        return text[:1].upper() + text[1:].lower()
    return text


def verdict_at_least(actual: str | None, expected: str | None) -> bool:
    """True if actual is at least as good as expected (pass >= warn >= fail)."""
    if expected is None:
        return True
    exp = str(expected).lower()
    act = str(actual).lower() if actual is not None else ""
    return VERDICT_RANK.get(act, -1) >= VERDICT_RANK.get(exp, 99)


def evaluate_expectations(
    expect: dict | None,
    *,
    duration_s: float | None = None,
    punch_count: int | None = None,
    hook_present: bool | None = None,
    cover_text: str | None = None,
    qa_verdict: str | None = None,
) -> list[dict]:
    """Compare a fixture expect block to measured values.

    Returns a list of {id, ok, detail} dicts. Keys absent from expect are
    not checked. Pure: no I/O.
    """
    checks: list[dict] = []
    if not isinstance(expect, dict) or not expect:
        return checks

    if "duration_window" in expect:
        window = expect["duration_window"]
        try:
            lo, hi = float(window[0]), float(window[1])
        except (TypeError, ValueError, IndexError, KeyError):
            checks.append(
                {
                    "id": "duration",
                    "ok": False,
                    "detail": "bad duration_window",
                }
            )
        else:
            if duration_s is None:
                checks.append(
                    {
                        "id": "duration",
                        "ok": False,
                        "detail": f"duration missing, expected [{lo}, {hi}]",
                    }
                )
            elif lo <= duration_s <= hi:
                checks.append(
                    {
                        "id": "duration",
                        "ok": True,
                        "detail": f"{duration_s:.2f}s in [{lo:g}, {hi:g}]",
                    }
                )
            else:
                checks.append(
                    {
                        "id": "duration",
                        "ok": False,
                        "detail": f"{duration_s:.2f}s outside [{lo:g}, {hi:g}]",
                    }
                )

    if "punch_count" in expect:
        wanted = expect["punch_count"]
        if punch_count is None:
            checks.append(
                {
                    "id": "punch_count",
                    "ok": False,
                    "detail": f"punch count missing, expected {wanted}",
                }
            )
        elif punch_count == wanted:
            checks.append(
                {
                    "id": "punch_count",
                    "ok": True,
                    "detail": f"{punch_count}",
                }
            )
        else:
            checks.append(
                {
                    "id": "punch_count",
                    "ok": False,
                    "detail": f"got {punch_count}, expected {wanted}",
                }
            )

    if "hook_present" in expect:
        wanted = bool(expect["hook_present"])
        if hook_present is None:
            checks.append(
                {
                    "id": "hook_present",
                    "ok": False,
                    "detail": f"hook flag missing, expected {wanted}",
                }
            )
        elif bool(hook_present) == wanted:
            checks.append(
                {
                    "id": "hook_present",
                    "ok": True,
                    "detail": str(wanted).lower(),
                }
            )
        else:
            checks.append(
                {
                    "id": "hook_present",
                    "ok": False,
                    "detail": f"got {hook_present}, expected {wanted}",
                }
            )

    if "cover_text" in expect:
        wanted = expect["cover_text"]
        if cover_text is None:
            checks.append(
                {
                    "id": "cover_text",
                    "ok": False,
                    "detail": "cover text missing",
                }
            )
        elif cover_text == wanted:
            checks.append(
                {
                    "id": "cover_text",
                    "ok": True,
                    "detail": cover_text,
                }
            )
        else:
            checks.append(
                {
                    "id": "cover_text",
                    "ok": False,
                    "detail": f"got {cover_text!r}, expected {wanted!r}",
                }
            )

    if "qa_verdict" in expect:
        wanted = expect["qa_verdict"]
        if qa_verdict is None:
            checks.append(
                {
                    "id": "qa_verdict",
                    "ok": False,
                    "detail": f"qa verdict missing, expected {wanted}",
                }
            )
        elif verdict_at_least(qa_verdict, wanted):
            checks.append(
                {
                    "id": "qa_verdict",
                    "ok": True,
                    "detail": f"{qa_verdict} (need at least {wanted})",
                }
            )
        else:
            checks.append(
                {
                    "id": "qa_verdict",
                    "ok": False,
                    "detail": f"got {qa_verdict}, need at least {wanted}",
                }
            )

    return checks


def evaluate_gold(
    gold_tolerance: dict | None,
    *,
    duration_s: float | None = None,
    gold_duration_s: float | None = None,
    ssim_min_measured: float | None = None,
) -> list[dict]:
    """Gold compare checks. Advisory unless gold_tolerance sets a threshold.

    Pure: no I/O. Duration delta FAILs when duration_s is set on the
    tolerance and the absolute delta is above it. SSIM FAILs when ssim_min
    is set and the measured min is below it (or missing).
    """
    checks: list[dict] = []
    if not isinstance(gold_tolerance, dict) or not gold_tolerance:
        return checks

    if "duration_s" in gold_tolerance:
        raw = gold_tolerance["duration_s"]
        if raw is None:
            if duration_s is not None and gold_duration_s is not None:
                delta = abs(duration_s - gold_duration_s)
                detail = f"delta {delta:.2f}s (advisory)"
            else:
                detail = "duration advisory (no floor)"
            checks.append(
                {"id": "gold_duration", "ok": True, "detail": detail}
            )
        else:
            try:
                limit = float(raw)
            except (TypeError, ValueError):
                checks.append(
                    {
                        "id": "gold_duration",
                        "ok": False,
                        "detail": "bad gold_tolerance.duration_s",
                    }
                )
            else:
                if duration_s is None or gold_duration_s is None:
                    checks.append(
                        {
                            "id": "gold_duration",
                            "ok": False,
                            "detail": "duration missing for gold compare",
                        }
                    )
                else:
                    delta = abs(duration_s - gold_duration_s)
                    if delta <= limit:
                        checks.append(
                            {
                                "id": "gold_duration",
                                "ok": True,
                                "detail": f"delta {delta:.2f}s within {limit:g}s",
                            }
                        )
                    else:
                        checks.append(
                            {
                                "id": "gold_duration",
                                "ok": False,
                                "detail": f"delta {delta:.2f}s exceeds {limit:g}s",
                            }
                        )

    if "ssim_min" in gold_tolerance:
        raw = gold_tolerance["ssim_min"]
        if raw is None:
            if ssim_min_measured is not None:
                detail = f"min SSIM {ssim_min_measured:.4f} (advisory)"
            else:
                detail = "ssim advisory (no floor)"
            checks.append(
                {"id": "gold_ssim", "ok": True, "detail": detail}
            )
        else:
            try:
                floor = float(raw)
            except (TypeError, ValueError):
                checks.append(
                    {
                        "id": "gold_ssim",
                        "ok": False,
                        "detail": "bad gold_tolerance.ssim_min",
                    }
                )
            else:
                if ssim_min_measured is None:
                    checks.append(
                        {
                            "id": "gold_ssim",
                            "ok": False,
                            "detail": f"ssim not computed, floor {floor:g}",
                        }
                    )
                elif ssim_min_measured < floor:
                    checks.append(
                        {
                            "id": "gold_ssim",
                            "ok": False,
                            "detail": f"min SSIM {ssim_min_measured:.4f} below {floor:g}",
                        }
                    )
                else:
                    checks.append(
                        {
                            "id": "gold_ssim",
                            "ok": True,
                            "detail": f"min SSIM {ssim_min_measured:.4f} >= {floor:g}",
                        }
                    )

    return checks


def ssim_sample_times(shorter_dur: float) -> list[float]:
    """Sample times: 1.0s, 40%, 85% of the shorter duration, clamped."""
    dur = max(float(shorter_dur), 0.1)
    pad = min(0.05, dur / 4.0)
    raw = [1.0, dur * 0.40, dur * 0.85]
    out = []
    for t in raw:
        clamped = min(max(pad, t), max(pad, dur - pad))
        out.append(round(clamped, 3))
    return out


def qa_verdict_of(qa: dict | None) -> str | None:
    if not isinstance(qa, dict):
        return None
    v = qa.get("verdict", qa.get("qa_verdict"))
    if isinstance(v, str) and v.strip():
        return v.strip().lower()
    summary = qa.get("summary")
    if isinstance(summary, dict):
        v = summary.get("verdict", summary.get("qa_verdict"))
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    return None


def qa_fail_ids(qa: dict | None) -> list[str]:
    if not isinstance(qa, dict):
        return []
    for key in ("fails", "fail_ids", "failing", "failures"):
        val = qa.get(key)
        if isinstance(val, list):
            out: list[str] = []
            for item in val:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    ident = item.get("id", item.get("name"))
                    if ident is not None:
                        out.append(str(ident))
            return out
    checks = qa.get("checks")
    if isinstance(checks, list):
        ids: list[str] = []
        for c in checks:
            if not isinstance(c, dict):
                continue
            status = str(c.get("status") or c.get("verdict") or "").lower()
            if status in {"fail", "failed"}:
                ids.append(str(c.get("id") or c.get("name") or "check"))
        return ids
    return []


def rendered_cover_text(manifest: dict | None, timeline: dict | None) -> str | None:
    """Cover text the renderer burned, or the manifest text after case."""
    if isinstance(timeline, dict):
        cover = timeline.get("cover")
        if isinstance(cover, dict) and isinstance(cover.get("text"), str):
            return cover["text"]
        if isinstance(timeline.get("cover_text"), str):
            return timeline["cover_text"]
    if not isinstance(manifest, dict):
        return None
    cover = manifest.get("cover")
    if not isinstance(cover, dict):
        return None
    text = cover.get("text")
    if not isinstance(text, str):
        return None
    return apply_cover_case(text, cover.get("case"))


def timeline_punch_count(timeline: dict | None) -> int | None:
    if not isinstance(timeline, dict):
        return None
    punches = timeline.get("punches")
    if isinstance(punches, list):
        return len(punches)
    n = timeline.get("punch_count")
    if isinstance(n, int):
        return n
    return None


def timeline_hook_present(timeline: dict | None) -> bool | None:
    if not isinstance(timeline, dict):
        return None
    if "hook_present" in timeline:
        return bool(timeline["hook_present"])
    hook = timeline.get("hook")
    if isinstance(hook, bool):
        return hook
    if isinstance(hook, dict):
        if "present" in hook:
            return bool(hook["present"])
        mode = hook.get("mode")
        if isinstance(mode, str):
            return mode != "none"
        return True
    if "hook" in timeline:
        return False
    return None


# ---------------------------------------------------------------------------
# Filesystem / process helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    try:
        val = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SetupError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SetupError(f"bad JSON: {path}: {exc}") from exc
    if not isinstance(val, dict):
        raise SetupError(f"bad JSON: {path}: not an object")
    return val


def script_help(script: Path) -> str:
    if not script.is_file():
        return ""
    try:
        r = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout or "") + (r.stderr or "")


def run_timed(cmd: list[str], timeout_s: float) -> tuple[int, str, str, bool]:
    """Run cmd. Return (code, stdout, stderr, timed_out).

    Uses a new session so ffmpeg children die with the parent on timeout.
    """
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        return 1, "", str(exc), False
    try:
        out, err = proc.communicate(timeout=timeout_s)
        return proc.returncode or 0, out or "", err or "", False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            out, err = proc.communicate()
        return proc.returncode or 1, out or "", err or "", True


def probe_duration(path: Path) -> float | None:
    if not path.is_file():
        return None
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except (ValueError, TypeError):
        return None


def _abs_path_field(obj: dict, key: str, base: Path) -> None:
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        return
    p = Path(val)
    if not p.is_absolute():
        obj[key] = str((base / p).resolve())


def resolve_manifest_paths(data: dict, base: Path) -> None:
    """Rewrite relative path fields against the original manifest directory."""
    source = data.get("source")
    if isinstance(source, dict):
        for k in ("video", "transcript_json", "lut"):
            _abs_path_field(source, k, base)
    hook = data.get("hook")
    if isinstance(hook, dict):
        for k in ("source", "transcript_json"):
            _abs_path_field(hook, k, base)
    cover = data.get("cover")
    if isinstance(cover, dict):
        _abs_path_field(cover, "font", base)
    captions = data.get("captions")
    if isinstance(captions, dict):
        _abs_path_field(captions, "font", base)
    qa = data.get("qa")
    if isinstance(qa, dict):
        _abs_path_field(qa, "banned_words_file", base)
    broll = data.get("broll")
    if isinstance(broll, list):
        for item in broll:
            if isinstance(item, dict):
                _abs_path_field(item, "path", base)
    inserts = data.get("inserts")
    if isinstance(inserts, list):
        for item in inserts:
            if isinstance(item, dict):
                _abs_path_field(item, "source", base)
                _abs_path_field(item, "transcript_json", base)


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return cleaned or "fixture"


def newest_mp4(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    files = [p for p in root.rglob("*.mp4") if p.is_file()]
    if not files:
        return None
    skip = {"work", "_work", "tmp", "temp"}

    def is_work(p: Path) -> bool:
        try:
            parts = p.relative_to(root).parts[:-1]
        except ValueError:
            return False
        return any(part.lower() in skip for part in parts)

    preferred = [p for p in files if not is_work(p)]
    pool = preferred or files
    return max(pool, key=lambda p: p.stat().st_mtime)


def sibling_with_suffix(video: Path, suffix: str) -> Path | None:
    """Match <stem>.qa.json next to <stem>.mp4 (suffix includes the extra bits)."""
    candidate = video.with_name(video.stem + suffix)
    return candidate if candidate.is_file() else None


FINISH_TIMELINE_KEYS = ("punches", "hook", "joins", "captions")


def is_finish_timeline(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    return any(key in data for key in FINISH_TIMELINE_KEYS)


def load_timeline_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def discover_finish_timeline(
    video: Path | None,
    run_dir: Path,
    summary: dict | None = None,
) -> tuple[Path | None, dict | None, bool]:
    """Same order as qa-reel.py. Returns (path, data, spine_only_seen).

    spine_only_seen is True when a JSON existed but had no punches/hook/joins/captions.
    """
    candidates: list[Path] = []
    if isinstance(summary, dict) and isinstance(summary.get("timeline"), str):
        candidates.append(Path(summary["timeline"]))
    if video is not None:
        candidates.append(Path(str(video) + ".timeline.json"))
        candidates.append(video.with_name(video.stem + ".timeline.json"))
        candidates.append(video.with_name(video.stem + ".finish.json"))
    if run_dir.is_dir():
        for name in ("*.mp4.timeline.json", "*.finish.json", "*.timeline.json"):
            candidates.extend(sorted(run_dir.rglob(name)))
    seen: set[str] = set()
    spine_only = False
    for path in candidates:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        data = load_timeline_file(path)
        if data is None:
            continue
        if is_finish_timeline(data):
            print(f"[regress] timeline {path}")
            return path, data, False
        spine_only = True
        eprint(f"[regress] skipping {path.name}: no punches/hook/joins/captions")
    return None, None, spine_only


def find_sidecar(video: Path | None, run_dir: Path, suffix: str, name: str) -> Path | None:
    if video is not None:
        p = sibling_with_suffix(video, suffix)
        if p is not None:
            return p
        p = video.with_name(name)
        if p.is_file():
            return p
    if run_dir.is_dir():
        matches = sorted(run_dir.rglob(name))
        if matches:
            return matches[0]
        if suffix:
            globbed = sorted(run_dir.rglob(f"*{suffix}"))
            files = [p for p in globbed if p.is_file()]
            if files:
                return files[0]
    return None


def find_contact_sheet(
    run_dir: Path, video: Path | None, qa: dict | None
) -> Path | None:
    if isinstance(qa, dict) and isinstance(qa.get("contact_sheet"), str):
        p = Path(qa["contact_sheet"])
        if p.is_file():
            return p
    if video is not None:
        for extra in (".sheet.jpg", ".sheet.png", ".contact-sheet.jpg", "_sheet.jpg"):
            p = sibling_with_suffix(video, extra)
            if p is not None:
                return p
    if run_dir.is_dir():
        for p in sorted(run_dir.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            if "sheet" in p.name.lower():
                return p
    return None


def output_from_summary(summary: dict | None) -> Path | None:
    if not isinstance(summary, dict):
        return None
    for k in ("output", "output_path", "mp4", "video"):
        v = summary.get(k)
        if isinstance(v, str) and v.strip():
            p = Path(v)
            if p.is_file():
                return p
    return None


def duration_from_summary(summary: dict | None) -> float | None:
    if not isinstance(summary, dict):
        return None
    for k in ("duration_s", "duration", "dur"):
        v = summary.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KiB"
    return f"{n / (1024 ** 2):.1f} MiB"


def human_secs(s: float | None) -> str:
    if s is None:
        return "n/a"
    return f"{s:.1f}s"


# ---------------------------------------------------------------------------
# Fixture discovery and command builders
# ---------------------------------------------------------------------------

class Fixture:
    def __init__(
        self,
        name: str,
        descriptor_path: Path,
        manifest_path: Path,
        descriptor: dict,
    ) -> None:
        self.name = name
        self.descriptor_path = descriptor_path
        self.manifest_path = manifest_path
        self.descriptor = descriptor

    @property
    def gold_path(self) -> Path | None:
        gold = self.descriptor.get("gold")
        if not isinstance(gold, str) or not gold.strip():
            return None
        p = Path(gold)
        if not p.is_absolute():
            p = self.descriptor_path.parent / p
        return p

    @property
    def expect(self) -> dict:
        val = self.descriptor.get("expect")
        return val if isinstance(val, dict) else {}

    @property
    def gold_tolerance(self) -> dict:
        val = self.descriptor.get("gold_tolerance")
        return val if isinstance(val, dict) else {}


def discover_fixtures(root: Path) -> list[Fixture]:
    out: list[Fixture] = []
    paths = sorted(root.glob("*.fixture.json"))
    for path in paths:
        desc = load_json(path)
        schema = desc.get("schema")
        if schema is not None and schema != "reel-fixture/1":
            eprint(f"[regress] {path.name}: unknown schema {schema!r}, continuing")
        name = desc.get("name") or path.name.removesuffix(".fixture.json")
        if not isinstance(name, str) or not name.strip():
            raise SetupError(f"fixture missing name: {path}")
        man = desc.get("manifest")
        if not isinstance(man, str) or not man.strip():
            raise SetupError(f"fixture missing manifest: {path}")
        man_path = Path(man)
        if not man_path.is_absolute():
            man_path = path.parent / man_path
        out.append(
            Fixture(
                name=name.strip(),
                descriptor_path=path,
                manifest_path=man_path,
                descriptor=desc,
            )
        )
    return out


def write_run_manifest(
    src: Path, dest: Path, output_dir: Path, mode: str
) -> dict:
    data = load_json(src)
    resolve_manifest_paths(data, src.parent)
    data["output_dir"] = str(output_dir)
    deliver = data.get("deliver")
    if isinstance(deliver, dict):
        deliver["copy_to"] = []
    else:
        data["deliver"] = {"copy_to": []}
    render = data.get("render")
    if not isinstance(render, dict):
        render = {}
        data["render"] = render
    render["mode"] = mode
    if mode == "proxy":
        render.setdefault("preset", "ultrafast")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def validate_manifest_keys(data: dict) -> str | None:
    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in data]
    if missing:
        return "manifest missing keys: " + ", ".join(missing)
    return None


def build_render_cmd(
    manifest: Path,
    help_text: str,
    use_proxy: bool,
) -> tuple[list[str], list[str]]:
    """Return (cmd, omitted_flag_notices). --manifest is always passed."""
    cmd = [sys.executable, str(RENDERER), "--manifest", str(manifest)]
    notices: list[str] = []

    def add(flag: str) -> None:
        if not help_text or has_flag(help_text, flag):
            cmd.append(flag)
        else:
            notices.append(f"omitting {flag} (not in render-reel.py --help)")

    add("--proxy" if use_proxy else "--final")
    add("--no-deliver")
    add("--keep-work")
    return cmd, notices


def build_qa_cmd(
    video: Path,
    manifest: Path,
    report: Path,
    sheet: Path,
    help_text: str,
    use_proxy: bool = False,
) -> tuple[list[str], list[str]]:
    cmd = [sys.executable, str(QA_SCRIPT)]
    notices: list[str] = []

    def add(flag: str, *values: str) -> None:
        if not help_text or has_flag(help_text, flag):
            cmd.append(flag)
            cmd.extend(values)
        else:
            notices.append(f"omitting {flag} (not in qa-reel.py --help)")

    add("--video", str(video))
    add("--manifest", str(manifest))
    add("--report", str(report))
    add("--contact-sheet", str(sheet))
    if use_proxy:
        add("--proxy")
    return cmd, notices


def build_validate_cmd(manifest: Path, help_text: str) -> list[str] | None:
    if not help_text:
        return None
    if not has_flag(help_text, "--dry-run"):
        return None
    cmd = [sys.executable, str(RENDERER), "--dry-run"]
    if has_flag(help_text, "--manifest"):
        cmd.extend(["--manifest", str(manifest)])
    return cmd


# ---------------------------------------------------------------------------
# Gold SSIM (ffmpeg)
# ---------------------------------------------------------------------------

def compute_ssim_at(out: Path, gold: Path, t: float) -> float | None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(out),
        "-ss",
        f"{t:.3f}",
        "-i",
        str(gold),
        "-filter_complex",
        "[0:v]scale=540:960[a];[1:v]scale=540:960[b];[a][b]ssim",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return parse_ssim_all((r.stderr or "") + (r.stdout or ""))


def measure_gold(out: Path, gold: Path) -> dict:
    out_dur = probe_duration(out)
    gold_dur = probe_duration(gold)
    samples: list[dict] = []
    min_ssim: float | None = None
    if out_dur and gold_dur:
        shorter = min(out_dur, gold_dur)
        for t in ssim_sample_times(shorter):
            val = compute_ssim_at(out, gold, t)
            samples.append({"t": t, "ssim": val})
            if val is not None:
                min_ssim = val if min_ssim is None else min(min_ssim, val)
    delta = None
    if out_dur is not None and gold_dur is not None:
        delta = out_dur - gold_dur
    return {
        "duration_s": out_dur,
        "gold_duration_s": gold_dur,
        "duration_delta_s": delta,
        "ssim_min": min_ssim,
        "ssim_samples": samples,
        "soft": True,
        "note": SSIM_NOTE,
    }


# ---------------------------------------------------------------------------
# Per-fixture run
# ---------------------------------------------------------------------------

def acquire_lock(run_dir: Path) -> int:
    lock_path = run_dir / ".render.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def run_fixture(
    fx: Fixture,
    *,
    run_dir: Path,
    use_proxy: bool,
    skip_render: bool,
    timeout_s: float,
    render_help: str,
    qa_help: str,
    allow_qa_fail: set[str] | None = None,
) -> dict:
    name = safe_name(fx.name)
    fx_dir = run_dir / name
    fx_dir.mkdir(parents=True, exist_ok=True)
    record: dict = {
        "name": fx.name,
        "result": "FAIL",
        "render_s": None,
        "output": None,
        "size": None,
        "duration_s": None,
        "qa_verdict": None,
        "qa_fail_ids": [],
        "punches": None,
        "punches_expected": fx.expect.get("punch_count"),
        "hook_present": None,
        "cover_text": None,
        "proxy": False,
        "checks": [],
        "gold": None,
        "contact_sheet": None,
        "commands": [],
        "error": None,
        "render_exit": None,
    }
    checks: list[dict] = []
    commands: list[str] = []

    def finish(result: str, error: str | None = None) -> dict:
        record["result"] = result
        record["checks"] = checks
        record["commands"] = commands
        if error:
            record["error"] = error
        record["ok"] = result == "PASS"
        return record

    try:
        manifest_data = write_run_manifest(
            fx.manifest_path,
            fx_dir / "manifest.reel.json",
            fx_dir,
            "proxy" if use_proxy else "final",
        )
    except SetupError as exc:
        checks.append({"id": "manifest", "ok": False, "detail": str(exc)})
        return finish("FAIL", str(exc))
    except OSError as exc:
        msg = f"cannot write run manifest: {exc}"
        checks.append({"id": "manifest", "ok": False, "detail": msg})
        return finish("FAIL", msg)

    run_manifest = fx_dir / "manifest.reel.json"

    validate_cmd = build_validate_cmd(run_manifest, render_help)
    if validate_cmd is not None and not skip_render:
        commands.append(pretty_cmd(validate_cmd))
        code, out, err, timed_out = run_timed(validate_cmd, min(timeout_s, 60))
        if timed_out:
            msg = "render-reel.py --dry-run timed out"
            checks.append({"id": "validate", "ok": False, "detail": msg})
            return finish("FAIL", msg)
        if code == 2:
            msg = (err or out or "render-reel dry-run exit 2").strip().splitlines()
            detail = msg[-1] if msg else "render-reel dry-run exit 2"
            checks.append({"id": "validate", "ok": False, "detail": detail})
            return finish("FAIL", detail)
        if code != 0:
            detail = f"render-reel dry-run exit {code}"
            tail = (err or out or "").strip().splitlines()
            if tail:
                detail = tail[-1]
            checks.append({"id": "validate", "ok": False, "detail": detail})
            return finish("FAIL", detail)
    else:
        key_err = validate_manifest_keys(manifest_data)
        if key_err:
            checks.append({"id": "validate", "ok": False, "detail": key_err})
            return finish("FAIL", key_err)

    output: Path | None = None
    summary: dict | None = None
    render_s: float | None = None

    if skip_render:
        output = newest_mp4(fx_dir)
        if output is None:
            msg = f"no mp4 to reuse in {fx_dir}"
            checks.append({"id": "render", "ok": False, "detail": msg})
            return finish("FAIL", msg)
        record["render_s"] = 0.0
    else:
        cmd, notices = build_render_cmd(run_manifest, render_help, use_proxy)
        for n in notices:
            eprint(f"[regress] {n}")
        commands.append(pretty_cmd(cmd))
        lock_fd = acquire_lock(run_dir)
        t0 = time.perf_counter()
        try:
            code, out, err, timed_out = run_timed(cmd, timeout_s)
        finally:
            render_s = time.perf_counter() - t0
            record["render_s"] = render_s
            release_lock(lock_fd)
        record["render_exit"] = None if timed_out else code
        if timed_out:
            msg = f"timeout after {timeout_s:.0f}s"
            checks.append({"id": "render", "ok": False, "detail": msg})
            return finish("TIMEOUT", msg)
        summary = parse_summary_json(out)
        output = output_from_summary(summary) or newest_mp4(fx_dir)
        if output is None:
            tail = (err or out or "").strip().splitlines()
            detail = tail[-1] if tail else f"renderer produced no mp4 (exit {code})"
            checks.append({"id": "render", "ok": False, "detail": detail})
            return finish("FAIL", detail)

    record["output"] = str(output)
    try:
        record["size"] = output.stat().st_size
    except OSError:
        record["size"] = None

    duration = duration_from_summary(summary)
    if duration is None:
        duration = probe_duration(output)
    record["duration_s"] = duration

    timeline_path, timeline, spine_only = discover_finish_timeline(
        output, fx_dir, summary
    )
    finish_missing = timeline is None
    if finish_missing and spine_only:
        checks.append(
            {
                "id": "timeline",
                "ok": True,
                "detail": "finish timeline missing",
            }
        )
        eprint(f"[regress] {fx.name}: finish timeline missing")

    record["punches"] = timeline_punch_count(timeline)
    record["hook_present"] = timeline_hook_present(timeline)
    record["cover_text"] = rendered_cover_text(manifest_data, timeline)

    qa_path = None
    if isinstance(summary, dict) and isinstance(summary.get("qa"), str):
        qp = Path(summary["qa"])
        if qp.is_file():
            qa_path = qp
    if qa_path is None:
        qa_path = find_sidecar(output, fx_dir, ".qa.json", "qa.json")

    qa: dict | None = None
    if qa_path is not None:
        try:
            loaded = json.loads(qa_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                qa = loaded
        except (OSError, json.JSONDecodeError) as exc:
            eprint(f"[regress] {fx.name}: cannot read qa json: {exc}")

    if qa is None and QA_SCRIPT.is_file() and not skip_render:
        report_path = fx_dir / f"{output.stem}.qa.md"
        sheet_path = fx_dir / f"{output.stem}.sheet.jpg"
        qa_cmd, qa_notices = build_qa_cmd(
            output, run_manifest, report_path, sheet_path, qa_help,
            use_proxy=use_proxy,
        )
        for n in qa_notices:
            eprint(f"[regress] {n}")
        commands.append(pretty_cmd(qa_cmd))
        code, out, err, timed_out = run_timed(qa_cmd, min(timeout_s, 180))
        if timed_out:
            checks.append(
                {
                    "id": "qa",
                    "ok": False,
                    "detail": "qa-reel.py timed out",
                }
            )
        else:
            qa_path = find_sidecar(output, fx_dir, ".qa.json", "qa.json")
            if qa_path is None and report_path.with_suffix(".json").is_file():
                qa_path = report_path.with_suffix(".json")
            if qa_path is not None:
                try:
                    loaded = json.loads(qa_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        qa = loaded
                except (OSError, json.JSONDecodeError):
                    qa = None
            if qa is None:
                parsed = parse_summary_json(out)
                if parsed is not None:
                    qa = parsed
            if qa is None and code != 0:
                tail = (err or out or "").strip().splitlines()
                detail = tail[-1] if tail else f"qa-reel.py exit {code}"
                checks.append({"id": "qa", "ok": False, "detail": detail})
    elif qa is None and "qa_verdict" in fx.expect:
        if QA_SCRIPT.is_file() and skip_render:
            # skip-render still needs a qa json on disk
            checks.append(
                {
                    "id": "qa",
                    "ok": False,
                    "detail": "qa json missing and --skip-render is set",
                }
            )
        elif not QA_SCRIPT.is_file():
            eprint("[regress] qa-reel.py missing; no qa json on disk")

    record["qa_verdict"] = qa_verdict_of(qa)
    if record["qa_verdict"] is None and isinstance(summary, dict):
        sv = summary.get("qa_verdict")
        if isinstance(sv, str):
            record["qa_verdict"] = sv.lower()
    record["qa_fail_ids"] = qa_fail_ids(qa)
    if isinstance(qa, dict):
        record["proxy"] = bool(qa.get("proxy"))
    elif use_proxy:
        record["proxy"] = True

    sheet = find_contact_sheet(fx_dir, output, qa)
    record["contact_sheet"] = str(sheet) if sheet else None

    expect = dict(fx.expect) if isinstance(fx.expect, dict) else {}
    if finish_missing:
        expect.pop("punch_count", None)
        expect.pop("hook_present", None)
    checks.extend(
        evaluate_expectations(
            expect,
            duration_s=record["duration_s"],
            punch_count=record["punches"],
            hook_present=record["hook_present"],
            cover_text=record["cover_text"],
            qa_verdict=record["qa_verdict"],
        )
    )

    gold_path = fx.gold_path
    if gold_path is not None:
        if not gold_path.is_file():
            checks.append(
                {
                    "id": "gold",
                    "ok": False,
                    "detail": f"gold missing: {gold_path}",
                }
            )
            record["gold"] = {"missing": str(gold_path)}
        else:
            gold_info = measure_gold(output, gold_path)
            record["gold"] = gold_info
            checks.extend(
                evaluate_gold(
                    fx.gold_tolerance,
                    duration_s=record["duration_s"],
                    gold_duration_s=gold_info.get("gold_duration_s"),
                    ssim_min_measured=gold_info.get("ssim_min"),
                )
            )

    failed = [c for c in checks if not c.get("ok")]
    if failed:
        allow = allow_qa_fail or set()
        only_qa = [c for c in failed if c.get("id") == "qa_verdict"]
        other = [c for c in failed if c.get("id") != "qa_verdict"]
        fail_ids = list(record.get("qa_fail_ids") or [])
        if (
            not other
            and only_qa
            and allow
            and fail_ids
            and all(i in allow for i in fail_ids)
        ):
            note = "allowed qa fails: " + ", ".join(fail_ids)
            record["note"] = note
            checks.append({"id": "allow_qa_fail", "ok": True, "detail": note})
            return finish("PASS")
        return finish("FAIL")
    return finish("PASS")


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def gold_cell(record: dict) -> str:
    gold = record.get("gold")
    if not isinstance(gold, dict):
        return "n/a"
    if gold.get("missing"):
        return "missing"
    parts = []
    delta = gold.get("duration_delta_s")
    if isinstance(delta, (int, float)):
        parts.append(f"Δt {delta:+.2f}s")
    ssim = gold.get("ssim_min")
    if isinstance(ssim, (int, float)):
        parts.append(f"SSIM {ssim:.3f}")
    return ", ".join(parts) if parts else "n/a"


def write_markdown(path: Path, run: dict) -> None:
    lines: list[str] = []
    lines.append("# Reel regression")
    lines.append("")
    lines.append(f"- Run dir: `{run['run_dir']}`")
    lines.append(f"- Mode: {run['mode']}")
    n = len(run["fixtures"])
    passed = sum(1 for f in run["fixtures"] if f.get("result") == "PASS")
    lines.append(f"- Result: **{run['result']}** ({passed}/{n} passed)")
    lines.append("")
    lines.append(
        "| name | result | render time | duration | qa | punches | gold Δs | sheet |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for f in run["fixtures"]:
        sheet = f.get("contact_sheet") or "n/a"
        if sheet != "n/a":
            sheet = Path(str(sheet)).name
        dur = f.get("duration_s")
        dur_s = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "n/a"
        qa = f.get("qa_verdict") or "n/a"
        if f.get("proxy"):
            qa = f"{qa} (proxy)"
        got = f.get("punches")
        exp = f.get("punches_expected")
        if got is None and exp is None:
            punch_s = "n/a"
        else:
            g = str(got) if got is not None else "n/a"
            e = str(exp) if exp is not None else "n/a"
            punch_s = f"{g}/{e}"
        lines.append(
            "| {name} | {result} | {rt} | {dur} | {qa} | {punches} | {gold} | {sheet} |".format(
                name=f.get("name"),
                result=f.get("result"),
                rt=human_secs(f.get("render_s")),
                dur=dur_s,
                qa=qa,
                punches=punch_s,
                gold=gold_cell(f),
                sheet=sheet,
            )
        )
    lines.append("")
    lines.append(SSIM_NOTE)
    lines.append("")

    failing = [f for f in run["fixtures"] if f.get("result") != "PASS"]
    if failing:
        lines.append("## Failures")
        lines.append("")
        for f in failing:
            lines.append(f"### {f.get('name')}")
            lines.append("")
            if f.get("error"):
                lines.append(f"- error: {f['error']}")
            for c in f.get("checks") or []:
                if c.get("ok"):
                    continue
                lines.append(f"- {c.get('id')}: {c.get('detail')}")
            fail_ids = f.get("qa_fail_ids") or []
            if fail_ids:
                lines.append("- qa fail ids: " + ", ".join(fail_ids))
            lines.append("")

    lines.append("## Commands")
    lines.append("")
    any_cmd = False
    for f in run["fixtures"]:
        cmds = f.get("commands") or []
        if not cmds:
            continue
        any_cmd = True
        lines.append(f"### {f.get('name')}")
        lines.append("")
        for c in cmds:
            lines.append(f"    {c}")
        lines.append("")
    if not any_cmd:
        lines.append("No commands ran.")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json_report(path: Path, run: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")


def print_plan(fixtures: list[Fixture], *, use_proxy: bool, run_dir: Path) -> None:
    print(f"[regress] fixtures: {len(fixtures)} found")
    print(f"[regress] run dir: {run_dir}")
    print(f"[regress] mode: {'proxy' if use_proxy else 'final'}")
    render_help = script_help(RENDERER) if RENDERER.is_file() else ""
    qa_help = script_help(QA_SCRIPT) if QA_SCRIPT.is_file() else ""
    if not RENDERER.is_file():
        print(f"[regress] renderer missing: expected {RENDERER}")
    for fx in fixtures:
        gold = fx.gold_path
        gold_s = str(gold) if gold else "null"
        print(
            f"[regress] {fx.name}  manifest={fx.manifest_path.name}  gold={gold_s}"
        )
        if not fx.manifest_path.is_file():
            print(f"[regress]   manifest missing: {fx.manifest_path}")
            continue
        man_copy = run_dir / safe_name(fx.name) / "manifest.reel.json"
        cmd, notices = build_render_cmd(man_copy, render_help, use_proxy)
        print(f"[regress]   would: {pretty_cmd(cmd)}")
        for n in notices:
            print(f"[regress]   {n}")
        if QA_SCRIPT.is_file():
            video = run_dir / safe_name(fx.name) / "output.mp4"
            report = run_dir / safe_name(fx.name) / "output.qa.md"
            sheet = run_dir / safe_name(fx.name) / "output.sheet.jpg"
            qa_cmd, _qa_n = build_qa_cmd(
                video, man_copy, report, sheet, qa_help, use_proxy=use_proxy
            )
            print(f"[regress]   would: {pretty_cmd(qa_cmd)}")
        else:
            print("[regress]   qa-reel.py not found; will use renderer qa.json if present")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_only(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run reel fixtures through the renderer and QA gate, then "
            "compare against expectations and an optional gold mp4."
        )
    )
    p.add_argument(
        "--fixtures",
        type=Path,
        required=True,
        help="Directory of <name>.fixture.json + <name>.reel.json pairs.",
    )
    p.add_argument(
        "--only",
        default="",
        help="Comma-separated fixture names to run (default: all).",
    )
    p.add_argument(
        "--run-dir",
        type=Path,
        help="Where per-fixture output lands (default: a temp directory).",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--proxy",
        action="store_true",
        help="Fast 540x960 render (default).",
    )
    mode.add_argument(
        "--final",
        action="store_true",
        help="Full-quality 1080x1920 render.",
    )
    p.add_argument("--report", type=Path, help="Write a markdown report here.")
    p.add_argument(
        "--json",
        type=Path,
        dest="json_out",
        metavar="PATH",
        help="Write a JSON report here.",
    )
    p.add_argument(
        "--skip-render",
        action="store_true",
        help="Reuse the newest mp4 already in <run-dir>/<name>/.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan (fixtures found, commands) and exit 0.",
    )
    p.add_argument(
        "--keep",
        action="store_true",
        help="Keep the temp run dir. Always kept when --run-dir is set.",
    )
    p.add_argument(
        "--timeout-min",
        type=float,
        default=DEFAULT_TIMEOUT_MIN,
        help=(
            "Kill a fixture render past this many minutes and mark it "
            f"FAIL (timeout). Default {DEFAULT_TIMEOUT_MIN}."
        ),
    )
    p.add_argument(
        "--allow-qa-fail",
        default="",
        metavar="ID,ID",
        help=(
            "Comma-separated QA check ids. If a fixture fails only on "
            "qa_verdict and every QA FAIL id is in this list, mark it PASS. "
            "Default empty."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fixtures_dir = args.fixtures
    if not fixtures_dir.is_dir():
        die(f"fixtures dir not found: {fixtures_dir}", EXIT_SETUP)

    try:
        fixtures = discover_fixtures(fixtures_dir)
    except SetupError as exc:
        die(str(exc), EXIT_SETUP)

    only = parse_only(args.only) if args.only else []
    if only:
        wanted = set(only)
        fixtures = [f for f in fixtures if f.name in wanted]
        missing = wanted - {f.name for f in fixtures}
        if missing and not args.dry_run:
            die("no fixtures matched: " + ", ".join(sorted(missing)), EXIT_SETUP)

    if not fixtures:
        if args.dry_run:
            print("[regress] no fixtures found")
            return EXIT_OK
        die("no fixtures", EXIT_SETUP)

    use_proxy = not args.final

    if args.dry_run:
        plan_dir = args.run_dir if args.run_dir is not None else Path("<run-dir>")
        print_plan(fixtures, use_proxy=use_proxy, run_dir=plan_dir)
        return EXIT_OK

    for fx in fixtures:
        if not fx.manifest_path.is_file():
            die(f"missing manifest: {fx.manifest_path}", EXIT_SETUP)

    if not RENDERER.is_file():
        die(f"renderer missing: expected {RENDERER}", EXIT_SETUP)

    auto_tmp = False
    if args.run_dir is not None:
        run_dir = args.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
    else:
        run_dir = Path(tempfile.mkdtemp(prefix="reel-regress-"))
        auto_tmp = True

    timeout_s = max(float(args.timeout_min), 0.1) * 60.0
    render_help = script_help(RENDERER)
    qa_help = script_help(QA_SCRIPT) if QA_SCRIPT.is_file() else ""
    allow_qa_fail = {p.strip() for p in (args.allow_qa_fail or "").split(",") if p.strip()}

    print(f"[regress] run dir: {run_dir}")
    print(f"[regress] mode: {'proxy' if use_proxy else 'final'}")
    print(f"[regress] fixtures: {', '.join(f.name for f in fixtures)}")

    records: list[dict] = []
    try:
        for fx in fixtures:
            print(f"[regress] {fx.name}: start")
            rec = run_fixture(
                fx,
                run_dir=run_dir,
                use_proxy=use_proxy,
                skip_render=args.skip_render,
                timeout_s=timeout_s,
                render_help=render_help,
                qa_help=qa_help,
                allow_qa_fail=allow_qa_fail,
            )
            records.append(rec)
            dur = rec.get("duration_s")
            dur_s = f"{dur:.2f}s" if isinstance(dur, (int, float)) else "n/a"
            print(
                f"[regress] {fx.name}: {rec['result']}  "
                f"render={human_secs(rec.get('render_s'))}  "
                f"dur={dur_s}  qa={rec.get('qa_verdict') or 'n/a'}"
            )

        passed = sum(1 for r in records if r.get("result") == "PASS")
        overall = "PASS" if passed == len(records) else "FAIL"
        run = {
            "ok": overall == "PASS",
            "result": overall,
            "mode": "proxy" if use_proxy else "final",
            "run_dir": str(run_dir),
            "fixtures": records,
            "passed": passed,
            "total": len(records),
            "ssim_note": SSIM_NOTE,
        }

        if args.report:
            write_markdown(args.report, run)
            print(f"[regress] report: {args.report}")
        if args.json_out:
            write_json_report(args.json_out, run)
            print(f"[regress] json: {args.json_out}")

        print(f"[regress] result: {passed}/{len(records)} passed")
        return EXIT_OK if overall == "PASS" else EXIT_FAIL
    finally:
        if auto_tmp and args.keep:
            eprint(f"[regress] keeping {run_dir}")
        elif auto_tmp and not args.keep:
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
