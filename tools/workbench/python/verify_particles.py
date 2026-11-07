#!/usr/bin/env python3
"""Fresh synthetic on-hit particles: actual native resources, lifecycle and PNGs.

The gameplay input comes from the current native --write-fixtures producer.
No captured item, migration, historical adapter or rendered substitute is used.
"""
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from PIL import Image
import workbench as w
from python.native_review import native_frames


TEXTURES = {
    'star': ('ParticleLibrary/Assets/Textures/Star', 'edd88a02fe82e8dc740248ba45add74ef0b4e9fdcf2e8c3fe12acfdc1d996939'),
    'shineFlare': ('Luminance/Assets/GreyscaleTextures/ShineFlare', '0d0445abd56981effdb50e045694ebd3312959eaa3a21c64618a345d5b9351e6'),
}
EFFECT_SHA256 = '3634b60379eb94f950922a92cfdbea537ca16f3ce676ba41b42cc71fbc3386c3'
MAGIC_PIXEL_SHA256 = '43e32609f2d123fc51cafbafab11955153ea545760952a578c3f909bbe88651c'


def particle_fixture(straight: dict[str, Any], texture: str) -> dict[str, Any]:
    """Author only the explicit particle experiment over a current straight fixture."""
    if texture not in TEXTURES:
        raise ValueError('Unsupported synthetic particle texture')
    item = copy.deepcopy(straight)
    root = next(e for e in item['runtimeProgram']['entities'] if e['id'] == 'root')
    root['spawn']['aim'] = 'cursor'
    root['events'] = []
    item['vfxManifest']['slots'] = [dict(
        id='hit_particles', entityId='root', event='on_hit', rendererKind='libraryParticle',
        anchor='self', blend='additive', layer='BeforeProjectiles', duration=14,
        alpha=1, startTick=0, repeatEvery=0, slotSeed=1,
        particle=dict(spawn=dict(shape='point'), textureId=texture, sampling='point', count=5,
            speedMinPxPerTick=1, speedMaxPxPerTick=3, spreadRadians=2,
            inheritVelocity=0, drag=1, accelerationXPxPerTickSquared=0,
            accelerationYPxPerTickSquared=0, widthPx=16, heightPx=16,
            rotationRadians=0, rotationSpeedRadiansPerTick=0,
            colorStart=dict(r=80, g=220, b=255), colorEnd=dict(r=80, g=220, b=255),
            endScaleMultiplier=1, endOpacity=1))]
    return item


def particle_scene() -> dict[str, Any]:
    return dict(playerUpdate='client_vfx', ticks=120, seed=1,
        player=dict(x=800, y=700, life=100, mana=200, manaCrystals=9),
        dummy=dict(x=920, y=700, width=32, height=48, life=10000),
        tiles=[dict(tileX=1, tileY=47, width=97, height=1)],
        actions=[dict(tick=0, kind='aim', x=936, y=724),
                 dict(tick=0, kind='primary'), dict(tick=1, kind='release')],
        assertions=[dict(kind='spawn_count', value=1), dict(kind='projectile_hit_count', value=1),
                    dict(kind='all_inactive'), dict(kind='no_nonfinite')],
        nativeRender=dict(width=512, height=384, cameraX=700, cameraY=550, zoom=1,
                          capture=True, lightingMode='viewport_fill'))


def resource_checks(render: dict[str, Any], texture: str) -> dict[str, bool]:
    path, expected = TEXTURES[texture]
    selected_hash = (render.get('starSha256') if texture == 'star' else
                    render.get('luminanceResources', {}).get('selectedTextureSha256', {}).get(path))
    return {
        'original-library-resources': render.get('resourceReady') is True
            and render.get('originalParticleLibraryEffect') is True
            and render.get('libraryBuffers') == 4 and render.get('effectSha256') == EFFECT_SHA256,
        'selected-original-texture': selected_hash == expected
            and path in render.get('readyLibraryTexturePaths', []),
        'original-magicpixel': render.get('magicPixelResource', {}).get('sha256') == MAGIC_PIXEL_SHA256
            and render.get('magicPixelResource', {}).get('playerArtworkLoaded') is False,
        'explicit-vfx-only-scope': all(render.get(k) is False for k in
            ('itemArtworkRendered', 'projectileArtworkRendered', 'worldRendered', 'soundValidated')),
    }


