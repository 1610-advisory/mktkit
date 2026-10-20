"""Tests for reel.py: prep, build (dry run and FakeBackend), qa and the Resolve lock.

Synthetic media only (ffmpeg lavfi). Nothing here talks to DaVinci Resolve.

    python3.12 -m pytest resolve-reel/scripts/tests -q
"""
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REEL_PY = HERE.parent / 'reel.py'
FPS = '30000/1001'

spec = importlib.util.spec_from_file_location('reel', REEL_PY)
reel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reel)

pytestmark = pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='needs ffmpeg')


def ff(*args):
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', *map(str, args)], check=True)


def find_font():
    for p in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Supplemental/Verdana.ttf',
              '/System/Library/Fonts/Supplemental/Georgia.ttf', '/Library/Fonts/Arial Unicode.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(p).exists():
            return p
    return None


# Speech stand-in: 0.8 s bursts (440 Hz + 5 kHz, so both check bands see them) every 2 s, from
# 0.2 s; quiet in between over a low noise floor. Words sit on the bursts.
BURSTS = [(0.2, 1.0), (2.2, 3.0), (4.2, 5.0), (6.2, 7.0), (8.2, 9.0)]
WORDS = ['alpha', 'beta', 'gamma', 'delta', 'echo', 'foxtrot', 'golf', 'hotel', 'india', 'juliet']


def make_clip(path, seconds=10.0, speech=True, color=None):
    gate = '+'.join(f'between(t,{a},{b})' for a, b in BURSTS) if speech else '0'
    expr = f'(0.25*sin(2*PI*440*t)+0.08*sin(2*PI*5000*t))*({gate})+0.0006*(random(0)*2-1)'
    video = f'color=c={color}:s=1080x1920:r={FPS}' if color else f'testsrc2=s=1080x1920:r={FPS}'
    ff('-f', 'lavfi', '-i', f'{video}:d={seconds}', '-f', 'lavfi',
       '-i', f"aevalsrc=exprs='{expr}':s=48000:d={seconds}", '-c:v', 'libx264', '-preset', 'ultrafast',
       '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', path)
    return path


def make_words(path):
    words = []
    for i, (a, b) in enumerate(BURSTS):
        mid = (a + b) / 2
        words.append({'word': ' ' + WORDS[2 * i], 'start': a + 0.02, 'end': mid - 0.02})
        words.append({'word': ' ' + WORDS[2 * i + 1] + '.', 'start': mid, 'end': b - 0.02})
    Path(path).write_text(json.dumps({'text': '', 'segments': [{'start': 0, 'end': 10, 'words': words,
                                                                 'no_speech_prob': 0.01, 'avg_logprob': -0.2}]}))
    return path


@pytest.fixture(scope='module')
def media(tmp_path_factory):
    font = find_font()
    if font is None:
        pytest.skip('no TrueType font found')
    d = tmp_path_factory.mktemp('media')
    (d / 'Video').mkdir()
    (d / 'Audio').mkdir()
    aroll = make_clip(d / 'Video' / 'ARoll-Take1.mp4')
    broll = make_clip(d / 'Video' / 'BRoll-Detail.mp4', 6.0, speech=False, color='0x806040')
    words = make_words(d / 'Audio' / 'ARoll-Take1.json')          # found by prep in the Audio/ sibling
    shutil.copy(font, d / 'font.ttf')
    (d / 'banned.txt').write_text('# test list\nforbiddenword\n')
    style = {
        'platforms': ['instagram_reels', 'youtube_shorts', 'tiktok'],
        'cover': {'font': str(d / 'font.ttf'), 'color': '#F2EDE0', 'size': 72, 'case': 'upper',
                  'anchor': 'center', 'seconds': 1.0},
        'captions': {'font': str(d / 'font.ttf'), 'size': 64, 'style': 'phrase', 'placement': 'safe-lower',
                     'max_chars_per_line': 32, 'min_cue_s': 0.5, 'max_cue_s': 2.8},
        'audio': {'loudnorm': 'two-pass', 'target_i': -16, 'true_peak': -1.5, 'lra': 11},
        'qa': {'banned_words_file': str(d / 'banned.txt')},
        'resolve': {'grade': {'camera_input': 'Rec.709 Gamma 2.4', 'lut_resolve': 'Test/house.cube',
                              'vignette': 0.035, 'voice_gain_db': 4.0, 'face_ire': 55}},
    }
    (d / 'resources').mkdir()
    (d / 'resources' / 'reel-style.json').write_text(json.dumps(style))
    return {'dir': d, 'aroll': aroll, 'broll': broll, 'words': words, 'style': d / 'resources' / 'reel-style.json'}


