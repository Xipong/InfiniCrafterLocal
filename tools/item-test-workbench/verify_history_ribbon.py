#!/usr/bin/env python3
"""Native historyRibbon draw, no-capture parity and refusal controls; no fake gameplay."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image

import workbench as w
from native_review import native_frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-build', action='store_true')
    parser.add_argument('--item', type=Path, help='Optional unchanged authored item for the same native VFX-only scene')
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a fresh evidence directory')
    w.native_executable(args.no_build)
    w.fixtures(out / 'fixtures', no_build=True)
    item = w.read_json(out / 'fixtures/synthetic-straight.json')
    item['vfxManifest']['slots'] = [dict(id='native_history', entityId='root', event='periodic',
        rendererKind='historyRibbon', anchor='self', layer='BeforeProjectiles', color=dict(r=80,g=180,b=255),
        alpha=1, blend='alpha', scale=2, density=0.5, spread=0, slotSeed=1, startTick=0,
        repeatEvery=1, duration=12, particleSystemId='none')]
    item_path = out / 'synthetic-history.json'
    item_path.write_text(json.dumps(item))
    stationary = copy.deepcopy(item)
    # Locate the authored primary projectile rather than relying on its array position.
    for entity in stationary['runtimeProgram']['entities']:
        if entity['id'] == stationary['runtimeProgram']['primaryEntityId']:
            entity['spawn']['speedPxPerTick'] = 0
    stationary_path = out / 'synthetic-stationary.json'
    stationary_path.write_text(json.dumps(stationary))
    scene = dict(playerUpdate='client_vfx',ticks=100,seed=1,
        player=dict(x=800,y=700,mana=200),dummy=dict(x=840,y=900,life=10000),
        tiles=[dict(tileX=1,tileY=47,width=97,height=1)],
        actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,
                          drawProjectileVfx=True,drawNativeDust=True,lightingMode='viewport_fill'))
    cases=[('moving',item_path,scene,0,'',{}),('repeat',item_path,copy.deepcopy(scene),0,'',{}),
           ('stationary',stationary_path,copy.deepcopy(scene),0,'',{})]
    # Explicit synthetic publication for the complete native PreDraw route.
    # This fixture is separate from the optional unchanged authored item.
    buffer=io.BytesIO();Image.new('RGBA',(16,16),(220,220,220,255)).save(buffer,format='PNG')
    raw=buffer.getvalue();identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode('ascii')
    png=out/('infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png');png.write_bytes(raw)
    artwork_item=copy.deepcopy(item)
    artwork_item['visual'].update(spritePath=png.name,spriteStatus='generated',renderSizePx=24,forwardAngleDegrees=0)
    for entity in artwork_item['runtimeProgram']['entities']:
        entity['visual'].update(assetMode='baked_sprite' if entity['kind']=='item_body' else 'reuse_item_icon',
                                spritePath=png.name,spriteStatus='generated')
    artwork_path=out/'synthetic-artwork.json';artwork_path.write_text(json.dumps(artwork_item))
    artwork_scene=copy.deepcopy(scene)
    artwork_scene['nativeRender'].update(drawArtwork=True,drawPlayer=True,drawProjectileVfx=False,artworkFiles=[str(png)])
    cases.append(('full-native-predraw',artwork_path,artwork_scene,0,'',{}))
    full_uncaptured=copy.deepcopy(artwork_scene);full_uncaptured['nativeRender']['capture']=False
    cases.append(('full-native-predraw-no-capture',artwork_path,full_uncaptured,0,'',{}))
    uncaptured=copy.deepcopy(scene);uncaptured['nativeRender']['capture']=False
    cases.append(('capture-disabled',item_path,uncaptured,0,'',{}))
    missing=copy.deepcopy(scene);missing['nativeRender']['drawProjectileVfx']=False;missing['nativeRender']['drawNativeDust']=False
    cases.append(('missing-draw-context',item_path,missing,2,'historyRibbon requires',{}))
    cases.append(('missing-native-assets',item_path,copy.deepcopy(scene),2,'',{'INFINI_PLAYER_ASSET_DIR':str(out/'missing-assets')}))
    if args.item:
        authored=copy.deepcopy(scene);authored['dummy']['y']=700
        authored['assertions']=[dict(kind='dummy_damaged'),dict(kind='no_nonfinite')]
        cases.append(('authored',args.item.resolve(),authored,0,'',{}))
    traces={};rows=[]
    for name,source,chosen,expected,reason,env in cases:
        path=out/(name+'-scenario.json');path.write_text(json.dumps(chosen))
        command=[sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(source),'--scenario',str(path),
                 '--out',str(out/name),'--no-build','--review','none']
        result=subprocess.run(command,cwd=w.ROOT,env={**os.environ,**env},capture_output=True,text=True,timeout=240)
        trace=w.read_json(out/name/'native.json');traces[name]=trace
        rows.append(dict(name=name,passed=result.returncode==expected and trace['status']=={0:'passed',2:'error'}[expected]
                         and reason in trace.get('error',''),exitCode=result.returncode,error=trace.get('error')))
        (out/(name+'.process.log')).write_text(result.stdout+result.stderr)
    def check(name,value):rows.append(dict(name=name,passed=bool(value)))
    def ribbon(trace):
        return [d for s in trace.get('nativeRender',{}).get('snapshots',[])
                for d in s.get('activeProjectileVfx',{}).get('historyRibbonDraws',[])]
    moving=traces['moving'];records=ribbon(moving)
    check('original-native-segments-submitted',bool(records) and sum(r['submittedSegments'] for r in records)>0
          and all(r['nativeMagicPixel'] and r['historyCount']<=20 for r in records))
    check('stationary-history-does-not-fabricate-lines',bool(ribbon(traces['stationary']))
          and sum(r['submittedSegments'] for r in ribbon(traces['stationary']))==0)
    check('capture-does-not-change-native-gameplay',moving['snapshots']==traces['capture-disabled']['snapshots'])
    check('capture-does-not-change-live-history-or-segments',ribbon(moving)==ribbon(traces['capture-disabled']))
    check('no-capture-still-executes-gpu',traces['capture-disabled']['nativeRender']['gpuRenderLifecycleExecuted']
          and not traces['capture-disabled']['nativeRender']['frames'])
    check('repeat-native-gameplay-and-history',moving['snapshots']==traces['repeat']['snapshots']
          and records==ribbon(traces['repeat']))
    check('repeat-pixels',[f['sha256'] for f in moving['nativeRender']['frames']]
          ==[f['sha256'] for f in traces['repeat']['nativeRender']['frames']])
    full=traces['full-native-predraw']
    check('full-native-predraw-ribbon',full.get('nativeRender',{}).get('fullProjectilePreDrawExecuted') is True
          and sum(r['submittedSegments'] for r in ribbon(full))>0)
    full_nocap=traces['full-native-predraw-no-capture']
    check('full-predraw-capture-independent',full['snapshots']==full_nocap['snapshots'] and ribbon(full)==ribbon(full_nocap)
          and full_nocap['nativeRender']['gpuRenderLifecycleEnabled'] and full_nocap['nativeRender']['gpuRenderLifecycleExecuted']
          and not full_nocap['nativeRender']['frames'])
    for name,trace in traces.items():
        if trace['status']=='error':continue
        frames=native_frames(trace,out/name/'native.json') if trace['nativeRender']['frames'] else []
        check(name+'-finite-recorded-pixels',not trace['nativeRender']['capture'] or bool(frames))
    if args.item:
        check('authored-bytes-preserved',w.digest(args.item)==w.digest(out/'authored/item.json'))
        check('authored-original-ribbon-executed',sum(r['submittedSegments'] for r in ribbon(traces['authored']))>0)
    summary=dict(passed=all(r['passed'] for r in rows),fullGameParity=False,
                 scope='Original native procedural VFX and live history; authored/player/world artwork not rendered',checks=rows)
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1


if __name__=='__main__':
    sys.exit(main())
