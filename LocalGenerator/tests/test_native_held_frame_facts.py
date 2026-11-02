"""Shared factual native-canvas context reaches both real request builders.

Provider calls are offline doubles; this proves transport, not image quality.
"""
from copy import deepcopy
from pathlib import Path
import struct

import pytest
from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config
from infini_local.core.images.contracts import native_held_frame_facts, sprite_contract_for
from infini_local.pipelines.visual import request as visual_request
from infini_local.pipelines.images import stage as images
from infini_local.pipelines.images import retry as image_retry
from test_low_level_three_stage_pipeline import wire_transport  # noqa: F401
from test_image_display_budget import _accepted_visual_data, _capture_backend, _framing


def test_bundled_native_frame_matches_real_asset_not_an_inferred_weapon_class():
    root = Path(__file__).resolve().parents[2]
    asset = root / "ModSources/InfiniCrafterLocal/Assets/GeneratedItem.png"
    raw = asset.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    data = _accepted_visual_data()
    facts = native_held_frame_facts(data, 48)
    assert facts["bundledNativeFrameSizePx"] == list(struct.unpack(">II", raw[16:24]))
    assert facts["finalCanvasSizePx"] == [48, 48]
    assert facts["renderSizePx"] == data["visual"]["renderSizePx"]
    contract = sprite_contract_for("item", 48)
    assert facts["framing"] == {k: contract[k] for k in facts["framing"]}
    assert facts["actualNativeOriginPx"] is None
    assert facts["actualNativeRotationRadians"] is None
    assert facts["nativeBodyAutoRotatesPngAxis"] is False
    assert facts["nativeBodyBindsPngGrip"] is False
    data.update(name="an entirely different weapon", category="not_a_router")
    assert native_held_frame_facts(data, 48) == facts


@pytest.mark.parametrize("hidden", [False, True])
def test_projection_preserves_only_actual_accepted_fields_and_is_detached(hidden):
    data = _accepted_visual_data()
    data["runtimeProgram"]["itemUse"].update(useStyle="shoot", hideUseGraphic=hidden, handPose="two_handed", holdoutOffsetX=7, holdoutOffsetY=-3)
    frozen = deepcopy(data)
    facts = native_held_frame_facts(data)
    assert facts["acceptedItemUse"] == {k: data["runtimeProgram"]["itemUse"][k] for k in ("useStyle", "hideUseGraphic", "handPose", "holdoutOffsetX", "holdoutOffsetY")}
    facts["acceptedItemUse"]["holdoutOffsetX"] = 99
    assert data == frozen
    assert native_held_frame_facts({}) == {}
    assert native_held_frame_facts({"runtimeProgram": {"itemUse": {}}})["acceptedItemUse"] == {}


@pytest.mark.parametrize("mode", ["json_object", "json_schema"])
@pytest.mark.parametrize("repair", [False, True])
def test_visual_outgoing_request_contains_shared_facts_without_changing_gameplay(wire_transport, monkeypatch, mode, repair):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    responses, sent = wire_transport
    data = _accepted_visual_data()
    frozen = deepcopy(data)
    responses.append({})
    kwargs = {} if not repair else {
        "repair_errors": [{"path": "$.item.renderSizePx", "message": "invalid"}],
        "previous": data["visualKit"],
        "repair_scope": {"fieldPermissions": {"itemPaths": ["renderSizePx"]}},
    }
    visual_request._request_visual_kit(data, {}, {}, **kwargs)
    packet = request_dossier(sent[-1])
    assert packet["nativeHeldCanvasReadOnly"] == native_held_frame_facts(data)
    assert data == frozen


@pytest.mark.parametrize("compact_retry", [False, True])
def test_actual_image_backend_and_retry_keep_native_frame_facts(monkeypatch, tmp_path, compact_retry):
    monkeypatch.setattr(image_retry, "image_backend_is_zimage", lambda: compact_retry)
    monkeypatch.setenv("INFINI_ZIMAGE_RETRY_PROMPT_LIMIT", "2200")
    data = _accepted_visual_data(long_art=True)
    frozen_runtime = deepcopy(data["runtimeProgram"])
    frozen_kit = deepcopy(data["visualKit"])
    calls = _capture_backend(monkeypatch, tmp_path, retries=True)
    images.maybe_generate_visual_assets(data)
    root_calls = [call for call in calls if "entityId" not in _framing(call["prompt"])]
    assert len(root_calls) == 2
    for call in root_calls:
        facts = _framing(call["prompt"])
        assert facts["nativeHeldCanvas"] == native_held_frame_facts(data, call["canvas"])
        assert facts["forwardAngleDegrees"] == data["visual"]["forwardAngleDegrees"]
    for call in calls:
        if _framing(call["prompt"]).get("entityId") == "nail":
            assert "nativeHeldCanvas" not in _framing(call["prompt"])
    # Image delivery legitimately appends sprite paths/status to entity visuals;
    # all accepted mechanics and the authored kit remain frozen.
    actual_runtime = deepcopy(data["runtimeProgram"])
    for runtime in (actual_runtime, frozen_runtime):
        for entity in runtime["entities"]:
            entity.pop("visual", None)
    assert actual_runtime == frozen_runtime
    assert data["visualKit"] == frozen_kit
