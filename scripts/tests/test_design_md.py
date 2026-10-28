#!/usr/bin/env python3
"""Synthetic DESIGN.md files only. No network."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import design_md as dm

SAMPLE = """---
version: alpha
name: Acme Bakery
description: "Visual identity for Acme Bakery."  # trailing comment
colors:
  paper: "#FFFDF8"
  ink: "#1F1A17"
  ink-muted: "#6B625B"
  primary: "#9C2F1E"
  primary-dark: "#7A2416"
  on-primary: "#FFFDF8"
  tertiary: "#D9A441"
  outline: "#E6DED3"
themes:
  dark:
    paper: "#17120F"
    ink: "#F4EEE6"
    ink-muted: "#B3A99E"
    primary: "#D0553F"
typography:
  display:
    fontFamily: "Fraunces"
    fontSize: 64px
    fontWeight: 400
    lineHeight: 0.95
  body-md:
    fontFamily: "Work Sans"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  button:
    fontFamily: "Work Sans"
    fontSize: 14px
    fontWeight: 600
rounded:
  sm: 4px
  pill: 999px
spacing:
  sm: 8px
  md: 16px
components:
  page:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.sm}"
    height: 48px
    padding: 20px
  button-primary-hover:
    backgroundColor: "{colors.primary-dark}"
---

# DESIGN.md — Acme Bakery

Intro line.

## Overview

Warm crust, flour on the counter. Nothing glossy.

## Colors

- **Paper (`#FFFDF8`):** the page.
- **Primary (`#9C2F1E`, crust):** the one button.
- **Tertiary (`#D9A441`):** rules only.

## Typography

Fraunces for headlines, Work Sans for the rest.

## Do's and Don'ts

