#!/usr/bin/env python3
"""Synthetic tests for broll-index.py and broll-search.py.

No pytest required. Run:

    python3 tests/test_broll.py

Uses a temp library of Pillow-drawn stills plus one short testsrc2 clip.
No client names, real paths, or live footage.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw


SCRIPTS = Path(__file__).resolve().parent.parent
INDEX_PY = SCRIPTS / "broll-index.py"
SEARCH_PY = SCRIPTS / "broll-search.py"
PY = sys.executable


def load_mod(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run(script: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        [PY, str(script), *args],
        capture_output=True,
        text=True,
    )
    if check and r.returncode != 0:
        raise AssertionError(
            f"{script.name} exit {r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


def make_still(path: Path, w: int, h: int, color: tuple[int, int, int], seed: int, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGB", (w, h), color)
    dr = ImageDraw.Draw(im)
    rng = random.Random(seed)
    for _ in range(280):
        x1, x2 = sorted((rng.randint(0, w - 1), rng.randint(0, w - 1)))
        y1, y2 = sorted((rng.randint(0, h - 1), rng.randint(0, h - 1)))
        outline = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
        dr.rectangle([x1, y1, x2, y2], outline=outline)
    dr.rectangle([8, 8, w - 8, 64], fill=(0, 0, 0))
    dr.text((16, 20), label, fill=(255, 255, 255))
    suffix = path.suffix.lower()
    if suffix == ".webp":
        im.save(path, "WEBP", quality=92)
    elif suffix == ".png":
        im.save(path, "PNG")
    else:
        im.save(path, "JPEG", quality=92)
    assert path.stat().st_size >= 20 * 1024, f"{path} is under 20 KB"


def ensure_min_bytes(path: Path, min_bytes: int = 1024 * 1024) -> None:
    size = path.stat().st_size
    if size >= min_bytes:
        return
    with path.open("ab") as f:
        f.write(b"\0" * (min_bytes - size))


def make_video(path: Path, duration: float = 3.0, lavfi: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for the synthetic video"
    if lavfi is None:
        lavfi = f"testsrc2=size=540x960:rate=24:duration={duration}"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", lavfi,
        "-t", str(duration), "-an", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:v", "libx264", "-b:v", "6M", "-minrate", "6M", "-maxrate", "6M",
        "-bufsize", "6M",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"ffmpeg failed:\n{r.stderr}")
    assert path.is_file()
    ensure_min_bytes(path)
    assert path.stat().st_size >= 1024 * 1024, path.stat().st_size


def make_color_cut_video(path: Path) -> None:
    """6 s clip that is red for 3 s then blue for 3 s."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for the synthetic video"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=540x960:d=3:r=24",
        "-f", "lavfi", "-i", "color=c=blue:s=540x960:d=3:r=24",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
        "-t", "6", "-an", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:v", "libx264", "-b:v", "6M", "-minrate", "6M", "-maxrate", "6M",
        "-bufsize", "6M",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"ffmpeg color-cut failed:\n{r.stderr}")
    assert path.is_file()
    ensure_min_bytes(path)
    assert path.stat().st_size >= 1024 * 1024, path.stat().st_size


def build_library(root: Path) -> dict[str, Path]:
    files = {
        "pocket": root / "projA" / "08-photos" / "projA_hallway-pocket-door-oak.jpg",
        "kitchen": root / "projA" / "08-photos" / "projA_kitchen-island-finished.jpg",
        "front": root / "projB" / "photos" / "projB_front-door-entry.jpg",
        "framing": root / "projB" / "photos" / "projB_framing-lumber-day.jpg",
        "demo": root / "projA" / "video" / "projA_demo-wall-tearout.mp4",
    }
    make_still(files["pocket"], 800, 1200, (30, 50, 90), 1, "pocket door hallway")
    make_still(files["kitchen"], 800, 1200, (180, 90, 40), 2, "kitchen island")
    make_still(files["front"], 1200, 800, (40, 120, 50), 3, "front entry door")
    make_still(files["framing"], 1200, 800, (90, 90, 90), 4, "framing lumber")
    make_video(files["demo"])
    cap = root / "captions.csv"
    with cap.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "caption"])
        w.writeheader()
        w.writerow(
            {
                "file": "projB_front-door-entry.jpg",
                "caption": "front entry door, hinged, painted",
            }
        )
    files["captions"] = cap
    return files


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def by_name(index: dict, name: str) -> dict:
    hits = [e for e in index["entries"] if Path(e["path"]).name == name]
    assert len(hits) == 1, f"expected 1 entry named {name}, got {len(hits)}"
    return hits[0]


