import unittest
from python.verify_native_fishing import inspect, scene


class NativeFishingEvidenceTests(unittest.TestCase):
    def test_cast_is_not_catch(self):
        trace={'fishing':{'observations':[{'kind':'native_state','tick':0,'bobbers':[{'wet':True,'ai0':0,'ai1':0}], 'inventory':[{'slot':0,'type':2289,'stack':1},{'slot':2,'type':2002,'stack':20}]}]}}
        facts=inspect(trace)
        self.assertTrue(facts['spawned'])
        self.assertTrue(facts['wet'])
        self.assertFalse(facts['bite'])
        self.assertFalse(facts['caught'])

    def test_actual_inventory_and_resource_observations_are_separate(self):
        trace={'fishing':{'observations':[{'kind':'natural_bite_reel_input'}, {'kind':'native_state','tick':30,'bobbers':[{'wet':True,'ai0':1,'ai1':2290}],'inventory':[]}, {'kind':'native_state','bobbers':[], 'inventory':[{'slot':2,'type':2002,'stack':19},{'slot':49,'type':2290,'stack':1}]}]},'resources':{'observedManaDebited':7}}
        facts=inspect(trace)
        self.assertTrue(facts['bite'])
        self.assertEqual([{'slot':49,'type':2290,'stack':1}], facts['caught'])
        self.assertEqual(19,facts['bait'])
        self.assertEqual(7,facts['manaDebited'])

    def test_scene_is_bounded_and_reels_only_after_observed_bite(self):
        value=scene(seed=6)
        self.assertEqual(6,value['seed'])
        self.assertLessEqual(value['ticks'],14400)
        self.assertEqual(['aim','primary','release'],[a['kind'] for a in value['actions']])
        self.assertTrue(value['fishing']['reelOnBite'])
        self.assertEqual(600,value['fishing']['water']['width']*value['fishing']['water']['height'])

if __name__=='__main__':unittest.main()
