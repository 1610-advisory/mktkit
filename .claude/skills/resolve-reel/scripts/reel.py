#!/usr/bin/env python3
"""reel.py: prep, build and QA a vertical reel in a few commands (resolve-reel skill).

    reel.py prep  --work DIR --footage FILE [FILE...] [--note NOTE.md] [--style reel-style.json] [--words W.json ...]
    reel.py build --edit DIR/edit.json --style reel-style.json --version vN [--dry-run] [--owner NAME] [--force]
    reel.py qa    --video FILE.mp4 --edit DIR/edit.json [--ass captions.ass] [--style reel-style.json]
    reel.py lock  {acquire,release,status} --owner NAME

The editor agent makes the decisions (what is said, what is shown, where each edge sits) and
writes them in edit.json. This tool does the labor: probing, transcripts, silence valleys, contact
sheets, the cut gates, captions and cover, the Resolve build (SKILL.md steps 2 to 10), the loudness
finish, QA, and one review sheet. Each command prints a short summary and writes the details to
files, so the agent's context stays small.

edit.json (what `build` and `qa` read; times on a clip are SOURCE time, `at` is RECORD time):

{
  "id": "piece-slug",                        # output stem: <id>_<version>.mp4 (public-safe name)
  "project": "Business Piece 2026-01-01",    # Resolve project (created, or reused on a rebuild)
  "timeline": "Piece - Reel",                # Resolve timeline; build adds " <version>"
  "out_dir": "renders",                      # optional, relative to edit.json (default: its folder)
  "fps": 29.97002997002997,
  "cover_text": "PUBLIC-SAFE TITLE",
  "platforms": ["instagram_reels", "youtube_shorts", "tiktok"],   # optional, else the style's
  "min_aroll_s": 3.0, "lead_frames": 4, "tail_frames": 3,         # optional
  "voice_gain_db": 4.0,                      # optional, else style resolve.grade.voice_gain_db
  "audio_fade_frames": 0,                    # optional default fade on every A1 edge
  "clips": {                                 # ids from prep.md
    "C1": {"path": "/abs/Video/take.MP4", "words": "/abs/Audio/take.json"},
    "C2": {"path": "/abs/Video/broll.MP4", "input": "Rec.709 Gamma 2.4"}   # input: optional override
  },
  "picture": {"rotation": 0, "zoom": 1.067, "tight_factor": 1.12,
              "calibration": {"pan_px": 0.9375, "tilt_px": 1.0}},        # optional; px per Pan/Tilt unit
  "hook": {"k": "H"},                        # optional: the prepended hook segment
  "spine": [                                 # V1/A1 in playback order; in_s/out_s or in/out (frames)
    {"k": "H",  "clip": "C1", "in_s": 4.34, "out_s": 7.91, "framing": "wide"},
    {"k": "K1", "clip": "C1", "in_s": 1.03, "out_s": 9.64, "framing": "tight",
     "shift_px": [4, 124], "gain_db": null, "fades": [0, 1], "cam": "C1"}
  ],
  "punches": [                               # V2, picture only; src_in_s/dur_s/at_s or src_in/len/at
    {"k": "P1", "clip": "C2", "src_in_s": 29.6, "dur_s": 1.6, "at_s": 10.54,
     "shows": "what the viewer sees", "line": "what is said over it"}
  ],
  "edge_exceptions": {"K1 in": "run-together words: quietest 10 ms + 1-frame fade"},
  "grade": {                                 # optional; default = one shot per clip, faces found
    "shots": {                               # automatically, B-roll matched to the first A-roll shot
      "A":  {"items": ["H", "K1"], "stills": {"A1": 60}, "faces": {"A1": "auto"}},
      "BR": {"items": ["P1"], "stills": {"BR": 322},
             "match_wall": {"box": [0, 480, 1080, 1440], "ref_shot": "A", "ref_still": 0,
                            "ref_box": [0, 480, 1080, 1440]}}
    }
  }
}

Tight framing without a zoom gets zoom x tight_factor. shift_px = [right, down] screen pixels,
turned into Pan/Tilt with the calibration (default from the clip's display size; check a still).
Everything that makes a reel look like one business comes from its reel-style.json.

Exit codes (build): 0 ok, 2 gate or input failure (message names the gate), 3 Resolve, render or
finish failure (a held lock is reported as 3 with the holder). qa: 0 pass or warn, 3 fail.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from fractions import Fraction
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILLS = SCRIPTS.parents[1]
CUT_SCRIPTS = SKILLS / 'cut-video' / 'scripts'
CONTACT_SHEET = CUT_SCRIPTS / 'contact-sheet.py'
FINISH = CUT_SCRIPTS / 'finish-reel.py'
QA_REEL = CUT_SCRIPTS / 'qa-reel.py'
TRANSCRIBE = SKILLS / 'transcribe-audio' / 'scripts' / 'transcribe.py'
HOUSE_GRAPHICS = SCRIPTS / 'house_graphics.py'
RESOLVE_OPS = SCRIPTS / 'resolve_ops.py'
CUT_CHECK = SCRIPTS / 'cut_check.py'

FPS_DEFAULT = 30000 / 1001
TL_W, TL_H = 1080, 1920
LOCK_MAX_AGE_S = 4 * 3600
DI_PER_STOP = 0.07329          # DaVinci Intermediate code per stop (vignette gain math)
GRADE_DEFAULTS = {'camera_input': None, 'lut_resolve': None, 'vignette': 0.035, 'voice_gain_db': 4.0,
                  'vignette_mode': 'gain'}


class GateError(Exception):
    """A gate or input problem the editor must fix (exit 2)."""


class BackendError(Exception):
    """Resolve, render or finish failure (exit 3)."""


# ---------------------------------------------------------------- small helpers

def log(msg):
    print(msg, flush=True)


def load_json(p):
    return json.loads(Path(p).read_text())


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=1) + '\n')


def sha(obj, n=12):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:n]


def file_sha(p, n=12):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:n]


def run(cmd, check=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, '\n'.join(tail))
    return r


def py():
    return sys.executable


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cut_check():
    return load_module('cut_check', CUT_CHECK)


def capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*a, **kw)
    return code, buf.getvalue()


def banned_terms(style, style_path):
    f = ((style or {}).get('qa') or {}).get('banned_words_file')
    if not f:
        return None, []
    p = Path(f)
    if not p.is_absolute() and style_path:
        p = Path(style_path).resolve().parent / p
    if not p.exists():
        return p, []
    terms = [ln.strip() for ln in p.read_text(errors='replace').splitlines()
             if ln.strip() and not ln.strip().startswith('#')]
    return p, terms


def banned_hit(text, terms):
    for t in terms:
        if re.search(r'\b' + re.escape(t) + r'\b', text or '', re.I):
            return t
    return None


# ---------------------------------------------------------------- probe + transcript

def probe(path):
    d = json.loads(run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams',
                        '-show_format', path]).stdout)
    v = next((s for s in d.get('streams', []) if s.get('codec_type') == 'video'), None)
    a = next((s for s in d.get('streams', []) if s.get('codec_type') == 'audio'), None)
    out = {'path': str(path), 'duration': round(float(d.get('format', {}).get('duration') or 0), 3)}
    if v:
        rot = 0
        for sd in v.get('side_data_list') or []:
            if 'rotation' in sd:
                rot = int(float(sd['rotation']))
        if not rot and (v.get('tags') or {}).get('rotate'):
            rot = int(v['tags']['rotate'])
        w, h = int(v.get('width') or 0), int(v.get('height') or 0)
        fr = v.get('r_frame_rate') or v.get('avg_frame_rate') or '0/1'
        try:
            fps = float(Fraction(fr))
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        disp = [h, w] if abs(rot) % 180 == 90 else [w, h]
        out.update({'width': w, 'height': h, 'rotation': rot, 'display': disp, 'fps': round(fps, 5),
                    'vcodec': v.get('codec_name'), 'pix_fmt': v.get('pix_fmt'),
                    'transfer': v.get('color_transfer'), 'tagged_input': tagged_input(v.get('color_transfer'))})
    if a:
        out.update({'audio_rate': int(a.get('sample_rate') or 0), 'audio_ch': a.get('channels'),
                    'acodec': a.get('codec_name')})
    return out


def tagged_input(transfer):
    """Resolve input space implied by an explicit transfer tag. Log camera files usually carry no
    transfer tag; phone and screen clips do. A display-referred clip graded as log comes out neon
    (live batch 2026-09-29: phone A-roll under a log camera_input), so a tag beats the style default."""
    return {'bt709': 'Rec.709 Gamma 2.4', 'smpte170m': 'Rec.709 Gamma 2.4', 'bt470bg': 'Rec.709 Gamma 2.4',
            'iec61966-2-1': 'sRGB', 'arib-std-b67': 'Rec.2100 HLG', 'smpte2084': 'Rec.2100 ST2084'}.get(transfer or '')


def probe_line(p):
    if 'width' not in p:
        return f"audio only | {p['duration']:.2f} s"
    rot = f", rot {p['rotation']:+d} -> {p['display'][0]}x{p['display'][1]} display" if p['rotation'] else ''
    au = f"{p.get('acodec')} {p.get('audio_rate')} Hz {p.get('audio_ch')}ch" if p.get('audio_rate') else 'no audio'
    tag = f" | tagged {p['tagged_input']} (build uses it, not the style camera_input)" if p.get('tagged_input') else ''
    return (f"{p['width']}x{p['height']} {p['vcodec']} {p['pix_fmt']}{rot} | {p['fps']:.3f} fps | "
            f"{p['duration']:.2f} s | {au}{tag}")


def has_words(path):
    try:
        d = load_json(path)
    except (OSError, ValueError):
        return False
    return any(seg.get('words') for seg in d.get('segments', []))


def find_words(clip, work, explicit=()):
    clip = Path(clip)
    stem = clip.stem.lower()
    for w in explicit:
        if Path(w).stem.lower() == stem and has_words(w):
            return str(Path(w).resolve())
    dirs = [clip.parent, clip.parent / 'Audio', clip.parent.parent / 'Audio', Path(work) / 'words']
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob('*.json')):
            if f.stem.lower() == stem and has_words(f):
                return str(f.resolve())
    return None


def transcribe(clip, work, model='large-v3-turbo', language=None):
    """One mlx-whisper job at a time on this machine (a blocking file lock)."""
    import fcntl
    out = Path(work) / 'words' / (Path(clip).stem + '.txt')
    out.parent.mkdir(parents=True, exist_ok=True)
    lockp = lock_path().parent / 'transcribe.lock'
    lockp.parent.mkdir(parents=True, exist_ok=True)
    cmd = [py(), TRANSCRIBE, clip, '--out', out, '--json', '--model', model]
    if language:
        cmd += ['--language', language]
    with open(lockp, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        run(cmd)
    j = out.with_suffix('.json')
    return str(j) if has_words(j) else None


def load_words(path):
    """[(start, end, token, low_confidence)], hyphen tokens joined like house_graphics does."""
    d = load_json(path)
    out = []
    for seg in d.get('segments', []):
        low = (seg.get('no_speech_prob') or 0) > 0.6 or (seg.get('avg_logprob') or 0) < -1.0
        for w in seg.get('words', []):
            tok = str(w.get('word', '')).strip()
            if not tok:
                continue
            if tok.startswith('-') and out:
                s0, _e, t0, l0 = out[-1]
                out[-1] = (s0, float(w['end']), t0 + tok, l0 or low)
                continue
            out.append((float(w['start']), float(w['end']), tok, low))
    out.sort(key=lambda x: x[0])
    return out


def phrases(words, gap=0.25, max_len=12.0):
    """Phrase lines: split on a pause >= gap, at a sentence end, or past max_len seconds."""
    out = []
    for s, e, tok, low in words:
        if out and s - out[-1][1] < gap and e - out[-1][0] <= max_len and not out[-1][2].endswith(('.', '?', '!')):
            p = out[-1]
            out[-1] = [p[0], e, p[2] + ' ' + tok, p[3] or low]
        else:
            out.append([s, e, tok, low])
    return [[round(a, 2), round(b, 2), t, lo] for a, b, t, lo in out]


def valleys(path, min_s=0.12):
    """Quiet runs >= min_s on the 48 kHz full band AND the >2.5 kHz band (cut_check's quiet map)."""
    import numpy as np
    cc = cut_check()
    try:
        a = cc.decode(str(path))
    except subprocess.CalledProcessError:
        return []
    q = cc.quiet_map(a)
    w = int(cc.WIN * cc.SR)
    need = int(round(min_s / cc.WIN))
    out, i, n = [], 0, len(q)
    while i < n:
        if not q[i]:
            i += 1
            continue
        j = i
        while j < n and q[j]:
            j += 1
        if j - i >= need:
            seg = a[i * w:j * w]
            db = 20 * math.log10(float(np.sqrt((seg * seg).mean())) + 1e-9)
            out.append([round(i * cc.WIN, 2), round(j * cc.WIN, 2), round(db)])
        i = j
    return out


# ---------------------------------------------------------------- note (brief)

def note_brief(note_path):
    text = Path(note_path).read_text(errors='replace')
    lines = text.splitlines()
    brief, cover = None, None
    for i, ln in enumerate(lines):
        m = re.match(r'^(#+)\s+.*editor brief', ln, re.I)
        if m and brief is None:
            lvl = len(m.group(1))
            j = i + 1
            while j < len(lines):
                m2 = re.match(r'^(#+)\s', lines[j])
                if m2 and len(m2.group(1)) <= lvl:
                    break
                j += 1
            brief = '\n'.join(lines[i:j]).strip()
    for ln in lines:
        if re.search(r'cover title \(public-safe\)\s*:', ln, re.I):
            cover = ln.strip()
            break
    return brief, cover


# ---------------------------------------------------------------- prep

def cmd_prep(a):
    work = Path(a.work).resolve()
    (work / 'sheets').mkdir(parents=True, exist_ok=True)
    style = load_json(a.style) if a.style else {}
    footage = [Path(f).resolve() for f in a.footage]
    for f in footage:
        if not f.exists():
            raise GateError(f'footage not found: {f}')
    explicit = [str(Path(w).resolve()) for w in (a.words or [])]
    clips, transcribed = {}, 0
    for n, f in enumerate(footage, 1):
        cid = f'C{n}'
        pr = probe(f)
        words = find_words(f, work, explicit)
        if not words and explicit and len(explicit) == len(footage) and has_words(explicit[n - 1]):
            words = explicit[n - 1]
        src = 'found' if words else None
        if not words and not a.no_transcribe and pr.get('audio_rate'):
            words = transcribe(f, work, a.model, a.language)
            src, transcribed = ('transcribed', transcribed + 1) if words else (None, transcribed)
        ph = phrases(load_words(words)) if words else []
        vl = valleys(f) if (ph and pr.get('audio_rate')) else []
        sheet = work / 'sheets' / f'{f.stem}.jpg'
        dur = pr['duration']
        k = 16 if dur > 4 else max(4, int(dur * 3))
        times = [round(0.1 + (dur - 0.25) * i / (k - 1), 2) for i in range(k)] if dur > 0.5 else [0.0]
        r = run([py(), CONTACT_SHEET, '--video', f, '--times', ','.join(map(str, times)),
                 '--labels', ','.join(f'{t:.1f}s' for t in times), '--cols', '4', '--tile-width', '240',
                 '--out', sheet], check=False)
        clips[cid] = {**pr, 'name': f.name, 'words': words, 'words_source': src,
                      'sheet': str(sheet) if r.returncode == 0 and sheet.exists() else None,
                      'phrases': ph, 'valleys': vl}
    brief = cover = None
    if a.note:
        brief, cover = note_brief(a.note)
    prep = {'work': str(work), 'style': str(Path(a.style).resolve()) if a.style else None,
            'note': str(Path(a.note).resolve()) if a.note else None, 'brief': brief, 'cover_line': cover,
            'clips': clips, 'made': dt.datetime.now().isoformat(timespec='seconds')}
    write_json(work / 'prep.json', prep)
    md = prep_markdown(prep, style)
    (work / 'prep.md').write_text(md)
    tok = len(md) // 4
    log(f'prep: {len(clips)} clips, {sum(1 for c in clips.values() if c["words"])} with words '
        f'({transcribed} transcribed now), {sum(len(c["valleys"]) for c in clips.values())} valleys')
    log(f'wrote {work / "prep.md"} (~{tok} tokens), prep.json, sheets/')
    missing = [c['name'] for c in clips.values() if not c['words'] and c.get('audio_rate')]
    if missing:
        log('no transcript: ' + ', '.join(missing))
    if a.note and not brief:
        log('note has no "Editor Brief" section')
    return 0


def prep_markdown(prep, style):
    g = ((style.get('resolve') or {}).get('grade') or {})
    cap, cov = style.get('captions') or {}, style.get('cover') or {}
    L = [f"# Prep: {Path(prep['work']).name}", '']
    if style:
        L.append(f"Style: camera `{g.get('camera_input')}`, captions {cap.get('size')} px "
                 f"{cap.get('placement', '')}, cover {cov.get('seconds', 2.0)} s {cov.get('case', '')}, "
                 f"platforms {', '.join(style.get('platforms') or [])}, voice gain {g.get('voice_gain_db')} dB, "
                 f"banned-words list: {'yes' if (style.get('qa') or {}).get('banned_words_file') else 'no'}.")
    L += ['Times are source seconds (frame = s x fps). `~` lines are silence valleys on the 48 kHz full band',
          'AND the >2.5 kHz band, >= 120 ms, as `start-end (dB)`: the only safe audio edges (edit-craft',
          'rule 4). An in-edge may move only earlier, an out-edge only later. `?` = low-confidence words',
          '(whisper invents words on quiet B-roll). Read each sheet image before choosing shots.', '']
    if prep.get('brief') or prep.get('cover_line'):
        L += ['## Brief (from the content note, verbatim)', '']
        if prep.get('brief'):
            L += [prep['brief'], '']
        if prep.get('cover_line'):
            L += [prep['cover_line'], '']
    L += ['## Clips', '']
    for cid, c in prep['clips'].items():
        L += [f"### {cid}: {c['name']}", f"`{c['path']}`", probe_line(c)]
        if c.get('rotation'):
            L.append('Rotation flag set: Resolve usually honours it (picture rotation 0, zoom 1.067); '
                     'some cards need rotation +-90 and zoom 1.91. The build checks a still for bars.')
        L.append(f"words: {c['words'] or 'none'}{' (' + c['words_source'] + ')' if c.get('words_source') else ''}"
                 f" | sheet: {c['sheet'] or 'none'}")
        vl = list(c['valleys'])
        ph = c['phrases']
        if ph:
            L.append('')
            lead = [v for v in vl if v[1] <= ph[0][0] + 0.05]
            if lead:
                L.append('  ~ ' + ' | '.join(f'{v[0]:.2f}-{v[1]:.2f} ({v[2]})' for v in lead[-4:]))
            for i, (s, e, t, low) in enumerate(ph):
                L.append(f"[{s:.2f}-{e:.2f}] {'? ' if low else ''}{t}")
                nxt = ph[i + 1][0] if i + 1 < len(ph) else 1e9
                vs = [v for v in vl if s < (v[0] + v[1]) / 2 <= nxt and v[1] > ph[0][0] + 0.05]
                if vs:
                    L.append('  ~ ' + ' | '.join(f'{v[0]:.2f}-{v[1]:.2f} ({v[2]})' for v in vs[:12])
                             + (f' (+{len(vs) - 12} more)' if len(vs) > 12 else ''))
        L.append('')
    skel = {'id': '<public-safe-slug>', 'project': '<Business Piece YYYY-MM-DD>', 'timeline': '<Piece - Reel>',
            'cover_text': '<PUBLIC-SAFE TITLE>',
            'clips': {cid: ({'path': c['path'], 'words': c['words']} if c['words'] else {'path': c['path']})
                      for cid, c in prep['clips'].items()},
            'hook': {'k': 'H'},
            'spine': [{'k': 'H', 'clip': 'C1', 'in_s': 0.0, 'out_s': 0.0, 'framing': 'wide'}],
            'punches': [{'k': 'P1', 'clip': 'C2', 'src_in_s': 0.0, 'dur_s': 0.0, 'at_s': 0.0, 'shows': '', 'line': ''}]}
    L += ['## edit.json skeleton (schema: `reel.py --help`)', '', '```json',
          json.dumps(skel, indent=1), '```', '']
    return '\n'.join(L)


# ---------------------------------------------------------------- edit.json -> plan

def fl(x):
    return int(math.floor(x + 1e-6))


def ce(x):
    return int(math.ceil(x - 1e-6))


def normalize(edit, edit_path, style=None, probes=None):
    """edit.json -> a plan with every time in frames and every default filled in."""
    base = Path(edit_path).resolve().parent
    style = style or {}
    fps = float(edit.get('fps') or FPS_DEFAULT)
    if not edit.get('spine'):
        raise GateError('edit.json has no spine')
    clips = {}
    for cid, c in (edit.get('clips') or {}).items():
        c = {'path': c} if isinstance(c, str) else dict(c)
        for key in ('path', 'words', 'audio'):
            if c.get(key):
                p = Path(c[key])
                c[key] = str(p if p.is_absolute() else (base / p).resolve())
        clips[cid] = c
    probes = probes if probes is not None else {}
    for cid, c in clips.items():
        if cid not in probes:
            if not Path(c['path']).exists():
                raise GateError(f'clip {cid} not found: {c["path"]}')
            probes[cid] = probe(c['path'])
    pic = edit.get('picture') or {}
    base_zoom = float(pic.get('zoom', 1.067))
    tight = float(pic.get('tight_factor', 1.12))
    rotation = float(pic.get('rotation', 0.0))

    def calib(cid):
        cal = pic.get('calibration') or {}
        disp = probes[cid].get('display') or [TL_W, TL_H]
        fit = min(TL_W / disp[0], TL_H / disp[1]) if disp[0] and disp[1] else 1.0
        return (float(cal.get('pan_px', disp[0] * fit / TL_W)), float(cal.get('tilt_px', disp[1] * fit / TL_H)))

    def transform(item, cid, default_zoom):
        zoom = float(item.get('zoom') or default_zoom)
        pan, tilt = float(item.get('pan', 0.0)), float(item.get('tilt', 0.0))
        if item.get('shift_px') and 'pan' not in item and 'tilt' not in item:
            px, ty = calib(cid)
            pan = round(float(item['shift_px'][0]) / px, 3)
            tilt = round(-float(item['shift_px'][1]) / ty, 3)
        return zoom, pan, tilt

    spine, rec = [], 0
    fade_default = int(edit.get('audio_fade_frames', 0))
    exceptions = edit.get('edge_exceptions') or {}
    for i, s in enumerate(edit['spine']):
        k = s.get('k') or f'K{i + 1}'
        cid = s.get('clip')
        if cid not in clips:
            raise GateError(f'spine {k}: unknown clip {cid!r}')
        cfps = probes[cid].get('fps') or fps
        if abs(cfps - fps) > 0.01:
            raise GateError(f'spine {k}: clip {cid} is {cfps:.3f} fps, timeline {fps:.3f}; spine clips must match')
        a = int(s['in']) if 'in' in s else fl(float(s['in_s']) * fps)
        b = int(s['out']) if 'out' in s else ce(float(s['out_s']) * fps)
        if b <= a:
            raise GateError(f'spine {k}: out <= in')
        framing = s.get('framing', 'wide')
        zdef = base_zoom * tight if framing in ('tight', 'punch', 'close-punch') else base_zoom
        zoom, pan, tilt = transform(s, cid, zdef)
        fades = list(s.get('fades') or [fade_default, fade_default])
        if 'fades' not in s:
            if f'{k} in' in exceptions:
                fades[0] = max(fades[0], 1)
            if f'{k} out' in exceptions:
                fades[1] = max(fades[1], 1)
        spine.append({'k': k, 'clip': cid, 'cam': s.get('cam', cid), 'framing': framing,
                      'src_in': a, 'src_out': b, 'rec_in': rec, 'rec_out': rec + b - a,
                      'zoom': zoom, 'pan': pan, 'tilt': tilt, 'rotation': float(s.get('rotation', rotation)),
                      'gain_db': s.get('gain_db'), 'fades': fades, 'grade': s.get('grade')})
        rec += b - a
    total = rec
    punches = []
    for i, p in enumerate(edit.get('punches') or []):
        k = p.get('k') or f'P{i + 1}'
        cid = p.get('clip')
        if cid not in clips:
            raise GateError(f'punch {k}: unknown clip {cid!r}')
        cfps = probes[cid].get('fps') or fps
        src_in = int(p['src_in']) if 'src_in' in p else fl(float(p['src_in_s']) * cfps)
        if 'len' in p:
            n_src = int(p['len'])
            n_tl = int(round(n_src * fps / cfps))
        else:
            n_tl = int(round(float(p['dur_s']) * fps))
            n_src = int(round(float(p['dur_s']) * cfps))
        at = int(p['at']) if 'at' in p else int(round(float(p['at_s']) * fps))
        if n_tl <= 0 or at < 0 or at + n_tl > total:
            raise GateError(f'punch {k}: {at}-{at + n_tl} is outside the spine (0-{total} frames)')
        zoom, pan, tilt = transform(p, cid, base_zoom)
        punches.append({'k': k, 'clip': cid, 'src_in': src_in, 'len_src': n_src, 'at': at, 'len': n_tl,
                        'zoom': zoom, 'pan': pan, 'tilt': tilt, 'rotation': float(p.get('rotation', rotation)),
                        'shows': p.get('shows', ''), 'line': p.get('line', ''), 'kind': p.get('kind', 'clip'),
                        'grade': p.get('grade')})
    punches.sort(key=lambda x: x['at'])
    for x, y in zip(punches, punches[1:]):
        if y['at'] < x['at'] + x['len']:
            raise GateError(f"punches {x['k']} and {y['k']} overlap on V2")
    ids = [s['k'] for s in spine] + [p['k'] for p in punches]
    if len(set(ids)) != len(ids):
        raise GateError('spine and punch k names must be unique')
    hook = (edit.get('hook') or {}).get('k')
    return {'fps': fps, 'clips': clips, 'probes': probes, 'spine': spine, 'punches': punches,
            'total': total, 'base_zoom': base_zoom, 'hook': hook,
            'min_aroll_s': float(edit.get('min_aroll_s', 3.0)), 'exceptions': exceptions,
            'cover_text': edit.get('cover_text', ''),
            'platforms': edit.get('platforms') or style.get('platforms') or ['instagram_reels', 'youtube_shorts'],
            'lead_frames': int(edit.get('lead_frames', 4)), 'tail_frames': int(edit.get('tail_frames', 3))}


def relayout(plan):
    rec = 0
    for s in plan['spine']:
        s['rec_in'], s['rec_out'] = rec, rec + s['src_out'] - s['src_in']
        rec = s['rec_out']
    plan['total'] = rec


def cut_plan(plan):
    fps = plan['fps']
    return {'fps': fps, 'lead_s': 0.0, 'min_aroll_s': plan['min_aroll_s'],
            'spine': [{'cam': s['cam'], 'framing': s['framing'], 'in': s['src_in'] / fps, 'out': s['src_out'] / fps,
                       'audio': plan['clips'][s['clip']].get('audio') or plan['clips'][s['clip']]['path']}
                      for s in plan['spine']],
            'cutaways': [{'at': p['at'] / fps, 'until': (p['at'] + p['len']) / fps, 'shows': p['shows']}
                         for p in plan['punches']]}


EDGE_RE = re.compile(r'\b(in|out)\s+(-?[\d.]+)\s+(ok|-> ([\d.]+)|NO CLEAN EDGE)')


def run_gates(plan, cache, max_move=0.40):
    """cut_check edges --fix (moves written into the plan, punches kept on their source moment),
    then cut_check aroll. Returns a record; raises GateError on a failing gate."""
    cc = cut_check()
    fps = plan['fps']
    anchors = []
    for p in plan['punches']:
        seg = next(s for s in plan['spine'] if s['rec_in'] <= p['at'] < s['rec_out'])
        anchors.append((seg['k'], seg['src_in'] + p['at'] - seg['rec_in']))
    moved, last = [], ''
    cache.mkdir(parents=True, exist_ok=True)
    tmp = cache / 'cut.json'
    for _ in range(3):
        cp = cut_plan(plan)
        write_json(tmp, cp)
        try:
            _code, last = capture(cc.check_edges, cp, str(tmp), True, max_move)
        except subprocess.CalledProcessError as e:
            raise GateError(f'gate edges: cannot decode audio ({e.cmd[-2] if e.cmd else ""})')
        fixed = load_json(tmp)['spine']
        changed = False
        for s, f in zip(plan['spine'], fixed):
            for side in ('in', 'out'):
                if f'{s["k"]} {side}' in plan['exceptions']:
                    continue
                new = fl(f[side] * fps) if side == 'in' else ce(f[side] * fps)
                key = 'src_' + side
                if new != s[key]:
                    moved.append(f"{s['k']} {side} {s[key] / fps:.2f}->{new / fps:.2f}")
                    s[key] = new
                    changed = True
        if not changed:
            break
        relayout(plan)
    relayout(plan)
    by_k = {s['k']: s for s in plan['spine']}
    for p, (k, src_t) in zip(plan['punches'], anchors):
        s = by_k[k]
        p['at'] = max(0, min(plan['total'] - p['len'], s['rec_in'] + src_t - s['src_in']))
    cp = cut_plan(plan)
    write_json(tmp, cp)
    _code, last = capture(cc.check_edges, cp, str(tmp), False, max_move)
    bad = []
    for ln in last.splitlines():
        m = re.match(r'K(\d+)', ln)
        if not m:
            continue
        k = plan['spine'][int(m.group(1)) - 1]['k']
        for side, _t, status, _to in EDGE_RE.findall(ln):
            if status != 'ok' and f'{k} {side}' not in plan['exceptions']:
                bad.append(f'{k} {side}: ' + ('no clean edge (add to edge_exceptions with a 1-frame fade, '
                                               'or move the cut)' if status.startswith('NO') else f'wants {status}'))
    if bad:
        raise GateError('gate edges: ' + '; '.join(bad))
    code, out = capture(cc.check_aroll, cp)
    if code:
        raise GateError('gate aroll: ' + ' | '.join(ln for ln in out.splitlines() if ln.startswith('FAIL')))
    return {'edges': 'ok' + (f' ({len(plan["exceptions"])} exceptions)' if plan['exceptions'] else ''),
            'moved': moved, 'aroll': out.strip()}


def write_back(edit, edit_path, plan):
    """Write moved edges and re-anchored punches back into edit.json, in the author's units."""
    fps = plan['fps']
    for s, e in zip(plan['spine'], edit['spine']):
        for side in ('in', 'out'):
            if f'{side}_s' in e:
                e[f'{side}_s'] = round(s['src_' + side] / fps, 4)
            else:
                e[side] = s['src_' + side]
    by_k = {p['k']: p for p in plan['punches']}
    for i, e in enumerate(edit.get('punches') or []):
        p = by_k.get(e.get('k') or f'P{i + 1}')
        if p is None:
            continue
        if 'at_s' in e:
            e['at_s'] = round(p['at'] / fps, 4)
        else:
            e['at'] = p['at']
    write_json(edit_path, edit)


# ---------------------------------------------------------------- graphics

def clip_words(plan, cid, work):
    c = plan['clips'][cid]
    w = c.get('words') or find_words(c['path'], work)
    if not w or not has_words(w):
        raise GateError(f'no word transcript for clip {cid} (run prep, or set clips.{cid}.words)')
    return w


def graphics(plan, style, style_path, work, cache, dry=False):
    """house_graphics.py on a derived edit (several spine clips become one virtual source)."""
    fps = plan['fps']
    cids = []
    for s in plan['spine']:
        if s['clip'] not in cids:
            cids.append(s['clip'])
    words = {cid: clip_words(plan, cid, work) for cid in cids}
    off = {cid: i * 1_000_000 for i, cid in enumerate(cids)}          # frames; one virtual source
    ranges = [[s['src_in'] + off[s['clip']], s['src_out'] + off[s['clip']]] for s in plan['spine']]
    cover_s = float((style.get('cover') or {}).get('seconds', 2.0))
    key_in = {'ranges': ranges, 'fps': fps, 'total': plan['total'], 'cover': plan['cover_text'],
              'platforms': plan['platforms'], 'lead': plan['lead_frames'], 'tail': plan['tail_frames'],
              'words': {c: file_sha(w) for c, w in words.items()},
              'style': {k: style.get(k) for k in ('captions', 'cover', 'platforms')},
              'shadow': (style.get('resolve') or {}).get('cover_shadow'), 'code': file_sha(HOUSE_GRAPHICS)}
    for f in ((style.get('captions') or {}).get('font'), (style.get('cover') or {}).get('font')):
        if f and Path(f).exists():
            key_in.setdefault('fonts', []).append(file_sha(f))
    key = sha(key_in)
    out = cache / f'graphics-{key}'
    rec = {'dir': str(out), 'key': key, 'cover_frames': round(cover_s * fps),
           'captions_mov': str(out / 'captions.mov'), 'cover_mov': str(out / 'cover.mov'),
           'ass': str(out / 'captions.ass'), 'srt': str(out / 'captions.srt')}
    if (out / 'captions.mov').exists() and (out / 'cover.mov').exists():
        rec['cached'] = True
        return rec
    out.mkdir(parents=True, exist_ok=True)
    if len(cids) == 1:
        transcript = words[cids[0]]
    else:
        merged = []
        for cid in cids:
            for seg in load_json(words[cid]).get('segments', []):
                for w in seg.get('words', []):
                    merged.append({'word': w.get('word', ''), 'start': float(w['start']) + off[cid] / fps,
                                   'end': float(w['end']) + off[cid] / fps})
        transcript = str(out / 'words-merged.json')
        write_json(transcript, {'segments': [{'words': merged}]})
    hg = {'transcript': transcript, 'cover_text': plan['cover_text'], 'fps': fps, 'audio_ranges': ranges,
          'duration_frames': plan['total'], 'platforms': plan['platforms'],
          'lead_frames': plan['lead_frames'], 'tail_frames': plan['tail_frames']}
    write_json(out / 'edit-graphics.json', hg)
    try:
        r = run([py(), HOUSE_GRAPHICS, out / 'edit-graphics.json', out, '--style', style_path])
    except subprocess.CalledProcessError as e:
        shutil.rmtree(out, ignore_errors=True)
        raise GateError(f'graphics: house_graphics.py failed: {e.stderr}')
    rec['cues'] = sum(1 for ln in r.stdout.splitlines() if re.match(r'\s*\d+\.\d+-\s*\d', ln))
    rec['cached'] = False
    return rec


def public_safe(plan, gfx, terms):
    hits = []
    h = banned_hit(plan['cover_text'], terms)
    if h:
        hits.append(f'cover: {h}')
    srt = Path(gfx['srt'])
    if srt.exists():
        for ln in srt.read_text(errors='replace').splitlines():
            if ln.strip() and not re.match(r'^\d+$|^\d\d:', ln.strip()):
                h = banned_hit(ln, terms)
                if h:
                    hits.append(f'captions: {h}')
    if hits:
        raise GateError('gate public-safe: banned term in ' + ', '.join(sorted(set(hits))))


# ---------------------------------------------------------------- grade plan

def item_at(plan, f):
    """What is on screen at record frame f: (kind, item, source frame)."""
    for p in plan['punches']:
        if p['at'] <= f < p['at'] + p['len']:
            return 'punch', p, p['src_in'] + round((f - p['at']) * p['len_src'] / p['len'])
    for s in plan['spine']:
        if s['rec_in'] <= f < s['rec_out']:
            return 'spine', s, s['src_in'] + f - s['rec_in']
    raise GateError(f'still frame {f} is outside the timeline')


def grade_shots(edit, plan):
    """Shots for grade_solve: {shot: {items, stills {name: rec frame}, faces|match_wall, ...}}."""
    items = [('spine', s) for s in plan['spine']] + [('punch', p) for p in plan['punches']]
    shots = (edit.get('grade') or {}).get('shots')
    auto = not shots
    if auto:
        shots = {}
        for kind, it in items:
            sh = shots.setdefault(it['clip'], {'items': [], 'kind': kind})
            sh['items'].append(it['k'])
            if kind == 'spine':
                sh['kind'] = 'spine'
    shots = {k: dict(v) for k, v in shots.items()}
    owner = {}
    for kind, it in items:
        name = it.get('grade') or next((n for n, v in shots.items() if it['k'] in (v.get('items') or [])), None)
        if name is None and it['clip'] in shots:
            name = it['clip']
        if name is None:
            raise GateError(f"grade: no shot for {it['k']} (add it to a grade.shots.<name>.items)")
        owner[it['k']] = name
        shots[name].setdefault('items', [])
        if it['k'] not in shots[name]['items']:
            shots[name]['items'].append(it['k'])
    by_k = {it['k']: it for _, it in items}
    first_face = None
    for name, sh in shots.items():
        if not sh.get('stills'):
            its = [by_k[k] for k in sh['items']]
            pick = its if len(its) <= 2 else [its[0], its[len(its) // 2]]
            sh['stills'] = {f'{name}_{i + 1}': (it['rec_in'] + it['rec_out']) // 2 if 'rec_in' in it
                            else it['at'] + it['len'] // 2 for i, it in enumerate(pick)}
        if not sh.get('faces') and not sh.get('match_wall'):
            if sh.get('kind', 'spine') == 'spine' or any(by_k[k] in plan['spine'] for k in sh['items']):
                sh['faces'] = {n: 'auto' for n in sh['stills']}
        if sh.get('faces') and first_face is None:
            first_face = name
    for name, sh in shots.items():
        if not sh.get('faces') and not sh.get('match_wall'):
            if first_face is None:
                raise GateError(f'grade: shot {name} has no face and no A-roll shot to match; set grade.shots')
            box = [270, 480, 810, 1440]
            sh['match_wall'] = {'box': box, 'ref_shot': first_face, 'ref_still': 0, 'ref_box': box}
            sh['_default_match'] = True
    order = sorted(shots, key=lambda n: 0 if shots[n].get('faces') else 1)   # refs solve first
    return {n: shots[n] for n in order}, owner


def still_content(plan, f):
    kind, it, src = item_at(plan, f)
    c = plan['clips'][it['clip']]
    return [c['path'], src, it['zoom'], it['pan'], it['tilt'], it['rotation'], c.get('input')]


# ---------------------------------------------------------------- lock

def lock_path():
    return Path(os.environ.get('REEL_LOCK') or Path.home() / '.cache' / 'reel' / 'resolve.lock')


def pid_alive(pid):
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def lock_read():
    p = lock_path()
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


PASSTHROUGH_CDL = {'slope': 1.0, 'offset': [0.0, 0.0, 0.0], 'sat': 1.0}


def apply_cdl_overrides(edit, plan, gr):
    """Fixed CDLs that skip the solve. A shot's `cdl` in edit.json wins ("passthrough" or a
    {slope, offset, sat} dict). Otherwise a shot whose clips all carry a display-referred tag
    (phone / Rec.709 / HLG) passes through: the solve's face anchor and log-oriented saturation
    (0.68) turned a sunlit phone A-roll grey and dull (reviewer, 2026-09-29), while the look LUT
    alone kept it right. Set `"solve": true` on the shot to force the solve anyway."""
    shots = (edit.get('grade') or {}).get('shots') or {}
    by_k = {it['k']: it for it in plan['spine'] + plan['punches']}
    done = []
    for name in list(gr.get('cdl') or {}):
        sh = shots.get(name) or {}
        fixed = sh.get('cdl')
        if fixed is None and not sh.get('solve'):
            items = [by_k[k] for k in (sh.get('items') or []) if k in by_k] or \
                    [it for it in by_k.values() if it['clip'] == name]
            tags = {(plan.get('probes', {}).get(it['clip']) or {}).get('tagged_input')
                    for it in items}
            if items and None not in tags and all(not (plan['clips'][it['clip']].get('input') or '').lower().startswith('canon')
                                                  for it in items):
                fixed = 'passthrough'
        if fixed is not None:
            gr['cdl'][name] = dict(PASSTHROUGH_CDL) if fixed == 'passthrough' else fixed
            done.append(name)
    return done


def lock_stale(info):
    try:
        age = time.time() - dt.datetime.fromisoformat(info['started_at']).timestamp()
    except (KeyError, ValueError, TypeError):
        return True, 'unreadable'
    if age > LOCK_MAX_AGE_S:
        return True, f'older than {LOCK_MAX_AGE_S // 3600} h'
    if info.get('host') == socket.gethostname() and pid_alive(info.get('pid')) is False:
        return True, f"pid {info.get('pid')} is gone"
    return False, ''


def lock_describe(info):
    return (f"{info.get('owner')} (pid {info.get('pid') or '-'} on {info.get('host')}, since "
            f"{info.get('started_at')}{', ' + info['note'] if info.get('note') else ''})")


def lock_acquire(owner, note='', pid=0):
    """Returns (acquired_now, message). acquired_now False + no exception = already ours."""
    p = lock_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    info = {'owner': owner, 'pid': pid, 'host': socket.gethostname(),
            'started_at': dt.datetime.now().isoformat(timespec='seconds'), 'note': note}
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            cur = lock_read()
            # Same owner is only re-entrant for the same process (or a manual, pid-less hold).
            # Two parallel builds with one owner name must still queue (batch run 2026-09-29).
            if cur and cur.get('owner') == owner and (not pid or not cur.get('pid') or cur.get('pid') == pid):
                return False, 'already held by ' + lock_describe(cur)
            stale, why = lock_stale(cur or {})
            if not stale:
                raise BackendError('LOCKED: Resolve is held by ' + lock_describe(cur))
            with contextlib.suppress(FileNotFoundError):
                p.unlink()
            note_msg = f"took over a stale lock ({why}) from {(cur or {}).get('owner')}"
            info['note'] = (note + '; ' if note else '') + note_msg
            continue
        with os.fdopen(fd, 'w') as f:
            json.dump(info, f)
        return True, 'acquired' + (f": {info['note']}" if 'took over' in info['note'] else '')
    raise BackendError('LOCKED: could not create ' + str(p))


def lock_release(owner, force=False):
    cur = lock_read()
    if not cur:
        return 'free'
    if cur.get('owner') != owner and not force:
        raise BackendError('LOCKED: held by ' + lock_describe(cur) + ' (not you; --force to break it)')
    with contextlib.suppress(FileNotFoundError):
        lock_path().unlink()
    return 'released'


@contextlib.contextmanager
def resolve_lock(owner, note):
    wait = float(os.environ.get('REEL_LOCK_WAIT') or 0)   # seconds to queue behind another holder
    deadline = time.monotonic() + wait
    while True:
        try:
            got, _msg = lock_acquire(owner, note, pid=os.getpid())
            break
        except BackendError as e:
            if not str(e).startswith('LOCKED') or time.monotonic() >= deadline:
                raise
            time.sleep(15)
    try:
        yield
    finally:
        if got:
            with contextlib.suppress(BackendError):
                lock_release(owner)


def cmd_lock(a):
    if a.action == 'status':
        cur = lock_read()
        if not cur:
            log('free')
        else:
            stale, why = lock_stale(cur)
            log('held by ' + lock_describe(cur) + (f' [stale: {why}]' if stale else ''))
        return 0
    if not a.owner:
        raise GateError('--owner is required')
    if a.action == 'acquire':
        _got, msg = lock_acquire(a.owner, a.note or '', pid=a.pid)
        log(msg)
    else:
        log(lock_release(a.owner, a.force))
    return 0


# ---------------------------------------------------------------- Resolve backends

def connect_resolve():
    """Resolve's own scripting API (no MCP). Needs Resolve Studio running with
    Preferences > System > General > External scripting using = Local."""
    api = os.environ.get('RESOLVE_SCRIPT_API',
                         '/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting')
    lib = os.environ.get('RESOLVE_SCRIPT_LIB',
                         '/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so')
    os.environ.setdefault('RESOLVE_SCRIPT_LIB', lib)
    mod = str(Path(api) / 'Modules')
    if mod not in sys.path:
        sys.path.append(mod)
    try:
        import DaVinciResolveScript as dvr   # noqa: N813
    except ImportError as e:
        raise BackendError(f'cannot load DaVinciResolveScript / fusionscript ({e}); check RESOLVE_SCRIPT_API/LIB')
    r = dvr.scriptapp('Resolve')
    if r is None:
        raise BackendError('Resolve is not reachable: is it running, with External scripting = Local?')
    return r


class ResolveBackend:
    """Drives Resolve through resolve_ops.py, loaded with the live `resolve` injected as a global
    (the same helpers the MCP route execs). Only a few steps resolve_ops has no helper for are here:
    reuse of an existing project / media, per-item transform, gain and fades, a vignette in gain form,
    and the .drp export."""

    def __init__(self, ops_path=RESOLVE_OPS):
        self.ops_path = Path(ops_path)
        self.resolve = self.ops = self.p = self.tl = None
        self.calls = []

    def connect(self):
        self.resolve = connect_resolve()
        ns = {'__name__': 'resolve_ops', '__file__': str(self.ops_path), 'resolve': self.resolve}
        exec(compile(self.ops_path.read_text(), str(self.ops_path), 'exec'), ns)   # noqa: S102
        self.ops = ns
        return self.resolve.GetVersionString() if hasattr(self.resolve, 'GetVersionString') else ''

    def open_project(self, name, fps_str='29.97'):
        pm = self.resolve.GetProjectManager()
        if name in (pm.GetProjectListInCurrentFolder() or []):
            pm.SaveProject()
            self.p = pm.LoadProject(name)
            if not self.p:
                raise BackendError(f'cannot open project {name}')
            return 'opened'
        self.p = self.ops['new_project'](name, TL_W, TL_H, fps_str)
        return 'created'

    def import_media(self, paths):
        mp = self.p.GetMediaPool()
        root = mp.GetRootFolder()
        mp.SetCurrentFolder(root)
        have = {}
        for c in root.GetClipList() or []:
            fp = c.GetClipProperty('File Path')
            if fp:
                have[os.path.realpath(fp)] = c
        need = [p for p in paths if os.path.realpath(p) not in have]
        if need:
            for c in mp.ImportMedia(need) or []:
                have[os.path.realpath(c.GetClipProperty('File Path'))] = c
        missing = [p for p in paths if os.path.realpath(p) not in have]
        if missing:
            raise BackendError('import failed: ' + ', '.join(missing))
        return {p: have[os.path.realpath(p)] for p in paths}

    def set_clip_input(self, item, space):
        return self.ops['set_clip_input'](self.p, item, space)

    def build_timeline(self, name, spine, punches, zoom, rotation):
        mp = self.p.GetMediaPool()
        old = [self.p.GetTimelineByIndex(i) for i in range(1, (self.p.GetTimelineCount() or 0) + 1)]
        old = [t for t in old if t and t.GetName() == name]
        if old:
            mp.DeleteTimelines(old)
        self.tl = self.ops['build_timeline'](self.p, name, spine, punches, zoom=zoom, rotation=rotation)
        if not self.tl:
            raise BackendError('timeline was not created')
        n1 = len(self.tl.GetItemListInTrack('video', 1) or [])
        n2 = len(self.tl.GetItemListInTrack('video', 2) or [])
        if n1 != len(spine) or n2 != len(punches):
            raise BackendError(f'timeline has V1 {n1}/{len(spine)} and V2 {n2}/{len(punches)} items')
        return self.tl.GetEndFrame() - self.tl.GetStartFrame()

    def _item(self, track, idx, kind='video'):
        return (self.tl.GetItemListInTrack(kind, track) or [])[idx]

    def set_transform(self, track, idx, zoom, pan, tilt, rotation):
        it = self._item(track, idx)
        ok = True
        for k, v in (('ZoomX', zoom), ('ZoomY', zoom), ('Pan', pan), ('Tilt', tilt), ('RotationAngle', rotation)):
            ok &= bool(it.SetProperty(k, float(v)))
        return ok

    def export_stills(self, frames, out_dir):
        return self.ops['export_di_stills'](self.p, self.tl, frames, str(out_dir))

    def apply_grade(self, track, idx, cdl, lut, vignette, geom):
        it = self._item(track, idx)
        mode = geom.get('mode', 'gain')
        ok = self.ops['apply_grade'](it, cdl, lut, vignette if mode == 'brightness' else 0)
        if vignette and mode != 'brightness':
            ok &= self._vignette_gain(it, cdl['slope'], vignette, geom)
        return bool(ok)

    def _vignette_gain(self, it, slope, amount, g):
        """REFERENCE.md vignette, in the gain form measured on renders (the Brightness form crushed
        the bottom third to black): Gain = 2^-((amount/slope)/0.07329), inverted soft ellipse, sized and
        centred so it sits in the same screen place on a punched-in item."""
        comp = it.AddFusionComp()
        mi, mo = comp.FindTool('MediaIn1'), comp.FindTool('MediaOut1')
        bc = comp.AddTool('BrightnessContrast', -32768, -32768)
        el = comp.AddTool('EllipseMask', -32768, -32768)
        for k, v in (('Width', g['w']), ('Height', g['h']), ('SoftEdge', 0.45), ('Invert', 1.0)):
            el.SetInput(k, v)
        el.SetInput('Center', {1: g['cx'], 2: g['cy']})
        bc.SetInput('Gain', 2 ** -((amount / slope) / DI_PER_STOP))
        bc.ConnectInput('Input', mi)
        bc.ConnectInput('EffectMask', el)
        mo.ConnectInput('Input', bc)
        return True

    def add_graphics(self, captions_mov, cover_mov, frames, cover_frames):
        return self.ops['add_graphics'](self.p, self.tl, captions_mov, cover_mov, frames, cover_frames)

    def voice_chain(self, gain_db):
        return self.ops['voice_chain'](self.tl, gain_db)

    def set_audio(self, idx, gain_db=None, fades=None):
        it = self._item(1, idx, 'audio')
        ok = True
        if gain_db is not None:
            ok &= bool(it.SetProperty('AudioVolume', float(gain_db)))
        if fades and any(fades):
            ok &= bool(it.SetFades({'FadeIn': int(fades[0]), 'FadeOut': int(fades[1])}))
        return ok

    def render(self, target_dir, name, timeout_s):
        st = self.ops['render'](self.p, str(target_dir), name, timeout_s=timeout_s)
        f = Path(target_dir) / f'{name}.mp4'
        if not f.exists():
            raise BackendError(f'render did not write {f} (status {st})')
        return str(f), st

    def export_drp(self, path):
        pm = self.resolve.GetProjectManager()
        pm.SaveProject()
        if not pm.ExportProject(self.p.GetName(), str(path), True):
            raise BackendError(f'ExportProject failed: {path}')
        return str(path)

    def close(self):
        if self.resolve:
            with contextlib.suppress(Exception):
                self.resolve.GetProjectManager().SaveProject()


class FakeBackend:
    """Records every call; for --dry-run (the plan of Resolve calls) and tests. still_fn(path) and
    render_fn(path, frames) may write real files so the rest of the pipeline runs."""

    def __init__(self, still_fn=None, render_fn=None):
        self.calls, self.still_fn, self.render_fn = [], still_fn, render_fn
        self.frames = 0

    def _c(self, _call, **kw):
        self.calls.append([_call, kw])

    def connect(self):
        self._c('connect')
        return 'fake'

    def open_project(self, name, fps_str='29.97'):
        self._c('open_project', name=name, fps=fps_str)
        return 'fake'

    def import_media(self, paths):
        self._c('import_media', paths=list(paths))
        return {p: f'item:{Path(p).name}' for p in paths}

    def set_clip_input(self, item, space):
        self._c('set_clip_input', item=item, space=space)
        return space

    def build_timeline(self, name, spine, punches, zoom, rotation):
        self._c('build_timeline', name=name, spine=[list(x) for x in spine], punches=[list(x) for x in punches],
                zoom=zoom, rotation=rotation)
        self.frames = sum(b - a for _i, a, b in spine)
        return self.frames

    def set_transform(self, track, idx, zoom, pan, tilt, rotation):
        self._c('set_transform', track=track, idx=idx, zoom=zoom, pan=pan, tilt=tilt, rotation=rotation)
        return True

    def export_stills(self, frames, out_dir):
        self._c('export_stills', frames=dict(frames), out_dir=str(out_dir))
        ok = {}
        for n in frames:
            if self.still_fn:
                self.still_fn(Path(out_dir) / f'di_{n}.tif')
            ok[n] = True
        return ok

    def apply_grade(self, track, idx, cdl, lut, vignette, geom):
        self._c('apply_grade', track=track, idx=idx, slope=cdl.get('slope'), lut=lut, vignette=vignette,
                geom=geom)
        return True

    def add_graphics(self, captions_mov, cover_mov, frames, cover_frames):
        self._c('add_graphics', captions=captions_mov, cover=cover_mov, frames=frames, cover_frames=cover_frames)

    def voice_chain(self, gain_db):
        self._c('voice_chain', gain_db=gain_db)

    def set_audio(self, idx, gain_db=None, fades=None):
        self._c('set_audio', idx=idx, gain_db=gain_db, fades=fades)
        return True

    def render(self, target_dir, name, timeout_s):
        self._c('render', target_dir=str(target_dir), name=name)
        f = Path(target_dir) / f'{name}.mp4'
        if self.render_fn:
            self.render_fn(f, self.frames)
        return str(f), {'JobStatus': 'Complete' if f.exists() else 'Planned'}

    def export_drp(self, path):
        self._c('export_drp', path=str(path))
        if self.render_fn:
            Path(path).write_bytes(b'fake drp')
        return str(path)

    def close(self):
        self._c('close')


# ---------------------------------------------------------------- build

def true_peak(path):
    r = run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-map', '0:a:0', '-af', 'ebur128=peak=true',
             '-f', 'null', '-'], check=False)
    m = re.findall(r'Peak:\s+(-?[\d.]+|-inf)\s+dBFS', r.stderr)
    i = re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)
    tp = float(m[-1]) if m and m[-1] != '-inf' else None
    return tp, (float(i[-1]) if i else None)


def vignette_geom(plan, it, mode):
    """Ellipse size/centre in image units so the vignette sits in the same screen place on a
    punched-in item (Fusion runs before the Inspector zoom/pan)."""
    disp = plan['probes'][it['clip']].get('display') or [TL_W, TL_H]
    fit = min(TL_W / disp[0], TL_H / disp[1]) if disp[0] and disp[1] else 1.0
    iw, ih = disp[0] * fit * it['zoom'], disp[1] * fit * it['zoom']
    k = plan['base_zoom'] / it['zoom']
    g = {'mode': mode, 'w': round(1.35 * k, 5), 'h': round(0.95 * k, 5), 'cx': 0.5, 'cy': 0.5}
    if it['rotation'] == 0:
        pan_px, tilt_px = disp[0] * fit / TL_W, disp[1] * fit / TL_H
        g['cx'] = round(0.5 - it['pan'] * pan_px / iw, 6)
        g['cy'] = round(0.5 - it['tilt'] * tilt_px / ih, 6)
    return g


def detect_face(tif):
    """Largest face on a DWG/DI still (OpenCV Haar, frontal then profile); inner-face box."""
    import cv2
    import numpy as np
    import tifffile
    sys.path.insert(0, str(SCRIPTS))
    from dwg_look import to_display
    di = tifffile.imread(str(tif)).astype(float) / 65535
    rgb = (to_display(di[..., :3]) * 255).astype(np.uint8)
    best = None
    if not hasattr(cv2, 'CascadeClassifier'):  # OpenCV 5 dropped Haar: use YuNet
        return detect_face_yunet(cv2, rgb)
    gray = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    for name in ('haarcascade_frontalface_default.xml', 'haarcascade_profileface.xml'):
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        for flip in (False, True):
            img = gray[:, ::-1] if flip else gray
            for x, y, w, h in casc.detectMultiScale(img, 1.1, 5, minSize=(60, 60)):
                if flip:
                    x = img.shape[1] - x - w
                if best is None or w * h > best[2] * best[3]:
                    best = (int(x), int(y), int(w), int(h))
        if best:
            break
    if not best:
        return None
    x, y, w, h = best
    return [x + int(0.15 * w), y + int(0.2 * h), x + w - int(0.15 * w), y + h - int(0.1 * h)]


YUNET_URL = ('https://github.com/opencv/opencv_zoo/raw/main/models/'
             'face_detection_yunet/face_detection_yunet_2023mar.onnx')
YUNET_SHA256 = '8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'


def yunet_model():
    """YuNet ONNX model, fetched once into ~/.cache/reel/models and checked by SHA-256."""
    import hashlib
    import urllib.request
    path = Path.home() / '.cache' / 'reel' / 'models' / 'face_detection_yunet_2023mar.onnx'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != YUNET_SHA256:
        path.unlink()
        raise RuntimeError('YuNet model checksum mismatch; deleted, run again')
    return path


def detect_face_yunet(cv2, rgb):
    """Largest face via OpenCV's YuNet detector; same inner-face box as the Haar path."""
    h0, w0 = rgb.shape[:2]
    s = min(1.0, 1280 / max(h0, w0))
    img = cv2.resize(rgb, (int(w0 * s), int(h0 * s))) if s < 1 else rgb
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    det = cv2.FaceDetectorYN.create(str(yunet_model()), '', (bgr.shape[1], bgr.shape[0]), 0.7)
    _, faces = det.detect(bgr)
    if faces is None or not len(faces):
        return None
    x, y, w, h = (float(v) / s for v in max(faces, key=lambda f: f[2] * f[3])[:4])
    x, y, w, h = int(x), int(y), int(w), int(h)
    return [x + int(0.15 * w), y + int(0.2 * h), x + w - int(0.15 * w), y + h - int(0.1 * h)]


def bars(tif):
    """True when a whole edge row/column is pure black (DI code 0 = outside the picture)."""
    import numpy as np
    import tifffile
    d = tifffile.imread(str(tif))
    d = d[..., :3].astype(float) / (65535 if d.dtype == np.uint16 else 255)
    edges = [d[:, :3], d[:, -3:], d[:3, :], d[-3:, :]]
    return any(float(e.max()) < 0.003 for e in edges)


def grade_solve_mod():
    sys.path.insert(0, str(SCRIPTS))
    return load_module('grade_solve', SCRIPTS / 'grade_solve.py')


def solve_grade(edit, plan, style, style_path, backend, cache, dry):
    """Stills (cached on what is on screen at each still) + grade_solve (cached on stills + settings)."""
    shots, owner = grade_shots(edit, plan)
    g = (style.get('resolve') or {}).get('grade') or {}
    stills = {n: f for sh in shots.values() for n, f in sh['stills'].items()}
    content = {n: still_content(plan, f) for n, f in stills.items()}
    cam = g.get('camera_input')
    inputs = {cid: c.get('input') or (plan.get('probes', {}).get(cid) or {}).get('tagged_input') or cam
              for cid, c in plan['clips'].items()}
    skey = sha({'content': content, 'cam': cam, 'inputs': inputs})
    sdir = cache / f'stills-{skey}'
    look_file = None
    if g.get('look_profile'):
        lp = Path(style_path).resolve().parents[1] / g['look_profile']
        look_file = file_sha(lp) if lp.exists() else str(lp)
    over = {k: v for k, v in (edit.get('grade') or {}).items() if k != 'shots'}
    solve_in = {'skey': skey, 'shots': {n: {k: v for k, v in sh.items() if k != 'items'} for n, sh in shots.items()},
                'grade': {k: g.get(k) for k in ('look_profile', 'face_ire', 'black_code', 'sat', 'wb_target_709')},
                'look': look_file, 'over': over,
                'code': [file_sha(SCRIPTS / 'grade_solve.py'), file_sha(SCRIPTS / 'dwg_look.py')]}
    gkey = sha(solve_in)
    cdl_path = sdir / f'cdl-{gkey}.json'
    rec = {'stills_dir': str(sdir), 'stills': stills, 'owner': owner, 'stills_cached': False, 'solve_cached': False,
           'default_match': [n for n, sh in shots.items() if sh.get('_default_match')]}
    if cdl_path.exists():
        rec.update(stills_cached=True, solve_cached=True, cdl=load_json(cdl_path))
        return rec
    have = all((sdir / f'di_{n}.tif').exists() for n in stills)
    if not have:
        if dry:
            backend.export_stills(stills, sdir)
            rec['cdl'] = {n: {'slope': 1.0, 'offset': [0, 0, 0], 'sat': g.get('sat', 0.68), '_dry': True}
                          for n in shots}
            return rec
        sdir.mkdir(parents=True, exist_ok=True)
        ok = backend.export_stills(stills, sdir)
        if not all((sdir / f'di_{n}.tif').exists() for n in stills):
            raise BackendError(f'still export failed: {ok}')
        barred = [n for n in stills if bars(sdir / f'di_{n}.tif')]
        if barred:
            shutil.rmtree(sdir, ignore_errors=True)
            raise GateError('gate picture: black bars on stills ' + ', '.join(barred) +
                            ': set picture.rotation / zoom (e.g. rotation -90 or 90 with zoom 1.91)')
    else:
        rec['stills_cached'] = True
    cfg = {k: v for k, v in over.items() if k in ('face_ire', 'black_code', 'sat', 'wb_target_709', 'look')}
    cfg['shots'] = {}
    for n, sh in shots.items():
        sn = list(sh['stills'])
        out = {'stills': [f'di_{x}.tif' for x in sn]}
        if sh.get('faces'):
            faces = sh['faces']
            if isinstance(faces, dict):
                lst = []
                for x, box in faces.items():
                    if box == 'auto':
                        box = detect_face(sdir / f'di_{x}.tif')
                        if box is None:
                            continue
                    lst.append([sn.index(x), box])
                faces = lst
            if not faces:
                raise GateError(f'grade: no face found on the {n} stills ({", ".join(sn)} in {sdir}); '
                                f'give grade.shots.{n}.faces boxes (1080x1920 px) or a match_wall')
            out['faces'] = faces
        else:
            out['match_wall'] = sh['match_wall']
        if sh.get('manual_wb'):
            out['manual_wb'] = sh['manual_wb']
        if sh.get('slope_min') is not None:
            out['slope_min'] = sh['slope_min']
        cfg['shots'][n] = out
    write_json(sdir / f'grade-{gkey}.json', cfg)
    if dry:
        rec['cdl'] = {n: {'slope': 1.0, 'offset': [0, 0, 0], 'sat': g.get('sat', 0.68), '_dry': True} for n in shots}
        return rec
    gs = grade_solve_mod()
    with contextlib.redirect_stdout(io.StringIO()):
        cdl = gs.solve(sdir / f'grade-{gkey}.json', style_path, write=False, quiet=True)
    write_json(cdl_path, cdl)
    rec['cdl'] = cdl
    return rec


def make_cache(out_dir):
    """Stills, graphics and gate files live next to the renders (Resolve links to the graphics),
    never tracked by git."""
    cache = Path(out_dir) / '.reel-cache'
    cache.mkdir(parents=True, exist_ok=True)
    gi = cache / '.gitignore'
    if not gi.exists():
        gi.write_text('*\n')
    return cache


def cmd_build(a, backend=None):
    if getattr(a, 'wait_lock', 0):
        os.environ['REEL_LOCK_WAIT'] = str(a.wait_lock)
    t0 = time.time()
    edit_path = Path(a.edit).resolve()
    work = edit_path.parent
    edit = load_json(edit_path)
    style_path = str(Path(a.style).resolve())
    style = load_json(style_path)
    g = {**GRADE_DEFAULTS, **((style.get('resolve') or {}).get('grade') or {})}
    ver = a.version
    pid = edit.get('id') or work.name
    out_dir = Path(edit['out_dir']) if edit.get('out_dir') else work
    out_dir = out_dir if out_dir.is_absolute() else (work / out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = make_cache(out_dir)
    master = out_dir / f'{pid}_{ver}.mp4'
    rec = {'version': ver, 'dry_run': bool(a.dry_run), 'edit': str(edit_path), 'style': style_path,
           'started': dt.datetime.now().isoformat(timespec='seconds')}
    report = work / f'build-{ver}.json'
    lines = []
    if not a.dry_run and master.exists() and not a.force:      # leave that version's record alone
        log(f'FAIL {master.name} exists: use a new --version, or --force to replace it')
        return 2
    try:
        if not (edit.get('cover_text') or '').strip():
            raise GateError('gate cover: edit.json needs a public-safe cover_text')
        plan = normalize(edit, edit_path, style)
        gates = run_gates(plan, cache)
        rec['gates'] = gates
        if gates['moved'] and not a.dry_run:
            write_back(edit, edit_path, plan)
        lines.append(f"gates: edges {gates['edges']}, {len(gates['moved'])} moved"
                     f"{' (written to edit.json)' if gates['moved'] and not a.dry_run else ''}; "
                     f"aroll {gates['aroll'].replace('ok: ', '')}")
        gfx = graphics(plan, style, style_path, work, cache)
        _bp, terms = banned_terms(style, style_path)
        if terms:
            public_safe(plan, gfx, terms)
        rec['graphics'] = gfx
        lines.append(f"graphics: {'cached' if gfx['cached'] else 'made'} {gfx['dir']}")
        rec['plan'] = {k: plan[k] for k in ('fps', 'total', 'spine', 'punches')}
        backend = backend or (FakeBackend() if a.dry_run else ResolveBackend())
        owner = a.owner or os.environ.get('REEL_OWNER') or f'reel-build:{work.name}'
        lock = contextlib.nullcontext() if a.dry_run else resolve_lock(owner, f'build {pid} {ver}')
        with lock:
            try:
                res = resolve_section(a, edit, plan, style, style_path, g, backend, cache, out_dir, pid, ver, gfx)
            finally:
                with contextlib.suppress(Exception):
                    backend.close()
        rec['resolve'] = res
        if isinstance(backend, FakeBackend):
            rec['resolve_calls'] = backend.calls
        gr = res['grade']
        lines.append(f"grade: stills {'cached' if gr['stills_cached'] else 'exported'}, solve "
                     f"{'cached' if gr['solve_cached'] else 'run'}; " + ', '.join(
                         f"{n} slope {c.get('slope')} face {c.get('anchor_ire', '-')}" for n, c in gr['cdl'].items())
                     + (f"; default wall match: {', '.join(gr['default_match'])}" if gr['default_match'] else '')
                     + (f"; passthrough (no solve): {', '.join(gr['passthrough'])}" if gr.get('passthrough') else ''))
        if a.dry_run:
            counts = {}
            for c in backend.calls:
                counts[c[0]] = counts.get(c[0], 0) + 1
            lines.append('dry-run plan: ' + ', '.join(f'{k} x{v}' for k, v in counts.items()))
            code = 0
        else:
            lines.append(f"resolve: project {res['project']} ({res['project_state']}), timeline {res['timeline']}, "
                         f"drp {Path(res['drp']).name}")
            lines.append(f"render: {Path(res['render']).name} TP {res['render_tp']} dBTP, voice {res['voice_gain_db']} dB"
                         + (f" (re-rendered: {res['rerender']})" if res.get('rerender') else ''))
            fin = finish(res['render'], master, style)
            rec['finish'] = fin
            lines.append(f"finish: {master.name} {fin.get('normalization', '')}".rstrip())
            q = qa_run(master, edit_path, gfx['ass'], style_path, plan=plan, edit=edit)
            rec['qa'] = {'verdict': q['verdict'], 'report': q['report'], 'sheet': q['sheet']}
            lines.append(q['line'])
            lines.append(f"review sheet: {q['sheet']}")
            code = 0 if q['verdict'] != 'fail' else 2
            if code:
                rec['error'] = 'gate qa: ' + ', '.join(q['fails'])
        rec['status'] = 'ok' if code == 0 else 'qa-fail'
    except GateError as e:
        rec.update(status='gate-fail', error=str(e))
        lines.append(f'FAIL {e}')
        code = 2
    except (BackendError, subprocess.CalledProcessError) as e:
        msg = str(e) if isinstance(e, BackendError) else f'{e.cmd[1] if len(e.cmd) > 1 else e.cmd}: {e.stderr}'
        rec.update(status='resolve-fail', error=msg)
        lines.append(f'FAIL {msg}')
        code = 3
    except Exception as e:                  # a bug here still leaves a build record
        import traceback
        rec.update(status='error', error=f'{type(e).__name__}: {e}', traceback=traceback.format_exc()[-2000:])
        lines.append(f"FAIL {rec['error']}")
        code = 3
    rec['seconds'] = round(time.time() - t0, 1)
    write_json(report, rec)
    head = f"build {ver}{' (dry run)' if a.dry_run else ''}: {rec['status']} in {rec['seconds']} s -> {report.name}"
    for ln in ([head] + lines)[:10]:
        log(ln)
    return code


def resolve_section(a, edit, plan, style, style_path, g, backend, cache, out_dir, pid, ver, gfx):
    fps = plan['fps']
    res = {'backend': type(backend).__name__}
    res['resolve_version'] = backend.connect()
    project = edit.get('project') or pid
    timeline = f"{edit.get('timeline') or pid} {ver}"
    res.update(project=project, timeline=timeline)
    res['project_state'] = backend.open_project(project, '29.97' if abs(fps - FPS_DEFAULT) < 0.01 else str(round(fps, 3)))
    paths = []
    for it in plan['spine'] + plan['punches']:
        p = plan['clips'][it['clip']]['path']
        if p not in paths:
            paths.append(p)
    items = backend.import_media(paths)
    cam = g.get('camera_input')
    res['clip_input'] = {}
    for cid, c in plan['clips'].items():
        if c['path'] in items:
            space = c.get('input') or (plan.get('probes', {}).get(cid) or {}).get('tagged_input') or cam
            if space:
                res['clip_input'][cid] = backend.set_clip_input(items[c['path']], space)
    spine = [(items[plan['clips'][s['clip']]['path']], s['src_in'], s['src_out']) for s in plan['spine']]
    punches = [(items[plan['clips'][p['clip']]['path']], p['src_in'], p['len_src'], p['at']) for p in plan['punches']]
    backend.build_timeline(timeline, spine, punches, plan['base_zoom'], plan['spine'][0]['rotation'])
    for track, lst in ((1, plan['spine']), (2, plan['punches'])):
        for i, it in enumerate(lst):
            if it['zoom'] != plan['base_zoom'] or it['pan'] or it['tilt'] or it['rotation'] != plan['spine'][0]['rotation']:
                backend.set_transform(track, i, it['zoom'], it['pan'], it['tilt'], it['rotation'])
    gr = solve_grade(edit, plan, style, style_path, backend, cache, a.dry_run)
    gr['passthrough'] = apply_cdl_overrides(edit, plan, gr)
    res['grade'] = gr
    lut, vig = g.get('lut_resolve'), float(g.get('vignette') or 0)
    if not lut:
        raise GateError('style resolve.grade.lut_resolve is not set (generate it: dwg_look.py write)')
    # Display-referred (phone / Rec.709) shots: 'look' = look LUT only; 'none' = no grade at all.
    # A reviewer found even the LUT wrong on phone A-roll and removed every node (2026-09-30).
    dr_mode = g.get('display_referred', 'look')
    for track, lst in ((1, plan['spine']), (2, plan['punches'])):
        for i, it in enumerate(lst):
            shot = gr['owner'][it['k']]
            if dr_mode == 'none' and shot in (gr.get('passthrough') or []):
                continue
            if not backend.apply_grade(track, i, gr['cdl'][shot], lut, vig, vignette_geom(plan, it, g.get('vignette_mode', 'gain'))):
                raise BackendError(f"apply_grade failed on {it['k']}")
    cap, cov = gfx['captions_mov'], gfx['cover_mov']
    if not a.dry_run:                    # a fresh file name per version, so Resolve imports it again
        cap, cov = link_copy(cap, f'captions-{ver}.mov'), link_copy(cov, f'cover-{ver}.mov')
    backend.add_graphics(cap, cov, plan['total'], gfx['cover_frames'])
    gain = float(edit.get('voice_gain_db', g.get('voice_gain_db', 4.0)))
    res['voice_gain_db'] = gain
    apply_audio(backend, plan, gain, 0.0)
    name = f'{pid}_{ver}_resolve'
    if not a.dry_run:
        for old in (out_dir / f'{name}.mp4', out_dir / f'{name}-r2.mp4'):
            if old.exists():
                old.unlink()
    timeout = max(300, int(plan['total'] / fps * 20))
    render, st = backend.render(out_dir, name, timeout)
    res.update(render=render, render_status=st)
    if a.dry_run:
        res['drp'] = backend.export_drp(out_dir / f'{pid}_{ver}.drp')
        return res
    tp, li = true_peak(render)
    res['render_tp'], res['render_lufs'] = tp, li
    # Overs in Resolve's float export survive the AAC file; finish-reel + peak_guard limit them.
    # Pulling the whole mix down for one transient left the voice ~-31 LUFS and a noisy +15 dB lift
    # (live test 2026-09-29), so only a gross over triggers the lower-gain re-render.
    if tp is not None and tp > 6.0:                   # one retry: bring the export under -1.5 dBTP
        delta = round(-1.5 - tp, 1)
        apply_audio(backend, plan, gain + delta, delta)
        render2, st2 = backend.render(out_dir, name + '-r2', timeout)
        tp2, li2 = true_peak(render2)
        res['rerender'] = f'gain {gain:+.1f} -> {gain + delta:+.1f} dB, TP {tp} -> {tp2}'
        res.update(render=render2, render_status=st2, render_tp=tp2, render_lufs=li2, voice_gain_db=gain + delta)
    res['drp'] = backend.export_drp(out_dir / f'{pid}_{ver}.drp')
    return res


def apply_audio(backend, plan, gain, delta):
    backend.voice_chain(gain)
    for i, s in enumerate(plan['spine']):
        gd = None if s['gain_db'] is None else float(s['gain_db']) + delta
        if gd is not None or any(s['fades']):
            backend.set_audio(i, gd, s['fades'])


def link_copy(src, name):
    dst = Path(src).parent / name
    if not dst.exists():
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return str(dst)


def finish(render, master, style):
    au = style.get('audio') or {}
    mode = au.get('loudnorm', 'two-pass')
    mode = mode if mode in ('two-pass', 'single', 'off') else 'two-pass'
    if master.exists():
        master.unlink()
    cmd = [py(), FINISH, '--spine', render, '--output', master, '--skip-lut', '--no-eq', '--no-captions',
           '--orient', 'none', '--cover-text', '', '--loudnorm-mode', mode,
           '--loudnorm-i', str(au.get('target_i', -16)), '--loudnorm-tp', str(au.get('true_peak', -1.5)),
           '--loudnorm-lra', str(au.get('lra', 11))]
    try:
        r = run(cmd)
    except subprocess.CalledProcessError as e:
        raise BackendError(f'finish-reel.py failed: {e.stderr}')
    m = re.search(r'Normalization Type:\s*(\w+)', r.stdout + r.stderr)
    out = {'master': str(master), 'normalization': f'loudnorm {m.group(1)}' if m else ''}
    out.update(peak_guard(master, float(au.get('true_peak', -1.5))))
    return out


def peak_guard(master, tp_target):
    """Loudnorm falls back to dynamic mode on peaky nat sound (a big lift on a quiet render) and can
    overshoot the true-peak ceiling. If it did, run a 4x-oversampled limiter on the audio only (video
    copied) and measure again; up to two tries, each 0.5 dB tighter."""
    tp, lufs = true_peak(master)
    res = {'lufs': lufs, 'true_peak': tp}
    if tp is None or tp <= tp_target + 0.3:
        return res
    limit = tp_target - 0.5
    for _ in range(2):
        tmp = master.with_name(master.stem + '.peak' + master.suffix)
        af = f'aresample=192000,alimiter=limit={10 ** (limit / 20):.4f}:level=disabled:attack=1:release=50,aresample=48000'
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(master), '-map', '0',
                        '-c:v', 'copy', '-af', af, '-c:a', 'aac', '-b:a', '320k', '-ar', '48000',
                        '-movflags', '+faststart', str(tmp)], check=True)
        tmp.replace(master)
        tp, lufs = true_peak(master)
        res.update({'lufs': lufs, 'true_peak': tp, 'peak_limited': round(limit, 2)})
        if tp is not None and tp <= tp_target + 0.3:
            break
        limit -= 0.5
    return res


