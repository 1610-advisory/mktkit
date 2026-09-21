---
description: Organize raw shoot day footage into content-piece folders using AI analysis
argument-hint: /path/to/shoot-folder [client-name]
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Agent, AskUserQuestion]
---

# Organize Shoot Day Footage

Process raw shoot day footage and organize it into content-piece folders using transcript analysis, visual frame matching, and bi-weekly brief context.

## Arguments

User provided: $ARGUMENTS

Parse for:
- **Path** to the shoot day folder (e.g., `/Volumes/ExternalDrive/ClientName/2026-03-09/`)
- **Client name** (e.g., `acme-builders`) — defaults to current client if in a client directory

If no path provided, ask:
1. "Where is the shoot day footage? (full path to folder)"
2. "Which client is this for?"

---

## Workflow

### Step 1: Read the Current Bi-Weekly Brief

Find the most recent bi-weekly brief for the client:
```
clients/[client]/outputs/biweekly-briefs/
```
Extract:
- Shot list (locations, what to capture)
- Content pieces planned (post numbers, titles, formats)
- Project name reference (social name ↔ internal name mapping)

If no brief exists, ask the user what content pieces were planned for this shoot.

### Step 2: Scan the Input Folder

Inventory all files in the shoot folder:
```bash
find "[shoot-folder]" -type f \( -name "*.MP4" -o -name "*.mp4" -o -name "*.CR3" -o -name "*.cr3" -o -name "*.JPG" -o -name "*.jpg" -o -name "*.RAF" -o -name "*.raf" \) | sort
```

Report:
- Number of subfolders (locations)
- File counts per location (video vs. photo)
- Total file count and size

### Step 3: Sort Files by Media Type

Create `Video/`, `Photos/`, and `Edits/` subfolders in each location and move files by extension. (`Audio/` is created in Step 4.) All four — **Video, Audio, Photos, Edits** — are created on every shoot so the structure matches prior shoots exactly: the editor pulls from a clean `Video/` folder and returns cuts into `Edits/`.

```bash
# For each location folder (or the shoot root if no location subfolders):
mkdir -p "[location]/Video"
mkdir -p "[location]/Photos"
mkdir -p "[location]/Edits"   # left empty — editor's returned deliverables land here

# Move video files
mv [location]/*.MP4 [location]/*.mp4 [location]/*.MOV [location]/*.mov "[location]/Video/" 2>/dev/null

# Move photo files
mv [location]/*.CR3 [location]/*.cr3 [location]/*.JPG [location]/*.jpg [location]/*.RAF [location]/*.raf "[location]/Photos/" 2>/dev/null
```

**Handle pre-existing structure:** If files are already in `Video/` or `Photos/` subfolders (from camera dump), skip the move for that media type. Check before moving.

Result:
```
[shoot-date]/
├── Video/              ← share this folder with editor
│   ├── 064A7325.MP4
│   └── ...
├── Audio/              ← created in next step (transcripts + audio)
│   ├── 064A7325.m4a
│   ├── 064A7325.txt
│   └── ...
├── Photos/             ← CR3, JPG, RAF files
│   ├── IMG_1234.CR3
│   └── ...
└── Edits/              ← empty; editor's returned cuts land here
```

### Step 4: Extract Audio from All Videos

For each video file in `Video/`, extract audio to the `Audio/` subfolder:
```bash
mkdir -p "[location]/Audio"
ffmpeg -i "[location]/Video/[input].MP4" -vn -acodec copy "[location]/Audio/[basename].m4a" -y
```

- `-vn` = no video stream
- `-acodec copy` = copy AAC audio (no re-encoding, fast)
- Skip files where `.m4a` already exists

### Step 5: Transcribe ALL Videos

**Transcribe every video, not just long ones.** The shooter narrates what they're filming on B-roll clips (e.g., "Here's a pocket door," "B-roll of the soffit detail"). These narration cues identify what's in the clip and enable smart naming even for short B-roll.

Get durations for all videos:
```bash
ffprobe -v quiet -show_entries format=duration -of csv=p=0 "[file]"
```

