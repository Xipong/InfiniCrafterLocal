"""Paired startup snapshots: integrity is not current-runtime compatibility."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from infini_local.services import runtime_dump_service as dumps
from infini_local.pipelines.context import parents


def manifest_pair(root: Path, snapshot_id: str = "a" * 32, *, item_rows=None, projectile_rows=None) -> tuple[Path, dict]:
    folder = root / "runtime_dump_snapshots" / snapshot_id
    folder.mkdir(parents=True)
    files = {}
    for kind, rows in (
        ("items", item_rows if item_rows is not None else [{"type": 97, "shoot": 42}]),
        ("projectiles", projectile_rows if projectile_rows is not None else [{"type": 42, "sourceMod": "Example", "internalName": "Bolt", "fullName": "Example/Bolt", "timeLeft": 90},
                         {"type": 43, "unavailable": True, "captureError": "InvalidOperationException"}]),
    ):
        path = folder / f"{kind}_runtime_dump.jsonl"
        data = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
        path.write_bytes(data)
        files[kind] = {"path": path.relative_to(root).as_posix(), "bytes": len(data), "rows": len(rows),
                       "unavailableRows": sum(row.get("unavailable") is True for row in rows),
                       "sha256": hashlib.sha256(data).hexdigest()}
    module = {"assembly": "tModLoader", "version": "2026.8.3.0", "mvid": "observed-tml-module"}
    manifest = {"schema": dumps.MANIFEST_SCHEMA, "snapshotId": snapshot_id,
                "capturedAtUtc": "2026-11-02T00:00:00+00:00",
                "environment": {"gameVersion": "1.4.4.9", "tModLoader": module,
                                "exporter": {"assembly": "IFC", "mvid": "observed-exporter"}, "mods": []},
                "files": files}
    path = root / dumps.MANIFEST_NAME
    path.write_text(json.dumps(manifest))
    return path, manifest


def use_snapshot(monkeypatch, snapshot):
    monkeypatch.setattr(dumps, "RUNTIME_DUMP_SNAPSHOT", snapshot)


def test_manifest_only_discovery_and_verified_pair(tmp_path, monkeypatch):
    root = tmp_path / "runtime_dumps"
    path, manifest = manifest_pair(root)
    for kind in ("items", "projectiles"):
        selected = dumps.resolve_runtime_dump_path(tmp_path, f"{kind}_runtime_dump.jsonl", "INFINI_TEST_EMPTY")
        assert selected == root / f"{kind}_runtime_dump.jsonl"
    snapshot = dumps.load_runtime_dump_snapshot(root / "items_runtime_dump.jsonl", root / "projectiles_runtime_dump.jsonl")
    assert snapshot.provenance == {"status": "verified_snapshot", "snapshotId": "a" * 32,
                                   "capturedAtUtc": manifest["capturedAtUtc"]}
    assert snapshot.items == {97: {"type": 97, "shoot": 42}}
    assert snapshot.projectiles[43]["unavailable"] is True
    # Explicit configuration can name the manifest instead of two payloads.
    assert dumps.load_runtime_dump_snapshot(path, path) == snapshot
    use_snapshot(monkeypatch, snapshot)
    raw = dumps.RUNTIME_DUMP_SNAPSHOT.lookup("projectile", 42)
    assert raw["runtimeDumpProvenance"]["compatibility"] == "unverified"
    raw["timeLeft"] = 0
    assert dumps.RUNTIME_DUMP_SNAPSHOT.lookup("projectile", 42)["timeLeft"] == 90


@pytest.mark.parametrize("mutation", ["tamper", "missing", "bad_rows", "bad_count", "bad_schema", "bad_date", "bad_hash"])
def test_invalid_pair_admits_neither_file_or_legacy_fallback(tmp_path, mutation, monkeypatch):
    path, manifest = manifest_pair(tmp_path)
    projectile = tmp_path / manifest["files"]["projectiles"]["path"]
    if mutation == "tamper":
        projectile.write_text('{"type":42,"timeLeft":999}\n')
    elif mutation == "missing":
        projectile.unlink()
    elif mutation == "bad_rows":
        data = b'{"type":42}\n{"type":42}\n'
        projectile.write_bytes(data)
        manifest["files"]["projectiles"].update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), unavailableRows=0)
    elif mutation == "bad_count":
        manifest["files"]["items"]["rows"] = 5
    elif mutation == "bad_schema":
        manifest["schema"] = "future-version"
    elif mutation == "bad_date":
        manifest["capturedAtUtc"] = "no timestamp"
    elif mutation == "bad_hash":
        manifest["files"]["items"]["sha256"] = "not-a-hash"
    path.write_text(json.dumps(manifest))
    (tmp_path / "items_runtime_dump.jsonl").write_text('{"type":2}\n')
    (tmp_path / "projectiles_runtime_dump.jsonl").write_text('{"type":42,"timeLeft":123}\n')
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    assert snapshot.items == {} and snapshot.projectiles == {}
    assert snapshot.provenance["status"] == "invalid_snapshot"
    use_snapshot(monkeypatch, snapshot)
    refusal = parents.compact_projectile_profile(parents.projectile_profile_of({"shoot": 42}))
    assert refusal["unavailable"] is True
    assert refusal["runtimeDumpProvenance"]["status"] == "invalid_snapshot"
    assert "timeLeft" not in refusal


@pytest.mark.parametrize("relative", ["/tmp/secret", "../../secret", "runtime_dump_snapshots/../secret",
                                      "C:\\secret", "runtime_dump_snapshots/" + "b" * 32 + "/items_runtime_dump.jsonl"])
def test_manifest_paths_cannot_select_other_files(tmp_path, relative):
    path, manifest = manifest_pair(tmp_path)
    manifest["files"]["items"]["path"] = relative
    path.write_text(json.dumps(manifest))
    assert dumps.load_runtime_dump_snapshot(path, path).provenance["status"] == "invalid_snapshot"


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "root"
    path, manifest = manifest_pair(root)
    item = root / manifest["files"]["items"]["path"]
    external = tmp_path / "outside.jsonl"
    item.rename(external)
    item.symlink_to(external)
    assert dumps.load_runtime_dump_snapshot(path, path).provenance["status"] == "invalid_snapshot"


@pytest.mark.parametrize("limit", ["MAX_MANIFEST_BYTES", "MAX_DUMP_BYTES", "MAX_DUMP_ROWS"])
def test_snapshot_resource_bounds(tmp_path, monkeypatch, limit):
    path, _ = manifest_pair(tmp_path)
    monkeypatch.setattr(dumps, limit, 1)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    assert not snapshot.items and not snapshot.projectiles
    assert snapshot.provenance["status"] == "invalid_snapshot"


def test_different_manifest_roots_do_not_form_a_pair(tmp_path):
    first, _ = manifest_pair(tmp_path / "a")
    second, _ = manifest_pair(tmp_path / "b")
    snapshot = dumps.load_runtime_dump_snapshot(first, second)
    assert snapshot.provenance["status"] == "invalid_snapshot"


def test_missing_manifest_refuses_old_dump_and_live_observation_wins(tmp_path, monkeypatch):
    items, projectiles = tmp_path / "items.jsonl", tmp_path / "projectiles.jsonl"
    items.write_text('{"type":97}\n')
    projectiles.write_text('{"type":42,"timeLeft":90}\n')
    snapshot = dumps.load_runtime_dump_snapshot(items, projectiles)
    assert snapshot.provenance == {"status": "invalid_snapshot", "reason": "snapshot_manifest_required"}
    assert snapshot.items == snapshot.projectiles == {}
    use_snapshot(monkeypatch, snapshot)
    profile = parents.compact_projectile_profile(parents.projectile_profile_of({"shoot": 42}))
    assert profile["unavailable"] is True and "timeLeft" not in profile
    assert profile["runtimeDumpProvenance"]["reason"] == "snapshot_manifest_required"
    assert items.read_text() == '{"type":97}\n'
    assert projectiles.read_text() == '{"type":42,"timeLeft":90}\n'
    direct = {"type": 42, "unavailable": True}
    live = parents.projectile_profile_of({"shoot": 42, "directProjectileRaw": direct})
    assert live["unavailable"] is True and "runtimeDumpProvenance" not in live


def test_known_identity_or_module_mismatch_refuses_numeric_facts(tmp_path, monkeypatch):
    path, _ = manifest_pair(tmp_path)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    use_snapshot(monkeypatch, snapshot)
    for item, reason in (
        ({"shoot": 42, "shootProjectileFullName": "Other/Bolt"}, "projectile_identity_mismatch"),
        ({"shoot": 42, "parentSourceGraph": {"modules": [{"assembly": "tModLoader", "mvid": "different-runtime"}]}}, "observed_module_mismatch"),
    ):
        profile = parents.compact_projectile_profile(parents.projectile_profile_of(item))
        assert profile["unavailable"] is True and "timeLeft" not in profile
        assert profile["runtimeDumpProvenance"]["reason"] == reason
    item = {"shoot": 42, "shootProjectileFullName": "Example/Bolt",
            "parentSourceGraph": {"modules": [{"assembly": "tModLoader", "mvid": "observed-tml-module"}]}}
    profile = parents.compact_projectile_profile(parents.projectile_profile_of(item))
    assert profile["timeLeft"] == 90
    assert profile["runtimeDumpProvenance"]["compatibility"] == "matched_available_identity_and_modules"


def test_unpublished_new_pair_cannot_change_loaded_snapshot(tmp_path, monkeypatch):
    path, old = manifest_pair(tmp_path)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    use_snapshot(monkeypatch, snapshot)
    manifest_pair(tmp_path, "b" * 32)
    # A process retains the original snapshot until restart, even after publication.
    assert dumps.RUNTIME_DUMP_SNAPSHOT.lookup("projectile", 42)["runtimeDumpProvenance"]["snapshotId"] == old["snapshotId"]
    assert dumps.load_runtime_dump_snapshot(path, path).provenance["snapshotId"] == "b" * 32


def test_noncomparable_module_does_not_prove_mod_set_compatibility(tmp_path, monkeypatch):
    path, _ = manifest_pair(tmp_path)
    use_snapshot(monkeypatch, dumps.load_runtime_dump_snapshot(path, path))
    profile = parents.projectile_profile_of({"shoot": 42,
        "parentSourceGraph": {"modules": [{"assembly": "UnobservedDependency", "mvid": "unknown"}]}})
    assert profile["timeLeft"] == 90
    assert profile["runtimeDumpProvenance"]["status"] == "verified_snapshot"
    assert profile["runtimeDumpProvenance"]["compatibility"] == "unverified"


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("state", ["verified_snapshot", "missing_manifest", "invalid_snapshot", "identity_mismatch"])
def test_provenance_reaches_actual_serialized_author_request(tmp_path, monkeypatch, mode, state):
    import socket
    from infini_local.core import llm_config
    from infini_local.pipelines.author import request as author
    from prompt_packet_helpers import expand_native_source_references, request_dossier

    def denied(*args, **kwargs):
        raise AssertionError("offline context construction must not use the network")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    path, manifest = manifest_pair(tmp_path)
    item = {"name": "Synthetic parent", "shoot": 42}
    if state == "missing_manifest":
        path.unlink()
        items = tmp_path / "items_runtime_dump.jsonl"
        projectiles = tmp_path / "projectiles_runtime_dump.jsonl"
        items.write_text('{"type":97}\n')
        projectiles.write_text('{"type":42,"timeLeft":90}\n')
        snapshot = dumps.load_runtime_dump_snapshot(items, projectiles)
    else:
        if state == "invalid_snapshot":
            (tmp_path / manifest["files"]["items"]["path"]).write_text("corrupt")
        if state == "identity_mismatch":
            item["shootProjectileFullName"] = "Different/Bolt"
        snapshot = dumps.load_runtime_dump_snapshot(path, path)
    use_snapshot(monkeypatch, snapshot)
    request, _, _ = author.build_initial_author_request(item, {}, "dump-provenance-offline", model_name="offline-test")
    dossier = expand_native_source_references(request_dossier(json.loads(json.dumps(request))))
    direct = dossier["parents"]["A"]["packet"]["raw"]["directProjectile"]
    provenance = direct["runtimeDumpProvenance"]
    assert provenance["status"] == ("verified_snapshot" if state == "identity_mismatch" else "invalid_snapshot" if state == "missing_manifest" else state)
    if state in ("invalid_snapshot", "identity_mismatch", "missing_manifest"):
        assert direct["unavailable"] is True and "timeLeft" not in direct
    else:
        assert direct["timeLeft"] == 90 and provenance["compatibility"] == "unverified"
    assert len(json.dumps(provenance)) < 320
    assert "environment" not in provenance and "files" not in provenance


@pytest.mark.parametrize("kind", ["item", "projectile"])
def test_lookup_does_not_reconstruct_retired_stable_identity_shape(tmp_path, kind):
    old = {"type": 42, "sourceMod": "Example", "internalName": "Bolt", "timeLeft": 90}
    path, _ = manifest_pair(tmp_path, item_rows=[old] if kind == "item" else None,
                            projectile_rows=[old] if kind == "projectile" else None)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    result = snapshot.lookup(kind, 42, expected_full_name="Example/Bolt")
    assert result["unavailable"] is True and "timeLeft" not in result
    assert result["runtimeDumpProvenance"]["reason"] == f"stable_{kind}_identity_unavailable"
    # Current producers carry the explicit stable name. Identity is not guessed
    # from presentation names, nor does an unavailable capture get filled.
    current_row = {**old, "fullName": "Example/Bolt"}
    current_path, _ = manifest_pair(tmp_path / "current", item_rows=[current_row] if kind == "item" else None,
                                    projectile_rows=[current_row] if kind == "projectile" else None)
    current = dumps.load_runtime_dump_snapshot(current_path, current_path)
    assert current.lookup(kind, 42, expected_full_name="Example/Bolt")["timeLeft"] == 90


def test_lookup_retains_its_snapshot_identity_when_another_is_installed(tmp_path, monkeypatch):
    first_path, _ = manifest_pair(tmp_path / "first", "a" * 32,
        projectile_rows=[{"type": 42, "timeLeft": 30, "fullName": "Example/First"}])
    first = dumps.load_runtime_dump_snapshot(first_path, first_path)
    second_path, _ = manifest_pair(tmp_path / "second", "b" * 32,
        projectile_rows=[{"type": 42, "timeLeft": 90, "fullName": "Example/Second"}])
    second = dumps.load_runtime_dump_snapshot(second_path, second_path)
    use_snapshot(monkeypatch, second)
    old = first.lookup("projectile", 42, expected_full_name="Example/First")
    current = second.lookup("projectile", 42, expected_full_name="Example/Second")
    assert old["timeLeft"] == 30 and old["runtimeDumpProvenance"]["snapshotId"] == "a" * 32
    assert current["timeLeft"] == 90 and current["runtimeDumpProvenance"]["snapshotId"] == "b" * 32
    assert old["runtimeDumpProvenance"]["compatibility"] == current["runtimeDumpProvenance"]["compatibility"] == "matched_available_identity"
