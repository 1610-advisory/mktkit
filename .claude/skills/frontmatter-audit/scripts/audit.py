#!/usr/bin/env python3
"""
Frontmatter audit for a 1610 Marketing Toolkit client folder.

Scans:
  - clients/[client]/knowledge/*.md            -> knowledge schema
  - clients/[client]/outputs/content/*.md      -> content-note schema
  - clients/[client]/outputs/biweekly-briefs/  -> brief schema
  - clients/[client]/outputs/weekly-briefs/    -> brief schema
  - clients/[client]/outputs/monthly-briefs/   -> brief schema

Skips: any path containing /_archive/ or starting with . or _ (segment-level).

Emits a single JSON object on stdout:
{
  "client": str,
  "audited_at": "YYYY-MM-DD",
  "counts": {"scanned": int, "issues": int, "errors": int,
             "warnings": int, "info": int,
             "auto_fixable": int, "manual": int},
  "schema_violations": {
      "knowledge": [...], "content_notes": [...], "briefs": [...]
  },
  "structural_issues": {
      "orphan_files": [...], "broken_brief_refs": [...],
      "broken_wiki_links": [...], "duplicate_content_ids": [...]
  },
  "stale_knowledge": [...],
  "auto_fixes": [
      {"file": str, "changes": [{"key": str, "old": Any, "new": Any}]}
  ],
  "applied_fixes": [...]   # only when --apply-auto-fixes is set
}

Issue object shape:
{
  "file": str (absolute path),
  "field": str | null,
  "expected": str,
  "actual": str,
  "severity": "error" | "warning" | "info",
  "fix": "auto" | "user" | "manual",
  "message": str
}

Read-only by default. Pass --apply-auto-fixes to actually mutate files.
PyYAML is preferred but optional — falls back to a simple line-based parser.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Schema definitions — keep in sync with references/schemas.md
# ---------------------------------------------------------------------------

KNOWLEDGE_REQUIRED = ["title", "description", "category", "last_updated", "status", "priority"]
KNOWLEDGE_ENUMS = {
    "category": {"strategy", "voice", "data", "workflow", "research"},
    "status": {"active", "needs-update", "reference"},
    "priority": {"high", "medium", "low"},
}

CONTENT_NOTE_REQUIRED = ["content_id", "title", "type", "client", "status", "post_date", "platform", "format"]
CONTENT_NOTE_ENUMS = {
    "status": {"concept", "pre-production", "captured", "editing",
               "pre-approval", "approved", "scheduled", "published"},
    "type": {"content-note"},
}

BRIEF_REQUIRED = ["title", "client", "period_start", "period_end", "status"]
BRIEF_ENUMS = {
    "status": {"active", "archived"},
}

DATE_FIELDS_KNOWLEDGE = {"last_updated"}
DATE_FIELDS_CONTENT = {"post_date", "shoot_date"}
DATE_FIELDS_BRIEF = {"period_start", "period_end"}

STALE_THRESHOLD_DAYS = 60

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CONTENT_NOTE_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[A-Za-z0-9]+-\d+-")  # YYYY-MM-DD-PREFIX-NN-

# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block, body). frontmatter_block is None if not present."""
    if not text.startswith("---"):
        return None, text
    # find closing --- on its own line
    lines = text.splitlines(keepends=True)
    if not lines:
        return None, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n").rstrip("\r") == "---":
            end_idx = i
            break
    if end_idx is None:
        return None, text
    frontmatter = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1:])
    return frontmatter, body