def test_help() -> None:
    idx = run(INDEX_PY, ["--help"])
    assert idx.returncode == 0
    assert "--dry-run" in idx.stdout
    assert "--keep-variants" in idx.stdout
    assert "--exclude" in idx.stdout
    assert "--captions-from-alt" in idx.stdout
    assert "prefix:N" in idx.stdout or "prefix:" in idx.stdout
    assert "prefix:auto" in idx.stdout
    assert "regex:" in idx.stdout
    assert "--clip-precision" in idx.stdout
    assert "f16" in idx.stdout
    assert "--video-step" in idx.stdout
    assert "--video-max-frames" in idx.stdout
    assert "--include-aroll" in idx.stdout
    helptext = " ".join(idx.stdout.split())
    assert "prefix:auto" in helptext
    assert "factory/thumbs" in helptext
    sch = run(SEARCH_PY, ["--help"])
    assert sch.returncode == 0
    assert "--dry-run" in sch.stdout
    assert "--min-score" in sch.stdout
    assert "--prefer-video" in sch.stdout
    assert "--no-prefer-video" in sch.stdout
    assert "--video-bonus" in sch.stdout
    assert "--punch-dur" in sch.stdout
    assert "--min-clip-s" in sch.stdout


def test_index_without_clip(lib: Path, files: dict[str, Path], index_path: Path) -> dict:
    r = run(
        INDEX_PY,
        [
            "--root", str(lib),
            "--captions", str(files["captions"]),
            "--out", str(index_path),
        ],
    )
    assert "open_clip" not in r.stderr.lower() or "skipping" in r.stderr.lower()
    idx = load_json(index_path)
    assert idx["schema"] == "broll-index/1.3"
    assert "thumbs_dir" in idx
    assert "video_step_s" in idx
    assert "video_max_frames" in idx
    assert len(idx["entries"]) == 5, [e["rel"] for e in idx["entries"]]
    pocket = by_name(idx, "projA_hallway-pocket-door-oak.jpg")
    assert pocket["project"] == "projA"
    assert pocket["kind"] == "image"
    assert pocket["orientation"] == "portrait"
    assert "pocket" in pocket["name_tokens"]
    kitchen = by_name(idx, "projA_kitchen-island-finished.jpg")
    assert kitchen["project"] == "projA"
    assert kitchen["orientation"] == "portrait"
    front = by_name(idx, "projB_front-door-entry.jpg")
    assert front["project"] == "projB"
    assert front["orientation"] == "landscape"
    assert front["caption"] == "front entry door, hinged, painted"
    framing = by_name(idx, "projB_framing-lumber-day.jpg")
    assert framing["project"] == "projB"
    demo = by_name(idx, "projA_demo-wall-tearout.mp4")
    assert demo["kind"] == "video"
    assert demo["project"] == "projA"
    assert demo.get("duration_s") is not None and demo["duration_s"] > 2.0
    assert demo.get("fps") is not None and demo["fps"] > 0
    assert demo.get("color_hint") in ("log", "rec709", None)
    return idx


def test_search_hidden_door(index_path: Path, tmp: Path) -> None:
    out = tmp / "hidden.json"
    r = run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "hidden door in a hallway",
            "--json", str(out),
            "--explain",
        ],
    )
    data = load_json(out)
    cands = data["queries"][0]["candidates"]
    assert cands, r.stdout
    top = cands[0]
    assert Path(top["path"]).name == "projA_hallway-pocket-door-oak.jpg", top


def test_prefer_project(index_path: Path, tmp: Path) -> None:
    out = tmp / "prefer.json"
    run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "door",
            "--prefer-project", "projB",
            "--json", str(out),
            "--explain",
        ],
    )
    cands = load_json(out)["queries"][0]["candidates"]
    assert cands
    assert Path(cands[0]["path"]).name == "projB_front-door-entry.jpg", cands[0]
    reasons = " ".join(cands[0].get("reasons") or [])
    assert "prefer-project" in reasons


def test_sheet(index_path: Path, tmp: Path) -> None:
    sheet = tmp / "sheet.jpg"
    run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "door",
            "--sheet", str(sheet),
        ],
    )
    assert sheet.is_file()
    im = Image.open(sheet)
    assert im.format == "JPEG"
    assert im.size[0] <= 1600, im.size