# ---------------------------------------------------------------- qa

def parse_ass(path):
    """(play_res_y, style dict, [(start_s, end_s, text)])"""
    fmt, style, cues, pry = None, {}, [], 1920
    for ln in Path(path).read_text(errors='replace').splitlines():
        if ln.startswith('PlayResY:'):
            pry = int(ln.split(':')[1])
        elif ln.startswith('Format:') and fmt is None and 'Fontsize' in ln:
            fmt = [x.strip() for x in ln[7:].split(',')]
        elif ln.startswith('Style:') and fmt and not style:
            style = dict(zip(fmt, [x.strip() for x in ln[6:].split(',')]))
        elif ln.startswith('Dialogue:'):
            parts = ln[9:].split(',', 9)

            def ts(x):
                h, m, s = x.strip().split(':')
                return int(h) * 3600 + int(m) * 60 + float(s)
            cues.append((ts(parts[1]), ts(parts[2]), re.sub(r'\{[^}]*\}', '', parts[9]).replace('\\N', ' / ')))
    return pry, style, cues


def caption_band(ass_path):
    pry, st, cues = parse_ass(ass_path)
    k = TL_H / pry
    size = float(st.get('Fontsize', 64)) * k
    mv = float(st.get('MarginV', 696)) * k
    al = int(st.get('Alignment', 2) or 2)
    tall = size * 1.3 * 2 + 40
    if al <= 3:
        y1 = TL_H - mv + 20
        y0 = y1 - tall
    elif al >= 7:
        y0 = mv - 20
        y1 = y0 + tall
    else:
        y0, y1 = TL_H / 2 - tall / 2, TL_H / 2 + tall / 2
    return int(max(0, y0)), int(min(TL_H, y1)), cues


