#!/usr/bin/env python3
"""Compile a footage catalog from a mounted footage volume.

Generic: no client names. The client repo receives catalog JSONL, talking
.txt copies, and a generated content-index.md. Picture and word-level JSON
stay on the volume.

Exit codes:
  0  success, including --dry-run
  1  usage or processing error
  2  no named footage root is mounted

--aroll-prefix PREFIX  extra A-roll filename prefix (repeatable). Extends
                       the default tuple (aroll-, cb-, post-).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}
SKIP_DIR_NAMES = {".work", "edits", "posted", ".git", "__pycache__"}
AROLL_PREFIXES = ("aroll-", "cb-", "post-")
SKIP_VIDEO_PREFIXES = ("scrap-",)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
SHA_BYTES = 1024 * 1024
KINDS = ("aroll", "broll", "photo_edited", "art")

BROLL_INDEX_PY = (
    Path(__file__).resolve().parent.parent.parent
    / "cut-video" / "scripts" / "broll-index.py"
)


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    eprint(msg)
    raise SystemExit(code)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_root(spec: str) -> tuple[str, Path]:
    if "=" in spec:
        name, path = spec.split("=", 1)
    elif ":" in spec and not spec.startswith("/"):
        name, path = spec.split(":", 1)
    else:
        die(f"ingest-footage: --root must be name=path, got {spec!r}")
    name = name.strip()
    path = path.strip()
    if not name or not path:
        die(f"ingest-footage: --root must be name=path, got {spec!r}")
    return name, Path(path)


def sha1_16(path: Path) -> str | None:
    try:
        h = hashlib.sha1()
        with path.open("rb") as f:
            h.update(f.read(SHA_BYTES))
        return h.hexdigest()[:16]
    except OSError:
        return None


def parse_duration(raw: str | None) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def ffprobe_duration(path: Path) -> float | None:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return parse_duration(r.stdout.strip())


def classify_video(name: str, mapping_type: str | None = None) -> str | None:
    if mapping_type:
        t = mapping_type.strip().lower().replace(" ", "").replace("_", "-")
        if t in {"scrap", "skip"}:
            return None
        if t in {"a-roll", "aroll", "cb", "talking"}:
            return "aroll"
        if t in {"b-roll", "broll", "silent", "timelapse", "tl"}:
            return "broll"
    lower = name.lower()
    if lower.startswith(SKIP_VIDEO_PREFIXES):
        return None
    if lower.startswith(AROLL_PREFIXES):
        return "aroll"
    return "broll"


def load_mapping(path: Path) -> dict[str, dict]:
    """Map renamed basename -> {type, duration_s} from a shoot file-mapping.csv."""
    out: dict[str, dict] = {}
    try:
        with path.open(newline="") as f:
            rows = csv.DictReader(f)
            if not rows.fieldnames:
                return out
            for row in rows:
                renamed = (
                    row.get("new_name")
                    or row.get("renamed")
                    or row.get("filename")
                    or ""
                ).strip()
                if not renamed:
                    continue
                kind_src = row.get("type") or row.get("classification") or ""
                duration = parse_duration(
                    row.get("duration_s") or row.get("duration_sec")
                )
                out[Path(renamed).name] = {
                    "type": kind_src,
                    "duration_s": duration,
                }
    except OSError:
        return out
    return out


def shoot_date_from_folder(name: str) -> str | None:
    m = DATE_RE.match(name)
    return m.group(1) if m else None


def is_shoot_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    names = {p.name for p in path.iterdir()} if path.exists() else set()
    return bool(
        names
        & {"Video", "Photos", "Audio", "Art", "file-mapping.csv", "file-mapping.txt"}
    )


def iter_shoots(root: Path) -> list[tuple[str, Path]]:
    shoots: list[tuple[str, Path]] = []
    if not root.is_dir():
        return shoots
    for project in sorted(p for p in root.iterdir() if p.is_dir()):
        if project.name.startswith(".") or project.name.lower() in SKIP_DIR_NAMES:
            continue
        if is_shoot_dir(project):
            shoots.append((project.name, project))
            continue
        for child in sorted(p for p in project.iterdir() if p.is_dir()):
            if child.name.startswith(".") or child.name.lower() in SKIP_DIR_NAMES:
                continue
            if is_shoot_dir(child):
                shoots.append((project.name, child))
    return shoots


def frontmatter_fields(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def load_note_index(notes_dir: Path | None) -> list[tuple[str, str]]:
    """Return (content_id, source_footage) pairs."""
    if notes_dir is None or not notes_dir.is_dir():
        return []
    pairs: list[tuple[str, str]] = []
    for path in notes_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = frontmatter_fields(text)
        cid = fm.get("content_id") or ""
        src = fm.get("source_footage") or ""
        if cid:
            pairs.append((cid, src))
    return pairs


def match_content_id(rel: str, stem: str, notes: list[tuple[str, str]]) -> str:
    for cid, src in notes:
        if not src:
            continue
        if stem and stem in src:
            return cid
        if rel and rel in src.replace(" / ", "/").replace(" ", ""):
            return cid
    return ""


def load_jsonl(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        rel = row.get("rel")
        if rel:
            rows[rel] = row
    return rows


def write_jsonl(path: Path, rows: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(rows[k], ensure_ascii=False, sort_keys=True)
        for k in sorted(rows)
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def generate_content_index(
    catalog: dict[str, dict],
    out: Path,
    roots_used: list[tuple[str, Path]],
    ingested_at: str,
) -> None:
    by_project: dict[str, dict[str, dict]] = {}
    for row in catalog.values():
        project = row.get("project_folder") or "unknown"
        shoot = row.get("shoot_date") or ""
        bucket = by_project.setdefault(project, {})
        stats = bucket.setdefault(
            shoot,
            {"videos": 0, "photo_edited": 0, "art": 0, "transcripts": 0, "social": row.get("social_name") or ""},
        )
        kind = row.get("kind")
        if kind in {"aroll", "broll"}:
            stats["videos"] += 1
        elif kind == "photo_edited":
            stats["photo_edited"] += 1
        elif kind == "art":
            stats["art"] += 1
        if row.get("transcript_repo"):
            stats["transcripts"] += 1

    today = ingested_at[:10]
    lines = [
        "---",
        "title: Content Asset Index",
        "description: Generated from tracking/footage-catalog.jsonl. Do not edit by hand.",
        f"last_updated: {today}",
        "generated: true",
        "---",
        "",
        "# Content Asset Index",
        "",
        f"Generated {ingested_at} by ingest-footage.py from footage-catalog.jsonl.",
        "Do not edit by hand. Re-run ingest after organize-shoot.",
        "",
        "## Storage Locations",
        "",
        "| Label | Path | Last Indexed |",
        "|-------|------|--------------|",
    ]
    for name, path in roots_used:
        lines.append(f"| {name} | {path} | {today} |")
    lines += ["", "## Projects", ""]
    for project in sorted(by_project):
        shoots = by_project[project]
        social = next((s["social"] for s in shoots.values() if s.get("social")), "")
        heading = social or project
        lines.append(f"### {heading}")
        lines.append(f"**Folder:** `{project}`")
        lines.append("")
        lines.append("| Shoot | Videos | Edited photos | Art | Transcripts | Organized |")
        lines.append("|-------|--------|---------------|-----|-------------|-----------|")
        for shoot in sorted(shoots):
            s = shoots[shoot]
            label = shoot or "—"
            lines.append(
                f"| {label} | {s['videos']} | {s['photo_edited']} | {s['art']} | {s['transcripts']} | Yes |"
            )
        lines.append("")
    n = len(catalog)
    lines.append(f"*Catalog rows: {n}*")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def copy_transcript(src: Path, dest: Path, dry_run: bool) -> str | None:
    if not src.exists():
        return None
    if dry_run:
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return str(dest)


def broll_roots_to_pass(index_path: Path, extra: list[Path]) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            for raw in data.get("roots") or []:
                p = Path(raw)
                key = str(p)
                if key not in seen and p.exists():
                    roots.append(p)
                    seen.add(key)
        except (OSError, json.JSONDecodeError):
            pass
    for p in extra:
        key = str(p)
        if key not in seen and p.exists():
            roots.append(p)
            seen.add(key)
    return roots


def run_broll_update(
    index_py: Path,
    index_path: Path,
    roots: list[Path],
    clip: bool,
    dry_run: bool,
) -> None:
    if not index_py.exists():
        eprint(f"ingest-footage: broll-index.py not found at {index_py}; skipping")
        return
    if not roots:
        eprint("ingest-footage: no broll roots still exist; skipping broll update")
        return
    cmd = [sys.executable, str(index_py), "--update", "--out", str(index_path)]
    for r in roots:
        cmd += ["--root", str(r)]
    if clip:
        cmd.append("--clip")
    if dry_run:
        cmd.append("--dry-run")
    eprint("ingest-footage: " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        die(f"ingest-footage: broll-index.py exited {r.returncode}", r.returncode or 1)


def ingest_shoot(
    root: Path,
    project_folder: str,
    shoot_dir: Path,
    social: str,
    notes: list[tuple[str, str]],
    transcripts_out: Path,
    ingested_at: str,
    dry_run: bool,
) -> list[dict]:
    rel_shoot = shoot_dir.relative_to(root).as_posix()
    mapping = load_mapping(shoot_dir / "file-mapping.csv")
    shoot_date = shoot_date_from_folder(shoot_dir.name)
    rows: list[dict] = []

    def add_row(
        path: Path,
        kind: str,
        duration: float | None,
        transcript_src: Path | None,
        word_json: Path | None,
    ) -> None:
        rel = path.relative_to(root).as_posix()
        stem = path.stem
        transcript_repo = None
        if transcript_src is not None and transcript_src.exists():
            dest = transcripts_out / project_folder / shoot_dir.name / f"{stem}.txt"
            copied = copy_transcript(transcript_src, dest, dry_run)
            if copied:
                transcript_repo = str(Path("footage/audio") / project_folder / shoot_dir.name / f"{stem}.txt")
        word_rel = None
        if word_json is not None and word_json.exists():
            word_rel = word_json.relative_to(root).as_posix()
        rows.append({
            "rel": rel,
            "kind": kind,
            "project_folder": project_folder,
            "social_name": social,
            "shoot_date": shoot_date,
            "duration_s": duration,
            "transcript_repo": transcript_repo,
            "word_json_rel": word_rel,
            "content_id": match_content_id(rel, stem, notes),
            "sha1_16": None if dry_run else sha1_16(path),
            "ingested_at": ingested_at,
        })

    video_dir = shoot_dir / "Video"
    audio_dir = shoot_dir / "Audio"
    if video_dir.is_dir():
        for path in sorted(video_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
                continue
            mapped = mapping.get(path.name, {})
            kind = classify_video(path.name, mapped.get("type"))
            if kind is None:
                continue
            duration = mapped.get("duration_s") or ffprobe_duration(path)
            txt = audio_dir / f"{path.stem}.txt"
            js = audio_dir / f"{path.stem}.json"
            add_row(path, kind, duration, txt if kind == "aroll" or txt.exists() else None, js)

    edited = shoot_dir / "Photos" / "_edited"
    if edited.is_dir():
        for path in sorted(edited.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXT:
                add_row(path, "photo_edited", None, None, None)

    art = shoot_dir / "Art"
    if art.is_dir():
        for path in sorted(art.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXT:
                add_row(path, "art", None, None, None)

    return rows


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compile a footage catalog from a mounted footage volume.",
    )
    p.add_argument(
        "--root", action="append", required=True, metavar="NAME=PATH",
        help="Named footage root. Repeatable. First existing root is used for "
             "catalog rel paths; all existing roots are eligible. Example: ssd:/Volumes/SSD-01/Jobs",
    )
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--transcripts-out", type=Path, required=True)
    p.add_argument("--content-index-out", type=Path, required=True)
    p.add_argument(
        "--social-map", type=Path, default=None,
        help="JSON object {project_folder: social_name}. Optional.",
    )
    p.add_argument("--notes-dir", type=Path, default=None)
    p.add_argument("--broll-index", type=Path, default=None)
    p.add_argument("--broll-index-py", type=Path, default=BROLL_INDEX_PY)
    p.add_argument("--skip-broll", action="store_true")
    p.add_argument(
        "--broll-clip", action="store_true",
        help="Pass --clip to broll-index.py. Default is --update only.",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--aroll-prefix", action="append", default=None, metavar="PREFIX",
        help="Extra A-roll filename prefix (case-insensitive). Repeatable. "
             "Extends the default prefixes: aroll-, cb-, post-.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    global AROLL_PREFIXES
    extra = tuple(p.lower() for p in (args.aroll_prefix or []) if p)
    AROLL_PREFIXES = ("aroll-", "cb-", "post-") + extra
    named: list[tuple[str, Path]] = []
    for spec in args.root:
        named.append(parse_root(spec))
    existing = [(n, p) for n, p in named if p.exists() and p.is_dir()]
    if not existing:
        tried = ", ".join(f"{n}={p}" for n, p in named)
        die(f"ingest-footage: no footage root is mounted ({tried})", 2)

    primary_name, primary = existing[0]
    eprint(f"ingest-footage: using root {primary_name}={primary}")

    social_map: dict[str, str] = {}
    if args.social_map is not None:
        if not args.social_map.exists():
            die(f"ingest-footage: social map not found: {args.social_map}", 2)
        social_map = json.loads(args.social_map.read_text(encoding="utf-8"))
        if not isinstance(social_map, dict):
            die("ingest-footage: social map must be a JSON object", 1)

    notes = load_note_index(args.notes_dir)
    ingested_at = utc_now()
    catalog = {} if args.dry_run else load_jsonl(args.catalog)
    if args.dry_run:
        catalog = {}

    n_new = 0
    shoots = iter_shoots(primary)
    eprint(f"ingest-footage: {len(shoots)} shoot folder(s) under {primary_name}")
    for project_folder, shoot_dir in shoots:
        social = social_map.get(project_folder, "")
        rows = ingest_shoot(
            primary, project_folder, shoot_dir, social, notes,
            args.transcripts_out, ingested_at, args.dry_run,
        )
        for row in rows:
            if row["kind"] not in KINDS:
                continue
            catalog[row["rel"]] = row
            n_new += 1
            if args.dry_run:
                eprint(f"  {row['kind']:13} {row['rel']}")

    if args.dry_run:
        eprint(f"ingest-footage: dry-run {n_new} row(s); wrote nothing")
        if args.broll_index and not args.skip_broll:
            roots = broll_roots_to_pass(args.broll_index, [p for _, p in existing])
            run_broll_update(
                args.broll_index_py, args.broll_index, roots,
                args.broll_clip, dry_run=True,
            )
        return 0

    write_jsonl(args.catalog, catalog)
    generate_content_index(catalog, args.content_index_out, existing, ingested_at)
    eprint(
        f"ingest-footage: wrote {len(catalog)} catalog rows → {args.catalog}; "
        f"content-index → {args.content_index_out}"
    )

    if args.broll_index and not args.skip_broll:
        roots = broll_roots_to_pass(args.broll_index, [p for _, p in existing])
        run_broll_update(
            args.broll_index_py, args.broll_index, roots,
            args.broll_clip, dry_run=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
