"""Interrupted crafts retain accepted design; retries cross the real admission gates."""
from __future__ import annotations

from collections import Counter
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from infini_local.core.errors import PlannerUnavailable
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.pipelines import combine_pipeline as pipeline
from infini_local.pipelines.images import stage as images
from infini_local.pipelines.transport import profiles
from infini_local.pipelines.visual import stage as visual
from infini_local.pipelines.visual.delivery import VisualDeliveryBlocked
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage import craft_progress, world_recipe_runtime, world_storage
from tests.test_low_level_three_stage_pipeline import _vfx_output, _visual_kit, wire_transport  # noqa: F401
from tests.vfx_image_fixtures import offline_backend  # noqa: F401


def _outputs(name=None):
    authored = build_runtime_fixture("workbench_blade")
    if name is not None:
        authored["name"] = name
    compiled = compile_runtime_program(authored)
    kit = _visual_kit(compiled)
    return authored, kit, _vfx_output(visual._apply_kit(compiled, kit))


def _mechanics(data):
    runtime = copy.deepcopy(data["runtimeProgram"])
    for entity in runtime["entities"]:
        entity.pop("visual", None)
    return runtime


@pytest.fixture
def craft(wire_transport, offline_backend, monkeypatch, tmp_path):
    return _craft_environment(wire_transport, offline_backend, monkeypatch, tmp_path)


def _craft_environment(wire_transport, offline_backend, monkeypatch, tmp_path):
    responses, requests = wire_transport
    world_root = tmp_path / "world-recipes"
    monkeypatch.setattr(world_recipe_runtime, "WORLD_RECIPES_DIR", world_root)
    monkeypatch.setattr(pipeline, "USE_LLM", True)
    monkeypatch.setattr(profiles, "configured_llm_pool", lambda: [
        {"profile_id": f"llm_{index}", "label": f"llm_{index}", "provider": "local",
         "model": "test-model", "base_url": "http://127.0.0.1:1"}
        for index in (1, 2, 3)
    ])
    return SimpleNamespace(
        payload={"worldId": "resume-world", "worldName": "Resume test",
                 "itemA": {"id": 9, "name": "Wood", "internalName": "Wood", "tooltip": "Original facts"},
                 "itemB": {"id": 3, "name": "Stone Block", "internalName": "StoneBlock"}},
        responses=responses, requests=requests, image_calls=offline_backend[0],
        backend=images.generate_sdcpp, world_root=world_root,
    )


def _progress_path(payload):
    world = world_recipe_runtime.normalize_world_id_from_payload(payload)
    key, _ = pipeline.combine_cache_lookup(payload)
    return craft_progress.progress_path(pipeline.world_recipe_dir(world), key)


def _fail_image(*args, **kwargs):
    raise RuntimeError("offline image service unavailable")


