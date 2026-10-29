#!/usr/bin/env python3
"""Real standalone tML/IFC loader scene with a separately autoloaded mod."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dll', type=Path, required=True)
    parser.add_argument('--probe-dll', type=Path, required=True)
    parser.add_argument('--probe-mod-root', type=Path, required=True)
    args = parser.parse_args()
    dll, probe, root = args.native_dll.resolve(), args.probe_dll.resolve(), args.probe_mod_root.resolve()
    dotnet = os.environ.get('DOTNET', 'dotnet')
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='ifc-loader-scene-') as directory:
        temp = Path(directory)
        fixtures = temp / 'fixtures'
        subprocess.run([dotnet, str(dll), '--write-fixtures', str(fixtures)], check=True, capture_output=True, text=True, timeout=120)
        item = json.loads((fixtures / 'synthetic-npc-effect.json').read_text(encoding='utf-8'))
        # This is a test fixture, not a user's item. The world identity change is
        # explicit and limited to the isolated test copy.
        item['recipeMeta']['worldId'] = '12'
        scenario = json.loads((here / 'scenarios/npc-effect.json').read_text(encoding='utf-8'))
        scenario.update(playerUpdate='full', worldId=12)
        scenario_path = temp / 'scenario.json'; scenario_path.write_text(json.dumps(scenario), encoding='utf-8')
        positive = temp / 'item.json'; positive.write_text(json.dumps(item), encoding='utf-8')
        negative = temp / 'no-effect.json'
        next(e for e in item['runtimeProgram']['entities'] if e['id'] == 'root')['events'] = []
        negative.write_text(json.dumps(item), encoding='utf-8')

        def run(name, item_path, with_probe=False, native_item=None, scene_path=None, disable_fixture_modifiers=False):
            trace_path, observer_path = temp / (name + '.json'), temp / (name + '-observer.json')
            command = [dotnet, str(dll), '--native-loader-scene']
            command += ['--native-item', native_item] if native_item is not None else ['--item', str(item_path)]
            command += ['--scenario', str(scene_path or scenario_path), '--output', str(trace_path)]
            env = os.environ.copy()
            env.pop('IFC_FIXTURE_DISABLE_DAMAGE_MODIFIERS', None)
            if with_probe:
                command += ['--probe-dll', str(probe), '--probe-mod-root', str(root)]
                env['IFC_WORKBENCH_OBSERVER_OUTPUT'] = str(observer_path)
                if disable_fixture_modifiers: env['IFC_FIXTURE_DISABLE_DAMAGE_MODIFIERS'] = '1'
            else:
                env.pop('IFC_WORKBENCH_OBSERVER_OUTPUT', None)
            proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
            if not trace_path.exists(): raise AssertionError((name, proc.returncode, proc.stderr))
            trace = json.loads(trace_path.read_text(encoding='utf-8'))
            observer = json.loads(observer_path.read_text(encoding='utf-8')) if observer_path.exists() else {}
            return proc, trace, observer

        base_proc, base, _ = run('base', positive)
        mod_proc, mod, observer = run('extra-mod', positive, True)
        neg_proc, neg, _ = run('no-effect', negative)
        assert base_proc.returncode == mod_proc.returncode == 0 and base['status'] == mod['status'] == 'passed', (base.get('error'), mod.get('error'))
        assert base['execution']['worldRegistered'] and mod['execution']['worldRegistered']
        assert base['combat'] == mod['combat'] and base['combat']['hits'] > 0
        assert mod['execution']['additionalMod'] == 'WorkbenchObserverFixture'
        counts = observer.get('counts', {})
        assert counts.get('ModSystem.PostUpdateEverything') == scenario['ticks'], counts
        for name in ('ModPlayer.PostUpdate', 'GlobalItem.ModifyWeaponDamage.Any', 'ModPlayer.ModifyWeaponDamage.Any',
                     'GlobalProjectile.OnSpawn.Any', 'GlobalProjectile.PostAI.Any',
                     'GlobalNPC.ModifyHitByProjectile.Any', 'GlobalProjectile.OnHitNPC.Any'):
            assert counts.get(name, 0) > 0, (name, counts)
        assert neg_proc.returncode == 1 and neg['status'] == 'failed', (neg_proc.returncode, neg.get('error'))
        assert any(a['name'] == 'target_effect_at' and a['status'] == 'failed' for a in neg['assertions'])
        # Exercise the loaded third-party ModItem, ModProjectile and ModNPC as
        # actual entities, rather than only observing its globals on an IFC item.
        probe_scene = {'playerUpdate':'full', 'ticks':120, 'seed':1,
            'player':{'x':640,'y':640,'life':100,'mana':200},
            'dummy':{'x':850,'y':640,'nativeType':'WorkbenchObserverFixture/ProbeNpc'},
            'actions':[{'tick':0,'kind':'aim','x':850,'y':661},{'tick':0,'kind':'primary'},{'tick':1,'kind':'release'}],
            'assertions':[{'kind':'spawned'},{'kind':'dummy_damaged'},{'kind':'all_inactive'},{'kind':'no_nonfinite'}]}
        probe_path=temp/'probe-scene.json';probe_path.write_text(json.dumps(probe_scene), encoding='utf-8')
        item_proc, item_trace, item_observer = run('native-mod-item', None, True, 'WorkbenchObserverFixture/ProbeItem', probe_path)
        assert item_proc.returncode == 0 and item_trace['status'] == 'passed' and item_trace['combat']['hits'] > 0, (item_proc.stderr, item_trace.get('error'))
        counts=item_observer.get('counts', {})
        assert counts.get('ModSystem.PostUpdateEverything') == probe_scene['ticks'], counts
        for name in ('ModItem.CanUseItem','ModItem.Shoot','GlobalItem.ModifyWeaponDamage',
                     'ModPlayer.ModifyWeaponDamage','ModPlayer.PostUpdate','ModProjectile.AI',
                     'ModProjectile.OnHitNPC','GlobalProjectile.OnSpawn','GlobalProjectile.PostAI',
                     'GlobalProjectile.OnHitNPC','GlobalNPC.OnSpawn','GlobalNPC.ModifyHitByProjectile','ModNPC.AI'):
            assert counts.get(name, 0)>0, (name, counts)
        control_proc, control_trace, control_observer = run('native-mod-damage-control',None,True,'WorkbenchObserverFixture/ProbeItem',probe_path,True)
        assert control_proc.returncode == 0 and control_trace['status'] == 'passed', (control_proc.stderr,control_trace.get('error'))
        enabled_damage=item_trace['combat']['initialLife']-item_trace['combat']['finalLife']
        control_damage=control_trace['combat']['initialLife']-control_trace['combat']['finalLife']
        assert enabled_damage>control_damage>0, (enabled_damage,control_damage)
        assert control_observer.get('counts',{}).get('GlobalNPC.ModifyHitByProjectile',0)>0
        missing_proc, missing_trace, _=run('missing-mod',None,False,'WorkbenchObserverFixture/ProbeItem',probe_path)
        assert missing_proc.returncode == 2 and missing_trace['status'] == 'error', (missing_proc.returncode, missing_trace)
        # Out-of-world rectangles must not overflow to an empty, silently
        # ignored range and produce a false successful scene.
        for axis in ('width', 'height'):
            overflow_scene={'ticks':1,'player':{'x':640,'y':640},'dummy':{'x':850,'y':640},
                'actions':[],'assertions':[{'kind':'no_nonfinite'}],
                'tiles':[{'tileX':2,'tileY':2,'width':1,'height':1,axis:2147483647}]}
            overflow_path=temp/('overflow-'+axis+'.json');overflow_path.write_text(json.dumps(overflow_scene),encoding='utf-8')
            bad_proc,bad_trace,_=run('overflow-result-'+axis,None,False,'WoodenBoomerang',overflow_path)
            assert bad_proc.returncode==2 and bad_trace['status']=='error' and 'Tile rectangle outside' in bad_trace.get('error',''), (bad_proc.returncode,bad_trace)
        # The loader must reject a foreign world rather than normalizing the
        # generated input into the current world's registry.
        foreign=json.loads(positive.read_text(encoding='utf-8'));foreign['recipeMeta']['worldId']='999'
        foreign_path=temp/'foreign-world.json';foreign_path.write_text(json.dumps(foreign),encoding='utf-8')
        original_bytes=foreign_path.read_bytes()
        foreign_proc,foreign_trace,_=run('foreign-world-result',foreign_path)
        assert foreign_proc.returncode==2 and foreign_trace['status']=='error' and 'scenario worldId' in foreign_trace.get('error',''), (foreign_proc.returncode,foreign_trace)
        assert foreign_path.read_bytes()==original_bytes
        vanilla_scene=json.loads((here/'scenarios/full-vanilla.json').read_text(encoding='utf-8'))
        vanilla_scene['assertions']=[{'kind':'spawned'},{'kind':'dummy_damaged'},{'kind':'all_inactive'},{'kind':'no_nonfinite'}]
        vanilla_path=temp/'vanilla-scene.json';vanilla_path.write_text(json.dumps(vanilla_scene),encoding='utf-8')
        vanilla_proc, vanilla_trace, _=run('native-vanilla-item',None,False,'WoodenBoomerang',vanilla_path)
        assert vanilla_proc.returncode == 0 and vanilla_trace['status'] == 'passed' and vanilla_trace['combat']['hits']>0, (vanilla_proc.stderr,vanilla_trace.get('error'))
    print(f'Native loader scenes, mod item/NPC hooks, system cadence and negative controls: PASS (modifiers: {enabled_damage} vs {control_damage} damage)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
