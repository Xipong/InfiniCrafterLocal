from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError

import pytest

from infini_local.pipelines import combine_pipeline
from infini_local.services import combine_endpoint, sdcpp_backend, sdcpp_service
from infini_local.web import server


def _contract_check_dev_fallback_helper_exposes_runtime_api_version() -> None:
    helpers = combine_pipeline._dev_fallback_helpers()
    assert helpers["ENGINE_RUNTIME_API_VERSION"]


def _contract_check_dev_fallback_resolves_its_package_owner() -> None:
    result = combine_pipeline.deterministic_plan(
        {"name": "Copper Shortsword"},
        {"name": "Gel"},
        {},
        {},
        "fallback-owner-test",
    )
    assert isinstance(result, dict)


def _contract_check_combine_exception_carries_immutable_request_failure_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", semaphore)
    failure = {"request": "A", "stage": "planner"}

    class CraftFailed(RuntimeError):
        pass

    def fail_combine(_payload: dict) -> dict:
        raise CraftFailed("boom")

    with pytest.raises(CraftFailed) as caught:
        combine_endpoint.handle_combine_request(
            {},
            app_version="test",
            combine_cache_lookup=lambda _payload: ("key", None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=fail_combine,
            trace_event=lambda *_args, **_kwargs: None,
            json=lambda _value: None,
            json_status=lambda _status, _value: None,
            last_failure_summary=lambda: dict(failure),
        )

    failure.clear()
    assert getattr(caught.value, "_infini_failure_snapshot") == {"request": "A", "stage": "planner"}
    assert semaphore.acquire(blocking=False) is True
    semaphore.release()


def _contract_check_busy_combine_returns_409_without_releasing_unacquired_semaphore(monkeypatch: pytest.MonkeyPatch) -> None:
    semaphore = threading.BoundedSemaphore(1)
    assert semaphore.acquire(blocking=False) is True
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", semaphore)
    monkeypatch.setattr(combine_endpoint, "COMBINE_BUSY_WAIT_SECONDS", 0)
    statuses: list[tuple[int, dict]] = []
    combine_called = False

    def combine(_payload: dict) -> dict:
        nonlocal combine_called
        combine_called = True
        return {}

    combine_endpoint.handle_combine_request(
        {},
        app_version="test",
        combine_cache_lookup=lambda _payload: ("key", None),
        sanitize_recipe_for_delivery=lambda value: value,
        combine=combine,
        trace_event=lambda *_args, **_kwargs: None,
        json=lambda _value: None,
        json_status=lambda status, value: statuses.append((status, value)),
    )

    assert combine_called is False
    assert statuses[0][0] == 409
    semaphore.release()
    assert semaphore.acquire(blocking=False) is True
    semaphore.release()


def _contract_check_combine_rejects_non_json_serializable_delivery_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", threading.BoundedSemaphore(1))
    statuses: list[tuple[int, dict]] = []
    delivered: list[dict] = []

    combine_endpoint.handle_combine_request(
        {},
        app_version="test",
        combine_cache_lookup=lambda _payload: ("key", None),
        sanitize_recipe_for_delivery=lambda value: value,
        combine=lambda _payload: {"bad": object()},
        trace_event=lambda *_args, **_kwargs: None,
        json=delivered.append,
        json_status=lambda status, value: statuses.append((status, value)),
    )

    assert delivered == []
    assert len(statuses) == 1
    status, payload = statuses[0]
    assert status == 500
    assert payload["ok"] is False
    assert payload["status"] == "combine_response_not_json_serializable"
    assert payload["error"] == "combine_response_not_json_serializable"
    assert payload["httpStatus"] == 500
    assert payload["cacheRecoveryAllowed"] is False


def _contract_check_cached_combine_clears_stale_failure_diagnostics_before_delivery() -> None:
    clear_reasons: list[str] = []
    delivered: list[dict] = []

    combine_endpoint.handle_combine_request(
        {"cacheOnly": True},
        app_version="test",
        combine_cache_lookup=lambda _payload: ("cached-key", {"id": "cached-item"}),
        sanitize_recipe_for_delivery=lambda value: value,
        combine=lambda _payload: (_ for _ in ()).throw(AssertionError("cache hit must not generate")),
        trace_event=lambda *_args, **_kwargs: None,
        json=delivered.append,
        json_status=lambda _status, _value: None,
        clear_failure_state=clear_reasons.append,
    )

    assert clear_reasons == ["endpoint_cache_hit_delivered"]
    assert delivered == [{"id": "cached-item"}]


def _contract_check_failure_summary_error_does_not_mask_original_combine_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", threading.BoundedSemaphore(1))

    class CraftFailed(RuntimeError):
        pass

    def fail_combine(_payload: dict) -> dict:
        raise CraftFailed("craft failed")

    def broken_summary() -> dict:
        raise ValueError("summary failed")

    with pytest.raises(CraftFailed, match="craft failed"):
        combine_endpoint.handle_combine_request(
            {},
            app_version="test",
            combine_cache_lookup=lambda _payload: ("key", None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=fail_combine,
            trace_event=lambda *_args, **_kwargs: None,
            json=lambda _value: None,
            json_status=lambda _status, _value: None,
            last_failure_summary=broken_summary,
        )


def _contract_check_server_main_clamps_invalid_port_before_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    bound: dict[str, object] = {}

    class FakeHttpServer:
        def __init__(self, address: tuple[str, int], _handler: object) -> None:
            bound["address"] = address

        def serve_forever(self) -> None:
            bound["served"] = True

    monkeypatch.setenv("INFINI_PORT", "-7")
    monkeypatch.setenv("INFINI_IMAGE_BACKEND", "off")
    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeHttpServer)
    server.main()

    assert bound["address"] == ("127.0.0.1", 1)
    assert bound["served"] is True



def _contract_check_sdcpp_readiness_rejects_http_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args, **_kwargs):
        raise HTTPError("http://127.0.0.1:7861/health", 404, "not found", Message(), None)

    monkeypatch.setattr(sdcpp_backend.urlrequest, "urlopen", not_found)
    assert sdcpp_backend.server_is_alive("http://127.0.0.1:7861", ["/health"], timeout=1) is False


