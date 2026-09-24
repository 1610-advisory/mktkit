"""Resolve-side helpers for the resolve-reel skill.

Load inside the Resolve MCP `run_script_unsafe` tool (it injects `resolve` and `project`):

    exec(open('<skills>/resolve-reel/scripts/resolve_ops.py').read())
    p = new_project('Client Piece 2026-01-01')
    ...

Every function takes explicit arguments; nothing here knows about a business. Values that
differ per business (camera input space, LUT, vignette) come from the style profile's
"grade" block, read by the caller.
"""
import time

FPS = 30000 / 1001
DI_TIMELINE = ('DaVinci WG', 'DaVinci Intermediate')     # "DaVinci Wide Gamut" is rejected
REC709_OUT = ('Rec.709', 'Gamma 2.4')


def new_project(name, width=1080, height=1920, fps='29.97'):
    """Create a project with DWG/DI color management, Rec.709 out, tone + gamut mapping off."""
    pm = resolve.GetProjectManager()
    pm.SaveProject()
    p = pm.CreateProject(name)
    if not p:
        raise RuntimeError(f'project exists: {name}')
    for k, v in [('timelineResolutionWidth', str(width)), ('timelineResolutionHeight', str(height)),
                 ('timelineFrameRate', fps), ('colorScienceMode', 'davinciYRGBColorManagedv2'),
                 ('separateColorSpaceAndGamma', '1')]:
        p.SetSetting(k, v)
    set_output(p, *REC709_OUT)
    for k, v in [('colorSpaceTimeline', DI_TIMELINE[0]), ('colorSpaceTimelineGamma', DI_TIMELINE[1]),
                 ('colorSpaceOutputToneMapping', 'None'), ('colorSpaceOutputGamutMapping', 'None')]:
        p.SetSetting(k, v)
    return p


def set_output(p, space, gamma):
    p.SetSetting('colorSpaceOutput', space)
    p.SetSetting('colorSpaceOutputGamma', gamma)


def set_clip_input(p, clip, combined):
    """Clip Input Color Space, e.g. 'Canon Cinema Gamut/Canon Log 3' or 'Rec.709 Gamma 2.4'.
    Combined names are only accepted with separateColorSpaceAndGamma = 0; a gamut name alone
    can silently pick the wrong gamma. Returns what Resolve reports back."""
    p.SetSetting('separateColorSpaceAndGamma', '0')
    ok = clip.SetClipProperty('Input Color Space', combined)
    p.SetSetting('separateColorSpaceAndGamma', '1')
    if not ok:
        raise RuntimeError(f'input color space rejected: {combined}')
    return clip.GetClipProperty('Input Color Space')


def build_timeline(p, name, spine, punches=(), zoom=1.067, rotation=0.0, extra_video_tracks=3):
    """spine: [(media_pool_item, in_frame, out_frame), ...] on V1/A1 in playback order
    (out is exclusive). punches: [(item, src_in, length, record_frame), ...] video-only on V2.
    Returns the timeline. Check one still: the R5 portrait flag is honoured by Resolve on
    most cards (rotation 0, zoom 1.067 fills the width); some cards need -90 / 1.91."""
    mp = p.GetMediaPool()
    tl = mp.CreateEmptyTimeline(name)
    p.SetCurrentTimeline(tl)
    for _ in range(extra_video_tracks):
        tl.AddTrack('video')
    t0, rec = tl.GetStartFrame(), 0
    for item, a, b in spine:
        mp.AppendToTimeline([{'mediaPoolItem': item, 'startFrame': a, 'endFrame': b, 'trackIndex': 1, 'recordFrame': t0 + rec}])
        rec += b - a
    for item, a, n, at in punches:
        mp.AppendToTimeline([{'mediaPoolItem': item, 'startFrame': a, 'endFrame': a + n, 'trackIndex': 2,
                              'recordFrame': t0 + at, 'mediaType': 1}])
    for k in (1, 2):
        for it in tl.GetItemListInTrack('video', k) or []:
            it.SetProperty('RotationAngle', rotation); it.SetProperty('ZoomX', zoom); it.SetProperty('ZoomY', zoom)
    return tl


