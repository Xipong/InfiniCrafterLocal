"""Durable craft recovery through real stage, image, delivery and cache owners."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from infini_local.core import llm_config
from infini_local.core.runtime_authoring.compiler import compile_runtime_program
from infini_local.core.vfx.contract import VFX_DIRECTOR_SCHEMA
from infini_local.pipelines import combine_pipeline as pipeline
from infini_local.pipelines.author import request as author_request
from infini_local.pipelines.images import manifest as image_manifest
from infini_local.pipelines.images import stage as image_stage
from infini_local.pipelines.vfx import request as vfx_request
from infini_local.pipelines.visual import contract as visual_contract
from infini_local.pipelines.visual import delivery
from infini_local.pipelines.visual import request as visual_request
from infini_local.pipelines.visual import stage as visual_stage
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.services.combine_endpoint import handle_combine_request
from infini_local.services.sdcpp_service import ImageRequestGate
from infini_local.storage import world_recipe_runtime, world_storage
from infini_local.storage.generation_checkpoint import GenerationCheckpoint
from tests.vfx_image_fixtures import offline_backend  # noqa: F401


_CALL_KEYS = (
    "gameplayAuthorCalls", "gameplayRepairCalls", "visualDirectorCalls",
    "visualRepairCalls", "vfxDirectorCalls", "vfxRepairCalls",
)
_DIRECTOR_KEYS = {
    "planner": "gameplayAuthorCalls", "visual_director": "visualDirectorCalls",
    "vfx_director": "vfxDirectorCalls",
}


def _visual_kit(authored):
    runtime = compile_runtime_program(authored)["runtimeProgram"]
    return {
        "schema": visual_contract.VISUAL_KIT_SCHEMA,
        "item": {
            "prompt": "one literal wooden blade with a steel edge",
            "negativePrompt": "text, watermark", "silhouette": "one joined object",
            "visualIdentity": "wooden blade", "palette": ["brown", "steel"],
            "preferredCanvasSize": 32, "renderSizePx": 40,
            "forwardAngleDegrees": 45, "inventoryScale": 1.0, "worldScale": 1.0,
        },
        "entities": [{
            "entityId": row["id"],
            "assetMode": "baked_sprite" if row["id"] == runtime["itemEntityId"] else "reuse_item_icon",
            "visualProjectRef": "item", "scale": 1.0,
        } for row in runtime["entities"]],
        "animationPlan": "Follow the accepted runtime movement.",
    }


class _Craft:
    def __init__(self, root, backend):
        self.root = root
        self.request = {
            "worldId": "resume-world", "worldName": "Resume world",
            "itemA": {"id": 36, "name": "Work Bench", "fullName": "Terraria/WorkBench"},
            "itemB": {"id": 3507, "name": "Copper Shortsword", "fullName": "Terraria/CopperShortsword"},
        }
        self.authored = build_runtime_fixture("workbench_blade")
        self.text_calls = []
        self.image_calls = []
        self.model = "original-model"
        self.fail = ""
        self.backend = backend

    def text(self, request, **_kwargs):
        stage = request["_infini_stage"]
        self.text_calls.append(stage)
        if self.fail == stage:
            self.fail = ""
            raise OSError("offline provider interrupted " + stage)
        if stage == "planner":
            result = copy.deepcopy(self.authored)
            result["name"] = "Wooden Blade " + str(self.text_calls.count("planner"))
        elif stage == "visual_director":
            result = _visual_kit(self.authored)
        elif stage == "vfx_director":
            result = {"schema": VFX_DIRECTOR_SCHEMA, "slots": []}
        else:
            pytest.fail("unexpected repair or other text call: " + stage)
        return {"choices": [{"message": {"content": json.dumps(result)}}]}

    def image(self, prompt, negative, asset_id, canvas, **kwargs):
        self.image_calls.append(asset_id)
        if self.fail == "image":
            self.fail = ""
            raise OSError("offline image provider interrupted")
        return self.backend(prompt, negative, asset_id, canvas, **kwargs)

    def drafts(self):
        return list((self.root / "world-recipes").glob("world_*/drafts/*.json"))

    def cache_only(self):
        responses = []
        handle_combine_request(
            {**self.request, "cacheOnly": True}, app_version="resume-test",
            combine_cache_lookup=pipeline.combine_cache_lookup,
            sanitize_recipe_for_delivery=world_storage.sanitize_recipe_for_delivery,
            combine=lambda _: pytest.fail("an unfinished draft must never be delivered as a cache hit"),
            trace_event=lambda *_: None,
            json=lambda data: responses.append((200, data)),
            json_status=lambda code, data: responses.append((code, data)),
        )
        assert len(responses) == 1
        return responses[0]


@pytest.fixture
def craft(tmp_path, monkeypatch, offline_backend):
    root = tmp_path / "world-recipes"
    for module in (world_recipe_runtime, image_stage, image_manifest, delivery):
        monkeypatch.setattr(module, "WORLD_RECIPES_DIR", root)
    candidate = _Craft(tmp_path, image_stage.generate_sdcpp)
    monkeypatch.setattr(image_stage, "generate_sdcpp", candidate.image)
    for module in (pipeline, author_request, visual_stage, vfx_request):
        monkeypatch.setattr(module, "USE_LLM", True)
    monkeypatch.setattr(visual_stage, "VISUAL_DIRECTOR_LLM", True)
    for module in (author_request, visual_request, vfx_request):
        monkeypatch.setattr(module, "resolve_llm_model", lambda: candidate.model)
        monkeypatch.setattr(module, "llm_chat_json", candidate.text)
    return candidate


def _debug(data, key):
    value = data["debug"][key]
    return json.loads(value) if isinstance(value, str) else value


def _mechanics(data):
    runtime = copy.deepcopy(data["runtimeProgram"])
    for entity in runtime["entities"]:
        entity.pop("visual", None)
    return runtime


def _assert_accounting(data, new_calls):
    expected = {key: int(key in _DIRECTOR_KEYS.values()) for key in _CALL_KEYS}
    assert data["llmStageAccounting"] == expected
    resume = _debug(data, "generationResume")
    assert resume["currentAttemptCalls"] == {
        key: sum(_DIRECTOR_KEYS.get(stage) == key for stage in new_calls) for key in _CALL_KEYS
    }
    assert resume["available"] is False


@pytest.mark.parametrize("failure,stage,new_calls", [
    ("visual_director", "gameplay", ["visual_director", "vfx_director"]),
    ("vfx_director", "visual", ["vfx_director"]),
    ("image", "vfx", []),
])
def test_retry_continues_persisted_accepted_stages_without_reauthoring(craft, failure, stage, new_calls):
    craft.fail = failure
    with pytest.raises((OSError, delivery.VisualDeliveryBlocked)) as failed:
        pipeline.combine(craft.request)
    draft_path, = craft.drafts()
    record = json.loads(draft_path.read_text(encoding="utf-8"))
    assert record["stage"] == stage
    assert failed.value._infini_failure_snapshot["generationResume"] == {"available": True, "stage": stage}
    accepted = record["data"]
    assert accepted["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] == 1
    assert craft.cache_only()[0] == 404
    text_before = len(craft.text_calls)
    # A new combine call constructs a fresh disk-backed checkpoint. Changing the
    # provider for unfinished stages must not throw away the accepted design.
    craft.model = "backup-model"
    result = pipeline.combine(copy.deepcopy(craft.request))
    assert craft.text_calls[text_before:] == new_calls
    assert result["id"] == accepted["id"]
    assert _mechanics(result) == _mechanics(accepted)
    assert pipeline._cached_payload_report(result)["ok"]
    assert _debug(result, "generationResume")["resumedFrom"] == stage
    _assert_accounting(result, new_calls)
    assert not craft.drafts()
    before = (list(craft.text_calls), list(craft.image_calls))
    code, cached = craft.cache_only()
    assert code == 200 and cached["id"] == result["id"]
    assert pipeline.combine(craft.request)["id"] == result["id"]
    assert (craft.text_calls, craft.image_calls) == before


@pytest.mark.parametrize("changed", ["parent_facts", "tooltip", "frame_size", "world", "contracts", "language", "prompt_style"])
def test_draft_requires_exact_source_world_and_contracts(craft, monkeypatch, changed):
    craft.request["itemA"]["spriteReferenceRaw"] = {
        "source": "TextureAssets.Item", "textureWidthPx": 64, "textureHeightPx": 64,
        "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 0, "widthPx": 32, "heightPx": 32},
    }
    craft.fail = "visual_director"
    with pytest.raises(OSError):
        pipeline.combine(craft.request)
    before = len(craft.text_calls)
    old_id = json.loads(craft.drafts()[0].read_text(encoding="utf-8"))["data"]["id"]
    if changed == "parent_facts":
        # Same item identity and recipe key, but new source mechanics.
        key, _ = pipeline.combine_cache_lookup(craft.request)
        craft.request["itemA"]["damage"] = 99
        assert pipeline.combine_cache_lookup(craft.request)[0] == key
    elif changed == "tooltip":
        craft.request["itemA"]["tooltipLines"] = ["This source now grants a different effect."]
    elif changed == "frame_size":
        craft.request["itemA"]["spriteReferenceRaw"]["currentFrame"]["widthPx"] = 16
    elif changed == "world":
        craft.request["worldId"] = "other-world"
    elif changed == "language":
        monkeypatch.setattr(llm_config, "LANGUAGE", "en" if llm_config.LANGUAGE != "en" else "ru")
    elif changed == "prompt_style":
        monkeypatch.setattr(llm_config, "PROMPT_STYLE", "Terraria Like" if llm_config.PROMPT_STYLE == "Default" else "Default")
    else:
        contracts = pipeline.contract_versions_payload()
        monkeypatch.setattr(pipeline, "contract_versions_payload", lambda: {**contracts, "appVersion": "future-test"})
    result = pipeline.combine(craft.request)
    assert craft.text_calls[before:] == ["planner", "visual_director", "vfx_director"]
    assert result["id"] != old_id
    assert pipeline._cached_payload_report(result)["ok"]


def test_native_animation_time_does_not_discard_accepted_craft(craft):
    craft.request["itemA"]["spriteReferenceRaw"] = {
        "source": "TextureAssets.Item", "textureWidthPx": 64, "textureHeightPx": 64,
        "currentFrame": {"source": "draw_animation", "xPx": 0, "yPx": 0, "widthPx": 32, "heightPx": 32},
    }
    craft.fail = "visual_director"
    with pytest.raises(OSError):
        pipeline.combine(craft.request)
    before = len(craft.text_calls)
    old = json.loads(craft.drafts()[0].read_text(encoding="utf-8"))["data"]
    craft.request["itemA"]["spriteReferenceRaw"]["currentFrame"]["yPx"] = 32
    result = pipeline.combine(craft.request)
    assert craft.text_calls[before:] == ["visual_director", "vfx_director"]
    assert result["id"] == old["id"]
    assert _mechanics(result) == _mechanics(old)


@pytest.mark.parametrize("asset_change", ["none", "missing", "corrupt"])
def test_commit_retry_keeps_directors_and_revalidates_saved_pngs(craft, monkeypatch, asset_change):
    real_write = world_storage.atomic_write_json
    attempted = []

    def fail_recipe_commit(path, payload):
        if path.parent.name == "recipes":
            attempted.append(copy.deepcopy(payload))
            raise OSError("offline recipe commit failure")
        real_write(path, payload)

    with monkeypatch.context() as patch:
        patch.setattr(world_storage, "atomic_write_json", fail_recipe_commit)
        with pytest.raises(OSError, match="offline recipe commit failure") as failed:
            pipeline.combine(craft.request)
    draft_path, = craft.drafts()
    record = json.loads(draft_path.read_text(encoding="utf-8"))
    assert record["stage"] == "vfx"
    assert failed.value._infini_failure_snapshot["generationResume"] == {"available": True, "stage": "vfx"}
    old, = attempted
    sprite = Path(old["visual"]["spritePath"])
    saved_pixels = sprite.read_bytes()
    assert craft.cache_only()[0] == 404
    if asset_change == "missing":
        sprite.unlink()
    elif asset_change == "corrupt":
        sprite.write_bytes(b"not a complete PNG")
    text_before, images_before = len(craft.text_calls), len(craft.image_calls)
    result = pipeline.combine(craft.request)
    assert craft.text_calls[text_before:] == []
    assert len(craft.image_calls) - images_before == int(asset_change != "none")
    assert result["id"] == old["id"]
    assert _mechanics(result) == _mechanics(old)
    assert Path(result["visual"]["spritePath"]).read_bytes() == saved_pixels
    _assert_accounting(result, [])
    assert pipeline._cached_payload_report(result)["ok"]
    assert not craft.drafts()


def test_unreadable_checkpoint_does_not_start_another_paid_author(craft, monkeypatch):
    craft.fail = "visual_director"
    with pytest.raises(OSError):
        pipeline.combine(craft.request)
    path, = craft.drafts()
    original = path.read_bytes()
    before = list(craft.text_calls)
    real_open = Path.open

    def refuse_checkpoint(self, *args, **kwargs):
        if self == path:
            raise PermissionError("offline draft cannot be read")
        return real_open(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", refuse_checkpoint)
        with pytest.raises(PermissionError, match="offline draft cannot be read"):
            pipeline.combine(craft.request)
    assert craft.text_calls == before
    assert path.read_bytes() == original
    result = pipeline.combine(craft.request)
    assert craft.text_calls[len(before):] == ["visual_director", "vfx_director"]
    assert pipeline._cached_payload_report(result)["ok"]


def test_images_finished_during_vfx_failure_survive_the_failed_attempt(craft, monkeypatch):
    monkeypatch.setattr(image_stage, "IMAGE_GENERATION_GATE", ImageRequestGate(2))
    image_returned = threading.Event()
    backend = image_stage.generate_sdcpp

    def image(*args, **kwargs):
        result = backend(*args, **kwargs)
        image_returned.set()
        return result

    def text(request, **kwargs):
        if request["_infini_stage"] == "vfx_director":
            assert image_returned.wait(5), "the independent image did not overlap VFX"
        return craft.text(request, **kwargs)

    monkeypatch.setattr(image_stage, "generate_sdcpp", image)
    monkeypatch.setattr(vfx_request, "llm_chat_json", text)
    craft.fail = "vfx_director"
    with pytest.raises(OSError, match="offline provider interrupted vfx_director"):
        pipeline.combine(craft.request)
    draft_path, = craft.drafts()
    record = json.loads(draft_path.read_text(encoding="utf-8"))
    assert record["stage"] == "visual"
    assert len(record["images"]) == 1, "joining the failed VFX attempt must retain its accepted image"
    text_before, images_before = len(craft.text_calls), len(craft.image_calls)
    result = pipeline.combine(craft.request)
    assert craft.text_calls[text_before:] == ["vfx_director"]
    assert len(craft.image_calls) == images_before == 1
    assert _debug(result, "itemSpriteCheckpointReuse")["newProviderCalls"] == 0
    _assert_accounting(result, ["vfx_director"])
    assert pipeline._cached_payload_report(result)["ok"]


@pytest.mark.parametrize("invalid", ["runtime", "visual", "vfx", "accounting", "accounting_string", "future_repair"])
def test_checksum_valid_draft_still_requires_canonical_stage_admission(craft, invalid):
    craft.fail = "visual_director" if invalid == "future_repair" else "image"
    with pytest.raises((OSError, delivery.VisualDeliveryBlocked)):
        pipeline.combine(craft.request)
    path, = craft.drafts()
    record = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = GenerationCheckpoint(path.parent.parent, path.stem, record["identity"])
    broken = checkpoint.data
    if invalid == "runtime":
        broken["runtimeProgram"]["entities"][0]["kind"] = "unknown_runtime_kind"
    elif invalid == "visual":
        broken["visualKit"]["entities"][0]["entityId"] = "missing_runtime_entity"
    elif invalid == "vfx":
        broken["vfxManifest"]["schema"] = "unknown_vfx_schema"
    elif invalid == "accounting_string":
        broken["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] = "bad"
    elif invalid == "future_repair":
        broken["debug"]["llmStageAccounting"]["visualRepairCalls"] = 1
    else:
        broken["debug"]["llmStageAccounting"]["gameplayAuthorCalls"] = 2
    # This is an atomically written, integrity-valid record. Semantic acceptance
    # must still use the current owners rather than trusting the file checksum.
    checkpoint.save_stage(record["stage"], broken)
    before = len(craft.text_calls)
    result = pipeline.combine(craft.request)
    assert craft.text_calls[before:] == ["planner", "visual_director", "vfx_director"]
    assert result["id"] != record["data"]["id"]
    assert pipeline._cached_payload_report(result)["ok"]


def test_checkpoint_writes_merge_concurrent_images_and_preserve_last_committed_progress(tmp_path, monkeypatch):
    identity = {"worldId": "one-world", "sourceFingerprint": "exact-parents"}
    checkpoint = GenerationCheckpoint(tmp_path, "one-recipe", identity)
    accepted = {"id": "authored-result", "runtimeProgram": {"values": [1, 2, 3]}}
    checkpoint.save_stage("gameplay", accepted)
    accepted["runtimeProgram"]["values"].append(4)
    barrier = threading.Barrier(3)

    def image_receipt(key):
        barrier.wait(5)
        checkpoint.image_put(key, {"sha256": key, "result": {"path": key + ".png"}})

    def visual_receipt():
        barrier.wait(5)
        checkpoint.save_stage("visual", {"id": "authored-result", "visualKit": {"accepted": True}})

    with ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(image_receipt, key) for key in ("first", "second")]
        futures.append(pool.submit(visual_receipt))
        for future in futures:
            future.result(5)
    loaded = GenerationCheckpoint(tmp_path, "one-recipe", identity)
    assert loaded.stage == "visual"
    assert [loaded.image_get(key)["sha256"] for key in ("first", "second")] == ["first", "second"]
    detached = loaded.data
    detached["visualKit"]["accepted"] = False
    assert loaded.data["visualKit"]["accepted"] is True
    raw = loaded.path.read_bytes()

    def reject_write(*_args, **_kwargs):
        raise OSError("offline checkpoint write failed")

    with monkeypatch.context() as patch:
        patch.setattr(world_storage, "atomic_write_json", reject_write)
        with pytest.raises(OSError, match="offline checkpoint write failed"):
            loaded.save_stage("vfx", {"id": "never-committed"})
    assert loaded.stage == "visual" and loaded.data["id"] == "authored-result"
    assert loaded.path.read_bytes() == raw
    assert GenerationCheckpoint(tmp_path, "one-recipe", identity).data == loaded.data
    loaded.clear()
    assert not loaded.path.exists()
