"""Per-shot CDL solver for the DWG/DI grade (see ../SKILL.md, step 6).

Inputs: DaVinci Intermediate stills exported from Resolve (16-bit TIFF; timeline and
output set to DWG/DI, no grade on the clip) and a grade.json:

{
  "look": "clean",                    # preset name or client look-profile path (optional)
  "face_ire": 55,                     # brightest part of the face (98th pct of box), graded
  "black_code": 14,                   # target 1st-percentile luma, 8-bit
  "sat": 0.68,                        # CDL saturation (log contrast inflates chroma)
  "wb_target_709": [1.02, 1.0, 0.97], # white-balance target, Rec.709 linear (1,1,1 = neutral)
  "shots": {                          # solved in order; wall matches point backwards only
    "S1": {"stills": ["di_S1a.tif", "di_S1b.tif"],
           "faces": [[0, [x0, y0, x1, y1]], [1, [x0, y0, x1, y1]]]},
    "S2": {"stills": ["di_S2.tif"],
           "match_wall": {"box": [x0, y0, x1, y1], "ref_shot": "S1", "ref_still": 0,
                          "ref_box": [x0, y0, x1, y1]}},
    "S3": {"stills": ["di_S3.tif"], "manual_wb": [1.0, 1.0, 1.0], "faces": [[0, [..]]]}
  }
}

Precedence for every setting: grade.json > the client's reel style profile "resolve"."grade" block
(--style) > the defaults below. Boxes are 1080x1920 timeline pixels; stills paths are
relative to grade.json. Writes cdl.json next to grade.json (slope, offset R G B, sat per
shot) ready for TimelineItem.SetCDL. `manual_wb` (linear gains) skips the automatic
neutral search for shots lit by one colored source.

    python3 grade_solve.py path/to/grade.json [--style client/resources/reel-style.json]
Needs numpy + tifffile.
"""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import tifffile as tf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dwg_look import to_display, look, load_look, di_decode, DWG_TO_709, C  # noqa: E402

DEFAULTS = {'look': None, 'face_ire': 55.0, 'black_code': 14, 'sat': 0.68,
            'wb_target_709': [1.02, 1.0, 0.97], 'pivot': 0.40}
LW = np.array([0.2126, 0.7152, 0.0722])


def Y(x):
    return x @ LW


def settings(cfg, style_path=None, base=None):
    """grade.json > client style profile "grade" block > DEFAULTS."""
    s = dict(DEFAULTS)
    if style_path:
        sty = json.loads(Path(style_path).read_text())
        g = (sty.get('resolve') or {}).get('grade') or sty.get('grade') or {}
        root = Path(style_path).resolve().parents[1]           # <client>/resources/reel-style.json
        if g.get('look_profile'):
            s['look'] = str((root / g['look_profile']).resolve())
        s.update({k: v for k, v in g.items() if k in DEFAULTS and k != 'look'})
    s.update({k: v for k, v in cfg.items() if k in DEFAULTS and k != 'look' and v is not None})
    if cfg.get('look'):                                      # preset name, or a path relative to grade.json
        s['look'] = cfg['look'] if (base is None or not (base / cfg['look']).exists()) else str(base / cfg['look'])
    return s


def wb_gains(stills, target):
    warm = np.linalg.solve(DWG_TO_709, np.array(target, float))
    warm /= warm[1]
    refs = []
    for di in stills:
        s = di[::4, ::4].reshape(-1, 3)
        lin = di_decode(s)
        y = lin @ np.array([0.3, 0.6, 0.1])
        ok = s.max(1) < 0.97
        hi = ok & (y > np.percentile(y[ok], 80)) & (y < np.percentile(y[ok], 98))
        c = lin[hi]
        ch = (c.max(1) - c.min(1)) / np.maximum(c.max(1), 1e-6)
        refs.append(c[ch < np.percentile(ch, 30)].mean(0))
    ref = np.mean(refs, 0)
    return warm / (ref / ref[1])


def crop(di, b):
    x0, y0, x1, y1 = b
    return di[y0:y1:2, x0:x1:2].reshape(-1, 3)


def solve(cfg_path, style_path=None, look_override=None, write=True, quiet=False):
    cfg_path = Path(cfg_path)
    cfg, base = json.loads(cfg_path.read_text()), cfg_path.parent
    st = settings(cfg, style_path, base)
    p = load_look(look_override or st['look'])
    sat, face_t, black, pivot = st['sat'], st['face_ire'] / 100, st['black_code'] / 255, st['pivot']

    def cdlsat(x):
        l = Y(x)[..., None]
        return np.clip(l + sat * (x - l), 0, 1)

    def render(arr, s, off):
        return to_display(look(cdlsat(np.clip(arr * s + off, 0, 1)), p))

    out, stills_of = {}, {}
    for shot, sc in cfg['shots'].items():
        stills = [tf.imread(base / f).astype(float) / 65535 for f in sc['stills']]
        stills_of[shot] = stills
        g = np.array(sc['manual_wb'], float) if 'manual_wb' in sc else wb_gains(stills, st['wb_target_709'])
        wb = C * np.log2(g)
        rng = np.random.default_rng(0)
        samp = np.concatenate([d.reshape(-1, 3)[rng.choice(d.shape[0] * d.shape[1], 8000, replace=False)] for d in stills])
        if 'faces' in sc:
            target = face_t
            def measure(s, off, sc=sc, stills=stills):
                return np.mean([np.percentile(Y(render(crop(stills[i], b), s, off)), 98) for i, b in sc['faces']])
        else:
            m = sc['match_wall']
            ref = out[m['ref_shot']]
            ref_px = crop(stills_of[m['ref_shot']][m.get('ref_still', 0)], m['ref_box'])
            target = float(np.median(Y(render(ref_px, ref['slope'], np.array(ref['offset'])))))
            def measure(s, off, m=m, stills=stills):
                return float(np.median(Y(render(crop(stills[0], m['box']), s, off))))
        best = None
        for s in np.linspace(0.75, 2.0, 26):
            lo, hi = -0.4, 0.3
            for _ in range(18):                              # exposure: bisection to the anchor
                e = (lo + hi) / 2
                lo, hi = (e, hi) if measure(s, wb + e + (1 - s) * pivot) < target else (lo, e)
            off = wb + e + (1 - s) * pivot
            p1 = np.percentile(Y(render(samp, s, off)), 1)
            if best is None or abs(p1 - black) < best[0]:    # contrast: 1st pct at the black code
                best = (abs(p1 - black), s, off, p1, measure(s, off))
        _, s, off, p1, v = best
        out[shot] = {'slope': round(float(s), 3), 'offset': [round(float(x), 5) for x in off], 'sat': sat,
                     'p1_code': round(float(p1) * 255, 1), 'anchor_ire': round(float(v) * 100, 1),
                     'wb_gains': [round(float(x), 3) for x in g]}
        if not quiet:
            print(shot, out[shot])
    if write:
        (base / 'cdl.json').write_text(json.dumps(out, indent=1) + '\n')
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('grade_json'); ap.add_argument('--style'); ap.add_argument('--look')
    a = ap.parse_args()
    solve(a.grade_json, a.style, a.look)
