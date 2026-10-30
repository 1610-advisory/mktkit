#!/usr/bin/env python3
"""DESIGN.md tools: check it, render it to one HTML page, or build the files
for a claude.ai Design System page from it.

DESIGN.md (Google DESIGN.md format: YAML tokens in the frontmatter, rules in
the prose) is the source. Everything this script writes is a view of it. Never
hand-edit the output; edit DESIGN.md and run the script again.

Standard library only (PyYAML is used when it is installed, else a small
built-in reader that covers the DESIGN.md frontmatter). No brand values live
here: every color, face and word comes from the file it reads.

Usage:
  python3 scripts/design_md.py check  knowledge/DESIGN.md
  python3 scripts/design_md.py render knowledge/DESIGN.md -o brand/design-md.html [--name-logo logo.svg]
          [--logo FILE ...] [--icon FILE_OR_DIR ...]
  python3 scripts/design_md.py ds     knowledge/DESIGN.md -o <dir> [--asset Logos=brand/logos/svg]
          [--asset Icons=brand/icons] [--name-logo logo-light.svg --name-logo dark=logo-dark.svg]
          [--page Home=site/home.html ...] [--page-height 560] [--react-lib <folder with React 18 UMD>]

ds also writes components/bundle.js (window.<Namespace>, one React export per
component), bundle.css and index.d.ts. Previews render through the bundle when
React is on the page and fall back to static markup when it is not.

Detail: references/design-md.md
"""
import argparse
import datetime as dt
import html
import json
import mimetypes
import re
import shutil
import sys
from pathlib import Path

VARIANT_SUFFIXES = ("hover", "active", "pressed", "focus", "disabled", "selected")
SECTION_FOR = {"colors": "Colors", "typography": "Typography", "spacing": "Layout",
               "rounded": "Shapes", "components": "Components"}


# --------------------------------------------------------------------------
# YAML: PyYAML when present, else a reader for the subset DESIGN.md uses
# (nested maps, scalars, simple lists, comments, | and > blocks).
# --------------------------------------------------------------------------

def _strip_comment(line):
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            if ch == q and (q == "'" or line[i - 1] != "\\"):
                q = None
        elif ch in "'\"":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(s):
    s = s.strip()
    if not s:
        return None
    if s[0] == s[-1] and s[0] in "'\"" and len(s) >= 2:
        body = s[1:-1]
        if s[0] == '"':
            return body.replace('\\"', '"').replace("\\\\", "\\")
        return body.replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_scalar(p) for p in _split_flow(inner)] if inner else []
    if s == "{}":
        return {}
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"[-+]?\d+", s):
        return int(s)
    if re.fullmatch(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?", s):
        return float(s)
    return s


def _split_flow(s):
    parts, cur, q = [], "", None
    for ch in s:
        if q:
            q = None if ch == q else q
        elif ch in "'\"":
            q = ch
        elif ch == ",":
            parts.append(cur)
            cur = ""
            continue
        cur += ch
    parts.append(cur)
    return parts


def mini_yaml(text):
    raw = text.splitlines()
    lines = []  # (indent, content, raw line) — raw kept for block scalars
    for r in raw:
        c = _strip_comment(r)
        if c.strip():
            lines.append((len(c) - len(c.lstrip(" ")), c.strip(), r))
        else:
            lines.append((None, "", r))

    def block(i, indent, style):
        """Collect a | or > block scalar whose lines are indented deeper than indent."""
        body, j = [], i
        while j < len(lines):
            ind, c, r = lines[j]
            rind = len(r) - len(r.lstrip(" "))
            if r.strip() and rind <= indent:
                break
            body.append(r)
            j += 1
        nonblank = [len(b) - len(b.lstrip(" ")) for b in body if b.strip()]
        cut = min(nonblank) if nonblank else 0
        body = [b[cut:] for b in body]
        while body and not body[-1].strip():
            body.pop()
        if style.startswith(">"):
            paras, cur = [], []
            for b in body:
                if b.strip():
                    cur.append(b.strip())
                else:
                    paras.append(" ".join(cur))
                    cur = []
            paras.append(" ".join(cur))
            return "\n".join(paras) + "\n", j
        return "\n".join(body) + "\n", j

    def parse(i, indent):
        while i < len(lines) and lines[i][0] is None:
            i += 1
        if i >= len(lines):
            return None, i
        if lines[i][1].startswith("- ") or lines[i][1] == "-":
            out = []
            while i < len(lines):
                ind, c, _ = lines[i]
                if ind is None:
                    i += 1
                    continue
                if ind != indent or not (c.startswith("- ") or c == "-"):
                    break
                item = c[1:].strip()
                if not item:
                    val, i = parse(i + 1, _next_indent(i + 1))
                    out.append(val)
                elif re.match(r"^[^'\"\s][^:]*:(\s|$)", item):
                    # "- key: value" starts a map; continue it at the item's indent
                    sub = indent + 2
                    lines[i] = (sub, item, lines[i][2])
                    val, i = parse(i, sub)
                    out.append(val)
                else:
                    out.append(_scalar(item))
                    i += 1
            return out, i
        out = {}
        while i < len(lines):
            ind, c, _ = lines[i]
            if ind is None:
                i += 1
                continue
            if ind < indent:
                break
            if ind > indent:
                raise ValueError(f"bad indent at: {c!r}")
            m = re.match(r'^("[^"]*"|\'[^\']*\'|[^:]+?)\s*:(\s+(.*))?$', c)
            if not m:
                raise ValueError(f"cannot read line: {c!r}")
            key = _scalar(m.group(1))
            key = str(key) if not isinstance(key, str) else key
            rest = (m.group(3) or "").strip()
            if rest in ("|", ">", "|-", ">-", "|+", ">+"):
                val, i = block(i + 1, ind, rest)
                out[key] = val.rstrip("\n") if rest.endswith("-") else val
            elif rest:
                out[key] = _scalar(rest)
                i += 1
            else:
                nxt = _next_indent(i + 1)
                if nxt is not None and (nxt > ind or (nxt == ind and lines[_next_line(i + 1)][1].startswith("-"))):
                    out[key], i = parse(_next_line(i + 1), nxt)
                else:
                    out[key] = None
                    i += 1
        return out, i

    def _next_line(i):
        while i < len(lines) and lines[i][0] is None:
            i += 1
        return i

    def _next_indent(i):
        j = _next_line(i)
        return lines[j][0] if j < len(lines) else None

    first = _next_indent(0)
    if first is None:
        return {}
    val, _ = parse(_next_line(0), first)
    return val


def parse_yaml(text):
    try:
        import yaml  # type: ignore
    except ImportError:
        return mini_yaml(text)
    return yaml.safe_load(text) or {}


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------

def split_frontmatter(text):
    m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)\Z", text, re.S)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    tokens = parse_yaml(fm) if fm else {}
    if not isinstance(tokens, dict):
        tokens = {}
    doc = {
        "path": str(path),
        "has_frontmatter": bool(fm),
        "tokens": tokens,
        "name": str(tokens.get("name") or "").strip(),
        "description": str(tokens.get("description") or "").strip(),
        "colors": {k: str(v) for k, v in (tokens.get("colors") or {}).items() if v is not None},
        "themes": {k: {kk: str(vv) for kk, vv in (v or {}).items() if vv is not None}
                   for k, v in (tokens.get("themes") or {}).items()},
        "typography": {k: v for k, v in (tokens.get("typography") or {}).items() if isinstance(v, dict)},
        "rounded": tokens.get("rounded") or {},
        "spacing": tokens.get("spacing") or {},
        "components": {k: v for k, v in (tokens.get("components") or {}).items() if isinstance(v, dict)},
        "design_system_url": tokens.get("design_system_url"),
        "body": body,
    }
    doc["intro"], doc["sections"] = split_sections(body)
    return doc


def split_sections(body):
    """Return (intro markdown, [(title, markdown)]) split on level-2 headings; the H1 is dropped."""
    body = re.sub(r"\A\s*# [^\n]*\n", "", body.strip() + "\n", count=1)
    chunks = re.split(r"(?m)^## ", body)
    intro, sections = chunks[0].strip(), []
    for c in chunks[1:]:
        title, _, text = c.partition("\n")
        sections.append((title.strip(), text.strip()))
    return intro, sections


def theme_ids(doc):
    return ["light"] + [t for t in doc["themes"] if t != "light"]


def color_in(doc, name, theme="light"):
    if theme != "light" and name in doc["themes"].get(theme, {}):
        return doc["themes"][theme][name]
    return doc["colors"].get(name)


REF = re.compile(r"^\{([a-zA-Z]+)\.([^}]+)\}$")


def ref_parts(value):
    m = REF.match(str(value).strip()) if isinstance(value, str) else None
    return (m.group(1), m.group(2)) if m else None


def resolve(doc, value, theme="light"):
    """Resolve a {group.name} reference to its value; plain values pass through."""
    parts = ref_parts(value)
    if not parts:
        return value
    group, name = parts
    if group == "colors":
        return color_in(doc, name, theme)
    table = doc["tokens"].get(group) or {}
    return table.get(name) if isinstance(table, dict) else None


# --------------------------------------------------------------------------
# Color math
# --------------------------------------------------------------------------

def hex_rgb(value):
    if not isinstance(value, str):
        return None
    h = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}", h):
        return None
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h[:3])
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(value):
    rgb = hex_rgb(value)
    if rgb is None:
        return None
    c = [x / 255 for x in rgb]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    if la is None or lb is None:
        return None
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# --------------------------------------------------------------------------
# Roles: which tokens the views use for ground, text, links and type
# --------------------------------------------------------------------------

def _first(doc, names):
    for n in names:
        if n in doc["colors"]:
            return n
    return None