def edit_doc(media, **over):
    e = {
        'id': 'test-piece', 'project': 'Test Project', 'timeline': 'Test - Reel',
        'cover_text': 'Test cover', 'fps': 30000 / 1001,
        'clips': {'C1': {'path': str(media['aroll']), 'words': str(media['words'])},
                  'C2': {'path': str(media['broll'])}},
        'hook': {'k': 'H'},
        'spine': [{'k': 'H', 'clip': 'C1', 'in_s': 4.0, 'out_s': 7.6, 'framing': 'wide'},
                  {'k': 'K1', 'clip': 'C1', 'in_s': 0.1, 'out_s': 9.6, 'framing': 'tight', 'shift_px': [4, 30]}],
        'punches': [{'k': 'P1', 'clip': 'C2', 'src_in_s': 1.0, 'dur_s': 2.0, 'at_s': 8.0, 'shows': 'detail'}],
        'grade': {'shots': {
            'A': {'items': ['H', 'K1'], 'stills': {'A1': 30, 'A2': 200}, 'faces': {'A1': [400, 600, 700, 900],
                                                                                 'A2': [400, 600, 700, 900]}},
            'BR': {'items': ['P1'], 'stills': {'BR': 270},
                   'match_wall': {'box': [100, 400, 900, 1400], 'ref_shot': 'A', 'ref_still': 0,
                                  'ref_box': [100, 400, 900, 1400]}}}},
    }
    e.update(over)
    return e


def write_edit(work, doc):
    work.mkdir(parents=True, exist_ok=True)
    p = work / 'edit.json'
    p.write_text(json.dumps(doc, indent=1))
    return p


def cli(*args, env=None):
    return subprocess.run([sys.executable, str(REEL_PY), *map(str, args)], capture_output=True, text=True,
                          env={**os.environ, 'REEL_NO_REEXEC': '1', **(env or {})})


# ---------------------------------------------------------------- prep

def test_prep_writes_compact_md(media, tmp_path):
    note = tmp_path / 'note.md'
    note.write_text('# Piece\n\n## Editor Brief\n\nOpen on the gamma line.\n- Footage: take 1\n\n'
                    'Cover title (public-safe): TEST COVER\n\n## History\n\nold stuff\n')
    work = tmp_path / 'work'
    r = cli('prep', '--work', work, '--footage', media['aroll'], media['broll'], '--note', note,
            '--style', media['style'], '--no-transcribe')
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(r.stdout.strip().splitlines()) <= 5
    md = (work / 'prep.md').read_text()
    assert '### C1: ARoll-Take1.mp4' in md and '### C2: BRoll-Detail.mp4' in md
    assert '[0.22-0.98] alpha beta.' in md                     # one phrase per burst, not per word
    assert '[2.22-2.98] gamma delta.' in md
    assert 'Open on the gamma line.' in md and 'Cover title (public-safe): TEST COVER' in md
    assert 'old stuff' not in md                               # only the Editor Brief section
    pj = json.loads((work / 'prep.json').read_text())
    c1 = pj['clips']['C1']
    assert c1['words_source'] == 'found' and c1['words'].endswith('Audio/ARoll-Take1.json')
    assert abs(c1['fps'] - 29.97) < 0.01 and c1['audio_rate'] == 48000 and c1['display'] == [1080, 1920]
    # valleys between the bursts, each >= 120 ms, both bands quiet
    gaps = [(1.0, 2.2), (3.0, 4.2), (5.0, 6.2), (7.0, 8.2)]
    for a, b in gaps:
        assert any(v[0] >= a - 0.05 and v[1] <= b + 0.05 and v[1] - v[0] >= 0.5 for v in c1['valleys']), (a, b)
    assert all(v[1] - v[0] >= 0.12 for v in c1['valleys'])
    assert '  ~ ' in md
    assert Path(c1['sheet']).exists() and Path(pj['clips']['C2']['sheet']).exists()
    assert pj['clips']['C2']['words'] is None
    assert len(md) // 4 < 12000


# ---------------------------------------------------------------- build (dry run)

