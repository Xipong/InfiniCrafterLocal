from __future__ import annotations
from infini_local.core import asset_files

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from infini_local.storage import image_store as store
from infini_local.services import asset_sync_service as sync


def data(world="world-1", item="item-1", name="Жезл: Света/Земли", world_name="Мой мир"):
    return {"id": item, "name": name, "recipeMeta": {"worldId": world, "worldName": world_name}}


def png(path, color=(30, 120, 170, 255)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16), color).save(path)
    return path


def publish(root, item, source, role="item"):
    return store.publish(root, item, role, b"exact authored identity", source)


def test_one_final_and_safe_unicode_human_directories(tmp_path):
    root = tmp_path / "images"
    source = png(tmp_path / "raw.png")
    result = publish(root, data(), source)
    assert result.parent.name == "final"
    assert result.name.startswith("item--")
    assert "Жезл_ Света_Земли--" in str(result)
    assert "Мой мир--" in str(result)
    assert asset_files.asset_filename_from_path(result) == result.name
    assert store.resolve(root, result.name) == result
    assert publish(root, data(), source) == result
    assert list(root.rglob("*.png")) == [result]
    entry = json.loads(store._index_path(root, result.name).read_text())
    assert entry["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert entry["path"] == result.relative_to(root).as_posix()


def test_rename_and_case_preserve_identity_without_duplicate_finals(tmp_path):
    root = tmp_path / "images"
    source = png(tmp_path / "raw.png")
    before = publish(root, data(), source)
    after = publish(root, data(name="Новый ЖЕЗЛ", world_name="Новый МИР"), source)
    assert before == after
    assert json.loads((after.parent.parent / ".identity.json").read_text())["name"] == "Новый ЖЕЗЛ"
    assert list(root.rglob("*.png")) == [before]


@pytest.mark.parametrize("world,item,role", [("World-1", "item-1", "item"), ("world-1", "Item-1", "item"),
    ("world-1", "item-1", "impact"), ("world-1", "item-1", "ITEM")])
def test_exact_scope_and_role_ids_never_alias_even_with_same_safe_label(tmp_path, world, item, role):
    root = tmp_path / "images"
    source = png(tmp_path / "raw.png")
    first = publish(root, data(), source)
    second = publish(root, data(world, item), source, role)
    assert first != second
    assert first.name.lower() != second.name.lower()


def test_different_unsafe_ids_with_same_label_cannot_collide(tmp_path):
    root = tmp_path / "images"
    source = png(tmp_path / "raw.png")
    first = publish(root, data(item="a/b", name="CON"), source)
    second = publish(root, data(item="a:b", name="CON"), source)
    assert first != second
    assert first.parent.parent.name.startswith("CON--")  # not the reserved device basename


def test_parallel_renames_share_one_identity_directory_and_final(tmp_path):
    root = tmp_path / "images"
    source = png(tmp_path / "raw.png")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: publish(root, data(name=f"Название {i}"), source), range(24)))
    assert len(set(results)) == 1
    assert len(list(root.rglob("*.png"))) == 1


def test_unknown_identity_directory_and_incomplete_png_are_preserved(tmp_path):
    root = tmp_path / "images"
    parent = root / "worlds"
    collision = parent / ("Мой мир--" + store._digest("world-1")[:16])
    collision.mkdir(parents=True)
    note = collision / "user.txt"
    note.write_text("keep")
    source = png(tmp_path / "raw.png")
    with pytest.raises(OSError, match="ownership conflict"):
        publish(root, data(), source)
    assert note.read_text() == "keep"
    source.write_bytes(b"not png")
    with pytest.raises(ValueError, match="incomplete"):
        publish(root, data(), source)


@pytest.mark.parametrize("relative", ["../secret.png", "worlds/x/diagnostics/final/secret.png", "/tmp/secret.png"])
def test_index_never_serves_outside_root_or_diagnostics(tmp_path, relative):
    root = tmp_path / "images"
    final = publish(root, data(), png(tmp_path / "raw.png"))
    path = store._index_path(root, final.name)
    entry = json.loads(path.read_text())
    entry["path"] = relative
    path.write_text(json.dumps(entry))
    assert store.resolve(root, final.name) is None


def test_diagnostic_png_is_not_discovered_by_public_basename(tmp_path):
    root = tmp_path / "images"
    private = store.diagnostics_directory(root, data(), "item")
    raw = png(private / "provider_raw.png")
    assert sync.find_asset_file(raw.name, sprite_dir=root, world_recipes_dir=tmp_path / "recipes") is None


def test_symlink_final_folder_cannot_redirect_publication(tmp_path):
    root = tmp_path / "images"
    item = store.item_directory(root, data())
    outside = tmp_path / "outside"
    outside.mkdir()
    (item / "final").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError, match="escapes"):
        publish(root, data(), png(tmp_path / "raw.png"))
    assert list(outside.iterdir()) == []


