# Naming rule: one string joins asset, ad, spend and lead

ads-kit's own text (MIT).

## Two ids, one creative

| Id | Looks like | Where it lives | Who uses it |
|---|---|---|---|
| **Note id** | `AP-20261201-03` (`<PREFIX>-YYYYMMDD-NN`) | the `content_id` field in the content note's frontmatter | people, ad names, `utm_content`, asset and brief file names, the library |
| **mktdata content UUID** | `0193a7c2-4b1e-7d3a-9f00-00000000c0de` | mktdata `content.content_id` | mktdata, the CRM's `content_id` key, the form's `content_id` hidden field |

mktdata maps one to the other: `content.note_ref` holds the note id (unique). A note id that mktdata cannot match goes on its "to match" list; nobody guesses.

In this kit, "note id" means the first one. Where a skill says `content_id` about a content note, it means the note's frontmatter field, that is, the note id.

## The rule

Every ad creative is a content note with a note id. The note id goes in two places:

1. **The ad name** in the platform starts with it.
2. **`utm_content`** on the ad's landing URL is exactly it.

Then the content note → the asset → the ad → its spend → the lead's `utm_content` all carry the same string, and mktdata turns it into its content UUID for joins. Unmapped spend (an ad name with no note id, or a note id on mktdata's "to match" list) is a naming bug: `ads-review` lists it with the dollar amount.

**The form's `content_id` field is never the note id.** `capture.js` fills it only from `<meta name="content-id">` and only with a UUID; a page that has no mktdata UUID leaves it out. The CRM still gets the note id through `utm_content`.

## Ad name

```
<note id> | <cell> | <short label>
AP-20261201-03 | MA-H2-B | drain camera video
```

- The note id first, always. Tools find it with the pattern `[A-Z]{2,5}-\d{8}-\d{2}`.
- `cell` is the ad-matrix cell (`MA-H{1-4}-{A-C}`, see `campaign-build.md` and `ad-matrix.schema.json`). It tells the hook and format.
- The label is for people. Keep it short.

Ad sets / ad groups: `<campaign slug> | <audience or theme>`. Campaigns: `<campaign slug> | <platform> | <objective>`.

## UTM tags

| Tag | Value |
|---|---|
| `utm_source` | `google` / `meta` |
| `utm_medium` | `paid` |
| `utm_campaign` | the campaign slug (lowercase, hyphens), same as `tracking/ads/campaigns/<slug>/` |
| `utm_content` | the note id, exact case (never the UUID) |
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

`<note id>-<ratio>-v<n>.<ext>`, for example `AP-20261201-03-9x16-v1.mp4`.
