# Mkt kit — pack questions, intake log, fonts

Companion to `SKILL.md`. One level deep.

## Intake log

Path: current client `knowledge/_intake-log.md`

```markdown
# Knowledge intake log

Answers collected because a pack file was missing. Promote into the named
file. Stop treating this as source of truth once that file exists.

## YYYY-MM-DD — DESIGN.md missing
- Q: …
- A: …
```

## Questions by missing file

Ask only what this task needs. Log all answers anyway if you asked them.

**DESIGN.md / brand-identity.md**
- Display (serif) family? Body (sans)? Mono for labels, if any?
- Page background hex? Primary/mass hex? Accent hex (rules, not fills)?
- Corners: square or radius?
- Light or dark default surface?

**voice-guidelines.md**
- We or I on this surface?
- Banned words?
- Em dashes: yes or no?
- Punchlines / mic drops: yes or no?
- Contractions: yes or no?
- One line that sounds like them, from something they actually wrote.

**personas-storybrand.md**
- Flagship buyer in one sentence (role + situation, not a slogan)?
- What do they already believe that's wrong?

**00-client-overview.md**
- What do they sell, in one sentence?
- Who is it for (band / industry / geography), not a tagline?

**goals-and-benchmarks.md**
- What is this period actually for (one outcome)?
- What are we explicitly not chasing (followers, vanity)?

**offer.md** (if the task sells)
- Front door name? What do they leave with?
- What is not for sale on this surface?

## Fonts

Cover / display → serif from DESIGN.md. Captions / UI → sans from DESIGN.md.

1. Parse family names.
2. `fc-list : family | sort -u` and look for those names. Also check `~/Library/Fonts` and the client's `resources/fonts/`.
3. If missing, download the Google Fonts zip (no font, no render):

```bash
FAM="Cormorant Garamond"   # from the pack, not a default
SLUG=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$FAM")
DEST="<client>/resources/fonts"
mkdir -p "$DEST" /tmp/gf
curl -fsSL "https://fonts.google.com/download?family=$SLUG" -o /tmp/gf/font.zip
unzip -o /tmp/gf/font.zip -d /tmp/gf/out
find /tmp/gf/out -iname '*.ttf' -o -iname '*.otf' | while read f; do cp "$f" "$DEST/"; done
```

4. Pass **absolute paths** to `finish-reel.py` (`--font` cover serif, `--caption-font` body sans) or `@font-face` src in HTML. ffmpeg cannot use a family name that isn't installed.
5. Log the path in `_intake-log.md` under DESIGN.md if that file is still missing.

Do not use Marcellus, Inter, Geist, Playfair (unless the pack names it), or system fallback as the brand face.

## Video style file

Any cut (`resolve-reel`, `cut-video`) reads `resources/reel-style.json` (shape: `cut-video/resources/style.example.json`). If it is missing, build it before the first cut, from this repo only:

1. **Fonts + colors** from `DESIGN.md` (Fonts above): cover = display face, captions = body sans. Absolute paths to files in `resources/fonts/`. Cover color from the pack.
2. **Sizes:** cover 72; captions 56 unless the business has set one.
3. **`edit_route`:** ask once (`references/edit-route.md` → step 4) or take the owner's known preference; write the reason.
4. **`resolve` block:** leave `grade` values out (the skill's middle defaults apply) and say so. Set `camera_input` and `look_profile` only after real footage and a look review (`resolve-reel` step 0).
5. Log the file in `_intake-log.md`.

## Cover / caption style

- Cover line: public-safe, ≤7 words, **casing from voice** (sentence case unless the pack says otherwise).
- Cover color: from DESIGN.md (ivory/on-primary on dark footage; charcoal on ivory). Not a hardcoded cream unless that's the pack.
- Dialogue captions: body sans, bottom-center, high-contrast. Outline if the plate is busy. Not the cover serif.
