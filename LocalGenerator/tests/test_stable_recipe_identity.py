"""Stable recipe lookup must retain accepted old discoveries, not reroll them."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from infini_local.core import item_identity_tools as identity
from infini_local.storage.recipe_identity_index import RecipeIdentityConflict
from tests.test_world_recipe_cache_admission import cache_record  # noqa: F401


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


def legacy_key(parents, world, version, profile=""):
    # Independent baseline formula: fixtures must not bless an accidental change
    # to the resolver's old-key proof or the multi-dev derivation.
    base = "r_" + identity.stable_hash(sorted(parents), "world:" + str(world), version, length=24)
    profile = profile.strip().lower()
    return hashlib.sha256(f"{base}\0multidev\0{profile}".encode()).hexdigest() if profile else base


def stored_record(root: Path, *, a=None, b=None, world="world", version="v", profile="", stable=False, key_override=None):
    a, b = a or parent(), b or {"id": 9, "fullName": "Terraria/Wood"}
    parents = [identity.item_identity(a), identity.item_identity(b)]
    key = (identity.recipe_key_from_identities(parents, world, version, stable_names=True, variant_id=profile)
           if stable else legacy_key(parents, world, version, profile))
    key = key_override or key
    folder = root / "recipes"
    folder.mkdir(parents=True, exist_ok=True)
    record = {"id": "g_accepted", "recipeKey": key, "recipeMeta": {"worldId": world, "parentIdentities": parents},
              "debug": {"recipeIdentityVersion": version, "multiDevProfileId": profile},
              "gameplay": {"damage": 12}, "vfxManifest": {"unchanged": True}}
    path = folder / (key + ".json")
    path.write_text(json.dumps(record), encoding="utf-8")
    return key, path


def resolve(root, a=None, b=None, world="world", version="v", profile=""):
    from infini_local.storage.recipe_identity_index import resolve_recipe_key
    return resolve_recipe_key(root, a or parent(7000), b or {"id": 9, "fullName": "Terraria/Wood"}, world, version, profile)


def test_exact_old_recipe_reused_after_number_change_without_rewriting(tmp_path):
    old_key, path = stored_record(tmp_path)
    before = path.read_bytes()
    assert resolve(tmp_path) == old_key
    assert resolve(tmp_path, a={"id": 9, "fullName": "Terraria/Wood"}, b=parent(8000)) == old_key
    assert path.read_bytes() == before
    assert list((tmp_path / "recipes").iterdir()) == [path]
    assert (tmp_path / "recipe_identity.sqlite3").is_file()


@pytest.mark.parametrize("lineage", [None, []])
def test_exact_old_key_without_lineage_still_returns_same_discovery(tmp_path, lineage):
    old_key, path = stored_record(tmp_path)
    record = json.loads(path.read_text())
    if lineage is None:
        record["recipeMeta"].pop("parentIdentities")
    else:
        record["recipeMeta"]["parentIdentities"] = lineage
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    # With unchanged numeric hints the literal old key is exact evidence even
    # when older metadata lacks the pair. Never create a second stable recipe.
    assert resolve(tmp_path, a=parent()) == old_key
    assert path.read_bytes() == before


def test_index_reused_without_rereading_unchanged_recipe_bodies(tmp_path, monkeypatch):
    old, _ = stored_record(tmp_path)
    assert resolve(tmp_path) == old
    from infini_local.storage import recipe_identity_index as index
    monkeypatch.setattr(index, "_read_record", lambda path: pytest.fail("unchanged body was reread"))
    assert resolve(tmp_path) == old


def test_new_file_change_and_removal_invalidate_index(tmp_path):
    new = resolve(tmp_path)
    old, path = stored_record(tmp_path)
    assert resolve(tmp_path) == old != new
    record = json.loads(path.read_text())
    record["recipeMeta"]["worldId"] = "foreign"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert resolve(tmp_path) == new
    path.unlink()
    assert resolve(tmp_path) == new


@pytest.mark.parametrize("change", ["key", "world", "parents", "version", "profile"])
def test_unbound_or_foreign_record_is_not_selected(tmp_path, change):
    old, path = stored_record(tmp_path)
    record = json.loads(path.read_text())
    if change == "key": record["recipeKey"] = "r_" + "0" * 24
    elif change == "world": record["recipeMeta"]["worldId"] = "other"
    elif change == "parents": record["recipeMeta"]["parentIdentities"][0] = "item:OtherMod/ExampleSword:6000"
    elif change == "version": record["debug"]["recipeIdentityVersion"] = "different"
    else: record["debug"]["multiDevProfileId"] = "llm_2"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert resolve(tmp_path) != old


def test_ambiguous_accepted_records_refuse_instead_of_selecting_or_rerolling(tmp_path):
    from infini_local.storage.recipe_identity_index import RecipeIdentityConflict
    stored_record(tmp_path, a=parent(6000))
    stored_record(tmp_path, a=parent(6500))
    with pytest.raises(RecipeIdentityConflict):
        resolve(tmp_path)


def test_profile_and_version_scopes_stay_distinct(tmp_path):
    old, _ = stored_record(tmp_path, profile="llm_1")
    assert resolve(tmp_path, profile="llm_1") == old
    assert resolve(tmp_path, profile="llm_2") != old
    assert resolve(tmp_path) != old
    assert resolve(tmp_path, profile="llm_1", version="other") != old


def test_new_stable_record_is_found_and_old_record_without_debug_can_be_proved(tmp_path):
    key, path = stored_record(tmp_path, stable=True)
    assert resolve(tmp_path) == key
    path.unlink()
    old, path = stored_record(tmp_path)
    record = json.loads(path.read_text())
    record.pop("debug")
    path.write_text(json.dumps(record), encoding="utf-8")
    assert resolve(tmp_path) == old


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


def test_name_spelling_generated_ids_and_numeric_display_fallback_remain_exact():
    b = {"generatedData": {"id": "g_exact"}}
    for other in (parent(fullName="ExampleMod/examplesword"), parent(fullName="examplemod/ExampleSword")):
        assert identity.recipe_key(parent(), b, "world", "v") != identity.recipe_key(other, b, "world", "v")
    assert identity.recipe_key(parent(fullName="ExampleMod/Épée"), b, "world", "v") != identity.recipe_key(
        parent(fullName="ExampleMod/E\u0301pée"), b, "world", "v")
    generated = ["generated:g_exact", "generated:g_OTHER"]
    assert identity.recipe_key_from_identities(generated, "world", "v", stable_names=True) == identity.recipe_key_from_identities(
        generated, "world", "v", stable_names=False)
    numeric = {"sourceMod": "Unknown", "id": 42, "name": "123"}
    assert identity.recipe_key(numeric, b, "world", "v") == identity.recipe_key_from_identities(
        [identity.item_identity(numeric), identity.item_identity(b)], "world", "v", stable_names=False)


@pytest.mark.parametrize("profile", ["", "llm_1"])
def test_missing_debug_is_proven_only_by_exact_version_and_profile_hash(tmp_path, profile):
    old, path = stored_record(tmp_path, profile=profile)
    record = json.loads(path.read_text())
    record.pop("debug")
    path.write_text(json.dumps(record))
    assert resolve(tmp_path, profile=profile) == old
    assert resolve(tmp_path, profile=profile, version="other") != old
    assert resolve(tmp_path, profile="llm_2") != old


@pytest.mark.parametrize("field,value", [("recipeIdentityVersion", None), ("multiDevProfileId", False),
                                          ("multiDevProfileId", []), ("recipeIdentityVersion", {})])
def test_explicit_invalid_stamp_is_not_missing_debug(tmp_path, field, value):
    old, path = stored_record(tmp_path)
    record = json.loads(path.read_text())
    record["debug"][field] = value
    path.write_text(json.dumps(record))
    assert resolve(tmp_path) != old


def test_generated_parent_change_does_not_reuse_a_native_match(tmp_path):
    generated = {"generatedData": {"id": "g_parent"}}
    old, _ = stored_record(tmp_path, b=generated)
    assert resolve(tmp_path, b=generated) == old
    assert resolve(tmp_path, b={"generatedData": {"id": "g_PARENT"}}) != old


def test_exact_stable_slot_with_contradictory_proof_is_not_delivered(tmp_path):
    _, path = stored_record(tmp_path, stable=True)
    record = json.loads(path.read_text())
    record["debug"]["recipeIdentityVersion"] = "other"
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    with pytest.raises(RecipeIdentityConflict):
        resolve(tmp_path)
    assert path.read_bytes() == before


def test_stable_and_historical_discoveries_are_ambiguous_even_on_exact_key(tmp_path):
    stored_record(tmp_path, stable=True)
    stored_record(tmp_path)
    with pytest.raises(RecipeIdentityConflict):
        resolve(tmp_path, a=parent())


def test_index_rebuild_and_same_size_mtime_replacement_detected(tmp_path):
    old, path = stored_record(tmp_path)
    assert resolve(tmp_path) == old
    (tmp_path / "recipe_identity.sqlite3").unlink()
    assert resolve(tmp_path) == old
    stat = path.stat()
    replacement = path.with_suffix(".tmp")
    replacement.write_bytes(path.read_bytes().replace(b'"worldId": "world"', b'"worldId": "other"'))
    os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    replacement.replace(path)
    assert path.stat().st_size == stat.st_size and path.stat().st_mtime_ns == stat.st_mtime_ns
    assert resolve(tmp_path) != old


@pytest.mark.parametrize("failure", ["read", "scan", "sqlite", "changing-file"])
def test_unassessed_storage_failure_propagates_instead_of_becoming_absence(tmp_path, monkeypatch, failure):
    from infini_local.storage import recipe_identity_index as index
    _, path = stored_record(tmp_path)
    before = path.read_bytes()

    def denied(*_args, **_kwargs):
        raise PermissionError("identity storage denied")

    if failure == "read": monkeypatch.setattr(index, "_read_record", denied)
    elif failure == "scan": monkeypatch.setattr(index.os, "scandir", denied)
    elif failure == "sqlite": monkeypatch.setattr(index.sqlite3, "connect", denied)
    else:
        real = index._read_record
        def changed(target):
            record = real(target)
            target.write_bytes(before + b" ")
            return record
        monkeypatch.setattr(index, "_read_record", changed)
    with pytest.raises(OSError):
        resolve(tmp_path)
    assert path.read_bytes() == (before + b" " if failure == "changing-file" else before)


def test_corrupt_derived_database_fails_closed_and_can_be_rebuilt(tmp_path):
    old, path = stored_record(tmp_path)
    before = path.read_bytes()
    db = tmp_path / "recipe_identity.sqlite3"
    db.write_bytes(b"not a sqlite database")
    with pytest.raises(sqlite3.DatabaseError):
        resolve(tmp_path)
    db.unlink()
    assert resolve(tmp_path) == old and path.read_bytes() == before


@pytest.fixture
def accepted_record(cache_record):
    from infini_local.core.config_bootstrap import RECIPE_IDENTITY_VERSION
    from infini_local.storage import world_recipe_runtime as runtime, world_storage
    root, request, _, stable_path, data = cache_record
    parents = [identity.item_identity(request[name]) for name in ("itemA", "itemB")]
    key = legacy_key(parents, request["worldId"], RECIPE_IDENTITY_VERSION)
    data["recipeKey"] = key
    data["recipeMeta"]["parentIdentities"] = parents
    data["debug"].update({"recipeIdentityVersion": RECIPE_IDENTITY_VERSION, "multiDevProfileId": ""})
    path = runtime.world_recipe_file(request["worldId"], key)
    world_storage.atomic_write_json(path, data)
    stable_path.unlink()
    request = copy.deepcopy(request)
    request["itemA"]["id"] += 10000
    request["itemA"]["name"] = "Localized display name"
    return root, request, key, path, data


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


@pytest.mark.parametrize("stable", [False, True])
def test_changed_runtime_id_returns_exact_accepted_definition_through_cache_and_combine(accepted_record, monkeypatch, stable):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, key, path, data = accepted_record
    if stable:
        key = identity.recipe_key(request["itemA"], request["itemB"], request["worldId"], data["debug"]["recipeIdentityVersion"])
        old_path, path = path, path.with_name(key + ".json")
        data["recipeKey"] = key
        world_storage.atomic_write_json(path, data)
        old_path.unlink()
    before = path.read_bytes()
    used_locks, discarded = [], []
    real_lock = world_storage.recipe_generation_lock

    @contextmanager
    def observe_lock(root, actual_key):
        used_locks.append(actual_key)
        with real_lock(root, actual_key):
            yield

    monkeypatch.setattr(world_storage, "recipe_generation_lock", observe_lock)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("accepted definition must not be rerolled"))
    monkeypatch.setattr(pipeline.craft_progress, "discard_progress", lambda root, actual_key: discarded.append(actual_key))
    assert pipeline.combine_cache_lookup(request)[0] == key
    for result in (pipeline.combine_cache_lookup(request)[1], pipeline.combine(request)):
        assert isinstance(result, dict)
        assert result["recipeKey"] == key
        for field in ("id", "name", "parentA", "parentB", "runtimeProgram", "visual", "vfxManifest"):
            assert result[field] == data[field]
        assert result["recipeMeta"]["parentIdentities"] == data["recipeMeta"]["parentIdentities"]
    code, result = _endpoint({**request, "cacheOnly": True})
    assert code == 200 and result["id"] == data["id"] and result["recipeKey"] == key
    assert used_locks == discarded == [key]
    assert path.read_bytes() == before and list(path.parent.iterdir()) == [path]
    assert not (path.parent.parent / "invalid").exists()


def test_endpoint_preserves_old_discovery_without_optional_lineage(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, key, path, data = accepted_record
    request["itemA"]["id"] -= 10000
    data["recipeMeta"].pop("parentIdentities")
    world_storage.atomic_write_json(path, data)
    before = path.read_bytes()
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("same exact old key must not reroll Author"))
    code, result = _endpoint(request)
    assert code == 200 and result["id"] == data["id"] and result["recipeKey"] == key
    assert path.read_bytes() == before


def test_missing_png_on_resolved_old_recipe_preserves_definition_and_returns_409(accepted_record, monkeypatch):
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


def test_ambiguous_storage_stops_endpoint_and_combine_before_author(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, _, path, data = accepted_record
    parents = list(data["recipeMeta"]["parentIdentities"])
    parents[0] = parents[0].rsplit(":", 1)[0] + ":9000"
    key = identity.recipe_key_from_identities(parents, request["worldId"], data["debug"]["recipeIdentityVersion"], stable_names=False)
    duplicate = copy.deepcopy(data)
    duplicate.update({"recipeKey": key, "id": "g_other_accepted"})
    duplicate["recipeMeta"]["parentIdentities"] = parents
    other = path.with_name(key + ".json")
    world_storage.atomic_write_json(other, duplicate)
    before = {p: p.read_bytes() for p in (path, other)}
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("ambiguous discovery must not reroll Author"))
    with pytest.raises(RecipeIdentityConflict):
        pipeline.combine(request)
    assert _endpoint({**request, "cacheOnly": True})[0] == 500  # Never 404/cache_miss.
    assert {p: p.read_bytes() for p in before} == before


def test_lookup_io_failure_cannot_start_author_or_become_http_cache_miss(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import recipe_identity_index as index
    _, request, _, path, _ = accepted_record
    before = path.read_bytes()

    def denied(*_args):
        raise PermissionError("recipe read unavailable")

    monkeypatch.setattr(index, "_read_record", denied)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("I/O failure must not reroll Author"))
    for action in (pipeline.combine_cache_lookup, pipeline.combine):
        with pytest.raises(PermissionError):
            action(request)
    assert _endpoint({**request, "cacheOnly": True})[0] == 500
    assert path.read_bytes() == before


def test_archive_change_inside_singleflight_cannot_change_checkpoint_key(accepted_record, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.storage import world_storage
    _, request, _, path, data = accepted_record
    raw = path.read_bytes()
    path.unlink()
    locks = []
    real_lock = world_storage.recipe_generation_lock

    @contextmanager
    def late_commit(root, actual_key):
        locks.append(actual_key)
        with real_lock(root, actual_key):
            path.write_bytes(raw)
            yield

    monkeypatch.setattr(world_storage, "recipe_generation_lock", late_commit)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: pytest.fail("join changed under lock"))
    monkeypatch.setattr(pipeline.craft_progress, "CraftProgress", lambda *_a, **_kw: pytest.fail("checkpoint under wrong key"))
    with pytest.raises(RecipeIdentityConflict, match="changed while waiting"):
        pipeline.combine(request)
    assert locks == [identity.recipe_key(request["itemA"], request["itemB"], request["worldId"], data["debug"]["recipeIdentityVersion"])]
    assert path.read_bytes() == raw and not world_storage._GENERATION_LOCKS
