"""Authored presentation, exact runtime ownership and representative refusals."""
from __future__ import annotations

import copy

import pytest

from prompt_packet_helpers import request_dossier
from infini_local.core import vfx_manifest as vfx
from infini_local.core.runtime_authoring import compile_runtime_program, validate_runtime_wire
from infini_local.pipelines import llm_authoring_pipeline as stage
from infini_local.pipelines import visual_generation_pipeline as visual
from infini_local.pipelines.image_backend_pipeline import comfyui_mapping
from infini_local.pipelines.visual_asset_plan import apply_visual_asset_runtime_gates, build_visual_asset_plan
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.storage.world_storage import sanitize_recipe_for_delivery
from test_low_level_three_stage_pipeline import _accepted_visual_data, _visual_kit, _vfx_output, wire_transport


def kit() -> dict:
    """Opaque-ID input retained for adjacent exact Repair-location scenarios."""
    item = dict(prompt="object", negativePrompt="", silhouette="object", visualIdentity="object", palette=["red"], preferredCanvasSize=32, renderSizePx=40, forwardAngleDegrees=45, inventoryScale=1.0, worldScale=1.0)
    return dict(schema=visual.VISUAL_KIT_SCHEMA, item=item, equipOverlay=dict(prompt="badge", silhouette="badge", visualIdentity="badge", preferredCanvasSize=32), entities=[dict(entityId="opaque_id", assetMode="baked_sprite", visualProjectRef="item", scale=1.0)], animationPlan="unchanged")


