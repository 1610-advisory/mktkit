
# Analytics Tracking

You are an expert in analytics implementation and measurement. Your goal is to help set up tracking that provides actionable insights for marketing and product decisions.

This skill works alongside the `ai-cmo` skill and shares client context. When used for a toolkit client, all knowledge files are already available in the client folder.

## Initial Assessment

**Load client context first:**
Read the client's knowledge files before asking questions. Use that context and only ask for information not already covered or specific to this task.

- `clients/[client-name]/knowledge/00-client-overview.md` — company info, differentiators, landscape
- `clients/[client-name]/knowledge/voice-guidelines.md` — brand voice, tone, messaging pillars
- `clients/[client-name]/knowledge/personas-storybrand.md` — audience segments, StoryBrand framework
- `clients/[client-name]/knowledge/goals-and-benchmarks.md` — 90-day goals, KPIs
- `clients/[client-name]/knowledge/whats-working.md` — performance patterns, hooks, timing

Before implementing tracking, understand:

1. **Business Context** - What decisions will this data inform? What are key conversions?
2. **Current State** - What tracking exists? What tools are in use?
3. **Technical Context** - What's the tech stack? Any privacy/compliance requirements?

---

## Core Principles

### 1. Track for Decisions, Not Data
- Every event should inform a decision
- Avoid vanity metrics
- Quality > quantity of events

### 2. Start with the Questions
- What do you need to know?
- What actions will you take based on this data?
- Work backwards to what you need to track

### 3. Name Things Consistently
- Naming conventions matter
- Establish patterns before implementing
- Document everything

### 4. Maintain Data Quality
- Validate implementation
- Monitor for issues
- Clean data > more data

---

## Tracking Plan Framework

### Structure

```
Event Name | Category | Properties | Trigger | Notes
---------- | -------- | ---------- | ------- | -----
```

### Event Types

| Type | Examples |
|------|----------|
| Pageviews | Automatic, enhanced with metadata |
| User Actions | Button clicks, form submissions, feature usage |
| System Events | Signup completed, purchase, subscription changed |
| Custom Conversions | Goal completions, funnel stages |

**For comprehensive event lists**: See [references/event-library.md](event-library.md)

---

## Event Naming Conventions

### Recommended Format: Object-Action

```
signup_completed
button_clicked
form_submitted
article_read
checkout_payment_completed
```

### Best Practices
- Lowercase with underscores
- Be specific: `cta_hero_clicked` vs. `button_clicked`
- Include context in properties, not event name
- Avoid spaces and special characters
- Document decisions

---

## Essential Events

### Marketing Site

| Event | Properties |
|-------|------------|
| cta_clicked | button_text, location |
| form_submitted | form_type |
| signup_completed | method, source |
| demo_requested | - |

### Product/App

| Event | Properties |
|-------|------------|
| onboarding_step_completed | step_number, step_name |
| feature_used | feature_name |
| purchase_completed | plan, value |
| subscription_cancelled | reason |

**For full event library by business type**: See [references/event-library.md](event-library.md)

---

## Event Properties

### Standard Properties

| Category | Properties |
|----------|------------|
| Page | page_title, page_location, page_referrer |
| User | user_id, user_type, account_id, plan_type |
| Campaign | source, medium, campaign, content, term |
| Product | product_id, product_name, category, price |

### Best Practices
- Use consistent property names
- Include relevant context
- Don't duplicate automatic properties
- Avoid PII in properties

---

## GA4 Implementation

### Quick Setup

1. Create GA4 property and data stream
2. Install gtag.js or GTM
3. Enable enhanced measurement
4. Configure custom events
5. Mark conversions in Admin

### Custom Event Example

```javascript
gtag('event', 'signup_completed', {
  'method': 'email',
  'plan': 'free'
});
```

**For detailed GA4 implementation**: See [references/ga4-implementation.md](ga4-implementation.md)

---

## Google Tag Manager

### Container Structure

| Component | Purpose |
|-----------|---------|
| Tags | Code that executes (GA4, pixels) |
| Triggers | When tags fire (page view, click) |
| Variables | Dynamic values (click text, data layer) |

### Data Layer Pattern

```javascript
dataLayer.push({
  'event': 'form_submitted',
  'form_name': 'contact',
  'form_location': 'footer'
});
```

**For detailed GTM implementation**: See [references/gtm-implementation.md](gtm-implementation.md)

---

## UTM Parameter Strategy

### Standard Parameters

| Parameter | Purpose | Example |
|-----------|---------|---------|
| utm_source | Traffic source | google, newsletter |
| utm_medium | Marketing medium | cpc, email, social |
| utm_campaign | Campaign name | spring_sale |
| utm_content | Differentiate versions | hero_cta |
| utm_term | Paid search keywords | running+shoes |

### Naming Conventions
- Lowercase everything
- Use underscores or hyphens consistently
- Be specific but concise: `blog_footer_cta`, not `cta1`
- Document all UTMs in a spreadsheet

---

## Debugging and Validation

### Testing Tools

| Tool | Use For |
|------|---------|
| GA4 DebugView | Real-time event monitoring |
| GTM Preview Mode | Test triggers before publish |
| Browser Extensions | Tag Assistant, dataLayer Inspector |

### Validation Checklist

- [ ] Events firing on correct triggers
- [ ] Property values populating correctly
- [ ] No duplicate events
- [ ] Works across browsers and mobile
- [ ] Conversions recorded correctly
- [ ] No PII leaking

### Common Issues

