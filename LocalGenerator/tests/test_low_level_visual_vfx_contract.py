from __future__ import annotations

import copy

from infini_local.core.runtime_authoring import (
    compile_runtime_program,
    runtime_event_inventory,
    runtime_visual_roles,
    validate_runtime_wire,
)
from infini_local.core.vfx_manifest import (
    VFX_DIRECTOR_SCHEMA,
    attach_hybrid_vfx_manifest,
    validate_vfx_director_output,
    vfx_director_surface,
)
from infini_local.pipelines.visual_generation_pipeline import _validate_kit
from infini_local.pipelines.visual_asset_plan import (
    apply_visual_asset_runtime_gates,
    build_visual_asset_plan,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def test_visual_roles_are_exact_runtime_entity_ids_not_family_roles() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("held_and_deployed"))
    roles = runtime_visual_roles(compiled)
    ids = {row["entityId"] for row in roles}
    assert ids == {row["id"] for row in compiled["runtimeProgram"]["entities"]}
    assert {row["visualRole"] for row in roles} >= {"inventory_item", "held_body", "deployed_entity", "child_projectile"}
    assert all("family" not in key.lower() for row in roles for key in row)


def test_visual_requires_exact_entity_rows_and_item_png() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    ids = [row["id"] for row in compiled["runtimeProgram"]["entities"]]
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    bad = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": {"prompt": "x", "negativePrompt": "", "silhouette": "x", "visualIdentity": "x", "palette": ["x"], "preferredCanvasSize": 32, "inventoryScale": 1.0, "worldScale": 1.0},
        "entities": [{"entityId": item_id, "assetMode": "no_asset", "prompt": "x", "silhouette": "x", "visualIdentity": "x", "scale": 1.0}],
        "animationPlan": "x",
    }
    kit, errors = _validate_kit(bad, ids, item_id)
    assert kit is None
    assert any("must use baked_sprite" in row["message"] for row in errors)
    assert any("missing entity rows" in row["message"] for row in errors)


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


def test_vfx_rejects_nonexistent_entity_event_pair() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("returning_potion"))
    surface = vfx_director_surface(compiled)
    assert surface["runtimePairs"]
    raw = {
        "schema": VFX_DIRECTOR_SCHEMA, "effectMagnitude": 0.5, "visualBudgetClass": "normal",
        "motif": {"element": "glass", "shapeLanguage": "splash", "motionLanguage": "arc", "paletteRole": "accent", "rhythm": 1.0, "chaos": 0.2},
        "slots": [{
            "id": "bad", "entityId": "not_real", "event": "on_hit", "rendererKind": "impactRing",
            "backend": "Realtime", "textureRole": "none", "particleRole": "none", "anchor": "hitPoint",
            "channel": "impactShape", "lane": "primary", "emissionMode": "burst", "blend": "additive",
            "particleSystemId": "none", "scale": 1.0, "density": 0.5, "duration": 20, "alpha": 0.8,
            "spread": 0.2, "jitter": 0.1, "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0,
            "signatureWeight": 0.5, "visualCost": 0.5, "startTick": 0, "repeatEvery": 0,
        }],
    }
    report = validate_vfx_director_output(raw, compiled)
    assert report["ok"] is False
    assert any("absent from runtimeProgram" in row["message"] for row in report["errors"])


def test_visual_entity_to_runtime_pair_to_final_vfx_manifest_closure() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("held_and_deployed"))
    entity_ids = [row["id"] for row in compiled["runtimeProgram"]["entities"]]
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    raw_kit = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": {
            "prompt": "literal lantern pike inventory item",
            "negativePrompt": "",
            "silhouette": "readable pike and lantern",
            "visualIdentity": "lantern pike",
            "palette": ["steel", "amber"],
            "preferredCanvasSize": 32,
            "inventoryScale": 1.0,
            "worldScale": 1.0,
        },
        "entities": [
            {
                "entityId": entity_id,
                "assetMode": "baked_sprite" if entity_id == item_id else "reuse_item_icon",
                "prompt": f"literal {entity_id}",
                "silhouette": entity_id,
                "visualIdentity": entity_id,
                "scale": 1.0,
            }
            for entity_id in entity_ids
        ],
        "animationPlan": "Follow the exact authored runtime entities.",
    }
    kit, kit_errors = _validate_kit(raw_kit, entity_ids, item_id)
    assert kit_errors == []
    assert kit is not None
    assert {row["entityId"] for row in kit["entities"]} == set(entity_ids)
    compiled["visualKit"] = kit

    pair = vfx_director_surface(compiled)["runtimePairs"][0]
    raw_vfx = {
        "schema": VFX_DIRECTOR_SCHEMA,
        "effectMagnitude": 0.5,
        "visualBudgetClass": "normal",
        "motif": {
            "element": "lantern",
            "shapeLanguage": "sparks",
            "motionLanguage": "short wake",
            "paletteRole": "accent",
            "rhythm": 1.0,
            "chaos": 0.2,
        },
        "slots": [{
            "id": "closure_slot",
            "entityId": pair["entityId"],
            "event": pair["event"],
            "rendererKind": "projectileAfterimage",
            "backend": "Realtime",
            "textureRole": "entity",
            "particleRole": "none",
            "anchor": "self",
            "channel": "motionTrail",
            "lane": "primary",
            "emissionMode": "wake",
            "blend": "alpha",
            "particleSystemId": "none",
            "scale": 1.0,
            "density": 0.4,
            "duration": 20,
            "alpha": 0.8,
            "spread": 0.1,
            "jitter": 0.1,
            "fadeIn": 0.1,
            "fadeOut": 0.4,
            "budgetWeight": 1.0,
            "signatureWeight": 0.5,
            "visualCost": 0.5,
            "startTick": 0,
            "repeatEvery": 0,
        }],
    }
    assert validate_vfx_director_output(raw_vfx, compiled)["ok"] is True
    final = attach_hybrid_vfx_manifest(
        compiled,
        "lantern pike",
        llm_director=lambda *_args, **_kwargs: copy.deepcopy(raw_vfx),
    )
    slot = final["vfxManifest"]["slots"][0]
    assert (slot["entityId"], slot["event"]) == (pair["entityId"], pair["event"])