def test_build_dry_run_plans_resolve_calls(media, tmp_path, monkeypatch):
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'lock' / 'resolve.lock'))
    ep = write_edit(tmp_path / 'piece', edit_doc(media))
    before = ep.read_text()
    r = cli('build', '--edit', ep, '--style', media['style'], '--version', 'v1', '--dry-run',
            env={'REEL_LOCK': str(tmp_path / 'lock' / 'resolve.lock')})
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(r.stdout.strip().splitlines()) <= 10
    assert not (tmp_path / 'lock' / 'resolve.lock').exists()    # dry run never takes the lock
    assert ep.read_text() == before                            # dry run never edits edit.json
    b = json.loads((tmp_path / 'piece' / 'build-v1.json').read_text())
    assert b['status'] == 'ok' and b['dry_run'] is True
    names = [c[0] for c in b['resolve_calls']]
    order = ['connect', 'open_project', 'import_media', 'set_clip_input', 'build_timeline', 'set_transform',
             'export_stills', 'apply_grade', 'add_graphics', 'voice_chain', 'render', 'export_drp', 'close']
    firsts = [names.index(n) for n in order]
    assert firsts == sorted(firsts), names
    assert names.count('apply_grade') == 3 and names.count('set_clip_input') == 2
    bt = next(c[1] for c in b['resolve_calls'] if c[0] == 'build_timeline')
    assert bt['name'] == 'Test - Reel v1'
    assert [x[1:] for x in bt['spine']] == [[119, 228], [2, 288]]             # floor in, ceil out
    assert bt['punches'][0][1:] == [29, 60, 240]                              # src_in, len, record
    st = next(c[1] for c in b['resolve_calls'] if c[0] == 'set_transform')
    assert st['idx'] == 1 and abs(st['zoom'] - 1.067 * 1.12) < 1e-6
    assert abs(st['pan'] - 4 / 0.9375) < 0.01 or abs(st['pan'] - 4.0) < 0.01  # display-derived calibration
    assert st['tilt'] == -30.0
    ag = [c[1] for c in b['resolve_calls'] if c[0] == 'apply_grade']
    assert ag[1]['geom']['w'] < 1.35 and ag[0]['geom']['w'] == 1.35          # vignette follows the punch-in
    assert Path(b['graphics']['captions_mov']).exists() and Path(b['graphics']['cover_mov']).exists()
    assert (tmp_path / 'piece' / '.reel-cache' / '.gitignore').read_text() == '*\n'
    assert b['gates']['aroll'].startswith('ok')


def test_build_gate_fails_on_short_aroll_and_banned_cover(media, tmp_path):
    doc = edit_doc(media)
    doc['spine'][0]['out_s'] = 5.6          # hook 1.6 s on the speaker, under the 3.0 s hold
    ep = write_edit(tmp_path / 'short', doc)
    r = cli('build', '--edit', ep, '--style', media['style'], '--version', 'v1', '--dry-run')
    assert r.returncode == 2 and 'gate aroll' in r.stdout
    ep2 = write_edit(tmp_path / 'banned', edit_doc(media, cover_text='A forbiddenword cover'))
    r = cli('build', '--edit', ep2, '--style', media['style'], '--version', 'v1', '--dry-run')
    assert r.returncode == 2 and 'gate public-safe' in r.stdout and 'forbiddenword' in r.stdout


def test_edges_fix_moves_edge_and_keeps_punch_on_its_moment(media, tmp_path):
    doc = edit_doc(media)
    doc['spine'][0]['in_s'] = 4.3            # inside a burst: must move earlier into the quiet
    doc['punches'][0]['at_s'] = 7.0
    ep = write_edit(tmp_path / 'fix', doc)
    style = json.loads(media['style'].read_text())
    plan = reel.normalize(doc, ep, style)
    p_src_before = plan['punches'][0]['at'] - plan['spine'][1]['rec_in'] + plan['spine'][1]['src_in']
    g = reel.run_gates(plan, tmp_path / 'fix' / '.reel-cache')
    assert g['moved'] and g['moved'][0].startswith('H in ')
    assert plan['spine'][0]['src_in'] / plan['fps'] <= 4.2
    p = plan['punches'][0]
    assert p['at'] - plan['spine'][1]['rec_in'] + plan['spine'][1]['src_in'] == p_src_before
    reel.write_back(doc, ep, plan)
    assert json.loads(ep.read_text())['spine'][0]['in_s'] <= 4.2


