#!/usr/bin/env python3
"""Synthetic DESIGN.md files only. No network."""

import json
import re
import shutil
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
    fontFeature: "lnum"
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
  divider:
    backgroundColor: "{colors.tertiary}"
    width: 40px
    height: 1px
  heading:
    textColor: "{colors.ink}"
    typography: "{typography.display}"
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
        self.assertEqual(list(g), ["page", "button-primary", "divider", "heading"])
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
        comps = sorted(p.name for p in (self.proj / "components").iterdir() if p.is_dir())
        self.assertEqual(comps, ["ButtonPrimary", "Cover", "Divider", "Heading", "Page"])
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
        files = json.loads((self.out / "publish.json").read_text())["files"]
        self.assertIn("project/components/index.d.ts", files)
        for k, v in files.items():
            if k.endswith(".d.ts"):
                self.assertEqual(v, {"from": k, "contentType": "text/plain"})
            else:
                self.assertEqual(v, k)


class FeatureAndRuleTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(SAMPLE))

    def test_feature_css(self):
        self.assertEqual(dm.feature_css({"fontFeature": "lnum"}), 'font-feature-settings:"lnum";')
        self.assertEqual(dm.feature_css({"fontFeature": "lnum, tnum"}), 'font-feature-settings:"lnum","tnum";')
        self.assertEqual(dm.feature_css({"fontFeature": "bad;x"}), "")
        self.assertEqual(dm.feature_css({}), "")

    def test_feature_reaches_every_view(self):
        self.assertIn('font-feature-settings:"lnum"', dm.render_html(self.doc).replace("&quot;", '"'))
        self.assertIn('font-feature-settings:"lnum"', dm.cover_html(self.doc))
        heading = dm.component_groups(self.doc)["heading"]
        self.assertIn('font-feature-settings:&quot;lnum&quot;', dm.preview_html(self.doc, "heading", heading))
        style = next(st for g in dm.tokens_json(self.doc)["type"]["groups"] for st in g["styles"] if st["name"] == "display")
        self.assertIn("lnum", style["usage"])

    def test_thin_component_is_a_bar(self):
        states = dm.component_groups(self.doc)["divider"]
        prev = dm.preview_html(self.doc, "divider", states)
        self.assertIn("height:1px", prev)
        self.assertIn("height:1px;\"></div><figcaption>", prev)


class NameLogoTest(unittest.TestCase):
    """Where the name stands as a header, the logo file shows, never the name typed in a font."""

    def setUp(self):
        self.doc = dm.load(write(SAMPLE))
        d = Path(tempfile.mkdtemp())
        self.light, self.dark = d / "mark-light.svg", d / "mark-dark.svg"
        self.light.write_text('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 10" width="40" height="10"><path fill="#111" d="M0 0h40v10H0z"/></svg>')
        self.dark.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 10"><path fill="#eee" d="M0 0h40v10H0z"/></svg>')
        self.marks = dm.parse_name_logo(self.doc, [str(self.light), f"dark={self.dark}"])

    def test_cover_shows_logo_not_typed_name(self):
        cover = dm.cover_html(self.doc, self.marks)
        self.assertNotIn('<h1 class="name">Acme Bakery</h1>', cover)
        self.assertIn('<span class="mark mark-light"><svg', cover)
        self.assertIn('<span class="mark mark-dark"><svg', cover)
        self.assertIn('<span class="sr">Acme Bakery</span>', cover)
        self.assertIn(':root[data-theme="dark"] .mark-dark{display:block}', cover)
        self.assertNotIn('viewBox="0 0 40 10" width=', cover)
        self.assertNotIn("<?xml", cover)
        self.assertIn('<h1 class="name">Acme Bakery</h1>', dm.cover_html(self.doc))

    def test_render_header_shows_logo(self):
        page = dm.render_html(self.doc, name_logo=self.marks)
        self.assertIn('<div class="hero"><h1><span class="mark mark-light">', page)
        self.assertIn("@media (prefers-color-scheme:dark){:root:not([data-theme]) .mark-dark{display:block}", page)

    def test_bad_specs(self):
        with self.assertRaises(ValueError):
            dm.parse_name_logo(self.doc, [f"sepia={self.dark}"])
        bad = self.light.with_name("bad.svg")
        bad.write_text('<svg onload="x()"></svg>')
        with self.assertRaises(ValueError):
            dm.name_logo_html(self.doc, {"light": str(bad)})

    def test_ds_cli(self):
        out = Path(tempfile.mkdtemp())
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(out), "--name-logo", str(self.light),
                                  "--name-logo", f"dark={self.dark}"]), 0)
        self.assertIn('class="mark mark-dark"', (out / "project/components/Cover/preview.html").read_text())
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(out), "--name-logo", "nope.png"]), 2)


