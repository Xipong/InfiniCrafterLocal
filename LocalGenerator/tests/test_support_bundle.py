from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import zlib

import pytest


spec = importlib.util.spec_from_file_location(
    "support_bundle", Path(__file__).resolve().parents[2] / "tools/diagnostics/export_support_bundle.py"
)
assert spec is not None and spec.loader is not None
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _png(*metadata):
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)) + b"".join(metadata) + _chunk(b"IDAT", zlib.compress(b"\0\0\0\0\xff")) + _chunk(b"IEND", b"")


def _write(cache, name, value):
    path = cache / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "cache"
    for name, data in {
        "events.ndjson": b'{"message":"first"}\n{"message":"first"}\n',
        "events.ndjson.1": b'{"message":"older"}\n',
        "prompt_trace.ndjson": ('{"prompt":"' + "long full history " * 10000 + 'TAIL"}\n').encode(),
        "pipeline_trace.ndjson": b'{"kind":"error","attempt":2}\n',
        "sdcpp_server.log": b"image backend attempt failed\n",
        "stage_requests/request.json": b'{"messages":[{"role":"user","content":"input"}]}',
        "transport_artifacts/stream.txt": b'{"delta":"output"}\n[DONE]',
        "world_recipes/world_1/recipe.json": b'{"id":"g_1"}',
        "sprites/g_1.png": _png(_chunk(b"tEXt", b"infini.chroma-key\0{\"mode\":\"test\"}")),
        "image-diagnostics/image-1/attempt-0/raw.png": _png(_chunk(b"tEXt", b"parameters\0full prompt")),
        "config.env": b"INFINI_SECRET=not-for-export",
        "codex-auth.json": b'{"access_token":"not-for-export"}',
        "events.ndjson.lock": b"\0",
    }.items():
        _write(root, name, data)
    return root


def _files(root):
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("full", [False, True])
def test_roundtrip_keeps_all_history_duplicates_and_original_pixels(cache, tmp_path, full):
    before = _files(cache)
    output = tmp_path / "support.tar.xz"
    result = bundle.export_bundle(cache, output, include_images=full)
    manifest = bundle.verify_bundle(output)
    with tarfile.open(output) as archive:
        delivered = {member.name.removeprefix("cache/"): archive.extractfile(member).read()
                     for member in archive if member.name != bundle.MANIFEST}
    names = {"events.ndjson", "events.ndjson.1", "prompt_trace.ndjson", "pipeline_trace.ndjson",
             "sdcpp_server.log", "stage_requests/request.json", "transport_artifacts/stream.txt",
             "world_recipes/world_1/recipe.json", "sprites/g_1.png"}
    if full:
        names.add("image-diagnostics/image-1/attempt-0/raw.png")
    expected = {name: before[name] for name in names}
    assert delivered == expected
    assert delivered["events.ndjson"].count(b"first") == 2
    assert delivered["prompt_trace.ndjson"].endswith(b'TAIL"}\n')
    assert _files(cache) == before
    assert result["omittedImages"] == (0 if full else 1)
    assert result["files"] == len(expected)
    assert result["redactedFiles"] == 0
    assert len(manifest["included"]) == len(expected)
    assert output.stat().st_size < len(before["prompt_trace.ndjson"]) // 10
    for entry in manifest["included"]:
        assert entry["sourceSha256"] == entry["sha256"] == hashlib.sha256(delivered[entry["path"].removeprefix("cache/")]).hexdigest()


def test_export_redacts_known_and_escaped_credentials_but_keeps_original(cache, tmp_path, monkeypatch):
    token = "sk-example-secret-123456789"
    known = "plain-secret-from-environment"
    monkeypatch.setenv("INFINI_LLM_API_KEY", known)
    raw = json.dumps({"token": token, "message": known, "escaped": "\\u0073k-example-secret-123456789"}).encode()
    _write(cache, "stage_requests/secret.json", raw)
    output = tmp_path / "support.tar.xz"
    result = bundle.export_bundle(cache, output)
    manifest = bundle.verify_bundle(output)
    with tarfile.open(output) as archive:
        clean = archive.extractfile("cache/stage_requests/secret.json").read()
        assert token.encode() not in clean and known.encode() not in clean
        assert "[REDACTED]" in json.loads(clean)["escaped"]
        assert all("auth" not in member.name and "config.env" not in member.name for member in archive)
    assert (cache / "stage_requests/secret.json").read_bytes() == raw
    assert result["redactedFiles"] == 1
    entry = next(entry for entry in manifest["included"] if entry["path"].endswith("secret.json"))
    assert entry["redacted"] and entry["sourceSha256"] != entry["sha256"]


def test_redaction_cannot_turn_valid_json_into_invalid_json(cache, tmp_path, monkeypatch):
    monkeypatch.setenv("INFINI_LLM_API_KEY", "123456789")
    raw = b'{"value":123456789}'
    _write(cache, "stage_requests/numeric.json", raw)
    output = tmp_path / "support.tar.xz"
    with pytest.raises(ValueError, match="invalidate JSON"):
        bundle.export_bundle(cache, output)
    assert not output.exists()
    assert (cache / "stage_requests/numeric.json").read_bytes() == raw


