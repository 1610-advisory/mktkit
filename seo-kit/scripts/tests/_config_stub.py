"""Stand-in for seo_config.load_config.

Scripts import seo_config, which is owned by the crawl/diff job. This file
exists so tests and a local dry-run can load a config without that module.
Do not rename it to seo_config.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REQUIRED = ("site", "sitemap", "brand", "domains")


def load_config(path) -> dict:
    """Load YAML and add repo_root (the config file's grandparent's parent)."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ValueError(f"config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config must be a YAML mapping")
    missing = [key for key in REQUIRED if not data.get(key)]
    if missing:
        raise ValueError("config missing required keys: " + ", ".join(missing))
    # tracking/seo/config.yaml -> repo root is three parents up.
    data["repo_root"] = config_path.parent.parent.parent
    facts = data.get("facts_file")
    if facts and not Path(facts).is_absolute():
        data["facts_file"] = str(data["repo_root"] / facts)
    return data
