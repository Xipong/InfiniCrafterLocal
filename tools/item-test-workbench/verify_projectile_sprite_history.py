#!/usr/bin/env python3
"""Actual entity-texture sprite history: native draws, pixels, expiry and refusals."""
import argparse,copy,hashlib,io,json,os,subprocess,sys
from pathlib import Path
from PIL import Image
import workbench as w


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-build',action='store_true');a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    w.native_executable(a.no_build);w.fixtures(out/'fixtures',no_build=True)
    item=w.read_json(out/'fixtures/synthetic-straight.json')
    item['vfxManifest']['slots']=[]
    buf=io.BytesIO();Image.new('RGBA',(16,16),(240,200,50,255)).save(buf,format='PNG');raw=buf.getvalue()
    identity=json.dumps([item['id'],'item','',item['id']],separators=(',',':')).encode('ascii')
    png=out/('infini_asset_png_'+hashlib.sha256(identity+b'\0'+raw).hexdigest()+'.png');png.write_bytes(raw)
    item['visual'].update(spritePath=png.name,spriteStatus='generated',renderSizePx=24,forwardAngleDegrees=0)
    for e in item['runtimeProgram']['entities']:
        e['visual'].update(assetMode='baked_sprite' if e['kind']=='item_body' else 'reuse_item_icon',spritePath=png.name,spriteStatus='generated')
        if e['kind']!='item_body':
            e['lifetimeTicks']=24
            e['rotation']=dict(mode='spin',radiansPerUpdate=.2,offsetRadians=0)
    trail=dict(id='entity_afterimages',entityId='root',event='periodic',rendererKind='historyTrail',anchor='self',layer='BeforeProjectiles',blend='alpha',slotSeed=1,
        trail=dict(draw='sprites',source='center',historyTicks=10,sampleStepTicks=2,firstSampleAgeTicks=2,
            opacityProfile=dict(start=.9,middle=.5,end=0,curve='linear'),color=dict(r=255,g=255,b=255),
            texture=dict(source='entity',assetId='',uv=dict(quarterTurns=0,mirrorU=False,mirrorV=False)),scale=1,pose='sampled'))
    scene=dict(playerUpdate='client_vfx',ticks=50,seed=1,player=dict(x=800,y=700,mana=200),dummy=dict(x=840,y=1100,life=10000),
        tiles=[dict(tileX=1,tileY=47,width=97,height=1)],actions=[dict(kind='primary',tick=0),dict(kind='release',tick=1)],
        assertions=[dict(kind='spawned'),dict(kind='no_nonfinite')],
        nativeRender=dict(width=512,height=384,cameraX=650,cameraY=550,capture=True,drawArtwork=True,drawPlayer=True,drawNativeDust=True,drawProjectileVfx=False,artworkFiles=[str(png)],lightingMode='viewport_fill'))
    enabled=copy.deepcopy(item);enabled['vfxManifest']['slots']=[trail]
    no_draw=copy.deepcopy(scene);no_draw['nativeRender'].update(drawPlayer=False,drawNativeDust=False)
    no_capture=copy.deepcopy(scene);no_capture['nativeRender']['capture']=False
    missing=copy.deepcopy(scene);missing['nativeRender']['artworkFiles']=[]
    unsupported=copy.deepcopy(enabled);unsupported['vfxManifest']['slots'][0]['trail']['pose']='current'
    rows=[];traces={}
    for name,d,s,code,reason in [('baseline',item,scene,0,''),('sampled',enabled,scene,0,''),('repeat',enabled,scene,0,''),('no-capture',enabled,no_capture,0,''),('no-native-draw',enabled,no_draw,2,'historyTrail requires'),('missing-publication',enabled,missing,2,''),('unproven-current-pose',unsupported,scene,2,'historyTrail requires')]:
        ip=out/(name+'-item.json');sp=out/(name+'-scene.json');ip.write_text(json.dumps(d));sp.write_text(json.dumps(s))
        cmd=[sys.executable,str(w.HERE/'workbench.py'),'run','--item',str(ip),'--scenario',str(sp),'--out',str(out/name),'--no-build','--review','none']
        r=subprocess.run(cmd,cwd=w.ROOT,capture_output=True,text=True,timeout=180);(out/(name+'.log')).write_text(r.stdout+r.stderr)
        t=w.read_json(out/name/'native.json');traces[name]=t
        rows.append(dict(name=name,passed=r.returncode==code and t['status']=={0:'passed',2:'error'}[code] and reason in t.get('error',''),exitCode=r.returncode,error=t.get('error')))
    def draws(t):return [d for s in t.get('nativeRender',{}).get('snapshots',[]) for d in s.get('activeProjectileVfx',{}).get('historyTrailDraws',[])]
    def check(n,v):rows.append(dict(name=n,passed=bool(v)))
    sample=traces['sampled'];ds=draws(sample);geo=[g for d in ds for g in d.get('geometry',[])]
    check('original-sprite-submissions',bool(geo) and all(d['draw']=='sprites' and d['source']=='center' for d in ds) and all(g['textureWidth']==16 and g['textureHeight']==16 for g in geo))
    check('recorded-sampled-rotations-not-current-pose',any(len({round(g['rotation'],5) for g in d.get('geometry',[])})>1 for d in ds))
    check('bounded-age-selected-draws',all(d['submittedSegments']<=4 for d in ds))
    check('actual-pixels-differ-from-no-trail',[f['sha256'] for f in sample['nativeRender']['frames']]!=[f['sha256'] for f in traces['baseline']['nativeRender']['frames']])
    check('gameplay-unchanged-by-history',sample['snapshots']==traces['baseline']['snapshots'])
    check('fresh-process-reset-replays-exact-pixels',[f['sha256'] for f in sample['nativeRender']['frames']]==[f['sha256'] for f in traces['repeat']['nativeRender']['frames']])
    check('capture-does-not-change-gameplay-or-submissions',sample['snapshots']==traces['no-capture']['snapshots'] and ds==draws(traces['no-capture']))
    last=sample['nativeRender']['snapshots'][-1]
    check('expired-projectile-leaves-no-trail',not last.get('activeProjectileVfx',{}).get('historyTrailDraws'))
    summary=dict(passed=all(r['passed'] for r in rows),scope='Synthetic proof only: sampled entity texture center trails; no alternate material/current pose/tip claim; reset is fresh process',checks=rows)
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2));return 0 if summary['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
