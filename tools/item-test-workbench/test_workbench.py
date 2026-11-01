"""Replay/runner safety checks. Synthetic telemetry is never native evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('workbench',Path(__file__).with_name('workbench.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

def trace():
    actor={'x':10,'y':20,'width':16,'height':32}
    return {'schemaVersion':1,'status':'failed','timeline':{'requestedTicks':3,'completedTicks':3,'complete':True},'execution':{'backend':'synthetic-renderer-test','fullGameParity':False,'unsupported':['game-rendering']},
            'input':{'path':'</script><script>alert(1)</script>'},'assertions':[{'name':'negative control','status':'failed'}],
            'snapshots':[{'tick':i,'player':actor,'dummy':dict(actor,x=80),'projectiles':[dict(actor,id=7,entityId='<unsafe>',vx=2,vy=0,active=True,x=20+i*2)]} for i in range(3)]}

class WorkbenchTests(unittest.TestCase):
    def test_loader_run_requires_completed_assertions_and_agrees_with_exit(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);item=root/'item.json';scene=root/'scene.json';dll=root/'ItemTestWorkbench.dll'
            item.write_text('{}');scene.write_text('{"ticks":2}');dll.write_bytes(b'host')
            complete={'status':'passed','snapshots':[{'tick':0},{'tick':1}],'assertions':[{'status':'passed'}]}
            for i,(report,exit_code,valid) in enumerate([(complete,0,True),({'status':'passed'},0,False),(complete,1,False)]):
                args=SimpleNamespace(timeout=10,item=item,scenario=scene,out=root/str(i),no_build=True,item_boundary='fresh',probe_dll=None,probe_mod_root=None)
                def run(command,**kwargs):
                    self.assertIn('--native-loader-scene',command)
                    Path(command[command.index('--output')+1]).write_text(json.dumps(report))
                    return subprocess.CompletedProcess(command,exit_code,'','')
                with patch.object(w,'native_executable',return_value=(dll,{})),patch.object(w,'build_state',return_value={}),patch.object(w.subprocess,'run',side_effect=run):
                    if valid:self.assertEqual(w.execute_loader_run(args),0)
                    else:
                        with self.assertRaises(RuntimeError):w.execute_loader_run(args)

    def test_loader_receipt_tracks_effective_production_content_override(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dll=root/'ItemTestWorkbench.dll';dll.write_bytes(b'host')
            scene=root/'scene.json';scene.write_text('{"ticks":1}')
            content=root/'custom-mod';content.mkdir();metadata=content/'build.txt'
            report={'status':'passed','snapshots':[{'tick':0}],'assertions':[{'status':'passed'}]}
            for mutate in (False,True):
                metadata.write_text('version=1')
                args=SimpleNamespace(timeout=10,item=None,native_item='WoodenBoomerang',scenario=scene,
                    out=root/str(mutate),no_build=True,item_boundary='fresh',probe_dll=None,probe_mod_root=None)
                def run(command,**kwargs):
                    Path(command[command.index('--output')+1]).write_text(json.dumps(report))
                    if mutate:metadata.write_text('version=2')
                    return subprocess.CompletedProcess(command,0,'','')
                with patch.dict(w.os.environ,{'INFINI_MOD_SOURCE_ROOT':str(content)}), \
                     patch.object(w,'native_executable',return_value=(dll,{})), \
                     patch.object(w,'build_state',return_value={}),patch.object(w.subprocess,'run',side_effect=run):
                    if mutate:
                        with self.assertRaisesRegex(RuntimeError,'changed during execution'):w.execute_loader_run(args)
                    else:self.assertEqual(w.execute_loader_run(args),0)
                receipt=json.loads((args.out/'receipt.json').read_text())
                self.assertEqual(receipt['productionContent']['root'],str(content))
                self.assertEqual(receipt['productionContent']['files']['build.txt'],w.hashlib.sha256(b'version=1').hexdigest())
                self.assertEqual(receipt['binariesUnchanged'],not mutate)

    def test_direct_native_receipt_tracks_host_and_separate_mod(self):
        with tempfile.TemporaryDirectory() as d:
            host=Path(d)/'ItemTestWorkbench.dll';mod=Path(d)/'InfiniCrafterLocal.dll'
            host.write_bytes(b'host')
            with self.assertRaises(FileNotFoundError):w.native_binaries_state(host)
            mod.write_bytes(b'mod');before=w.native_binaries_state(host)
            mod.write_bytes(b'changed mod');self.assertNotEqual(before,w.native_binaries_state(host))
            mod.write_bytes(b'mod');host.write_bytes(b'changed host');self.assertNotEqual(before,w.native_binaries_state(host))

    def test_loader_receipt_detects_changed_archive(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);host=root/'ItemTestWorkbench.dll';host.write_bytes(b'host')
            scene=root/'scene.json';scene.write_text('{"ticks":1}')
            archive=root/'fixture.tmod';archive.write_bytes(b'original')
            args=SimpleNamespace(timeout=10,item=None,native_item='Example/Item',scenario=scene,
                out=root/'run',no_build=True,item_boundary='fresh',probe_dll=None,probe_mod_root=None,tmods=[archive],server_mode=True)
            def run(command,**kwargs):
                self.assertEqual(command[command.index('--tmod')+1],str(archive))
                self.assertEqual(command[command.index('--server-mode')+1],'true')
                Path(command[command.index('--output')+1]).write_text(json.dumps({'status':'passed','snapshots':[{'tick':0}],'assertions':[{'status':'passed'}]}))
                archive.write_bytes(b'changed')
                return subprocess.CompletedProcess(command,0,'','')
            with patch.object(w,'native_executable',return_value=(host,{})),patch.object(w,'build_state',return_value={}),patch.object(w.subprocess,'run',side_effect=run):
                with self.assertRaisesRegex(RuntimeError,'changed during execution'):w.execute_loader_run(args)
            receipt=json.loads((args.out/'receipt.json').read_text())
            self.assertEqual(receipt['extraArchives'][str(archive)],w.hashlib.sha256(b'original').hexdigest())
            self.assertFalse(receipt['binariesUnchanged'])

    def test_loader_tracks_all_extra_mod_content_and_preserves_input_order(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);host=root/'ItemTestWorkbench.dll';host.write_bytes(b'host')
            scene=root/'scene.json';scene.write_text('{"ticks":1}')
            mods=[]
            for name in ('dependent','dependency'):
                dll=root/(name+'.dll');dll.write_bytes(name.encode())
                content=root/name;(content/'Items').mkdir(parents=True)
                (content/'build.txt').write_text('version=1')
                (content/'Items'/'texture.png').write_bytes(b'original')
                mods.append((dll,content))
            report={'status':'passed','snapshots':[{'tick':0}],'assertions':[{'status':'passed'}]}
            for mutate in (False,True):
                texture=mods[0][1]/'Items'/'texture.png';texture.write_bytes(b'original')
                args=SimpleNamespace(timeout=10,item=None,native_item='Example/Item',scenario=scene,
                    out=root/str(mutate),no_build=True,item_boundary='fresh',probe_dll=None,probe_mod_root=None,mods=mods)
                def run(command,**kwargs):
                    pairs=[(command[i+1],command[i+3]) for i,x in enumerate(command) if x=='--mod-dll']
                    self.assertEqual(pairs,[(str(dll),str(content)) for dll,content in mods])
                    Path(command[command.index('--output')+1]).write_text(json.dumps(report))
                    if mutate:texture.write_bytes(b'changed')
                    return subprocess.CompletedProcess(command,0,'','')
                with patch.object(w,'native_executable',return_value=(host,{})),patch.object(w,'build_state',return_value={}),patch.object(w.subprocess,'run',side_effect=run):
                    if mutate:
                        with self.assertRaisesRegex(RuntimeError,'changed during execution'):w.execute_loader_run(args)
                    else:self.assertEqual(w.execute_loader_run(args),0)
                receipt=json.loads((args.out/'receipt.json').read_text())
                self.assertEqual(receipt['extraContent'][str(mods[0][1])]['Items/texture.png'],w.hashlib.sha256(b'original').hexdigest())
                self.assertEqual(receipt['binariesUnchanged'],not mutate)

    def test_no_build_refuses_changed_index_or_separate_mod_build_inputs(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);here=root/'tools/item-test-workbench'
            sources={
                here/'vanilla-item-assets.json':b'{"items":{}}',
                here/'production-mod/InfiniCrafterWorkbenchMod.csproj':b'<Project />',
                root/'ModSources/InfiniCrafterLocal/Assets/item.png':b'asset',
                root/'ModSources/InfiniCrafterLocal/Localization/en-US.hjson':b'Name: item',
                root/'ModSources/InfiniCrafterLocal/build.txt':b'version=1',
            }
            for path,raw in sources.items():
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            dll=here/'bin/Release/net8.0/ItemTestWorkbench.dll'
            dll.parent.mkdir(parents=True);dll.write_bytes(b'host')
            (dll.parent/'InfiniCrafterLocal.dll').write_bytes(b'production mod')
            with patch.object(w,'ROOT',root),patch.object(w,'HERE',here),patch.object(w,'doctor',return_value={'ready':True}):
                (dll.parent/'build-provenance.json').write_text(json.dumps(w.build_state(dll)))
                self.assertEqual(w.native_executable(no_build=True)[0],dll)
                for path,raw in sources.items():
                    with self.subTest(source=str(path.relative_to(root))):
                        path.write_bytes(raw+b' changed')
                        with self.assertRaisesRegex(RuntimeError,'stale or modified'):
                            w.native_executable(no_build=True)
                        path.write_bytes(raw)
                        self.assertEqual(w.native_executable(no_build=True)[0],dll)

    def test_shared_build_gate_refuses_missing_or_malformed_readiness(self):
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('workbench_release_gate',w.ROOT/'tools/validate_release.py')
        gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
        command=['python','tools/item-test-workbench/workbench.py','build']
        for output,code,status in [('{"ready":false}',2,'notRun'),('bad-json',2,'failed'),('{"ready":true}',2,'failed')]:
            with patch.object(gate,'_execute',return_value=subprocess.CompletedProcess([],code,output)) as execute:
                result=gate.run_check('item_workbench_build',command,root=w.ROOT,env={})
                self.assertEqual(result['status'],status);self.assertEqual(execute.call_count,1)
                self.assertEqual(execute.call_args.args[0][-1],'doctor')
        with patch.object(gate,'_execute',side_effect=[subprocess.CompletedProcess([],0,'{"ready":true}'),subprocess.CompletedProcess([],0,'built')]) as execute:
            result=gate.run_check('item_workbench_build',command,root=w.ROOT,env={})
            self.assertEqual(result['status'],'passed');self.assertEqual(execute.call_count,2)
            self.assertEqual(execute.call_args.args[0][-1],'build')


    def test_build_receipt_covers_copied_runtime_and_load_manifests(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);dll=root/'ItemTestWorkbench.dll';dll.write_bytes(b'own fixture')
            dep=root/'tModLoader.dll';dep.write_bytes(b'copied runtime fixture')
            manifest=root/'ItemTestWorkbench.deps.json';manifest.write_text('{}')
            before=w.build_state(dll)
            self.assertEqual(before['runtimeFilesSha256']['tModLoader.dll'],w.digest(dep))
            dep.write_bytes(b'altered copied runtime');self.assertNotEqual(before,w.build_state(dll))
            dep.write_bytes(b'copied runtime fixture');manifest.write_text('{"changed":true}')
            self.assertNotEqual(before,w.build_state(dll))
            manifest.write_text('{}');dep.unlink();self.assertNotEqual(before,w.build_state(dll))
            content=root/'native-mod';content.mkdir();metadata=content/'build.txt';metadata.write_text('version=1')
            before=w.build_state(dll);metadata.write_text('version=2');self.assertNotEqual(before,w.build_state(dll))

    def test_build_receipt_distinguishes_configured_reference_from_runtime(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bin_dir=root/'bin';bin_dir.mkdir();refs=root/'refs';refs.mkdir()
            dll=bin_dir/'ItemTestWorkbench.dll';dll.write_bytes(b'own fixture')
            copied=bin_dir/'tModLoader.dll';copied.write_bytes(b'actual copied bytes')
            reference=refs/'tModLoader.dll';reference.write_bytes(b'configured reference bytes')
            with patch.dict(w.os.environ,{'INFINI_TML_REFERENCE_DIR':str(refs)}):
                before=w.build_state(dll)
                self.assertNotEqual(before['runtimeFilesSha256']['tModLoader.dll'],before['configuredReferences']['tModLoader']['sha256'])
                reference.write_bytes(b'reference changed after build');self.assertNotEqual(before,w.build_state(dll))


    def test_summary_uses_recorded_damage_and_net_resources_without_reclassifying(self):
        t=trace();t['resources']={'observedManaDebited':7};t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],mana=100,life=90)
        t['snapshots'][-1]['player']=dict(t['snapshots'][-1]['player'],mana=95,life=91)
        t['snapshots'][0]['events']=[{'kind':'hit','damageDone':10,'crit':True},{'kind':'item_hit','damageDone':17,'crit':False}]
        before=json.dumps(t);summary=w.summarize_trace(t)
        self.assertEqual(summary['status'],'failed');self.assertEqual(summary['nativeHits']['hit'],{'count':1,'damageDone':10,'criticalCount':1,'unknownCriticalCount':0})
        self.assertEqual(summary['resources']['mana']['delta'],-5)
        self.assertEqual(summary['nativeResourceObservers']['observedManaDebited'],7)
        self.assertEqual(summary['resources']['playerLife']['delta'],1)
        self.assertEqual(summary['resources']['dummyLife']['delta'],None)
        self.assertEqual(before,json.dumps(t))
        del t['snapshots'][0]['events'][0]['crit']
        self.assertEqual(w.summarize_trace(t)['nativeHits']['hit']['unknownCriticalCount'],1)
        t['snapshots'][0]['events'][0]['damageDone']='10'
        with self.assertRaises(ValueError):w.summarize_trace(t)

    def test_summary_preserves_native_refusal_error(self):
        t={'schemaVersion':1,'status':'error','error':'unsupported body action','execution':{'backend':'unit-fixture','fullGameParity':False},'assertions':[],'snapshots':[]}
        summary=w.summarize_trace(t)
        self.assertEqual(summary['error'],'unsupported body action')
        self.assertEqual(summary['status'],'error')
        self.assertIsNone(summary['activeProjectilesAtEnd'])
        self.assertIsNone(summary['nativeResourceObservers'])

    def test_malformed_event_or_projectile_arrays_fail_closed(self):
        for field,bad in [('events',None),('events',[None]),('events',[{}]),('events',{}),('projectiles',None),('projectiles',[3])]:
            t=trace();t['snapshots'][0][field]=bad
            with self.assertRaises(ValueError):w.summarize_trace(t)

    def test_exhaustion_preview_uses_actual_recorded_clock(self):
        t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],generatedBuffTicks=599,generatedItemExhaustion=[{'itemId':'honey','remainingTicks':1799}],moveSpeed=1.1,lifeRegen=1)
        t['coverage']={'wholeItemValidated':False,'untestedBindings':[{'input':'alternate_use','status':'unsupported'}]};t['scene']={'worldId':12,'currentWorldSource':True}
        self.assertEqual(w.summarize_trace(t)['coverage'],t['coverage']);self.assertEqual(w.summarize_trace(t)['sceneIdentity']['worldId'],12)
        before=json.dumps(t);svg=w.frame_svg(w.validate_trace(t),0)
        self.assertIn('item exhaustion max 1799',svg);self.assertIn('life regen 1',svg)
        self.assertEqual(before,json.dumps(t))
        t['snapshots'][0]['player']['generatedItemExhaustion'][0]['remainingTicks']=-1
        with self.assertRaises(ValueError):w.validate_trace(t)

    def test_timeline_uses_recorded_samples_and_keeps_failure_visible(self):
        t=trace()
        for frame in t['snapshots']:
            frame['player']=dict(frame['player'],mana=200,generatedBuffTicks=599-frame['tick'],generatedItemExhaustion=[{'remainingTicks':1800-frame['tick']}])
        t['snapshots'][0]['events']=[{'kind':'input','input':'primary'}]
        before=json.dumps(t);svg=w.timeline_svg(t)
        self.assertIn('Status: failed',svg);self.assertIn('primary@0',svg);self.assertIn('Input attempts (not proof effect accepted)',svg)
        self.assertIn('1800',svg);self.assertIn('599',svg);self.assertEqual(before,json.dumps(t))
        del t['snapshots'][1]['player']['generatedBuffTicks']
        with self.assertRaises(ValueError):w.timeline_svg(t)

    def test_render_preserves_input_and_marks_replay(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.json';path.write_text(json.dumps(trace()));before=path.read_bytes()
            out=Path(d)/'review';r=w.render(path,out)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(r['frames'],3)
            page=(out/'replay.html').read_text()
            self.assertIn('NOT Terraria rendering',page)
            self.assertNotIn('</script><script>alert(1)</script>',page)
            self.assertNotIn('<unsafe>',page)
            self.assertEqual(json.loads((out/'telemetry.json').read_text()),trace())
            self.assertIn('failed',page)
    def test_equipment_and_ammo_labels_use_recorded_state(self):
        t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],maxMana=240,manaCost=.95,defense=0,armor=[{'placement':'functional','slot':3}],inventory=[{'slot':54,'nativeType':40,'stack':2}])
        svg=w.frame_svg(w.validate_trace(t),0)
        for text in ['max mana 240','mana cost 0.950','functional:3','slot 54: native 40 × 2']:
            self.assertIn(text,svg)
    def test_contact_overlay_is_observed_query_not_inferred_hit(self):
        t=trace();t['execution']['clientGraphics']={'nativeClientBranch':True};t['snapshots'][0]['events']=[{'kind':'item_contact_query','x':123,'y':234,'width':45,'height':67}]
        t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],itemPose={'x':15,'y':25,'rotation':0})
        svg=w.frame_svg(w.validate_trace(t),0)
        self.assertIn('x="123" y="234" width="45" height="67"',svg)
        self.assertIn('native contact query (not hit)',svg)
        self.assertIn('cx="15" cy="25"',svg)
        t['snapshots'][0]['events']=[]
        self.assertNotIn('native contact query (not hit)',w.frame_svg(w.validate_trace(t),0))
    def test_build_provenance_detects_copied_asset_changes(self):
        with tempfile.TemporaryDirectory() as d:
            dll=Path(d)/'unit-test-not-real.dll';dll.write_bytes(b'unit-fixture')
            asset=Path(d)/'native-assets'/'proxy.png';asset.parent.mkdir();asset.write_bytes(b'first-unit-fixture')
            before=w.build_state(dll);asset.write_bytes(b'changed-unit-fixture')
            self.assertNotEqual(before,w.build_state(dll))
            asset.unlink();self.assertNotEqual(before,w.build_state(dll))
    def test_malformed_contact_pose_or_rectangle_is_not_silently_hidden(self):
        t=trace();t['snapshots'][0]['events']=[{'kind':'item_contact_query','x':1,'y':2,'width':-4,'height':5}]
        with self.assertRaises(ValueError):w.validate_trace(t)
        t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],itemPose={'x':1,'y':2,'rotation':None})
        with self.assertRaises(ValueError):w.validate_trace(t)
    def test_hybrid_review_separates_recorded_budgets_from_critical_hit_damage(self):
        t=trace();t['execution']['clientGraphics']={'nativeClientBranch':True,'phaseFlags':{'Projectile.Update.dedServ':False}}
        t['snapshots'][0]['projectiles']=[dict(t['snapshots'][0]['projectiles'][0],id=i,entityId='child',damage=4,active=False) for i in range(5)]
        t['snapshots'][0]['events']=[{'kind':'item_hit','damageDone':17,'crit':False},{'kind':'hit','damageDone':10,'crit':True}]
        before=json.dumps(t);svg=w.frame_svg(w.validate_trace(t),0)
        self.assertIn('Recorded projectiles',svg);self.assertIn('dmg 4',svg)
        self.assertIn('native item damage 17 · projectile damage 10 · critical hits 1',svg)
        self.assertEqual(before,json.dumps(t))
    def test_rejects_nonfinite_and_bad_dimensions(self):
        for bad in [float('inf'),float('nan'),'1',True]:
            t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],x=bad)
            with self.assertRaises(ValueError):w.validate_trace(t)
        t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],width=-1)
        with self.assertRaises(ValueError):w.validate_trace(t)
        for field,value in [('vx',float('inf')),('vy',None),('rotation',True),('nonFinite','false')]:
            t=trace();t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],**{field:value})
            with self.assertRaises(ValueError):w.validate_trace(t)
        t=trace();t['status']='passed';t['assertions'][0]['status']='passed'
        t['snapshots'][0]['player']=dict(t['snapshots'][0]['player'],nonFinite=True)
        with self.assertRaises(ValueError):w.validate_trace(t)
    def test_rejects_unordered_and_provenance_free(self):
        t=trace();t['snapshots'].reverse()
        with self.assertRaises(ValueError):w.validate_trace(t)
        t=trace();del t['execution']
        with self.assertRaises(ValueError):w.validate_trace(t)
    def test_empty_native_run_has_no_visual_success(self):
        with tempfile.TemporaryDirectory() as d:
            t=trace();t['snapshots']=[];p=Path(d)/'trace.json';p.write_text(json.dumps(t))
            with self.assertRaises(ValueError):w.render(p,Path(d)/'review')
    def test_svg_uses_exact_recorded_position(self):
        svg=w.frame_svg(w.validate_trace(trace()),2)
        self.assertIn('x="24"',svg)
        self.assertIn('&lt;unsafe&gt;',svg)
    def test_native_nonfinite_failure_remains_inspectable_without_fake_coordinates(self):
        t=trace();t['status']='failed';p=t['snapshots'][-1]['projectiles'][0]
        p.update(x=None,y=None,vx=None,vy=None,nonFinite=True)
        w.validate_trace(t)
        svg=w.frame_svg(t,2)
        self.assertIn('NATIVE INVALID STATE',svg)
        self.assertNotIn('x="None"',svg)
        self.assertIsNone(t['snapshots'][-1]['projectiles'][0]['x'])
        t['status']='passed'
        with self.assertRaises(ValueError):w.validate_trace(t)
    def test_invalid_player_geometry_is_not_drawn_at_invented_origin(self):
        t=trace();t['snapshots'][-1]['player']=dict(t['snapshots'][-1]['player'],x=None,y=None,nonFinite=True,aimX=100,aimY=200)
        w.validate_trace(t);svg=w.frame_svg(t,2)
        self.assertIn('NATIVE INVALID STATE',svg)
        self.assertNotIn('x1="None"',svg)
        self.assertNotIn('stroke-dasharray',svg)
    def test_valid_json_truncation_cannot_keep_pass_status(self):
        t=trace();t['status']='passed';t['assertions'][0]['status']='passed'
        w.validate_trace(t)
        t['snapshots'].pop()
        with self.assertRaises(ValueError):w.validate_trace(t)
        t=trace();t['status']='passed';t['assertions']=[]
        with self.assertRaises(ValueError):w.validate_trace(t)
    def test_cli_missing_native_fails_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{"bad":NaN}')
            run=subprocess.run([sys.executable,str(Path(w.__file__)),'render',str(p),'--out',str(Path(d)/'out')],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('Non-finite',run.stderr)

if __name__=='__main__':unittest.main()
