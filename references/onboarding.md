# New Client Onboarding

When the user says "new client [name]", run this onboarding workflow. The goal is to set up a complete client folder with populated knowledge files so the AI CMO can start producing strategic plans.

**This workflow is designed for everyone** — whether you've run marketing campaigns for years or you're posting for the first time. Every concept is explained as it comes up. There are no wrong answers.

## What to Have Ready

Before starting, it helps to gather a few things. **You don't need all of these** — work with whatever you have:

- [ ] Your website URL (if you have one)
- [ ] Links to 3-5 pieces of content you've created (social posts, blog posts, videos — anything)
- [ ] Links to 2-3 accounts or posts you admire (competitors, peers, or brands in any industry whose style you like)
- [ ] A few examples of your natural writing — emails to customers, text messages about your business, captions you've written, anything in your own words
- [ ] A rough sense of who your customers are
- [ ] What you'd like to accomplish with marketing in the next few months

If you don't have some of these, that's completely fine. We'll work with what you've got and fill in the gaps together.

---

## Step 1: Create the Folder Structure

Run the initialization script to create all folders and copy templates:

```bash
python3 [skill-path]/scripts/init-client.py [client-name] --path clients/
```

This creates:
```
clients/[client-name]/
├── .gitignore (copied from templates/gitignore.template)
├── .git/ (isolated repo, initial commit made automatically)
├── CLAUDE.md
├── knowledge/ (all template files including 00-client-overview.md)
├── tracking/ (CSV headers)
├── content/our-content/
├── content/competitors/
├── research/
├── transcripts/
├── memory/MEMORY.md & logs/
└── outputs/monthly-briefs/, weekly-briefs/, & biweekly-briefs/
```

**About the git repo:** The script initializes an isolated git repo inside the client folder for revision tracking. The parent toolkit repo ignores `clients/*/`, so this repo stays private and never leaks when the plugin is published. Obsidian Sync will carry the `.git` folder across devices, giving multi-machine history without needing a remote. Commit progress as work is done:

```bash
cd clients/[client-name]
git add .
git commit -m "Updated what's working after March performance pull"
```

## Step 2: Discovery Interview

Walk through discovery questions **one section at a time**. Don't dump all questions at once — complete one section before moving to the next. Update the corresponding knowledge file as you go.

Use conversational language. If the user seems unsure about a question, offer examples or explain the concept before pressing for an answer.

---

### Phase 1: Company Overview (→ `00-client-overview.md`)

Cover these three areas in a natural conversation:

**The basics:**
- What's your company called, and what do you do? (Products, services, who you serve)
- Where are you based? Do you have a website?
- How long have you been in business?

**Where you are now with marketing:**
- Are you active on any social media platforms? Which ones? Roughly how often do you post?
- What's been working so far? What feels like a waste of time?
- If you could accomplish one thing with your marketing in the next 3 months, what would it be?

**What makes you different:**
- What makes you genuinely different from competitors? (This could be your process, your story, your values, your product quality — anything)
- Who are your main competitors? How do you think about your position relative to them?
- Is there a founder story or brand origin that's worth telling?
- Any seasonal patterns to your business? (Busy seasons, key dates, etc.)

> **Starting from zero?** If you haven't done any marketing yet, that's a perfectly fine starting point. Just answer what you can about your business, customers, and what makes you different. We'll figure out the marketing strategy together.

---

### Phase 2a: Content Examples (→ seeds `voice-guidelines.md` + `whats-working.md`)

**This is a new and important step.** Ask the user to share content they've created or admire so you can analyze patterns.

Ask:
- "Can you share 3-5 pieces of content you've created? These could be social posts, blog articles, videos, emails — anything you've put out there."
- "Can you share 2-3 accounts or specific posts from others that you admire? They don't have to be in your industry — just content whose style, tone, or approach feels right to you."

**What to do with the examples:**

For each piece of content shared (links, screenshots, or pasted text):
1. Note the **tone** — formal vs. casual, serious vs. playful, polished vs. raw
2. Note the **format** — short-form vs. long-form, video vs. text, educational vs. entertaining
3. Note the **hooks** — how do they open? Question, bold statement, story, statistic?
4. Note the **structure** — how is the content organized? What's the flow?
5. Note the **CTA pattern** — how do they close? Direct ask, soft suggestion, question?

