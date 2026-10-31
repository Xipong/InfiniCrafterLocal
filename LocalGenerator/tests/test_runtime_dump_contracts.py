"""Optional live /infinidump discovery and parent-context facts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from infini_local.services import runtime_dump_service as dumps


def test_discovery_prefers_current_then_legacy_then_existing_packaged_dump(tmp_path, monkeypatch):
    current = tmp_path / "current.jsonl"
    legacy = tmp_path / "legacy.jsonl"
    packaged = tmp_path / "runtime_dumps" / "items.jsonl"
    packaged.parent.mkdir()
    packaged.write_text("{}\n")
    legacy.write_text("{}\n")
    monkeypatch.setenv("INFINI_TEST_DUMP", str(current))
    monkeypatch.setenv("INFINI_TEST_LEGACY_DUMP", str(legacy))
    args = (tmp_path, "items.jsonl", "INFINI_TEST_DUMP", "INFINI_TEST_LEGACY_DUMP")
    # An explicit missing file does not hide an existing discovered file.
    assert dumps.resolve_runtime_dump_path(*args) == packaged
    current.write_text("{}\n")
    assert dumps.resolve_runtime_dump_path(*args) == current
    monkeypatch.delenv("INFINI_TEST_DUMP")
    assert dumps.resolve_runtime_dump_path(*args) == legacy


def test_jsonl_index_tolerates_missing_and_malformed_records(tmp_path):
    path = tmp_path / "dump.jsonl"
    assert dumps.load_jsonl_index(path) == ([], {})
    row = {"type": "42", "sourceMod": "Example", "internalName": "Bolt", "name": "Live Bolt"}
    path.write_text('\ufeff\ninvalid json\n[]\n' + json.dumps(row) + '\n', encoding="utf-8")
    rows, by_type = dumps.load_jsonl_index(path)
    assert rows == [row]
    assert by_type[42] == by_type["42"] == row


def test_jsonl_bad_rows_do_not_hide_later_native_facts(tmp_path):
    path = tmp_path / "dump.jsonl"
    good = {"type": 42, "name": "Later projectile"}
    invalid = [{"type": []}, {"type": {}}, {"type": True}, {"type": 42.5},
               {"type": -1}, {"type": "invalid"}]
    path.write_bytes(b'\xff\n' + b'{"type":2,"damage":NaN}\n'
                     + b'\n'.join(json.dumps(row).encode() for row in [*invalid, good]) + b'\n')
    assert dumps.load_jsonl_index(path) == ([good], {42: good})


def test_startup_dump_snapshot_feeds_parent_context(tmp_path):
    items = tmp_path / "items.jsonl"
    projectiles = tmp_path / "projectiles.jsonl"
    items.write_text(json.dumps({"type": 97, "ammo": 97, "shoot": 42, "sourceMod": "Terraria", "internalName": "LiveAmmo"}) + '\n')
    projectiles.write_text(json.dumps({"type": 42, "tileCollide": True, "internalName": "LiveBolt"}) + '\n')
    env = {**os.environ, "INFINI_ITEMS_RUNTIME_DUMP": str(items), "INFINI_PROJECTILES_RUNTIME_DUMP": str(projectiles)}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c", '''
from infini_local.pipelines.context.parents import ammo_profile_of, projectile_profile_of
from infini_local.services.runtime_dump_service import runtime_projectile_lookup
profile = projectile_profile_of({"shoot": 42})
assert profile["tileCollide"] is True and profile["fromRuntimeDump"] is True
assert profile["fromItemShoot"] == 42
# A native useAmmo ID does not authorize scanning for a guessed example.
assert ammo_profile_of({"useAmmo": 97}) == {}
literal = {"mode": "weapon_uses_ammo", "ammoId": 97,
           "ammoItemRaw": {"type": 97, "internalName": "LiveAmmo"},
           "projectileRaw": {"type": 42, "internalName": "LiveBolt"}}
assert ammo_profile_of({"ammoRaw": literal}) == literal
assert runtime_projectile_lookup("42")["tileCollide"] is True
assert runtime_projectile_lookup("invalid") == {}
assert runtime_projectile_lookup(99999) == {}
# Importing the HTTP composition root must reuse the existing snapshot.
from infini_local.services import runtime_dump_service
def unexpected_reload(*args, **kwargs):
    raise AssertionError("HTTP startup reloaded the live runtime dumps")
runtime_dump_service.load_jsonl_index = unexpected_reload
from infini_local.web import server
'''], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
