"""Probe CLI preparation and orchestration; synthetic items are not native evidence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import campaign
import probe
import workbench as w


def arguments(*values):
    parser = argparse.ArgumentParser()
    probe.add_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(["probe", *map(str, values)])


class ProbeTests(unittest.TestCase):
    def test_public_cli_plans_matrix_without_installation_or_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "item.json"
            item.write_text('{"syntheticTestOnly":true}')
            proc = subprocess.run([sys.executable, "-m", "toolbox", "workbench", "probe",
                                   "--item", str(item), "--vanilla-item", "WoodenBoomerang",
                                   "--input", "primary", "alt", "--plan", "--out", str(root / "absent")],
                                  cwd=w.ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan = json.loads(proc.stdout)
            self.assertEqual(len(plan["cases"]), 4)
            self.assertEqual(list(root.iterdir()), [item])
            self.assertFalse(plan["wholeItemCertified"])
            self.assertEqual(plan["scenes"]["primary"]["assertions"], [{"kind": "no_nonfinite"}])
            self.assertEqual(plan["scenes"]["alt"]["actions"], [{"tick": 0, "kind": "alt"}, {"tick": 1, "kind": "release"}])

    def test_held_and_repeated_inputs_are_explicit_bounded_native_actions(self):
        held = probe.plan_probe(arguments("--vanilla-item", "284", "--input", "alt", "--hold", "90"))
        self.assertEqual(held["scenes"]["alt"]["actions"], [{"tick": 0, "kind": "alt"}, {"tick": 90, "kind": "release"}])
        repeated = probe.plan_probe(arguments("--vanilla-item", "284", "--start", "2", "--hold", "4", "--repeat", "30"))
        actions = repeated["scenes"]["primary"]["actions"]
        self.assertEqual([a["tick"] for a in actions if a["kind"] == "primary"], [2, 32, 62, 92, 122, 152])
        self.assertEqual([a["tick"] for a in actions if a["kind"] == "release"], [6, 36, 66, 96, 126, 156])
        idle = probe.plan_probe(arguments("--vanilla-item", "284", "--input", "idle"))
        self.assertEqual(idle["scenes"]["idle"]["actions"], [])
        equipped = probe.plan_probe(arguments("--vanilla-item", "284", "--input", "equip"))
        self.assertEqual(equipped["scenes"]["equip"]["actions"], [{"tick": 0, "kind": "equip"}])

    def test_focused_scene_needs_no_python_or_item_rewrite(self):
        args = arguments("--vanilla-item", "284", "--input", "alt", "--ticks", "180", "--hold", "120",
                         "--set", "tiles.0.tileY=44", "--set", "dummy.x=840",
                         "--set", 'inventory=[{"slot":54,"itemId":75,"stack":10}]',
                         "--action", '{"kind":"aim","tick":0,"x":850,"y":700}',
                         "--assert", "dummy_damaged", "--assert", '{"kind":"mana_debited","value":14}')
        scene = probe.plan_probe(args)["scenes"]["alt"]
        self.assertEqual(scene["tiles"][0]["tileY"], 44)
        self.assertEqual(scene["dummy"]["x"], 840)
        self.assertEqual(scene["inventory"][0]["itemId"], 75)
        self.assertEqual([a["kind"] for a in scene["actions"]], ["alt", "aim", "release"])
        self.assertEqual(scene["assertions"], [{"kind": "no_nonfinite"}, {"kind": "dummy_damaged"},
                                                {"kind": "mana_debited", "value": 14}])
        # Each plan starts from the original neutral template.
        self.assertEqual(probe.plan_probe(arguments("--vanilla-item", "284"))["scenes"]["primary"]["tiles"][0]["tileY"], 47)

    def test_prepare_is_portable_and_preserves_exact_item_bytes_and_duplicate_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = []
            for folder in ("one", "two"):
                item = root / folder / "предмет.json"
                item.parent.mkdir()
                item.write_bytes(json.dumps({"syntheticTestOnly": True, "name": "Item from " + folder}).encode() + b"\n")
                items.append(item)
            args = arguments("--item", *items, "--input", "primary", "alt", "--prepare", "--out", root / "original")
            with patch.object(w, "native_executable", side_effect=AssertionError("must not execute")), \
                 patch.object(w, "doctor", side_effect=AssertionError("must not require dependencies")):
                result = probe.execute_probe(args)
            self.assertEqual(result["nativeStatus"], "notRun")
            self.assertNotIn("passed", result)
            for i, item in enumerate(items, 1):
                self.assertEqual((root / "original/inputs" / f"item-{i:03d}.json").read_bytes(), item.read_bytes())
            shutil.move(root / "original", root / "moved")
            for item in items:
                item.unlink()
            plan = campaign.plan_suite(root / "moved/suite.json")
            self.assertEqual(len(plan["cases"]), 4)
            self.assertEqual(len({c["name"] for c in plan["cases"]}), 4)
            self.assertTrue(all(Path(c["item"]).is_relative_to(root / "moved") for c in plan["cases"]))
            before = (root / "moved/suite.json").read_bytes()
            with self.assertRaises(ValueError):
                probe.prepare_probe(probe.plan_probe(arguments("--vanilla-item", "284")), root / "moved")
            self.assertEqual(before, (root / "moved/suite.json").read_bytes())
            probe_plan = json.loads((root / "moved/probe-plan.json").read_text())
            self.assertEqual([c["displayName"] for c in probe_plan["cases"]],
                             ["Item from one", "Item from one", "Item from two", "Item from two"])

    def test_invalid_bounds_and_ambiguous_options_fail_before_outputs(self):
        invalid = [(), ("--ticks", "0"), ("--ticks", "14401"), ("--hold", "0"), ("--hold", "180"),
                   ("--repeat", "1"), ("--repeat", "10", "--hold", "10"), ("--repeat", "179"),
                   ("--start", "180"), ("--timeout", "0"), ("--input", "idle", "--hold", "2"),
                   ("--input", "primary", "primary"), ("--set", "actions=[]"), ("--set", "assertions=[]"),
                   ("--set", "tiles.9.tileY=44"), ("--set", "foo.bar=1"), ("--set", "dummy.x=NaN"),
                   ("--set", "dummy.x=1e999"), ("--set", "dummy.x=bareword"),
                   ("--assert", "[]"), ("--assert", '{"kind":"mana_equals","value":NaN}'),
                   ("--action", '{"kind":"release","tick":180}'), ("--action", '{"kind":"release","tick":true}'),
                   ("--expect", '{"status":"failed"}'), ("--expect", '{"status":"error"}'),
                   ("--mode", "client_vfx"), ("--item-boundary", "local_cache"),
                   ("--ticks", "600", "--repeat", "2")]
        for extra in invalid:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                base = [] if not extra else ["--vanilla-item", "284"]
                args = arguments(*base, *extra, "--prepare", "--out", root / "absent")
                with self.assertRaises((ValueError, OSError)):
                    probe.execute_probe(args)
                self.assertEqual(list(root.iterdir()), [])

    def test_cache_boundary_and_exact_expected_failures_are_forwarded(self):
        with tempfile.TemporaryDirectory() as directory:
            item = Path(directory) / "item.json"
            item.write_text('{"syntheticTestOnly":true}')
            args = arguments("--item", item, "--item-boundary", "local_cache", "--assert", "dummy_damaged",
                             "--expect", '{"status":"failed","failedAssertions":["dummy_damaged"]}',
                             "--out", Path(directory) / "out")
            with patch.object(w, "doctor", return_value={"ready": True}), \
                 patch.object(probe, "run_suite", return_value={"passed": False, "cases": [{"name": "001-item-primary", "expectationMatched": False}]}) as run:
                data = probe.execute_probe(args)
            self.assertFalse(data["passed"])
            self.assertEqual(run.call_count, 1)
            manifest, output, no_build = run.call_args.args
            self.assertEqual(output, args.out / "runs")
            self.assertFalse(no_build)
            plan = campaign.plan_suite(manifest)
            self.assertEqual(plan["cases"][0]["itemBoundary"], "local_cache")
            self.assertEqual(plan["cases"][0]["expect"]["failedAssertions"], ["dummy_damaged"])
            self.assertEqual(data["cases"][0]["item"], str(item))
            self.assertEqual(data["cases"][0]["displayName"], "item.json")
            self.assertEqual(json.loads((args.out / "probe-result.json").read_text()), data)

    def test_changed_source_and_missing_dependencies_do_not_leave_partial_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = root / "item.json"
            item.write_text('{"syntheticTestOnly":true}')
            args = arguments("--item", item, "--out", root / "out")
            plan = probe.plan_probe(args)
            item.write_text('{"syntheticTestOnly":false}')
            with self.assertRaisesRegex(ValueError, "changed after planning"):
                probe.prepare_probe(plan, args.out)
            self.assertFalse(args.out.exists())
            with patch.object(w, "doctor", return_value={"ready": False}):
                with self.assertRaisesRegex(RuntimeError, "prerequisites unavailable"):
                    probe.execute_probe(args)
            self.assertFalse(args.out.exists())


if __name__ == "__main__":
    unittest.main()
