# Platform specs: where the numbers come from

Companion to `platform-specs.json`. Every number in the JSON has a row here with its source and the date it was checked. When a platform changes its UI, update the JSON first, then this file, then re-run the fixtures (`regress.py`).

Rule of thumb: the pipeline publishes one 1080x1920 file to every platform, so text is placed inside the **intersection** of all targeted safe rectangles. qa-reel.py and finish-reel.py take the strictest value across the platforms named in the manifest.

## Safe zones (pixels from the edge that platform UI may cover)

| Platform | Top | Bottom | Left | Right | Source | Checked |
|---|---|---|---|---|---|---|
| Instagram Reels, Facebook Reels | 270 (14%) | 672 (35%) | 65 (6%) | 65 (6%) | Meta's 2026 unified 9:16 creative safe-zone guidance for Stories and Reels (14% top, 35% bottom, 6% sides); summarized by several agency guides, e.g. https://behaviour.digital/post/meta-reels-safe-zone-14-top-35-bottom-6-sides-the-2026-official-guide and https://kreatli.com/guides/instagram-reels-safe-zone | 2026-09-04 |
| TikTok | 130 | 484 | 60 | 140 | TikTok Ads creative best practices (keep key elements clear of the status area, caption and audio strip, and the right action rail): https://ads.tiktok.com/help/article/creative-best-practices ; pixel values are the conservative end of practitioner measurements | 2026-09-04 |
| YouTube Shorts | 180 | 350 | 60 | 120 | No official pixel spec. Practitioner consensus for the title and channel row at the bottom and the action rail at the right: https://kreatli.com/guides/safe-zone-guide | 2026-09-04 |

Consequences already built in:
- Dialogue captions default to `safe-lower`: bottom-center alignment with `MarginV = strictest bottom + 24` (694 px for Instagram + Shorts) and side margins of the strictest side band + 16. The old default, `MarginV 220`, put caption text under the Reels caption box on a real phone.
- The cover title is center-anchored, which is inside every safe rectangle.
- Supers sit below the top band.

## Delivery

| Item | Value | Why |
|---|---|---|
| Canvas | 1080x1920, 9:16 | Native vertical canvas for Reels, Shorts, TikTok |
| Codec | H.264 High, yuv420p, AAC 48 kHz, `+faststart` | Universally accepted upload format; 10-bit or 4:4:4 masters are transcoded badly or rejected |
| Frame rate | any of 23.976 to 60 | Platforms accept the common rates; the QA gate flags odd values |
| Minimum video bitrate | 6 Mb/s | Below this, platform re-encodes visibly soften fine texture (tile, brick, wood grain) |
| Max duration | Reels 90 s, Shorts 180 s, TikTok 600 s | Platform limits at the time of checking; the manifest window is always tighter |

## Loudness

| Item | Value | Source |
|---|---|---|
| Pipeline master target | -16 LUFS integrated, -1.5 dBTP, LRA target 11 | House standard for phone playback headroom. Platforms normalize downward toward roughly -14 LUFS; a -16 master arrives without limiting artifacts. |
| Two-pass loudnorm | measure with `print_format=json`, then apply `measured_*` + `linear=true` | The filter's author documents single-pass as the live mode that applies dynamic gain (audible pumping on dialogue): http://k.ylo.ph/2016/04/04/loudnorm.html |
| Keep LRA in the target | yes | ffmpeg's linear mode silently reverts to dynamic when the measured LRA exceeds the target LRA; verified locally on ffmpeg 8.1.1. The QA gate should read `normalization_type` from the second pass when available and flag `dynamic`. |
| Do not assert LRA on the delivered file | informational only | EBU R128 Supplement 1 (short-form programmes) states that Loudness Range limits shall not be specified for short content: https://tech.ebu.ch/docs/r/r128s1.pdf |
| Measurement | `ebur128=peak=true` on the delivered file | EBU Tech 3341/3343 measurement; ffmpeg filter reference: https://ffmpeg.org/ffmpeg-filters.html#ebur128-1 |

## Captions

| Item | Value | Source |
|---|---|---|
| Minimum cue | 0.83 s (20 frames) | Netflix Timed Text Style Guide, subtitle timing: https://partnerhelp.netflixstudios.com/hc/en-us/articles/360051554394-Timed-Text-Style-Guide-Subtitle-Timing-Guidelines |
| Minimum gap between cues | 2 frames (0.067 s at 30 fps) | same |
| Reading speed | 20 characters per second maximum (adults) | Netflix English Timed Text Style Guide: https://partnerhelp.netflixstudios.com/hc/en-us/articles/217350977-English-Timed-Text-Style-Guide |
| Line length | 32 characters, 2 lines | Netflix allows 42 on a 16:9 frame; DCMP Captioning Key recommends 32 or fewer: https://dcmp.org/learn/597-captioning-key---text . On a 1080-wide frame at size 42 to 48 inside 65 to 140 px side margins, 32 is what fits. |
| Never cross an edit join | rule | A cue that spans a jump cut reads as a mistake; the engine splits cues at every `--spine-range` boundary |
| Never drop a kept word | rule | Short words at range ends were dropped by an earlier clamp; the engine now keeps the word and clamps its end |
| Escape handling | ASS `\N` is the line break; drawtext has no such escape | The literal backslash-N defect (2026-09-04) was in the cover drawtext; the cover now wraps via a textfile and rejects a backslash in the text |

## Punch-ins and pacing

| Item | Value | Why |
|---|---|---|
| Clip punch | under 3.0 s | House rule from the owner's reviews; longer clip punches read as a cutaway, not a punch |
| Still punch | 3.5 s default | Slow-push stills need the extra second to read (owner note 2026-09-04) |
| Punch carrying a super | 3.5 to 4.0 s | Text must be readable (owner note 2026-09-04) |
| Consecutive stills | 2 maximum | Three stills in a row reads as a montage, not a talking reel |
| A-roll between punches | 3.0 s minimum, or butt the punches | Shorter A-roll flashes read as a glitch (reviewer, 2026-09-24) |
| Visual change cadence | a visual change every 3 to 7 s, tighter in the first 5 s | Practitioner retention guidance for vertical short-form; not a standard, a budget the timeline should meet: https://www.strategia-x.com/blog/2026-07-01-vertical-video-retention-editing-playbook/ |
| Punches per minute | 10 maximum | Derived from the cadence rule and the 3.0 s minimum A-roll; a soft ceiling the QA gate can warn on |

Owner rule 2026-09-07: a punch must literally show the noun phrase spoken under it, or the reel stays on the speaker. Stills are the fallback to video: at most two per reel (`max_stills_per_reel: 2`), never two in a row (`max_consecutive_stills: 1`), and each still starts within 0.3 s of the spoken noun (`still_on_noun_s`). A photo pulls the viewer out of the moment; only an exact one earns it. Video punches use a looser 0.8 s window (`clip_on_noun_s`).

## Cover title

| Item | Value | Why |
|---|---|---|
| Words | 7 maximum | Readable in the 2.0 s hold at display size 72 |
| Line width | about 18 characters before wrapping to two lines | Display serif at 72 px on a 1080 canvas with side margins |
| Content | public-safe: never a client surname or address | Confidentiality rule; enforced by the banned-words list in QA |
