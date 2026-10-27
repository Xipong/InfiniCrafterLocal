"""Launcher safety tests: no tModLoader or game process is started."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("tmod_workbench_runner", Path(__file__).with_name("runner.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tml = self.root / "tml"
        self.tml.mkdir()
        (self.tml / "tModLoader.dll").write_bytes(b"not an executable")
        self.driver = self.root / "driver.tmod"
        self.driver.write_bytes(b"fixture")
        self.example = self.root / "other.tmod"
        self.example.write_bytes(b"fixture2")
        self.scene = self.root / "source.json"
        self.input_scene = {"mode": "projectile", "ticks": 30, "minHits": 1}
        self.scene.write_text(json.dumps(self.input_scene), encoding="utf-8")
        self.mods = [f"IFCWorkbenchDriver={self.driver}", f"ExampleMod={self.example}"]

    def test_prepare_copies_inputs_and_fences_all_mutable_paths(self):
        state = runner.prepare(self.scene, self.mods, self.root)
        sandbox = state["sandbox"]
        self.assertNotEqual(sandbox, self.root)
        self.assertEqual(sandbox.parent, self.root)
        self.assertEqual(json.loads((state["mods"] / "enabled.json").read_text()),
                         ["ExampleMod", "IFCWorkbenchDriver"])
        self.assertEqual((state["mods"] / "ExampleMod.tmod").read_bytes(), b"fixture2")
        marker = json.loads((sandbox / "ifc-workbench-sandbox.json").read_text())
        self.assertEqual(marker, {"token": state["token"], "worldPath": str(state["world"])})
        self.assertGreaterEqual(len(state["token"]), 32)
        for name in ("mods", "world", "scenario", "output", "workshop"):
            self.assertTrue(state[name].is_relative_to(sandbox))
        command = runner.server_command("dotnet", self.tml, state, 12345)
        for option in ("-server", "-nosteam", "-noupnp"):
            self.assertIn(option, command)
        self.assertEqual(command[command.index("-ip") + 1], "127.0.0.1")
        for option in ("-tmlsavedirectory", "-modpath", "-steamworkshopfolder", "-world", "-banlist", "-config"):
            self.assertTrue(Path(command[command.index(option) + 1]).is_relative_to(sandbox))
        self.assertEqual(self.scene.read_text(), json.dumps(self.input_scene))

    def test_prepare_only_does_not_start_any_process(self):
        args = ["--tml-dir", str(self.tml), "--scenario", str(self.scene), "--sandbox-root", str(self.root),
                "--mod", self.mods[0], "--prepare-only"]
        with patch.object(runner.subprocess, "Popen", side_effect=AssertionError("game must not launch")):
            self.assertEqual(runner.main(args), 0)

    def test_item_use_and_invalid_mod_names_fail_before_sandbox_creation(self):
        before = set(self.root.iterdir())
        self.scene.write_text('{"mode":"item_use"}')
        with self.assertRaisesRegex(ValueError, "local client"):
            runner.prepare(self.scene, self.mods, self.root)
        self.assertEqual(set(self.root.iterdir()), before)
        self.scene.write_text(json.dumps(self.input_scene))
        with self.assertRaises(ValueError):
            runner.prepare(self.scene, self.mods + [f"../bad={self.example}"], self.root)
        with self.assertRaises(ValueError):
            runner.prepare(self.scene, [self.mods[0], f"ifcworkbenchdriver={self.example}"], self.root)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_server_forwards_fenced_environment_and_waits_for_result(self):
        state = runner.prepare(self.scene, self.mods, self.root,
                               ["IFC_WORKBENCH_OBSERVER_OUTPUT=observer.json"])
        calls = []

        class FakeProcess:
            def __init__(self, command, **kwargs):
                calls.append((command, kwargs))
                self.status = None
                self.stdin = self
                Path(kwargs["env"]["IFC_WORKBENCH_OUTPUT"]).write_text(json.dumps({
                    "schemaVersion": 1, "status": "passed", "mode": "projectile",
                    "scenarioSha256": state["scenario_sha256"], "requestedTicks": 30,
                    "completedTicks": 30, "minHits": 1, "minDamage": 1, "hits": 1, "totalDamage": 1}))
            def poll(self): return self.status
            def write(self, value): self.line = value
            def flush(self): pass
            def wait(self, timeout=None): self.status = 0; return 0

        with patch.dict(os.environ, {"IFC_WORKBENCH_STALE_OUTPUT": "/outside.json"}), patch.object(runner.subprocess, "Popen", FakeProcess):
            self.assertEqual(runner.run_server("dotnet", self.tml, state, 1, 12345), 0)
        command, kwargs = calls[0]
        env = kwargs["env"]
        self.assertEqual(kwargs["cwd"], self.tml)
        self.assertEqual(env["IFC_WORKBENCH_TOKEN"], state["token"])
        self.assertEqual(env["IFC_WORKBENCH_ENABLED"], "1")
        self.assertNotIn("IFC_WORKBENCH_STALE_OUTPUT", env)
        self.assertEqual(env["IFC_WORKBENCH_OBSERVER_OUTPUT"], str(state["sandbox"] / "observer.json"))
        for variable in ("IFC_WORKBENCH_SANDBOX", "IFC_WORKBENCH_SCENARIO", "IFC_WORKBENCH_OUTPUT"):
            self.assertTrue(Path(env[variable]).is_relative_to(state["sandbox"]))
        self.assertEqual(command[command.index("-port") + 1], "12345")
        class CrashedProcess(FakeProcess):
            def wait(self, timeout=None): self.status = 17; return 17
        with patch.object(runner.subprocess, "Popen", CrashedProcess), self.assertRaisesRegex(RuntimeError, "code 17"):
            runner.run_server("dotnet", self.tml, state, 1, 12345)

    def test_extra_output_cannot_escape_or_overwrite_driver_files(self):
        for value in ("IFC_WORKBENCH_X_OUTPUT=../outside.json", "HOME=outside.json",
                      "IFC_WORKBENCH_X_OUTPUT=result.json", "IFC_WORKBENCH_X_OUTPUT=scenario.json",
                      "IFC_WORKBENCH_X_OUTPUT=client-launch.json", "IFC_WORKBENCH_X_OUTPUT=world-source-receipt.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.prepare(self.scene, self.mods, self.root, [value])
        with self.assertRaises(ValueError):
            runner.prepare(self.scene, self.mods, self.root,
                           ["IFC_WORKBENCH_X_OUTPUT=same.json", "IFC_WORKBENCH_Y_OUTPUT=same.json"])

    def test_pass_report_requires_matching_scenario_and_observed_thresholds(self):
        state = runner.prepare(self.scene, self.mods, self.root)
        valid = {"schemaVersion": 1, "status": "passed", "mode": "projectile", "scenarioSha256": state["scenario_sha256"],
                 "requestedTicks": 30, "completedTicks": 30, "minHits": 1, "minDamage": 1, "hits": 1, "totalDamage": 1}
        runner.validate_passed_result(valid, state)
        for update in ({}, {"schemaVersion": True}, {"scenarioSha256": "bad"}, {"mode": "item_use"},
                       {"completedTicks": 29}, {"requestedTicks": True}, {"hits": 0}, {"totalDamage": 0},
                       {"hits": True}, {"minDamage": 0}, {"minHits": 2}):
            bad = {"status": "passed"} if not update else {**valid, **update}
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                runner.validate_passed_result(bad, state)

    def test_client_preparation_preserves_item_adapter_without_launching(self):
        item_scene = {"mode": "item_use", "ticks": 60, "minHits": 1,
                      "adapter": "InfiniCrafterLocal", "itemData": {"id": "example"}}
        self.scene.write_text(json.dumps(item_scene))
        args = ["--tml-dir", str(self.tml), "--scenario", str(self.scene), "--sandbox-root", str(self.root),
                "--mod", self.mods[0], "--mode", "client"]
        before = set(self.root.iterdir())
        with patch.object(runner.subprocess, "Popen", side_effect=AssertionError("must not launch")):
            with self.assertRaises(SystemExit): runner.main(args + ["--run"])
            self.assertEqual(set(self.root.iterdir()), before)
            self.assertEqual(runner.main(args + ["--prepare-only"]), 0)
        sandbox = next(path for path in set(self.root.iterdir()) - before if path.is_dir())
        plan = json.loads((sandbox / "client-launch.json").read_text())
        self.assertEqual(json.loads((sandbox / "scenario.json").read_text()), item_scene)
        self.assertEqual(plan["environment"]["IFC_WORKBENCH_SANDBOX"], str(sandbox))
        self.assertEqual(plan["expectedWorldPath"], str(sandbox / "Worlds" / "workbench.wld"))
        self.assertNotIn("-server", plan["command"])

    def test_world_source_is_copied_with_hash_receipt_and_never_auto_created(self):
        world = self.root / "original.wld"
        sidecar = self.root / "original.twld"
        world.write_bytes(b"existing-world-id-and-state")
        sidecar.write_bytes(b"mod-world-data")
        original = (world.read_bytes(), sidecar.read_bytes())
        state = runner.prepare(self.scene, self.mods, self.root, world_source=world)
        receipt = json.loads((state["sandbox"] / "world-source-receipt.json").read_text())["files"]
        self.assertEqual(state["world"].read_bytes(), original[0])
        self.assertEqual(state["world"].with_suffix(".twld").read_bytes(), original[1])
        self.assertEqual((world.read_bytes(), sidecar.read_bytes()), original)
        self.assertTrue(all(r["sourceSha256"] == r["sandboxSha256"] and len(r["sourceSha256"]) == 64 for r in receipt))
        command = runner.server_command("dotnet", self.tml, state, 12345)
        self.assertNotIn("-autocreate", command)
        self.assertNotIn("-worldname", command)
        self.assertEqual(command[command.index("-world") + 1], str(state["world"]))
        state["world"].write_bytes(b"changed-only-the-copy")
        self.assertEqual(world.read_bytes(), original[0])

    def test_world_source_requires_both_nonempty_files_before_creating_sandbox(self):
        world = self.root / "original.wld"
        world.write_bytes(b"world")
        before = set(self.root.iterdir())
        with self.assertRaises(OSError):
            runner.prepare(self.scene, self.mods, self.root, world_source=world)
        self.assertEqual(set(self.root.iterdir()), before)
        sidecar = self.root / "original.twld"
        sidecar.write_bytes(b"")
        before = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            runner.prepare(self.scene, self.mods, self.root, world_source=world)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_modified_source_is_rejected_during_copy(self):
        world = self.root / "original.wld"
        world.write_bytes(b"world")
        world.with_suffix(".twld").write_bytes(b"mod-world")
        original_copy = runner.shutil.copyfile
        def changing_copy(source, destination):
            result = original_copy(source, destination)
            if Path(source) == world:
                world.write_bytes(b"changed")
            return result
        with patch.object(runner.shutil, "copyfile", side_effect=changing_copy), self.assertRaisesRegex(RuntimeError, "changed during isolated copy"):
            runner.prepare(self.scene, self.mods, self.root, world_source=world)

    def test_assets_stage_exact_runtime_owners_and_keep_other_json_unchanged(self):
        old_a = "/old/location/item.png"
        old_b = "C:\\old\\impact.png"
        png_a = self.root / "a.png"
        png_b = self.root / "b.png"
        png_a.write_bytes(runner.PNG_SIGNATURE + b"fixture-a")
        png_b.write_bytes(runner.PNG_SIGNATURE + b"fixture-b")
        scene = {"mode": "item_use", "ticks": 30, "minHits": 1, "adapter": "InfiniCrafterLocal",
                 "itemData": {"visual": {"spritePath": old_a, "spriteRawPath": old_a, "equipOverlayPath": old_b},
                              "runtimeProgram": {"entities": [{"visual": {"spritePath": old_a, "impactSpritePath": old_b}}]},
                              "vfxManifest": {"assets": [{"spritePath": old_b}]}, "debug": {"path": old_a}}}
        self.scene.write_text(json.dumps(scene), encoding="utf-8")
        before = self.scene.read_bytes()
        state = runner.prepare(self.scene, self.mods, self.root, launch_mode="client",
                               asset_values=[f"{old_a}={png_a}", f"{old_b}={png_b}"])
        runtime = json.loads(state["scenario"].read_text())
        visual = runtime["itemData"]["visual"]
        a, b = Path(visual["spritePath"]), Path(visual["equipOverlayPath"])
        self.assertEqual(a.name, "item.png")
        self.assertEqual(b.name, "impact.png")
        self.assertTrue(a.is_relative_to(state["sandbox"]) and b.is_relative_to(state["sandbox"]))
        self.assertEqual((a.read_bytes(), b.read_bytes()), (png_a.read_bytes(), png_b.read_bytes()))
        self.assertEqual(visual["spriteRawPath"], old_a)
        self.assertEqual(runtime["itemData"]["debug"]["path"], old_a)
        self.assertEqual(runtime["itemData"]["runtimeProgram"]["entities"][0]["visual"]["spritePath"], str(a))
        self.assertEqual(runtime["itemData"]["vfxManifest"]["assets"][0]["spritePath"], str(b))
        receipt = json.loads((state["sandbox"] / "asset-staging-receipt.json").read_text())
        self.assertEqual(receipt["originalScenarioSha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(receipt["runtimeScenarioSha256"], state["scenario_sha256"])
        self.assertTrue(all(asset["sourceSha256"] == asset["sandboxSha256"] for asset in receipt["assets"]))
        self.assertEqual(self.scene.read_bytes(), before)

    def test_asset_mapping_is_explicit_complete_and_unambiguous(self):
        png = self.root / "source.png"
        png.write_bytes(runner.PNG_SIGNATURE + b"fixture")
        scene = {"mode": "item_use", "ticks": 30, "minHits": 1,
                 "itemData": {"visual": {"spritePath": "/original/sprite.png"}}}
        self.scene.write_text(json.dumps(scene))
        valid = f"/original/sprite.png={png}"
        for options in ([], [f"/wrong/sprite.png={png}"], [valid, valid]):
            with self.subTest(options=options), self.assertRaises(ValueError):
                runner.prepare(self.scene, self.mods, self.root, launch_mode="client", asset_values=options)
        other = self.root / "other.png"
        other.write_bytes(runner.PNG_SIGNATURE + b"different")
        scene["itemData"]["runtimeProgram"] = {"entities": [{"visual": {"spritePath": "/second/sprite.png"}}]}
        self.scene.write_text(json.dumps(scene))
        with self.assertRaisesRegex(ValueError, "Conflicting runtime asset filename"):
            runner.prepare(self.scene, self.mods, self.root, launch_mode="client",
                           asset_values=[valid, f"/second/sprite.png={other}"])


if __name__ == "__main__":
    unittest.main()
