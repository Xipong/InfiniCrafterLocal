#!/usr/bin/env python3
"""Native bow/projectile pixels, ammo and refusal controls; no gameplay simulation."""
import argparse
import copy
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import workbench as w
from native_review import native_frames, export_native_review

BOWS = [('daedalus-wooden', 'DaedalusStormbow', 40, 1),
        ('pulse-wooden', 'PulseBow', 40, 357), ('pulse-holy', 'PulseBow', 516, 357),
        ('hellwing-wooden', 'HellwingBow', 40, 485), ('hellwing-holy', 'HellwingBow', 516, 91)]


def scenes(asset_root):
    base = w.read_json(w.HERE/'scenarios/daedalus-stormbow.json')
    base['vanillaAssetRoot'] = str(asset_root)
    rows = []
    for name, bow, ammo, projectile in BOWS:
        scene = copy.deepcopy(base)
        scene['inventory'][0]['itemId'] = ammo
        scene['assertions'][0]['id'] = projectile
        if bow != 'DaedalusStormbow':
            scene['player']['x'] = 600
            scene['nativeRender'].update(width=960, height=640, cameraX=350, cameraY=1830)
            scene['tiles'].append(dict(tileX=83, tileY=110, width=1, height=30))
        rows.append((name, bow, scene, 0, ''))
    negative = copy.deepcopy(base)
    negative['inventory'] = []
    negative['nativeRender']['capture'] = False
    rows.append(('no-ammo', 'DaedalusStormbow', negative, 1, ''))
    legacy = copy.deepcopy(base)
    legacy['nativeRender']['drawVanillaProjectiles'] = False
    rows.append(('legacy-pose', 'DaedalusStormbow', legacy, 0, ''))
    offscreen = copy.deepcopy(base)
    offscreen['nativeRender'].update(cameraX=-3000, drawNativeDust=False)
    offscreen['assertions'] = [base['assertions'][0], dict(kind='no_nonfinite')]
    rows.append(('offscreen', 'DaedalusStormbow', offscreen, 0, ''))
    for capture in (True, False):
        scene = copy.deepcopy(base)
        scene.update(ticks=30, actions=scene['actions'][:2])
        scene['assertions'] = [scene['assertions'][0], dict(kind='no_nonfinite')]
        scene['nativeRender'].update(capture=capture, drawNativeDust=False)
        rows.append(('no-dust-captured' if capture else 'no-capture', 'DaedalusStormbow', scene, 0, ''))
    unsupported = copy.deepcopy(base)
    unsupported['inventory'][0]['itemId'] = 41  # Flaming Arrow, native projectile2.
    unsupported['ticks'] = 4
    unsupported['actions'] = unsupported['actions'][:2]
    rows.append(('unsupported-projectile', 'DaedalusStormbow', unsupported, 2, 'Native projectile draw requires pinned Projectile_2.png'))
    wrong = copy.deepcopy(base)
    wrong['nativeRender']['drawPlayer'] = False
    rows.append(('wrong-mode', 'DaedalusStormbow', wrong, 2, 'drawVanillaProjectiles requires'))
    bullet = copy.deepcopy(base)
    bullet['inventory'][0]['itemId'] = 97
    bullet['assertions'][0]['id'] = 14
    rows.append(('bullet', 'Minishark', bullet, 0, ''))
    return rows


COMPLEX = [
    ('nebula', 'NebulaBlaze', None, [634, 635], 240, 180),
    ('prism', 'LastPrism', None, [633, 632], 240, 180),
    ('prism-mana', 'LastPrism', None, [633, 632], 300, 240),
    ('eventide', 'FairyQueenRangedItem', 40, [932], 180, 120),
    ('charged', 'ChargedBlasterCannon', None, [460, 461, 459], 420, 360),
    ('heat-ray', 'HeatRay', None, [260], 180, 120),
    ('flaming-arrow', 'WoodenBow', 41, [2], 180, 120),
]