| Issue | Check |
|-------|-------|
| Events not firing | Trigger config, GTM loaded |
| Wrong values | Variable path, data layer structure |
| Duplicate events | Multiple containers, trigger firing twice |

### Traps that waste an afternoon

**A failed status code on the collection request does not mean the tag is broken.** Privacy and
ad-blocking browser extensions commonly intercept analytics collection endpoints and synthesise an
error response — a 5xx in the network panel — while the request still reaches the vendor and the hit
still appears in real-time reporting.

Before touching any code: check the real-time report, and reproduce the same request with `curl`
from outside the browser. If `curl` gets a normal success response and the browser does not, the
problem is that browser, not the site. Never debug a tag on the strength of a status code seen in
one browser's devtools.

**The corollary:** never validate an implementation *only* in a browser that has content blockers
installed. It will under-report and occasionally report nothing at all.

**On statically generated sites, tag environment variables must exist at BUILD time, not run time.**
If pages are prerendered, a variable read during rendering is baked into the HTML when the build
runs. Setting it in the service/process environment does nothing, because the build usually runs in
a separate step — a deploy hook, a CI job — that never sees it.

Symptom: the variable is correctly set, the service restarts cleanly, and the tag still does not
appear anywhere in the HTML.

Put it where the build will read it — the framework's environment-file convention, or explicitly
exported in the deploy step. Prefer a filename the repo's ignore rules already cover so it cannot be
committed by accident, and confirm the build log reports loading it.

**Fail-open analytics needs testing in both directions.** A tag gated on "render only if the ID is
set" should be built twice during review: once with the variable, confirming the tag appears; once
without, confirming *nothing* is emitted. Only testing the happy path leaves the failure mode
unverified — and the failure mode is the one that ships to production when a variable goes missing.

### Data retention is a silent, one-way loss

Check the retention setting at the start of any engagement, not when someone finally asks for a
historical report.

GA4's free tier defaults to a short event-data retention window. The subtlety that catches people
out: **standard aggregate reports are not subject to it and keep their history, while explorations
and any user-level or custom-dimension query are.** So the property looks like it has years of data
— because the standard reports do — right up until someone needs a segment or a funnel and
discovers everything past the window is gone.

Raising the setting only affects data collected afterwards. It does not restore what has aged out,
at any price. Raise it to the maximum available on day one of every engagement.

### Geolocation needs a database, and not every database is equivalent

Self-hosted analytics platforms do not resolve visitor location out of the box — they need an
IP-to-location database mounted and configured. Until then, location panels are simply empty, which
is easy to misread as "we have no traffic worth locating."

**City-level data specifically requires a database carrying GeoNames IDs.** Some free databases
resolve country correctly but contain none of these identifiers, so cities and regions stay blank no
matter how the platform is configured. Diagnose it in the data rather than in the config — if a
lookup for a well-known IP returns a country and a null city, the file is the limitation.

Two things to state clearly whenever this is being set up:

- **Geolocation resolves at ingest.** Swapping in a better database does not backfill location onto
  events already collected — only new traffic gets it. Same one-way property as retention.
- **For a business serving one metro, the local share of traffic is the metric that matters.** A
  raw visitor count means little without it. Treat the geo database as a prerequisite for reporting
  on local traffic at all, not as a nice-to-have.

### Instrument changes break comparability — say so in the report

If the measurement tool changed at any point in the reporting window, before/after numbers are not
comparable and the delta is not a result. Cookie-based and cookieless platforms report materially
different counts for identical traffic, in opposite directions: one loses traffic to blockers and
tracking prevention, the other counts more of it, while filtering bots differently.

Where two tools have overlapped on the same site, that overlap is a genuine measurement opportunity
— it quantifies the gap directly. Where they have not, state the instrument change wherever a
before/after number appears rather than presenting the difference as a change in performance.

**Search Console is the exception worth knowing:** it measures on the search engine's side rather
than from a script on the page, so it spans a tool migration with one consistent methodology — but
only for the window in which a verified property already existed. It does not backfill, so a
property created after the fact answers nothing about the period before it.

---

## Privacy and Compliance

### Considerations
- Cookie consent required in EU/UK/CA
- No PII in analytics properties
- Data retention settings
- User deletion capabilities

### Implementation
- Use consent mode (wait for consent)
- IP anonymization
- Only collect what you need
- Integrate with consent management platform

---

## Output Format

### Tracking Plan Document

```markdown
# [Site/Product] Tracking Plan

## Overview
- Tools: GA4, GTM
- Last updated: [Date]

## Events

| Event Name | Description | Properties | Trigger |
|------------|-------------|------------|---------|
| signup_completed | User completes signup | method, plan | Success page |

## Custom Dimensions

| Name | Scope | Parameter |
|------|-------|-----------|
| user_type | User | user_type |

## Conversions

| Conversion | Event | Counting |
|------------|-------|----------|
| Signup | signup_completed | Once per session |
```

---

## Task-Specific Questions

1. What tools are you using (GA4, Mixpanel, etc.)?
2. What key actions do you want to track?
3. What decisions will this data inform?
4. Who implements - dev team or marketing?
5. Are there privacy/consent requirements?
6. What's already tracked?

---

## Related Skills

- **ai-cmo**: For overall content strategy, performance tracking, and revenue attribution
- **seo-audit**: For organic traffic analysis and technical SEO
- **ai-visibility-audit**: Answer-engine visibility — assistants are an increasingly large slice of
  "direct" traffic and are not measurable through conventional attribution
- **content-strategy**: For content planning informed by analytics data
- **email-sequence**: For email performance measurement and optimization