@pytest.mark.parametrize("failed_stage,saved_stage,swap_parents", [
    ("visual_director", "author", False),
    ("vfx_director", "visual", False),
    ("images", "vfx", False),
    ("vfx_director", "visual", True),
])
def test_retry_retains_accepted_design_and_commits_only_complete_item(craft, monkeypatch, failed_stage, saved_stage, swap_parents):
    authored, kit, vfx = _outputs()
    first = {"visual_director": [authored, RuntimeError("offline Visual failure")],
             "vfx_director": [authored, kit, RuntimeError("offline VFX failure")],
             "images": [authored, kit, vfx]}[failed_stage]
    craft.responses.extend(first)
    if failed_stage == "images":
        monkeypatch.setattr(images, "generate_sdcpp", _fail_image)
    with pytest.raises(RuntimeError):
        pipeline.combine(copy.deepcopy(craft.payload))

    path = _progress_path(craft.payload)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["stage"] == saved_stage
    accepted = saved["data"]
    assert pipeline.combine_cache_lookup(craft.payload)[1] is None, "an unfinished design is never a delivered recipe"
    accounting = accepted["debug"]["llmStageAccounting"]
    assert accounting["gameplayAuthorCalls"] == 1
    assert accounting["visualDirectorCalls"] == int(saved_stage in {"visual", "vfx"})
    assert accounting["vfxDirectorCalls"] == int(saved_stage == "vfx")

    # Reconstruct storage state from bytes, without a surviving progress object.
    importlib.reload(craft_progress)
    remaining = {"visual_director": [kit, vfx], "vfx_director": [vfx], "images": []}[failed_stage]
    craft.responses.extend(remaining)
    monkeypatch.setattr(images, "generate_sdcpp", craft.backend)
    if swap_parents:
        craft.payload["itemA"], craft.payload["itemB"] = craft.payload["itemB"], craft.payload["itemA"]
    result = pipeline.combine(copy.deepcopy(craft.payload))
    stages = Counter(request["_infini_stage"] for request in craft.requests)
    assert stages == Counter({"planner": 1,
                             "visual_director": 1 + int(failed_stage == "visual_director"),
                             "vfx_director": 1 + int(failed_stage == "vfx_director")})
    assert result["id"] == accepted["id"]
    assert result["name"] == accepted["name"]
    assert _mechanics(result) == _mechanics(accepted)
    if saved_stage in {"visual", "vfx"}:
        expected_prompt = images.normalize_asset_prompt(
            accepted, "item", accepted["visual"]["imagePrompt"], accepted["visual"]["preferredCanvasSize"])
        assert result["visual"]["imagePrompt"] == expected_prompt
        for field in ("negativePrompt", "palette", "preferredCanvasSize"):
            assert result["visual"][field] == accepted["visual"][field]
    if saved_stage == "vfx":
        assert result["vfxManifest"] == accepted["vfxManifest"]
    assert result["llmStageAccounting"] == {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0,
        "visualDirectorCalls": 1, "visualRepairCalls": 0,
        "vfxDirectorCalls": 1, "vfxRepairCalls": 0,
    }
    assert not path.exists()
    assert not craft.responses
    requests_before, images_before = len(craft.requests), len(craft.image_calls)
    cached = pipeline.combine(copy.deepcopy(craft.payload))
    assert (cached["id"], cached["runtimeProgram"], cached["vfxManifest"]) == (
        result["id"], result["runtimeProgram"], result["vfxManifest"])
    assert (cached["parentA"], cached["parentB"]) == (accepted["parentA"], accepted["parentB"])
    assert (len(craft.requests), len(craft.image_calls)) == (requests_before, images_before)


@pytest.mark.parametrize("difference", ["parent_facts", "world", "lane", "contracts"])
def test_checkpoint_identity_never_reuses_another_craft(craft, monkeypatch, difference):
    if difference == "lane":
        craft.payload.update(multiDevCraft=True, llmProfileId="llm_1")
    craft.responses.extend(_outputs())
    monkeypatch.setattr(images, "generate_sdcpp", _fail_image)
    with pytest.raises(VisualDeliveryBlocked):
        pipeline.combine(copy.deepcopy(craft.payload))
    previous_path = _progress_path(craft.payload)
    assert previous_path.is_file()
    changed = copy.deepcopy(craft.payload)
    if difference == "parent_facts":
        changed["itemA"]["tooltip"] = "Changed full native parent facts"
        assert _progress_path(changed) == previous_path, "same recipe identity must still check literal parent facts"
    elif difference == "world":
        changed["worldId"] = "other-world"
    elif difference == "lane":
        changed["llmProfileId"] = "llm_2"
    else:
        contracts = pipeline._progress_contracts()
        monkeypatch.setattr(pipeline, "_progress_contracts", lambda: {**contracts, "revision": "next-contract"})
    craft.responses.extend(_outputs("Independent fresh discovery"))
    monkeypatch.setattr(images, "generate_sdcpp", craft.backend)
    result = pipeline.combine(changed)
    assert result["name"] == "Independent fresh discovery"
    assert result["recipeMeta"]["worldId"] == changed["worldId"]
    assert Counter(request["_infini_stage"] for request in craft.requests) == Counter({
        "planner": 2, "visual_director": 2, "vfx_director": 2,
    })
    assert not _progress_path(changed).exists()
    assert not craft.responses


