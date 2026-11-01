#!/usr/bin/env python3
"""Exercise original NPC hit dust and on-hit sprite/ring draws with real native capture.

The extra impact sprite is an explicitly synthetic regression fixture. It is
published using the normal identity, never substituted for an authored asset.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

import workbench as w


def events(trace, kind):
    return [(s['tick'], e) for s in trace['snapshots'] for e in s.get('events', []) if e.get('kind') == kind]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--item', type=Path, required=True, help='Built public lunar-harpoon item')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh hit-feedback output directory')
    out.mkdir(parents=True, exist_ok=True)

    original = w.read_json(args.item)
    positive = copy.deepcopy(original)
    entity = next(e for e in positive['runtimeProgram']['entities'] if e['id'] == 'harpoon')
    image = Image.new('RGBA', (32, 32))
    draw = ImageDraw.Draw(image)
    draw.ellipse((3, 3, 28, 28), fill=(255, 45, 180, 255))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    raw = buffer.getvalue()
    identity = [positive['id'], 'impact', entity['id'], positive['id'] + '_' + entity['id'] + '_impact']
    digest = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode('ascii') + b'\0' + raw).hexdigest()
    art = out / ('infini_asset_png_' + digest + '.png')
    art.write_bytes(raw)
    entity['visual'].update(impactSpritePath=str(art), impactSpriteStatus='generated')
    common = {'entityId': entity['id'], 'event': 'on_hit', 'anchor': 'hitPoint',
              'blend': 'additive', 'layer': 'AfterProjectiles',
              'scale': 1, 'duration': 14, 'alpha': 0.95, 'phaseOffset': 0,
              'color': {'r': 255, 'g': 255, 'b': 255}}
    positive['vfxManifest']['slots'] += [
        {**common, 'id': 'test_hit_sprite', 'rendererKind': 'impactSprite', 'textureRole': 'impact', 'slotSeed': 41},
        {**common, 'id': 'test_hit_ring', 'rendererKind': 'impactRing', 'particleSystemId': 'none',
         'density': 0.65, 'spread': 0, 'startTick': 0, 'repeatEvery': 0, 'slotSeed': 42},
    ]
    hit_item = out / 'hit-impact.json'
    hit_item.write_text(json.dumps(positive), encoding='utf-8')
    control_item = out / 'hit-control.json'
    control_item.write_text(json.dumps(original), encoding='utf-8')

    traces = {}
    for name, item, x in [('hit', hit_item, 848), ('control', control_item, 848), ('miss', hit_item, 1300)]:
        target = {'nativeType': 'zombie', 'x': x, 'y': 700, 'width': 32, 'height': 48, 'life': 10000}
        case = out / name
        cmd = [sys.executable, str(w.HERE / 'workbench.py'), 'probe', '--item', str(item), '--gif',
               '--ticks', '85', '--hold', '35', '--gif-stride', '2', '--out', str(case),
               '--set', 'dummy=' + json.dumps(target)]
        if args.no_build:
            cmd.append('--no-build')
        proc = subprocess.run(cmd, cwd=w.ROOT, capture_output=True, text=True, timeout=360)
        (out / (name + '.log')).write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
        if proc.returncode != 0:
            raise RuntimeError(name + ' native probe failed: ' + proc.stderr[-2000:])
        result = w.read_json(case / 'probe-result.json')
        if not result.get('passed') or len(result.get('cases', [])) != 1:
            raise RuntimeError(name + ' has no passing native probe result')
        run = case / 'runs' / result['cases'][0]['run']
        traces[name] = (w.read_json(run / 'native.json'), run)

    hit, hit_dir = traces['hit']
    control, control_dir = traces['control']
    miss, _ = traces['miss']
    hits = events(hit, 'hit')
    feedback = events(hit, 'native_npc_hit_effect')
    created = [(tick, row) for tick, row in feedback if row['npcType'] == 3 and not row['dedServ'] and row['newActiveDust']]
    if not hits or not created or events(miss, 'hit') or events(miss, 'native_npc_hit_effect'):
        raise RuntimeError('Expected zombie hit and native NPC.HitEffect dust only on the hit path')
    if [t for t, _ in hits] != [t for t, _ in events(control, 'hit')]:
        raise RuntimeError('The effect ablation changed native hit timing')

    visual = hit['nativeRender']
    start = hits[0][0]
    after = [s for s in visual['snapshots'] if s['tick'] >= start]
    sprite = [d for s in after for d in s.get('detached', []) if d.get('texturePath', '').endswith(art.name)]
    ring = [d for s in after for d in s.get('detached', []) if d.get('primitiveKind') == 'ImpactRing']
    if not sprite or not ring:
        raise RuntimeError('On-hit impact sprite and ring did not reach the original detached renderer')
    if any(d.get('texturePath', '').endswith(art.name) or d.get('primitiveKind') == 'ImpactRing'
           for s in miss['nativeRender']['snapshots'] for d in s.get('detached', [])):
        raise RuntimeError('On-hit effects were emitted on a miss')
    if not any(s.get('nativeDustBeforeDraw') and s.get('nativeDustDrawExecuted') for s in after):
        raise RuntimeError('Native hit dust was not present during original Main.DrawDust')

    control_frames = {f['tick']: f for f in control['nativeRender']['frames']}
    changed = 0
    for frame in visual['frames']:
        if not start <= frame['tick'] < start + 14:
            continue
        other = control_frames[frame['tick']]
        with Image.open(hit_dir / frame['path']) as a, Image.open(control_dir / other['path']) as b:
            if ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox():
                changed += 1
    if changed == 0:
        raise RuntimeError('Hit effects did not produce any different rendered pixels')
    summary = {'passed': True, 'scope': 'Native NPC.HitEffect/NPCLoader dust and original on-hit impact sprite/ring; synthetic control art',
               'hitTicks': [t for t, _ in hits], 'nativeHitEffectsWithNewDust': created,
               'impactSpriteRecords': len(sprite), 'impactRingRecords': len(ring),
               'changedFramesVersusEffectAblation': changed, 'missHits': 0}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
