"""Exercise the build-time archive checker against delivered bytes and aliases."""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("native_source_pack_checker", ROOT / "tools/generate/build_native_source_pack.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_projection_fingerprint_covers_shared_analysis_primitives(tmp_path, monkeypatch):
    mod = tmp_path / "mod/InfiniCrafterLocal"
    analysis = mod / "Common/Analysis"
    analysis.mkdir(parents=True)
    (mod / "GeneratorClient.Fixture.cs").write_text("source owner", encoding="utf-8")
    helper = analysis / "SourceAnalysisBuffers.cs"
    helper.write_text("first primitive implementation", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "MOD", mod)
    before, count = checker.projection_fingerprint()
    assert count == 2
    helper.write_text("changed primitive implementation", encoding="utf-8")
    after, count = checker.projection_fingerprint()
    assert count == 2 and before != after


@pytest.fixture
def pack(tmp_path, monkeypatch):
    mod = tmp_path / "mod"
    (mod / "lib").mkdir(parents=True)
    (mod / "lib/ICSharpCode.Decompiler.dll").write_bytes(b"fixture decompiler")
    monkeypatch.setattr(checker, "MOD", mod)
    native = tmp_path / "tModLoader.dll"
    native.write_bytes(b"fixture native")
    payload = b'{"last":"source\\r\\nbytes","first":null,"values":[2,2,1]}'
    digest = sha(payload)
    manifest = {
        "version": 2, "minimumMethodIlBytes": 1, "projectionSha256": "projection",
        "decompilerSha256": sha(b"fixture decompiler"), "nativeAssemblySha256": sha(b"fixture native"),
        "entries": [["a" * 64, "projectile_method", 0], ["b" * 64, "projectile_method", 0],
                    ["c" * 64, "projectile_lifecycle", 0], ["d" * 64, "item_dispatch", 0],
                    ["e" * 64, "projectile_interaction", 0]],
        "blobs": [{"sha256": digest, "bytes": len(payload)}],
    }
    pin_index(manifest)
    return tmp_path / "pack.zip", manifest, {digest + ".json": payload}, native


def pin_index(manifest):
    framed = json.dumps(manifest["entries"], separators=(",", ":")) + "\n" + json.dumps(manifest["blobs"], separators=(",", ":"))
    manifest["indexSha256"] = sha(framed.encode("utf-8"))


def write_pack(path, manifest, files, extra=()):
    metadata = manifest if isinstance(manifest, bytes) else json.dumps(manifest, separators=(",", ":")).encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in [("manifest.json", metadata), *files.items(), *extra]:
            archive.writestr(name, data)


def check(pack):
    path, manifest, files, native = pack
    write_pack(path, manifest, files)
    return checker.check_pack(path, "projection", native)


def test_shared_blob_preserves_all_keys_kinds_and_literal_payloads(pack):
    path, manifest, files, native = pack
    expected = Counter((key, kind, next(iter(files.values()))) for key, kind, _ in manifest["entries"])
    for rows in (manifest["entries"], list(reversed(manifest["entries"]))):
        reordered = copy.deepcopy(manifest)
        reordered["entries"] = rows
        pin_index(reordered)
        write_pack(path, reordered, files)
        actual = checker.check_pack(path, "projection", native)
        with zipfile.ZipFile(path) as archive:
            deliveries = Counter((key, kind, archive.read(actual["blobs"][index]["sha256"] + ".json"))
                                 for key, kind, index in actual["entries"])
            assert archive.namelist().count("manifest.json") == 1
            assert len(archive.infolist()) == 2
        assert deliveries == expected


@pytest.mark.parametrize("mutation", [
    lambda m: m.update(version=1),
    lambda m: m.update(minimumMethodIlBytes=2048),
    lambda m: m.update(projectionSha256="other"),
    lambda m: m.update(nativeAssemblySha256="other"),
    lambda m: m.update(decompilerSha256="other"),
    lambda m: m.update(entries=[]),
    lambda m: m.update(blobs=[]),
    lambda m: m["entries"].append(m["entries"][0]),
    lambda m: m["entries"][1].__setitem__(0, m["entries"][0][0]),
    lambda m: m["entries"][0].__setitem__(0, "../../escape"),
    lambda m: m["entries"][0].__setitem__(1, "unknown_kind"),
    lambda m: m["entries"][0].__setitem__(2, -1),
    lambda m: m["entries"][0].__setitem__(2, 1),
    lambda m: m["entries"][0].__setitem__(2, True),
    lambda m: m["entries"][0].__setitem__(2, m["entries"][1][0]),
    lambda m: m["entries"][0].append(0),
    lambda m: m["blobs"][0].__setitem__("bytes", 0),
    lambda m: m["blobs"][0].__setitem__("bytes", True),
    lambda m: m["blobs"][0].__setitem__("bytes", 4 * 1024 * 1024 + 1),
    lambda m: m["blobs"][0].__setitem__("bytes", m["blobs"][0]["bytes"] + 1),
    lambda m: m["blobs"][0].__setitem__("sha256", "x" * 64),
    lambda m: m["blobs"][0].__setitem__("sha256", "e" * 64),
    lambda m: m["blobs"].append(m["blobs"][0]),
])
def test_invalid_identity_key_or_blob_metadata_is_rejected(pack, mutation):
    mutation(pack[1])
    with pytest.raises(ValueError):
        check(pack)


@pytest.mark.parametrize("name", ["manifest.json", "payload"])
def test_duplicate_zip_names_are_rejected_even_with_matching_content(pack, name):
    path, manifest, files, native = pack
    duplicate = ("manifest.json", json.dumps(manifest).encode()) if name == "manifest.json" else next(iter(files.items()))
    with pytest.warns(UserWarning, match="Duplicate name"):
        write_pack(path, manifest, files, [duplicate])
    with pytest.raises(ValueError, match="duplicate"):
        checker.check_pack(path, "projection", native)


def test_unused_content_and_unindexed_zip_entries_are_rejected(pack):
    path, manifest, files, native = pack
    other = b'{"code":"different"}'
    files[sha(other) + ".json"] = other
    with pytest.raises(ValueError):
        check(pack)
    manifest["blobs"].append({"sha256": sha(other), "bytes": len(other)})
    with pytest.raises(ValueError, match="unreferenced"):
        check(pack)
    # Another complete key can legitimately use that blob, without merging keys.
    manifest["entries"][1][2] = 1
    pin_index(manifest)
    assert len(check(pack)["entries"]) == len(manifest["entries"])
    # A second blob row cannot recursively alias a key or repeat a blob pin.
    manifest["blobs"][1] = copy.deepcopy(manifest["blobs"][0])
    with pytest.raises(ValueError, match="duplicate"):
        check(pack)


def test_payload_corruption_does_not_change_any_alias_into_source(pack):
    name, payload = next(iter(pack[2].items()))
    pack[2][name] = payload.replace(b"source", b"broken")
    with pytest.raises(ValueError, match="entry bytes"):
        check(pack)


def test_duplicate_json_properties_are_not_silently_normalized(pack):
    path, manifest, files, native = pack
    metadata = json.dumps(manifest).encode().replace(b'"version": 2', b'"version": 1, "version": 2')
    write_pack(path, metadata, files)
    with pytest.raises(ValueError, match="duplicate JSON"):
        checker.check_pack(path, "projection", native)


def test_full_key_bound_does_not_depend_on_unique_blob_count(pack):
    pack[1]["entries"] = [[f"{index:064x}", "projectile_method", 0] for index in range(30000)]
    pin_index(pack[1])
    assert len(check(pack)["entries"]) == 30000
    pack[1]["entries"].append(["f" * 64, "projectile_method", 0])
    with pytest.raises(ValueError, match="entry index"):
        check(pack)


def test_manifest_and_archive_bounds_are_enforced_before_reading_content(pack):
    path, manifest, files, native = pack
    metadata = json.dumps(manifest).encode() + b" " * (4 * 1024 * 1024)
    write_pack(path, metadata, files)
    with pytest.raises(ValueError, match="manifest exceeds"):
        checker.check_pack(path, "projection", native)
    with path.open("wb") as stream:
        stream.truncate(128 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="archive exceeds"):
        checker.check_pack(path, "projection", native)


@pytest.mark.parametrize("mutation", [
    lambda m: (m["entries"][0].__setitem__(2, 1), m["entries"][1].__setitem__(2, 0)),
    lambda m: m["blobs"].reverse(),
    lambda m: m["entries"][0].__setitem__(1, "item_dispatch"),
    lambda m: m.pop("indexSha256"),
    lambda m: m.__setitem__("indexSha256", "0" * 64),
])
def test_valid_in_range_alias_edits_require_index_integrity(pack, mutation):
    path, manifest, files, native = pack
    other = b'{"code":"different valid projection"}'
    files[sha(other) + ".json"] = other
    manifest["blobs"].append({"sha256": sha(other), "bytes": len(other)})
    manifest["entries"][1][2] = 1
    pin_index(manifest)
    assert len(check(pack)["blobs"]) == 2
    mutation(manifest)
    # All bytes, lengths, kinds, references and used-blob checks still pass.
    with pytest.raises(ValueError, match="index integrity"):
        check(pack)
