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
from test_low_level_three_stage_pipeline import _visual_kit, _accepted_visual_data, _vfx_output


def kit() -> dict[str, Any]:
    """Small opaque-ID fixture also consumed by the exact Repair-location contracts."""
    item = dict(prompt="object", negativePrompt="", silhouette="object", visualIdentity="object", palette=["red"], preferredCanvasSize=32, inventoryScale=1.0, worldScale=1.0)
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
