from __future__ import annotations

import threading
from pathlib import Path

import pytest

from infini_local.pipelines import combine_pipeline, llm_transport
from infini_local.services import combine_endpoint
from infini_local.storage.world_recipe_runtime import recipe_key


def test_multidev_profiles_are_exact_pinned_and_have_independent_recipe_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = [
        {"profile_id": "llm_1", "label": "llm_1", "provider": "local", "base_url": "http://one", "model": "one", "api_mode": "chat_completions"},
        {"profile_id": "llm_2", "label": "llm_2", "provider": "openai_compat", "base_url": "http://two", "model": "two", "api_mode": "chat_completions"},
        {"profile_id": "llm_3", "label": "llm_3", "provider": "openai_compat", "base_url": "http://three", "model": "three", "api_mode": "chat_completions"},
    ]
    monkeypatch.setattr(llm_transport, "configured_llm_pool", lambda: profiles)
    llm_transport._reset_llm_pool_runtime_for_tests()

    lease, token = llm_transport.begin_llm_item_lease("recipe", preferred_profile_id="llm_2")
    try:
        assert lease.profile_id == "llm_2"
        assert lease.context["model"] == "two"
        # Exact multi-dev lane: no adjacent pool profile and no legacy fallback.
        assert lease.pool_size == 1
        assert [row["profile_id"] for row in lease.profiles] == ["llm_2"]
        assert lease.legacy_fallback_allowed is False
    finally:
        llm_transport.end_llm_item_lease(lease, token)

    with pytest.raises(RuntimeError, match="llm_4.*unavailable"):
        llm_transport.begin_llm_item_lease("recipe", preferred_profile_id="llm_4")

    a = {"id": 1, "name": "A"}
    b = {"id": 2, "name": "B"}
    normal = recipe_key(a, b, "world")
    assert recipe_key(a, b, "world", variant_id="") == normal
    lane1 = recipe_key(a, b, "world", variant_id="llm_1")
    lane2 = recipe_key(a, b, "world", variant_id="llm_2")
    assert len({normal, lane1, lane2}) == 3

    payload = {"itemA": a, "itemB": b, "worldId": "world", "multiDevCraft": True, "llmProfileId": "llm_2"}
    key, _cached = combine_pipeline.combine_cache_lookup(payload)
    assert key == lane2
    with pytest.raises(ValueError, match="exact llmProfileId"):
        combine_pipeline.combine_cache_lookup({**payload, "llmProfileId": "fallback"})


