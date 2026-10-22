"""Offline witnesses for independent body/entity image scheduling (no paid API)."""
import copy
import os
import subprocess
import sys
import threading
import time

import pytest

from infini_local.pipelines import visual_sprite_generation as generation
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
            time.sleep(.01)
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
    result = subprocess.run([sys.executable, "-c", "from infini_local.pipelines.pipeline_visual_config import IMAGE_GENERATION_GATE; print(IMAGE_GENERATION_GATE.capacity)"], env=env, capture_output=True, text=True, check=True, timeout=20)
    assert int(result.stdout.strip().splitlines()[-1]) == expected


def test_unexpected_worker_failure_joins_inflight_and_leaves_dto_untouched(monkeypatch):
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    started = threading.Event()
    finished = threading.Event()
    def slow(local, role):
        started.set()
        time.sleep(.05)
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


def test_visual_images_start_before_vfx_and_new_jobs_share_batch(offline_backend, monkeypatch):
    data = _existing_texture_data("entity")
    data.pop("vfxManifest")
    frozen = copy.deepcopy(data)
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(4))
    backend = generation.generate_sdcpp
    item_started, entity_started, vfx_started = (threading.Event() for _ in range(3))
    calls = []
    def transport(prompt, negative, asset_id, *args, **kwargs):
        calls.append(asset_id)
        if asset_id.startswith("infini_vfx_job_"):
            vfx_started.set()
        else:
            (entity_started if asset_id.endswith("_orb") else item_started).set()
            assert vfx_started.wait(3), "Visual calls remain in flight until VFX enqueues its job"
        return backend(prompt, negative, asset_id, *args, **kwargs)
    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    with generation.overlap_visual_images(data) as pending:
        assert pending is not None
        assert item_started.wait(3) and entity_started.wait(3)
        assert data == frozen, "VFX receives an unmutated Visual DTO while PNGs are in flight"
        # Stand-in for the accepted VFX Director result arriving later.
        data["vfxManifest"] = _data([_request()])["vfxManifest"]
        out = generation.maybe_generate_visual_assets(data, pending=pending)
    assert len(calls) == 3 and len(set(calls)) == 3
    assert out["visual"]["spriteStatus"] == "generated"
    assert out["vfxManifest"]["assets"][0]["spriteStatus"] == "generated"


def test_single_slot_does_not_start_images_before_vfx(offline_backend, monkeypatch):
    data = _existing_texture_data("entity")
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(1))
    with generation.overlap_visual_images(data) as pending:
        assert pending is None
        assert not offline_backend[0]
        generation.maybe_generate_visual_assets(data, pending=pending)
    assert len(offline_backend[0]) == 2


def test_vfx_failure_joins_image_workers_without_mutating_input(offline_backend, monkeypatch):
    data = _existing_texture_data("entity")
    frozen = copy.deepcopy(data)
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    backend = generation.generate_sdcpp
    started, done = threading.Event(), threading.Event()
    def transport(*args, **kwargs):
        started.set()
        time.sleep(.05)
        result = backend(*args, **kwargs)
        done.set()
        return result
    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    with pytest.raises(ValueError, match="VFX rejected"):
        with generation.overlap_visual_images(data):
            assert started.wait(3)
            raise ValueError("VFX rejected")
    assert done.is_set()
    assert data == frozen


# Reuse the endpoint/cache harness, not the scheduling implementation.
from tests.test_recipe_singleflight import pipeline_harness  # noqa: E402,F401


def test_combine_overlaps_visual_calls_with_vfx_director(pipeline_harness, offline_backend, monkeypatch):
    from infini_local.pipelines import combine_pipeline as pipeline
    data = _existing_texture_data("entity")
    data.pop("vfxManifest")
    monkeypatch.setattr(generation, "IMAGE_GENERATION_GATE", ImageRequestGate(4))
    backend = generation.generate_sdcpp
    image_started, vfx_finished = threading.Event(), threading.Event()
    def transport(*args, **kwargs):
        image_started.set()
        assert vfx_finished.wait(3)
        return backend(*args, **kwargs)
    def director(candidate, *args):
        assert image_started.wait(3), "image request must start before VFX returns"
        assert not candidate["visual"].get("spritePath")
        candidate["vfxManifest"] = _data([_request()])["vfxManifest"]
        vfx_finished.set()
        return candidate
    monkeypatch.setattr(generation, "generate_sdcpp", transport)
    monkeypatch.setattr(pipeline, "try_llm_plan", lambda *args: copy.deepcopy(data))
    monkeypatch.setattr(pipeline, "attach_vfx_manifest", director)
    monkeypatch.setattr(pipeline, "maybe_generate_visual_assets", generation.maybe_generate_visual_assets)
    out = pipeline.combine(pipeline_harness)
    assert out["visual"]["spriteStatus"] == "generated"
    assert len(offline_backend[0]) == 3