- Do keep one button per view.
"""


def write(text):
    d = Path(tempfile.mkdtemp())
    p = d / "DESIGN.md"
    p.write_text(text)
    return p


class YamlTest(unittest.TestCase):
    def test_mini_reads_the_subset(self):
        fm, _ = dm.split_frontmatter(SAMPLE)
        y = dm.mini_yaml(fm)
        self.assertEqual(y["name"], "Acme Bakery")
        self.assertEqual(y["description"], "Visual identity for Acme Bakery.")
        self.assertEqual(y["colors"]["primary"], "#9C2F1E")
        self.assertEqual(y["themes"]["dark"]["primary"], "#D0553F")
        self.assertEqual(y["typography"]["display"]["fontWeight"], 400)
        self.assertEqual(y["typography"]["display"]["lineHeight"], 0.95)
        self.assertEqual(y["typography"]["display"]["fontSize"], "64px")
        self.assertEqual(y["components"]["page"]["backgroundColor"], "{colors.paper}")

    def test_mini_lists_blocks_and_flow(self):
        y = dm.mini_yaml("a:\n  - one\n  - 'two'\nb: [1, x]\nc: |\n  line 1\n  line 2\nd: {}\n")
        self.assertEqual(y["a"], ["one", "two"])
        self.assertEqual(y["b"], [1, "x"])
        self.assertEqual(y["c"], "line 1\nline 2\n")
        self.assertEqual(y["d"], {})

    def test_mini_matches_pyyaml_when_present(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for text in (SAMPLE, (Path(__file__).resolve().parents[2] / "templates" / "DESIGN.md").read_text()):
            fm, _ = dm.split_frontmatter(text)
            self.assertEqual(dm.mini_yaml(fm), yaml.safe_load(fm))


class DocTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(SAMPLE))

    def test_load_and_sections(self):
        self.assertEqual(self.doc["name"], "Acme Bakery")
        self.assertEqual([t for t, _ in self.doc["sections"]], ["Overview", "Colors", "Typography", "Do's and Don'ts"])
        self.assertEqual(self.doc["intro"], "Intro line.")
        self.assertEqual(dm.theme_ids(self.doc), ["light", "dark"])

    def test_resolve_and_theme_fallback(self):
        self.assertEqual(dm.resolve(self.doc, "{colors.primary}", "dark"), "#D0553F")
        self.assertEqual(dm.resolve(self.doc, "{colors.on-primary}", "dark"), "#FFFDF8")  # not in dark: light value
        self.assertEqual(dm.resolve(self.doc, "{rounded.sm}"), "4px")
        self.assertIsNone(dm.resolve(self.doc, "{colors.nope}"))

    def test_contrast(self):
        self.assertAlmostEqual(dm.contrast("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(dm.contrast("#fff", "#FFFFFF"), 1.0, places=2)
        self.assertIsNone(dm.contrast("red", "#fff"))

    def test_roles(self):
        r = dm.roles(self.doc)
        self.assertEqual((r["ground"], r["ink"], r["muted"]), ("paper", "ink", "ink-muted"))

    def test_variants_fold_and_inherit(self):
        g = dm.component_groups(self.doc)
        self.assertEqual(list(g), ["page", "button-primary"])
        states = g["button-primary"]
        self.assertEqual([s for s, _, _ in states], ["default", "hover"])
        hover = states[1][2]
        self.assertEqual(hover["backgroundColor"], "{colors.primary-dark}")
        self.assertEqual(hover["height"], "48px")  # inherited from the base


class CheckTest(unittest.TestCase):
    def test_clean_sample(self):
        self.assertEqual([m for lvl, m in dm.check(dm.load(write(SAMPLE))) if lvl == "error"], [])

    def test_broken_reference_and_placeholder(self):
        text = SAMPLE.replace("name: Acme Bakery", 'name: "[CLIENT NAME]"').replace("{colors.on-primary}", "{colors.missing}")
        errors = [m for lvl, m in dm.check(dm.load(write(text))) if lvl == "error"]
        self.assertTrue(any("placeholder" in m for m in errors))
        self.assertTrue(any("colors.missing" in m for m in errors))

    def test_low_contrast_warns_per_theme(self):
        text = SAMPLE.replace('    primary: "#D0553F"', '    primary: "#F0E8E0"')
        warns = [m for lvl, m in dm.check(dm.load(write(text))) if lvl == "warn"]
        self.assertTrue(any("button-primary" in m and "dark" in m for m in warns))

    def test_no_frontmatter(self):
        self.assertEqual(dm.check(dm.load(write("# Just prose\n")))[0][0], "error")

    def test_template_needs_filling(self):
        tpl = Path(__file__).resolve().parents[2] / "templates" / "DESIGN.md"
        errors = [m for lvl, m in dm.check(dm.load(tpl)) if lvl == "error"]
        self.assertTrue(any("placeholder" in m for m in errors))


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.page = dm.render_html(dm.load(write(SAMPLE)))

    def test_tokens_in_both_themes(self):
        self.assertIn("--c-primary:#9C2F1E", self.page)
        self.assertIn("--c-primary:#D0553F", self.page)
        self.assertIn('@media (prefers-color-scheme:dark)', self.page)
        self.assertIn(':root[data-theme="dark"]', self.page)

    def test_only_fonts_load_from_network(self):
        hosts = set(re.findall(r'(?:src|href)="(https?://[^/"]+)', self.page))
        self.assertEqual(hosts, {"https://fonts.googleapis.com"})

    def test_sections_and_prose(self):
        for t in ("Overview", "Colors", "Typography", "Layout", "Shapes", "Components"):
            self.assertIn(f">{t}</h2>", self.page)
        self.assertIn("<strong>Primary (<code>#9C2F1E</code>, crust):</strong>", self.page)
        self.assertIn("the file wins", self.page)

    def test_logo_tiles_inline(self):
        d = Path(tempfile.mkdtemp())
        logo = d / "mark.svg"
        logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
        page = dm.render_html(dm.load(write(SAMPLE)), [logo])
        self.assertIn(">Logo</h2>", page)
        self.assertIn("data:image/svg+xml;base64,", page)

    def test_markdown_table_and_lists(self):
        out = dm.md_to_html("| A | B |\n|---|---|\n| `x` | **y** |\n\n1. one\n2. two\n")
        self.assertIn("<td><code>x</code></td>", out)
        self.assertIn("<ol><li>one</li><li>two</li></ol>", out)


class DesignSystemTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(SAMPLE))
        self.out = Path(tempfile.mkdtemp())
        logos = self.out / "src"
        logos.mkdir()
        (logos / "mark.svg").write_text("<svg/>")
        self.plan = dm.build_ds(self.doc, self.out, assets=[("Logos", logos)], now="2026-01-01T00:00:00Z", by="Owner")
        self.proj = self.out / "project"

    def test_tokens_shape(self):
        t = json.loads((self.proj / "tokens.json").read_text())
        self.assertEqual([x["id"] for x in t["color"]["themes"]], ["light", "dark"])
        prim = next(c for c in t["color"]["tokens"] if c["name"] == "primary")
        self.assertEqual(prim["value"], {"light": "#9C2F1E", "dark": "#D0553F"})
        self.assertEqual(prim["usage"], "Primary (#9C2F1E, crust): the one button.")
        self.assertIsInstance(t["spacing"]["tokens"], list)
        names = [x["name"] for fam in ("color", "spacing", "radius") for x in t[fam]["tokens"]]
        self.assertEqual(len(names), len(set(names)))
        for n in names:
            self.assertRegex(n, r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
        self.assertIn("space-sm", names)
        self.assertIn("radius-pill", names)
        self.assertEqual(t["type"]["families"]["fraunces"], '"Fraunces", Georgia, serif')
        self.assertEqual([g["name"] for g in t["type"]["groups"]], ["Fraunces", "Work Sans"])

    def test_readme_carries_the_source_rule_and_prose(self):
        r = (self.proj / "README.md").read_text()
        self.assertTrue(r.startswith("> Generated from"))
        self.assertIn("the file wins", r)
        self.assertIn("## Do's and Don'ts", r)
        self.assertNotIn("# DESIGN.md", r)

    def test_components_and_cover(self):
        comps = sorted(p.name for p in (self.proj / "components").iterdir())
        self.assertEqual(comps, ["ButtonPrimary", "Cover", "Page"])
        prev = (self.proj / "components" / "ButtonPrimary" / "preview.html").read_text()
        self.assertTrue(prev.startswith("<!-- @dsCard"))
        self.assertIn("var(--primary-dark)", prev)
        self.assertIn('class="el button"', prev)
        self.assertNotIn("#9C2F1E", prev)  # tokens, never literals
        self.assertFalse((self.proj / "components" / "Cover" / "README.md").exists())
        cover = (self.proj / "components" / "Cover" / "preview.html").read_text()
        self.assertTrue(cover.startswith("<!-- @dsCard height=288 -->"))
        self.assertIn("Acme Bakery", cover)
        self.assertNotRegex(cover, r"fill:#|background:#")

    def test_index_and_plan(self):
        ix = json.loads((self.proj / "design-system.json").read_text())
        self.assertEqual((ix["v"], ix["layout"], ix["title"]), (3, "files", "Acme Bakery"))
        self.assertEqual(ix["createdOnFiles"], {"v": 1, "at": "2026-01-01T00:00:00Z"})
        self.assertEqual(ix["lastChange"]["by"], "Owner")
        self.assertEqual(ix["groups"], ["Logos"])
        self.assertEqual(ix["assetGroups"]["Logos"]["order"], ["mark.svg"])
        self.assertEqual(len(self.plan["uploads"]), 1)
        self.assertNotIn("project/assets/Logos/mark.svg", self.plan["files"])  # an upload, not a file
        self.assertIn("project/assets/Logos/README.md", self.plan["files"])
        self.assertNotIn("project/design-system.json", self.plan["files"])
        self.assertTrue((self.out / "publish.json").exists())


class CliTest(unittest.TestCase):
    def test_check_exit_codes(self):
        self.assertEqual(dm.main(["check", str(write(SAMPLE))]), 0)
        self.assertEqual(dm.main(["check", str(write("# none\n"))]), 1)

    def test_render_writes_file(self):
        p = write(SAMPLE)
        out = p.with_name("view.html")
        self.assertEqual(dm.main(["render", str(p), "-o", str(out)]), 0)
        self.assertIn("<title>Acme Bakery design</title>", out.read_text())


if __name__ == "__main__":
    unittest.main()
