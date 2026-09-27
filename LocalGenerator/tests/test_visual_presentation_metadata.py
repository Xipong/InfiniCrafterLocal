"""Explicit presentation choices survive Visual validation and delivery unchanged."""
import json
from typing import Any
import pytest
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.storage.world_storage import sanitize_recipe_for_delivery


def kit() -> dict[str, Any]:
    item = dict(prompt="object", negativePrompt="", silhouette="object", visualIdentity="object", palette=["red"], preferredCanvasSize=32, inventoryScale=1.0, worldScale=1.0)
    return dict(schema=visual.VISUAL_KIT_SCHEMA, item=item, equipOverlay=dict(prompt="badge", silhouette="badge", visualIdentity="badge", preferredCanvasSize=32), entities=[dict(entityId="opaque_id", assetMode="baked_sprite", visualProjectRef="item", prompt="object", silhouette="object", visualIdentity="object", scale=1.0)], animationPlan="unchanged")


@pytest.mark.parametrize("token", ["white", "gray", "brown", "tan", "red", "orange", "yellow", "gold", "green", "cyan", "blue", "purple", "pink", "black"])
def test_explicit_effect_color_survives_delivery_without_palette_inference(token):
    raw = kit()
    raw["item"]["palette"] = ["copper and verdigris"]
    raw["item"]["effectColor"] = token
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert not errors and accepted is not None
    out = sanitize_recipe_for_delivery(visual._apply_kit({}, accepted))
    assert out["visual"]["effectColor"] == token
    assert out["visual"]["palette"] == ["copper and verdigris"]


@pytest.mark.parametrize("token", [None, "", True, 3, "Gold", " gold", "verdigris", "#ff0000", "dark blue"])
def test_effect_color_rejects_invalid_present_token(token):
    raw = kit()
    raw["item"]["effectColor"] = token
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(e["path"] == "$.item.effectColor" for e in errors)


def test_explicit_grip_and_mount_validate_apply_and_deliver():
    raw = kit()
    raw["item"]["grip"] = {"normalizedX": 0.0, "normalizedY": 1.0}
    raw["equipOverlay"]["accessoryMount"] = "shoulder"
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert not errors
    assert accepted is not None
    data = visual._apply_kit({"runtimeProgram": {"entities": [{"id": "opaque_id"}]}}, accepted)
    delivered = sanitize_recipe_for_delivery(data)
    assert delivered["visual"]["grip"] == raw["item"]["grip"]
    assert delivered["visual"]["accessoryMount"] == "shoulder"
    assert "grip" not in delivered["runtimeProgram"]["entities"][0]["visual"]


@pytest.mark.parametrize("grip", [None, [], {}, {"normalizedX": float("nan"), "normalizedY": 0.5}, {"normalizedX": float("inf"), "normalizedY": 0.5}, {"normalizedX": 0.2}, {"normalizedY": 0.2}, {"normalizedX": True, "normalizedY": 0.5}, {"normalizedX": "0.2", "normalizedY": 0.5}, {"normalizedX": -0.1, "normalizedY": 0.5}, {"normalizedX": 0.5, "normalizedY": 1.1}, {"normalizedX": 0.5, "normalizedY": 0.5, "extra": 0}])
def test_grip_rejects_invalid_present_values(grip):
    raw = kit()
    raw["item"]["grip"] = grip
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(e["path"].startswith("$.item.grip") for e in errors)


@pytest.mark.parametrize("mount", [None, "", "Chest", " chest", "wing", 3, True, {}])
def test_mount_rejects_invalid_present_values(mount):
    raw = kit()
    raw["equipOverlay"]["accessoryMount"] = mount
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(e["path"] == "$.equipOverlay.accessoryMount" for e in errors)


def test_metadata_absent_preserves_old_contract_and_clears_stale_projection():
    raw = kit()
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert not errors and accepted is not None
    data = visual._apply_kit({"visual": {"grip": {"normalizedX": 0, "normalizedY": 0}, "accessoryMount": "chest"}}, accepted)
    assert "grip" not in data["visual"] and "accessoryMount" not in data["visual"]
    assert "effectColor" not in data["visual"]


def test_grip_repair_is_leaf_local_and_does_not_grant_entity_fields():
    raw = kit()
    raw["item"]["grip"] = {"normalizedX": 0.25, "normalizedY": 2}
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert scope["fieldPermissions"]["itemPaths"] == ["grip.normalizedY"]
    assert scope["fieldPermissions"]["entities"] == []
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.75}}, equipOverlayPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="repair Y")
    filtered, audit = visual._filter_visual_repair_patch(raw, patch, scope, ["opaque_id"])
    assert audit["ok"]
    assert filtered["itemPatch"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
    assert audit["ignoredChanges"]


def test_grip_repair_deletes_only_invalid_nested_extra_key():
    raw = kit()
    raw["item"]["grip"] = {"normalizedX": 0.25, "normalizedY": 0.75, "extra": "invalid"}
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.1}}, equipOverlayPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="remove extra")
    merged, audit = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    assert merged["item"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
    assert audit["ok"] and "$.itemPatch.grip.extra" in audit["acceptedPaths"]


@pytest.mark.parametrize("grip", [{"normalizedX": 0.25}, {"normalizedX": 0.25, "normalizedY": None}])
def test_missing_or_invalid_coordinate_repair_preserves_valid_sibling(grip):
    raw = kit()
    raw["item"]["grip"] = grip
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.75}}, equipOverlayPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="repair Y")
    merged = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"])
    assert merged["item"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}


