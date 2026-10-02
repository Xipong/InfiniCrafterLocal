"""Runtime-service owners of historical Python boundary regressions.

These are deliberately not provider-only checks: combine delivery/semaphores,
image-service readiness/lifecycle, and import/startup ownership live here.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from infini_local.pipelines import combine_pipeline, generation_debug
from infini_local.services import combine_endpoint, sdcpp_backend, sdcpp_service
from infini_local.web import server


@pytest.fixture
def endpoint(monkeypatch):
    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(combine_endpoint, "COMBINE_SEMAPHORE", semaphore)
    monkeypatch.setattr(combine_endpoint, "COMBINE_BUSY_WAIT_SECONDS", 0)
    delivered, statuses, cleared, events = [], [], [], []
    return SimpleNamespace(semaphore=semaphore, delivered=delivered, statuses=statuses, cleared=cleared, events=events,
        options=dict(app_version="test", combine_cache_lookup=lambda _: ("key", None),
            sanitize_recipe_for_delivery=lambda value: value, combine=lambda _: {"ok": True},
            trace_event=lambda *args: events.append(args), json=delivered.append,
            json_status=lambda status, value: statuses.append((status, value)), clear_failure_state=cleared.append))


@pytest.mark.parametrize("source,invalid", [
    pytest.param(source, invalid, id=source + "-" + label)
    for source in ("fresh", "cache") for label, invalid in [
        ("nonserializable", {"bad": object()}), ("nan", {"bad": float("nan")}),
        ("infinity", {"bad": float("inf")}), ("array-root", ["response-root-must-be-object"]),
    ]
])
def test_combine_delivery_rejects_invalid_json_without_cache_recovery(endpoint, source, invalid):
    options = dict(endpoint.options)
    if source == "cache":
        options["combine_cache_lookup"] = lambda _: ("cached-key", invalid)
        options["combine"] = lambda _: pytest.fail("invalid cache must not generate")
    else:
        options["combine"] = lambda _: invalid
    combine_endpoint.handle_combine_request({}, **options)
    assert endpoint.delivered == [] and len(endpoint.statuses) == 1
    status, payload = endpoint.statuses[0]
    assert status == 500
    assert payload["ok"] is False
    assert payload["status"] == payload["error"] == "combine_response_not_json_serializable"
    assert payload["httpStatus"] == 500 and payload["cacheRecoveryAllowed"] is False
    assert endpoint.cleared == []


@pytest.mark.parametrize("scenario", ["busy", "cache-hit", "cache-error", "craft-error", "summary-error"])
def test_combine_endpoint_preserves_admission_cache_and_failure_owner(endpoint, scenario):
    options = dict(endpoint.options)
    failure = {"request": "A", "stage": "planner"}
    craft_error = RuntimeError("craft failed")
    if scenario == "busy":
        assert endpoint.semaphore.acquire(blocking=False) is True
        options["combine"] = lambda _: pytest.fail("busy combine must not run")
    elif scenario == "cache-hit":
        options["combine_cache_lookup"] = lambda _: ("cached-key", {"id": "cached-item"})
        options["combine"] = lambda _: pytest.fail("cache hit must not generate")
    elif scenario == "cache-error":
        options["combine_cache_lookup"] = lambda _: (_ for _ in ()).throw(OSError("cache unavailable"))
    else:
        options["combine"] = lambda _: (_ for _ in ()).throw(craft_error)
        options["last_failure_summary"] = (lambda: (_ for _ in ()).throw(ValueError("summary failed"))) if scenario == "summary-error" else lambda: dict(failure)
    if scenario.endswith("error") and scenario != "cache-error":
        with pytest.raises(RuntimeError, match="craft failed") as caught:
            combine_endpoint.handle_combine_request({}, **options)
        assert caught.value is craft_error
        if scenario == "craft-error":
            failure.clear()
            assert caught.value._infini_failure_snapshot == {"request": "A", "stage": "planner"}
    else:
        combine_endpoint.handle_combine_request({"cacheOnly": scenario == "cache-hit"}, **options)
        if scenario == "busy":
            assert endpoint.statuses[0][0] == 409
            assert not endpoint.delivered
            # The endpoint did not release a permit it never acquired.
            assert endpoint.semaphore.acquire(blocking=False) is False
            endpoint.semaphore.release()
        elif scenario == "cache-hit":
            assert endpoint.cleared == ["endpoint_cache_hit_delivered"]
            assert endpoint.delivered == [{"id": "cached-item"}]
        else:
            assert endpoint.delivered == [{"ok": True}]
            assert any(event[:3] == ("warn", "HTTP:/combine", "world recipe cache lookup failed; continuing with fresh generation") for event in endpoint.events)
    assert endpoint.semaphore.acquire(blocking=False) is True
    endpoint.semaphore.release()


@pytest.mark.parametrize("port,expected", [("-7", 1), ("70000", 65535)])
def test_server_startup_owns_cleanup_registration_before_bounded_bind(monkeypatch, port, expected):
    events = []
    monkeypatch.setenv("INFINI_PORT", port)
    monkeypatch.setenv("INFINI_HOST", "127.0.0.1")
    monkeypatch.setenv("INFINI_IMAGE_BACKEND", "off")
    monkeypatch.setattr(server, "initialize_trace_storage", lambda: None)
    monkeypatch.setattr(server.visual_config, "install_sdcpp_cleanup_handlers", lambda: events.append("cleanup"))
    monkeypatch.setattr(server, "ThreadingHTTPServer", lambda address, handler: events.append(address) or SimpleNamespace(serve_forever=lambda: events.append("served")))
    server.main()
    assert events == ["cleanup", ("127.0.0.1", expected), "served"]


@pytest.mark.parametrize("path,status,body,expected", [
    pytest.param("/health", 404, b"", False, id="404-not-ready"),
    pytest.param("/health", 200, b'{"status":"ok"}', False, id="unrelated-200-not-ready"),
    pytest.param("/sdapi/v1/sd-models", 200, b'[{"model_name":"flux"}]', True, id="model-roster-ready"),
])
def test_sdcpp_readiness_identifies_the_actual_image_service(monkeypatch, path, status, body, expected):
    def open_url(url, **kwargs):
        if status != 200:
            raise HTTPError(url, status, "not found", {}, None)
        result = io.BytesIO(body)
        result.status = status
        return result
    monkeypatch.setattr(sdcpp_backend.urlrequest, "urlopen", open_url)
    paths = ["/", path] if path == "/health" and status == 200 else [path]
    assert sdcpp_backend.server_is_alive("http://127.0.0.1:7861", paths, timeout=1) is expected


@pytest.mark.parametrize("probe,overrides,code,expected", [
    pytest.param("bounded-env", {"INFINI_SDCPP_WIDTH": "-5", "INFINI_SDCPP_HEIGHT": "99999",
        "INFINI_SDCPP_STEPS": "0", "INFINI_SDCPP_CFG": "-2", "INFINI_SDCPP_SERVER_PORT": "70000"},
        "from infini_local.pipelines import pipeline_visual_config as v, image_backend_pipeline as i; print(json.dumps([v.SDCPP_WIDTH,v.SDCPP_HEIGHT,v.SDCPP_STEPS,v.SDCPP_CFG,v.SDCPP_SERVER_PORT,i.SDCPP_WIDTH,i.SDCPP_HEIGHT]))",
        [64, 2048, 1, 0.0, 65535, 64, 2048], id="bounded-env-shared-backend"),
    pytest.param("signal-import", {},
        "import signal; signals=[s for s in (getattr(signal,'SIGINT',None),getattr(signal,'SIGTERM',None)) if s is not None]; before=[signal.getsignal(s) for s in signals]; import infini_local.pipelines.pipeline_visual_config; after=[signal.getsignal(s) for s in signals]; print(json.dumps([a is b for a,b in zip(before,after)]))",
        [True, True], id="import-does-not-own-process-signals"),
])
def test_visual_configuration_is_bounded_and_import_inert(probe, overrides, code, expected):
    env = {**os.environ, **overrides}
    package_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = package_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run([sys.executable, "-c", "import json; " + code], env=env, text=True,
                            capture_output=True, check=True, timeout=30)
    assert json.loads(result.stdout.strip().splitlines()[-1]) == expected


@pytest.fixture
def service_options(tmp_path):
    return dict(state=sdcpp_service.SdcppServerState(), root=tmp_path, cache_dir=tmp_path,
        server_url="http://127.0.0.1:7861", server_autostart=True, startup_timeout=1,
        show_console=False, server_log_file=str(tmp_path / "sdcpp.log"), server_is_alive=lambda: False,
        build_command=lambda: (["fake-sdcpp"], False), stringify_cmd=lambda cmd: " ".join(cmd),
        cleanup_process=lambda _reason: None, log_event=lambda *_args: None, tail_text_file=lambda *_args: "")


def test_sdcpp_cleanup_is_lazy_worker_safe_and_registered_once(monkeypatch, service_options):
    lazy = sdcpp_service.SdcppServerState()
    assert sdcpp_service.ensure_server(**{**service_options, "state": lazy, "server_autostart": False,
        "build_command": lambda: pytest.fail("autostart disabled")}) is False
    assert lazy.cleanup_registered is False and lazy.signal_handlers_registered is False
    atexit_calls, signal_calls = [], []
    monkeypatch.setattr(sdcpp_service.atexit, "register", atexit_calls.append)
    monkeypatch.setattr(sdcpp_service.signal, "getsignal", lambda _sig: sdcpp_service.signal.SIG_DFL)
    monkeypatch.setattr(sdcpp_service.signal, "signal", lambda sig, handler: signal_calls.append((sig, handler)))
    state = service_options["state"]
    cleanup = lambda _reason: None
    worker = threading.Thread(target=sdcpp_service.install_cleanup_handlers, args=(state, cleanup))
    worker.start()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert state.cleanup_registered is True and state.signal_handlers_registered is False
    assert len(atexit_calls) == 1 and signal_calls == []
    sdcpp_service.install_cleanup_handlers(state, cleanup)
    assert state.signal_handlers_registered is True
    assert len(atexit_calls) == 1 and len(signal_calls) == 2


def test_sdcpp_spawn_failure_closes_unowned_log_handle(monkeypatch, service_options):
    state = service_options["state"]
    state.cleanup_registered = state.signal_handlers_registered = True
    log_handle = io.StringIO()
    monkeypatch.setattr("builtins.open", lambda *_a, **_k: log_handle)
    monkeypatch.setattr(sdcpp_service.subprocess, "Popen", lambda *_a, **_k: (_ for _ in ()).throw(OSError("synthetic spawn failure")))
    assert sdcpp_service.ensure_server(**service_options) is False
    assert log_handle.closed is True and state.process is None
    assert "synthetic spawn failure" in state.last_start_error


def test_parallel_sdcpp_ensure_has_one_process_owner(monkeypatch, service_options):
    monkeypatch.setattr(sdcpp_service.atexit, "register", lambda _callback: None)
    monkeypatch.setattr(sdcpp_service.signal, "signal", lambda *_args: None)
    spawn_ids, results = [], []
    lock, start = threading.Lock(), threading.Barrier(2)
    def spawn(*args, **kwargs):
        with lock:
            spawn_ids.append(len(spawn_ids) + 1)
        return SimpleNamespace(returncode=None, poll=lambda: None)
    def alive():
        with lock:
            spawned = bool(spawn_ids)
        if not spawned:
            time.sleep(0.05)
        return spawned
    def worker():
        start.wait(timeout=3)
        results.append(sdcpp_service.ensure_server(**service_options))
    monkeypatch.setattr(sdcpp_service.subprocess, "Popen", spawn)
    service_options["server_is_alive"] = alive
    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert results == [True, True] and spawn_ids == [1]


def test_dev_fallback_resolves_its_package_owner() -> None:
    result = combine_pipeline.deterministic_plan(
        {"name": "Copper Shortsword"},
        {"name": "Gel"},
        {},
        {},
        "fallback-owner-test",
    )
    from infini_local.core.runtime_authoring import (
        compile_runtime_program, validate_runtime_program, validate_runtime_wire,
    )
    report = validate_runtime_program(result)
    assert report["ok"], report["errors"]
    wire = compile_runtime_program(result)
    wire_report = validate_runtime_wire(wire)
    assert wire_report["ok"], wire_report["errors"]
    entities = {entity["id"]: entity for entity in wire["runtimeProgram"]["entities"]}
    assert entities["held_body"]["spawn"]["speedPxPerTick"] == 1.0
    assert entities["child_shard"]["spawn"]["speedPxPerTick"] == 9.0
    assert entities["child_shard"]["collision"]["localNpcHitCooldownTicks"] == -1
    assert entities["child_shard"]["movement"]["params"]["gravityPerTick"] == 0.12


def test_failure_record_keeps_each_exception_snapshot_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
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
