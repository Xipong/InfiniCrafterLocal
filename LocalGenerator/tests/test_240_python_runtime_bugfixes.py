from __future__ import annotations

import io
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

from infini_local.pipelines import combine_pipeline, generation_debug
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


def _contract_check_failure_record_keeps_each_exception_snapshot_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        generation_debug.failure_state,
        "build_combine_failure",
        lambda **kwargs: {
            "stage": kwargs["stage"],
            "payload": dict(kwargs.get("payload") or {}),
            "error": str(kwargs["error"]),
        },
    )
    monkeypatch.setattr(generation_debug.failure_state, "persist_failure", lambda *_args, **_kwargs: None)

    barrier = threading.Barrier(2)
    errors = [RuntimeError("request-a"), RuntimeError("request-b")]
    snapshots: list[dict] = [{}, {}]

    def worker(index: int) -> None:
        barrier.wait()
        snapshots[index] = generation_debug.record_combine_failure(
            f"stage-{index}",
            errors[index],
            {"request": index},
            None,
            [],
        )

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    for index, error in enumerate(errors):
        expected = {"stage": f"stage-{index}", "payload": {"request": index}, "error": f"request-{chr(97 + index)}"}
        assert snapshots[index] == expected
        assert getattr(error, "_infini_failure_snapshot") == expected

    snapshots[0]["payload"]["request"] = "mutated"
    assert getattr(errors[0], "_infini_failure_snapshot")["payload"]["request"] == 0


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
    invalid_values: tuple[object, ...] = (
        {"bad": object()},
        {"bad": float("nan")},
        {"bad": float("inf")},
        ["response-root-must-be-object"],
    )
    for invalid in invalid_values:
        monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", threading.BoundedSemaphore(1))
        statuses: list[tuple[int, dict]] = []
        delivered: list[object] = []
        combine_endpoint.handle_combine_request(
            {},
            app_version="test",
            combine_cache_lookup=lambda _payload: ("key", None),
            sanitize_recipe_for_delivery=lambda value: value,
            combine=lambda _payload, invalid=invalid: invalid,
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

    cleared: list[str] = []
    cached_statuses: list[tuple[int, dict]] = []
    combine_endpoint.handle_combine_request(
        {},
        app_version="test",
        combine_cache_lookup=lambda _payload: ("cached-key", {"bad": float("nan")}),
        sanitize_recipe_for_delivery=lambda value: value,
        combine=lambda _payload: {},
        trace_event=lambda *_args, **_kwargs: None,
        json=lambda _value: None,
        json_status=lambda status, value: cached_statuses.append((status, value)),
        clear_failure_state=cleared.append,
    )
    assert cached_statuses[0][0] == 500
    assert cleared == []


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


def _contract_check_visual_config_import_does_not_replace_process_signal_handlers() -> None:
    env = os.environ.copy()
    code = (
        "import json, signal; "
        "signals=[s for s in (getattr(signal,'SIGINT',None),getattr(signal,'SIGTERM',None)) if s is not None]; "
        "before=[signal.getsignal(s) for s in signals]; "
        "import infini_local.pipelines.pipeline_visual_config; "
        "after=[signal.getsignal(s) for s in signals]; "
        "print(json.dumps([a is b for a,b in zip(before,after)]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [True, True]
    server_source = Path(server.__file__).read_text(encoding="utf-8")
    main_block = server_source.split("def main() -> None:", 1)[1].split('if __name__ == "__main__":', 1)[0]
    assert "visual_config.install_sdcpp_cleanup_handlers()" in main_block


def _contract_check_sdcpp_cleanup_registration_is_lazy_and_worker_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lazy_state = sdcpp_service.SdcppServerState()
    assert sdcpp_service.ensure_server(
        state=lazy_state,
        root=tmp_path,
        cache_dir=tmp_path,
        server_url="http://127.0.0.1:7861",
        server_autostart=False,
        startup_timeout=1,
        show_console=False,
        server_log_file=str(tmp_path / "unused.log"),
        server_is_alive=lambda: False,
        build_command=lambda: (_ for _ in ()).throw(AssertionError("autostart disabled")),
        stringify_cmd=lambda _cmd: "",
        cleanup_process=lambda _reason: None,
        log_event=lambda *_args: None,
        tail_text_file=lambda *_args: "",
    ) is False
    assert lazy_state.cleanup_registered is False
    assert lazy_state.signal_handlers_registered is False

    atexit_calls: list[object] = []
    signal_calls: list[object] = []
    monkeypatch.setattr(sdcpp_service.atexit, "register", lambda callback: atexit_calls.append(callback))
    monkeypatch.setattr(sdcpp_service.signal, "getsignal", lambda _sig: sdcpp_service.signal.SIG_DFL)
    monkeypatch.setattr(
        sdcpp_service.signal,
        "signal",
        lambda sig, handler: signal_calls.append((sig, handler)),
    )
    state = sdcpp_service.SdcppServerState()
    cleanup = lambda _reason: None
    worker = threading.Thread(target=sdcpp_service.install_cleanup_handlers, args=(state, cleanup))
    worker.start()
    worker.join(timeout=3)
    assert worker.is_alive() is False
    assert state.cleanup_registered is True
    assert state.signal_handlers_registered is False
    assert len(atexit_calls) == 1
    assert signal_calls == []

    sdcpp_service.install_cleanup_handlers(state, cleanup)
    assert state.signal_handlers_registered is True
    assert len(atexit_calls) == 1
    assert len(signal_calls) == 2


def _contract_check_sdcpp_spawn_failure_closes_log_handle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state = sdcpp_service.SdcppServerState(
        cleanup_registered=True,
        signal_handlers_registered=True,
    )
    log_handle = io.StringIO()
    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: log_handle)

    def fail_popen(*_args, **_kwargs):
        raise OSError("synthetic spawn failure")

    monkeypatch.setattr(sdcpp_service.subprocess, "Popen", fail_popen)
    result = sdcpp_service.ensure_server(
        state=state,
        root=tmp_path,
        cache_dir=tmp_path,
        server_url="http://127.0.0.1:7861",
        server_autostart=True,
        startup_timeout=1,
        show_console=False,
        server_log_file=str(tmp_path / "sdcpp.log"),
        server_is_alive=lambda: False,
        build_command=lambda: (["fake-sdcpp"], False),
        stringify_cmd=lambda cmd: " ".join(cmd),
        cleanup_process=lambda _reason: None,
        log_event=lambda *_args: None,
        tail_text_file=lambda *_args: "",
    )

    assert result is False
    assert log_handle.closed is True
    assert state.process is None
    assert "synthetic spawn failure" in state.last_start_error


def _contract_check_parallel_sdcpp_ensure_spawns_only_one_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Keep the test-owned fake process out of the interpreter's real atexit list.
    monkeypatch.setattr(sdcpp_service.atexit, "register", lambda _callback: None)
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
            '_contract_check_failure_record_keeps_each_exception_snapshot_isolated',
            '_contract_check_busy_combine_returns_409_without_releasing_unacquired_semaphore',
            '_contract_check_combine_rejects_non_json_serializable_delivery_payload',
            '_contract_check_cached_combine_clears_stale_failure_diagnostics_before_delivery',
            '_contract_check_failure_summary_error_does_not_mask_original_combine_exception',
            '_contract_check_server_main_clamps_invalid_port_before_binding',
            '_contract_check_sdcpp_readiness_rejects_http_404',
            '_contract_check_invalid_sdcpp_env_is_bounded_once_and_shared_by_backend',
            '_contract_check_visual_config_import_does_not_replace_process_signal_handlers',
            '_contract_check_sdcpp_cleanup_registration_is_lazy_and_worker_safe',
            '_contract_check_sdcpp_spawn_failure_closes_log_handle',
            '_contract_check_parallel_sdcpp_ensure_spawns_only_one_process',
        ),
    )
