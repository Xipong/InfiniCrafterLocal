"""Agent workflow contracts with synthetic saved evidence, never native parity."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import agent_evidence as e
import campaign as c
import workbench as w


def saved_run(root, status="passed", failed=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "item.json").write_text('{"syntheticTestOnly":true}')
    (root / "scenario.json").write_text('{"syntheticTestOnly":true}')
    actor = {"x": 0, "y": 0, "width": 16, "height": 32, "mana": 20, "life": 100}
    trace = {"schemaVersion": 1, "status": status,
             "execution": {"backend": "synthetic-test-only", "fullGameParity": False},
             "timeline": {"requestedTicks": 3, "completedTicks": 3, "complete": True},
             "input": {"source": "generated", "boundary": "GeneratedItemData.FromJson", "seed": 1,
                       "sha256": w.digest(root / "item.json"), "scenarioSha256": w.digest(root / "scenario.json")},
             "assertions": [{"name": name, "request": {"kind": name}, "status": "failed"}
                            for name in (failed or [])] or [{"name": "no_nonfinite", "status": "passed"}],
             "snapshots": [{"tick": i, "player": dict(actor), "dummy": dict(actor, x=80),
                            "events": [], "projectiles": []} for i in range(3)]}
    (root / "native.json").write_text(json.dumps(trace))
    receipt = {"schemaVersion": 2, "source": {"kind": "generated-json"},
               "itemSha256": w.digest(root / "item.json"), "scenarioSha256": w.digest(root / "scenario.json"),
               "traceSha256": w.digest(root / "native.json"), "nativeExitCode": e.NATIVE_EXIT[status],
               "exitCode": e.NATIVE_EXIT[status], "sourceSha256": "synthetic-test-not-real-source"}
    (root / "run.json").write_text(json.dumps(receipt))
    return trace, receipt


def save_trace(root, trace, receipt):
    (root / "native.json").write_text(json.dumps(trace))
    receipt["traceSha256"] = w.digest(root / "native.json")
    (root / "run.json").write_text(json.dumps(receipt))


class AgentEvidenceTests(unittest.TestCase):
    def test_archive_audit_survives_move_and_detects_each_modified_evidence_file(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "original"
            saved_run(root)
            moved = Path(d) / "moved"
            shutil.move(root, moved)
            self.assertEqual(e.report(moved)["integrity"]["status"], "verified")
            for name in ("item.json", "scenario.json", "native.json"):
                with self.subTest(name=name):
                    path = moved / name
                    original = path.read_bytes()
                    path.write_bytes(original + b" ")
                    self.assertEqual(e.report(moved)["integrity"]["status"], "invalid")
                    path.write_bytes(original)
            (moved / "run.json").unlink()
            self.assertEqual(e.report(moved)["integrity"]["status"], "unverified")

    def test_failed_item_stays_failed_and_final_assertion_has_no_invented_tick(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved_run(root, "failed", ["dummy_damaged"])
            data = e.report(root)
            self.assertEqual(data["nativeStatus"], "failed")
            self.assertEqual(data["integrity"]["status"], "verified")
            self.assertIsNone(data["failureContext"]["observedFailureTick"])
            self.assertEqual(data["failureContext"]["contextTicks"], [1, 2])
            self.assertFalse(data["wholeItemCertified"])
            self.assertTrue(c.matches_expectation(data, {"status": "failed", "failedAssertions": ["dummy_damaged"]}, 1))
            for expected, code in [({"status": "failed", "failedAssertions": ["spawned"]}, 1),
                                   ({"status": "failed", "failedAssertions": ["dummy_damaged"]}, 2),
                                   ({"status": "passed", "failedAssertions": []}, 0)]:
                self.assertFalse(c.matches_expectation(data, expected, code))

    def test_unexpected_error_and_extra_failed_assertions_do_not_satisfy_negative_control(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            trace, receipt = saved_run(root, "failed", ["dummy_damaged", "no_nonfinite"])
            data = e.report(root)
            self.assertFalse(c.matches_expectation(data, {"status": "failed", "failedAssertions": ["dummy_damaged"]}, 1))
            trace.update(status="error", error="unexpected runtime crash", snapshots=[], assertions=[])
            receipt.update(nativeExitCode=2, exitCode=2)
            save_trace(root, trace, receipt)
            self.assertFalse(c.matches_expectation(e.report(root), {"status": "error", "failedAssertions": [],
                                   "errorContains": "Unsupported expected lane"}, 2))

    def test_report_does_not_create_fake_pixels_or_overwrite_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "run"
            saved_run(root)
            out = Path(d) / "report"
            with self.assertRaises(ValueError):
                e.export_report(root, out, contact_sheet=True)
            self.assertFalse(out.exists())
            for output in (root, root / "native-frames", root.parent):
                with self.assertRaises(ValueError):
                    e.export_report(root, output)
            data = e.export_report(root, out)
            self.assertEqual(data["vision"]["pixelSource"], "none")
            self.assertEqual(json.loads((out / "report.json").read_text())["nativeStatus"], "passed")
            with self.assertRaises(ValueError):
                e.export_report(root, out)

    def test_real_png_contact_sheet_keeps_source_tick_and_hash(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Optional Pillow not installed")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "run"
            trace, receipt = saved_run(root)
            frames = []
            for i in range(3):
                p = root / f"native-frames/{i}.png"
                p.parent.mkdir(exist_ok=True)
                Image.new("RGBA", (16, 16), (i * 50, 20, 40, 255)).save(p)
                frames.append({"tick": i, "path": f"native-frames/{i}.png", "sha256": w.digest(p), "width": 16, "height": 16})
            trace["nativeRender"] = {"backend": "original_mod_draw_layers", "itemArtworkRendered": False,
                                     "projectileArtworkRendered": False, "worldRendered": False, "frames": frames}
            save_trace(root, trace, receipt)
            data = e.export_report(root, Path(d) / "review", contact_sheet=True)
            meta = data["vision"]["contactSheet"]
            self.assertEqual([f["tick"] for f in meta["frames"]], [0, 1, 2])
            self.assertEqual([f["sha256"] for f in meta["frames"]], [f["sha256"] for f in frames])
            self.assertFalse(meta["interpolated"])
            # Tampered native pixels invalidate the report, even with untouched JSON.
            (root / frames[0]["path"]).write_bytes(b"not PNG")
            with self.assertRaises(ValueError):
                e.report(root)


class RunnerBoundaryTests(unittest.TestCase):
    def run_fake_native(self, root, behavior, review="none"):
        original = root / "input"
        saved_run(original)
        dll = root / "bin/fixture.dll"
        dll.parent.mkdir(exist_ok=True)
        dll.write_bytes(b"not-a-native-assembly-test-only")
        provenance = {"sourceSha256": "test", "dllSha256": w.digest(dll), "nativeAssetSha256": {}, "runtimeFilesSha256": {}, "configuredReferences": {}}
        args = argparse.Namespace(item=original / "item.json", vanilla_item=None, scenario=original / "scenario.json",
                                  out=root / "run", no_build=True, item_boundary="fresh", png=False, gif=False,
                                  gif_stride=1, camera="action", review=review, timeout=1)

        def execute(command, **kwargs):
            output = Path(command[command.index("--output") + 1]).parent
            trace = json.loads((original / "native.json").read_text())
            if behavior != "missing":
                if behavior == "invalid":
                    trace["timeline"]["complete"] = False
                (output / "native.json").write_text(json.dumps(trace))
            if behavior == "timeout":
                raise subprocess.TimeoutExpired(command, 1, output=b"partial output", stderr=b"timeout fixture")
            return subprocess.CompletedProcess(command, 1 if behavior == "wrong-exit" else 0, "native stdout", "")

        with patch.object(w, "native_executable", return_value=(dll, provenance)), \
             patch.object(w, "build_state", return_value=provenance), \
             patch.object(w.subprocess, "run", side_effect=execute):
            return w.execute_run(args)

    def test_process_zero_without_valid_trace_cannot_pass_and_timeout_retains_receipts(self):
        for behavior in ("missing", "invalid", "wrong-exit", "timeout"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                result = self.run_fake_native(root, behavior)
                self.assertEqual(result["exitCode"], 2)
                self.assertIn("error", result)
                self.assertTrue((root / "run/run.json").is_file())
                self.assertTrue((root / "run/stderr.log").is_file())
                if behavior == "timeout":
                    self.assertEqual(result["nativeExitCode"], 124)

    def test_optional_export_failure_keeps_native_outcome_and_error_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with patch.object(w, "render", side_effect=RuntimeError("optional rasterizer missing")):
                result = self.run_fake_native(root, "valid", "schematic")
            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(result["nativeExitCode"], 0)
            self.assertEqual(result["nativeStatus"], "passed")
            self.assertEqual(result["review"]["status"], "error")
            self.assertEqual(e.report(root / "run")["integrity"]["status"], "invalid")


class SuiteTests(unittest.TestCase):
    def test_public_smoke_plan_is_read_only_and_manifest_relative(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = w.HERE / "suites/smoke.json"
            proc = subprocess.run([sys.executable, str(w.HERE / "workbench.py"), "suite", str(manifest),
                                   "--out", str(root / "must-not-exist"), "--plan"], cwd=root,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            plan = json.loads(proc.stdout)
            self.assertEqual(len(plan["cases"]), 8)
            self.assertIn("npc-effect-lifecycle", [case["name"] for case in plan["cases"]])
            self.assertEqual(list(root.iterdir()), [])

    def test_removed_compare_command_is_rejected_without_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            proc = subprocess.run([sys.executable, str(w.HERE / "workbench.py"),
                                   "compare", "baseline", "candidate"], cwd=root,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("invalid choice", proc.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_ambiguous_and_blanket_expected_failures_are_refused(self):
        valid = w.read_json(w.HERE / "suites/smoke.json")
        variants = []
        for change in ({"name": "../escape"}, {"fixture": "../../elsewhere.json"}, {"unexpected": True},
                       {"expect": {"status": "failed"}}, {"expect": {"status": "error"}},
                       {"compareTo": "straight"}, {"vanillaItem": "WoodenBoomerang"}, {"timeout": True}):
            item = copy.deepcopy(valid)
            item["cases"][0].update(change)
            variants.append(item)
        prior_case = copy.deepcopy(valid)
        prior_case["cases"][1]["compareTo"] = "straight"
        variants.append(prior_case)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "suite.json"
            # Resolve scenarios once so failures exercise suite semantics, not missing files.
            for value in variants:
                for case in value["cases"]:
                    case["scenario"] = str((w.HERE / "suites" / case["scenario"]).resolve())
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    c.plan_suite(path)

    def test_suite_continues_after_broken_case_and_keeps_native_failure_separate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            saved_run(root / "input")
            cases = [{"name": name, "item": "input/item.json", "scenario": "input/scenario.json", "expect": expected}
                     for name, expected in [("bad", {"status": "failed", "failedAssertions": ["dummy_damaged"]}),
                                            ("negative", {"status": "failed", "failedAssertions": ["dummy_damaged"]}),
                                            ("healthy", {"status": "passed"})]]
            manifest = root / "suite.json"
            manifest.write_text(json.dumps({"schemaVersion": 1, "cases": cases}))

            def execute(command, **kwargs):
                out = Path(command[command.index("--out") + 1])
                if out.name == "bad":
                    return subprocess.CompletedProcess(command, 2, "", "crash")
                saved_run(out, "failed", ["dummy_damaged"]) if out.name == "negative" else saved_run(out)
                return subprocess.CompletedProcess(command, 1 if out.name == "negative" else 0, "", "")

            with patch.object(c.w, "native_executable"), patch.object(c.subprocess, "run", side_effect=execute):
                result = c.run_suite(manifest, root / "out", no_build=True)
            self.assertFalse(result["passed"])
            self.assertEqual(result["completedCases"], 3)
            self.assertEqual([r["expectationMatched"] for r in result["cases"]], [False, True, True])
            self.assertEqual(result["cases"][1]["nativeStatus"], "failed")
            self.assertTrue((root / "out/summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
