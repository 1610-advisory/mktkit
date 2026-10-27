# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
Crawl a site and write a JSON snapshot of pages, robots, and issues.

Usage:
    uv run site_crawl.py --config tracking/seo/config.yaml --out tracking/seo/snapshots/2026-10-27/crawl.json

Seeds from the sitemap (including sitemap index files) and from internal links.
Stays on the config site host. www is the same host. Does not follow redirects
automatically: each hop is fetched on its own, up to 5 hops, and the chain is
recorded. Delay between requests defaults to 0.3 seconds.

Environment variables:
    none

Commands:
    (single action; no subcommands)
"""

from __future__ import annotations

import argparse
import gzip
import http.client
import json
import re
import socket
import ssl
import sys
import time
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, urldefrag
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_config import load_config

USER_AGENT = "seo-kit-crawler/0.1 (+https://github.com/1610-advisory/mktkit)"
MAX_BYTES = 2_000_000
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_HOPS = 5
BOTS = (
    "GPTBot",
    "OAI-SearchBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Bingbot",
    "Googlebot",
)
# Googlebot and Bingbot are search crawlers, not AI bots, but the issue code
# in the spec covers this whole list. Severity is higher when search is blocked.
SEARCH_BOTS = {"Googlebot", "Bingbot"}
SEVERITY = {
    "broken_internal_link": "high",
    "sitemap_non_200": "high",
    "sitemap_noindex": "high",
    "missing_title": "high",
    "canonical_mismatch": "high",
    "sitemap_redirect": "medium",
    "sitemap_non_html": "medium",
    "title_too_long": "medium",
    "duplicate_title": "medium",
    "missing_description": "medium",
    "description_length": "medium",
    "duplicate_description": "medium",
    "h1_count": "medium",
    "canonical_missing": "medium",
    "not_in_sitemap": "medium",
    "jsonld_parse_error": "medium",
    "jsonld_entity_no_id": "medium",
    "jsonld_entity_ids_differ": "medium",
    "redirect_chain": "medium",
    "orphan": "medium",
    "robots_blocks_ai_bot": "medium",
    "img_missing_alt": "low",
    "noindex_linked": "low",
    "thin_inbound": "low",
    "llms_txt_missing": "low",
    "jsonld_org_incomplete": "low",
    "sitemap_lastmod_uniform": "low",
}
SEV_RANK = {"high": 0, "medium": 1, "low": 2}


class NetworkError(Exception):
    """The site or sitemap could not be read. CLI exits 2."""


def bare_host(host: str | None) -> str:
    host = (host or "").lower().rstrip(".")
    if host.startswith("www."):
        return host[4:]
    return host


def same_site(url: str, site: str) -> bool:
    host = bare_host(urlparse(url).hostname)
    site_host = bare_host(urlparse(site).hostname)
    return bool(host) and host == site_host


def strip_fragment(url: str) -> str:
    clean, _frag = urldefrag(url)
    return clean


def normalize_url(url: str) -> str:
    """Identity key: ignore fragment, trailing slash, and a leading www."""
    parsed = urlparse(strip_fragment(url.strip()))
    if not parsed.scheme or not parsed.hostname:
        return strip_fragment(url.strip())
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{bare_host(parsed.hostname)}{path}{query}"


def slash_key(url: str) -> str:
    """Compare canonical to final URL. Ignore trailing slash only, keep www."""
    parsed = urlparse(strip_fragment(url.strip()))
    if not parsed.scheme or not parsed.hostname:
        return strip_fragment(url.strip())
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{path}{query}"


def should_skip(url: str, skip_links: list[str]) -> bool:
    return any(part and part in url for part in skip_links)


def resolve_link(href: str, page_url: str) -> str | None:
    href = (href or "").strip()
    if not href:
        return None
    lower = href.lower()
    if lower.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    absolute = strip_fragment(urljoin(page_url, href))
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return absolute


def header_value(headers: dict, name: str) -> str | None:
    values = headers.get(name.lower()) or []
    if not values:
        return None
    return ", ".join(values)


def _split_link_values(header: str) -> list[str]:
    """Split a Link header on commas that are outside quotes and <URI>s."""
    parts: list[str] = []
    buf: list[str] = []
    in_quotes = False
    quote = ""
    angle = 0
    for ch in header:
        if in_quotes:
            buf.append(ch)
            if ch == quote:
                in_quotes = False
            continue
        if ch in "\"'":
            in_quotes = True
            quote = ch
            buf.append(ch)
            continue
        if ch == "<":
            angle += 1
            buf.append(ch)
            continue
        if ch == ">" and angle:
            angle -= 1
            buf.append(ch)
            continue
        if ch == "," and angle == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def has_canonical_link(header: str | None) -> bool:
    """True when an HTTP Link header has rel=canonical as its own token."""
    if not header:
        return False
    for part in _split_link_values(header):
        # rel= inside the URI is not a parameter. Parameters follow the >.
        gt = part.find(">")
        params = part[gt + 1 :] if gt >= 0 else part
        for match in re.finditer(
            r"""\brel\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s;,]+))""",
            params,
            re.I,
        ):
            raw = next(group for group in match.groups() if group is not None)
            if "canonical" in raw.lower().split():
                return True
    return False


def _is_text_html(content_type: str | None) -> bool:
    if not content_type:
        return False
    return content_type.split(";", 1)[0].strip().lower() == "text/html"


def decode_body(body: bytes, content_type: str, headers: dict | None = None) -> str:
    raw = body or b""
    encoding = header_value(headers or {}, "content-encoding") or ""
    if "gzip" in encoding.lower() or raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    charset = "utf-8"
    match = re.search(r"charset=([^\s;]+)", content_type or "", re.I)
    if match:
        charset = match.group(1).strip('"').strip("'")
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


# First address that completed a handshake, so later requests skip a dead A record.
_REACHABLE: dict[tuple[str, int], tuple] = {}


def connect_socket(hostname: str, port: int, timeout: float):
    """Connect, trying IPv4 before IPv6, with a short timeout per address.

    getaddrinfo often lists an unreachable address first. Waiting out the full
    read timeout on that SYN makes every request look hung.
    """
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    infos.sort(key=lambda item: 0 if item[0] == socket.AF_INET else 1)
    cached = _REACHABLE.get((hostname, port))
    if cached is not None:
        infos.sort(key=lambda item: 0 if item[4] == cached else 1)
    connect_timeout = min(3.0, timeout)
    last_error = None
    for family, socktype, proto, _canon, sockaddr in infos:
        sock = socket.socket(family, socktype, proto)
        try:
            sock.settimeout(connect_timeout)
            sock.connect(sockaddr)
            sock.settimeout(timeout)
            _REACHABLE[(hostname, port)] = sockaddr
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
            if cached == sockaddr:
                _REACHABLE.pop((hostname, port), None)
    raise last_error or OSError(f"could not connect to {hostname}:{port}")


def fetch_once(url: str, timeout: float = 20.0) -> dict:
    """GET one URL. Does not follow redirects. Returns status, headers, body, location."""
    parsed = urlparse(url)
    empty = {
        "status": 0,
        "headers": {},
        "body": b"",
        "location": None,
        "error": None,
        "truncated": False,
    }
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        empty["error"] = "unsupported URL"
        return empty
    path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=")
    if parsed.query:
        path += "?" + parsed.query
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    conn = None
    try:
        raw = connect_socket(parsed.hostname, port, timeout)
        if parsed.scheme == "https":
            raw = ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
            conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
        conn.sock = raw
        conn.request(
            "GET",
            path,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        )
        resp = conn.getresponse()
        headers: dict[str, list[str]] = {}
        for key, value in resp.getheaders():
            headers.setdefault(key.lower(), []).append(value)
        blob = resp.read(MAX_BYTES + 1)
        truncated = len(blob) > MAX_BYTES
        body = blob[:MAX_BYTES]
        location = (headers.get("location") or [None])[0]
        if location:
            location = strip_fragment(urljoin(url, location.strip()))
        return {
            "status": resp.status,
            "headers": headers,
            "body": body,
            "location": location,
            "error": None,
            "truncated": truncated,
        }
    except Exception as exc:  # network, TLS, timeout: record and keep crawling
        empty["error"] = str(exc)
        return empty
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap_entries(xml_text: str | bytes) -> tuple[str, list[dict]]:
    """Return ('index' or 'urlset', entries with loc and lastmod).

    lastmod is the stripped text, or None when that entry has none.
    Raises ValueError on bad XML.
    """
    if isinstance(xml_text, str):
        data = xml_text.lstrip("\ufeff").encode("utf-8")
    else:
        data = xml_text
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError(f"sitemap XML: {exc}") from exc
    kind = "index" if _local(root.tag) == "sitemapindex" else "urlset"
    parent = "sitemap" if kind == "index" else "url"
    entries = []
    for el in root.iter():
        if _local(el.tag) != parent:
            continue
        loc = None
        lastmod = None
        for child in list(el):
            name = _local(child.tag)
            text = (child.text or "").strip()
            if name == "loc" and text and loc is None:
                loc = text
            elif name == "lastmod" and text and lastmod is None:
                lastmod = text
        if loc:
            entries.append({"loc": loc, "lastmod": lastmod})
    return kind, entries


def parse_sitemap(xml_text: str | bytes) -> tuple[str, list[str]]:
    """Return ('index' or 'urlset', loc URLs). Raises ValueError on bad XML."""
    kind, entries = parse_sitemap_entries(xml_text)
    return kind, [entry["loc"] for entry in entries]


def _robots_pattern_matches(pattern: str, path: str) -> bool:
    if pattern == "":
        return False
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    parts = []
    for char in body:
        parts.append(".*" if char == "*" else re.escape(char))
    regex = "^" + "".join(parts) + ("$" if anchored else "")
    return re.match(regex, path) is not None


def _root_blocked(allows: list[str], disallows: list[str]) -> bool:
    """True when the longest matching rule for '/' is a disallow."""
    path = "/"

    def matching(rules: list[str]) -> list[int]:
        return [len(rule) for rule in rules if _robots_pattern_matches(rule, path)]

    disallow_lens = matching(disallows)
    if not disallow_lens:
        return False
    allow_lens = matching(allows)
    best_disallow = max(disallow_lens)
    best_allow = max(allow_lens) if allow_lens else -1
    # Same length: allow wins, matching Google's robots.txt tie break.
    return best_disallow > best_allow


def parse_robots(text: str) -> dict:
    """Return lists_sitemap and whether each named bot is blocked from '/'."""
    groups: list[dict] = []
    current = None
    lists_sitemap = False

    def start_group(agent: str) -> None:
        nonlocal current
        current = {"agents": [agent], "allow": [], "disallow": [], "closed": False}
        groups.append(current)

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current is None or current["allow"] or current["disallow"] or current["closed"]:
                start_group(value)
            else:
                current["agents"].append(value)
        elif key == "allow":
            if current is None:
                continue
            current["allow"].append(value)
            current["closed"] = True
        elif key == "disallow":
            if current is None:
                continue
            current["disallow"].append(value)
            current["closed"] = True
        elif key == "sitemap":
            if value:
                lists_sitemap = True
            if current is not None:
                current["closed"] = True
        elif current is not None:
            current["closed"] = True

    def blocked(bot: str) -> bool:
        bot_l = bot.lower()
        specific = []
        best = -1
        wildcard_allow: list[str] = []
        wildcard_disallow: list[str] = []
        for group in groups:
            for agent in group["agents"]:
                token = agent.lower()
                if token == "*":
                    wildcard_allow.extend(group["allow"])
                    wildcard_disallow.extend(group["disallow"])
                elif bot_l.startswith(token) and len(token) > best:
                    best = len(token)
        if best >= 0:
            for group in groups:
                if any(bot_l.startswith(agent.lower()) and len(agent) == best and agent != "*" for agent in group["agents"]):
                    specific.append(group)
            allows = [rule for group in specific for rule in group["allow"]]
            disallows = [rule for group in specific for rule in group["disallow"]]
        else:
            allows = wildcard_allow
            disallows = wildcard_disallow
        return _root_blocked(allows, disallows)

    return {"lists_sitemap": lists_sitemap, "blocks": {bot: blocked(bot) for bot in BOTS}}


def _collapse(text: str) -> str:
    return " ".join(text.split())


ORG_TYPES = {
    "Organization",
    "Corporation",
    "LocalBusiness",
    "ProfessionalService",
    "AccountingService",
    "FinancialService",
}
ORG_PROP_KEYS = ("url", "logo", "sameAs", "founder", "name")
# logo, sameAs, and url are the fields a crawler can actually use. founder and
# name are recorded so a later pass can see them, but they do not gate the issue.
ORG_REQUIRED = ("logo", "sameAs", "url")


def _type_names(kind) -> list[str]:
    if kind is None:
        return []
    if isinstance(kind, list):
        raw_items = kind
    else:
        raw_items = re.split(r"\s*,\s*", str(kind))
    names = []
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        # https://schema.org/Organization and schema:Organization both count.
        if "/" in text or "#" in text or ":" in text:
            text = re.split(r"[/#:]", text)[-1]
        if text:
            names.append(text)
    return names


def _is_org_type(kind) -> bool:
    return any(name in ORG_TYPES for name in _type_names(kind))


def _value_present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def _org_url_value(node: dict):
    """String url, a list of them, or None. Host checks need the value, not just presence."""
    value = node.get("url")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list):
        urls = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if not urls:
            return None
        return urls[0] if len(urls) == 1 else urls
    if isinstance(value, dict):
        for key in ("url", "@id"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def parse_jsonld_nodes(text: str) -> tuple[list[dict], list[str]]:
    raw = (text or "").strip()
    if not raw:
        return [], []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [], [f"JSON-LD parse error: {exc.msg}"]
    nodes: list[dict] = []

    def add(node: dict) -> None:
        kind = node.get("@type")
        if isinstance(kind, list):
            kind_s = ", ".join(str(item) for item in kind)
        elif kind is not None:
            kind_s = str(kind)
        else:
            kind_s = None
        node_id = node.get("@id")
        record = {"type": kind_s, "id": node_id if isinstance(node_id, str) else None}
        if _is_org_type(kind):
            record["org_props"] = [key for key in ORG_PROP_KEYS if _value_present(node.get(key))]
            url_value = _org_url_value(node)
            if url_value is not None:
                record["url"] = url_value
        nodes.append(record)

    def walk(node) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        # Nested publisher/founder objects are real entities, not just @graph siblings.
        if "@type" in node or "@id" in node:
            add(node)
        for key, value in node.items():
            if key == "@context":
                continue
            if isinstance(value, (dict, list)):
                walk(value)

    walk(data)
    return nodes, []


class PageParser(HTMLParser):
    """HTMLParser subclass is required to read tags. The rest of the crawler is functions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_title = False
        self.in_h1 = False
        self.in_jsonld = False
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.h1: list[str] = []
        self.h2_count = 0
        self.text_parts: list[str] = []
        self.meta_description = None
        self.meta_robots = None
        self.canonical = None
        self.og_title = None
        self.og_image = None
        self.hrefs: list[str] = []
        self.images_missing_alt = 0
        self.json_ld_raw: list[str] = []
        self._jsonld_buf: list[str] = []
        self.base = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attr = {key.lower(): (value if value is not None else "") for key, value in attrs}
        if tag == "script" and attr.get("type", "").lower() == "application/ld+json":
            self.in_jsonld = True
            self._jsonld_buf = []
        if tag in ("script", "style"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "base" and attr.get("href"):
            self.base = attr["href"]
        elif tag == "title":
            self.in_title = True
            self.title_parts = []
        elif tag == "h1":
            self.in_h1 = True
            self.h1_parts = []
        elif tag == "h2":
            self.h2_count += 1
        elif tag == "a" and attr.get("href"):
            self.hrefs.append(attr["href"])
        elif tag == "img":
            if "alt" not in attr:
                self.images_missing_alt += 1
        elif tag == "link" and "canonical" in attr.get("rel", "").lower().split():
            if attr.get("href"):
                self.canonical = attr["href"]
        elif tag == "meta":
            name = attr.get("name", "").lower()
            prop = attr.get("property", "").lower()
            content = attr.get("content")
            if name == "description" and self.meta_description is None:
                self.meta_description = content or ""
            elif name == "robots" and self.meta_robots is None:
                self.meta_robots = content or ""
            elif prop == "og:title" and self.og_title is None:
                self.og_title = content or ""
            elif prop == "og:image" and self.og_image is None:
                self.og_image = content or ""

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self.in_jsonld:
            self.json_ld_raw.append("".join(self._jsonld_buf))
            self.in_jsonld = False
            self._jsonld_buf = []
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "title" and self.in_title:
            self.in_title = False
        elif tag == "h1" and self.in_h1:
            self.h1.append(_collapse("".join(self.h1_parts)))
            self.in_h1 = False
            self.h1_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self._jsonld_buf.append(data)
            return
        if self.skip:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.in_h1:
            self.h1_parts.append(data)
        if not self.in_title:
            self.text_parts.append(data)

    def close(self) -> None:
        super().close()
        if self.in_h1:
            self.h1.append(_collapse("".join(self.h1_parts)))
            self.in_h1 = False
        self.in_title = False


def parse_html(html: str, page_url: str, site: str) -> dict:
    parser = PageParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        # Keep whatever was parsed before the break.
        parser.json_ld_raw.append("")
        parse_note = str(exc)
    else:
        parse_note = None

    base = urljoin(page_url, parser.base) if parser.base else page_url
    title = _collapse("".join(parser.title_parts)) or None
    description = parser.meta_description
    if description is not None:
        description = _collapse(description) or None
    canonical = parser.canonical
    if canonical:
        canonical = strip_fragment(urljoin(base, canonical))

    internal: list[str] = []
    seen: set[str] = set()
    external = 0
    for href in parser.hrefs:
        absolute = resolve_link(href, base)
        if not absolute:
            continue
        if same_site(absolute, site):
            key = normalize_url(absolute)
            if key not in seen:
                seen.add(key)
                internal.append(absolute)
        else:
            external += 1
    internal.sort()

    nodes: list[dict] = []
    errors: list[str] = []
    if parse_note:
        errors.append(f"HTML parse error: {parse_note}")
    for blob in parser.json_ld_raw:
        found, errs = parse_jsonld_nodes(blob)
        nodes.extend(found)
        errors.extend(errs)

    return {
        "title": title,
        "meta_description": description,
        "meta_robots": parser.meta_robots,
        "canonical": canonical,
        "og_title": parser.og_title,
        "og_image": parser.og_image,
        "h1": parser.h1,
        "h2_count": parser.h2_count,
        "json_ld": nodes,
        "json_ld_errors": errors,
        "internal_links": internal,
        "external_link_count": external,
        "images_missing_alt": parser.images_missing_alt,
        "word_count": len("".join(parser.text_parts).split()),
    }


def looks_like_html(content_type: str, body: bytes) -> bool:
    ctype = (content_type or "").lower()
    if "html" in ctype or "xhtml" in ctype:
        return True
    if ctype and "text/plain" not in ctype:
        return False
    sniff = body.lstrip()[:200].lower()
    return sniff.startswith(b"<!doctype html") or sniff.startswith(b"<html") or b"<head" in sniff or b"<body" in sniff


def record_from_fetch(url: str, raw: dict, site: str, in_sitemap: bool) -> dict:
    headers = raw.get("headers") or {}
    content_type = header_value(headers, "content-type")
    record = {
        "url": url,
        "status": raw.get("status") or 0,
        "redirect_location": raw.get("location") if (raw.get("status") or 0) in REDIRECT_STATUSES else None,
        "redirect_chain": [url],
        "final_url": url,
        "content_type": content_type,
        "link_header": header_value(headers, "link"),
        "x_robots_tag": header_value(headers, "x-robots-tag"),
        "cache_control": header_value(headers, "cache-control"),
        "in_sitemap": in_sitemap,
        "error": raw.get("error"),
    }
    if raw.get("truncated"):
        record["truncated"] = True
    if record["status"] == 200 and looks_like_html(content_type or "", raw.get("body") or b""):
        text = decode_body(raw.get("body") or b"", content_type or "", headers)
        record.update(parse_html(text, url, site))
    return record


def index_pages(pages: dict) -> dict:
    by_norm = {}
    for url, record in pages.items():
        by_norm[normalize_url(url)] = record
    return by_norm


def find_page(url: str, pages: dict, by_norm: dict | None = None) -> dict | None:
    if url in pages:
        return pages[url]
    key = normalize_url(url)
    if by_norm is not None and key in by_norm:
        return by_norm[key]
    for page_url, record in pages.items():
        if normalize_url(page_url) == key:
            return record
    return None


def stamp_chains(pages: dict) -> None:
    by_norm = index_pages(pages)
    for url, record in pages.items():
        chain = [url]
        current = record
        seen = {normalize_url(url)}
        for _ in range(MAX_HOPS):
            loc = current.get("redirect_location")
            status = current.get("status")
            if status not in REDIRECT_STATUSES or not loc:
                break
            chain.append(loc)
            nxt = find_page(loc, pages, by_norm)
            if nxt is None:
                break
            key = normalize_url(loc)
            if key in seen:
                break
            seen.add(key)
            current = nxt
        record["redirect_chain"] = chain
        fetched = [item for item in chain if find_page(item, pages, by_norm)]
        record["final_url"] = fetched[-1] if fetched else url


def final_record(url: str, pages: dict, by_norm: dict) -> dict | None:
    record = find_page(url, pages, by_norm)
    if record is None:
        return None
    chain = record.get("redirect_chain") or [url]
    last = record
    for item in chain:
        found = find_page(item, pages, by_norm)
        if found is not None:
            last = found
    return last


def has_noindex(record: dict) -> bool:
    blob = " ".join(filter(None, [record.get("meta_robots"), record.get("x_robots_tag")])).lower()
    return "noindex" in blob or re.search(r"\bnone\b", blob) is not None


def is_html_200(record: dict) -> bool:
    if record.get("status") != 200:
        return False
    ctype = (record.get("content_type") or "").lower()
    if "html" in ctype:
        return True
    return "h1" in record or "title" in record


def is_indexable(record: dict) -> bool:
    return is_html_200(record) and not has_noindex(record)


def _issue(code: str, url: str, detail: str, severity: str | None = None) -> dict:
    return {
        "code": code,
        "severity": severity or SEVERITY[code],
        "url": url,
        "detail": detail,
    }


def _inbound(pages: dict) -> dict[str, set[str]]:
    inbound: dict[str, set[str]] = {}
    for src, record in pages.items():
        if not is_html_200(record):
            continue
        src_key = normalize_url(src)
        for link in record.get("internal_links") or []:
            key = normalize_url(link)
            if key == src_key:
                continue
            inbound.setdefault(key, set()).add(record.get("url") or src)
    return inbound


def _host_kind(value: str, page_url: str, site: str) -> str:
    absolute = urljoin(page_url, value.strip())
    if not urlparse(absolute).hostname:
        return "none"
    return "ours" if same_site(absolute, site) else "foreign"


def _id_key(value: str, page_url: str) -> str:
    """Identity for an @id. www is the same host; the fragment is not."""
    absolute = urljoin(page_url, value.strip())
    parsed = urlparse(absolute)
    if not parsed.hostname:
        return value.strip()
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    frag = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{parsed.scheme.lower()}://{bare_host(parsed.hostname)}{path}{query}{frag}"


def _org_urls(node: dict) -> list[str]:
    value = node.get("url")
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _is_org_node(node: dict) -> bool:
    if "org_props" in node:
        return True
    return _is_org_type(node.get("type"))


def _org_is_ours(node: dict, page_url: str, site: str) -> bool:
    """True when this organization node is the crawled business, not a client.

    An org whose url is on another host is a partner embedded in the page.
    No url and no @id still counts: nothing points off-site.
    """
    urls = _org_urls(node)
    node_id = node.get("id") if isinstance(node.get("id"), str) else ""
    has_id = bool(node_id.strip())
    if not urls and not has_id:
        return True
    if urls:
        kinds = [_host_kind(url, page_url, site) for url in urls]
        if "foreign" in kinds:
            return False
        if "ours" in kinds:
            return True
    if has_id:
        kind = _host_kind(node_id, page_url, site)
        if kind == "ours":
            return True
        if kind == "foreign":
            return False
    return False


def _jsonld_entity_issues(pages: dict, site: str) -> list[dict]:
    issues = []
    id_pages: dict[str, set[str]] = {}
    id_props: dict[str, set[str]] = {}
    for page in pages.values():
        page_url = page.get("url") or ""
        missing_types = []
        for node in page.get("json_ld") or []:
            if not isinstance(node, dict) or not _is_org_node(node):
                continue
            if not _org_is_ours(node, page_url, site):
                continue
            node_id = node.get("id") if isinstance(node.get("id"), str) else ""
            if not node_id.strip():
                missing_types.append(node.get("type") or "Organization")
                continue
            cid = _id_key(node_id, page_url)
            id_pages.setdefault(cid, set()).add(page_url)
            id_props.setdefault(cid, set()).update(node.get("org_props") or [])
        if missing_types:
            issues.append(_issue("jsonld_entity_no_id", page_url, "No @id on " + ", ".join(missing_types)))
    if len(id_pages) > 1:
        listed = ", ".join(sorted(id_pages))
        issues.append(_issue("jsonld_entity_ids_differ", site, f"Distinct @id values: {listed}"))
    if id_pages:
        best = max(len(seen) for seen in id_pages.values())
        # One site-level issue. A tie picks the alphabetically first id.
        winner = sorted(cid for cid, seen in id_pages.items() if len(seen) == best)[0]
        missing = [key for key in ORG_REQUIRED if key not in id_props.get(winner, set())]
        if missing:
            missing_text = ", ".join(missing)
            issues.append(_issue("jsonld_org_incomplete", site, f"{winner} lacks {missing_text}"))
    return issues


def _sitemap_lastmod_issue(sitemap_urls: list[str], sitemap_lastmods: list | None, site: str) -> dict | None:
    """Flag a sitemap whose every URL was stamped with the same lastmod.

    That value is usually the build time, so crawlers cannot tell what changed.
    A missing lastmod means they are not all the same stamp, so no flag.
    """
    if sitemap_lastmods is None or len(sitemap_urls) <= 5:
        return None
    if len(sitemap_lastmods) != len(sitemap_urls):
        return None
    values = []
    for lastmod in sitemap_lastmods:
        if not isinstance(lastmod, str) or not lastmod.strip():
            return None
        values.append(lastmod.strip())
    if len(set(values)) != 1:
        return None
    return _issue(
        "sitemap_lastmod_uniform",
        site,
        f"All {len(values)} URLs share lastmod {values[0]}",
    )


def compute_issues(pages: dict, sitemap_urls: list[str], robots: dict, llms: dict, site: str, sitemap_lastmods: list | None = None) -> list[dict]:
    stamp_chains(pages)
    by_norm = index_pages(pages)
    inbound = _inbound(pages)
    sitemap_norm = {normalize_url(url) for url in sitemap_urls}
    issues: list[dict] = []

    def page_inbound(url: str) -> set[str]:
        return inbound.get(normalize_url(url), set())

    broken: dict[str, dict] = {}
    for src, record in pages.items():
        if not is_html_200(record):
            continue
        for link in record.get("internal_links") or []:
            target = final_record(link, pages, by_norm)
            if target is None:
                continue
            status = target.get("status") or 0
            if status < 400:
                continue
            key = target.get("url") or link
            slot = broken.setdefault(key, {"status": status, "sources": set()})
            slot["sources"].add(record.get("url") or src)
    for url, slot in broken.items():
        sources = ", ".join(sorted(slot["sources"]))
        issues.append(_issue("broken_internal_link", url, f"Status {slot['status']}. Linked from {sources}"))

    for sitemap_url in sitemap_urls:
        record = find_page(sitemap_url, pages, by_norm)
        if record is None:
            continue
        own_status = record.get("status") or 0
        if own_status in REDIRECT_STATUSES:
            dest = record.get("redirect_location") or "unknown"
            issues.append(_issue("sitemap_redirect", record.get("url") or sitemap_url, f"Redirects to {dest}"))
        final = final_record(sitemap_url, pages, by_norm)
        final_status = (final or record).get("status") or 0
        if final_status != 200:
            detail = f"Final status {final_status}"
            if (final or record).get("error"):
                detail += f". {(final or record)['error']}"
            issues.append(_issue("sitemap_non_200", record.get("url") or sitemap_url, detail))
        elif final and is_html_200(final) and has_noindex(final):
            issues.append(_issue("sitemap_noindex", record.get("url") or sitemap_url, "Sitemap URL is noindex"))
        # Markdown and JSON twins are 200s that are not HTML. Errors stay on sitemap_non_200.
        if final_status == 200 and not _is_text_html((final or record).get("content_type")):
            if not has_canonical_link((final or record).get("link_header")):
                ctype = (final or record).get("content_type") or "(missing)"
                issues.append(_issue("sitemap_non_html", record.get("url") or sitemap_url, ctype))

    html_pages = [record for record in pages.values() if is_html_200(record)]
    titles: dict[str, list[str]] = {}
    descriptions: dict[str, list[str]] = {}
    for record in html_pages:
        url = record.get("url") or ""
        title = record.get("title")
        if not title:
            issues.append(_issue("missing_title", url, "No title"))
        else:
            if len(title) > 60:
                issues.append(_issue("title_too_long", url, f"{len(title)} characters"))
            titles.setdefault(title, []).append(url)
        description = record.get("meta_description")
        if not description:
            issues.append(_issue("missing_description", url, "No meta description"))
        else:
            length = len(description)
            if length < 70 or length > 160:
                issues.append(_issue("description_length", url, f"{length} characters"))
            descriptions.setdefault(description, []).append(url)
        h1 = record.get("h1") or []
        if len(h1) != 1:
            issues.append(_issue("h1_count", url, f"Found {len(h1)} h1"))
        canonical = record.get("canonical")
        final_url = record.get("final_url") or url
        if not canonical:
            issues.append(_issue("canonical_missing", url, "No canonical"))
        elif slash_key(canonical) != slash_key(final_url):
            issues.append(_issue("canonical_mismatch", url, f"Canonical is {canonical}"))
        errors = record.get("json_ld_errors") or []
        if errors:
            issues.append(_issue("jsonld_parse_error", url, "; ".join(errors)))
        missing_alt = record.get("images_missing_alt") or 0
        if missing_alt:
            noun = "image" if missing_alt == 1 else "images"
            issues.append(_issue("img_missing_alt", url, f"{missing_alt} {noun} missing alt"))
        hops = max(0, len(record.get("redirect_chain") or []) - 1)
        if hops > 1:
            issues.append(_issue("redirect_chain", url, f"{hops} hops"))

        referring = page_inbound(url)
        if normalize_url(url) in sitemap_norm and is_html_200(record) and not referring:
            # Non-HTML sitemap files (markdown mirrors, feeds) are not pages that need links.
            issues.append(_issue("orphan", url, "In the sitemap with no internal links pointing here"))
        if is_indexable(record) and len(referring) == 1:
            issues.append(_issue("thin_inbound", url, "Only 1 internal page links here"))
        if is_indexable(record) and normalize_url(url) not in sitemap_norm and referring:
            issues.append(_issue("not_in_sitemap", url, "Indexable page is not in the sitemap"))
        if has_noindex(record) and referring:
            issues.append(_issue("noindex_linked", url, f"noindex, but linked from {len(referring)} pages"))

    for title, urls in titles.items():
        if len(urls) < 2:
            continue
        for url in urls:
            others = [other for other in urls if other != url]
            shown = ", ".join(others[:5])
            if len(others) > 5:
                shown += f", and {len(others) - 5} more"
            issues.append(_issue("duplicate_title", url, f"Same title as {shown}"))
    for description, urls in descriptions.items():
        if len(urls) < 2:
            continue
        for url in urls:
            others = [other for other in urls if other != url]
            shown = ", ".join(others[:5])
            if len(others) > 5:
                shown += f", and {len(others) - 5} more"
            issues.append(_issue("duplicate_description", url, f"Same description as {shown}"))

    # Redirect records are not HTML, so the loop above missed long chains that never return 200.
    for record in pages.values():
        if is_html_200(record):
            continue
        hops = max(0, len(record.get("redirect_chain") or []) - 1)
        if hops > 1:
            issues.append(_issue("redirect_chain", record.get("url") or "", f"{hops} hops"))

    robots_url = (robots or {}).get("url") or (site.rstrip("/") + "/robots.txt")
    for bot, blocked in ((robots or {}).get("blocks") or {}).items():
        if not blocked:
            continue
        severity = "high" if bot in SEARCH_BOTS else "medium"
        # Fragment keeps code+url unique per bot so a weekly diff can see one bot change.
        issues.append(_issue("robots_blocks_ai_bot", f"{robots_url}#{bot}", f"{bot} is blocked", severity))

    llms_status = (llms or {}).get("status")
    if llms_status != 200:
        llms_url = (llms or {}).get("url") or (site.rstrip("/") + "/llms.txt")
        detail = f"Status {llms_status}"
        if (llms or {}).get("error"):
            detail += f". {llms['error']}"
        issues.append(_issue("llms_txt_missing", llms_url, detail))

    issues.extend(_jsonld_entity_issues(pages, site))
    lastmod_issue = _sitemap_lastmod_issue(sitemap_urls, sitemap_lastmods, site)
    if lastmod_issue:
        issues.append(lastmod_issue)

    issues.sort(key=lambda item: (SEV_RANK.get(item["severity"], 9), item["code"], item["url"]))
    return issues


def _content_type(raw: dict) -> str:
    return header_value(raw.get("headers") or {}, "content-type") or ""


def collect_sitemap(url: str, fetch, site: str, seen: set[str] | None = None, depth: int = 0) -> tuple[list[dict], str | None]:
    """Return urlset entries ({loc, lastmod}) and an error string.

    Index lastmod is not copied onto child URLs. Those dates belong to the
    child sitemap file, not to the pages.
    """
    if seen is None:
        seen = set()
    key = normalize_url(url)
    if key in seen or depth > 5:
        return [], None
    seen.add(key)
    raw = fetch(url)
    if raw.get("error") or not raw.get("status"):
        return [], raw.get("error") or f"sitemap fetch failed for {url}"
    status = raw["status"]
    if status in REDIRECT_STATUSES and raw.get("location") and same_site(raw["location"], site):
        return collect_sitemap(raw["location"], fetch, site, seen, depth)
    if status != 200:
        return [], f"sitemap status {status} for {url}"
    text = decode_body(raw.get("body") or b"", _content_type(raw), raw.get("headers"))
    try:
        kind, entries = parse_sitemap_entries(text)
    except ValueError as exc:
        return [], str(exc)
    resolved = []
    for entry in entries:
        resolved.append({"loc": urljoin(url, entry["loc"]), "lastmod": entry.get("lastmod")})
    if kind == "index":
        found: list[dict] = []
        errors = []
        for entry in resolved:
            child, err = collect_sitemap(entry["loc"], fetch, site, seen, depth + 1)
            found.extend(child)
            if err:
                errors.append(err)
        return found, "; ".join(errors) or None
    return resolved, None


def _robots_record(url: str, raw: dict) -> dict:
    record = {
        "url": url,
        "status": raw.get("status") or 0,
        "lists_sitemap": False,
        "blocks": {bot: False for bot in BOTS},
        "error": raw.get("error"),
    }
    if record["status"] == 200 and raw.get("body"):
        parsed = parse_robots(decode_body(raw["body"], _content_type(raw), raw.get("headers")))
        record["lists_sitemap"] = parsed["lists_sitemap"]
        record["blocks"] = parsed["blocks"]
    return record


def _llms_record(url: str, raw: dict) -> dict:
    status = raw.get("status") or 0
    return {
        "url": url,
        "status": status,
        "present": status == 200,
        "error": raw.get("error"),
    }


def crawl(config: dict, *, fetch=None, delay: float = 0.3, max_pages: int | None = None, sleep=time.sleep) -> dict:
    fetch = fetch or fetch_once
    site = config["site"]
    limit = int(config.get("max_pages") or 300) if max_pages is None else int(max_pages)
    skip = list(config.get("skip_links") or [])
    request_count = 0

    def polite(url: str) -> dict:
        nonlocal request_count
        if delay > 0 and request_count:
            sleep(delay)
        request_count += 1
        return fetch(url)

    robots_url = site + "/robots.txt"
    llms_url = site + "/llms.txt"
    robots = _robots_record(robots_url, polite(robots_url))
    llms = _llms_record(llms_url, polite(llms_url))

    sitemap_entries, sitemap_error = collect_sitemap(config["sitemap"], polite, site)
    # Dedupe sitemap locs but keep the first spelling for the fetch.
    deduped = []
    seen_sm = set()
    for entry in sitemap_entries:
        url = entry.get("loc") or ""
        if not same_site(url, site):
            continue
        key = normalize_url(url)
        if key in seen_sm:
            continue
        seen_sm.add(key)
        deduped.append({"loc": strip_fragment(url), "lastmod": entry.get("lastmod")})
    sitemap_urls = [entry["loc"] for entry in deduped]
    sitemap_lastmods = [entry.get("lastmod") for entry in deduped]
    if sitemap_error and not sitemap_urls:
        raise NetworkError(sitemap_error)
    if sitemap_error:
        print(f"Warning: {sitemap_error}", file=sys.stderr)

    sitemap_norm = {normalize_url(url) for url in sitemap_urls}
    pages: dict[str, dict] = {}
    by_norm: dict[str, dict] = {}
    queued: set[str] = set()
    queue: deque[str] = deque()

    def enqueue(url: str) -> None:
        url = strip_fragment(url.strip())
        if not url or not same_site(url, site) or should_skip(url, skip):
            return
        key = normalize_url(url)
        if key in queued:
            return
        queued.add(key)
        queue.append(url)

    for url in sitemap_urls:
        enqueue(url)

    while queue and len(pages) < limit:
        start = queue.popleft()
        if normalize_url(start) in by_norm:
            continue
        current = start
        hops = 0
        while current and len(pages) < limit:
            key = normalize_url(current)
            if key in by_norm:
                break
            if should_skip(current, skip) or not same_site(current, site):
                break
            queued.add(key)
            raw = polite(current)
            record = record_from_fetch(current, raw, site, key in sitemap_norm)
            pages[current] = record
            by_norm[key] = record
            status = record["status"]
            loc = record.get("redirect_location")
            if status in REDIRECT_STATUSES and loc and hops < MAX_HOPS and same_site(loc, site) and not should_skip(loc, skip):
                hops += 1
                current = loc
                continue
            if status == 200 and is_html_200(record):
                for link in record.get("internal_links") or []:
                    enqueue(link)
            break

    stamp_chains(pages)
    issues = compute_issues(pages, sitemap_urls, robots, llms, site, sitemap_lastmods)
    html_pages = sum(1 for record in pages.values() if is_html_200(record))
    by_sev = {"high": 0, "medium": 0, "low": 0}
    for item in issues:
        if item["severity"] in by_sev:
            by_sev[item["severity"]] += 1
    ordered = dict(sorted(pages.items(), key=lambda item: item[0]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "site": site,
        "robots": robots,
        "llms_txt": llms,
        "pages": ordered,
        "issues": issues,
        "counts": {
            "pages": len(ordered),
            "html_pages": html_pages,
            "issues_by_severity": by_sev,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crawl a site and write an SEO snapshot.")
    parser.add_argument("--config", required=True, help="Path to tracking/seo/config.yaml")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between requests (default 0.3)")
    parser.add_argument("--max-pages", type=int, help="Override config max_pages")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    try:
        report = crawl(config, delay=args.delay, max_pages=args.max_pages)
    except NetworkError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = report["counts"]
    sev = counts["issues_by_severity"]
    print(
        f"Crawled {counts['pages']} URLs ({counts['html_pages']} HTML). "
        f"{len(report['issues'])} issues ({sev['high']} high, {sev['medium']} medium, {sev['low']} low).",
        file=sys.stderr,
    )
    blocked = [bot for bot, flag in report["robots"]["blocks"].items() if flag]
    if blocked:
        print("robots.txt blocks: " + ", ".join(blocked), file=sys.stderr)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
