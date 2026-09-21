#!/usr/bin/env python3
"""Run the same reel task through several harnesses and compare.

Every harness does the same judgment work (read the brief, fill the
manifest, choose punches). The render and the QA gate are identical
code. The comparison is the manifest, dry runs to a clean preflight,
QA verdict, punch fit, cost, and wall time.

Adapters
--------
pi       $PI_RUN or `pi-run` on PATH. Missing binary fails the harness.
claude   `claude -p`. Missing binary fails the harness. If --effort is
         rejected, retry once without it.
codex    `codex exec --model M`. Missing binary: skipped.
grok     `grok --prompt`. Missing binary: skipped.
cursor   `cursor-agent -p`. Missing binary: skipped.

Scoring columns
---------------
id, model, produced_render, qa_verdict, qa_fail_ids, qa_warn_ids,
duration_s, in_window, hook_mode, cover_text, punches, joins_covered,
preflight_warns, renders, dry_runs, stray_writes, wall_s, cost_usd,
tokens_in, tokens_out, exact, category, wrong, unpunched_ok, missed,
stills, video_punches, verifier_cost_usd, verifier_wall_s.

Ranking: zero wrong and zero category first; then fewest missed; then
gate fails 0, preflight warns 0, stray writes 0; then cost, then wall.
video.static_gap is listed but never scored. Verifier cost and wall are
separate columns and are never folded into the harness cost.

Exit codes
----------
0  every harness produced a scorable render (skipped binaries do not fail)
2  config problem
3  at least one harness failed to produce a render or exceeded its timeout

Usage
-----
    bench-reel.py --config bench.json [--only id,id] [--concurrency 2]
                  [--dry-run] [--report-only]
                  [--verifier-cmd CMD] [--grades FILE]
                  [--report DIR/bench-report.md]
                  [--html DIR/bench-report.html]

Config keys (see resources/bench.example.json): schema, cwd, task.note,
task.style, task.output_root, task.skill_dir, task.mode,
task.extra_instructions, task.broll_index, task.deliver_to, concurrency,
timeout_min, harnesses, verifier (kind, provider, model, thinking,
alternate).
"""

from __future__ import annotations

import argparse
import base64
import html
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parent
RESOURCES = SCRIPTS_DIR.parent / "resources"
TEMPLATE_PATH = RESOURCES / "bench-task.template.md"
RENDERER = SCRIPTS_DIR / "render-reel.py"
QA_SCRIPT = SCRIPTS_DIR / "qa-reel.py"
REGRESS_PATH = SCRIPTS_DIR / "regress.py"

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_FAIL = 3

ALLOWED_KINDS = ("pi", "claude", "codex", "grok", "cursor")
PI_TOOLS = "read,grep,find,ls,bash,edit,write"
DEFAULT_CONCURRENCY = 2
DEFAULT_TIMEOUT_MIN = 45
SCHEMA = "reel-bench/1"
PLACEHOLDERS = (
    "note",
    "style",
    "output_dir",
    "skill_dir",
    "mode",
    "harness_id",
    "extra",
    "index",
)
SKIP_KINDS = frozenset({"codex", "grok", "cursor"})
WORK_DIR_NAMES = {"work", "_work", "tmp", "temp"}
FAMILY_PREFIXES = ("gpt", "claude", "grok", "gemini", "muse")
GRADE_VALUES = ("exact", "category", "wrong")
STATIC_GAP_ID = "video.static_gap"
VERIFIER_TOOLS = "read"
RANKING_RULE = (
    "Ranking: zero wrong and zero category first; then fewest missed; "
    "then gate fails 0, preflight warns 0, stray writes 0; then cost, "
    "then wall. video.static_gap is listed but never scored."
)

_REGRESS = None


class ConfigError(Exception):
    """Bad config. Maps to exit 2."""


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def die(msg: str, code: int = EXIT_CONFIG) -> None:
    eprint(f"[bench] {msg}")
    raise SystemExit(code)


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pretty_cmd(cmd: list[str]) -> str:
    parts = []
    for c in cmd:
        s = str(c)
        if any(ch in s for ch in ' \t\n:"\''):
            parts.append("'" + s.replace("'", "'\\''") + "'")
        else:
            parts.append(s)
    return " ".join(parts)


def load_regress():
    """Import regress.py via importlib. Do not copy its helpers."""
    global _REGRESS
    if _REGRESS is not None:
        return _REGRESS
    path = REGRESS_PATH
    if not path.is_file():
        raise ConfigError(f"regress.py missing: {path}")
    spec = importlib.util.spec_from_file_location("cut_video_regress", path)
    if spec is None or spec.loader is None:
        raise ConfigError(f"cannot import regress.py: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _REGRESS = mod
    return mod


def load_json_file(path: Path) -> Any:
    try:
        val = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"bad JSON: {path}: {exc}") from exc
    return val


def as_path(val: Any) -> Path:
    return Path(str(val)).expanduser()


def render_template(text: str, values: dict[str, str]) -> str:
    """Replace {name} placeholders. Extra braces in values are kept."""
    out = text
    for key in PLACEHOLDERS:
        out = out.replace("{" + key + "}", values.get(key, ""))
    return out


def load_template() -> str:
    if not TEMPLATE_PATH.is_file():
        raise ConfigError(f"task template missing: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def index_instruction(index_path: str | None) -> str:
    """One search line for the task, or empty when no index is configured."""
    path = str(index_path or "").strip()
    if not path:
        return ""
    return (
        f"Search the B-roll index at `{path}` with "
        f"`broll-search.py --index {path} --lines-from-manifest` "
        f"and look at the sheet before choosing."
    )


def render_task_text(
    *,
    note: str,
    style: str,
    output_dir: str,
    skill_dir: str,
    mode: str,
    harness_id: str,
    extra: str = "",
    index: str = "",
    template: str | None = None,
) -> str:
    body = template if template is not None else load_template()
    return render_template(
        body,
        {
            "note": note,
            "style": style,
            "output_dir": output_dir,
            "skill_dir": skill_dir,
            "mode": mode,
            "harness_id": harness_id,
            "extra": extra or "",
            "index": index_instruction(index),
        },
    )


def find_pi_run() -> Path | None:
    env = os.environ.get("PI_RUN")
    if env:
        p = Path(env).expanduser()
        return p if p.is_file() else None
    return which_bin("pi-run")


def which_bin(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found) if found else None


def family_keys(provider: str | None, model: str | None) -> set[str]:
    """Family tokens from a provider/model pair (gpt, claude, grok, gemini, muse)."""
    blob = f"{provider or ''} {model or ''}".lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", blob) if t]
    keys: set[str] = set()
    for tok in tokens:
        for fam in FAMILY_PREFIXES:
            if tok.startswith(fam):
                keys.add(fam)
    return keys


def same_verifier_family(harness: dict, verifier: dict) -> bool:
    """True when provider matches or a model-family prefix matches."""
    hp = str(harness.get("provider") or "").strip().lower()
    vp = str(verifier.get("provider") or "").strip().lower()
    if hp and vp and hp == vp:
        return True
    return bool(
        family_keys(harness.get("provider"), harness.get("model"))
        & family_keys(verifier.get("provider"), verifier.get("model"))
    )


def choose_verifier(harness: dict, verifier_cfg: dict | None) -> dict | None:
    """Pick primary or alternate so the verifier is a different model family."""
    if not isinstance(verifier_cfg, dict) or not verifier_cfg:
        return None
    primary = {
        "kind": verifier_cfg.get("kind") or "pi",
        "provider": verifier_cfg.get("provider"),
        "model": verifier_cfg.get("model"),
        "thinking": verifier_cfg.get("thinking"),
    }
    alt = verifier_cfg.get("alternate")
    alt_d = alt if isinstance(alt, dict) else None
    if same_verifier_family(harness, primary) and alt_d:
        chosen = {
            "kind": alt_d.get("kind") or "pi",
            "provider": alt_d.get("provider"),
            "model": alt_d.get("model"),
            "thinking": alt_d.get("thinking") or primary.get("thinking"),
        }
        return chosen
    return primary


def build_pi_cmd(
    *,
    pi_run: Path | str,
    cwd: Path | str,
    provider: str,
    model: str,
    thinking: str | None,
    harness_id: str,
    timeout_s: int,
    task_file: Path | str,
) -> list[str]:
    cmd = [
        str(pi_run),
        "--cwd",
        str(cwd),
        "--role",
        "generic",
        "--provider",
        str(provider),
        "--model",
        str(model),
    ]
    if thinking:
        cmd.extend(["--thinking", str(thinking)])
    cmd.extend(
        [
            "--tools",
            PI_TOOLS,
            "--isolation",
            "none",
            "--label",
            f"bench-{harness_id}",
            "--timeout",
            str(int(timeout_s)),
            "--json",
            "--spec-file",
            str(task_file),
        ]
    )
    return cmd


def build_claude_cmd(
    *,
    model: str,
    effort: str | None,
    skill_dir: Path | str | None,
    task_text: str,
    include_effort: bool = True,
) -> list[str]:
    # --add-dir is variadic (<directories...>); placed last it swallowed the
    # prompt and claude -p exited with "Input must be provided". Put it first
    # so the next option (-p) closes its list, and keep the prompt positional.
    cmd = ["claude"]
    if skill_dir:
        cmd.extend(["--add-dir", str(skill_dir)])
    cmd.extend(["-p", "--model", str(model)])
    if include_effort and effort:
        cmd.extend(["--effort", str(effort)])
    cmd.extend(
        [
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "json",
        ]
    )
    cmd.append(task_text)
    return cmd


def build_codex_cmd(*, model: str | None, task_text: str) -> list[str]:
    cmd = ["codex", "exec"]
    if model:
        cmd.extend(["--model", str(model)])
    cmd.append(task_text)
    return cmd


def build_grok_cmd(*, model: str | None, task_text: str) -> list[str]:
    cmd = ["grok", "--prompt", task_text]
    if model:
        cmd.extend(["--model", str(model)])
    return cmd


def build_cursor_cmd(*, model: str | None, task_text: str) -> list[str]:
    cmd = ["cursor-agent", "-p", task_text]
    if model:
        cmd.extend(["--model", str(model)])
    return cmd


def validate_config(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ConfigError("config must be a JSON object")
    schema = raw.get("schema")
    if schema != SCHEMA:
        raise ConfigError(f"schema must be {SCHEMA!r}, got {schema!r}")
    for key in ("cwd", "task", "harnesses"):
        if key not in raw:
            raise ConfigError(f"missing key: {key}")
    cwd = as_path(raw["cwd"])
    if not cwd.is_dir():
        raise ConfigError(f"cwd does not exist: {cwd}")
    task = raw["task"]
    if not isinstance(task, dict):
        raise ConfigError("task must be an object")
    for key in ("note", "style", "output_root", "skill_dir"):
        if key not in task:
            raise ConfigError(f"missing task.{key}")
    note = as_path(task["note"])
    if not note.is_file():
        raise ConfigError(f"note does not exist: {note}")
    style = as_path(task["style"])
    output_root = as_path(task["output_root"])
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(f"output_root not creatable: {output_root}: {exc}") from exc
    skill_dir = as_path(task["skill_dir"])
    if not (skill_dir / "SKILL.md").is_file():
        raise ConfigError(f"skill_dir has no SKILL.md: {skill_dir}")
    mode = str(task.get("mode") or "proxy")
    extra = task.get("extra_instructions")
    extra_text = extra if isinstance(extra, str) else ""
    broll_index_raw = task.get("broll_index")
    broll_index = as_path(broll_index_raw) if broll_index_raw else None
    deliver_to_raw = task.get("deliver_to")
    deliver_to = None
    if deliver_to_raw:
        deliver_to = as_path(deliver_to_raw)
        try:
            deliver_to.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(f"deliver_to not creatable: {deliver_to}: {exc}") from exc
    verifier = raw.get("verifier")
    if verifier is not None:
        if not isinstance(verifier, dict):
            raise ConfigError("verifier must be an object")
        if not verifier.get("kind") or not verifier.get("model"):
            raise ConfigError("verifier needs kind and model")
    harnesses = raw["harnesses"]
    if not isinstance(harnesses, list) or not harnesses:
        raise ConfigError("harnesses must be a non-empty list")
    ids: list[str] = []
    cleaned: list[dict] = []
    for i, item in enumerate(harnesses):
        if not isinstance(item, dict):
            raise ConfigError(f"harnesses[{i}] must be an object")
        hid = item.get("id")
        kind = item.get("kind")
        if not hid or not isinstance(hid, str):
            raise ConfigError(f"harnesses[{i}] missing id")
        if kind not in ALLOWED_KINDS:
            raise ConfigError(
                f"harnesses[{i}] kind must be one of {', '.join(ALLOWED_KINDS)}"
            )
        ids.append(hid)
        cleaned.append(dict(item))
    if len(ids) != len(set(ids)):
        raise ConfigError("duplicate harness ids")
    concurrency = raw.get("concurrency", DEFAULT_CONCURRENCY)
    try:
        concurrency_n = int(concurrency)
    except (TypeError, ValueError) as exc:
        raise ConfigError("concurrency must be an integer") from exc
    if concurrency_n < 1:
        raise ConfigError("concurrency must be >= 1")
    timeout_min = raw.get("timeout_min", DEFAULT_TIMEOUT_MIN)
    try:
        timeout_n = int(timeout_min)
    except (TypeError, ValueError) as exc:
        raise ConfigError("timeout_min must be an integer") from exc
    if timeout_n < 1:
        raise ConfigError("timeout_min must be >= 1")
    return {
        "schema": SCHEMA,
        "cwd": cwd,
        "task": {
            "note": note,
            "style": style,
            "output_root": output_root,
            "skill_dir": skill_dir,
            "mode": mode,
            "extra_instructions": extra_text,
            "broll_index": broll_index,
            "deliver_to": deliver_to,
        },
        "concurrency": concurrency_n,
        "timeout_min": timeout_n,
        "harnesses": cleaned,
        "verifier": verifier,
    }


def git_porcelain(cwd: Path) -> set[str]:
    """Relative paths from `git status --porcelain`. Empty if git fails."""
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if r.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in (r.stdout or "").splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) >= 4 else line.strip()
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if rest:
            paths.add(rest)
    return paths


def git_toplevel(cwd: Path) -> Path | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    return Path(r.stdout.strip())


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def stray_writes(
    before: set[str],
    after: set[str],
    *,
    cwd: Path,
    output_root: Path,
) -> list[str]:
    """Paths that appeared or changed and are not under output_root."""
    new = after - before
    if not new:
        return []
    top = git_toplevel(cwd) or cwd
    stray: list[str] = []
    for rel in sorted(new):
        resolved = (top / rel).resolve()
        if is_under(resolved, output_root):
            continue
        stray.append(rel)
    return stray


def run_process(
    cmd: list[str],
    *,
    cwd: Path | None,
    timeout_s: float,
    log_path: Path,
) -> dict:
    """Run cmd in a new session. Kill the process group on timeout."""
    started = iso_now()
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        text = str(exc)
        log_path.write_text(text + "\n", encoding="utf-8")
        return {
            "started": started,
            "ended": iso_now(),
            "wall_s": round(time.monotonic() - t0, 3),
            "exit": 127,
            "timeout": False,
            "output": text,
            "error": text,
        }
    timed_out = False
    out = ""
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        code = proc.returncode if proc.returncode is not None else 0
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            out, _ = proc.communicate()
        code = proc.returncode if proc.returncode is not None else 1
    ended = iso_now()
    text = out or ""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(text, encoding="utf-8")
    return {
        "started": started,
        "ended": ended,
        "wall_s": round(time.monotonic() - t0, 3),
        "exit": code,
        "timeout": timed_out,
        "output": text,
        "error": None,
    }


def _num(val: Any) -> float | None:
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.strip())
        except ValueError:
            return None
    return None