def roles(doc):
    comp_page = doc["components"].get("page") or {}
    ref_bg, ref_fg = ref_parts(comp_page.get("backgroundColor")), ref_parts(comp_page.get("textColor"))
    ground = (ref_bg[1] if ref_bg and ref_bg[0] == "colors" and ref_bg[1] in doc["colors"] else None) or \
        _first(doc, ["background", "paper", "surface", "neutral", "canvas", "base", "white"])
    ink = (ref_fg[1] if ref_fg and ref_fg[0] == "colors" and ref_fg[1] in doc["colors"] else None) or \
        _first(doc, ["ink", "on-surface", "on-background", "text", "foreground", "on-neutral"])
    if ink is None and ground and doc["colors"]:
        best = max(doc["colors"], key=lambda n: contrast(doc["colors"][n], doc["colors"][ground]) or 0)
        ink = best if (contrast(doc["colors"][best], doc["colors"][ground]) or 0) >= 4.5 else None
    muted = _first(doc, ["ink-muted", "on-surface-variant", "text-muted", "muted", "secondary-text"]) or ink
    accent = _first(doc, ["link", "primary", "accent"]) or ink
    rule = _first(doc, ["outline", "border", "divider", "line", "outline-variant"]) or muted
    return {"ground": ground, "ink": ink, "muted": muted, "accent": accent, "rule": rule}


def _style_key(doc, names, contains=None):
    for n in names:
        if n in doc["typography"]:
            return n
    if contains:
        for n in doc["typography"]:
            if contains in n:
                return n
    return next(iter(doc["typography"]), None)


def type_roles(doc):
    display = _style_key(doc, ["display", "display-lg", "headline-lg", "headline", "h1"], "headline")
    body = _style_key(doc, ["body-md", "body", "body-lg"], "body")
    label = None
    for n, t in doc["typography"].items():
        if "mono" in str(t.get("fontFamily", "")).lower():
            label = n
            break
    return {"display": display, "body": body, "label": label}


def family_of(doc, style):
    t = doc["typography"].get(style) or {}
    return str(t.get("fontFamily") or "").strip()


SERIF_HINTS = ("serif", "garamond", "playfair", "georgia", "times", "baskerville", "caslon", "lora",
               "merriweather", "fraunces", "cormorant", "libre", "crimson", "spectral", "bodoni", "didot")


def fallback_for(family):
    f = family.lower()
    if "mono" in f or "code" in f:
        return "ui-monospace, monospace"
    if any(h in f for h in SERIF_HINTS) and "sans" not in f:
        return "Georgia, serif"
    return "system-ui, sans-serif"


def stack(family):
    return f'"{family}", {fallback_for(family)}' if family else "system-ui, sans-serif"


def families(doc):
    seen = []
    for t in doc["typography"].values():
        f = str(t.get("fontFamily") or "").strip()
        if f and f not in seen:
            seen.append(f)
    return seen


def google_fonts_href(doc):
    fams = families(doc)
    if not fams:
        return None
    parts = []
    for f in fams:
        weights = sorted({int(str(t.get("fontWeight", 400)).split()[0]) for t in doc["typography"].values()
                          if str(t.get("fontFamily") or "").strip() == f and str(t.get("fontWeight", 400)).split()[0].isdigit()} or {400})
        parts.append("family=" + f.replace(" ", "+") + ":wght@" + ";".join(str(w) for w in weights))
    return "https://fonts.googleapis.com/css2?" + "&".join(parts) + "&display=swap"


def overview_sentence(doc, limit=110):
    for title, text in doc["sections"]:
        if title.lower() == "overview":
            plain = plain_text(text)
            m = re.match(r"(.+?[.!?])(\s|$)", plain)
            s = m.group(1) if m else plain
            if 0 < len(s) <= limit:
                return s
    d = plain_text(doc["description"])
    m = re.match(r"(.+?[.!?])(\s|$)", d)
    s = m.group(1) if m else d
    return s if len(s) <= limit else s[:limit - 1].rsplit(" ", 1)[0] + "…"


# --------------------------------------------------------------------------
# Check
# --------------------------------------------------------------------------

def check(doc):
    """Return a list of (level, message). level is 'error' or 'warn'."""
    out = []
    if not doc["has_frontmatter"]:
        return [("error", "no YAML frontmatter (--- block) at the top of the file")]
    if not doc["name"] or doc["name"].startswith("["):
        out.append(("error", "`name` is missing or still the template placeholder"))
    if not doc["colors"]:
        out.append(("error", "no `colors` tokens"))
    for scope, table in [("colors", doc["colors"])] + [(f"themes.{t}", v) for t, v in doc["themes"].items()]:
        for k, v in table.items():
            if hex_rgb(v) is None:
                out.append(("warn", f"{scope}.{k} = {v!r} is not a hex color; contrast checks skip it"))
    for t, v in doc["themes"].items():
        for k in v:
            if k not in doc["colors"]:
                out.append(("warn", f"themes.{t}.{k} has no light value in `colors`"))
    if not doc["typography"]:
        out.append(("error", "no `typography` tokens"))
    for k, t in doc["typography"].items():
        if not str(t.get("fontFamily") or "").strip():
            out.append(("warn", f"typography.{k} has no fontFamily"))
    for cname, comp in doc["components"].items():
        for prop, val in comp.items():
            parts = ref_parts(val)
            if parts and resolve(doc, val) is None:
                out.append(("error", f"components.{cname}.{prop} points at {val}, which does not exist"))
        bg, fg = comp.get("backgroundColor"), comp.get("textColor")
        if bg and fg:
            for th in theme_ids(doc):
                r = contrast(resolve(doc, fg, th), resolve(doc, bg, th))
                if r is not None and r < 4.5:
                    out.append(("warn", f"components.{cname}: text on background is {r:.1f}:1 in {th} (under 4.5:1)"))
    if not doc["sections"]:
        out.append(("warn", "no prose sections (## headings); the rules belong below the tokens"))
    return out


# --------------------------------------------------------------------------
# Markdown (the small set DESIGN.md prose uses)
# --------------------------------------------------------------------------

def _inline(text):
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", keep, text)
    t = html.escape(t, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    t = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noopener">\1</a>', t)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{html.escape(codes[int(m.group(1))])}</code>", t)


def plain_text(md):
    t = re.sub(r"`([^`]+)`", r"\1", md)
    t = re.sub(r"\*\*(.+?)\*\*|\*(.+?)\*", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def md_to_html(md):
    lines, out, i = md.splitlines(), [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            j, buf = i + 1, []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            i = j + 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl = min(len(m.group(1)) + 1, 6)  # the page owns h1/h2
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if re.fullmatch(r"(-{3,}|\*{3,})", s):
            out.append("<hr>")
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\|?[\s:|-]+\|?", lines[i + 1].strip()):
            cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            head = cells(s)
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(cells(lines[j]))
                j += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in head)
            tb = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table></div>')
            i = j
            continue
        if s.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(buf))}</p></blockquote>")
            continue
        lm = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", ln)
        if lm:
            ordered = lm.group(2)[0].isdigit()
            items = []
            while i < len(lines):
                cur = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[i])
                if cur:
                    items.append(cur.group(3).strip())
                    i += 1
                elif lines[i].strip() and lines[i].startswith((" ", "\t")) and items:
                    items[-1] += " " + lines[i].strip()
                    i += 1
                else:
                    break
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        buf = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(\s*)([-*+]|\d+[.)])\s+|^#{1,6}\s|^```|^\||^>", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{_inline(' '.join(buf))}</p>")
        else:
            i += 1
    return "\n".join(out)


# --------------------------------------------------------------------------
# Components: fold state variants into their base
# --------------------------------------------------------------------------

def component_groups(doc):
    """{base: [(state, name, props)]}, base state first, in file order."""
    groups = {}
    names = list(doc["components"])
    for n in names:
        base, state = n, "default"
        for suf in VARIANT_SUFFIXES:
            if n.endswith("-" + suf) and n[: -len(suf) - 1] in doc["components"]:
                base, state = n[: -len(suf) - 1], suf
                break
        props = doc["components"][n]
        if state != "default":
            props = {**doc["components"][base], **props}  # a state inherits its base
        groups.setdefault(base, []).append((state, n, props))
    for base in groups:
        groups[base].sort(key=lambda x: x[0] != "default")
    return groups


def humanize(name):
    words = name.replace("_", "-").split("-")
    return " ".join(words).capitalize()


def pascal(name):
    p = "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", name) if w)
    if not p or not p[0].isalpha():
        p = "C" + p
    return p


# --------------------------------------------------------------------------
# render: one self-contained HTML view (any agent)
# --------------------------------------------------------------------------

def _css_color_vars(doc, theme):
    names = list(doc["colors"]) + [k for k in doc["themes"].get(theme, {}) if k not in doc["colors"]]
    return ";".join(f"--c-{n}:{color_in(doc, n, theme) or doc['themes'].get(theme, {}).get(n)}" for n in names)


def _role_vars(doc):
    r = roles(doc)
    v = lambda n, fb: f"var(--c-{n})" if n else fb
    return (f"--ground:{v(r['ground'], '#ffffff')};--ink:{v(r['ink'], '#111111')};--muted:{v(r['muted'], '#555555')};"
            f"--accent:{v(r['accent'], '#111111')};--rule:color-mix(in srgb,var(--ink) 16%,transparent)")


def _swatches(doc):
    themes = theme_ids(doc)
    r = roles(doc)
    head = "".join(f"<span>{html.escape(t.capitalize())}</span>" for t in themes)
    rows = []
    for name in doc["colors"]:
        cells = []
        for th in themes:
            hx = color_in(doc, name, th)
            ground = color_in(doc, r["ground"], th) if r["ground"] else "#ffffff"
            cr = contrast(hx, ground)
            note = f"{cr:.1f}:1 on {r['ground'] or 'white'}" if cr is not None and name != r["ground"] else ("the ground" if name == r["ground"] else "")
            cells.append(f'<div class="sw-c"><span class="chip" style="background:{html.escape(hx or "transparent")}"></span>'
                         f'<code>{html.escape(hx or "")}</code><span class="cr">{note}</span></div>')
        use = color_usage(doc, name)
        use = "" if use.startswith("Defined in") else (use if len(use) <= 90 else use[:89].rsplit(" ", 1)[0] + "…")
        rows.append(f'<div class="sw-row" style="--cols:{len(themes)}"><div class="sw-n"><b>{html.escape(name)}</b>'
                    f'<span>{html.escape(use)}</span></div>{"".join(cells)}</div>')
    return (f'<div class="sw"><div class="sw-row sw-head" style="--cols:{len(themes)}"><span>Token</span>{head}</div>'
            f'{"".join(rows)}</div>')


def _sample_for(doc, style):
    n = style.lower()
    if any(k in n for k in ("body", "paragraph", "text")):
        return overview_sentence(doc, 160) or doc["name"]
    return doc["name"] or style


