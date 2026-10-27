import importlib.util
from pathlib import Path

STUB = Path(__file__).parent / "_config_stub.py"


def load_stub():
    spec = importlib.util.spec_from_file_location("config_stub", STUB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stub_repo_root_and_required_keys(tmp_path):
    root = tmp_path / "client"
    config = root / "tracking" / "seo" / "config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "site: https://example.com\n"
        "sitemap: https://example.com/sitemap.xml\n"
        "brand: Acme Corp\n"
        "domains: [example.com]\n"
        "facts_file: knowledge/corpus-numbers.md\n",
        encoding="utf-8",
    )
    data = load_stub().load_config(config)
    assert data["repo_root"] == root.resolve()
    assert data["facts_file"] == str(root.resolve() / "knowledge" / "corpus-numbers.md")


def test_stub_rejects_missing_keys(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("site: https://example.com\n", encoding="utf-8")
    try:
        load_stub().load_config(path)
    except ValueError as exc:
        assert "brand" in str(exc)
    else:
        raise AssertionError("expected ValueError")
