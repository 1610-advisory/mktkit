#!/usr/bin/env python3
"""Transcript-driven video cut engine.

Given a source video, a Whisper word-level JSON transcript, and a list of
coarse keep ranges (Garret-only regions etc.), renders a tight cut that:
  - Excludes filler words (uh, um, er, ...) inside the keep ranges
  - Compresses inter-word pauses longer than --max-pause to --keep-tail seconds
  - Concatenates the resulting micro-segments with ffmpeg filter_complex

Used by the `/cut-video` workflow. Can also be called standalone.

Usage:
    cut-video.py \
        --source /path/to/source.MOV \
        --json   /path/to/transcript.json \
        --output /path/to/output.mp4 \
        --range 14.40:29.55 \
        --range 33.10:47.32 \
        --range 75.22:99.85 \
        [--max-pause 0.40] \
        [--keep-tail 0.10] \
        [--keep-lead 0.05] \
        [--no-filler-removal] \
        [--no-pause-compression] \
        [--dry-run]

Output:
    Renders to --output (H.264 / AAC, CRF 18, --preset fast).
    Prints the final keep ranges, total duration, and the ffmpeg command.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_FILLERS = {"uh", "um", "umm", "uhh", "er", "erm"}


def parse_range(s: str) -> tuple[float, float]:
    """Parse 'start:end' (seconds) into (start, end)."""
    try:
        a, b = s.split(":")
        start, end = float(a), float(b)
        if end <= start:
            raise ValueError("end must be > start")
        return start, end
    except Exception as e:
        raise argparse.ArgumentTypeError(
            f"Bad --range '{s}': expected 'start:end' in seconds. {e}"
        )


def words_in_ranges(
    transcript: dict,
    coarse: list[tuple[float, float]],
    fillers: set[str] | None,
) -> list[tuple[float, float, str]]:
    """Return [(start, end, word), ...] for all words inside any coarse range.

    Skips words in `fillers` (case-insensitive, alphanumeric-only comparison).
    `fillers=None` disables filler removal.
    """
    out = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words", []):
            if fillers is not None:
                tok = re.sub(r"[^a-z]", "", w["word"].lower())
                if tok in fillers:
                    continue
            for ks, ke in coarse:
                if w["start"] >= ks and w["end"] <= ke:
                    out.append((w["start"], w["end"], w["word"]))
                    break
    out.sort()
    return out


def compress_pauses(
    words: list[tuple[float, float, str]],
    max_pause: float,
    keep_tail: float,
    keep_lead: float,
    lead_in: float,
    lead_out: float,
) -> list[tuple[float, float]]:
    """Walk consecutive words; any gap > max_pause becomes a cut.

    The previous range ends at prev_word.end + keep_tail; the next range
    starts at next_word.start - keep_lead. This preserves natural breath
    on both sides of the splice without leaving the full dead air.

    `lead_in`/`lead_out` add cushion at the very start/end of the result.
    """
    if not words:
        return []
    ranges: list[tuple[float, float]] = []
    seg_start = max(0.0, words[0][0] - lead_in)
    prev_end = words[0][1]
    for ws, we, _ in words[1:]:
        if ws - prev_end > max_pause:
            ranges.append((seg_start, prev_end + keep_tail))
            seg_start = ws - keep_lead
        prev_end = we
    ranges.append((seg_start, prev_end + lead_out))
    # Drop sub-50ms slivers
    return [(s, e) for s, e in ranges if e - s > 0.05]


def build_filter_complex(ranges: list[tuple[float, float]]) -> str:
    parts: list[str] = []
    labels: list[str] = []
    for i, (s, e) in enumerate(ranges):
        parts.append(f"[0:v]trim={s:.3f}:{e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    return (
        ";".join(parts)
        + ";"
        + "".join(labels)
        + f"concat=n={len(ranges)}:v=1:a=1[outv][outa]"
    )


def probe_source_color(source: Path) -> dict:
    """ffprobe the source video stream to capture pix_fmt + color tags.

    Returns a dict with keys: pix_fmt, color_space, color_primaries,
    color_transfer, color_range. Missing/unknown fields are None.

    Used so the encoded output inherits the source's color pipeline
    (critical for HDR HLG / Rec.2020 sources — without this, NLEs like
    Resolve interpret untagged output as Rec.601 and the cut looks
    desaturated relative to the source).
    """
    keys = ["pix_fmt", "color_space", "color_primaries", "color_transfer", "color_range"]
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=" + ",".join(keys),
        "-of", "default=noprint_wrappers=1",
        str(source),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out: dict = {k: None for k in keys}
    if r.returncode != 0:
        return out
    for line in r.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            v = v.strip()
            if v and v != "unknown":
                out[k] = v
    return out


def color_args_for(color: dict) -> tuple[list[str], str | None]:
    """Build ffmpeg color-tag args + the matching x264-params string.

    Returns (container_args, x264_params_str).
    """
    container: list[str] = []
    x264_pairs: list[str] = []

    if color.get("color_space"):
        container += ["-colorspace", color["color_space"]]
        x264_pairs.append(f"colormatrix={color['color_space']}")
    if color.get("color_primaries"):
        container += ["-color_primaries", color["color_primaries"]]
        x264_pairs.append(f"colorprim={color['color_primaries']}")
    if color.get("color_transfer"):
        container += ["-color_trc", color["color_transfer"]]
        x264_pairs.append(f"transfer={color['color_transfer']}")
    if color.get("color_range"):
        container += ["-color_range", color["color_range"]]
        x264_pairs.append(f"range={color['color_range']}")

    x264_params = ":".join(x264_pairs) if x264_pairs else None
    return container, x264_params


def is_10bit(pix_fmt: str | None) -> bool:
    return bool(pix_fmt) and ("10" in pix_fmt or "12" in pix_fmt)


def is_hdr(color: dict) -> bool:
    """Detect HDR transfer functions (HLG, PQ)."""
    trc = (color.get("color_transfer") or "").lower()
    return trc in {"arib-std-b67", "smpte2084", "smpte428"}


def has_filter(name: str) -> bool:
    """Check if ffmpeg was built with a given filter (libplacebo, zscale, etc.)."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False
    return any(
        line.split()[1] == name
        for line in r.stdout.splitlines()
        if len(line.split()) >= 2
    )