def feature_css(t):
    """fontFeature ("lnum", or "lnum, tnum") as font-feature-settings; empty when absent."""
    tags = [x.strip().strip("'\"") for x in str(t.get("fontFeature") or "").split(",")]
    tags = [x for x in tags if re.fullmatch(r"[a-z0-9]{4}( (on|off|\d+))?", x)]
    return "font-feature-settings:" + ",".join(f'"{x[:4]}"{x[4:]}' for x in tags) + ";" if tags else ""


def is_rule(props):
    """A component no taller than 4px (a hairline or gold rule) shows as a bar, not a label."""
    m = re.match(r"^([\d.]+)px$", str(props.get("height") or ""))
    return bool(m) and float(m.group(1)) <= 4


def _type_css(t):
    css = f"font-family:{stack(str(t.get('fontFamily') or ''))};" + feature_css(t)
    for k, prop in (("fontSize", "font-size"), ("fontWeight", "font-weight"), ("lineHeight", "line-height"),
                    ("letterSpacing", "letter-spacing"), ("fontStyle", "font-style")):
        if t.get(k) not in (None, ""):
            css += f"{prop}:{t[k]};"
    return css


def _specimens(doc):
    rows = []
    for k, t in doc["typography"].items():
        spec = " · ".join(str(t.get(x)) for x in ("fontFamily", "fontSize", "fontWeight") if t.get(x) not in (None, ""))
        style = _type_css(t)
        size = str(t.get("fontSize") or "")
        m = re.match(r"([\d.]+)px", size)
        if m and float(m.group(1)) > 56:
            style += "font-size:56px;"
        if "caps" in k or "eyebrow" in k:
            style += "text-transform:uppercase;"
        rows.append(f'<div class="ty"><div class="ty-k"><b>{html.escape(k)}</b><span>{html.escape(spec)}</span></div>'
                    f'<div class="ty-s" style="{html.escape(style)}">{html.escape(_sample_for(doc, k))}</div></div>')
    return f'<div class="ty-list">{"".join(rows)}</div>'


def _scale(doc, key):
    table = doc[key]
    rows = []
    for k, v in table.items():
        m = re.match(r"^([\d.]+)px$", str(v).strip())
        px = float(m.group(1)) if m else None
        if key == "spacing":
            bar = f'<span class="bar" style="width:min(100%,{px:g}px)"></span>' if px is not None else ""
        else:
            bar = f'<span class="rad" style="border-radius:{html.escape(str(v))}"></span>'
        rows.append(f'<div class="sc"><b>{html.escape(str(k))}</b><code>{html.escape(str(v))}</code>{bar}</div>')
    return f'<div class="sc-list">{"".join(rows)}</div>'


def _comp_style(doc, props, preview=False):
    """Inline CSS for a component sample. render: --c-<name> vars; preview: the Design System page's --<name>."""
    var = (lambda n: f"var(--{n})") if preview else (lambda n: f"var(--c-{n})")
    css, cls = "", ""
    for prop, val in props.items():
        parts = ref_parts(val)
        if prop in ("backgroundColor", "textColor", "borderColor"):
            cssprop = {"backgroundColor": "background", "textColor": "color", "borderColor": "border-color"}[prop]
            if parts and parts[0] == "colors":
                css += f"{cssprop}:{var(parts[1])};"
            elif not parts:
                css += f"{cssprop}:{val};"
            if prop == "borderColor":
                css += "border-width:1px;border-style:solid;"
        elif prop == "typography":
            if parts and parts[0] == "typography":
                if preview:
                    cls = token_name("type", parts[1])
                    css += feature_css(doc["typography"].get(parts[1]) or {})
                else:
                    css += _type_css(doc["typography"].get(parts[1]) or {})
        elif prop == "rounded":
            if parts and parts[0] == "rounded":
                css += f"border-radius:{var('radius-' + parts[1]) if preview else resolve(doc, val)};"
            else:
                css += f"border-radius:{val};"
        elif prop == "height":
            css += f"height:{val};" if is_rule(props) else f"min-height:{val};"
        elif prop == "padding":
            css += f"padding-inline:{val};" if "height" in props else f"padding:{val};"
        elif prop == "width":
            css += f"width:{val};"
    return css, cls


def _components(doc):
    cells = []
    r = roles(doc)
    for base, states in component_groups(doc).items():
        samples = []
        for state, name, props in states:
            css, _ = _comp_style(doc, props)
            if props.get("backgroundColor") and r["ground"] and ref_parts(props["backgroundColor"]) == ("colors", r["ground"]):
                css += "outline:1px solid var(--rule);"
            label = "" if is_rule(props) else html.escape(humanize(base))
            samples.append(f'<div class="cp-s"><div class="cp-el" style="{html.escape(css)}">{label}</div>'
                           f'<span class="cp-st">{html.escape(state)}</span></div>')
        spec = "; ".join(f"{k}: {v}" for k, v in states[0][2].items())
        cells.append(f'<figure class="cp"><div class="cp-stage">{"".join(samples)}</div>'
                     f'<figcaption><b>{html.escape(base)}</b> <code>{html.escape(spec)}</code></figcaption></figure>')
    return f'<div class="cp-grid">{"".join(cells)}</div>'


def _logos(paths):
    import base64
    cells = []
    for p in paths:
        p = Path(p)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        data = base64.b64encode(p.read_bytes()).decode()
        cells.append(f'<figure class="lg"><div class="lg-tile"><img src="data:{mime};base64,{data}" alt="{html.escape(p.stem)}">'
                     f'</div><figcaption>{html.escape(p.name)}</figcaption></figure>')
    return f'<div class="lg-grid">{"".join(cells)}</div>'


ICON_EXT = {".svg", ".png", ".webp", ".gif", ".jpg", ".jpeg"}


def expand_files(specs, exts):
    """Files from FILE or DIR arguments, a folder's files sorted, dot-files skipped."""
    out = []
    for s in specs:
        p = Path(s)
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in exts
                          and not any(part.startswith(".") for part in f.relative_to(p).parts))
        elif p.is_file():
            out.append(p)
        else:
            raise ValueError(f"{s}: no such file or folder")
    return out


def clean_svg(text, path="svg"):
    """An SVG fit to inline: no XML prolog, no scripts or event handlers."""
    svg = re.sub(r"<\?xml[^>]*>\s*", "", text)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg, flags=re.I).strip()
    svg = re.sub(r"\A(<!--.*?-->\s*)+", "", svg, flags=re.S)
    if (re.search(r"<script|<foreignObject|\son[a-z]+\s*=|javascript:", svg, re.I)
            or not svg.startswith("<svg")):
        raise ValueError(f"{path}: not a plain SVG")
    return svg


def _icons(paths):
    """Icon tiles on the page's ink: SVGs inline (so currentColor takes the ink), other images as data URIs."""
    import base64
    cells = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() == ".svg":
            art = clean_svg(p.read_text(encoding="utf-8"), p)
            art = re.sub(r"^<svg\b", '<svg aria-hidden="true" focusable="false"', art, count=1)
        else:
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            art = f'<img src="data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}" alt="">'
        cells.append(f'<figure class="ic"><div class="ic-tile">{art}</div><figcaption>{html.escape(p.name)}</figcaption></figure>')
    return f'<div class="ic-grid">{"".join(cells)}</div>'


def _visual_for(doc, title, logos=(), icons=()):
    t = title.lower()
    if t.startswith("logo"):
        return "logos", _logos(logos) if logos else ""
    if t.startswith("icon"):
        return "icons", _icons(icons) if icons else ""
    if t.startswith("color"):
        return "colors", _swatches(doc) if doc["colors"] else ""
    if t.startswith("typograph"):
        return "typography", _specimens(doc) if doc["typography"] else ""
    if t.startswith("layout") or t.startswith("spacing"):
        return "spacing", _scale(doc, "spacing") if doc["spacing"] else ""
    if t.startswith("shape") or t.startswith("corner") or t.startswith("radius"):
        return "rounded", _scale(doc, "rounded") if doc["rounded"] else ""
    if t.startswith("component"):
        return "components", _components(doc) if doc["components"] else ""
    return None, ""


def name_logo_html(doc, marks):
    """The logo, inline, standing in for the name in a header. marks: {theme: svg path}; "light" is the default.

    One copy per theme, each shown only in its theme ([data-theme] on <html>, or the system setting when no
    theme is picked), so a header shows the real logo file and never the name retyped in a font."""
    if not marks:
        return "", ""
    themes = theme_ids(doc)
    base = "light" if "light" in marks else next(iter(marks))
    parts, css = [], [".mark,.mark svg{display:block}"]
    for t, path in marks.items():
        svg = Path(path).read_text(encoding="utf-8")
        svg = re.sub(r"<\?xml[^>]*>\s*", "", svg).strip()
        if re.search(r"<script|\son[a-z]+\s*=", svg, re.I) or not svg.startswith("<svg"):
            raise ValueError(f"{path}: not a plain SVG logo")
        svg = re.sub(r"^<svg\b([^>]*)>", lambda m: "<svg" + re.sub(r'\s(width|height|preserveAspectRatio)="[^"]*"', "", m.group(1))
                     + ' preserveAspectRatio="xMinYMax meet" aria-hidden="true" focusable="false">', svg, count=1)
        parts.append(f'<span class="mark mark-{slug(t)}">{svg}</span>')
        if t != base:
            css.append(f".mark-{slug(t)}{{display:none}}")
            css.append(f':root[data-theme="{t}"] .mark-{slug(t)}{{display:block}}'
                       f':root[data-theme="{t}"] .mark-{slug(base)}{{display:none}}')
            if t == "dark" and t in themes:
                css.append(f"@media (prefers-color-scheme:dark){{:root:not([data-theme]) .mark-dark{{display:block}}"
                           f":root:not([data-theme]) .mark-{slug(base)}{{display:none}}}}")
    sr = f'<span class="sr">{html.escape(doc["name"] or "Design")}</span>'
    css.append(".sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}")
    return "".join(parts) + sr, "\n".join(css)


