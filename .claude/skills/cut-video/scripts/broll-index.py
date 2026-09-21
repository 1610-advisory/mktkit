#!/usr/bin/env python3
"""Build or refresh a JSON index of candidate B-roll stills and clips.

The sourcing ladder this index serves:
  1. Footage and stills from the same job first (the `project` field).
  2. Then a photo library, searched by caption, filename, verified subject,
     and optional CLIP embedding. Video clips are sampled into frames so a
     moment later in the take can still match a spoken line.
  3. When a searcher confirms or rejects a subject, that write-back lives on
     the entry (`descriptions` / `rejects`) and is preserved across --update.
  4. Filename grep alone is not enough. A "hidden door" line must not rank a
     hinged door just because both files contain the word door.
  5. Raw clips only by default. Finished reels, talking A-roll, scraps, and
     files under 1 MB are skipped. Photos are the fallback when no exact clip
     exists.

Exit codes:
  0  success, including --help and --dry-run
  1  usage or processing error
  2  a required input path is missing

--dry-run prints the walk and the output path, then exits 0 without writing
the index, thumbnails, or any other media.
"""
from __future__ import annotations

import argparse
import base64
import csv
import fnmatch
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
SKIP_DIRS = {".work", "Edits"}
RAW_SKIP_DIR_NAMES = frozenset({".work", "Edits", "posted", "Posted"})
MIN_BYTES = 20 * 1024
MIN_VIDEO_BYTES = 1024 * 1024
SHA_BYTES = 1024 * 1024
YMIN_LOG_THRESHOLD = 20.0
DEFAULT_VIDEO_STEP = 3.0
DEFAULT_VIDEO_MAX_FRAMES = 8
CLIP_PRETRAINED = "laion2b_s34b_b79k"
SCHEMA = "broll-index/1.3"
SCHEMA_READ = {
    "broll-index/1", "broll-index/1.1", "broll-index/1.2", "broll-index/1.3",
}
RESPONSIVE_SIZE_TOKENS = frozenset({"320", "640", "1024", "1600", "2048"})
PAGE_EXT = {".mdx", ".md", ".astro", ".html", ".jsx", ".tsx", ".svelte", ".vue"}
SKIP_PAGE_DIRS = SKIP_DIRS | {"node_modules", "dist", ".next", ".git"}
VARIANT_RE = re.compile(r"^(.*)-(\d{3,4})\.(webp|jpe?g|png)$", re.IGNORECASE)
VARIANT_EXTS = (".webp", ".jpg", ".jpeg", ".png")
SIZE_SUFFIX_RE = re.compile(r"-\d{3,4}(\.(?:webp|jpe?g|png))$", re.IGNORECASE)

