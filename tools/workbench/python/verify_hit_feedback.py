#!/usr/bin/env python3
"""Exercise original NPC hit dust and on-hit sprite/ring draws with real native capture.

The extra spriteElement is an explicitly synthetic regression fixture. It is
published using the normal identity, never substituted for an authored asset.
"""
from __future__ import annotations

# Direct script entrypoints resolve the same package as workbench.py.
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import copy
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from PIL import Image, ImageChops, ImageDraw

import workbench as w


def events(trace, kind):
    return [(s['tick'], e) for s in trace['snapshots'] for e in s.get('events', []) if e.get('kind') == kind]


def hit_effect_slots(entity_id: str, asset_id: str) -> list[dict[str, Any]]:
    """Fresh current-wire controls; never changes the supplied authored definition."""
    color = dict(r=255, g=255, b=255)
    ramp = dict(start=1, middle=1, end=1, curve='linear')
    common = dict(entityId=entity_id, event='on_hit', anchor='hitPoint', blend='additive',
                  layer='AfterProjectiles', duration=14, startTick=0, repeatEvery=0)
    return [
        dict(**common, id='test_hit_sprite', rendererKind='spriteElement', slotSeed=41, alpha=.95,
             element=dict(texture=dict(source='asset', assetId=asset_id,
                                       uv=dict(quarterTurns=0, mirrorU=False, mirrorV=False)),
                          spawn=dict(shape='point'), attachment='world', count=1,
                          offsetForwardPx=0, offsetSidePx=0, speedMinPxPerTick=0, speedMaxPxPerTick=0,
                          spreadRadians=0, inheritVelocity=0, drag=1,
                          accelerationXPxPerTickSquared=0, accelerationYPxPerTickSquared=0,
                          rotationRadians=0, rotationSpeedRadiansPerTick=0, widthPx=32, heightPx=32,
                          widthProfile=copy.deepcopy(ramp), heightProfile=copy.deepcopy(ramp),
                          opacityProfile=copy.deepcopy(ramp),
                          colorProfile=dict(start=copy.deepcopy(color), middle=copy.deepcopy(color),
                                            end=copy.deepcopy(color), curve='linear'))),
        dict(**common, id='test_hit_ring', rendererKind='shape', slotSeed=42,
             shape=dict(kind='arc', attachment='world', rotationFrame='world',
                        offsetForwardPx=0, offsetSidePx=0, rotationRadians=0, rotationSpeedRadiansPerTick=0,
                        colorStart=copy.deepcopy(color), colorEnd=copy.deepcopy(color),
                        opacityStart=.95, opacityEnd=0, opacityCurve='linear',
                        radiusStartPx=8, radiusEndPx=24, widthPx=3, sweepRadians=math.tau,
                        segments=32, tailOpacityStart=1, tailOpacityEnd=1)),
    ]