def test_sensitive_filename_is_not_published_in_manifest(cache, tmp_path):
    _write(cache, "image-diagnostics/sk-example-secret-123456789.png", _png())
    output = tmp_path / "support.tar.xz"
    with pytest.raises(ValueError, match="filename contains credentials"):
        bundle.export_bundle(cache, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", [b"tEXt", b"zTXt", b"iTXt", b"iTXt-compressed"])
@pytest.mark.parametrize("sensitive", [False, True])
def test_png_metadata_is_inspected_without_changing_bytes(cache, tmp_path, kind, sensitive):
    text = b"sk-test-secret-123456789" if sensitive else "legitimate image prompt ж".encode()
    if kind == b"tEXt":
        body = b"parameters\0" + text
    elif kind == b"zTXt":
        body = b"parameters\0\0" + zlib.compress(text)
    else:
        compressed = kind.endswith(b"-compressed")
        body = b"parameters\0" + bytes([int(compressed), 0]) + b"\0\0" + (zlib.compress(text) if compressed else text)
        kind = b"iTXt"
    raw = _png(_chunk(kind, body))
    _write(cache, "sprites/g_1.png", raw)
    output = tmp_path / "support.tar.xz"
    if sensitive:
        with pytest.raises(ValueError, match="credentials"):
            bundle.export_bundle(cache, output)
        assert not output.exists()
        assert not list(tmp_path.glob(".support-*"))
    else:
        bundle.export_bundle(cache, output)
        with tarfile.open(output) as archive:
            assert archive.extractfile("cache/sprites/g_1.png").read() == raw
    assert (cache / "sprites/g_1.png").read_bytes() == raw


@pytest.mark.parametrize("suffix", [b"private trailing text", b"\0"])
def test_png_trailing_private_bytes_are_refused(cache, tmp_path, suffix):
    _write(cache, "sprites/g_1.png", _png() + suffix)
    with pytest.raises(ValueError, match="trailing"):
        bundle.export_bundle(cache, tmp_path / "support.tar.xz")


def test_png_compression_bomb_and_uninspected_metadata_are_refused(cache, tmp_path):
    for chunk in (_chunk(b"zTXt", b"comment\0\0" + zlib.compress(b"x" * (3 * 1024 * 1024))),
                  _chunk(b"eXIf", b"private metadata")):
        _write(cache, "sprites/g_1.png", _png(chunk))
        with pytest.raises(ValueError):
            bundle.export_bundle(cache, tmp_path / "support.tar.xz")
        assert not (tmp_path / "support.tar.xz").exists()


def test_never_follows_symlinks_or_overwrites_output(cache, tmp_path):
    secret = tmp_path / "private.txt"
    secret.write_text("private outside cache")
    (cache / "stage_requests/linked.json").symlink_to(secret)
    (cache / "world_recipes/linked").symlink_to(tmp_path, target_is_directory=True)
    output = tmp_path / "support.tar.xz"
    bundle.export_bundle(cache, output)
    with tarfile.open(output) as archive:
        assert not any("linked" in member.name for member in archive)
    saved = output.read_bytes()
    with pytest.raises(ValueError, match="new file"):
        bundle.export_bundle(cache, output)
    assert output.read_bytes() == saved and secret.read_text() == "private outside cache"
    with pytest.raises(ValueError, match="outside"):
        bundle.export_bundle(cache, cache / "support.tar.xz")


def test_cache_mutation_during_export_fails_without_publishing(cache, tmp_path, monkeypatch):
    real_add = bundle._add
    changed = False
    def mutate(archive, name, data):
        nonlocal changed
        real_add(archive, name, data)
        if not changed:
            changed = True
            with (cache / "events.ndjson").open("ab") as handle:
                handle.write(b'{"message":"new write"}\n')
    monkeypatch.setattr(bundle, "_add", mutate)
    output = tmp_path / "support.tar.xz"
    with pytest.raises(ValueError, match="cache changed"):
        bundle.export_bundle(cache, output)
    assert not output.exists() and not list(tmp_path.glob(".support-*"))


def test_verification_rejects_missing_duplicate_and_modified_members(cache, tmp_path):
    original = tmp_path / "support.tar.xz"
    bundle.export_bundle(cache, original)
    with tarfile.open(original) as archive:
        records = [(member.name, archive.extractfile(member).read()) for member in archive]
    for mode in ("missing", "duplicate", "modified", "duplicate-null-manifest"):
        target = tmp_path / f"{mode}.tar.xz"
        rows = records[1:] if mode == "missing" else records + records[:1] if mode == "duplicate" else [(records[0][0], b"modified"), *records[1:]]
        if mode == "duplicate-null-manifest":
            rows = [(bundle.MANIFEST, b"null"), *records]
        with tarfile.open(target, "w:xz") as archive:
            for name, data in rows:
                bundle._add(archive, name, data)
        with pytest.raises(ValueError):
            bundle.verify_bundle(target)


@pytest.mark.parametrize("include_images", [False, True])
def test_persistent_image_store_is_included_without_unknown_or_private_core_files(cache, tmp_path, include_images):
    images = tmp_path / "images"
    final_name = "worlds/Мир--123/Жезл--456/final/item--digest.png"
    raw_name = "worlds/Мир--123/Жезл--456/diagnostics/item-1/attempt-0/raw.png"
    _write(images, final_name, _png())
    _write(images, raw_name, _png())
    _write(images, ".index/private.json", b'{"not":"exported"}')
    _write(images, "unknown.txt", b'leave unknown data alone')
    output = tmp_path / "with-images.tar.xz"
    before = {p: p.read_bytes() for p in images.rglob("*") if p.is_file()}
    bundle.export_bundle(cache, output, image_root=images, include_images=include_images)
    manifest = bundle.verify_bundle(output)
    included = {row["path"] for row in manifest["included"]}
    assert "images/" + final_name in included
    assert ("images/" + raw_name in included) is include_images
    assert "images/.index/private.json" not in included
    assert "images/unknown.txt" not in included
    assert all(p.read_bytes() == raw for p, raw in before.items())
