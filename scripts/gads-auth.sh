#!/bin/bash
# One-time Google Ads + GA4 OAuth setup — re-auth with both scopes
# Update the customer ID for your setup
source ~/.zshrc.local 2>/dev/null
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
uv run "$SCRIPT_DIR/gads_pull.py" \
  --oauth-client ~/.config/google/ga4-oauth-client.json \
  --customer-id "${GOOGLE_ADS_CUSTOMER_ID:?Set GOOGLE_ADS_CUSTOMER_ID env var}" \
  campaigns --days 7
