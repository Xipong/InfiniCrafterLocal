"""Offline witnesses for independent body/entity image scheduling (no paid API)."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
import subprocess
import sys
import threading

import pytest

from infini_local.pipelines.images import stage as generation
from infini_local.services.sdcpp_service import ImageRequestGate
from tests.vfx_image_fixtures import _data, _request, _existing_texture_data, offline_backend  # noqa: F401


@pytest.mark.parametrize("capacity", [1, 2, 4])
def test_body_and_projectiles_overlap_only_within_global_bound(offline_backend, monkeypatch, capacity):
    data = _existing_texture_data("entity")
    orb = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "orb")
    for index in range(5):
        sibling = copy.deepcopy(orb)
        sibling["id"] = f"extra_{index}"
        sibling["visual"]["prompt"] = f"literal amber orb {index}"
        data["runtimeProgram"]["entities"].append(sibling)
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(capacity))
    backend = generation.generate_sdcpp
    lock = threading.Lock()
    active = peak = 0
    first_wave = threading.Barrier(capacity)
    calls = 0

    def transport(*args, **kwargs):
        nonlocal active, peak, calls
        with lock:
            active += 1
            peak = max(peak, active)
            calls += 1
            ordinal = calls
        try:
            if ordinal <= capacity:
                first_wave.wait(timeout=3)
            return backend(*args, **kwargs)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    out = generation.maybe_generate_visual_assets(data)
    assert peak == capacity
    assert active == 0
    assert calls == 7  # body + six explicitly baked projectiles
    assert out["visual"]["spriteStatus"] == "generated"
    for entity in out["runtimeProgram"]["entities"]:
        if entity["visual"]["assetMode"] == "baked_sprite":
            assert entity["visual"]["spriteStatus"] == "generated"


def test_repeated_roles_keep_own_prompt_despite_stale_snapshot(monkeypatch):
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    def fake(local, prompt):
        local.setdefault("debug", {})["runtime:projectileFinalPrompt"] = prompt
        return prompt
    jobs = [("entity:a", lambda d, *a: fake(d, "A"), ("runtime:projectile",), {}),
            ("entity:b", lambda d, *a: fake(d, "B"), ("runtime:projectile",), {})]
    monkeypatch.setattr(generation, "_independent_image_jobs", lambda *args: iter(jobs))
    data = {"debug": {"runtime:projectileFinalPrompt": "B", "unrelated": "keep"}}
    completed = generation._generate_independent_images(data, [])
    for role, expected in [("entity:a", "A"), ("entity:b", "B")]:
        assert generation._join_image_result(data, completed, role) == expected
        assert data["debug"]["runtime:projectileFinalPrompt"] == expected
    assert data["debug"]["unrelated"] == "keep"


@pytest.mark.parametrize("capacity", [1, 2])
def test_failed_projectile_is_not_published_and_sibling_survives(offline_backend, monkeypatch, capacity):
    data = _existing_texture_data("entity")
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(capacity))
    backend = generation.generate_sdcpp
    def transport(prompt, negative, asset_id, *args, **kwargs):
        if asset_id.endswith("_orb"):
            raise RuntimeError("offline provider failure")
        return backend(prompt, negative, asset_id, *args, **kwargs)
    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    out = generation.maybe_generate_visual_assets(data)
    orb = next(row for row in out["runtimeProgram"]["entities"] if row["id"] == "orb")
    assert orb["visual"]["spriteStatus"] == "failed"
    assert not orb["visual"]["spritePath"]
    assert out["visual"]["spriteStatus"] == "generated"


@pytest.mark.parametrize("toggle,limit,expected", [("0", "4", 1), ("1", "4", 4), ("1", "999", 4), (None, None, 4)])
def test_runtime_checkbox_overrides_saved_limit(toggle, limit, expected):
    env = dict(os.environ)
    for key, value in [("INFINI_IMAGE_PARALLEL", toggle), ("INFINI_IMAGE_MAX_CONCURRENCY", limit)]:
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    result = subprocess.run([sys.executable, "-c", "from infini_local.core.images.config import IMAGE_GENERATION_GATE; print(IMAGE_GENERATION_GATE.capacity)"], env=env, capture_output=True, text=True, check=True, timeout=20)
    assert int(result.stdout.strip().splitlines()[-1]) == expected


@pytest.fixture
def finish_during_join(monkeypatch):
    """Release blocked I/O at the real executor's synchronous-join boundary.

    Missing shutdown or wait=False leaves the worker visibly unfinished when
    the operation returns. Teardown still releases and joins every real pool.
    """
    release = threading.Event()
    pools = []

    class ObservedExecutor(ThreadPoolExecutor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            pools.append(self)

        def shutdown(self, wait=True, *, cancel_futures=False):
            if wait:
                release.set()
            return super().shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(generation, "ThreadPoolExecutor", ObservedExecutor)
    yield release
    release.set()
    for pool in pools:
        ThreadPoolExecutor.shutdown(pool, wait=True, cancel_futures=True)


def test_unexpected_worker_failure_joins_inflight_and_leaves_dto_untouched(monkeypatch, finish_during_join):
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    started = threading.Event()
    finished = threading.Event()
    def slow(local, role):
        started.set()
        assert finish_during_join.wait(5), "image worker was never joined"
        local["debug"]["unrelated"] = "worker only"
        finished.set()
    def fail(local, role):
        assert started.wait(2)
        raise ValueError("offline unexpected error")
    jobs = [("slow", slow, ("slow",), {}), ("fail", fail, ("fail",), {})]
    monkeypatch.setattr(generation, "_independent_image_jobs", lambda *args: iter(jobs))
    data = {"debug": {"unrelated": "original"}}
    with pytest.raises(ValueError, match="offline unexpected error"):
        generation._generate_independent_images(data, [])
    assert finished.is_set(), "do not leave a worker running after the failed craft returns"
    assert data == {"debug": {"unrelated": "original"}}


def test_single_slot_does_not_start_images_before_vfx(offline_backend, monkeypatch):
    data = _existing_texture_data("entity")
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(1))
    with generation.overlap_visual_images(data) as pending:
        assert pending is None
        assert not offline_backend[0]
        generation.maybe_generate_visual_assets(data, pending=pending)
    assert len(offline_backend[0]) == 2


def test_vfx_failure_joins_image_workers_without_mutating_input(offline_backend, monkeypatch, finish_during_join):
    data = _existing_texture_data("entity")
    frozen = copy.deepcopy(data)
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    backend = generation.generate_sdcpp
    in_flight = threading.Barrier(3)  # Body, projectile, and the failing VFX caller.
    started, completed = [], []
    def transport(prompt, negative, asset_id, *args, **kwargs):
        started.append(asset_id)
        in_flight.wait(timeout=5)
        assert finish_during_join.wait(5), "image worker was never joined"
        result = backend(prompt, negative, asset_id, *args, **kwargs)
        completed.append(asset_id)
        return result
    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    with pytest.raises(ValueError, match="VFX rejected"):
        with generation.overlap_visual_images(data):
            in_flight.wait(timeout=5)
            raise ValueError("VFX rejected")
    assert Counter(started) == Counter([data["id"], data["id"] + "_orb"])
    assert Counter(completed) == Counter(started), "all running images must finish before VFX failure returns"
    assert data == frozen


# Real stage/cache owners; only the external text and image services are inert.
from tests.test_generation_resume import craft  # noqa: E402,F401


def test_combine_overlaps_visual_calls_with_vfx_director(craft, offline_backend, monkeypatch):
    from infini_local.core.runtime_authoring.compiler import compile_runtime_program
    from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA
    from infini_local.core.vfx.materials import vfx_model_payload
    from infini_local.pipelines import combine_pipeline as pipeline
    from infini_local.pipelines.visual import request as visual_request
    from infini_local.pipelines.vfx import request as vfx_request
    from tests.prompt_packet_helpers import request_dossier
    from tests.vfx_image_fixtures import _slot

    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(4))
    backend = generation.generate_sdcpp
    item_started, entity_started, vfx_started = (threading.Event() for _ in range(3))
    calls, vfx_attempts = [], []
    authored_kit = None
    expected_runtime = compile_runtime_program(craft.authored)["runtimeProgram"]
    for entity in expected_runtime["entities"]:
        entity.pop("visual", None)

    def transport(prompt, negative, asset_id, *args, **kwargs):
        calls.append(asset_id)
        if asset_id.startswith("infini_vfx_job_"):
            vfx_attempts.append(asset_id)
            vfx_started.set()
        else:
            (entity_started if asset_id.endswith("_workbench_blade") else item_started).set()
            assert vfx_started.wait(15), "Visual calls must stay in flight until the new VFX job starts"
        return backend(prompt, negative, asset_id, *args, **kwargs)

    def visual(request, **kwargs):
        nonlocal authored_kit
        response = craft.text(request, **kwargs)
        authored_kit = json.loads(response["choices"][0]["message"]["content"])
        entity = next(row for row in authored_kit["entities"] if row["entityId"] == "workbench_blade")
        entity.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="one isolated amber blade",
                      silhouette="one blade", visualIdentity="amber blade", preferredCanvasSize=32,
                      renderSizePx=40, forwardAngleDegrees=45)
        response["choices"][0]["message"]["content"] = json.dumps(authored_kit)
        return response

    def director(request, **kwargs):
        assert item_started.wait(15) and entity_started.wait(15), "all accepted Visual jobs must start before VFX returns"
        packet = request_dossier(request)
        assert packet["acceptedVisualKit"] == authored_kit
        assert packet["acceptedRuntimeProgramReadOnly"] == expected_runtime
        item_id = packet["item"]["id"]
        assert Counter(calls) == Counter([item_id, item_id + "_workbench_blade"])
        response = craft.text(request, **kwargs)
        slot = _slot("first", "grain")
        slot["entityId"] = "workbench_blade"
        authored_vfx = {"schema": VFX_DIRECTOR_SCHEMA, "slots": [slot], "assets": [_request()]}
        response["choices"][0]["message"]["content"] = json.dumps(vfx_model_payload(authored_vfx))
        return response

    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    monkeypatch.setattr(visual_request, "llm_chat_json", visual)
    monkeypatch.setattr(vfx_request, "llm_chat_json", director)
    out = pipeline.combine(craft.request)
    assert out["visual"]["spriteStatus"] == "generated"
    assert out["vfxManifest"]["assets"][0]["spriteStatus"] == "generated"
    assert len(vfx_attempts) == 1
    expected = Counter([out["id"], out["id"] + "_workbench_blade", *vfx_attempts])
    assert Counter(calls) == expected, "Visual jobs must not be resubmitted when the VFX batch arrives"
    assert Counter(call["id"] for call in offline_backend[0]) == expected