CAMEL_1 = re.compile(r"([a-z0-9])([A-Z])")
CAMEL_2 = re.compile(r"([A-Z]+)([A-Z][a-z])")
SPLIT_DIGIT_A = re.compile(r"([0-9])([A-Za-z])")
SPLIT_DIGIT_B = re.compile(r"([A-Za-z])([0-9])")
TOKEN_SPLIT = re.compile(r"[-_.\s]+")


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    eprint(msg)
    raise SystemExit(code)


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha1_16(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        h.update(f.read(SHA_BYTES))
    return h.hexdigest()[:16]


def name_tokens(filename: str) -> list[str]:
    """Split a filename on -, _, ., spaces, camelCase. Digits stay as tokens."""
    stem = Path(filename).stem
    s = CAMEL_1.sub(r"\1 \2", stem)
    s = CAMEL_2.sub(r"\1 \2", s)
    s = SPLIT_DIGIT_A.sub(r"\1 \2", s)
    s = SPLIT_DIGIT_B.sub(r"\1 \2", s)
    parts = [p.lower() for p in TOKEN_SPLIT.split(s) if p]
    return parts


def orientation_of(width: int | None, height: int | None) -> str | None:
    if not width or not height:
        return None
    if height > width:
        return "portrait"
    if width > height:
        return "landscape"
    return "square"


def hyphen_tokens(basename: str) -> list[str]:
    stem = Path(basename).stem
    if not stem:
        return []
    return [t for t in stem.split("-") if t != ""]


def strip_trailing_project_noise(tokens: list[str]) -> list[str]:
    """From the right: drop a responsive size token, then a 1-3 digit image number."""
    toks = list(tokens)
    if toks and toks[-1] in RESPONSIVE_SIZE_TOKENS:
        toks.pop()
    if toks and toks[-1].isdigit() and 1 <= len(toks[-1]) <= 3:
        toks.pop()
    return toks


def prefix_project(basename: str, n: int | None) -> str:
    """Project id from a basename after stripping size and image-number tokens.

    n is how many remaining hyphen tokens to keep. None means keep all
    of them (prefix:auto). A leading 4-digit year is a normal token.
    """
    stem = Path(basename).stem
    tokens = strip_trailing_project_noise(hyphen_tokens(basename))
    if not tokens:
        return stem
    if n is None:
        return "-".join(tokens)
    return "-".join(tokens[:n])


def root_is_flat(root: Path, min_files: int = 50) -> bool:
    """True when root has no real subfolders and more than min_files files."""
    n_files = 0
    try:
        for p in root.iterdir():
            name = p.name
            if name.startswith("."):
                continue
            if p.is_dir():
                if name in SKIP_DIRS:
                    continue
                return False
            if p.is_file():
                n_files += 1
    except OSError:
        return False
    return n_files > min_files


def resolve_project_from(spec: str | None, roots: list[Path]) -> str:
    if spec:
        return spec
    if roots and all(root_is_flat(r) for r in roots):
        print("[broll-index] --project-from omitted; flat root(s); using prefix:auto")
        return "prefix:auto"
    return "first"


def default_thumbs_dir(out_path: Path) -> Path:
    name = out_path.name
    if name.lower().endswith(".json"):
        name = name[: -len(".json")]
    if not name:
        name = "index"
    return Path.home() / ".cache" / "reel-factory" / "thumbs" / name


def project_of(rel: str, root: Path, spec: str) -> str:
    parts = Path(rel).parts
    first = parts[0] if len(parts) > 1 else root.name
    if spec in ("", "first"):
        return first
    if spec == "parent":
        parent = Path(rel).parent.name
        return parent or first
    if spec == "grandparent":
        gp = Path(rel).parent.parent.name
        return gp or first
    if spec.startswith("prefix:"):
        raw = spec[len("prefix:") :].strip()
        basename = Path(rel).name
        if raw == "auto":
            return prefix_project(basename, None) or first
        try:
            n = int(raw)
        except ValueError:
            die(
                f"broll-index: bad --project-from '{spec}' "
                "(prefix:N needs an integer or auto)"
            )
        if n < 1:
            die(f"broll-index: bad --project-from '{spec}' (N must be >= 1)")
        return prefix_project(basename, n) or first
    if spec.startswith("regex:"):
        pat = spec[len("regex:") :]
        try:
            cre = re.compile(pat)
        except re.error as exc:
            die(f"broll-index: bad --project-from regex: {exc}")
        basename = Path(rel).name
        m = cre.search(basename)
        if not (m and m.lastindex):
            m = cre.search(rel)
        if m and m.lastindex:
            return m.group(1)
        return first
    die(
        f"broll-index: bad --project-from '{spec}' "
        "(use parent, grandparent, prefix:N, prefix:auto, or regex:PATTERN)"
    )


def exif_dt_to_iso(raw: str) -> str | None:
    raw = raw.strip()
    m = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", raw)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return f"{y}-{mo}-{d}T{h}:{mi}:{s}"
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
    if m:
        return m.group(1)
    return None


def image_size_and_taken(path: Path) -> tuple[int | None, int | None, str | None]:
    try:
        from PIL import Image, ImageOps
    except Exception:
        return probe_wh_ffprobe(path) + (None,)
    try:
        with Image.open(path) as im:
            taken = None
            try:
                exif = im.getexif()
            except Exception:
                exif = None
            if exif:
                val = exif.get(36867) or exif.get(306)
                if not val:
                    try:
                        ifd = exif.get_ifd(0x8769)
                        val = ifd.get(36867) if ifd else None
                    except Exception:
                        val = None
                if val:
                    taken = exif_dt_to_iso(str(val))
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            w, h = im.size
            return int(w), int(h), taken
    except Exception:
        w, h = probe_wh_ffprobe(path)
        return w, h, None


def probe_wh_ffprobe(path: Path) -> tuple[int | None, int | None]:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        return None, None
    parts = r.stdout.strip().split(",")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None, None


def parse_frame_rate(rate) -> float | None:
    if rate is None or rate == "":
        return None
    if isinstance(rate, (int, float)):
        val = float(rate)
        return val if val > 0 else None
    s = str(rate).strip()
    if not s or s in {"0/0", "N/A"}:
        return None
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            den = float(b)
            if den == 0:
                return None
            val = float(a) / den
        except (TypeError, ValueError):
            return None
        return val if val > 0 else None
    try:
        val = float(s)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def parse_rotation(stream: dict) -> float | None:
    if not isinstance(stream, dict):
        return None
    rot = stream.get("rotation")
    if rot is not None:
        try:
            return float(rot)
        except (TypeError, ValueError):
            pass
    tags = stream.get("tags") or {}
    for key in ("rotate", "ROTATE"):
        if tags.get(key) is None:
            continue
        try:
            return float(tags[key])
        except (TypeError, ValueError):
            continue
    return None


def apply_rotation_dims(
    width: int | None, height: int | None, rotation: float | None,
) -> tuple[int | None, int | None]:
    if width is None or height is None or rotation is None:
        return width, height
    deg = abs(rotation) % 360
    if min(abs(deg - 90), abs(deg - 270)) <= 1.0:
        return height, width
    return width, height


def probe_video(
    path: Path,
) -> tuple[int | None, int | None, float | None, str | None, float | None]:
    """Return width, height, duration_s, taken, fps.

    width/height are display size after honoring rotation metadata.
    """
    r = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries",
            "stream=width,height,duration,r_frame_rate,avg_frame_rate,rotation"
            ":stream_tags=rotate:format=duration:format_tags=creation_time",
            str(path),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not r.stdout.strip():
        eprint(f"broll-index: ffprobe failed: {path}")
        return None, None, None, None, None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return None, None, None, None, None
    width = height = None
    duration = None
    fps = None
    rotation = None
    for stream in data.get("streams") or []:
        if stream.get("width") and stream.get("height") and width is None:
            width = int(stream["width"])
            height = int(stream["height"])
            rotation = parse_rotation(stream)
            fps = parse_frame_rate(stream.get("r_frame_rate")) or parse_frame_rate(
                stream.get("avg_frame_rate")
            )
        if stream.get("duration") and duration is None:
            try:
                duration = float(stream["duration"])
            except (TypeError, ValueError):
                pass
    fmt = data.get("format") or {}
    if duration is None and fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
        except (TypeError, ValueError):
            pass
    tags = fmt.get("tags") or {}
    taken = None
    ct = tags.get("creation_time") or tags.get("CREATION_TIME")
    if ct:
        taken = ct.replace("Z", "").split(".")[0]
        if "T" not in taken and " " in taken:
            taken = taken.replace(" ", "T")
        # ffprobe often returns 2024-01-15T12:00:00.000000Z; keep ISO-like
        if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ct.replace("Z", "")):
            taken = ct.replace("Z", "").split(".")[0]
    width, height = apply_rotation_dims(width, height, rotation)
    return width, height, duration, taken, fps


