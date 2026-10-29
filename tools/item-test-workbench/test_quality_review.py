import copy
import unittest
from quality_review import variants, summarize

class QualityReviewTests(unittest.TestCase):
    def scene(self):
        return dict(playerUpdate='client_vfx',ticks=60,player=dict(x=800,y=700),nativeRender=dict(drawPlayer=True),actions=[dict(tick=0,kind='primary'),dict(tick=1,kind='release'),dict(tick=0,kind='aim',x=1000,y=710)],inventory=[dict(item='Flare',stack=99)],assertions=[dict(kind='spawn_count',value=1)])
    def test_four_explicit_native_scenes_hold_release_and_ammo(self):
        source=self.scene();before=copy.deepcopy(source);cases=list(variants(source,30))
        self.assertEqual(source,before);self.assertEqual(len(cases),4)
        for _,scene in cases:
            self.assertEqual(scene['inventory'],source['inventory'])
            self.assertEqual([a['tick'] for a in scene['actions'] if a['kind']=='release'],[30])
            self.assertEqual(scene['assertions'],[dict(kind='no_nonfinite')])
        self.assertEqual(next(a['x'] for a in cases[2][1]['actions'] if a['kind']=='aim'),620)
    def test_initial_aim_is_explicit_even_without_source_aim(self):
        scene=self.scene();scene['actions']=[a for a in scene['actions'] if a['kind']!='aim']
        for name,s in variants(scene,30):
            aim=next(a for a in s['actions'] if a['kind']=='aim' and a['tick']==0)
            self.assertEqual(aim['x'],1010 if name.startswith('right') else 610)
    def test_equipment_never_invokes_primary(self):
        for _,s in variants(self.scene(),30,True):
            self.assertIn('equip',[a['kind'] for a in s['actions']]);self.assertNotIn('primary',[a['kind'] for a in s['actions']])
    def test_refuse_invalid_hold_or_fake_native(self):
        for hold in (0,60):
            with self.assertRaises(ValueError):list(variants(self.scene(),hold))
        scene=self.scene();scene['playerUpdate']='full'
        with self.assertRaises(ValueError):list(variants(scene,30))
    def test_large_authored_reach_never_becomes_auto_fail_or_pass(self):
        trace=dict(status='passed',nativeRender=dict(frames=[dict(heldGeometry=[dict(gripDistancePx=32)],visualReview=dict(direction=-1,gravityDirection=1,controlUseItem=True,velocity=dict(x=0,y=0)))]))
        result=summarize(trace);self.assertEqual(result['maxObservedGripDistancePx'],32);self.assertEqual(result['visualVerdict'],'review_required')
    def test_noncomposite_diagnostic_is_not_an_authoritative_error(self):
        trace=dict(nativeRender=dict(frames=[dict(heldGeometry=[dict(gripDistancePx=None,diagnosticFrameArmGetterDistancePx=20)])]))
        self.assertIsNone(summarize(trace)['maxObservedGripDistancePx'])
    def test_absent_render_is_not_run_not_visual_pass(self):
        self.assertEqual(summarize({})['nativeStatus'],'notRun');self.assertIsNone(summarize({})['maxObservedGripDistancePx'])

if __name__=='__main__':unittest.main()
