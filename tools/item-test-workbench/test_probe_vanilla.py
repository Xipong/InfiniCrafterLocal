"""Behavioral checks for preparing native vanilla and generated GIF probes."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest

import campaign
import probe


def arguments(*values):
    parser = argparse.ArgumentParser()
    probe.add_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(["probe", *map(str, values)])


class VanillaGifTests(unittest.TestCase):
    def test_vanilla_capture_prepares_original_draw_and_explicit_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "vanilla-assets"
            assets.mkdir()
            args = arguments("--vanilla-item", "DaedalusStormbow", "--gif", "--vanilla-assets", assets,
                             "--ammo", "40:200", "--aim", "1056", "2220", "--prepare", "--out", root / "run")
            result = probe.execute_probe(args)
            self.assertEqual(result["nativeStatus"], "notRun")
            suite = campaign.plan_suite(root / "run" / "suite.json")
            self.assertEqual(len(suite["cases"]), 1)
            case = suite["cases"][0]
            self.assertEqual(case["vanillaItem"], "DaedalusStormbow")
            self.assertTrue(case["gif"])
            scene = json.loads(Path(case["scenario"]).read_text())
            self.assertEqual(scene["playerUpdate"], "client_vfx")
            self.assertEqual(Path(scene["vanillaAssetRoot"]), assets.resolve())
            self.assertEqual(scene["nativeRender"]["artworkFiles"], [])
            self.assertTrue(scene["nativeRender"]["drawPlayer"])
            self.assertTrue(scene["nativeRender"]["drawVanillaProjectiles"])
            self.assertEqual(scene["inventory"], [{"slot": 54, "itemId": 40, "stack": 200}])
            self.assertIn({"kind": "aim", "tick": 0, "x": 1056, "y": 2220}, scene["actions"])

    def test_mixed_generated_and_vanilla_keep_separate_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "vanilla-assets"
            assets.mkdir()
            image = root / "item.png"
            image.write_bytes(b"published image for planning")
            item = root / "item.json"
            item.write_text(json.dumps({"name": "example", "visual": {"spritePath": str(image)},
                                        "runtimeProgram": {"entities": []}}))
            args = arguments("--item", item, "--vanilla-item", "WoodenSword", "--gif",
                             "--vanilla-assets", assets, "--prepare", "--out", root / "run")
            probe.execute_probe(args)
            suite = campaign.plan_suite(root / "run" / "suite.json")
            self.assertEqual(len(suite["cases"]), 2)
            generated = next(c for c in suite["cases"] if "item" in c)
            vanilla = next(c for c in suite["cases"] if "vanillaItem" in c)
            generated_scene = json.loads(Path(generated["scenario"]).read_text())
            vanilla_scene = json.loads(Path(vanilla["scenario"]).read_text())
            self.assertEqual(generated_scene["nativeRender"]["artworkFiles"], [str(image.resolve())])
            self.assertEqual(vanilla_scene["nativeRender"]["artworkFiles"], [])
            self.assertEqual(Path(vanilla_scene["vanillaAssetRoot"]), assets.resolve())
            self.assertNotIn("vanillaAssetRoot", generated_scene)
            self.assertEqual(Path(generated["item"]).read_bytes(), item.read_bytes())

    def test_vanilla_world_override_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = arguments("--vanilla-item", "WoodenSword", "--gif", "--vanilla-assets", root,
                             "--test-world-id", "12")
            with self.assertRaises(ValueError):
                probe.plan_probe(args)


if __name__ == "__main__":
    unittest.main()
