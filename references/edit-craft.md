---
title: "Edit craft: house rules for every cut"
description: "The editing rules that hold for every business, on both edit routes, and how a reviewer's note becomes a rule here or a value in the business's repo."
status: active
last_updated: 2026-10-07
---

# Edit craft

These rules hold for every business and both routes (`resolve-reel`, `cut-video`). What makes a cut look like **one** business (look, fonts, caption size, speaker, route, public-safe names) lives in that business's repo: `resources/reel-style.json` and `memory/`. The toolkit never holds it.

Read this before the first cut in a session. Each rule came from a reviewer's note on a real cut.

## Rules

1. **Open on the hook.** Read the real transcript (never a summary) and find the grabbiest line: a contrarian setup, a vivid concrete detail, a clean list, a before/after contrast. It is usually in the middle of the take, not at the top. Open the cut on it (the first 2 to 5 s), under the strongest visual. Then play the whole edit through from the top, so the hook line repeats once, in context (reviewer, 2026-09-25: repeat the hook). `cut-video`: `hook.mode: prepend`, `lift_from_spine: false` (the default); in Resolve, prepend the hook and leave the spine whole. Never more than one repeat (`hook.once`). A brief for an outside editor gives the verbatim quote, the source timecode and a runner-up.
   **In a talking cut, the strongest visual is the speaker on camera, with movement** (walking toward the lens, the camera following, hands working). Do not put a static cutaway under the opening line with the speaker off camera; a walkthrough that opened that way got very poor reach and was re-cut (reviewer, 2026-10-07: "open with [the speaker] talking and some movement"). Pick the hook take where the speaker is on screen and moving. When the hook plays on camera, do not repeat it in context on the same picture: drop the repeat, or cover it with different picture that moves.
2. **A-roll holds at least 3.0 s.** Never cut back to the speaker for a second between two cutaways. If the gap is shorter, run the cutaways back to back (extend one, or pull the next one earlier). Gate: `cut_check.py aroll`.
3. **Hide every join.** A spine join sits under a cutaway, at a camera switch, or at a framing change. Two same-angle segments that meet in view get a punch-in: the next segment about 10 to 15% tighter, the eyes on the same pixel, then back to wide on the next join. Not on the first segment. Check the source has the resolution headroom. Resolve detail: `resolve-reel/REFERENCE.md` → Jump cuts. Gate: `cut_check.py aroll`.
   A framing change mid-sentence (same source, no trim) is a **continuous join**: give both sides the same time. Never let them overlap (that slice of audio plays twice, a stutter) and never leave a small gap (it deletes part of a word). `reel.py` snaps 1-2 frame rounding shut, keeps the edge gate and fades off that join, and fails on an overlap (reviewer, 2026-10-19: a 0.23 s overlap doubled half a word; an editor then dodged the gate with 2-4 frame gaps).
4. **No clipped words.** Word times drift, and low-rate energy maps miss fricatives (the "s" of "house", the "th" of "the"). Check every edge on the full-band 48 kHz audio and on a >2.5 kHz band. Move an out-edge only later and an in-edge only earlier (keep more, never less). Where two words run together with no silence, cut at the quietest 10 ms and give that clip a 1-frame audio fade. Gate: `cut_check.py edges`.
   Captions follow the same rule: a cue never leaves a sentence's last word alone on the next cue, and phrase cues close at a sentence end (`group_caption_cues`). When a full two-line cue still pushes the end of a sentence over, the tail cue pulls words back from the cue before it so the payoff reads as a phrase ("has no door.", never "door.") (reviewer, 2026-10-19: one-word punchline cards on several talking cuts). Re-time a caption word only when the word JSON is plainly wrong against the audio, never to dodge an orphan.
5. **Wordless montages cut straight.** No push-in, zoom or Ken Burns move on montage clips, even static shots. (A punch-in at a jump cut in a talking cut is rule 3, not this. A still used as a B-roll punch in a talking cut has its own move settings.)
6. **Cheap labor, strong verdict.** The `reel-editor` agent (Sonnet class by default) reads one compact prep packet, makes the cut plan and runs `reel.py` and the gates; the `reel-qa` agent checks the result against rules 8 to 10. The session's strongest model gives the final verdict on each round from the QA JSON and the one sheet, and handles anything the rubric cannot settle. Never hand edit work to a small or other-family model: those results needed a full re-check every time. (Reviewer, 2026-09-28: the cost was the rework, not the edit.)
7. **Review before anything ships.** The owner watches every cut before it is published or scheduled. A new look gets a stills review first (`resolve-reel` step 0).
8. **Nothing crosses the caption zone.** A screen, tablet or frame edge that runs through the captions is a fail. Fix the picture (reframe or zoom the wide shot, or mask it with a power window), never move the captions.
9. **Two rounds, then the reviewer.** A cut gets at most two build-and-check rounds. After that, hand it to the reviewer with the open notes. Block a round only for what the reviewer would reject: a public-safe name on screen or in audio, a missing, cut-off or covered caption, broken audio or a clipped word, a black, frozen, upside-down or corrupt shot, or a grade that is plainly broken (neon or red skin, a near-black cutaway, crushed blacks). Grade and framing taste go into the delivery notes, not into another rebuild. A check that fails on something you can see is fine is a false positive: note it, never change the design to satisfy the checker. (Live batch 2026-09-29: a QA round enlarged a house cover to pass a cover detector, and passed two plainly broken grades.) (Reviewer, 2026-09-28, approving cuts that automatic QA had failed on taste.)
   A grade solve that lands on its slope limit has failed, whatever the checker says. A cutaway shot in the same room and light as the A-roll takes the A-roll's CDL (`grade.shots.<clip>.cdl`), not a wall match against it (reviewer, 2026-10-19: three after-demo cutaways solved to slope 2.0 and came out orange).
10. **Judge from one sheet, not frame by frame.** QA reads `reel.py qa` output: one JSON and one contact sheet (frames around every cut, the cover, the caption zone). Reading frames one at a time keeps every image in context for the rest of the run and was the largest single cost.

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