def test_lines_from_manifest(index_path: Path, tmp: Path) -> None:
    man = tmp / "reel.json"
    man.write_text(
        json.dumps(
            {
                "schema": "reel-manifest/1",
                "notes": "project: projA",
                "broll": [
                    {
                        "path": "",
                        "at": 4.0,
                        "line": "hidden door in a hallway",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp / "proposals.json"
    run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--lines-from-manifest", str(man),
            "--json", str(out),
        ],
    )
    data = load_json(out)
    assert data["queries"]
    q = data["queries"][0]
    assert "hidden door" in q["query"]
    assert q["candidates"]
    names = [Path(c["path"]).name for c in q["candidates"]]
    assert "projA_hallway-pocket-door-oak.jpg" in names


def test_reject(index_path: Path, files: dict[str, Path], tmp: Path) -> None:
    run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--reject", str(files["front"]),
            "--subject", "hidden door",
        ],
    )
    out = tmp / "after-reject.json"
    run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "hidden door",
            "--json", str(out),
            "--top", "8",
        ],
    )
    names = [Path(c["path"]).name for c in load_json(out)["queries"][0]["candidates"]]
    assert "projB_front-door-entry.jpg" not in names, names


def test_confirm(index_path: Path, files: dict[str, Path], tmp: Path) -> None:
    r = run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--confirm", str(files["pocket"]),
            "--subject", "hidden pocket door, oak, hallway",
            "--by", "vision-check",
        ],
    )
    assert "confirmed" in r.stdout.lower() or "descriptions=" in r.stdout
    out = tmp / "after-confirm.json"
    r = run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "oak pocket door",
            "--json", str(out),
            "--explain",
        ],
    )
    data = load_json(out)
    cands = data["queries"][0]["candidates"]
    assert cands
    top = cands[0]
    assert Path(top["path"]).name == "projA_hallway-pocket-door-oak.jpg"
    reasons = " ".join(top.get("reasons") or [])
    assert "verified" in reasons.lower(), reasons
    assert any("oak" in x or "pocket" in x or "+2" in x or "+6" in x for x in top["reasons"])
    idx = load_json(index_path)
    pocket = by_name(idx, "projA_hallway-pocket-door-oak.jpg")
    subs = [d["subject"] for d in pocket.get("descriptions") or []]
    assert "hidden pocket door, oak, hallway" in subs


def test_clip_or_fallback(lib: Path, tmp: Path) -> None:
    out = tmp / "clip-index.json"
    thumbs = tmp / "clip-thumbs"
    r = run(
        INDEX_PY,
        [
            "--root", str(lib), "--out", str(out), "--clip",
            "--max-files", "4", "--thumbs", str(thumbs),
        ],
        check=True,
    )
    idx = load_json(out)
    assert len(idx["entries"]) >= 1
    clip_ok = False
    try:
        import open_clip  # noqa: F401
        import torch  # noqa: F401

        clip_ok = True
    except ImportError:
        clip_ok = False
    if clip_ok:
        with_clip = [e for e in idx["entries"] if e.get("clip")]
        assert with_clip, "open_clip imported but no embeddings stored"
        clip0 = with_clip[0]["clip"]
        if isinstance(clip0, str):
            assert with_clip[0].get("clip_dtype") == "f16"
            assert with_clip[0].get("clip_dim") == 512
            idx_mod = load_mod(INDEX_PY, "broll_index_clipcheck")
            decoded = idx_mod.decode_clip(clip0, "f16", 512)
            assert decoded is not None and len(decoded) == 512
        else:
            assert len(clip0) == 512
        assert idx.get("clip_model")
    else:
        combined = (r.stderr + r.stdout).lower()
        assert "open_clip" in combined or "skipping" in combined or "torch" in combined
        for e in idx["entries"]:
            assert "clip" not in e or e.get("clip") in (None, [])


def test_dry_run_writes_nothing(lib: Path, tmp: Path) -> None:
    out = tmp / "dry.json"
    r = run(INDEX_PY, ["--root", str(lib), "--out", str(out), "--dry-run"])
    assert r.returncode == 0
    assert "DRY RUN" in r.stdout
    assert not out.exists()


def test_missing_index_exits_2(tmp: Path) -> None:
    r = run(
        SEARCH_PY,
        ["--index", str(tmp / "nope.json"), "--query", "door"],
        check=False,
    )
    assert r.returncode == 2
    assert "not found" in r.stderr.lower()