def test_director_projects_root_and_distinct_art_without_changing_mechanics(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    before = copy.deepcopy(data)
    raw = _visual_kit(data)
    raw["item"].update(preferredCanvasSize=96, renderSizePx=40, forwardAngleDegrees=45,
                       grip={"normalizedX": 0.25, "normalizedY": 0.75}, effectColor="gold",
                       palette=["copper and verdigris"], negativePrompt="")
    body = next(row for row in raw["entities"] if row["entityId"] == "chained_door")
    body.update(assetMode="baked_sprite", visualProjectRef="entity", prompt="independent door",
                silhouette="rectangular door", visualIdentity="bronze door", preferredCanvasSize=64,
                renderSizePx=48, forwardAngleDegrees=-30)
    responses, requests = wire_transport
    responses.append(raw)
    projected = visual.apply_visual_director(data, {}, {}, {}, {})
    plan = {row["entityId"]: row for row in build_visual_asset_plan(projected)}
    assert (plan["item"]["canvas"], plan["item"]["renderSizePx"], plan["item"]["forwardAngleDegrees"]) == (96, 40, 45)
    assert (plan["chained_door"]["canvas"], plan["chained_door"]["renderSizePx"], plan["chained_door"]["forwardAngleDegrees"]) == (64, 48, -30)
    assert plan["chained_door"]["prompt"] == "independent door"
    delivered = sanitize_recipe_for_delivery(projected)
    assert validate_runtime_wire(delivered)["ok"]
    assert "visualKit" not in delivered
    assert delivered["visual"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
    assert delivered["visual"]["effectColor"] == "gold"
    assert delivered["visual"]["palette"] == ["copper and verdigris"]
    assert comfyui_mapping("literal item", delivered["visual"]["negativePrompt"], "exact", seed=123)["{{NEGATIVE_PROMPT}}"] == ""
    entities = {row["id"]: row for row in delivered["runtimeProgram"]["entities"]}
    assert entities["chained_door"]["visual"]["renderSizePx"] == 48
    assert "renderSizePx" not in entities["item"]["visual"]
    assert "grip" not in entities["chained_door"]["visual"]
    assert all("runtimeGateReason" not in row["visual"] for row in entities.values())
    assert delivered["gameplay"] == before["gameplay"]
    mechanics = copy.deepcopy(delivered["runtimeProgram"])
    for row in mechanics["entities"]:
        row["visual"] = next(old["visual"] for old in before["runtimeProgram"]["entities"] if old["id"] == row["id"])
    assert mechanics == before["runtimeProgram"]
    assert len(requests) == 1 and not responses
    assert projected["debug"]["llmStageAccounting"]["visualRepairCalls"] == 0


def test_item_body_references_root_visual_project_without_duplicate_design(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    body = next(row for row in raw["entities"] if row["entityId"] == "item")
    for field in ("prompt", "silhouette", "visualIdentity"):
        body.pop(field, None)
    root_before = copy.deepcopy(raw["item"])
    responses, requests = wire_transport
    responses.append(raw)

    projected = visual.apply_visual_director(data, {}, {}, {}, {})

    assert projected["visualKit"]["item"] == root_before
    accepted_body = next(row for row in projected["visualKit"]["entities"] if row["entityId"] == "item")
    assert accepted_body == {"entityId": "item", "assetMode": "baked_sprite", "visualProjectRef": "item", "scale": 1.0}
    runtime_body = next(row for row in projected["runtimeProgram"]["entities"] if row["id"] == "item")
    assert runtime_body["visual"]["prompt"] == root_before["prompt"]
    plan = next(row for row in build_visual_asset_plan(projected) if row["role"] == "item")
    assert plan["prompt"] == root_before["prompt"]
    assert len(requests) == 1 and not responses
    assert projected["debug"]["llmStageAccounting"]["visualRepairCalls"] == 0


@pytest.mark.parametrize("field", ["prompt", "silhouette", "visualIdentity"])
def test_root_design_repair_does_not_open_entity_permissions(wire_transport, field):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    raw["item"][field] = ""
    entities_before = copy.deepcopy(raw["entities"])
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                 itemPatch={field: "repaired root design"}, entitiesUpsert=[],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="root leaf only")
    responses, requests = wire_transport
    responses.extend([raw, patch])

    result = visual.apply_visual_director(data, {}, {}, {}, {})

    assert result["visualKit"]["item"][field] == "repaired root design"
    assert result["visualKit"]["entities"] == entities_before
    scope = request_dossier(requests[1])["repairScope"]
    assert scope["fieldPermissions"]["itemPaths"] == [field]
    assert scope["fieldPermissions"]["entities"] == []
    assert scope["mutableEntityIds"] == []
    assert len(requests) == 2 and not responses


@pytest.mark.parametrize("field", ["prompt", "silhouette", "visualIdentity"])
def test_fresh_item_body_cannot_reintroduce_a_second_design(field):
    raw = kit()
    raw["entities"][0][field] = raw["item"][field]
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(row["path"] == f"$.entities[0].{field}" for row in errors)


def test_repair_removes_only_forbidden_body_copies_without_reauthoring_root(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    reference = copy.deepcopy(raw["entities"][0])
    raw["entities"][0].update({field: raw["item"][field] for field in ("prompt", "silhouette", "visualIdentity")})
    root_before = copy.deepcopy(raw["item"])
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                 itemPatch={"prompt": "unrequested root rewrite"}, entitiesUpsert=[reference],
                 entityIdsDelete=[], entityIndicesDelete=[], animationPlan=None, note="remove duplicate leaves only")
    responses, requests = wire_transport
    responses.extend([raw, patch])

    result = visual.apply_visual_director(data, {}, {}, {}, {})

    assert result["visualKit"]["item"] == root_before
    assert result["visualKit"]["entities"][0] == reference
    assert result["visualKit"]["entities"][1] == raw["entities"][1]
    scope = request_dossier(requests[1])["repairScope"]
    assert scope["fieldPermissions"]["itemPaths"] == []
    assert scope["fieldPermissions"]["entities"] == [{"entityId": "item", "paths": ["prompt", "silhouette", "visualIdentity"]}]
    assert result["debug"]["visualRepairFilterAudit"]["ignoredChanges"]
    assert len(requests) == 2 and not responses


def test_descriptive_palette_survives_director_and_delivery_without_repair(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    description = "Oxidized copper with blue-green recesses and pale silver highlights; " + "restrained readable facets " * 3
    raw["item"]["palette"] = [description]
    responses, requests = wire_transport
    responses.append(raw)
    projected = visual.apply_visual_director(data, {}, {}, {}, {})
    assert projected["visual"]["palette"] == [description]
    assert sanitize_recipe_for_delivery(projected)["visual"]["palette"] == [description]
    assert len(requests) == 1 and not responses
    assert projected["debug"]["llmStageAccounting"]["visualRepairCalls"] == 0


def test_equipment_overlay_keeps_authored_mount_and_single_badge_plan(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("equipment_tool_combat"))
    before = copy.deepcopy(data)
    raw = _visual_kit(data)
    raw["equipOverlay"] = dict(kit()["equipOverlay"], accessoryMount="back")
    responses, _ = wire_transport
    responses.append(raw)
    projected = visual.apply_visual_director(data, {}, {}, {}, {})
    badge = next(row for row in build_visual_asset_plan(projected) if row["role"] == "equip_overlay")
    assert (badge["entityId"], badge["canvas"], badge["prompt"], badge["equipmentSlot"]) == ("item", 32, "badge", "accessory")
    assert sanitize_recipe_for_delivery(projected)["visual"]["accessoryMount"] == "back"
    assert projected["gameplay"] == before["gameplay"] and projected["accessory"] == before["accessory"]


@pytest.mark.parametrize("container,field,value", [
    pytest.param("item", "effectColor", None, id="present-color-null"),
    pytest.param("item", "effectColor", True, id="color-wrong-type"),
    pytest.param("item", "effectColor", "verdigris", id="color-not-prose"),
    pytest.param("equipOverlay", "accessoryMount", {}, id="mount-wrong-type"),
    pytest.param("equipOverlay", "accessoryMount", "wing", id="mount-unknown"),
    pytest.param("item", "grip", [], id="grip-not-object"),
    pytest.param("item", "grip", {"normalizedX": 0.25}, id="grip-incomplete"),
    pytest.param("item", "grip", {"normalizedX": 0.25, "normalizedY": 1.1}, id="grip-out-of-range"),
])
def test_present_metadata_refuses_representative_bad_inputs(container, field, value):
    raw = kit()
    raw[container][field] = value
    before = copy.deepcopy(raw)
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(row["path"].startswith(f"$.{container}.{field}") for row in errors)
    assert raw == before


@pytest.mark.parametrize("bad_field,value,path", [
    pytest.param("entityId", "outside_runtime", "$.entities[0].entityId", id="outside-runtime-id"),
    pytest.param("assetMode", "invented", "$.entities[0].assetMode", id="unknown-asset-mode"),
    pytest.param("renderSizePx", None, "$.item.renderSizePx", id="required-size-null"),
    pytest.param("forwardAngleDegrees", 181, "$.item.forwardAngleDegrees", id="axis-out-of-range"),
])
def test_visual_admission_does_not_invent_identity_or_presentation(bad_field, value, path):
    raw = kit()
    target = raw["entities"][0] if bad_field in {"entityId", "assetMode"} else raw["item"]
    target[bad_field] = value
    before = copy.deepcopy(raw)
    accepted, errors = visual._validate_kit(raw, ["opaque_id"], "opaque_id", equipment_overlay_required=True)
    assert accepted is None and any(row["path"] == path for row in errors)
    assert raw == before


@pytest.mark.parametrize("repair_grip", [pytest.param(True, id="bad-y-frozen-x"), pytest.param(False, id="unrelated-repair-preserves-absence")])
def test_scoped_visual_repair_preserves_good_siblings_absence_and_mechanics(wire_transport, repair_grip):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    before = copy.deepcopy(data)
    raw = _visual_kit(data)
    if repair_grip:
        raw["item"]["grip"] = {"normalizedX": 0.25, "normalizedY": 2}
    else:
        raw["item"]["inventoryScale"] = 99
    raw_before = copy.deepcopy(raw)
    hostile_entity = dict(raw["entities"][1], scale=4)
    patch = dict(schema=visual.VISUAL_REPAIR_PATCH_SCHEMA,
                 itemPatch={"grip": {"normalizedX": 0.9, "normalizedY": 0.75}, "inventoryScale": 2,
                            "effectColor": "pink", "prompt": "unrequested replacement"},
                 entitiesUpsert=[hostile_entity], entityIdsDelete=["chained_door"], entityIndicesDelete=[],
                 animationPlan="unrequested animation", note="repair only the bad leaf")
    responses, requests = wire_transport
    responses.extend([raw, patch])
    result = visual.apply_visual_director(data, {}, {}, {}, {})
    repaired = result["visualKit"]
    if repair_grip:
        assert repaired["item"]["grip"] == {"normalizedX": 0.25, "normalizedY": 0.75}
        assert repaired["item"]["inventoryScale"] == 1.0
    else:
        assert repaired["item"]["inventoryScale"] == 2
        assert "grip" not in repaired["item"] and "grip" not in result["visual"]
    assert "effectColor" not in repaired["item"] and "accessoryMount" not in result["visual"]
    assert repaired["item"]["prompt"] == "literal Terraria item"
    assert repaired["entities"] == raw_before["entities"]
    assert repaired["animationPlan"] == raw_before["animationPlan"]
    assert result["gameplay"] == before["gameplay"]
    assert result["runtimeProgram"]["itemUse"] == before["runtimeProgram"]["itemUse"]
    assert next(row for row in result["runtimeProgram"]["entities"] if row["id"] == "chained_door")["movement"] == before["runtimeProgram"]["entities"][1]["movement"]
    assert validate_runtime_wire(sanitize_recipe_for_delivery(result))["ok"]
    assert result["debug"]["visualRepairFilterAudit"]["ignoredChanges"]
    scope = request_dossier(requests[1])["repairScope"]
    assert scope["fieldPermissions"]["itemPaths"] == (["grip.normalizedY"] if repair_grip else ["inventoryScale"])
    assert scope["fieldPermissions"]["entities"] == []
    assert [request["_infini_stage"] for request in requests] == ["visual_director", "visual_repair"]
    assert not responses and raw == raw_before


@pytest.mark.parametrize("design,accepted", [
    pytest.param("complete", True, id="complete-design-only-mode-missing"),
    pytest.param("incomplete", False, id="no-design-invention"),
    pytest.param("explicit-no-asset", False, id="cannot-replace-explicit-choice"),
])
def test_item_png_fix_requires_complete_authored_design(design, accepted):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    row = next(row for row in raw["entities"] if row["entityId"] == "item")
    row.pop("assetMode")
    if design == "incomplete":
        raw["item"]["prompt"] = ""
    elif design == "explicit-no-asset":
        row["assetMode"] = "no_asset"
    result, errors = visual._validate_kit(raw, ["item", "chained_door"], "item")
    assert (result is not None) is accepted, errors
    # The ordinary projector resolves root art before runtime-gate admission;
    # the thin model row is not itself a delivered runtime visual DTO.
    data = visual._apply_kit(data, result if result is not None else raw)
    if "assetMode" not in row:
        body = next(entity for entity in data["runtimeProgram"]["entities"] if entity["id"] == "item")
        body["visual"].pop("assetMode", None)
    apply_visual_asset_runtime_gates(data, {})
    item = next(row for row in data["runtimeProgram"]["entities"] if row["id"] == "item")
    assert item["visual"]["assetMode"] == ("baked_sprite" if accepted else "")
    if accepted:
        plan = next(row for row in build_visual_asset_plan(data) if row["role"] == "item")
        assert plan["runtimeGateReason"] == "fix:item_body_baked_sprite_from_complete_visual_design"
        assert data["debug"]["visualAssetFixes"][0]["entityId"] == "item"
    else:
        assert not data.get("debug", {}).get("visualAssetFixes")


@pytest.mark.parametrize("values,path", [
    pytest.param({"renderSizePx": True}, "$.visual.renderSizePx", id="wire-size-type"),
    pytest.param({"forwardAngleDegrees": 181}, "$.visual.forwardAngleDegrees", id="wire-axis-bound"),
    pytest.param({"renderSizePx": 32}, "$.runtimeProgram.entities[1].visual.renderSizePx", id="nonowning-reused-sprite"),
])
def test_wire_refuses_malformed_or_nonowning_presentation(values, path):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    target = data.setdefault("visual", {})
    if "entities" in path:
        target = data["runtimeProgram"]["entities"][1]["visual"]
        target["assetMode"] = "reuse_item_icon"
    target.update(values)
    report = validate_runtime_wire(data)
    assert not report["ok"] and any(row["path"] == path for row in report["errors"])


def test_legacy_absence_remains_absent_and_fresh_director_clears_stale_metadata():
    legacy = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    assert validate_runtime_wire(legacy)["ok"]
    delivered = sanitize_recipe_for_delivery(legacy)
    assert all(field not in delivered.get("visual", {}) for field in ("renderSizePx", "grip", "effectColor", "accessoryMount"))
    legacy["visual"] = {"grip": {"normalizedX": 0, "normalizedY": 0}, "effectColor": "red", "accessoryMount": "chest"}
    projected = visual._apply_kit(legacy, _visual_kit(legacy))
    assert all(field not in projected["visual"] for field in ("grip", "effectColor", "accessoryMount"))


def test_vfx_consumes_visual_color_and_exact_impact_binding_without_prose_or_audio_inference(wire_transport):
    data = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    raw = _visual_kit(data)
    raw["item"].update(effectColor="cyan", palette=["dark blue copper"], grip={"normalizedX": 0.25, "normalizedY": 0.75})
    data = visual._apply_kit(data, raw)
    before = copy.deepcopy(data)
    authored = _vfx_output(data)
    authored["slots"][0].update(id="door_impact", entityId="chained_door", event="on_hit", rendererKind="impactSprite",
                                backend="Sprite", textureRole="impact", anchor="hitPoint", channel="impactShape",
                                emissionMode="burst", layer="AfterProjectiles", spritePrompt="literal door impact", spriteNegativePrompt="")
    responses, requests = wire_transport
    responses.append(authored)
    final = vfx.attach_hybrid_vfx_manifest(data, "door-impact", llm_director=stage.call_llm_vfx_director)
    packet = request_dossier(requests[0])
    assert packet["acceptedVisualKit"]["item"]["effectColor"] == "cyan"
    assert {("chained_door", "on_hit"), ("item", "on_use")}.issubset({(row["entityId"], row["event"]) for row in packet["runtimeSurface"]["runtimePairs"]})
    assert final["visual"]["effectColor"] == "cyan" and final["visual"]["palette"] == ["dark blue copper"]
    slot, = final["vfxManifest"]["slots"]
    assert (slot["entityId"], slot["event"], slot["layer"]) == ("chained_door", "on_hit", "AfterProjectiles")
    assert "sound" not in slot and "soundId" not in slot and "spritePrompt" not in slot
    impact = next(row for row in build_visual_asset_plan(final) if row["role"] == "impact:chained_door")
    assert impact["prompt"] == "literal door impact" and impact["negativePrompt"] == ""
    assert final["gameplay"] == before["gameplay"]
    assert final["runtimeProgram"]["entities"][1]["movement"] == before["runtimeProgram"]["entities"][1]["movement"]
    assert vfx.validate_vfx_manifest_wire(sanitize_recipe_for_delivery(final))["ok"]
    assert not responses


@pytest.mark.parametrize("change,path", [
    pytest.param("outside-pair", "$.slots[0]", id="unaccepted-entity-event"),
    pytest.param("extra-field", "inventedStyle", id="unknown-slot-field"),
])
def test_vfx_admission_refuses_outside_runtime_or_unknown_fields(change, path):
    data = _accepted_visual_data("door_on_chain")
    raw = _vfx_output(data)
    if change == "outside-pair":
        raw["slots"][0].update(entityId="outside_runtime", event="on_hit")
    else:
        raw["slots"][0]["inventedStyle"] = "must not be dropped"
    report = vfx.validate_vfx_director_output(raw, data)
    assert not report["ok"] and any(path in row["path"] or path in row["message"] for row in report["errors"])
