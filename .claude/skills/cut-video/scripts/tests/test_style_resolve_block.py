#!/usr/bin/env python3
"""The style profile's "resolve" block (read by resolve-reel) must never reach the
manifest merge: the manifest schema forbids unknown keys. Run: python3 tests/test_style_resolve_block.py"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("render_reel", SCRIPTS / "render-reel.py")
rr = importlib.util.module_from_spec(spec)
sys.argv = ["render-reel"]
spec.loader.exec_module(rr)


def test_resolve_block_dropped():
    example = json.loads((SCRIPTS.parent / "resources/style.example.json").read_text())
    assert "resolve" in example, "example should document the resolve block"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "style.json"
        p.write_text(json.dumps(example))
        style, _defaults = rr.load_style(p)
    assert "resolve" not in style
    assert not any(str(k).startswith("_") for k in style)
    schema = json.loads((SCRIPTS.parent / "resources/reel-manifest.schema.json").read_text())
    allowed = set(schema["properties"])
    assert set(style) <= allowed, f"style keys outside the manifest schema: {set(style) - allowed}"
    for block in ("cover", "captions"):
        ok = set(schema["properties"][block]["properties"])
        assert set(style[block]) <= ok, f"{block} keys outside schema: {set(style[block]) - ok}"


if __name__ == "__main__":
    test_resolve_block_dropped()
    print("ok")