def test_responsive_variants(tmp: Path) -> None:
    lib = tmp / "variants"
    make_still(lib / "photo.webp", 800, 1200, (30, 50, 90), 11, "base")
    make_still(lib / "photo-640.webp", 800, 1200, (40, 60, 100), 12, "v640")
    make_still(lib / "photo-1024.webp", 800, 1200, (50, 70, 110), 13, "v1024")
    out = tmp / "var-default.json"
    r = run(INDEX_PY, ["--root", str(lib), "--out", str(out)])
    assert "skipped 2 responsive variants" in r.stdout, r.stdout
    idx = load_json(out)
    names = sorted(Path(e["path"]).name for e in idx["entries"])
    assert names == ["photo.webp"], names
    assert idx["entries"][0].get("variant_of") in (None, "")

    kept = tmp / "var-keep.json"
    r = run(
        INDEX_PY,
        ["--root", str(lib), "--out", str(kept), "--keep-variants"],
    )
    assert "skipped 0 responsive variants" in r.stdout, r.stdout
    idx = load_json(kept)
    by = {Path(e["path"]).name: e for e in idx["entries"]}
    assert set(by) == {"photo.webp", "photo-640.webp", "photo-1024.webp"}
    assert by["photo.webp"].get("variant_of") in (None, "")
    assert by["photo-640.webp"].get("variant_of") == "photo.webp"
    assert by["photo-1024.webp"].get("variant_of") == "photo.webp"


def test_project_from_prefix_and_regex(tmp: Path) -> None:
    lib = tmp / "projfrom"
    make_still(lib / "2024-loft-remodel-02.jpg", 800, 1200, (20, 80, 40), 21, "loft")
    out = tmp / "prefix.json"
    run(
        INDEX_PY,
        ["--root", str(lib), "--out", str(out), "--project-from", "prefix:3"],
    )
    e = load_json(out)["entries"][0]
    assert e["project"] == "2024-loft-remodel", e["project"]

    out2 = tmp / "regex.json"
    run(
        INDEX_PY,
        [
            "--root", str(lib), "--out", str(out2),
            "--project-from", r"regex:^(\d{4}-[a-z]+)",
        ],
    )
    e2 = load_json(out2)["entries"][0]
    assert e2["project"] == "2024-loft", e2["project"]


def test_captions_from_alt(tmp: Path) -> None:
    lib = tmp / "altlib"
    pages = tmp / "pages"
    pages.mkdir(parents=True)
    make_still(lib / "photo.webp", 800, 1200, (30, 50, 90), 31, "photo")
    make_still(lib / "photo2.jpg", 800, 1200, (90, 40, 20), 32, "photo2")
    make_still(lib / "kitchen.jpg", 800, 1200, (180, 90, 40), 33, "kitchen")
    (pages / "hallway.mdx").write_text(
        '---\n'
        "title: Hallway details\n"
        "---\n\n"
        '<img src="/assets/photo.webp" alt="oak pocket door in a hallway" />\n',
        encoding="utf-8",
    )
    (pages / "framing.md").write_text(
        "![framing day](img/photo2.jpg)\n",
        encoding="utf-8",
    )
    (pages / "kitchen.md").write_text(
        "---\n"
        "title: Kitchen remodel\n"
        "image: kitchen.jpg\n"
        "---\n",
        encoding="utf-8",
    )
    out = tmp / "alt-index.json"
    r = run(
        INDEX_PY,
        [
            "--root", str(lib),
            "--captions-from-alt", str(pages),
            "--out", str(out),
        ],
    )
    assert "captions-from-alt:" in r.stdout, r.stdout
    assert "scanned=3" in r.stdout, r.stdout
    idx = load_json(out)
    photo = by_name(idx, "photo.webp")
    assert photo["caption"] == "oak pocket door in a hallway"
    assert photo.get("page_title") == "Hallway details"
    photo2 = by_name(idx, "photo2.jpg")
    assert photo2["caption"] == "framing day"
    kitchen = by_name(idx, "kitchen.jpg")
    assert kitchen["caption"] == "Kitchen remodel"
    assert kitchen.get("page_title") == "Kitchen remodel"

    hits = tmp / "pocket.json"
    r = run(
        SEARCH_PY,
        [
            "--index", str(out),
            "--query", "pocket door",
            "--json", str(hits),
            "--explain",
        ],
    )
    cands = load_json(hits)["queries"][0]["candidates"]
    assert cands, r.stdout
    top = cands[0]
    assert Path(top["path"]).name == "photo.webp", top
    reasons = " ".join(top.get("reasons") or [])
    assert "bm25" in reasons.lower(), top.get("reasons")
    assert top.get("evidence") == "text"


