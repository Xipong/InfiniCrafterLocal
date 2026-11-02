"""Packaged Studio paths and process ownership; no sockets or live model calls.

These unittest cases also run directly when pytest is unavailable. Fresh
subprocesses exercise the real import-time path selection without inheriting the
test runner's cached configuration or the operator's INFINI settings.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


GENERATOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GENERATOR))

from infini_local.desktop.web_studio import _stop_owned_generator, _watch_parent


def isolated_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("INFINI_")}


def copy_runtime(destination: Path) -> Path:
    root = destination / "LocalGenerator"
    shutil.copytree(GENERATOR / "infini_local", root / "infini_local",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "AGENTS.md"))
    (root / "scripts").mkdir()
    shutil.copyfile(GENERATOR / "scripts/bundled_studio.py", root / "scripts/bundled_studio.py")
    shutil.copyfile(GENERATOR / "config.example.env", root / "config.example.env")
    return root


def inventory(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


class BundledPathsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ifc-bundled-paths-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runtime = copy_runtime(self.root / "runtime-one")
        self.data = self.root / "Документы" / "My Games" / "Studio data"
        self.save = self.root / "custom tML save"

    def run_application(self, *, runtime: Path | None = None, updates: dict | None = None) -> dict:
        script = r'''
import importlib.util, json, os, sys
from pathlib import Path
runtime, data, save = map(Path, sys.argv[1:4])
spec = importlib.util.spec_from_file_location("bundled_entry", runtime / "scripts/bundled_studio.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.configure_environment(data, save)
from infini_local.core import app_paths
from infini_local.desktop.settings_controller import SettingsController
from infini_local.desktop.settings_env import parse_env
app = SettingsController()
updates = json.loads(sys.argv[4])
if updates is not None:
    app.update_values(updates)
    app.save()
proposed = app._proposed_effective_config()
from infini_local.core import config_bootstrap
saved = parse_env(app.config_path)
print(json.dumps({
    "root": str(app_paths.ROOT), "state": str(app_paths.STATE_ROOT),
    "config": str(app.config_path), "cwd": str(Path.cwd()),
    "cache": str(config_bootstrap.CACHE_DIR.resolve()),
    "worlds": str(config_bootstrap.WORLD_RECIPES_DIR.resolve()),
    "proposedCache": proposed["cacheDir"], "proposedWorlds": proposed["worldRecipesDir"],
    "prompt": saved.get("INFINI_PROMPT_STYLE"), "language": saved.get("INFINI_LANGUAGE"),
    "itemsDump": os.environ.get("INFINI_ITEMS_RUNTIME_DUMP"),
    "projectilesDump": os.environ.get("INFINI_PROJECTILES_RUNTIME_DUMP"),
}))
app.on_close()
'''
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", script, str(runtime or self.runtime),
             str(self.data), str(self.save), json.dumps(updates)],
            cwd=self.root, env=isolated_environment(), capture_output=True,
            text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_saved_settings_and_cache_survive_another_runtime_without_runtime_writes(self):
        second_runtime = copy_runtime(self.root / "runtime-two")
        before = inventory(self.runtime), inventory(second_runtime)
        first = self.run_application(updates={
            "INFINI_PROMPT_STYLE": "retained player settings", "INFINI_LANGUAGE": "en",
            "INFINI_IMAGE_BACKEND": "off", "INFINI_SDCPP_SERVER_AUTOSTART": "0",
        })
        self.assertEqual(first["config"], str(self.data / "config.env"))
        self.assertEqual(first["state"], str(self.data))
        self.assertEqual(first["cwd"], str(self.data))
        self.assertEqual(first["cache"], str(self.data / "cache"))
        self.assertEqual(first["worlds"], str(self.data / "cache/world_recipes"))
        cache_item = Path(first["worlds"]) / "saved-recipe.json"
        cache_item.write_bytes(b'{"retained": true}')
        config_bytes = (self.data / "config.env").read_bytes()

        second = self.run_application(runtime=second_runtime)
        self.assertEqual(second["root"], str(second_runtime))
        self.assertNotEqual(first["root"], second["root"])
        for key in ("state", "config", "cache", "worlds", "prompt", "language"):
            self.assertEqual(second[key], first[key], key)
        self.assertEqual(second["prompt"], "retained player settings")
        self.assertEqual((self.data / "config.env").read_bytes(), config_bytes)
        self.assertEqual(cache_item.read_bytes(), b'{"retained": true}')
        self.assertEqual((inventory(self.runtime), inventory(second_runtime)), before)

    def test_relative_cache_and_world_paths_agree_with_launch_projection(self):
        result = self.run_application(updates={
            "INFINI_CACHE_DIR": "relative cache", "INFINI_WORLD_RECIPES_DIR": "relative worlds",
            "INFINI_LANGUAGE": "en",
        })
        for actual, proposed, expected in (
            ("cache", "proposedCache", self.data / "relative cache"),
            ("worlds", "proposedWorlds", self.data / "relative worlds"),
        ):
            self.assertEqual(result[actual], str(expected))
            self.assertEqual(result[proposed], result[actual])
            self.assertTrue(expected.is_dir())

    def test_custom_save_dump_defaults_preserve_saved_override(self):
        self.data.mkdir(parents=True)
        override = self.root / "explicit item dump.jsonl"
        (self.data / "config.env").write_text(
            "INFINI_ITEMS_RUNTIME_DUMP=" + str(override) + "\n"
            "INFINI_PROMPT_STYLE=existing profile\n"
            "INFINI_DATA_DIR=must-not-redirect-selected-state\n", encoding="utf-8")
        result = self.run_application()
        self.assertEqual(result["state"], str(self.data))
        self.assertEqual(result["itemsDump"], str(override))
        self.assertEqual(result["projectilesDump"],
                         str(self.save / "InfiniCrafterLocal/projectiles_runtime_dump.jsonl"))
        self.assertEqual(result["prompt"], "existing profile")

    def test_help_is_read_only_and_source_launch_keeps_its_state_location(self):
        before = inventory(self.runtime)
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(self.runtime / "scripts/bundled_studio.py"),
             "--data-dir", str(self.data), "--help"],
            cwd=self.root, env=isolated_environment(), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-dir", result.stdout)
        self.assertFalse(self.data.exists())
        self.assertEqual(inventory(self.runtime), before)
        script = "import sys; sys.path.insert(0, sys.argv[1]); from infini_local.core.app_paths import ROOT, STATE_ROOT; assert ROOT == STATE_ROOT"
        source = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(self.runtime)],
                                cwd=self.root, env=isolated_environment(), capture_output=True, text=True, timeout=10)
        self.assertEqual(source.returncode, 0, source.stderr)
        self.assertEqual(inventory(self.runtime), before)


class ManagedPipeTests(unittest.TestCase):
    @staticmethod
    def watcher(descriptor, shutdown):
        errors = []

        def run():
            try:
                _watch_parent(descriptor, shutdown)
            except BaseException as exc:
                errors.append(exc)

        return threading.Thread(target=run), errors

    def test_split_stop_waits_for_the_complete_line(self):
        read_fd, write_fd = os.pipe()
        shutdown, second_read = threading.Event(), threading.Event()
        real_read = os.read
        calls = 0

        def observed_read(descriptor, size):
            nonlocal calls
            calls += 1
            if calls == 2:
                second_read.set()  # The owner consumed and processed the first chunk.
            return real_read(descriptor, size)

        watcher, errors = self.watcher(read_fd, shutdown)
        with patch("infini_local.desktop.web_studio.os.read", side_effect=observed_read):
            watcher.start()
            try:
                os.write(write_fd, b"ST")
                self.assertTrue(second_read.wait(3), "Parent watcher did not consume the first chunk")
                self.assertFalse(shutdown.is_set(), "A partial command must not close Studio")
                os.write(write_fd, b"OP\n")
                self.assertTrue(shutdown.wait(3))
            finally:
                os.close(write_fd)
                watcher.join(3)
                os.close(read_fd)
        self.assertFalse(watcher.is_alive())
        self.assertEqual(errors, [])

    def test_parent_pipe_eof_requests_shutdown(self):
        read_fd, write_fd = os.pipe()
        shutdown = threading.Event()
        watcher, errors = self.watcher(read_fd, shutdown)
        watcher.start()
        os.close(write_fd)
        try:
            self.assertTrue(shutdown.wait(3))
        finally:
            watcher.join(3)
            os.close(read_fd)
        self.assertFalse(watcher.is_alive())
        self.assertEqual(errors, [])


class FakeOwnedProcess:
    """Popen boundary only; its deliberately fake PID never reaches an OS API."""
    pid = 876543210

    def __init__(self, *, refuses_terminate=False):
        self.returncode = None
        self.events = []
        self.refuses_terminate = refuses_terminate

    def poll(self):
        return self.returncode

    def terminate(self):
        self.events.append("terminate")
        if not self.refuses_terminate:
            self.returncode = -15

    def kill(self):
        self.events.append("kill")
        self.returncode = -9

    def wait(self, timeout):
        self.events.append(("wait", timeout))
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fixture-owned-process", timeout)
        return self.returncode


class ManagedGeneratorTests(unittest.TestCase):
    def operation_host(self, process, health):
        from infini_local.desktop.studio_operations import StudioOperations
        app = StudioOperations()
        app.proc = process
        app._owned_server_base_url = "http://127.0.0.1:5055"
        requests = []

        def http_boundary(url, **options):
            requests.append((url, options.get("method", "GET")))
            if url.endswith("/health"):
                return health
            if url.endswith("/shutdown?force=1"):
                process.returncode = 0
                return {"ok": True}
            raise AssertionError("Unexpected HTTP operation: " + url)

        app._read_gui_json = http_boundary
        return app, requests

    def test_no_owned_process_never_contacts_an_external_generator(self):
        app, requests = self.operation_host(None, {"pid": 12345})
        _stop_owned_generator(app)
        self.assertEqual(requests, [])

    def test_matching_owned_process_shuts_down_through_existing_http_guard(self):
        from infini_local.desktop.studio_operations import ROOT
        process = FakeOwnedProcess()
        app, requests = self.operation_host(process, {"pid": process.pid, "serverRoot": str(ROOT)})
        _stop_owned_generator(app)
        self.assertEqual(requests, [(app._owned_server_base_url + "/health", "GET"),
                                    (app._owned_server_base_url + "/shutdown?force=1", "POST")])
        self.assertEqual(process.events, [("wait", 3)])

    def test_mismatched_http_identity_never_receives_shutdown(self):
        from infini_local.desktop.studio_operations import ROOT
        for health in ({"pid": 12345, "serverRoot": str(ROOT)},
                       {"pid": FakeOwnedProcess.pid, "serverRoot": str(ROOT / "foreign-copy")}):
            with self.subTest(health=health):
                process = FakeOwnedProcess()
                app, requests = self.operation_host(process, health)
                _stop_owned_generator(app)
                self.assertEqual(requests, [(app._owned_server_base_url + "/health", "GET")])
                self.assertEqual(process.events, ["terminate", ("wait", 2)])

    def test_unresponsive_owned_handle_is_killed_and_joined_without_http_adoption(self):
        process = FakeOwnedProcess(refuses_terminate=True)
        app, requests = self.operation_host(process, {})
        del app._owned_server_base_url
        _stop_owned_generator(app)
        self.assertEqual(requests, [])
        self.assertEqual(process.events, ["terminate", ("wait", 2), "kill", ("wait", 2)])


if __name__ == "__main__":
    unittest.main()
