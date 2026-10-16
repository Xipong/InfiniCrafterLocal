"""Offline real-route fault injection for cache, failures and active diagnostics."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from types import SimpleNamespace
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError

import pytest
from provider_test_support import deliverable_recipe, loopback_server, write_json_response, endpoint_options
from infini_local.pipelines import (
    combine_pipeline as pipeline,
    gameplay_stage,
    llm_transport as transport,
    llm_authoring_pipeline as author,
    generation_debug,
)
from infini_local.services import combine_endpoint as endpoint
from infini_local.storage import world_storage, world_recipe_runtime as recipes
from infini_local.web.server_handler import build_handler
from infini_local.web import http_response_helpers as helpers
from infini_local.core.errors import PlannerUnavailable
from infini_local.pipelines.visual_delivery_gate import VisualDeliveryBlocked

PAYLOAD = {
    "worldId": "11111111-1111-1111-1111-111111111111",
    "itemA": {"id": 3507, "name": "Copper Shortsword", "fullName": "Terraria/CopperShortsword"},
    "itemB": {"id": 8, "name": "Torch", "fullName": "Terraria/Torch"},
}


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    connect = socket.socket.connect

    def loopback_only(self, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("external networking forbidden")
        return connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    monkeypatch.setattr(endpoint, "_GENERATION_ACCEPTING", True)
    monkeypatch.setattr(endpoint, "COMBINE_SEMAPHORE", threading.BoundedSemaphore(1))
    monkeypatch.setattr(endpoint, "COMBINE_BUSY_WAIT_SECONDS", 0)
    transport._reset_llm_pool_runtime_for_tests()
    generation_debug.clear_combine_failure("test_isolation")
    monkeypatch.setattr(transport, "LLM_FALLBACK_NETWORK_FAILS", 1)
    monkeypatch.setattr(transport, "_fallback_llm_context", lambda: None)
    monkeypatch.setattr(transport, "log_event", lambda *_a, **_k: None)
    monkeypatch.setattr(author, "USE_LLM", True)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    yield
    assert endpoint.generation_activity_snapshot()["active"] == 0
    assert endpoint.generation_activity_snapshot()["waiting"] == 0
    assert transport.current_llm_item_lease() is None


@pytest.fixture
def route_worker():
    """Explicit route worker ownership; releases all declared gates on failure."""
    from types import SimpleNamespace

    owned = []

    def start(route, payload, *release):
        results = []
        worker = threading.Thread(target=lambda: results.append(route(payload)))
        owned.append((worker, release))
        worker.start()
        return SimpleNamespace(thread=worker, results=results)

    yield start
    for worker, release in owned:
        for event in release:
            event.set()
        worker.join(5)
        assert not worker.is_alive(), "route request leaked a worker"


@pytest.fixture
def configured_profiles(monkeypatch):
    """Patch only the declared profile keys; malformed/legacy omissions stay absent."""
    def install(*profiles):
        monkeypatch.setattr(transport, "configured_llm_pool", lambda: list(profiles))
    return install


def local_profile(**overrides):
    return {"provider": "local", "base_url": "http://127.0.0.1:9", "model": "offline",
            "profile_id": "llm_1", **overrides}


@pytest.fixture
def real_route():
    cls = build_handler(
        app_version="test",
        utility_routes=lambda: SimpleNamespace(handle_get=lambda h, p: False),
        vfx_debug_routes=lambda: None,
        combine_endpoint=endpoint,
        combine_cache_lookup=pipeline.combine_cache_lookup,
        sanitize_recipe_for_delivery=world_storage.sanitize_recipe_for_delivery,
        combine=pipeline.combine,
        trace_event=lambda *_a, **_k: None,
        log_event=lambda *_a, **_k: None,
        is_client_disconnect=helpers._is_client_disconnect,
        world_scope_missing=recipes.WorldScopeMissing,
        visual_delivery_blocked=VisualDeliveryBlocked,
        planner_unavailable=PlannerUnavailable,
        clear_combine_failure=generation_debug.clear_combine_failure,
        combine_failure_http_response=helpers._combine_failure_http_response,
        combine_failure_payload=helpers._combine_failure_payload,
        ascii_reason=helpers._ascii_reason,
    )
    with loopback_server(cls) as server:
        def post(payload):
            req = Request(
                f"http://127.0.0.1:{server.server_port}/combine",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                response = build_opener(ProxyHandler({})).open(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                body = json.loads(response.read())
                if response.code >= 400:
                    assert "Items were returned" not in body.get("playerMessage", ""), "route has no native material authority"
                return response.code, body

        yield post


def valid_cached_recipe(tmp_path, monkeypatch):
    good = deliverable_recipe(tmp_path, monkeypatch, manifest_key="read-error-test")
    key, _ = pipeline.combine_cache_lookup(PAYLOAD)
    target = recipes.world_recipe_file(PAYLOAD["worldId"], key)
    recipes.cache_put(key, PAYLOAD["itemA"], PAYLOAD["itemB"], good, PAYLOAD["worldId"])
    return target, good


@pytest.mark.parametrize("cache_only", [False, True])
@pytest.mark.parametrize("error_type", [PermissionError, OSError])
def test_recipe_read_io_failure_keeps_active_bytes_and_recovers(monkeypatch, real_route, tmp_path, cache_only, error_type):
    target, good = valid_cached_recipe(tmp_path, monkeypatch)
    original = target.read_bytes()
    read_text = Path.read_text

    def denied(self, *args, **kwargs):
        if self == target:
            raise error_type("synthetic transient read denial")
        return read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_a, **_k: pytest.fail("read failure must not start inference"))
    request = {**PAYLOAD, "cacheOnly": cache_only}
    status, body = real_route(request)
    assert target.exists() and target.read_bytes() == original, "unassessed bytes must remain active"
    assert status == 500 and body["error"] == "cache_lookup_failed"
    assert not list((target.parent.parent / "invalid").glob("*.json"))
    monkeypatch.setattr(Path, "read_text", read_text)
    status, body = real_route(request)
    assert status == 200 and body["id"] == good["id"]
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "fault,status,provider_code,param,expected,retryable",
    [
        ("model", 404, "model_not_found", "model", "llm_model_unavailable", False),
        ("auth", 401, "invalid_api_key", None, "llm_auth_failed", False),
        ("route", 404, "not_found", None, "llm_endpoint_unavailable", False),
        ("quota", 429, "insufficient_quota", None, "llm_quota_exhausted", False),
        ("deadline", None, None, None, "llm_timeout", True),
    ],
)
def test_real_author_provider_failure_has_safe_actionable_metadata(
    monkeypatch, real_route, tmp_path, fault, status, provider_code, param, expected, retryable
):
    from infini_local.storage import trace_runtime, failure_state

    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", True)
    monkeypatch.setattr(generation_debug, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(generation_debug, "LAST_COMBINE_FAILURE_FILE", tmp_path / "failure.json")
    sends = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            sends.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            write_json_response(self, {"error": {
                "code": provider_code, "param": param,
                "message": "PRIVATE-PROMPT-OR-CREDENTIAL",
                "unknown": "PRIVATE-PROMPT-OR-CREDENTIAL",
            }}, status=status)

    with loopback_server(Provider) as provider:
        context = {
            "provider": "openai_compat",
            "base_url": f"http://127.0.0.1:{provider.server_port}/v1",
            "model": "owner/missing",
            "api_key": "offline-synthetic",
            "api_mode": "chat_completions",
            "profile_id": "llm_1",
        }
        monkeypatch.setattr(transport, "configured_llm_pool", lambda: [context])
        if fault == "deadline":
            from infini_local.core.http_io import HttpDeadlineExceeded

            monkeypatch.setattr(
                transport, "http_json", lambda *_a, **_k: (_ for _ in ()).throw(HttpDeadlineExceeded("HTTP logical-call deadline exceeded"))
            )
        response_status, body = real_route(dict(PAYLOAD))
        assert "Items were returned" not in body["playerMessage"], "HTTP diagnostics have no material delivery authority"
        assert body["error"] == expected
        assert body["retryable"] is retryable
        assert response_status in {424, 504}
        supplement = body["lastFailure"]["transportDebug"]
        assert supplement["failureCategory"]
        assert supplement.get("httpStatus") == status
        if provider_code is not None:
            assert supplement["providerErrorCode"] == provider_code
            assert supplement.get("providerErrorParam") == param
        assert len(sends) == int(fault != "deadline")
        assert "PRIVATE-PROMPT-OR-CREDENTIAL" not in json.dumps(body)
        persisted = json.loads(generation_debug.LAST_COMBINE_FAILURE_FILE.read_text())
        assert persisted["transportDebug"] == supplement
        assert failure_state.read_failure_summary({}, generation_debug.LAST_COMBINE_FAILURE_FILE)["transportDebug"] == supplement
        assert "PRIVATE-PROMPT-OR-CREDENTIAL" not in json.dumps(persisted)
        assert expected not in {"llm_auth_failed", "llm_model_unavailable"} or "try crafting again" not in body["playerMessage"]


@pytest.mark.parametrize("status,code,retryable", [
    (424, "llm_auth_failed", False), (422, "llm_output_invalid", True),
    (424, "visual_dependency_failed", True), (424, "planner_unavailable", True),
    (409, "generator_busy", True), (428, "world_scope_missing", False),
    (500, "combine_failed", True), (500, "unknown_failure", False),
])
def test_failure_payload_does_not_claim_native_material_delivery(status, code, retryable):
    body = helpers._combine_failure_payload(status, code, "check configured provider", {}, retryable=retryable)
    assert "returned" not in body["playerMessage"].lower()
    assert body["httpStatus"] == status and body["error"] == code
    assert body["retryable"] is retryable and body["manualRegenerateAllowed"] is retryable
    assert body["cacheRecoveryAllowed"] is False


def test_disabled_profile_records_own_prelease_failure_on_real_route(monkeypatch, real_route):
    context = {
        "provider": "local",
        "base_url": "http://127.0.0.1:9",
        "model": "offline",
        "api_key": "",
        "api_mode": "chat_completions",
        "profile_id": "llm_1",
    }
    monkeypatch.setattr(transport, "configured_llm_pool", lambda: [context])
    generation_debug.record_combine_failure(
        "05_visual_director", PlannerUnavailable("prior unrelated request"), {"worldId": "other-world"}, None, []
    )
    status, body = real_route({**PAYLOAD, "multiDevCraft": True, "llmProfileId": "llm_2"})
    assert status == 424 and body["error"] == "llm_profile_unavailable"
    assert body["retryable"] is False
    assert body["lastFailure"]["worldId"] == PAYLOAD["worldId"]
    assert body["lastFailure"]["stage"] == "00_llm_lease"
    for semaphore in (endpoint.MULTIDEV_SEMAPHORE, endpoint.MULTIDEV_PROFILE_SEMAPHORES["llm_2"]):
        assert semaphore.acquire(blocking=False)
        semaphore.release()


def test_endpoint_never_attaches_unjoined_global_failure(monkeypatch):
    error = PlannerUnavailable("request with no recorded snapshot")
    generation_debug.record_combine_failure(
        "05_visual_director", PlannerUnavailable("sibling failure"), {"worldId": "other-world"}, None, []
    )
    with pytest.raises(PlannerUnavailable) as caught:
        endpoint.handle_combine_request(
            dict(PAYLOAD), **endpoint_options(
                combine=lambda _: (_ for _ in ()).throw(error),
                json=lambda _: None,
                json_status=lambda *_: None,
            ),
        )
    assert caught.value._infini_failure_snapshot == {}


def test_actual_active_stages_are_private_detached_and_removed_with_logging_off(monkeypatch, route_worker, real_route):
    from infini_local.web import server
    from infini_local.storage import trace_runtime

    monkeypatch.setattr(trace_runtime, "TRACE_PROMPTS_ENABLED", False)
    monkeypatch.setattr(server, "llm_auth_snapshot", lambda: {"provider": "local", "model": "offline"})
    monkeypatch.setattr(
        transport,
        "configured_llm_pool",
        lambda: [
            {
                "provider": "local",
                "base_url": "http://127.0.0.1:9?secret=PRIVATE",
                "model": "offline",
                "api_key": "PRIVATE",
                "api_mode": "chat_completions",
                "profile_id": "llm_1",
            }
        ],
    )
    entered, resume = threading.Event(), threading.Event()

    def blocked(*_a, **_k):
        entered.set()
        assert resume.wait(5)
        raise PlannerUnavailable("controlled stage failure")

    monkeypatch.setattr(pipeline, "try_llm_plan", blocked)
    worker = route_worker(real_route, {**PAYLOAD, "worldName": "PRIVATE", "itemA": {**PAYLOAD["itemA"], "privateSummary": "PRIVATE"}}, resume)
    assert entered.wait(5)
    activity = server._health_payload()["generationActivity"]
    assert activity["active"] == 1 and activity["waiting"] == 0
    rows = activity.get("requests", [])
    assert len(rows) == 1, "parked real pipeline must expose the currently entered stage"
    row = rows[0]
    assert row["stage"] == "01_gameplay_author"
    assert row["profileId"] == "llm_1"
    assert row["waitReason"] == "none" and row["networkStarted"] is None
    assert row["elapsedSeconds"] >= row["stageElapsedSeconds"] >= 0
    assert isinstance(row["requestId"], str) and len(row["requestId"]) == 32
    assert "PRIVATE" not in json.dumps(activity)
    row["stage"] = "modified-detached-copy"
    assert endpoint.generation_activity_snapshot()["requests"][0]["stage"] == "01_gameplay_author"
    resume.set()
    worker.thread.join(5)
    assert not worker.thread.is_alive()
    assert worker.results[0][0] == 424
    assert endpoint.generation_activity_snapshot()["requests"] == []


@pytest.mark.parametrize("multi_dev", [False, True])
def test_live_semaphore_wait_reason_is_owned_by_request(monkeypatch, configured_profiles, real_route, multi_dev):
    waiting = threading.Event()

    class ObservedSemaphore(threading.BoundedSemaphore):
        def acquire(self, blocking=True, timeout=None):
            if blocking and timeout is not None:
                waiting.set()
            return super().acquire(blocking=blocking, timeout=timeout)

    held = ObservedSemaphore(1)
    held.acquire()
    monkeypatch.setattr(endpoint, "COMBINE_BUSY_WAIT_SECONDS", 2)
    if multi_dev:
        monkeypatch.setattr(endpoint, "MULTIDEV_PROFILE_SEMAPHORES", {"llm_2": held})
    else:
        monkeypatch.setattr(endpoint, "COMBINE_SEMAPHORE", held)
    configured_profiles(local_profile())
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *_: (_ for _ in ()).throw(PlannerUnavailable("controlled stop")))
    result = []
    worker = threading.Thread(target=lambda: result.append(real_route({**PAYLOAD, "multiDevCraft": multi_dev, "llmProfileId": "llm_2"})))
    worker.start()
    try:
        assert waiting.wait(3)
        activity = endpoint.generation_activity_snapshot()
        assert activity["waiting"] == 1 and activity["active"] == 0
        assert activity["requests"][0]["waitReason"] == ("profile_slot" if multi_dev else "generation_slot")
        assert activity["requests"][0]["networkStarted"] is None
    finally:
        held.release()
        worker.join(5)
        assert not worker.is_alive()
    assert held.acquire(blocking=False)
    held.release()


def test_real_author_rate_queue_and_network_start_are_live_across_sibling_lanes(monkeypatch, real_route):
    import time

    parked, queued, resume, sending, finish = (threading.Event() for _ in range(5))
    sends, results = [], []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            sends.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            sending.set()
            assert finish.wait(5)
            write_json_response(self, {"error": {"code": "invalid_api_key"}}, status=401)

    with loopback_server(Provider) as provider:
        contexts = [
            {
                "provider": "openai_compat",
                "base_url": f"http://127.0.0.1:{provider.server_port}/v1",
                "model": "offline",
                "api_key": "PRIVATE",
                "api_mode": "chat_completions",
                "profile_id": f"llm_{i}",
            }
            for i in (1, 2)
        ]
        monkeypatch.setattr(transport, "configured_llm_pool", lambda: contexts)
        monkeypatch.setattr(transport, "_remote_rate_key", lambda *_: "fixture-rate-key")
        monkeypatch.setattr(transport, "_remote_admission_policy", lambda *_: "nous_openai_feedback")
        monkeypatch.setattr(transport, "_LLM_RATE_GENERIC_MIN_INTERVAL_SECONDS", 0.05)
        transport._LLM_RATE_STATE["fixture-rate-key"] = {"events": [], "lastRequest": time.monotonic() + 1.0, "blockedUntil": 0.0}
        sleep = time.sleep

        def gated_sleep(seconds):
            if not resume.is_set() and transport._CURRENT_LLM_ATTEMPT.get() is not None:
                parked.set()
                assert resume.wait(5)
            else:
                sleep(seconds)

        monkeypatch.setattr(transport.time, "sleep", gated_sleep)
        event_wait = threading.Event.wait

        def observed_wait(self, timeout=None):
            row = transport._CURRENT_LLM_ATTEMPT.get()
            if row is not None and row.get("rateWaitReason") == "rate_queue":
                queued.set()
            return event_wait(self, timeout)

        monkeypatch.setattr(threading.Event, "wait", observed_wait)
        workers = [
            threading.Thread(
                target=lambda i=i: results.append(
                    (i, real_route({**PAYLOAD, "worldId": f"world-{i}", "multiDevCraft": True, "llmProfileId": f"llm_{i}"}))
                )
            )
            for i in (1, 2)
        ]
        try:
            workers[0].start()
            assert parked.wait(3)
            workers[1].start()
            assert queued.wait(3)
            activity = endpoint.generation_activity_snapshot()
            assert activity["active"] == 2
            rows = {r["profileId"]: r for r in activity["requests"]}
            assert rows["llm_1"]["stage"] == rows["llm_2"]["stage"] == "01_gameplay_author"
            assert rows["llm_1"]["waitReason"] == "pacing"
            assert rows["llm_2"]["waitReason"] == "rate_queue"
            assert all(r["networkStarted"] is False for r in rows.values())
            assert len({r["requestId"] for r in rows.values()}) == 2
            assert not sends and "PRIVATE" not in json.dumps(activity)
            resume.set()
            assert sending.wait(3)
            assert any(r["networkStarted"] is True and r["waitReason"] == "none" for r in endpoint.generation_activity_snapshot()["requests"])
        finally:
            resume.set()
            finish.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(15)
            assert not any(w.is_alive() for w in workers)
    assert len(sends) == 2 and len(results) == 2
    for i, (status, body) in results:
        assert status == 424 and body["error"] == "llm_auth_failed"
        assert body["lastFailure"]["worldId"] == f"world-{i}"
    assert endpoint.generation_activity_snapshot()["requests"] == []
    assert not transport._LLM_RATE_STATE["fixture-rate-key"]["waiters"]


def test_real_author_unsent_rate_deadline_is_not_provider_timeout(monkeypatch, real_route):
    import time
    from infini_local.core import http_io

    # Only admission sleep spends this test's budget. Real payload preparation
    # can exceed 40 ms on a busy worker before the rate wait is ever entered.
    now, sleeps = [time.monotonic()], []

    def advance(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    clock = SimpleNamespace(monotonic=lambda: now[0], sleep=advance, time=time.time)
    monkeypatch.setattr(transport, "time", clock)
    monkeypatch.setattr(http_io, "time", clock)

    context = {
        "provider": "openai_compat",
        "base_url": "http://127.0.0.1:9/v1",
        "model": "offline",
        "api_mode": "chat_completions",
        "api_key": "PRIVATE",
        "profile_id": "llm_1",
    }
    monkeypatch.setattr(transport, "configured_llm_pool", lambda: [context])
    monkeypatch.setattr(transport, "_remote_rate_key", lambda *_: "fixture-deadline")
    transport._LLM_RATE_STATE["fixture-deadline"] = {"events": [], "lastRequest": now[0], "blockedUntil": now[0] + 10}
    call = author.llm_chat_json
    monkeypatch.setattr(author, "llm_chat_json", lambda payload, timeout=10: call(payload, timeout=0.04))
    monkeypatch.setattr(transport, "urlopen_no_redirect", lambda *_a, **_k: pytest.fail("expired admission must never send"))
    status, body = real_route(dict(PAYLOAD))
    assert status == 504 and body["error"] == "llm_admission_timeout"
    assert sleeps == pytest.approx([0.04])
    debug = body["lastFailure"]["transportDebug"]
    assert debug["networkStarted"] is False and debug["physicalAttemptCount"] == 0
    assert debug["rateWaitReason"] == "provider_cooldown"
    assert "no request was sent" in body["playerMessage"]
    assert not transport._LLM_RATE_STATE["fixture-deadline"]["waiters"]
    assert endpoint.generation_activity_snapshot()["requests"] == []


def test_actual_stage_transition_preserves_request_identity(monkeypatch, route_worker, configured_profiles, real_route):
    first, second, resume_first, resume_second = (threading.Event() for _ in range(4))
    configured_profiles(local_profile())

    def authored(*_):
        first.set()
        assert resume_first.wait(5)
        return {"name": "stage observation fixture"}

    def validate(*_):
        second.set()
        assert resume_second.wait(5)
        raise PlannerUnavailable("controlled validation stop")

    monkeypatch.setattr(pipeline, "try_llm_plan", authored)
    monkeypatch.setattr(gameplay_stage, "strict_validate_authored_item", validate)
    worker = route_worker(real_route, dict(PAYLOAD), resume_first, resume_second)
    assert first.wait(3)
    one = endpoint.generation_activity_snapshot()["requests"][0]
    assert one["stage"] == "01_gameplay_author"
    resume_first.set()
    assert second.wait(3)
    two = endpoint.generation_activity_snapshot()["requests"][0]
    assert two["stage"] == "02_strict_runtime_program"
    assert two["requestId"] == one["requestId"]
    assert two["elapsedSeconds"] >= one["elapsedSeconds"]
    assert two["waitReason"] == "none" and two["networkStarted"] is None
    resume_first.set()
    resume_second.set()
    worker.thread.join(5)
    assert not worker.thread.is_alive()
    assert worker.results[0][0] == 422
    assert endpoint.generation_activity_snapshot()["requests"] == []


def test_healthy_cache_sibling_cannot_clear_disabled_lane_response(monkeypatch, route_worker, configured_profiles, real_route, tmp_path):
    _, good = valid_cached_recipe(tmp_path, monkeypatch)
    entered, resume = threading.Event(), threading.Event()
    configured_profiles(local_profile())

    def park(*_):
        entered.set()
        assert resume.wait(5)
        raise PlannerUnavailable("active sibling stopped")

    monkeypatch.setattr(pipeline, "try_llm_plan", park)
    worker = route_worker(real_route, {**PAYLOAD, "worldId": "active-world", "multiDevCraft": True, "llmProfileId": "llm_1"}, resume)
    assert entered.wait(3)
    status, failed = real_route({**PAYLOAD, "worldId": "disabled-world", "multiDevCraft": True, "llmProfileId": "llm_2"})
    assert status == 424 and failed["error"] == "llm_profile_unavailable"
    status, cached = real_route(dict(PAYLOAD))
    assert status == 200 and cached["id"] == good["id"]
    assert generation_debug.last_combine_failure_summary() == {}
    assert failed["lastFailure"]["worldId"] == "disabled-world"
    rows = endpoint.generation_activity_snapshot()["requests"]
    assert len(rows) == 1 and rows[0]["profileId"] == "llm_1"
    resume.set()
    worker.thread.join(5)
    assert not worker.thread.is_alive()
    assert worker.results[0][1]["lastFailure"]["worldId"] == "active-world"


def test_activity_projection_is_bounded_and_unknowns_are_not_private_values():
    from contextlib import ExitStack

    with ExitStack() as stack:
        for _ in range(35):
            stack.enter_context(endpoint._GenerationAdmission("PRIVATE-PROFILE"))
        endpoint.update_generation_activity(profile_id="PRIVATE-PROFILE", wait_reason="PRIVATE-REASON", network_started="PRIVATE")
        with endpoint.generation_stage("PRIVATE-STAGE"):
            # The latest row is omitted, but admitted counts remain exact.
            snapshot = endpoint.generation_activity_snapshot()
            assert snapshot["waiting"] == 35 and len(snapshot["requests"]) == 32 and snapshot["requestsOmitted"] == 3
            assert "PRIVATE" not in json.dumps(snapshot)
    assert endpoint.generation_activity_snapshot()["requests"] == []
    assert endpoint._CURRENT_GENERATION.get() is None


@pytest.mark.parametrize("bad", [{"code": ["PRIVATE"]}, {"param": {"PRIVATE": 1}}, {"code": "PRIVATE", "param": "PRIVATE"}])
def test_provider_metadata_unknowns_never_echo_arbitrary_values(bad):
    from infini_local.storage import failure_state

    metadata = transport._provider_error_metadata(json.dumps({"error": bad}))
    assert "PRIVATE" not in json.dumps(metadata)
    snapshot = failure_state.summarize_failure(
        {
            "ok": False,
            "transportDebug": {
                "failureCategory": "PRIVATE",
                "providerErrorCode": "PRIVATE",
                "providerErrorParam": "PRIVATE",
                "httpStatus": float("inf"),
            },
        }
    )
    assert "PRIVATE" not in json.dumps(snapshot) and "Infinity" not in json.dumps(snapshot)


def test_deadline_during_http_error_body_is_deadline_not_stale_provider_status():
    from infini_local.core.http_io import HttpDeadlineExceeded

    metadata = transport._failure_metadata(
        HttpDeadlineExceeded("body read budget"), {"httpStatus": 404, "providerErrorCode": "model_not_found", "networkStarted": True}
    )
    assert metadata["failureCategory"] == "logical_timeout"


@pytest.mark.parametrize("phase", ["begin", "end"])
def test_lease_context_is_released_even_when_diagnostic_logging_fails(monkeypatch, configured_profiles, phase):
    configured_profiles(local_profile())

    def broken_log(*_):
        raise OSError("diagnostic write failed")

    if phase == "end":
        lease, token = transport.begin_llm_item_lease("offline-key")
    monkeypatch.setattr(transport, "log_event", broken_log)
    with pytest.raises(OSError, match="diagnostic write failed"):
        if phase == "begin":
            transport.begin_llm_item_lease("offline-key")
        else:
            transport.end_llm_item_lease(lease, token)
    assert transport.current_llm_item_lease() is None


def test_profile_permit_is_returned_if_generation_admission_raises(monkeypatch):
    class BrokenSemaphore:
        def acquire(self, **_):
            raise OSError("controlled semaphore failure")

        def release(self):
            pytest.fail("no global permit was acquired")

    profile = threading.BoundedSemaphore(1)
    monkeypatch.setattr(endpoint, "MULTIDEV_PROFILE_SEMAPHORES", {"llm_2": profile})
    monkeypatch.setattr(endpoint, "MULTIDEV_SEMAPHORE", BrokenSemaphore())
    with pytest.raises(OSError, match="controlled semaphore failure"):
        endpoint.handle_combine_request(
            {**PAYLOAD, 'multiDevCraft': True, 'llmProfileId': 'llm_2'}, **endpoint_options(
                combine=lambda _: pytest.fail('admission failed'),
                json=lambda _: None,
                json_status=lambda *_: None,
            ),
        )
    assert profile.acquire(blocking=False), "already acquired lane permit leaked on admission exception"
    profile.release()
