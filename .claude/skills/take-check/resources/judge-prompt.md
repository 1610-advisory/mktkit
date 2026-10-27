You are scoring one raw talking-head take for a short-form vertical video (Reels, Shorts, or TikTok). A business owner is talking to camera. Nothing has been edited. Judge only the spoken word below. Do not invent lines, times, or facts.

What a usable take has:
- A hook in the first sentence or two that gives a stranger a reason to stay.
- ONE idea. A second idea is a problem, not a bonus.
- A payoff line that lands that idea.
- A clean end on a full sentence. "So yeah", a trailing "and...", or the thought stopping mid-line is a dangling end.
- No self-contradiction and no on-camera correction left in ("wait, no", restarting the line).
- Self-contained. "Like I said", "as I mentioned", or a reference to something not said in this take is context_missing.

Also decide how the take should be used:
- cut: the spoken word can be cut as-is inside the suggested in/out.
- trim: usable only if the editor keeps the suggested in/out and drops the rest.
- voiceover: the words are useful but this picture should not carry them (bad energy, looking off, or it only works as narration).
- blooper: keep it only as a blooper, not as the piece.
- reshoot: the idea is not on the tape. Do not cut this take.

Suggested in/out are seconds on the same clock as the sentences. Prefer in at the start of the hook (after any slate chatter already noted below) and out at the end of the payoff sentence.

Quotes must be copied verbatim from the sentences. If you cannot point at the words, do not include that problem. Times must fall on the words you quote.

Context (what this take was meant to be; may be none):
{{CONTEXT}}

Layer-1 measurements (already computed; do not redo the arithmetic, do use them):
{{LAYER1}}

Sentences, numbered, with [start-end] in seconds:
{{SENTENCES}}

Reply with one JSON object and nothing else. No markdown fences, no commentary. Shape:

{
  "hook": {"quote": "verbatim words", "start": 0.0, "end": 0.0, "score": 1},
  "main_point": "one sentence",
  "single_idea": true,
  "payoff": {"quote": "verbatim words", "start": 0.0, "end": 0.0},
  "problems": [
    {"type": "contradiction", "quote": "verbatim words", "start": 0.0, "end": 0.0, "note": "short"}
  ],
  "suggested_in": 0.0,
  "suggested_out": 0.0,
  "structure_score": 1,
  "verdict": "green",
  "use": "cut",
  "reason": "one or two sentences"
}

Rules for the fields:
- hook.score and structure_score are integers 1 through 5. 5 means a stranger stays, one idea, the payoff lands, and the end is clean. 1 means there is nothing to cut.
- payoff may be null if no line lands the idea. If present, quote is verbatim.
- problems is an array, empty if there are none. type is one of: contradiction, restart, ramble, filler, dangling_end, off_topic, context_missing, other.
- verdict is green, yellow, or red. green only if you would hand this take to an editor without a note. yellow if a trim saves it. red if it should not be cut as the piece.
- use is cut, trim, reshoot, blooper, or voiceover.
- Do not wrap the JSON in fences.
