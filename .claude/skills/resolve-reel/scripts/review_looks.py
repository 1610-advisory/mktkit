"""Numbered look-review page: several looks on the same real frames, exact Resolve math.

For each look, the per-shot grade is solved with grade_solve (so exposure and white
balance follow the business's rules under that look), then every still is rendered with
dwg_look.to_display + an optional vignette. Output: one self-contained HTML page (images
embedded) and one tall JPEG of the same grid, for review on a phone before a look is
committed.

    python3 review_looks.py grade.json --out DIR [--style reel-style.json]
        [--looks clean,rich,path/to/look.json] [--title "..."] [--vignette 0.035]
        [--labels "S1=Wide,S2=Close"]
Needs numpy, tifffile, Pillow.
"""
import argparse
import base64
import io
import json
import sys
from pathlib import Path
import numpy as np
import tifffile as tf
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dwg_look import PRESETS, load_look, look, to_display  # noqa: E402
from grade_solve import solve, settings  # noqa: E402

LW = np.array([0.2126, 0.7152, 0.0722])


def vignette(h, w, strength):
    y, x = np.mgrid[0:h, 0:w]
    r = np.sqrt(((x / w - 0.5) / 0.5) ** 2 + ((y / h - 0.45) / 0.55) ** 2)
    return strength * (np.clip((r - 0.55) / 0.75, 0, 1) ** 1.6)[..., None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('grade_json'); ap.add_argument('--out', required=True); ap.add_argument('--style')
    ap.add_argument('--looks', help='comma list of preset names or look-profile paths (default: all presets)')
    ap.add_argument('--title', default='Look review'); ap.add_argument('--vignette', type=float, default=0.035)
    ap.add_argument('--labels', default='', help='SHOT=label,...')
    a = ap.parse_args()
    gpath = Path(a.grade_json); cfg = json.loads(gpath.read_text()); base = gpath.parent
    looks = a.looks.split(',') if a.looks else list(PRESETS['presets'])
    labels = dict(kv.split('=', 1) for kv in a.labels.split(',') if '=' in kv)
    st = settings(cfg, a.style, base)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    stills = [(shot, f) for shot, sc in cfg['shots'].items() for f in sc['stills']]
    di = {f: tf.imread(base / f).astype(float) / 65535 for _, f in stills}
    vig = vignette(1920, 1080, a.vignette)
    rows = []
    for i, lk in enumerate(looks, 1):
        cdl = solve(gpath, a.style, lk, write=False, quiet=True)
        p = load_look(lk)
        tiles = []
        for shot, f in stills:
            c = cdl[shot]
            x = np.clip(di[f] * c['slope'] + np.array(c['offset']), 0, 1)
            l = (x @ LW)[..., None]
            x = np.clip(np.clip(l + c['sat'] * (x - l), 0, 1) - vig, 0, 1)
            img = Image.fromarray((to_display(look(x, p)) * 255 + 0.5).astype('uint8')).resize((432, 768), Image.LANCZOS)
            tiles.append((labels.get(shot, shot), img))
        name = Path(lk).stem if lk not in PRESETS['presets'] else lk
        rows.append((i, name, tiles))
        print(f'{i} {name}: ' + ', '.join(f"{s} {cdl[s]['anchor_ire']} IRE" for s in cdl))

    def b64(im):
        b = io.BytesIO(); im.save(b, 'JPEG', quality=84)
        return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()
    sec = ''.join(
        f'<section><h2><span class="n">{i}</span>{n}</h2><div class="g">'
        + ''.join(f'<figure><img src="{b64(im)}" alt="{n} {lab}"><figcaption>{lab}</figcaption></figure>' for lab, im in tiles)
        + '</div></section>' for i, n, tiles in rows)
    note = (f"Exposure: brightest part of the face at {st['face_ire']} IRE; black point {st['black_code']}/255. "
            "Same per-shot rules under every look. Exact Resolve output math. Reply with a number or a mix.")
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{a.title}</title><style>
:root{{--bg:#f4f2ee;--fg:#1d1d1b;--mut:#6b6a64;--card:#ffffff}}@media (prefers-color-scheme:dark){{:root{{--bg:#141412;--fg:#f2f0ea;--mut:#a8a69e;--card:#1f1f1c}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}}main{{max-width:960px;margin:0 auto;padding:16px}}
h1{{font-size:24px;margin:8px 0}}section{{background:var(--card);border-radius:12px;padding:12px;margin:14px 0}}
h2{{font-size:19px;margin:0 0 8px;display:flex;align-items:center;gap:10px}}.n{{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:50%;background:var(--fg);color:var(--bg);font-weight:600}}
p{{color:var(--mut)}}.g{{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}}figure{{margin:0}}figcaption{{font-size:11px;color:var(--mut)}}img{{width:100%;height:auto;border-radius:6px;display:block}}</style></head>
<body><main><h1>{a.title}</h1><p>{note}</p>{sec}</main></body></html>'''
    (out / f'{a.title}.html').write_text(html)
    W, H, cols = 300, 533, len(stills)
    sheet = Image.new('RGB', (cols * (W + 10) + 10, len(rows) * (H + 56) + 20), (244, 242, 238))
    d = ImageDraw.Draw(sheet)
    try:
        f = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 28)
    except OSError:
        f = ImageFont.load_default()
    for r, (i, n, tiles) in enumerate(rows):
        y = 10 + r * (H + 56); d.text((12, y), f'{i}  {n}', font=f, fill=(29, 29, 27))
        for j, (_, im) in enumerate(tiles):
            sheet.paste(im.resize((W, H)), (10 + j * (W + 10), y + 44))
    sheet.save(out / f'{a.title}.jpg', quality=85)
    print(out / f'{a.title}.html')


if __name__ == '__main__':
    main()
