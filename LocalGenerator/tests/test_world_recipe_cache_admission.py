"""Admission of whole world-cache records, through their real offline consumers."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from infini_local.core.vfx_manifest import _compile_manifest
from infini_local.pipelines import combine_pipeline, visual_delivery_gate
from infini_local.qa.live_no_image_fixture import hydrate_no_image_fixture_assets, write_no_image_fixture_png
from infini_local.services.combine_endpoint import handle_combine_request
from infini_local.storage import world_recipe_runtime, world_storage
from infini_local.web.vfx_debug_routes import _sample_data


@pytest.fixture
def cache_record(tmp_path, monkeypatch):
    root = tmp_path / "worlds"
    monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", root)
    monkeypatch.setattr(visual_delivery_gate, "WORLD_RECIPES_DIR", root)
    monkeypatch.setattr(visual_delivery_gate, "SPRITE_DIR", tmp_path / "sprites")
    data = _sample_data()
    data["visual"] = {"preferredCanvasSize": 32}
    hydrate_no_image_fixture_assets(data, write_no_image_fixture_png(tmp_path / "sprites" / "offline.png"))
    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, "offline-cache-admission")
    assert world_storage.is_deliverable_recipe_payload(data)
    assert combine_pipeline._cached_payload_report(data)["ok"]
    request = {
        "worldId": "11111111-1111-1111-1111-111111111111", "cacheOnly": True,
        "itemA": {"id": 3507, "name": "Copper Shortsword", "fullName": "Terraria/CopperShortsword"},
        "itemB": {"id": 8, "name": "Torch", "fullName": "Terraria/Torch"},
    }
    key, cached = combine_pipeline.combine_cache_lookup(request)
    assert cached is None
    world_recipe_runtime.cache_put(key, request["itemA"], request["itemB"], data, request["worldId"])
    path = world_recipe_runtime.world_recipe_file(request["worldId"], key)
    committed = world_storage.read_json_file(path)
    assert committed is not None
    return root, request, key, path, committed


def _cache_only_endpoint(request):
    responses = []
    handle_combine_request(
        request, app_version="storage-regression",
        combine_cache_lookup=combine_pipeline.combine_cache_lookup,
        sanitize_recipe_for_delivery=world_storage.sanitize_recipe_for_delivery,
        combine=lambda _: pytest.fail("cache-only endpoint must not generate"),
        trace_event=lambda *_: None,
        json=lambda data: responses.append((200, data)),
        json_status=lambda code, data: responses.append((code, data)),
    )
    assert len(responses) == 1
    return responses[0]


def _assert_whole_record_quarantine(path: Path, raw: bytes, reason: str):
    assert not path.exists(), "rejected record remained an active recipe"
    invalid = path.parent.parent / "invalid"
    reasons = list(invalid.glob("*.reason.json"))
    originals = [p for p in invalid.glob("*.json") if not p.name.endswith(".reason.json")]
    assert len(reasons) == len(originals) == 1
    receipt = json.loads(reasons[0].read_text(encoding="utf-8"))
    assert receipt["reason"] == reason
    assert (invalid / receipt["payloadFile"]).read_bytes() == raw
    assert originals[0].read_bytes() == raw
    return receipt


@pytest.mark.parametrize("identity", ["world", "recipe", "world-and-recipe"])
def test_cache_only_endpoint_quarantines_contradictory_committed_identity(cache_record, identity):
    root, request, key, target, good = cache_record
    assert _cache_only_endpoint(request)[0] == 200
    foreign_request = copy.deepcopy(request)
    if "world" in identity:
        foreign_request["worldId"] = "22222222-2222-2222-2222-222222222222"
    if "recipe" in identity:
        foreign_request["itemB"] = {"id": 9, "name": "Wood", "fullName": "Terraria/Wood"}
    foreign_key, _ = combine_pipeline.combine_cache_lookup(foreign_request)
    world_recipe_runtime.cache_put(
        foreign_key, foreign_request["itemA"], foreign_request["itemB"], good, foreign_request["worldId"],
    )
    source = world_recipe_runtime.world_recipe_file(foreign_request["worldId"], foreign_key)
    foreign_bytes = source.read_bytes()
    target.write_bytes(foreign_bytes)  # misplaced exact durable bytes, not a migration

    code, result = _cache_only_endpoint(request)

    assert code == 404, "contradictory durable identity was delivered as a cache hit"
    assert result["status"] == "cache_miss" and result["recipeKey"] == key
    receipt = _assert_whole_record_quarantine(target, foreign_bytes, "cache_identity_mismatch")
    stored = json.loads(foreign_bytes)
    expected = {}
    if stored["recipeKey"] != key:
        expected["recipeKey"] = {"expected": key, "stored": stored["recipeKey"]}
    if stored["recipeMeta"]["worldId"] != request["worldId"]:
        expected["recipeMeta.worldId"] = {"expected": request["worldId"], "stored": stored["recipeMeta"]["worldId"]}
    assert receipt["details"]["identityMismatches"] == expected
    assert source.read_bytes() == foreign_bytes
    assert _cache_only_endpoint(request)[0] == 404
    assert len(list((target.parent.parent / "invalid").glob("*.reason.json"))) == 1


def test_default_debug_reroll_refuses_unsupported_runtime_before_vfx_stage(cache_record, monkeypatch):
    from infini_local.web import vfx_debug_routes

    _, request, key, path, data = cache_record
    data["runtimeProgram"]["schema"] = "private-unsupported-runtime-schema"
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()
    stages = []

    def forbidden_stage(*_args, **_kwargs):
        stages.append("vfx")
        raise AssertionError("default debug path started VFX for non-admitted runtime")

    monkeypatch.setattr(vfx_debug_routes, "attach_vfx_manifest", forbidden_stage)
    routes = vfx_debug_routes.VfxDebugRoutes(
        app_version="storage-regression",
        normalize_world_id_from_payload=world_recipe_runtime.normalize_world_id_from_payload,
        read_world_recipe_cache=world_recipe_runtime.read_world_recipe_cache,
        write_world_recipe_cache=lambda *_a, **_k: pytest.fail("invalid gameplay must not be rewritten"),
        final_normalize=lambda _: pytest.fail("invalid gameplay must not be normalized"),
    )
    with pytest.raises(FileNotFoundError, match="recipe not found"):
        routes.reroll_cached_manifest({"recipeKey": key, "worldId": request["worldId"]})
    assert stages == []
    _assert_whole_record_quarantine(path, raw, "low_level_runtime_contract_invalid")


@pytest.mark.parametrize("corruption", ["runtime-schema", "binding", "schema-version", "fallback", "vfx", "asset"])
def test_optional_accepting_validator_cannot_replace_canonical_admission(cache_record, corruption):
    _, request, key, path, data = cache_record
    if corruption == "runtime-schema":
        data["runtimeProgram"]["schema"] = "unsupported"
    elif corruption == "binding":
        data["runtimeProgram"]["bindings"][0]["id"] = ""
    elif corruption == "schema-version":
        data["schemaVersion"] = True
    elif corruption == "fallback":
        data["sourceMode"] = "fallback_test"
    elif corruption == "vfx":
        data["vfxManifest"]["schema"] = "unsupported"
    else:
        Path(data["visual"]["spritePath"]).unlink()
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()
    called = []

    def accepts_everything(delivered):
        called.append(delivered)
        return {"ok": True, "errors": []}

    result = world_recipe_runtime.read_world_recipe_cache(
        key, request["worldId"], validate_payload=accepts_everything,
    )

    assert result is None, "optional accepting caller bypassed canonical storage admission"
    assert called == [], "canonical refusal must precede caller-specific work"
    _assert_whole_record_quarantine(path, raw, "low_level_runtime_contract_invalid")


@pytest.mark.parametrize("field,value", [
    ("recipeKey", None), ("recipeMeta.worldId", None),
    ("recipeMeta.worldId", ""), ("recipeKey", False),
    ("recipeMeta.worldId", []), ("recipeKey", " world "),
])
def test_explicit_invalid_identity_is_not_historical_absence(cache_record, field, value):
    _, request, key, path, data = cache_record
    owner = data["recipeMeta"] if "." in field else data
    owner[field.rsplit(".", 1)[-1]] = value
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()

    result = world_recipe_runtime.read_world_recipe_cache(
        key, request["worldId"],
        validate_payload=lambda _: pytest.fail("contradictory identity reached a caller validator"),
    )

    assert result is None
    receipt = _assert_whole_record_quarantine(path, raw, "cache_identity_mismatch")
    assert receipt["details"]["identityMismatches"] == {
        field: {"expected": request["worldId"] if "." in field else key, "stored": value},
    }


@pytest.mark.parametrize("omitted", ["recipeKey", "worldId", "recipeMeta", "all-metadata"])
def test_missing_current_cache_scope_is_refused_without_guessing_identity(cache_record, omitted):
    _, request, key, path, data = cache_record
    if omitted in {"recipeKey", "all-metadata"}:
        data.pop("recipeKey")
    if omitted == "worldId":
        data["recipeMeta"].pop("worldId")
    elif omitted in {"recipeMeta", "all-metadata"}:
        data.pop("recipeMeta")
    if omitted == "all-metadata":
        data.pop("debug", None)
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()
    snapshots = []

    def caller(delivered):
        snapshots.append(copy.deepcopy(delivered))
        return combine_pipeline._cached_payload_report(delivered)

    delivered = world_recipe_runtime.read_world_recipe_cache(key, request["worldId"], validate_payload=caller)

    assert delivered is None and snapshots == []
    receipt = _assert_whole_record_quarantine(path, raw, "cache_identity_mismatch")
    expected = {}
    if omitted in {"recipeKey", "all-metadata"}:
        expected["recipeKey"] = {"expected": key, "stored": None}
    if omitted in {"worldId", "recipeMeta", "all-metadata"}:
        expected["recipeMeta.worldId"] = {"expected": request["worldId"], "stored": None}
    assert receipt["details"]["identityMismatches"] == expected
    assert _cache_only_endpoint(request)[0] == 404


def test_current_writer_supplies_exact_cache_scope_and_reader_preserves_bytes(cache_record):
    _, request, key, path, committed = cache_record
    raw = path.read_bytes()
    assert committed["recipeKey"] == key
    assert committed["recipeMeta"]["worldId"] == request["worldId"]
    delivered = world_recipe_runtime.read_world_recipe_cache(key, request["worldId"])
    assert delivered is not None
    assert delivered["recipeKey"] == key
    assert delivered["recipeMeta"]["worldId"] == request["worldId"]
    for field in ("runtimeProgram", "vfxManifest", "visual", "parentA", "parentB", "id", "name"):
        assert delivered[field] == committed[field]
    assert path.read_bytes() == raw
    assert not (path.parent.parent / "invalid").exists()
    assert _cache_only_endpoint(request)[0] == 200


@pytest.mark.parametrize("validator", ["none", "accepts", "rejects"])
def test_caller_validator_only_adds_checks_to_admitted_record(cache_record, validator):
    _, request, key, path, data = cache_record
    raw = path.read_bytes()
    snapshots = []

    def check(delivered):
        snapshots.append(copy.deepcopy(delivered))
        return {"ok": validator == "accepts", "errors": ["caller_specific_refusal"] if validator == "rejects" else []}

    delivered = world_recipe_runtime.read_world_recipe_cache(
        key, request["worldId"], validate_payload=None if validator == "none" else check,
    )

    if validator == "rejects":
        assert delivered is None and len(snapshots) == 1
        receipt = _assert_whole_record_quarantine(path, raw, "low_level_runtime_contract_invalid")
        assert receipt["details"]["errors"] == ["caller_specific_refusal"]
        assert receipt["details"]["runtimeReady"] is True
        assert receipt["details"]["assetsReady"] is True
    else:
        assert delivered is not None
        assert snapshots == ([] if validator == "none" else [delivered])
        assert delivered["runtimeProgram"] == data["runtimeProgram"]
        assert path.read_bytes() == raw
        assert not (path.parent.parent / "invalid").exists()


@pytest.mark.parametrize("rejection", ["identity", "runtime", "asset"])
def test_canonical_refusal_survives_quarantine_io_failure(cache_record, monkeypatch, rejection):
    from infini_local.storage import trace_runtime

    _, request, key, path, data = cache_record
    if rejection == "identity":
        data["recipeMeta"]["worldId"] = "foreign"
    elif rejection == "runtime":
        data["runtimeProgram"]["schema"] = "unsupported"
    else:
        Path(data["visual"]["spritePath"]).unlink()
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()
    events = []

    def refuse(*_args, **_kwargs):
        raise PermissionError("offline quarantine denied")

    monkeypatch.setattr(world_storage, "quarantine_world_recipe_cache", refuse)
    monkeypatch.setattr(trace_runtime, "trace_event", lambda *event: events.append(event))

    assert world_recipe_runtime.read_world_recipe_cache(key, request["worldId"]) is None
    assert path.read_bytes() == raw
    assert len(events) == 1 and events[0][0] == "warn"
    assert "could not quarantine" in events[0][2]
    assert events[0][3]["reason"] == ("cache_identity_mismatch" if rejection == "identity" else "low_level_runtime_contract_invalid")
    assert _cache_only_endpoint(request)[0] == 404


def test_default_debug_positive_control_uses_admitted_gameplay(cache_record, monkeypatch):
    from infini_local.web import vfx_debug_routes

    _, request, key, path, data = cache_record
    observed = []

    def offline_vfx_stage(admitted, stage_key):
        assert stage_key == key and world_storage.is_deliverable_recipe_payload(admitted)
        observed.append(copy.deepcopy(admitted))
        return admitted  # identity-only offline stage, no model or generation

    monkeypatch.setattr(vfx_debug_routes, "attach_vfx_manifest", offline_vfx_stage)
    routes = vfx_debug_routes.VfxDebugRoutes(
        app_version="storage-regression",
        normalize_world_id_from_payload=world_recipe_runtime.normalize_world_id_from_payload,
        read_world_recipe_cache=world_recipe_runtime.read_world_recipe_cache,
        write_world_recipe_cache=world_recipe_runtime.write_world_recipe_cache,
        final_normalize=world_storage.sanitize_recipe_for_delivery,
    )
    result = routes.reroll_cached_manifest({"recipeKey": key, "worldId": request["worldId"], "returnData": True})

    assert result["ok"] and len(observed) == 1
    committed = world_storage.read_json_file(path)
    assert committed is not None
    for field in ("runtimeProgram", "vfxManifest", "visual", "recipeKey", "parentA", "parentB"):
        assert result["data"][field] == committed[field] == data[field]
    assert _cache_only_endpoint(request)[0] == 200


def test_unknown_root_cannot_be_cached_or_replayed(cache_record):
    _, request, key, path, good = cache_record
    assert _cache_only_endpoint(request)[0] == 200
    corrupt = copy.deepcopy(good)
    corrupt["unexpectedRoot"] = {"value": "unrecognized"}
    original = path.read_bytes()
    with pytest.raises(ValueError, match="non-deliverable"):
        world_recipe_runtime.cache_put(key, request["itemA"], request["itemB"], corrupt, request["worldId"])
    assert path.read_bytes() == original
    world_storage.atomic_write_json(path, corrupt)
    raw = path.read_bytes()
    assert not combine_pipeline._cached_payload_report(corrupt)["ok"]
    assert _cache_only_endpoint(request)[0] == 404
    _assert_whole_record_quarantine(path, raw, "low_level_runtime_contract_invalid")


def test_no_image_record_is_refused_by_both_storage_and_strict_combine(cache_record):
    _, request, key, path, data = cache_record
    # No-assets/no-VFX-PNG is not permission to omit the required item PNG.
    # This explicitly corrupt durable witness must be refused, never completed.
    from infini_local.core.vfx_manifest import _compile_manifest

    data["vfxManifest"] = _compile_manifest(data, {"slots": []}, key)
    data.pop("visual", None)
    for entity in data["runtimeProgram"]["entities"]:
        for field in ("spritePath", "spriteUrl", "spriteStatus"):
            entity["visual"].pop(field, None)
    assert not world_storage.is_deliverable_recipe_payload(data)
    assert not combine_pipeline._cached_payload_report(data)["ok"]
    world_storage.atomic_write_json(path, data)
    raw = path.read_bytes()

    delivered = world_recipe_runtime.read_world_recipe_cache(key, request["worldId"])

    assert delivered is None
    receipt = _assert_whole_record_quarantine(path, raw, "low_level_runtime_contract_invalid")
    assert receipt["details"]["runtimeReady"] is True and receipt["details"]["assetsReady"] is False
    assert _cache_only_endpoint(request)[0] == 404


@pytest.mark.parametrize(("raw", "component"), [
    ("ordinary-world_123", "ordinary-world_123"),
    ("../outside/recipe", "outside_recipe"),
    (r"..\outside\recipe", "outside_recipe"),
    ("  .-world name-.  ", "world_name"),
    ("a" * 100, "a" * 80),
    ("/../", ""),
    (None, ""),
])
def test_world_paths_keep_bounded_filename_identity(tmp_path, raw, component):
    world_dir = world_storage.world_recipe_dir(tmp_path, raw)
    recipe_file = world_storage.world_recipe_file(tmp_path, raw, raw)
    assert world_dir == tmp_path / ("world_" + (component or "unknown_world"))
    assert recipe_file == world_dir / "recipes" / ((component or "recipe") + ".json")
    assert recipe_file.resolve().is_relative_to(tmp_path.resolve())