Transcribe **all** extracted audio files using `mlx-whisper` (Apple Silicon GPU — 5-10x faster than CPU `openai-whisper`). Default model is `mlx-community/whisper-large-v3-turbo` — fast on the GPU and top-tier accuracy. Only drop to `mlx-community/whisper-tiny` for short identification-only B-roll where speed matters more than accuracy. When in doubt, use turbo — it's cheap and avoids having to re-transcribe later when someone wants to edit the clip.

**Always emit word-level timestamps.** Downstream video editing (transcript-driven cuts via ffmpeg) relies on per-word timing, not just the text. The CLI invocation:

```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/mlx_whisper \
  "[audio-file].m4a" \
  --model mlx-community/whisper-large-v3-turbo \
  --language en \
  --output-format all \
  --word-timestamps True \
  --output-dir "[location]/Audio"
```

`--output-format all` writes `.txt`, `.json`, `.srt`, `.vtt`, and `.tsv` alongside the audio. The `.json` carries word-level start/end times and is what enables transcript-driven cutting. Keep all of them — they're small.

(Legacy CPU `openai-whisper` is still installed at `/Library/Frameworks/Python.framework/Versions/3.12/bin/whisper` as a fallback if mlx-whisper ever breaks, but new runs should use mlx_whisper.)

Resulting layout:
```
[location]/Audio/064A7325.m4a
[location]/Audio/064A7325.txt    ← human-readable transcript
[location]/Audio/064A7325.json   ← word-level timestamps (for editing)
[location]/Audio/064A7325.srt    ← subtitle file
[location]/Audio/064A7325.vtt    ← web subtitle file
[location]/Audio/064A7325.tsv    ← tab-separated segment table
```

**Parallelization:** Batch transcriptions in parallel using background tasks. Group by location (one batch per location folder) to maximize throughput. Whisper tiny is fast per-file but 60+ files adds up.

**Transcript analysis — two types of speech to look for:**
1. **A-roll speech** — the owner talking to camera, explaining a project or concept. Longer clips (>30s), full sentences, educational content.
2. **Shooter narration** — Brief descriptions of what's being filmed. Short clips (<15s), phrases like "B-roll of the [thing]," "here's the [detail]," "shooting the [room/feature]." Use these cues to name B-roll files descriptively.

**Skip transcription** only for clips where the audio is clearly empty/silent (file size <20KB for the .m4a).

### Step 6: Match Footage to Content Pieces

Using transcripts (both A-roll speech and shooter narration) and the bi-weekly brief, identify which videos match which content pieces:

1. **Read each transcript** — look for:
   - **A-roll**: Project names, locations, room types, the owner's talking points matching planned scripts
   - **B-roll narration**: Shooter describing the shot (e.g., "pocket door," "kitchen wide shot," "siding detail") — use these descriptions for naming

2. **Cross-reference with shot list** — match by:
   - Location folder name ↔ project name
   - Transcript content ↔ planned script/concept
   - Shooter narration ↔ shot list items
   - Duration ↔ expected format (30s quick take vs. 90s walkthrough)

3. **Classify each video as:**
   - **A-Roll** — Primary talking/walkthrough footage (the owner speaking to camera, matches a content piece)
   - **B-Roll (described)** — Short clips where the shooter narrated what's in the shot. Name using the narration.
   - **B-Roll (silent)** — No useful audio. Leave original filename but note location.
   - **Unmatched** — Has speech but can't confidently assign to a content piece

### Step 7: Rename Videos

Rename **all videos that have useful transcript content** (A-roll and narrated B-roll) inside the `Video/` subfolder. Silent B-roll keeps its original filename.

**A-Roll naming pattern:**
```
ARoll-[Location]-[Description].MP4         # Primary talking/walkthrough footage
CB-[Location]-[Description].MP4            # For content bank items
```

**B-Roll naming pattern (when shooter narrated the shot):**
```
BRoll-[Location]-[Description].MP4
```

Examples:
- `ARoll-Maple-Kitchen-Walkthrough.MP4`
- `CB-Cedar-PocketDoors-CavitySliders.MP4`
- `BRoll-Cedar-Insulation-WideShot.MP4`
- `BRoll-Maple-Cabinet-Detail.MP4`

