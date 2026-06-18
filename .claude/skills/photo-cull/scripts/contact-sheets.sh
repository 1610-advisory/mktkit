#!/usr/bin/env bash
# contact-sheets.sh — enumerate a photo folder, build labeled thumbnails + batched
# contact sheets you can actually review, and write a manifest mapping the on-sheet
# index (#N) back to the original full-res filename.
#
# Generic across toolkit clients. No client values hardcoded. Pass paths as args.
#
# Usage:
#   contact-sheets.sh --src DIR [--out DIR] [--width PX] [--cols N] [--batch N] [--recurse]
#
#   --src DIR     Folder of photos to review (required). Point it at the finals/edits
#                 subfolder if one exists; otherwise the raw shoot folder.
#   --out DIR     Work dir for thumbs/sheets/manifest (default: /tmp/photo-cull/<src-basename>)
#   --width PX    Thumbnail long-edge width (default 500)
#   --cols N      Contact-sheet columns (default 4)
#   --batch N     Images per contact sheet (default 18 — keep sheets legible when read)
#   --recurse     Recurse into subfolders (default: top level only)
#   --filelist F  Process exactly the paths listed in file F (one per line) instead of
#                 scanning --src. Essential for large galleries (weddings): chunk a huge
#                 folder into slices and render each without copying any files.
#
# Output:
#   <out>/thumbs/NNNN.jpg     labeled thumbnails (label = on-sheet index #N)
#   <out>/sheet-1.jpg ...     contact sheets, ~<batch> images each
#   <out>/manifest.tsv        index<TAB>original-absolute-path   (feeds stage-picks.sh)
#
# Notes baked in from production:
#   - macOS ImageMagick has NO default font; annotate/montage REQUIRE an explicit -font.
#   - RAW (.CR3/.CR2/.NEF/.ARW/.DNG/.RAF) isn't directly viewable — rendered via `sips`.
#   - AppleDouble `._*` sidecars on exFAT/network drives are filtered out.
set -euo pipefail

FONT="/System/Library/Fonts/Supplemental/Arial.ttf"
[ -f "$FONT" ] || FONT="/System/Library/Fonts/Helvetica.ttc"

SRC=""; OUT=""; WIDTH=500; COLS=4; BATCH=18; RECURSE=0; FILELIST=""
while [ $# -gt 0 ]; do
  case "$1" in
    --src)   SRC="$2"; shift 2;;
    --out)   OUT="$2"; shift 2;;
    --width) WIDTH="$2"; shift 2;;
    --cols)  COLS="$2"; shift 2;;
    --batch) BATCH="$2"; shift 2;;
    --recurse) RECURSE=1; shift;;
    --filelist) FILELIST="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
command -v magick >/dev/null || { echo "ERROR: ImageMagick (magick) not found. brew install imagemagick" >&2; exit 2; }
if [ -n "$FILELIST" ]; then
  [ -f "$FILELIST" ] || { echo "ERROR: --filelist must be an existing file" >&2; exit 2; }
  [ -n "$OUT" ] || OUT="/tmp/photo-cull/filelist-$(basename "$FILELIST")"
else
  [ -n "$SRC" ] && [ -d "$SRC" ] || { echo "ERROR: --src must be an existing directory (or use --filelist)" >&2; exit 2; }
  [ -n "$OUT" ] || OUT="/tmp/photo-cull/$(basename "$SRC")"
fi
mkdir -p "$OUT/thumbs"
rm -f "$OUT/thumbs/"*.jpg "$OUT/sheet-"*.jpg "$OUT/manifest.tsv" 2>/dev/null || true

# Enumerate images (sorted, AppleDouble filtered) — from an explicit file list, or by scanning --src.
if [ -n "$FILELIST" ]; then
  grep -v '^[[:space:]]*$' "$FILELIST" | grep -v '/\._' | LC_ALL=C sort > "$OUT/files.txt"
