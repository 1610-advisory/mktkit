#!/usr/bin/env bash
# stage-picks.sh — copy the chosen full-res photos, in the order given, into a single
# staging folder with slot-numbered names. Resolves on-sheet indices (#N) back to the
# original files via the manifest written by contact-sheets.sh.
#
# Generic across toolkit clients. No client values hardcoded.
#
# Usage:
#   stage-picks.sh --manifest FILE --picks "11,3,44,9" --dest DIR [--prefix STR]
#
#   --manifest FILE  manifest.tsv from contact-sheets.sh (index<TAB>original-path)
#   --picks LIST     ordered on-sheet indices to keep, comma- or space-separated.
#                    Order = deliverable/posting order. Duplicates are allowed (e.g. a
#                    hero you also want later); each becomes its own slot.
#   --dest DIR       staging folder to create/fill (e.g. <project>/<date>/Photos/_to-edit)
#   --prefix STR     optional filename prefix (default: none). Output is NN[_PREFIX]_orig.ext
#
# Output: --dest/01_<origname>, 02_<origname>, ...  (full-res, byte-for-byte copies)
#         --dest/_pick-order.tsv  (slot<TAB>index<TAB>source) for traceability
#
# AppleDouble `._*` sidecars are never copied and are swept from --dest after.
set -euo pipefail

MANIFEST=""; PICKS=""; DEST=""; PREFIX=""
while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2;;
    --picks)    PICKS="$2"; shift 2;;
    --dest)     DEST="$2"; shift 2;;
    --prefix)   PREFIX="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$MANIFEST" ] && [ -f "$MANIFEST" ] || { echo "ERROR: --manifest must be an existing file" >&2; exit 2; }
[ -n "$PICKS" ] || { echo "ERROR: --picks is required" >&2; exit 2; }
[ -n "$DEST" ] || { echo "ERROR: --dest is required" >&2; exit 2; }

mkdir -p "$DEST"
: > "$DEST/_pick-order.tsv"

# Normalize picks: commas -> spaces, collapse whitespace.
picks_norm=$(printf '%s' "$PICKS" | tr ',' ' ')

slot=0; missing=0
for idx in $picks_norm; do
  [ -n "$idx" ] || continue
  # Resolve index -> original path from manifest (exact match on first column).
  src=$(awk -F'\t' -v want="$idx" '$1==want {print $2; exit}' "$MANIFEST")
  if [ -z "$src" ] || [ ! -f "$src" ]; then
    echo "WARN: pick #$idx not found in manifest (or file missing) — skipping" >&2
    missing=$((missing+1))
    continue
  fi
  slot=$((slot+1))
  ext="${src##*.}"
  base=$(basename "$src"); stem="${base%.*}"
  name=$(printf '%02d' "$slot")
  [ -n "$PREFIX" ] && name="${name}_${PREFIX}"
  out="$DEST/${name}_${stem}.${ext}"
  cp "$src" "$out"
  printf '%s\t%s\t%s\n' "$slot" "$idx" "$src" >> "$DEST/_pick-order.tsv"
done

# Sweep AppleDouble sidecars the copy may have created on exFAT/network targets.
find "$DEST" -name '._*' -delete 2>/dev/null || true

echo "staged $slot photos -> $DEST"
[ "$missing" -gt 0 ] && echo "($missing pick(s) skipped — see warnings above)"
echo "order recorded in $DEST/_pick-order.tsv"
du -sh "$DEST" 2>/dev/null || true
