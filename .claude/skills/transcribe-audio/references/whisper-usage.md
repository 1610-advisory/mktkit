# Whisper usage reference (mlx-whisper, Apple Silicon GPU)

Concrete commands, model selection, and gotchas for running Whisper from this skill.

This skill uses **`mlx-whisper`** — Whisper running on the Apple Silicon GPU via the MLX framework. It is roughly 5-10x faster than the CPU-bound `openai-whisper` Python package, supports word-level timestamps for transcript-driven editing, and is the system default. The CPU-bound `openai-whisper` package (`whisper` command) works as a fallback if you have it, but new code should target mlx-whisper.

Set `AI_CMO_ROOT` to the absolute path of your toolkit repo root before running these commands.

---

## Environment

| Item | Path |
|------|------|
| mlx-whisper CLI | `mlx_whisper` on PATH after `pip install -U mlx-whisper` |
| Python (with mlx-whisper installed) | Any; `transcribe.py` finds one itself. Override with `MLX_WHISPER_PYTHON=/path/to/python3` |
| Model cache | `~/.cache/huggingface/hub/` (HuggingFace cache) |
| Legacy fallback CLI | `whisper` from `pip install -U openai-whisper` (CPU, `~/.cache/whisper/`) |

mlx-whisper downloads models on first use from HuggingFace (the `mlx-community/` org). Turbo is ~800 MB. Subsequent runs are instant to start.

---

## Model selection

mlx-whisper models live on HuggingFace under `mlx-community/`. Use the full repo path in `--model` / `path_or_hf_repo`.

| Model | Repo | Speed (GPU) | Quality | Use when |
|-------|------|-------------|---------|----------|
| `tiny` | `mlx-community/whisper-tiny` | Fastest | Decent on clean single-speaker audio | Short B-roll identification clips where speed > accuracy |
| `medium` | `mlx-community/whisper-medium` | Fast | Good | Fallback if turbo errors |
| **`large-v3-turbo`** | `mlx-community/whisper-large-v3-turbo` | Fast (close to medium) | Best | **Default.** Interviews, meetings, anything that might be edited later, anything > 5 min |
| `large-v3` | `mlx-community/whisper-large-v3` | Slowest | Best | Only if turbo missed words on a critical file |

**Auto-promotion heuristics** (decide before transcribing — saves a second pass):
- File length > 5 min → `large-v3-turbo`
- Meeting recording with multiple voices → `large-v3-turbo`
- Single-speaker memo or shoot clip recorded close to the mic → `large-v3-turbo` (turbo is still fast enough; only use `tiny` if you specifically need raw speed on a short clip)
- User flagged it as "important" or "this is the source for a blog post / video edit" → `large-v3-turbo`
- User said "just give me the gist quickly" → `tiny`

To estimate length without playing the file:
```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "<audio>"
```

---

## Word-level timestamps — when and why

**Default to `--word-timestamps True` for anything that might be edited.** The resulting `.json` carries per-word `start`/`end` times that downstream ffmpeg cuts and transcript-driven video editing depend on. Without word timestamps, the JSON only has segment-level timing (~3-15 seconds per chunk), which is too coarse for tight cuts.

Skip word timestamps only for ad-hoc "just paste me the text" requests where the transcript will never be edited.

---

## Running the bundled script

The skill ships `scripts/transcribe.py`. It wraps `mlx_whisper.transcribe()` and prints the transcript to stdout (or to `--out`).

**One audio file, transcript to stdout:**
```bash
python3 \
  $AI_CMO_ROOT/.claude/skills/transcribe-audio/scripts/transcribe.py \
  "/path/to/audio.m4a"
```

**Write transcript + sidecar JSON next to the audio file (shoot-flow / editing pattern):**
```bash
PY=python3   # transcribe.py re-runs itself under a Python that has mlx-whisper
SCRIPT=$AI_CMO_ROOT/.claude/skills/transcribe-audio/scripts/transcribe.py
AUDIO="/path/to/Audio/clip.m4a"
OUT="${AUDIO%.*}.txt"
"$PY" "$SCRIPT" "$AUDIO" --model large-v3-turbo --language en --out "$OUT" --json
```

`--json` makes the script also write a sibling `.json` (and `.srt`, `.vtt`) with word-level timestamps — required for editing workflows.