def hit_effect_records(snapshots: list[dict[str, Any]], texture_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sprites = [d for s in snapshots for d in s.get('records', [])
               if d.get('renderer') == 'spriteElement' and d.get('texturePath', '').endswith(texture_name)
               and d.get('started') is True and d.get('particleCount', 0) > 0]
    rings = [d for s in snapshots for d in s.get('shapes', [])
             if d.get('kind') == 'arc' and d.get('attachment') == 'world'
             and d.get('rotationFrame') == 'world' and d.get('durationTicks') == 14]
    return sprites, rings


def probe_asset_arguments(item_path: Path, definition: dict[str, Any], additional: Path) -> list[str]:
    from python.probe import artwork_files
    # Preserve exact source provenance before the definition is copied into a
    # different output tree. Current DTO basenames contain no private store path.
    originals = artwork_files(item_path.resolve(), definition, [])
    directories = dict.fromkeys(Path(path).parent for path in [*originals, str(additional)])
    return [value for directory in directories for value in ('--asset-dir', str(directory))]


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
    asset_id = 'hit_feedback_sprite'
    identity = [positive['vfxManifest']['recipeId'], asset_id]
    art = w.publish_artwork(out, positive, 'vfx_' + asset_id,
        json.dumps(identity, separators=(',', ':')).encode('ascii'), raw)
    asset_arguments = probe_asset_arguments(args.item, original, art)
    positive['vfxManifest'].setdefault('assets', []).append(dict(
        id=asset_id, prompt='Synthetic uniform hit-feedback cutout', negativePrompt='', canvasSize=32,
        layout='cutout', spritePath=art.name, spriteUrl='', spriteStatus='generated', spriteTechnicalScore=1))
    positive['vfxManifest']['slots'] += hit_effect_slots(entity['id'], asset_id)
    hit_item = out / 'hit-impact.json'
    hit_item.write_text(json.dumps(positive), encoding='utf-8')
    control_item = out / 'hit-control.json'
    control_item.write_text(json.dumps(original), encoding='utf-8')

    traces = {}
    for name, item, x, visible in [('hit', hit_item, 848, True), ('control', control_item, 848, True),
                                  ('miss', hit_item, 1300, True), ('hidden', hit_item, 848, False)]:
        case = out / name
        cmd = [sys.executable, str(w.HERE / 'workbench.py'), 'probe', '--item', str(item), '--gif',
               '--ticks', '85', '--hold', '35', '--gif-stride', '2', '--out', str(case),
               '--target', 'zombie', '--set', 'dummy.x=' + str(x)]
        if not visible:
            cmd += ['--set', 'nativeRender.drawZombie=false']
        if args.no_build:
            cmd.append('--no-build')
        proc = subprocess.run(cmd + asset_arguments, cwd=w.ROOT, capture_output=True, text=True, timeout=360)
        (out / (name + '.log')).write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
        if proc.returncode != 0:
            raise RuntimeError(name + ' native probe failed: ' + proc.stderr[-2000:])
        result = w.read_json(case / 'probe-result.json')
        if not result.get('passed') or len(result.get('cases', [])) != 1:
            raise RuntimeError(name + ' has no passing native probe result')
        run = case / 'runs' / result['cases'][0]['run']
        traces[name] = (w.read_native_json(run / 'native.json'), run)

    # Original player textures are available but the optional zombie PNG is not.
    # Refuse the scene instead of substituting an invented sprite.
    source_assets = Path(os.environ['INFINI_PLAYER_ASSET_DIR'])
    missing_assets = out / 'missing-zombie-assets'
    shutil.copytree(source_assets, missing_assets,
                    ignore=lambda _dir, names: ['NPC_3.png'] if 'NPC_3.png' in names else [])
    missing_case = out / 'missing-zombie'
    cmd = [sys.executable, str(w.HERE / 'workbench.py'), 'probe', '--item', str(hit_item), '--gif',
           '--ticks', '85', '--hold', '35', '--out', str(missing_case), '--target', 'zombie']
    if args.no_build:
        cmd.append('--no-build')
    proc = subprocess.run(cmd + asset_arguments, cwd=w.ROOT, capture_output=True, text=True, timeout=360,
                          env={**os.environ, 'INFINI_PLAYER_ASSET_DIR': str(missing_assets)})
    (out / 'missing-zombie.log').write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
    missing_traces = list(missing_case.glob('runs/*/native.json'))
    if proc.returncode == 0 or len(missing_traces) != 1:
        raise RuntimeError('Missing zombie texture was not explicitly refused')
    missing = w.read_native_json(missing_traces[0])
    if missing.get('status') != 'error' or 'NPC_3.png' not in missing.get('error', '') or list(missing_case.rglob('*.gif')):
        raise RuntimeError('Missing zombie texture did not produce the expected no-fallback error')

    wrong_target = out / 'wrong-target'
    cmd = [sys.executable, str(w.HERE / 'workbench.py'), 'probe', '--item', str(hit_item), '--gif',
           '--ticks', '85', '--hold', '35', '--out', str(wrong_target), '--target', 'zombie',
           '--set', 'dummy.nativeType="target_dummy"']
    if args.no_build:
        cmd.append('--no-build')
    proc = subprocess.run(cmd + asset_arguments, cwd=w.ROOT, capture_output=True, text=True, timeout=360)
    (out / 'wrong-target.log').write_text(proc.stdout + '\n' + proc.stderr, encoding='utf-8')
    wrong_traces = list(wrong_target.glob('runs/*/native.json'))
    if proc.returncode == 0 or len(wrong_traces) != 1:
        raise RuntimeError('Zombie rendering on a different NPC was not refused')
    wrong = w.read_native_json(wrong_traces[0])
    if wrong.get('status') != 'error' or 'drawZombie requires' not in wrong.get('error', '') or list(wrong_target.rglob('*.gif')):
        raise RuntimeError('Wrong target did not produce the expected no-fallback error')

    hit, hit_dir = traces['hit']
    control, control_dir = traces['control']
    miss, _ = traces['miss']
    hidden, hidden_dir = traces['hidden']
    hits = events(hit, 'hit')
    feedback = events(hit, 'native_npc_hit_effect')
    created = [(tick, row) for tick, row in feedback if row['npcType'] == 3 and not row['dedServ'] and row['newActiveDust']]
    if not hits or not created or events(miss, 'hit') or events(miss, 'native_npc_hit_effect'):
        raise RuntimeError('Expected zombie hit and native NPC.HitEffect dust only on the hit path')
    if [t for t, _ in hits] != [t for t, _ in events(control, 'hit')]:
        raise RuntimeError('The effect ablation changed native hit timing')

    visual = hit['nativeRender']
    if not visual.get('zombieArtworkRendered') or not any(
            f.get('zombie', {}).get('drawCount', 0) > 0 for f in visual.get('frames', [])):
        raise RuntimeError('Controlled zombie did not render through original Main.DrawNPC')
    if [(t, e['damageDone']) for t, e in hits] != [(t, e['damageDone']) for t, e in events(hidden, 'hit')]:
        raise RuntimeError('Enabling zombie artwork changed native hit timing or damage')
    # Before the hit, compare the exact same target with native drawing on/off.
    # PNG pixels prove a visible change, rather than relying on a draw call alone.
    visible_frame = next(f for f in visual['frames'] if f['tick'] == 0)
    hidden_frame = next(f for f in hidden['nativeRender']['frames'] if f['tick'] == 0)
    with Image.open(hit_dir / visible_frame['path']) as a, Image.open(hidden_dir / hidden_frame['path']) as b:
        if not ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox():
            raise RuntimeError('Original zombie draw did not change any pixels')
    start = hits[0][0]
    after = [s for s in visual['snapshots'] if s['tick'] >= start]
    sprite, ring = hit_effect_records(after, art.name)
    if not sprite or not ring:
        raise RuntimeError('On-hit spriteElement and arc did not reach the original current renderers')
    miss_sprites, miss_rings = hit_effect_records(miss['nativeRender']['snapshots'], art.name)
    if miss_sprites or miss_rings:
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
    summary = {'passed': True, 'scope': 'Native NPC.HitEffect/NPCLoader dust and original current on-hit spriteElement/arc; synthetic control art',
               'hitTicks': [t for t, _ in hits], 'nativeHitEffectsWithNewDust': created,
               'spriteElementRecords': len(sprite), 'arcRecords': len(ring),
               'changedFramesVersusEffectAblation': changed, 'missHits': 0,
               'missingZombieRefused': True, 'wrongTargetRefused': True}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