**Also rename the corresponding Audio + Transcript files** to match. Rename every sidecar Whisper produced (`.m4a`, `.txt`, `.json`, `.srt`, `.vtt`, `.tsv`) — they must stay in lockstep so editing workflows can find the JSON by the video's basename:
```
Audio/064A7325.m4a  → Audio/ARoll-Maple-Kitchen-Walkthrough.m4a
Audio/064A7325.txt  → Audio/ARoll-Maple-Kitchen-Walkthrough.txt
Audio/064A7325.json → Audio/ARoll-Maple-Kitchen-Walkthrough.json
Audio/064A7325.srt  → Audio/ARoll-Maple-Kitchen-Walkthrough.srt
Audio/064A7325.vtt  → Audio/ARoll-Maple-Kitchen-Walkthrough.vtt
Audio/064A7325.tsv  → Audio/ARoll-Maple-Kitchen-Walkthrough.tsv
```

**Create a `file-mapping.txt`** in each location folder mapping original → new names:
```
Video/064A7325.MP4 → Video/ARoll-Maple-Kitchen-Walkthrough.MP4
Video/064A7326.MP4 → Video/BRoll-Maple-Window-Detail.MP4
Video/064A7327.MP4  (silent — not renamed)
```

Rename in place — no copies.

### Step 8: Present Summary to User

Show a clear summary:

```
## Shoot Organization Summary

### Maple (1970s Kitchen)
- 12 videos, 16 photos
- A-Roll: 2 files (Kitchen Walkthrough)
- B-Roll: 10 files (detail shots, pans)
- Photos: 16 CR3 files

### [Location 2]
...

### Shot List Status
✅ Maple kitchen walkthrough — captured (2 takes)
✅ Cedar addition progress — captured
❌ Birch bathroom — NOT SHOT
❌ Owner talking heads — NOT RECORDED

### Unmatched Files
- [list any files that couldn't be confidently placed]
```

### Step 9: Update Bi-Weekly Brief

Update the bi-weekly brief to reflect actual shoot results:
- Check off captured shots in the shot list
- Mark unshot items as "not captured — needs rescheduling"
- Note any unplanned footage that was captured
- Update content piece status (which posts have footage, which need reshoots)

### Step 10: Flip Content Notes to `captured`

For every content piece confirmed as shot in Step 8, find the matching content note in `outputs/content/` and update its `status:` frontmatter to `captured` — but only if the current status is `concept` or `pre-production`. Don't downgrade notes already at `captured` or later.

1. Match by content ID, title, or brief slot number (e.g., "AB-08 5/14" → `2026-05-14-AB-08-*.md`)
2. Read the note, check current status
3. If `concept` or `pre-production` → flip to `captured`
4. If already `captured` or later → skip

Report what changed:
```
## Kanban Updates
✅ 2026-05-14-AB-08 Series P4 — concept → captured
✅ 2026-05-18-AC-01 Acme Weekly — concept → captured
⏭️ 2026-05-07-AB-03 Series P5 — already pre-approval, skipped
```

Also flip any matching BANKED notes (in `outputs/content/BANKED-*.md`) if they map to footage captured on this shoot.

### Step 11: Save File Mapping

Create a master `file-mapping.csv` in the shoot day root folder:
```csv
original_name,new_name,location,subfolder,content_piece,type,duration_s,transcript_summary
064A7325.MP4,ARoll-Maple-Kitchen-Walkthrough.MP4,Maple,Video/,a-roll,78,"intro walkthrough — layout and framing"
064A7326.MP4,BRoll-Maple-Window-Detail.MP4,Maple,Video/,b-roll,7,"B-roll of the window situation"
064A7327.MP4,,Maple,Video/,b-roll-silent,6,""
IMG_1234.CR3,,Maple,Photos/,photo,,"
```

### Step 12: Update Shoot Log

Append a new entry to the client's **shoot log** at `tracking/shoot-log.md`. This is a cumulative record that persists across sessions and prevents content from falling through the cracks.

**What to write:**
1. Shoot date and locations visited
2. Per-location table: video count, photo count, content pieces identified
3. Content pieces table with edit status (all start as "Waiting")
4. Any content bank items identified
5. Outstanding items — anything planned but not captured

