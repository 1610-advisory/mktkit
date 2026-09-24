"""House-style captions + cover for a Resolve reel, as frame-exact ProRes 4444 alpha clips.

Every style value comes from the business's reel style profile (the same file cut-video
takes with --style; shape: ../cut-video/resources/style.example.json). Captions are built
with the cut-video engine's own functions (cue grouping, ASS style, safe-zone layout), so a
Resolve reel matches what finish-reel.py burns in.

edit.json:
{
  "transcript": "/path/to/Audio/<clip>.json",     # word-level whisper JSON
  "cover_text": "PUBLIC-SAFE TITLE",
  "fps": 29.97002997002997,
  "audio_ranges": [[in_frame, out_frame], ...],    # source frames, playback order
  "duration_frames": 605,
  "platforms": ["instagram_reels", "youtube_shorts", "tiktok"],   # optional, else the style's
  "lead_frames": 4, "tail_frames": 3               # optional word-edge tolerances (see REFERENCE)
}

    python3 house_graphics.py edit.json OUT_DIR --style <client>/resources/reel-style.json
Writes captions.ass/.srt, captions-matte.ass, captions.mov, cover.png, cover.mov.
Needs Pillow and ffmpeg with libass.
"""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SKILLS = Path(__file__).resolve().parents[2]
ENGINE = SKILLS / 'cut-video'
SPECS = json.loads((ENGINE / 'resources/platform-specs.json').read_text())
DEFAULT_SHADOW = {'y': 2, 'blur': 24, 'alpha': 0.45}      # CSS text-shadow 0 2px 24px rgba(0,0,0,.45)

ap = argparse.ArgumentParser()
ap.add_argument('edit_json'); ap.add_argument('out_dir'); ap.add_argument('--style', required=True)
args = ap.parse_args()
CFG = json.loads(Path(args.edit_json).read_text())
STYLE = json.loads(Path(args.style).read_text())

spec = importlib.util.spec_from_file_location('finish_reel', ENGINE / 'scripts/finish-reel.py')
fr = importlib.util.module_from_spec(spec)
_argv, sys.argv = sys.argv, ['finish-reel']
spec.loader.exec_module(fr)
sys.argv = _argv


def font_name(path):
    """ASS Fontname for a TTF: fontconfig full name, else PIL family + style."""
    if shutil.which('fc-scan'):
        r = subprocess.run(['fc-scan', '--format', '%{fullname}', str(path)], capture_output=True, text=True)
        if r.stdout.strip():
            return r.stdout.split(',')[0].strip()
    fam, sty = ImageFont.truetype(str(path), 10).getname()
    return fam if sty in ('Regular', '') else f'{fam} {sty}'


def need(path, what):
    p = Path(path)
    if not p.exists():
        sys.exit(f'{what} not found: {p} (set it in the style profile)')
    return p


out = Path(args.out_dir)
out.mkdir(parents=True, exist_ok=True)
fps, frames = CFG['fps'], CFG['duration_frames']
ranges = [(a / fps, b / fps) for a, b in CFG['audio_ranges']]
cap, cv = STYLE['captions'], STYLE['cover']
platforms = CFG.get('platforms') or STYLE.get('platforms') or ['instagram_reels', 'youtube_shorts']
cap_font = need(cap['font'], 'caption font')
cap_color = cv.get('color') or '#FFFFFF'           # finish-reel colors captions with the cover color

# --- words: join whisper's split hyphen tokens, then clean cut edges ---
words = []
for ws, we, tok in fr.words_from_transcript(Path(CFG['transcript'])):
    if tok.startswith('-') and words:
        pws, _pwe, ptok = words[-1]; words[-1] = (pws, we, ptok + tok); continue
    words.append((ws, we, tok))
LEAD, TAIL = CFG.get('lead_frames', 4), CFG.get('tail_frames', 3)
edge = []
for ws, we, tok in words:
    for a, b in ranges:
        if a - LEAD / fps <= ws < a:
            ws = a                      # audible word that whisper starts a little early
        if b - TAIL / fps <= ws < b:
            ws = None                   # word that starts in the last frames: not heard
            break
    if ws is not None:
        edge.append((ws, we, tok))

