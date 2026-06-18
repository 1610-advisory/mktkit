# HubSpot CRM Integration

How to set up and use HubSpot CRM for lead tracking, pipeline management, and a leads dashboard. Client-specific API tokens, pipeline stages, and dashboard URLs live in the client's `knowledge/hubspot-integration.md`.

---

## Setup

1. **Create a HubSpot Private App:**
   - Go to HubSpot > Settings > Integrations > Private Apps
   - Create a new app with scopes: CRM read/write (contacts, companies, deals, schemas), forms, content
   - Copy the access token (`pat-na2-...`)

2. **Store the token:**
   ```bash
   export HUBSPOT_API_KEY_[CLIENT]="pat-na2-..."
   ```
   Add to `~/.zshrc.local` for persistence.

3. **API base URL:** `https://api.hubapi.com/crm/v3/`

## Common API Patterns

### Get all deals in a pipeline
```bash
source ~/.zshrc.local
curl -s "https://api.hubapi.com/crm/v3/objects/deals?properties=dealname,dealstage,amount,closedate,pipeline&limit=100" \
  -H "Authorization: Bearer ${HUBSPOT_API_KEY_[CLIENT]}"
```

### Get contacts
```bash
curl -s "https://api.hubapi.com/crm/v3/objects/contacts?properties=firstname,lastname,email,phone,lifecyclestage&limit=100" \
  -H "Authorization: Bearer ${HUBSPOT_API_KEY_[CLIENT]}"
```

### Create a deal
```bash
curl -s -X POST "https://api.hubapi.com/crm/v3/objects/deals" \
  -H "Authorization: Bearer ${HUBSPOT_API_KEY_[CLIENT]}" \
  -H "Content-Type: application/json" \
  -d '{"properties": {"dealname": "...", "pipeline": "[PIPELINE_ID]", "dealstage": "[STAGE_ID]", "amount": "..."}}'
```

### Get pipeline stages
```bash
curl -s "https://api.hubapi.com/crm/v3/pipelines/deals" \
  -H "Authorization: Bearer ${HUBSPOT_API_KEY_[CLIENT]}"
```

## Pipeline Management

Each client defines their own pipeline stages in `knowledge/hubspot-integration.md`. Common patterns:

| Stage | Type | Meaning |
|-------|------|---------|
| New Lead | Open | Initial inquiry, not yet contacted |
| Consultation | Open | Meeting scheduled or completed |
| Estimating | Open | Working on proposal/estimate |
| Proposal Presented | Open | Waiting for decision |
| Closed Won | Closed | Deal signed |
| Closed Lost | Closed | Declined or went elsewhere |
| Disqualified | Closed | Not a fit (spam, wrong market, etc.) |

**General rules:**
- Sales tracking ends at Closed Won. Post-sale tracking uses deal properties, not pipeline stages.
- Don't move deals backward in the pipeline (e.g., from Proposal Presented back to New Lead).
- Disqualified = spam, wrong fit, tire kickers. Exclude from close rate metrics.
- Spam contacts: disqualify the deal, delete the contact.

## Leads Dashboard

A live dashboard can be built as a Node.js + Express app that pulls from the HubSpot API.

**Architecture:**
- Backend: Node.js + Express
- Frontend: Vanilla HTML/CSS/JS + Chart.js (CDN)
- Auth: HubSpot Private App token
- Cache: 5-minute TTL, refresh button for instant update
- Deployment: Docker container on a VPS, reverse-proxied via Nginx

**Common dashboard sections:**
- KPI cards (total leads, pipeline value, close rate)
- Pipeline stage distribution chart
- Monthly lead trends
- Close rates by time period
- Won revenue by period
- Lead source breakdown
- Lead triage table (actionable: stale deals, missing info)

**Deployment pattern:**
```bash
rsync -avz --exclude node_modules ~/[dashboard-folder]/ [server]:~/[dashboard-folder]/
ssh [server] "cd ~/[dashboard-folder] && docker compose up -d --build"
```

## Revenue Attribution

When the client has HubSpot integrated, lead and revenue tracking can be pulled directly from the CRM instead of manual CSV logging. Cross-reference deal sources with content tracking data to identify which content drives the most valuable leads.

---

## Client-Specific Config

Each client that uses HubSpot should have a `knowledge/hubspot-integration.md` containing:
- **API token env var name** (e.g., `HUBSPOT_API_KEY_ACME`)
- **Pipeline ID** and stage definitions with IDs
- **Lead statuses** used for this client
- **Leads dashboard URL** (if deployed)
- **Dashboard source folder** and deployment commands
- **Legacy pipelines** (if migrated from an older pipeline setup)
- **CRM audit reports** (if they exist, reference the file paths)