def parse_frontmatter(block: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse YAML frontmatter. Returns (data, error_msg). data is None on error."""
    if _HAS_YAML:
        try:
            data = yaml.safe_load(block)
            if data is None:
                return {}, None
            if not isinstance(data, dict):
                return None, f"top-level YAML is {type(data).__name__}, expected mapping"
            return data, None
        except yaml.YAMLError as e:
            return None, f"YAML parse error: {e}"
    # Fallback parser — handles simple key: value and key: [a, b], key: \n  - a \n  - b
    return _simple_yaml(block)


def _simple_yaml(block: str) -> tuple[dict[str, Any] | None, str | None]:
    data: dict[str, Any] = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        # detect indented list item (continuation)
        if line.startswith(" ") or line.startswith("\t"):
            i += 1
            continue
        if ":" not in stripped:
            i += 1
            continue
        key, _, raw_val = stripped.partition(":")
        key = key.strip()
        val = raw_val.strip()
        if val == "":
            # collect indented list items
            items: list[str] = []
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if next_line.strip() == "":
                    j += 1
                    continue
                if next_line.startswith(" ") or next_line.startswith("\t"):
                    s = next_line.strip()
                    if s.startswith("- "):
                        items.append(_strip_quotes(s[2:].strip()))
                    j += 1
                else:
                    break
            data[key] = items
            i = j
            continue
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if inner == "":
                data[key] = []
            else:
                data[key] = [_strip_quotes(p.strip()) for p in inner.split(",")]
            i += 1
            continue
        data[key] = _coerce_scalar(_strip_quotes(val))
        i += 1
    return data, None


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _coerce_scalar(s: str) -> Any:
    if s in ("true", "True", "yes"):
        return True
    if s in ("false", "False", "no"):
        return False
    if re.match(r"^-?\d+$", s):
        try:
            return int(s)
        except ValueError:
            return s
    # date YYYY-MM-DD — leave as string; we'll parse where needed
    return s

# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------

def is_skipped_path(p: Path) -> bool:
    """Skip _archive, hidden dirs, underscore-prefixed dirs."""
    for part in p.parts:
        if part.startswith("."):
            return True
        if part.startswith("_"):
            return True
    return False


def list_markdown(folder: Path) -> list[Path]:
    if not folder.exists() or not folder.is_dir():
        return []
    files: list[Path] = []
    for root, dirs, names in os.walk(folder):
        root_path = Path(root)
        # prune
        dirs[:] = [d for d in dirs if not (d.startswith(".") or d.startswith("_"))]
        for name in names:
            if not name.endswith(".md"):
                continue
            path = root_path / name
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def make_issue(file: Path, field: str | None, expected: str, actual: str,
               severity: str, fix: str, message: str) -> dict[str, Any]:
    return {
        "file": str(file),
        "field": field,
        "expected": expected,
        "actual": actual,
        "severity": severity,
        "fix": fix,
        "message": message,
    }


def parse_date(s: Any) -> date | None:
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def validate_required(data: dict[str, Any], required: list[str], file: Path,
                       fix_inferable: dict[str, Any] | None = None) -> tuple[list[dict], list[dict]]:
    """Return (issues, auto_fixes_for_missing_keys). fix_inferable maps field->value if we can infer one."""
    fix_inferable = fix_inferable or {}
    issues: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    for key in required:
        val = data.get(key)
        missing = (key not in data) or (val is None) or (isinstance(val, str) and val.strip() == "") \
                  or (isinstance(val, list) and len(val) == 0)
        if not missing:
            continue
        if key in fix_inferable:
            fixes.append({"key": key, "old": data.get(key), "new": fix_inferable[key]})
            issues.append(make_issue(file, key, "non-empty", "missing", "warning", "auto",
                                     f"required field `{key}` missing — can be inferred"))
        else:
            issues.append(make_issue(file, key, "non-empty", "missing", "error", "user",
                                     f"required field `{key}` missing — needs user decision"))
    return issues, fixes


def validate_enum(data: dict[str, Any], enums: dict[str, set[str]], file: Path) -> list[dict]:
    issues: list[dict[str, Any]] = []
    for field, allowed in enums.items():
        if field not in data:
            continue
        val = data[field]
        if val is None:
            continue
        if isinstance(val, str) and val.strip() == "":
            continue
        if val not in allowed:
            issues.append(make_issue(
                file, field, "one of: " + ", ".join(sorted(allowed)),
                str(val), "error", "user",
                f"`{field}` has invalid value — must be one of {sorted(allowed)}"
            ))
    return issues


def validate_dates(data: dict[str, Any], date_fields: set[str], file: Path) -> list[dict]:
    issues: list[dict[str, Any]] = []
    for field in date_fields:
        if field not in data:
            continue
        val = data[field]
        if val is None or (isinstance(val, str) and val.strip() == ""):
            continue
        if parse_date(val) is None:
            issues.append(make_issue(
                file, field, "YYYY-MM-DD", str(val), "error", "user",
                f"`{field}` does not parse as YYYY-MM-DD"
            ))
    return issues


# ---------------------------------------------------------------------------
# Per-type audit
# ---------------------------------------------------------------------------

def audit_knowledge_file(file: Path, today: date) -> tuple[list[dict], list[dict], dict | None]:
    """Returns (issues, auto_fix_changes, stale_record_or_none)."""
    text = _safe_read(file)
    if text is None:
        return [make_issue(file, None, "readable file", "io error", "error", "manual",
                           "could not read file")], [], None
    fm, body = split_frontmatter(text)
    if fm is None:
        return [make_issue(file, None, "YAML frontmatter block", "missing", "error", "user",
                           "file has no YAML frontmatter")], [], None
    data, err = parse_frontmatter(fm)
    if err or data is None:
        return [make_issue(file, None, "valid YAML", err or "parse error", "error", "user",
                           f"frontmatter unparseable: {err}")], [], None

    issues: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    # Inferable: last_updated from file mtime
    inferable: dict[str, Any] = {}
    mtime = datetime.fromtimestamp(file.stat().st_mtime).date()
    if "last_updated" not in data or not data.get("last_updated"):
        inferable["last_updated"] = mtime.isoformat()

    req_issues, req_fixes = validate_required(data, KNOWLEDGE_REQUIRED, file, inferable)
    issues.extend(req_issues)
    changes.extend(req_fixes)

    issues.extend(validate_enum(data, KNOWLEDGE_ENUMS, file))
    issues.extend(validate_dates(data, DATE_FIELDS_KNOWLEDGE, file))

    # Stale check — only if data is well-formed enough
    stale = None
    status_val = data.get("status")
    last_updated = parse_date(data.get("last_updated"))
    if status_val == "needs-update" and last_updated is not None:
        days = (today - last_updated).days
        if days > STALE_THRESHOLD_DAYS:
            stale = {"file": str(file), "last_updated": last_updated.isoformat(),
                     "days_old": days, "status": "needs-update"}

    return issues, changes, stale


def audit_content_note_file(file: Path, client_name: str) -> tuple[list[dict], list[dict], str | None, str | None]:
    """Returns (issues, auto_fix_changes, content_id_or_none, brief_ref_or_none)."""
    text = _safe_read(file)
    if text is None:
        return [make_issue(file, None, "readable file", "io error", "error", "manual",
                           "could not read file")], [], None, None
    fm, body = split_frontmatter(text)
    if fm is None:
        return [make_issue(file, None, "YAML frontmatter block", "missing", "error", "user",
                           "file has no YAML frontmatter")], [], None, None
    data, err = parse_frontmatter(fm)
    if err or data is None:
        return [make_issue(file, None, "valid YAML", err or "parse error", "error", "user",
                           f"frontmatter unparseable: {err}")], [], None, None

    issues: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    # Inferables
    inferable: dict[str, Any] = {}
    if not data.get("client"):
        inferable["client"] = client_name
    if not data.get("type"):
        inferable["type"] = "content-note"

    req_issues, req_fixes = validate_required(data, CONTENT_NOTE_REQUIRED, file, inferable)
    issues.extend(req_issues)
    changes.extend(req_fixes)

    issues.extend(validate_enum(data, CONTENT_NOTE_ENUMS, file))
    issues.extend(validate_dates(data, DATE_FIELDS_CONTENT, file))

    # client field mismatch — auto-fixable
    actual_client = data.get("client")
    if actual_client and actual_client != client_name:
        issues.append(make_issue(
            file, "client", client_name, str(actual_client), "warning", "auto",
            f"`client` field doesn't match folder name — should be `{client_name}`"
        ))
        changes.append({"key": "client", "old": actual_client, "new": client_name})

    # type field mismatch — auto-fixable
    actual_type = data.get("type")
    if actual_type and actual_type != "content-note":
        issues.append(make_issue(
            file, "type", "content-note", str(actual_type), "error", "auto",
            f"`type` should be `content-note`, got `{actual_type}`"
        ))
        changes.append({"key": "type", "old": actual_type, "new": "content-note"})

    # platform must be a list
    plat = data.get("platform")
    if plat is not None and not isinstance(plat, list):
        issues.append(make_issue(
            file, "platform", "list of strings", type(plat).__name__,
            "warning", "user", "`platform` should be a YAML list"
        ))

    content_id = data.get("content_id") if isinstance(data.get("content_id"), str) else None

    brief_raw = data.get("brief")
    brief_ref: str | None = None
    if isinstance(brief_raw, str) and brief_raw.strip() and brief_raw.strip() != '""':
        m = WIKI_LINK_RE.search(brief_raw)
        if m:
            brief_ref = m.group(1).strip()
        else:
            # plain string, treat as filename stem
            brief_ref = brief_raw.strip().rstrip(".md")

    return issues, changes, content_id, brief_ref


def audit_brief_file(file: Path, client_name: str) -> tuple[list[dict], list[dict], list[str]]:
    """Returns (issues, auto_fix_changes, content_note_wiki_refs_in_body)."""
    text = _safe_read(file)
    if text is None:
        return [make_issue(file, None, "readable file", "io error", "error", "manual",
                           "could not read file")], [], []
    fm, body = split_frontmatter(text)
    if fm is None:
        return [make_issue(file, None, "YAML frontmatter block", "missing", "error", "user",
                           "file has no YAML frontmatter")], [], []
    data, err = parse_frontmatter(fm)
    if err or data is None:
        return [make_issue(file, None, "valid YAML", err or "parse error", "error", "user",
                           f"frontmatter unparseable: {err}")], [], []

    issues: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []

    inferable: dict[str, Any] = {}
    if not data.get("client"):
        inferable["client"] = client_name

    req_issues, req_fixes = validate_required(data, BRIEF_REQUIRED, file, inferable)
    issues.extend(req_issues)
    changes.extend(req_fixes)

    issues.extend(validate_enum(data, BRIEF_ENUMS, file))
    issues.extend(validate_dates(data, DATE_FIELDS_BRIEF, file))

    # period_end >= period_start
    ps = parse_date(data.get("period_start"))
    pe = parse_date(data.get("period_end"))
    if ps is not None and pe is not None and pe < ps:
        issues.append(make_issue(
            file, "period_end", f">= {ps}", str(pe), "error", "user",
            "`period_end` is before `period_start`"
        ))

    # client mismatch
    actual_client = data.get("client")
    if actual_client and actual_client != client_name:
        issues.append(make_issue(
            file, "client", client_name, str(actual_client), "warning", "auto",
            f"`client` field doesn't match folder name — should be `{client_name}`"
        ))
        changes.append({"key": "client", "old": actual_client, "new": client_name})

    # Find content-note-style wiki-links in the body
    refs: list[str] = []
    for match in WIKI_LINK_RE.finditer(body or ""):
        target = match.group(1).strip()
        # take the part before any | (alias) or # (heading)
        target = target.split("|", 1)[0].split("#", 1)[0].strip()
        if CONTENT_NOTE_NAME_RE.match(target):
            refs.append(target)

    return issues, changes, refs


def _safe_read(file: Path) -> str | None:
    try:
        return file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Structural checks
# ---------------------------------------------------------------------------

def find_orphan_outputs(outputs_dir: Path) -> list[str]:
    """Files at the root of outputs/ that aren't in a subfolder. Hidden files and README allowed."""
    if not outputs_dir.exists():
        return []
    orphans: list[str] = []
    for entry in sorted(outputs_dir.iterdir()):
        if entry.is_dir():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name.lower() in ("readme.md", "index.md"):
            continue
        orphans.append(str(entry))
    return orphans


def find_brief_files(outputs_dir: Path) -> dict[str, Path]:
    """Map basename (without .md) -> Path for every brief file."""
    out: dict[str, Path] = {}
    for sub in ("biweekly-briefs", "weekly-briefs", "monthly-briefs"):
        folder = outputs_dir / sub
        for p in list_markdown(folder):
            if is_skipped_path(p.relative_to(outputs_dir)):
                continue
            out[p.stem] = p
    return out


def find_content_note_files(outputs_dir: Path) -> dict[str, Path]:
    """Map basename (without .md) -> Path for every content note."""
    out: dict[str, Path] = {}
    folder = outputs_dir / "content"
    for p in list_markdown(folder):
        if is_skipped_path(p.relative_to(outputs_dir)):
            continue
        out[p.stem] = p
    return out


# ---------------------------------------------------------------------------
# Auto-fix application
# ---------------------------------------------------------------------------

def apply_auto_fixes(auto_fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply changes to each file's frontmatter. Returns a list of applied-fix records."""
    applied: list[dict[str, Any]] = []
    for entry in auto_fixes:
        file = Path(entry["file"])
        changes = entry["changes"]
        if not changes:
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except OSError as e:
            applied.append({"file": str(file), "error": f"could not read: {e}", "changes": []})
            continue

        fm, body = split_frontmatter(text)
        if fm is None:
            applied.append({"file": str(file), "error": "no frontmatter to edit", "changes": []})
            continue

        new_fm = fm
        applied_changes: list[dict[str, Any]] = []
        for change in changes:
            key = change["key"]
            new_val = change["new"]
            new_fm, did_change = _set_yaml_scalar(new_fm, key, new_val)
            if did_change:
                applied_changes.append(change)

        if not applied_changes:
            continue

        new_text = "---\n" + new_fm
        if not new_fm.endswith("\n"):
            new_text += "\n"
        new_text += "---\n" + body
        try:
            file.write_text(new_text, encoding="utf-8")
            applied.append({"file": str(file), "changes": applied_changes})
        except OSError as e:
            applied.append({"file": str(file), "error": f"could not write: {e}",
                            "changes": []})
    return applied


def _set_yaml_scalar(fm: str, key: str, value: Any) -> tuple[str, bool]:
    """
    Idempotent set of a top-level scalar key in the frontmatter block.
    - If key exists at column 0 with a scalar value, replace its value.
    - If key is missing, append `key: value` at the end.
    - If key exists as a block (list/mapping), refuse — return (fm, False).
    """
    lines = fm.splitlines(keepends=True)
    # Find the scalar key line
    pattern = re.compile(rf"^({re.escape(key)})\s*:\s*(.*?)\s*$")
    val_str = _format_scalar(value)
    for i, line in enumerate(lines):
        stripped_no_nl = line.rstrip("\n").rstrip("\r")
        m = pattern.match(stripped_no_nl)
        if not m:
            continue
        existing = m.group(2).strip()
        if existing == "":
            # block form (list/mapping follows on indented lines) — refuse to mutate
            j = i + 1
            has_block = False
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() == "":
                    j += 1
                    continue
                if nxt.startswith(" ") or nxt.startswith("\t"):
                    has_block = True
                break
            if has_block:
                return fm, False
            # empty scalar; treat as replaceable
        # Replace this whole line
        ending = "\n" if line.endswith("\n") else ""
        lines[i] = f"{key}: {val_str}{ending}"
        return "".join(lines), True

    # Not found — append
    suffix = "" if (fm.endswith("\n") or fm == "") else "\n"
    fm_new = fm + suffix + f"{key}: {val_str}\n"
    return fm_new, True


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return '""'
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Quote if it contains characters that would confuse a YAML scalar reader
    needs_quote = any(c in s for c in [":", "#", "{", "}", "[", "]", ",", "&", "*",
                                        "!", "|", ">", "'", '"', "%", "@", "`"])
    needs_quote = needs_quote or s.strip() != s or s == ""
    if needs_quote:
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="1610 Marketing Toolkit frontmatter audit")
    parser.add_argument("--client-root", required=True,
                        help="Absolute path to clients/[client]/")
    parser.add_argument("--today", default=None,
                        help="Date to use for staleness check (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--apply-auto-fixes", action="store_true",
                        help="Mutate files to apply auto-fixable changes. "
                             "Default is read-only.")
    args = parser.parse_args()

    client_root = Path(args.client_root).resolve()
    if not client_root.exists() or not client_root.is_dir():
        print(f"error: client root does not exist or is not a directory: {client_root}",
              file=sys.stderr)
        return 2
    has_claude_md = (client_root / "CLAUDE.md").exists() or (client_root / ".claude" / "CLAUDE.md").exists()
    if not has_claude_md or not (client_root / "knowledge").exists():
        print(f"error: client root does not look like a toolkit client folder "
              f"(missing CLAUDE.md or knowledge/): {client_root}",
              file=sys.stderr)
        return 2

    client_name = client_root.name
    today = parse_date(args.today) if args.today else date.today()
    if today is None:
        print(f"error: could not parse --today value: {args.today}", file=sys.stderr)
        return 2

    knowledge_dir = client_root / "knowledge"
    outputs_dir = client_root / "outputs"
    content_dir = outputs_dir / "content"

    # Walk files
    knowledge_files = [p for p in list_markdown(knowledge_dir)
                        if not is_skipped_path(p.relative_to(knowledge_dir))]
    content_files = [p for p in list_markdown(content_dir)
                       if not is_skipped_path(p.relative_to(content_dir))] if content_dir.exists() else []
    brief_files: list[Path] = []
    for sub in ("biweekly-briefs", "weekly-briefs", "monthly-briefs"):
        folder = outputs_dir / sub
        for p in list_markdown(folder):
            if not is_skipped_path(p.relative_to(folder)):
                brief_files.append(p)

    # Collect issues
    schema_violations: dict[str, list] = {"knowledge": [], "content_notes": [], "briefs": []}
    auto_fixes_by_file: dict[str, list[dict]] = {}
    stale_records: list[dict] = []
    content_id_map: dict[str, list[str]] = {}
    brief_refs_from_notes: list[tuple[str, str]] = []   # (note_path, brief_basename)
    wiki_refs_from_briefs: list[tuple[str, str]] = []   # (brief_path, target_basename)

    def add_fix(file: Path, change: dict[str, Any]) -> None:
        auto_fixes_by_file.setdefault(str(file), []).append(change)

    # Knowledge
    for kf in knowledge_files:
        issues, fixes, stale = audit_knowledge_file(kf, today)
        schema_violations["knowledge"].extend(issues)
        for f in fixes:
            add_fix(kf, f)
        if stale:
            stale_records.append(stale)

    # Content notes
    for cf in content_files:
        issues, fixes, content_id, brief_ref = audit_content_note_file(cf, client_name)
        schema_violations["content_notes"].extend(issues)
        for f in fixes:
            add_fix(cf, f)
        if content_id:
            content_id_map.setdefault(content_id, []).append(str(cf))
        if brief_ref:
            brief_refs_from_notes.append((str(cf), brief_ref))

    # Briefs
    for bf in brief_files:
        issues, fixes, refs = audit_brief_file(bf, client_name)
        schema_violations["briefs"].extend(issues)
        for f in fixes:
            add_fix(bf, f)
        for r in refs:
            wiki_refs_from_briefs.append((str(bf), r))

    # Structural
    orphans = find_orphan_outputs(outputs_dir)
    brief_index = find_brief_files(outputs_dir)
    note_index = find_content_note_files(outputs_dir)

    broken_brief_refs: list[dict[str, str]] = []
    for note_path, brief_ref in brief_refs_from_notes:
        # normalize: drop .md
        ref_stem = brief_ref[:-3] if brief_ref.endswith(".md") else brief_ref
        if ref_stem not in brief_index:
            broken_brief_refs.append({"file": note_path, "brief_ref": brief_ref})

    broken_wiki_links: list[dict[str, str]] = []
    for brief_path, target in wiki_refs_from_briefs:
        target_stem = target[:-3] if target.endswith(".md") else target
        if target_stem not in note_index:
            broken_wiki_links.append({"file": brief_path, "wiki_link": target})

    duplicate_ids: list[dict[str, Any]] = []
    for cid, files in content_id_map.items():
        if len(files) > 1:
            duplicate_ids.append({"content_id": cid, "files": files})

    # Pack auto_fixes
    auto_fixes_list = [{"file": f, "changes": c} for f, c in sorted(auto_fixes_by_file.items())]

    applied_fixes: list[dict[str, Any]] = []
    if args.apply_auto_fixes:
        applied_fixes = apply_auto_fixes(auto_fixes_list)

    # Counts
    all_issues = (schema_violations["knowledge"]
                   + schema_violations["content_notes"]
                   + schema_violations["briefs"])
    sev_count = {"error": 0, "warning": 0, "info": 0}
    fix_count = {"auto": 0, "user": 0, "manual": 0}
    for it in all_issues:
        sev_count[it["severity"]] = sev_count.get(it["severity"], 0) + 1
        fix_count[it["fix"]] = fix_count.get(it["fix"], 0) + 1

    # Manual = orphans + broken refs + dupes (each is at least one manual cleanup item)
    manual_count = (fix_count["user"] + fix_count["manual"]
                     + len(orphans) + len(broken_brief_refs)
                     + len(broken_wiki_links) + len(duplicate_ids))

    out = {
        "client": client_name,
        "audited_at": today.isoformat(),
        "counts": {
            "scanned": len(knowledge_files) + len(content_files) + len(brief_files),
            "knowledge_files": len(knowledge_files),
            "content_notes": len(content_files),
            "briefs": len(brief_files),
            "issues": len(all_issues),
            "errors": sev_count["error"],
            "warnings": sev_count["warning"],
            "info": sev_count["info"],
            "auto_fixable": fix_count["auto"],
            "manual": manual_count,
        },
        "schema_violations": schema_violations,
        "structural_issues": {
            "orphan_files": orphans,
            "broken_brief_refs": broken_brief_refs,
            "broken_wiki_links": broken_wiki_links,
            "duplicate_content_ids": duplicate_ids,
        },
        "stale_knowledge": stale_records,
        "auto_fixes": auto_fixes_list,
        "applied_fixes": applied_fixes,
        "yaml_parser": "PyYAML" if _HAS_YAML else "fallback (line-based)",
    }
    json.dump(out, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
