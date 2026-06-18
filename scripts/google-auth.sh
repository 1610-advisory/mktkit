#!/bin/bash
# Master Google OAuth — authenticates with ALL scopes at once
# Run this once. Covers: GA4, Google Ads, Search Console
rm -f ~/.config/google/ga4-token.json

cat > /tmp/google_auth_all.py << 'PYEOF'
# /// script
# requires-python = ">=3.11"
# dependencies = ["google-auth-oauthlib>=1.0.0", "google-auth>=2.0.0"]
# ///
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

TOKEN_PATH = Path.home() / ".config" / "google" / "ga4-token.json"
CLIENT_FILE = Path.home() / ".config" / "google" / "ga4-oauth-client.json"

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/webmasters.readonly",
]

if not CLIENT_FILE.exists():
    print(f"Error: OAuth client not found at {CLIENT_FILE}")
    sys.exit(1)

flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
creds = flow.run_local_server(port=0)

TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
TOKEN_PATH.write_text(creds.to_json())
print(f"\nToken saved with all scopes: {TOKEN_PATH}")
print("Scopes:", SCOPES)
PYEOF

uv run /tmp/google_auth_all.py
