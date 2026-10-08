"""Presentation admission, frozen metadata and runtime/asset/VFX closure."""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any
import pytest
from PIL import Image
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines import visual_soul as VISUAL
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from infini_local.core.runtime_authoring import compile_runtime_program, runtime_event_inventory, runtime_visual_roles, validate_runtime_wire
from infini_local.core.vfx_manifest import attach_hybrid_vfx_manifest, validate_vfx_director_output, vfx_director_surface
from infini_local.pipelines.image_backend_pipeline import comfyui_mapping
from infini_local.pipelines.visual_asset_plan import apply_visual_asset_runtime_gates, build_visual_asset_plan
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_witnesses import build_capability_witness
from csharp_partial_reader import read_text_with_partial_bundles
from test_low_level_three_stage_pipeline import _visual_kit, _accepted_visual_data, _vfx_output, wire_transport


def kit() -> dict[str, Any]:
    """Small opaque-ID fixture also consumed by the exact Repair-location contracts."""
    item = dict(prompt="object", negativePrompt="", silhouette="object", visualIdentity="object", palette=["red"], preferredCanvasSize=32, renderSizePx=40, forwardAngleDegrees=45, inventoryScale=1.0, worldScale=1.0)
    return dict(schema=visual.VISUAL_KIT_SCHEMA, item=item, equipOverlay=dict(prompt="badge", silhouette="badge", visualIdentity="badge", preferredCanvasSize=32), entities=[dict(entityId="opaque_id", assetMode="baked_sprite", visualProjectRef="item", prompt="object", silhouette="object", visualIdentity="object", scale=1.0)], animationPlan="unchanged")


METADATA_INVALID = [
    *(pytest.param("item", "effectColor", value, id=f"color-{name}") for name, value in [
        ("null", None), ("empty", ""), ("bool", True), ("integer", 3), ("case", "Gold"), ("space", " gold"),
        ("undeclared", "verdigris"), ("hex", "#ff0000"), ("prose", "dark blue")]),
    *(pytest.param("equipOverlay", "accessoryMount", value, id=f"mount-{name}") for name, value in [
        ("null", None), ("empty", ""), ("case", "Chest"), ("space", " chest"), ("undeclared", "wing"),
        ("integer", 3), ("bool", True), ("object", {})]),
    *(pytest.param("item", "grip", value, id=f"grip-{name}") for name, value in [
        ("null", None), ("array", []), ("empty", {}), ("nan", {"normalizedX": float("nan"), "normalizedY": 0.5}),
        ("infinity", {"normalizedX": float("inf"), "normalizedY": 0.5}), ("missing-y", {"normalizedX": 0.2}),
        ("missing-x", {"normalizedY": 0.2}), ("bool", {"normalizedX": True, "normalizedY": 0.5}),
        ("string", {"normalizedX": "0.2", "normalizedY": 0.5}), ("negative-x", {"normalizedX": -0.1, "normalizedY": 0.5}),
        ("excess-y", {"normalizedX": 0.5, "normalizedY": 1.1}), ("extra-key", {"normalizedX": 0.5, "normalizedY": 0.5, "extra": 0})]),
]


@pytest.mark.parametrize("container,field,value", METADATA_INVALID)
def test_present_metadata_rejects_invalid_types_and_tokens(container, field, value):
    raw = kit()
    raw[container][field] = value
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None
    path = f"$.{container}.{field}"
    assert any(e["path"].startswith(path) if field == "grip" else e["path"] == path for e in errors)


@pytest.mark.parametrize("container,field,value", [
    *(pytest.param("item", "effectColor", value, id=f"color-{value}") for value in visual._visual_item_schema()["properties"]["effectColor"]["enum"]),
    *(pytest.param("equipOverlay", "accessoryMount", value, id=f"mount-{value}") for value in visual._visual_equip_overlay_schema()["properties"]["accessoryMount"]["enum"]),
    pytest.param("item", "grip", {"normalizedX": 0.0, "normalizedY": 1.0}, id="grip-inclusive-boundaries"),
])
def test_authored_metadata_survives_delivery_without_inference(container, field, value):
    raw = kit()
    raw["item"]["palette"] = ["copper and verdigris"]
    raw[container][field] = value
    if field == "grip":
        raw["equipOverlay"]["accessoryMount"] = "shoulder"
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is not None and not errors
    delivered = sanitize_recipe_for_delivery(visual._apply_kit({"runtimeProgram": {"entities": [{"id": "opaque_id"}]}}, accepted))
    assert delivered["visual"][field] == value
    if field == "grip":
        assert delivered["visual"]["accessoryMount"] == "shoulder"
    assert delivered["visual"]["palette"] == ["copper and verdigris"]
    assert "grip" not in delivered["runtimeProgram"]["entities"][0]["visual"]


