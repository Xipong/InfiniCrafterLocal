"""Concurrent real combine calls share one committed world recipe, not its design."""
from concurrent.futures import ThreadPoolExecutor
import copy
import threading

import pytest

from infini_local.pipelines import combine_pipeline as pipeline
from infini_local.storage import world_storage


@pytest.fixture
def pipeline_harness(tmp_path, monkeypatch):
    def identity(data, *args, **kwargs):
        return data

    def ok(*args, **kwargs):
        return {"ok": True}

    def get(key, world, *args, **kwargs):
        return world_storage.read_json_file(world_storage.world_recipe_file(tmp_path, world, key))

    def put(key, a, b, data, world, *args):
        world_storage.atomic_write_json(world_storage.world_recipe_file(tmp_path, world, key), data)

    overrides = {
        "USE_LLM": True, "begin_llm_item_lease": lambda *a, **kw: (None, None),
        "cache_get": get, "cache_put": put,
        "world_recipe_dir": lambda world: world_storage.world_recipe_dir(tmp_path, world),
        "sanitize_recipe_for_delivery": lambda data: copy.deepcopy(data),
    }
    for name in ("compile_and_validate_authored_runtime", "attach_visual", "apply_visual_director",
                 "attach_vfx_manifest", "finalize_visual_asset_runtime_gates", "maybe_generate_visual_assets",
                 "assert_visual_delivery_ready", "attach_generated_parent_summary", "final_normalize"):
        overrides[name] = identity
    for name in ("validate_final_runtime_wire_boundary", "validate_vfx_manifest_wire", "visual_delivery_report", "_cached_payload_report"):
        overrides[name] = ok
    for name, value in overrides.items():
        monkeypatch.setattr(pipeline, name, value)
    monkeypatch.setattr(pipeline.asset_sync_service, "attach_asset_sync_meta", identity)
    monkeypatch.setattr(world_storage, "attach_recipe_health", identity)
    return {"worldId": "123", "itemA": {"id": 1, "name": "A"}, "itemB": {"id": 2, "name": "B"}}


@pytest.mark.parametrize("first_fails", [False, True])
def test_same_recipe_rechecks_cache_and_releases_failed_flight(pipeline_harness, monkeypatch, first_fails):
    entered, release, second_key = threading.Event(), threading.Event(), threading.Event()
    calls = []
    real_key = pipeline.recipe_key
    key_calls = []

    def key(*args):
        key_calls.append(1)
        if len(key_calls) == 2:
            second_key.set()
        return real_key(*args)

    def author(a, b, recipe_key):
        calls.append(recipe_key)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
            if first_fails:
                raise RuntimeError("first flight failed")
        return {"id": f"winner-{len(calls)}", "name": "result", "debug": {}}

    monkeypatch.setattr(pipeline, "recipe_key", key)
    monkeypatch.setattr(pipeline, "try_llm_plan", author)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(pipeline.combine, copy.deepcopy(pipeline_harness))
        assert entered.wait(5)
        second = pool.submit(pipeline.combine, copy.deepcopy(pipeline_harness))
        try:
            assert second_key.wait(5)
        finally:
            release.set()
        if first_fails:
            with pytest.raises(RuntimeError, match="first flight failed"):
                first.result(5)
            assert second.result(5)["id"] == "winner-2"
        else:
            assert first.result(5)["id"] == second.result(5)["id"] == "winner-1"
    assert len(calls) == (2 if first_fails else 1)
    assert not world_storage._GENERATION_LOCKS


@pytest.mark.parametrize("different_world", [False, True])
def test_unrelated_recipes_generate_concurrently(pipeline_harness, monkeypatch, different_world):
    both_authors = threading.Barrier(2)

    def author(a, b, key):
        both_authors.wait(5)
        return {"id": key, "name": "result", "debug": {}}

    monkeypatch.setattr(pipeline, "try_llm_plan", author)
    other = copy.deepcopy(pipeline_harness)
    if different_world:
        other["worldId"] = "456"
    else:
        other["itemB"] = {"id": 3, "name": "C"}
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(pipeline.combine, pipeline_harness)
        second = pool.submit(pipeline.combine, other)
        assert first.result(5)["id"] != second.result(5)["id"]
    assert not world_storage._GENERATION_LOCKS
