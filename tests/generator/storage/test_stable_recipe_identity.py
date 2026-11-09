"""Current recipe identity and canonical cache reuse without archive adoption."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from infini_local.core import item_identity_tools as identity
from tests.generator.storage.test_world_recipe_cache_admission import cache_record  # noqa: F401


def parent(runtime_id=6000, **values):
    return {"id": runtime_id, "fullName": "ExampleMod/ExampleSword", **values}


def test_native_name_not_runtime_number_owns_new_recipe_key():
    a, b = parent(), {"id": 9, "fullName": "Terraria/Wood"}
    before = copy.deepcopy(a)
    assert identity.recipe_key(a, b, "world", "v") == identity.recipe_key(parent(7000), b, "world", "v")
    assert identity.recipe_key(a, b, "world", "v") == identity.recipe_key(b, a, "world", "v")
    assert identity.recipe_key(a, b, "world", "v") != identity.recipe_key(a, b, "other", "v")
    assert identity.recipe_key(a, b, "world", "v") != identity.recipe_key(a, b, "world", "other")
    assert identity.recipe_key(a, b, "world", "v") != identity.recipe_key(parent(fullName="OtherMod/ExampleSword"), b, "world", "v")
    # Wire lineage retains its existing reader contract and capture evidence.
    assert identity.item_identity(a) == "item:ExampleMod/ExampleSword:6000"
    assert a == before


def test_generated_identity_and_unknown_native_identity_do_not_change():
    a, b = {"generatedData": {"id": "g_original"}}, {"sourceMod": "Unknown", "id": 42, "name": "Missing name"}
    pair = sorted([identity.item_identity(a), identity.item_identity(b)])
    assert identity.recipe_key(a, b, "world", "v") == "r_" + identity.stable_hash(pair, "world:world", "v", length=24)
    assert identity.recipe_key(a, b, "world", "v") != identity.recipe_key({"generatedData": {"id": "g_other"}}, b, "world", "v")


def test_explicit_full_and_split_names_are_one_stable_native_identity():
    b = {"generatedData": {"id": "g_other"}}
    assert identity.recipe_key(parent(), b, "world", "v") == identity.recipe_key(
        {"sourceMod": "ExampleMod", "internalName": "ExampleSword", "id": 7000}, b, "world", "v")


@pytest.mark.parametrize("raw,expected", [
    ("item:Unknown:42:123", "item:Unknown:42:123"),
    ("item:Unknown:42:missing_name", "item:Unknown:42:missing_name"),
    ("generated:Exact:Case/42", "generated:Exact:Case/42"),
    ("item:Mod/Thing:7000", "item:Mod/Thing"),
    ("item:Mod:Thing:7000", "item:Mod/Thing"),
    ("item:Мод/Предмет:7", "item:Мод/Предмет"),
    ("item:Mod/Thing:", "item:Mod/Thing"),
    ("item:Mod/Thing:٧", "item:Mod/Thing:٧"),
    ("item:Mod/Thing:-7", "item:Mod/Thing:-7"),
    ("item:Mod/Thing:seven", "item:Mod/Thing:seven"),
    ("item:Mod/Thing/Extra:7", "item:Mod/Thing/Extra:7"),
    ("item:Mod/Thing:Extra:7", "item:Mod/Thing:Extra:7"),
    ("item:Mod:Thing:Extra:7", "item:Mod:Thing:Extra:7"),
    ("item:Mod/Display Name:7", "item:Mod/Display Name:7"),
    ("item:Mod/Thing\n:7", "item:Mod/Thing\n:7"),
])
def test_only_provable_native_names_lose_the_runtime_hint(raw, expected):
    assert identity.stable_recipe_identity(raw) == expected


def _endpoint(request):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.services.combine_endpoint import handle_combine_request
    from infini_local.storage.world_storage import sanitize_recipe_for_delivery
    responses = []
    handle_combine_request(
        request, app_version="identity-test", combine_cache_lookup=pipeline.combine_cache_lookup,
        sanitize_recipe_for_delivery=sanitize_recipe_for_delivery, combine=pipeline.combine,
        trace_event=lambda *_: None, json=lambda data: responses.append((200, data)),
        json_status=lambda code, data: responses.append((code, data)),
    )
    assert len(responses) == 1
    return responses[0]


def test_missing_png_preserves_current_definition_and_returns_409(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, key, path, data = accepted_record
    before = path.read_bytes()
    Path(data["visual"]["spritePath"]).unlink()
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("missing PNG must not reroll Author"))
    for action in (pipeline.combine_cache_lookup, pipeline.combine):
        with pytest.raises(world_storage.RecipeAssetsUnavailable) as error:
            action(request)
        assert error.value.recipe_key == key
    for cache_only in (True, False):
        code, result = _endpoint({**request, "cacheOnly": cache_only})
        assert code == 409 and result["status"] == "accepted_recipe_assets_unavailable" and result["recipeKey"] == key
    assert path.read_bytes() == before and list(path.parent.iterdir()) == [path]
    assert not (path.parent.parent / "invalid").exists()


@pytest.fixture
def accepted_record(cache_record):
    root, request, key, path, data = cache_record
    request = copy.deepcopy(request)
    request["itemA"]["id"] += 10000
    request["itemA"]["name"] = "Localized display name"
    return root, request, key, path, data


def test_changed_runtime_id_reuses_current_cache_without_author(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    _, request, key, path, data = accepted_record
    before = path.read_bytes()
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("accepted definition must not be rerolled"))
    assert pipeline.combine_cache_lookup(request)[0] == key
    for result in (pipeline.combine_cache_lookup(request)[1], pipeline.combine(request)):
        assert isinstance(result, dict)
        assert result["recipeKey"] == key
        for field in ("id", "name", "parentA", "parentB", "runtimeProgram", "visual", "vfxManifest"):
            assert result[field] == data[field]
    code, result = _endpoint({**request, "cacheOnly": True})
    assert code == 200 and result["id"] == data["id"] and result["recipeKey"] == key
    assert path.read_bytes() == before


def test_old_numeric_hash_record_is_not_adopted_or_rewritten(cache_record):
    from infini_local.pipelines import combine_pipeline as pipeline
    _, request, key, path, data = cache_record
    parents = [identity.item_identity(request[name]) for name in ("itemA", "itemB")]
    from infini_local.core.config_bootstrap import RECIPE_IDENTITY_VERSION
    old_key = "r_" + identity.stable_hash(sorted(parents), "world:" + request["worldId"], RECIPE_IDENTITY_VERSION, length=24)
    assert old_key != key
    old = path.with_name(old_key + ".json")
    path.rename(old)
    before = old.read_bytes()
    assert pipeline.combine_cache_lookup(request) == (key, None)
    assert old.read_bytes() == before
    assert not path.exists()
    assert not (path.parent.parent / "recipe_identity.sqlite3").exists()


def test_current_hash_preserves_profile_scope_and_exact_name_spelling():
    from infini_local.storage.world_recipe_runtime import recipe_key
    a, b = parent(), {"generatedData": {"id": "g_exact"}}
    base = recipe_key(a, b, "world", "v")
    assert recipe_key(a, b, "world", "v", "llm_1") != base
    assert recipe_key(a, b, "world", "v", "llm_1") != recipe_key(a, b, "world", "v", "llm_2")
    assert recipe_key(a, b, "world", "v", " LLM_1 ") == recipe_key(a, b, "world", "v", "llm_1")
    for other in (parent(fullName="ExampleMod/examplesword"), parent(fullName="examplemod/ExampleSword")):
        assert recipe_key(other, b, "world", "v") != base


def test_lookup_io_failure_cannot_start_author_or_become_http_cache_miss(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, _, path, _ = accepted_record
    before = path.read_bytes()
    def denied(*_args, **_kwargs):
        raise PermissionError("recipe read unavailable")
    monkeypatch.setattr(world_storage, "read_json_file", denied)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("I/O failure must not reroll Author"))
    for action in (pipeline.combine_cache_lookup, pipeline.combine):
        with pytest.raises(PermissionError):
            action(request)
    assert _endpoint({**request, "cacheOnly": True})[0] == 500
    assert path.read_bytes() == before
