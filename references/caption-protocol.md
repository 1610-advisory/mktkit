# Caption Protocol (spokesperson / on-camera content)

Read this whenever you write or finalize a caption for a reel, short, or any video where a client spokesperson is on camera. It is platform-agnostic (IG, FB, YouTube descriptions, LinkedIn, TikTok). It assumes the client has a transcript of what was said on camera and, ideally, a sentence-level voice guide.

This is the **generic** procedure. Each client keeps their own voice specifics (signature phrases, vocabulary, do/don't lists, named examples) in their `knowledge/voice-analysis.md` and `knowledge/voice-guidelines.md`. Read those for the register; read this for the structure and the QA gate.

## Scope: the gate is universal, the structure is for captions

The hook-and-expand **structure** below is for spokesperson/on-camera captions. The **QA gate** — run the client's voice-guidelines/voice-analysis check AND actually invoke the `humanizer` skill — applies to **every piece of client-facing copy on every brand**: captions, blog posts, landing pages, emails, ad copy, social posts. Nothing client-facing ships without both passes. (Internal-only working docs — briefs, content-note editor sections, planning — are exempt.)

This is enforced, not just documented. A global `PostToolUse` hook (`~/.claude/hooks/humanizer-voice-guard.py`) fires whenever a content note / landing page / email draft under any client folder is written, and reminds you to run both passes and log the humanizer result. The hook is a backstop for the recurring "asserted humanizer-clean but never invoked the tool" miss — it does not replace doing it.

---

## The rule: hook + expand, never a 1:1 transcript

A caption is not the video script retyped. If someone who just watched the reel reads the caption and learns nothing new, the caption is dead weight.

1. **Hook (first 1–2 lines):** the spokesperson's actual on-camera line, lightly trimmed for filler. Preserves voice fidelity and continuity with the reel.
2. **Body: expand beyond the reel.** Add the mechanics, specific numbers, concrete examples, or checklist questions the 30–75s video didn't have room for. The substance must be *additive*. Common expansions:
   - a concrete contrast or worked example (two options, same headline price, different real cost)
   - the layer underneath the claim (the assumption, the lead time, the failure mode)
   - a short checklist of questions the viewer can take into a decision
   - the "what's NOT in this" angle
3. **Close:** an in-voice CTA (save, send to a friend, ask your vendor X) + hashtags.

Keep the spokesperson's register throughout: their sentence length, their vocabulary, no marketing-brochure words. The body can lean slightly more written than the hook, but it should still read like the person, not like a brand.

Anything invented (dollar figures, example scenarios, percentages) must be plausible and consistent with the client's real pricing/operations. If you're unsure, flag it for review rather than fabricate.

---

## The BANKED-promotion trap

When you promote a banked/backlog content note to a dated slot, **do not copy its existing Caption section forward.** Banked captions are frequently written under an older or looser rule and are often near-1:1 with the transcript. They look done. They are not done.

Correct workflow on promotion:
1. Read the banked note's editor brief + transcript block for context.
2. Open the source transcript directly to confirm the hook line.
3. **Write the caption from scratch** under hook + expand. The banked Caption section is reference, not a draft to lightly edit.
4. Log a revision entry noting what the reel covers vs. what the caption adds.

If you catch yourself copy-pasting a banked caption and tweaking a few words, stop and rewrite from the transcript.

---

## Pre-flight self-check (run before saving ANY caption)

1. **Hook traceable to a specific transcript line?** Cite the file in the revision history.
2. **Rewrite, or cleaned-up transcript?** Strip the hook and the CTA. If what's left is the reel's spoken words with the grammar tidied, it FAILS. Point to the specific mechanic / number / failure mode / question the body adds. If you can't, rewrite.
3. **Negative-parallelism count: one per caption, max.** Count every "not X, it's Y" / "isn't… it's…" / "Not because A. Because B." construction. The shape is fine sparingly and is often authentic to a plainspoken voice, but **stacking two or more is an AI tell** — and it survives a humanizer self-pass because each instance looks fine in isolation. Keep one only if it's the spokesperson's verbatim line; reword the rest. Apply the same "don't repeat the scaffold" discipline to rule-of-three and to any bridge phrase ("here's the part the reel doesn't cover") across a posting cycle.
4. **No AI vocabulary** (transformation, vision, journey, peace of mind, craftsmanship, and the client's own banned-word list). No em-dashes if the client bans them. No client/customer/vendor proper names unless the client's rules allow it.
5. **Humanizer skill actually invoked** — call the tool, don't assert "humanizer clean" from a mental pass. Humanizer checks for AI tells; it does NOT check the hook-and-expand requirement or count negative parallelisms for you. Both passes are required.

---

## Why this exists

Two failure modes recur and compound:
- **Transcript-copy:** captions promoted as the video script retyped, adding nothing beyond watching. Caught repeatedly; the fix is the hook-and-expand rewrite, done *before* promotion.
- **Negative-parallelism stacking:** even a properly-expanded caption can read as AI when it leans on "not X, it's Y" as a rhythm crutch. The humanizer self-pass misses it because each instance is individually fine.

Both are cheap to prevent with the self-check above and expensive to clean up after a draft is built and queued.
