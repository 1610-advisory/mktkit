---
title: "Edit craft: house rules for every cut"
description: "The editing rules that hold for every business, on both edit routes, and how a reviewer's note becomes a rule here or a value in the business's repo."
status: active
last_updated: 2026-09-25
---

# Edit craft

These rules hold for every business and both routes (`resolve-reel`, `cut-video`). What makes a cut look like **one** business (look, fonts, caption size, speaker, route, public-safe names) lives in that business's repo: `resources/reel-style.json` and `memory/`. The toolkit never holds it.

Read this before the first cut in a session. Each rule came from a reviewer's note on a real cut.

## Rules

1. **Open on the hook.** Read the real transcript (never a summary) and find the grabbiest line: a contrarian setup, a vivid concrete detail, a clean list, a before/after contrast. It is usually in the middle of the take, not at the top. Open the cut on it (the first 2 to 5 s), under the strongest visual. The line plays once: `cut-video` lifts it out of the spine (`hook.mode: prepend`, `lift_from_spine: true`, checked by `hook.once`); in Resolve, cut it out of the spine the same way. A brief for an outside editor gives the verbatim quote, the source timecode and a runner-up.
2. **A-roll holds at least 3.0 s.** Never cut back to the speaker for a second between two cutaways. If the gap is shorter, run the cutaways back to back (extend one, or pull the next one earlier). Gate: `cut_check.py aroll`.
3. **Hide every join.** A spine join sits under a cutaway, at a camera switch, or at a framing change. Two same-angle segments that meet in view get a punch-in: the next segment about 10 to 15% tighter, the eyes on the same pixel, then back to wide on the next join. Not on the first segment. Check the source has the resolution headroom. Resolve detail: `resolve-reel/REFERENCE.md` → Jump cuts. Gate: `cut_check.py aroll`.
4. **No clipped words.** Word times drift, and low-rate energy maps miss fricatives (the "s" of "house", the "th" of "the"). Check every edge on the full-band 48 kHz audio and on a >2.5 kHz band. Move an out-edge only later and an in-edge only earlier (keep more, never less). Where two words run together with no silence, cut at the quietest 10 ms and give that clip a 1-frame audio fade. Gate: `cut_check.py edges`.
5. **Wordless montages cut straight.** No push-in, zoom or Ken Burns move on montage clips, even static shots. (A punch-in at a jump cut in a talking cut is rule 3, not this. A still used as a B-roll punch in a talking cut has its own move settings.)
6. **Edit work stays on the session model.** Cut decisions, builds, prep, QA and checks run on the strongest model in the session. Do not hand any part to a smaller or other-family model: every such result needed a re-check, so it cost more than it saved. This overrides the toolkit's general delegation defaults for edit work.
7. **Review before anything ships.** The owner watches every cut before it is published or scheduled. A new look gets a stills review first (`resolve-reel` step 0).

Gate commands (run from the business's repo; the scripts are in the plugin's `resolve-reel/scripts/`):

```
python3 cut_check.py aroll cut.json
python3 cut_check.py edges cut.json --fix
```

Plan shape: `resolve-reel/resources/cut.example.json`. Exit 3 means stop and fix.

## Filing a reviewer's note (do this every time)

When the reviewer gives a note on a cut, file it **in the same session**, before the next version. Sort it first:

| The note is… | Test | It goes to |
|---|---|---|
| **Craft** | It would be true on any business this reviewer edits (one person often reviews every business) | A rule in this file, and a gate in `cut_check.py`, `qa-reel.py` or `render-reel.py` when it can be checked |
| **Taste of this business** | It names this business's look, fonts, sizes, platforms, speaker, route or confidentiality | The business's `resources/reel-style.json` (a value) or `memory/` (a rule) |
| **Both** | A general rule with a business-specific value | The rule here, the value in the business's repo |
| **One-off** | It is about this piece only | The piece's run notes |

Then:

1. **Check for a clash.** If the note changes a rule here, edit that rule; do not add a second one. If it clashes with the business's own memory, the business wins for that business; say so.
2. **Make it a gate when you can.** A prose rule comes back; a check does not (`cut-video/CHECKLIST.md`, first paragraph).
3. **Keep this repo public-safe.** No business, speaker, job, address or place names here. Write the rule in general terms and quote the reviewer without names. The pre-commit hook checks, but write it clean.
4. **Say where it went** in the delivery note: `Filed: craft → edit-craft.md #3; taste → reel-style.json captions.size`.

A business's memory may keep a one-line pointer to a rule here, but the rule itself lives here, so every other business gets it.