def _contract_check_invalid_sdcpp_env_is_bounded_once_and_shared_by_backend() -> None:
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "INFINI_SDCPP_WIDTH": "-5",
        "INFINI_SDCPP_HEIGHT": "99999",
        "INFINI_SDCPP_STEPS": "0",
        "INFINI_SDCPP_CFG": "-2",
        "INFINI_SDCPP_SERVER_PORT": "70000",
    })
    code = (
        "import json; "
        "from infini_local.pipelines import pipeline_visual_config as v, image_backend_pipeline as i; "
        "print(json.dumps([v.SDCPP_WIDTH,v.SDCPP_HEIGHT,v.SDCPP_STEPS,v.SDCPP_CFG,v.SDCPP_SERVER_PORT,i.SDCPP_WIDTH,i.SDCPP_HEIGHT]))"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True, check=True, timeout=30)
    assert json.loads(result.stdout.strip()) == [64, 2048, 1, 0.0, 65535, 64, 2048]


def _contract_check_parallel_sdcpp_ensure_spawns_only_one_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    state = sdcpp_service.SdcppServerState()
    spawn_ids: list[int] = []
    spawn_lock = threading.Lock()

    class FakeProcess:
        returncode = None

        def __init__(self, ident: int) -> None:
            self.ident = ident

        def poll(self):
            return None

        def terminate(self) -> None:
            self.returncode = 0

        def wait(self, timeout=None) -> int:
            self.returncode = 0
            return 0

        def kill(self) -> None:
            self.returncode = -9

    def fake_popen(*_args, **_kwargs):
        with spawn_lock:
            ident = len(spawn_ids) + 1
            spawn_ids.append(ident)
        return FakeProcess(ident)

    def alive() -> bool:
        with spawn_lock:
            spawned = bool(spawn_ids)
        if not spawned:
            time.sleep(0.05)
            return False
        return True

    monkeypatch.setattr(sdcpp_service.subprocess, "Popen", fake_popen)
    cleanup = lambda reason: sdcpp_service.cleanup_server_process(state, lambda *_args: None, reason)
    kwargs = dict(
        state=state,
        root=tmp_path,
        cache_dir=tmp_path,
        server_url="http://127.0.0.1:7861",
        server_autostart=True,
        startup_timeout=1,
        show_console=False,
        server_log_file=str(tmp_path / "sdcpp.log"),
        server_is_alive=alive,
        build_command=lambda: (["fake-sdcpp"], False),
        stringify_cmd=lambda cmd: " ".join(cmd),
        cleanup_process=cleanup,
        log_event=lambda *_args: None,
        tail_text_file=lambda *_args: "",
    )
    start = threading.Barrier(2)
    results: list[bool] = []

    def worker() -> None:
        start.wait()
        results.append(sdcpp_service.ensure_server(**kwargs))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert results == [True, True]
    assert spawn_ids == [1]


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_240_python_runtime_bugfixes_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_dev_fallback_helper_exposes_runtime_api_version',
            '_contract_check_dev_fallback_resolves_its_package_owner',
            '_contract_check_combine_exception_carries_immutable_request_failure_snapshot',
            '_contract_check_busy_combine_returns_409_without_releasing_unacquired_semaphore',
            '_contract_check_combine_rejects_non_json_serializable_delivery_payload',
            '_contract_check_cached_combine_clears_stale_failure_diagnostics_before_delivery',
            '_contract_check_failure_summary_error_does_not_mask_original_combine_exception',
            '_contract_check_server_main_clamps_invalid_port_before_binding',
            '_contract_check_sdcpp_readiness_rejects_http_404',
            '_contract_check_invalid_sdcpp_env_is_bounded_once_and_shared_by_backend',
            '_contract_check_parallel_sdcpp_ensure_spawns_only_one_process',
        ),
    )
