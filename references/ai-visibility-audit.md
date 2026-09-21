
# AI Visibility Audit (Answer-Engine / GEO)

You are auditing whether a site can be found, parsed, cited and **recommended** by assistants —
ChatGPT, Claude, Perplexity, Google AI Overviews, Gemini — rather than whether it ranks in a
classic blue-link list. Run this alongside `seo-audit.md`, not instead of it. They overlap less
than people expect: a site can be technically excellent for Google and invisible to assistants.

**The framing question.** Not "does the site rank" but: *when a real person asks an assistant the
question this business exists to answer, does this business come back?* Write that question down
before you start, in the user's words, and run it. Everything below is in service of that one test.

---

## Run the real query FIRST

Before auditing anything, run the actual buying-intent question through a live search and see what
comes back. This reorders the whole audit, and it regularly overturns the assumption that on-site
work is the bottleneck.

Do this for two or three phrasings — the "who should I hire" version, the "how much does X cost"
version, and the comparison version.

**For local service businesses expect this result, and do not be surprised by it:** assistants
answer from **aggregators** — Yelp, Angi, HomeAdvisor, BBB, Thumbtack, "best X in [city]"
listicles — not from the contractor's own website. If the client is absent from that layer, no
amount of on-site optimization will surface them, and it is a disservice to spend the engagement's
budget on schema tweaks while the actual gap is an unclaimed Yelp profile.

**Report the finding as what it is.** If the site is fine and the entity is the problem, lead with
that, and be explicit that on-site work will not fix it.

---

## The entity check

Assistants recommend *entities*, not pages. An entity that does not resolve cleanly cannot be
confidently recommended, and ambiguity is itself a ranking penalty in a system that has to decide
whether two records are the same business.

**Inventory every public record of the business and diff them.** Site JSON-LD, the primary business
profile, the aggregators, the data brokers, the industry registries.

Check specifically:

- **Address conflicts.** Count the distinct addresses in public circulation. More than one is a
  problem; three or four is common and badly under-diagnosed. Service-area businesses are the worst
  affected, because a legacy record often carries a street address the business has deliberately
  stopped publishing.
- **Category misfiling.** A business filed under the wrong category on a major directory never
  surfaces for its own core query, no matter how good the profile is. Check the literal category
  string on each directory, not what the profile *looks* like it is about.
- **Legal name vs trading name.** Records split across both is a frequent cause of duplicate
  profiles and split review counts.
- **Stale positioning.** Third-party profiles often preserve a description of the business from
  years ago — services it no longer offers, a market it has left. Assistants will quote it.
- **`sameAs` coverage.** The site's structured data should link out to every profile that
  represents the business. Missing links from `sameAs` to major directories is a missed
  entity-resolution hook and is trivially fixable.

**Deliverable:** a table of *source → what it says → what it should say → who can change it.*
Most rows will need the client's own login, so this becomes an ask, not a task.

---

## Crawler access — check what is actually served

Fetch `/robots.txt` live. Do not read it from the repo; a CDN or edge rule can rewrite it.

**Understand the citation/training split before recommending anything.** These are different
populations of bot and blocking them has different consequences:

- **Citation / search bots** feed the assistant's *answers*. Blocking them removes the site from
  answers. Almost never correct to block.
- **Training bots** harvest for model training. Blocking them is a legitimate policy choice with
  little or no citation cost.
- **User-triggered fetchers** retrieve a page because a user pasted or asked about it. Blocking
  these breaks the case where someone hands the assistant the client's own URL.

**Three failure modes worth checking for specifically:**

1. **The incomplete block list.** A partial list of training bots is worse than none, because the
   unlisted ones fall through to the permissive `*` rule. The result is a policy that blocks some
   vendors and silently permits others — usually not what anyone decided. If a training block is
   intended, enumerate it properly; if it is not, say so and simplify.
2. **The self-cancelling agent layer.** If the site publishes machine-readable endpoints (see
   below) while `robots.txt` disallows the path they live on, a well-behaved agent is told to use
   endpoints it is simultaneously forbidden to fetch. Blanket-disallowing an entire API prefix is
   the usual cause. Narrow the disallow to the genuinely private routes and allow the documented
   ones explicitly.
3. **Advisory vs enforced.** `robots.txt` is advisory. If a project's notes claim enforcement via a
   firewall or WAF rule, verify the rule exists. It frequently does not.

**Verify by fetching as each bot**, with the user-agent set, and confirm the status code. This
catches edge rules and bot-fighting products that override the file's stated intent — a common and
otherwise invisible cause of "we allow them but never get cited."