@pytest.mark.parametrize("scenario,grip,paths", [
    pytest.param("repair-y", {"normalizedX": 0.25, "normalizedY": 2}, ["grip.normalizedY"], id="invalid-y-frozen-x"),
    pytest.param("repair-y", {"normalizedX": 0.25}, ["grip.normalizedY"], id="missing-y-frozen-x"),
    pytest.param("repair-y", {"normalizedX": 0.25, "normalizedY": None}, ["grip.normalizedY"], id="null-y-frozen-x"),
    pytest.param("delete-extra", {"normalizedX": 0.25, "normalizedY": 0.75, "extra": "invalid"}, ["grip.extra"], id="exact-extra-key-omission"),
    pytest.param("unrelated", None, ["inventoryScale"], id="unrelated-repair-no-optional-addition"),
    pytest.param("absent", None, [], id="absent-clears-stale-projection"),
])
def test_metadata_scope_preserves_siblings_and_optional_absence(scenario, grip, paths):
    raw = kit()
    if grip is not None:
        raw["item"]["grip"] = grip
    if scenario == "absent":
        accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
        assert accepted is not None and not errors
        result = visual._apply_kit({"visual": {"grip": {"normalizedX": 0, "normalizedY": 0}, "accessoryMount": "chest"}}, accepted)
        assert all(key not in result["visual"] for key in ("grip", "accessoryMount", "effectColor"))
        return
    if scenario == "unrelated":
        raw["item"]["inventoryScale"] = 99
    _, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert errors
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert scope["fieldPermissions"]["itemPaths"] == paths
    assert scope["fieldPermissions"]["entities"] == []
    patch: dict[str, Any] = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.75 if scenario != "delete-extra" else 0.1}}, equipOverlayPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="exact leaf")
    if scenario == "unrelated":
        patch["itemPatch"]["inventoryScale"] = 2
        patch["equipOverlayPatch"] = dict(raw["equipOverlay"], accessoryMount="chest")
    filtered, audit = visual._filter_visual_repair_patch(raw, patch, scope, ["opaque_id"])
    assert audit["ok"] and audit["ignoredChanges"]
    result, audit = visual._apply_visual_repair_patch(raw, patch, scope, ["opaque_id"], return_audit=True)
    assert audit["ok"]
    if scenario == "unrelated":
        assert result["item"]["inventoryScale"] == 2
        assert "grip" not in result["item"] and "accessoryMount" not in result["equipOverlay"]
    else:
        assert filtered["itemPatch"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
        assert result["item"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
        if scenario == "delete-extra":
            assert "$.itemPatch.grip.extra" in audit["acceptedPaths"]


@pytest.mark.parametrize("scenario", ["extra-keys", "partial-prompt", "unknown-row"])
def test_visual_project_repair_deletes_or_replaces_exact_rows(scenario):
    raw = kit()
    raw.pop("equipOverlay")
    raw["item"]["palette"] = ["brown", "steel"]
    ids = ["opaque_id"]
    item_id = "opaque_id"
    patch: dict[str, Any] = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, entitiesUpsert=[], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="exact visual project repair")
    if scenario == "extra-keys":
        raw["item"][":palette"] = ["invalid duplicate key"]
        raw["entities"][0][":scale"] = 2.0
        errors = [{"path": '$.item[":palette"]', "code": "schema_additional_property", "message": "additional property"},
                  {"path": '$.entities[0][":scale"]', "code": "schema_additional_property", "message": "additional property"}]
        patch["itemPatch"] = {k: v for k, v in raw["item"].items() if k != ":palette"}
        patch["entitiesUpsert"] = [{k: v for k, v in raw["entities"][0].items() if k != ":scale"}]
    elif scenario == "partial-prompt":
        raw["item"]["prompt"] = raw["entities"][0]["prompt"] = "broken prompt"
        raw["item"]["palette"] = ["brown"]
        errors = [{"path": "$.item.prompt", "code": "schema_min_length", "message": "prompt is empty or invalid"}]
        patch["itemPatch"] = {"prompt": "wooden blade with a literal workbench guard"}
        patch["entitiesUpsert"] = [dict(raw["entities"][0], prompt=patch["itemPatch"]["prompt"])]
    else:
        ids = ["opaque_id", "whip_projectile", "spore_particle"]
        valid_item = copy.deepcopy(raw["entities"][0])
        raw["entities"] = [{**valid_item, "entityId": "item_handle", "visualProjectRef": "entity"},
                           {"entityId": "whip_projectile", "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0},
                           {"entityId": "spore_particle", "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0}]
        accepted, errors = visual._validate_kit(raw, ids, item_id)
        assert accepted is None
        patch["entitiesUpsert"] = [valid_item]
    before = copy.deepcopy(raw)
    scope = visual._build_visual_repair_scope(raw, errors, ids, item_id)
    if scenario == "unknown-row":
        assert scope["entityReplacementTransactions"] == [{"entityId": item_id, "replaceIndex": 0}]
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ids, return_audit=True)
    assert audit["ok"], audit
    if scenario == "extra-keys":
        assert ":palette" not in repaired["item"] and ":scale" not in repaired["entities"][0]
        assert repaired["entities"][0]["scale"] == 1.0
    elif scenario == "partial-prompt":
        assert repaired["item"]["prompt"] == patch["itemPatch"]["prompt"]
        assert repaired["item"]["silhouette"] == before["item"]["silhouette"]
    else:
        assert [e["entityId"] for e in repaired["entities"]] == ["whip_projectile", "spore_particle", item_id]
        assert 0 in audit["filteredPatch"]["entityIndicesDelete"]
    assert repaired["item"]["palette"] == before["item"]["palette"]
    accepted, errors = visual._validate_kit(repaired, ids, item_id)
    assert accepted is not None, errors


@pytest.mark.parametrize("scenario", ["complete-item-design", "missing-prompt", "missing-silhouette", "missing-identity", "explicit-wrong-item-mode", "missing-nonitem-mode", "incomplete-roster"])
def test_item_png_fix_has_narrow_authored_preconditions(scenario):
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(compiled)
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    ids = [e["id"] for e in compiled["runtimeProgram"]["entities"]]
    item_row = next(e for e in raw["entities"] if e["entityId"] == item_id)
    item_row.pop("assetMode")
    missing = {"missing-prompt": "prompt", "missing-silhouette": "silhouette", "missing-identity": "visualIdentity"}.get(scenario)
    if missing:
        item_row[missing] = ""
    elif scenario == "explicit-wrong-item-mode":
        item_row["assetMode"] = "no_asset"
    elif scenario == "missing-nonitem-mode":
        raw["entities"][1].pop("assetMode")
    elif scenario == "incomplete-roster":
        item_row["assetMode"] = "no_asset"
        raw["entities"] = [item_row]
    accepted, errors = visual._validate_kit(raw, ids, item_id)
    assert (accepted is not None) is (scenario == "complete-item-design"), errors
    if scenario == "missing-nonitem-mode":
        assert any(e["path"].endswith(".assetMode") for e in errors)
    if scenario == "incomplete-roster":
        assert any("must use baked_sprite" in e["message"] for e in errors)
        assert any("missing entity rows" in e["message"] for e in errors)
    for entity in compiled["runtimeProgram"]["entities"]:
        authored = next((e for e in raw["entities"] if e["entityId"] == entity["id"]), {"assetMode": "reuse_item_icon"})
        entity["visual"] = {k: v for k, v in authored.items() if k != "entityId"}
    apply_visual_asset_runtime_gates(compiled, {})
    item = next(e for e in compiled["runtimeProgram"]["entities"] if e["id"] == item_id)
    row = next(e for e in build_visual_asset_plan(compiled) if e["role"] == "item")
    item_fix = scenario in {"complete-item-design", "missing-nonitem-mode"}
    assert item["visual"]["assetMode"] == ("baked_sprite" if item_fix else "")
    if item_fix:
        reason = "fix:item_body_baked_sprite_from_complete_visual_design"
        assert row["runtimeGateReason"] == reason
        assert compiled["debug"]["visualAssetFixes"] == [{"entityId": item_id, "field": "assetMode", "value": "baked_sprite", "reason": reason}]
    elif missing:
        assert row["runtimeGateReason"] == "invalid_or_missing_authored_asset_mode"
        assert not compiled.get("debug", {}).get("visualAssetFixes")


@pytest.mark.parametrize("scenario,path", [("missing-pair", "$.slots[0]"), ("exact-id", "$.slots[0].id"), ("motif-overflow", "$.motif.element"), ("unknown-field", "inventedStyle")])
def test_vfx_wire_rejects_invalid_pairs_and_preserves_invalid_values(scenario, path):
    compiled = _accepted_visual_data("returning_potion")
    raw = _vfx_output(compiled)
    assert vfx_director_surface(compiled)["runtimePairs"]
    if scenario == "missing-pair":
        raw["slots"][0].update(entityId="not_real", event="on_hit")
    elif scenario == "exact-id":
        raw["slots"][0]["id"] = " bad "
    elif scenario == "motif-overflow":
        raw["motif"]["element"] = "x" * 49
    else:
        raw["slots"][0]["inventedStyle"] = "code must not drop me"
    report = validate_vfx_director_output(raw, compiled)
    assert report["ok"] is False
    assert any(path in e["path"] or path in e["message"] for e in report["errors"])
    if scenario == "missing-pair":
        assert any("absent from runtimeProgram" in e["message"] for e in report["errors"])
    elif scenario == "exact-id":
        assert report["normalized"]["slots"][0]["id"] == " bad "
    elif scenario == "motif-overflow":
        assert report["normalized"]["motif"]["element"] == "x" * 49


def test_visual_to_vfx_asset_consumer_closure():
    compiled = compile_runtime_program(build_runtime_fixture("held_and_deployed"))
    ids = [e["id"] for e in compiled["runtimeProgram"]["entities"]]
    raw = _visual_kit(compiled)
    kit_value, errors = visual._validate_kit(raw, ids, compiled["runtimeProgram"]["itemEntityId"])
    assert kit_value is not None and errors == []
    assert {e["entityId"] for e in kit_value["entities"]} == set(ids)
    compiled = visual._apply_kit(compiled, kit_value)
    pair = vfx_director_surface(compiled)["runtimePairs"][0]
    vfx = _vfx_output(compiled)
    vfx["slots"][0].update(id="closure_slot", layer="AfterProjectiles")
    assert validate_vfx_director_output(vfx, compiled)["ok"]
    final = attach_hybrid_vfx_manifest(compiled, "lantern pike", llm_director=lambda *_args, **_kwargs: copy.deepcopy(vfx))
    slot = final["vfxManifest"]["slots"][0]
    assert (slot["entityId"], slot["event"]) == (pair["entityId"], pair["event"])
    assert slot["layer"] == "AfterProjectiles"
    assert all(field not in slot for field in ("curve", "importance", "variant"))
    impact = copy.deepcopy(vfx)
    impact["slots"][0].update(id="impact_asset_slot", rendererKind="impactSprite", backend="Sprite", textureRole="impact", anchor="hitPoint", channel="impactShape", emissionMode="burst", spritePrompt="literal authored lantern impact", spriteNegativePrompt="text, watermark")
    unpaired = copy.deepcopy(vfx)
    unpaired["slots"][0]["textureRole"] = "impact"
    report = validate_vfx_director_output(unpaired, compiled)
    assert not report["ok"] and any(e["path"] == "$.slots[0].textureRole" for e in report["errors"])
    paired = copy.deepcopy(impact)
    paired["slots"].append({**unpaired["slots"][0], "id": "impact_trail_slot"})
    assert validate_vfx_director_output(paired, compiled)["ok"]
    primitive = copy.deepcopy(unpaired)
    primitive["slots"][0]["rendererKind"] = "impactRing"
    assert validate_vfx_director_output(primitive, compiled)["ok"]
    impact_final = attach_hybrid_vfx_manifest(compiled, "lantern pike impact", llm_director=lambda *_args, **_kwargs: copy.deepcopy(impact))
    assert all(field not in impact_final["vfxManifest"]["slots"][0] for field in ("spritePrompt", "spriteNegativePrompt"))
    entity = next(e for e in impact_final["runtimeProgram"]["entities"] if e["id"] == pair["entityId"])
    assert entity["visual"]["impactPrompt"] == "literal authored lantern impact"
    assert entity["visual"]["impactNegativePrompt"] == "text, watermark"


def test_finished_png_metrics_are_diagnostic_not_presentation(tmp_path):
    path = tmp_path / "soul.png"
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for y in range(8, 24):
        for x in range(8, 24):
            img.putpixel((x, y), (255, 72, 32, 255))
    img.putpixel((16, 16), (255, 240, 80, 255))
    img.save(path)
    data = {"id": "soul_test", "visual": {"palette": ["tin"]}, "debug": {}}
    VISUAL.attach_visual_soul_from_sprite(data, str(path), validation={"ok": True}, score=0.77)
    assert data["visual"] == {"palette": ["tin"]}
    metrics = json.loads(data["debug"]["spritePixelMetrics"])
    assert metrics["spriteSignature"]
    assert metrics["accentColorHex"].startswith("#") and metrics["dominantColorHex"].startswith("#")
    assert 0.0 < metrics["coverage"] <= 1.0 and 0.0 <= metrics["edgeDensity"] <= 1.0
    assert "visualSoulGlow" not in metrics and "visualSoulPulse" not in metrics
    root = Path(visual.__file__).resolve().parents[3] / "ModSources/InfiniCrafterLocal"
    model = read_text_with_partial_bundles(root / "Common/Models/GeneratedItemData.cs")
    item = (root / "Content/Items/GeneratedItem.cs").read_text(encoding="utf-8")
    held = (root / "Common/Players/GeneratedHeldItemDrawLayer.cs").read_text(encoding="utf-8")
    player = read_text_with_partial_bundles(root / "Common/Players/InfiniCraftPlayer.cs")
    assert "public string VisualSoulSignature" in model
    assert all(forbidden not in item for forbidden in ("InfiniVisualSoul", "VisualSoulAuraEligible", "DrawSoulGlow", "VisualSoulColor", "SpawnSoulDust", "AddSoulDrawData"))
    assert "GeneratedItem.AddSoulDrawData" not in held
    assert "RunLocalCraftReveal" in player
    assert "VisualSoulAuraEligible(data)" not in player and "✦ Discovered:" not in player


def test_empty_authored_negative_prompt_reaches_backend_without_fallback() -> None:
    mapping = comfyui_mapping("literal item", "", "negative_prompt_exact", seed=123)
    assert mapping["{{NEGATIVE_PROMPT}}"] == ""


def test_visual_roles_are_exact_runtime_entity_ids_not_family_roles() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("held_and_deployed"))
    roles = runtime_visual_roles(compiled)
    ids = {row["entityId"] for row in roles}
    assert ids == {row["id"] for row in compiled["runtimeProgram"]["entities"]}
    assert {row["visualRole"] for row in roles} >= {"inventory_item", "held_body", "deployed_entity", "child_projectile"}
    assert all("family" not in key.lower() for row in roles for key in row)


def test_vfx_runtime_pairs_follow_actual_item_and_projectile_emitters() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("workbench_blade"))
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    primary_target = compiled["runtimeProgram"]["bindings"][0]["usePolicy"]["action"]["targetId"]
    pairs = {
        (row["entityId"], row["event"])
        for row in runtime_event_inventory(compiled)
    }
    assert (item_id, "on_use") in pairs
    assert (item_id, "periodic") in pairs
    assert (item_id, "on_hit") in pairs
    assert (item_id, "on_crit") in pairs
    assert (item_id, "on_spawn") not in pairs
    assert (item_id, "on_expire") not in pairs
    assert (item_id, "on_kill") not in pairs
    assert (primary_target, "on_spawn") in pairs
    assert (primary_target, "on_expire") in pairs
    assert (primary_target, "on_kill") in pairs
    assert (primary_target, "on_use") not in pairs

    place_only = compile_runtime_program(build_capability_witness("configure_placeable"))
    place_item_id = place_only["runtimeProgram"]["itemEntityId"]
    place_pairs = {
        (row["entityId"], row["event"])
        for row in runtime_event_inventory(place_only)
    }
    assert (place_item_id, "periodic") in place_pairs
    assert (place_item_id, "on_use") not in place_pairs
    assert (place_item_id, "on_hit") not in place_pairs
    assert (place_item_id, "on_crit") not in place_pairs


def test_visual_gate_reason_stays_in_asset_plan_not_executable_runtime_wire() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    for entity in compiled["runtimeProgram"]["entities"]:
        visual = entity.setdefault("visual", {})
        visual["assetMode"] = "baked_sprite" if entity["kind"] == "item_body" else "reuse_item_icon"
        visual["runtimeGateReason"] = "stale_control_plane_value"

    apply_visual_asset_runtime_gates(compiled, {})
    plan = build_visual_asset_plan(compiled)

    assert plan
    assert all(row["runtimeGateReason"] == "authored_runtime_entity_asset_mode" for row in plan)
    assert all("runtimeGateReason" not in entity["visual"] for entity in compiled["runtimeProgram"]["entities"])
    assert validate_runtime_wire(compiled)["ok"] is True


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


@pytest.mark.parametrize("item_canvas,entity_canvas", [(32, 64), (96, 64), (128, 32)])
def test_declared_render_size_and_bake_canvas_do_not_change_mechanics(item_canvas, entity_canvas):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    before = copy.deepcopy(data)
    raw = _visual_kit(data)
    raw["item"].update(preferredCanvasSize=item_canvas, renderSizePx=40)
    item_id = data["runtimeProgram"]["itemEntityId"]
    other = next(row for row in raw["entities"] if row["entityId"] != item_id)
    other.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="independent authored object",
                 silhouette="authored object", visualIdentity="independent object", preferredCanvasSize=entity_canvas,
                 renderSizePx=48, forwardAngleDegrees=-30)
    ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    accepted, errors = visual._validate_kit(raw, ids, item_id)
    assert accepted is not None and not errors, errors
    projected = visual._apply_kit(data, accepted)
    assert projected["visual"]["renderSizePx"] == 40
    assert projected["visual"]["forwardAngleDegrees"] == 45
    entity = next(row for row in projected["runtimeProgram"]["entities"] if row["id"] == other["entityId"])
    assert entity["visual"]["renderSizePx"] == 48
    assert entity["visual"]["forwardAngleDegrees"] == -30
    item_entity = next(row for row in projected["runtimeProgram"]["entities"] if row["id"] == item_id)
    assert all(field not in item_entity["visual"] for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"))
    assert entity["visual"]["preferredCanvasSize"] == entity_canvas
    plan = build_visual_asset_plan(projected)
    assert next(row for row in plan if row["entityId"] == entity["id"])["canvas"] == entity_canvas
    for old, new in zip(before["runtimeProgram"]["entities"], projected["runtimeProgram"]["entities"]):
        assert {key: value for key, value in old.items() if key != "visual"} == {key: value for key, value in new.items() if key != "visual"}
    assert projected["gameplay"] == before["gameplay"]
    assert data == before


@pytest.mark.parametrize("field,good,bad", [
    ("renderSizePx", 1, [None, True, "40", 0, -1, 513, 1.0]),
    ("forwardAngleDegrees", -180, [None, True, "45", -181, 181, float("nan"), float("inf")]),
    ("preferredCanvasSize", 128, [None, True, "64", 16, 65, 64.0]),
])
@pytest.mark.parametrize("owner", ["item", "distinct"])
def test_wire_presentation_is_absence_compatible_but_strict_when_present(field, good, bad, owner):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    before = copy.deepcopy(data)
    assert validate_runtime_wire(data)["ok"]
    assert sanitize_recipe_for_delivery(data).get("visual") == sanitize_recipe_for_delivery(before).get("visual")
    if owner == "item" and field == "preferredCanvasSize":
        # The old root canvas normalization contract is deliberately unchanged.
        return
    if owner == "item":
        target, path = data.setdefault("visual", {}), f"$.visual.{field}"
    else:
        index = next(i for i, row in enumerate(data["runtimeProgram"]["entities"]) if row["kind"] != "item_body")
        target = data["runtimeProgram"]["entities"][index]["visual"]
        target["assetMode"] = "baked_sprite"
        path = f"$.runtimeProgram.entities[{index}].visual.{field}"
    target[field] = good
    assert validate_runtime_wire(data)["ok"]
    for value in bad:
        target[field] = value
        report = validate_runtime_wire(data)
        assert not report["ok"], (field, value, report)
        assert any(row["path"] == path for row in report["errors"])
    assert before == compile_runtime_program(build_runtime_fixture("door_on_chain"))


def test_delivered_presentation_survives_sanitizer_without_alias_authorities():
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    accepted, errors = visual._validate_kit(raw, ids, data["runtimeProgram"]["itemEntityId"])
    assert accepted is not None, errors
    applied = visual._apply_kit(data, accepted)
    delivered = sanitize_recipe_for_delivery(applied)
    assert delivered["visual"]["renderSizePx"] == 40
    assert delivered["visual"]["forwardAngleDegrees"] == 45
    assert validate_runtime_wire(delivered)["ok"]
    for row in delivered["runtimeProgram"]["entities"]:
        assert all(field not in row["visual"] for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"))
    assert applied["gameplay"] == data["gameplay"]
    assert "visualKit" not in delivered


@pytest.mark.parametrize("mode", ["reuse_item_icon", "runtime_geometry", "no_asset", "baked_sprite"])
@pytest.mark.parametrize("field", ["renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"])
def test_wire_rejects_metadata_on_nonowning_projects(mode, field):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    index = 0 if mode == "baked_sprite" else 1
    entity = data["runtimeProgram"]["entities"][index]
    entity["visual"].update(assetMode=mode, **{field: 32})
    report = validate_runtime_wire(data)
    assert not report["ok"]
    assert any(e["path"] == f"$.runtimeProgram.entities[{index}].visual.{field}" for e in report["errors"])


@pytest.mark.parametrize("field,value", [
    ("renderSizePx", None), ("renderSizePx", True), ("renderSizePx", "40"),
    ("renderSizePx", 0), ("renderSizePx", 513), ("renderSizePx", 40.0),
    ("forwardAngleDegrees", None), ("forwardAngleDegrees", True), ("forwardAngleDegrees", "45"),
    ("forwardAngleDegrees", -181), ("forwardAngleDegrees", float("nan")), ("forwardAngleDegrees", float("inf")),
])
def test_fresh_presentation_invalid_values_retain_exact_root_leaf(field, value):
    raw = kit()
    raw["item"][field] = value
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None
    scope = visual._build_visual_repair_scope(raw, errors, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert scope["fieldPermissions"]["itemPaths"] == [field]
    assert scope["fieldPermissions"]["entities"] == []


@pytest.mark.parametrize("owner,field", [("item", "renderSizePx"), ("item", "forwardAngleDegrees"),
    ("distinct", "renderSizePx"), ("distinct", "preferredCanvasSize"), ("distinct", "forwardAngleDegrees")])
def test_missing_presentation_repair_is_exact_and_preserves_independent_mechanics(owner, field):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    ids, item_id = [row["id"] for row in data["runtimeProgram"]["entities"]], data["runtimeProgram"]["itemEntityId"]
    row = next(e for e in raw["entities"] if e["entityId"] != item_id)
    row.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="other", silhouette="other", visualIdentity="other", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=-90)
    target = raw["item"] if owner == "item" else row
    chosen = target.pop(field)
    _, errors = visual._validate_kit(raw, ids, item_id)
    scope = visual._build_visual_repair_scope(raw, errors, ids, item_id)
    expected = {"itemPaths": [field] if owner == "item" else [], "equipOverlayPaths": [],
                "entities": [] if owner == "item" else [{"entityId": row["entityId"], "paths": [field]}]}
    assert scope["fieldPermissions"] == expected
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={field: chosen, "worldScale": 4} if owner == "item" else None,
                 entitiesUpsert=[] if owner == "item" else [dict(row, **{field: chosen}, scale=4, prompt="hostile")],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan="hostile", note="repair exact missing choice")
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ids, return_audit=True)
    assert audit["ok"] and audit["ignoredChanges"]
    expected_raw = copy.deepcopy(raw)
    (expected_raw["item"] if owner == "item" else next(e for e in expected_raw["entities"] if e["entityId"] == row["entityId"]))[field] = chosen
    assert repaired == expected_raw
    accepted, errors = visual._validate_kit(repaired, ids, item_id)
    assert accepted is not None, errors
    applied = visual._apply_kit(data, accepted)
    assert applied["gameplay"] == data["gameplay"]
    assert applied["runtimeProgram"]["itemUse"] == data["runtimeProgram"]["itemUse"]


