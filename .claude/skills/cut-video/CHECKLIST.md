# Cut Video: definition of done and review questions

Companion to `SKILL.md`. Two audiences: the model that cuts (run this before calling a reel done) and the model or person that verifies (answer the frame questions from the contact sheet alone).

## Why the gate is code

Across the first nine working days of the in-house pipeline (about 35 renders, roughly 60 defect instances), every defect class that was fixed with a code gate stayed fixed: the frozen-punch check, the duration cap, the overwrite refusal. Every class fixed with a prose rule or a manual recipe came back at least once: the transpose direction (fixed in the engine, then re-introduced by a hand-built pre-grade step), the repeated hook (a rule existed; two repeats followed), the cover centering (fixed twice), the LUT on Rec.709 footage (three times). Half of all defects reached the reviewer. So: when a reviewer catches something, the fix is a check in `qa-reel.py`, a refusal in `render-reel.py`, or a fixture in `regress.py`, and only then a sentence in a document.

## Definition of done (the renderer and QA gate enforce most of this; you confirm the rest)

Machine-checked, from `qa-reel.py` (id in parentheses):

- [ ] 1080x1920, yuv420p, H.264 + AAC 48 kHz, faststart (`container.*`)
- [ ] Duration inside the brief window and under the platform maximum (`duration.*`)
- [ ] Integrated loudness at the manifest target ±1 LU, true peak under the platform ceiling, no silence gap over 0.8 s, no clipped tail (`audio.*`)
- [ ] No black run, no frozen frame outside a punch window (`video.*`)
- [ ] Captions inside the strictest platform safe zone, no cue under the minimum duration, no oversized cue (`captions.*`)
- [ ] Cover text 7 words or fewer, no literal escape characters (`text.cover_words`)
- [ ] No banned term (client surname, address) in cover, supers, captions, or punch lines (`text.banned_words`)
- [ ] Hook does not also sit inside a spine range; first-cue words do not recur later (`hook.once`)
- [ ] Every punch has `verified: true` (`broll.verified`)

Confirmed by a look at the contact sheet (see the questions below):

- [ ] The person is upright and framed in every sampled frame, including the hook and the last frame
- [ ] The cover reads as one or two centered lines in the display font, in the brand color, over a frame that is not blown out
- [ ] Each punch is `exact`: the frame literally shows the noun phrase in its `line`, and `shows` names that object. Category matches are defects. No more than two stills, never two in a row, each on its noun. Lines with no exact asset stay on the speaker
- [ ] Captions are legible, not overlapping the cover or a super, and not touching the bottom band
- [ ] Grade: A-roll and punches match; nothing flat (log left ungraded) or crushed (a Rec.709 still put through the LUT)
- [ ] Nothing on screen names a client or shows a house number, mailbox, or address

Process:

- [ ] Rendered from the camera file through `render-reel.py`, not from an older spine, not by hand
- [ ] RUNNOTES beside the file: why this version exists, punch map with lines, color decisions, loudness, known deviations, provenance
- [ ] Proxy iterations done; exactly one final for this version number
- [ ] Revision history line appended in the client's content note; nothing published or scheduled

## Frame questions for the verifier

Given ONLY the contact sheet (first, cover at 1.0 s, hook end, each punch midpoint, each join, last), the cover line, the hook quote, and the punch lines. Answer each with `yes`, `no`, or `cannot tell`, plus the frame label and one sentence. Return JSON: `[{"q": "...", "answer": "yes|no|cannot tell", "frame": "punch2", "note": "..."}]`. Default to `no` when unsure; `cannot tell` is a request for a better frame, not a pass.

1. Is the person upright (head at the top, floor at the bottom) in the first, hook-end, and last frames?
2. Does the cover frame show the exact cover line, wrapped to at most two lines, centered, in a serif display face and the brand color?
3. For each punch frame, grade it: `exact` (the picture literally shows the noun phrase in `line`; name the object you see), `category` (the same kind of thing but not what the line names: a hallway for "a hallway full of doors", any door for "hidden door", a closet slider for "pocket door"), or `wrong` (something else). Trade terms are literal: a pocket door disappears into a wall cavity, a bypass or barn slider on a track does not; a hidden door is concealed in the wall's finish (slats, paneling), not a dark door in matching trim; an arched opening has no door slab. Only `exact` passes. A line with no punch is correct when no exact asset exists; say whether the run's own `shows` texts suggest one did.
4. Do any two punch frames show the same picture? Are there more than two stills, or two stills back to back?
5. Is any caption cut off, overlapping the cover or a super, or sitting inside the bottom third of the frame?
6. Does any frame look flat and desaturated (ungraded log) or crushed and orange (double-graded)?
7. Is there any readable text that is not ours: a house number, a street sign, a mailbox, a client's name, a crew member's first name burned in?
8. Does the last frame show the person mid-sentence (a hard-out that cut too early) or a blank/black frame (a hard-out that ran long)?
9. Is there a join frame where the background jumps in a way a punch should have covered?
10. Would a stranger scrolling past understand the topic from the cover frame alone?

A reel passes the verifier when every answer is `yes` for 1, 2, 3 (all punches), 10, and `no` for 4 to 9.

## Incident to fixture

When the reviewer finds a defect the pipeline did not flag:

1. Write one line in the client's `defects.csv` (class, date, reel, version, caught by, recurred).
2. Decide the gate: a `qa-reel.py` check (measurable on the file), a `render-reel.py` refusal (detectable from the manifest or inputs), or a fixture in the client's fixtures folder (needs real footage to reproduce).
3. Build the gate first; confirm it fails on the defective render; then fix the cause; confirm the gate passes.
4. Only then update SKILL.md or REFERENCE.md if wording must change.

## Review rounds

Label each delivered version in RUNNOTES as `Round: STRUCTURE` (line selection, order, hook, hard-out, punch subjects) or `Round: POLISH` (color, caption styling, cover wording, timing nudges). Reviewer notes about structure on a POLISH cut open a new STRUCTURE round. Ask the reviewer for notes in one shape: `mm:ss  what is wrong  what it should be`, one line each, and a final `SHIP` or `REVISE`.
