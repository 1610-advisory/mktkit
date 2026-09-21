Read `{skill_dir}/SKILL.md` and `{skill_dir}/CHECKLIST.md` first and follow them.

Cut the content note at `{note}` through the cut-video skill in `{mode}` mode. Unattended: no questions, no approval stops.

Hard rules:
- Write the reel manifest to `{output_dir}/<content_id>.reel.json` and set its `output_dir` to `{output_dir}`.
- Pass `--style {style}`.
- do NOT set `deliver.copy_to`.
- do NOT modify any file outside `{output_dir}` (no content-note edits, no status flips, no git commits).
- One render at a time.
- Finish by printing the renderer's summary JSON line and a five-line summary: hook decision, cover line, each punch with its spoken line, QA verdict, known deviations.

Punch ladder:
- Video first from any raw clip in the index (never finished reels or another piece's A-roll), then an exact photo, else stay on the speaker.
- Never a same-category picture.
- At most two stills, never back to back. Each still starts within 0.3 s of the noun it shows.
- Every punch must carry `line` and `shows`. Write `shows` after looking at the picture, naming the object.
- Mark lines you deliberately left un-punched in your final summary with the reason.

{index}

{extra}
