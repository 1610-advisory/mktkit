# Marketing Analytics Dashboard

How to build and deploy a live analytics dashboard for a client. Pulls from GA4, Search Console, Google Ads, and other data sources into a single view. Client-specific URLs, property IDs, and deployment details live in the client's `knowledge/marketing-dashboard.md`.

---

## Overview

A marketing dashboard gives the client (and the CMO) a single place to see all key metrics without logging into multiple platforms. It's a web app deployed to a VPS that pulls data from Google APIs.

## Architecture

| Component | Technology |
|-----------|-----------|
| **Backend** | Node.js + Express |
| **Frontend** | Vanilla HTML/CSS/JS + Chart.js (CDN) |
| **Auth** | OAuth2 refresh token (Google APIs) |
| **GA4** | `@google-analytics/data` npm package |
| **Search Console** | `googleapis` npm package |
| **Google Ads** | REST API (searchStream endpoint) |
| **Cache** | 5-minute TTL, refresh button bypasses |
| **Deployment** | Docker container on VPS, reverse-proxied via Nginx |

## Data Sources

| Source | What it provides |
|--------|-----------------|
| **GA4** | Sessions, users, engagement, pages, traffic sources, form conversions |
| **Search Console** | Organic keywords, rankings, impressions, CTR, SEO opportunities |
| **Google Ads** | Campaign spend, CPC, clicks, impressions, conversions, ad groups |

## Dashboard Sections

1. **KPI Cards** — Sessions, users, engagement rate, organic clicks, avg position, form submissions (30d with period-over-period comparison)
2. **Daily Sessions Chart** — 30-day trend line
3. **Traffic Sources Chart** — Channel breakdown bar chart
4. **Engagement by Source** — Engagement rate vs bounce rate by channel
5. **Conversion Funnel** — Form start -> form submission -> qualifiers (if applicable)
6. **Google Ads** — Campaign table with spend/clicks/conversions + ad group breakdown (if running ads)
7. **Top Pages** — GA4 sessions + GSC organic clicks merged into one table
8. **Top Search Queries** — GSC keywords ranked by clicks
9. **SEO Opportunities** — High-impression, low-CTR queries where ranking improvement would drive traffic

## Setup

### 1. Google API Credentials

All three data sources (GA4, GSC, Google Ads) can share the same OAuth2 credentials:

```
GOOGLE_CLIENT_ID=[from GCP console]
GOOGLE_CLIENT_SECRET=[from GCP console]
GOOGLE_REFRESH_TOKEN=[from OAuth flow]
```

Run the OAuth flow once to get the refresh token. Store in `.env` on the server.

### 2. Data Source IDs

```
GA4_PROPERTY_ID=[numeric property ID]
GSC_SITE_URL=sc-domain:[domain.com]
GOOGLE_ADS_DEVELOPER_TOKEN=[from Google Ads API Center]
GOOGLE_ADS_MCC_ID=[MCC account ID]
GOOGLE_ADS_CUSTOMER_ID=[client account ID]
```

### 3. Deployment

```bash
# Deploy / update
rsync -avz --exclude node_modules --exclude .env ~/[dashboard-folder]/ [server]:~/[dashboard-folder]/
ssh [server] "cd ~/[dashboard-folder] && docker compose up -d --build"

# Check logs
ssh [server] "docker logs [container-name]"

# Restart
ssh [server] "cd ~/[dashboard-folder] && docker compose restart"
```

### 4. Nginx Reverse Proxy

Set up an Nginx site config on the server pointing to the Docker container's internal port. Use Certbot for SSL.

## When to Build a Dashboard

Not every client needs a custom dashboard. Consider building one when:
- The client has GA4 + Search Console (minimum viable data sources)
- The client wants to see metrics without logging into platforms
- Multiple team members need access to analytics
- You want to track conversion funnels specific to the client's business

For simpler setups, the GA4 pull script (`ga4_pull.py`) and manual performance tracking in CSVs are sufficient.

## Related

- GA4 integration: `references/ga4-integration.md` (setup + data pull scripts)
- Local analytics scripts: `skills/analytics-tracking/scripts/` (ga4_pull.py, gsc_pull.py, gads_pull.py)

---

## Client-Specific Config

Each client that has a dashboard should have a `knowledge/marketing-dashboard.md` containing:
- **Dashboard URL**
- **Local source folder path**
- **Server hostname and IP**
- **Docker container name and port mapping**
- **Nginx config path on server**
- **GA4 property ID**
- **Search Console site URL**
- **Google Ads account IDs** (developer token, MCC ID, customer ID)
- **GTM container ID** (if using Google Tag Manager for event tracking)
- **Deploy commands** (rsync + docker compose)
