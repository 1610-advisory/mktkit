"""Look engine for Resolve reels graded in DaVinci Wide Gamut / DaVinci Intermediate.

Pipeline it models (Resolve Color Managed, output tone mapping and gamut mapping OFF):
    camera log --clip input space--> DWG/DI timeline
    node 1: per-shot CDL (log offsets = white balance + exposure, slope = contrast in log)
    node 1: look LUT (made here, DI in -> DI out), which carries the tone curve
    output: DWG/DI -> Rec.709, Gamma 2.4 (plain matrix + encode)

Because the output step is plain math, to_display() reproduces the Resolve render, so
preview stills match the timeline (checked to about 0.3 of an 8-bit code value).

Look design (from Steve Yedlin, Cullen Kelly, Juan Melara, Mixing Light, Frame.io):
- per-channel log-logistic toe + shoulder on scene-linear, not an S-curve after Rec.709
- subtractive saturation in OkLab (chroma up, lightness down), fading out on neutrals
- split tone: cool shadows, warm highlights / skin; low-chroma surfaces stay clean

A look is a preset name from resources/looks.presets.json, or a path to a client look
profile (resources/look.example.json shape).

    python3 dwg_look.py write  --look clean            --out house.cube
    python3 dwg_look.py write  --look path/to/look.json --out house.cube
    python3 dwg_look.py presets OUT_DIR                 # every preset as .cube
Needs numpy.
"""
import argparse
import json
from pathlib import Path
import numpy as np

SKILL = Path(__file__).resolve().parents[1]
PRESETS = json.loads((SKILL / 'resources/looks.presets.json').read_text())

# DaVinci Intermediate transfer
A, B, C, M = 0.0075, 7.0, 0.07329248, 10.44426855
LIN_CUT, LOG_CUT = 0.00262409, 0.02740668


def di_decode(y):
    y = np.asarray(y, dtype=np.float64)
    return np.where(y <= LOG_CUT, y / M, np.exp2(y / C - B) - A)


def di_encode(x):
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= LIN_CUT, x * M, (np.log2(np.maximum(x, 1e-10) + A) + B) * C)


def rgb_to_xyz_matrix(prim, white=(0.3127, 0.3290)):
    def xyz(xy):
        x, y = xy
        return np.array([x / y, 1.0, (1 - x - y) / y])
    P = np.stack([xyz(p) for p in prim], axis=1)
    return P * np.linalg.solve(P, xyz(white))


DWG_XYZ = rgb_to_xyz_matrix([(0.8000, 0.3130), (0.1682, 0.9877), (0.0790, -0.1155)])
R709_XYZ = rgb_to_xyz_matrix([(0.64, 0.33), (0.30, 0.60), (0.15, 0.06)])
DWG_TO_709 = np.linalg.solve(R709_XYZ, DWG_XYZ)
XYZ_DWG = np.linalg.inv(DWG_XYZ)

M1 = np.array([[0.8189330101, 0.3618667424, -0.1288597137],
               [0.0329845436, 0.9293118715, 0.0361456387],
               [0.0482003018, 0.2643662691, 0.6338517070]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
               [1.9779984951, -2.4285922050, 0.4505937099],
               [0.0259040371, 0.7827717662, -0.8086757660]])
M1i, M2i = np.linalg.inv(M1), np.linalg.inv(M2)


def xyz_to_oklab(xyz):
    return np.cbrt(xyz @ M1.T) @ M2.T


def oklab_to_xyz(lab):
    return ((lab @ M2i.T) ** 3) @ M1i.T


def to_display(di, gamma=2.4):
    """Resolve output with tone/gamut mapping off: DWG/DI -> Rec.709 at `gamma`."""
    lin = di_decode(di) @ DWG_TO_709.T
    return np.clip(lin, 0, 1) ** (1 / gamma)


def tone(x, contrast, grey_out=0.16, peak=1.0, flare=0.004):
    """Per-channel filmic curve on scene-linear. Scene 0.18 -> grey_out, asymptote peak."""
    x = np.maximum(x, 0)
    h = 0.18 * (peak / grey_out - 1) ** (1 / contrast)
    d = peak * x ** contrast / (x ** contrast + h ** contrast)
    return np.maximum(d - flare, 0) / (1 - flare)


def load_look(spec=None):
    """Preset name, a look-profile path, or None (the presets file's default)."""
    spec = spec or PRESETS['default']
    if spec in PRESETS['presets']:
        return dict(PRESETS['presets'][spec])
    prof = json.loads(Path(spec).read_text())
    p = dict(PRESETS['presets'][prof.get('base', PRESETS['default'])])
    p.update(prof.get('params', {}))
    return p


def look(di, p):
    """DI in -> DI out. di: (..., 3) in DWG / DaVinci Intermediate."""
    disp = tone(di_decode(di), p['contrast'], p['grey'])
    lab = xyz_to_oklab(np.maximum(disp, 0) @ DWG_XYZ.T)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)
    colorful = np.clip((chroma - p['neutral']) / 0.04, 0, 1)
    gain = 1 + (p['sat'] - 1) * colorful
    a2, b2 = a * gain, b * gain
    L = L - p['sub'] * (np.hypot(a2, b2) - chroma)
    shadow = np.clip(1 - L / 0.45, 0, 1) ** 2
    high = np.clip((L - 0.45) / 0.45, 0, 1)
    b2 = b2 - p['cool'] * shadow + p['warm'] * high * (0.3 + 0.7 * colorful)
    a2 = a2 - p['cool'] * 0.3 * shadow
    hue = np.degrees(np.arctan2(b2, a2)) % 360
    b2 = b2 + p['skin'] * np.clip(1 - np.abs(hue - 60) / 30, 0, 1) * colorful
    out = np.maximum(oklab_to_xyz(np.stack([L, a2, b2], axis=-1)) @ XYZ_DWG.T, 0)
    return di_encode(out)


def write_cube(path, p, n=33, title=None):
    g = np.linspace(0, 1, n)
    b, gg, r = np.meshgrid(g, g, g, indexing='ij')          # red varies fastest
    out = np.clip(look(np.stack([r, gg, b], axis=-1).reshape(-1, 3), p), 0, 1)
    head = [f'TITLE "{title or Path(path).stem}"',
            '# DaVinci Wide Gamut / DaVinci Intermediate in -> out. Resolve output: tone + gamut mapping off.',
            f'LUT_3D_SIZE {n}', 'DOMAIN_MIN 0 0 0', 'DOMAIN_MAX 1 1 1']
    Path(path).write_text('\n'.join(head) + '\n' + '\n'.join(f'{x:.6f} {y:.6f} {z:.6f}' for x, y, z in out) + '\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    w = sub.add_parser('write'); w.add_argument('--look'); w.add_argument('--out', required=True)
    pr = sub.add_parser('presets'); pr.add_argument('out_dir')
    a = ap.parse_args()
    if a.cmd == 'write':
        write_cube(a.out, load_look(a.look)); print(a.out)
    else:
        d = Path(a.out_dir); d.mkdir(parents=True, exist_ok=True)
        for name in PRESETS['presets']:
            write_cube(d / f'dwg-{name}.cube', load_look(name)); print(d / f'dwg-{name}.cube')