def test_multidev_endpoint_uses_its_parallel_gate_without_widening_normal_craft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", threading.BoundedSemaphore(1))
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_SEMAPHORE", threading.BoundedSemaphore(2))
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_PROFILE_SEMAPHORES", {
        profile_id: threading.BoundedSemaphore(1)
        for profile_id in ("llm_1", "llm_2", "llm_3")
    })
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_CONCURRENCY", 2)
    monkeypatch.setattr(combine_endpoint, "COMBINE_BUSY_WAIT_SECONDS", 0)

    entered = threading.Barrier(3)
    release = threading.Event()
    statuses: list[tuple[int, dict]] = []
    delivered: list[dict] = []

    def combine(payload: dict) -> dict:
        entered.wait(timeout=2)
        release.wait(timeout=2)
        return {"lane": payload["llmProfileId"]}

    def run(profile_id: str) -> None:
        combine_endpoint.handle_combine_request(
            {"multiDevCraft": True, "llmProfileId": profile_id},
            app_version="test",
            combine_cache_lookup=lambda payload: (str(payload["llmProfileId"]), None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=combine,
            trace_event=lambda *_args, **_kwargs: None,
            json=delivered.append,
            json_status=lambda status, value: statuses.append((status, value)),
        )

    threads = [threading.Thread(target=run, args=(profile,)) for profile in ("llm_1", "llm_2")]
    for thread in threads:
        thread.start()
    entered.wait(timeout=2)
    release.set()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()

    assert statuses == []
    assert {row["lane"] for row in delivered} == {"llm_1", "llm_2"}
    # Ordinary mode still owns the original serial semaphore.
    assert combine_endpoint.COMBINE_SEMAPHORE.acquire(blocking=False)
    normal_statuses: list[tuple[int, dict]] = []
    try:
        combine_endpoint.handle_combine_request(
            {},
            app_version="test",
            combine_cache_lookup=lambda _payload: ("normal", None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=lambda _payload: {"unexpected": True},
            trace_event=lambda *_args, **_kwargs: None,
            json=lambda _value: None,
            json_status=lambda status, value: normal_statuses.append((status, value)),
        )
    finally:
        combine_endpoint.COMBINE_SEMAPHORE.release()
    assert normal_statuses[0][0] == 409
    assert normal_statuses[0][1]["multiDevCraft"] is False


def test_multidev_same_profile_is_single_owner_and_invalid_profile_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_SEMAPHORE", threading.BoundedSemaphore(2))
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_PROFILE_SEMAPHORES", {
        profile_id: threading.BoundedSemaphore(1)
        for profile_id in ("llm_1", "llm_2", "llm_3")
    })
    monkeypatch.setattr(combine_endpoint, "MULTIDEV_CONCURRENCY", 2)
    monkeypatch.setattr(combine_endpoint, "COMBINE_BUSY_WAIT_SECONDS", 0)
    entered = threading.Event()
    release = threading.Event()
    delivered: list[dict] = []
    statuses: list[tuple[int, dict]] = []

    def slow_combine(payload: dict) -> dict:
        entered.set()
        release.wait(timeout=2)
        return {"lane": payload["llmProfileId"]}

    def call(payload: dict, combine=slow_combine) -> None:
        combine_endpoint.handle_combine_request(
            payload,
            app_version="test",
            combine_cache_lookup=lambda value: (str(value.get("llmProfileId") or ""), None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=combine,
            trace_event=lambda *_args, **_kwargs: None,
            json=delivered.append,
            json_status=lambda status, value: statuses.append((status, value)),
        )

    first = threading.Thread(target=call, args=({"multiDevCraft": True, "llmProfileId": "llm_2"},))
    first.start()
    assert entered.wait(timeout=2)
    call({"multiDevCraft": True, "llmProfileId": "llm_2"}, combine=lambda _payload: {"unexpected": True})
    release.set()
    first.join(timeout=3)
    assert not first.is_alive()
    assert statuses[0][0] == 409
    assert statuses[0][1]["status"] == "multidev_profile_busy"
    assert statuses[0][1]["llmProfileId"] == "llm_2"
    assert delivered == [{"lane": "llm_2"}]

    statuses.clear()
    call({"multiDevCraft": True, "llmProfileId": "llm_4"}, combine=lambda _payload: {"unexpected": True})
    assert statuses[0][0] == 422
    assert statuses[0][1]["status"] == "invalid_multidev_profile"


def test_multidev_csharp_packet_and_refund_contract_is_compile_shaped() -> None:
    root = Path(__file__).resolve().parents[2] / "ModSources" / "InfiniCrafterLocal"
    multi = (root / "Common" / "Players" / "InfiniCraftPlayer.MultiDev.cs").read_text(encoding="utf-8")
    multiplayer = (root / "Common" / "Players" / "InfiniCraftPlayer.Multiplayer.cs").read_text(encoding="utf-8")
    station_ui = (root / "Common" / "UI" / "InfiniCraftStationUISystem.cs").read_text(encoding="utf-8")

    assert "private static void DrawInputSlot(SpriteBatch spriteBatch, Rectangle rect, ref Item item, string label)" in station_ui
    assert "Math.Clamp((int)reader.ReadByte(), 1, 3)" in multi
    assert "Math.Clamp((int)reader.ReadByte(), 0, 2)" in multiplayer
    send_failure = multi.split("if (!SendServerCraftRequest(requestId, laneIndex, a, b))", 1)[1].split("return true;", 1)[0]
    assert "failedA = a" in send_failure and "failedB = b" in send_failure
    assert "RefundOne(" not in send_failure
    local_begin = multi.split("bool began = BeginExtraCraftLane", 1)[1].split("catch", 1)[0]
    assert "if (!began)" in local_begin
    assert "RefundOne(a)" in local_begin and "RefundOne(b)" in local_begin
