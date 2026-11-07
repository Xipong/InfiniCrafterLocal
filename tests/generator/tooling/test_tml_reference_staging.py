"""Declared runtime bytes and host bindings must survive the harness build."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("stage_tml_references", ROOT / "tools/build/stage_tml_references.py")
staging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(staging)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def official_fixture(tmp_path):
    root = tmp_path / "official"
    target = {
        "tModLoader/1.0.0": {"runtime": {"tModLoader.dll": {}}},
        "FNA/1.0.0": {"runtime": {"FNA.dll": {}}},
        "FNA.Reference/23.0.0": {"runtime": {"FNA.dll": {"assemblyVersion": "23.0.0.0"}}},
        "System.Text.Json/8.0.4": {"runtime": {"lib/net8.0/System.Text.Json.dll": {
            "assemblyVersion": "8.0.0.0", "fileVersion": "8.0.724.31311"}}},
        "Platform/1.0.0": {"runtime": {"lib/net8.0/Platform.dll": {}}, "runtimeTargets": {
            "runtimes/win/lib/net8.0/Platform.dll": {"rid": "win", "assetType": "runtime"},
            "runtimes/linux/lib/net8.0/Platform.dll": {"rid": "linux", "assetType": "runtime"}}},
    }
    libraries = {
        "tModLoader/1.0.0": {"type": "project"}, "FNA/1.0.0": {"type": "project"},
        "FNA.Reference/23.0.0": {"type": "reference"},
        "System.Text.Json/8.0.4": {"type": "package", "path": "system.text.json/8.0.4"},
        "Platform/1.0.0": {"type": "package", "path": "platform/1.0.0"},
    }
    write(root / "tModLoader.deps.json", {"runtimeTarget": {"name": "net8"}, "targets": {"net8": target}, "libraries": libraries})
    write(root / "tModLoader.runtimeconfig.json", {"runtimeOptions": {"framework": {"name": "Microsoft.NETCore.App", "version": "8.0.0"}}})
    for path, content in {
        "tModLoader.dll": b"native", "Libraries/FNA/1.0.0/FNA.dll": b"canonical FNA",
        "Libraries/system.text.json/8.0.4/lib/net8.0/System.Text.Json.dll": b"primary JSON",
        "Libraries/buildtools/BuildHost/System.Text.Json.dll": b"wrong nested tool JSON",
        "Libraries/platform/1.0.0/lib/net8.0/Platform.dll": b"base platform",
        "Libraries/platform/1.0.0/runtimes/win/lib/net8.0/Platform.dll": b"Windows platform",
        "Libraries/platform/1.0.0/runtimes/linux/lib/net8.0/Platform.dll": b"Linux platform",
    }.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    return root


def test_primary_assets_exclude_build_tools_and_select_target_rid(tmp_path):
    runtime = official_fixture(tmp_path)
    for rid, expected in (("win-x64", b"Windows platform"), ("linux-x64", b"Linux platform")):
        manifest = staging.selected_assets(runtime, rid)
        destination = tmp_path / rid
        staging.stage_references(runtime, destination, manifest)
        assert (destination / "System.Text.Json.dll").read_bytes() == b"primary JSON"
        assert (destination / "Platform.dll").read_bytes() == expected
        assert (destination / "FNA.dll").read_bytes() == b"canonical FNA"
        assert len(manifest["assets"]) == 4
        assert all("BuildHost" not in row["source"] for row in manifest["assets"])


def test_missing_primary_is_not_replaced_by_nested_tool_or_conflicting_alias(tmp_path):
    runtime = official_fixture(tmp_path)
    primary = runtime / "Libraries/system.text.json/8.0.4/lib/net8.0/System.Text.Json.dll"
    primary.unlink()
    with pytest.raises(ValueError, match="Missing official primary"):
        staging.selected_assets(runtime, "linux-x64")
    primary.write_bytes(b"primary JSON")
    duplicate = runtime / "Libraries/FNA.Reference/23.0.0/FNA.dll"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b"different assembly")
    with pytest.raises(ValueError, match="Conflicting primary assets"):
        staging.selected_assets(runtime, "linux-x64")


def test_harness_receives_missing_framework_override_and_preserves_own_dependencies(tmp_path):
    runtime = official_fixture(tmp_path)
    manifest = staging.selected_assets(runtime, "linux-x64")
    harness = tmp_path / "bin/EngineRuntimeChecks.dll"
    harness.parent.mkdir()
    harness.write_bytes(b"fixture executable; not a PE")
    target = {
        "EngineRuntimeChecks/1.0.0": {"dependencies": {"tModLoader": "1.0.0", "Decompiler": "8.2.0"}, "runtime": {harness.name: {}}},
        "tModLoader/1.0.0": {"runtime": {"tModLoader.dll": {}}},
        "Decompiler/8.2.0": {"runtime": {"Decompiler.dll": {}}},
    }
    write(harness.with_suffix(".deps.json"), {"runtimeTarget": {"name": "net8"}, "targets": {"net8": target},
                                           "libraries": {key: {"type": "reference"} for key in target}})
    staging.stage_harness(runtime, harness, manifest)
    payload = harness.with_suffix(".deps.json").read_bytes()
    updated = json.loads(payload)["targets"]["net8"]
    assert updated["System.Text.Json/8.0.0.0"]["runtime"]["System.Text.Json.dll"]["fileVersion"] == "8.0.724.31311"
    assert updated["EngineRuntimeChecks/1.0.0"]["dependencies"]["System.Text.Json"] == "8.0.0.0"
    assert "Decompiler/8.2.0" in updated
    assert (harness.parent / "System.Text.Json.dll").read_bytes() == b"primary JSON"
    staging.stage_harness(runtime, harness, manifest)
    assert harness.with_suffix(".deps.json").read_bytes() == payload


def test_reference_staging_does_not_overwrite_an_unowned_directory(tmp_path):
    runtime = official_fixture(tmp_path)
    destination = tmp_path / "user-files"
    destination.mkdir()
    (destination / "important.txt").write_text("keep")
    with pytest.raises(ValueError, match="must be empty or owned"):
        staging.stage_references(runtime, destination, staging.selected_assets(runtime, "linux-x64"))
    assert (destination / "important.txt").read_text() == "keep"
