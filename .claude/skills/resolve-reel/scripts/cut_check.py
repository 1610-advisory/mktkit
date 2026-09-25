#!/usr/bin/env python3
"""Cut gates for a talking edit (see ../../../../references/edit-craft.md). Both routes.

Two checks on a cut plan (shape: ../resources/cut.example.json):

  aroll   Every visible A-roll shot holds at least min_aroll_s (default 3.0 s), and every
          spine join is hidden: under a cutaway, at a camera switch, or at a framing change
          (a punch-in). An exposed same-angle, same-framing join is a jump cut. Exit 3 on FAIL.

  edges   Every spine edge sits in true silence on the full-band 48 kHz audio AND on a
          >2.5 kHz band (the band that carries s, f and th, which 8 kHz energy maps miss).
          In-edges may only move earlier and out-edges only later (keep more, never less),
          up to --max-move s. Prints a proposal per edge; --fix writes the clean moves back
          into the plan. An edge with no silence in reach (two words run together) is
          reported: cut at the quietest 10 ms and give that clip a 1-frame audio fade.
          Exit 3 while any edge needs attention.

Times: spine in/out are SOURCE seconds of that segment's audio; cutaways are RECORD
(timeline) seconds, with the spine starting at lead_s.

    python3 cut_check.py aroll cut.json
    python3 cut_check.py edges cut.json [--fix] [--max-move 0.40]

Needs ffmpeg on PATH; `edges` also needs numpy.
"""
import argparse
import json
import subprocess
import sys

SR = 48000
WIN = 0.01          # envelope window, s
QUIET = 4.0         # quiet = under QUIET x the file's noise floor, on both bands
HOLD = 6            # windows of quiet needed on the removed side (60 ms)
HP_HZ = 2500


def load(path):
    with open(path) as f:
        return json.load(f)


def record_layout(plan):
    """Spine segments with record in/out frames, in playback order."""
    fps = plan['fps']
    rec = round(plan.get('lead_s', 0.0) * fps)
    out = []
    for n, s in enumerate(plan['spine']):
        length = round(s['out'] * fps) - round(s['in'] * fps)
        out.append({'n': n + 1, 'cam': s.get('cam', 'A'), 'framing': s.get('framing', 'wide'),
                    'rec_in': rec, 'rec_out': rec + length})
        rec += length
    return out


def check_aroll(plan):
    fps = plan['fps']
    min_s = plan.get('min_aroll_s', 3.0)
    segs = record_layout(plan)
    cov = sorted((round(c['at'] * fps), round(c['until'] * fps)) for c in plan.get('cutaways', []))

    visible = []
    for s in segs:
        t = s['rec_in']
        for a, b in cov:
            if b <= t or a >= s['rec_out']:
                continue
            if a > t:
                visible.append([t, a, s['cam'], s['framing']])
            t = max(t, b)
        if t < s['rec_out']:
            visible.append([t, s['rec_out'], s['cam'], s['framing']])
    shots = []                          # one shot = touching pieces with the same camera and framing
    for p in visible:
        if shots and shots[-1][1] == p[0] and shots[-1][2:] == p[2:]:
            shots[-1][1] = p[1]
        else:
            shots.append(p)
    short = [(round(a / fps, 2), round((b - a) / fps, 2), cam) for a, b, cam, _ in shots
             if (b - a) / fps < min_s - 1e-6]

    exposed = []
    for prev, nxt in zip(segs, segs[1:]):
        j = nxt['rec_in']
        under = any(a <= j <= b for a, b in cov)
        if not (under or prev['cam'] != nxt['cam'] or prev['framing'] != nxt['framing']):
            exposed.append((round(j / fps, 2), f"K{prev['n']:02d}|K{nxt['n']:02d}"))

    for t, d, cam in short:
        print(f'FAIL short A-roll: {d:.2f} s of {cam} at {t:.2f} s (min {min_s} s). '
              'Run the cutaways back to back, or move one so the gap holds.')
    for t, k in exposed:
        print(f'FAIL exposed jump cut at {t:.2f} s ({k}): put it under a cutaway or punch in '
              '(alternate framing, eyes on the same spot).')
    if short or exposed:
        return 3
    shortest = min((b - a) / fps for a, b, _, _ in shots) if shots else 0
    print(f'ok: {len(shots)} A-roll shots, shortest {shortest:.2f} s; {len(segs) - 1} joins hidden')
    return 0


def decode(path):
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-ac', '1',
                          '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def quiet_map(a):
    import numpy as np
    spec = np.fft.rfft(a)
    spec[:int(HP_HZ * len(a) / SR)] = 0
    hf = np.fft.irfft(spec, len(a))
    w = int(WIN * SR)

    def env(x):
        n = len(x) // w
        x = x[:n * w].reshape(n, w)
        return np.sqrt((x * x).mean(1))
    ef, eh = env(a), env(hf)
    return (ef < QUIET * np.percentile(ef, 8)) & (eh < QUIET * np.percentile(eh, 8))


def check_edges(plan, path, fix, max_move):
    maps, bad, moved = {}, 0, 0
    for n, s in enumerate(plan['spine'], 1):
        src = s.get('audio') or plan.get('audio')
        if not src:
            sys.exit(f'K{n:02d}: no "audio" on the segment or the plan')
        if src not in maps:
            maps[src] = quiet_map(decode(src))
        q = maps[src]

        def clean(k, side):             # side -1: quiet before an in-edge; +1: quiet after an out-edge
            if k - HOLD < 0 or k + HOLD > len(q):
                return False
            return bool(q[k - HOLD:k].all() if side < 0 else q[k:k + HOLD].all())

        def find(t, side):
            k0 = round(t / WIN)
            for d in range(int(round(max_move / WIN)) + 1):
                if clean(k0 + d * side, side):
                    return round((k0 + d * side) * WIN, 2), round(d * WIN, 2)
            return None, None

        line = []
        for key, side, word in (('in', -1, 'earlier'), ('out', 1, 'later')):
            t, d = find(s[key], side)
            if t is None:
                bad += 1
                line.append(f'{key} {s[key]:8.2f} NO CLEAN EDGE: quietest 10 ms + 1-frame audio fade')
            elif d == 0:
                line.append(f'{key} {s[key]:8.2f} ok')
            else:
                bad += 1
                line.append(f'{key} {s[key]:8.2f} -> {t:.2f} ({word} {d:.2f})')
                if fix:
                    s[key] = t
                    moved += 1
        print(f'K{n:02d}  ' + '   '.join(line))
    if fix and moved:
        with open(path, 'w') as f:
            json.dump(plan, f, indent=2)
            f.write('\n')
        print(f'wrote {moved} moved edges to {path}; run again to confirm')
    return 3 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('check', choices=['aroll', 'edges'])
    ap.add_argument('plan')
    ap.add_argument('--fix', action='store_true', help='edges: write clean moves into the plan')
    ap.add_argument('--max-move', type=float, default=0.40, help='edges: furthest move, s')
    a = ap.parse_args()
    plan = load(a.plan)
    if a.check == 'aroll':
        sys.exit(check_aroll(plan))
    sys.exit(check_edges(plan, a.plan, a.fix, a.max_move))


if __name__ == '__main__':
    main()
