#!/usr/bin/env python3
"""Explicit synthetic held history: final native pose, lifetime and draw controls; no craft-quality claim."""
import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageDraw
import workbench as w


def pose_checks(trace, scene, item):
    """Compare recorded history to independently observed final body DrawData, not helper output."""
    positions = {}
    errors = []
    rotations = []
    trail = item['vfxManifest']['slots'][0]['trail'] if item['vfxManifest']['slots'] else None
    if trail is None:
        return not any(f.get('activeProjectileVfx', {}).get('heldHistoryDraws', []) for f in trace['nativeRender']['frames'])
    angle = math.radians(item['visual']['forwardAngleDegrees'])
    for frame in trace['nativeRender']['frames']:
        bodies = [b for b in frame['nativePlayerDrawData'] if b['textureIdentity'] == 'generated_held_item']
        if bodies:
            body = bodies[0]
            width, height = body['sourceWidth'], body['sourceHeight']
            x, y = width / 2, height / 2
            if trail['source'] == 'tip':
                ax, ay = math.cos(angle), math.sin(angle)
                edge = min(width / 2 / abs(ax) if abs(ax) > 1e-6 else math.inf,
                           height / 2 / abs(ay) if abs(ay) > 1e-6 else math.inf)
                x += ax * edge
                y += ay * edge
            if 'FlipHorizontally' in body['effects']:
                x = width - x
            if 'FlipVertically' in body['effects']:
                y = height - y
            x = (x - body['originX']) * body['scaleX']
            y = (y - body['originY']) * body['scaleY']
            cosine, sine = math.cos(body['rotation']), math.sin(body['rotation'])
            positions[frame['tick']] = (body['positionX'] + x*cosine - y*sine + scene['nativeRender']['cameraX'],
                body['positionY'] + x*sine + y*cosine + scene['nativeRender']['cameraY'], body['rotation'])
        for draw in frame.get('activeProjectileVfx', {}).get('heldHistoryDraws', []):
            for sample in draw['samples']:
                expected = positions[sample['tick']]
                errors.append(math.hypot(sample['position']['x']-expected[0], sample['position']['y']-expected[1]))
            if trail['draw'] == 'sprites':
                chosen = [s for s in draw['samples'] if 0 <= frame['tick']-s['tick'] < trail['historyTicks']
                    and (frame['tick']-s['tick']-trail['firstSampleAgeTicks']) % trail['sampleStepTicks'] == 0]
                if len(chosen) != len(draw['geometry']):
                    return False
                for sample, geometry in zip(chosen, draw['geometry']):
                    tick = sample['tick'] if trail['pose'] == 'sampled' else frame['tick']
                    rotations.append(abs(positions[tick][2]-geometry['rotation']))
    return bool(errors) and max(errors) < .001 and max(rotations, default=0) < .001


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    w.native_executable(args.no_build)
    item = w.read_json(w.HERE/'fixtures/synthetic-client-contact.json')
    # Deliberate test publication, never used as a fallback for authored art.
    image = Image.new('RGBA', (64, 16))
    ImageDraw.Draw(image).polygon([(0, 6), (48, 6), (48, 0), (63, 8), (48, 15), (48, 10), (0, 10)], fill=(240, 220, 80, 255))
    buffer = io.BytesIO(); image.save(buffer, format='PNG'); raw = buffer.getvalue()
    identity = json.dumps([item['id'], 'item', '', item['id']], separators=(',', ':')).encode('ascii')
    publication = out/('infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png')
    publication.write_bytes(raw)
    item['visual'].update(spritePath=publication.name, spriteStatus='generated', renderSizePx=64, forwardAngleDegrees=0)
    for entity in item['runtimeProgram']['entities']:
        if entity['kind'] == 'item_body':
            entity['visual'].update(assetMode='baked_sprite', spritePath=publication.name, spriteStatus='generated')
    trail = dict(draw='stroke', source='center', historyTicks=16, sampleStepTicks=1, firstSampleAgeTicks=0,
        opacityProfile=dict(start=.8, middle=.5, end=0, curve='linear'), color=dict(r=100, g=170, b=255), widthPx=3)
    item['vfxManifest']['slots'] = [dict(id='held', entityId=item['runtimeProgram']['itemEntityId'], event='on_use',
        rendererKind='historyTrail', anchor='self', layer='AfterPlayer', blend='alpha', trail=trail)]
    scene = w.read_json(w.HERE/'scenarios/client-contact.json')
    scene.update(playerUpdate='client_vfx', nativeRender=dict(width=320, height=256, cameraX=700, cameraY=540,
        zoom=2, capture=True, drawArtwork=True, drawPlayer=True, lightingMode='viewport_fill', artworkFiles=[str(publication)]))
    scene['player']['y'] = 710
    scene['assertions'] = [dict(kind='no_nonfinite')]
    names = ['baseline', 'center', 'tip_before', 'sampled', 'current', 'zero', 'budget_zero', 'switch', 'repeat', 'inverted_left', 'mid_use_flip']
    traces, rows = {}, []
    for name in names:
        candidate, scenario = copy.deepcopy(item), copy.deepcopy(scene)
        slot = candidate['vfxManifest']['slots'][0]; design = slot['trail']
        if name == 'baseline': candidate['vfxManifest']['slots'] = []
        if name == 'tip_before': design['source'] = 'tip'; slot['layer'] = 'BeforePlayer'
        if name in ('sampled', 'current'):
            design.pop('widthPx'); design.update(draw='sprites', scale=1, pose=name, sampleStepTicks=3,
                texture=dict(source='item', assetId='', uv=dict(quarterTurns=0, mirrorU=False, mirrorV=False)))
        if name == 'zero': design['widthPx'] = 0
        if name == 'budget_zero': candidate['vfxManifest']['budget']['maxDrawCalls'] = 0
        if name == 'switch': scenario['actions'].append(dict(tick=12, kind='select_slot', slot=1))
        if name == 'repeat':
            scenario['ticks'] = 70
            scenario['actions'] += [dict(tick=34, kind='primary'), dict(tick=35, kind='release')]
        if name == 'mid_use_flip':
            scenario['player']['gravitationPotion'] = True
            scenario['actions'] += [dict(tick=6, kind='controls', left=True, right=False, jump=False, up=True),
                                    dict(tick=8, kind='controls', left=False, right=True, jump=False, up=False)]
        if name == 'inverted_left':
            scenario['player'].update(direction=-1, gravityDirection=-1, gravitationPotion=True)
            scenario['tiles'] = [dict(tileX=1, tileY=42, width=97, height=1)]
            scenario['nativeRender']['cameraX'] -= 17
            scenario['nativeRender']['cameraY'] -= 11
        ip, sp = out/(name+'-item.json'), out/(name+'-scene.json')
        ip.write_text(json.dumps(candidate)); sp.write_text(json.dumps(scenario))
        command = [sys.executable, str(w.HERE/'workbench.py'), 'run', '--no-build', '--item', str(ip),
            '--scenario', str(sp), '--out', str(out/name), '--review', 'native', '--gif']
        proc = subprocess.run(command, cwd=w.ROOT, capture_output=True, text=True, timeout=240)
        (out/(name+'.log')).write_text(proc.stdout+'\n'+proc.stderr)
        trace_path = out/name/'native.json'
        trace = w.read_json(trace_path) if trace_path.exists() else {}; traces[name] = trace
        frames = trace.get('nativeRender', {}).get('frames', [])
        submissions = sum(d['submittedSegments'] for f in frames for d in f.get('activeProjectileVfx', {}).get('heldHistoryDraws', []))
        passed = proc.returncode == 0 and trace.get('status') == 'passed' and bool(frames)
        passed = passed and pose_checks(trace, scenario, candidate) and not any(f['drawChangedMainRng'] for f in frames)
        passed = passed and (submissions == 0 if name in ('baseline', 'zero', 'budget_zero') else submissions > 0)
        if name == 'switch': passed = passed and not any(f.get('activeProjectileVfx', {}).get('heldHistoryDraws', []) for f in frames if f['tick'] >= 12)
        if name == 'mid_use_flip':
            body_poses = [b for f in frames for b in f.get('nativePlayerDrawData', []) if b['textureIdentity']=='generated_held_item']
            flags = {('FlipHorizontally' in b['effects'], 'FlipVertically' in b['effects']) for b in body_poses}
            passed = passed and {(False, False), (True, True), (False, True)} <= flags
        if name == 'repeat':
            start = next(f for f in frames if f['tick'] == 34)['activeProjectileVfx']['heldHistoryDraws']
            passed = passed and bool(start) and all(len(d['samples']) == 1 and d['samples'][0]['tick'] == 34 for d in start)
        if name in ('center', 'tip_before', 'sampled', 'current', 'zero', 'budget_zero'):
            passed = passed and all(trace.get(key) == traces['baseline'].get(key) for key in ('snapshots', 'combat', 'resources', 'timeline'))
        rows.append(dict(name=name, passed=passed, submissions=submissions, nativeStatus=trace.get('status'), trace=str(trace_path)))
        print(name+': '+('PASS' if passed else 'FAIL'), flush=True)
        if proc.returncode: break
    negatives = ['missing_body_png', 'missing_native_player', 'wrong_layer', 'hidden_source']
    for name in negatives:
        candidate, scenario = copy.deepcopy(item), copy.deepcopy(scene)
        if name == 'missing_body_png': scenario['nativeRender']['artworkFiles'] = []
        if name == 'missing_native_player': scenario['nativeRender']['drawPlayer'] = False
        if name == 'wrong_layer': candidate['vfxManifest']['slots'][0]['layer'] = 'AfterProjectiles'
        if name == 'hidden_source': candidate['runtimeProgram']['itemUse']['hideUseGraphic'] = True
        ip, sp = out/(name+'-item.json'), out/(name+'-scene.json')
        ip.write_text(json.dumps(candidate)); sp.write_text(json.dumps(scenario))
        proc = subprocess.run([sys.executable, str(w.HERE/'workbench.py'), 'run', '--no-build', '--item', str(ip),
            '--scenario', str(sp), '--out', str(out/name)], cwd=w.ROOT, capture_output=True, text=True, timeout=240)
        (out/(name+'.log')).write_text(proc.stdout+'\n'+proc.stderr)
        path = out/name/'native.json'; trace = w.read_json(path) if path.exists() else {}
        reason = {'missing_body_png':'Missing explicit artwork', 'missing_native_player':'historyTrail requires drawPlayer',
                  'wrong_layer':'held item history requires', 'hidden_source':'held item history requires'}[name]
        passed = proc.returncode == 2 and trace.get('status') == 'error' and reason in trace.get('error', '')
        rows.append(dict(name=name, passed=passed, nativeStatus=trace.get('status'), trace=str(path)))
        print(name+': '+('PASS' if passed else 'FAIL'), flush=True)
    summary = dict(passed=all(r['passed'] for r in rows) and len(rows)==len(names)+len(negatives), checks=rows,
        scope='Original native held DrawData and cosmetic history; synthetic arrow artwork, not generated craft quality or full-game parity.')
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    return 0 if summary['passed'] else 1

if __name__ == '__main__':
    sys.exit(main())
