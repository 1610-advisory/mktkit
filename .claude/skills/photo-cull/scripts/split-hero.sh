#!/usr/bin/env bash
# split-hero.sh — split one landscape photo into two seamless 4:5 halves so a carousel
# opens with a "swipe to reveal one continuous image" effect (slides 01 + 02).
#
# Generic helper. The combined output is two 4:5 panels that line up edge-to-edge; when
# posted as the first two carousel slides, swiping reveals the original wide shot.
#
# Usage:
#   split-hero.sh --src FILE --dest DIR [--start SLOT] [--ratio W:H]
#
#   --src FILE    a LANDSCAPE photo (wider than tall) to use as the hero
#   --dest DIR    folder to write the two halves into
#   --start SLOT  starting slot number (default 1 -> writes 01.jpg, 02.jpg)
#   --ratio W:H   per-slide aspect (default 4:5 = Instagram portrait). Each half targets this.
#
# Math: to make two side-by-side W:H panels from one image, the source is center-cropped
# to a combined (2W):H aspect, then split down the middle. Each half is exactly W:H, so
# resizing to the post size never distorts.
set -euo pipefail

SRC=""; DEST=""; START=1; RATIO="4:5"
while [ $# -gt 0 ]; do
  case "$1" in
    --src)   SRC="$2"; shift 2;;
    --dest)  DEST="$2"; shift 2;;
    --start) START="$2"; shift 2;;
    --ratio) RATIO="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "ERROR: --src must be an existing file" >&2; exit 2; }
[ -n "$DEST" ] || { echo "ERROR: --dest is required" >&2; exit 2; }
command -v magick >/dev/null || { echo "ERROR: ImageMagick (magick) not found" >&2; exit 2; }
mkdir -p "$DEST"

RW="${RATIO%%:*}"; RH="${RATIO##*:}"

read -r IW IH < <(magick identify -format '%w %h\n' "$SRC")
if [ "$IW" -le "$IH" ]; then
  echo "ERROR: --src is not landscape (${IW}x${IH}). The split-hero opener needs a wide image." >&2
  exit 1
fi

# Combined target aspect = (2*RW):RH. Fit the largest such rectangle inside the source.
# combined ratio r = (2*RW)/RH. If IW/IH > r, height-bound; else width-bound.
# Use integer-safe comparison via awk.
read -r CW CH OX OY < <(awk -v iw="$IW" -v ih="$IH" -v rw="$RW" -v rh="$RH" 'BEGIN{
  r=(2*rw)/rh;
  if (iw/ih > r) { ch=ih; cw=int(ih*r); } else { cw=iw; ch=int(iw/r); }
  cw=cw-(cw%2);                # keep even so the two halves are equal integer widths
  ox=int((iw-cw)/2); oy=int((ih-ch)/2);
  print cw, ch, ox, oy;
}')

HALF=$((CW/2))
S1=$(printf '%02d' "$START")
S2=$(printf '%02d' "$((START+1))")

magick "$SRC" -auto-orient -crop "${HALF}x${CH}+${OX}+${OY}"            +repage -quality 95 "$DEST/$S1.jpg"
magick "$SRC" -auto-orient -crop "${HALF}x${CH}+$((OX+HALF))+${OY}"     +repage -quality 95 "$DEST/$S2.jpg"

# Seam check: stitch the halves back and confirm they recombine.
magick "$DEST/$S1.jpg" "$DEST/$S2.jpg" +append -resize 1200x "$DEST/.seam-check.jpg" 2>/dev/null || true

echo "split hero -> $DEST/$S1.jpg + $DEST/$S2.jpg  (each ${HALF}x${CH}, target ${RATIO})"
echo "seam check -> $DEST/.seam-check.jpg  (READ it: the join should be invisible, nothing important bisected)"
