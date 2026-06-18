#!/usr/bin/env python3
"""Transcribe a single audio file with mlx-whisper (Apple Silicon GPU).

Prints the transcript text to stdout. Errors and progress go to stderr so
stdout can be redirected straight into a .txt file or captured by a parent
process.

Usage:
    transcribe.py <audio-path>
        [--model tiny|medium|large-v3-turbo|large-v3]    # short alias
        [--model mlx-community/whisper-...]              # or full HF repo
        [--language en]
        [--out path.txt]                                 # write transcript here
        [--json]                                         # also write sidecar
                                                         # .json/.srt/.vtt with
                                                         # word-level timestamps

Defaults:
    model    = large-v3-turbo  (fast on Apple Silicon GPU, top-tier accuracy)
    language = (auto-detect)
    out      = stdout

Run with the project's Python interpreter (mlx-whisper is installed there):
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
        scripts/transcribe.py /path/to/audio.m4a --model large-v3-turbo --json

Models cache to ~/.cache/huggingface/hub/ on first download.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Short alias → HuggingFace repo. Users can also pass a full repo path.
MODEL_ALIASES = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large": "mlx-community/whisper-large-v3",
    "large-v3": "mlx-community/whisper-large-v3",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",
}


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _resolve_model(name: str) -> str:
    """Allow short aliases (`turbo`, `tiny`) or full HF repo paths."""
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]
    if "/" in name:
        return name  # assume caller passed a full HF repo path
    _eprint(
        f"ERROR: unknown model alias '{name}'. "
        f"Known aliases: {', '.join(sorted(MODEL_ALIASES))}. "
        f"Or pass a full HuggingFace repo like 'mlx-community/whisper-medium'."
    )
    sys.exit(2)


def _write_sidecars(result: dict, base_path: Path) -> None:
    """Write .json, .srt, .vtt sidecars alongside the .txt output.

    These carry word-level timestamps (when --word-timestamps was on) needed
    for transcript-driven video editing.
    """
    # JSON — full result with segments + per-word timings
    json_path = base_path.with_suffix(".json")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _eprint(f"[transcribe] wrote {json_path}")

    # SRT — subtitle format with segment-level cues
    srt_lines = []
    for i, seg in enumerate(result.get("segments", []), start=1):
        srt_lines.append(str(i))
        srt_lines.append(f"{_srt_time(seg['start'])} --> {_srt_time(seg['end'])}")
        srt_lines.append(seg["text"].strip())
        srt_lines.append("")
    srt_path = base_path.with_suffix(".srt")
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
    _eprint(f"[transcribe] wrote {srt_path}")

    # VTT — web subtitle format
    vtt_lines = ["WEBVTT", ""]
    for seg in result.get("segments", []):
        vtt_lines.append(
            f"{_vtt_time(seg['start'])} --> {_vtt_time(seg['end'])}"
        )
        vtt_lines.append(seg["text"].strip())
        vtt_lines.append("")
    vtt_path = base_path.with_suffix(".vtt")
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    _eprint(f"[transcribe] wrote {vtt_path}")


def _srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t - int(t)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _vtt_time(t: float) -> str:
    return _srt_time(t).replace(",", ".")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcribe audio with mlx-whisper (Apple Silicon GPU)."
    )
    parser.add_argument(
        "audio_path", type=Path, help="Path to audio file (m4a, mp3, wav, etc.)"
    )
    parser.add_argument(
        "--model",
        default="large-v3-turbo",
        help=(
            "Model alias (tiny, medium, large-v3-turbo, turbo, large-v3) "
            "or full HuggingFace repo path. Default: large-v3-turbo."
        ),
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Force a language code (e.g. 'en'). Default: auto-detect.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write transcript text to this file instead of stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help=(
            "Also write sidecar .json/.srt/.vtt next to --out (or next to the "
            "audio file if no --out). Requires --out to determine basename."
        ),
    )
    parser.add_argument(
        "--no-word-timestamps",
        action="store_true",
        help=(
            "Skip word-level timestamps. Faster, but the .json won't be "
            "usable for transcript-driven video cuts."
        ),
    )
    args = parser.parse_args()

    audio = args.audio_path
    if not audio.exists():
        _eprint(f"ERROR: audio file not found: {audio}")
        return 2
    if not audio.is_file():
        _eprint(f"ERROR: not a file: {audio}")
        return 2

    try:
        import mlx_whisper  # type: ignore
    except ImportError:
        _eprint(
            "ERROR: mlx-whisper is not installed for this Python.\n"
            "Install with: pip install -U mlx-whisper\n"
            "Or run with: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
        )
        return 3

    repo = _resolve_model(args.model)
    _eprint(f"[transcribe] model={repo}")
    _eprint(
        f"[transcribe] transcribing {audio.name} "
        f"(word-timestamps={'off' if args.no_word_timestamps else 'on'})"
    )

    kwargs = {
        "path_or_hf_repo": repo,
        "word_timestamps": not args.no_word_timestamps,
    }
    if args.language:
        kwargs["language"] = args.language

    result = mlx_whisper.transcribe(str(audio), **kwargs)
    text = (result.get("text") or "").strip()

    if not text:
        _eprint("WARNING: transcript is empty (silent audio or model failure?)")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        _eprint(f"[transcribe] wrote {len(text)} chars to {args.out}")
        if args.json:
            _write_sidecars(result, args.out.with_suffix(""))
    else:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
        if args.json:
            _eprint(
                "WARNING: --json requires --out to know where to write sidecars. "
                "Sidecars NOT written."
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
