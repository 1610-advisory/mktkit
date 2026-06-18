# GA4 Data API Reference

Pull analytics data from Google Analytics 4 using the `ga4_pull.py` script. Uses the official Google Analytics Data API v1beta with a service account.

## Setup

### 1. Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use existing)
3. Enable **Google Analytics Data API** in APIs & Services > Library

### 2. Service Account

1. IAM & Admin > Service Accounts > Create Service Account
2. Name it (e.g., `ga4-reader`)
3. No roles needed at the project level
4. Keys tab > Add Key > Create New Key > JSON
5. Save the JSON file securely (e.g., `~/.config/google/ga4-service-account.json`)

### 3. Grant GA4 Access

1. Go to Google Analytics > Admin > Property Access Management
2. Add the service account email (from the JSON file's `client_email` field)
3. Grant **Viewer** role

### 4. Environment Variables

Add to `~/.zshrc.local` (or equivalent):

```bash
# GA4 Data API — per-client pattern: GA4_PROPERTY_ID_[CLIENT]
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/google/ga4-service-account.json"
export GA4_PROPERTY_ID="123456789"  # Numeric property ID, NOT the G- measurement ID
```

Find your property ID: Google Analytics > Admin > Property Details (numeric ID, e.g., `123456789`)

### 5. Install uv (if not already)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Usage

All commands use `uv run` which auto-installs dependencies in an ephemeral venv.

```bash
# Source env vars
source ~/.zshrc.local

# Top pages by sessions (last 30 days)
uv run ga4_pull.py top-pages

# Traffic sources breakdown
uv run ga4_pull.py traffic-sources --days 14

# Landing page engagement (great for content strategy)
uv run ga4_pull.py content-perf --days 30 --limit 50

# Conversion events
uv run ga4_pull.py conversions --days 30

# Active users right now
uv run ga4_pull.py realtime

# Custom report — any dimensions/metrics combo
uv run ga4_pull.py report \
  --dimensions "pagePath,sessionDefaultChannelGrouping" \
  --metrics "sessions,engagementRate,conversions" \
  --days 14

# CSV output (for saving to tracking files)
uv run ga4_pull.py top-pages --format csv --days 30 > tracking/ga4-top-pages.csv
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--property-id` | `$GA4_PROPERTY_ID` | GA4 numeric property ID |
| `--credentials` | `$GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON |
| `--format` | `json` | Output format: `json` or `csv` |
| `--days` | `30` | Lookback period in days |
| `--limit` | `25` | Max rows returned |

### Commands

| Command | What it pulls | Key metrics |
|---------|--------------|-------------|
| `top-pages` | Pages ranked by sessions | sessions, pageviews, engagement rate, avg session duration |
| `traffic-sources` | Channel / source / medium | sessions, users, engagement rate, conversions |
| `content-perf` | Landing pages with engagement | sessions, bounce rate, engagement rate, conversions |
| `conversions` | All events ranked by count | event count, total users |
| `realtime` | Active users by page | active users per page |
| `report` | Custom dimensions + metrics | whatever you specify |

## Common Dimensions & Metrics

### Dimensions
- `pagePath`, `pageTitle`, `landingPagePlusQueryString`
- `sessionDefaultChannelGrouping`, `sessionSource`, `sessionMedium`
- `deviceCategory`, `city`, `country`
- `date`, `dayOfWeek`, `hour`
- `eventName`, `firstUserSource`, `newVsReturning`

### Metrics
- `sessions`, `activeUsers`, `newUsers`, `totalUsers`
- `screenPageViews`, `engagementRate`, `bounceRate`
- `averageSessionDuration`, `sessionsPerUser`
- `conversions`, `eventCount`

Full list: [GA4 API Dimensions & Metrics](https://developers.google.com/analytics/devguides/reporting/data/v1/api-schema)

## Multi-Client Setup

For multiple clients, use per-client env vars:

```bash
# In ~/.zshrc.local
export GA4_PROPERTY_ID_CLIENTA="123456789"
export GA4_PROPERTY_ID_CLIENTB="987654321"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/google/ga4-service-account.json"
```

Then call with explicit property ID:

```bash
uv run ga4_pull.py --property-id $GA4_PROPERTY_ID_CLIENTA top-pages
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| `PERMISSION_DENIED` | Service account not added to GA4 property, or wrong property ID |
| `NOT_FOUND` | Wrong property ID — use numeric ID, not `G-` measurement ID |
| `UNAUTHENTICATED` | Credentials file missing or invalid — check path |
| `API not enabled` | Enable "Google Analytics Data API" in GCP console |
| Empty results | Check date range — property may not have data for that period |