**Force English (small speedup, avoids language-detect drift):**
```bash
"$PY" "$SCRIPT" "$AUDIO" --model large-v3-turbo --language en --out "$OUT"
```

**Use the CLI directly** (no Python wrapper) when you want all output formats in one shot:
```bash
mlx_whisper \
  "$AUDIO" \
  --model mlx-community/whisper-large-v3-turbo \
  --language en \
  --output-format all \
  --word-timestamps True \
  --output-dir "$(dirname "$AUDIO")"
```

---

## Running in the background

Long files (>10 min) and batch jobs should run in the background so the conversation isn't blocked.

In Claude Code, use the `Bash` tool with `run_in_background: true`. Otherwise:

```bash
nohup "$PY" "$SCRIPT" "$AUDIO" --model large-v3-turbo --out "$OUT" \
  > "${OUT%.txt}.log" 2>&1 &
echo "PID=$!"
```

For a folder of files, prefer a small for-loop wrapped in `nohup`:
```bash
LOGDIR=/tmp/whisper-batch
mkdir -p "$LOGDIR"
nohup bash -c '
  for f in /path/to/Audio/*.m4a; do
    out="${f%.*}.txt"
    [ -s "$out" ] && { echo "skip $f (already has $out)"; continue; }
    "'$PY'" "'$SCRIPT'" "$f" --model large-v3-turbo --language en --out "$out" --json
  done
' > "$LOGDIR/batch.log" 2>&1 &
```

When the background process completes, the harness notifies you. Check the log file for the per-file summary.

---

## Skip-already-transcribed rule

For shoot-flow batches, an `.m4a` is considered already done when a sibling `.txt` exists with the same basename **and is non-empty**:

```bash
[ -s "${audio%.*}.txt" ] && skip
```

Use `-s` (size > 0), not just `-f`, so a stray empty `.txt` doesn't block re-transcription.

If a file has a `.txt` but no `.json` and you need word-level timestamps for editing, force a re-run — `.txt` alone is insufficient.

---

## Gotchas

**`m4a` needs ffmpeg.** mlx-whisper shells out to `ffmpeg` to decode non-WAV audio. If `ffmpeg` isn't on `PATH`, transcription fails with a confusing error. Verify:
```bash
which ffmpeg && ffmpeg -version | head -1
```
If missing: `brew install ffmpeg`.

**HEIC and other image formats are NOT audio.** mlx-whisper will reject them. Only feed `.m4a`, `.mp3`, `.wav`, `.flac`, `.aac`, `.ogg`, `.webm`, `.mp4`/`.mov` (the audio track will be extracted).

**Video containers work** — for `.mov` or `.mp4`, mlx-whisper extracts the audio stream automatically via ffmpeg. No need to pre-extract.

**First run on a new model downloads it from HuggingFace.** If the model isn't already in `~/.cache/huggingface/hub/`, the first call blocks on a download (~800 MB for turbo, ~3 GB for large-v3). Warn the user before triggering this if bandwidth is constrained.

**External SSD can spin down mid-transcription** and kill the process. If a long job dies with exit code 144 or similar, copy the audio to local disk (`/tmp/`) and re-run from there.

**Word-level timestamps add ~10-20% to runtime.** Still worth it by default for anything editable. Skip only for true throwaway transcripts.

**Empty transcripts mean silent audio or a decode failure.** If `text` comes back empty, mlx-whisper printed a warning to stderr — read the captured log before reporting success.

---

## Quick verification commands

After a batch run, confirm what was produced:
```bash
ls -la /path/to/Audio/*.txt | head
wc -l /path/to/Audio/*.txt
```

To re-transcribe a single file (e.g. user said "do that one again with turbo"):
1. Rename or remove the existing `.txt` (and sidecar `.json` / `.srt` / `.vtt` if present).
2. Re-run with the new model.

---

## Legacy `openai-whisper` fallback

If for some reason mlx-whisper is broken (rare), the CPU `openai-whisper` package works if installed:

```bash
whisper \
  "<audio>" \
  --model medium \
  --language en \
  --output_format all \
  --word_timestamps True \
  --output_dir "<out>"
```

Models cache to `~/.cache/whisper/`. Expect 5-10x slower runtimes than mlx-whisper. Use only as a fallback.