@pytest.mark.parametrize("mode,ref", [("reuse_item_icon", "item"), ("runtime_geometry", "none"), ("no_asset", "none"), ("baked_sprite", "item")])
@pytest.mark.parametrize("hostile_branch", [False, True])
def test_selected_branch_repair_deletes_only_diagnosed_forbidden_presentation(mode, ref, hostile_branch):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    item_id = data["runtimeProgram"]["itemEntityId"]
    ids = [row["id"] for row in data["runtimeProgram"]["entities"]]
    row = next(e for e in raw["entities"] if (e["entityId"] == item_id) == (mode == "baked_sprite"))
    row.update(assetMode=mode, visualProjectRef=ref, renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=90)
    _, errors = visual._validate_kit(raw, ids, item_id)
    scope = visual._build_visual_repair_scope(raw, errors, ids, item_id)
    assert scope["fieldPermissions"]["entities"] == [{"entityId": row["entityId"], "paths": ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx"]}]
    candidate = {k: v for k, v in row.items() if k not in {"renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"}}
    if hostile_branch:
        candidate.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="hostile", silhouette="hostile", visualIdentity="hostile", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=90)
    candidate["scale"] = 4
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, entitiesUpsert=[candidate], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="delete branch-forbidden leaves")
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ids, return_audit=True)
    assert audit["ok"], audit
    expected = copy.deepcopy(raw)
    expected_row = next(e for e in expected["entities"] if e["entityId"] == row["entityId"])
    for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"):
        del expected_row[field]
    assert repaired == expected
    assert len([p for p in audit["acceptedPaths"] if any(p.endswith(f) for f in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"))]) == 3
    accepted, errors = visual._validate_kit(repaired, ids, item_id)
    assert accepted is not None, errors


def _known_project_transition_case(owner):
    # Exact authored source/targets from the independent known_owner_repro and
    # boundary_followups probes; no inferred presentation choices in production.
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    runtime = data["runtimeProgram"]
    item_id = runtime["itemEntityId"]
    ids = [row["id"] for row in runtime["entities"]]
    item = dict(prompt="literal object", negativePrompt="", silhouette="literal outline",
                visualIdentity="literal composition", palette=["brown"], preferredCanvasSize=32,
                renderSizePx=40, forwardAngleDegrees=0, inventoryScale=1.0, worldScale=1.0)
    rows = [dict(entityId=eid, assetMode="baked_sprite", visualProjectRef="item",
                 prompt=item["prompt"], silhouette=item["silhouette"], visualIdentity=item["visualIdentity"], scale=1.0)
            if eid == item_id else dict(entityId=eid, assetMode="reuse_item_icon", visualProjectRef="item", scale=1.0)
            for eid in ids]
    control: dict[str, Any] = dict(schema=visual.VISUAL_KIT_SCHEMA, item=item, entities=rows, animationPlan="Keep accepted movement")
    raw = copy.deepcopy(control)
    if owner == "root":
        row = next(e for e in raw["entities"] if e["entityId"] == item_id)
        row.update(visualProjectRef="entity", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=90)
    else:
        row = next(e for e in raw["entities"] if e["entityId"] != item_id)
        row.update(assetMode="baked_sprite", visualProjectRef="item", prompt="separate object",
                   silhouette="separate outline", visualIdentity="separate identity")
        fixed = next(e for e in control["entities"] if e["entityId"] == row["entityId"])
        fixed.update(row, visualProjectRef="entity", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=0)
    return data, raw, control, row["entityId"], ids, item_id


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("hostile_mode", [False, True])
def test_known_root_project_transition_closes_real_single_repair(wire_transport, monkeypatch, format_mode, hostile_mode):
    from infini_local.pipelines import llm_transport
    responses, requests = wire_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case("root")
    before = copy.deepcopy(raw)
    assert visual._validate_kit(control, ids, item_id)[0] is not None
    candidate = dict(next(e for e in control["entities"] if e["entityId"] == entity_id),
                     prompt="hostile prompt", silhouette="hostile outline", visualIdentity="hostile art", scale=4)
    if hostile_mode:
        candidate = dict(entityId=entity_id, assetMode="reuse_item_icon", visualProjectRef="item", scale=4)
    neighbor = dict(next(e for e in control["entities"] if e["entityId"] != entity_id), scale=4)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                 itemPatch={"worldScale": 4, "renderSizePx": 512, "preferredCanvasSize": 128, "forwardAngleDegrees": 180,
                            "prompt": "hostile item", "palette": ["pink"], "grip": {"normalizedX": 0, "normalizedY": 0}},
                 entitiesUpsert=[candidate, neighbor], entityIdsDelete=[neighbor["entityId"]],
                 entityIndicesDelete=[1], animationPlan="hostile animation", note="Restore exact item root project")
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    assert result["debug"]["llmStageAccounting"]["visualDirectorCalls"] == 1
    assert result["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"]["fieldPermissions"] == {
        "itemPaths": [], "equipOverlayPaths": [], "entities": [{"entityId": entity_id,
        "paths": ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx", "visualProjectRef"]}]}
    assert all(e["path"] != "$.entities[0].entityId" for e in packet["exactErrors"])
    assert packet["brokenFragments"]["entities"] == [before["entities"][0]]
    assert result["visualKit"] == control
    audit = result["debug"]["visualRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"]
    assert audit["filteredPatch"]["entitiesUpsert"] == [control["entities"][0]]
    assert visual._validate_kit(result["visualKit"], ids, item_id)[1] == []
    assert result["gameplay"] == data["gameplay"]
    assert result["runtimeProgram"]["itemUse"] == data["runtimeProgram"]["itemUse"]
    assert raw == before


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("existing", ["absent", "partial", "complete"])
def test_known_nonitem_project_transition_closes_real_single_repair(wire_transport, monkeypatch, format_mode, existing):
    from infini_local.pipelines import llm_transport
    responses, requests = wire_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case("distinct")
    row = next(e for e in raw["entities"] if e["entityId"] == entity_id)
    target = next(e for e in control["entities"] if e["entityId"] == entity_id)
    fields = ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx"]
    present = fields if existing == "complete" else ["renderSizePx"] if existing == "partial" else []
    for field in present:
        row[field] = target[field]
    candidate = dict(target, prompt="hostile art", silhouette="hostile outline", visualIdentity="hostile identity", scale=4)
    # Existing, valid target-domain metadata is frozen even with a wrong ref.
    for field in present:
        candidate[field] = {"renderSizePx": 512, "preferredCanvasSize": 128, "forwardAngleDegrees": 180}[field]
    root = dict(control["entities"][0], scale=4)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={"worldScale": 4, "palette": ["pink"]},
                 entitiesUpsert=[candidate, root], entityIdsDelete=[item_id], entityIndicesDelete=[0],
                 animationPlan="hostile animation", note="Choose separate exact project")
    assert visual._validate_kit(control, ids, item_id)[0] is not None
    before = copy.deepcopy(raw)
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    assert result["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"]["fieldPermissions"] == {
        "itemPaths": [], "equipOverlayPaths": [], "entities": [{"entityId": entity_id,
        "paths": sorted([f for f in fields if f not in present] + ["visualProjectRef"])}]}
    assert packet["repairScope"]["deletableEntityIndices"] == []
    assert all(e["path"] != "$.entities[1].entityId" for e in packet["exactErrors"])
    assert result["visualKit"] == control
    audit = result["debug"]["visualRepairFilterAudit"]
    assert audit["ok"] and audit["ignoredChanges"]
    assert audit["filteredPatch"]["entitiesUpsert"] == [target]
    assert visual._validate_kit(result["visualKit"], ids, item_id)[1] == []
    assert result["gameplay"] == data["gameplay"]
    assert result["runtimeProgram"]["itemUse"] == data["runtimeProgram"]["itemUse"]
    assert raw == before


@pytest.mark.parametrize("field,old,new", [("renderSizePx", True, 1), ("renderSizePx", 1.0, 1),
    ("preferredCanvasSize", 64.0, 64), ("forwardAngleDegrees", True, 1.0)])
def test_known_project_transition_repairs_only_invalid_target_typed_leaves(wire_transport, field, old, new):
    responses, requests = wire_transport
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case("distinct")
    row = next(e for e in raw["entities"] if e["entityId"] == entity_id)
    target = next(e for e in control["entities"] if e["entityId"] == entity_id)
    target[field] = new
    row.update({f: target[f] for f in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees")})
    row[field] = old
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, entitiesUpsert=[copy.deepcopy(target)],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="Exact target-domain typed correction")
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"]["fieldPermissions"]["entities"] == [{"entityId": entity_id,
        "paths": sorted([field, "visualProjectRef"])}]
    assert result["visualKit"] == control
    fixed = next(e for e in result["visualKit"]["entities"] if e["entityId"] == entity_id)
    assert type(fixed[field]) is type(new) and fixed[field] == new


@pytest.mark.parametrize("owner", ["root", "distinct"])
def test_known_project_transition_uses_exact_opaque_root_identity(wire_transport, owner):
    responses, requests = wire_transport
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case(owner)
    opaque_id = "accepted_opaque_root"
    # A minimal accepted Visual runtime card, not a partially renamed gameplay
    # fixture with stale binding references.
    data = {"name": "opaque root object", "runtimeProgram": {"itemEntityId": opaque_id, "entities": [
        {"id": opaque_id if e["id"] == item_id else e["id"], "kind": e["kind"], "visualRole": e["visualRole"]}
        for e in data["runtimeProgram"]["entities"]]}}
    for document in (raw, control):
        for row in document["entities"]:
            if row["entityId"] == item_id:
                row["entityId"] = opaque_id
    entity_id = opaque_id if owner == "root" else entity_id
    ids = [opaque_id if eid == item_id else eid for eid in ids]
    if owner == "root":
        # Without old dependent fields, only the projectRef is broken; never
        # grant arbitrary metadata additions just because that ref is wrong.
        for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees"):
            raw["entities"][0].pop(field)
    target = next(e for e in control["entities"] if e["entityId"] == entity_id)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, entitiesUpsert=[copy.deepcopy(target)],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="Use exact accepted opaque identity")
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    assert result["visualKit"] == control
    packet = json.loads(requests[1]["messages"][1]["content"])
    expected_paths = ["visualProjectRef"] if owner == "root" else ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx", "visualProjectRef"]
    assert packet["repairScope"]["fieldPermissions"]["entities"] == [{"entityId": entity_id, "paths": expected_paths}]
    assert visual._validate_kit(result["visualKit"], ids, opaque_id)[1] == []


@pytest.mark.parametrize("owner", ["root", "distinct"])
@pytest.mark.parametrize("delete_duplicate", [False, True])
def test_known_project_transition_keeps_original_index_provenance(wire_transport, owner, delete_duplicate):
    responses, requests = wire_transport
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case(owner)
    original = next(e for e in raw["entities"] if e["entityId"] == entity_id)
    duplicate = dict(original, prompt="duplicate art", silhouette="duplicate outline", visualIdentity="duplicate identity", scale=3)
    # Later malformed leaves authorize index deletion, never original-row edits.
    duplicate["scale"] = True
    raw["entities"].append(duplicate)
    target = next(e for e in control["entities"] if e["entityId"] == entity_id)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None,
                 entitiesUpsert=[dict(target, prompt="hostile", silhouette="hostile", visualIdentity="hostile", scale=4)],
                 entityIdsDelete=[entity_id], entityIndicesDelete=[2] if delete_duplicate else [],
                 animationPlan=None, note="Fix original and delete only diagnosed later duplicate")
    _, errors = visual._validate_kit(raw, ids, item_id)
    scope = visual._build_visual_repair_scope(raw, errors, ids, item_id)
    assert scope["deletableEntityIndices"] == [2]
    assert scope["deletableEntityIds"] == []
    assert scope["fieldPermissions"]["entities"] == [{"entityId": entity_id,
        "paths": ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx", "visualProjectRef"]}]
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ids, return_audit=True)
    assert audit["ok"]
    expected = copy.deepcopy(control)
    if not delete_duplicate:
        expected["entities"].append(duplicate)
    assert repaired == expected
    if not delete_duplicate:
        assert visual._validate_kit(repaired, ids, item_id)[0] is None
        return
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"] == scope
    assert result["visualKit"] == control
    assert result["debug"]["visualRepairPatch"]["entityIndicesDelete"] == [2]
    assert result["debug"]["visualRepairPatch"]["entityIdsDelete"] == []


@pytest.mark.parametrize("owner,defect,field", [
    ("root", "no-op", None), ("distinct", "no-op", None),
    *(("distinct", defect, field) for defect in ("missing", "invalid")
      for field in ("renderSizePx", "preferredCanvasSize", "forwardAngleDegrees")),
    ("root", "still-forbidden", "renderSizePx"),
])
def test_known_project_transition_never_invents_unreturned_choices(wire_transport, owner, defect, field):
    from infini_local.core.errors import PlannerUnavailable
    responses, requests = wire_transport
    data, raw, control, entity_id, ids, item_id = _known_project_transition_case(owner)
    candidate = copy.deepcopy(next(e for e in control["entities"] if e["entityId"] == entity_id))
    if defect == "missing":
        candidate.pop(field)
    elif defect == "invalid":
        candidate[field] = True  # Never coerce bool to a numeric choice.
    elif defect == "still-forbidden":
        candidate[field] = 48
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None,
                 entitiesUpsert=[] if defect == "no-op" else [candidate],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="No host completion allowed")
    before = copy.deepcopy(raw)
    responses.extend([raw, patch])
    with pytest.raises(PlannerUnavailable):
        visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    assert data["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"]["fieldPermissions"]["entities"] == [{"entityId": entity_id,
        "paths": ["forwardAngleDegrees", "preferredCanvasSize", "renderSizePx", "visualProjectRef"]}]
    assert raw == before
    if defect == "no-op":
        repaired, audit = visual._apply_visual_repair_patch(raw, patch, packet["repairScope"], ids, return_audit=True)
        assert audit["ok"] and repaired == before
        assert visual._validate_kit(repaired, ids, item_id)[0] is None


@pytest.mark.parametrize("field,value", [
    ("entityId", "unaccepted"), ("entityId", None), ("entityId", ["item"]),
    ("assetMode", "unknown"), ("assetMode", "reuse_item_icon"), ("assetMode", None),
    ("visualProjectRef", "unknown"), ("visualProjectRef", "none"), ("visualProjectRef", None),
])
@pytest.mark.parametrize("owner", ["root", "distinct"])
def test_known_project_transition_does_not_guess_unknown_or_missing_literals(owner, field, value):
    from infini_local.core.repair_merge import merge_frozen_subtree
    _, raw, _, entity_id, ids, item_id = _known_project_transition_case(owner)
    row = next(e for e in raw["entities"] if e["entityId"] == entity_id)
    if value is None:
        row.pop(field)
    else:
        row[field] = value
    before = copy.deepcopy(row)
    assert visual._known_baked_project_target_schema(row, ids, item_id) is None
    # A guessed incoming discriminator cannot affect deletion after frozen merge.
    candidate = dict(row, assetMode="baked_sprite", visualProjectRef="item", foreign=12)
    source = dict(row, foreign=12)
    merged, _, _ = merge_frozen_subtree(source, candidate, mutable_paths=["foreign"], audit_path="$", allow_additions=False)
    assert "foreign" in merged
    accepted = []
    result = visual._drop_schema_forbidden_mutable_fields(source, merged, mutable_paths=("foreign",),
        schema=visual._visual_entity_schema(ids, item_id), audit_path="$", accepted=accepted)
    if field in {"assetMode", "visualProjectRef"} and value not in {"reuse_item_icon", "none"}:
        assert result == merged and accepted == []
    assert row == before


def test_known_project_transition_declines_ambiguous_target_schema(monkeypatch):
    _, raw, _, entity_id, ids, item_id = _known_project_transition_case("root")
    schema = visual._visual_entity_schema(ids, item_id)
    branch = next(b for b in schema["oneOf"] if b["properties"]["assetMode"]["const"] == "baked_sprite"
                  and b["properties"]["visualProjectRef"]["const"] == "item")
    schema["oneOf"].append(copy.deepcopy(branch))
    monkeypatch.setattr(visual, "_visual_entity_schema", lambda *_: schema)
    assert visual._known_baked_project_target_schema(raw["entities"][0], ids, item_id) is None


@pytest.mark.parametrize("discriminator", ["unknown", "ambiguous", "missing"])
def test_branch_forbidden_deletion_does_not_guess_discriminators(discriminator):
    schema = visual._visual_entity_schema(["opaque_id"])
    source = {"entityId": "opaque_id", "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1, "foreign": 12}
    if discriminator == "unknown":
        source["assetMode"] = "unknown"
    elif discriminator == "missing":
        source.pop("visualProjectRef")
    else:
        schema["oneOf"].append(copy.deepcopy(next(b for b in schema["oneOf"] if b["properties"]["assetMode"]["const"] == "reuse_item_icon")))
    accepted = []
    result = visual._drop_schema_forbidden_mutable_fields(source, source, mutable_paths=("foreign",), schema=schema, audit_path="$.entities[0]", accepted=accepted)
    assert result == source and accepted == []


@pytest.mark.parametrize("field,old,new", [("renderSizePx", True, 1), ("renderSizePx", 1.0, 1), ("preferredCanvasSize", 64.0, 64), ("forwardAngleDegrees", True, 1.0)])
def test_distinct_presentation_type_only_repair_is_retained(field, old, new):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    ids = [e["id"] for e in data["runtimeProgram"]["entities"]]
    item_id = data["runtimeProgram"]["itemEntityId"]
    row = next(e for e in raw["entities"] if e["entityId"] != item_id)
    row.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="other", silhouette="other", visualIdentity="other", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=0)
    row[field] = old
    _, errors = visual._validate_kit(raw, ids, item_id)
    scope = visual._build_visual_repair_scope(raw, errors, ids, item_id)
    assert scope["fieldPermissions"]["entities"] == [{"entityId": row["entityId"], "paths": [field]}]
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch=None, entitiesUpsert=[dict(row, **{field: new})], entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="exact typed correction")
    repaired, audit = visual._apply_visual_repair_patch(raw, patch, scope, ids, return_audit=True)
    assert audit["ok"] and len(audit["filteredPatch"]["entitiesUpsert"]) == 1
    corrected = next(e for e in repaired["entities"] if e["entityId"] == row["entityId"])
    assert type(corrected[field]) is type(new) and corrected[field] == new
    assert visual._validate_kit(repaired, ids, item_id)[0] is not None