@pytest.mark.parametrize("corruption", ["json", "runtime_wire"])
def test_corrupt_checkpoint_is_neither_delivered_nor_silently_reauthored(craft, monkeypatch, corruption):
    craft.responses.extend(_outputs())
    monkeypatch.setattr(images, "generate_sdcpp", _fail_image)
    with pytest.raises(VisualDeliveryBlocked):
        pipeline.combine(copy.deepcopy(craft.payload))
    path = _progress_path(craft.payload)
    if corruption == "json":
        path.write_text('{"stage": "vfx",', encoding="utf-8")
    else:
        damaged = json.loads(path.read_text(encoding="utf-8"))
        damaged["data"]["runtimeProgram"] = None
        world_storage.atomic_write_json(path, damaged)
    requests_before = len(craft.requests)
    monkeypatch.setattr(images, "generate_sdcpp", craft.backend)
    with pytest.raises(PlannerUnavailable):
        pipeline.combine(copy.deepcopy(craft.payload))
    assert len(craft.requests) == requests_before, "corruption cannot spend another generation or silently replace the design"
    assert path.is_file(), "retain failed progress for an explicit reset or diagnosis"
    assert pipeline.combine_cache_lookup(craft.payload)[1] is None


def test_progress_write_failure_stops_before_next_paid_stage_and_preserves_old_snapshot(craft, monkeypatch):
    authored, kit, vfx = _outputs()
    craft.responses.extend([authored, RuntimeError("offline Visual failure")])
    with pytest.raises(RuntimeError):
        pipeline.combine(copy.deepcopy(craft.payload))
    path = _progress_path(craft.payload)
    before = path.read_bytes()
    replace = os.replace

    def unwritable(source, destination):
        if Path(destination) == path:
            raise OSError("offline disk full")
        return replace(source, destination)

    craft.responses.append(kit)
    monkeypatch.setattr(os, "replace", unwritable)
    with pytest.raises(OSError, match="offline disk full"):
        pipeline.combine(copy.deepcopy(craft.payload))
    assert path.read_bytes() == before
    assert Counter(request["_infini_stage"] for request in craft.requests) == Counter({"planner": 1, "visual_director": 2})
    assert not craft.image_calls
    assert not craft.responses

    monkeypatch.setattr(os, "replace", replace)
    craft.responses.extend([kit, vfx])
    result = pipeline.combine(copy.deepcopy(craft.payload))
    assert result["id"] == json.loads(before)["data"]["id"]
    assert Counter(request["_infini_stage"] for request in craft.requests) == Counter({
        "planner": 1, "visual_director": 3, "vfx_director": 1,
    })
    assert not path.exists()


def _run_resume_process(directory, phase):
    """Two independent interpreters share only accepted JSON and PNG files."""
    directory.mkdir(parents=True, exist_ok=True)
    with pytest.MonkeyPatch.context() as patch:
        transport = wire_transport.__wrapped__(patch)
        backend = offline_backend.__wrapped__(patch, directory)
        run = _craft_environment(transport, backend, patch, directory)
        if phase == "fail":
            run.responses.extend(_outputs())
            patch.setattr(images, "generate_sdcpp", _fail_image)
            with pytest.raises(VisualDeliveryBlocked):
                pipeline.combine(run.payload)
            path = _progress_path(run.payload)
            saved = json.loads(path.read_text(encoding="utf-8"))
            result = {"id": saved["data"]["id"], "pending": str(path)}
        else:
            result = pipeline.combine(run.payload)
            result = {"id": result["id"], "accounting": result["llmStageAccounting"]}
        result["requests"] = [request["_infini_stage"] for request in run.requests]
        print(json.dumps(result))


def test_new_process_resumes_paid_design_without_any_llm_call(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = (
        "import sys; from pathlib import Path; "
        "sys.path[:0] = [str(Path.cwd() / 'LocalGenerator'), str(Path.cwd() / 'LocalGenerator/tests')]; "
        "from tests.test_generation_resume import _run_resume_process; "
        "_run_resume_process(Path(sys.argv[1]), sys.argv[2])"
    )
    results = []
    for phase in ("fail", "resume"):
        process = subprocess.run([sys.executable, "-c", script, str(tmp_path), phase],
                                 cwd=root, text=True, capture_output=True, timeout=60)
        assert process.returncode == 0, process.stdout + process.stderr
        results.append(json.loads(process.stdout.strip().splitlines()[-1]))
    first, resumed = results
    assert first["requests"] == ["planner", "visual_director", "vfx_director"]
    assert resumed["requests"] == []
    assert resumed["id"] == first["id"]
    assert resumed["accounting"] == {
        "gameplayAuthorCalls": 1, "gameplayRepairCalls": 0,
        "visualDirectorCalls": 1, "visualRepairCalls": 0,
        "vfxDirectorCalls": 1, "vfxRepairCalls": 0,
    }
    assert not Path(first["pending"]).exists()