def hlg_to_rec709_filter() -> str | None:
    """Return an ffmpeg filter string that tonemaps HLG/PQ → Rec.709 SDR.

    Filter preference depends on platform:
      - macOS: prefer zscale (zimg). libplacebo on macOS only ships with a
        Vulkan backend, which doesn't work on Apple Silicon — it would build
        but fail at runtime with "VK_ERROR_INCOMPATIBLE_DRIVER".
      - Linux: prefer libplacebo (best quality), fall back to zscale.

    Returns None if no working tonemap filter is available — caller should
    warn the user.
    """
    is_mac = sys.platform == "darwin"

    if not is_mac and has_filter("libplacebo"):
        return (
            "libplacebo=colorspace=bt709:color_primaries=bt709:"
            "color_trc=bt709:range=limited:tonemapping=spline:format=yuv420p"
        )
    if has_filter("zscale"):
        # Classic zimg-based pipeline. `npl=100` = 100 nits SDR target.
        # `tonemap=hable` is a smooth filmic curve, matches what most NLEs
        # do internally for HDR→SDR previews.
        return (
            "zscale=t=linear:npl=100,"
            "format=gbrpf32le,"
            "tonemap=hable:desat=0,"
            "zscale=p=bt709:t=bt709:m=bt709:r=tv,"
            "format=yuv420p"
        )
    # Last resort on Linux only — libplacebo if zscale isn't built.
    if not is_mac and has_filter("libplacebo"):
        return (
            "libplacebo=colorspace=bt709:color_primaries=bt709:"
            "color_trc=bt709:range=limited:tonemapping=spline:format=yuv420p"
        )
    return None