Summarize your analysis back to the user: "Based on what you shared, here's what I'm seeing about your style..." and confirm it resonates before using it to seed the voice guidelines.

> **Starting from zero?** If you haven't created any content yet, that's okay. Focus on the "content you admire" part — sharing examples of what you *want* to sound like gives us plenty to work with. If you don't have those either, we'll build your voice from scratch in the next phases using your natural writing.

---

### Phase 2b: Writing Samples (→ `voice-guidelines.md`)

Ask the user for examples of their natural, unpolished writing:

- "Do you have any emails you've sent to customers, captions you've written, texts where you described your business to someone, or anything where you were just being yourself about your work?"
- "Even a message you'd send a friend explaining what you do counts."

**What to do with writing samples:**

1. Identify voice characteristics: sentence length, vocabulary level, humor, directness, warmth
2. Compare to the content examples from Phase 2a — note similarities and differences
3. Extract the authentic voice beneath any "marketing speak" from the content examples
4. Use this to draft the voice guidelines: attributes, "we sound like" / "we don't sound like" examples, tone variations

Share your draft voice profile with the user and ask: "Does this feel like you? Anything feel off?"

> **Starting from zero?** If you don't have writing samples, ask the user to describe their business to you right now as if they're telling a friend about it. Use that conversational response as your writing sample.

---

### Phase 2c: Voice Refinement (→ `voice-guidelines.md`)

Based on what you've gathered in 2a and 2b, now fill in the remaining voice details:

- "What are the 2-3 main things you want people to associate with your brand?" (These become messaging pillars — the themes you come back to again and again in content)
- "Are there specific words or phrases you always use? Words you'd never use?"
- "Should your content feel more like talking to a friend, presenting to a room, or teaching a class?"
- "Do you use emojis? Exclamation points? Short punchy sentences or longer flowing ones?"
- "Do you have any hashtags you already use or want to use?"

Use all of Phase 2 to populate `voice-guidelines.md` with real examples and concrete attributes rather than abstract descriptions.

---

### Phase 3: Customer Intelligence (→ `personas-storybrand.md`)

This phase is about understanding who you're talking to. We'll use a framework called StoryBrand — don't worry if you've never heard of it, we'll walk through it naturally.

**Understanding your customers:**
- Who's your ideal customer? Describe them — not just demographics (age, location), but what they care about, what keeps them up at night, what they're trying to achieve.
- If you serve different types of customers, describe the top 1-2 groups.
- What objections do people have before buying from you? What holds them back?
- How do customers typically find you? What makes them finally reach out?

**The story your customer is living** (this is the StoryBrand part):

Think of your customer as the hero of a story. Your brand is the guide who helps them succeed.

