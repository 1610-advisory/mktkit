You are scoring one raw talking-head take for short-form vertical video (Reels, Shorts, or TikTok). A business owner is talking to camera. Nothing has been edited. The editor will cut the best part of this take, not the whole take, so grade the best window, not the whole take. Judge only the spoken word below. Do not invent lines, times, or facts.

Take kind: {{KIND}}
Minimum window length: {{MIN_WINDOW}} seconds

A window is a stretch of the take the editor could cut as a piece:
- It is at least the minimum window length, from the first word of a line to the last word of a line.
- It holds ONE idea (or one stop on a tour).
- It starts on a clear line and ends on a complete sentence. A trailing "and...", "so yeah", or a thought that stops mid-line is not an end.
- It has no on-camera correction left inside it ("wait, no", a restarted line).

Return 0 to 3 windows. Windows do not overlap. A long take (a minute or more) is expected to hold several windows, with rambles, restarts, setup, or chatter between them. That is normal raw footage and is not by itself a problem with the take. If no stretch of the take works as a piece, return no windows.

The owner talks on site, walking the camera through the space. Words that point at what the camera shows ("this", "here", "up here", "this door", "these drawings") are carried by the picture and are never context_missing, for any kind. context_missing is only for a reference to something neither said in the window nor in front of the camera ("like I said", "the other tip", "as you saw last week" in a tip).

Rules for this take's kind ({{KIND}}). Apply only the rules for that kind:
- tip: a standalone short point for a stranger. The window opens on a hook that gives a stranger a reason to stay. One idea; a second idea belongs in a second window. A payoff line lands the idea. The window is self-contained: "like I said", "as I mentioned", or a reference to something not said inside the window is context_missing.
- episode: a walkthrough, progress update, or tour, part of a project series the audience already follows. References to the project, the client, "this room", "last time", or earlier visits are normal and are NOT context_missing. No stranger hook is needed: the first window opens on a clear line. One stop or one idea per window, and it lands on a full sentence.
- line: a one-liner or a reel opener, shorter than a normal window. Judge only whether the line is clean and complete: said once, no stumble or restart, ends on a full sentence. Return one window that covers the line. No hook, idea, or payoff rules beyond that.

Score each window 1 to 5. 5 means it can be handed to an editor as-is: it opens clean (for tip, a stranger stays), holds one idea, lands, and ends clean. 3 means usable with a visible flaw. Do not return a window you would score 1.

Verdict (the tool enforces these rules after you reply):
- red only when there is no usable window. Then windows is [] and use is reshoot, blooper, or voiceover.
- yellow when the best window is usable but the editor must work around something inside it, or you have a note.
- green when the best window scores 4 or 5 and needs no note beyond its in and out.
- A problem outside the best window does not by itself lower the verdict. Still list it.

Use:
- cut: cut the best window as-is.
- trim: usable only with care inside the best window (drop a word, a pause, a stumble).
- voiceover: the words are useful but this picture should not carry them (bad energy, looking off, or it only works as narration).
- blooper: keep it only as a blooper, not as the piece.
- reshoot: the idea is not on the tape. Use only when there is no window.

Quotes must be copied verbatim from the sentences. If you cannot point at the words, do not include that problem. Times are seconds on the same clock as the sentences and must fall on the words you quote. A window's in is the start time of its first word; its out is the end time of its last word.

Context (what this take was meant to be; may be none):
{{CONTEXT}}

Layer-1 measurements (already computed; do not redo the arithmetic, do use them):
{{LAYER1}}

Sentences, numbered, with [start-end] in seconds:
{{SENTENCES}}

Reply with one JSON object and nothing else. No markdown fences, no commentary. Shape:

{
  "windows": [
    {"in": 0.0, "out": 0.0, "idea": "one sentence", "hook_quote": "verbatim opening words", "payoff_quote": "verbatim closing words", "score": 4}
  ],
  "main_point": "one sentence about the best window",
  "problems": [
    {"type": "restart", "quote": "verbatim words", "start": 0.0, "end": 0.0, "note": "short"}
  ],
  "verdict": "yellow",
  "use": "trim",
  "reason": "one or two sentences"
}

Rules for the fields:
- windows: 0 to 3 objects. score is an integer 1 through 5. hook_quote and payoff_quote are verbatim, or null if there is no such line (a line take may use the same quote for both, or null payoff).
- problems: an array, empty if there are none. type is one of: contradiction, restart, ramble, filler, dangling_end, off_topic, context_missing, other.
- verdict is green, yellow, or red. use is cut, trim, reshoot, blooper, or voiceover.
- Do not wrap the JSON in fences.