def main() -> int:
    p = argparse.ArgumentParser(description="Transcript-driven video cut engine.")
    p.add_argument("--source", type=Path, required=True, help="Source video file")
    p.add_argument("--json", type=Path, required=True, help="Whisper word-level JSON")
    p.add_argument("--output", type=Path, required=True, help="Output MP4 path")
    p.add_argument(
        "--range",
        type=parse_range,
        action="append",
        required=True,
        help="Coarse keep range in seconds 'start:end'. Pass multiple.",
    )
    p.add_argument(
        "--max-pause",
        type=float,
        default=0.40,
        help="Compress inter-word gaps longer than this (default 0.40s).",
    )
    p.add_argument(
        "--keep-tail",
        type=float,
        default=0.10,
        help="Silence to keep after a word at a cut point (default 0.10s).",
    )
    p.add_argument(
        "--keep-lead",
        type=float,
        default=0.05,
        help="Silence to keep before the first word of the next segment (default 0.05s).",
    )
    p.add_argument(
        "--lead-in",
        type=float,
        default=0.10,
        help="Cushion before the very first word (default 0.10s).",
    )
    p.add_argument(
        "--lead-out",
        type=float,
        default=0.15,
        help="Cushion after the very last word (default 0.15s).",
    )
    p.add_argument(
        "--no-filler-removal",
        action="store_true",
        help="Do not strip uh/um/er.",
    )
    p.add_argument(
        "--no-pause-compression",
        action="store_true",
        help="Keep natural pauses; only the coarse ranges drive cuts.",
    )
    p.add_argument(
        "--crf",
        type=int,
        default=18,
        help="x264 CRF (default 18). Higher = smaller file, lower quality.",
    )
    p.add_argument(
        "--preset",
        default="fast",
        help="x264 preset (default 'fast'). ultrafast→veryslow.",
    )
    p.add_argument(
        "--force-8bit",
        action="store_true",
        help=(
            "Force 8-bit yuv420p output even if source is 10-bit. "
            "Smaller files, broader compatibility, but lossy on HDR sources."
        ),
    )
    p.add_argument(
        "--strip-color",
        action="store_true",
        help=(
            "Don't carry source color tags through to output. Rarely useful; "
            "only set if the source has wrong/misleading tags."
        ),
    )
    p.add_argument(
        "--keep-hdr",
        action="store_true",
        help=(
            "Preserve HDR/HLG color pipeline end-to-end (10-bit, Rec.2020 tags). "
            "Default is to tonemap HDR sources to Rec.709 SDR so the output "
            "looks correct in non-color-managed NLEs/players. Use this when "
            "the downstream tool is HDR-aware (e.g. Resolve in color-managed mode)."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute ranges and print the ffmpeg command without running it.",
    )
    args = p.parse_args()

    if not args.source.exists():
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        return 2
    if not args.json.exists():
        print(f"ERROR: transcript JSON not found: {args.json}", file=sys.stderr)
        return 2

    transcript = json.loads(args.json.read_text())
    fillers = None if args.no_filler_removal else DEFAULT_FILLERS
    words = words_in_ranges(transcript, args.range, fillers)
    print(f"[cut-video] coarse ranges: {len(args.range)}")
    print(f"[cut-video] kept words: {len(words)} (filler removal={'off' if fillers is None else 'on'})")

    if args.no_pause_compression:
        # Just use the coarse ranges as-is
        ranges = list(args.range)
    else:
        ranges = compress_pauses(
            words,
            max_pause=args.max_pause,
            keep_tail=args.keep_tail,
            keep_lead=args.keep_lead,
            lead_in=args.lead_in,
            lead_out=args.lead_out,
        )

    total = sum(e - s for s, e in ranges)
    print(f"[cut-video] output ranges: {len(ranges)}  total {total:.2f}s")
    for s, e in ranges:
        print(f"  {s:7.2f} - {e:7.2f}  ({e-s:.2f}s)")

    if not ranges:
        print("ERROR: no ranges to render.", file=sys.stderr)
        return 3

    filter_str = build_filter_complex(ranges)

    # Probe source color to decide pipeline (HDR tonemap vs SDR passthrough).
    color = probe_source_color(args.source)
    src_10bit = is_10bit(color.get("pix_fmt"))
    src_hdr = is_hdr(color)

    print(
        f"[cut-video] source color: pix_fmt={color.get('pix_fmt')} "
        f"space={color.get('color_space')} primaries={color.get('color_primaries')} "
        f"transfer={color.get('color_transfer')} range={color.get('color_range')}"
    )
    print(
        f"[cut-video] source HDR: {src_hdr}, source 10-bit: {src_10bit}"
    )

    # Decide pipeline:
    #   HDR source + --keep-hdr   → 10-bit Rec.2020/HLG passthrough
    #   HDR source (default)      → tonemap to 8-bit Rec.709 SDR (looks right
    #                               in non-color-managed players/NLEs)
    #   SDR source                → passthrough source color tags
    tonemap_filter = None
    if src_hdr and not args.keep_hdr:
        tonemap_filter = hlg_to_rec709_filter()
        if tonemap_filter is None:
            print(
                "[cut-video] WARNING: source is HDR but ffmpeg has neither "
                "libplacebo nor zscale built — cannot tonemap. Falling back "
                "to HDR passthrough. Install ffmpeg with libplacebo for "
                "proper HLG→Rec.709 conversion. Use --keep-hdr to silence "
                "this warning.",
                file=sys.stderr,
            )

    do_tonemap = tonemap_filter is not None
    use_10bit = src_10bit and not args.force_8bit and not do_tonemap
    pix_fmt = "yuv420p10le" if use_10bit else "yuv420p"
    profile = ["-profile:v", "high10"] if use_10bit else []

    # If tonemapping, append the filter chain after concat and re-route to a
    # new label. Output color tags become Rec.709 SDR.
    if do_tonemap:
        filter_str = (
            filter_str.replace("[outv]", "[concat_v]")
            + f";[concat_v]{tonemap_filter}[outv]"
        )
        # Synthesize SDR Rec.709 color metadata for the output, regardless
        # of source tags.
        sdr_color = {
            "color_space": "bt709",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
            "color_range": "tv",
            "pix_fmt": "yuv420p",
        }
        color_container, x264_color_params = (
            ([], None) if args.strip_color else color_args_for(sdr_color)
        )
        print("[cut-video] output: 8-bit Rec.709 SDR (HLG→Rec.709 tonemapped)")
    else:
        color_container, x264_color_params = (
            ([], None) if args.strip_color else color_args_for(color)
        )
        print(
            f"[cut-video] output: pix_fmt={pix_fmt}"
            f"{' (10-bit preserved)' if use_10bit else ''}"
            f"{' (forced 8-bit)' if (src_10bit and args.force_8bit) else ''}"
            f"{' (HDR preserved per --keep-hdr)' if (src_hdr and args.keep_hdr) else ''}"
        )

    x264_params_args: list[str] = []
    if x264_color_params:
        x264_params_args = ["-x264-params", x264_color_params]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-i", str(args.source),
        "-filter_complex", filter_str,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264",
        *profile,
        "-preset", args.preset, "-crf", str(args.crf),
        "-pix_fmt", pix_fmt,
        *color_container,
        *x264_params_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(args.output), "-y",
    ]

    if args.dry_run:
        print("\n[cut-video] DRY RUN — ffmpeg command:")
        print(" ".join(f"'{c}'" if " " in c or ":" in c else c for c in cmd))
        return 0

    print(f"\n[cut-video] rendering to {args.output} ...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("[cut-video] ffmpeg FAILED:", file=sys.stderr)
        print(r.stderr[-2000:], file=sys.stderr)
        return r.returncode
    print(f"[cut-video] wrote {args.output} ({total:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