def load_captions(path: Path) -> dict[str, str]:
    """Map lowercase basename -> caption text. JSON object or CSV file,caption."""
    raw = path.read_text(encoding="utf-8-sig")
    stripped = raw.lstrip()
    if path.suffix.lower() == ".json" or stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            die(f"broll-index: captions JSON is not valid: {exc}")
        if not isinstance(data, dict):
            die("broll-index: captions JSON must be an object of filename -> text")
        out = {}
        for k, v in data.items():
            if v is None:
                continue
            out[Path(str(k)).name.lower()] = str(v)
        return out
    out = {}
    reader = csv.DictReader(raw.splitlines())
    if reader.fieldnames is None:
        die("broll-index: captions CSV has no header (need file,caption)")
    key_map = {fn.lower().strip(): fn for fn in reader.fieldnames}
    file_k = key_map.get("file") or key_map.get("filename") or key_map.get("path")
    cap_k = key_map.get("caption") or key_map.get("text")
    if not file_k or not cap_k:
        die("broll-index: captions CSV needs file,caption columns")
    for row in reader:
        name = (row.get(file_k) or "").strip()
        cap = (row.get(cap_k) or "").strip()
        if name and cap:
            out[Path(name).name.lower()] = cap
    return out


def strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1].strip()
    return s


def strip_size_suffix_name(name: str) -> str:
    """photo-640.webp -> photo.webp. Leaves other names alone."""
    m = SIZE_SUFFIX_RE.search(name)
    if not m:
        return name
    return name[: m.start()] + m.group(1)


def basename_key(src: str) -> str | None:
    src = strip_quotes(src or "")
    src = src.split("?")[0].split("#")[0].strip()
    if not src:
        return None
    name = Path(src).name
    if not name or name in (".", ".."):
        return None
    return strip_size_suffix_name(name).lower()


def find_variant_base(path: Path) -> Path | None:
    """If path is name-640.webp and name.<ext> exists beside it, return that file."""
    m = VARIANT_RE.match(path.name)
    if not m:
        return None
    stem_base = m.group(1)
    parent = path.parent
    try:
        self_r = path.resolve()
    except OSError:
        self_r = path
    same_ext = path.suffix.lower()
    ordered = [same_ext] + [e for e in VARIANT_EXTS if e != same_ext]
    for ext in ordered:
        cand = parent / f"{stem_base}{ext}"
        if not cand.is_file():
            continue
        try:
            if cand.resolve() == self_r:
                continue
        except OSError:
            continue
        return cand
    return None


def excluded_by_glob(rel: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in globs)


def filter_variants_and_excludes(
    files: list[tuple[Path, Path, str]],
    keep_variants: bool,
    exclude_globs: list[str],
) -> tuple[list[tuple[Path, Path, str]], dict[str, str], int, int]:
    """Drop --exclude globs and responsive variants. variant_of maps abs path -> base basename."""
    kept: list[tuple[Path, Path, str]] = []
    variant_of: dict[str, str] = {}
    n_exclude = 0
    n_variant_skip = 0
    for path, root, rel in files:
        if exclude_globs and excluded_by_glob(rel, exclude_globs):
            n_exclude += 1
            continue
        base = find_variant_base(path)
        if base is not None:
            try:
                abs_path = str(path.resolve())
            except OSError:
                abs_path = str(path)
            variant_of[abs_path] = base.name
            if not keep_variants:
                n_variant_skip += 1
                continue
        kept.append((path, root, rel))
    return kept, variant_of, n_variant_skip, n_exclude


ATTR_RE = re.compile(
    r"""(?is)(?<!\w)(src|alt|image)\s*=\s*(?:"([^"]*)"|'([^']*)'|\{["']([^"']+)["']\})"""
)
TAG_RE = re.compile(
    r"<([A-Za-z][A-Za-z0-9._-]*)(\s[^>]*?)(/?)>",
    re.DOTALL,
)
MD_IMG_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)(?:\s+[^)]*)?>?\s*\)")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
IMAGE_LINE_RE = re.compile(r"^image\s*:\s*(.+)$")
ALT_LINE_RE = re.compile(r"^(alt|caption)\s*:\s*(.*)$")
TITLE_LINE_RE = re.compile(r"^title\s*:\s*(.*)$")
H1_RE = re.compile(r"^#\s+(.+?)\s*$")


def _tag_attrs(blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in ATTR_RE.finditer(blob):
        key = m.group(1).lower()
        val = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else (m.group(4) or "")
        )
        out[key] = val
    return out


def _looks_like_image(src: str) -> bool:
    key = basename_key(src)
    if not key:
        return False
    return Path(key).suffix.lower() in IMAGE_EXT or Path(key).suffix.lower() in {
        ".gif", ".avif", ".svg",
    }


def page_title_of(text: str) -> str | None:
    m = FRONTMATTER_RE.match(text)
    body = text
    if m:
        for line in m.group(1).splitlines():
            tm = TITLE_LINE_RE.match(line.strip())
            if tm:
                title = strip_quotes(tm.group(1))
                if title:
                    return title
        body = text[m.end() :]
    for line in body.splitlines():
        hm = H1_RE.match(line.rstrip())
        if hm:
            title = hm.group(1).strip()
            if title:
                return title
    return None


class AltHarvest:
    """Map image basename -> longest alt and a page title."""

    def __init__(self) -> None:
        self.alts: dict[str, str] = {}
        self.titles: dict[str, str] = {}
        self.keys: set[str] = set()
        self.files_scanned = 0

    def add(self, src: str, alt: str | None, page_title: str | None) -> None:
        key = basename_key(src)
        if not key:
            return
        self.keys.add(key)
        alt_s = (alt or "").strip()
        title_s = (page_title or "").strip()
        prev = self.alts.get(key, "")
        if len(alt_s) > len(prev):
            self.alts[key] = alt_s
            if title_s:
                self.titles[key] = title_s
        elif title_s and not self.titles.get(key):
            self.titles[key] = title_s

    def lookup(self, filename: str) -> tuple[str | None, str | None]:
        keys = []
        low = filename.lower()
        keys.append(low)
        stripped = strip_size_suffix_name(low)
        if stripped != low:
            keys.append(stripped)
        alt = None
        title = None
        for k in keys:
            if k in self.alts or k in self.titles:
                alt = self.alts.get(k) or None
                title = self.titles.get(k) or None
                break
        return alt, title


