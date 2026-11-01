"""Offline setup tests: all network bytes are supplied by local fixtures."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("fetch_vfx_assets", Path(__file__).with_name("fetch_vfx_assets.py"))
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class FetchVfxAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "assets"
        self.dll = self.root / "ParticleLibrary.dll"
        self.dll.write_bytes(b"existing DLL")
        self.contents = {"LICENSE": b"test license", "Assets/Textures/Star.png": b"test image bytes"}
        self.manifest = {"package": "ParticleLibrary", "version": "test", "commit": "a" * 40,
            "installedDll": {"relativePath": "ParticleLibrary/ParticleLibrary.dll",
                "sourceURL": setup.OFFICIAL_PREFIX + "a" * 40 + "/ParticleLibrary.dll",
                "bytes": self.dll.stat().st_size, "sha256": setup.digest(self.dll.read_bytes())},
            "files": [{"path": path, "sourceURL": setup.OFFICIAL_PREFIX + "a" * 40 + "/" + path,
                       "bytes": len(data), "sha256": setup.digest(data)} for path, data in self.contents.items()]}
        self.calls = []

    def fetch(self, entry):
        self.calls.append(entry["path"])
        return self.contents[entry["path"]]

    def run_setup(self, manifest=None, fetch=None):
        return setup.provision(self.out, self.dll, manifest or self.manifest, fetch or self.fetch)

    def test_download_and_reuse(self):
        result = self.run_setup()
        self.assertEqual(result["downloaded"], 2)
        self.assertFalse(result["runtimeReady"])
        self.assertEqual(result["environment"]["INFINI_PARTICLE_ASSET_DIR"], str(self.out))
        self.calls.clear()
        result = self.run_setup()
        self.assertEqual(result["reused"], 2)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.out.rglob(".asset-*")), [])

    def test_setup_installs_dll_and_assets_and_reuses_verified_files(self):
        deps = self.root / "dependencies"
        original = self.dll.read_bytes()
        self.contents["ParticleLibrary/ParticleLibrary.dll"] = original
        result = setup.setup_particle(deps, self.manifest, self.fetch)
        self.assertEqual((deps / "ParticleLibrary/ParticleLibrary.dll").read_bytes(), original)
        self.assertEqual((deps / "particle-assets/LICENSE").read_bytes(), self.contents["LICENSE"])
        self.assertTrue(result["dll"]["downloaded"])
        self.assertEqual(result["environment"]["INFINI_TML_DEPS_SRC"], str(deps))
        self.assertFalse(result["runtimeReady"])
        self.calls.clear()
        again = setup.setup_particle(deps, self.manifest, self.fetch)
        self.assertFalse(again["dll"]["downloaded"])
        self.assertEqual(self.calls, [])

    def test_setup_rejects_corrupt_or_untrusted_dll_without_replacement(self):
        deps = self.root / "dependencies"
        bad = deps / "ParticleLibrary/ParticleLibrary.dll"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"existing unrelated bytes")
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            setup.setup_particle(deps, self.manifest, self.fetch)
        self.assertEqual(bad.read_bytes(), b"existing unrelated bytes")
        self.assertEqual(self.calls, [])
        bad.unlink()
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            setup.setup_particle(deps, self.manifest, lambda entry: b"bad download")
        self.assertFalse(bad.exists())
        manifest = copy.deepcopy(self.manifest)
        manifest["installedDll"]["sourceURL"] = "https://example.com/ParticleLibrary.dll"
        with self.assertRaisesRegex(ValueError, "pinned official source"):
            setup.setup_particle(deps, manifest, self.fetch)

    def test_workbench_setup_command_routes_to_particle_installer(self):
        import sys
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        import fetch_vfx_assets
        import workbench
        deps = self.root / "cli-dependencies"
        with patch.object(sys, "argv", ["workbench", "setup-particle", "--deps-root", str(deps)]), \
             patch.object(fetch_vfx_assets, "setup_particle", return_value={"status": "verified"}) as install, \
             redirect_stdout(StringIO()):
            self.assertEqual(workbench.main(), 0)
        self.assertEqual(install.call_args.args[0], deps)
        self.assertEqual(install.call_args.args[1]["package"], "ParticleLibrary")

    def test_wrong_dll_refuses_before_download(self):
        self.dll.write_bytes(b"wrong DLL")
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            self.run_setup()
        self.assertEqual(self.calls, [])
        self.assertFalse(self.out.exists())

    def test_existing_mismatch_never_overwritten(self):
        path = self.out / "LICENSE"
        path.parent.mkdir()
        path.write_bytes(b"user data")
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            self.run_setup()
        self.assertEqual(path.read_bytes(), b"user data")
        self.assertEqual(self.calls, [])

    def test_corrupt_download_not_installed(self):
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            self.run_setup(fetch=lambda _: b"corrupt")
        self.assertFalse(self.out.exists())

    def test_same_length_corruption_rejected(self):
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            self.run_setup(fetch=lambda e: b"x" * e["bytes"])
        self.assertFalse(self.out.exists())

    def test_official_source_and_commit_required(self):
        m = copy.deepcopy(self.manifest)
        m["files"][0]["sourceURL"] = "https://example.com/LICENSE"
        with self.assertRaisesRegex(ValueError, "official"):
            self.run_setup(manifest=m)
        self.assertEqual(self.calls, [])

    def test_traversal_rejected(self):
        m = copy.deepcopy(self.manifest)
        m["files"][0]["path"] = "../outside"
        m["files"][0]["sourceURL"] = setup.OFFICIAL_PREFIX + m["commit"] + "/../outside"
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.run_setup(manifest=m)
        self.assertEqual(self.calls, [])

    def test_duplicate_rejected(self):
        m = copy.deepcopy(self.manifest)
        m["files"].append(m["files"][0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.run_setup(manifest=m)
        self.assertEqual(self.calls, [])

    def test_symlink_destination_rejected(self):
        self.out.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        try:
            (self.out / "Assets").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable on this platform")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            self.run_setup()
        self.assertEqual(self.calls, [])
        self.assertEqual(list(outside.iterdir()), [])

    def test_concurrent_mismatching_file_not_overwritten(self):
        def race(entry):
            path = self.out / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"other writer")
            return self.contents[entry["path"]]
        with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
            self.run_setup(fetch=race)
        self.assertEqual((self.out / "LICENSE").read_bytes(), b"other writer")
        self.assertEqual(list(self.out.rglob(".asset-*")), [])

    def test_download_failure_keeps_only_prior_verified_files(self):
        def fail_second(entry):
            if entry["path"] != "LICENSE":
                raise OSError("test offline")
            return self.contents[entry["path"]]
        with self.assertRaisesRegex(OSError, "offline"):
            self.run_setup(fetch=fail_second)
        self.assertEqual((self.out / "LICENSE").read_bytes(), self.contents["LICENSE"])
        self.assertFalse((self.out / "Assets").exists())

    def test_luminance_setup_verifies_and_reuses_original_resources(self):
        import hashlib
        from unittest.mock import patch
        import fetch_luminance
        dll, image = b"actual dll", b"actual png"
        path = "Assets/GreyscaleTextures/ShineFlare.png"
        blob = hashlib.sha1(b"blob " + str(len(image)).encode() + b"\0" + image).hexdigest()
        calls = []
        def fetch(entry):
            calls.append(entry["path"])
            return dll if entry["path"].endswith(".dll") else image
        deps = self.root / "deps"
        with patch.object(fetch_luminance, "DLL_SHA256", setup.digest(dll)), \
             patch.object(fetch_luminance, "FILES", {path: (len(image), blob)}), \
             patch.object(fetch_luminance, "DLL_BYTES", len(dll)):
            result = fetch_luminance.setup_luminance(deps, fetch)
            self.assertEqual((deps / "luminance-assets" / path).read_bytes(), image)
            self.assertEqual(result["environment"]["INFINI_LUMINANCE_ASSET_DIR"], str(deps / "luminance-assets"))
            calls.clear()
            fetch_luminance.setup_luminance(deps, fetch)
            self.assertEqual(calls, [])
            (deps / "luminance-assets" / path).write_bytes(b"wrong bytes")
            with self.assertRaisesRegex(ValueError, "Integrity mismatch"):
                fetch_luminance.setup_luminance(deps, fetch)


if __name__ == "__main__":
    unittest.main()
