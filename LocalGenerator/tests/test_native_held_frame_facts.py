"""Shared factual native-canvas context reaches both real request builders.

Provider calls are offline doubles; this proves transport, not image quality.
"""
from copy import deepcopy
from pathlib import Path
import struct
import json

import pytest
from prompt_packet_helpers import request_dossier
from infini_local.core import llm_config
from infini_local.core.images.contracts import native_held_frame_facts, sprite_contract_for
from infini_local.pipelines.visual import request as visual_request
from infini_local.pipelines.visual.context import _presentation_packet_context, _runtime_card
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
@pytest.mark.parametrize("repair_path", [None, "renderSizePx", "prompt"])
@pytest.mark.parametrize("placement,offset", [("owner_center", 16), ("cursor", 0)])
def test_visual_outgoing_request_preserves_emission_and_scoped_guidance(
        wire_transport, monkeypatch, mode, repair_path, placement, offset):
    monkeypatch.setattr(llm_config, "LLM_RESPONSE_FORMAT_MODE", mode)
    responses, sent = wire_transport
    data = _accepted_visual_data()
    # Both attached-origin and deliberately detached emission remain explicit
    # accepted inputs to the real request builder, not inferred from the art.
    projectile = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "nail")
    projectile["spawn"].update(placement=placement, offsetPx=offset)
    frozen = deepcopy(data)
    presentation = _presentation_packet_context(data, _runtime_card(data))
    responses.append({})
    kwargs = {} if repair_path is None else {
        "repair_errors": [{"path": "$.item." + repair_path, "message": "invalid"}],
        "previous": data["visualKit"],
        "repair_scope": {"fieldPermissions": {"itemPaths": [repair_path]}},
    }
    visual_request._request_visual_kit(data, {}, {}, **kwargs)
    assert len(sent) == 1
    packet = request_dossier(sent[-1])
    rows = packet["runtimeEntities" if repair_path is None else "runtimeEntitiesReadOnly"]
    assert next(row["spawn"] for row in rows if row["id"] == "nail") == projectile["spawn"]
    assert packet["nativeHeldCanvasReadOnly"] == native_held_frame_facts(data)
    if repair_path is not None:
        assert packet["repairScope"] == kwargs["repair_scope"]
    # Observe actual serialized message delivery, including multiplicity, without
    # pinning particular advice words or replacing the context/request owners.
    delivered = []
    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "sourceCalibration":
                    delivered.append(child)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    for message in sent[-1]["messages"]:
        try:
            collect(json.loads(message["content"]))
        except json.JSONDecodeError:
            pass
    expected = [] if repair_path == "prompt" else [presentation["spritePresentationReadOnly"]["sourceCalibration"]]
    assert delivered == expected
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


@pytest.mark.parametrize("placement,offset,aim,height,expected", [
    ("owner_center", 16, "cursor", 0, {"placement": "owner_center", "offsetPx": 16, "aim": "cursor"}),
    ("cursor", 0, "cursor", 0, {"placement": "cursor", "offsetPx": 0}),
    ("owner_center", 16, "none", 0, {"placement": "owner_center", "offsetPx": 16, "aim": "none"}),
    ("cursor", 0, "facing", 3, {"placement": "cursor", "offsetPx": 0, "overTarget": {"heightTiles": 3}}),
    ("owner_center", 16, None, 0, {"placement": "owner_center", "offsetPx": 16}),
    ("owner_center", None, "cursor", 0, {"placement": "owner_center"}),
    ("above_cursor", 0, "cursor", 0, {"placement": "above_cursor", "offsetPx": 0}),
])
@pytest.mark.parametrize("reverse", [False, True])
def test_image_requests_deliver_only_explicit_use_target_placement(monkeypatch, tmp_path, placement, offset, aim, height, expected, reverse):
    data = _accepted_visual_data()
    runtime = data["runtimeProgram"]
    projectile = next(row for row in runtime["entities"] if row["id"] == "nail")
    projectile["spawn"].update(placement=placement, offsetPx=offset, aim=aim,
                               overTarget={"heightTiles": height, "delayTicks": 17})
    if aim is None:
        projectile["spawn"].pop("aim")
    if offset is None:
        projectile["spawn"].pop("offsetPx")
    # Two explicit uses of the same target must remain two records, not a set.
    bindings = [
        {"id": "first", "input": "primary_use", "usePolicy": {"action": {"kind": "spawn_entity", "targetId": "nail"}}},
        {"id": "second", "input": "alt_use", "usePolicy": {"action": {"kind": "spawn_entity", "targetId": "nail"}}},
    ]
    runtime["bindings"] = list(reversed(bindings)) if reverse else bindings
    if reverse:
        runtime["entities"].reverse()
    frozen = deepcopy(data)
    calls = _capture_backend(monkeypatch, tmp_path)
    images.maybe_generate_visual_assets(data)
    assert len(calls) == 2
    delivered = [_framing(call["prompt"]) for call in calls]
    roots = [row for row in delivered if "entityId" not in row]
    projectiles = [row for row in delivered if row.get("entityId") == "nail"]
    assert len(roots) == len(projectiles) == 1
    assert roots[0]["itemUseSpawnsReadOnly"] == {
        "itemEntityId": runtime["itemEntityId"],
        "bindings": [{"bindingId": binding["id"], "input": binding["input"],
                      "action": binding["usePolicy"]["action"], "targetPlacement": expected}
                     for binding in frozen["runtimeProgram"]["bindings"]],
    }
    assert "spawnReadOnly" not in roots[0]
    assert "spawnReadOnly" not in projectiles[0]
    assert "itemUseSpawnsReadOnly" not in projectiles[0]
    for call in calls:
        owner = frozen["visual"] if "entityId" not in _framing(call["prompt"]) else projectile["visual"]
        assert owner.get("imagePrompt", owner.get("prompt")) in call["prompt"]
        assert frozen["visualKit"]["animationPlan"] not in call["prompt"]
    for snapshot in (data, frozen):
        for row in snapshot["runtimeProgram"]["entities"]:
            row.pop("visual", None)
    assert data["runtimeProgram"] == frozen["runtimeProgram"]
    assert data["visualKit"] == frozen["visualKit"]