def harvest_page_text(text: str, harvest: AltHarvest) -> None:
    title = page_title_of(text)
    for tag, blob, _slash in TAG_RE.findall(text):
        attrs = _tag_attrs(blob)
        src = attrs.get("src") or attrs.get("image")
        if not src:
            continue
        is_img = tag.lower() == "img"
        if not is_img and "alt" not in attrs and not _looks_like_image(src):
            continue
        harvest.add(src, attrs.get("alt"), title)
    for alt, src in MD_IMG_RE.findall(text):
        harvest.add(src, alt, title)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        im = IMAGE_LINE_RE.match(line.strip())
        if not im:
            continue
        src = strip_quotes(im.group(1))
        alt = ""
        for j in range(i + 1, min(i + 4, len(lines))):
            am = ALT_LINE_RE.match(lines[j].strip())
            if am:
                alt = strip_quotes(am.group(2))
                break
        harvest.add(src, alt, title)


def load_captions_from_alt(dirs: list[Path]) -> AltHarvest:
    harvest = AltHarvest()
    for root in dirs:
        root_r = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root_r):
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in SKIP_PAGE_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in PAGE_EXT:
                    continue
                path = Path(dirpath) / name
                harvest.files_scanned += 1
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    eprint(f"broll-index: cannot read page source {path}: {exc}")
                    continue
                harvest_page_text(text, harvest)
    return harvest


def resolve_caption(
    filename: str,
    explicit: dict[str, str],
    harvest: AltHarvest | None,
) -> tuple[str | None, str | None]:
    """Return (caption, page_title). Explicit --captions file wins for caption."""
    keys = []
    low = filename.lower()
    keys.append(low)
    stripped = strip_size_suffix_name(low)
    if stripped != low:
        keys.append(stripped)
    explicit_cap = None
    for k in keys:
        if k in explicit:
            explicit_cap = explicit[k]
            break
    alt = None
    page_title = None
    if harvest is not None:
        for k in keys:
            a, t = harvest.lookup(k)
            if a or t:
                alt = a
                page_title = t
                break
        if alt is None and page_title is None:
            alt, page_title = harvest.lookup(filename)
    caption = explicit_cap if explicit_cap is not None else (alt or page_title)
    return caption, page_title


def walk_media(roots: list[Path]) -> list[tuple[Path, Path, str]]:
    """Return (abs_path, root, rel) for eligible media, sorted by rel."""
    found: list[tuple[Path, Path, str]] = []
    seen: set[str] = set()
    for root in roots:
        root_r = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root_r):
            dirnames[:] = sorted(
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                ext = Path(name).suffix.lower()
                if ext not in IMAGE_EXT and ext not in VIDEO_EXT:
                    continue
                path = Path(dirpath) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    eprint(f"broll-index: cannot stat {path}")
                    continue
                if size < MIN_BYTES:
                    continue
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    rel = path.relative_to(root_r).as_posix()
                except ValueError:
                    rel = name
                found.append((path, root_r, rel))
    found.sort(key=lambda t: (t[2], t[0].as_posix()))
    return found


def write_image_thumb(src: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageOps

        with Image.open(src) as im:
            try:
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            im = im.convert("RGB")
            im.thumbnail((400, 400))
            im.save(dest, "JPEG", quality=85)
        return dest.is_file()
    except Exception:
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(src), "-frames:v", "1",
                "-vf", "scale=400:400:force_original_aspect_ratio=decrease",
                str(dest),
            ],
            capture_output=True, text=True,
        )
        return r.returncode == 0 and dest.is_file()


def write_video_thumb(src: Path, dest: Path, duration_s: float | None) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = max(0.0, (duration_s or 0.0) * 0.4)
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
            str(dest),
        ],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not dest.is_file():
        eprint(f"broll-index: ffmpeg thumb failed: {src}")
        return False
    try:
        from PIL import Image

        with Image.open(dest) as im:
            im = im.convert("RGB")
            im.thumbnail((400, 400))
            im.save(dest, "JPEG", quality=85)
    except Exception:
        pass
    return dest.is_file()


def rel_in_raw_skip_dir(rel: str) -> bool:
    parts = Path(rel).parts
    if len(parts) < 2:
        return False
    return any(p in RAW_SKIP_DIR_NAMES for p in parts[:-1])


def video_skip_reason(
    rel: str, name: str, size: int, include_aroll: bool,
) -> str | None:
    """First matching raw-clip skip rule, or None to keep the file."""
    if rel_in_raw_skip_dir(rel):
        return "path"
    if size < MIN_VIDEO_BYTES:
        return "under-1mb"
    if "RUNNOTES" in name:
        return "runnotes"
    if name.startswith("Scrap-"):
        return "scrap"
    if name.startswith("CP-"):
        return "cp"
    if name.startswith("ARoll-") and not include_aroll:
        return "aroll"
    return None


def filter_raw_clips(
    files: list[tuple[Path, Path, str]],
    include_aroll: bool,
) -> tuple[list[tuple[Path, Path, str]], Counter]:
    """Drop finished reels, talking A-roll, scraps, and tiny video files."""
    counts: Counter = Counter()
    kept: list[tuple[Path, Path, str]] = []
    for path, root, rel in files:
        ext = path.suffix.lower()
        if ext not in VIDEO_EXT:
            kept.append((path, root, rel))
            continue
        try:
            size = path.stat().st_size
        except OSError:
            eprint(f"broll-index: cannot stat {path}")
            continue
        reason = video_skip_reason(rel, path.name, size, include_aroll)
        if reason:
            counts[reason] += 1
            continue
        kept.append((path, root, rel))
    return kept, counts


def print_skip_counts(counts: Counter) -> None:
    print(
        "[broll-index] skipped-by-rule: "
        f"path={counts.get('path', 0)} "
        f"aroll={counts.get('aroll', 0)} "
        f"scrap={counts.get('scrap', 0)} "
        f"cp={counts.get('cp', 0)} "
        f"runnotes={counts.get('runnotes', 0)} "
        f"under-1mb={counts.get('under-1mb', 0)}"
    )


