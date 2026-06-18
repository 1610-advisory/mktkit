# GA4 Integration

How to set up and pull Google Analytics 4 data for any client. Client-specific property IDs, credentials, and key metrics live in the client's `knowledge/ga4-integration.md`.

---

## Setup

Before first use, the client needs to:

1. **Create a GCP service account** and download JSON key — see `skills/analytics-tracking/references/ga4-data-api.md` for detailed instructions
2. **Add service account as Viewer** on the GA4 property for the client's website
3. **Find the GA4 Property ID** (numeric, NOT the `G-` measurement ID)
4. **Add env vars to `~/.zshrc.local`:**
   ```bash
   export GA4_PROPERTY_ID_[CLIENT]="XXXXXXXXX"
   export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.config/google/ga4-service-account.json"
   ```

## Pulling Data

The GA4 pull script lives in `skills/analytics-tracking/scripts/ga4_pull.py`. It runs via `uv run` (auto-installs dependencies).

```bash
source ~/.zshrc.local
GA4="uv run [path-to-ga4_pull.py] --property-id $GA4_PROPERTY_ID_[CLIENT]"

# Bi-weekly brief data pulls (run all 3 in parallel)
$GA4 top-pages --days 14 --limit 20           # Which pages get traffic
$GA4 traffic-sources --days 14                  # Where traffic comes from
$GA4 content-perf --days 14 --limit 20         # Landing page engagement

# Monthly analysis
$GA4 top-pages --days 30 --limit 50
$GA4 traffic-sources --days 30
$GA4 conversions --days 30

# Save to tracking
$GA4 top-pages --days 30 --format csv > tracking/ga4-top-pages.csv
$GA4 traffic-sources --days 30 --format csv > tracking/ga4-traffic-sources.csv

# Custom: page performance by device
$GA4 report --dimensions "pagePath,deviceCategory" --metrics "sessions,engagementRate" --days 30

# Custom: daily traffic trend
$GA4 report --dimensions "date" --metrics "sessions,activeUsers,newUsers" --days 30

# Realtime check
$GA4 realtime
```

## What to Look For

### In bi-weekly briefs
- Which pages get the most organic traffic (SEO wins to amplify on social)
- Which landing pages have high bounce rates (content/expectation mismatch)
- Traffic source trends — is social growing relative to organic/direct?
- Are link-in-bio clicks showing up as referral traffic?

### In monthly reviews
- Month-over-month traffic trends
- New vs returning visitor ratio
- Top converting pages (form submissions, contact clicks)
- Geographic distribution

### Cross-reference with social data
- When a post goes viral, does site traffic spike?
- Which content themes drive the most website visits?
- Do project reveals generate more site visits than educational content?

## Data Storage

| File | Contents |
|------|----------|
| `tracking/ga4-top-pages.csv` | Latest top pages pull |
| `tracking/ga4-traffic-sources.csv` | Latest traffic sources pull |
| `tracking/ga4-performance.csv` | Combined performance data (from brief pulls) |

## Troubleshooting

- **Credentials error:** Check that the service account JSON exists at the path in `GOOGLE_APPLICATION_CREDENTIALS` and that the service account email has Viewer access on the GA4 property.
- **No data:** Verify the property ID is the numeric GA4 property ID, not the `G-XXXXXXXX` measurement ID.
- **Script not found:** The script path may vary. Check the client's `knowledge/ga4-integration.md` for the exact path.

---

## Client-Specific Config

Each client that uses GA4 should have a `knowledge/ga4-integration.md` containing:
- **Website URL**
- **GA4 property ID env var name** (e.g., `GA4_PROPERTY_ID_ACME`)
- **Service account credentials path**
- **Script path** (may vary by install location)
- **Key pages to track** (e.g., /services, /contact, /portfolio)
- **Custom events** (e.g., form_submit, phone_click, add_to_cart)
- **Key metrics for this client's business** (what matters most for their goals)
