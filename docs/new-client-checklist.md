# New Client Onboarding Checklist

Use this checklist when onboarding a new client to the 1610 Marketing Toolkit.

---

## Quick Start Command

```
new client [client-name]
```

This command will:
1. Create a new folder in `clients/[client-name]/`
2. Copy all templates to the client folder
3. Guide you through completing each file

---

## Phase 1: Discovery

### Initial Information Gathering

- [ ] **Kickoff call scheduled and completed**
  - Record the call for reference
  - Key attendees: decision maker, subject matter expert, day-to-day contact

- [ ] **Basic company information collected**
  - Company name, website, industry
  - Years in business
  - Team size
  - Location(s)

- [ ] **Business model understood**
  - Products/services offered
  - Pricing model
  - Target customer type (B2B/B2C)
  - Sales cycle length
  - Average deal size

- [ ] **Current marketing state assessed**
  - Active social platforms
  - Current follower counts
  - Posting frequency
  - Who manages marketing currently
  - Tools/platforms used

- [ ] **Historical context gathered**
  - Past marketing efforts and results
  - What's been tried before
  - Why previous approaches did/didn't work
  - Any campaigns to reference

- [ ] **Complete `00-client-overview.md`**

---

## Phase 2: Brand & Voice

### Voice Discovery

- [ ] **Brand personality defined**
  - Ask: "If your brand was a person, how would you describe them?"
  - Ask: "What 3-5 words describe how you want to come across?"
  - Ask: "Who are brands you admire (even outside your industry)?"

- [ ] **Voice examples collected**
  - Gather 3-5 examples of content they love (theirs or others')
  - Gather 3-5 examples of content that feels wrong for them
  - Note specific language patterns they use

- [ ] **Language preferences documented**
  - Industry jargon: use it or avoid it?
  - Formal vs. casual
  - Contractions (yes/no)
  - Emoji usage preferences

- [ ] **Messaging pillars identified**
  - What are the 3 main themes you want to be known for?
  - What proof points support each pillar?

- [ ] **Complete `voice-guidelines.md`**

---

## Phase 3: Customer Intelligence

### Audience Research

- [ ] **Primary personas defined**
  - Demographics (age, role, location)
  - Psychographics (values, motivations, fears)
  - Where they spend time online
  - How they make decisions

- [ ] **Customer interviews conducted** (ideal: 3-5)
  - How did you find us?
  - What problem were you trying to solve?
  - What made you choose us?
  - What almost stopped you?
  - How would you describe us to a friend?

- [ ] **Review mining completed**
  - Analyze client's reviews (Google, Facebook, etc.)
  - Analyze competitor reviews
  - Document actual customer language

- [ ] **StoryBrand framework completed**
  - Character (customer) defined
  - External, internal, philosophical problems
  - Guide positioning established
  - Plan articulated
  - CTAs defined
  - Stakes (success and failure) clear

- [ ] **One-liner created and approved**

- [ ] **Complete `personas-storybrand.md`**

---

## Phase 4: Strategic Context

### Goals & Measurement

- [ ] **90-day goals defined**
  - Primary goal with specific metric
  - 2-3 supporting goals
  - Current baseline for each

- [ ] **KPIs established**
  - Primary KPIs (1-3)
  - Secondary KPIs (2-4)
  - Platform-specific targets

- [ ] **Benchmarks set**
  - Current performance baselines
  - Industry benchmarks for context
  - Realistic targets based on resources

- [ ] **Competitive analysis completed**
  - Top 3 competitors identified
  - Their positioning documented
  - Differentiation opportunities noted

- [ ] **Seasonal considerations mapped**
  - Key dates and events
  - Busy/slow seasons
  - Content implications

- [ ] **Complete `goals-and-benchmarks.md`**

---

## Phase 5: Operational Setup

### Workflow Configuration

- [ ] **Content workflow established**
  - Who approves content?
  - What's the review process?
  - What are the deadlines?
  - Who has posting access?

- [ ] **Communication channels set**
  - Primary contact method
  - Response time expectations
  - Escalation process

- [ ] **Tracking systems configured**
  - Content-log.csv initialized (or Google Sheet created)
  - Performance.csv initialized (or Google Sheet created)
  - Revenue-attribution.csv initialized (or Google Sheet created)
  - Tracking cadence agreed upon

- [ ] **Integrations configured (optional)**
  - Google Drive: shared folder created, folder ID documented in client config
  - Google Sheets: spreadsheet(s) created for tracking data, IDs documented
  - Google Docs: decide if deliverables go to Docs or markdown + pandoc
  - Typefully: API key set up, social set ID documented in `knowledge/typefully-config.md`
  - Document all integration config in client's `CLAUDE.md` or `knowledge/integrations-config.md`

- [ ] **Existing content audited**
  - Top 5 historical performers identified
  - Initial patterns noted
  - Archive of reusable content created

- [ ] **Initialize `whats-working.md`** with any known insights

- [ ] **Video style set up** (any business that will get reels or cuts; `.claude/skills/mkt-kit/REFERENCE.md` → Video style file)
  - `resources/reel-style.json` built from `DESIGN.md`: cover + caption fonts (files in `resources/fonts/`), cover color, platforms
  - `edit_route` set (Resolve, ffmpeg, or ask) with the reason
  - First real footage: camera input measured, look review (`resolve-reel` step 0), owner picks a look

---

## Phase 6: Launch Preparation

### Final Steps

- [ ] **Client CLAUDE.md created** (at client root)
  - All placeholders filled in
  - Voice reminders added
  - Current priorities listed

- [ ] **Knowledge files reviewed with client**
  - Walk through each completed document
  - Get explicit approval on voice guidelines
  - Confirm personas are accurate
  - Verify goals are aligned

- [ ] **First weekly plan generated**
  - Run: `weekly plan for [client]`
  - Review with client
  - Make adjustments based on feedback

- [ ] **Kickoff complete**
  - Client knows how to request plans
  - Review cadence established
  - First content scheduled

---

## Onboarding Timeline

| Phase | Activities | Typical Duration |
|-------|-----------|------------------|
| 1. Discovery | Kickoff, company info, current state | Days 1-2 |
| 2. Brand & Voice | Voice discovery, messaging pillars | Days 2-3 |
| 3. Customer Intel | Personas, StoryBrand, research | Days 3-5 |
| 4. Strategic Context | Goals, KPIs, competitive analysis | Days 5-6 |
| 5. Operational | Workflow setup, tracking config | Day 6-7 |
| 6. Launch | Final review, first plan, kickoff | Day 7 |

---

## Common Onboarding Questions

**Q: What if the client doesn't have clear personas?**
A: Use the discovery call to create them together. Ask about their best customers and build from there.

**Q: What if they don't have performance history?**
A: Start whats-working.md with industry best practices and hypotheses. Update as you gather data.

**Q: How detailed should the StoryBrand be?**
A: At minimum: clear problem statement, guide positioning, and one-liner. Full framework is ideal.

**Q: What's the minimum viable onboarding?**
A: Complete: 00-client-overview.md, voice-guidelines.md, goals-and-benchmarks.md, and CLIENT-CLAUDE.md

---

## Post-Onboarding

After the first month, schedule a review to:
- [ ] Validate personas with real data
- [ ] Update whats-working.md with initial findings
- [ ] Adjust goals if needed
- [ ] Refine voice guidelines based on what resonates

---

*Template Version: 1.0*
*Last updated: [Date]*
