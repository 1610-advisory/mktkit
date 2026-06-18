#!/usr/bin/env bash
# Scaffold a new carousel project folder for the ai-cmo:carousel-slides skill.
#
# Usage:
#   init-carousel.sh <target-dir>
#
# Copies slide-template.html → slides.html and render.js into <target-dir>,
# initializes a package.json, and installs Playwright (Chromium) for rendering.
#
# Safe to re-run: existing slides.html and render.js are left alone.

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <target-dir>" >&2
  exit 1
fi

TARGET="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REF_DIR="${SKILL_ROOT}/references"

mkdir -p "${TARGET}"
cd "${TARGET}"

if [[ ! -f slides.html ]]; then
  cp "${REF_DIR}/slide-template.html" slides.html
  echo "wrote slides.html (copy of slide-template.html — edit brand vars + slides next)"
else
  echo "slides.html already exists — left alone"
fi

if [[ ! -f render.js ]]; then
  cp "${REF_DIR}/render.js" render.js
  echo "wrote render.js"
else
  echo "render.js already exists — left alone"
fi

if [[ ! -f package.json ]]; then
  npm init -y >/dev/null
  echo "wrote package.json"
fi

if [[ ! -d node_modules/playwright ]]; then
  echo "installing playwright..."
  npm install playwright --silent
  npx playwright install chromium
else
  echo "playwright already installed"
fi

echo
echo "Done. Next:"
echo "  1. Edit ${TARGET}/slides.html: replace :root brand vars, photo paths, slide content"
echo "  2. Open slides.html in a browser to proof"
echo "  3. cd ${TARGET} && node render.js  (writes slide-N.png)"
