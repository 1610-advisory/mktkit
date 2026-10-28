# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
Load a client SEO config.

Usage:
    from seo_config import load_config
    cfg = load_config("tracking/seo/config.yaml")

The config file lives at tracking/seo/config.yaml inside the client repo.
load_config() checks required keys and sets repo_root to that repo
(the config file's grandparent's parent). Relative facts_file is resolved
against repo_root and stored as an absolute path string. Joining repo_root
with an already-absolute facts_file still yields that absolute path.

Environment variables:
    none

Commands:
    (library; no CLI)
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

from yaml import YAMLError, safe_load

REQUIRED = ("site", "sitemap", "brand", "domains")


def load_config(path: str | Path) -> dict:
    """Load and validate a client SEO config. Adds repo_root (Path)."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ValueError(f"Config not found: {config_path}")
    try:
        data = safe_load(config_path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping")

    missing = [key for key in REQUIRED if data.get(key) in (None, "", [])]
    if missing:
        raise ValueError("Config missing required keys: " + ", ".join(missing))

    site = str(data["site"]).strip().rstrip("/")
    parsed = urlparse(site)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Config site must be an absolute http(s) URL, got {data['site']!r}")
    data["site"] = site

    sitemap = str(data["sitemap"]).strip()
    sm = urlparse(sitemap)
    if sm.scheme not in ("http", "https") or not sm.hostname:
        raise ValueError(f"Config sitemap must be an absolute http(s) URL, got {data['sitemap']!r}")
    data["sitemap"] = sitemap

    if not isinstance(data["brand"], str) or not data["brand"].strip():
        raise ValueError("Config brand must be a non-empty string")
    data["brand"] = data["brand"].strip()

    domains = data["domains"]
    if not isinstance(domains, list) or not domains or not all(isinstance(d, str) and d.strip() for d in domains):
        raise ValueError("Config domains must be a non-empty list of hostnames")
    data["domains"] = [d.strip() for d in domains]

    # tracking/seo/config.yaml -> repo root is three parents up.
    data["repo_root"] = config_path.parent.parent.parent

    facts = data.get("facts_file")
    if isinstance(facts, str) and facts.strip():
        facts_path = Path(facts.strip())
        if not facts_path.is_absolute():
            facts_path = data["repo_root"] / facts_path
        data["facts_file"] = str(facts_path.resolve())

    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run seo_config.py tracking/seo/config.yaml", file=sys.stderr)
        sys.exit(1)
    try:
        cfg = load_config(sys.argv[1])
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"site={cfg['site']} repo_root={cfg['repo_root']}", file=sys.stderr)
