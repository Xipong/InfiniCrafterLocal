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


def _replace_payload(root, manifest_path, manifest, kind, data, *, rows=1, errors=0):
    descriptor = manifest["files"][kind]
    (root / descriptor["path"]).write_bytes(data)
    descriptor.update(bytes=len(data), rows=rows, unavailableRows=errors, sha256=hashlib.sha256(data).hexdigest())
    manifest_path.write_text(json.dumps(manifest))


def test_disk_snapshot_retains_verified_bytes_after_source_and_lookup_mutation(tmp_path):
    path, manifest = manifest_pair(tmp_path)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    original = snapshot.projectiles[42]
    original["timeLeft"] = 999
    for descriptor in manifest["files"].values():
        (tmp_path / descriptor["path"]).write_bytes(b"corrupted after admission\n")
    path.unlink()
    assert snapshot.projectiles[42]["timeLeft"] == 90
    assert snapshot.lookup("projectile", 42)["timeLeft"] == 90
    assert sorted(snapshot.projectiles) == [42, 43]
    assert dict(snapshot.items) == {97: {"type": 97, "shoot": 42}}
    with pytest.raises(TypeError):
        snapshot.projectiles[42] = {"type": 42}


@pytest.mark.parametrize("payload", [b'{"type":1,"type":2}\n', b'{"type":true}\n',
                                      b'{"type":1,"value":NaN}\n', b'\xff\n', b'\n',
                                      b'{"type":1}\n{"type":1}\n',
                                      pytest.param(b'{"type":42,"nested":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}\n", id="deep-row"),
                                      pytest.param(b'{"type":42,"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}\n", id="parser-depth-overflow")])
def test_stream_rejects_invalid_records_and_releases_private_index(tmp_path, monkeypatch, payload):
    from infini_local.services import runtime_dump_index
    cache = tmp_path / "private"
    cache.mkdir()
    monkeypatch.setattr(runtime_dump_index.tempfile, "tempdir", str(cache))
    path, manifest = manifest_pair(tmp_path / "source")
    _replace_payload(path.parent, path, manifest, "projectiles", payload, rows=payload.count(b"\n"))
    for _ in range(3):
        rejected = dumps.load_runtime_dump_snapshot(path, path)
        assert rejected.provenance["status"] == "invalid_snapshot"
        assert not rejected.items and not rejected.projectiles
        assert list(cache.iterdir()) == []
    _replace_payload(path.parent, path, manifest, "projectiles", b'{"type":42,"timeLeft":77}\n')
    admitted = dumps.load_runtime_dump_snapshot(path, path)
    assert admitted.lookup("projectile", 42)["timeLeft"] == 77
    del admitted
    import gc
    gc.collect()
    assert list(cache.iterdir()) == []


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b""])
def test_record_limit_applies_to_actual_bytes_and_includes_line_ending(tmp_path, monkeypatch, newline):
    path, manifest = manifest_pair(tmp_path, item_rows=[{"type": 1}])
    data = b'{"type":42,"payload":"' + b"x" * 100 + b'"}' + newline
    monkeypatch.setattr(dumps, "MAX_DUMP_ROW_BYTES", len(data))
    _replace_payload(tmp_path, path, manifest, "projectiles", data)
    assert dumps.load_runtime_dump_snapshot(path, path).projectiles[42]["payload"] == "x" * 100
    monkeypatch.setattr(dumps, "MAX_DUMP_ROW_BYTES", len(data) - 1)
    rejected = dumps.load_runtime_dump_snapshot(path, path)
    assert rejected.provenance["status"] == "invalid_snapshot" and not rejected.items


def test_incomplete_recovery_directory_does_not_override_published_manifest(tmp_path, monkeypatch):
    root = tmp_path / "runtime_dumps"
    incomplete = root / "runtime_dump_snapshots" / ("b" * 32)
    incomplete.mkdir(parents=True)
    (incomplete / "items_runtime_dump.jsonl").write_text('{"type":97,"shoot":999}\n')
    items, projectiles = [root / f"{kind}_runtime_dump.jsonl" for kind in ("items", "projectiles")]
    assert dumps.load_runtime_dump_snapshot(items, projectiles).provenance["status"] == "absent"
    path, _ = manifest_pair(root)
    snapshot = dumps.load_runtime_dump_snapshot(items, projectiles)
    assert snapshot.items[97]["shoot"] == 42
    assert snapshot.provenance["snapshotId"] == "a" * 32


def test_replaced_payload_symlink_during_admission_is_rejected(tmp_path, monkeypatch):
    import os
    if os.open not in os.supports_dir_fd or not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("openat no-follow admission is POSIX-specific")
    path, manifest = manifest_pair(tmp_path / "source")
    external = tmp_path / "outside.jsonl"
    original = dumps._snapshot_file

    def swapped(*args):
        target = original(*args)
        if target.name == "items_runtime_dump.jsonl":
            target.rename(external)
            target.symlink_to(external)
        return target

    monkeypatch.setattr(dumps, "_snapshot_file", swapped)
    rejected = dumps.load_runtime_dump_snapshot(path, path)
    assert rejected.provenance["status"] == "invalid_snapshot"
    assert not rejected.items and not rejected.projectiles


def test_catalog_over_512_mib_and_100k_rows_is_indexed_with_bounded_memory(tmp_path):
    """Real byte boundary, not a patched limit or a giant in-memory fixture."""
    import os
    import subprocess
    import sys
    path, manifest = manifest_pair(tmp_path)
    descriptor = manifest["files"]["projectiles"]
    target = tmp_path / descriptor["path"]
    count = 131_073
    hasher = hashlib.sha256()
    with target.open("wb") as stream:
        for identity in range(1, count + 1):
            prefix = ('{"type":%d,"timeLeft":90,"payload":"' % identity).encode()
            line = prefix + b"x" * (4096 - len(prefix) - 3) + b'"}\n'
            stream.write(line)
            hasher.update(line)
    descriptor.update(bytes=target.stat().st_size, rows=count, unavailableRows=0, sha256=hasher.hexdigest())
    assert descriptor["bytes"] > 512 * 1024 * 1024
    path.write_text(json.dumps(manifest))
    script = '''
import json, sys
from pathlib import Path
from infini_local.services import runtime_dump_service as dumps
path = Path(sys.argv[1])
snapshot = dumps.load_runtime_dump_snapshot(path, path)
assert snapshot.provenance["status"] == "verified_snapshot", snapshot.provenance
assert len(snapshot.projectiles) == 131073
assert snapshot.lookup("projectile", 131073)["timeLeft"] == 90
assert snapshot.items[97]["shoot"] == 42
if sys.platform == "linux":
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert peak < 192 * 1024, peak
    print(json.dumps({"peakRssKiB": peak, "rows": len(snapshot.projectiles)}))
'''
    result = subprocess.run([sys.executable, "-c", script, str(path)], env=os.environ.copy(),
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_disk_snapshot_supports_concurrent_detached_lookups(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    path, _ = manifest_pair(tmp_path)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)

    def lookup(_):
        row = snapshot.projectiles[42]
        row["timeLeft"] = 0
        return snapshot.lookup("projectile", 42)["timeLeft"], tuple(sorted(snapshot.projectiles))

    with ThreadPoolExecutor(max_workers=8) as workers:
        assert list(workers.map(lookup, range(100))) == [(90, (42, 43))] * 100


def test_same_length_corruption_rejects_pair_and_corrected_retry_succeeds(tmp_path):
    path, manifest = manifest_pair(tmp_path)
    payload = tmp_path / manifest["files"]["projectiles"]["path"]
    original = payload.read_bytes()
    corrupted = original.replace(b'"timeLeft": 90', b'"timeLeft": 99')
    assert corrupted != original and len(corrupted) == len(original)
    payload.write_bytes(corrupted)
    rejected = dumps.load_runtime_dump_snapshot(path, path)
    assert rejected.provenance["status"] == "invalid_snapshot"
    assert not rejected.items and not rejected.projectiles
    payload.write_bytes(original)
    assert dumps.load_runtime_dump_snapshot(path, path).lookup("projectile", 42)["timeLeft"] == 90


def test_private_index_disk_full_refuses_pair_and_can_retry(tmp_path, monkeypatch):
    from infini_local.services import runtime_dump_index
    cache = tmp_path / "private"
    cache.mkdir()
    monkeypatch.setattr(runtime_dump_index.tempfile, "tempdir", str(cache))
    path, _ = manifest_pair(tmp_path / "source", projectile_rows=[{"type": 42, "payload": "x" * 20000}])
    real_store = dumps.RuntimeDumpIndex

    def storage_with_page_quota():
        store = real_store()
        # Exercise SQLite's real SQLITE_FULL path, without exhausting host disk.
        pages = store._connection.execute("PRAGMA page_count").fetchone()[0]
        store._connection.execute(f"PRAGMA max_page_count={pages}")
        return store

    with monkeypatch.context() as patch:
        patch.setattr(dumps, "RuntimeDumpIndex", storage_with_page_quota)
        rejected = dumps.load_runtime_dump_snapshot(path, path)
        assert rejected.provenance["status"] == "invalid_snapshot"
        assert not rejected.items and not rejected.projectiles
        assert list(cache.iterdir()) == []
    admitted = dumps.load_runtime_dump_snapshot(path, path)
    assert admitted.projectiles[42]["payload"] == "x" * 20000


@pytest.mark.parametrize("arrays, admitted", [(63, True), (64, False)])
def test_record_depth_matches_exporter_limit_and_lookup_is_safe(tmp_path, arrays, admitted):
    path, manifest = manifest_pair(tmp_path)
    payload = b'{"type":42,"nested":' + b"[" * arrays + b"0" + b"]" * arrays + b"}\n"
    _replace_payload(tmp_path, path, manifest, "projectiles", payload)
    snapshot = dumps.load_runtime_dump_snapshot(path, path)
    assert (snapshot.provenance["status"] == "verified_snapshot") is admitted
    if admitted:
        assert snapshot.lookup("projectile", 42)["type"] == 42
    else:
        assert not snapshot.items and not snapshot.projectiles