def test_search_honesty(tmp: Path) -> None:
    lib = tmp / "honest"
    make_still(lib / "still-01.jpg", 800, 1200, (10, 10, 10), 41, "n1")
    make_still(lib / "still-02.jpg", 800, 1200, (20, 20, 20), 42, "n2")
    index_path = tmp / "honest-index.json"
    run(INDEX_PY, ["--root", str(lib), "--out", str(index_path)])
    out = tmp / "honest.json"
    r = run(
        SEARCH_PY,
        [
            "--index", str(index_path),
            "--query", "hidden pocket door",
            "--json", str(out),
            "--explain",
        ],
    )
    notice = (
        "no caption, filename, or embedding evidence for this query; "
        "index with --clip or add captions (--captions-from-alt)"
    )
    assert notice in r.stdout, r.stdout
    data = load_json(out)
    cands = data["queries"][0]["candidates"]
    assert cands
    for c in cands:
        assert c.get("evidence") == "none", c
        assert c.get("reasons") == ["no evidence"], c.get("reasons")


PREFIX_CASES = [
    # basename, n (None = auto), expected project
    ("1930-addition-06.jpg", 3, "1930-addition"),
    ("2007-kitchen-04.jpg", 3, "2007-kitchen"),
    ("dahlia-loft-06.jpg", 3, "dahlia-loft"),
    ("1937-kitchen-remodel-12.jpg", 3, "1937-kitchen-remodel"),
    ("blog-og.jpg", 3, "blog-og"),
    ("An1MXtawek8.mp4", 3, "An1MXtawek8"),
    ("1930-addition-06.jpg", None, "1930-addition"),
    ("2007-kitchen-04.jpg", None, "2007-kitchen"),
    ("dahlia-loft-06.jpg", None, "dahlia-loft"),
    ("1937-kitchen-remodel-12.webp", None, "1937-kitchen-remodel"),
    ("blog-og", None, "blog-og"),
    ("An1MXtawek8", None, "An1MXtawek8"),
    ("1930-addition-06-640.webp", 3, "1930-addition"),
    ("1937-kitchen-remodel-12-1024.webp", None, "1937-kitchen-remodel"),
    ("1937-kitchen-remodel-12.jpg", 2, "1937-kitchen"),
]


def test_prefix_table() -> None:
    idx_mod = load_mod(INDEX_PY, "broll_index_prefix")
    for basename, n, expected in PREFIX_CASES:
        got = idx_mod.prefix_project(basename, n)
        assert got == expected, (basename, n, got, expected)
    # A leading 4-digit year is a token, not stripped.
    assert idx_mod.prefix_project("1930-addition-06.jpg", None).startswith("1930-")


def test_prefix_auto_default_flat(tmp: Path) -> None:
    seed = tmp / "seed.jpg"
    make_still(seed, 400, 600, (30, 50, 90), 99, "seed")
    lib = tmp / "flatlib"
    lib.mkdir()
    for i in range(1, 31):
        shutil.copy(seed, lib / f"alpha-room-{i:02d}.jpg")
        shutil.copy(seed, lib / f"beta-hall-{i:02d}.jpg")
    out = tmp / "flat-index.json"
    r = run(INDEX_PY, ["--root", str(lib), "--out", str(out)])
    assert "prefix:auto" in r.stdout, r.stdout
    assert "top 15 projects" in r.stdout, r.stdout
    assert "single-image projects" in r.stdout, r.stdout
    idx = load_json(out)
    assert len(idx["entries"]) == 60
    projects = Counter(e["project"] for e in idx["entries"])
    assert set(projects) == {"alpha-room", "beta-hall"}, set(projects)
    assert projects["alpha-room"] == 30
    assert projects["beta-hall"] == 30
    assert idx["schema"] == "broll-index/1.3"


def _unit_vec(n: int = 512, phase: float = 0.017) -> list[float]:
    raw = [math.sin(i * phase) * 0.5 for i in range(n)]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return [v / norm for v in raw]


