"""Camera-invariant gameplay comparisons for the native VFX verifier."""
import copy
import unittest
import json
import tempfile
from pathlib import Path

from verify_vfx import gameplay_snapshots_equal, prepare_captured_fixture, expected_refusal, REFUSAL_CAUSES, particle_snapshots_equal


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


    def test_archived_fixture_projection_preserves_source_and_exact_held_visibility(self):
        original = {"gameplay": {"releaseTiming": ""},
                    "runtimeProgram": {"itemUse": {"releaseTiming": "immediate", "hideUseGraphic": False}},
                    "vfxManifest": {"slots": [{"rendererKind": "libraryParticle", "event": "on_hit"}]}}
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "archived.json"
            source.write_text(json.dumps(original))
            before = source.read_bytes()
            target = prepare_captured_fixture(source, Path(root) / "current")
            expected = copy.deepcopy(original)
            expected["gameplay"].pop("releaseTiming")
            expected["runtimeProgram"]["itemUse"].pop("releaseTiming")
            expected["runtimeProgram"]["itemUse"]["hideUseGraphic"] = True
            self.assertEqual(expected, json.loads(target.read_text()))
            self.assertEqual(before, source.read_bytes())
            receipt = json.loads(target.with_suffix(".projection.json").read_text())
            self.assertEqual({"gameplay.releaseTiming": "", "runtimeProgram.itemUse.releaseTiming": "immediate"},
                             receipt["removedRetiredFields"])
            self.assertFalse(receipt["visibilityProjection"]["hideUseGraphicBefore"])
            self.assertTrue(receipt["visibilityProjection"]["hideUseGraphicAfter"])
            blank = copy.deepcopy(original)
            blank["runtimeProgram"]["itemUse"]["releaseTiming"] = ""
            source.write_text(json.dumps(blank))
            unchanged = prepare_captured_fixture(source, Path(root) / "blank")
            self.assertFalse(json.loads(unchanged.read_text())["runtimeProgram"]["itemUse"]["hideUseGraphic"])
            for value in ("delayed", "hidden", None, 1):
                invalid = copy.deepcopy(original)
                invalid["runtimeProgram"]["itemUse"]["releaseTiming"] = value
                source.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    prepare_captured_fixture(source, Path(root) / "rejected")
                self.assertFalse((Path(root) / "rejected").exists())

    def test_negative_control_cannot_pass_an_unrelated_admission_failure(self):
        for name, cause in REFUSAL_CAUSES.items():
            with self.subTest(name=name):
                good = {"status": "error", "error": "System.Exception: " + cause, "snapshots": []}
                self.assertTrue(expected_refusal(name, good))
                bad = dict(good, error="Item rejected: releaseTiming could not be mapped")
                self.assertFalse(expected_refusal(name, bad))
                self.assertFalse(expected_refusal(name, dict(good, snapshots=[{"tick": 0}])))
                self.assertFalse(expected_refusal(name, dict(good, nativeRender={"frames": [{"tick": 0}]})))
                self.assertFalse(expected_refusal(name, dict(good, status="passed")))


    def test_particle_comparison_ignores_only_camera_scene_telemetry(self):
        original = [{"tick": 12, "particleCount": 5, "records": [{"age": 1}],
                     "lightingScene": {"zoom": 4, "player": {"screenLeft": -20}}}]
        moved = copy.deepcopy(original)
        moved[0]["lightingScene"] = {"zoom": 1, "player": {"screenLeft": 10}}
        self.assertTrue(particle_snapshots_equal(original, moved))
        for key, value in (("tick", 13), ("particleCount", 4), ("records", [{"age": 2}]), ("records", [{"age": 1, "lightingScene": {"changed": True}}]), ("newState", 1)):
            wrong = copy.deepcopy(moved)
            wrong[0][key] = value
            self.assertFalse(particle_snapshots_equal(original, wrong))
        for invalid in (None, [], [{}], [None]):
            self.assertFalse(particle_snapshots_equal(original, invalid))
        self.assertEqual(4, original[0]["lightingScene"]["zoom"])


if __name__ == '__main__':
    unittest.main()