---

## Machine-readable surfaces

Check whether `/llms.txt` and any agent manifest exist **live**, not just in the repo — and read
them critically rather than ticking a box for presence.

**The most damaging failure is a machine-readable file that contradicts the site.** Treat these
files as production content with the same review bar as a landing page, because assistants weight
them as authoritative and will quote them verbatim.

Audit for:

- **Facts that contradict the site's own structured data.** Especially addresses and hours. A file
  written months ago and never revisited is the normal case.
- **Numbers that appear nowhere else.** Any price, statistic or claim that exists *only* in the
  machine-readable file is unverifiable by definition, and is how a fabricated figure ends up
  quoted back as the client's published price. Cross-check every number against a page that renders
  it. Delete anything that fails, and say plainly why.
- **Whether it links to any content at all.** A file that lists only a homepage and a contact email
  is not a site map and gives an agent nothing to navigate. It should name the key pages with a
  one-line description each, ideally carrying the specific detail that makes each page worth
  fetching.
- **Endpoint claims that are blocked or dead.** Fetch every URL and endpoint the file advertises.
- **Consistency with the manifest.** If both a manifest and `llms.txt` exist, their permissions and
  endpoint lists must agree with each other and with `robots.txt`.

---

## Extractability — is the answer actually in the HTML?

**This is the highest-yield technical check in the audit, and the one most likely to be missed.**
See the collapsed-content trap in `seo-audit.md` — content inside accordions, tabs, "read more"
toggles and modals is frequently absent from the served HTML entirely. Assistants extract main
text; content that lives only in a hydration payload or renders on click is invisible to them.

FAQ content is the usual casualty, and it is exactly the content best suited to being quoted in an
answer. A site can ship a page of twenty questions, structured data declaring twenty answers, and
zero answer text a crawler can read.

**How to check:** fetch the raw HTML, strip `<script>` and `<style>`, then confirm the substantive
prose is present. If an answer string appears in the file only inside script tags, it does not
count. Do this per template, not just on the homepage.

---

## Citability — is there any reason to quote this site?

Assistants quote what is *specific*. Generic service copy is interchangeable and gets summarized
away; concrete detail gets cited with attribution.

Assess honestly whether the site contains anything a third party would have reason to repeat:

- **Real numbers** — price ranges, sizing thresholds, timelines, measurable outcomes. A published
  range that competitors do not publish is a genuine moat and usually the single most citable asset
  on the site.
- **Named specifics** — products, brands, models, standards, local authorities and processes.
  Named entities are what make an answer feel sourced.
- **A stated point of view** — a recommendation the business is willing to make, including advice
  that costs them a sale. This is disproportionately quotable and disproportionately rare.
- **Original material** — anything the business knows that cannot be found on a competitor's site.

If the answer is "nothing here is quotable," that is the finding. Say it, and treat content
creation as the fix rather than more markup on thin pages.

**Constraint that overrides all of the above:** never recommend inventing a number, a credential or
a claim to make a page more citable. Fabricated specificity is worse than vagueness — it is a
liability, it will be quoted back, and correcting it later is far more expensive than never
publishing it. If a needed figure is unverified, the correct recommendation is to get it verified
or to publish the reasoning without the number.

---

## Entity, credential and authorship signals

- **Structured data** — verify the live JSON-LD parses and describes the business accurately.
- **Credentials** — a licence or certification is a strong trust signal, but only if it is stated
  in a form that can be checked. A credential with no identifier and no link to the issuing
  registry is an unverifiable assertion. Add the number and the registry link; state only what is
  true.
- **A stable person node** — for owner-led businesses, the person should be a first-class entity
  with a durable identifier and links out, not an inline string.
- **Dates and authorship** — a real published/modified date and a named author. Build timestamps
  copied into every URL's `lastmod` carry no information and should not be mistaken for freshness.

---

## Output

Match `seo-audit.md`'s report structure, with three additions:

1. **Lead with the single biggest reason an assistant would fail to recommend this business today.**
   Frequently this is not on the website.
2. **Label every finding verified-live or repo-only.** They diverge constantly — an undeployed
   commit, a CDN cache, an edge rule. Say which you checked.
3. **Separate "genuinely missing" from "present but weak."** They have different fixes and very
   different effort profiles.

State plainly what is already good and move on. A padded audit buries the two or three findings
that matter.

---

## Related

- `seo-audit.md` — classic technical, on-page and local SEO. Run both; they overlap less than expected.
- `analytics-tracking.md` — measuring whether any of this changed anything.
