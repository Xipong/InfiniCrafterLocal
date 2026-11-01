"""Concurrent real combine calls share one committed world recipe, not its design."""
from concurrent.futures import ThreadPoolExecutor
import copy
import threading

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines import combine_pipeline as pipeline
from infini_local.pipelines.author import request as author_request
from infini_local.storage import world_storage
from tests.test_generation_resume import craft  # noqa: F401
from tests.vfx_image_fixtures import offline_backend  # noqa: F401


@pytest.mark.parametrize("first_fails", [False, True])
def test_same_recipe_rechecks_cache_and_releases_failed_flight(craft, monkeypatch, first_fails):
    entered, release, second_key = threading.Event(), threading.Event(), threading.Event()
    calls = []
    real_key = pipeline.recipe_key
    key_calls = []

    def key(*args):
        key_calls.append(1)
        if len(key_calls) == 2:
            second_key.set()
        return real_key(*args)

    def author(request, **kwargs):
        calls.append(copy.deepcopy(request))
        if len(calls) == 1:
            entered.set()
            assert release.wait(15)
        return craft.text(request, **kwargs)

    craft.fail = "planner" if first_fails else ""
    monkeypatch.setattr(pipeline, "recipe_key", key)
    monkeypatch.setattr(author_request, "llm_chat_json", author)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(pipeline.combine, copy.deepcopy(craft.request))
        try:
            assert entered.wait(15)
            second = pool.submit(pipeline.combine, copy.deepcopy(craft.request))
            assert second_key.wait(15)
        finally:
            release.set()
        if first_fails:
            with pytest.raises(PlannerUnavailable, match="Gameplay Author failed") as failure:
                first.result(30)
            assert isinstance(failure.value.__cause__, OSError)
            assert "offline provider interrupted planner" in str(failure.value.__cause__)
            result = second.result(30)
            assert result["name"] == "Wooden Blade 2"
        else:
            result = first.result(30)
            assert second.result(30)["id"] == result["id"]
            assert result["name"] == "Wooden Blade 1"
    assert pipeline._cached_payload_report(result)["ok"]
    assert len(calls) == (2 if first_fails else 1)
    assert craft.text_calls.count("visual_director") == craft.text_calls.count("vfx_director") == 1
    assert len(craft.image_calls) == 1
    assert not world_storage._GENERATION_LOCKS


@pytest.mark.parametrize("different_world", [False, True])
def test_unrelated_recipes_generate_concurrently(craft, monkeypatch, different_world):
    both_authors = threading.Barrier(2)

    def author(request, **kwargs):
        both_authors.wait(15)
        return craft.text(request, **kwargs)

    monkeypatch.setattr(author_request, "llm_chat_json", author)
    other = copy.deepcopy(craft.request)
    if different_world:
        other["worldId"] = "456"
    else:
        other["itemB"] = {"id": 8, "name": "Torch", "fullName": "Terraria/Torch"}
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(pipeline.combine, copy.deepcopy(craft.request))
        second = pool.submit(pipeline.combine, other)
        results = [first.result(30), second.result(30)]
        assert results[0]["id"] != results[1]["id"]
    assert all(pipeline._cached_payload_report(result)["ok"] for result in results)
    assert craft.text_calls.count("planner") == 2
    assert len(craft.image_calls) == 2
    assert not world_storage._GENERATION_LOCKS
