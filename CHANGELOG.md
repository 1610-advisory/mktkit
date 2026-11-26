# Changelog

Plain-language history of the 1610 Marketing Toolkit. Newest first.

## 2026-11-26
- ads-kit 0.2: the paid-ads engineer now reads and writes the mktdata tool by its named requests (spend, funnel, outcomes, creatives, the change queue) when a business has it, and keeps working from files when it does not. It still only proposes money changes; a person approves them on the mktdata screen.
- ads-kit: the daily review now checks which outcome source mktdata counts (CSV by default, or the CRM, or Notion) and tells you when CRM counts will not show until the owner switches it.

## 2026-11-25
- ads-kit: the daily ads review now copies CRM sales results (leads, qualified, won) into mktdata first, so the screens and reports show the same numbers.
- Added a paid-ads engineer (the new ads-kit plugin). It maps how leads reach you, proves ad clicks are saved on your forms, builds Google and Meta campaigns, judges ads by qualified leads from your own records, and proposes every money change for you or your set limit to approve.

## 2026-11-21
- Fixed the footage catalog listing macOS "._" helper files (made when a Mac writes to an exFAT drive) as B-roll, edited photos or art. The footage index now skips them.

## 2026-11-10
- Fixed reel captions ending a line or a card on a small word ("out of", "from the", "that I") or leaving one word alone ("person."). Caption breaks now go at sentence ends, commas and pauses, and the two lines of a card are balanced.

## 2026-10-30
- Made the claude.ai design system page complete: components now work as real React parts, the business's own pages and icons can show on it, and it ends with short notes on how to use the system.

## 2026-10-28
- Made DESIGN.md the required brand file for every business. A new script checks it, turns it into one local web page any assistant can make, and builds a private claude.ai design system page from it in Claude sessions. The file stays the source; the pages are views of it.
- Headers on those pages now show the business's real logo file, not the name typed in a font, so a hand-set mark (special numerals, custom spacing) always looks right.
- Added a take check that reads each raw talking take before anyone edits it. It names the best take of each piece and the part to cut, and it flags takes to shoot again.
- Made the shoot organizer run the take check right after it names the clips, so the shoot summary lists the best takes and the reshoots.

## 2026-10-27
- Gave the toolkit its own home page on the 1610 website, with this changelog right under it.
- Added an SEO engineer (the new seo-kit plugin) that checks your website every week, ranks what to fix, and makes the fixes as a reviewable change.
- Added tracking for whether AI assistants name and cite your business, with one OpenRouter key or a key per engine.
- Added weekly site snapshots, speed tests that take the middle of three runs, and search engine pings after a change goes live.
- Added a way to share a toolkit improvement back with everyone, stripped of anything about your business, or to turn that question off for good.
- Added this changelog, also shown as a timeline with a suggestion box on the 1610 website.

## 2026-10-21
- Fixed a crash in the DaVinci Resolve color grading step that stopped reel builds.

## 2026-10-20
- Added per camera color settings and an optional house color preset for graded reels.

## 2026-10-19
- Fixed caption timing so sentence tails stay with their cue and old captions stop being reused.
- Made same-source video joins snap together cleanly instead of leaving gaps or doubled audio.

## 2026-10-11
- Made footage and photo indexing read every plugged-in drive and keep entries when one is unplugged.

## 2026-10-07
- Made talking-head cuts open on the speaker, on camera and moving.

## 2026-09-30
- Added an option to skip color grading entirely on phone footage.
- Improved post scheduling with collaborators, cover frames, and thumbnail handling.

## 2026-09-29
- Added simple reel commands plus editor and checker helpers so cutting a reel takes a few steps (version 4.2.0).
- Fixed grading so phone clips keep their natural look instead of coming out grey or neon.
- Fixed loudness and face detection, and made parallel builds queue instead of colliding.

## 2026-09-25
- Added a choice between DaVinci Resolve and a simpler editing route for reels, with help choosing.
- Added shared editing house rules and quality gates that apply to every reel.
- Made captions bigger by default and repeat the opening hook once on purpose.

## 2026-09-24
- Made the toolkit install as a ready-made plugin for Claude Code and Claude Desktop (version 4.0.0).
- Added color-graded reels in DaVinci Resolve with look previews, house captions, and punch-ins (version 4.1.0).
- Added a newsletter writing pipeline with templates and a built-in copy checker.
- Made transcription run on any machine and added a filter keeping finished videos out of the index.

## 2026-09-21
- Added the full video and content pipeline: reel cutting, quality checks, B-roll search, and blog drafting.
- Made example data generic so the public copy shares no private names, paths, or codes.

## 2026-08-28
- Made every session start by loading the business knowledge pack so advice stays on brand.

## 2026-07-29
- Moved reference detail out of the main instructions so agent tools read the full rules reliably.

## 2026-07-07
- Added automatic posting stats from your social accounts and a tidier layout for shoot folders.

## 2026-06-18
- Released the toolkit publicly: run your marketing in Claude Code with plain text files and spreadsheets.