def test_delivered_wire_uses_index_basename_without_long_machine_path(tmp_path, monkeypatch):
    from infini_local.core import config_bootstrap
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery
    root = tmp_path.joinpath(*(["длинный каталог"] * 9), "images")
    item = data()
    final = publish(root, item, png(tmp_path / "raw.png"))
    item["visual"] = {"spritePath": str(final), "spriteRawPath": "private-original-raw.png"}
    item["runtimeProgram"] = {"entities": [{"id": "body", "visual": {"spritePath": str(final)}}]}
    monkeypatch.setattr(config_bootstrap, "SPRITE_DIR", root)
    outgoing = sanitize_recipe_for_delivery(item)
    assert len(str(final)) > 260
    assert outgoing["visual"]["spritePath"] == final.name
    assert outgoing["runtimeProgram"]["entities"][0]["visual"]["spritePath"] == final.name
    assert outgoing["visual"]["spriteRawPath"] == "private-original-raw.png"
    assert item["visual"]["spritePath"] == str(final)


def test_changed_indexed_bytes_never_fall_back_to_legacy_shadow(tmp_path):
    root = tmp_path / "images"
    final = publish(root, data(), png(tmp_path / "source.png"))
    original = final.read_bytes()
    (root / final.name).write_bytes(original)
    final.write_bytes(b"x" * len(original))
    assert sync.find_asset_file(final.name, sprite_dir=root, world_recipes_dir=tmp_path / "recipes") is None


@pytest.mark.parametrize("source,expected", [
    ("C:\\Users\\Имя\\images", "\\\\?\\C:\\Users\\Имя\\images"),
    ("\\\\server\\share\\images", "\\\\?\\UNC\\server\\share\\images"),
    ("\\\\?\\C:\\images", "\\\\?\\C:\\images"),
    ("\\\\?\\UNC\\server\\share\\images", "\\\\?\\UNC\\server\\share\\images"),
])
def test_windows_long_path_normalization_does_not_change_wire_names(source, expected):
    from infini_local.core.app_paths import windows_extended_path
    assert windows_extended_path(source) == expected
    assert asset_files.asset_filename_from_path(expected + "\\item--digest.png") == "item--digest.png"


@pytest.mark.parametrize("query", ["hash", "file", "name"])
def test_asset_queries_resolve_current_indexed_final(tmp_path, query):
    root = tmp_path / "images"
    final = publish(root, data(), png(tmp_path / "source.png"))
    name = sync.safe_asset_file_from_query({query: [final.stem]}, sprite_dir=root, world_recipes_dir=tmp_path / "recipes")
    assert name == final.name
    assert sync.find_asset_file(name, sprite_dir=root, world_recipes_dir=tmp_path / "recipes") == final


@pytest.mark.parametrize("segment", ["Diagnostics", "DIAGNOSTICS", "diagnostics"])
def test_index_never_exposes_case_variant_private_diagnostics(tmp_path, segment):
    root = tmp_path / "images"
    final = publish(root, data(), png(tmp_path / "source.png"))
    entry_path = store._index_path(root, final.name)
    entry = json.loads(entry_path.read_text())
    private = root / segment / "final" / final.name
    private.parent.mkdir(parents=True)
    private.write_bytes(final.read_bytes())
    entry["path"] = private.relative_to(root).as_posix()
    entry_path.write_text(json.dumps(entry))
    assert store.resolve(root, final.name) is None
    assert sync.find_asset_file(final.name, sprite_dir=root, world_recipes_dir=tmp_path / "recipes") is None


@pytest.mark.parametrize("malformed", [
    {"visual": []}, {"runtimeProgram": []}, {"runtimeProgram": {"entities": [None, [], "invalid"]}},
    {"runtimeProgram": {"entities": [{"visual": []}]}}, {"vfxManifest": []},
    {"vfxManifest": {"assets": [None, [], "invalid"]}},
])
def test_path_projection_leaves_invalid_payload_for_canonical_rejection(tmp_path, malformed):
    before = copy.deepcopy(malformed)
    store.compact_delivery_paths(tmp_path, malformed)
    assert list(store.runtime_image_fields(malformed)) == []
    assert malformed == before


@pytest.mark.parametrize("folder", ["images", "sprites", "asset_cache", "recipes"])
def test_unindexed_png_is_not_served_or_adopted(tmp_path, folder):
    root = tmp_path / "images"
    source = png(tmp_path / folder / "unindexed.png")
    before = source.read_bytes()
    assert sync.find_asset_file(source.name, sprite_dir=root, world_recipes_dir=tmp_path / "recipes") is None
    assert source.read_bytes() == before
    assert not (root / ".index").exists()


def test_interrupted_index_publication_can_retry_without_duplicate_or_early_delivery(tmp_path, monkeypatch):
    root = tmp_path / "images"
    raw = png(tmp_path / "source.png")
    atomic_json = store._atomic_json
    def denied(path, value):
        if path.parent.name == ".index":
            raise PermissionError("index unavailable")
        return atomic_json(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(store, "_atomic_json", denied)
        with pytest.raises(PermissionError):
            publish(root, data(), raw)
    pending, = root.rglob("*.png")
    assert store.resolve(root, pending.name) is None
    final = publish(root, data(), raw)
    assert final == pending and store.resolve(root, final.name) == final
    assert list(root.rglob("*.png")) == [final]
    assert raw.read_bytes() == final.read_bytes()


def test_publisher_refuses_png_over_transfer_budget_without_creating_store(tmp_path, monkeypatch):
    root = tmp_path / "images"
    raw = png(tmp_path / "source.png")
    monkeypatch.setattr(asset_files, "MAX_ASSET_RESPONSE_BYTES", raw.stat().st_size - 1)
    with pytest.raises(ValueError, match="byte limit"):
        publish(root, data(), raw)
    assert not root.exists()