- **What does your customer want?** (The desire that drives them to look for you)
- **What problem stands in their way?** Think about this on three levels:
  - The practical problem (the tangible thing that's broken or missing)
  - The emotional problem (how it makes them feel — frustrated, overwhelmed, embarrassed)
  - The deeper issue (why this matters — "I shouldn't have to deal with this" or "I deserve better than this")
- **How does your brand help them?** What makes you a trustworthy guide? (Your experience, your empathy for their situation, your track record)
- **What's the simple plan?** If someone wanted to work with you, what are the 3 steps? (e.g., "Book a call → We create a plan → You see results")
- **What does success look like for them?** Paint the picture of life after working with you.
- **What does failure look like?** What happens if they don't solve this problem?

- "If you had to explain what you do and why it matters in one sentence, what would you say?"
- "How do your customers describe their problem in their own words?" (Think about what they'd type into Google, say to a friend, or write in a review)

> **If you haven't thought about this before, that's normal.** Most business owners know this stuff intuitively — they just haven't written it down. Answer from your gut and we'll refine from there. It's okay to say "I'm not sure" on any of these.

---

### Phase 4: Goals & Benchmarks (→ `goals-and-benchmarks.md`)

Keep this practical and grounded in where the user actually is.

**The main goal:**
- "What's the one thing you most want marketing to accomplish in the next 3 months?" (Examples: get more followers, drive website traffic, generate leads, launch a product, build awareness)
- "How would you know if it's working? What would you measure?" (If they're unsure, suggest simple metrics: follower growth, DMs received, website visits, inquiries)

**Current state:**
- "What are your current numbers?" (Followers, average engagement, website traffic, leads per month — whatever they track. If they don't track anything, that's fine — we start from here)

**Resources:**
- "How much content can you realistically create per week?" (Posting 3x/week is a solid starting point)
- "Who's involved? Is it just you, or do you have a team/contractor?"
- "Any budget for ads, tools, or freelancers? Or is this organic-only for now?"
- "What content assets do you already have?" (Photos, videos, testimonials, case studies, a blog, etc.)

> **Starting from zero?** Great defaults: "Post consistently 3x/week for 90 days." That's a real, achievable goal that builds the habit and gives you enough data to make smarter decisions. Don't worry about engagement rate targets or platform-specific benchmarks until you have a month of data.

---

### Phase 5: Operational Setup (→ client `CLAUDE.md` + tracking files)

Ask about:
- Who does what? (Content creation workflow — who films, edits, posts, writes)
- Communication channels (how do you want to receive plans and updates?)
- Tracking preferences: CSV files or Google Sheets?
- Integration needs:
  - Google Drive folder for deliverables?
  - Google Sheets for tracking?
  - Typefully for social media drafts?
- Existing content to audit? (Import past performance data if available)
- Posting schedule preferences (frequency, days, times)

---

### Phase 6: Finalize and Launch

1. **Review all knowledge files** — read them back and confirm with the user that everything is accurate
2. **Generate the client's `CLAUDE.md`** with:
   - Client overview table
   - Folder map
   - Brand voice quick reference
   - Current priorities
   - What's working quick hits
   - Special considerations
   - Integration configuration
3. **Initialize `whats-working.md`** with any known patterns from the discovery (even if limited)
4. **Generate the first monthly plan** using the monthly plan procedure
5. **Generate the first weekly plan** using the weekly plan procedure — the user should leave onboarding with something actionable they can start creating immediately
6. **Summary of what was created** — walk the user through everything that was set up:

   Present this clearly:
   ```
   Here's everything that was set up for [Client Name]:

   Knowledge files (your strategy profile):
   - knowledge/00-client-overview.md — Your company info, differentiators, competitive landscape
   - knowledge/voice-guidelines.md — Your brand voice, tone, messaging pillars
   - knowledge/personas-storybrand.md — Your customer profiles and messaging framework
   - knowledge/goals-and-benchmarks.md — Your 90-day goals and KPIs
   - knowledge/whats-working.md — Performance insights (will fill in as you publish)

   Tracking files:
   - tracking/content-log.csv — Log each piece of content you publish
   - tracking/performance.csv — Log engagement metrics after a few days
   - tracking/revenue-attribution.csv — Track leads back to content (optional)

   Your first plans:
   - outputs/monthly-briefs/[filename] — This month's content strategy
   - outputs/weekly-briefs/[filename] — This week's specific content plan

   What to do next:
   1. Review your weekly plan and pick the easiest 1-2 pieces to create first
   2. After publishing, run: log content for [client]
   3. After a few days, log the performance: log performance for [client]
   4. Next Monday, run: weekly plan for [client] to get your next week's plan
   ```

7. **Confirm onboarding is complete** and let the user know they can say `brief me on [client]` anytime for a refresher

---

## Onboarding Timeline

| Phase | Duration | Output |
|-------|----------|--------|
| Setup (Step 1) | 1 minute | Folder structure created |
| Discovery (Phases 1-4) | 1-3 sessions | All knowledge files populated |
| Operational Setup (Phase 5) | 1 session | Integrations configured, tracking ready |
| Launch (Phase 6) | 1 session | First monthly + weekly plans generated |

## Tips

- You don't need perfect information to start. Populate what you can and note gaps as "[TBD - need from client]" in the knowledge files.
- It's better to do discovery conversationally than to send a long form. Ask a few questions, listen, then ask follow-ups.
- If the client already has content, analyze their existing posts before the discovery to come prepared with observations.
- Some clients won't know their StoryBrand framework — that's fine. Help them work through it during Phase 3 by asking the questions in plain language.
- When a user says "I don't know" to a question, offer an example answer from a similar business to help them think through it. Don't pressure — move on and come back if needed.
- The content examples in Phase 2a are the single most valuable input. Push gently for these even if the user is hesitant — even one or two examples dramatically improve the quality of everything that follows.