def test_continuous_join_is_not_an_edge_and_overlap_fails(media, tmp_path):
    doc = edit_doc(media)
    doc['spine'][1:] = [{'k': 'K1', 'clip': 'C1', 'in_s': 0.1, 'out_s': 4.5, 'framing': 'tight'},
                        {'k': 'K2', 'clip': 'C1', 'in_s': 4.5, 'out_s': 9.6, 'framing': 'wide'}]
    doc['grade']['shots']['A']['items'] = ['H', 'K1', 'K2']
    doc['edge_exceptions'] = {'K2 in': 'set on purpose: a continuous join still gets no fade'}
    ep = write_edit(tmp_path / 'cont', doc)
    style = json.loads(media['style'].read_text())
    plan = reel.normalize(doc, ep, style)
    k1, k2 = plan['spine'][1], plan['spine'][2]
    assert k1['src_out'] == k2['src_in'] and k1['rec_out'] == k2['rec_in']   # rounding snapped shut
    assert k1['fades'][1] == 0 and k2['fades'][0] == 0
    assert plan['continuous'] == {'K1 out', 'K2 in'}
    g = reel.run_gates(plan, tmp_path / 'cont' / '.reel-cache')          # 4.5 s is mid-burst
    assert not any(m.startswith(('K1 out', 'K2 in')) for m in g['moved'])
    assert k1['src_out'] == k2['src_in']
    doc['spine'][1]['out_s'] = 4.7                                       # 0.2 s plays twice
    with pytest.raises(reel.GateError, match='overlaps'):
        reel.normalize(doc, write_edit(tmp_path / 'over', doc), style)


# ---------------------------------------------------------------- build (FakeBackend, full pipeline)

def fake_backend(tmp_path, loud):
    import numpy as np
    tifffile = pytest.importorskip('tifffile')

    def still(path):
        y = np.linspace(0.30, 0.55, 1920)[:, None, None] * np.ones((1920, 1080, 3))
        y[600:900, 400:700] = 0.52
        y[..., 2] *= 0.97
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tifffile.imwrite(str(path), (np.clip(y, 0, 1) * 65535).astype(np.uint16))

    be = reel.FakeBackend(still_fn=still)

    def render(path, frames):
        gfx = next(c[1] for c in reversed(be.calls) if c[0] == 'add_graphics')
        amp = 8.0 if loud['on'] and not str(path).endswith('-r2.mp4') else 0.8
        ff('-f', 'lavfi', '-i', f'testsrc2=s=1080x1920:r={FPS}', '-i', gfx['captions'], '-i', gfx['cover'],
           '-f', 'lavfi', '-i', f'sine=f=300:sample_rate=48000,volume={amp}',
           '-filter_complex', '[0][1]overlay=eof_action=pass[a];[a][2]overlay=eof_action=pass[v]',
           '-map', '[v]', '-map', '3:a', '-frames:v', frames, '-c:v', 'libx264', '-preset', 'ultrafast',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-shortest', path)

    be.render_fn = render
    return be


def run_build(ep, style, version, backend, dry=False):
    a = reel.parser().parse_args(['build', '--edit', str(ep), '--style', str(style), '--version', version]
                                 + (['--dry-run'] if dry else []))
    code = reel.cmd_build(a, backend=backend)
    return code, json.loads((ep.parent / f'build-{version}.json').read_text())


def test_build_full_with_fake_backend_caches_grade(media, tmp_path, monkeypatch):
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'resolve.lock'))
    ep = write_edit(tmp_path / 'full', edit_doc(media))
    loud = {'on': False}

    be = fake_backend(tmp_path, loud)
    code, b = run_build(ep, media['style'], 'v1', be)
    assert code == 0, b.get('error')
    assert not (tmp_path / 'resolve.lock').exists()                 # released in finally
    assert b['resolve']['grade']['stills_cached'] is False and b['resolve']['grade']['solve_cached'] is False
    cdl = b['resolve']['grade']['cdl']
    assert set(cdl) == {'A', 'BR'} and 0.75 <= cdl['A']['slope'] <= 2.0
    master = Path(b['finish']['master'])
    assert master.exists() and Path(b['resolve']['drp']).exists()
    assert b['qa']['verdict'] in ('pass', 'warn')
    q = json.loads(Path(b['qa']['report']).read_text())
    assert q['checks']['cover.present']['status'] == 'pass'
    assert Path(b['qa']['sheet']).exists()

    # v2: caption/cover tweak -> graphics remade, stills + solve reused
    doc = json.loads(ep.read_text())
    doc['cover_text'] = 'Test cover two'
    ep.write_text(json.dumps(doc))
    be2 = fake_backend(tmp_path, loud)
    code, b2 = run_build(ep, media['style'], 'v2', be2)
    assert code == 0, b2.get('error')
    assert 'export_stills' not in [c[0] for c in be2.calls]
    assert b2['resolve']['grade']['solve_cached'] is True and b2['graphics']['cached'] is False
    assert b2['resolve']['grade']['cdl'] == cdl

    # v3: the hook moves -> what is on screen at still A1 changes -> stills + solve again.
    # The export also peaks hot -> no whole-mix re-render; finish + peak_guard hold the ceiling.
    doc['spine'][0]['in_s'] = 3.9
    doc['spine'][0]['out_s'] = 7.5
    ep.write_text(json.dumps(doc))
    loud['on'] = True
    be3 = fake_backend(tmp_path, loud)
    code, b3 = run_build(ep, media['style'], 'v3', be3)
    assert code == 0, b3.get('error')
    assert 'export_stills' in [c[0] for c in be3.calls]
    assert b3['resolve']['grade']['stills_cached'] is False
    assert b3['graphics']['cached'] is False                         # the spine moved, captions re-timed
    assert not b3['resolve'].get('rerender') and b3['resolve']['voice_gain_db'] == 4.0
    assert [c[0] for c in be3.calls].count('voice_chain') == 1
    fin = b3['finish']
    assert fin['true_peak'] is not None and fin['true_peak'] <= -1.2, fin

    # the same version again is refused without --force
    a = reel.parser().parse_args(['build', '--edit', str(ep), '--style', str(media['style']), '--version', 'v3'])
    assert reel.cmd_build(a, backend=fake_backend(tmp_path, loud)) == 2
    assert json.loads((ep.parent / 'build-v3.json').read_text())['status'] == 'ok'   # record kept