def video_frame_times(
    duration_s: float | None, step: float, max_frames: int,
) -> tuple[list[float], str]:
    """Return (timestamps, fps-filter-or-empty).

    Empty vf means one frame (clips under 1.0 s). Otherwise vf is the fps
    portion of -vf before scale=400:-2.
    """
    if step <= 0:
        step = DEFAULT_VIDEO_STEP
    if max_frames < 1:
        max_frames = 1
    dur = float(duration_s or 0.0)
    if dur < 1.0:
        return [0.0], ""
    if dur > step * max_frames:
        interval = dur / max_frames
        times = [round(i * interval, 3) for i in range(max_frames)]
        rate = max_frames / dur
        return times, f"fps={rate:.10g}"
    times = []
    t = 0.0
    while t < dur - 1e-9 and len(times) < max_frames:
        times.append(round(t, 3))
        t += step
    if not times:
        times = [0.0]
    return times, f"fps={1.0 / step:.10g}"


FRAME_NAME_RE = re.compile(r"^(.+)_f(\d{2})\.jpg$")


def clear_sha_frames(thumbs_dir: Path, sha: str) -> None:
    for old in thumbs_dir.glob(f"{sha}_f*.jpg"):
        if FRAME_NAME_RE.match(old.name):
            try:
                old.unlink()
            except OSError:
                pass


def extract_video_frames(
    src: Path,
    thumbs_dir: Path,
    sha: str,
    duration_s: float | None,
    step: float,
    max_frames: int,
) -> list[dict]:
    """One ffmpeg pass. Do not pass -noautorotate; frames stay upright."""
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    clear_sha_frames(thumbs_dir, sha)
    times, fps_vf = video_frame_times(duration_s, step, max_frames)
    n = max(1, len(times))
    pattern = thumbs_dir / f"{sha}_f%02d.jpg"
    if fps_vf:
        vf = f"{fps_vf},scale=400:-2"
    else:
        vf = "scale=400:-2"
    # Decode keyframes only: sampling one frame every few seconds does not need
    # every frame of a 4K 10-bit clip decoded. On IPB footage this is many times
    # faster; on ALL-I footage it costs nothing. Fall back to a full decode when
    # the keyframe pass yields nothing (odd containers).
    def _run(skip_nonkey: bool) -> subprocess.CompletedProcess:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
        if skip_nonkey:
            cmd += ["-skip_frame", "nokey"]
        cmd += [
            "-i", str(src),
            "-vf", vf,
            "-frames:v", str(n),
            "-q:v", "4",
            str(pattern),
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    def _written() -> list[Path]:
        return sorted(
            p for p in thumbs_dir.glob(f"{sha}_f*.jpg")
            if FRAME_NAME_RE.match(p.name)
        )

    # Fastest path when the duration is known: one input seek per sampled time.
    # ALL-I camera footage makes every frame a keyframe, so a fps= pass still
    # decodes every 4K frame (about 20 s per minute of footage); eight seeks
    # decode eight frames (about 4 s per clip).
    if times and duration_s:
        for i, t in enumerate(times[:n]):
            out = thumbs_dir / f"{sha}_f{i + 1:02d}.jpg"
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{max(0.0, t):.3f}", "-i", str(src),
                 "-frames:v", "1", "-vf", "scale=400:-2", "-q:v", "4", str(out)],
                capture_output=True, text=True,
            )
        written = _written()
        r = subprocess.CompletedProcess(args=[], returncode=0 if written else 1, stdout="", stderr="seek sampling wrote nothing")
    else:
        r = _run(True)
        written = _written()
    if r.returncode != 0 or not written:
        clear_sha_frames(thumbs_dir, sha)
        r = _run(False)
        written = _written()
    if r.returncode != 0 or not written:
        err = (r.stderr or r.stdout or "").strip().splitlines()
        tail = err[-1] if err else f"exit {r.returncode}"
        eprint(f"broll-index: ffmpeg frames failed: {src} ({tail})")
        return []
    frames = []
    for i, path in enumerate(written[:n]):
        t = times[i] if i < len(times) else times[-1]
        frames.append({"t": t, "thumb": str(path.resolve()), "clip": None})
    return frames


def color_hint_of(path: Path, duration_s: float | None) -> str | None:
    """signalstats YMIN on the middle frame. >= 20 is log, else rec709."""
    dur = float(duration_s or 0.0)
    t = 0.0 if dur <= 0 else max(0.0, dur * 0.5)
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
    if not found:
        return None
    try:
        ymin = float(found[-1])
    except ValueError:
        return None
    return "log" if ymin >= YMIN_LOG_THRESHOLD else "rec709"


def l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(float(x) * float(x) for x in vec)) or 1.0
    return [float(x) / n for x in vec]


def mean_l2_normalize(vecs: list[list[float]]) -> list[float] | None:
    if not vecs:
        return None
    dim = len(vecs[0])
    if dim < 1:
        return None
    acc = [0.0] * dim
    n = 0
    for v in vecs:
        if len(v) != dim:
            continue
        for i, x in enumerate(v):
            acc[i] += float(x)
        n += 1
    if n == 0:
        return None
    return l2_normalize([x / n for x in acc])


def closest_frame_index(vecs: list[list[float]], mean: list[float]) -> int:
    best_i = 0
    best_dot = None
    for i, v in enumerate(vecs):
        if len(v) != len(mean):
            continue
        d = sum(float(a) * float(b) for a, b in zip(v, mean))
        if best_dot is None or d > best_dot:
            best_dot = d
            best_i = i
    return best_i


def middle_frame(frames: list[dict], duration_s: float | None) -> dict | None:
    if not frames:
        return None
    mid = float(duration_s or 0.0) / 2.0
    return min(frames, key=lambda fr: abs(float(fr.get("t") or 0.0) - mid))


def cleanup_entry_thumbs(entry: dict, thumbs_dir: Path | None) -> None:
    if thumbs_dir is None:
        return
    thumbs_r = thumbs_dir.resolve()
    paths = []
    if entry.get("thumb"):
        paths.append(entry.get("thumb"))
    for fr in entry.get("frames") or []:
        if isinstance(fr, dict) and fr.get("thumb"):
            paths.append(fr.get("thumb"))
    for raw in paths:
        try:
            p = Path(str(raw))
            resolved = p.resolve()
        except OSError:
            continue
        try:
            if resolved.parent != thumbs_r and thumbs_r not in resolved.parents:
                continue
            if resolved.is_file():
                resolved.unlink()
        except OSError:
            continue