def test_clip_f16_roundtrip_and_search(tmp: Path) -> None:
    idx_mod = load_mod(INDEX_PY, "broll_index_f16")
    sch_mod = load_mod(SEARCH_PY, "broll_search_f16")
    vec = _unit_vec(512, 0.017)
    encoded = idx_mod.encode_clip_f16(vec)
    assert isinstance(encoded, str) and len(encoded) > 100
    decoded = idx_mod.decode_clip(encoded, "f16", 512)
    assert decoded is not None and len(decoded) == 512
    err = max(abs(a - b) for a, b in zip(vec, decoded))
    assert err < 1e-3, err
    decoded_s = sch_mod.decode_clip(encoded, "f16", 512)
    assert decoded_s is not None
    assert max(abs(a - b) for a, b in zip(decoded, decoded_s)) == 0.0

    listed = [round(v, 4) for v in vec]
    listed_back = idx_mod.decode_clip(listed, "list", 512)
    assert listed_back is not None
    q = _unit_vec(512, 0.013)
    c_f16 = sch_mod.cosine(decoded, q)
    c_list = sch_mod.cosine(listed_back, q)
    assert abs(c_f16 - c_list) < 1e-3, (c_f16, c_list)

    # 935 of these blobs plus a modest per-entry JSON envelope stay under 2.5 MB.
    envelope = json.dumps({"clip": encoded, "clip_dtype": "f16", "clip_dim": 512})
    assert 935 * (len(envelope) + 500) < int(2.5 * 1024 * 1024)

    lib = tmp / "oldfmt"
    still = lib / "proj-door-oak.jpg"
    make_still(still, 400, 600, (40, 80, 20), 7, "oak door")
    old_index = {
        "schema": "broll-index/1.1",
        "built": "2024-01-01T00:00:00Z",
        "roots": [str(lib.resolve())],
        "clip_model": None,
        "entries": [
            {
                "path": str(still.resolve()),
                "rel": still.name,
                "root": str(lib.resolve()),
                "kind": "image",
                "project": "proj",
                "name_tokens": ["proj", "door", "oak"],
                "size": still.stat().st_size,
                "mtime": still.stat().st_mtime,
                "width": 400,
                "height": 600,
                "orientation": "portrait",
                "taken": None,
                "duration_s": None,
                "caption": "oak pocket door",
                "page_title": None,
                "variant_of": None,
                "descriptions": [],
                "rejects": [],
                "sha1_16": "0" * 16,
                "thumb": None,
                "clip": listed,
            }
        ],
    }
    old_path = tmp / "old-index.json"
    old_path.write_text(json.dumps(old_index, indent=2) + "\n", encoding="utf-8")
    hits = tmp / "old-hits.json"
    r = run(
        SEARCH_PY,
        ["--index", str(old_path), "--query", "oak door", "--json", str(hits)],
    )
    cands = load_json(hits)["queries"][0]["candidates"]
    assert cands, r.stdout
    assert Path(cands[0]["path"]).name == "proj-door-oak.jpg"

    # Same vector stored as f16 is readable by search cosine.
    f16_index = json.loads(old_path.read_text(encoding="utf-8"))
    f16_index["schema"] = "broll-index/1.2"
    f16_index["entries"][0]["clip"] = encoded
    f16_index["entries"][0]["clip_dtype"] = "f16"
    f16_index["entries"][0]["clip_dim"] = 512
    f16_path = tmp / "f16-index.json"
    f16_path.write_text(json.dumps(f16_index, indent=2) + "\n", encoding="utf-8")
    e_list = sch_mod.entry_clip_vector(old_index["entries"][0])
    e_f16 = sch_mod.entry_clip_vector(f16_index["entries"][0])
    assert e_list is not None and e_f16 is not None
    assert abs(sch_mod.cosine(e_list, q) - sch_mod.cosine(e_f16, q)) < 1e-3
    hits2 = tmp / "f16-hits.json"
    run(
        SEARCH_PY,
        ["--index", str(f16_path), "--query", "oak door", "--json", str(hits2)],
    )
    cands2 = load_json(hits2)["queries"][0]["candidates"]
    assert cands2
    assert Path(cands2[0]["path"]).name == "proj-door-oak.jpg"


def test_thumbs_default_dry_run(tmp: Path) -> None:
    lib = tmp / "thumblib"
    make_still(lib / "still.jpg", 400, 600, (10, 20, 30), 3, "s")
    out = tmp / "named-index.json"
    r = run(
        INDEX_PY,
        ["--root", str(lib), "--out", str(out), "--clip", "--dry-run"],
    )
    assert r.returncode == 0
    assert "thumbs default:" in r.stdout, r.stdout
    assert "reel-factory/thumbs/named-index" in r.stdout.replace("\\", "/"), r.stdout
    assert not out.exists()