def parse_name_logo(doc, specs):
    """--name-logo FILE (every theme) or THEME=FILE. Returns {theme: path}."""
    marks = {}
    for spec in specs:
        theme, sep, path = spec.partition("=")
        if not sep:
            theme, path = "light", spec
        if theme not in theme_ids(doc):
            raise ValueError(f"--name-logo: no theme {theme!r} in DESIGN.md (themes: {', '.join(theme_ids(doc))})")
        if not Path(path).is_file() or Path(path).suffix.lower() != ".svg":
            raise ValueError(f"--name-logo: {path} is not an .svg file")
        marks[theme] = path
    return marks


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "section"


def render_html(doc, logos=(), name_logo=None, icons=()):
    """One self-contained page. logos: image files shown as tiles in the Logo section (or a section of their own).
    name_logo: {theme: svg} shown in the header in place of the typed name (see name_logo_html).
    icons: icon files shown as tiles in the Iconography section (or a section of their own)."""
    sections, done = [], set()
    for title, text in doc["sections"]:
        key, visual = _visual_for(doc, title, logos, icons)
        if key:
            done.add(key)
        sections.append((title, visual, md_to_html(text)))
    makers = {"colors": _swatches, "typography": _specimens, "spacing": lambda d: _scale(d, "spacing"),
              "rounded": lambda d: _scale(d, "rounded"), "components": _components}
    missing = [(SECTION_FOR[k], makers[k](doc), "") for k in SECTION_FOR
               if k not in done and doc[k]]
    if icons and "icons" not in done:
        missing.insert(0, ("Iconography", _icons(icons), ""))
    if logos and "logos" not in done:
        missing.insert(0, ("Logo", _logos(logos), ""))
    at = 1 if sections and sections[0][0].lower() == "overview" else 0
    sections[at:at] = missing

    mark, mark_css = name_logo_html(doc, name_logo)
    nav = "".join(f'<a href="#{slug(t)}">{html.escape(t)}</a>' for t, _, _ in sections)
    body = "".join(f'<section id="{slug(t)}"><h2>{html.escape(t)}</h2>{v}<div class="prose">{p}</div></section>'
                   for t, v, p in sections)
    tr = type_roles(doc)
    disp, bodyf = family_of(doc, tr["display"]), family_of(doc, tr["body"])
    monof = family_of(doc, tr["label"]) if tr["label"] else ""
    fonts = google_fonts_href(doc)
    themes = theme_ids(doc)
    light = _css_color_vars(doc, "light")
    theme_css = ""
    toggle = ""
    if len(themes) > 1:
        dark = next((t for t in themes if t == "dark"), None)
        for t in themes[1:]:
            theme_css += f':root[data-theme="{t}"]{{{_css_color_vars(doc, t)}{";color-scheme:dark" if t == "dark" else ""}}}\n'
        if dark:
            theme_css += f'@media (prefers-color-scheme:dark){{:root:not([data-theme]){{{_css_color_vars(doc, "dark")};color-scheme:dark}}}}\n'
        toggle = ('<div class="theme" role="group" aria-label="Theme">'
                  + "".join(f'<button type="button" data-t="{t}">{html.escape(t.capitalize())}</button>' for t in themes)
                  + '<button type="button" data-t="system">System</button></div>')
    name = doc["name"] or "Design"
    page = PAGE.format(
        title=html.escape(f"{name} design"),
        fonts=f'<link rel="stylesheet" href="{html.escape(fonts)}">' if fonts else "",
        light=light, theme_css=theme_css, roles=_role_vars(doc),
        display=stack(disp), body=stack(bodyf), mono=stack(monof) if monof else "ui-monospace, monospace",
        name=html.escape(name), toggle=toggle, intro=md_to_html(doc["intro"]) if doc["intro"] else
        (f"<p>{html.escape(doc['description'])}</p>" if doc["description"] else ""),
        nav=nav, sections=body, src=html.escape(Path(doc["path"]).name),
        script=THEME_JS if toggle else "", hero_name=mark or html.escape(name), mark_css=mark_css)
    return page


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{title}</title>
{fonts}
<style>
/* Generated from DESIGN.md by the marketing toolkit's design_md.py. Edit the file, not this page. */
:root{{{light};{roles};--display:{display};--body:{body};--mono:{mono};color-scheme:light}}
{theme_css}*{{box-sizing:border-box}}
body{{margin:0;background:var(--ground);color:var(--ink);font:400 16px/1.6 var(--body)}}
.wrap{{max-width:1200px;margin:0 auto;padding-inline:max(16px,env(safe-area-inset-left,0px)) max(16px,env(safe-area-inset-right,0px));padding-block:28px 96px}}
header.top{{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;padding-bottom:20px;border-bottom:1px solid var(--rule)}}
.kicker{{font:500 11px/1.5 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
.theme{{display:inline-flex;border:1px solid var(--rule)}}
.theme button{{font:500 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;background:transparent;color:var(--muted);border:0;padding:9px 12px;cursor:pointer}}
.theme button[aria-pressed="true"]{{background:var(--ink);color:var(--ground)}}
.hero{{padding:48px 0 16px;max-width:760px}}
.hero h1{{font:400 clamp(40px,6vw,68px)/.95 var(--display);letter-spacing:-.02em;margin:10px 0 16px;text-wrap:balance}}
.hero .prose p{{font-size:18px;color:var(--muted)}}
.hero h1 .mark svg{{width:min(100%,480px);height:auto;max-height:120px}}
{mark_css}
.layout{{display:grid;grid-template-columns:200px minmax(0,1fr);gap:48px;margin-top:24px}}
nav.idx{{position:sticky;top:20px;align-self:start;display:flex;flex-direction:column;border-left:1px solid var(--rule)}}
nav.idx a{{color:var(--muted);text-decoration:none;font-size:14px;padding:6px 0 6px 14px}}
nav.idx a:hover{{color:var(--ink)}}
main{{min-width:0}}
section{{padding:44px 0 8px;border-top:1px solid var(--rule)}}
section:first-child{{border-top:0;padding-top:0}}
section h2{{font:400 40px/1.05 var(--display);margin:0 0 22px;text-wrap:balance}}
.prose{{max-width:720px}}
.prose h3,.prose h4{{font:500 22px/1.2 var(--display);margin:28px 0 8px}}
.prose a{{color:var(--accent);text-underline-offset:3px}}
code{{font:400 13px var(--mono);background:color-mix(in srgb,var(--ink) 7%,transparent);padding:1px 5px}}
pre{{overflow-x:auto;background:color-mix(in srgb,var(--ink) 6%,transparent);padding:14px}}pre code{{background:none;padding:0}}
blockquote{{margin:16px 0;padding-left:16px;border-left:2px solid var(--rule);color:var(--muted)}}
.tbl{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:15px;margin:16px 0}}
th,td{{text-align:left;padding:9px 14px 9px 0;border-bottom:1px solid var(--rule);vertical-align:top}}
th{{font:500 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}}
.sw{{margin-bottom:28px}}
.sw-row{{display:grid;grid-template-columns:minmax(0,1fr) repeat(var(--cols),minmax(0,1.2fr));gap:14px;align-items:center;padding:8px 0;border-bottom:1px solid var(--rule)}}
.sw-head{{font:500 11px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}}
.sw-n{{display:grid;font-size:13px;min-width:0;overflow-wrap:anywhere}}.sw-n span{{color:var(--muted);font-size:12px;line-height:1.35}}
.lg-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:28px}}
.lg{{margin:0;display:grid;gap:6px}}.lg-tile{{display:flex;align-items:center;justify-content:center;height:140px;padding:24px;outline:1px solid var(--rule);outline-offset:-1px}}
.lg-tile img{{max-width:100%;max-height:92px}}
.ic-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:12px;margin-bottom:28px}}
.ic{{margin:0;display:grid;gap:6px;min-width:0}}.ic figcaption{{font-size:12px;overflow-wrap:anywhere}}
.ic-tile{{display:flex;align-items:center;justify-content:center;height:80px;color:var(--ink);outline:1px solid var(--rule);outline-offset:-1px}}
.ic-tile svg,.ic-tile img{{width:32px;height:32px}}
.sw-c{{display:grid;grid-template-columns:34px minmax(0,1fr);column-gap:10px;align-items:center;min-width:0}}
.chip{{grid-row:span 2;width:34px;height:34px;outline:1px solid var(--rule);outline-offset:-1px}}
.sw-c code{{background:none;padding:0}}.cr{{font:400 11px var(--mono);color:var(--muted)}}
.ty-list{{border-top:1px solid var(--rule);margin-bottom:28px}}
.ty{{display:grid;grid-template-columns:200px minmax(0,1fr);gap:20px;padding:16px 0;border-bottom:1px solid var(--rule);align-items:baseline}}
.ty-k{{display:grid;font-size:13px}}.ty-k span{{color:var(--muted);font:400 11px var(--mono)}}.ty-s{{min-width:0;overflow-wrap:anywhere}}
.sc-list{{display:grid;gap:8px;margin-bottom:28px}}
.sc{{display:grid;grid-template-columns:120px 90px minmax(0,1fr);gap:12px;align-items:center;font-size:13px}}
.sc code{{background:none;padding:0}}
.bar{{display:block;height:10px;background:var(--accent)}}
.rad{{display:block;width:48px;height:48px;border:1.5px solid var(--ink)}}
.cp-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-bottom:28px}}
.cp{{margin:0;display:grid;gap:8px;min-width:0}}
.cp-stage{{border:1px solid var(--rule);padding:20px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start;min-height:110px}}
.cp-s{{display:grid;gap:6px;justify-items:start;min-width:0;max-width:100%}}
.cp-el{{display:inline-flex;align-items:center;max-width:100%;overflow-wrap:anywhere}}
.cp-st{{font:400 11px var(--mono);color:var(--muted)}}
figcaption{{font-size:13px;color:var(--muted)}}figcaption b{{color:var(--ink);margin-right:6px}}figcaption code{{font-size:11px}}
footer.src{{margin-top:56px;padding-top:16px;border-top:1px solid var(--rule);font-size:13px;color:var(--muted)}}
a:focus-visible,button:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
@media (max-width:860px){{.layout{{grid-template-columns:minmax(0,1fr);gap:8px}}nav.idx{{position:static;flex-direction:row;flex-wrap:wrap;border-left:0;gap:4px 14px}}nav.idx a{{padding:4px 0}}
.ty{{grid-template-columns:minmax(0,1fr);gap:6px}}.sw-row{{grid-template-columns:repeat(var(--cols),minmax(0,1fr))}}.sw-n{{grid-column:1/-1}}.sw-head span:first-child{{display:none}}.sc{{grid-template-columns:90px 80px minmax(0,1fr)}}}}
</style></head>
<body><div class="wrap">
<header class="top"><span class="kicker">{name} · rendered from {src}</span>{toggle}</header>
<div class="hero"><h1>{hero_name}</h1><div class="prose">{intro}</div></div>
<div class="layout"><nav class="idx" aria-label="Sections">{nav}</nav><main>{sections}</main></div>
<footer class="src">This page is generated from {src}. The file is the source; if they disagree, the file wins. Edit the file and render again.</footer>
</div>{script}</body></html>
"""

THEME_JS = """<script>
(function(){var root=document.documentElement,K='design-md-theme';
function apply(t){if(t==='system'){root.removeAttribute('data-theme')}else{root.setAttribute('data-theme',t)}
document.querySelectorAll('.theme button').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.t===t))})}
var saved=null;try{saved=localStorage.getItem(K)}catch(e){}apply(saved||'system');
document.querySelectorAll('.theme button').forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.t);try{localStorage.setItem(K,b.dataset.t)}catch(e){}})})})();
</script>"""


# --------------------------------------------------------------------------
# ds: files for a claude.ai Design System page (Claude sessions)
# --------------------------------------------------------------------------

def token_name(kind, key):
    """The Design System page's token name for a DESIGN.md key. Colors keep their names."""
    key = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(key)).strip("-") or "x"
    if kind == "color":
        name = key
    elif kind == "type":
        name = key
    elif kind == "spacing":
        name = key if key.startswith("space") else f"space-{key}"
    else:
        name = key if key.startswith("radius") else f"radius-{key}"
    if not name[0].isalnum():
        name = "t" + name
    return name[:64]


