#!/usr/bin/env python3
"""Reproducible native scenario matrix; expected failures must fail, not be skipped."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import workbench as w


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--no-build',action='store_true');parser.add_argument('--native-dll',type=Path,help='Direct executable, with independent build receipt; not wrapper provenance');args=parser.parse_args()
    if args.native_dll and not args.no_build:parser.error('--native-dll requires --no-build')
    out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise SystemExit('Use a fresh output directory')
    out.mkdir(parents=True,exist_ok=True)
    if not args.no_build:w.build()
    dll=(args.native_dll or w.HERE/'bin/Release/net8.0/ItemTestWorkbench.dll').resolve();binaries=w.native_binaries_state(dll)
    def binaries_unchanged():
        try:return w.native_binaries_state(dll)==binaries
        except OSError:return False
    fixtures=out/'fixtures';subprocess.run([os.environ.get('DOTNET','dotnet'),str(dll),'--write-fixtures',str(fixtures)],cwd=w.ROOT,check=True)
    base=w.read_json(w.HERE/'scenarios/primary.json')
    def modified(**changes):
        value=json.loads(json.dumps(base));value.update(changes);return value
    finite={'kind':'no_nonfinite'}
    inactive={'kind':'all_inactive'}
    spawned={'kind':'spawn_count','value':1}
    cases=[('straight','synthetic-straight.json',base,0),
           ('charge','synthetic-charge.json',w.read_json(w.HERE/'scenarios/charge-release.json'),0),
           ('alternate','synthetic-alt.json',w.read_json(w.HERE/'scenarios/alternate.json'),0),
           ('mana-debit','synthetic-mana.json',modified(assertions=[spawned,{'kind':'mana_equals','value':190},finite]),0),
           ('mana-refused','synthetic-mana.json',modified(player={**base['player'],'mana':5},assertions=[{'kind':'spawn_count','value':0},{'kind':'mana_equals','value':5},finite]),0),
           ('held-cadence','synthetic-straight.json',modified(ticks=60,actions=[{'tick':0,'kind':'primary'},{'tick':59,'kind':'release'}],assertions=[{'kind':'spawn_count','value':3},finite]),0),
           ('click-cooldown','synthetic-straight.json',modified(actions=[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'},{'tick':2,'kind':'primary'},{'tick':3,'kind':'release'}],assertions=[spawned,finite]),0),
           ('natural-expiry','synthetic-straight.json',modified(dummy={**base['dummy'],'y':1000},assertions=[spawned,inactive,finite,{'kind':'natural_expiry'}]),0),
           ('negative-miss','synthetic-straight.json',w.read_json(w.HERE/'scenarios/negative-miss.json'),1),
           ('negative-empty-assertions','synthetic-straight.json',modified(assertions=[]),2),
           ('negative-unknown-action','synthetic-straight.json',modified(actions=[{'tick':0,'kind':'primray'}]),2),
           ('negative-invalid-item','invalid.json',base,2),
           ('negative-held-buff','unsupported-held-buff.json',base,2),
           ('tile-wall','synthetic-wall.json',modified(tiles=[{'tileX':48,'tileY':36,'width':1,'height':12}],assertions=[spawned,{'kind':'tile_collision'},{'kind':'dummy_undamaged'},inactive,finite]),0),
           ('vanilla-wooden-boomerang',284,modified(ticks=180,assertions=[spawned,{'kind':'dummy_damaged'},inactive,finite]),0),
           ('straight-repeat','synthetic-straight.json',base,0),
           ('return-coincident-finite-regression','synthetic-return.json',modified(dummy={**base['dummy'],'y':1000},assertions=[spawned,{'kind':'returned'},finite]),0),
           ('imported-front-hand',str(w.ROOT/'tools/fixtures/front-hand-compiled.json'),modified(assertions=[{'kind':'spawned'},inactive,finite]),0),
           ('captured-pumpkin-wand',str(w.ROOT/'tools/fixtures/video-ui-buffs/g_4efc7c05f7b078e0.json'),modified(player={**base['player'],'life':80,'maxLife':100},dummy={**base['dummy'],'x':750},assertions=[spawned,{'kind':'dummy_damaged'},{'kind':'life_equals','value':81},{'kind':'mana_equals','value':195},inactive,finite]),0),
           ('captured-frog-chest-wand',str(w.ROOT/'tools/fixtures/video-ui-buffs/g_17d5099f992a900b.json'),modified(player={**base['player'],'life':80,'maxLife':100},dummy={**base['dummy'],'x':750},assertions=[spawned,{'kind':'dummy_damaged'},{'kind':'life_equals','value':81},{'kind':'mana_equals','value':190},inactive,finite]),0)]
    # An interval of held alt must behave like the formerly necessary explicit
    # per-tick reassertion, and a later primary must switch the binding.
    alt_base=w.read_json(w.HERE/'scenarios/alternate.json')
    alt_base['assertions']=[finite]
    held=json.loads(json.dumps(alt_base)); held['actions']=[{'tick':0,'kind':'alt'},{'tick':80,'kind':'release'},{'tick':100,'kind':'primary'},{'tick':101,'kind':'release'}]
    explicit=json.loads(json.dumps(held)); explicit['actions']=[{'tick':t,'kind':'alt'} for t in range(80)]+held['actions'][1:]
    cases.extend([('alt-held-switch','synthetic-alt.json',held,0),('alt-explicit-switch','synthetic-alt.json',explicit,0)])
    for name,scene in [('alt-held-switch-full',held),('alt-explicit-switch-full',explicit)]:
        scene=json.loads(json.dumps(scene));scene['playerUpdate']='full';scene['tiles']=[{'tileX':1,'tileY':44,'width':97,'height':1}]
        cases.append((name,'synthetic-alt.json',scene,0))
    frog=str(w.ROOT/'tools/fixtures/video-ui-buffs/g_17d5099f992a900b.json')
    pumpkin=str(w.ROOT/'tools/fixtures/video-ui-buffs/g_4efc7c05f7b078e0.json')
    cases.extend([
        ('full-captured-primary',frog,w.read_json(w.HERE/'scenarios/full-primary.json'),0),
        ('full-captured-alt',frog,w.read_json(w.HERE/'scenarios/full-alternate.json'),0),
        ('full-alt-repeat',frog,w.read_json(w.HERE/'scenarios/full-alternate-repeat.json'),0),
        ('full-alt-repeat-again',frog,w.read_json(w.HERE/'scenarios/full-alternate-repeat.json'),0),
        ('full-held-deselect','unsupported-held-buff.json',w.read_json(w.HERE/'scenarios/full-held-deselect.json'),0),
        ('full-vanilla',284,w.read_json(w.HERE/'scenarios/full-vanilla.json'),0),
        ('full-pumpkin-pet',pumpkin,w.read_json(w.HERE/'scenarios/full-pumpkin-pet.json'),0),
    ])
    insufficient=w.read_json(w.HERE/'scenarios/full-alternate.json');insufficient['ticks']=30;insufficient['player']['mana']=5
    insufficient['assertions']=[{'kind':'mana_debited','value':0},{'kind':'teleport_count','value':0},{'kind':'spawn_count','value':0},{'kind':'jump_boost_equals','value':0},finite]
    wrong_blink=w.read_json(w.HERE/'scenarios/full-alternate-repeat.json')
    for check in wrong_blink['assertions']:
        if check['kind']=='teleport_count':check['value']=3
    short_held=w.read_json(w.HERE/'scenarios/full-held-deselect.json');short_held['ticks']=100
    vanilla_repeat=modified(ticks=180,actions=[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'},{'tick':20,'kind':'primary'},{'tick':21,'kind':'release'}],assertions=[spawned,{'kind':'dummy_damaged'},inactive,finite])
    full_vanilla_repeat=w.read_json(w.HERE/'scenarios/full-vanilla.json');full_vanilla_repeat['actions']=vanilla_repeat['actions']
    cases.extend([('full-alt-insufficient',frog,insufficient,0),('full-negative-blink-count',frog,wrong_blink,1),('full-negative-premature-expiry','unsupported-held-buff.json',short_held,1),('vanilla-repeat',284,vanilla_repeat,0),('full-vanilla-repeat',284,full_vanilla_repeat,0)])
    pumpkin_primary=w.read_json(w.HERE/'scenarios/full-primary.json')
    for check in pumpkin_primary['assertions']:
        if check['kind']=='mana_debited':check['value']=5
    cases.append(('full-pumpkin-primary',pumpkin,pumpkin_primary,0))
    crystal=str(w.ROOT/'tools/fixtures/video-ui-buffs/g_9ea7b3af556e6125.json')
    equipment=w.read_json(w.HERE/'scenarios/full-equipment.json')
    inventory=json.loads(json.dumps(equipment));inventory['actions']=[]
    inventory['assertions']=[finite,{'kind':'spawn_count','value':0},{'kind':'player_stat_at','tick':119,'stat':'maxMana','value':200},{'kind':'player_stat_at','tick':119,'stat':'manaCost','value':1}]
    vanity=json.loads(json.dumps(inventory));vanity['actions']=[{'tick':0,'kind':'vanity'}]
    wrong_equipment=json.loads(json.dumps(equipment));wrong_equipment['assertions']=[{'kind':'player_stat_at','tick':0,'stat':'maxMana','value':280},finite]
    refused_equipment=json.loads(json.dumps(equipment));refused_equipment['playerUpdate']='item_check'
    cases.extend([('full-equipment',crystal,equipment,0),('full-equipment-inventory',crystal,inventory,0),('full-equipment-vanity',crystal,vanity,0),('full-equipment-negative-stacking',crystal,wrong_equipment,1),('negative-equipment-itemcheck',crystal,refused_equipment,2)])
    ammo_base={'playerUpdate':'full','ticks':50,'seed':1,'player':{'x':800,'y':700},'dummy':{'x':1000,'y':700,'life':10000},'tiles':[{'tileX':1,'tileY':47,'width':97,'height':1}],'actions':[{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}]}
    def ammo_check(kind,item_id,value,slot=None):
        check={'kind':kind,'itemId':item_id,'value':value}
        if slot is not None:check['slot']=slot
        return check
    def ammo_case(name,category,speed,inventory,spawns,checks,repeat=False,expected=0):
        scenario=json.loads(json.dumps(ammo_base));scenario['inventory']=[{'slot':slot,'itemId':item_id,'stack':count} for slot,item_id,count in inventory]
        if repeat:
            scenario['ticks']=180;scenario['actions']=[{'tick':tick+offset,'kind':kind} for tick in [0,50,100,150] for offset,kind in [(0,'primary'),(1,'release')]]
        scenario['assertions']=[{'kind':'spawn_count','value':spawns},finite,*checks]
        cases.append(('ammo-'+name,'synthetic-ammo-'+category+'-'+speed+'.json',scenario,expected))
    for category,item_id,wrong in [('arrow',40,97),('bullet',278,40),('fallen_star',75,40)]:
        for speed in ['authored_spawn','native_shot']:
            ammo_case(category+'-'+speed,category,speed,[(54,item_id,3)],1,[ammo_check('inventory_stack',item_id,2,54),ammo_check('ammo_source_spawn_count',item_id,1),ammo_check('ammo_consumed_count',item_id,1)])
        ammo_case(category+'-empty',category,'authored_spawn',[],0,[ammo_check('ammo_consumed_count',item_id,0),ammo_check('ammo_source_spawn_count',item_id,0)])
        ammo_case(category+'-wrong',category,'authored_spawn',[(54,wrong,3)],0,[ammo_check('inventory_stack',wrong,3,54),ammo_check('ammo_consumed_count',wrong,0)])
        ammo_case(category+'-depletion',category,'authored_spawn',[(54,item_id,3)],3,[ammo_check('inventory_stack',0,0,54),ammo_check('ammo_source_spawn_count',item_id,3),ammo_check('ammo_consumed_count',item_id,3)],True)
    ammo_case('priority','arrow','authored_spawn',[(54,40,3),(1,40,5)],1,[ammo_check('inventory_stack',40,2,54),ammo_check('inventory_stack',40,5,1)])
    for category,item_id in [('arrow',3103),('bullet',3104)]:
        ammo_case('endless-'+category,category,'authored_spawn',[(54,item_id,1)],1,[ammo_check('inventory_stack',item_id,1,54),ammo_check('ammo_consumed_count',item_id,0),ammo_check('ammo_source_spawn_count',item_id,1)])
    ammo_case('negative-endless-debit','arrow','authored_spawn',[(54,3103,1)],1,[ammo_check('ammo_consumed_count',3103,1)],expected=1)
    ammo_case('negative-finite-conservation','arrow','authored_spawn',[(54,40,3)],1,[ammo_check('ammo_consumed_count',40,0)],expected=1)
    (fixtures/'invalid.json').write_text('{}')
    held=w.read_json(fixtures/'synthetic-straight.json')
    held['runtimeProgram']['effectGroups']=[{'id':'held_utility','generatedBuff':{'durationTicks':60,'jumpBoost':0.5}}]
    held['runtimeProgram']['heldEffectGroupId']='held_utility'
    (fixtures/'unsupported-held-buff.json').write_text(json.dumps(held,indent=2))
    rows=[]
    for name,item,scenario,expected in cases:
        scenario_path=out/(name+'-scenario.json');scenario_path.write_text(json.dumps(scenario,indent=2))
        command=[sys.executable,str(w.HERE/'workbench.py'),'run']+(['--vanilla-item',str(item)] if isinstance(item,int) else ['--item',str(fixtures/item)])+['--scenario',str(scenario_path),'--out',str(out/name),'--no-build']
        if args.native_dll:
            command=[os.environ.get('DOTNET','dotnet'),str(dll)]+(['--vanilla-item',str(item)] if isinstance(item,int) else ['--item',str(fixtures/item)])+['--scenario',str(scenario_path),'--output',str(out/name/'native.json')]
        proc=subprocess.run(command,cwd=w.ROOT,capture_output=True,text=True,timeout=240)
        trace_path=out/name/'native.json';trace=w.read_json(trace_path) if trace_path.exists() else {}
        passed=binaries_unchanged() and proc.returncode==expected and trace.get('status')=={0:'passed',1:'failed',2:'error'}[expected]
        if name=='negative-held-buff':
            passed=passed and 'NotSupportedException' in trace.get('error','') and 'held' in trace.get('error','').lower()
        if name=='return-coincident-finite-regression':
            passed = passed and bool(trace.get('snapshots')) and not any(p.get('nonFinite') for frame in trace['snapshots'] for p in frame.get('projectiles',[]))
        rows.append({'name':name,'passed':passed,'expectedExitCode':expected,'actualExitCode':proc.returncode,'nativeStatus':trace.get('status'),'trace':str(trace_path),'runnerStdout':proc.stdout,'runnerStderr':proc.stderr})
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
    def recorded(name):
        path=out/name/'native.json'
        return w.read_json(path) if path.exists() else {}
    def binding_spawns(name):
        return [(f['tick'],e.get('entityId')) for f in recorded(name).get('snapshots',[]) for e in f.get('events',[]) if e.get('kind')=='entity_configured']
    for suffix in ('','-full'):
        held_spawns=binding_spawns('alt-held-switch'+suffix); explicit_spawns=binding_spawns('alt-explicit-switch'+suffix)
        rows.append({'name':'held-alt-does-not-switch-to-primary'+suffix, 'passed':held_spawns==explicit_spawns and sum(t<80 and e=='alt' for t,e in held_spawns)>=2 and not any(t<100 and e=='root' for t,e in held_spawns) and any(t>=100 and e=='root' for t,e in held_spawns), 'spawns':held_spawns})
    first=recorded('straight');second=recorded('straight-repeat')
    deterministic=bool(first and second) and first.get('snapshots')==second.get('snapshots') and first.get('assertions')==second.get('assertions')
    rows.append({'name':'same-seed-determinism','passed':deterministic})
    cadence=recorded('held-cadence')
    spawn_ids=[e['projectileId'] for frame in cadence.get('snapshots',[]) for e in frame['events'] if e['kind']=='spawn']
    rows.append({'name':'distinct-projectile-lifetimes','passed':len(spawn_ids)==3 and len(set(spawn_ids))==3,'spawnIds':spawn_ids})
    full=recorded('full-alt-repeat');full_repeat=recorded('full-alt-repeat-again')
    rows.append({'name':'full-player-same-seed-determinism','passed':bool(full and full_repeat) and full.get('snapshots')==full_repeat.get('snapshots') and full.get('assertions')==full_repeat.get('assertions')})
    post={s['tick']:s for s in full.get('snapshots',[]) if s.get('phase')!='after_input_before_update'}
    checkpoints={0:(299,119),60:(299,59),121:(299,119),420:(0,0)}
    correct=all(post.get(t,{}).get('player',{}).get('generatedBuffTicks')==buff and post.get(t,{}).get('player',{}).get('mobilityCooldownTicks')==cooldown for t,(buff,cooldown) in checkpoints.items())
    correct=correct and post.get(421,{}).get('player',{}).get('jumpSpeedBoost')==0 and max(s['player']['jumpSpeedBoost'] for s in full.get('snapshots',[]))==1.5
    rows.append({'name':'native-buff-cooldown-exact-checkpoints-and-no-stacking','passed':correct,'checkpoints':{str(t):list(v) for t,v in checkpoints.items()}})
    for category,native_speed,damage,knockback in [('arrow',11,35,4),('bullet',12.5,39,5)]:
        observed={};passed=True
        for policy,expected_speed in [('authored_spawn',8),('native_shot',native_speed)]:
            trace=recorded('ammo-'+category+'-'+policy)
            roots=[e for frame in trace.get('snapshots',[]) for e in frame.get('events',[]) if e.get('kind')=='spawn']
            passed=passed and len(roots)==1
            if roots:
                root=roots[0];speed=math.hypot(root['initialVx'],root['initialVy']);observed[policy]={'speed':speed,'damage':root['initialDamage'],'knockback':root['initialKnockback']}
                passed=passed and abs(speed-expected_speed)<.0001 and root['initialDamage']==damage and root['initialKnockback']==knockback
            passed=passed and bool(trace.get('snapshots')) and all(any(i['slot']==0 and i['stack']==1 for i in frame['player']['inventory']) for frame in trace.get('snapshots',[]))
        rows.append({'name':'ammo-'+category+'-native-launch-policy-and-weapon-preservation','passed':passed,'observed':observed})
    summary={**binaries,'binariesUnchanged':binaries_unchanged(),'buildProvenance':'Explicit direct executable; independent source-build receipt required' if args.native_dll else 'standard workbench wrapper','fullGameParity':False,'scope':'Actual native scenarios and explicit negative controls; not universal item coverage','passed':all(r['passed'] for r in rows) and binaries_unchanged(),'itemReadiness':'not certified','regressionScope':'Coincident return seek must remain finite after the production fix; negative controls still require their exact intended failures','checks':rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