def lifecycle_checks(trace: dict[str, Any], duration: int = 14, count: int = 5) -> dict[str, bool]:
    hits = [s['tick'] for s in trace.get('snapshots', [])
            for e in s.get('events', []) if e.get('kind') == 'hit']
    states = trace.get('nativeRender', {}).get('snapshots', [])
    live = [s for s in states if s.get('particleCount', 0) > 0]
    expected = list(range(hits[0], hits[0] + duration)) if len(hits) == 1 else []
    return {
        'real-hit-starts-particles': bool(expected) and [s['tick'] for s in live] == expected,
        'actual-particle-count-and-duration': bool(live) and all(s['particleCount'] == count
            and s.get('records') and all(r['started'] and r['durationTicks'] == duration
                for r in s['records']) for s in live),
        'particles-retire': bool(states) and states[-1].get('particleCount') == 0
            and states[-1].get('materialRecordCount') == 0,
    }


def frame_checks(trace: dict[str, Any], trace_path: Path, ticks: int) -> tuple[dict[str, bool], list[int]]:
    """Decode native PNGs; telemetry saying 'nonblack' alone is not pixel evidence."""
    frames = native_frames(trace, trace_path)
    visible = []
    agrees = True
    for frame, path in frames:
        with Image.open(path) as image:
            nonblack = sum(any(pixel) for pixel in image.convert('RGB').get_flattened_data())
        agrees &= frame.get('nonblackPixels') == nonblack
        if nonblack:
            visible.append(frame['tick'])
    checks = {
        'complete-native-pngs': [f['tick'] for f, _ in frames] == list(range(ticks)),
        'native-pixel-telemetry-matches-decoded-pngs': agrees,
        'draw-preserves-main-rng': all(f.get('drawChangedMainRng') is False
            and f['mainRngBeforeDraw'] == f['mainRngAfterDraw'] for f, _ in frames),
    }
    return checks, visible


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--texture', choices=TEXTURES, default='star')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    w.fixtures(out / 'fixtures', no_build=args.no_build)
    item = particle_fixture(w.read_json(out / 'fixtures/synthetic-straight.json'), args.texture)
    scene = particle_scene()
    off = copy.deepcopy(item); off['vfxManifest']['slots'] = []
    silent = copy.deepcopy(scene); silent['nativeRender']['capture'] = False
    miss = copy.deepcopy(scene); miss['dummy']['y'] = 300
    miss['assertions'] = [dict(kind='spawn_count', value=1), dict(kind='dummy_undamaged'),
                          dict(kind='all_inactive'), dict(kind='no_nonfinite')]
    unused = copy.deepcopy(miss); unused['actions'] = []
    unused['assertions'][0]['value'] = 0
    bad_camera = copy.deepcopy(scene); bad_camera['nativeRender']['zoom'] = 0
    bad_ticks = copy.deepcopy(scene); bad_ticks['ticks'] = 601
    cases = [('hit', item, scene, '' , {}), ('repeat', item, scene, '', {}),
             ('vfx-off', off, scene, '', {}), ('no-capture', item, silent, '', {}),
             ('miss', item, miss, '', {}), ('no-use', item, unused, '', {}),
             ('missing-library', item, scene, 'Original ParticleLibrary Star.png and InstancedParticle.xnb required',
              {'INFINI_PARTICLE_ASSET_DIR': str(out / 'absent-library')}),
             ('missing-magicpixel', item, scene, 'Missing exact starter-player source PNG: MagicPixel',
              {'INFINI_PLAYER_ASSET_DIR': str(out / 'absent-player')}),
             ('invalid-camera', item, bad_camera, 'finite camera and zoom(0,16]', {}),
             ('bounded-ticks', item, bad_ticks, 'at most600 ticks', {})]
    rows: list[dict[str, Any]] = []
    traces: dict[str, Any] = {}
    pixels: dict[str, list[int]] = {}
    def check(name: str, value: Any) -> None:
        rows.append(dict(name=name, passed=bool(value)))
    for name, candidate, scenario, refusal, env in cases:
        ip, sp = out / (name + '-item.json'), out / (name + '-scenario.json')
        ip.write_text(json.dumps(candidate)); sp.write_text(json.dumps(scenario))
        proc = subprocess.run([sys.executable, str(w.HERE / 'workbench.py'), 'run', '--no-build',
            '--item', str(ip), '--scenario', str(sp), '--out', str(out / name), '--review', 'none'],
            cwd=w.ROOT, env={**os.environ, **env}, capture_output=True, text=True, timeout=240)
        (out / (name + '.log')).write_text(proc.stdout + '\n' + proc.stderr)
        tp = out / name / 'native.json'
        trace = w.read_native_json(tp) if tp.exists() else {}
        traces[name] = trace
        check(name + '-result', proc.returncode == (2 if refusal else 0)
              and trace.get('status') == ('error' if refusal else 'passed'))
        if refusal:
            check(name + '-exact-refusal', refusal in trace.get('error', '')
                  and not trace.get('snapshots') and not trace.get('nativeRender', {}).get('frames'))
            continue
        check(name + '-unchanged-input', (out / name / 'item.json').is_file()
              and w.digest(ip) == w.digest(out / name / 'item.json'))
        render = trace.get('nativeRender', {})
        for key, value in resource_checks(render, args.texture).items():
            # VFX-off intentionally selects no library texture.
            if name != 'vfx-off' or key != 'selected-original-texture':
                check(name + '-' + key, value)
        if name == 'no-capture':
            check('no-capture-no-fabricated-frames', render.get('capture') is False and render.get('frames') == [])
            continue
        try:
            checks, pixels[name] = frame_checks(trace, tp, scenario['ticks'])
            for key, value in checks.items(): check(name + '-' + key, value)
        except (ValueError, OSError) as error:
            check(name + '-native-png-integrity: ' + str(error), False)
    hit, repeat, silent = (traces[n] for n in ('hit', 'repeat', 'no-capture'))
    for key, value in lifecycle_checks(hit).items(): check(key, value)
    render = hit.get('nativeRender', {})
    live_ticks = [s['tick'] for s in render.get('snapshots', []) if s.get('particleCount', 0) > 0]
    check('real-hit-visible-native-pixels-only-during-life', bool(live_ticks) and pixels.get('hit') == live_ticks)
    for name in ('repeat', 'no-capture', 'vfx-off'):
        check(name + '-same-native-gameplay', bool(hit.get('snapshots')) and hit.get('snapshots') == traces[name].get('snapshots'))
    for name in ('repeat', 'no-capture'):
        check(name + '-same-native-particles', bool(render.get('snapshots'))
              and render.get('snapshots') == traces[name].get('nativeRender', {}).get('snapshots'))
    check('fresh-process-exact-pixel-repeat', bool(render.get('frames'))
          and [f['sha256'] for f in render.get('frames', [])]
          == [f['sha256'] for f in repeat.get('nativeRender', {}).get('frames', [])])
    for name in ('vfx-off', 'miss', 'no-use'):
        states = traces[name].get('nativeRender', {}).get('snapshots', [])
        check(name + '-blank-without-stale-particles', pixels.get(name) == [] and bool(states)
              and all(s.get('particleCount') == 0 and s.get('materialRecordCount') == 0 for s in states))
    summary = dict(passed=all(r['passed'] for r in rows), fullGameParity=False, checks=rows,
        scope='Current synthetic fixture, real ParticleLibrary/Luminance resources and native PNGs; no item/world artwork or sound approval.')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
