#!/usr/bin/env python3
"""stills-to-broll.py — turn a still photo into a short 9:16 motion clip for
finish-reel.py --broll punch-ins.

Why: KB / archive photography is the most topical B-roll we own, but the
finish engine wants moving video. This makes a slow push (or pull) clip from
one image, cropped to 9:16 around a focus point, at the delivery frame size.

Usage:
  stills-to-broll.py --image IN.jpg --output OUT.mp4 [--dur 3.5] [--fps 30]
      [--width 1080 --height 1920] [--zoom 1.10] [--direction in|out]
      [--focus 0.5,0.45] [--eq contrast=1.05:saturation=1.12:brightness=0.01]
      [--engine pil|zoompan] [--no-autorotate] [--dry-run]

Motion engine:
- `pil` (default when Pillow is installed): every frame is a fresh sub-pixel
  affine resample of the source window, so the push is continuous. Measured
  frame-to-frame motion is flat.
- `zoompan`: ffmpeg's zoompan. It places its window on whole pixels, so a slow
  push steps (alternating fast/slow frames, a stall every few frames). Kept as
  the fallback when Pillow is missing.

Notes:
- EXIF orientation is honored (PIL when present, else macOS sips fallback).
- Crop is 9:16 around --focus (fractions of width/height, default centre,
  slightly high because faces and work sit above centre in most site photos).
- Output has no audio stream; finish-reel only uses B-roll video.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def run(cmd: list[str], dry: bool) -> None:
    print("[stills-to-broll] " + " ".join(str(c) for c in cmd))
    if dry:
        return
    subprocess.run(cmd, check=True)


def have_pil() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def exif_upright(src: Path, work: Path) -> Path:
    """Return a path to an upright copy of src (EXIF orientation applied)."""
    try:
        from PIL import Image, ImageOps  # type: ignore

        im = Image.open(src)
        im = ImageOps.exif_transpose(im)
        out = work / (src.stem + "_upright.png")
        im.convert("RGB").save(out, format="PNG", compress_level=1)
        return out
    except Exception:  # PIL missing or unreadable EXIF: try sips (macOS)
        if shutil.which("sips"):
            out = work / (src.stem + "_upright.jpg")
            subprocess.run(
                ["sips", "-s", "format", "jpeg", str(src), "--out", str(out)],
                check=True, capture_output=True,
            )
            return out
        return src


def probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip().split(",")
    return int(out[0]), int(out[1])


def crop_916(w: int, h: int, fx: float, fy: float) -> tuple[int, int, int, int]:
    """Largest 9:16 window inside w x h centred on (fx, fy) fractions."""
    if w * 16 > h * 9:  # too wide: full height, crop width
        ch = h
        cw = (h * 9) // 16
    else:               # too tall: full width, crop height
        cw = w
        ch = (w * 16) // 9
    cw -= cw % 2
    ch -= ch % 2
    x = int(fx * w - cw / 2)
    y = int(fy * h - ch / 2)
    x = max(0, min(x, w - cw))
    y = max(0, min(y, h - ch))
    return cw, ch, x, y


def encode_cmd(a: argparse.Namespace, raw_input: bool) -> list[str]:
    cmd = ["ffmpeg", "-y" if a.force else "-n", "-hide_banner", "-loglevel", "error"]
    if raw_input:
        cmd += [
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{a.width}x{a.height}",
            "-r", str(a.fps), "-i", "-",
        ]
    return cmd


def render_pil(a: argparse.Namespace, src: Path, cw: int, ch: int, x: int, y: int, frames: int, zmax: float) -> None:
    """Sub-pixel push: each frame is an affine resample of a fractional window."""
    from PIL import Image  # type: ignore

    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(src).convert("RGB").crop((x, y, x + cw, y + ch))
    # Work from a 2x-output copy: enough detail for a 10 percent push, fast to sample.
    ww, hh = a.width * 2, a.height * 2
    if im.width > ww:
        im = im.resize((ww, hh), Image.LANCZOS)
    W, H = im.size
    vf = []
    if a.eq:
        vf.append(f"eq={a.eq}")
    vf.append("format=yuv420p")
    cmd = encode_cmd(a, raw_input=True) + [
        "-vf", ",".join(vf),
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(a.crf),
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
        str(a.output),
    ]
    print("[stills-to-broll] " + " ".join(cmd))
    if a.dry_run:
        return
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(frames):
        t = i / max(1, frames - 1)
        z = 1.0 + (zmax - 1.0) * (t if a.direction == "in" else (1.0 - t))
        win_w = W / z
        win_h = H / z
        x0 = (W - win_w) / 2.0
        y0 = (H - win_h) / 2.0
        # Output pixel (ox, oy) -> source (x0 + sx*ox, y0 + sy*oy); fractional, so smooth.
        sx = win_w / a.width
        sy = win_h / a.height
        frame = im.transform(
            (a.width, a.height), Image.AFFINE, (sx, 0.0, x0, 0.0, sy, y0), resample=Image.BICUBIC,
        )
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg exited {rc}")


def render_zoompan(a: argparse.Namespace, src: Path, cw: int, ch: int, x: int, y: int, frames: int, zmax: float) -> None:
    ww, hh = a.width * a.oversample, a.height * a.oversample
    if a.direction == "in":
        zexpr = f"1+({zmax}-1)*on/{frames}"
    else:
        zexpr = f"{zmax}-({zmax}-1)*on/{frames}"
    vf = [
        f"crop={cw}:{ch}:{x}:{y}",
        f"scale={ww}:{hh}:flags=lanczos",
        f"zoompan=z='{zexpr}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={frames}:s={a.width}x{a.height}:fps={a.fps}",
    ]
    if a.eq:
        vf.append(f"eq={a.eq}")
    vf.append("format=yuv420p")
    cmd = encode_cmd(a, raw_input=False) + [
        "-i", str(src),
        "-vf", ",".join(vf),
        "-t", f"{a.dur:.3f}",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", str(a.crf),
        "-pix_fmt", "yuv420p", "-r", str(a.fps),
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
        str(a.output),
    ]
    run(cmd, a.dry_run)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--dur", type=float, default=3.5)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--zoom", type=float, default=1.10, help="End zoom factor (>1). 1.0 = static")
    p.add_argument("--direction", choices=["in", "out"], default="in")
    p.add_argument("--focus", default="0.5,0.45", help="fx,fy fractions for the crop centre")
    p.add_argument("--eq", default=None, help="ffmpeg eq= params applied after the crop (match the A-roll)")
    p.add_argument("--engine", choices=["auto", "pil", "zoompan"], default="auto",
                   help="pil = sub-pixel affine per frame (smooth, default when Pillow exists); zoompan = ffmpeg fallback (steps)")
    p.add_argument("--oversample", type=int, default=4, help="zoompan engine only: working scale before zoompan")
    p.add_argument("--crf", type=int, default=16)
    p.add_argument("--no-autorotate", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if not a.image.exists():
        eprint(f"ERROR: image not found: {a.image}")
        return 2
    if a.output.exists() and not a.force:
        eprint(f"ERROR: output exists (use --force): {a.output}")
        return 2
    try:
        fx, fy = (float(v) for v in a.focus.split(","))
    except ValueError:
        eprint("ERROR: --focus must be fx,fy")
        return 2
    engine = a.engine
    if engine == "auto":
        engine = "pil" if have_pil() else "zoompan"

    work = Path(tempfile.mkdtemp(prefix="stills-to-broll-"))
    src = a.image if a.no_autorotate else exif_upright(a.image, work)
    w, h = probe_size(src)
    cw, ch, x, y = crop_916(w, h, fx, fy)
    frames = max(2, int(round(a.dur * a.fps)))
    zmax = max(1.0, a.zoom)
    print(f"[stills-to-broll] {a.image.name}: {w}x{h} -> crop {cw}x{ch}+{x}+{y}, {frames} frames, zoom {a.direction} to {zmax}, engine {engine}")
    if engine == "pil":
        render_pil(a, src, cw, ch, x, y, frames, zmax)
    else:
        render_zoompan(a, src, cw, ch, x, y, frames, zmax)
    if not a.dry_run:
        ow, oh = probe_size(a.output)
        print(f"[stills-to-broll] wrote {a.output} ({ow}x{oh})")
    shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
