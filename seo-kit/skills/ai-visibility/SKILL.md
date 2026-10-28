---
name: ai-visibility
description: >
  Run the business's fixed battery of buyer questions through AI engines with
  web search on (OpenAI, Perplexity, Gemini, Anthropic APIs), and log whether
  the business is named, where, which sites are cited, and any dollar figures
  to check by hand. Tracked week over week. Use when someone asks "are we
  showing up in ChatGPT / Perplexity / AI answers", "AI visibility", "GEO",
  "AEO", "what does AI say about us", or when the seo-loop reaches its AI step.
metadata:
  version: 0.1.0
---

# AI visibility

Script: `<kit>/scripts/ai_visibility.py`. Business files: `tracking/seo/prompts.yaml` (the questions), `tracking/seo/ai-visibility.jsonl` (every answer, append-only), `tracking/seo/snapshots/<date>/ai.json` (the summary).

## First time

1. Copy `<kit>/templates/prompts.yaml` to `<biz>/tracking/seo/prompts.yaml`. Rewrite the questions from the pack: what each persona would really ask an assistant (who to hire, what it costs, X vs Y, how to do the job). 15 to 25 questions. Mix: about a quarter branded ("what is <brand>"), the rest category, cost and comparison. Show them to the person before the first paid run.
2. In `config.yaml` → `ai_engines`, enable the engines that have a key in the environment, and set each `model` from the vendor's current docs. Never guess a model id.
   One OpenRouter key can stand in for all four vendor keys; set `models` and keep `search: native` so each model uses its own provider's web search.
3. `--dry-run` first: it prints the engines, skipped engines and the call count. Calls = prompts × engines × runs.

## Run

```
uv run <kit>/scripts/ai_visibility.py --config <biz>/tracking/seo/config.yaml \
  --prompts <biz>/tracking/seo/prompts.yaml --log <biz>/tracking/seo/ai-visibility.jsonl \
  --out <snapshot>/ai.json --runs 3 --max-calls 300
```

Three runs per question, because answers vary run to run. Keep the questions fixed week to week; changing them breaks the trend (log any change as a decision).

## Read the result

- **Mention rate** per engine (share of answers that name the business) and **citation rate** (share that link our domains). These are the trend lines.
- **Top cited domains:** where the engines get their answers. Domains that keep showing up and do not mention the business are the off-site gap (directories, review sites, lists, forums). Off-site mentions correlate with AI visibility more than on-site markup does; put the gap list in `needs_a_person`.
- **Unverified figures:** dollar amounts near the business name that are not in the facts file. Check each by hand. A wrong price or old fact in AI answers usually comes from an old page, an old directory listing or a stale cache: find the source domain in the log row and fix it there.

## Say this in every report

API answers with web search are a proxy. The consumer apps (ChatGPT, Google AI Overviews, Copilot) can answer differently. Bing Webmaster Tools has an AI Performance report for Copilot citations; read it by hand if the person has access.

## What moves citations (evidence, short)

- Cited sources, quotations and specific statistics in the page text (GEO paper, Aggarwal et al., KDD 2024). Keyword stuffing does not help.
- Mentions on other sites (correlation studies; not proven causal).
- Being indexed by Bing (Copilot) and Google (AI Overviews) at all.
- llms.txt: no measured effect so far. Cheap to keep, not a lever.
More detail: `<kit>/references/ai-visibility-audit.md`.