**Format:**
```markdown
## YYYY-MM-DD — Shoot Day

**Locations:** [Location 1], [Location 2], ...

| Location | Videos | Photos | Content Pieces |
|----------|--------|--------|----------------|
| [Name] | [#] | [#] | [Pieces identified] |

**Content Pieces — Edit Status:**

| Piece | Brief | Edit Status |
|-------|-------|-------------|
| [Name] | [Which brief it's planned for] | Waiting |

**Content Bank:**

| Piece | Duration | Source File | Edit Status |
|-------|----------|------------|-------------|
| [Name] | [Xs] | [Filename] | Waiting |

**Outstanding:**
- [ ] [Anything planned but not captured]
```

**Insert new entries at the top** of the log (below the header), so the most recent shoot is always first.

Also update the `last_updated` date in the shoot log's YAML frontmatter.

### Step 13: Compile the footage catalog (required — organize-shoot is not done until this exits 0)

Do not skip this. Do not "offer it next." Do not wait for someone to remember a skill. The file-mapping you just wrote is per-shoot; this step is the compiled record (catalog JSONL, talking `.txt` copies in the client repo, generated `tracking/content-index.md`, optional broll-index refresh).

From the **client marketing repo root**:

1. If `scripts/ingest-footage.py` exists, run it:
   ```bash
   python3 scripts/ingest-footage.py
   ```
   Extra flags the wrapper already documents (`--dry-run`, `--skip-broll`, `--broll-clip`) may be passed through. Default is a real ingest including broll `--update`. Use `--skip-broll` only if the user said to skip the visual index.
2. Else run the toolkit script (`footage-index` skill → `scripts/ingest-footage.py`) with that client's `--root`, `--catalog`, `--transcripts-out`, `--content-index-out`, and optional `--social-map` / `--notes-dir` / `--broll-index`.
3. **Exit 0** → report catalog row count and that `content-index.md` was regenerated. Then you may offer shoot-review.
4. **Exit 2** (no footage root mounted) → organize-shoot **failed**. You just wrote files on a volume that ingest cannot see; say so. Do not hand-edit `content-index.md` as a substitute.
5. Any other non-zero exit → failed. Fix or stop. Do not mark the shoot organized in the index by hand.

Do **not** hand-merge rows into `tracking/content-index.md` when ingest exists. That file is generated (`generated: true` in frontmatter). The old `/index-content` hand scan is the fallback only for clients that have no ingest script yet.

---

## Technical Reference

### FFmpeg Audio Extraction
```bash
ffmpeg -i input.MP4 -vn -acodec copy output.m4a -y
```

### FFmpeg Duration Check
```bash
ffprobe -v quiet -show_entries format=duration -of csv=p=0 input.MP4
```

### Whisper Transcription (mlx-whisper, GPU, word-level timestamps, all formats)
```bash
/Library/Frameworks/Python.framework/Versions/3.12/bin/mlx_whisper \
  input.m4a \
  --model mlx-community/whisper-large-v3-turbo \
  --language en \
  --output-format all \
  --word-timestamps True \
  --output-dir ./Audio
```

Use `mlx-community/whisper-tiny` for short identification-only B-roll clips where raw speed matters; use `mlx-community/whisper-large-v3-turbo` (default) for anything that might be edited later. `--word-timestamps True` is required for downstream transcript-driven editing (the `.json` carries per-word start/end times).

**Note the flag dialect.** mlx-whisper uses **dashes** (`--output-format`, `--word-timestamps`); the legacy CPU `openai-whisper` CLI used **underscores** (`--output_format`, `--word_timestamps`). Don't mix them up.

### CR3 to JPEG Thumbnail (for visual analysis if needed)
```bash
sips -s format jpeg input.CR3 --out thumbnail.jpg -Z 1024
```

### Frame Extraction (for visual analysis if needed)
```bash
ffmpeg -i input.MP4 -vf "fps=0.1" -q:v 2 frames/frame_%04d.jpg
```

---

## Limitations

- **CR3 RAW files**: Can generate thumbnails but full-quality files stay in original location
- **Whisper tiny** may miss words or misinterpret brief narration — flag low-confidence transcriptions for manual review
- **Shooter narration** varies — some clips may have partial or unclear descriptions. When narration is ambiguous, keep original filename and note the raw transcript in the mapping.
- **Files are moved into media subfolders** (Video/, Audio/, Photos/) — original flat structure is not preserved, but file-mapping.csv tracks all moves
- **SSD paths**: Ensure the SSD is mounted before running. Check with `ls [path]`