def test_unrelated_repair_cannot_add_optional_metadata():
    raw = kit()
    raw["item"]["inventoryScale"] = 99
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    overlay = dict(raw["equipOverlay"], accessoryMount="chest")
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"inventoryScale": 2, "grip": {"normalizedX": 0.9, "normalizedY": 0.75}}, equipOverlayPatch=overlay, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="repair scale")
    merged, audit = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    assert merged["item"]["inventoryScale"] == 2
    assert "grip" not in merged["item"] and "accessoryMount" not in merged["equipOverlay"]
    assert audit["ignoredChanges"]




@pytest.mark.parametrize("repair_needed", [False, True])
def test_real_director_dispatch_projects_metadata_with_conditional_repair(monkeypatch, repair_needed):
    from infini_local.pipelines import llm_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", "json_schema")
    monkeypatch.setattr(visual, "USE_LLM", True)
    monkeypatch.setattr(visual, "VISUAL_DIRECTOR_LLM", True)
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual, "equipment_overlay_requirement", lambda _: {"required": True, "slot": "accessory"})
    raw = kit()
    raw["item"]["grip"] = {"normalizedX": 0.25, "normalizedY": 2 if repair_needed else 0.75}
    raw["equipOverlay"]["accessoryMount"] = "back"
    responses = [raw]
    if repair_needed:
        responses.append(dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.75}}, equipOverlayPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="repair grip Y only"))
    requests = []
    def reply(request, **_):
        requests.append(request)
        return {"choices": [{"message": {"content": json.dumps(responses.pop(0))}}]}
    monkeypatch.setattr(visual, "llm_chat_json", reply)
    data = {"name": "opaque object", "runtimeProgram": {"entities": [{"id": "opaque_id", "kind": "item_body", "visualRole": "inventory_item"}]}}
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert result["visual"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
    assert result["visual"]["accessoryMount"] == "back"
    assert len(requests) == (2 if repair_needed else 1)
    assert result["debug"]["llmStageAccounting"]["visualRepairCalls"] == int(repair_needed)
    if repair_needed:
        scope = json.loads(requests[1]["messages"][1]["content"])["repairScope"]
        assert scope["fieldPermissions"]["itemPaths"] == ["grip.normalizedY"]
        assert not scope["equipOverlayMutable"]


@pytest.mark.parametrize("mode,debug,omitted", [
    ("json_schema", {}, True), ("json_object", {}, False), ("off", {}, False),
    ("json_schema", {"strictSchemaDowngraded": True}, False),
    ("json_schema", {"responseFormatType": "json_object"}, False),
    ("json_schema", {"responseFormatUsed": False}, False),
])
@pytest.mark.parametrize("repair", [False, True])
def test_actual_provider_transport_optional_nulls(monkeypatch, mode, debug, omitted, repair):
    from infini_local.pipelines import llm_transport
    from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", mode)
    monkeypatch.setattr(visual, "resolve_llm_model", lambda: "test-model")
    monkeypatch.setattr(visual, "equipment_overlay_requirement", lambda _: {"required": True, "slot": "accessory"})
    raw = kit()
    raw["item"]["grip"] = None
    raw["item"]["effectColor"] = None
    raw["equipOverlay"]["accessoryMount"] = None
    if repair:
        raw = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": None, "effectColor": None, "inventoryScale": 2}, equipOverlayPatch=raw["equipOverlay"], entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="repair scale")
    requests = []
    monkeypatch.setattr(visual, "llm_chat_json", lambda request, **_: requests.append(request) or {"choices": [{"message": {"content": json.dumps(raw)}}], "_debug": debug})
    kwargs: dict[str, Any] = dict(repair_errors=[{"path": "$.item.inventoryScale", "message": "invalid"}], previous=kit(), repair_scope={}) if repair else {}
    result = visual._request_visual_kit(build_runtime_fixture("workbench_blade"), {}, {}, {}, {}, **kwargs)
    item_key, overlay_key = ("itemPatch", "equipOverlayPatch") if repair else ("item", "equipOverlay")
    assert isinstance(result, dict)
    assert ("grip" not in result[item_key]) is omitted
    assert ("effectColor" not in result[item_key]) is omitted
    assert ("accessoryMount" not in result[overlay_key]) is omitted
    packet = json.loads(requests[-1]["messages"][1]["content"])
    if mode == "json_schema":
        assert packet["responseSchema"] == requests[-1]["response_format"]["json_schema"]["schema"]
        assert "nullable transport" in requests[-1]["messages"][0]["content"]
    if not repair:
        assert "choose item.grip" in " ".join(packet["rules"])
        assert "accessoryMount" in " ".join(packet["rules"])
        assert "choose item.effectColor" in " ".join(packet["rules"])
