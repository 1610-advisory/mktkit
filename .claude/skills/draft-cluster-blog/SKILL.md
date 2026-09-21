---
name: draft-cluster-blog
description: >
  Draft a search-first cluster blog post from an existing video transcript or
  content note — grounds the post in client voice, local market housing texture,
  numbered bracket citations [1][2] to video shorts and industry data, non-generic
  actionable FAQs, and strict anti-AI writing standards. Use when the user says
  "draft a blog", "write the blog from this video", "draft cluster blog",
  "turn this video into a blog", "blog post from transcript", "search cluster blog",
  or is drafting long-form content from existing tape.
metadata:
  version: 1.0.0
---

# Draft Cluster Blog

You are drafting an authoritative, search-optimized blog post from an existing client video transcript. The post is the caption protocol expanded to 1,000–1,500 words: authentic client quotes as the spine, grounded in local building and neighborhood reality, free of AI cliches.

## Preflight

1. **Locate the source:** Identify the source content note and verbatim transcript in `outputs/content/` or the shoot audio folder. Read the raw text — never guess quotes from summaries.
2. **Read the voice & brand files:**
   - `knowledge/voice-analysis.md` (sentence-level signature lines and cadences)
   - `knowledge/voice-guidelines.md` (strategic written vs spoken register)
   - `knowledge/current-projects.md` (project history, client team roles, public-safe social names)
   - `references/search-cluster-blog-ranking.md` (ranking factors: original photography, video embeds, neighborhood texture, immediate web publishing vs staggered social, numbered bracket citations)
3. **Verify team roles:** Confirm who manages field operations/jobsites vs who is the on-camera design or sales face. Never attribute field PM work to the sales lead or vice versa.

## Core Writing Rules

### 1. Spine = Real Transcript Quotes
- The client spokesperson's verbatim words become the anchor blockquotes. If they didn't say it on tape, it is not a quote.
- Anchor one strong quote near the opening hook.

### 2. Local Market & Neighborhood Texture
- Never write generic national remodeling advice. Anchor housing stock in specific local neighborhoods where the client works (cite the actual local historic and suburban districts — not invented national stand-ins).
- Detail specific home eras and real building conditions: 1920s lath-and-plaster and knob-and-tube, 1960s ranches with partition wall surprises, 1980s daylight basements, local freeze/thaw climate conditions.

### 3. Forensic Contractor Reality
- Use specific trade mechanisms instead of vague generalities: galvanized pipe crumbling into cast iron stacks, unvented plumbing lines, sistered joists that aren't level, converging roof valleys pooling snow/water, HVAC load limits on additions, clearance-aisle tile allowances.

### 4. Software & Process Naming
- Do not cite third-party software brands (like BuilderTrend) unless explicitly confirmed permanent by the client. Refer to the client's "dedicated project management process" or custom client portal.

### 5. Numbered Bracket Citations & Sources Block
- Any industry claim or national statistic (e.g. 25–30% budget overruns without drawings) must carry a bracketed citation `[N]` linking to an authoritative source (Houzz & Home, Harvard JCHS, etc.).
- Direct video quotes and key arguments must carry a bracketed citation `[N]` linking to the matching YouTube Short or channel video.
- Conclude every post with a clean `## Sources and References` section listing `[1]`, `[2]`, etc. with markdown links.

### 6. Anti-AI Writing Standards (Strict)
- **Zero meta-staging:** No "Stefan asked this on camera and waited," "Stefan was standing in a 1926 home when he said this," or "Type [query] into Google." Start directly in the topic.
- **Zero em dashes:** Do not use em dashes (—). Use commas, periods, or natural sentence breaks.
- **No symmetrical contrast templates:** Avoid rigid "One contractor assumes X, while the other assumes Y" balance. Vary pacing and sentence lengths.
- **No AI vocabulary:** Ban words like *delve, tapestry, testament, pivotal, vibrant, crucial, landscape, seamlessly*.
- **No copula avoidance:** Use simple, direct verbs (*is, are, has*) instead of *serves as, stands as, marks*.

### 7. Actionable, Non-Generic FAQ Block
- Include 3–5 high-intent questions.
- Answers must provide concrete numbers (real local price bands, square-foot thresholds, timelines) and actionable rules of thumb. Never provide generic non-answers.

### 8. Internal Linking & Frontmatter
- Link to the matching service pillar (e.g., `/kitchen-remodeling`, `/whole-home-remodeling`, `/home-additions`) and at least one related live blog post.
- Ensure standard frontmatter: `title`, `target_query`, `pillar`, `source_content_id`, `source_transcript`, `status: draft`.

## Output & Review
Save the draft to `outputs/blog/YYYY-MM-DD-<slug>.md`. When generating a multi-post review, compile into the self-contained review HTML and publish via `publish-share` for phone review.
