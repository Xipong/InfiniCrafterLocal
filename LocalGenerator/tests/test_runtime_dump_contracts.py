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
    assert dumps.load_jsonl_index(path, ("sourceMod", "internalName")) == ([], {}, {})
    row = {"type": "42", "sourceMod": "Example", "internalName": "Bolt", "name": "Live Bolt"}
    path.write_text('\ufeff\ninvalid json\n[]\n' + json.dumps(row) + '\n', encoding="utf-8")
    rows, by_type, by_name = dumps.load_jsonl_index(path, ("sourceMod", "internalName"))
    assert rows == [row]
    assert by_type[42] == by_type["42"] == row
    assert by_name["example/bolt"] == by_name["bolt"] == by_name["live bolt"] == row


def test_startup_dump_snapshot_feeds_parent_context(tmp_path):
    items = tmp_path / "items.jsonl"
    projectiles = tmp_path / "projectiles.jsonl"
    items.write_text(json.dumps({"type": 97, "ammo": 97, "shoot": 42, "sourceMod": "Terraria", "internalName": "LiveAmmo"}) + '\n')
    projectiles.write_text(json.dumps({"type": 42, "tileCollide": True, "internalName": "LiveBolt"}) + '\n')
    env = {**os.environ, "INFINI_ITEMS_RUNTIME_DUMP": str(items), "INFINI_PROJECTILES_RUNTIME_DUMP": str(projectiles)}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-c", '''
from infini_local.pipelines.parent_context_pipeline import ammo_profile_of, projectile_profile_of
from infini_local.services.runtime_dump_service import runtime_projectile_lookup
profile = projectile_profile_of({"shoot": 42})
assert profile["tileCollide"] is True and profile["fromRuntimeDump"] is True
assert profile["fromItemShoot"] == 42
ammo = ammo_profile_of({"useAmmo": 97})
assert ammo["exampleAmmo"] == "LiveAmmo"
assert ammo["exampleProjectile"]["internalName"] == "LiveBolt"
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
