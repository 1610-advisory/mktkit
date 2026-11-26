# Third-party notices

Each vendored file under `references/` starts with an HTML comment that names its source and what changed, then a short ads-kit note. Every edit inside a file is marked with an `<!-- ads-kit ... -->` comment.

## boring-marketing-skills

- Read from: https://github.com/Midnight-Farmer/boring-marketing-skills (a fork)
- Upstream: https://github.com/boringmarketer/boring-marketing-skills
- Commit: `7c6678c857fe514f79396ea607aa2a56ea82e676`

| ads-kit file | Source path | What changed |
|---|---|---|
| `references/campaign-build.md` | `skills/paid-ads/SKILL.md` | Excerpt: section "Mode 1: CAMPAIGN BUILD (default)" only. Text unmodified; trailing `---` separator dropped. |
| `references/policy-check.md` | `skills/paid-ads/SKILL.md` | Excerpt: section "Mode 2: POLICY CHECK" only. Text unmodified; trailing `---` separator dropped. |
| `references/results-review.md` | `skills/paid-ads/SKILL.md` | Excerpt: section "Mode 3: RESULTS REVIEW" only. Text unmodified; trailing `---` separator dropped. |
| `references/ads-judgment.md` | `skills/paid-ads/references/ads-judgment.md` | Whole file, verbatim. |
| `references/meta-tracking.md` | `skills/meta-ads/references/tracking.md` | Whole file, verbatim. |
| `references/ad-matrix.schema.json` | `_system/schemas/ad-matrix.schema.json` | Whole file, byte-for-byte (JSON cannot carry a comment; this notice covers it). |

All `.md` files above also get the source comment and an ads-kit note at the top.

```
MIT License

Copyright (c) 2026 Boring Marketing, LLC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## marketingskills

- Source: https://github.com/coreyhaines31/marketingskills
- Commit: `8fd2fcade2fd6629026e9dfe6d133b55b36968b9`

| ads-kit file | Source path | What changed |
|---|---|---|
| `references/conversion-tracking-rules.md` | `skills/conversion-tracking/SKILL.md` | Excerpt: sections "The one distinction that drives everything", "The three questions", "Non-negotiables", "Verdict rules" (a sub-section of "Audit flow" in the source; heading raised from `###` to `##`) and "Verification discipline". YAML frontmatter and all other sections dropped. Text otherwise unmodified. |
| `references/google-ads-tracking.md` | `skills/conversion-tracking/references/google-ads.md` | Excerpt: "Part B: diagnostic reference" to end of file. "Category G" rewritten in full by ads-kit for the Google Data Manager API (marked `<!-- ads-kit: rewritten for Data Manager API, not from source -->`). Inline edits, each marked `<!-- ads-kit edit -->`: four offline import/upload sentences now say "offline conversion upload (Data Manager API)" (auto-tagging 1.4, gclid lifecycle step 5, failure B2, audit order step 5); ranked-prevalence item 10 reworded and its range changed from G1-G4 to G1-G12; the GTM container-id placeholder (`GTM-` plus seven X) changed to `GTM-<container-id>` so it does not trip the repo leak check. The "Key sources" line is kept verbatim. |
| `references/discrepancies.md` | `skills/conversion-tracking/references/discrepancies.md` | Whole file. One inline edit, marked `<!-- ads-kit edit -->`: "offline import" in the spam-conversions fixes now says "offline conversion upload (Data Manager API)". |
| `references/audit-guardrails.md` | `skills/ads/references/audit-guardrails.md` | Whole file, verbatim. Its own closing line credits [claude-ads](https://github.com/AgriciDaniel/claude-ads) by Daniel Agrici (MIT), kept as written. |

All files above also get the source comment and an ads-kit note at the top.

```
MIT License

Copyright (c) 2025 Corey Haines

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Not copied

- `last30days-skill`: no licence. Read only; nothing copied.
- BSL-licensed repos, such as `pipeboard-co/meta-ads-mcp`: nothing copied.

## ads-kit's own text

These files are original to ads-kit and are not covered by the notices above:

- `references/change-queue.md`
- `references/naming.md`
- `references/data-manager.md`
- `scripts/capture.js`