def test_new_visual_admission_does_not_accept_a_historical_v1_missing_choices():
    raw = kit()
    raw["schema"] = "infini.visual-kit.runtime-entities.v1"
    raw["item"].pop("renderSizePx")
    raw["item"].pop("forwardAngleDegrees")
    before = copy.deepcopy(raw)
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None
    assert {"$.schema", "$.item.renderSizePx", "$.item.forwardAngleDegrees"}.issubset({e["path"] for e in errors})
    assert raw == before


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("owner,field,defect", [("item", "renderSizePx", "missing"), ("item", "forwardAngleDegrees", "null"),
    ("distinct", "preferredCanvasSize", "missing"), ("distinct", "renderSizePx", "null"), ("distinct", "forwardAngleDegrees", "missing"),
    ("reuse", "renderSizePx", "forbidden")])
def test_actual_sizing_director_and_one_repair_keep_exact_choices(wire_transport, monkeypatch, format_mode, owner, field, defect):
    from infini_local.pipelines import llm_transport
    responses, requests = wire_transport
    monkeypatch.setattr(llm_transport, "LLM_RESPONSE_FORMAT_MODE", format_mode)
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    item_id = data["runtimeProgram"]["itemEntityId"]
    row = next(e for e in raw["entities"] if e["entityId"] != item_id)
    if owner == "distinct":
        row.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="other", silhouette="other", visualIdentity="other", renderSizePx=48, preferredCanvasSize=64, forwardAngleDegrees=-90)
    target = raw["item"] if owner == "item" else row
    chosen = target.get(field)
    if defect == "missing":
        del target[field]
    else:
        target[field] = None
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA, itemPatch={field: chosen, "worldScale": 4} if owner == "item" else None,
                 entitiesUpsert=[] if owner == "item" else [{**{k:v for k,v in row.items() if k != field}, **({field: chosen} if defect != "forbidden" else {}), "scale": 4}],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="exact presentation correction")
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    assert len(requests) == 2 and not responses
    assert result["debug"]["llmStageAccounting"]["visualRepairCalls"] == 1
    packet = json.loads(requests[1]["messages"][1]["content"])
    assert packet["repairScope"]["fieldPermissions"] == {"itemPaths": [field] if owner == "item" else [], "equipOverlayPaths": [],
           "entities": [] if owner == "item" else [{"entityId": row["entityId"], "paths": [field]}]}
    broken = packet["brokenFragments"]["item"] if owner == "item" else packet["brokenFragments"]["entities"][0]
    assert (field in broken) is (defect != "missing")
    if defect != "missing":
        assert broken[field] is None
    target_result = result["visualKit"]["item"] if owner == "item" else next(e for e in result["visualKit"]["entities"] if e["entityId"] == row["entityId"])
    if defect == "forbidden":
        assert field not in target_result
    else:
        assert target_result[field] == chosen
    assert result["gameplay"] == data["gameplay"]
    assert result["runtimeProgram"]["itemUse"] == data["runtimeProgram"]["itemUse"]
    assert result["visual"]["worldScale"] == raw["item"]["worldScale"]
    assert next(e for e in result["visualKit"]["entities"] if e["entityId"] == row["entityId"])["scale"] == row["scale"]