def test_video_frame_sampling(tmp: Path) -> None:
    lib = tmp / "vlib"
    colorful = lib / "job" / "colorful.mp4"
    cut = lib / "job" / "color-cut.mp4"
    make_video(colorful, duration=6.0)
    make_color_cut_video(cut)
    thumbs = tmp / "vthumbs"
    out = tmp / "v-index.json"
    r = run(
        INDEX_PY,
        [
            "--root", str(lib),
            "--out", str(out),
            "--thumbs", str(thumbs),
            "--video-step", "1.5",
            "--video-max-frames", "4",
        ],
    )
    assert "skipped-by-rule:" in r.stdout, r.stdout
    idx = load_json(out)
    assert idx["schema"] == "broll-index/1.3"
    assert idx.get("video_step_s") == 1.5
    assert idx.get("video_max_frames") == 4
    assert len(idx["entries"]) == 2, [e["rel"] for e in idx["entries"]]
    for e in idx["entries"]:
        assert e["kind"] == "video"
        frames = e.get("frames") or []
        assert len(frames) == 4, (e["rel"], len(frames), frames)
        for fr in frames:
            thumb = Path(fr["thumb"])
            assert thumb.is_file(), thumb
            assert fr.get("clip") is None
            assert "t" in fr
        assert e.get("thumb")
        assert Path(e["thumb"]).is_file()
        assert e.get("duration_s") is not None
        assert abs(float(e["duration_s"]) - 6.0) < 0.5, e["duration_s"]
        assert e.get("fps") is not None and e["fps"] > 0
        # Middle frame is the representative thumb without --clip.
        times = [float(fr["t"]) for fr in frames]
        mid = float(e["duration_s"]) / 2.0
        closest = min(frames, key=lambda fr: abs(float(fr["t"]) - mid))
        assert e["thumb"] == closest["thumb"], (e["thumb"], closest, times)


def test_raw_clip_exclusions(tmp: Path) -> None:
    lib = tmp / "excl"
    keep = lib / "keep-clip.mp4"
    make_video(keep, duration=6.0)
    (lib / "Edits").mkdir(parents=True)
    (lib / "posted").mkdir(parents=True)
    shutil.copy(keep, lib / "Edits" / "hidden.mp4")
    shutil.copy(keep, lib / "posted" / "posted-clip.mp4")
    shutil.copy(keep, lib / "ARoll-x.mp4")
    shutil.copy(keep, lib / "Scrap-x.mp4")
    shutil.copy(keep, lib / "CP-take.mp4")
    shutil.copy(keep, lib / "clip-RUNNOTES.mp4")
    out = tmp / "excl-index.json"
    r = run(INDEX_PY, ["--root", str(lib), "--out", str(out)])
    assert "skipped-by-rule:" in r.stdout, r.stdout
    idx = load_json(out)
    names = sorted(Path(e["path"]).name for e in idx["entries"])
    assert names == ["keep-clip.mp4"], names
    assert "ARoll-x.mp4" not in names
    assert "Scrap-x.mp4" not in names

    kept = tmp / "excl-aroll.json"
    r = run(
        INDEX_PY,
        ["--root", str(lib), "--out", str(kept), "--include-aroll"],
    )
    assert "aroll=0" in r.stdout, r.stdout
    idx2 = load_json(kept)
    names2 = sorted(Path(e["path"]).name for e in idx2["entries"])
    assert "keep-clip.mp4" in names2
    assert "ARoll-x.mp4" in names2
    assert "Scrap-x.mp4" not in names2
    assert "CP-take.mp4" not in names2
    assert "clip-RUNNOTES.mp4" not in names2


