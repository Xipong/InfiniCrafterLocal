"""Synthetic observer/matrix controls, not native gameplay or balance certification."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import performance_review as p


def sample():
    actor = {'x': 0, 'y': 0, 'width': 20, 'height': 42}
    frames=[]
    for tick in (-1, 0, 1):
        target=dict(actor, slot=0, nativeType=3, life=100 if tick<1 else 87, active=True,
                    targetState={'defense': 8, 'nativeBuffs': [{'id': 20, 'ticks': 50}] if tick>=0 else []})
        player=dict(actor, mana=100 if tick<1 else 94, inventory=[{'slot': 54, 'nativeType': 97, 'stack': 10 if tick<1 else 9}], controlUseItem=tick==0, channel=False)
        events=[] if tick<0 else [{'kind':'native_item_time_applied'}]
        if tick==1: events += [{'kind':'hit','damageDone':10,'npcId':0,'crit':True}, {'kind':'native_direct_npc_damage','lifeLost':3,'npcId':0}, {'kind':'native_mana_payment','spent':10}]
        frames.append({'tick':tick,'player':player,'dummy':target,'events':events})
    return {'schemaVersion':1,'status':'passed','execution':{'backend':'synthetic-only'},
            'timeline':{'requestedTicks':2,'completedTicks':2,'complete':True},
            'assertions':[{'status':'passed','name':'no_nonfinite'}],'snapshots':frames}


class PerformanceTests(unittest.TestCase):
    def test_channels_uptime_debits_and_real_cadence_not_arithmetic(self):
        result=p.measure(sample())
        self.assertEqual(result['observedTargetLifeLost'],13)
        self.assertEqual(result['channels']['hit']['damage'],10)
        self.assertEqual(result['channels']['native_direct_npc_damage']['damage'],3)
        self.assertEqual(result['statusUptime'][0]['observedTicks'],2)
        self.assertEqual(result['resources']['observedManaPayments'],10)
        self.assertEqual(result['resources']['finalMana'],94)  # Net is not cost.
        self.assertEqual(result['resources']['inventory'][0]['netStackDebit'],1)
        self.assertEqual(result['cadence']['intervalTicks'],[1])

    def test_before_input_samples_do_not_double_count_uptime(self):
        trace=sample(); before=copy.deepcopy(trace['snapshots'][1]); before['phase']='after_input_before_update';before['events']=[]
        trace['snapshots'].insert(1,before)
        self.assertEqual(p.measure(trace)['statusUptime'][0]['observedTicks'],2)

    def test_missing_failed_or_truncated_is_not_zero_damage(self):
        trace=sample();trace['snapshots'][0]['dummy'].pop('targetState')
        with self.assertRaisesRegex(ValueError,'target state'): p.measure(trace)
        trace=sample();trace['snapshots'].pop()
        with self.assertRaises(ValueError): p.measure(trace)
        trace={'schemaVersion':1,'status':'error','execution':{},'snapshots':[],'assertions':[],'error':'Not admitted'}
        self.assertEqual(p.measure(trace)['status'],'notMeasured')

    def test_exact_parents_no_name_or_numeric_fallback(self):
        item={'recipeMeta':{'parentIdentities':['item:Terraria/WoodenBoomerang:55','generated:missing','item:Other/Foo:1']}}
        rows=p.parent_candidates(item)
        self.assertEqual(rows[0]['vanillaItem'],'WoodenBoomerang')
        self.assertEqual(rows[1]['status'],'notRun');self.assertEqual(rows[2]['status'],'notRun')
        with self.assertRaises(ValueError): p.parent_candidates({'parentA':'Sword'})

    def test_wrong_generated_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'item.json';path.write_text('{"id":"wrong"}')
            with self.assertRaisesRegex(ValueError,'identity mismatch'):
                p.parent_candidates({'recipeMeta':{'parentIdentities':['generated:expected']}},{'generated:expected':str(path)})

    def test_three_native_scenes_preserve_player_rng_inputs_and_armor(self):
        base={'ticks':90,'seed':42,'playerUpdate':'full','player':{'x':800,'y':700,'mana':200},
              'dummy':{'x':840,'y':700,'defense':12},'inventory':[{'slot':54,'itemId':97,'stack':99}],
              'actions':[{'tick':0,'kind':'primary'},{'tick':60,'kind':'release'}]}
        rows=dict(p.scenarios(base));self.assertEqual(set(rows),{'lone','moving','grouped'})
        for scene in rows.values():
            for key in ('ticks','seed','player','inventory','actions'): self.assertEqual(scene[key],base[key])
            self.assertEqual(scene['dummy']['defense'],12)
        self.assertEqual(rows['moving']['dummy']['vx'],.5)
        self.assertEqual(len(rows['grouped']['hostiles']),2)
        for target in rows['grouped']['hostiles']:self.assertEqual(target['defense'],12)
        self.assertNotIn('nativeType',base['dummy'])

    def test_default_geometry_assets_belong_to_complete_pinned_source(self):
        root=Path(__file__).parent
        manifest=json.loads((root/'performance-assets-manifest.json').read_text())
        index=json.loads((root/'vanilla-item-assets.json').read_text())
        self.assertEqual(len(manifest['files']),12)
        self.assertEqual(index['communityCommit'],manifest['commit'])
        for row in manifest['files']:
            item_id=Path(row['path']).stem.removeprefix('Item_')
            self.assertEqual(index['items'][item_id][1],row['bytes'])
        self.assertIn('24',index['items'])

    def test_native_identity_requires_both_name_and_id(self):
        c={'vanillaItem':'BladeofGrass','recordedId':190}
        self.assertTrue(p.native_identity_matches(c,{'input':{'nativeItemName':'BladeofGrass','nativeItemId':190}}))
        self.assertFalse(p.native_identity_matches(c,{'input':{'nativeItemName':'BladeofGrass','nativeItemId':46}}))
        self.assertFalse(p.native_identity_matches(c,{'input':{'nativeItemName':'LightsBane','nativeItemId':190}}))

    def test_comparability_observes_context_and_refusals(self):
        row={'scene':'lone','status':'measured','executionMode':'client_vfx','mechanicalSceneSha256':'same',
             'rng':{'seed':1,'resetBoundary':'beforeGameplay'},'initialPlayer':{'x':800},'initialAmmo':[], 'ammoAvailableAtStart':True}
        self.assertEqual(p.assess_comparisons([row,copy.deepcopy(row)],['lone'])[0]['status'],'matched')
        for key,value in [('executionMode','full'),('mechanicalSceneSha256','different'),('rng',None),('initialPlayer',{'x':801}),('initialAmmo',[{'slot':1}]),('ammoAvailableAtStart',False),('targetDied',True),('status','notRun')]:
            with self.subTest(key=key):
                changed=copy.deepcopy(row);changed[key]=value
                self.assertEqual(p.assess_comparisons([row,changed],['lone'])[0]['status'],'limited')

    def test_seed_and_existing_secondary_targets_require_explicit_control(self):
        with self.assertRaisesRegex(ValueError,'seed'): list(p.scenarios({'ticks':90,'playerUpdate':'full'}))
        with self.assertRaisesRegex(ValueError,'secondary'): list(p.scenarios({'seed':1,'ticks':90,'playerUpdate':'full','hostiles':[{}]}))

    def test_repeated_press_release_schedule_is_explicit_and_shared(self):
        base={'ticks':100,'actions':[{'tick':0,'kind':'aim','x':10,'y':20}, {'tick':0,'kind':'primary'}, {'tick':90,'kind':'release'}]}
        r=p.repeated_schedule(base,30,5)
        self.assertEqual([a['tick'] for a in r['actions'] if a['kind']=='primary'],[0,30,60,90])
        self.assertEqual([a['tick'] for a in r['actions'] if a['kind']=='release'],[5,35,65,95])
        self.assertEqual(r['actions'][0],base['actions'][0])
        self.assertEqual(len(base['actions']),3)
        for every,hold in [(None,None),(30,30),(0,0),(5,-1)]:
            with self.assertRaises(ValueError): p.repeated_schedule(base,every,hold)
        with self.assertRaisesRegex(ValueError,'256'): p.repeated_schedule({'ticks':600},2,1)


    def test_requested_controls_are_not_forged_parents(self):
        item={'recipeMeta':{'parentIdentities':['item:Terraria/Boomstick:964']}}
        before=copy.deepcopy(item)
        parents=p.parent_candidates(item)
        controls=p.requested_controls(['item:Terraria/Minishark:98','item:Terraria/Musket:96','item:Terraria/Minishark:98'])
        self.assertEqual(item,before)
        self.assertEqual(parents[0]['role'],'authoredParent')
        self.assertEqual(len(controls),2)
        self.assertTrue(all(row['role']=='requestedControl' for row in controls))
        self.assertEqual([row['recordedId'] for row in controls],[98,96])
        for bad in ['Minishark','item:Terraria/Minishark:0','generated:fake']:
            with self.assertRaises(ValueError):p.requested_controls([bad])

if __name__=='__main__': unittest.main()