def tc(tl, frame):
    f = tl.GetStartFrame() + frame
    return '%02d:%02d:%02d:%02d' % (f // 108000, f // 1800 % 60, f // 30 % 60, f % 30)


def export_di_stills(p, tl, frames, out_dir):
    """frames: {name: timeline_frame}. Writes <out_dir>/di_<name>.tif in DWG/DI (16-bit),
    then restores Rec.709 output. Clear grades first for solver input."""
    set_output(p, *DI_TIMELINE)
    resolve.OpenPage('color')
    ok = {}
    for n, f in frames.items():
        tl.SetCurrentTimecode(tc(tl, f + 1)); time.sleep(1)
        tl.SetCurrentTimecode(tc(tl, f)); time.sleep(2.5)
        ok[n] = p.ExportCurrentFrameAsStill(f'{out_dir}/di_{n}.tif')
    set_output(p, *REC709_OUT)
    return ok


def apply_grade(item, cdl, lut, vignette=0.035):
    """Node 1: CDL (dict with slope, offset[3], sat) + LUT (path relative to Resolve's LUT
    folder, e.g. 'MCP/house.cube'); then a Fusion vignette: BrightnessContrast masked by an
    inverted soft EllipseMask. vignette = 0 skips it."""
    ok = item.SetCDL({'NodeIndex': '1', 'Slope': ' '.join([str(cdl['slope'])] * 3),
                      'Offset': ' '.join(str(o) for o in cdl['offset']), 'Power': '1 1 1',
                      'Saturation': str(cdl['sat'])})
    ok &= item.GetNodeGraph().SetLUT(1, lut)
    if vignette:
        comp = item.AddFusionComp()
        mi, mo = comp.FindTool('MediaIn1'), comp.FindTool('MediaOut1')
        bc = comp.AddTool('BrightnessContrast', -32768, -32768)
        el = comp.AddTool('EllipseMask', -32768, -32768)
        for k, v in (('Width', 1.35), ('Height', 0.95), ('SoftEdge', 0.45), ('Invert', 1.0)):
            el.SetInput(k, v)
        bc.SetInput('Brightness', -vignette / cdl['slope'])
        # tool.EffectMask = x.Output does NOT connect; ConnectInput does
        bc.ConnectInput('Input', mi); bc.ConnectInput('EffectMask', el); mo.ConnectInput('Input', bc)
    return bool(ok)


def add_graphics(p, tl, captions_mov, cover_mov, frames, cover_frames, captions_track=3, cover_track=4):
    mp = p.GetMediaPool()
    cap, cov = mp.ImportMedia([captions_mov, cover_mov])
    for c in (cap, cov):
        set_clip_input(p, c, 'Rec.709 Gamma 2.4')
    t0 = tl.GetStartFrame()
    mp.AppendToTimeline([{'mediaPoolItem': cap, 'startFrame': 0, 'endFrame': frames, 'trackIndex': captions_track, 'recordFrame': t0, 'mediaType': 1}])
    mp.AppendToTimeline([{'mediaPoolItem': cov, 'startFrame': 0, 'endFrame': cover_frames, 'trackIndex': cover_track, 'recordFrame': t0, 'mediaType': 1}])


def voice_chain(tl, gain_db):
    """Dialogue Leveler (reduce loud + lift soft) + clip gain on every A1 clip. Pick gain so
    the Resolve export peaks near -1.5 dBTP; the loudness finish does the rest."""
    for it in tl.GetItemListInTrack('audio', 1) or []:
        for k, v in {'AudioDialogueLevelerEnabled': True, 'AudioDialogueLevelerReduceLoudDialogue': True,
                     'AudioDialogueLevelerLiftSoftDialogue': True, 'AudioVolume': float(gain_db)}.items():
            it.SetProperty(k, v)


def render(p, target_dir, name, timeout_s=300):
    p.DeleteAllRenderJobs()
    p.SetCurrentRenderFormatAndCodec('mp4', 'H264')
    p.SetRenderSettings({'SelectAllFrames': True, 'TargetDir': target_dir, 'CustomName': name,
                         'FormatWidth': 1080, 'FormatHeight': 1920, 'VideoQuality': 'Best',
                         'AudioCodec': 'aac', 'AudioSampleRate': 48000})
    job = p.AddRenderJob()
    p.StartRendering([job])
    t = time.time()
    while p.IsRenderingInProgress() and time.time() - t < timeout_s:
        time.sleep(1)
    return p.GetRenderJobStatus(job)
