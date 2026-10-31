#!/usr/bin/env python3
"""Actual original mod VFX pixels, native combat, no-draw parity and refusal controls."""
import argparse,copy,json,os,subprocess,sys
from pathlib import Path
import workbench as w
from native_review import native_frames


def gameplay_snapshots_equal(first, second):
    """Compare every recorded field except camera-culled native dust counts."""
    if not isinstance(first, list) or not isinstance(second, list) or not first or len(first) != len(second):
        return False
    for left, right in zip(first, second):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        if 'nativeActiveDust' not in left or 'nativeActiveDust' not in right:
            return False
        # Only the snapshot's top-level dust telemetry is camera-dependent.
        # Never mutate raw traces or ignore similarly named gameplay fields.
        if {k: v for k, v in left.items() if k != 'nativeActiveDust'} != {k: v for k, v in right.items() if k != 'nativeActiveDust'}:
            return False
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');args=p.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh evidence directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    original=w.ROOT/'tools/fixtures/video-ui-buffs/g_17d5099f992a900b.json';base=w.read_json(w.HERE/'scenarios/client-vfx-captured.json')
    cases=[('captured-hit',original,base,0,{}),('captured-hit-repeat',original,base,0,{})]
    s=copy.deepcopy(base);s['nativeRender']['capture']=False;cases.append(('no-draw-same-update',original,s,0,{}))
    s=copy.deepcopy(base);s['nativeRender']['zoom']=1;cases.append(('native-camera-1x',original,s,0,{}))
    s=copy.deepcopy(base);s['actions']=[];s['assertions']=[{'kind':'spawn_count','value':0},{'kind':'dummy_undamaged'},{'kind':'mana_debited','value':0},{'kind':'direct_healing','value':0},{'kind':'no_nonfinite'}];cases.append(('no-use-blank-control',original,s,0,{}))
    s=copy.deepcopy(base);s['dummy']['x']=1300;s['assertions']=[{'kind':'spawn_count','value':1},{'kind':'dummy_undamaged'},{'kind':'mana_debited','value':10},{'kind':'direct_healing','value':0},{'kind':'returned'},{'kind':'all_inactive'},{'kind':'no_nonfinite'}];cases.append(('miss-no-hit-vfx',original,s,0,{}))
    s=copy.deepcopy(base)
    for a in s['assertions']:
        if a['kind']=='mana_debited':a['value']=5
    cases.append(('captured-periodic-and-hit',w.ROOT/'tools/fixtures/video-ui-buffs/g_4efc7c05f7b078e0.json',s,0,{}))
    s=copy.deepcopy(base);s['assertions']=[{'kind':'direct_healing','value':2}];cases.append(('negative-double-healing',original,s,1,{}))
    cases.append(('missing-original-assets',original,base,2,{'INFINI_PARTICLE_ASSET_DIR':str(out/'absent-original-assets')}))
    cases.append(('missing-native-magicpixel',original,base,2,{'INFINI_PLAYER_ASSET_DIR':str(out/'absent-pixel-assets')}))
    s=copy.deepcopy(base);s['ticks']=601;cases.append(('bounded-render-ticks',original,s,2,{}))
    cases.append(('unsupported-authored-sprite-renderer',w.ROOT/'tools/fixtures/played-silver-delivered.json',base,2,{}))
    s=copy.deepcopy(base);s['nativeRender']['zoom']=0;cases.append(('invalid-native-camera',original,s,2,{}))
    s=copy.deepcopy(base);s['nativeRender']['cameraX']=1400;s['nativeRender']['cameraY']=0;cases.append(('off-camera-telemetry',original,s,0,{}))
    s=copy.deepcopy(base);s['nativeRender']['lightingMode']='unknown';cases.append(('invalid-lighting-mode',original,s,2,{}))
    rows=[];traces={}
    def check(name,value):rows.append({'name':name,'passed':bool(value)})
    for name,ip,s,expected,env in cases:
        sp=out/(name+'-scenario.json');sp.write_text(json.dumps(s,indent=2))
        r=subprocess.run([sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build'],cwd=w.ROOT,env={**os.environ,**env},capture_output=True,text=True,timeout=240)
        tp=out/name/'native.json';t=w.read_json(tp) if tp.exists() else {};traces[name]=t
        rows.append({'name':name,'passed':r.returncode==expected and t.get('status')=={0:'passed',1:'failed',2:'error'}[expected],'expectedExitCode':expected,'actualExitCode':r.returncode,'nativeStatus':t.get('status'),'trace':str(tp),'runnerStdout':r.stdout,'runnerStderr':r.stderr});print(name+': '+('PASS' if rows[-1]['passed'] else 'FAIL'),flush=True)
        if t.get('nativeRender',{}).get('frames'):
            try:native_frames(t,tp);valid=True
            except (ValueError,OSError):valid=False
            check(name+'-every-native-png-hash-dimensions-integrity',valid)
        if expected!=2:
            receipt=w.read_json(out/name/'run.json');check(name+'-unchanged-input-sha',w.digest(ip)==w.digest(out/name/'item.json')==receipt['itemSha256'])
    main=traces['captured-hit'];repeat=traces['captured-hit-repeat'];nodraw=traces['no-draw-same-update'];render=main.get('nativeRender',{})
    check('same-seed-exact-gameplay-and-vfx-repeat',bool(main.get('snapshots')) and main.get('snapshots')==repeat.get('snapshots') and render.get('snapshots')==repeat.get('nativeRender',{}).get('snapshots'))
    check('same-seed-exact-native-pixel-repeat',[f.get('sha256') for f in render.get('frames',[])]==[f.get('sha256') for f in repeat.get('nativeRender',{}).get('frames',[])] and bool(render.get('frames')))
    check('native-draw-does-not-change-gameplay-or-particles',bool(main.get('snapshots')) and main.get('snapshots')==nodraw.get('snapshots') and render.get('snapshots')==nodraw.get('nativeRender',{}).get('snapshots'))
    check('capturefalse-has-no-fabricated-frames',nodraw.get('nativeRender',{}).get('capture') is False and nodraw.get('nativeRender',{}).get('frames')==[])
    check('camera-does-not-change-gameplay-or-particles',main.get('snapshots')==traces['native-camera-1x'].get('snapshots') and render.get('snapshots')==traces['native-camera-1x'].get('nativeRender',{}).get('snapshots'))
    camera_frames=traces['off-camera-telemetry'].get('nativeRender',{}).get('frames',[])
    check('off-camera-keeps-native-gameplay',gameplay_snapshots_equal(main.get('snapshots'),traces['off-camera-telemetry'].get('snapshots')))
    check('off-camera-records-bounds-not-visible-sprite-claims',bool(camera_frames) and all(f.get('scene',{}).get('cameraX')==1400 and f.get('scene',{}).get('player',{}).get('hitboxIntersectsViewport') is False for f in camera_frames) and any(f.get('scene',{}).get('projectiles') for f in camera_frames))
    check('captured-camera-has-native-scene-telemetry',bool(render.get('frames')) and all(f.get('scene',{}).get('player',{}).get('centerLightRgb') is not None and 'not sprite bounds' in f.get('scene',{}).get('scope','') for f in render['frames']))
    hits=[s['tick'] for s in main.get('snapshots',[]) for e in s.get('events',[]) if e['kind']=='hit']
    visible=[f['tick'] for f in render.get('frames',[]) if f.get('nonblackPixels',0)>0]
    check('real-native-hit-drives-visible-particles-and-expiry',hits==[12] and visible==list(range(12,26)))
    states=render.get('snapshots',[])
    check('actual-particles-start-immediately-and-retire-native-duration',bool(states) and all(s['particleCount']==5 and all(r['started'] and r['durationTicks']==14 for r in s['records']) for s in states if 12<=s['tick']<=25) and all(s['materialRecordCount']==0 for s in states if s['tick']>=26))
    for name,t in traces.items():
        r=t.get('nativeRender',{});f=r.get('frames',[])
        if not f:continue
        check(name+'-all-draws-preserve-main-rng',all(a.get('drawChangedMainRng') is False and a['mainRngBeforeDraw']==a['mainRngAfterDraw'] for a in f))
        check(name+'-exact-resources-and-explicit-incomplete-art',r.get('resourceReady') is True and r.get('libraryBuffers')==4 and r.get('originalParticleLibraryEffect') is True and r.get('loadedAssetSha256') and r.get('soundValidated') is False and all(r.get(k) is False for k in ('itemArtworkRendered','projectileArtworkRendered','worldRendered')) and r.get('unrenderedArtwork'))
        pixel=r.get('magicPixelResource',{})
        check(name+'-genuine-magicpixel-without-player-art',pixel.get('sha256')=='43e32609f2d123fc51cafbafab11955153ea545760952a578c3f909bbe88651c' and pixel.get('playerArtworkLoaded') is False)
    for name in ('no-use-blank-control','miss-no-hit-vfx'):
        r=traces[name].get('nativeRender',{});check(name+'-no-silent-stale-particles',bool(r.get('frames')) and all(f['nonblackPixels']==0 for f in r['frames']) and all(s['particleCount']==0 and s['materialRecordCount']==0 for s in r.get('snapshots',[])))
    periodic=traces['captured-periodic-and-hit'].get('nativeRender',{});check('second-captured-item-real-periodic-particle-lifecycle',bool(periodic.get('frames')) and sum(f['nonblackPixels']>0 for f in periodic['frames'])>14 and any(s['materialRecordCount']>1 for s in periodic.get('snapshots',[])))
    for name in ('missing-original-assets','missing-native-magicpixel','bounded-render-ticks','unsupported-authored-sprite-renderer','invalid-native-camera','invalid-lighting-mode'):
        check(name+'-refuses-without-native-frame-fallback',traces[name].get('status')=='error' and not traces[name].get('nativeRender',{}).get('frames') and not traces[name].get('snapshots'))
    summary={'passed':all(r['passed'] for r in rows),'fullGameParity':False,'scope':'Actual original mod libraryParticle update/draw with genuine resources and captured combat; neutral background, item/projectile/world art and sound unrendered','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