def encode_clip_f16(vec: list[float]) -> str:
    """Little-endian float16 packed as a base64 string. stdlib only."""
    packed = struct.pack(f"<{len(vec)}e", *[float(x) for x in vec])
    return base64.b64encode(packed).decode("ascii")


def decode_clip(
    clip,
    clip_dtype: str | None = None,
    clip_dim: int | None = None,
) -> list[float] | None:
    """Read a clip field stored as a float list or an f16 base64 string."""
    if clip is None or clip == [] or clip == "":
        return None
    if isinstance(clip, list):
        return [float(x) for x in clip]
    if not isinstance(clip, str):
        return None
    dtype = (clip_dtype or "f16").lower()
    if dtype != "f16":
        return None
    try:
        raw = base64.b64decode(clip)
    except Exception:
        return None
    if len(raw) < 2 or len(raw) % 2:
        return None
    n = len(raw) // 2
    if clip_dim is not None and n != int(clip_dim):
        return None
    try:
        return list(struct.unpack(f"<{n}e", raw))
    except Exception:
        return None


def pack_clip(vec: list[float], precision: str) -> tuple[list[float] | str, str, int]:
    dim = len(vec)
    if precision == "list":
        return [round(float(x), 4) for x in vec], "list", dim
    return encode_clip_f16(vec), "f16", dim


