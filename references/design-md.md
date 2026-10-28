# DESIGN.md: the brand source, and its two views

Every business that uses this toolkit keeps its visual system in one file:
`knowledge/DESIGN.md` in its own marketing repo. That file is the source of
truth. Two views are built from it. Neither view is ever the source.

| What | Who builds it | Who can read it |
|---|---|---|
| `knowledge/DESIGN.md` | The owner, with any agent | Every agent and person with the repo |
| Local HTML view (`design_md.py render`), committed in the marketing repo | Any agent, any model | Everyone with access to the business's marketing repo, by default |
| claude.ai Design System page (`design_md.py ds` + Artifact tool) | Claude sessions only | Claude Code sessions and claude.ai on the owner's account. Nobody else, in or outside the org, until the owner shares it. Never pi or Grok, Cursor, Codex, scripts or CI |

So **every agent reads DESIGN.md itself**, never only a view. If a view and
the file disagree, the file wins: fix the file, then build the view again.
No fact may live only in a view.

## 1. The file

Google DESIGN.md format (spec alpha): YAML tokens in the frontmatter, rules
in the prose below. Start from `templates/DESIGN.md`.

- **Tokens:** `name`, `description`, `colors` (name: hex), `typography`
  (name: fontFamily, fontSize, fontWeight, lineHeight, letterSpacing),
  `rounded`, `spacing`, `components` (properties that point at tokens:
  `"{colors.primary}"`, `"{typography.button}"`, `"{rounded.sm}"`).
- **Type features:** `fontFeature: "lnum"` (or `"lnum, tnum"`) on a type
  token sets lining or tabular figures in every view.
- **Rules as components:** a component 4px tall or less (a 1px gold rule)
  shows as a bar, not a label.
- **State variants:** name them `<component>-hover`, `-active`, `-pressed`,
  `-focus`, `-disabled` or `-selected`. A variant lists only what changes;
  the views fold it into its base component.
- **Toolkit extensions** (optional, the spec ignores them):
  - `themes.<id>`: the same color names, redefined for another theme
    (`themes.dark`). Anything not listed keeps its light value.
  - `design_system_url`: the claude.ai page built from this file (step 3).
- **Prose sections**, in this order when they apply: Overview, Colors,
  Typography, Layout, Elevation & Depth, Shapes, Components, Do's and
  Don'ts. Add others (Logo, Photography, Voice) as the brand needs.
- **One rule per color token.** In Colors, write each role as a bullet whose
  bold label starts with the token name: `- **Primary (#9C2F1E):** the one
  button.` The Design System page lifts that bullet as the token's usage
  note. A token with no such bullet gets a generic note.
- **A component that must not change in dark mode** points at a token that
  does not change (`on-night`), not at one that flips (`paper`).
  `design_md.py check` warns when text on a component falls under 4.5:1 in
  any theme.

**Missing file:** copy the template to `knowledge/DESIGN.md`, ask the owner
the DESIGN.md questions in `mkt-kit/REFERENCE.md`, and log the answers in
`knowledge/_intake-log.md`. Take values from the live site's CSS or a brand
guide. Never invent a brand fact: leave a value blank before you guess it.
`brand-identity.md` is an optional flat twin for older skills; if both
exist, DESIGN.md wins.

## 2. The script

`scripts/design_md.py` in this toolkit. Python standard library only (it
uses PyYAML if installed). It holds no brand values.

```bash
python3 <toolkit>/scripts/design_md.py check  knowledge/DESIGN.md
python3 <toolkit>/scripts/design_md.py render knowledge/DESIGN.md -o <out>.html [--logo <file> ...]
python3 <toolkit>/scripts/design_md.py ds     knowledge/DESIGN.md -o <scratch dir> \
        [--asset Logos=<folder or file>] [--by "<owner name>"] \
        [--name-logo <logo for light>.svg --name-logo dark=<logo for dark>.svg]
```

- `--name-logo` (render and ds): the logo file that stands for the name
  in a header (the view's title, the page's cover), one per theme. **When
  the business has a logo, always pass it.** A header shows the real logo
  file, never the name typed in a font: a font cannot match a mark that was
  drawn or kerned by hand. The name stays as plain text everywhere else
  (prose, notes, labels).

- `check`: errors (exit 1) for no frontmatter, a placeholder name, no colors
  or type, a component reference that does not resolve. Warnings for non-hex
  colors, blank font families, low contrast per theme.
- `render`: one self-contained HTML page (fonts from Google Fonts only).
  Swatches per theme with contrast, type specimens, spacing and radius
  scales, live component samples, then the prose. Optional logo tiles.
  Any agent can make it. **Its home is the business's marketing repo:**
  commit it beside DESIGN.md (default `brand/design-system.html`), so
  everyone with access to that repo sees it by default. Render it again in
  the same commit as any DESIGN.md change. Do not publish it anywhere else
  without the owner's yes. A business may keep its own richer renderer
  instead (its committed page is then the view); this one is the default.

## 3. The Design System page (Claude sessions)

One page per business, built only from that business's DESIGN.md. Never two
businesses in one page. Name it for the business. Private.

**First build**

1. `check` passes with no errors.
2. `ds` writes `<dir>/project/...` (tokens.json, README.md from the prose,
   one preview + README per component, a cover, a new index) and
   `<dir>/publish.json` (the files map and the uploads list).
3. Artifact tool: `action: "quickstart"`, `intent: "other"`, then publish
   with the Design System `type_url` from the quickstart result (today the
   core type https://claude.ai/artifact/5M7UeXXcx16TP3vzVFNDzd), `title` =
   the business name, `auto_open: "after_first_write"`, no files.
4. Upload the logo files (`asset: true`, `file_paths`, to the new URL). Put
   each returned id in the index:
   `assetGroups.<Group>.files.<name> = {name, blob, size, type}`, with the
   `size` the upload result reports (the store can change an SVG's bytes, so
   the local size may differ). Upload only the logo versions DESIGN.md names.
5. ONE publish: `url`, `root` = `<dir>`, `file_path` = the index,
   `files` = the map in `publish.json`.
6. Write `design_system_url: <url>` in DESIGN.md's frontmatter. Commit it in
   the business's repo. Never write the URL in this toolkit.

**DESIGN.md changed:** run `ds` again to a fresh folder and compare it with
the last build (`cmp` per file) to find what changed. `read` the live index,
copy only the changed files into a new folder at their `project/` paths, and
publish them to the same `url` (`root` = that folder). Logos that did not
change are not uploaded again. Send the index
last and only to change its own keys (title, asset records, `lastChange`),
keeping every other key.

**Rules**

- The page is generated. Do not edit its tokens, README or previews on the
  page or by hand. A change goes into DESIGN.md first.
- The cover is a picture made only from tokens, plus the logo file in place
  of the name (`--name-logo`). You may redraw it when the owner asks ("more
  green"), with tokens only, no new facts.
- Sharing the page needs the owner's yes. You cannot share it; the owner
  uses the page's Share menu. When the owner shares it, the audience is the
  people with access to the business's marketing repo, no one wider. Until
  then the committed local view is how they see the system.
- Before you use the page in a later session, compare it with DESIGN.md
  (`design_md.py ds` to a scratch folder, diff `tokens.json`). Out of date:
  rebuild, then use it.