def test_frame_scoring_video_bonus() -> None:
    sch = load_mod(SEARCH_PY, "broll_search_wp12")
    dim = 8
    query = [1.0] + [0.0] * (dim - 1)

    def vec(cos: float) -> list[float]:
        rest = math.sqrt(max(0.0, 1.0 - cos * cos))
        return [cos, rest] + [0.0] * (dim - 2)

    video = {
        "path": "/tmp/synth-clip.mp4",
        "rel": "synth-clip.mp4",
        "kind": "video",
        "project": "job",
        "name_tokens": ["synth", "clip"],
        "orientation": "portrait",
        "duration_s": 6.0,
        "color_hint": "rec709",
        "caption": None,
        "descriptions": [],
        "rejects": [],
        "taken": None,
        "thumb": "/tmp/synth-clip.jpg",
        "frames": [
            {"t": 1.5, "thumb": "/tmp/f-far.jpg", "clip": vec(0.20)},
            {"t": 4.5, "thumb": "/tmp/f-near.jpg", "clip": vec(0.80)},
        ],
    }
    photo = {
        "path": "/tmp/synth-still.jpg",
        "rel": "synth-still.jpg",
        "kind": "image",
        "project": "job",
        "name_tokens": ["synth", "still"],
        "orientation": "portrait",
        "duration_s": None,
        "caption": None,
        "descriptions": [],
        "rejects": [],
        "taken": None,
        "thumb": "/tmp/synth-still.jpg",
        "clip": vec(0.85),
    }
    ranked = sch.rank_query(
        [video, photo], "navy canvas",
        prefer_project=None, query_clip=query, top=8,
        prefer_video=True, video_bonus=1.5, punch_dur=2.5,
    )
    assert ranked, ranked
    top = ranked[0]
    assert top["kind"] == "video", top
    assert top["best_t"] == 4.5, top
    assert abs(float(top["src"]) - 3.25) < 1e-6, top
    assert top.get("dur") == 2.5
    assert top.get("duration_s") == 6.0
    assert top.get("color_hint") == "rec709"
    assert top.get("thumb") == "/tmp/f-near.jpg"
    reasons = " ".join(top.get("reasons") or [])
    assert "prefer-video" in reasons, top.get("reasons")
    assert "max-frame" in reasons, top.get("reasons")
    assert Path(ranked[1]["path"]).name == "synth-still.jpg"

    flipped = sch.rank_query(
        [video, photo], "navy canvas",
        prefer_project=None, query_clip=query, top=8,
        prefer_video=False, video_bonus=1.5, punch_dur=2.5,
    )
    assert flipped[0]["kind"] == "image", flipped[0]
    assert Path(flipped[0]["path"]).name == "synth-still.jpg"
    assert flipped[1]["kind"] == "video"
    assert flipped[1]["best_t"] == 4.5
    assert "prefer-video" not in " ".join(flipped[1].get("reasons") or [])

    assert abs(sch.punch_src(4.5, 6.0, 2.5) - 3.25) < 1e-9


def test_update_keeps_frames(tmp: Path) -> None:
    lib = tmp / "upd"
    clip = lib / "keep.mp4"
    make_video(clip, duration=6.0)
    thumbs = tmp / "upd-thumbs"
    out = tmp / "upd-index.json"
    args = [
        "--root", str(lib), "--out", str(out),
        "--thumbs", str(thumbs),
        "--video-step", "1.5", "--video-max-frames", "4",
    ]
    run(INDEX_PY, args)
    first = load_json(out)
    entry = first["entries"][0]
    frames = entry.get("frames") or []
    assert len(frames) == 4
    snapshot = [(fr["t"], fr["thumb"]) for fr in frames]
    thumb_paths = [Path(fr["thumb"]) for fr in frames]
    mtimes = [p.stat().st_mtime for p in thumb_paths]
    r = run(INDEX_PY, [*args, "--update"])
    assert "kept=1" in r.stdout, r.stdout
    second = load_json(out)
    entry2 = second["entries"][0]
    frames2 = entry2.get("frames") or []
    assert [(fr["t"], fr["thumb"]) for fr in frames2] == snapshot
    for p, mt in zip(thumb_paths, mtimes):
        assert p.is_file()
        assert abs(p.stat().st_mtime - mt) < 0.01


def main() -> int:
    test_help()
    test_prefix_table()
    test_frame_scoring_video_bonus()
    with tempfile.TemporaryDirectory(prefix="broll-test-") as raw:
        tmp = Path(raw)
        lib = tmp / "lib"
        files = build_library(lib)
        index_path = tmp / "index.json"
        test_index_without_clip(lib, files, index_path)
        test_search_hidden_door(index_path, tmp)
        test_prefer_project(index_path, tmp)
        test_sheet(index_path, tmp)
        test_lines_from_manifest(index_path, tmp)
        test_reject(index_path, files, tmp)
        test_confirm(index_path, files, tmp)
        test_clip_or_fallback(lib, tmp)
        test_dry_run_writes_nothing(lib, tmp)
        test_missing_index_exits_2(tmp)
        test_responsive_variants(tmp)
        test_project_from_prefix_and_regex(tmp)
        test_captions_from_alt(tmp)
        test_search_honesty(tmp)
        test_prefix_auto_default_flat(tmp)
        test_clip_f16_roundtrip_and_search(tmp)
        test_thumbs_default_dry_run(tmp)
        test_video_frame_sampling(tmp)
        test_raw_clip_exclusions(tmp)
        test_update_keeps_frames(tmp)
    print("all tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