from infini_local.core.item_identity_tools import recipe_key
from infini_local.pipelines.parent_context_cards import raw_parent_card_for_llm


def _native_sprite_reference(frame_source="texture_bounds"):
    return {"source": "TextureAssets.Item", "textureWidthPx": 40, "textureHeightPx": 68,
            "currentFrame": {"source": frame_source, "xPx": 0, "yPx": 0 if frame_source == "texture_bounds" else 34,
                             "widthPx": 40, "heightPx": 68 if frame_source == "texture_bounds" else 32}}


@pytest.mark.parametrize("frame_source", ["texture_bounds", "draw_animation"])
def test_parent_native_sprite_reference_is_visual_only_exact_and_detached(frame_source):
    parent = {"id": 1, "name": "literal", "damage": 17, "createTile": None,
              "width": 999, "height": 888, "scale": 4, "spriteReferenceRaw": _native_sprite_reference(frame_source)}
    before = copy.deepcopy(parent)
    gameplay = raw_parent_card_for_llm(parent)
    stripped = {key: value for key, value in parent.items() if key != "spriteReferenceRaw"}
    assert gameplay == raw_parent_card_for_llm(stripped)
    assert "spriteReference" not in gameplay["raw"]
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert card["raw"]["spriteReference"] == parent["spriteReferenceRaw"]
    assert {key: value for key, value in card["raw"].items() if key != "spriteReference"} == gameplay["raw"]
    assert parent == before
    assert recipe_key(parent, parent, 7, "frozen") == recipe_key(stripped, stripped, 7, "frozen")
    card["raw"]["spriteReference"]["currentFrame"]["xPx"] = 1
    assert parent == before


