#!/usr/bin/env python3
"""Build a labelled contact sheet JPEG from stills or video timestamps.

Tiles are scaled to --tile-width keeping aspect. A 28 px dark strip under
each tile holds the label in white. 8 px gutters. The sheet is at most
1600 px wide. Default grid is 4 columns.

Inputs (one of):
  --frames a.jpg,b.jpg,...  [--labels "t=0.0 first,t=1.0 cover"]
  --frames a.jpg b.jpg --labels "#1 x" "#2 y"   (repeated / nargs)
  --video FILE --times 0,1.0,5.2  [--labels ...]
  --video FILE --every 5

--output is an alias of --out. --columns is an alias of --cols.
A label may contain #, spaces, dots, and unicode. When the label
count does not match the frame count, missing labels are filled
with the frame basename and a one-line notice is printed.

Exit codes:
  0  wrote the sheet, or --dry-run / --help
  2  bad inputs or no frames

Pillow TrueType is optional. --font loads a TTF when it works; otherwise
the default bitmap font is used (one-line notice on stderr).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


GUTTER = 8
LABEL_H = 28
MAX_SHEET_W = 1600


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif",
}


def parse_csv(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    out = []
    for part in raw.split(","):
        bit = part.strip().strip('"').strip("'")
        if bit:
            out.append(bit)
    return out


def flatten_append(groups: list[list[str]] | None) -> list[str]:
    """Flatten --frames/--labels action=append + nargs='+' groups.

    Each token may itself be comma-separated. Tokens without a comma
    are kept whole so a label like '#1 x' survives.
    """
    if not groups:
        return []
    out: list[str] = []
    for group in groups:
        for item in group:
            if item is None:
                continue
            s = str(item)
            if "," in s:
                out.extend(parse_csv(s))
            else:
                bit = s.strip()
                if bit:
                    out.append(bit)
    return out


def peel_trailing_images(items: list[str]) -> tuple[list[str], list[str]]:
    """If labels swallowed leftover image paths, split them back out."""
    labels = list(items)
    frames: list[str] = []
    while labels:
        p = Path(labels[-1])
        if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file():
            frames.insert(0, labels.pop())
        else:
            break
    return labels, frames


def pad_labels(labels: list[str], frames: list[Path]) -> list[str]:
    if not frames:
        return list(labels)
    if labels and len(labels) != len(frames):
        eprint(
            f"notice: label count {len(labels)} != frame count {len(frames)}; "
            "padding with basenames"
        )
    out = list(labels)
    while len(out) < len(frames):
        out.append(frames[len(out)].name)
    if len(out) > len(frames):
        out = out[: len(frames)]
    return out


def parse_times(raw: str) -> list[float]:
    times = []
    for bit in parse_csv(raw):
        try:
            times.append(float(bit))
        except ValueError:
            raise argparse.ArgumentTypeError(f"bad time '{bit}'") from None
    return times


def load_font(font_path: Path | None, size: int):
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    if font_path is not None:
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            eprint("notice: TrueType font failed, using bitmap font")
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def scale_vf(max_px: int) -> str:
    """Longest side <= max_px, even dimensions."""
    return (
        f"scale='if(gte(iw,ih),min(iw,{max_px}),-2)':"
        f"'if(gt(ih,iw),min(ih,{max_px}),-2)'"
    )


def probe_duration(video: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        eprint(f"ERROR: ffprobe failed on {video}")
        raise SystemExit(2)
    try:
        return float(r.stdout.strip())
    except ValueError:
        eprint(f"ERROR: could not read duration from {video}")
        raise SystemExit(2)


def extract_frame(video: Path, t: float, dest: Path, max_px: int, dry: bool) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(video),
        "-frames:v", "1",
        "-vf", scale_vf(max_px),
        "-q:v", "4",
        str(dest),
    ]
    pretty = " ".join(cmd)
    print(f"[contact-sheet] {'DRY ' if dry else ''}{pretty}")
    if dry:
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        err = (r.stderr or "").strip().splitlines()
        tail = err[-1] if err else "ffmpeg produced no frame"
        eprint(f"ERROR: frame at t={t:.3f}s: {tail}")
        raise SystemExit(2)


def fit_text(draw, text: str, font, max_w: int) -> str:
    if font is None:
        return text
    try:
        width_of = lambda s: draw.textlength(s, font=font)
    except Exception:
        width_of = lambda s: len(s) * 6
    if width_of(text) <= max_w:
        return text
    ell = "..."
    while text and width_of(text + ell) > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


def build_sheet(
    frames: list[Path],
    labels: list[str],
    out: Path,
    cols: int,
    tile_width: int,
    quality: int,
    font_path: Path | None,
    dry: bool,
) -> tuple[int, int]:
    n = len(frames)
    if n == 0:
        eprint("ERROR: no frames")
        raise SystemExit(2)
    cols = max(1, min(cols, n))
    tile_w = tile_width
    total_w = cols * tile_w + (cols - 1) * GUTTER
    if total_w > MAX_SHEET_W:
        tile_w = max(1, (MAX_SHEET_W - (cols - 1) * GUTTER) // cols)
        total_w = cols * tile_w + (cols - 1) * GUTTER

    if dry:
        print(f"[contact-sheet] DRY would write {out} from {n} tiles, cols={cols}")
        print(str(out))
        return total_w, 0

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        eprint("ERROR: Pillow is required for contact-sheet.py")
        raise SystemExit(2)

    font = load_font(font_path, 14)
    images = []
    heights = []
    for path in frames:
        try:
            im = Image.open(path).convert("RGB")
        except Exception as exc:
            eprint(f"ERROR: cannot read frame {path}: {exc}")
            raise SystemExit(2)
        w, h = im.size
        if w <= 0 or h <= 0:
            eprint(f"ERROR: empty frame {path}")
            raise SystemExit(2)
        new_h = max(1, round(h * (tile_w / w)))
        im = im.resize((tile_w, new_h), Image.Resampling.LANCZOS)
        images.append(im)
        heights.append(new_h)

    rows = (n + cols - 1) // cols
    row_h = []
    for r in range(rows):
        chunk = heights[r * cols : r * cols + cols]
        row_h.append(max(chunk) if chunk else 0)
    sheet_h = sum(h + LABEL_H for h in row_h) + (rows - 1) * GUTTER
    sheet_w = total_w

    canvas = Image.new("RGB", (sheet_w, sheet_h), (12, 12, 12))
    draw = ImageDraw.Draw(canvas)
    for i, im in enumerate(images):
        r, c = divmod(i, cols)
        x = c * (tile_w + GUTTER)
        y = sum(h + LABEL_H + GUTTER for h in row_h[:r])
        tile_h = heights[i]
        canvas.paste(im, (x, y))
        strip_y = y + tile_h
        # If this tile is shorter than the row, the strip sits under the tile
        # and the leftover is the dark canvas.
        draw.rectangle([x, strip_y, x + tile_w, strip_y + LABEL_H], fill=(24, 24, 24))
        label = labels[i] if i < len(labels) else f"t={i}"
        label = fit_text(draw, label, font, tile_w - 8)
        try:
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            ty_off = bbox[1]
        except Exception:
            tw, th, ty_off = len(label) * 6, 10, 0
        tx = x + 4
        ty = strip_y + max(0, (LABEL_H - th) // 2) - ty_off
        draw.text((tx, ty), label, fill=(255, 255, 255), font=font)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="JPEG", quality=quality, optimize=True)
    return sheet_w, sheet_h


def times_every(duration: float, every: float) -> list[float]:
    if every <= 0:
        eprint("ERROR: --every must be > 0")
        raise SystemExit(2)
    times = [0.0]
    t = every
    last = max(0.0, duration - 0.05)
    while t < last - 0.01:
        times.append(t)
        t += every
    if last - times[-1] > 0.05:
        times.append(last)
    return times


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Build a labelled contact sheet JPEG from stills or video timestamps. "
            "At most 1600 px wide, 4 columns, 28 px label strip under each tile."
        )
    )
    p.add_argument(
        "--out",
        "--output",
        dest="out",
        type=Path,
        required=True,
        help="Output JPEG path (alias: --output)",
    )
    p.add_argument(
        "--frames",
        action="append",
        nargs="+",
        default=None,
        help=(
            "Image paths. Comma-separated (--frames a.jpg,b.jpg) or "
            "repeated (--frames a.jpg b.jpg). Mix either form."
        ),
    )
    p.add_argument(
        "--labels",
        action="append",
        nargs="+",
        default=None,
        help=(
            "Labels, same order as frames or times. Comma-joined or "
            "repeated. A label may contain #, spaces, dots, unicode."
        ),
    )
    p.add_argument("--video", type=Path, help="Source video (with --times or --every)")
    p.add_argument("--times", default="", help="Comma-separated timestamps in seconds")
    p.add_argument("--every", type=float, help="Sample every N seconds plus first and last")
    p.add_argument(
        "--cols",
        "--columns",
        dest="cols",
        type=int,
        default=4,
        help="Grid columns (default 4, alias: --columns)",
    )
    p.add_argument(
        "positional_frames",
        nargs="*",
        default=[],
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--max-px",
        type=int,
        default=540,
        help="Longest side of extracted video frames (default 540)",
    )
    p.add_argument("--tile-width", type=int, default=400, help="Tile width in px (default 400)")
    p.add_argument("--quality", type=int, default=85, help="JPEG quality (default 85)")
    p.add_argument("--font", type=Path, help="Optional TrueType font for labels")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run and exit 0 without writing media",
    )
    args = p.parse_args(argv)

    if args.cols < 1:
        eprint("ERROR: --cols must be >= 1")
        return 2
    if args.tile_width < 1:
        eprint("ERROR: --tile-width must be >= 1")
        return 2

    frame_paths = [Path(x) for x in flatten_append(args.frames)]
    labels = flatten_append(args.labels)
    if not frame_paths and args.positional_frames:
        extra = [Path(x) for x in args.positional_frames]
        frame_paths.extend(extra)
    elif labels and not frame_paths and args.video is None:
        peeled_labels, peeled_frames = peel_trailing_images(labels)
        if peeled_frames:
            labels = peeled_labels
            frame_paths = [Path(x) for x in peeled_frames]
    times: list[float] = []
    if args.times:
        try:
            times = parse_times(args.times)
        except argparse.ArgumentTypeError as exc:
            eprint(f"ERROR: {exc}")
            return 2

    if frame_paths and args.video:
        eprint("ERROR: pass --frames or --video, not both")
        return 2
    if not frame_paths and args.video is None:
        eprint("ERROR: no frames (need --frames or --video)")
        return 2

    tmp: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.video is not None:
            if not args.video.exists():
                eprint(f"ERROR: video not found: {args.video}")
                return 2
            if not times and args.every is None:
                eprint("ERROR: --video requires --times or --every")
                return 2
            if not times:
                duration = probe_duration(args.video)
                times = times_every(duration, args.every)
            if not times:
                eprint("ERROR: no frames")
                return 2
            if not labels:
                labels = [f"t={t:.1f}s" for t in times]
            tmp = tempfile.TemporaryDirectory(prefix="contact-sheet-")
            work = Path(tmp.name)
            for i, t in enumerate(times):
                dest = work / f"{i:02d}_{t:.3f}.jpg"
                extract_frame(args.video, t, dest, args.max_px, args.dry_run)
                frame_paths.append(dest)
            if args.dry_run:
                print(f"[contact-sheet] DRY {args.out}")
                print(str(args.out))
                return 0
        else:
            missing = [str(p) for p in frame_paths if not p.exists()]
            if missing:
                eprint(f"ERROR: frame not found: {missing[0]}")
                return 2
            if not labels:
                labels = [p.stem for p in frame_paths]

        if not frame_paths:
            eprint("ERROR: no frames")
            return 2

        labels = pad_labels(labels, frame_paths)

        w, h = build_sheet(
            frame_paths,
            labels,
            args.out,
            cols=args.cols,
            tile_width=args.tile_width,
            quality=args.quality,
            font_path=args.font,
            dry=args.dry_run,
        )
        if args.dry_run:
            return 0
        print(f"{args.out} {w}x{h}")
        return 0
    finally:
        if tmp is not None:
            tmp.cleanup()


if __name__ == "__main__":
    sys.exit(main())
