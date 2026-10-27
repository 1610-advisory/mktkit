import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import seo_config


def _write_config(root: Path, extra: str = "") -> Path:
    path = root / "tracking" / "seo" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                "site: https://example.com/",
                "sitemap: https://example.com/sitemap.xml",
                "brand: Acme Corp",
                "domains: [example.com]",
                "facts_file: knowledge/corpus-numbers.md",
                "gsc_property: sc-domain:example.com",
                extra,
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_load_config_repo_root_and_facts(tmp_path):
    path = _write_config(tmp_path)
    cfg = seo_config.load_config(path)
    assert cfg["repo_root"] == tmp_path.resolve()
    assert cfg["site"] == "https://example.com"
    assert cfg["facts_file"] == str((tmp_path / "knowledge" / "corpus-numbers.md").resolve())
    assert cfg["gsc_property"] == "sc-domain:example.com"
    assert isinstance(cfg["repo_root"], Path)


def test_missing_required_key(tmp_path):
    path = tmp_path / "tracking" / "seo" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("site: https://example.com\nsitemap: https://example.com/sitemap.xml\nbrand: Acme\n", encoding="utf-8")
    with pytest.raises(ValueError, match="domains"):
        seo_config.load_config(path)


def test_empty_domains(tmp_path):
    path = tmp_path / "tracking" / "seo" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "site: https://example.com\nsitemap: https://example.com/sitemap.xml\nbrand: Acme\ndomains: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="domains"):
        seo_config.load_config(path)


def test_missing_file(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        seo_config.load_config(tmp_path / "nope.yaml")


def test_bad_site(tmp_path):
    path = tmp_path / "tracking" / "seo" / "config.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        "site: example.com\nsitemap: https://example.com/sitemap.xml\nbrand: Acme\ndomains: [example.com]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="site"):
        seo_config.load_config(path)