def _bullets(md):
    items, cur = [], None
    for ln in md.splitlines():
        m = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", ln)
        if m:
            if cur:
                items.append(cur)
            cur = m.group(1).strip()
        elif cur is not None and ln.strip() and ln.startswith((" ", "\t")):
            cur += " " + ln.strip()
        else:
            if cur:
                items.append(cur)
            cur = None
    if cur:
        items.append(cur)
    return items


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def color_usage(doc, name):
    """A usage note from the prose: the bullet whose bold label names this token
    ("**Paper (`#FFFDF8`):** the page."), exact label first, then the name as a word in the label."""
    labelled = []
    for b in _bullets(doc["body"]):
        m = re.match(r"^\*\*([^*]+?)\*\*", b)
        if m:
            labelled.append((m.group(1), b))
    for label, b in labelled:
        if _norm(re.split(r"[(:,]", label)[0]) == _norm(name):
            return plain_text(b)
    word = re.compile(r"(?<![\w-])" + re.escape(name.lower()) + r"(?![\w-])")
    for label, b in labelled:
        if word.search(label.lower()):
            return plain_text(b)
    users = [f"{c} ({p.replace('Color', '')})" for c, comp in doc["components"].items() for p, v in comp.items()
             if ref_parts(v) == ("colors", name)]
    if users:
        return "Used by components: " + ", ".join(users) + "."
    return "Defined in DESIGN.md with no rule of its own; see the brand book."


def tokens_json(doc):
    themes = theme_ids(doc)
    seen = set()

    def unique(n):
        base, i = n, 2
        while n in seen:
            n = f"{base}-{i}"
            i += 1
        seen.add(n)
        return n

    color_tokens = []
    names = list(doc["colors"]) + [k for t in themes[1:] for k in doc["themes"].get(t, {}) if k not in doc["colors"]]
    for n in dict.fromkeys(names):
        value = {}
        for th in themes:
            v = color_in(doc, n, th) if n in doc["colors"] else doc["themes"].get(th, {}).get(n)
            if v is not None:
                value[th] = v
        color_tokens.append({"name": unique(token_name("color", n)),
                             "value": value if len(themes) > 1 else value.get("light"),
                             "usage": color_usage(doc, n)[:1000]})
    out = {"name": doc["name"], "version": 1,
           "color": {"themes": [{"id": t, "name": t.capitalize()} for t in themes], "tokens": color_tokens}}

    fams = families(doc)
    fam_key = {f: slug(f) for f in fams}
    groups = []
    for f in fams:
        styles = []
        for k, t in doc["typography"].items():
            if str(t.get("fontFamily") or "").strip() != f:
                continue
            st = {"name": token_name("type", k)}
            for src, dst in (("fontSize", "fontSize"), ("lineHeight", "lineHeight"), ("fontWeight", "fontWeight"),
                             ("letterSpacing", "letterSpacing"), ("fontStyle", "fontStyle")):
                if t.get(src) not in (None, ""):
                    st[dst] = t[src]
            users = [c for c, comp in doc["components"].items() if ref_parts(comp.get("typography")) == ("typography", k)]
            notes = (["Used by components: " + ", ".join(users) + "."] if users else []) + \
                ([f"Font features: {t['fontFeature']} (font-feature-settings)."] if t.get("fontFeature") else [])
            if notes:
                st["usage"] = " ".join(notes)
            st["sample"] = _sample_for(doc, k)[:200]
            styles.append(st)
        groups.append({"name": f, "family": fam_key[f], "styles": styles})
    out["type"] = {"fonts": [], "families": {fam_key[f]: stack(f) for f in fams}, "groups": groups}

    if doc["spacing"]:
        out["spacing"] = {"tokens": [{"name": unique(token_name("spacing", k)), "value": str(v),
                                      "usage": f"DESIGN.md spacing.{k}."} for k, v in doc["spacing"].items()]}
    if doc["rounded"]:
        out["radius"] = {"tokens": [{"name": unique(token_name("radius", k)), "value": str(v),
                                     "usage": f"DESIGN.md rounded.{k}."} for k, v in doc["rounded"].items()]}
    return out


def using_section(doc, groups=(), current_color=(), pages=()):
    """The generated `## Using this system` section: how to consume the page, from the tokens only.
    groups: asset group names; current_color: asset files drawn with currentColor; pages: example card names."""
    themes = theme_ids(doc)
    lines = ["## Using this system", ""]
    if len(themes) > 1:
        lines.append("- Themes: " + ", ".join(f"`{t}`" for t in themes) + f". The first, `{themes[0]}`, is the "
                     "fallback: a color a later theme does not set keeps its first-theme value.")
    else:
        lines.append(f"- One theme, `{themes[0]}`.")
    ons = [n for n in doc["colors"] if n.startswith("on-") and n[3:] in doc["colors"]]
    if ons:
        lines.append(f"- A token named `on-<fill>` is the text color on a fill of that name (`{ons[0]}` on "
                     f"`{ons[0][3:]}`). Never put plain white or black text on a fill.")
    if doc["typography"]:
        lines.append("- Type: put the type style's class on the element (" +
                     ", ".join(f"`.{token_name('type', k)}`" for k in list(doc["typography"])[:4]) + ").")
    specs = bundle_specs(doc)
    if specs:
        ns = namespace(doc)
        lines.append(f"- Components are `window.{ns}` in `components/bundle.js` (" +
                     ", ".join(f"`{ns}.{c}`" for c in list(specs)[:4]) + (", ..." if len(specs) > 4 else "") +
                     "), styled by `components/bundle.css`. They need React 18 on the page. They take "
                     "`className`, `children` (not a rule or an input) and, when DESIGN.md has states, `state`.")
    if groups:
        lines.append("- Asset groups: " + ", ".join(groups) + ". Use the files as they are; never redraw them.")
    if current_color:
        lines.append("- Single-ink SVG icons draw with `currentColor`: inline them to take the text color. "
                     "In an `<img>` they show black.")
    if pages:
        lines.append("- Examples (" + ", ".join(pages) + ") are this business's own pages, shown as they are.")
    lines.append("- DESIGN.md is the source. Change it there and build this page again.")
    return "\n".join(lines) + "\n"


def ds_readme(doc, groups=(), current_color=(), pages=()):
    head = ("> Generated from this business's `knowledge/DESIGN.md`. That file is the source: "
            "change it there and build this page again. Never edit this page as the source. "
            "If the page and the file disagree, the file wins.\n\n")
    parts = [head]
    if doc["intro"]:
        parts.append(doc["intro"].strip() + "\n\n")
    elif doc["description"]:
        parts.append(doc["description"] + "\n\n")
    for title, text in doc["sections"]:
        parts.append(f"## {title}\n\n{text.strip()}\n\n")
    if not any(_norm(t) == _norm("Using this system") for t, _ in doc["sections"]):
        parts.append(using_section(doc, groups, current_color, pages))
    return "".join(parts).rstrip() + "\n"


def asset_note(doc, group):
    """The prose section that describes an asset group: an exact name first ("Logos" or "Logo"), then a
    section whose title shares a 4+ letter stem with the group ("Icons" and "Iconography")."""
    g = _norm(group)
    exact = (g, _norm(group.rstrip("sS")))
    for title, text in doc["sections"]:
        if _norm(title) in exact:
            return text
    stem = _norm(group.rstrip("sS"))
    for title, text in doc["sections"]:
        words = re.findall(r"[A-Za-z0-9]+", title)
        if not words:
            continue
        w = _norm(words[0])
        n = 0
        while n < min(len(w), len(stem)) and w[n] == stem[n]:
            n += 1
        if n >= 4 and n >= min(len(w), len(stem)) - 2:
            return text
    return None


def uses_current_color(path):
    p = Path(path)
    if p.suffix.lower() != ".svg":
        return False
    try:
        return "currentcolor" in p.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


# --------------------------------------------------------------------------
# Example pages: a business's own HTML, shown as a showcase card
# --------------------------------------------------------------------------

PAGE_MARKER = '<!-- @dsCard group="Examples" height={height} page -->'
PAGE_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
PAGE_TAGS = re.compile(r"<\s*(iframe|frame|object|embed|portal|noscript)\b", re.I)
DS_MARKER = re.compile(r"\A\s*<!--\s*@dsCard\b.*?-->[ \t]*\n?", re.S)