def grab_frames(video, frames, out_dir):
    """Exact frames (by index) from one decode pass. Returns {frame: path}."""
    frames = sorted(set(int(f) for f in frames if f >= 0))
    if not frames:
        return {}
    expr = '+'.join(f'eq(n\\,{f})' for f in frames)
    run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', video, '-vf', f'select={expr}',
         '-fps_mode', 'passthrough', '-q:v', '3', str(Path(out_dir) / 'f%04d.jpg')])
    got = sorted(Path(out_dir).glob('f*.jpg'))
    return {f: str(p) for f, p in zip(frames, got)}


def cover_present(video, style, fps, cover_frames, grabs):
    from PIL import Image
    cov = style.get('cover') or {}
    col = cov.get('color') or '#FFFFFF'
    rgb = tuple(int(col.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    fa, fb = cover_frames // 2, cover_frames + 10

    def frac(path):
        im = Image.open(path).convert('RGB')
        w, h = im.size
        band = im.crop((0, int(h * 0.30), w, int(h * 0.70))) if cov.get('anchor', 'center') == 'center' \
            else im.crop((0, 0, w, int(h * 0.40)))
        px = band.getdata()
        n = sum(1 for p in px if abs(p[0] - rgb[0]) + abs(p[1] - rgb[1]) + abs(p[2] - rgb[2]) < 40)
        return n / max(1, len(px))
    if fa not in grabs or fb not in grabs:
        return 'na', None
    x, y = frac(grabs[fa]), frac(grabs[fb])
    return ('pass' if x > 0.002 and x > 1.5 * y + 0.001 else 'fail'), {'cover': round(x, 4), 'after': round(y, 4)}


def qa_sheet(video, plan, ass_path, style, sheet_path, tile=150):
    """One image: before/after every cut, the cover frame, the caption band at every caption change."""
    from PIL import Image, ImageDraw, ImageFont
    fps = plan['fps']
    cover_frames = round(float((style.get('cover') or {}).get('seconds', 2.0)) * fps)
    cuts = []
    for s in plan['spine'][1:]:
        cuts.append((s['rec_in'], f"{s['k']} join"))
    for p in plan['punches']:
        if p['at'] > 0:
            cuts.append((p['at'], f"{p['k']} in"))
        if p['at'] + p['len'] < plan['total']:
            cuts.append((p['at'] + p['len'], f"{p['k']} out"))
    cuts.sort()
    y0 = y1 = None
    cues = []
    if ass_path and Path(ass_path).exists():
        y0, y1, cues = caption_band(ass_path)
    cue_frames = [(min(plan['total'] - 1, int((s + 0.15) * fps)), t) for s, _e, t in cues]
    want = [cover_frames // 2, cover_frames + 10] + [f for c, _ in cuts for f in (c - 1, c)] + [f for f, _ in cue_frames]
    with tempfile.TemporaryDirectory() as td:
        grabs = grab_frames(video, want, td)
        cov_status, cov_measured = cover_present(video, style, fps, cover_frames, grabs)
        try:
            font = ImageFont.load_default(size=13)
        except TypeError:
            font = ImageFont.load_default()
        th = int(tile * TL_H / TL_W)
        lab = 18
        tiles = []                                       # (image, label)

        def thumb(f):
            if f not in grabs:
                return Image.new('RGB', (tile, th), (40, 0, 0))
            return Image.open(grabs[f]).convert('RGB').resize((tile, th))
        tiles.append(([thumb(cover_frames // 2)], f'cover {cover_frames // 2 / fps:.2f}s'))
        for c, name in cuts:
            tiles.append(([thumb(c - 1), thumb(c)], f'{c / fps:.2f}s {name}'))
        W = 1600
        cols, x, y, rows = [], 0, 0, []
        for imgs, label in tiles:
            w = len(imgs) * tile + (len(imgs) - 1) * 2
            if x and x + w > W:
                rows.append(cols)
                cols, x = [], 0
            cols.append((imgs, label, x))
            x += w + 10
        if cols:
            rows.append(cols)
        cap_tiles = []
        if cues and y0 is not None:
            cw = 390
            chh = int((y1 - y0) * cw / TL_W)
            for f, text in cue_frames:
                if f in grabs:
                    im = Image.open(grabs[f]).convert('RGB')
                    sx = im.size[0] / TL_W
                    crop = im.crop((0, int(y0 * sx), im.size[0], int(y1 * sx))).resize((cw, chh))
                    cap_tiles.append((crop, f'{f / fps:.2f}s {text[:44]}'))
        per = max(1, W // (390 + 10))
        cap_rows = math.ceil(len(cap_tiles) / per)
        height = 24 + len(rows) * (th + lab + 8) + (24 + cap_rows * ((cap_tiles[0][0].size[1] if cap_tiles else 0) + lab + 8)
                                                     if cap_tiles else 0)
        sheet = Image.new('RGB', (W, max(height, 60)), (18, 18, 18))
        d = ImageDraw.Draw(sheet)
        d.text((6, 4), f'{Path(video).name}: cover + before|after each cut ({len(cuts)})', fill=(230, 230, 230), font=font)
        yy = 24
        for row in rows:
            for imgs, label, xx in row:
                for j, im in enumerate(imgs):
                    sheet.paste(im, (xx + j * (tile + 2), yy))
                d.text((xx + 2, yy + th + 2), label, fill=(240, 220, 120), font=font)
            yy += th + lab + 8
        if cap_tiles:
            d.text((6, yy + 2), f'caption band at each caption change ({len(cap_tiles)})', fill=(230, 230, 230), font=font)
            yy += 24
            for i, (im, label) in enumerate(cap_tiles):
                xx = (i % per) * (390 + 10)
                if i and i % per == 0:
                    yy += im.size[1] + lab + 8
                sheet.paste(im, (xx, yy))
                d.text((xx + 2, yy + im.size[1] + 2), label, fill=(240, 220, 120), font=font)
        sheet.save(sheet_path, quality=82)
    return {'cuts': len(cuts), 'captions': len(cap_tiles), 'cover': (cov_status, cov_measured)}


QA_KEEP = ['duration.window', 'duration.platform_max', 'audio.integrated_loudness', 'audio.true_peak',
           'audio.clipping', 'audio.silence_gaps', 'audio.tail', 'video.black_frames', 'video.frozen_frames',
           'video.orientation_sanity', 'video.static_gap', 'video.join_uncovered', 'captions.safe_zone',
           'captions.timing', 'text.cover_words', 'text.banned_words', 'container.resolution', 'container.fps']


def short(v, n=4):
    if isinstance(v, list):
        return v[:n] + ([f'+{len(v) - n} more'] if len(v) > n else [])
    if isinstance(v, dict):
        return {k: short(x, n) for k, x in list(v.items())[:8]}
    return v


def qa_run(video, edit_path, ass, style_path, plan=None, edit=None):
    video = Path(video).resolve()
    edit = edit or load_json(edit_path)
    style = load_json(style_path) if style_path else {}
    plan = plan or normalize(edit, edit_path, style)
    fps = plan['fps']
    stem = video.with_suffix('')
    full = Path(f'{stem}.qa-full.json')
    compact_path = Path(f'{stem}.qa.json')
    sheet_path = Path(f'{stem}.qa-sheet.jpg')
    bp, _terms = banned_terms(style, style_path)
    man = {'platforms': plan['platforms'], 'cover': {'text': plan['cover_text']}}
    if (style.get('audio') or {}).get('target_i') is not None:      # the house target, not the platform's
        man['audio'] = {'target_i': style['audio']['target_i']}
    if bp and bp.exists():
        man['qa'] = {'banned_words_file': str(bp)}
    hook = next((s for s in plan['spine'] if s['k'] == plan['hook']), None) if plan['hook'] else None
    exposed = []
    for x, y in zip(plan['spine'], plan['spine'][1:]):
        if x['cam'] == y['cam'] and x['framing'] == y['framing']:
            exposed.append(round(y['rec_in'] / fps, 3))
    tl = {'punches': [{'at_final': round(p['at'] / fps, 3), 'dur': round(p['len'] / fps, 3),
                       'kind': 'still' if p['kind'] == 'still' else 'clip', 'shows': p['shows'] or None}
                      for p in plan['punches']],
          'joins': exposed}
    if hook is not None and hook['rec_in'] == 0:
        tl['hook'] = {'duration_s': round((hook['rec_out'] - hook['rec_in']) / fps, 3)}
        man['hook'] = {'mode': 'prepend', 'lift_from_spine': False}      # edit-craft rule 1: repeats once
    if ass:
        tl['captions'] = {'ass': str(Path(ass).resolve())}
    with tempfile.TemporaryDirectory() as td:
        mp, tp = Path(td) / 'manifest.json', Path(td) / 'timeline.json'
        write_json(mp, man)
        write_json(tp, tl)
        cmd = [py(), QA_REEL, '--video', video, '--manifest', mp, '--timeline', tp, '--report', full, '--quiet']
        if ass:
            cmd += ['--ass', ass]
        r = run(cmd, check=False)
    if r.returncode == 2 or not full.exists():
        raise GateError(f'qa-reel.py could not run: {(r.stderr or r.stdout).strip()[-300:]}')
    rep = load_json(full)
    checks = {c['id']: c for c in rep.get('checks', [])}
    out = {}
    for cid in QA_KEEP:
        c = checks.get(cid)
        if not c or c['status'] == 'na':
            continue
        e = {'status': c['status'], 'measured': short(c.get('measured'))}
        if c['status'] != 'pass':
            e['detail'] = c.get('detail')
        out[cid] = e
    for cid, c in checks.items():
        if cid not in out and c['status'] in ('fail', 'warn'):
            out[cid] = {'status': c['status'], 'measured': short(c.get('measured')), 'detail': c.get('detail')}
    sheet = qa_sheet(video, plan, ass, style, sheet_path)
    cs, cm = sheet['cover']
    if plan['cover_text'] and style.get('cover'):
        out['cover.present'] = {'status': cs, 'measured': cm}
    out['captions.collision'] = {'status': 'na', 'detail': 'judge on the sheet: caption band crops'}
    fails = [k for k, v in out.items() if v['status'] == 'fail']
    warns = [k for k, v in out.items() if v['status'] == 'warn']
    verdict = 'fail' if fails else ('warn' if warns else 'pass')
    num = lambda cid: (checks.get(cid) or {}).get('measured')   # noqa: E731
    compact = {'video': str(video), 'verdict': verdict, 'fails': fails, 'warns': warns,
               'duration_s': num('duration.window') if isinstance(num('duration.window'), (int, float)) else None,
               'lufs': num('audio.integrated_loudness'), 'dbtp': num('audio.true_peak'),
               'checks': out, 'sheet': str(sheet_path), 'sheet_counts': {'cuts': sheet['cuts'], 'captions': sheet['captions']},
               'full_report': str(full)}
    write_json(compact_path, compact)
    dur = compact['duration_s']
    line = (f"qa {verdict.upper()}: {video.name}" + (f' {dur:.1f} s' if isinstance(dur, (int, float)) else '')
            + (f" {compact['lufs']} LUFS" if compact['lufs'] is not None else '')
            + (f" {compact['dbtp']} dBTP" if compact['dbtp'] is not None else '')
            + (f"; fail {', '.join(fails)}" if fails else '') + (f"; warn {', '.join(warns)}" if warns else ''))
    return {'verdict': verdict, 'fails': fails, 'warns': warns, 'report': str(compact_path), 'sheet': str(sheet_path),
            'line': line, 'counts': sheet}


def cmd_qa(a):
    edit_path = Path(a.edit).resolve()
    edit = load_json(edit_path)
    ass = a.ass
    style_path = a.style
    if not ass:
        od = Path(edit['out_dir']) if edit.get('out_dir') else edit_path.parent
        od = od if od.is_absolute() else edit_path.parent / od
        cands = sorted((od / '.reel-cache').glob('graphics-*/captions.ass'), key=os.path.getmtime)
        ass = str(cands[-1]) if cands else None
    q = qa_run(a.video, edit_path, ass, style_path, edit=edit)
    log(q['line'])
    for cid in q['fails'] + q['warns']:
        d = load_json(q['report'])['checks'][cid]
        log(f"  {cid}: {d.get('detail') or d.get('measured')}"[:160])
    log(f"sheet: {q['sheet']} ({q['counts']['cuts']} cuts, {q['counts']['captions']} captions)")
    log(f"report: {q['report']}" + ('' if ass else ' (no captions.ass found: caption checks skipped)'))
    return 3 if q['verdict'] == 'fail' else 0


# ---------------------------------------------------------------- CLI

def ensure_python():
    """Sibling scripts need numpy/tifffile/opencv; re-run under a python3.x that has them."""
    if os.environ.get('REEL_NO_REEXEC'):
        return
    try:
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    for cand in ('python3.12', 'python3.13', 'python3.11'):
        p = shutil.which(cand)
        if p and os.path.realpath(p) != os.path.realpath(sys.executable):
            ok = subprocess.run([p, '-c', 'import numpy, tifffile'], capture_output=True).returncode == 0
            if ok:
                os.environ['REEL_NO_REEXEC'] = '1'
                os.execv(p, [p, str(Path(__file__).resolve()), *sys.argv[1:]])


SCHEMA = 'edit.json' + __doc__.split('\nedit.json', 1)[1]


def parser():
    ap = argparse.ArgumentParser(prog='reel.py', description=__doc__.split('\n\n')[0].split(': ', 1)[1],
                                 epilog='edit.json schema: reel.py build --help',
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('prep', help='probe, transcripts, silence valleys, contact sheets -> prep.md',
                       description='Writes DIR/prep.md (the only file the editor reads to decide the cut), '
                                   'DIR/prep.json and DIR/sheets/<clip>.jpg. Finds word JSON next to the footage, '
                                   'in an Audio/ folder beside it or above it, or from --words; transcribes the rest '
                                   'with mlx-whisper (one job at a time).')
    p.add_argument('--work', required=True, help='work folder for this piece')
    p.add_argument('--footage', nargs='+', required=True, help='camera files (A-roll first)')
    p.add_argument('--note', help='content note: its Editor Brief and cover title go into prep.md verbatim')
    p.add_argument('--style', help="business reel-style.json (summary line)")
    p.add_argument('--words', nargs='+', help='word JSON files (matched to footage by file stem, else by order)')
    p.add_argument('--model', default='large-v3-turbo', help='whisper model for missing transcripts')
    p.add_argument('--language', help="force a language code, e.g. 'en'")
    p.add_argument('--no-transcribe', action='store_true', help='never run whisper')

    b = sub.add_parser('build', help='gates -> Resolve build -> render -> loudness finish -> QA',
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog=SCHEMA,
                       description=textwrap.fill('SKILL.md steps 2-10 from edit.json. Gates (cut_check edges --fix, aroll, '
                                   'public-safe words), graphics (house_graphics.py), then in Resolve: project, '
                                   'import, clip input, timeline, DI stills, grade_solve, CDL + LUT + vignette, '
                                   'graphics, voice chain, render, .drp; then finish-reel.py (loudness only) and '
                                   'reel.py qa. Stills + solve are cached on what is on screen at each still, '
                                   'graphics on captions + cover, so a caption tweak does not re-solve the grade. '
                                   'Holds the Resolve lock for the Resolve part. Writes DIR/build-<version>.json. '
                                   'Exit 0 ok, 2 gate/QA fail, 3 Resolve/render/finish failure or lock held.', 96))
    b.add_argument('--edit', required=True, help="DIR/edit.json (schema below)")
    b.add_argument('--style', required=True, help="business reel-style.json (resolve.grade block)")
    b.add_argument('--version', required=True, help='v1, v2, ... (output <id>_<version>.mp4)')
    b.add_argument('--wait-lock', type=float, default=0, metavar='SEC', help='wait up to SEC for another session to release Resolve (else exit 3)')
    b.add_argument('--dry-run', action='store_true', help='gates + graphics + the plan of Resolve calls; no Resolve')
    b.add_argument('--owner', help='lock owner name (default $REEL_OWNER or reel-build:<folder>)')
    b.add_argument('--force', action='store_true', help='replace an existing <id>_<version>.mp4')

    q = sub.add_parser('qa', help='qa-reel checks -> compact <stem>.qa.json + one <stem>.qa-sheet.jpg',
                       description='Wraps qa-reel.py (loudness, true peak, black/frozen frames, rotation, safe '
                                   'zone, banned words) and adds a cover-present check, then draws ONE sheet: the '
                                   'cover, the frames just before and after every cut, and the caption band at every '
                                   'caption change. Exit 0 pass/warn, 3 fail.')
    q.add_argument('--video', required=True)
    q.add_argument('--edit', required=True)
    q.add_argument('--ass', help='captions.ass (default: the newest one build made for this edit)')
    q.add_argument('--style', help='reel-style.json (cover color, banned-words file)')

    lk = sub.add_parser('lock', help='cross-session Resolve lock (~/.cache/reel/resolve.lock)',
                        description='One Resolve, several sessions. acquire fails with the holder while it is held '
                                    '(a dead pid or a lock older than 4 h is taken over). A manual acquire has no '
                                    'process to watch, so release it when done. build takes it by itself.')
    lk.add_argument('action', choices=['acquire', 'release', 'status'])
    lk.add_argument('--owner', help='who holds it (a session or business label)')
    lk.add_argument('--note', help='what it is held for')
    lk.add_argument('--pid', type=int, default=0, help='a process to watch (default none: age-out only)')
    lk.add_argument('--force', action='store_true', help='release even if another owner holds it')
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    if a.cmd != 'lock':
        ensure_python()
    try:
        return {'prep': cmd_prep, 'build': cmd_build, 'qa': cmd_qa, 'lock': cmd_lock}[a.cmd](a)
    except GateError as e:
        log(f'FAIL {e}')
        return 2
    except BackendError as e:
        log(f'FAIL {e}')
        return 3


if __name__ == '__main__':
    sys.exit(main())