class ClipEncoder:
    """Optional open_clip wrapper. Never required."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.ok = False
        self.model = None
        self.preprocess = None
        self.device = "cpu"
        self.label = None
        try:
            import torch
            import open_clip
        except ImportError:
            eprint("broll-index: open_clip/torch not installed; skipping embeddings")
            return
        try:
            device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
            model, _, preprocess = open_clip.create_model_and_transforms(
                model_name, pretrained=CLIP_PRETRAINED, device=device,
            )
            model.eval()
            self.model = model
            self.preprocess = preprocess
            self.device = device
            self.ok = True
            self.label = f"{model_name}/{CLIP_PRETRAINED}"
        except Exception as exc:
            eprint(f"broll-index: CLIP load failed ({exc}); skipping embeddings")

    def embed_image(self, pil_image) -> list[float] | None:
        if not self.ok:
            return None
        try:
            import torch

            tensor = self.preprocess(pil_image.convert("RGB")).unsqueeze(0).to(self.device)
            with torch.no_grad():
                feat = self.model.encode_image(tensor)
                feat = feat / feat.norm(dim=-1, keepdim=True)
            return [float(x) for x in feat.detach().cpu().tolist()[0]]
        except Exception as exc:
            eprint(f"broll-index: CLIP embed failed ({exc})")
            return None


def open_rgb(path: Path):
    try:
        from PIL import Image, ImageOps

        im = Image.open(path)
        try:
            im = ImageOps.exif_transpose(im)
        except Exception:
            pass
        return im.convert("RGB")
    except Exception:
        return None


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def embed_video_frames(
    frames: list[dict],
    clipper: ClipEncoder | None,
    clip_precision: str,
) -> tuple[list[float] | None, str | None]:
    """Embed each sampled frame. Return (mean vector, representative thumb)."""
    if not frames or clipper is None or not clipper.ok:
        return None, None
    embedded: list[tuple[dict, list[float]]] = []
    for fr in frames:
        thumb = fr.get("thumb")
        if not thumb:
            fr["clip"] = None
            continue
        pil = open_rgb(Path(thumb))
        if pil is None:
            fr["clip"] = None
            continue
        vec = clipper.embed_image(pil)
        pil.close()
        if vec is None:
            fr["clip"] = None
            continue
        stored, _dtype, _dim = pack_clip(vec, clip_precision)
        fr["clip"] = stored
        embedded.append((fr, vec))
    if not embedded:
        return None, None
    mean = mean_l2_normalize([v for _fr, v in embedded])
    if mean is None:
        return None, embedded[0][0].get("thumb")
    idx = closest_frame_index([v for _fr, v in embedded], mean)
    thumb = embedded[idx][0].get("thumb")
    return mean, thumb


def build_entry(
    path: Path,
    root: Path,
    rel: str,
    project_from: str,
    caption: str | None,
    page_title: str | None,
    variant_of: str | None,
    thumbs_dir: Path | None,
    clipper: ClipEncoder | None,
    dry: bool,
    clip_precision: str = "f16",
    video_step: float = DEFAULT_VIDEO_STEP,
    video_max_frames: int = DEFAULT_VIDEO_MAX_FRAMES,
) -> dict | None:
    try:
        st = path.stat()
    except OSError:
        eprint(f"broll-index: missing during scan: {path}")
        return None
    ext = path.suffix.lower()
    kind = "video" if ext in VIDEO_EXT else "image"
    width = height = None
    taken = None
    duration_s = None
    fps = None
    color_hint = None
    frames: list[dict] = []
    if kind == "image":
        width, height, taken = image_size_and_taken(path)
    else:
        width, height, duration_s, taken, fps = probe_video(path)
        if not dry:
            color_hint = color_hint_of(path, duration_s)
    sha = sha1_16(path)
    thumb = None
    clip_vec = None
    if not dry and thumbs_dir is not None:
        if kind == "video":
            frames = extract_video_frames(
                path, thumbs_dir, sha, duration_s, video_step, video_max_frames,
            )
        else:
            dest = thumbs_dir / f"{sha}_{path.stem}.jpg"
            if write_image_thumb(path, dest):
                thumb = str(dest.resolve())
    if not dry and clipper is not None and clipper.ok:
        if kind == "image":
            pil = open_rgb(path)
            if pil is not None:
                clip_vec = clipper.embed_image(pil)
                pil.close()
        else:
            clip_vec, mean_thumb = embed_video_frames(frames, clipper, clip_precision)
            if mean_thumb:
                thumb = mean_thumb
    if kind == "video" and not thumb:
        mid = middle_frame(frames, duration_s)
        if mid is not None:
            thumb = mid.get("thumb")
        elif not dry and thumbs_dir is not None:
            dest = thumbs_dir / f"{sha}_{path.stem}.jpg"
            if write_video_thumb(path, dest, duration_s):
                thumb = str(dest.resolve())
    entry = {
        "path": str(path.resolve()),
        "rel": rel,
        "root": str(root),
        "kind": kind,
        "project": project_of(rel, root, project_from),
        "name_tokens": name_tokens(path.name),
        "size": int(st.st_size),
        "mtime": float(st.st_mtime),
        "width": width,
        "height": height,
        "orientation": orientation_of(width, height),
        "taken": taken,
        "duration_s": duration_s,
        "caption": caption,
        "page_title": page_title,
        "variant_of": variant_of,
        "descriptions": [],
        "rejects": [],
        "sha1_16": sha,
        "thumb": thumb,
    }
    if kind == "video":
        entry["fps"] = fps
        entry["color_hint"] = color_hint
        entry["frames"] = frames
    if clip_vec is not None:
        stored, dtype, dim = pack_clip(clip_vec, clip_precision)
        entry["clip"] = stored
        entry["clip_dtype"] = dtype
        entry["clip_dim"] = dim
    return entry


def print_summary(index: dict) -> None:
    entries = index.get("entries") or []
    kinds = Counter(e.get("kind") for e in entries)
    projects = Counter(e.get("project") or "(none)" for e in entries)
    n_cap = sum(1 for e in entries if e.get("caption"))
    n_emb = sum(1 for e in entries if e.get("clip"))
    n_thumb = sum(1 for e in entries if e.get("thumb"))
    print(
        f"[broll-index] entries={len(entries)} images={kinds.get('image', 0)} "
        f"videos={kinds.get('video', 0)} captions={n_cap} embeddings={n_emb} thumbs={n_thumb}"
    )
    if projects:
        top = projects.most_common(15)
        bits = " ".join(f"{k}={v}" for k, v in top)
        print(f"[broll-index] top 15 projects: {bits}")
        n_single = sum(1 for _p, c in projects.items() if c == 1)
        print(f"[broll-index] single-image projects: {n_single}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--root", action="append", type=Path, required=True,
        help="Library or job folder to walk. Repeatable.",
    )
    p.add_argument(
        "--project-from", default=None, metavar="SPEC",
        help="How to set entry.project. When omitted: first path component under "
             "the root, or prefix:auto when every root is flat (more than 50 files "
             "directly under it and no subfolders). Also: parent, grandparent, "
             "prefix:N (first N hyphen tokens of the basename after stripping a "
             "trailing size token 320/640/1024/1600/2048 and a 1-3 digit image "
             "number), prefix:auto (same strip, keep the rest), regex:PATTERN "
             "(first capture group; tried against the basename, then the relative "
             "path).",
    )
    p.add_argument(
        "--captions", type=Path, default=None,
        help="JSON {filename: text} or CSV with file,caption columns. Matched by basename. "
             "Wins over --captions-from-alt when both caption the same file.",
    )
    p.add_argument(
        "--captions-from-alt", action="append", type=Path, default=None, metavar="DIR",
        help="Walk page sources in DIR (.mdx .md .astro .html .jsx .tsx .svelte .vue) "
             "and collect img/markdown/frontmatter alt text plus page titles. Repeatable.",
    )
    p.add_argument(
        "--keep-variants", action="store_true",
        help="Keep responsive size variants (name-640.webp when name.webp exists). "
             "Default is to skip them. Kept variants get variant_of = the base basename.",
    )
    p.add_argument(
        "--exclude", action="append", default=None, metavar="GLOB",
        help="Skip files whose relative path matches this glob (fnmatch). Repeatable.",
    )
    p.add_argument(
        "--include-aroll", action="store_true",
        help="Keep video files whose basename starts with ARoll- (skipped by default).",
    )
    p.add_argument(
        "--video-step", type=float, default=DEFAULT_VIDEO_STEP, metavar="SEC",
        help="Seconds between sampled video frames (default 3.0). Clips longer "
             "than step times max-frames spread frames evenly. Clips under 1.0 s "
             "get one frame.",
    )
    p.add_argument(
        "--video-max-frames", type=int, default=DEFAULT_VIDEO_MAX_FRAMES, metavar="N",
        help="Max frames sampled per video (default 8).",
    )
    p.add_argument("--out", type=Path, default=Path("broll-index.json"))
    p.add_argument(
        "--update", action="store_true",
        help="Keep unchanged size+mtime entries (and their descriptions/rejects "
             "and sampled frames). Re-scan changed or new files. Drop files that "
             "are gone.",
    )
    p.add_argument(
        "--clip", action="store_true",
        help="Embed images and every sampled video frame with open_clip if installed.",
    )
    p.add_argument("--clip-model", default="ViT-B-32")
    p.add_argument(
        "--clip-precision", choices=["list", "f16"], default="f16",
        help="How to store CLIP embeddings. f16 (default) is a base64 little-endian "
             "float16 blob with clip_dtype=f16 and clip_dim on the entry. list is "
             "the legacy JSON array of 512 floats at 4 decimals.",
    )
    p.add_argument(
        "--thumbs", type=Path, default=None,
        help="Write <=400px JPEG thumbs here. When omitted and --clip is set, "
             "defaults to ~/.cache/reel-factory/thumbs/<index basename without .json>/ "
             "and prints the path. Stored on the index as thumbs_dir.",
    )
    p.add_argument("--max-files", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    roots: list[Path] = []
    for r in args.root:
        if not r.exists():
            die(f"broll-index: root not found: {r}", 2)
        if not r.is_dir():
            die(f"broll-index: root is not a directory: {r}", 2)
        roots.append(r.resolve())

    captions: dict[str, str] = {}
    if args.captions is not None:
        if not args.captions.exists():
            die(f"broll-index: captions file not found: {args.captions}", 2)
        captions = load_captions(args.captions)

    harvest: AltHarvest | None = None
    alt_dirs = list(args.captions_from_alt or [])
    if alt_dirs:
        resolved_alt: list[Path] = []
        for d in alt_dirs:
            if not d.exists():
                die(f"broll-index: captions-from-alt dir not found: {d}", 2)
            if not d.is_dir():
                die(f"broll-index: captions-from-alt is not a directory: {d}", 2)
            resolved_alt.append(d.resolve())
        harvest = load_captions_from_alt(resolved_alt)

    files = walk_media(roots)
    files, variant_of_map, n_variant_skip, n_exclude = filter_variants_and_excludes(
        files,
        keep_variants=bool(args.keep_variants),
        exclude_globs=list(args.exclude or []),
    )
    print(f"[broll-index] skipped {n_variant_skip} responsive variants")
    if n_exclude:
        print(f"[broll-index] excluded {n_exclude} files by --exclude")
    files, skip_counts = filter_raw_clips(files, include_aroll=bool(args.include_aroll))
    print_skip_counts(skip_counts)
    if args.max_files is not None:
        files = files[: max(0, args.max_files)]

    old = {"entries": []}
    if args.update and args.out.exists():
        try:
            old = json.loads(args.out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            eprint(f"broll-index: existing index is not valid JSON, rebuilding: {args.out}")
            old = {"entries": []}
        schema = old.get("schema")
        if schema not in SCHEMA_READ and schema is not None:
            eprint(f"broll-index: unrecognized index schema {schema!r}; continuing")
    elif args.update and not args.out.exists():
        eprint(f"broll-index: --update but {args.out} is missing; building fresh")

    old_by_path = {e.get("path"): e for e in old.get("entries") or [] if e.get("path")}
    project_from = resolve_project_from(args.project_from, roots)
    print(f"[broll-index] project-from: {project_from}")
    clipper = None
    clip_model_label = None
    if args.clip and not args.dry_run:
        clipper = ClipEncoder(args.clip_model)
        if clipper.ok:
            clip_model_label = clipper.label

    thumbs_dir = None
    if args.thumbs is not None:
        thumbs_dir = args.thumbs.expanduser().resolve()
    elif args.clip:
        thumbs_dir = default_thumbs_dir(args.out)
        print(f"[broll-index] thumbs default: {thumbs_dir}")
    if thumbs_dir is not None and not args.dry_run:
        thumbs_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"[broll-index] DRY RUN: would index {len(files)} files from {len(roots)} root(s)")
        for path, root, rel in files:
            print(f"  {rel}  ({path})")
        print(f"[broll-index] would write {args.out.resolve()}")
        print(
            f"[broll-index] video-step={args.video_step} "
            f"video-max-frames={args.video_max_frames}"
        )
        if thumbs_dir is not None:
            print(f"[broll-index] would write thumbs under {thumbs_dir}")
        if args.clip:
            print("[broll-index] would attempt CLIP embeddings")
        if harvest is not None:
            print(
                f"[broll-index] captions-from-alt: scanned={harvest.files_scanned} "
                f"images_matched={len(harvest.keys)} entries_captioned=(dry-run)"
            )
        return 0

    entries: list[dict] = []
    n_kept = n_rescanned = n_new = 0
    seen_paths: set[str] = set()

    def caption_fields(path: Path) -> tuple[str | None, str | None, str | None]:
        cap, page_title = resolve_caption(path.name, captions, harvest)
        try:
            abs_p = str(path.resolve())
        except OSError:
            abs_p = str(path)
        vof = variant_of_map.get(abs_p)
        return cap, page_title, vof

    for path, root, rel in files:
        abs_path = str(path.resolve())
        seen_paths.add(abs_path)
        try:
            st = path.stat()
        except OSError:
            eprint(f"broll-index: missing during scan: {path}")
            continue
        cap, page_title, vof = caption_fields(path)
        prev = old_by_path.get(abs_path)
        if (
            args.update
            and prev is not None
            and prev.get("size") == int(st.st_size)
            and abs(float(prev.get("mtime") or 0) - float(st.st_mtime)) < 0.01
        ):
            entry = dict(prev)
            entry["caption"] = cap
            entry["page_title"] = page_title
            entry["variant_of"] = vof
            entries.append(entry)
            n_kept += 1
            continue
        if prev is not None:
            cleanup_entry_thumbs(prev, thumbs_dir)
        entry = build_entry(
            path, root, rel, project_from, cap, page_title, vof,
            thumbs_dir, clipper, dry=False,
            clip_precision=args.clip_precision,
            video_step=float(args.video_step),
            video_max_frames=int(args.video_max_frames),
        )
        if entry is None:
            continue
        if prev is not None:
            entry["descriptions"] = list(prev.get("descriptions") or [])
            entry["rejects"] = list(prev.get("rejects") or [])
            n_rescanned += 1
        else:
            n_new += 1
        entries.append(entry)

    n_dropped = 0
    if args.update:
        dropped_entries = [e for p, e in old_by_path.items() if p not in seen_paths]
        n_dropped = len(dropped_entries)
        for e in dropped_entries:
            cleanup_entry_thumbs(e, thumbs_dir)
        print(
            f"[broll-index] update: kept={n_kept} rescanned={n_rescanned} "
            f"new={n_new} dropped={n_dropped}"
        )

    if clip_model_label is None:
        # Keep a previous model name if unchanged entries still carry vectors.
        if any(e.get("clip") for e in entries):
            clip_model_label = old.get("clip_model")

    index = {
        "schema": SCHEMA,
        "built": iso_now(),
        "roots": [str(r) for r in roots],
        "clip_model": clip_model_label,
        "thumbs_dir": str(thumbs_dir) if thumbs_dir is not None else None,
        "video_step_s": float(args.video_step),
        "video_max_frames": int(args.video_max_frames),
        "entries": entries,
    }
    atomic_write_json(args.out, index)
    print(f"[broll-index] wrote {args.out.resolve()}")
    print_summary(index)
    if harvest is not None:
        n_got = 0
        for e in entries:
            name = Path(e.get("path") or "").name
            alt, title = harvest.lookup(name)
            if e.get("caption") and (alt or title):
                n_got += 1
        print(
            f"[broll-index] captions-from-alt: scanned={harvest.files_scanned} "
            f"images_matched={len(harvest.keys)} entries_captioned={n_got}"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        sys.exit(0)