def complex_scenes(asset_root):
    """Test inputs only; production Terraria supplies every weapon mechanic."""
    base = w.read_json(w.HERE/'scenarios/daedalus-stormbow.json')
    rows = []
    for name, item, ammo, projectiles, ticks, hold in COMPLEX:
        scene = copy.deepcopy(base)
        scene['vanillaAssetRoot'] = str(asset_root)
        scene['ticks'] = ticks
        scene['player']['x'] = 600
        scene['actions'][-1]['tick'] = hold
        scene['inventory'] = [] if ammo is None else [dict(slot=54, itemId=ammo, stack=999)]
        if name == 'prism-mana':
            scene['inventory'] = [dict(slot=1, itemId=189, stack=2)]
            scene['actions'].append(dict(kind='quick_mana', tick=140))
        scene['assertions'] = [dict(kind='native_projectile_seen', id=p) for p in projectiles]
        scene['assertions'] += [dict(kind='hit_count_at_least', minimum=1), dict(kind='no_nonfinite')]
        scene['nativeRender'].update(width=960, height=640, cameraX=350, cameraY=1830)
        # Native LaserScan needs room beyond the held beam; tiny worlds clamp it.
        if name in ('prism', 'prism-mana', 'heat-ray'):
            scene['worldWidthTiles'] = 400
            scene['tiles'][0]['width'] = 397
            scene['player']['x'] = 800
            scene['nativeRender']['cameraX'] = 500
        if name == 'flaming-arrow':
            # The ordinary bow arc reaches a nearer target before the real floor.
            scene['player']['x'] = 800
        if name == 'heat-ray':
            # 100 native extraUpdates cross a nearby target before the first render.
            # Keep real speed/lifetime and place the target beyond one frame's travel.
            scene['dummy']['tileX'] = 175
            scene['actions'][0]['x'] = 2816
            scene['nativeRender'].update(width=1024, cameraX=1300, cameraY=1700, zoom=0.4)
        rows.append((name, item, scene, 0, ''))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vanilla-assets', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--native-dll', type=Path, help='Independently built executable; retain its source/reference receipt')
    p.add_argument('--no-build', action='store_true')
    p.add_argument('--gif', action='store_true', help='Export each passing bow as native PNG review/GIF')
    p.add_argument('--complex', action='store_true', help='Include channelled/beam/conditional vanilla cases; requires their explicit pinned PNGs')
    p.add_argument('--case', action='append', help='Run only named cases; no full-matrix acceptance claim')
    a = p.parse_args()
    if a.native_dll and not a.no_build: p.error('--native-dll requires --no-build')
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()): p.error('Use a fresh evidence directory')
    rows = scenes(a.vanilla_assets.resolve())
    if a.complex: rows += complex_scenes(a.vanilla_assets.resolve())
    if a.case:
        unknown = set(a.case) - {r[0] for r in rows}
        if unknown: p.error('Unknown cases: ' + ', '.join(sorted(unknown)))
        rows = [r for r in rows if r[0] in a.case]
    out.mkdir(parents=True, exist_ok=True)
    dll = a.native_dll.resolve() if a.native_dll else w.native_executable(a.no_build)[0]
    binary_hash = w.digest(dll)
    command = [os.environ.get('DOTNET', 'dotnet'), str(dll)]
    # Missing/corrupted resources are separate explicit inputs, never edits to source assets.
    if not a.case:
        for name in ('missing-texture', 'tampered-texture'):
            root = out/name/'assets/Images'; root.mkdir(parents=True)
            for file in ('Item_3029.png', 'Projectile_1.png', 'Projectile_14.png',
                         'Projectile_91.png', 'Projectile_92.png', 'Projectile_357.png', 'Projectile_485.png',
                         'Projectile_982.png', 'Extra_98.png'):
                if name == 'missing-texture' and file == 'Projectile_1.png': continue
                shutil.copyfile(a.vanilla_assets.resolve()/'Images'/file, root/file)
            ripples = a.vanilla_assets.resolve()/'Images/Misc/Ripples.png'
            if ripples.exists():
                (root/'Misc').mkdir(exist_ok=True)
                shutil.copyfile(ripples, root/'Misc/Ripples.png')
            if name == 'tampered-texture':
                path = root/'Projectile_485.png'; path.write_bytes(path.read_bytes() + b'corrupt')
            scene = copy.deepcopy(rows[0][2]); scene['vanillaAssetRoot'] = str(root.parent)
            rows.append((name, 'DaedalusStormbow', scene, 2, 'Native projectile draw requires pinned Projectile_1.png' if name == 'missing-texture' else 'Vanilla asset PNG'))
    results = []; traces = {}
    for name, bow, scene, expected, reason in rows:
        directory = out/name; directory.mkdir(exist_ok=True)
        if name == 'unsupported-projectile':
            private = directory/'missing-projectile-assets'/'Images'; private.mkdir(parents=True)
            for source in (a.vanilla_assets.resolve()/'Images').rglob('*.png'):
                if source.name != 'Projectile_2.png':
                    destination = private/source.relative_to(a.vanilla_assets.resolve()/'Images')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
            scene['vanillaAssetRoot'] = str(private.parent)
        sp = directory/'scenario.json'; sp.write_text(json.dumps(scene, indent=2))
        process = subprocess.run(command + ['--vanilla-item', bow, '--scenario', str(sp), '--output', str(directory/'native.json')],
                                 cwd=w.ROOT, capture_output=True, text=True, timeout=240)
        (directory/'process.log').write_text(process.stdout + process.stderr)
        trace = w.validate_trace(w.read_native_json(directory/'native.json')); traces[name] = trace
        events = [e for s in trace['snapshots'] for e in s.get('events', [])]
        failed = sorted(c['name'] for c in trace['assertions'] if c['status'] == 'failed')
        checks = dict(nativeOutcome=process.returncode==expected and trace['status']=={0:'passed', 1:'failed', 2:'error'}[expected],
                      binaryUnchanged=w.digest(dll)==binary_hash,
                      exactFailures=failed==(['hit_count_at_least', 'native_projectile_seen'] if expected==1 else []),
                      refusalReason=reason.lower() in trace.get('error', '').lower())
        frames = trace.get('nativeRender', {}).get('frames', [])
        if expected != 2:
            checks['completeTimeline'] = trace['timeline']['complete'] and trace['timeline']['completedTicks']==scene['ticks']
        if frames: checks['pngIntegrity'] = len(native_frames(trace, directory/'native.json'))==scene['ticks']
        if name in {r[0] for r in BOWS + COMPLEX} or name=='bullet':
            checks['nativeSpriteSubmitted'] = any(f['projectileDrawCount']>0 and f['projectileGeometry'] for f in frames)
            ammo_rows = [row for row in scene['inventory'] if row['slot'] >= 54]
            if ammo_rows:
                checks['ammoSource'] = any(e['kind']=='spawn' and e.get('ammoItemIdUsed')==ammo_rows[0]['itemId'] for e in events)
            checks['noGeneratedReplacement'] = all(f['nativeProxyVetoCount']==0 and f.get('nativeGeneratedHeldDrawDataCount',0)==0 for f in frames)
            checks['viewportBeforeGameplay'] = trace['nativeRender'].get('viewportAppliedBeforeGameplay') is True
            checks['worldAimPreserved'] = all(abs(s['player']['aimX']-scene['actions'][0]['x'])<1 and abs(s['player']['aimY']-scene['actions'][0]['y'])<1 for s in trace['snapshots'] if s['tick']>=0)
            if name.startswith('pulse-'):
                checks['nativePulseReplacement'] = {e['nativeType'] for e in events if e['kind']=='spawn'}=={357}
                checks['nativeDustVisible'] = any(s.get('nativeDustAfterDraw') for s in trace['nativeRender']['snapshots'])
            if name=='hellwing-holy': checks['nativeChildStar'] = any(e['kind']=='spawn' and e['nativeType']==92 for e in events)
            if a.gif and name in {r[0] for r in BOWS + COMPLEX}:
                export_native_review(trace, directory/'native.json', directory/'review', True, max(2, (scene['ticks'] + 79)//80))
        if expected != 2 and scene.get('nativeRender', {}).get('drawVanillaProjectiles'):
            water = trace.get('nativeRender', {}).get('waterDistortion', {})
            checks['genuineWaterShaderLifecycle'] = (
                water.get('shaderType') == 'Terraria.GameContent.Shaders.WaterShaderData'
                and water.get('constructor') == 'WaterShaderData(FilterWaterDistortion)'
                and water.get('aiImplementationReplaced') is False
                and water.get('worldWaterPostprocessing') == 'notRun'
                and water.get('eventHandlersDetached') == 3
                and water.get('cleanup') == 'complete')
        if name in {r[0] for r in COMPLEX}:
            expected_types = next(r[3] for r in COMPLEX if r[0] == name)
            visible_types = {v['nativeType'] for f in frames for v in f.get('nativeVanillaDrawVisits', []) if v.get('spriteDrawCount', 0) > 0}
            checks['requiredNativeSpritesObserved'] = set(expected_types) <= visible_types
            checks['nativeDrawOwnershipNoDuplicates'] = all(
                max(Counter((v['nativeSlot'], v['nativeIdentity']) for v in f.get('nativeVanillaDrawVisits', [])).values(), default=0) <= 1
                for f in frames)
            if name == 'prism-mana':
                quick = [e for e in events if e['kind'] == 'input' and e.get('input') == 'quick_mana']
                checks['quickManaNativeEvent'] = (len(quick) == 1 and quick[0].get('nativeMethod') == 'Player.QuickMana'
                                                and quick[0].get('manaSicknessPresent') is True
                                                and quick[0].get('selectedSlotBefore') == quick[0].get('selectedSlotAfter'))
                final_inventory = trace['snapshots'][-1]['player']['inventory']
                checks['onePotionConsumed'] = any(i['slot'] == 1 and i['nativeType'] == 189 and i['stack'] == 1 for i in final_inventory)
                checks['fullChargeBeamObserved'] = any(
                    p['nativeType'] == 632 and p['active'] and p['damage'] > 200
                    for snapshot in trace['snapshots'] for p in snapshot.get('projectiles', []))
            if name == 'charged':
                checks['hiddenBeamDrawnByNativeOwner'] = any(
                    h['nativeType'] == 461 and h.get('visitedByNativeOwner') for f in frames for h in f.get('hiddenNativeProjectiles', []))
        if name=='no-ammo': checks['noInventedShots'] = not any(e['kind'] in ('spawn','hit','native_ammo_consumption') for e in events)
        if name=='legacy-pose': checks['legacyOmissionPreserved'] = any(f['unrenderedVanillaProjectiles'] for f in frames) and not any(f['projectileDrawCount'] for f in frames)
        if name=='offscreen':
            checks['culledNotCountedAsSprite'] = any(f['vanillaProjectileDrawAttemptCount'] for f in frames) and not any(f['projectileDrawCount'] or f['projectileGeometry'] for f in frames) and not trace['nativeRender']['vanillaProjectileDrawExecuted']
        if name=='no-capture':
            render = trace['nativeRender']
            checks['drawWithoutPngOrDust'] = not frames and render['gpuRenderLifecycleExecuted'] and any(s.get('nativeDrawCounters',{}).get('projectileDrawCount',0)>0 for s in render['snapshots'])
            checks['sameNativeLifecycle'] = trace['snapshots']==traces['no-dust-captured']['snapshots'] if 'no-dust-captured' in traces else False
        result = dict(name=name, passed=all(checks.values()), checks=checks,
                      spawns=sum(e['kind']=='spawn' for e in events), hits=sum(e['kind']=='hit' for e in events),
                      damage=sum(e['damageDone'] for e in events if e['kind']=='hit'), frames=len(frames),
                      nativeTraceSha256=w.digest(directory/'native.json'), scenarioSha256=w.digest(sp))
        results.append(result); print(json.dumps(result), flush=True)
        (out/'summary.json').write_text(json.dumps(dict(passed=False, complete=False, cases=results, nativeDllSha256=binary_hash), indent=2))
    summary = dict(passed=all(r['passed'] for r in results), complete=True, selection='subset' if a.case else 'full', cases=results,
                   nativeDllSha256=binary_hash, sourceSha256=w.source_fingerprint(),
                   scope='Original native player/projectile/dust and training dummy in controlled scene. No complete Main.Draw/world, Gore rendering, audio or multiplayer parity. Draw submission is not aesthetic approval.')
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    return int(not summary['passed'])


if __name__ == '__main__': raise SystemExit(main())