@pytest.mark.parametrize("size", [1, 47, 512])
def test_generated_parent_visual_reference_keeps_present_calibration_without_inference(size):
    parent = {"id": 1, "name": "shared proxy", "width": 123, "height": 456,
              "spriteReferenceRaw": _native_sprite_reference(),
              "generatedData": {"id": "exact-definition", "visual": {"renderSizePx": size,
                  "preferredCanvasSize": 32, "worldScale": 4, "inventoryScale": 3, "spritePath": "private.png"},
                  "gameplay": {"damage": 17}, "runtimeProgram": {"entities": [], "bindings": []}}}
    before = copy.deepcopy(parent)
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert "spriteReference" not in card["raw"]
    calibration = {"renderSizePx": size, "preferredCanvasSize": 32, "worldScale": 4, "inventoryScale": 3}
    assert card["raw"]["generatedParent"]["visual"] == calibration
    gameplay = raw_parent_card_for_llm(parent)
    assert "visual" not in gameplay["raw"]["generatedParent"]
    assert parent == before
    undeclared = copy.deepcopy(parent)
    undeclared["generatedData"]["visual"].pop("renderSizePx")
    assert raw_parent_card_for_llm(undeclared, include_visual_reference=True)["raw"]["generatedParent"]["visual"] == {
        key: value for key, value in calibration.items() if key != "renderSizePx"
    }
    assert recipe_key(parent, parent, 7, "frozen") == recipe_key(undeclared, undeclared, 7, "frozen")
    other = copy.deepcopy(parent)
    other["generatedData"]["id"] = "other-definition"
    other["generatedData"]["visual"]["renderSizePx"] = 91
    assert raw_parent_card_for_llm(other, include_visual_reference=True)["raw"]["generatedParent"]["visual"] == {**calibration, "renderSizePx": 91}
    card["raw"]["generatedParent"]["visual"]["renderSizePx"] = 2
    assert parent == before


