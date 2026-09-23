"""Offline regressions for authoritative world-recipe cache boundaries."""
from __future__ import annotations

import copy

import pytest

from infini_local.core.vfx_manifest import VFX_MANIFEST_SCHEMA
from infini_local.storage import world_storage
from infini_local.web.vfx_debug_routes import _sample_data


@pytest.fixture
def recipe() -> dict:
    data = _sample_data()
    data["vfxManifest"] = {"schema": VFX_MANIFEST_SCHEMA, "slots": []}
    assert world_storage.is_deliverable_recipe_payload(data) is True
    return data


@pytest.mark.parametrize("schema_version", ["broken", [], {}, [5], "5", 5.0, 5.9, True, None])
def test_deliverability_rejects_invalid_schema_version_without_coercion(recipe, schema_version):
    recipe["schemaVersion"] = schema_version
    original = copy.deepcopy(recipe)

    assert world_storage.is_deliverable_recipe_payload(recipe) is False
    assert recipe == original


@pytest.mark.parametrize("field", ["debug", "recipeMeta"])
@pytest.mark.parametrize("value", [None, [], "broken", 7])
def test_cache_read_quarantines_malformed_metadata_without_losing_original(
    tmp_path, recipe, field, value,
):
    recipe[field] = value
    path = world_storage.world_recipe_file(tmp_path, "world", "recipe")
    world_storage.atomic_write_json(path, recipe)
    original = path.read_bytes()

    assert world_storage.read_world_recipe_cache(tmp_path, "test", "v5", "recipe", "world") is None
    assert not path.exists()
    invalid_dir = path.parent.parent / "invalid"
    payloads = [p for p in invalid_dir.glob("*.json") if not p.name.endswith(".reason.json")]
    assert len(payloads) == 1
    assert payloads[0].read_bytes() == original
    reason = world_storage.read_json_file(payloads[0].with_suffix(".reason.json"))
    assert isinstance(reason, dict)
    assert reason["reason"] == "invalid_cache_metadata"
    assert reason["details"]["invalidFields"] == [field]
    assert world_storage.read_world_recipe_cache(tmp_path, "test", "v5", "recipe", "world") is None
    assert len(list(invalid_dir.glob("*.reason.json"))) == 1


@pytest.mark.parametrize("include_metadata", [False, True])
def test_valid_recipe_roundtrip_preserves_gameplay_and_stored_bytes(tmp_path, recipe, include_metadata):
    if include_metadata:
        recipe["debug"] = {"recipeIdentityVersion": "original", "custom": "keep"}
        recipe["recipeMeta"] = {"generationDepth": 2}
    original = copy.deepcopy(recipe)
    world_storage.write_world_recipe_cache(tmp_path, "test", "recipe", "world", recipe)
    assert recipe == original
    path = world_storage.world_recipe_file(tmp_path, "world", "recipe")
    stored = path.read_bytes()

    result = world_storage.read_world_recipe_cache(tmp_path, "test", "v5", "recipe", "world")

    assert result is not None
    assert world_storage.is_deliverable_recipe_payload(result) is True
    assert result["runtimeProgram"] == original["runtimeProgram"]
    assert result["vfxManifest"] == original["vfxManifest"]
    assert result["recipeMeta"]["worldId"] == "world"
    assert result["recipeMeta"]["worldScoped"] is True
    assert result["debug"]["cacheHit"] == "world_file"
    assert result["debug"]["cacheScope"] == "world"
    assert result["debug"]["recipeIdentityVersion"] == ("original" if include_metadata else "v5")
    if include_metadata:
        assert result["recipeMeta"]["generationDepth"] == 2
        assert result["debug"]["custom"] == "keep"
    assert path.read_bytes() == stored
    assert not (path.parent.parent / "invalid").exists()


@pytest.mark.parametrize("content", [b"{broken", b"{}", b"[]", b"\xff"])
def test_unreadable_recipe_quarantine_still_preserves_bytes(tmp_path, content):
    path = world_storage.world_recipe_file(tmp_path, "world", "recipe")
    path.parent.mkdir(parents=True)
    path.write_bytes(content)

    assert world_storage.read_world_recipe_cache(tmp_path, "test", "v5", "recipe", "world") is None
    assert not path.exists()
    reasons = list((path.parent.parent / "invalid").glob("*.reason.json"))
    assert len(reasons) == 1
    reason = world_storage.read_json_file(reasons[0])
    assert isinstance(reason, dict)
    assert reason["reason"] == "json_unreadable_or_empty"
    assert (reasons[0].parent / reason["payloadFile"]).read_bytes() == content


@pytest.mark.parametrize("schema_version", ["broken", [5], "5", 5.9])
def test_combine_cache_lookup_quarantines_invalid_schema_offline(tmp_path, monkeypatch, recipe, schema_version):
    from infini_local.storage import world_recipe_runtime
    from infini_local.pipelines.combine_pipeline import combine_cache_lookup

    monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", tmp_path)
    payload = {"worldId": "world", "itemA": {"type": 1}, "itemB": {"type": 2}}
    key, cached = combine_cache_lookup(payload)
    assert cached is None
    recipe["schemaVersion"] = schema_version
    path = world_storage.world_recipe_file(tmp_path, "world", key)
    world_storage.atomic_write_json(path, recipe)
    stored = path.read_bytes()

    assert combine_cache_lookup(payload) == (key, None)
    assert not path.exists()
    reasons = list((path.parent.parent / "invalid").glob("*.reason.json"))
    assert len(reasons) == 1
    reason = world_storage.read_json_file(reasons[0])
    assert isinstance(reason, dict)
    assert reason["reason"] == "low_level_runtime_contract_invalid"
    assert (reasons[0].parent / reason["payloadFile"]).read_bytes() == stored
