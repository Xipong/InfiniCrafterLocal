"""Camera-invariant gameplay comparisons for the native VFX verifier."""
import copy
import unittest

from verify_vfx import gameplay_snapshots_equal


class VerifyVfxSnapshotTests(unittest.TestCase):
    def test_only_top_level_native_dust_is_ignored_without_mutation(self):
        original = [{'tick': 12, 'nativeActiveDust': 5, 'dummy': {'life': 90},
                     'events': [{'kind': 'hit', 'damageDone': 10}],
                     'projectiles': [{'x': 12, 'nativeActiveDust': 3}]}]
        off_camera = copy.deepcopy(original)
        off_camera[0]['nativeActiveDust'] = 0
        saved_original, saved_off_camera = copy.deepcopy(original), copy.deepcopy(off_camera)
        self.assertTrue(gameplay_snapshots_equal(original, off_camera))
        self.assertEqual(original, saved_original)
        self.assertEqual(off_camera, saved_off_camera)

        for change in (
            lambda s: s[0]['dummy'].__setitem__('life', 89),
            lambda s: s[0]['events'][0].__setitem__('damageDone', 11),
            lambda s: s[0]['projectiles'][0].__setitem__('nativeActiveDust', 4),
            lambda s: s[0].__setitem__('tick', 13),
            lambda s: s[0].__setitem__('newTelemetry', 1),
        ):
            candidate = copy.deepcopy(off_camera)
            change(candidate)
            self.assertFalse(gameplay_snapshots_equal(original, candidate))

    def test_missing_or_incomplete_snapshots_are_not_evidence(self):
        snapshot = {'tick': 1, 'nativeActiveDust': 0}
        for left, right in ((None, None), ([], []), ([snapshot], []),
                            ([snapshot], [{'tick': 1}]), ([{}], [{}]),
                            ([None], [None])):
            with self.subTest(left=left, right=right):
                self.assertFalse(gameplay_snapshots_equal(left, right))


if __name__ == '__main__':
    unittest.main()