@pytest.mark.parametrize("missing", ["item_id", "bindings", "target", "spawn", "action_kind"])
def test_image_context_does_not_invent_missing_root_use_links(missing):
    from infini_local.pipelines.images.prompts import normalize_asset_prompt
    data = _accepted_visual_data()
    runtime = data["runtimeProgram"]
    runtime["bindings"] = [{"id": "use", "input": "primary_use", "usePolicy": {
        "action": {"kind": "spawn_entity", "targetId": "nail"}}}]
    projectile = next(row for row in runtime["entities"] if row["id"] == "nail")
    if missing == "item_id":
        runtime.pop("itemEntityId")
    elif missing == "bindings":
        runtime["bindings"] = []
    elif missing == "target":
        runtime["bindings"][0]["usePolicy"]["action"]["targetId"] = "absent"
    elif missing == "spawn":
        projectile.pop("spawn")
    else:
        runtime["bindings"][0]["usePolicy"]["action"]["kind"] = "none"
    frozen = deepcopy(data)
    root = _framing(normalize_asset_prompt(data, "item", "literal item", 48))
    assert "itemUseSpawnsReadOnly" not in root
    selected = _framing(normalize_asset_prompt(data, "runtime:child_projectile", "literal cloud", 32, entity_id="nail"))
    assert "spawnReadOnly" not in selected
    for role in ("impact", "vfx_strip", "vfx_cutout", "equip_overlay"):
        prompt = normalize_asset_prompt(data, role, "literal special asset", 32, entity_id="nail")
        assert "spawnReadOnly" not in prompt and "itemUseSpawnsReadOnly" not in prompt
    assert data == frozen


@pytest.mark.parametrize("duplicate", ["item", "target"])
def test_ambiguous_entity_ids_do_not_produce_new_spawn_facts(duplicate):
    from infini_local.pipelines.images.prompts import normalize_asset_prompt
    data = _accepted_visual_data()
    runtime = data["runtimeProgram"]
    runtime["bindings"] = [{"id": "use", "input": "primary_use", "usePolicy": {
        "action": {"kind": "spawn_entity", "targetId": "nail"}}}]
    entity_id = runtime["itemEntityId"] if duplicate == "item" else "nail"
    runtime["entities"].append(deepcopy(next(row for row in runtime["entities"] if row["id"] == entity_id)))
    frozen = deepcopy(data)
    root = _framing(normalize_asset_prompt(data, "item", "literal item", 48))
    assert "itemUseSpawnsReadOnly" not in root
    if duplicate == "target":
        selected = _framing(normalize_asset_prompt(data, "runtime:child_projectile", "literal cloud", 32, entity_id="nail"))
        assert "spawnReadOnly" not in selected
    assert data == frozen