def check_page_html(text):
    """Problems that keep a page off the Design System page (empty list = fine)."""
    out = []
    for m in PAGE_TAGS.finditer(text):
        out.append(f"<{m.group(1).lower()}> is not allowed in a card")
    refs = re.findall(r"""\b(?:src|href)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", text, re.I)
    refs = [a or b or c for a, b, c in refs]
    refs += re.findall(r"""url\(\s*['"]?([^'")\s]+)""", text, re.I)
    refs += re.findall(r"""@import\s+['"]([^'"]+)""", text, re.I)
    for ref in refs:
        r = ref.strip()
        low = r.lower()
        if low.startswith("javascript:"):
            out.append(f"{r}: javascript: links are not allowed")
            continue
        m = re.match(r"^(?:https?:)?//([^/:?#]+)", r, re.I)
        if m:
            if m.group(1).lower() not in PAGE_HOSTS:
                out.append(f"{r}: only Google Fonts may load from another host")
        elif re.match(r"^[a-z][a-z0-9+.-]*:", low) and not low.startswith(("data:", "mailto:", "tel:")):
            out.append(f"{r}: only relative paths, Google Fonts, data:, mailto: and tel: are allowed")
    for m in re.finditer(r"<\s*script\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+)", text, re.I):
        if re.match(r"^([a-z][a-z0-9+.-]*:|//)", m.group(1), re.I):
            out.append(f"<script src={m.group(1)}>: a script may load only by a relative path")
    return list(dict.fromkeys(out))


def parse_pages(specs):
    """--page NAME=FILE.html → [(Comp, path)]. NAME must be a JS identifier; the card folder is its PascalCase."""
    pages = []
    for spec in specs:
        name, sep, path = spec.partition("=")
        if not sep or not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name or ""):
            raise ValueError(f"--page wants NAME=FILE.html with NAME a JS identifier, got {spec!r}")
        p = Path(path)
        if not p.is_file() or p.suffix.lower() not in (".html", ".htm"):
            raise ValueError(f"--page: {path} is not an .html file")
        comp = pascal(name)
        if comp in [c for c, _ in pages]:
            raise ValueError(f"--page: {comp} is named twice")
        pages.append((comp, str(p)))
    return pages


def page_card(comp, path, height=560):
    """(preview.html, README.md) for one example page. Raises ValueError when the page breaks the card rules."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    problems = check_page_html(text)
    if problems:
        raise ValueError(f"--page {p.name}: " + "; ".join(problems))
    text = DS_MARKER.sub("", text, count=1).lstrip()
    m = re.search(r"""<meta\s+name=["']ds-height["']\s+content=["'](\d+)["']""", text, re.I)
    h = int(m.group(1)) if m else int(height)
    h = max(40, min(4000, h))
    md = p.with_suffix(".md")
    if md.is_file():
        readme = md.read_text(encoding="utf-8").rstrip() + "\n"
    else:
        readme = (f"# {comp}\n\nAn example page from this business's own work (`{p.name}`), shown as it is. "
                  "It is not a component. Change the page in its own repo and build again, not here.\n")
    return PAGE_MARKER.format(height=h) + "\n" + text, readme


def _on_ground(doc, props):
    r = roles(doc)
    return bool(props.get("backgroundColor") and r["ground"]
                and ref_parts(props["backgroundColor"]) == ("colors", r["ground"]))


def preview_html(doc, base, states):
    """The component's card. Static samples first (they need only tokens.css); when the frame has React and
    the bundle, one script renders the same states through window.<namespace> in their place."""
    r = roles(doc)
    tr = type_roles(doc)
    ns = namespace(doc)
    comp = pascal(base)
    kind = comp_element(base, states[0][2])[1]
    label = humanize(base)
    cap_family = slug(family_of(doc, tr["body"])) if tr["body"] else None
    samples, figs = [], []
    for state, name, props in states:
        css, cls = _comp_style(doc, props, preview=True)
        edge = _on_ground(doc, props)
        if edge:
            css += f"outline:1px solid var(--{r['rule']});"
        wide = not props.get("height") and props.get("backgroundColor")
        el_cls = ("el " + cls).strip()
        wide_cls = " wide" if wide else ""
        samples.append(f'<figure class="s{wide_cls}"><div class="{el_cls}" style="{html.escape(css)}">'
                       f'{"" if is_rule(props) else html.escape(label)}</div><figcaption>{html.escape(state)}</figcaption></figure>')
        p = {"className": "el edge" if edge else "el"}
        if state != "default":
            p["state"] = state
        if kind == "input":
            p.update({"placeholder": label, "aria-label": label})
        kids = "" if kind in ("rule", "input") else "," + js_str(label)
        figs.append(f'h("figure",{{className:{js_str("s" + wide_cls)}}},h(N.{comp},{js_json(p)}{kids}),'
                    f'h("figcaption",null,{js_str(state)}))')
    height = 140 if any(not p.get("height") and p.get("backgroundColor") for _, _, p in states) else 112
    ground = f"var(--{r['ground']})" if r["ground"] else "#ffffff"
    ink = f"var(--{r['ink']})" if r["ink"] else "#111111"
    muted = f"var(--{r['muted']})" if r["muted"] else ink
    rule = f"var(--{r['rule']})" if r["rule"] else muted
    capfont = f"var(--font-{cap_family})" if cap_family else "system-ui, sans-serif"
    script = ("<script>\n(function(){var N=window." + ns + ",R=window.React,D=window.ReactDOM;\n"
              "if(!N||!N." + comp + "||!R||!D||!D.createRoot){return}\nvar h=R.createElement;\n"
              "D.createRoot(document.getElementById(\"root\")).render(h(R.Fragment,null,\n"
              + ",\n".join(figs) + "));\n})();\n</script>\n")
    return (f'<!-- @dsCard group="Components" height={height} -->\n<!doctype html>\n<html lang="en">\n<head>\n'
            f'<meta charset="utf-8">\n<title>{html.escape(label)}</title>\n<style>\n'
            f"/* Generated from DESIGN.md components.{base}. Edit the file, not this preview. */\n"
            f"html,body{{margin:0}}body{{background:{ground};color:{ink};padding:16px;font-family:{capfont}}}\n"
            ".row{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}\n"
            ".s{margin:0;display:grid;gap:6px;justify-items:start}.s.wide{flex:1 1 100%;justify-items:stretch}\n"
            ".el{display:inline-flex;align-items:center;box-sizing:border-box}.s.wide .el{display:flex;min-height:72px}\n"
            f".edge{{outline:1px solid {rule}}}\n"
            f"figcaption{{font:12px/1.4 {capfont};color:{muted}}}\n"
            f'</style>\n</head>\n<body>\n<div class="row" id="root">{"".join(samples)}</div>\n{script}</body>\n</html>\n')


# --------------------------------------------------------------------------
# The component bundle: one React export per base component (no build step)
# --------------------------------------------------------------------------

REACT_VERSION = "18.3.1"
REACT_LIBS = (("react", "React", "react.production.min.js"), ("react-dom", "ReactDOM", "react-dom.production.min.js"))
STATE_SELECTORS = {"hover": [":hover"], "focus": [":focus-visible"], "active": [":active"],
                   "pressed": ['[aria-pressed="true"]'], "disabled": [":disabled", '[aria-disabled="true"]'],
                   "selected": ['[aria-selected="true"]']}
# Zero-specificity resets (:where), so the type class from tokens.css still sets the font.
ELEMENT_RESET = {
    "button": "font:inherit;border:0;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box",
    "input": "font:inherit;border:0;box-sizing:border-box",
    "rule": "display:block;border:0;margin:0",
    "div": "box-sizing:border-box", "nav": "box-sizing:border-box",
}
DTS_ATTRS = {"button": "React.ButtonHTMLAttributes<HTMLButtonElement>", "link": "React.AnchorHTMLAttributes<HTMLAnchorElement>",
             "input": "React.InputHTMLAttributes<HTMLInputElement>", "rule": "React.HTMLAttributes<HTMLDivElement>",
             "nav": "React.HTMLAttributes<HTMLElement>", "div": "React.HTMLAttributes<HTMLDivElement>"}


def namespace(doc):
    return pascal(doc["name"] or "Design")


def js_str(s):
    """A JS string literal that is safe inside an inline <script>."""
    return js_json(str(s))


def js_json(v):
    return json.dumps(v, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e")


def comp_element(base, props):
    """(tag, kind) for a component's React export, picked from its name. A rule (4px or less) comes first."""
    n = base.lower()
    if is_rule(props):
        return "div", "rule"
    if "button" in n:
        return "button", "button"
    if "link" in n:
        return "a", "link"
    if "input" in n or "field" in n:
        return "input", "input"
    if any(w.startswith("nav") for w in re.split(r"[^a-z0-9]+", n)):
        return "nav", "nav"
    return "div", "div"


def comp_class(doc, base):
    return f"{slug(namespace(doc))}-{slug(base)}"


def _decls(css):
    return [d.strip() for d in css.split(";") if d.strip()]


def bundle_specs(doc):
    """{Comp: {tag, cls, kind, states, type: {state: type class}}} in file order."""
    specs = {}
    for base, states in component_groups(doc).items():
        tag, kind = comp_element(base, states[0][2])
        specs[pascal(base)] = {
            "base": base, "tag": tag, "kind": kind, "cls": comp_class(doc, base),
            "states": [s for s, _, _ in states[1:]],
            "type": {s: _comp_style(doc, p, preview=True)[1] for s, _, p in states},
        }
    return specs


def bundle_js(doc):
    ns = namespace(doc)
    specs = bundle_specs(doc)
    header = {"format": 4, "namespace": ns, "components": [{"name": c} for c in specs]}
    table = {c: {"tag": s["tag"], "cls": s["cls"], "states": s["states"], "type": s["type"],
                 "rule": s["kind"] == "rule", "empty": s["kind"] in ("rule", "input")} for c, s in specs.items()}
    return ("/* @ds-bundle: " + json.dumps(header, separators=(",", ":")) + " */\n"
            "/* Generated from DESIGN.md components by the marketing toolkit's design_md.py. "
            "Edit DESIGN.md and build again; never edit this file. */\n"
            "(function () {\n"
            "  \"use strict\";\n"
            "  var SPECS = " + js_json(table) + ";\n"
            "  var own = Object.prototype.hasOwnProperty;\n"
            "  function make(name, s) {\n"
            "    function C(props) {\n"
            "      var R = window.React, p = {}, k;\n"
            "      props = props || {};\n"
            "      for (k in props) {\n"
            "        if (own.call(props, k) && k !== \"children\" && k !== \"className\" && k !== \"state\") { p[k] = props[k]; }\n"
            "      }\n"
            "      var st = s.states.indexOf(props.state) >= 0 ? props.state : null;\n"
            "      var type = st && own.call(s.type, st) ? s.type[st] : s.type[\"default\"];\n"
            "      p.className = [s.cls, type, st ? \"is-\" + st : \"\", props.className].filter(Boolean).join(\" \");\n"
            "      if (s.tag === \"button\" && p.type === undefined) { p.type = \"button\"; }\n"
            "      if (s.rule && p.role === undefined) { p.role = \"separator\"; }\n"
            "      if (s.empty) { return R.createElement(s.tag, p); }\n"
            "      return R.createElement(s.tag, p, props.children);\n"
            "    }\n"
            "    C.displayName = name;\n"
            "    return C;\n"
            "  }\n"
            "  var ns = window." + ns + " = window." + ns + " || {};\n"
            "  for (var n in SPECS) { if (own.call(SPECS, n)) { ns[n] = make(n, SPECS[n]); } }\n"
            "})();\n")


def bundle_css(doc):
    out = ["/* Generated from DESIGN.md components by the marketing toolkit's design_md.py. Edit DESIGN.md, "
           "not this file. Colors and sizes are tokens.css variables; type is the type class on the element. */"]
    groups = component_groups(doc)
    for comp, spec in bundle_specs(doc).items():
        states = groups[spec["base"]]
        cls = spec["cls"]
        reset = ELEMENT_RESET.get(spec["kind"])
        if reset:
            out.append(f":where(.{cls}){{{reset}}}")
        base_css, _ = _comp_style(doc, states[0][2], preview=True)
        base_decls = _decls(base_css)
        out.append(f".{cls}{{{';'.join(base_decls)}}}")
        for state, name, props in states[1:]:
            diff = [d for d in _decls(_comp_style(doc, props, preview=True)[0]) if d not in base_decls]
            sels = [f".{cls}{s}" for s in STATE_SELECTORS.get(state, [])] + [f".{cls}.is-{state}"]
            out.append(",".join(sels) + "{" + (";".join(diff) if diff else "/* same tokens as the default */") + "}")
    return "\n".join(out) + "\n"


def index_dts(doc):
    ns = namespace(doc)
    specs = bundle_specs(doc)
    lines = ["// Generated from DESIGN.md components by the marketing toolkit's design_md.py. Documentation, not type-checked.",
             "import type * as React from 'react';"]
    for comp, s in specs.items():
        state = " | ".join(js_str(x) for x in s["states"])
        extra = (f" state?: {state};" if state else "")
        kids = "" if s["kind"] in ("rule", "input") else " children?: React.ReactNode;"
        lines.append(f"/** DESIGN.md components.{s['base']}: a <{s['tag']}> with class {s['cls']}. */")
        lines.append(f"export interface {comp}Props extends {DTS_ATTRS[s['kind']]} {{{kids} className?: string;{extra} }}")
        lines.append(f"export declare function {comp}(props: {comp}Props): React.ReactElement;")
    members = "; ".join(f"{c}: typeof {c}" for c in specs)
    lines.append(f"declare global {{ interface Window {{ {ns}: {{ {members} }} }} }}")
    return "\n".join(lines) + "\n"


def libraries(react_lib=None):
    """The index `libraries`: React 18 for the previews. With react_lib, the files are packed in components/lib/."""
    out = []
    for name, glob, fname in REACT_LIBS:
        lib = {"name": name, "version": REACT_VERSION, "global": glob}
        if react_lib:
            lib["file"] = f"components/lib/{fname}"
        out.append(lib)
    return out


def component_readme(doc, base, states):
    lines = [f"# {pascal(base)}", ""]
    props = states[0][2]
    desc = []
    for p, v in props.items():
        parts = ref_parts(v)
        label = {"backgroundColor": "background", "textColor": "text", "typography": "type", "rounded": "corners",
                 "borderColor": "border"}.get(p, p)
        if parts and parts[0] == "colors":
            desc.append(f"{label} `{parts[1]}`")
        elif parts and parts[0] == "typography":
            desc.append(f"{label} `{parts[1]}`")
        elif parts and parts[0] == "rounded":
            desc.append(f"{label} `{token_name('radius', parts[1])}`")
        else:
            desc.append(f"{label} {v}")
    lines.append(f"{humanize(base)} as DESIGN.md defines it (`components.{base}`): " + ", ".join(desc) + ".")
    for state, name, p in states[1:]:
        ch = ", ".join(f"{k.replace('Color', '')} `{ref_parts(v)[1] if ref_parts(v) else v}`" for k, v in p.items()
                       if props.get(k) != v)
        lines.append(f"\n**{state.capitalize()}** (`components.{name}`): {ch or 'same tokens'}.")
    bg, fg = props.get("backgroundColor"), props.get("textColor")
    if bg and fg:
        ratios = []
        for th in theme_ids(doc):
            c = contrast(resolve(doc, fg, th), resolve(doc, bg, th))
            if c is not None:
                ratios.append(f"{c:.1f}:1 {th}" + (" (under 4.5:1)" if c < 4.5 else ""))
        if ratios:
            lines.append("\nText on its background: " + ", ".join(ratios) + ".")
    tag, kind = comp_element(base, props)
    use = ["`className`"] + ([] if kind in ("rule", "input") else ["`children`"])
    if len(states) > 1:
        use.append("`state` (" + ", ".join(f'`"{s}"`' for s, _, _ in states[1:]) + ")")
    lines.append(f"\nUse it: `{namespace(doc)}.{pascal(base)}`, a `<{tag}>`. Props: " + ", ".join(use)
                 + f", and any `<{tag}>` attribute.")
    lines.append("\nThe consumer provides the label or content. When and how to use it: the brand book, "
                 "section Components. Change it in DESIGN.md, not here.")
    return "\n".join(lines) + "\n"


def _visible(doc, name, ground, floor=1.25):
    for th in theme_ids(doc):
        c = contrast(color_in(doc, name, th), color_in(doc, ground, th) if ground else "#ffffff")
        if c is None or c < floor:
            return False
    return True


def cover_html(doc, name_logo=None):
    """The cover. name_logo: {theme: svg}; when given, the logo stands where the name would be typed."""
    r = roles(doc)
    g = r["ground"]
    text_roles = {r["ink"], r["muted"]}
    cols = [n for n in doc["colors"] if n != g and n not in text_roles and not n.startswith("on-")]
    pick = lambda cands: next((c for c in cands if c in doc["colors"] and c != g and _visible(doc, c, g)), None)
    brand = pick(["primary", "brand", "accent"] + cols)
    accent = pick(["tertiary", "secondary", "accent"] + [c for c in cols if c != brand])
    by_dark = sorted(cols, key=lambda n: luminance(doc["colors"][n]) if luminance(doc["colors"][n]) is not None else 9)
    deep = pick([c for c in by_dark if c not in (brand, accent)])
    tints = [c for c in reversed(by_dark) if c not in (brand, accent, deep)]
    tint = pick(tints) or next((c for c in tints if _visible(doc, c, g, 1.08)), None)
    radii = [(k, str(v)) for k, v in doc["rounded"].items()]
    px = lambda v: float(re.match(r"([\d.]+)", v).group(1)) if re.match(r"([\d.]+)", v) else 0.0
    square = all(px(v) == 0 for _, v in radii) if radii else True
    rad = token_name("radius", min(radii, key=lambda kv: px(kv[1]))[0]) if radii else None
    tr = type_roles(doc)
    disp = family_of(doc, tr["display"])
    fam_var = f"var(--font-{slug(disp)})" if disp else "system-ui, sans-serif"
    bodyf = family_of(doc, tr["body"])
    tag_var = f"var(--font-{slug(bodyf)})" if bodyf else "system-ui, sans-serif"
    name = doc["name"] or "Design"
    per = 0.55 if fallback_for(disp).endswith("serif") and "sans" not in fallback_for(disp) else 0.6
    longest = len(name) if len(name) * per * 64 <= 440 else max(len(p) for p in name.split(" "))
    size = 120
    while size > 64 and longest * per * size > 440:
        size -= 4
    lines = 1 if len(name) * per * size <= 440 else 2
    tagline = overview_sentence(doc)
    blocks = []
    if brand:
        blocks.append(f'<rect class="b-brand blk" x="16" y="-16" width="144" height="240"/>')
    if tint:
        blocks.append(f'<rect class="b-tint blk" x="176" y="80" width="144" height="184"/>')
    if deep:
        blocks.append(f'<rect class="b-deep blk" x="336" y="48" width="160" height="216"/>')
    if accent:
        blocks.append(f'<rect class="b-accent blk" x="16" y="240" width="64" height="24"/>')
    if square:
        pattern = "".join(f'<line class="rule" x1="16" x2="496" y1="{y}" y2="{y}"/>' for y in (120, 144, 168, 192))
        row = "editorial, square corners (every rounded token is 0) → a few hairline rules cut across the blocks in the ground"
    else:
        pattern = "".join(f'<rect class="pill" x="{x}" y="{y}" width="{w}" height="8"/>'
                          for x, y, w in ((192, 240, 40), (248, 240, 24), (280, 240, 24), (208, 216, 24), (248, 216, 48)))
        row = "rounded corners in the rounded tokens → pills over the tint"
    css = [f".b-{k}{{fill:var(--{v})}}" for k, v in (("brand", brand), ("tint", tint), ("deep", deep), ("accent", accent)) if v]
    css.append(f".blk{{rx:var(--{rad})}}" if rad else ".blk{rx:0}")
    css.append(f".rule{{stroke:var(--{g});stroke-width:1}}" if g else ".rule{stroke:#fff;stroke-width:1}")
    css.append(f".pill{{fill:var(--{brand or deep});rx:4px}}")
    derivation = (f"blocks      {brand} 144x240 off the top · {tint} 144x184 · {deep} 160x216 off the right · {accent} 64x24\n"
                  f"  arrangement one tall slab with satellites, bottoms on one line\n"
                  f"  pattern     {row}\n"
                  f"  scales      corners {rad or 'none'}; generated by design_md.py from DESIGN.md tokens only")
    ground = f"var(--{g})" if g else "#ffffff"
    ink = f"var(--{r['ink']})" if r["ink"] else "#111111"
    muted = f"var(--{r['muted']})" if r["muted"] else ink
    mark, mark_css = name_logo_html(doc, name_logo)
    if mark:
        mark_css += "\n.name .mark svg{width:440px;max-width:100%;height:auto;max-height:150px}"
        derivation += "\n  name        the logo file (--name-logo), not the name typed in a font"
    return f"""<!-- @dsCard height=288 -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(name)}</title>
<style>
html,body{{margin:0;height:100%}}
body{{background:{ground};color:{ink};overflow:hidden}}
.cover{{position:relative;height:288px;overflow:hidden}}
.art{{position:absolute;top:0;left:480px;width:480px;height:288px;overflow:hidden}}
.art svg{{display:block;width:480px;height:288px}}
{chr(10).join(css)}
.words{{position:absolute;left:32px;bottom:32px;max-width:440px}}
.name{{margin:0;{feature_css(doc["typography"].get(tr["display"]) or {})}font-family:{fam_var};font-size:{size}px;line-height:{'.95' if lines > 1 else '.92'};font-weight:400;color:{ink}}}
{mark_css}
.tag{{margin:10px 0 0 2px;font-family:{tag_var};font-size:14px;line-height:20px;color:{muted}}}
</style>
</head>
<body>
<div class="cover">
<div class="art" aria-hidden="true">
<svg viewBox="0 0 480 288" width="480" height="288">
<!--
  {derivation}
-->
{''.join(blocks)}
{pattern}
</svg>
</div>
<div class="words"><h1 class="name">{mark or html.escape(name)}</h1><p class="tag">{html.escape(tagline)}</p></div>
</div>
</body>
</html>
"""


def ds_index(doc, now, by="Claude", via="Claude Code", react_lib=None):
    """A NEW index. On a revision, read the live one and keep its keys instead."""
    return {"v": 3, "layout": "files", "createdOnFiles": {"v": 1, "at": now}, "title": doc["name"],
            "namespace": namespace(doc),
            "libraries": libraries(react_lib) if doc["components"] else [],
            "sections": {}, "groups": [], "assetGroups": {}, "blobs": {},
            "docs": {"readme": "project/README.md", "sections": []},
            "lastChange": {"by": by, "at": now, "via": via, "note": "Generated from knowledge/DESIGN.md"}}


UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".webm", ".pdf"}


def build_ds(doc, out_dir, assets=(), now=None, by="Claude", name_logo=None, pages=(), page_height=560,
             react_lib=None):
    """Write <out_dir>/project/... and <out_dir>/publish.json. Returns the publish plan.
    pages: [(Comp, file.html)] example pages; react_lib: a folder holding the React 18 UMD builds to pack."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    out = Path(out_dir)
    groups = component_groups(doc)
    taken = {pascal(b) for b in groups} | {"Cover"}
    cards = []
    for comp, path in pages:
        if comp in taken:
            raise ValueError(f"--page {comp}: that name is already a component or the cover")
        taken.add(comp)
        cards.append((comp, page_card(comp, path, page_height)))
    if react_lib:
        missing = [f for _, _, f in REACT_LIBS if not (Path(react_lib) / f).is_file()]
        if missing:
            raise ValueError(f"--react-lib {react_lib}: missing " + ", ".join(missing))
    proj = out / "project"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    written = {}

    def put(rel, text):
        p = proj / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        written[f"project/{rel}"] = str(p)

    put("tokens.json", json.dumps(tokens_json(doc), indent=2) + "\n")
    for base, states in groups.items():
        comp = pascal(base)
        put(f"components/{comp}/preview.html", preview_html(doc, base, states))
        put(f"components/{comp}/README.md", component_readme(doc, base, states))
    if groups:
        put("components/bundle.js", bundle_js(doc))
        put("components/bundle.css", bundle_css(doc))
        put("components/index.d.ts", index_dts(doc))
        if react_lib:
            for _, _, fname in REACT_LIBS:
                dest = proj / "components" / "lib" / fname
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(react_lib) / fname, dest)
                written[f"project/components/lib/{fname}"] = str(dest)
    put("components/Cover/preview.html", cover_html(doc, name_logo))
    for comp, (preview, readme) in cards:
        put(f"components/{comp}/preview.html", preview)
        put(f"components/{comp}/README.md", readme)

    uploads, current = [], []
    for group, src in assets:
        src = Path(src)
        files = sorted(p for p in (src.rglob("*") if src.is_dir() else [src]) if p.is_file() and not p.name.startswith("."))
        gdir = proj / "assets" / group
        gdir.mkdir(parents=True, exist_ok=True)
        for f in files:
            rel = f.relative_to(src) if src.is_dir() else Path(f.name)
            dest = gdir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
            if f.suffix.lower() in UPLOAD_EXT:
                uploads.append({"group": group, "name": str(rel), "path": str(dest),
                                "type": mimetypes.guess_type(f.name)[0] or "application/octet-stream",
                                "size": dest.stat().st_size})
            else:
                written[f"project/assets/{group}/{rel}"] = str(dest)
        note = asset_note(doc, group)
        readme = (f"# {group}\n\n" + (note.strip() if note else
                  f"Files copied from the business's repo. Use them as they are; never redraw them.") + "\n")
        inked = [str(f.relative_to(src) if src.is_dir() else Path(f.name)) for f in files if uses_current_color(f)]
        current += inked
        if inked:
            ink = roles(doc)["ink"]
            readme += ("\nDrawn in one ink with `currentColor`: " + ", ".join(f"`{x}`" for x in inked) + ". Inline "
                       "them to take the text color" + (f" (`{ink}` on the page)" if ink else "") +
                       "; in an `<img>` they show black.\n")
        put(f"assets/{group}/README.md", readme)
    put("README.md", ds_readme(doc, [g for g, _ in assets], current, [c for c, _ in cards]))

    index = ds_index(doc, now, by=by, react_lib=react_lib)
    index["groups"] = [g for g, _ in assets]
    index["assetGroups"] = {g: {"name": g, "tile": "l", "order": [u["name"] for u in uploads if u["group"] == g], "files": {}}
                            for g, _ in assets}
    (proj / "design-system.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    plan = {"root": str(out.resolve()), "file_path": str((proj / "design-system.json").resolve()),
            "files": {k: k for k in written}, "uploads": uploads,
            "note": ("New page: send file_path + files in ONE Artifact publish (root as given). Uploads go first "
                     "(asset: true), then fill index.assetGroups.<Group>.files.<name> = {name, blob, size, type}. "
                     "Revision: read the live index first and send it only last, keeping its keys.")}
    (out / "publish.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="lint DESIGN.md")
    c.add_argument("design")
    r = sub.add_parser("render", help="write one self-contained HTML view")
    r.add_argument("design")
    r.add_argument("-o", "--out", help="output .html (default: DESIGN.html beside the file)")
    r.add_argument("--logo", action="append", default=[], metavar="FILE",
                   help="a logo file (svg/png) to show in the Logo section. Repeatable.")
    r.add_argument("--name-logo", action="append", default=[], metavar="[THEME=]FILE.svg",
                   help="the logo that stands for the name in headers (the view's title, the cover), "
                        "per theme: dark=FILE for dark mode. Repeatable.")
    r.add_argument("--icon", action="append", default=[], metavar="FILE_OR_DIR",
                   help="an icon file, or a folder of them, to show in the Iconography section. Repeatable.")
    d = sub.add_parser("ds", help="write the files for a claude.ai Design System page")
    d.add_argument("design")
    d.add_argument("-o", "--out", required=True, help="output folder (gets project/ and publish.json)")
    d.add_argument("--asset", action="append", default=[], metavar="GROUP=PATH",
                   help="copy a file or folder into assets/GROUP (logos, icons). Repeatable.")
    d.add_argument("--by", default="Claude", help="the person this is built for (index lastChange.by)")
    d.add_argument("--name-logo", action="append", default=[], metavar="[THEME=]FILE.svg",
                   help="the logo that stands for the name in headers (the view's title, the cover), "
                        "per theme: dark=FILE for dark mode. Repeatable.")
    d.add_argument("--page", action="append", default=[], metavar="NAME=FILE.html",
                   help="one of the business's own pages, shown as an example card (group Examples). "
                        "NAME is a JS identifier. A FILE.md beside it becomes the card's README. Repeatable.")
    d.add_argument("--page-height", type=int, default=560, metavar="N",
                   help="example card height in px when the page has no <meta name=\"ds-height\"> (default 560)")
    d.add_argument("--react-lib", metavar="DIR",
                   help="a folder with react.production.min.js and react-dom.production.min.js (18.3.1) to pack "
                        "into components/lib/. Without it the page loads React 18 from jsDelivr.")
    a = ap.parse_args(argv)

    doc = load(a.design)
    issues = check(doc)
    errors = [m for lvl, m in issues if lvl == "error"]
    if a.cmd == "check":
        for lvl, m in issues:
            print(f"{lvl}: {m}")
        print("ok" if not issues else f"{len(errors)} error(s), {len(issues) - len(errors)} warning(s)")
        return 1 if errors else 0
    if errors:
        for m in errors:
            print(f"error: {m}", file=sys.stderr)
        return 1
    try:
        marks = parse_name_logo(doc, a.name_logo)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.cmd == "render":
        out = Path(a.out) if a.out else Path(a.design).with_name("DESIGN.html")
        try:
            page = render_html(doc, a.logo, marks, expand_files(a.icon, ICON_EXT))
        except ValueError as e:
            print(f"error: --icon: {e}", file=sys.stderr)
            return 2
        out.write_text(page, encoding="utf-8")
        print("wrote", out)
        return 0
    assets = []
    for spec in a.asset:
        group, _, path = spec.partition("=")
        if not group or not path or not re.fullmatch(r"[A-Za-z0-9 _-]+", group):
            print(f"error: --asset wants GROUP=PATH, got {spec!r}", file=sys.stderr)
            return 2
        assets.append((group, path))
    try:
        pages = parse_pages(a.page)
        plan = build_ds(doc, a.out, assets, by=a.by, name_logo=marks, pages=pages, page_height=a.page_height,
                        react_lib=a.react_lib)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"wrote {len(plan['files']) + 1} files under {Path(a.out) / 'project'}; "
          f"{len(plan['uploads'])} upload(s); plan: {Path(a.out) / 'publish.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