def test_resolve_backend_injects_resolve_into_resolve_ops(monkeypatch):
    from unittest import mock
    fake = mock.MagicMock(name='resolve')
    pm = fake.GetProjectManager.return_value
    pm.GetProjectListInCurrentFolder.return_value = []
    monkeypatch.setattr(reel, 'connect_resolve', lambda: fake)
    be = reel.ResolveBackend()
    be.connect()
    assert be.ops['resolve'] is fake and callable(be.ops['build_timeline'])
    assert be.open_project('Test Project') == 'created'
    pm.CreateProject.assert_called_once_with('Test Project')
    be.p.SetSetting.assert_any_call('colorScienceMode', 'davinciYRGBColorManagedv2')
    be.p.SetSetting.assert_any_call('colorSpaceOutputToneMapping', 'None')
    pm.GetProjectListInCurrentFolder.return_value = ['Test Project']
    assert be.open_project('Test Project') == 'opened'


def test_build_refuses_when_lock_held(media, tmp_path, monkeypatch):
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'resolve.lock'))
    reel.lock_acquire('other-session', 'busy', pid=os.getpid())
    ep = write_edit(tmp_path / 'locked', edit_doc(media))
    code, b = run_build(ep, media['style'], 'v1', reel.FakeBackend())
    assert code == 3 and b['error'].startswith('LOCKED') and 'other-session' in b['error']


# ---------------------------------------------------------------- qa

