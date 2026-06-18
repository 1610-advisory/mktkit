# Hybrid Content Workflow

A framework for producing consistent content (3-5 posts/week) using AI planning + in-house capture + freelance editing. Designed to minimize the organizer's time while maintaining quality.

---

## The System Overview

```
MONDAY (Organizer: 30-45 min)
  AI generates:
  • Weekly or bi-weekly content plan
  • Shot list for each piece
  • Hook/caption direction
  • Script outlines for video
  Organizer reviews, approves, assigns to team

SHOOT DAYS (Capture team)
  Shoot raw footage based on shot list
  • On location / at subject sites
  • B-roll library building
  • Talking head content (if needed)
  Upload raw files to shared folder

EDITING (Freelancer or in-house, 48-72hr turnaround)
  Edit videos based on:
  • Shot list/script from AI
  • Brand guidelines (fonts, colors, music style)
  • Caption templates
  Upload edited content to review folder

REVIEW (Organizer: 30 min)
  Quick review of edited content
  Approve or request revisions
  Schedule posts for following week
  Log content to tracking

ONGOING (Team member or freelancer)
  Engagement:
  • Respond to comments within 4 hours
  • Reply to DMs (escalate leads)
  • Engage with local/relevant accounts
```

---

## Time Budget

The organizer (strategist/business owner) should spend no more than 2 hours/week:

| Day | Task | Time |
|-----|------|------|
| Monday | Review AI plan, approve, assign | 30-45 min |
| Review day | Quick review of edited content, approve | 30 min |
| As needed | Questions from team | 15-30 min |
| **Total** | | **~1.5-2 hours** |

---

## Role Breakdown

### AI (Claude) — Planning

**Deliverables per cycle:**
1. **Content pieces** (5-7 per week or 10-14 per bi-weekly) with:
   - Platform and format
   - Topic and hook
   - Key message and CTA
   - Why this works (tied to whats-working.md)

2. **Shot list** for each piece:
   - Specific shots needed
   - Location
   - Who needs to be on camera
   - Props/setup needed

3. **Script outline** for video content:
   - Hook (0-3 sec)
   - Setup (3-10 sec)
   - Value (10-45 sec)
   - CTA (last 5 sec)

4. **Caption direction:**
   - Opening hook line
   - Key points to cover
   - CTA and hashtag set

### Capture Team — Content Creation

**Responsibilities:**
- Receive shot list from organizer
- Coordinate with talent for talking head content
- Capture raw footage on location
- Upload to shared folder with clear naming: `YYYY-MM-DD_[subject]_[shot].mov`

**Shoot Day Checklist:**
- [ ] Review shot list before arriving
- [ ] Capture all required shots
- [ ] Get B-roll (details, textures, wide shots)
- [ ] Check audio quality for talking head content
- [ ] Upload same day or next morning

**B-Roll Library Building:**
Continuously capture:
- Detail close-ups
- Wide establishing shots
- Team at work
- Material/product textures
- Before/during/after progression

### Freelance Editor — Post-Production

**What they receive:**
1. Raw footage (shared folder)
2. Shot list/script from AI
3. Brand kit (fonts, colors, music style)
4. Caption template

**Deliverables:**
1. Edited video (proper format for platform)
2. Thumbnail/cover image
3. Caption draft (based on AI direction)

**Turnaround:** 48-72 hours from receiving footage

**Editor Guidelines:**
- Music: Modern, energetic but professional
- Text on screen: Clean, readable, minimal
- Pacing: Fast enough to retain attention, slow enough to appreciate the subject

### Posting & Engagement

**Scheduling:**
- Use scheduling tool (Later, Planoly, or native platform tools)
- Schedule full week/cycle in one batch session
- Follow optimal posting times from `knowledge/whats-working.md`

**Engagement Protocol:**
- Check comments 2-3x daily
- Respond within 4 hours during business hours
- **Lead escalation:** If someone asks about pricing, availability, or wants to start working together, immediately notify the business owner/sales contact
- DM responses: Warm, helpful, point to booking link or contact method for serious inquiries

---

## Shared Folder Structure

```
[Client] Content/
├── 01_Plans/             # AI-generated plans for reference
├── 02_Raw Footage/       # Organized by date and subject
├── 03_Ready for Edit/    # Footage + shot list for freelancer
├── 04_Edited - Review/   # Freelancer uploads here
├── 05_Approved/          # Final approved content
├── 06_Posted Archive/    # Archived after posting
└── Brand Assets/         # Logos, fonts, music
```

---

## Weekly Checklist

### Monday
- [ ] Run content plan (weekly or bi-weekly brief)
- [ ] Review and approve plan
- [ ] Share shot list with capture team

### Shoot Days
- [ ] Capture footage per shot list
- [ ] Upload to shared folder
- [ ] Notify editor footage is ready

### Edit Days
- [ ] Editor delivers edited content
- [ ] Upload to review folder

### Review Day
- [ ] Quick review of edits
- [ ] Request revisions if needed
- [ ] Approve final content
- [ ] Schedule posts
- [ ] Log content to `tracking/content-log.csv`

### Ongoing
- [ ] Monitor comments and DMs
- [ ] Escalate leads
- [ ] Note high-performing content for monthly review

---

## Finding a Freelance Editor

### Where to Look
1. **Upwork** — Search "short form video editor" or "social media video editor"
2. **Fiverr** — Good for testing with small projects first
3. **Local colleges** — Film/media students
4. **Referrals** — Ask other local businesses

### What to Look For
- Experience with Reels/TikTok format
- Portfolio showing clean, modern edits
- Understands pacing for social media
- Can work with brand guidelines
- Reliable turnaround (48-72 hours)

### Test Project
Before committing, send them one piece of raw footage + shot list + brand guidelines. Evaluate quality, communication, adherence to guidelines, and turnaround time.

### Pricing Expectations
- Per video: $25-75 depending on complexity
- Monthly retainer (15-20 videos): $400-800

---

## Troubleshooting

**Not enough footage:** Build B-roll library on slow weeks. Repurpose older footage with new hooks. Create static/carousel content as backup.

**Editor missing deadlines:** Have 1-week content buffer. Set clear expectations in contract. Identify a backup editor.

**Content not getting engagement:** Run `analyze performance for [client]`. Update whats-working.md. Test new hook patterns.

**Organizer spending >2 hours:** Create clearer templates for AI prompts. Delegate more approval authority to team. Batch decisions (once/week only).

---

## Client-Specific Config

Each client that uses this workflow should have a `knowledge/hybrid-workflow.md` containing:
- **Team roster** — who fills each role (organizer, capture, editor, engagement)
- **Time budgets** per role
- **Shared folder location** (Google Drive, Dropbox, etc.)
- **Shoot schedule** (weekly, bi-weekly, etc.)
- **Scheduling tool** being used
- **Lead escalation contact** and method
- **Brand kit location** (fonts, colors, music style)
- **Editor contact info** and rate