@pytest.mark.parametrize("raw", [
    None, {}, [], {"source": "TextureAssets.Item", "textureWidthPx": 40},
    *({**_native_sprite_reference(), "source": token} for token in ("texture_bounds", "textureassets.item", " TextureAssets.Item", None)),
    *({**_native_sprite_reference(), "textureWidthPx": value} for value in (True, "40", 40.0, 0, -1, 2_147_483_648)),
    *({**_native_sprite_reference(), "textureHeightPx": value} for value in (False, "68", 68.0, 0, -1, 2_147_483_648)),
])
def test_parent_malformed_native_observation_is_omitted_without_gameplay_failure(raw):
    parent = {"name": "still valid gameplay parent", "damage": 17, "spriteReferenceRaw": raw}
    before = copy.deepcopy(parent)
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert card == raw_parent_card_for_llm(parent)
    assert parent == before


@pytest.mark.parametrize("frame", [
    None, {}, [], {"source": "draw_animation"},
    *({**_native_sprite_reference()["currentFrame"], "source": source} for source in ("Draw_Animation", "TextureAssets.Item", None)),
    *({**_native_sprite_reference("draw_animation")["currentFrame"], key: value} for key, value in (
        ("xPx", True), ("yPx", "0"), ("widthPx", 11.0), ("heightPx", False),
        ("xPx", -1), ("yPx", -1), ("widthPx", 0), ("heightPx", 0),
        ("xPx", 40), ("yPx", 68), ("widthPx", 41), ("heightPx", 69), ("xPx", 2_147_483_647))),
    {"source": "texture_bounds", "xPx": 0, "yPx": 0, "widthPx": 40, "heightPx": 32},
])
def test_parent_unknown_or_bad_frame_keeps_only_valid_texture_dimensions(frame):
    raw = _native_sprite_reference()
    raw["currentFrame"] = frame
    parent = {"name": "literal", "spriteReferenceRaw": raw}
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert card["raw"]["spriteReference"] == {key: value for key, value in raw.items() if key != "currentFrame"}