else
  depth=( -maxdepth 1 ); [ "$RECURSE" -eq 1 ] && depth=()
  find "$SRC" "${depth[@]}" -type f \
    \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.heic' \
       -o -iname '*.webp' -o -iname '*.tif' -o -iname '*.tiff' \
       -o -iname '*.cr3' -o -iname '*.cr2' -o -iname '*.nef' -o -iname '*.arw' \
       -o -iname '*.dng' -o -iname '*.raf' \) \
    ! -name '._*' 2>/dev/null | LC_ALL=C sort > "$OUT/files.txt"
fi

N=$(wc -l < "$OUT/files.txt" | tr -d ' ')
[ "$N" -gt 0 ] || { echo "ERROR: no images found under $SRC" >&2; exit 1; }
echo "found $N images in $SRC"

is_raw() { case "${1##*.}" in [Cc][Rr]3|[Cc][Rr]2|[Nn][Ee][Ff]|[Aa][Rr][Ww]|[Dd][Nn][Gg]|[Rr][Aa][Ff]) return 0;; *) return 1;; esac; }

i=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  i=$((i+1))
  idx=$(printf '%04d' "$i")
  printf '%s\t%s\n' "$i" "$f" >> "$OUT/manifest.tsv"
  src_for_magick="$f"
  tmp=""
  if is_raw "$f"; then
    # Render a viewable JPEG preview from the RAW.
    # FAST PATH: extract the embedded JPEG preview with exiftool — no full-raw decode,
    # ~10x faster than sips (matters enormously at wedding scale: minutes vs hours for
    # thousands of 30MB+ raws). FALLBACK: sips (macOS ImageIO) if exiftool is absent or
    # the file has no usable embedded preview.
    tmp="$OUT/thumbs/.raw-$idx.jpg"
    if command -v exiftool >/dev/null 2>&1 \
       && exiftool -b -PreviewImage "$f" > "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
      :  # got the embedded preview
    elif command -v exiftool >/dev/null 2>&1 \
       && exiftool -b -JpgFromRaw "$f" > "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
      :  # some raws expose the full-res JPEG under JpgFromRaw instead
    elif sips -s format jpeg "$f" --out "$tmp" >/dev/null 2>&1 && [ -s "$tmp" ]; then
      :  # slow but reliable
    else
      echo "WARN: could not render RAW preview for $f (skipping)" >&2
      rm -f "$tmp"; continue
    fi
    src_for_magick="$tmp"
  fi
  magick "$src_for_magick" -auto-orient -resize "${WIDTH}x" \
    -background '#111' -gravity south -splice "0x$((WIDTH/15))" \
    -font "$FONT" -fill yellow -pointsize "$((WIDTH/19))" -annotate +0+2 "#$i" \
    "$OUT/thumbs/$idx.jpg" 2>/dev/null || echo "WARN: thumb failed for $f" >&2
  [ -n "$tmp" ] && rm -f "$tmp"
done < "$OUT/files.txt"

# Batch the thumbnails into contact sheets. (Portable to bash 3.2 — no mapfile.)
THUMBS=()
while IFS= read -r line; do THUMBS+=("$line"); done < <(ls "$OUT"/thumbs/*.jpg 2>/dev/null | LC_ALL=C sort)
total=${#THUMBS[@]}
[ "$total" -gt 0 ] || { echo "ERROR: no thumbnails were produced" >&2; exit 1; }
sheet=0; start=0
while [ "$start" -lt "$total" ]; do
  sheet=$((sheet+1))
  batch=( "${THUMBS[@]:start:BATCH}" )
  montage "${batch[@]}" -tile "${COLS}x" -geometry '+6+6' -background '#000' \
    "$OUT/sheet-$sheet.jpg" 2>/dev/null || true
  start=$((start+BATCH))
done

echo "---"
echo "thumbnails: $total  ->  $OUT/thumbs/"
echo "sheets:     $sheet  ->  $OUT/sheet-1.jpg .. $OUT/sheet-$sheet.jpg"
echo "manifest:   $OUT/manifest.tsv  (index -> original path)"
echo "NEXT: Read each sheet, pick the keepers by their #N labels, then run stage-picks.sh."