def test_qa_on_synthetic_video(media, tmp_path):
    work = tmp_path / 'qa'
    ep = write_edit(work, edit_doc(media))
    video = work / 'plain_v1.mp4'
    ff('-f', 'lavfi', '-i', f'testsrc2=s=1080x1920:r={FPS}', '-f', 'lavfi', '-i', 'sine=f=300:sample_rate=48000',
       '-frames:v', 392, '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
       '-shortest', video)
    ass = work / 'captions.ass'
    ass.write_text('[Script Info]\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n'
                   'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, '
                   'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, '
                   'Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                   'Style: Default,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,'
                   '2,81,156,696,1\n\n[Events]\n'
                   'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
                   'Dialogue: 0,0:00:00.00,0:00:01.50,Default,,0,0,0,,gamma delta\n'
                   'Dialogue: 0,0:00:01.50,0:00:03.00,Default,,0,0,0,,echo foxtrot\n'
                   'Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,forbiddenword here\n')
    r = cli('qa', '--video', video, '--edit', ep, '--ass', ass, '--style', media['style'])
    assert r.returncode == 3, r.stdout + r.stderr                # no cover drawn, banned word in captions
    assert len(r.stdout.strip().splitlines()) <= 10
    q = json.loads((work / 'plain_v1.qa.json').read_text())
    assert q['verdict'] == 'fail'
    assert q['checks']['cover.present']['status'] == 'fail'
    assert q['checks']['text.banned_words']['status'] == 'fail'
    assert q['checks']['video.black_frames']['status'] == 'pass'
    assert q['sheet_counts'] == {'cuts': 3, 'captions': 3}        # H|K1 join, P1 in, P1 out
    from PIL import Image
    im = Image.open(work / 'plain_v1.qa-sheet.jpg')
    assert im.size[0] <= 1600 and im.size[1] < 2400
    assert len(json.dumps(q)) < 8000


# ---------------------------------------------------------------- lock

def test_lock_acquire_release_status(tmp_path):
    env = {'REEL_LOCK': str(tmp_path / 'resolve.lock')}
    assert cli('lock', 'status', env=env).stdout.strip() == 'free'
    r = cli('lock', 'acquire', '--owner', 'biz-a', '--note', 'build v1', env=env)
    assert r.returncode == 0 and r.stdout.startswith('acquired')
    info = json.loads((tmp_path / 'resolve.lock').read_text())
    assert set(info) == {'owner', 'pid', 'host', 'started_at', 'note'} and info['owner'] == 'biz-a'
    r = cli('lock', 'acquire', '--owner', 'biz-b', env=env)
    assert r.returncode == 3 and 'biz-a' in r.stdout
    assert 'held by biz-a' in cli('lock', 'status', env=env).stdout
    assert cli('lock', 'release', '--owner', 'biz-b', env=env).returncode == 3
    assert cli('lock', 'release', '--owner', 'biz-a', env=env).stdout.strip() == 'released'
    assert not (tmp_path / 'resolve.lock').exists()


def test_lock_stale_takeover(tmp_path, monkeypatch):
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'resolve.lock'))
    dead = subprocess.Popen([sys.executable, '-c', 'pass'])
    dead.wait()
    reel.lock_acquire('crashed', pid=dead.pid)
    got, msg = reel.lock_acquire('biz-b', pid=os.getpid())
    assert got and 'stale' in msg and 'crashed' in msg
    reel.lock_release('biz-b')
    reel.lock_acquire('old', pid=0)
    info = json.loads((tmp_path / 'resolve.lock').read_text())
    info['started_at'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - 5 * 3600))
    (tmp_path / 'resolve.lock').write_text(json.dumps(info))
    got, msg = reel.lock_acquire('biz-c', pid=os.getpid())
    assert got and 'older than 4 h' in msg
    got, msg = reel.lock_acquire('biz-c', pid=os.getpid())    # same owner: re-entrant, not re-acquired
    assert got is False
    reel.lock_release('biz-c')


def test_lock_live_pid_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'resolve.lock'))
    reel.lock_acquire('live', pid=os.getpid())
    with pytest.raises(reel.BackendError, match='LOCKED'):
        reel.lock_acquire('other', pid=os.getpid())
    reel.lock_release('live')


def test_help_lists_subcommands():
    r = cli('--help')
    assert r.returncode == 0 and all(s in r.stdout for s in ('prep', 'build', 'qa', 'lock'))
    r = cli('build', '--help')
    assert '"spine"' in r.stdout and '"punches"' in r.stdout


def test_lock_same_owner_other_live_pid_queues(tmp_path, monkeypatch):
    """Two parallel builds under one owner name must not both enter Resolve."""
    monkeypatch.setenv('REEL_LOCK', str(tmp_path / 'resolve.lock'))
    got, _ = reel.lock_acquire('biz', pid=os.getpid())
    assert got
    with pytest.raises(reel.BackendError, match='LOCKED'):
        reel.lock_acquire('biz', pid=os.getppid())          # another live process, same owner
    assert reel.lock_acquire('biz', pid=os.getpid())[0] is False   # same process re-enters
    assert reel.lock_acquire('biz')[0] is False                    # manual pid-less hold re-enters
    reel.lock_release('biz')
