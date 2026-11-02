#!/usr/bin/env python3
"""Bounded native world/source arc and sector controls; never substitutes an authored item's effects."""
import argparse
import copy
import json
import math
import os
from pathlib import Path
import subprocess

from PIL import Image, ImageChops
import workbench as w


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--kind', choices=('arc','sector'), default='arc')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    dll = args.native_dll.resolve()
    binary = w.digest(dll)
    command = [os.environ.get('DOTNET', 'dotnet'), str(dll)]
    subprocess.run(command + ['--write-fixtures', str(out/'fixtures')], cwd=w.ROOT, check=True)
    item = w.read_json(out/'fixtures/synthetic-straight.json')
    next(e for e in item['runtimeProgram']['entities'] if e['id']=='root')['spawn']['aim']='cursor'
    arc = dict(id='native_arc', entityId='root', event='on_spawn', rendererKind='shape',
               anchor='self', blend='additive', layer='BeforeProjectiles', duration=12,
               startTick=3, repeatEvery=0, slotSeed=1,
               shape=dict(kind='arc', attachment='world', rotationFrame='world',
                          offsetForwardPx=0, offsetSidePx=0, rotationRadians=0,
                          rotationSpeedRadiansPerTick=0, colorStart=dict(r=80,g=220,b=255),
                          colorEnd=dict(r=80,g=220,b=255), opacityStart=1, opacityEnd=1,
                          radiusStartPx=16, radiusEndPx=24, widthPx=3, sweepRadians=2.1,
                          segments=20, tailOpacityStart=1, tailOpacityEnd=1))
    if args.kind == 'sector':
        shape = arc['shape']
        for key in ('radiusStartPx','radiusEndPx','widthPx','tailOpacityStart','tailOpacityEnd'):
            del shape[key]
        shape.update(kind='sector',innerRadiusStartPx=0,innerRadiusEndPx=0,
                     outerRadiusStartPx=16,outerRadiusEndPx=24)
    item['vfxManifest']['slots'] = [arc]
    scene = dict(playerUpdate='client_vfx', ticks=48, seed=1,
                 player=dict(x=800,y=700,mana=200), dummy=dict(x=1100,y=900,life=10000),
                 tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
                 actions=[dict(kind='aim',tick=0,x=1000,y=600),dict(kind='primary',tick=0),dict(kind='release',tick=1)],
                 assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
                 nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,
                                   drawProjectileVfx=True,lightingMode='viewport_fill'))
    off = copy.deepcopy(item); off['vfxManifest']['slots'] = []
    attached = copy.deepcopy(item); attached['vfxManifest']['slots'][0]['shape']['attachment'] = 'source'
    source_frame = copy.deepcopy(item); source_frame['vfxManifest']['slots'][0]['shape']['rotationFrame'] = 'source'
    both = copy.deepcopy(attached); both['vfxManifest']['slots'][0]['shape']['rotationFrame'] = 'source'
    line = copy.deepcopy(item); geometry = line['vfxManifest']['slots'][0]['shape']
    for key in ('radiusStartPx','radiusEndPx','innerRadiusStartPx','innerRadiusEndPx','outerRadiusStartPx','outerRadiusEndPx','sweepRadians','segments','tailOpacityStart','tailOpacityEnd'): geometry.pop(key,None)
    geometry.update(kind='line',lengthPx=32,widthPx=3)
    nocapture = copy.deepcopy(scene); nocapture['nativeRender']['capture'] = False
    partial = copy.deepcopy(scene); partial['nativeRender']['drawProjectileVfx'] = False
    cases = [('arc',item,scene,0),('off',off,scene,0),('repeat',item,scene,0),
             ('no-capture',item,nocapture,0),('source-attachment',attached,scene,0),
             ('source-rotation',source_frame,scene,0),('source-both',both,scene,0),('line-unproven',line,scene,2),
             ('partial-draw',item,partial,2)]
    if args.kind == 'sector':
        for name, changes in [('full-circle',dict(sweepRadians=math.tau,outerRadiusStartPx=64,outerRadiusEndPx=64)),
                              ('rotated',dict(rotationRadians=math.pi)),
                              ('larger',dict(outerRadiusStartPx=32,outerRadiusEndPx=48)),
                              ('negative-sweep',dict(sweepRadians=-2.1))]:
            variant=copy.deepcopy(item);variant['vfxManifest']['slots'][0]['shape'].update(changes)
            cases.append((name,variant,scene,0))
    traces = {}; checks = []
    for name, value, scenario, expected in cases:
        directory = out/name; directory.mkdir()
        (directory/'item.json').write_text(json.dumps(value))
        (directory/'scenario.json').write_text(json.dumps(scenario))
        process = subprocess.run(command + ['--item',str(directory/'item.json'),'--scenario',str(directory/'scenario.json'),
                                          '--output',str(directory/'native.json')], cwd=w.ROOT, capture_output=True,text=True,timeout=180)
        (directory/'process.log').write_text(process.stdout+process.stderr)
        trace = w.read_json(directory/'native.json'); traces[name] = trace
        passed = process.returncode == expected and trace['status'] == ('passed' if expected==0 else 'error')
        if expected: passed = passed and 'shape currently requires' in trace.get('error','')
        checks.append(dict(name=name,passed=passed,exitCode=process.returncode))
    actual = traces['arc']; control = traces['off']; repeat = traces['repeat']; silent = traces['no-capture']
    snapshots = actual.get('nativeRender',{}).get('snapshots',[])
    onframes = actual.get('nativeRender',{}).get('frames',[])
    offframes = control.get('nativeRender',{}).get('frames',[])
    pixels = []; integrity = len(onframes)==len(offframes)==48
    for on, off_frame in zip(onframes,offframes):
        a = out/'arc'/on['path']; b = out/'off'/off_frame['path']
        integrity = integrity and w.digest(a)==on['sha256'] and w.digest(b)==off_frame['sha256'] and on['tick']==off_frame['tick']
        with Image.open(a) as ia, Image.open(b) as ib:
            pixels.append(sum(any(p) for p in ImageChops.difference(ia.convert('RGB'),ib.convert('RGB')).get_flattened_data()))
    present = [s for s in snapshots if s.get('shapeRecordCount',0)>0]
    frame_hashes = lambda trace: [f['sha256'] for f in trace.get('nativeRender',{}).get('frames',[])]
    observed = {
        'real-shape-record':bool(present) and all(v['kind']==args.kind and v['attachment']=='world' and v['rotationFrame']=='world' for s in present for v in s['shapes']),
        'shape-expired':bool(snapshots) and snapshots[-1].get('shapeRecordCount')==0,
        'pixels-visible-only-during-life':bool(pixels) and any(pixels[3:15]) and not any(pixels[:3]) and not any(pixels[15:]),
        'native-png-hash-integrity':integrity,
        'same-native-gameplay':actual.get('snapshots')==control.get('snapshots'),
        'fresh-process-deterministic-reset':frame_hashes(actual)==frame_hashes(repeat) and snapshots==repeat.get('nativeRender',{}).get('snapshots'),
        'no-capture-keeps-lifecycle':snapshots==silent.get('nativeRender',{}).get('snapshots') and not silent.get('nativeRender',{}).get('frames'),
        'binary-unchanged':w.digest(dll)==binary,
    }
    for name, attachment, rotation in [('source-attachment','source','world'),('source-rotation','world','source'),('source-both','source','source')]:
        trace=traces[name]
        states=trace.get('nativeRender',{}).get('snapshots',[])
        records=[v for state in states for v in state.get('shapes',[])]
        frames=trace.get('nativeRender',{}).get('frames',[])
        observed[name+'-actual-records']=bool(records) and all(v['attachment']==attachment and v['rotationFrame']==rotation for v in records)
        observed[name+'-expired']=bool(states) and states[-1].get('shapeRecordCount')==0
        observed[name+'-same-gameplay']=trace.get('snapshots')==control.get('snapshots')
        diffs=[]
        for frame,blank in zip(frames,offframes):
            with Image.open(out/name/frame['path']) as a,Image.open(out/'off'/blank['path']) as b:
                diffs.append(ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is not None)
        observed[name+'-visible-only-during-life']=len(diffs)==48 and any(diffs[3:15]) and not any(diffs[:3]) and not any(diffs[15:])
        observed[name+'-different-from-world-pose']=frame_hashes(trace)!=frame_hashes(actual)
        if attachment=='source':
            observed[name+'-follows-moving-source']=len({(v['x'],v['y']) for v in records})>3
    if args.kind == 'sector':
        def changed_points(name, index=3):
            frame=traces[name]['nativeRender']['frames'][index]
            blank=offframes[index]
            with Image.open(out/name/frame['path']) as a, Image.open(out/'off'/blank['path']) as b:
                diff=ImageChops.difference(a.convert('RGB'),b.convert('RGB'))
                return {(x,y) for y in range(diff.height) for x in range(diff.width) if any(diff.getpixel((x,y)))}
        base_points=changed_points('arc'); larger=changed_points('larger')
        circle=changed_points('full-circle')
        record=next(s for s in traces['full-circle']['nativeRender']['snapshots'] if s.get('shapes'))['shapes'][0]
        cx,cy=record['x']-650,record['y']-550
        distances=[math.hypot(x+.5-cx,y+.5-cy) for x,y in circle]
        observed.update({
            'sector-radius-expands-visible-area':len(larger)>len(base_points)*3,
            'sector-rotation-changes-pixels':bool(base_points) and changed_points('rotated')!=base_points,
            'sector-negative-sweep-visible':bool(changed_points('negative-sweep')) and changed_points('negative-sweep')!=base_points,
            'sector-full-circle-radius64':bool(distances) and 61<max(distances)<66,
            'sector-full-circle-all-quadrants':all(any((x>cx)==right and (y>cy)==bottom for x,y in circle) for right in (False,True) for bottom in (False,True)),
            'sector-full-circle-filled':len(circle)>11000,
        })
    checks.extend(dict(name=name,passed=value) for name,value in observed.items())
    summary = dict(passed=all(c['passed'] for c in checks),nativeDllSha256=binary,checks=checks,
                   changedRgbPixelsByTick=pixels,scope=f'Fresh synthetic world/source {args.kind} native renderer proof; reset is fresh-process, not same-process unload. No authored-item quality claim.')
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
