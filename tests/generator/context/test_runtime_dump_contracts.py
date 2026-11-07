"""Optional live /infinidump discovery and parent-context facts."""
from __future__ import annotations
from suite_paths import GENERATOR_ROOT

import json
import hashlib
import pytest
import os
from pathlib import Path
import subprocess
import sys

from infini_local.services import runtime_dump_service as dumps
from tests.generator.context.test_runtime_dump_snapshot import manifest_pair


def test_explicit_dump_path_never_falls_through_to_discovered_data(tmp_path, monkeypatch):
    current = tmp_path / "current.jsonl"
    legacy = tmp_path / "legacy.jsonl"
    packaged = tmp_path / "runtime_dumps" / "items.jsonl"
    packaged.parent.mkdir()
    packaged.write_text("{}\n")
    legacy.write_text("{}\n")
    monkeypatch.setenv("INFINI_TEST_DUMP", str(current))
    monkeypatch.setenv("INFINI_TEST_LEGACY_DUMP", str(legacy))
    args = (tmp_path, "items.jsonl", "INFINI_TEST_DUMP")
    # Explicit selection remains authoritative even when temporarily missing.
    assert dumps.resolve_runtime_dump_path(*args) == current
    current.write_text("{}\n")
    assert dumps.resolve_runtime_dump_path(*args) == current
    monkeypatch.delenv("INFINI_TEST_DUMP")
    assert dumps.resolve_runtime_dump_path(*args) == packaged


def test_absent_dump_has_no_records_or_invented_provenance(tmp_path):
    snapshot = dumps.load_runtime_dump_snapshot(tmp_path / "items_runtime_dump.jsonl", tmp_path / "projectiles_runtime_dump.jsonl")
    assert snapshot.items == snapshot.projectiles == {}
    assert snapshot.provenance == {"status": "absent"}
    assert snapshot.lookup("projectile", 42) == {}


@pytest.mark.parametrize("bad_row", [b"invalid json", b"[]", b"\xff", b'{"type":2,"damage":NaN}',
                                     b'{"type":[]}', b'{"type":{}}', b'{"type":true}', b'{"type":42.5}',
                                     b'{"type":-1}', b'{"type":"42"}'])
def test_bad_rows_refuse_whole_snapshot_instead_of_skipping_to_later_facts(tmp_path, bad_row):
    path, manifest = manifest_pair(tmp_path)
    descriptor = manifest["files"]["projectiles"]
    payload = bad_row + b'\n{"type":42,"name":"Later projectile"}\n'
    (tmp_path / descriptor["path"]).write_bytes(payload)
    descriptor.update(bytes=len(payload), rows=2, unavailableRows=0, sha256=hashlib.sha256(payload).hexdigest())
    path.write_text(json.dumps(manifest))
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    assert snapshot.items == snapshot.projectiles == {}
    assert snapshot.provenance["status"] == "invalid_snapshot"
    assert snapshot.lookup("projectile", 42)["unavailable"] is True


def test_startup_dump_snapshot_feeds_parent_context(tmp_path):
    manifest, _ = manifest_pair(tmp_path,
        item_rows=[{"type": 97, "ammo": 97, "shoot": 42, "sourceMod": "Terraria", "internalName": "LiveAmmo"}],
        projectile_rows=[{"type": 42, "tileCollide": True, "internalName": "LiveBolt"}])
    env = {**os.environ, "INFINI_ITEMS_RUNTIME_DUMP": str(manifest), "INFINI_PROJECTILES_RUNTIME_DUMP": str(manifest)}
    env["PYTHONPATH"] = str(GENERATOR_ROOT)
    result = subprocess.run([sys.executable, "-c", '''
from infini_local.pipelines.context.parents import ammo_profile_of, projectile_profile_of
from infini_local.services.runtime_dump_service import RUNTIME_DUMP_SNAPSHOT
profile = projectile_profile_of({"shoot": 42})
assert profile["tileCollide"] is True and profile["fromRuntimeDump"] is True
assert profile["fromItemShoot"] == 42
# A native useAmmo ID does not authorize scanning for a guessed example.
assert ammo_profile_of({"useAmmo": 97}) == {}
literal = {"mode": "weapon_uses_ammo", "ammoId": 97,
           "ammoItemRaw": {"type": 97, "internalName": "LiveAmmo"},
           "projectileRaw": {"type": 42, "internalName": "LiveBolt"}}
assert ammo_profile_of({"ammoRaw": literal}) == literal
assert RUNTIME_DUMP_SNAPSHOT.lookup("projectile", "42")["tileCollide"] is True
assert RUNTIME_DUMP_SNAPSHOT.lookup("projectile", "invalid") == {}
assert RUNTIME_DUMP_SNAPSHOT.lookup("projectile", 99999) == {}
# Importing the HTTP composition root must reuse the existing snapshot.
from infini_local.services import runtime_dump_service
def unexpected_reload(*args, **kwargs):
    raise AssertionError("HTTP startup reloaded the live runtime dumps")
runtime_dump_service.load_runtime_dump_snapshot = unexpected_reload
from infini_local.web import server
'''], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
