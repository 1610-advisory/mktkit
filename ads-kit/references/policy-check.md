<!-- Vendored from https://github.com/boringmarketer/boring-marketing-skills (commit 7c6678c), skills/paid-ads/SKILL.md. MIT License, Copyright (c) 2026 Boring Marketing, LLC. See ../THIRD_PARTY_NOTICES.md. Excerpt: the section "Mode 2: POLICY CHECK" only; text unmodified. -->

> **ads-kit note:** read this as a playbook. In ads-kit the measure is the CRM-qualified lead (cost per qualified lead from the business's own records), not the platform's conversion count.
> The ads-engineer never writes to an ad account itself: money changes go only through the mktdata change queue (`propose_change`), see `change-queue.md`.
> Run this on drafted copy before it goes into a change-queue proposal; a flagged ad is fixed in the draft, never live.

## Mode 2: POLICY CHECK

The compliance pass. Run on pasted copy, a copy file, or the output of Phase 3. Flag →
classify → rewrite. A rewrite must preserve the hook's psychology; a compliant ad that
lost its hook is a different kind of rejection.

**Meta violations that actually catch people:**

- **Personal attributes.** Ads may not assert or imply knowledge of personal
  attributes: health, finances, race, religion, age, sexual orientation, criminal
  record. "Are you struggling with debt?" implies Meta knows the viewer's finances,
  so it is flagged. Rewrite to third person or the condition itself: "Debt consolidation,
  explained in plain English" / "Most people overpay on X." The word "you" + an
  attribute is the tell; "other people like you" framing passes.
- **Before/after and unrealistic outcomes.** Body transformation images, "lose X lbs in
  Y days", income screenshots. Rewrite to process or capability claims with timeframes
  removed or substantiated.
- **Special ad categories** (credit, employment, housing, social/politics): targeting
  restrictions apply account-side; flag so the user declares the category, because running
  undeclared is an account-level risk, not just an ad rejection.
- **Financial/health restricted verticals:** guaranteed returns, cure/treatment claims,
  supplement promises. These need disclaimers at minimum and are often category-gated.

**Google editorial and claims rules:**

- **Superlatives without proof.** "Best", "#1", "cheapest" require third-party
  verification visible on the landing page. Either cite the source in the ad/page or
  rewrite to a specific, ownable claim ("rated 4.8/5 by say 2,000 customers" beats
  "best-rated").
- **Trademark.** Competitor brand names in ad text get disapproved without
  authorization (bidding on the keyword is allowed; using the mark in copy is not).
- **Editorial:** excessive caps, "$$$", gimmick punctuation, repeated exclamation,
  vague CTAs, display URL ≠ destination domain.
- **Misrepresentation:** the offer in the ad must exist, unaltered, on the destination.

**LinkedIn:** professional-context standards: no clickbait constructions, ROI claims
need a methodology or footnote, testimonials from identifiable people.
**TikTok:** no fake UI elements or fake interactivity, no other platforms' watermarks,
disclosure for synthetic/AI-generated people, regulated-vertical age gates.

Output: a table of flags with the columns `ad or line · platform · rule · severity (REJECTION /
ACCOUNT RISK / DELIVERY DRAG) · compliant rewrite`, saved to
`./campaigns/<name>/ads/policy-review.md`. Ads are named by hook and format; clean ads are
not listed. State plainly, once: this is a platform-policy pass, not legal review;
regulated verticals (health claims, financial products, alcohol, etc.) need counsel.