# --- captions ---
safe = fr.max_safe_zones(SPECS, platforms)
layout = fr.caption_layout(cap.get('placement', 'safe-lower'), safe, None, None)
cues = fr.group_caption_cues(fr.map_words_to_output(edge, None, ranges),
                             max_chars=cap.get('max_chars_per_line', 32), max_dur=cap.get('max_cue_s', 2.8),
                             min_cue=cap.get('min_cue_s', 0.83), max_lines=cap.get('max_lines', 2),
                             style=cap.get('style', 'phrase'))
ass = out / 'captions.ass'
fr.write_ass(ass, cues, font_name(cap_font), cap.get('size', 56), cap_color,
             alignment=layout['alignment'], margin_l=layout['margin_l'],
             margin_r=layout['margin_r'], margin_v=layout['margin_v'])
fr.write_srt(out / 'captions.srt', cues)
# libass paints colour but leaves alpha at 0 on a transparent source, so render a white
# matte from the same ASS (primary + outline white, same alphas) and merge it as alpha.
matte = out / 'captions-matte.ass'
lines = ass.read_text().splitlines()
for i, ln in enumerate(lines):
    if ln.startswith('Style: Default,'):
        f = ln.split(','); f[3] = '&H00FFFFFF'; f[5] = '&H80FFFFFF'; lines[i] = ','.join(f)
matte.write_text('\n'.join(lines) + '\n')
src = f'color=c=black:s=1080x1920:r=30000/1001:d={frames / fps:.4f}'
fontsdir = cap_font.parent
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', src, '-f', 'lavfi', '-i', src,
                '-filter_complex',
                f"[0]subtitles='{ass}':fontsdir='{fontsdir}',format=rgba[c];"
                f"[1]subtitles='{matte}':fontsdir='{fontsdir}',format=gray[m];"
                "[c][m]alphamerge,unpremultiply=inplace=1,format=yuva444p10le[v]",
                '-map', '[v]', '-frames:v', str(frames), '-c:v', 'prores_ks', '-profile:v', '4444',
                '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', str(out / 'captions.mov')], check=True)

# --- cover: display font, centered or upper-safe, soft shadow ---
font = ImageFont.truetype(str(need(cv['font'], 'cover font')), cv.get('size', 72))
text = CFG['cover_text'].upper() if cv.get('case', 'as-is') == 'upper' else CFG['cover_text']
canvas = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
l, t, r, b = ImageDraw.Draw(canvas).textbbox((0, 0), text, font=font)
x = (1080 - (r - l)) // 2 - l
y = (1920 - (b - t)) // 2 - t if cv.get('anchor', 'center') == 'center' else safe['top'] + 24 - t
rs = (STYLE.get('resolve') or {}).get('cover_shadow', {})
sh = None if rs is False else {**DEFAULT_SHADOW, **(rs or {})}
if sh:
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x, y + sh['y']), text, font=font, fill=(0, 0, 0, round(255 * sh['alpha'])))
    canvas = Image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(sh['blur'] / 2)), canvas)
ImageDraw.Draw(canvas).text((x, y), text, font=font, fill=cv.get('color', '#FFFFFF'))
canvas.save(out / 'cover.png')
cover_frames = round(cv.get('seconds', 2.0) * fps)
subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-loop', '1', '-framerate', '30000/1001',
                '-i', str(out / 'cover.png'), '-frames:v', str(cover_frames), '-c:v', 'prores_ks',
                '-profile:v', '4444', '-pix_fmt', 'yuva444p10le', '-alpha_bits', '16', str(out / 'cover.mov')], check=True)

print(f'{len(cues)} cues | platforms {platforms} | safe {safe} | layout {layout} | cover {cover_frames} f at y={y}')
for s0, e0, txt in cues:
    print(f'{s0:6.2f}-{e0:6.2f}  ' + txt.replace('\\N', ' / '))
