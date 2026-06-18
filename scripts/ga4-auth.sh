#!/bin/bash
# One-time GA4 OAuth setup — run this once, then ga4_pull.py works forever
# Update the paths and property ID for your setup
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
uv run "$SCRIPT_DIR/ga4_pull.py" \
  --oauth-client ~/.config/google/ga4-oauth-client.json \
  --property-id "${GA4_PROPERTY_ID:?Set GA4_PROPERTY_ID env var}" \
  top-pages
