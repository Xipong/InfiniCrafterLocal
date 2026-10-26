#!/usr/bin/env python3
"""Synthetic original-renderer scene/publication controls; not authored-item approval."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops
import workbench as w


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native-dll', type=Path, help='Explicit separately built native executable; report records its hash, not a wrapper build receipt')
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    if args.native_dll and not args.no_build:
        raise SystemExit('--native-dll requires --no-build')
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True, exist_ok=True)
    if not args.native_dll and not args.no_build:
        w.build()
    dll = (args.native_dll or w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll').resolve()
    binary_hash = w.digest(dll)
    command = [os.environ.get('DOTNET', 'dotnet'), str(dll)]
    fixtures = out/'fixtures'
    subprocess.run(command + ['--write-fixtures', str(fixtures)], cwd=w.ROOT, check=True)
    item = w.read_json(fixtures/'synthetic-straight.json')
    files = []

    def publication(identity, color, prefix='infini_asset_png_'):
        # Explicit synthetic control, never substituted for an authored PNG.
        buffer = io.BytesIO()
        Image.new('RGBA', (16, 16), color).save(buffer, format='PNG')
        raw = buffer.getvalue()
        digest = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode('ascii') + b'\0' + raw).hexdigest()
        path = out/(prefix + digest + '.png')
        path.write_bytes(raw)
        files.append(str(path))
        return path.name

    root = publication([item['id'], 'item', '', item['id']], (240, 240, 240, 255))
    item['visual'].update(spritePath=root, spriteStatus='generated', renderSizePx=24, forwardAngleDegrees=0)
    for entity in item['runtimeProgram']['entities']:
        entity['visual'].update(assetMode='reuse_item_icon' if entity['kind']!='item_body' else 'baked_sprite', spritePath=root, spriteStatus='generated')
    texture = publication(['synthetic-material-scene', 'test_strip'], (230, 120, 30, 255), 'infini_vfx_png_')
    ramp = {'start':1, 'middle':1, 'end':1, 'curve':'linear'}
    color = {'r':255, 'g':255, 'b':255}
    color_ramp = {'start':color, 'middle':color, 'end':color, 'curve':'linear'}
    item['vfxManifest'].update(recipeId='synthetic-material-scene', assets=[{'id':'test_strip','layout':'strip','canvasSize':16,'prompt':'Synthetic uniform test strip','negativePrompt':'','spritePath':texture,'spriteStatus':'generated','spriteTechnicalScore':1}], slots=[{
        'id':'synthetic_history', 'entityId':'root', 'event':'periodic', 'rendererKind':'texturedPath', 'anchor':'self', 'layer':'BeforeProjectiles', 'alpha':1, 'blend':'alpha', 'slotSeed':1, 'startTick':0,
        'path':{'source':'anchorHistory','texture':{'source':'asset','assetId':'test_strip'},'historyTicks':6,'minDistancePx':1,'maxSegmentLengthPx':48,'widthPx':4,'profileDomain':'age','uvMode':'repeat','repeatLengthPx':16,'scrollPxPerTick':0,'widthProfile':ramp,'opacityProfile':ramp,'colorProfile':color_ramp}}])
    item_path = out/'synthetic-material.json'
    item_path.write_text(json.dumps(item))
    base = {'playerUpdate':'client_vfx','ticks':120,'seed':1,'player':{'x':800,'y':1500,'mana':200},'dummy':{'x':1100,'y':1500,'life':10000},'tiles':[{'tileX':1,'tileY':97,'width':97,'height':1}], 'actions':[{'tick':0,'kind':'aim','x':1100,'y':1520},{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}], 'assertions':[{'kind':'spawned'},{'kind':'all_inactive'},{'kind':'no_nonfinite'}], 'nativeRender':{'width':512,'height':512,'cameraX':700,'cameraY':1250,'zoom':1,'drawArtwork':True,'lightingMode':'viewport_fill','artworkFiles':files}}
    cases = [('material-path', base, 0, '')]
    missing = copy.deepcopy(base); missing['nativeRender']['artworkFiles'] = files[:-1]
    cases.append(('missing-material-png', missing, 2, 'Missing explicit artwork file'))
    tampered_dir = out/'tampered'; tampered_dir.mkdir()
    material_source = Path(files[-1]); tampered_path = tampered_dir/material_source.name
    changed = bytearray(material_source.read_bytes()); changed[-1] ^= 1; tampered_path.write_bytes(changed)
    tampered = copy.deepcopy(base); tampered['nativeRender']['artworkFiles'][-1] = str(tampered_path)
    cases.append(('tampered-material-png', tampered, 2, 'publication identity/content mismatch'))
    wrong = copy.deepcopy(base); wrong['nativeRender']['lightingMode'] = 'invented'
    cases.append(('invalid-lighting', wrong, 2, 'lightingMode'))
    # Explicit synthetic ablation only: same native gameplay/art, no VFX slots.
    # This never mutates an authored item or substitutes a review frame.
    control_item = copy.deepcopy(item)
    control_item['vfxManifest']['slots'] = []
    control_item['vfxManifest']['assets'] = []
    control_path = out/'synthetic-material-off.json'
    control_path.write_text(json.dumps(control_item))
    control_scene = copy.deepcopy(base)
    control_scene['nativeRender']['artworkFiles'] = files[:-1]
    cases.append(('material-off-control', control_scene, 0, ''))
    traces = {}; rows = []
    for name, scenario, expected, reason in cases:
        directory = out/name; directory.mkdir()
        scenario_path = directory/'scenario.json'; scenario_path.write_text(json.dumps(scenario))
        selected_item = control_path if name == 'material-off-control' else item_path
        result = subprocess.run(command + ['--item',str(selected_item),'--scenario',str(scenario_path),'--output',str(directory/'native.json')],cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        (directory/'process.log').write_text(result.stdout+result.stderr)
        trace = w.read_json(directory/'native.json'); traces[name] = trace
        rows.append({'name':name,'passed':w.digest(dll)==binary_hash and result.returncode==expected and trace['status']==('passed' if expected==0 else 'error') and reason in trace.get('error',''),'exitCode':result.returncode})
    trace = traces['material-path']; render = trace.get('nativeRender',{}); snapshots = render.get('snapshots',[])
    control = traces['material-off-control']
    same_gameplay = trace.get('snapshots') == control.get('snapshots')
    on_frames = render.get('frames', [])
    off_frames = control.get('nativeRender', {}).get('frames', [])
    png_integrity = len(on_frames) == len(off_frames) == 120
    changed_pixels = []
    for on, off in zip(on_frames, off_frames):
        a = out/'material-path'/on['path']
        b = out/'material-off-control'/off['path']
        png_integrity &= on['tick'] == off['tick'] and a.is_file() and b.is_file()
        if not a.is_file() or not b.is_file():
            continue
        png_integrity &= w.digest(a) == on['sha256'] and w.digest(b) == off['sha256']
        with Image.open(a) as ia, Image.open(b) as ib:
            delta = ImageChops.difference(ia.convert('RGB'), ib.convert('RGB'))
            changed_pixels.append(sum(any(pixel) for pixel in delta.get_flattened_data()))
    checks = {
        'native-path-history-exercised':any(len(p['history'])>=2 for s in snapshots for p in s.get('paths',[])),
        'native-path-retired':bool(snapshots) and snapshots[-1].get('pathRecordCount')==0,
        'lighting-follows-distant-camera':render.get('lighting',{}).get('tileBounds',{}).get('top',0)>56,
        'original-frame-evidence':len(render.get('frames',[]))==120 and any(f.get('projectileDrawCount',0)>0 for f in render.get('frames',[])),
        'matched-native-gameplay':same_gameplay,
        'native-png-integrity':png_integrity,
        'material-visible-native-pixels':same_gameplay and png_integrity and any(changed_pixels),
        'vfx-update-camera':render.get('vfxUpdateUsesSceneCamera') is True,
    }
    rows.extend({'name':name,'passed':passed} for name,passed in checks.items())
    summary = {'passed':all(row['passed'] for row in rows),'scope':'Synthetic native material path, scene lighting and exact asset admission; not original item visual approval','nativeDllSha256':binary_hash,'syntheticItemSha256':w.digest(item_path),'syntheticControlSha256':w.digest(control_path),'materialPixelControl':{'changedRgbPixelsByTick':changed_pixels,'scope':'Actual native PNGs, matched gameplay snapshots; only synthetic texturedPath slots/assets removed in control. No authored visual quality claim.'},'checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