def _int(val: Any) -> int | None:
    n = _num(val)
    if n is None:
        return None
    return int(n)


def parse_pi_summary(text: str) -> dict:
    """Defensive parse of pi-run --json (or last JSON object line)."""
    reg = load_regress()
    data = reg.parse_summary_json(text) if text else None
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    cost = (
        _num(usage.get("cost_usd"))
        or _num(data.get("cost_usd"))
        or _num(data.get("cost"))
    )
    wall = (
        _num(result.get("duration_s"))
        or _num(data.get("duration_s"))
        or _num(data.get("wall"))
        or _num(data.get("duration"))
    )
    if wall is None:
        ms = _num(result.get("duration_ms")) or _num(data.get("duration_ms"))
        if ms is not None:
            wall = ms / 1000.0
    tokens_in = (
        _int(usage.get("tokens_in"))
        or _int(data.get("tokens_in"))
        or _int(data.get("input_tokens"))
    )
    tokens_out = (
        _int(usage.get("tokens_out"))
        or _int(data.get("tokens_out"))
        or _int(data.get("output_tokens"))
    )
    return {
        "raw": data,
        "status": data.get("status"),
        "provider": data.get("provider"),
        "model": data.get("model"),
        "cost_usd": cost,
        "wall_s": wall,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def parse_claude_summary(text: str) -> dict:
    """Defensive parse of `claude -p --output-format json`."""
    reg = load_regress()
    data = reg.parse_summary_json(text) if text else None
    if not isinstance(data, dict):
        return {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    cost = (
        _num(data.get("total_cost_usd"))
        or _num(data.get("cost_usd"))
        or _num(usage.get("cost_usd"))
    )
    wall = _num(data.get("duration_s")) or _num(data.get("wall"))
    if wall is None:
        ms = _num(data.get("duration_ms"))
        if ms is not None:
            wall = ms / 1000.0
    tokens_in = (
        _int(usage.get("input_tokens"))
        or _int(data.get("tokens_in"))
        or _int(usage.get("tokens_in"))
    )
    tokens_out = (
        _int(usage.get("output_tokens"))
        or _int(data.get("tokens_out"))
        or _int(usage.get("tokens_out"))
    )
    return {
        "raw": data,
        "status": data.get("status") or data.get("subtype"),
        "model": data.get("model"),
        "cost_usd": cost,
        "wall_s": wall,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "num_turns": data.get("num_turns"),
        "result": data.get("result"),
    }


def write_harness_json(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def skip_record(
    harness: dict,
    *,
    started: str,
    reason: str,
) -> dict:
    return {
        "id": harness.get("id"),
        "kind": harness.get("kind"),
        "provider": harness.get("provider"),
        "model": harness.get("model"),
        "thinking": harness.get("thinking"),
        "effort": harness.get("effort"),
        "started": started,
        "ended": iso_now(),
        "wall_s": 0.0,
        "exit": None,
        "cost_usd": None,
        "tokens_in": None,
        "tokens_out": None,
        "notes": [reason],
        "skipped": True,
        "timeout": False,
    }


def effort_rejected(output: str) -> bool:
    text = (output or "").lower()
    if "effort" not in text:
        return False
    needles = (
        "unknown option",
        "unexpected",
        "unrecognized",
        "invalid",
        "not a valid",
        "no such option",
        "unknown argument",
    )
    return any(n in text for n in needles)


def run_adapter(
    harness: dict,
    *,
    cwd: Path,
    skill_dir: Path,
    task_text: str,
    task_file: Path,
    output_dir: Path,
    timeout_s: int,
    dry_run: bool,
) -> dict:
    kind = harness["kind"]
    hid = harness["id"]
    log_path = output_dir / "harness.log"
    json_path = output_dir / "harness.json"
    notes: list[str] = []
    started = iso_now()

    if kind == "pi":
        if not harness.get("provider") or not harness.get("model"):
            raise ConfigError(f"{hid}: pi harness needs provider and model")
        pi_run = find_pi_run()
        cmd = build_pi_cmd(
            pi_run=pi_run or Path("pi-run"),
            cwd=cwd,
            provider=str(harness["provider"]),
            model=str(harness["model"]),
            thinking=harness.get("thinking"),
            harness_id=hid,
            timeout_s=timeout_s,
            task_file=task_file,
        )
        if dry_run:
            print(pretty_cmd(cmd), flush=True)
            rec = skip_record(harness, started=started, reason="dry-run")
            rec["skipped"] = False
            rec["notes"] = ["dry-run"]
            rec["command"] = cmd
            write_harness_json(json_path, rec)
            return rec
        if pi_run is None:
            rec = skip_record(harness, started=started, reason="pi-run missing")
            rec["skipped"] = False
            rec["notes"] = [
                "pi-run missing: set PI_RUN or install pi-run on PATH"
            ]
            rec["exit"] = 127
            write_harness_json(json_path, rec)
            log_path.write_text(rec["notes"][0] + "\n", encoding="utf-8")
            eprint(f"[bench] {hid}: pi-run missing")
            return rec
        run = run_process(cmd, cwd=cwd, timeout_s=timeout_s, log_path=log_path)
        parsed = parse_pi_summary(run["output"])
        rec = {
            "id": hid,
            "kind": kind,
            "provider": harness.get("provider") or parsed.get("provider"),
            "model": harness.get("model") or parsed.get("model"),
            "thinking": harness.get("thinking"),
            "effort": None,
            "started": run["started"],
            "ended": run["ended"],
            "wall_s": parsed.get("wall_s") if parsed.get("wall_s") is not None else run["wall_s"],
            "exit": run["exit"],
            "cost_usd": parsed.get("cost_usd"),
            "tokens_in": parsed.get("tokens_in"),
            "tokens_out": parsed.get("tokens_out"),
            "notes": notes,
            "skipped": False,
            "timeout": run["timeout"],
            "raw": parsed.get("raw"),
        }
        write_harness_json(json_path, rec)
        return rec

    if kind == "claude":
        if not harness.get("model"):
            raise ConfigError(f"{hid}: claude harness needs model")
        cmd = build_claude_cmd(
            model=str(harness["model"]),
            effort=harness.get("effort"),
            skill_dir=skill_dir,
            task_text=task_text,
            include_effort=True,
        )
        if dry_run:
            print(pretty_cmd(cmd), flush=True)
            rec = skip_record(harness, started=started, reason="dry-run")
            rec["skipped"] = False
            rec["notes"] = ["dry-run"]
            rec["command"] = cmd
            write_harness_json(json_path, rec)
            return rec
        binary = which_bin("claude")
        if binary is None:
            rec = skip_record(harness, started=started, reason="claude missing")
            rec["skipped"] = False
            rec["notes"] = ["claude binary not found"]
            rec["exit"] = 127
            write_harness_json(json_path, rec)
            log_path.write_text(rec["notes"][0] + "\n", encoding="utf-8")
            eprint(f"[bench] {hid}: claude binary not found")
            return rec
        run = run_process(cmd, cwd=cwd, timeout_s=timeout_s, log_path=log_path)
        if (
            run["exit"]
            and not run["timeout"]
            and harness.get("effort")
            and effort_rejected(run["output"])
        ):
            notes.append("--effort rejected; retrying without it")
            eprint(f"[bench] {hid}: --effort rejected, retrying without it")
            cmd2 = build_claude_cmd(
                model=str(harness["model"]),
                effort=harness.get("effort"),
                skill_dir=skill_dir,
                task_text=task_text,
                include_effort=False,
            )
            first_log = run["output"]
            run = run_process(cmd2, cwd=cwd, timeout_s=timeout_s, log_path=log_path)
            log_path.write_text(
                first_log
                + "\n--- retry without --effort ---\n"
                + (run["output"] or ""),
                encoding="utf-8",
            )
        parsed = parse_claude_summary(run["output"])
        rec = {
            "id": hid,
            "kind": kind,
            "provider": harness.get("provider") or "anthropic",
            "model": harness.get("model") or parsed.get("model"),
            "thinking": harness.get("thinking"),
            "effort": harness.get("effort"),
            "started": run["started"],
            "ended": run["ended"],
            "wall_s": parsed.get("wall_s") if parsed.get("wall_s") is not None else run["wall_s"],
            "exit": run["exit"],
            "cost_usd": parsed.get("cost_usd"),
            "tokens_in": parsed.get("tokens_in"),
            "tokens_out": parsed.get("tokens_out"),
            "notes": notes,
            "skipped": False,
            "timeout": run["timeout"],
            "raw": parsed.get("raw"),
        }
        write_harness_json(json_path, rec)
        return rec

    bin_name = {"codex": "codex", "grok": "grok", "cursor": "cursor-agent"}[kind]
    binary = which_bin(bin_name)
    if binary is None:
        reason = f"skipped: binary not found ({bin_name})"
        rec = skip_record(harness, started=started, reason=reason)
        write_harness_json(json_path, rec)
        log_path.write_text(reason + "\n", encoding="utf-8")
        eprint(f"[bench] {hid}: {reason}")
        if dry_run:
            print(f"# {hid} {reason}", flush=True)
        return rec

    model = harness.get("model")
    if kind == "codex":
        cmd = build_codex_cmd(model=model, task_text=task_text)
    elif kind == "grok":
        cmd = build_grok_cmd(model=model, task_text=task_text)
    else:
        cmd = build_cursor_cmd(model=model, task_text=task_text)
    if dry_run:
        print(pretty_cmd(cmd), flush=True)
        rec = skip_record(harness, started=started, reason="dry-run")
        rec["skipped"] = False
        rec["notes"] = ["dry-run"]
        rec["command"] = cmd
        write_harness_json(json_path, rec)
        return rec
    run = run_process(cmd, cwd=cwd, timeout_s=timeout_s, log_path=log_path)
    rec = {
        "id": hid,
        "kind": kind,
        "provider": harness.get("provider"),
        "model": model,
        "thinking": harness.get("thinking"),
        "effort": harness.get("effort"),
        "started": run["started"],
        "ended": run["ended"],
        "wall_s": run["wall_s"],
        "exit": run["exit"],
        "cost_usd": None,
        "tokens_in": None,
        "tokens_out": None,
        "notes": notes,
        "skipped": False,
        "timeout": run["timeout"],
    }
    write_harness_json(json_path, rec)
    return rec


def is_work_path(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts[:-1]
    except ValueError:
        return False
    return any(part.lower() in WORK_DIR_NAMES for part in parts)


def list_mp4s(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files = [p for p in root.rglob("*.mp4") if p.is_file()]
    preferred = [p for p in files if not is_work_path(p, root)]
    return preferred or files


def newest_video(root: Path) -> Path | None:
    files = list_mp4s(root)
    if not files:
        return None
    proxies = [p for p in files if "-proxy" in p.stem or p.name.endswith("-proxy.mp4")]
    pool = proxies or files
    return max(pool, key=lambda p: p.stat().st_mtime)


def find_manifest(output_dir: Path, video: Path | None) -> Path | None:
    if video is not None:
        sibling = video.with_name(video.stem + ".reel.json")
        if sibling.is_file():
            return sibling
        alt = Path(str(video) + ".reel.json")
        if alt.is_file():
            return alt
    if not output_dir.is_dir():
        return None
    matches = [p for p in output_dir.rglob("*.reel.json") if p.is_file()]
    if not matches:
        return None
    if video is not None:
        same = [p for p in matches if p.parent == video.parent]
        if same:
            return max(same, key=lambda p: p.stat().st_mtime)
    return max(matches, key=lambda p: p.stat().st_mtime)


def find_qa_json(output_dir: Path, video: Path | None) -> Path | None:
    reg = load_regress()
    found = reg.find_sidecar(video, output_dir, ".qa.json", "qa.json")
    if found is not None:
        return found
    if output_dir.is_dir():
        matches = [p for p in output_dir.rglob("*.qa.json") if p.is_file()]
        if matches:
            return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def find_runnotes(output_dir: Path) -> Path | None:
    if not output_dir.is_dir():
        return None
    hits = []
    for p in output_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".md", ".txt"}:
            continue
        if "runnotes" in p.name.lower():
            hits.append(p)
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)


def parse_known_deviations(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    out: list[str] = []
    in_sec = False
    for line in lines:
        if line.startswith("## "):
            if in_sec:
                break
            if line.strip().lower() == "## known deviations":
                in_sec = True
            continue
        if in_sec:
            out.append(line)
    return "\n".join(out).strip()


def qa_ids_with_status(qa: dict | None, status: str) -> list[str]:
    if not isinstance(qa, dict):
        return []
    want = status.lower()
    if want == "fail":
        return load_regress().qa_fail_ids(qa)
    key_map = {"warn": ("warns", "warn_ids", "warnings")}
    for key in key_map.get(want, ()):
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
            st = str(c.get("status") or c.get("verdict") or "").lower()
            if st == want or (want == "warn" and st == "warning"):
                ids.append(str(c.get("id") or c.get("name") or "check"))
        return ids
    return []


def qa_detail_map(qa: dict | None) -> dict[str, str]:
    if not isinstance(qa, dict):
        return {}
    out: dict[str, str] = {}
    checks = qa.get("checks")
    if isinstance(checks, list):
        for c in checks:
            if not isinstance(c, dict):
                continue
            ident = c.get("id") or c.get("name")
            if ident is None:
                continue
            detail = c.get("detail") or c.get("message") or ""
            out[str(ident)] = str(detail)
    return out


def join_uncovered_status(qa: dict | None) -> str | None:
    if not isinstance(qa, dict):
        return None
    checks = qa.get("checks")
    if not isinstance(checks, list):
        return None
    for c in checks:
        if isinstance(c, dict) and c.get("id") == "video.join_uncovered":
            st = c.get("status") or c.get("verdict")
            return str(st).lower() if st is not None else None
    return None


def punch_rows(timeline: dict | None, manifest: dict | None) -> list[dict]:
    src = None
    if isinstance(timeline, dict) and isinstance(timeline.get("punches"), list):
        src = timeline["punches"]
    elif isinstance(manifest, dict) and isinstance(manifest.get("broll"), list):
        src = manifest["broll"]
    if not src:
        return []
    # The finish timeline carries no spoken line; the manifest does. Join by
    # index when the counts match, otherwise leave the line empty.
    manifest_lines: list[str] = []
    manifest_shows: list[str] = []
    manifest_kinds: list[str] = []
    if isinstance(manifest, dict) and isinstance(manifest.get("broll"), list):
        for b in manifest["broll"]:
            if not isinstance(b, dict):
                continue
            manifest_lines.append(str(b.get("line") or ""))
            manifest_shows.append(str(b.get("shows") or ""))
            # The finish timeline labels a converted still as a clip; the
            # manifest knows (kind: still, or an image extension on the path).
            mk = str(b.get("kind") or "auto").lower()
            ext = str(b.get("path") or "").lower().rsplit(".", 1)[-1]
            if mk == "still" or (mk == "auto" and ext in ("jpg", "jpeg", "png", "webp", "heic", "tif", "tiff")):
                manifest_kinds.append("still")
            else:
                manifest_kinds.append(mk if mk in ("clip", "still") else "")
    rows: list[dict] = []
    for i, item in enumerate(src):
        if not isinstance(item, dict):
            continue
        path = item.get("path") or ""
        basename = Path(str(path)).name if path else ""
        at = item.get("at_final", item.get("at"))
        line = item.get("line") or ""
        if not line and len(manifest_lines) == len(src) and i < len(manifest_lines):
            line = manifest_lines[i]
        shows = str(item.get("shows") or "")
        if not shows and len(manifest_shows) == len(src) and i < len(manifest_shows):
            shows = manifest_shows[i]
        kind = item.get("kind")
        if len(manifest_kinds) == len(src) and i < len(manifest_kinds):
            if manifest_kinds[i] == "still" or not kind:
                kind = manifest_kinds[i] or kind
        rows.append(
            {
                "index": i,
                "at_final": at,
                "dur": item.get("dur"),
                "kind": kind,
                "line": line,
                "shows": shows,
                "path": basename,
            }
        )
    return rows


def hook_mode_of(timeline: dict | None, manifest: dict | None) -> str | None:
    for obj in (timeline, manifest):
        if not isinstance(obj, dict):
            continue
        hook = obj.get("hook")
        if isinstance(hook, dict) and isinstance(hook.get("mode"), str):
            return hook["mode"]
        if isinstance(obj.get("hook_mode"), str):
            return obj["hook_mode"]
    return None


def in_window_of(manifest: dict | None, duration_s: float | None) -> bool | None:
    if duration_s is None or not isinstance(manifest, dict):
        return None
    window = manifest.get("duration_window")
    if not (isinstance(window, (list, tuple)) and len(window) >= 2):
        return None
    try:
        lo = float(window[0])
        hi = float(window[1])
    except (TypeError, ValueError):
        return None
    return lo <= float(duration_s) <= hi


def count_preflight_warns(text: str) -> int:
    if not text:
        return 0
    n = 0
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[render-reel] Preflight") or stripped == "Preflight":
            in_table = True
            continue
        if stripped.startswith("WARN"):
            n += 1
            continue
        if in_table and stripped.startswith("|") and "| WARN" in stripped:
            n += 1
            continue
        if in_table and stripped and not stripped.startswith("|") and not stripped.startswith("WARN"):
            in_table = False
    return n


def script_help(script: Path) -> str:
    try:
        return load_regress().script_help(script)
    except Exception:
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


def maybe_run_qa(
    video: Path,
    manifest: Path | None,
    output_dir: Path,
) -> Path | None:
    if not QA_SCRIPT.is_file():
        eprint("[bench] qa-reel.py missing; skipping QA")
        return None
    help_text = script_help(QA_SCRIPT)
    reg = load_regress()
    report = video.with_name(video.stem + ".qa.json")
    sheet = video.with_name(video.stem + ".sheet.jpg")
    cmd, notices = reg.build_qa_cmd(
        video,
        manifest if manifest is not None else video,
        report,
        sheet,
        help_text,
        use_proxy=("-proxy" in video.stem),
    )
    if manifest is None:
        # build_qa_cmd always adds --manifest when the flag exists. Drop it
        # if we have no manifest so qa-reel does not read a dummy path.
        if "--manifest" in cmd:
            i = cmd.index("--manifest")
            drop = 2 if i + 1 < len(cmd) else 1
            cmd = cmd[:i] + cmd[i + drop :]
    for note in notices:
        eprint(f"[bench] {note}")
    run = run_process(cmd, cwd=None, timeout_s=60, log_path=output_dir / "qa-invoke.log")
    if report.is_file():
        return report
    if run["exit"] not in (0, 3, 4):
        eprint(f"[bench] qa-reel.py failed: exit {run['exit']}")
    return report if report.is_file() else None


def maybe_run_preflight(manifest: Path, style: Path | None) -> tuple[int, str]:
    if not RENDERER.is_file():
        eprint("[bench] render-reel.py missing; skipping preflight count")
        return 0, ""
    help_text = script_help(RENDERER)
    reg = load_regress()
    if help_text and not reg.has_flag(help_text, "--dry-run"):
        eprint("[bench] omitting --dry-run (not in render-reel.py --help)")
        return 0, ""
    cmd = [sys.executable, str(RENDERER), "--dry-run"]
    if not help_text or reg.has_flag(help_text, "--manifest"):
        cmd.extend(["--manifest", str(manifest)])
    if style is not None and style.is_file():
        if not help_text or reg.has_flag(help_text, "--style"):
            cmd.extend(["--style", str(style)])
        else:
            eprint("[bench] omitting --style (not in render-reel.py --help)")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        eprint(f"[bench] render-reel.py --dry-run failed: {exc}")
        return 0, ""
    text = (r.stdout or "") + (r.stderr or "")
    return count_preflight_warns(text), text


def load_optional_json(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        val = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return val if isinstance(val, dict) else None


def _as_ranges(manifest: dict | None) -> list[tuple[float, float]]:
    if not isinstance(manifest, dict):
        return []
    spine = manifest.get("spine")
    if not isinstance(spine, dict):
        return []
    out: list[tuple[float, float]] = []
    for item in spine.get("ranges") or []:
        if not isinstance(item, dict):
            continue
        try:
            out.append((float(item["start"]), float(item["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _beats_from_transcript(
    path: Path, ranges: list[tuple[float, float]]
) -> list[dict]:
    data = load_optional_json(path)
    if not data:
        return []
    sentences: list[tuple[float, float, str]] = []
    segs = data.get("segments") if isinstance(data.get("segments"), list) else []
    for seg in segs:
        if not isinstance(seg, dict):
            continue
        words = seg.get("words") if isinstance(seg.get("words"), list) else []
        if words:
            buf: list[str] = []
            buf_start: float | None = None
            last_end: float | None = None
            for w in words:
                if not isinstance(w, dict):
                    continue
                token = str(w.get("word") or w.get("text") or "").strip()
                if not token:
                    continue
                try:
                    ws = float(w.get("start"))
                    we = float(w.get("end", w.get("start")))
                except (TypeError, ValueError):
                    continue
                if buf_start is None:
                    buf_start = ws
                buf.append(token)
                last_end = we
                if re.search(r"[.!?]$", token):
                    sentences.append((buf_start, last_end, " ".join(buf)))
                    buf = []
                    buf_start = None
            if buf and buf_start is not None:
                end = last_end if last_end is not None else buf_start
                sentences.append((buf_start, end, " ".join(buf)))
        else:
            try:
                s0 = float(seg.get("start", 0))
                s1 = float(seg.get("end", s0))
            except (TypeError, ValueError):
                continue
            text = str(seg.get("text") or "").strip()
            if text:
                sentences.append((s0, s1, text))
    beats: list[dict] = []
    for start, end, text in sentences:
        if any(lo <= start < hi for lo, hi in ranges):
            beats.append({"beat": text, "start": start, "end": end})
    return beats


def _spine_to_source(t: float, ranges: list[tuple[float, float]]) -> float | None:
    acc = 0.0
    for lo, hi in ranges:
        length = hi - lo
        if t <= acc + length + 1e-9:
            return lo + max(0.0, t - acc)
        acc += length
    return None


def _punch_windows(
    timeline: dict | None, manifest: dict | None
) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    ranges = _as_ranges(manifest)
    if isinstance(manifest, dict) and isinstance(manifest.get("broll"), list):
        for b in manifest["broll"]:
            if not isinstance(b, dict):
                continue
            at = _num(b.get("at"))
            dur = _num(b.get("dur")) or 2.5
            if at is None:
                continue
            src_at = _spine_to_source(at, ranges)
            if src_at is None:
                src_at = at
            windows.append((src_at, src_at + dur))
        if windows:
            return windows
    if isinstance(timeline, dict) and isinstance(timeline.get("punches"), list):
        for p in timeline["punches"]:
            if not isinstance(p, dict):
                continue
            at = _num(p.get("at_final", p.get("at")))
            dur = _num(p.get("dur")) or 2.5
            if at is None:
                continue
            windows.append((at, at + dur))
    return windows


def unpunched_beats(manifest: dict | None, timeline: dict | None) -> list[str]:
    """Sentences starting inside kept ranges whose window holds no punch."""
    ranges = _as_ranges(manifest)
    if not ranges:
        return []
    transcript: Path | None = None
    if isinstance(manifest, dict):
        src = manifest.get("source")
        if isinstance(src, dict) and src.get("transcript_json"):
            p = Path(str(src["transcript_json"]))
            if p.is_file():
                transcript = p
    beats: list[dict] = []
    if transcript is not None:
        beats = _beats_from_transcript(transcript, ranges)
    if not beats and isinstance(manifest, dict):
        spine = manifest.get("spine") if isinstance(manifest.get("spine"), dict) else {}
        for item in (spine or {}).get("ranges") or []:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            if not quote:
                continue
            try:
                start, end = float(item["start"]), float(item["end"])
            except (KeyError, TypeError, ValueError):
                continue
            beats.append({"beat": quote, "start": start, "end": end})
    windows = _punch_windows(timeline, manifest)
    out: list[str] = []
    for b in beats:
        start, end = b["start"], b["end"]
        covered = any(lo < end and hi > start for lo, hi in windows)
        if not covered:
            out.append(b["beat"])
    return out


def build_verifier_prompt(
    *,
    sheet: str | None,
    punches: list[dict],
    unpunched: list[str],
) -> str:
    lines = [
        "Grade each punch from the contact sheet. Return strict JSON only.",
        "",
        f"Contact sheet path: {sheet or '(none)'}",
        "Open that image. It is the only picture you may look at.",
        "",
        "Punch table:",
        "| index | time | kind | line | shows | file |",
        "|---|---|---|---|---|---|",
    ]
    if not punches:
        lines.append("| | | | | | |")
    for i, p in enumerate(punches):
        idx = p.get("index", i)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    fmt_cell(p.get("at_final")),
                    fmt_cell(p.get("kind")),
                    str(p.get("line") or "").replace("|", "\\|"),
                    str(p.get("shows") or "").replace("|", "\\|"),
                    str(p.get("path") or ""),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Unpunched transcript beats (sentences starting inside kept ranges whose window holds no punch):",
        ]
    )
    if unpunched:
        for beat in unpunched:
            lines.append(f"- {beat}")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "Rubric:",
            "- exact: the picture literally shows the noun phrase in `line`. Trade terms are literal: a pocket door disappears into a wall cavity; a closet bypass or barn slider on a track is NOT a pocket door; a hidden door is concealed in the wall's finish (paneling, slats), not merely a dark door in matching trim; an arched opening has no door slab.",
            '- category: the same kind of thing but not what the line names (a hallway for "hallway full of doors", any door for "hidden door", a sliding closet door for "pocket door").',
            "- wrong: something else.",
            "",
            "For each un-punched beat set should_have_punched to true or false with a one-line reason, judged ONLY from whether this run's own `shows` texts or the visible sheet suggest an exact asset was available. Do not search a library.",
            "",
            "Return exactly this JSON shape:",
            '{"punches": [{"index": 0, "grade": "exact|category|wrong", "sees": "", "reason": ""}], "unpunched": [{"beat": "", "should_have_punched": false, "reason": ""}]}',
        ]
    )
    return "\n".join(lines) + "\n"


def extract_json_object(text: str) -> dict | None:
    """First JSON object that looks like verifier output."""
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    candidates: list[str] = [raw]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fence:
        candidates.append(fence.group(1))
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    try:
        wrapped = load_regress().parse_summary_json(raw)
    except Exception:
        wrapped = None
    if isinstance(wrapped, dict):
        if "punches" in wrapped or "unpunched" in wrapped:
            return wrapped
        for key in ("result", "output", "text", "message"):
            val = wrapped.get(key)
            if isinstance(val, dict) and ("punches" in val or "unpunched" in val):
                return val
            if isinstance(val, str):
                candidates.append(val)
            # pi-run --json nests the model's reply as result.text (a JSON string,
            # sometimes fenced). The first real bench lost every grade here.
            if isinstance(val, dict):
                for tkey in ("text", "final_text", "salvaged_text", "message"):
                    tval = val.get(tkey)
                    if isinstance(tval, str) and tval.strip():
                        candidates.append(tval)
                        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", tval, re.S)
                        if fenced:
                            candidates.append(fenced.group(1))
                        s, e = tval.find("{"), tval.rfind("}")
                        if s != -1 and e > s:
                            candidates.append(tval[s : e + 1])
    for c in candidates:
        try:
            val = json.loads(c)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(val, dict):
            continue
        if "punches" in val or "unpunched" in val:
            return val
        inner = val.get("result")
        if isinstance(inner, dict) and ("punches" in inner or "unpunched" in inner):
            return inner
    return None


def normalize_verifier_payload(data: dict | None) -> dict:
    punches: list[dict] = []
    unpunched: list[dict] = []
    if isinstance(data, dict):
        for i, item in enumerate(data.get("punches") or []):
            if not isinstance(item, dict):
                continue
            grade = str(item.get("grade") or "").lower().strip()
            if grade not in GRADE_VALUES:
                continue
            try:
                idx = int(item.get("index", i))
            except (TypeError, ValueError):
                idx = i
            punches.append(
                {
                    "index": idx,
                    "grade": grade,
                    "sees": str(item.get("sees") or ""),
                    "reason": str(item.get("reason") or ""),
                }
            )
        for item in data.get("unpunched") or []:
            if not isinstance(item, dict):
                continue
            flag = item.get("should_have_punched")
            if isinstance(flag, str):
                flag = flag.strip().lower() in ("true", "yes", "1")
            unpunched.append(
                {
                    "beat": str(item.get("beat") or ""),
                    "should_have_punched": bool(flag),
                    "reason": str(item.get("reason") or ""),
                }
            )
    return {"punches": punches, "unpunched": unpunched}


def count_punch_kinds(punches: list[dict]) -> tuple[int, int]:
    stills = 0
    video_n = 0
    for p in punches:
        kind = str(p.get("kind") or "").lower()
        if kind == "still":
            stills += 1
        else:
            video_n += 1
    return stills, video_n


def apply_verifier_payload(score: dict, payload: dict) -> None:
    # A verifier that returned nothing (failed run, empty reply) leaves the
    # harness UNGRADED, which ranks last; zeros would read as a perfect run.
    if not (payload.get("punches") or payload.get("unpunched")):
        for k in ("exact", "category", "wrong", "unpunched_ok", "missed"):
            score[k] = None
        score["verifier_punches"] = []
        score["verifier_unpunched"] = []
        return
    grades = [p.get("grade") for p in payload.get("punches") or []]
    score["exact"] = grades.count("exact")
    score["category"] = grades.count("category")
    score["wrong"] = grades.count("wrong")
    unp = payload.get("unpunched") or []
    score["unpunched_ok"] = sum(1 for u in unp if not u.get("should_have_punched"))
    score["missed"] = sum(1 for u in unp if u.get("should_have_punched"))
    score["verifier_punches"] = payload.get("punches") or []
    score["verifier_unpunched"] = unp


def scored_fail_count(score: dict) -> int:
    ids = score.get("qa_fail_ids") or []
    return sum(1 for i in ids if i != STATIC_GAP_ID)


def rank_key(score: dict) -> tuple:
    ran = 0 if score.get("exact") is not None else 1
    wrong = int(score.get("wrong") or 0)
    category = int(score.get("category") or 0)
    defect = 0 if (wrong == 0 and category == 0) else 1
    missed = int(score.get("missed") or 0)
    fails = scored_fail_count(score)
    pre = int(score.get("preflight_warns") or 0)
    stray = len(score.get("stray_writes") or [])
    cost = score.get("cost_usd")
    wall = score.get("wall_s")
    cost_n = float(cost) if isinstance(cost, (int, float)) else float("inf")
    wall_n = float(wall) if isinstance(wall, (int, float)) else float("inf")
    # Among defect-free runs with equal misses, more exact punches wins:
    # otherwise a cut with no punches at all (nothing to grade) ranks first.
    exact_n = int(score.get("exact") or 0)
    return (ran, defect, missed, -exact_n, fails, pre, stray, cost_n, wall_n)


def rank_scores(scores: list[dict]) -> list[dict]:
    return sorted(scores, key=rank_key)


def grades_sidecar_path(output_dir: Path, score: dict) -> Path:
    video = score.get("video")
    if video:
        p = Path(str(video))
        return p.with_name(p.stem + ".grades.json")
    sheet = score.get("contact_sheet")
    if sheet:
        p = Path(str(sheet))
        name = p.name
        if name.endswith(".sheet.jpg"):
            return p.with_name(name[: -len(".sheet.jpg")] + ".grades.json")
        return p.with_name(p.stem + ".grades.json")
    return output_dir / "grades.json"


def write_grades_sidecar(path: Path, payload: dict) -> None:
    doc = {
        "punches": [
            {"index": p["index"], "grade": p["grade"], "by": "verifier"}
            for p in payload.get("punches") or []
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def punch_grade_at(score: dict, index: int, who: str) -> str:
    key = "verifier_punches" if who == "verifier" else "owner_punches"
    for p in score.get(key) or []:
        if not isinstance(p, dict):
            continue
        try:
            if int(p.get("index")) == int(index):
                return str(p.get("grade") or "")
        except (TypeError, ValueError):
            continue
    return ""


def agreement_for(
    verifier_punches: list[dict], owner_punches: list[dict]
) -> tuple[int, int, float | None]:
    owner_by: dict[int, str] = {}
    for p in owner_punches:
        if not isinstance(p, dict):
            continue
        try:
            owner_by[int(p.get("index"))] = str(p.get("grade") or "").lower()
        except (TypeError, ValueError):
            continue
    ver_by: dict[int, str] = {}
    for p in verifier_punches:
        if not isinstance(p, dict):
            continue
        try:
            ver_by[int(p.get("index"))] = str(p.get("grade") or "").lower()
        except (TypeError, ValueError):
            continue
    graded = list(owner_by)
    if not graded:
        return 0, 0, None
    match = sum(1 for k in graded if owner_by.get(k) == ver_by.get(k))
    return match, len(graded), match / len(graded)


def merge_grades(scores: list[dict], owner: dict) -> dict:
    harnesses: dict[str, dict] = {}
    match_all = 0
    graded_all = 0
    for score in scores:
        hid = str(score.get("id"))
        owner_h = owner.get(hid) if isinstance(owner.get(hid), dict) else {}
        owner_ps = (
            owner_h.get("punches") if isinstance(owner_h.get("punches"), list) else []
        )
        ver_ps = score.get("verifier_punches") or []
        matched, graded, ratio = agreement_for(ver_ps, owner_ps)
        match_all += matched
        graded_all += graded
        owner_by: dict[int, str] = {}
        for p in owner_ps:
            if isinstance(p, dict):
                try:
                    owner_by[int(p.get("index"))] = str(p.get("grade") or "").lower()
                except (TypeError, ValueError):
                    pass
        ver_by: dict[int, str] = {}
        for p in ver_ps:
            if isinstance(p, dict) and "index" in p:
                try:
                    ver_by[int(p["index"])] = str(p.get("grade") or "")
                except (TypeError, ValueError):
                    pass
        rows = []
        for idx in sorted(set(owner_by) | set(ver_by)):
            vg = ver_by.get(idx)
            og = owner_by.get(idx)
            rows.append(
                {
                    "index": idx,
                    "verifier": vg,
                    "owner": og,
                    "agree": vg is not None and og is not None and vg == og,
                }
            )
        harnesses[hid] = {
            "punches": rows,
            "agreement": None if graded == 0 else round(ratio or 0.0, 2),
            "matched": matched,
            "graded": graded,
        }
        score["owner_punches"] = owner_ps
        score["agreement"] = None if graded == 0 else round(ratio or 0.0, 2)
        score["agreement_matched"] = matched
        score["agreement_graded"] = graded
    overall = None if graded_all == 0 else round(match_all / graded_all, 2)
    return {
        "harnesses": harnesses,
        "overall": overall,
        "matched": match_all,
        "graded": graded_all,
    }


def build_verifier_pi_cmd(
    *,
    pi_run: Path | str,
    cwd: Path | str,
    provider: str,
    model: str,
    thinking: str | None,
    harness_id: str,
    task_file: Path | str,
) -> list[str]:
    cmd = [
        str(pi_run),
        "--cwd",
        str(cwd),
        "--role",
        "generic",
        "--provider",
        str(provider),
        "--model",
        str(model),
    ]
    if thinking:
        cmd.extend(["--thinking", str(thinking)])
    cmd.extend(
        [
            "--tools",
            VERIFIER_TOOLS,
            "--isolation",
            "none",
            "--label",
            f"verify-{harness_id}",
            "--json",
            "--spec-file",
            str(task_file),
        ]
    )
    return cmd


def run_verifier_command(
    cmd: str, prompt: str, *, timeout_s: float, log_path: Path
) -> dict:
    t0 = time.monotonic()
    started = iso_now()
    try:
        args = shlex.split(cmd)
    except ValueError as exc:
        text = str(exc)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(text + "\n", encoding="utf-8")
        return {
            "started": started,
            "ended": iso_now(),
            "wall_s": 0.0,
            "exit": 2,
            "timeout": False,
            "output": text,
            "error": text,
        }
    try:
        proc = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        out = proc.stdout or ""
        if proc.stderr:
            out = out + ("\n" + proc.stderr if out else proc.stderr)
        code = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        code = 1
        timed_out = True
    except OSError as exc:
        out = str(exc)
        code = 127
        timed_out = False
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(prompt + "\n---\n" + (out or ""), encoding="utf-8")
    return {
        "started": started,
        "ended": iso_now(),
        "wall_s": round(time.monotonic() - t0, 3),
        "exit": code,
        "timeout": timed_out,
        "output": out,
        "error": None if code == 0 else out,
    }


def verify_one(
    score: dict,
    *,
    harness: dict,
    cfg: dict,
    output_dir: Path,
    verifier_cmd: str | None,
    verifier_cfg: dict | None,
    timeout_s: float = 600,
) -> None:
    """Run the verifier after a harness is scored. Does not edit the manifest."""
    if score.get("skipped"):
        return
    manifest = (
        load_optional_json(Path(score["manifest"])) if score.get("manifest") else None
    )
    timeline = (
        load_optional_json(Path(score["timeline"])) if score.get("timeline") else None
    )
    punches = score.get("punches") or []
    unpunched = unpunched_beats(manifest, timeline)
    prompt = build_verifier_prompt(
        sheet=score.get("contact_sheet"),
        punches=punches,
        unpunched=unpunched,
    )
    spec_file = output_dir / "verify-task.md"
    spec_file.write_text(prompt, encoding="utf-8")
    log_path = output_dir / "verifier.log"
    rec: dict[str, Any] = {"id": score.get("id"), "started": iso_now()}
    raw_out = ""

    if verifier_cmd:
        run = run_verifier_command(
            verifier_cmd, prompt, timeout_s=timeout_s, log_path=log_path
        )
        raw_out = run.get("output") or ""
        rec.update(
            {
                "kind": "cmd",
                "command": verifier_cmd,
                "model": None,
                "provider": None,
                "exit": run.get("exit"),
                "wall_s": run.get("wall_s"),
                "cost_usd": None,
                "timeout": run.get("timeout"),
                "raw": raw_out,
            }
        )
    else:
        chosen = choose_verifier(harness, verifier_cfg)
        if not chosen:
            eprint(f"[bench] {score.get('id')}: verifier config empty; skipping")
            return
        if str(chosen.get("kind") or "pi") != "pi":
            eprint(
                f"[bench] {score.get('id')}: verifier kind {chosen.get('kind')} "
                "needs --verifier-cmd"
            )
            return
        if not chosen.get("provider") or not chosen.get("model"):
            eprint(f"[bench] {score.get('id')}: verifier needs provider and model")
            return
        pi_run = find_pi_run()
        if pi_run is None:
            eprint(f"[bench] {score.get('id')}: pi-run missing; skipping verifier")
            rec.update({"notes": ["pi-run missing"], "skipped": True, "model": chosen.get("model")})
            write_harness_json(output_dir / "verifier.json", rec)
            return
        cmd = build_verifier_pi_cmd(
            pi_run=pi_run,
            cwd=cfg["cwd"],
            provider=str(chosen["provider"]),
            model=str(chosen["model"]),
            thinking=chosen.get("thinking"),
            harness_id=str(score.get("id")),
            task_file=spec_file,
        )
        run = run_process(cmd, cwd=cfg["cwd"], timeout_s=timeout_s, log_path=log_path)
        raw_out = run.get("output") or ""
        parsed_summary = parse_pi_summary(raw_out)
        rec.update(
            {
                "kind": "pi",
                "provider": chosen.get("provider"),
                "model": chosen.get("model"),
                "thinking": chosen.get("thinking"),
                "exit": run.get("exit"),
                "wall_s": (
                    parsed_summary.get("wall_s")
                    if parsed_summary.get("wall_s") is not None
                    else run.get("wall_s")
                ),
                "cost_usd": parsed_summary.get("cost_usd"),
                "tokens_in": parsed_summary.get("tokens_in"),
                "tokens_out": parsed_summary.get("tokens_out"),
                "timeout": run.get("timeout"),
                "raw": parsed_summary.get("raw")
                if parsed_summary.get("raw") is not None
                else raw_out,
            }
        )

    payload = extract_json_object(raw_out)
    if payload is None:
        eprint(f"[bench] {score.get('id')}: verifier did not print JSON")
    normalized = normalize_verifier_payload(payload)
    rec["parsed"] = normalized
    rec["ended"] = iso_now()
    write_harness_json(output_dir / "verifier.json", rec)
    grades_path = grades_sidecar_path(output_dir, score)
    write_grades_sidecar(grades_path, normalized)
    apply_verifier_payload(score, normalized)
    score["verifier_cost_usd"] = rec.get("cost_usd")
    score["verifier_wall_s"] = rec.get("wall_s")
    score["grades_path"] = str(grades_path)
    score["verifier_model"] = rec.get("model")


def deliver_bench_outputs(
    dest: Path,
    *,
    scores: list[dict],
    md_path: Path,
    html_path: Path,
) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for score in scores:
        hid = str(score.get("id") or "harness")
        try:
            safe = load_regress().safe_name(hid)
        except Exception:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "-", hid).strip("-") or "harness"
        pairs: list[tuple[Path, str]] = []
        video = score.get("video")
        if video and Path(str(video)).is_file():
            src = Path(str(video))
            pairs.append((src, f"{safe}-{src.name}"))
        rn = score.get("runnotes")
        if rn and Path(str(rn)).is_file():
            src = Path(str(rn))
            pairs.append((src, f"{safe}-{src.name}"))
        sheet = score.get("contact_sheet")
        if sheet and Path(str(sheet)).is_file():
            src = Path(str(sheet))
            pairs.append((src, f"{safe}-{src.name}"))
        for report in (md_path, html_path):
            if report.is_file():
                pairs.append((report, f"{safe}-{report.name}"))
        for src, name in pairs:
            target = dest / name
            shutil.copy2(src, target)
            copied.append(str(target))
    return copied


def score_harness_dir(
    output_dir: Path,
    *,
    style: Path | None = None,
    stray: list[str] | None = None,
    run_preflight: bool = True,
    run_qa_if_missing: bool = True,
) -> dict:
    """Score whatever is in a harness output dir."""
    harness = load_optional_json(output_dir / "harness.json") or {}
    log_text = ""
    log_path = output_dir / "harness.log"
    if log_path.is_file():
        try:
            log_text = log_path.read_text(encoding="utf-8")
        except OSError:
            log_text = ""
    video = newest_video(output_dir)
    produced = video is not None
    manifest_path = find_manifest(output_dir, video)
    manifest = load_optional_json(manifest_path)
    qa_path = find_qa_json(output_dir, video)
    if produced and qa_path is None and run_qa_if_missing:
        qa_path = maybe_run_qa(video, manifest_path, output_dir)
    qa = load_optional_json(qa_path)
    reg = load_regress()
    timeline_path, timeline, _spine_only = reg.discover_finish_timeline(
        video, output_dir, None
    )
    # The sheet must belong to the render being scored. A harness that
    # rendered v1..v3 has three sheets; the regress finder picked v2's for
    # Grok's v3 in run 2 and the verifier graded the wrong pictures.
    own_sheet = video.with_name(video.stem + ".sheet.jpg") if video is not None else None
    if own_sheet is not None and own_sheet.exists():
        sheet = own_sheet
    else:
        sheet = reg.find_contact_sheet(output_dir, video, qa)
    runnotes_path = find_runnotes(output_dir)
    deviations = ""
    if runnotes_path is not None:
        try:
            deviations = parse_known_deviations(
                runnotes_path.read_text(encoding="utf-8")
            )
        except OSError:
            deviations = ""
    duration_s = None
    if video is not None:
        duration_s = reg.probe_duration(video)
    if duration_s is None and isinstance(timeline, dict):
        duration_s = _num(timeline.get("duration_s"))
    preflight_warns = 0
    if run_preflight and manifest_path is not None:
        preflight_warns, _ = maybe_run_preflight(manifest_path, style)
    mp4s = list_mp4s(output_dir)
    dry_runs = log_text.count("Preflight")
    fail_ids = qa_ids_with_status(qa, "fail")
    warn_ids = qa_ids_with_status(qa, "warn")
    details = qa_detail_map(qa)
    join_st = join_uncovered_status(qa)
    joins_covered = None
    if join_st is not None:
        joins_covered = join_st == "pass"
    skipped = bool(harness.get("skipped"))
    timeout = bool(harness.get("timeout"))
    punches = punch_rows(timeline, manifest)
    stills, video_punches = count_punch_kinds(punches)
    cover = None
    try:
        cover = reg.rendered_cover_text(manifest, timeline)
    except Exception:
        if isinstance(manifest, dict):
            cover_obj = manifest.get("cover")
            if isinstance(cover_obj, dict):
                cover = cover_obj.get("text")
    status = "ok"
    if skipped:
        status = "skipped"
    elif timeout:
        status = "timeout"
    elif not produced:
        status = "no_render"
    return {
        "id": harness.get("id") or output_dir.name,
        "kind": harness.get("kind"),
        "provider": harness.get("provider"),
        "model": harness.get("model"),
        "thinking": harness.get("thinking"),
        "effort": harness.get("effort"),
        "produced_render": produced,
        "skipped": skipped,
        "timeout": timeout,
        "status": status,
        "qa_verdict": reg.qa_verdict_of(qa),
        "qa_fail_ids": fail_ids,
        "qa_warn_ids": warn_ids,
        "qa_fail_details": {i: details.get(i, "") for i in fail_ids},
        "qa_warn_details": {i: details.get(i, "") for i in warn_ids},
        "duration_s": duration_s,
        "in_window": in_window_of(manifest, duration_s),
        "hook_mode": hook_mode_of(timeline, manifest),
        "cover_text": cover,
        "punches": punches,
        "stills": stills,
        "video_punches": video_punches,
        "exact": None,
        "category": None,
        "wrong": None,
        "unpunched_ok": None,
        "missed": None,
        "verifier_cost_usd": None,
        "verifier_wall_s": None,
        "joins_covered": joins_covered,
        "preflight_warns": preflight_warns,
        "renders": len(mp4s),
        "dry_runs": dry_runs,
        "stray_writes": list(stray or harness.get("stray_writes") or []),
        "wall_s": harness.get("wall_s"),
        "cost_usd": harness.get("cost_usd"),
        "tokens_in": harness.get("tokens_in"),
        "tokens_out": harness.get("tokens_out"),
        "contact_sheet": str(sheet) if sheet is not None else None,
        "runnotes": str(runnotes_path) if runnotes_path is not None else None,
        "runnotes_deviations": deviations,
        "manifest": str(manifest_path) if manifest_path is not None else None,
        "video": str(video) if video is not None else None,
        "qa_path": str(qa_path) if qa_path is not None else None,
        "timeline": str(timeline_path) if timeline_path is not None else None,
        "notes": list(harness.get("notes") or []),
        "exit": harness.get("exit"),
        "started": harness.get("started"),
        "ended": harness.get("ended"),
    }


def fmt_cell(val: Any) -> str:
    if val is None:
        return "n/a"
    if isinstance(val, bool):
        return "yes" if val else "no"
    if isinstance(val, float):
        if abs(val) >= 100:
            return f"{val:.1f}"
        return f"{val:.2f}"
    if isinstance(val, list):
        if not val:
            return "0"
        if all(isinstance(x, str) for x in val):
            return ", ".join(val)
        return str(len(val))
    return str(val)


def table_row(score: dict) -> dict:
    fails = score.get("qa_fail_ids") or []
    warns = score.get("qa_warn_ids") or []
    punches = score.get("punches") or []
    stray = score.get("stray_writes") or []
    produced = "skipped" if score.get("skipped") else fmt_cell(score.get("produced_render"))
    return {
        "id": score.get("id"),
        "model": score.get("model"),
        "produced": produced,
        "qa": score.get("qa_verdict") or "n/a",
        "fails": len(fails) if fails else (0 if score.get("qa_verdict") else "n/a"),
        "warns": len(warns) if warns else (0 if score.get("qa_verdict") else "n/a"),
        "duration": score.get("duration_s"),
        "punches": len(punches),
        "exact": score.get("exact"),
        "category": score.get("category"),
        "wrong": score.get("wrong"),
        "unpunched_ok": score.get("unpunched_ok"),
        "missed": score.get("missed"),
        "stills": score.get("stills"),
        "video_punches": score.get("video_punches"),
        "preflight_warns": score.get("preflight_warns"),
        "renders": score.get("renders"),
        "stray_writes": len(stray),
        "wall": score.get("wall_s"),
        "cost": score.get("cost_usd"),
        "verifier_wall": score.get("verifier_wall_s"),
        "verifier_cost": score.get("verifier_cost_usd"),
        "fail_ids": fails,
        "warn_ids": warns,
    }


def write_markdown(
    path: Path,
    *,
    cfg: dict,
    scores: list[dict],
    date_s: str,
    concurrency: int,
) -> None:
    task = cfg["task"]
    lines = [
        "# Reel bench",
        "",
        f"- note: `{task['note']}`",
        f"- mode: {task['mode']}",
        f"- date: {date_s}",
        f"- concurrency: {concurrency}",
        f"- output_root: `{task['output_root']}`",
        "",
        "| id | model | produced | QA | fails | warns | duration | punches | exact | category | wrong | unpunched_ok | missed | stills | video_punches | preflight warns | renders | stray writes | wall | cost | verifier wall | verifier cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for score in scores:
        row = table_row(score)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["id"]),
                    fmt_cell(row["model"]),
                    str(row["produced"]),
                    str(row["qa"]),
                    fmt_cell(row["fail_ids"] if row["fail_ids"] else row["fails"]),
                    fmt_cell(row["warn_ids"] if row["warn_ids"] else row["warns"]),
                    fmt_cell(row["duration"]),
                    str(row["punches"]),
                    fmt_cell(row["exact"]),
                    fmt_cell(row["category"]),
                    fmt_cell(row["wrong"]),
                    fmt_cell(row["unpunched_ok"]),
                    fmt_cell(row["missed"]),
                    fmt_cell(row["stills"]),
                    fmt_cell(row["video_punches"]),
                    fmt_cell(row["preflight_warns"]),
                    fmt_cell(row["renders"]),
                    fmt_cell(row["stray_writes"]),
                    fmt_cell(row["wall"]),
                    fmt_cell(row["cost"]),
                    fmt_cell(row["verifier_wall"]),
                    fmt_cell(row["verifier_cost"]),
                ]
            )
            + " |"
        )
    lines.extend(["", RANKING_RULE, ""])
    if any(s.get("agreement") is not None for s in scores):
        parts = []
        for score in scores:
            if score.get("agreement") is None:
                continue
            parts.append(
                f"{score.get('id')}: {score.get('agreement_matched')}/{score.get('agreement_graded')} ({fmt_cell(score.get('agreement'))})"
            )
        matched = sum(int(s.get("agreement_matched") or 0) for s in scores)
        graded = sum(int(s.get("agreement_graded") or 0) for s in scores)
        overall_r = None if graded == 0 else round(matched / graded, 2)
        lines.append("Verifier agreement: " + "; ".join(parts))
        lines.append(f"Overall agreement: {matched}/{graded} ({fmt_cell(overall_r)})")
        lines.append("")
    for score in scores:
        hid = score.get("id")
        lines.extend(["", f"## {hid}", ""])
        if score.get("skipped"):
            notes = score.get("notes") or ["skipped"]
            lines.append("Skipped: " + "; ".join(str(n) for n in notes))
            lines.append("")
        lines.append(f"Cover line: {score.get('cover_text') or '(none)'}")
        lines.append(f"Hook decision: {score.get('hook_mode') or '(unknown)'}")
        lines.append("")
        lines.append("| time | kind | file | line | shows | verifier | owner |")
        lines.append("|---|---|---|---|---|---|---|")
        punches = score.get("punches") or []
        if not punches:
            lines.append("| | | | | | | |")
        for i, p in enumerate(punches):
            idx = p.get("index", i)
            try:
                idx_n = int(idx)
            except (TypeError, ValueError):
                idx_n = i
            lines.append(
                "| "
                + " | ".join(
                    [
                        fmt_cell(p.get("at_final")),
                        fmt_cell(p.get("kind")),
                        str(p.get("path") or ""),
                        str(p.get("line") or "").replace("|", "\\|"),
                        str(p.get("shows") or "").replace("|", "\\|"),
                        punch_grade_at(score, idx_n, "verifier") or "",
                        punch_grade_at(score, idx_n, "owner") or "",
                    ]
                )
                + " |"
            )
        lines.append("")
        lines.append("QA fail/warn ids:")
        fail_d = score.get("qa_fail_details") or {}
        warn_d = score.get("qa_warn_details") or {}
        if not fail_d and not warn_d:
            lines.append("- (none)")
        for ident, detail in fail_d.items():
            lines.append(f"- FAIL `{ident}`: {detail or '(no detail)'}")
        for ident, detail in warn_d.items():
            lines.append(f"- WARN `{ident}`: {detail or '(no detail)'}")
        lines.append("")
        lines.append("Known deviations:")
        dev = score.get("runnotes_deviations") or ""
        lines.append(dev if dev else "(none)")
        lines.append("")
        stray = score.get("stray_writes") or []
        lines.append("Stray writes:")
        if stray:
            for s in stray:
                lines.append(f"- `{s}`")
        else:
            lines.append("(none)")
        lines.append("")
        sheet = score.get("contact_sheet")
        lines.append(f"Contact sheet: `{sheet}`" if sheet else "Contact sheet: (none)")
        notes = score.get("notes") or []
        if notes and not score.get("skipped"):
            lines.append("")
            lines.append("Notes: " + "; ".join(str(n) for n in notes))
    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "Rows are ranked: zero wrong and zero category first, then fewest "
            "missed, then gate fails 0, preflight warns 0, stray writes 0, then "
            "cost, then wall. video.static_gap is listed in fails but never "
            "scored. Verifier cost and wall are their own columns.",
            "",
            "exact / category / wrong come from a fresh-context verifier looking "
            "at the contact sheet. Owner grades (--grades) are ground truth; "
            "agreement is matching grades over graded punches.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def sheet_data_uri(path: Path, max_width: int = 900) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        eprint("[bench] Pillow missing; skipping contact sheet embed")
        return None
    try:
        im = Image.open(path)
        im.load()
    except OSError as exc:
        eprint(f"[bench] cannot read sheet {path}: {exc}")
        return None
    if im.width > max_width and im.width > 0:
        h = max(1, int(im.height * max_width / im.width))
        im = im.resize((max_width, h), Image.Resampling.LANCZOS)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def write_html(
    path: Path,
    *,
    cfg: dict,
    scores: list[dict],
    date_s: str,
    concurrency: int,
) -> None:
    task = cfg["task"]
    esc = html.escape
    rows_html = []
    for score in scores:
        row = table_row(score)
        cells = [
            row["id"],
            fmt_cell(row["model"]),
            row["produced"],
            row["qa"],
            fmt_cell(row["fail_ids"] if row["fail_ids"] else row["fails"]),
            fmt_cell(row["warn_ids"] if row["warn_ids"] else row["warns"]),
            fmt_cell(row["duration"]),
            row["punches"],
            fmt_cell(row["exact"]),
            fmt_cell(row["category"]),
            fmt_cell(row["wrong"]),
            fmt_cell(row["unpunched_ok"]),
            fmt_cell(row["missed"]),
            fmt_cell(row["stills"]),
            fmt_cell(row["video_punches"]),
            fmt_cell(row["preflight_warns"]),
            fmt_cell(row["renders"]),
            fmt_cell(row["stray_writes"]),
            fmt_cell(row["wall"]),
            fmt_cell(row["cost"]),
            fmt_cell(row["verifier_wall"]),
            fmt_cell(row["verifier_cost"]),
        ]
        tds = "".join(f"<td>{esc(str(c))}</td>" for c in cells)
        rows_html.append(f"<tr>{tds}</tr>")
    sections = []
    for score in scores:
        hid = esc(str(score.get("id")))
        punches = score.get("punches") or []
        punch_rows_html = []
        for i, p in enumerate(punches):
            idx = p.get("index", i)
            try:
                idx_n = int(idx)
            except (TypeError, ValueError):
                idx_n = i
            cells_p = [
                fmt_cell(p.get("at_final")),
                fmt_cell(p.get("kind")),
                p.get("path") or "",
                p.get("line") or "",
                p.get("shows") or "",
                punch_grade_at(score, idx_n, "verifier") or "",
                punch_grade_at(score, idx_n, "owner") or "",
            ]
            punch_rows_html.append(
                "<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in cells_p) + "</tr>"
            )
        qa_items = []
        for ident, detail in (score.get("qa_fail_details") or {}).items():
            qa_items.append(f"<li>FAIL <code>{esc(ident)}</code>: {esc(detail or '(no detail)')}</li>")
        for ident, detail in (score.get("qa_warn_details") or {}).items():
            qa_items.append(f"<li>WARN <code>{esc(ident)}</code>: {esc(detail or '(no detail)')}</li>")
        stray = score.get("stray_writes") or []
        stray_html = (
            "<ul>" + "".join(f"<li><code>{esc(s)}</code></li>" for s in stray) + "</ul>"
            if stray
            else "<p>(none)</p>"
        )
        img = ""
        sheet = score.get("contact_sheet")
        if sheet and Path(sheet).is_file():
            uri = sheet_data_uri(Path(sheet))
            if uri:
                img = (
                    f'<p>Contact sheet</p><p><img src="{uri}" alt="contact sheet {hid}" '
                    f'style="max-width:900px;height:auto"></p>'
                )
            else:
                img = f"<p>Contact sheet: <code>{esc(sheet)}</code></p>"
        else:
            img = "<p>Contact sheet: (none)</p>"
        skipped = ""
        if score.get("skipped"):
            notes = "; ".join(esc(str(n)) for n in (score.get("notes") or ["skipped"]))
            skipped = f"<p><strong>Skipped:</strong> {notes}</p>"
        sections.append(
            f"<section><h2>{hid}</h2>{skipped}"
            f"<p>Cover line: {esc(str(score.get('cover_text') or '(none)'))}</p>"
            f"<p>Hook decision: {esc(str(score.get('hook_mode') or '(unknown)'))}</p>"
            "<table><thead><tr><th>time</th><th>kind</th><th>file</th><th>line</th><th>shows</th><th>verifier</th><th>owner</th></tr></thead>"
            f"<tbody>{''.join(punch_rows_html) or '<tr><td colspan=7>(none)</td></tr>'}</tbody></table>"
            f"<p>QA fail/warn ids</p><ul>{''.join(qa_items) or '<li>(none)</li>'}</ul>"
            f"<p>Known deviations</p><pre>{esc(score.get('runnotes_deviations') or '(none)')}</pre>"
            f"<p>Stray writes</p>{stray_html}{img}</section>"
        )
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reel bench</title>
<style>
:root {{ color: #1a1a1a; background: #f7f4ef; }}
@media (prefers-color-scheme: dark) {{
  :root {{ color: #eeeae3; background: #161513; }}
}}
body {{
  font-family: Georgia, "Times New Roman", serif;
  line-height: 1.45;
  margin: 2rem auto;
  max-width: 1100px;
  padding: 0 1rem;
}}
h1, h2 {{ font-family: Georgia, serif; font-weight: 600; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }}
th, td {{ border: 1px solid currentColor; padding: 0.35rem 0.5rem; text-align: left; vertical-align: top; }}
th {{ font-weight: 600; }}
code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.86rem; }}
pre {{ white-space: pre-wrap; }}
img {{ max-width: 900px; height: auto; border: 1px solid currentColor; }}
.meta {{ margin: 0.3rem 0; }}
</style>
</head>
<body>
<h1>Reel bench</h1>
<p class="meta">note: <code>{esc(str(task['note']))}</code></p>
<p class="meta">mode: {esc(str(task['mode']))}</p>
<p class="meta">date: {esc(date_s)}</p>
<p class="meta">concurrency: {esc(str(concurrency))}</p>
<table>
<thead>
<tr>
<th>id</th><th>model</th><th>produced</th><th>QA</th><th>fails</th><th>warns</th>
<th>duration</th><th>punches</th><th>exact</th><th>category</th><th>wrong</th>
<th>unpunched_ok</th><th>missed</th><th>stills</th><th>video_punches</th>
<th>preflight warns</th><th>renders</th>
<th>stray writes</th><th>wall</th><th>cost</th>
<th>verifier wall</th><th>verifier cost</th>
</tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
<p class="meta">{esc(RANKING_RULE)}</p>
{''.join(sections)}
<h2>How to read this</h2>
<p>Rows are ranked: zero wrong and zero category first, then fewest missed,
then gate fails 0, preflight warns 0, stray writes 0, then cost, then wall.
video.static_gap is listed in fails but never scored. Verifier cost and wall
are their own columns.</p>
<p>exact / category / wrong come from a fresh-context verifier looking at the
contact sheet. Owner grades sit beside the verifier grade on each punch.
Agreement is matching grades over graded punches.</p>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")


def write_json_report(path: Path, *, cfg: dict, scores: list[dict], date_s: str, concurrency: int) -> None:
    payload = {
        "schema": "reel-bench-report/1",
        "note": str(cfg["task"]["note"]),
        "mode": cfg["task"]["mode"],
        "date": date_s,
        "concurrency": concurrency,
        "output_root": str(cfg["task"]["output_root"]),
        "table": [table_row(s) for s in scores],
        "harnesses": scores,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_only(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def select_harnesses(cfg: dict, only: list[str] | None) -> list[dict]:
    items = cfg["harnesses"]
    if only is None:
        return items
    by_id = {h["id"]: h for h in items}
    missing = [i for i in only if i not in by_id]
    if missing:
        raise ConfigError("unknown --only id(s): " + ", ".join(missing))
    return [by_id[i] for i in only]


def harness_output_dir(output_root: Path, harness_id: str) -> Path:
    try:
        safe = load_regress().safe_name(harness_id)
    except Exception:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", harness_id).strip("-.") or "harness"
    return output_root / safe


def counts_as_failure(score: dict) -> bool:
    if score.get("skipped"):
        return False
    if score.get("timeout"):
        return True
    return not bool(score.get("produced_render"))


def run_one_harness(
    harness: dict,
    *,
    cfg: dict,
    timeout_s: int,
    git_lock: threading.Lock,
    dry_run: bool,
    report_only: bool,
) -> dict:
    task = cfg["task"]
    output_dir = harness_output_dir(task["output_root"], harness["id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    task_text = render_task_text(
        note=str(task["note"]),
        style=str(task["style"]),
        output_dir=str(output_dir),
        skill_dir=str(task["skill_dir"]),
        mode=str(task["mode"]),
        harness_id=harness["id"],
        extra=task.get("extra_instructions") or "",
        index=str(task["broll_index"]) if task.get("broll_index") else "",
    )
    task_file = output_dir / "task.md"
    task_file.write_text(task_text, encoding="utf-8")
    stray: list[str] = []
    if report_only:
        existing = load_optional_json(output_dir / "harness.json") or {}
        stray = list(existing.get("stray_writes") or [])
        return score_harness_dir(
            output_dir,
            style=task["style"],
            stray=stray,
        )
    before: set[str] = set()
    with git_lock:
        before = git_porcelain(cfg["cwd"])
    rec = run_adapter(
        harness,
        cwd=cfg["cwd"],
        skill_dir=task["skill_dir"],
        task_text=task_text,
        task_file=task_file,
        output_dir=output_dir,
        timeout_s=timeout_s,
        dry_run=dry_run,
    )
    with git_lock:
        after = git_porcelain(cfg["cwd"])
        stray = stray_writes(
            before, after, cwd=cfg["cwd"], output_root=task["output_root"]
        )
    rec["stray_writes"] = stray
    write_harness_json(output_dir / "harness.json", rec)
    if dry_run:
        return {
            "id": harness["id"],
            "kind": harness.get("kind"),
            "model": harness.get("model"),
            "produced_render": False,
            "skipped": False,
            "timeout": False,
            "status": "dry-run",
            "qa_verdict": None,
            "qa_fail_ids": [],
            "qa_warn_ids": [],
            "qa_fail_details": {},
            "qa_warn_details": {},
            "duration_s": None,
            "in_window": None,
            "hook_mode": None,
            "cover_text": None,
            "punches": [],
            "joins_covered": None,
            "preflight_warns": 0,
            "renders": 0,
            "dry_runs": 0,
            "stray_writes": stray,
            "wall_s": 0,
            "cost_usd": None,
            "tokens_in": None,
            "tokens_out": None,
            "contact_sheet": None,
            "runnotes_deviations": "",
            "notes": ["dry-run"],
            "command": rec.get("command"),
        }
    return score_harness_dir(
        output_dir,
        style=task["style"],
        stray=stray,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Run the same reel task through several harnesses and compare. "
            "Exit 0 every harness produced a scorable render; 3 at least one "
            "failed to render or timed out; 2 config problem. "
            "Adapters: pi, claude, codex, grok, cursor. "
            "Scoring columns: id, model, produced, QA, fails, warns, duration, "
            "punches, exact, category, wrong, unpunched_ok, missed, stills, "
            "video_punches, preflight warns, renders, stray writes, wall, cost, "
            "verifier wall, verifier cost."
        )
    )
    p.add_argument("--config", required=True, help="bench.json (schema reel-bench/1)")
    p.add_argument("--only", help="Comma-separated harness ids")
    p.add_argument("--concurrency", type=int, help="Max parallel harnesses (default 2)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Write every task.md, print commands, run nothing",
    )
    p.add_argument(
        "--report-only",
        action="store_true",
        help="Skip running; score whatever is in the output dirs",
    )
    p.add_argument(
        "--verifier-cmd",
        help=(
            "Override the verifier stage with a command that reads the prompt "
            "on stdin and prints JSON. Used in tests and for any harness that "
            "is not pi-run."
        ),
    )
    p.add_argument(
        "--grades",
        help=(
            "Owner grades JSON keyed by harness id: {\"<id>\": {\"punches\": "
            "[{\"index\": 0, \"grade\": \"exact|category|wrong\"}]}}. "
            "Computes verifier agreement and writes grades-merged.json."
        ),
    )
    p.add_argument("--report", help="Markdown report path")
    p.add_argument("--html", help="HTML report path")
    p.epilog = (
        "Config keys: schema, cwd, task.note, task.style, task.output_root, "
        "task.skill_dir, task.mode, task.extra_instructions, task.broll_index, "
        "task.deliver_to, concurrency, timeout_min, harnesses, verifier "
        "(kind, provider, model, thinking, alternate). "
        "--verifier-cmd overrides the verifier stage. --grades FILE is owner "
        "grades keyed by harness id."
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg_path = as_path(args.config)
    if not cfg_path.is_file():
        die(f"config not found: {cfg_path}")
    try:
        raw = load_json_file(cfg_path)
        cfg = validate_config(raw)
        selected = select_harnesses(cfg, parse_only(args.only))
    except ConfigError as exc:
        die(str(exc))
        return EXIT_CONFIG
    concurrency = args.concurrency if args.concurrency is not None else cfg["concurrency"]
    if concurrency < 1:
        die("concurrency must be >= 1")
    timeout_s = int(cfg["timeout_min"]) * 60
    output_root: Path = cfg["task"]["output_root"]
    output_root.mkdir(parents=True, exist_ok=True)
    date_s = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_path = as_path(args.report) if args.report else output_root / "bench-report.md"
    html_path = as_path(args.html) if args.html else md_path.with_name("bench-report.html")
    json_path = md_path.with_name("bench-report.json")

    if args.dry_run:
        for h in selected:
            out_dir = harness_output_dir(output_root, h["id"])
            out_dir.mkdir(parents=True, exist_ok=True)
            text = render_task_text(
                note=str(cfg["task"]["note"]),
                style=str(cfg["task"]["style"]),
                output_dir=str(out_dir),
                skill_dir=str(cfg["task"]["skill_dir"]),
                mode=str(cfg["task"]["mode"]),
                harness_id=h["id"],
                extra=cfg["task"].get("extra_instructions") or "",
                index=(
                    str(cfg["task"]["broll_index"])
                    if cfg["task"].get("broll_index")
                    else ""
                ),
            )
            (out_dir / "task.md").write_text(text, encoding="utf-8")
            run_adapter(
                h,
                cwd=cfg["cwd"],
                skill_dir=cfg["task"]["skill_dir"],
                task_text=text,
                task_file=out_dir / "task.md",
                output_dir=out_dir,
                timeout_s=timeout_s,
                dry_run=True,
            )
        return EXIT_OK

    git_lock = threading.Lock()
    baseline = git_porcelain(cfg["cwd"])
    print(f"[bench] git status at start: {len(baseline)} dirty paths", flush=True)
    scores: list[dict] = []
    if args.report_only or len(selected) == 1 or concurrency == 1:
        for h in selected:
            scores.append(
                run_one_harness(
                    h,
                    cfg=cfg,
                    timeout_s=timeout_s,
                    git_lock=git_lock,
                    dry_run=False,
                    report_only=args.report_only,
                )
            )
    else:
        by_id: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futs = {
                pool.submit(
                    run_one_harness,
                    h,
                    cfg=cfg,
                    timeout_s=timeout_s,
                    git_lock=git_lock,
                    dry_run=False,
                    report_only=False,
                ): h["id"]
                for h in selected
            }
            for fut in as_completed(futs):
                hid = futs[fut]
                try:
                    by_id[hid] = fut.result()
                except ConfigError as exc:
                    die(str(exc))
                except Exception as exc:
                    eprint(f"[bench] {hid}: {exc}")
                    by_id[hid] = {
                        "id": hid,
                        "produced_render": False,
                        "skipped": False,
                        "timeout": False,
                        "status": "error",
                        "qa_verdict": None,
                        "qa_fail_ids": [],
                        "qa_warn_ids": [],
                        "qa_fail_details": {},
                        "qa_warn_details": {},
                        "punches": [],
                        "stray_writes": [],
                        "notes": [str(exc)],
                        "preflight_warns": 0,
                        "renders": 0,
                        "dry_runs": 0,
                    }
        scores = [by_id[h["id"]] for h in selected]

    verifier_cmd = getattr(args, "verifier_cmd", None)
    verifier_cfg = cfg.get("verifier")
    if verifier_cmd or verifier_cfg:
        selected_by_id = {h["id"]: h for h in selected}
        for score in scores:
            hid = score.get("id")
            harness = dict(selected_by_id.get(hid) or {})
            for k in ("provider", "model", "kind"):
                if score.get(k) and not harness.get(k):
                    harness[k] = score.get(k)
            out_dir = harness_output_dir(output_root, str(hid))
            verify_one(
                score,
                harness=harness,
                cfg=cfg,
                output_dir=out_dir,
                verifier_cmd=verifier_cmd,
                verifier_cfg=verifier_cfg,
            )

    scores = rank_scores(scores)

    if getattr(args, "grades", None):
        gpath = as_path(args.grades)
        if not gpath.is_file():
            die(f"grades file not found: {gpath}")
        owner = load_json_file(gpath)
        if not isinstance(owner, dict):
            die("grades file must be a JSON object")
        merged = merge_grades(scores, owner)
        merged_path = md_path.with_name("grades-merged.json")
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        merged_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        print(f"[bench] wrote {merged_path}", flush=True)
        for hid, rec in (merged.get("harnesses") or {}).items():
            n = rec.get("graded") or 0
            m = rec.get("matched") or 0
            print(
                f"[bench] verifier agreement {hid}: {m}/{n} ({fmt_cell(rec.get('agreement'))})",
                flush=True,
            )
        print(
            f"[bench] verifier agreement overall: {merged.get('matched')}/{merged.get('graded')} ({fmt_cell(merged.get('overall'))})",
            flush=True,
        )

    write_markdown(
        md_path, cfg=cfg, scores=scores, date_s=date_s, concurrency=concurrency
    )
    write_html(
        html_path, cfg=cfg, scores=scores, date_s=date_s, concurrency=concurrency
    )
    write_json_report(
        json_path, cfg=cfg, scores=scores, date_s=date_s, concurrency=concurrency
    )
    print(f"[bench] wrote {md_path}", flush=True)
    print(f"[bench] wrote {html_path}", flush=True)
    print(f"[bench] wrote {json_path}", flush=True)

    deliver_to = cfg["task"].get("deliver_to")
    if deliver_to:
        copied = deliver_bench_outputs(
            Path(deliver_to), scores=scores, md_path=md_path, html_path=html_path
        )
        print(f"[bench] delivered {len(copied)} files to {deliver_to}", flush=True)

    failed = [s for s in scores if counts_as_failure(s)]
    if failed:
        names = ", ".join(str(s.get("id")) for s in failed)
        eprint(f"[bench] failed harnesses: {names}")
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
