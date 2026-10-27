---
name: kit-contribute
description: >
  After someone changes how the toolkit itself works (a skill, script,
  reference, template or rule meant for every business, not just theirs),
  offer once to share an anonymized version back to the open-source toolkit,
  or to stop asking forever. Also turns sharing and update checks on or off.
  Use right after a toolkit-level change is made and working, or when someone
  says "contribute this", "share this fix", "send this upstream", "stop asking
  me to contribute", "turn contributions back on", "get other people's
  improvements", or "update the toolkit".
metadata:
  version: 1.0.0
---

# Kit contribute

The toolkit is free and open source. When one business finds a better way, every business can get it. This skill asks, once per change, whether to share it. It never shares anything without a clear yes, and it is easy to switch off for good.

## Settings (per person, on their machine)

File: `~/.config/mktkit/contribute.json`. Never in a client folder, never committed.

```json
{ "ask": true, "updates": "ask" }
```

- `ask`: `true` = offer after toolkit changes. `false` = never offer, never mention it again. The toolkit works fully either way; it is the person's copy.
- `updates`: `"ask"` = at most once a week, say when a newer toolkit version exists. `"auto"` = update without asking. `"off"` = never check.

Missing file = `{ "ask": true, "updates": "ask" }`. Write the file only when the person makes a choice.

## When to offer

Only when ALL are true:
1. The change is to the **toolkit** (files in the toolkit repo or the installed plugin: `.claude/skills/`, `scripts/`, `references/`, `templates/`, `seo-kit/`, `CLAUDE.md`), not to one business's folder (`clients/*`, a business repo's `knowledge/`, `memory/`, `tracking/`). Taste for one business stays with that business.
2. It is done and it worked (a test passed, a run succeeded, the person said it is good).
3. `ask` is not `false`.
4. Not already offered for this same change.

## The question (ask exactly once, short)

> This change could help other people using the toolkit. Do you want to:
> 1. **Share it.** I strip out anything about your business, show you exactly what would be sent, and open a pull request to the open-source toolkit. People who contribute are credited, and regular contributors get invited as collaborators.
> 2. **Not this time.**
> 3. **Never ask again.** Your copy keeps working exactly as it is. You can turn this back on any time by saying "turn kit contributions back on".

Option 3 → write `"ask": false`, confirm in one line, and stop. Option 2 → stop.

## Share it (option 1)

1. **Collect only the toolkit diff.** `git diff` of the toolkit files you changed. If the toolkit is an installed plugin (path under `~/.claude/plugins/`), copy the changed files into a fresh clone of `https://github.com/1610-advisory/mktkit` first, and tell the person: edits inside an installed plugin are lost at the next update, so sharing also keeps them.
2. **Anonymize.** Replace business names, people, places, domains, emails, phone numbers, prices and other figures from one business, account and property IDs, file paths with a business name in them, and any quote from a business's content with neutral placeholders (`Acme Corp`, `example.com`, `[client-name]`, `$X`). Keep the general rule, method or fix. If the change only makes sense with the business's private details, say so and stop.
3. **Check for leaks.** Install and run the toolkit's leak check: `git config core.hooksPath .githooks`, stage, and let `.githooks/pre-commit` run. It also reads the person's own blocklist at `~/.config/ai-cmo-sanitize/blocklist.txt` if they have one; offer to add their business names to it first. Never use `SKIP_AI_CMO_SANITIZE`.
4. **Show the final diff** and a 3-line summary: what changed, why (the finding), how it was tested. Ask: "Send this?" Only a clear yes continues.
5. **Open the pull request** with the person's own GitHub login (`gh auth status`; if not logged in, ask them to run `gh auth login` themselves, never handle their credentials): `gh repo fork 1610-advisory/mktkit --clone=false`, push a branch named `community/<short-name>` to their fork, then `gh pr create --repo 1610-advisory/mktkit` with the summary as the body and the line "Contributed with the kit-contribute skill." Tell them: the pull request shows their GitHub name; the content is anonymized, the author is not.
6. **No GitHub, or they want no name on it:** write the anonymized summary and diff to a file in their working folder and point them to the suggestion box at https://1610advisory.com/toolkits/marketing/changelog (paste the summary there) or https://github.com/1610-advisory/mktkit/issues/new.
7. Log it in the business's memory log: date, what was shared, the PR link.

## Learning from others (updates)

- `updates: "ask"`: at the start of a session, at most once every 7 days, compare the installed version with the latest (`/plugin marketplace update mktkit` shows it, or `git fetch` in a clone). If newer, give the top 3 lines from `CHANGELOG.md` and ask whether to update.
- `updates: "auto"`: update, then say in one line what changed.
- `updates: "off"`: never check.
- Ask about update mode only the first time someone chooses "Share it", or when they ask.

## Never

- Never send, push or open anything without a yes to step 4.
- Never include anything from a business's folder, memory, logs, transcripts or tracking data.
- Never ask again after "never ask again", and never nag: one offer per change.
