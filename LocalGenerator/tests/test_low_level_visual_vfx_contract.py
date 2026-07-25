from __future__ import annotations

import copy

from infini_local.core.runtime_authoring import compile_runtime_program, runtime_event_inventory, runtime_visual_roles
from infini_local.core.vfx_manifest import VFX_DIRECTOR_SCHEMA, validate_vfx_director_output, vfx_director_surface
from infini_local.pipelines.visual_generation_pipeline import _validate_kit
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
