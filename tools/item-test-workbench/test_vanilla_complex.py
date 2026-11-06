"""Scenario definitions exercise original native AI, never an inferred weapon model."""
import unittest
from pathlib import Path
import verify_vanilla_projectiles as verify


class ComplexScenes(unittest.TestCase):
    def test_explicit_lifecycle_and_resources(self):
        rows = {name: (item, scene) for name, item, scene, _, _ in verify.complex_scenes(Path('/verified'))}
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows['eventide'][1]['inventory'][0]['itemId'], 40)
        self.assertEqual(rows['flaming-arrow'][1]['inventory'][0]['itemId'], 41)
        for name in ('nebula', 'prism', 'charged', 'heat-ray'):
            self.assertEqual(rows[name][1]['inventory'], [])
        self.assertGreater(rows['charged'][1]['actions'][-1]['tick'], 180)
        self.assertGreater(rows['prism'][1]['actions'][-1]['tick'], 120)
        self.assertEqual(rows['prism-mana'][1]['inventory'], [dict(slot=1, itemId=189, stack=2)])
        self.assertIn(dict(kind='quick_mana', tick=140), rows['prism-mana'][1]['actions'])
        for name in ('prism', 'prism-mana', 'heat-ray'):
            self.assertEqual(rows[name][1]['worldWidthTiles'], 400)
            self.assertEqual(rows[name][1]['player']['x'], 800)
        self.assertGreater(rows['heat-ray'][1]['actions'][0]['x'] - 800, 1500)
        for _, scene in rows.values():
            self.assertEqual(scene['vanillaAssetRoot'], '/verified')
            self.assertTrue(scene['nativeRender']['drawVanillaProjectiles'])
            self.assertTrue(scene['nativeRender']['drawNativeDust'])
            self.assertLess(scene['actions'][-1]['tick'], scene['ticks'])
            kinds = {x['kind'] for x in scene['assertions']}
            self.assertEqual(kinds, {'native_projectile_seen', 'hit_count_at_least', 'no_nonfinite'})


class NativeTraceBounds(unittest.TestCase):
    def test_output_bound_does_not_relax_item_input_limit(self):
        import tempfile
        from unittest.mock import patch
        import workbench as w
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native.json'
            path.write_text('{"a":"abcdefghijklmnop"}')
            with patch.object(w, 'LIMIT', 16), patch.object(w, 'NATIVE_TRACE_LIMIT', 32):
                with self.assertRaisesRegex(ValueError, 'exceeds 16'):
                    w.read_json(path)
                self.assertEqual(w.read_native_json(path), {'a': 'abcdefghijklmnop'})
                path.write_text('{"a":"' + 'x'*40 + '"}')
                with self.assertRaisesRegex(ValueError, 'exceeds 32'):
                    w.read_native_json(path)

    def test_native_nonfinite_is_still_rejected(self):
        import tempfile
        import workbench as w
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'native.json'
            path.write_text('{"a":NaN}')
            with self.assertRaisesRegex(ValueError, 'Non-finite'):
                w.read_native_json(path)

    def test_numeric_overflow_is_rejected_by_both_readers(self):
        import tempfile
        import workbench as w
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'input.json'
            for read in (w.read_json, w.read_native_json):
                for number in ('1e999', '-1e999', '9' * 310 + '.0'):
                    with self.subTest(reader=read.__name__, number=number):
                        path.write_text('{"nested":[{"value":' + number + '}]}')
                        with self.assertRaisesRegex(ValueError, 'Non-finite'):
                            read(path)
                path.write_text('{"values":[1e308,-1e308,1e-999,0.5]}')
                self.assertEqual(read(path), {'values': [1e308, -1e308, 0.0, 0.5]})
