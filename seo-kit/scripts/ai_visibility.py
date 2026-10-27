# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.27",
#     "pyyaml>=6",
# ]
# ///
"""
AI answer battery. Ask a fixed prompt list to web-search engines and log
whether the brand is named and the site is cited.

Usage:
    uv run ai_visibility.py \\
        --config tracking/seo/config.yaml \\
        --prompts tracking/seo/prompts.yaml \\
        --log tracking/seo/ai-visibility.jsonl \\
        --out tracking/seo/snapshots/2026-10-27/ai.json \\
        [--engines openai,perplexity,openrouter] [--runs 3] [--dry-run] [--max-calls 100]

--dry-run prints the plan (engines that would run, engines skipped and why,
total calls) and makes no request. Each openrouter:<model> is listed with its
own call count.

Engines come from config ai_engines. The model id is read from config and is
never defaulted. An enabled engine with an empty model is refused. Keys come
from OPENAI_API_KEY, PERPLEXITY_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
and OPENROUTER_API_KEY. A missing key skips that engine with a note. Keys are
never printed.

OpenRouter is one key for several models. Each models entry is its own engine,
named openrouter:<model>, in the plan, the log and the summary. search is
native (the provider's own web search) or exa; an empty search omits the
plugin engine. usage.cost is stored as cost_usd and summed per engine.

Each engine has a request builder and a parser that returns
{answer, cited_urls, usage}. usage token counts are stored as the API returned
them. Timeout 90 s, one retry on 429/5xx with backoff.

Unverified money figures are marked "check by hand". They are not errors.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENGINES = ("openai", "perplexity", "gemini", "anthropic")
KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
# OpenRouter asks for these so the app is identifiable. They are not secrets.
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_REFERER = "https://github.com/1610-advisory/mktkit"
OPENROUTER_TITLE = "seo-kit"
KINDS = {"branded", "category", "comparison", "cost"}
TIMEOUT_S = 90
RETRY_BACKOFF_S = 2.0
NEAR_BRAND_CHARS = 300
# Anthropic requires max_tokens. This is a length cap, not a model id.
ANTHROPIC_MAX_TOKENS = 4096
VERTEX_HOST = "vertexaisearch.cloud.google.com"
MONEY_RE = re.compile(r"\$\s?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def load_client(path: str) -> dict:
    try:
        from seo_config import load_config
    except ImportError:
        print(
            "Error: seo-kit/scripts/seo_config.py is missing (it is provided separately).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        return load_config(path)
    except Exception as exc:
        print(f"Error: could not load config: {exc}", file=sys.stderr)
        raise SystemExit(1)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_prompts(path: str) -> list[dict]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    items = raw.get("prompts") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ValueError("prompts file must be a non-empty list")
    prompts = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each prompt must be a mapping")
        prompt_id = str(item.get("id") or "").strip()
        text = str(item.get("text") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not prompt_id or not text:
            raise ValueError("each prompt needs id and text")
        if kind not in KINDS:
            raise ValueError(f"prompt {prompt_id} has unknown kind {kind!r}")
        prompts.append({"id": prompt_id, "text": text, "kind": kind})
    return prompts


def _engine_spec(config: dict, name: str) -> dict:
    engines = config.get("ai_engines") or {}
    spec = engines.get(name) or {}
    if not isinstance(spec, dict):
        return {}
    return spec


def _canon_engine_name(name: str) -> str:
    """Vendor names are case-insensitive. The model id after openrouter: is not."""
    raw = str(name or "").strip()
    lower = raw.lower()
    if lower == "openrouter":
        return "openrouter"
    if lower.startswith("openrouter:"):
        return "openrouter:" + raw.split(":", 1)[1].strip()
    return lower


def _openrouter_search(spec: dict) -> str:
    # Missing means the provider's own search. Empty string means omit engine.
    if "search" not in spec or spec.get("search") is None:
        return "native"
    value = spec.get("search")
    if not isinstance(value, str):
        return "native"
    return value.strip()


def _openrouter_models(spec: dict) -> list[str] | str:
    """A deduped model list, or an error reason if the field is unusable."""
    raw = spec.get("models")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return "models must be a list"
    models = []
    for item in raw:
        model = str(item).strip()
        if model and model not in models:
            models.append(model)
    return models


def _plan_openrouter(name, config, env, would_run, skipped, refused, planned) -> None:
    spec = _engine_spec(config, "openrouter")
    specific = name.startswith("openrouter:")
    wanted = name.split(":", 1)[1].strip() if specific else ""
    label = name if specific else "openrouter"
    if not spec.get("enabled"):
        skipped.append({"engine": label, "reason": "disabled in config"})
        return
    if specific and not wanted:
        refused.append({"engine": name, "reason": "refusing to run openrouter: model is empty"})
        return
    models = _openrouter_models(spec)
    if isinstance(models, str):
        refused.append({"engine": label, "reason": f"refusing to run openrouter: {models}"})
        return
    if specific:
        if wanted not in models:
            refused.append({"engine": name, "reason": f"refusing to run {name}: model is not in openrouter.models"})
            return
        models = [wanted]
    elif not models:
        refused.append({"engine": "openrouter", "reason": "refusing to run openrouter: models is empty"})
        return
    if not read_api_key(env, "openrouter"):
        for model in models:
            engine_name = f"openrouter:{model}"
            if engine_name in planned:
                continue
            planned.add(engine_name)
            skipped.append({"engine": engine_name, "reason": "missing OPENROUTER_API_KEY"})
        return
    search = _openrouter_search(spec)
    for model in models:
        engine_name = f"openrouter:{model}"
        if engine_name in planned:
            continue
        planned.add(engine_name)
        would_run.append({
            "engine": engine_name,
            "model": model,
            "provider": "openrouter",
            "search": search,
        })


def plan_calls(
    config: dict,
    prompts: list[dict],
    engines: list[str] | None,
    runs: int,
    env: dict,
    max_calls: int,
) -> dict:
    """Decide which engines would run. Does not read the network."""
    if engines:
        selected = []
        for name in engines:
            canon = _canon_engine_name(name)
            if canon:
                selected.append(canon)
    else:
        selected = list(ENGINES)
        if "openrouter" in (config.get("ai_engines") or {}):
            selected.append("openrouter")
    would_run = []
    skipped = []
    refused = []
    seen = set()
    planned = set()
    for name in selected:
        if name in seen:
            continue
        seen.add(name)
        if name == "openrouter" or name.startswith("openrouter:"):
            _plan_openrouter(name, config, env, would_run, skipped, refused, planned)
            continue
        if name not in ENGINES:
            refused.append({"engine": name, "reason": f"unknown engine {name}"})
            continue
        spec = _engine_spec(config, name)
        if not spec.get("enabled"):
            skipped.append({"engine": name, "reason": "disabled in config"})
            continue
        model = str(spec.get("model") or "").strip()
        if not model:
            refused.append({"engine": name, "reason": f"refusing to run {name}: model is empty"})
            continue
        if name == "anthropic" and not str(spec.get("tool") or "").strip():
            refused.append({"engine": name, "reason": f"refusing to run {name}: tool type is empty"})
            continue
        key_name = KEY_ENV[name]
        if not read_api_key(env, name):
            skipped.append({"engine": name, "reason": f"missing {key_name}"})
            continue
        item = {"engine": name, "model": model}
        if name == "anthropic":
            item["tool"] = str(spec.get("tool")).strip()
        would_run.append(item)
    per_engine_calls = len(prompts) * runs
    for item in would_run:
        item["calls"] = per_engine_calls
    total = per_engine_calls * len(would_run)
    return {
        "would_run": would_run,
        "skipped": skipped,
        "refused": refused,
        "total_calls": total,
        "capped_calls": min(total, max_calls),
        "runs": runs,
        "prompts": len(prompts),
        "max_calls": max_calls,
    }


def format_plan(plan: dict) -> str:
    lines = ["would run:"]
    if plan["would_run"]:
        for item in plan["would_run"]:
            extra = f" tool={item['tool']}" if item.get("tool") else ""
            if "search" in item:
                shown = item["search"] if item["search"] else "(omitted)"
                extra += f" search={shown}"
            if item.get("calls") is not None:
                extra += f" calls={item['calls']}"
            lines.append(f"- {item['engine']} model={item['model']}{extra}")
    else:
        lines.append("- (none)")
    lines.append("skipped:")
    notes = plan["skipped"] + plan["refused"]
    if notes:
        for item in notes:
            lines.append(f"- {item['engine']}: {item['reason']}")
    else:
        lines.append("- (none)")
    lines.append(f"total calls: {plan['total_calls']}")
    if plan["capped_calls"] < plan["total_calls"]:
        lines.append(f"max-calls would stop at {plan['capped_calls']}")
    return "\n".join(lines)


def read_api_key(env: dict, engine: str) -> str:
    """Strip the key once at the read. Callers must use this value, not the raw env string."""
    return str(env.get(KEY_ENV[engine]) or "").strip()


def call_budget(limit: int) -> dict:
    return {"limit": limit, "made": 0, "capped": False}


def build_openai_request(model: str, prompt: str, api_key: str) -> dict:
    return {
        "method": "POST",
        "url": "https://api.openai.com/v1/responses",
        "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        "json": {"model": model, "input": prompt, "tools": [{"type": "web_search"}]},
        "timeout": TIMEOUT_S,
    }


def build_perplexity_request(model: str, prompt: str, api_key: str) -> dict:
    return {
        "method": "POST",
        "url": "https://api.perplexity.ai/chat/completions",
        "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        "json": {"model": model, "messages": [{"role": "user", "content": prompt}]},
        "timeout": TIMEOUT_S,
    }


def build_gemini_request(model: str, prompt: str, api_key: str) -> dict:
    encoded = quote(model, safe="")
    return {
        "method": "POST",
        "url": f"https://generativelanguage.googleapis.com/v1beta/models/{encoded}:generateContent",
        "headers": {"x-goog-api-key": api_key, "Content-Type": "application/json"},
        "json": {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        },
        "timeout": TIMEOUT_S,
    }


def build_anthropic_request(model: str, prompt: str, api_key: str, tool: str) -> dict:
    return {
        "method": "POST",
        "url": "https://api.anthropic.com/v1/messages",
        "headers": {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        "json": {
            "model": model,
            "max_tokens": ANTHROPIC_MAX_TOKENS,
            "tools": [{"type": tool, "name": "web_search", "max_uses": 3}],
            "messages": [{"role": "user", "content": prompt}],
        },
        "timeout": TIMEOUT_S,
    }


def build_openrouter_request(model: str, prompt: str, api_key: str, search: str = "native") -> dict:
    plugin = {"id": "web"}
    # Empty search means "do not pin an engine"; the key is omitted, not sent blank.
    if search:
        plugin["engine"] = search
    return {
        "method": "POST",
        "url": OPENROUTER_URL,
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": OPENROUTER_REFERER,
            "X-Title": OPENROUTER_TITLE,
        },
        "json": {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "plugins": [plugin],
            "usage": {"include": True},
        },
        "timeout": TIMEOUT_S,
    }


def build_request(engine: str, model: str, prompt: str, api_key: str, tool: str = "", search: str = "native") -> dict:
    if engine == "openai":
        return build_openai_request(model, prompt, api_key)
    if engine == "perplexity":
        return build_perplexity_request(model, prompt, api_key)
    if engine == "gemini":
        return build_gemini_request(model, prompt, api_key)
    if engine == "anthropic":
        return build_anthropic_request(model, prompt, api_key, tool)
    if engine == "openrouter":
        return build_openrouter_request(model, prompt, api_key, search)
    raise ValueError(f"unknown engine {engine}")


def _dedupe(urls: list[str]) -> list[str]:
    seen = set()
    out = []
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def parse_openai_response(payload: dict) -> dict:
    texts = []
    urls = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str):
            texts.append(content)
            continue
        for part in content or []:
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                texts.append(part["text"])
            for note in part.get("annotations") or []:
                if isinstance(note, dict) and note.get("type") == "url_citation" and note.get("url"):
                    urls.append(note["url"])
    return {
        "answer": "\n".join(texts),
        "cited_urls": _dedupe(urls),
        "retrieved_urls": [],
        "usage": payload.get("usage"),
    }


def parse_perplexity_response(payload: dict) -> dict:
    choices = payload.get("choices") or []
    message = (choices[0].get("message") if choices else {}) or {}
    answer = message.get("content") or ""
    cited = []
    for cite in payload.get("citations") or []:
        if isinstance(cite, str):
            cited.append(cite)
        elif isinstance(cite, dict) and cite.get("url"):
            cited.append(cite["url"])
    retrieved = []
    for result in payload.get("search_results") or []:
        if isinstance(result, dict) and result.get("url"):
            retrieved.append(result["url"])
    return {
        "answer": answer,
        "cited_urls": _dedupe(cited),
        "retrieved_urls": _dedupe(retrieved),
        "usage": payload.get("usage"),
    }


def _gemini_chunk_url(web: dict) -> str | None:
    """Grounding proxy URIs hide the real host in web.title."""
    uri = str(web.get("uri") or "").strip()
    title = str(web.get("title") or "").strip()
    host = (urlparse(uri).hostname or "").lower()
    proxy = host == VERTEX_HOST or "grounding-api-redirect" in uri
    if not proxy:
        return uri or None
    if title and "." in title and " " not in title:
        if title.startswith(("http://", "https://")):
            return title
        return "https://" + title
    return uri or None


def parse_gemini_response(payload: dict) -> dict:
    candidates = payload.get("candidates") or []
    candidate = candidates[0] if candidates else {}
    texts = []
    for part in ((candidate.get("content") or {}).get("parts") or []):
        if isinstance(part, dict) and part.get("text"):
            texts.append(part["text"])
    urls = []
    grounding = candidate.get("groundingMetadata") or {}
    for chunk in grounding.get("groundingChunks") or []:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not isinstance(web, dict):
            continue
        cited = _gemini_chunk_url(web)
        if cited:
            urls.append(cited)
    return {
        "answer": "\n".join(texts),
        "cited_urls": _dedupe(urls),
        "retrieved_urls": [],
        "usage": payload.get("usageMetadata"),
    }


def _anthropic_result_urls(content) -> list[str]:
    urls = []
    blocks = content if isinstance(content, list) else []
    for block in blocks:
        if isinstance(block, dict) and block.get("url"):
            urls.append(block["url"])
    return urls


def parse_anthropic_response(payload: dict) -> dict:
    texts = []
    cited = []
    retrieved = []
    for block in payload.get("content") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            if block.get("text"):
                texts.append(block["text"])
            for cite in block.get("citations") or []:
                if isinstance(cite, dict) and cite.get("url"):
                    cited.append(cite["url"])
        elif block.get("type") == "web_search_tool_result":
            retrieved.extend(_anthropic_result_urls(block.get("content")))
    return {
        "answer": "\n".join(texts),
        "cited_urls": _dedupe(cited),
        "retrieved_urls": _dedupe(retrieved),
        "usage": payload.get("usage"),
    }


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("text"):
                parts.append(str(part["text"]))
        return "\n".join(parts)
    return ""


def parse_openrouter_response(payload: dict) -> dict:
    """OpenRouter nests citation URLs under annotations[].url_citation.url.

    Perplexity models may also return a top-level citations list. Both count.
    """
    choices = payload.get("choices") or []
    first = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = first.get("message") or {}
    if not isinstance(message, dict):
        message = {}
    urls = []
    for note in message.get("annotations") or []:
        if not isinstance(note, dict) or note.get("type") != "url_citation":
            continue
        citation = note.get("url_citation") or {}
        if isinstance(citation, dict) and citation.get("url"):
            urls.append(citation["url"])
    for cite in payload.get("citations") or []:
        if isinstance(cite, str):
            urls.append(cite)
        elif isinstance(cite, dict) and cite.get("url"):
            urls.append(cite["url"])
    return {
        "answer": _message_text(message.get("content")),
        "cited_urls": _dedupe(urls),
        "retrieved_urls": [],
        "usage": payload.get("usage"),
    }


PARSERS = {
    "openai": parse_openai_response,
    "perplexity": parse_perplexity_response,
    "gemini": parse_gemini_response,
    "anthropic": parse_anthropic_response,
    "openrouter": parse_openrouter_response,
}


def mention_spans(text: str, name: str) -> list[tuple[int, int]]:
    cleaned = (name or "").strip()
    if not cleaned:
        return []
    pattern = re.compile(r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)", re.IGNORECASE)
    return [(match.start(), match.end()) for match in pattern.finditer(text or "")]


def _first_span(text: str, names: list[str]) -> tuple[int, int] | None:
    spans = []
    for name in names:
        spans.extend(mention_spans(text, name))
    if not spans:
        return None
    return min(spans, key=lambda span: span[0])


def brand_names(brand: str, aliases: list[str] | None) -> list[str]:
    names = []
    for name in [brand, *(aliases or [])]:
        if name and str(name).strip() and str(name).strip() not in names:
            names.append(str(name).strip())
    return names


def brand_mentioned(text: str, brand: str, aliases: list[str] | None = None) -> bool:
    return _first_span(text, brand_names(brand, aliases)) is not None


def competitors_mentioned(text: str, competitors: list[str] | None) -> list[str]:
    found = []
    for name in competitors or []:
        spans = mention_spans(text, name)
        if spans:
            found.append((spans[0][0], name))
    found.sort(key=lambda item: item[0])
    return [name for _, name in found]


def brand_position(
    text: str,
    brand: str,
    aliases: list[str] | None = None,
    competitors: list[str] | None = None,
) -> int | None:
    """1-based rank of the first brand mention among first mentions of brand + competitors."""
    entries = []
    brand_span = _first_span(text, brand_names(brand, aliases))
    if brand_span is not None:
        entries.append((brand_span[0], "brand"))
    for name in competitors or []:
        spans = mention_spans(text, name)
        if spans:
            entries.append((spans[0][0], "competitor"))
    if brand_span is None:
        return None
    entries.sort(key=lambda item: item[0])
    for index, (_start, kind) in enumerate(entries, start=1):
        if kind == "brand":
            return index
    return None


def host_of(url: str) -> str | None:
    try:
        host = urlparse(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def host_matches(host: str, domains: list[str]) -> bool:
    host = host.lower().rstrip(".")
    for domain in domains:
        domain = str(domain).lower().rstrip(".")
        if domain.startswith("www."):
            domain = domain[4:]
        if host == domain or host.endswith("." + domain):
            return True
    return False


def our_url_cited(urls: list[str], domains: list[str]) -> bool:
    for url in urls or []:
        host = host_of(url)
        if host and host_matches(host, domains):
            return True
    return False


def cited_domains(urls: list[str]) -> list[str]:
    """Registrable-ish host: lowercase, strip a leading www. only."""
    seen = set()
    out = []
    for url in urls or []:
        host = host_of(url)
        if not host or host in seen or host == VERTEX_HOST:
            continue
        seen.add(host)
        out.append(host)
    return out


def money_figures(text: str) -> list[str]:
    return [match.group(0).replace(" ", "") for match in MONEY_RE.finditer(text or "")]


def money_spans(text: str) -> list[tuple[int, int, str]]:
    return [(match.start(), match.end(), match.group(0).replace(" ", "")) for match in MONEY_RE.finditer(text or "")]


def money_key(figure: str) -> str | None:
    cleaned = re.sub(r"[$,\s]", "", figure)
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def figure_in_facts(figure: str, facts: str) -> bool:
    key = money_key(figure)
    if key is None:
        return False
    for other in money_figures(facts or ""):
        if money_key(other) == key:
            return True
    return False


def _near(span: tuple[int, int], anchors: list[tuple[int, int]], window: int = NEAR_BRAND_CHARS) -> bool:
    start, end = span
    for anchor_start, anchor_end in anchors:
        if end < anchor_start:
            gap = anchor_start - end
        elif anchor_end < start:
            gap = start - anchor_end
        else:
            gap = 0
        if gap <= window:
            return True
    return False


def unverified_figures(
    text: str,
    brand: str,
    aliases: list[str] | None,
    facts: str,
) -> list[dict]:
    """Money figures within 300 chars of a brand mention that are not in the facts file.

    Each item is marked check-by-hand. This is not an error.
    """
    anchors = []
    for name in brand_names(brand, aliases):
        anchors.extend(mention_spans(text, name))
    found = []
    seen = set()
    for start, end, figure in money_spans(text):
        if figure in seen:
            continue
        if not _near((start, end), anchors):
            continue
        if figure_in_facts(figure, facts):
            continue
        seen.add(figure)
        found.append({"figure": figure, "note": "check by hand"})
    return found


def _string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value]
    except TypeError:
        return [str(value)]


def analyze(
    text: str,
    cited_urls: list[str],
    config: dict,
    facts: str,
    retrieved_urls: list[str] | None = None,
) -> dict:
    brand = config.get("brand") or ""
    aliases = _string_list(config.get("brand_aliases"))
    competitors = _string_list(config.get("competitors"))
    domains = _string_list(config.get("domains"))
    return {
        "brand_mentioned": brand_mentioned(text, brand, aliases),
        "brand_position": brand_position(text, brand, aliases, competitors),
        "our_url_cited": our_url_cited(cited_urls, domains),
        "our_url_retrieved": our_url_cited(retrieved_urls or [], domains),
        "cited_domains": cited_domains(cited_urls),
        "competitors_mentioned": competitors_mentioned(text, competitors),
        "money_figures": money_figures(text),
        "unverified_figures": unverified_figures(text, brand, aliases, facts),
    }


def redact(text: str, secrets: list[str]) -> str:
    out = text
    for secret in secrets:
        if not secret:
            continue
        out = out.replace(secret, "[redacted]")
        # Exception text often contains repr(secret) without the surrounding quotes.
        escaped = repr(secret)[1:-1]
        if escaped and escaped != secret:
            out = out.replace(escaped, "[redacted]")
    return out


def request_with_retry(
    do_request,
    sleep_fn=time.sleep,
    retries: int = 1,
    backoff: float = RETRY_BACKOFF_S,
    budget: dict | None = None,
):
    """One retry on 429/5xx or a transport error. do_request() -> (status, body, error).

    Each HTTP attempt, including the retry, counts against budget when one is passed.
    """
    if budget is not None and budget["made"] >= budget["limit"]:
        budget["capped"] = True
        return None, None, "max-calls reached"
    last = (None, None, "no attempt")
    for attempt in range(retries + 1):
        if budget is not None and budget["made"] >= budget["limit"]:
            budget["capped"] = True
            break
        if budget is not None:
            budget["made"] += 1
        status, body, error = do_request()
        last = (status, body, error)
        # Transport errors have no status. 400-class responses are not retried.
        retryable = status is None or status == 429 or (isinstance(status, int) and status >= 500)
        if retryable and attempt < retries:
            sleep_fn(backoff * (2 ** attempt))
            continue
        break
    return last


def perform_request(request: dict, client, sleep_fn=time.sleep, secrets: list[str] | None = None, budget: dict | None = None):
    secrets = secrets or []

    def once():
        try:
            resp = client.request(
                request["method"],
                request["url"],
                headers=request["headers"],
                json=request["json"],
                timeout=request["timeout"],
            )
        except Exception as exc:
            return None, None, redact(f"{type(exc).__name__}: {exc}", secrets)[:300]
        try:
            body = resp.json()
        except Exception:
            body = {"_raw": redact(resp.text[:300], secrets)}
        if resp.status_code >= 400:
            return resp.status_code, body, redact(_error_text(resp.status_code, body), secrets)
        return resp.status_code, body, None

    return request_with_retry(once, sleep_fn=sleep_fn, budget=budget)


def _error_text(status: int, body) -> str:
    # Keep the vendor's reason: a 429 can mean "out of credits", not just "slow down".
    # 401/403 messages can echo a masked key, so keep only the status and error code.
    err = body.get("error") if isinstance(body, dict) else None
    if status in (401, 403):
        code = ""
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or err.get("status") or "").strip()
        if code:
            return f"HTTP {status} {code}"
        return f"HTTP {status}"
    if isinstance(err, dict):
        detail = err.get("code") or err.get("type") or err.get("status") or ""
        message = str(err.get("message") or "")[:160]
        return f"HTTP {status} {detail}: {message}".strip()
    if isinstance(err, str):
        return f"HTTP {status}: {err[:160]}"
    return f"HTTP {status}"


def _openrouter_error_text(err) -> str:
    """Body error object: code plus a short message. 401/403 keep the code only."""
    if isinstance(err, str):
        return err.replace("\n", " ").strip()[:160] or "error"
    if not isinstance(err, dict):
        return "error"
    raw_code = err.get("code")
    if raw_code is None:
        raw_code = err.get("type") or err.get("status") or ""
    code = str(raw_code).strip()
    message = str(err.get("message") or "").replace("\n", " ").strip()[:160]
    if code in ("401", "403"):
        return code
    if code and message:
        return f"{code}: {message}"
    return code or message or "error"


def response_error(engine: str, payload: dict, parsed: dict) -> str | None:
    """A 200 can still be a failed answer. Return a short error, or None."""
    if engine == "openrouter" or str(engine).startswith("openrouter:"):
        if not isinstance(payload, dict):
            return "openrouter no choices"
        err = payload.get("error")
        if err:
            return _openrouter_error_text(err)
        if not payload.get("choices"):
            return "openrouter no choices"
    if engine == "openai":
        status = payload.get("status")
        if status is not None and status != "completed":
            return f"openai status {status}"
    if engine == "anthropic":
        stop = payload.get("stop_reason")
        if stop in ("pause_turn", "max_tokens"):
            return f"anthropic stop_reason {stop}"
    if engine == "gemini":
        feedback = payload.get("promptFeedback") or {}
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            return f"gemini blockReason {feedback.get('blockReason')}"
        if not payload.get("candidates"):
            return "gemini no candidates"
    if not str(parsed.get("answer") or "").strip():
        return "empty answer"
    return None


def empty_analysis() -> dict:
    return {
        "brand_mentioned": False,
        "brand_position": None,
        "our_url_cited": False,
        "our_url_retrieved": False,
        "cited_domains": [],
        "competitors_mentioned": [],
        "money_figures": [],
        "unverified_figures": [],
    }


def read_facts(config: dict) -> str:
    raw = config.get("facts_file") or ""
    if not raw:
        return ""
    path = Path(raw)
    if not path.is_absolute():
        root = config.get("repo_root")
        if not root:
            return ""
        path = Path(root) / path
    if not path.is_file():
        print(f"facts file missing, near-brand figures will be unverified: {path.name}", file=sys.stderr)
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _open_jsonl(path: str):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    return out.open("a", encoding="utf-8")


def _write_jsonl_row(handle, row: dict) -> None:
    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    handle.flush()


def _parse_cost(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, (int, float, str)):
        try:
            parsed = Decimal(str(value))
        except InvalidOperation:
            return None
    else:
        return None
    if not parsed.is_finite():
        return None
    return parsed


def _json_cost(value: Decimal) -> int | float:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        return 0
    if "." not in text:
        return int(text)
    return float(text)


def cost_usd_of(usage) -> int | float | None:
    """usage.cost when the API returned one. Absent means do not record cost_usd."""
    if not isinstance(usage, dict) or "cost" not in usage:
        return None
    parsed = _parse_cost(usage.get("cost"))
    if parsed is None:
        return None
    return _json_cost(parsed)


def run_battery(
    prompts: list[dict],
    engines: list[dict],
    runs: int,
    call_fn,
    max_calls: int,
    facts: str,
    config: dict,
    clock=utc_now,
    *,
    log_path: str | None = None,
    budget: dict | None = None,
) -> list[dict]:
    """call_fn(engine_item, prompt_text) -> {answer, cited_urls, usage, error}.

    Order is prompt, run, engine so a call cap does not starve later engines.
    When budget is set, HTTP attempts (including retries) count against it.
    Otherwise each scheduled call counts as one against max_calls.
    """
    records = []
    scheduled = 0
    stopped = False
    handle = _open_jsonl(log_path) if log_path else None
    try:
        for prompt in prompts:
            if stopped:
                break
            for run in range(1, runs + 1):
                if stopped:
                    break
                for engine in engines:
                    if budget is not None:
                        if budget["made"] >= budget["limit"]:
                            budget["capped"] = True
                            stopped = True
                            break
                    elif scheduled >= max_calls:
                        stopped = True
                        break
                    if budget is None:
                        scheduled += 1
                    try:
                        result = call_fn(engine, prompt["text"])
                    except Exception as exc:
                        result = {
                            "answer": "",
                            "cited_urls": [],
                            "retrieved_urls": [],
                            "usage": None,
                            "error": type(exc).__name__,
                        }
                    answer = result.get("answer") or ""
                    cited = result.get("cited_urls") or []
                    retrieved = result.get("retrieved_urls") or []
                    error = result.get("error")
                    usage = result.get("usage")
                    try:
                        analysis = analyze(answer, cited, config, facts, retrieved)
                    except Exception as exc:
                        analysis = empty_analysis()
                        if not error:
                            error = f"analyze failed: {type(exc).__name__}"
                    row = {
                        "ts": clock(),
                        "engine": engine["engine"],
                        "model": engine["model"],
                        "prompt_id": prompt["id"],
                        "kind": prompt["kind"],
                        "run": run,
                        "answer": answer,
                        "cited_urls": cited,
                        "retrieved_urls": retrieved,
                        **analysis,
                        "usage": usage,
                        "error": error,
                    }
                    # Charged failures still cost money, so record cost even when error is set.
                    cost = cost_usd_of(usage)
                    if cost is not None:
                        row["cost_usd"] = cost
                    records.append(row)
                    if handle is not None:
                        _write_jsonl_row(handle, row)
    finally:
        if handle is not None:
            handle.close()
    return records


def _rate(numerator: int, denominator: int):
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _avg(values: list[float]):
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def build_summary(
    records: list[dict],
    prompts: int,
    runs: int,
    generated_at: str,
    skipped: list[dict],
    *,
    capped: bool = False,
    calls_made: int | None = None,
) -> dict:
    by_engine: dict[str, dict] = {}
    for row in records:
        bucket = by_engine.setdefault(
            row["engine"],
            {"calls": 0, "ok": 0, "mentions": 0, "citations": 0, "positions": [], "cost": None},
        )
        bucket["calls"] += 1
        cost = _parse_cost(row.get("cost_usd"))
        if cost is not None:
            bucket["cost"] = cost if bucket["cost"] is None else bucket["cost"] + cost
        if row.get("error"):
            continue
        bucket["ok"] += 1
        if row.get("brand_mentioned"):
            bucket["mentions"] += 1
        if row.get("our_url_cited"):
            bucket["citations"] += 1
        if row.get("brand_position") is not None:
            bucket["positions"].append(row["brand_position"])
    summary = {}
    for engine, bucket in by_engine.items():
        summary[engine] = {
            "calls": bucket["calls"],
            "failed": bucket["calls"] - bucket["ok"],
            "mention_rate": _rate(bucket["mentions"], bucket["ok"]),
            "citation_rate": _rate(bucket["citations"], bucket["ok"]),
            "avg_position": _avg(bucket["positions"]),
            "cost_usd": 0 if bucket["cost"] is None else _json_cost(bucket["cost"]),
        }

    by_prompt_acc: dict[str, dict] = {}
    for row in records:
        bucket = by_prompt_acc.setdefault(
            row["prompt_id"],
            {"id": row["prompt_id"], "kind": row["kind"], "calls": 0, "ok": 0, "mentions": 0, "citations": 0, "positions": []},
        )
        bucket["calls"] += 1
        if row.get("error"):
            continue
        bucket["ok"] += 1
        if row.get("brand_mentioned"):
            bucket["mentions"] += 1
        if row.get("our_url_cited"):
            bucket["citations"] += 1
        if row.get("brand_position") is not None:
            bucket["positions"].append(row["brand_position"])
    by_prompt = []
    for bucket in by_prompt_acc.values():
        by_prompt.append(
            {
                "id": bucket["id"],
                "kind": bucket["kind"],
                "calls": bucket["calls"],
                "mention_rate": _rate(bucket["mentions"], bucket["ok"]),
                "citation_rate": _rate(bucket["citations"], bucket["ok"]),
                "avg_position": _avg(bucket["positions"]),
            }
        )

    domain_counts: dict[str, int] = {}
    for row in records:
        if row.get("error"):
            continue
        for domain in row.get("cited_domains") or []:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    top_cited = sorted(domain_counts.items(), key=lambda item: (-item[1], item[0]))

    unverified = []
    for row in records:
        for item in row.get("unverified_figures") or []:
            unverified.append(
                {
                    "engine": row["engine"],
                    "prompt_id": row["prompt_id"],
                    "run": row["run"],
                    "figure": item.get("figure"),
                    "note": "check by hand",
                }
            )
    return {
        "generated_at": generated_at,
        "prompts": prompts,
        "runs": runs,
        "summary": summary,
        "by_prompt": by_prompt,
        "top_cited_domains": [[domain, count] for domain, count in top_cited],
        "unverified_figures": unverified,
        "skipped": skipped,
        "capped": bool(capped),
        "calls_made": len(records) if calls_made is None else calls_made,
    }


def append_jsonl(path: str, records: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ask buyer questions to AI engines and log brand mentions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _error(message: str) -> None:
        print(f"Error: {message}", file=sys.stderr)
        raise SystemExit(1)

    parser.error = _error  # type: ignore[method-assign]
    parser.add_argument("--config", required=True)
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--log", required=True, help="JSONL log, appended")
    parser.add_argument("--out", required=True, help="Summary JSON path")
    parser.add_argument(
        "--engines",
        help="Comma-separated subset: openai,perplexity,gemini,anthropic,openrouter or openrouter:<model>",
    )
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-calls", type=int, default=100)
    return parser


def _provider(engine: dict) -> str:
    provider = str(engine.get("provider") or "").strip()
    if provider:
        return provider
    name = str(engine.get("engine") or "")
    if name.startswith("openrouter:"):
        return "openrouter"
    return name


def _live_call(engine: dict, prompt: str, env: dict, client, sleep_fn, budget: dict | None = None):
    provider = _provider(engine)
    key = read_api_key(env, provider)
    request = build_request(
        provider,
        engine["model"],
        prompt,
        key,
        engine.get("tool", ""),
        engine.get("search", "native"),
    )
    status, body, error = perform_request(request, client, sleep_fn=sleep_fn, secrets=[key], budget=budget)
    if error or not isinstance(body, dict):
        return {
            "answer": "",
            "cited_urls": [],
            "retrieved_urls": [],
            "usage": None,
            "error": error or f"HTTP {status}",
        }
    parsed = PARSERS[provider](body)
    parsed.setdefault("retrieved_urls", [])
    err = response_error(provider, body, parsed)
    if err:
        err = redact(err, [key])
    parsed["error"] = err
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.runs < 1:
        print("Error: --runs must be at least 1.", file=sys.stderr)
        return 1
    if args.max_calls < 0:
        print("Error: --max-calls must be 0 or more.", file=sys.stderr)
        return 1
    config = load_client(args.config)
    try:
        prompts = load_prompts(args.prompts)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Error: could not load prompts: {exc}", file=sys.stderr)
        return 1
    requested = None
    if args.engines:
        requested = [_canon_engine_name(part) for part in args.engines.split(",") if part.strip()]
    plan = plan_calls(config, prompts, requested, args.runs, os.environ, args.max_calls)
    if args.dry_run:
        print(format_plan(plan))
        print(
            f"ai-visibility dry-run: {len(plan['would_run'])} engines, {plan['total_calls']} calls, no request",
            file=sys.stderr,
        )
        return 0
    if plan["refused"]:
        for item in plan["refused"]:
            print(f"Error: {item['reason']}", file=sys.stderr)
        return 1
    if not plan["would_run"]:
        for item in plan["skipped"]:
            print(f"skipped {item['engine']}: {item['reason']}", file=sys.stderr)
        print("Error: no engines to run.", file=sys.stderr)
        return 1
    for item in plan["skipped"]:
        print(f"skipped {item['engine']}: {item['reason']}", file=sys.stderr)
    facts = read_facts(config)
    budget = call_budget(args.max_calls)

    def call_fn(engine, prompt):
        with httpx.Client() as client:
            return _live_call(engine, prompt, os.environ, client, time.sleep, budget=budget)

    records = run_battery(
        prompts,
        plan["would_run"],
        args.runs,
        call_fn,
        args.max_calls,
        facts,
        config,
        log_path=args.log,
        budget=budget,
    )
    summary = build_summary(
        records,
        len(prompts),
        args.runs,
        utc_now(),
        plan["skipped"] + plan["refused"],
        capped=bool(budget["capped"]),
        calls_made=budget["made"],
    )
    write_json(args.out, summary)
    failed = sum(1 for row in records if row.get("error"))
    print(
        f"ai-visibility: {len(records)} calls, {failed} failed, wrote {args.out}",
        file=sys.stderr,
    )
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