STATES = SAMPLE.replace("""  divider:
""", """  button-primary-focus:
    borderColor: "{colors.ink}"
  button-primary-disabled:
    backgroundColor: "{colors.outline}"
  button-primary-pressed:
    backgroundColor: "{colors.primary-dark}"
  nav-item:
    textColor: "{colors.ink}"
  nav-item-selected:
    textColor: "{colors.primary}"
  text-link:
    textColor: "{colors.primary}"
  email-field:
    backgroundColor: "{colors.paper}"
    borderColor: "{colors.outline}"
    height: 44px
  divider:
""")


def js_bundle_exports(bundle, preview_props):
    """Run bundle.js in node with a stand-in React; return what each export makes."""
    script = ("global.window = global;\n"
              "window.React = {createElement: function (t, p) { var k = [].slice.call(arguments, 2);"
              " return {t: t, p: p, k: k}; }};\n" + bundle +
              "\nvar out = {};\nfor (var n in window.AcmeBakery) { out[n] = window.AcmeBakery[n](" + preview_props + "); }\n"
              "console.log(JSON.stringify(out));\n")
    import subprocess
    r = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class BundleTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(STATES))
        self.js = dm.bundle_js(self.doc)
        self.css = dm.bundle_css(self.doc)

    def test_header_and_namespace(self):
        first = self.js.splitlines()[0]
        m = re.fullmatch(r"/\* @ds-bundle: (\{.*\}) \*/", first)
        self.assertTrue(m)
        head = json.loads(m.group(1))
        self.assertEqual(head["format"], 4)
        self.assertEqual(head["namespace"], "AcmeBakery")
        self.assertEqual([c["name"] for c in head["components"]],
                         ["Page", "ButtonPrimary", "NavItem", "TextLink", "EmailField", "Divider", "Heading"])
        self.assertIn("window.AcmeBakery = window.AcmeBakery || {}", self.js)
        self.assertIn("window.React", self.js)

    def test_safe_to_inline(self):
        for bad in ("</script", "<!--", "import ", "http", "fetch("):
            self.assertNotIn(bad, self.js.lower())
        self.assertNotIn("#9C2F1E", self.css)
        self.assertNotIn("</style", self.css.lower())

    def test_elements_by_name(self):
        g = dm.component_groups(self.doc)
        pick = {b: dm.comp_element(b, s[0][2]) for b, s in g.items()}
        self.assertEqual(pick["button-primary"], ("button", "button"))
        self.assertEqual(pick["text-link"], ("a", "link"))
        self.assertEqual(pick["email-field"], ("input", "input"))
        self.assertEqual(pick["divider"], ("div", "rule"))
        self.assertEqual(pick["nav-item"], ("nav", "nav"))
        self.assertEqual(pick["page"], ("div", "div"))
        self.assertEqual(dm.comp_element("canvas", {}), ("div", "div"))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_exports_render(self):
        out = js_bundle_exports(self.js, '{state: "hover", className: "x", children: "Go", title: "t"}')
        btn = out["ButtonPrimary"]
        self.assertEqual(btn["t"], "button")
        self.assertEqual(btn["p"]["className"], "acmebakery-button-primary button is-hover x")
        self.assertEqual((btn["p"]["type"], btn["p"]["title"]), ("button", "t"))
        self.assertEqual(btn["k"], ["Go"])
        self.assertNotIn("state", btn["p"])
        self.assertEqual(out["NavItem"]["p"]["className"], "acmebakery-nav-item x")  # no hover state: ignored
        self.assertEqual(out["Divider"]["p"]["role"], "separator")
        self.assertEqual(out["Divider"]["k"], [])
        self.assertEqual(out["EmailField"]["t"], "input")
        self.assertEqual(out["EmailField"]["k"], [])

    def test_css_states(self):
        self.assertIn(".acmebakery-button-primary{background:var(--primary);color:var(--on-primary);"
                      "border-radius:var(--radius-sm);min-height:48px;padding-inline:20px}", self.css)
        self.assertIn(".acmebakery-button-primary:hover,.acmebakery-button-primary.is-hover{background:var(--primary-dark)}", self.css)
        self.assertIn(".acmebakery-button-primary:focus-visible,.acmebakery-button-primary.is-focus{border-color:var(--ink);"
                      "border-width:1px;border-style:solid}", self.css)
        self.assertIn('.acmebakery-button-primary:disabled,.acmebakery-button-primary[aria-disabled="true"],'
                      ".acmebakery-button-primary.is-disabled{background:var(--outline)}", self.css)
        self.assertIn('.acmebakery-button-primary[aria-pressed="true"],.acmebakery-button-primary.is-pressed{', self.css)
        self.assertIn('.acmebakery-nav-item[aria-selected="true"],.acmebakery-nav-item.is-selected{color:var(--primary)}', self.css)
        self.assertIn(":where(.acmebakery-button-primary){font:inherit;", self.css)  # resets never outrank the type class
        self.assertIn(".acmebakery-divider{background:var(--tertiary);width:40px;height:1px}", self.css)

    def test_dts(self):
        d = dm.index_dts(self.doc)
        self.assertIn("import type * as React from 'react';", d)
        self.assertIn('export interface ButtonPrimaryProps extends React.ButtonHTMLAttributes<HTMLButtonElement> '
                      '{ children?: React.ReactNode; className?: string; state?: "hover" | "focus" | "disabled" | "pressed"; }', d)
        self.assertIn("export interface EmailFieldProps extends React.InputHTMLAttributes<HTMLInputElement> { className?: string; }", d)
        self.assertIn("export declare function TextLink(props: TextLinkProps): React.ReactElement;", d)
        self.assertRegex(d, r"declare global \{ interface Window \{ AcmeBakery: \{ Page: typeof Page; ButtonPrimary: typeof ButtonPrimary;")

    def test_preview_renders_through_bundle_with_fallback(self):
        states = dm.component_groups(self.doc)["button-primary"]
        prev = dm.preview_html(self.doc, "button-primary", states)
        self.assertTrue(prev.startswith('<!-- @dsCard group="Components" height=112 -->\n'))
        self.assertIn('<div class="row" id="root"><figure class="s"><div class="el button" style="background:var(--primary);', prev)
        self.assertEqual(prev.count("<script>"), 1)
        self.assertIn("var N=window.AcmeBakery,R=window.React,D=window.ReactDOM;", prev)
        self.assertIn("if(!N||!N.ButtonPrimary||!R||!D||!D.createRoot){return}", prev)
        for st in ("hover", "focus", "disabled", "pressed"):
            self.assertIn(f'"state":"{st}"', prev)
            self.assertIn(f'h("figcaption",null,"{st}")', prev)
        field = dm.preview_html(self.doc, "email-field", dm.component_groups(self.doc)["email-field"])
        self.assertIn('"placeholder":"Email field"', field)
        self.assertIn('"className":"el edge"', field)  # paper on paper gets an edge

    def test_readme_use_it(self):
        g = dm.component_groups(self.doc)
        r = dm.component_readme(self.doc, "button-primary", g["button-primary"])
        self.assertIn('Use it: `AcmeBakery.ButtonPrimary`, a `<button>`. Props: `className`, `children`, '
                      '`state` (`"hover"`, `"focus"`, `"disabled"`, `"pressed"`), and any `<button>` attribute.', r)
        self.assertIn("Use it: `AcmeBakery.Divider`, a `<div>`. Props: `className`, and any",
                      dm.component_readme(self.doc, "divider", g["divider"]))


class ReactLibTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(SAMPLE))
        self.lib = Path(tempfile.mkdtemp())
        (self.lib / "react.production.min.js").write_text("window.React={};")
        (self.lib / "react-dom.production.min.js").write_text("window.ReactDOM={};")

    def test_packed(self):
        out = Path(tempfile.mkdtemp())
        plan = dm.build_ds(self.doc, out, react_lib=self.lib, now="2026-01-01T00:00:00Z")
        proj = out / "project"
        self.assertEqual((proj / "components/lib/react.production.min.js").read_text(), "window.React={};")
        ix = json.loads((proj / "design-system.json").read_text())
        self.assertEqual(ix["libraries"], [
            {"name": "react", "version": "18.3.1", "global": "React", "file": "components/lib/react.production.min.js"},
            {"name": "react-dom", "version": "18.3.1", "global": "ReactDOM", "file": "components/lib/react-dom.production.min.js"}])
        for f in ("project/components/lib/react-dom.production.min.js", "project/components/bundle.js",
                  "project/components/bundle.css", "project/components/index.d.ts"):
            self.assertIn(f, plan["files"])

    def test_not_packed(self):
        out = Path(tempfile.mkdtemp())
        dm.build_ds(self.doc, out, now="2026-01-01T00:00:00Z")
        ix = json.loads((out / "project/design-system.json").read_text())
        self.assertEqual(ix["libraries"], [{"name": "react", "version": "18.3.1", "global": "React"},
                                           {"name": "react-dom", "version": "18.3.1", "global": "ReactDOM"}])
        self.assertFalse((out / "project/components/lib").exists())

    def test_cli_missing_lib(self):
        empty = Path(tempfile.mkdtemp())
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(Path(tempfile.mkdtemp())),
                                  "--react-lib", str(empty)]), 2)
        out = Path(tempfile.mkdtemp())
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(out), "--react-lib", str(self.lib)]), 0)
        self.assertTrue((out / "project/components/lib/react-dom.production.min.js").exists())


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Home</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces&display=swap">
<style>body{background:var(--paper)}</style></head>
<body><h1 class="display">Fresh bread</h1><a href="mailto:hello@example.com">Mail</a><img src="data:image/png;base64,AAAA" alt=""></body></html>
"""


class PageTest(unittest.TestCase):
    def setUp(self):
        self.doc = dm.load(write(SAMPLE))
        self.dir = Path(tempfile.mkdtemp())

    def page(self, name, text):
        p = self.dir / name
        p.write_text(text)
        return p

    def test_card_marker_readme_and_height(self):
        home = self.page("home.html", PAGE)
        self.page("home.md", "# Home\n\nThe shop's front page.\n")
        out = Path(tempfile.mkdtemp())
        dm.build_ds(self.doc, out, pages=dm.parse_pages([f"home_page={home}"]), now="2026-01-01T00:00:00Z")
        prev = (out / "project/components/HomePage/preview.html").read_text()
        self.assertEqual(prev.splitlines()[0], '<!-- @dsCard group="Examples" height=560 page -->')
        self.assertEqual(prev.splitlines()[0], dm.PAGE_MARKER.format(height=560))
        self.assertIn("Fresh bread", prev)
        self.assertEqual((out / "project/components/HomePage/README.md").read_text(), "# Home\n\nThe shop's front page.\n")
        self.assertNotIn("HomePage", dm.bundle_js(self.doc))  # a page, not a bundle export
        self.assertIn("Examples (HomePage)", (out / "project/README.md").read_text())

    def test_height_meta_old_marker_and_generic_readme(self):
        text = '<!-- @dsCard group="Old" height=90 -->\n<meta name="ds-height" content="900">\n' + PAGE
        prev, readme = dm.page_card("Menu", self.page("menu.html", text), 400)
        self.assertTrue(prev.startswith('<!-- @dsCard group="Examples" height=900 page -->\n<meta'))
        self.assertEqual(prev.count("@dsCard"), 1)
        self.assertIn("`menu.html`", readme)
        self.assertTrue(readme.startswith("# Menu\n"))
        prev, _ = dm.page_card("Menu", self.page("plain.html", PAGE), 400)
        self.assertTrue(prev.startswith('<!-- @dsCard group="Examples" height=400 page -->'))
        prev, _ = dm.page_card("Menu", self.page("huge.html", '<meta name="ds-height" content="99999">' + PAGE))
        self.assertIn("height=4000 page", prev.splitlines()[0])

    def test_refuses_unsafe_pages(self):
        bad = {
            "frame.html": PAGE.replace("<body>", '<body><iframe src="x.html"></iframe>'),
            "embed.html": PAGE.replace("<body>", "<body><EMBED src=a.swf>"),
            "noscript.html": PAGE.replace("<body>", "<body><noscript>x</noscript>"),
            "cdn.html": PAGE.replace("</head>", '<link rel="stylesheet" href="https://cdn.example.com/a.css"></head>'),
            "img.html": PAGE.replace("<body>", "<body><img src='//images.example.com/a.png'>"),
            "css.html": PAGE.replace("var(--paper)", "url(https://images.example.com/bg.png)"),
            "script.html": PAGE.replace("</head>", '<script src="https://fonts.googleapis.com/x.js"></script></head>'),
            "js.html": PAGE.replace("mailto:hello@example.com", "javascript:alert(1)"),
        }
        for name, text in bad.items():
            with self.assertRaises(ValueError, msg=name):
                dm.page_card("Bad", self.page(name, text))
        self.assertEqual(dm.check_page_html(PAGE.replace("</head>", '<script src="app.js"></script></head>')), [])

    def test_names_and_cli(self):
        home = self.page("home.html", PAGE)
        with self.assertRaises(ValueError):
            dm.parse_pages([f"home-page={home}"])
        with self.assertRaises(ValueError):
            dm.parse_pages([f"Home={self.dir / 'missing.html'}"])
        with self.assertRaises(ValueError):
            dm.build_ds(self.doc, Path(tempfile.mkdtemp()), pages=dm.parse_pages([f"buttonPrimary={home}"]))
        bad = self.page("bad.html", PAGE.replace("<body>", "<body><object></object>"))
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(Path(tempfile.mkdtemp())), "--page", f"Bad={bad}"]), 2)
        out = Path(tempfile.mkdtemp())
        self.assertEqual(dm.main(["ds", str(write(SAMPLE)), "-o", str(out), "--page", f"Home={home}",
                                  "--page-height", "700"]), 0)
        self.assertIn("height=700 page", (out / "project/components/Home/preview.html").read_text())


ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.75"><path d="M4 8h12v6H4z"/></svg>')


class AssetNoteTest(unittest.TestCase):
    def doc_with(self, *titles):
        text = SAMPLE + "".join(f"\n## {t}\n\nNotes for {t}.\n" for t in titles)
        return dm.load(write(text))

    def test_stem_and_exact(self):
        doc = self.doc_with("Iconography", "Photography and imagery", "Logo", "Company voice")
        self.assertEqual(dm.asset_note(doc, "Icons"), "Notes for Iconography.")
        self.assertEqual(dm.asset_note(doc, "Photos"), "Notes for Photography and imagery.")
        self.assertEqual(dm.asset_note(doc, "Logos"), "Notes for Logo.")
        self.assertIsNone(dm.asset_note(doc, "Components"))  # "comp" alone is no shared stem
        self.assertIsNone(dm.asset_note(doc, "Fonts"))

    def test_exact_first(self):
        doc = self.doc_with("Iconography", "Icons")
        self.assertEqual(dm.asset_note(doc, "Icons"), "Notes for Icons.")

    def test_group_readme_in_build(self):
        doc = self.doc_with("Iconography")
        src = Path(tempfile.mkdtemp())
        (src / "cup.svg").write_text(ICON)
        (src / "mark.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><path fill="#111" d="M0 0h1v1z"/></svg>')
        photos = Path(tempfile.mkdtemp())
        (photos / "a.jpg").write_bytes(b"\xff\xd8\xff")
        out = Path(tempfile.mkdtemp())
        dm.build_ds(doc, out, assets=[("Icons", src), ("Photos", photos)], now="2026-01-01T00:00:00Z")
        icons = (out / "project/assets/Icons/README.md").read_text()
        self.assertTrue(icons.startswith("# Icons\n\nNotes for Iconography.\n"))
        self.assertIn("`currentColor`: `cup.svg`.", icons)
        self.assertNotIn("mark.svg", icons)
        self.assertIn("never redraw them", (out / "project/assets/Photos/README.md").read_text())
        readme = (out / "project/README.md").read_text()
        self.assertIn("- Asset groups: Icons, Photos.", readme)
        self.assertIn("Single-ink SVG icons draw with `currentColor`", readme)


class UsingSectionTest(unittest.TestCase):
    def test_section(self):
        doc = dm.load(write(SAMPLE))
        s = dm.using_section(doc, ["Logos"])
        lines = s.strip().splitlines()
        self.assertEqual(lines[0], "## Using this system")
        self.assertLessEqual(len(lines), 12)
        self.assertIn("`light`, `dark`. The first, `light`, is the fallback", s)
        self.assertIn("(`on-primary` on `primary`)", s)
        self.assertIn("`window.AcmeBakery` in `components/bundle.js`", s)
        self.assertIn("React 18", s)
        self.assertIn("- Asset groups: Logos.", s)
        self.assertNotIn("currentColor", s)
        self.assertTrue(lines[-1].startswith("- DESIGN.md is the source."))
        readme = dm.ds_readme(doc)
        self.assertTrue(readme.rstrip().endswith("Change it there and build this page again."))
        self.assertEqual(readme.count("## Using this system"), 1)

    def test_own_section_wins(self):
        doc = dm.load(write(SAMPLE + "\n## Using this system\n\nOur own words.\n"))
        readme = dm.ds_readme(doc)
        self.assertEqual(readme.count("## Using this system"), 1)
        self.assertIn("Our own words.", readme)


class RenderIconTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "cup.svg").write_text('<?xml version="1.0"?>' + ICON)
        (self.dir / ".hidden.svg").write_text(ICON)

    def test_own_section_inline_on_ink(self):
        page = dm.render_html(dm.load(write(SAMPLE)), icons=dm.expand_files([str(self.dir)], dm.ICON_EXT))
        self.assertIn(">Iconography</h2>", page)
        self.assertIn('<div class="ic-tile"><svg aria-hidden="true" focusable="false" xmlns=', page)
        self.assertIn('stroke="currentColor"', page)
        self.assertIn("color:var(--ink)", page)
        self.assertNotIn(".hidden.svg", page)
        self.assertNotIn("<?xml", page)

    def test_matches_existing_section(self):
        doc = dm.load(write(SAMPLE + "\n## Icons\n\nLine icons, 1.75 stroke.\n"))
        page = dm.render_html(doc, icons=[self.dir / "cup.svg"])
        self.assertNotIn(">Iconography</h2>", page)
        self.assertRegex(page, r'<section id="icons"><h2>Icons</h2><div class="ic-grid">')

    def test_cli(self):
        p = write(SAMPLE)
        out = p.with_name("view.html")
        self.assertEqual(dm.main(["render", str(p), "-o", str(out), "--icon", str(self.dir / "cup.svg")]), 0)
        self.assertIn('class="ic-tile"', out.read_text())
        bad = self.dir / "bad.svg"
        bad.write_text('<svg onload="x()"></svg>')
        self.assertEqual(dm.main(["render", str(p), "-o", str(out), "--icon", str(bad)]), 2)
        self.assertEqual(dm.main(["render", str(p), "-o", str(out), "--icon", str(self.dir / "nope")]), 2)


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
