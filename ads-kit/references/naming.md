# Naming rule: one string joins asset, ad, spend and lead

ads-kit's own text (MIT).

## The rule

Every ad creative is a content piece with a `content_id` (the toolkit's content-note id, `<PREFIX>-YYYYMMDD-NN`, for example `AP-20261201-03`). That id goes in two places:

1. **The ad name** in the platform starts with it.
2. **`utm_content`** on the ad's landing URL is exactly it.

Then the content note → the asset → the ad → its spend → the form's hidden fields → the CRM lead all carry the same string. Unmapped spend (an ad name with no `content_id`) is a naming bug: `ads-review` lists it with the dollar amount.

## Ad name

```
<content_id> | <cell> | <short label>
AP-20261201-03 | MA-H2-B | drain camera video
```

- `content_id` first, always. Tools find it with the pattern `[A-Z]{2,5}-\d{8}-\d{2}`.
- `cell` is the ad-matrix cell (`MA-H{1-4}-{A-C}`, see `campaign-build.md` and `ad-matrix.schema.json`). It tells the hook and format.
- The label is for people. Keep it short.

Ad sets / ad groups: `<campaign slug> | <audience or theme>`. Campaigns: `<campaign slug> | <platform> | <objective>`.

## UTM tags

| Tag | Value |
|---|---|
| `utm_source` | `google` / `meta` |
| `utm_medium` | `paid` |
| `utm_campaign` | the campaign slug (lowercase, hyphens), same as `tracking/ads/campaigns/<slug>/` |
| `utm_content` | the `content_id`, exact case |
| `utm_term` | the keyword (Google Search only; `{keyword}` ValueTrack is fine) |

- Google: keep auto-tagging **on** (it adds `gclid`). Put the UTMs in the ad's final URL suffix. Never turn auto-tagging off to make UTMs work.
- Meta: put the UTMs in the ad's URL parameters field. Meta adds `fbclid` itself.
- Check one live ad by clicking it once: the landing URL must show the click id and all five tags, and the site must not redirect them away (see `ads-tracking-check`).

## Content note `ad:` block

A content note used as an ad gets an `ad:` block in its frontmatter, so one reel can be both a post and an ad:

```yaml
ad:
  cell: MA-H2-B
  status: approved        # draft | approved | live | paused | retired
  approved_by: ""         # a person
  approved_on: ""         # YYYY-MM-DD
  platforms: [meta]
  ratios: ["9x16", "4x5"]
  assets: ["AP-20261201-03-9x16-v1.mp4"]
```

Only `status: approved` (or later) creatives can go into a `create_ad` proposal.

## Asset files

`<content_id>-<ratio>-v<n>.<ext>`, for example `AP-20261201-03-9x16-v1.mp4`.
