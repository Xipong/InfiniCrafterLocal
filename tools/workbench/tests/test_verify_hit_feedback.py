"""Synthetic reader controls, not native draw or gameplay evidence."""
import copy
import unittest
from python.verify_hit_feedback import hit_effect_records, hit_effect_slots


class HitFeedbackReaderTests(unittest.TestCase):
    def test_current_material_and_shape_records_are_read_without_mutation(self):
        rows = [dict(records=[dict(renderer='spriteElement', texturePath='/art/hit.png', started=True, particleCount=1)],
                     shapes=[dict(kind='arc', attachment='world', rotationFrame='world', durationTicks=14)])]
        before = copy.deepcopy(rows)
        sprite, ring = hit_effect_records(rows, 'hit.png')
        self.assertEqual((len(sprite), len(ring)), (1, 1))
        self.assertEqual(rows, before)
        self.assertEqual(hit_effect_records(rows, 'other.png')[0], [])
        for key, value in [('renderer', 'libraryParticle'), ('started', False), ('particleCount', 0)]:
            invalid = copy.deepcopy(rows); invalid[0]['records'][0][key] = value
            self.assertEqual(hit_effect_records(invalid, 'hit.png')[0], [])
        for key, value in [('kind', 'sector'), ('attachment', 'source'), ('rotationFrame', 'source'), ('durationTicks', 1)]:
            invalid = copy.deepcopy(rows); invalid[0]['shapes'][0][key] = value
            self.assertEqual(hit_effect_records(invalid, 'hit.png')[1], [])
        self.assertEqual(hit_effect_records([], 'hit.png'), ([], []))

    def test_synthetic_current_slots_are_fresh_and_do_not_share_profile_objects(self):
        slots = hit_effect_slots('probe', 'hit')
        self.assertEqual([slot['rendererKind'] for slot in slots], ['spriteElement', 'shape'])
        self.assertTrue(all(slot['entityId'] == 'probe' and slot['event'] == 'on_hit' for slot in slots))
        slots[0]['element']['widthProfile']['start'] = 0
        self.assertEqual(slots[0]['element']['heightProfile']['start'], 1)
        self.assertEqual(hit_effect_slots('probe', 'hit')[0]['element']['widthProfile']['start'], 1)


if __name__ == '__main__':
    unittest.main()