@pytest.mark.parametrize("size", [None, False, True, "47", 47.0, 0, -1, 513, {}, []])
def test_generated_parent_bad_or_old_size_stays_unknown_without_inference(size):
    parent = {"name": "shared proxy", "spriteReferenceRaw": _native_sprite_reference(),
              "generatedData": {"id": "same-definition", "visual": {"renderSizePx": size,
                  "preferredCanvasSize": 32, "worldScale": 4, "inventoryScale": 3},
                  "gameplay": {"width": 64, "height": 32}, "runtimeProgram": {"entities": [], "bindings": []}}}
    card = raw_parent_card_for_llm(parent, include_visual_reference=True)
    assert card["raw"]["generatedParent"]["visual"] == {
        "preferredCanvasSize": 32, "worldScale": 4, "inventoryScale": 3,
    }
    assert "spriteReference" not in card["raw"]
    author_card = raw_parent_card_for_llm(parent)
    without_visual = copy.deepcopy(card)
    without_visual["raw"]["generatedParent"].pop("visual")
    assert without_visual == author_card


def test_parent_reference_never_reads_fingerprint_or_proxy_and_accepts_loaded_literal_one_pixel():
    raw = {"source": "TextureAssets.Item", "textureWidthPx": 1, "textureHeightPx": 1}
    parent = {"name": "literal", "fingerprint": {"spriteReferenceRaw": raw}, "runtimeFacts": {"spriteReferenceRaw": raw}}
    assert "spriteReference" not in raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]
    parent["spriteReferenceRaw"] = raw
    assert raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["spriteReference"] == raw
    parent["generatedData"] = {}
    assert "spriteReference" not in raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]


def test_parent_reference_is_key_name_independent_and_whitelists_native_fact_members():
    raw = _native_sprite_reference("draw_animation")
    raw["privatePath"] = "/not/model/context.png"
    raw["currentFrame"]["extra"] = "not a captured rectangle member"
    first = {"id": 7, "name": "Blade", "sourceMod": "Terraria", "spriteReferenceRaw": raw}
    second = {**first, "id": 8, "name": "Staff", "sourceMod": "UnrelatedMod"}
    expected = _native_sprite_reference("draw_animation")
    for parent in (first, second):
        assert raw_parent_card_for_llm(parent, include_visual_reference=True)["raw"]["spriteReference"] == expected


@pytest.mark.parametrize("format_mode", ["json_schema", "json_object"])
@pytest.mark.parametrize("capability,slot,source", [("move_whip_lash", "movement", "whip"), ("channel_beam", "controller", "beam")])
@pytest.mark.parametrize("asset_mode", ["baked_sprite", "runtime_geometry"])
def test_physical_geometry_guidance_reaches_director_repair_and_vfx_without_selecting_representation(wire_transport, monkeypatch, format_mode, capability, slot, source, asset_mode):
    from infini_local.core import vfx_manifest as vfx
    from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY
    from infini_local.pipelines import llm_authoring_pipeline as gameplay
    from vfx_material_fixtures import _path
    monkeypatch.setattr("infini_local.pipelines.llm_transport.LLM_RESPONSE_FORMAT_MODE", format_mode)
    responses, requests = wire_transport
    data = compile_runtime_program(build_capability_witness(capability))
    before = copy.deepcopy(data)
    entity = next(e for e in data["runtimeProgram"]["entities"] if e["kind"] != "item_body")
    raw = _visual_kit(data)
    row = next(e for e in raw["entities"] if e["entityId"] == entity["id"])
    row.update(assetMode=asset_mode, visualProjectRef="entity" if asset_mode == "baked_sprite" else "none")
    if asset_mode == "baked_sprite":
        row.update(prompt="literal terminal body, not the complete collision path", silhouette="small terminal body", visualIdentity="authored tip body", renderSizePx=24, preferredCanvasSize=32, forwardAngleDegrees=0)
    accepted = copy.deepcopy(raw)
    raw["item"]["inventoryScale"] = 99
    responses.extend([raw, {"schema": visual.VISUAL_REPAIR_PATCH_SCHEMA, "itemPatch": {"inventoryScale": 1.0}, "entitiesUpsert": [], "entityIdsDelete": [], "entityIndicesDelete": [], "animationPlan": None, "note": "inventoryScale only"}])
    projected = visual.apply_visual_director(data, {}, {}, {}, {})
    assert projected["visualKit"] == accepted
    authored_vfx = _path(projected, source)
    if asset_mode == "runtime_geometry":
        authored_vfx["slots"] = []  # Geometry is already drawn; no forced VFX slot count.
    assert vfx.validate_vfx_director_output(authored_vfx, projected)["ok"]
    raw_vfx = copy.deepcopy(authored_vfx)
    raw_vfx["effectMagnitude"] = 2
    responses.extend([raw_vfx, {"schema": vfx.VFX_REPAIR_PATCH_SCHEMA, "effectMagnitude": authored_vfx["effectMagnitude"], "slotsUpsert": [], "note": "effectMagnitude only"}])
    final = vfx.attach_hybrid_vfx_manifest(projected, "physical-geometry", llm_director=gameplay.call_llm_vfx_director)
    assert not responses and len(requests) == 4
    packets = [json.loads(r["messages"][1]["content"]) for r in requests]
    assert packets[1]["repairScope"]["fieldPermissions"] == {"itemPaths": ["inventoryScale"], "equipOverlayPaths": [], "entities": []}
    assert packets[3]["repairScope"]["fieldPermissions"] == {"globals": {"effectMagnitude": [""]}, "slots": [], "assets": []}
    assert final["visualKit"] == accepted
    assert final["debug"]["vfxDirectorRaw"] == authored_vfx
    assert final["runtimeProgram"]["itemUse"] == before["runtimeProgram"]["itemUse"]
    assert final["gameplay"] == before["gameplay"]
    for old, new in zip(before["runtimeProgram"]["entities"], final["runtimeProgram"]["entities"]):
        assert {k: v for k, v in old.items() if k != "visual"} == {k: v for k, v in new.items() if k != "visual"}
    for i, key in enumerate(("runtimeEntities", "runtimeEntitiesReadOnly")):
        owner = next(r for r in packets[i][key] if r["id"] == entity["id"])
        assert owner[slot] == entity[slot]
        assert owner["driverMeaningReadOnly"][slot] == CAPABILITY_REGISTRY[capability].summary
        assert all(term in owner["driverMeaningReadOnly"][slot] for term in ("collision", "PNG", "runtime_geometry"))
        coverage = packets[i]["spritePresentationReadOnly"]["geometryCoverage"]
        assert all(term in coverage for term in ("texturedPath", "not yet authored", "no_asset", "no automatic", "physical"))
    for i, vocabulary_key, surface_key in ((2, "runtimeVocabulary", "runtimeSurface"), (3, "runtimeVocabularyReadOnly", "runtimeSurfaceReadOnly")):
        vocabulary = packets[i][vocabulary_key]
        semantics = vocabulary["rendererSemantics"]["texturedPath"]
        assert all(term.lower() in semantics.lower() for term in ("baked_sprite", "single PNG", "curve", "physical", "not automatic")), semantics
        assert source in next(r["sources"] for r in packets[i][surface_key]["texturedPathSources"] if r["entityId"] == entity["id"])
        mechanics = copy.deepcopy(projected["runtimeProgram"])
        for e in mechanics["entities"]:
            e.pop("visual", None)
        assert packets[i]["acceptedRuntimeProgramReadOnly"] == mechanics
        assert packets[i]["acceptedVisualKitReadOnly" if i == 3 else "acceptedVisualKit"] == accepted
    for request in requests:
        assert request["response_format"]["type"] == format_mode
    # Rebuild a genuine accepted parameter variant: stable prefix, changed exact facts.
    variant = build_capability_witness(capability)
    next(c for c in variant["runtimeProgram"]["calls"] if c["fn"] == capability)["params"]["rangeTiles"] = 3.0
    variant = compile_runtime_program(variant)
    variant_before = copy.deepcopy(variant)
    responses.append({})
    visual._request_visual_kit(variant, {}, {}, {}, {})
    variant_request = requests[-1]
    prefix_chars = requests[0]["_infini_prompt_cache"]["prefixChars"]
    assert variant_request["messages"][1]["content"][:prefix_chars] == requests[0]["messages"][1]["content"][:prefix_chars]
    variant_packet = json.loads(variant_request["messages"][1]["content"])
    variant_owner = next(r for r in variant_packet["runtimeEntities"] if r["id"] == entity["id"])
    assert variant_owner[slot]["params"]["rangeTiles"] == 3.0
    assert variant_owner[slot] != entity[slot]
    assert variant == variant_before
