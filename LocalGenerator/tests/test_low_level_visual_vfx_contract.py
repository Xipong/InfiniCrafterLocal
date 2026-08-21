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
from infini_local.pipelines.image_backend_pipeline import comfyui_mapping
from infini_local.pipelines.visual_generation_pipeline import (
    VISUAL_REPAIR_PATCH_SCHEMA,
    _apply_visual_repair_patch,
    _build_visual_repair_scope,
    _validate_kit,
)
from infini_local.pipelines.visual_asset_plan import (
    apply_visual_asset_runtime_gates,
    build_visual_asset_plan,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture
from infini_local.qa.capability_witnesses import build_capability_witness


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


def test_visual_requires_exact_entity_rows_and_item_png() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    ids = [row["id"] for row in compiled["runtimeProgram"]["entities"]]
    item_id = compiled["runtimeProgram"]["itemEntityId"]
    bad = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": {"prompt": "x", "negativePrompt": "", "silhouette": "x", "visualIdentity": "x", "palette": ["x"], "preferredCanvasSize": 32, "inventoryScale": 1.0, "worldScale": 1.0},
        "entities": [{"entityId": item_id, "assetMode": "no_asset", "prompt": "x", "silhouette": "x", "visualIdentity": "x", "impactPrompt": "x impact", "impactNegativePrompt": "", "scale": 1.0}],
        "animationPlan": "x",
    }
    kit, errors = _validate_kit(bad, ids, item_id)
    assert kit is None
    assert any("must use baked_sprite" in row["message"] for row in errors)
    assert any("missing entity rows" in row["message"] for row in errors)

    fixable = copy.deepcopy(bad)
    fixable["entities"] = [
        ({
            "entityId": entity_id,
            "prompt": "x", "silhouette": "x", "visualIdentity": "x",
            "scale": 1.0,
        } if entity_id == item_id else {
            "entityId": entity_id, "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0,
        })
        for entity_id in ids
    ]
    kit, errors = _validate_kit(fixable, ids, item_id)
    assert kit is not None, errors

    non_item = next(row for row in fixable["entities"] if row["entityId"] != item_id)
    non_item.pop("assetMode")
    kit, errors = _validate_kit(fixable, ids, item_id)
    assert kit is None
    assert any(row["path"].endswith(".assetMode") for row in errors)


def test_visual_repair_deletes_exact_unknown_item_property() -> None:
    item = {
        "prompt": "wooden blade with a literal workbench guard",
        "negativePrompt": "",
        "silhouette": "broad blade and square guard",
        "visualIdentity": "carpentry sword",
        "palette": ["brown", "steel"],
        ":palette": ["invalid duplicate key"],
        "preferredCanvasSize": 32,
        "inventoryScale": 1.0,
        "worldScale": 1.0,
    }
    entity = {
        "entityId": "item",
        "assetMode": "baked_sprite",
        "visualProjectRef": "item",
        "prompt": item["prompt"],
        "silhouette": item["silhouette"],
        "visualIdentity": "carpentry sword",
        "scale": 1.0,
        ":scale": 2.0,
    }
    previous = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": item,
        "entities": [entity],
        "animationPlan": "static inventory sprite",
    }
    errors = [
        {
            "path": "$.item.:palette",
            "code": "schema_additional_property",
            "message": "additional property ':palette' is not allowed",
        },
        {
            "path": "$.entities[0].:scale",
            "code": "schema_additional_property",
            "message": "additional property ':scale' is not allowed",
        },
    ]
    scope = _build_visual_repair_scope(previous, errors, ["item"], "item")
    patch = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": {key: copy.deepcopy(value) for key, value in item.items() if key != ":palette"},
        "entitiesUpsert": [{key: copy.deepcopy(value) for key, value in entity.items() if key != ":scale"}],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "animationPlan": None,
        "note": "remove invalid duplicate palette key",
    }

    repaired, audit = _apply_visual_repair_patch(
        previous,
        patch,
        scope,
        ["item"],
        return_audit=True,
    )

    assert audit["ok"], audit
    assert ":palette" not in repaired["item"]
    assert repaired["item"]["palette"] == ["brown", "steel"]
    assert ":scale" not in repaired["entities"][0]
    assert repaired["entities"][0]["scale"] == 1.0
    kit, validation_errors = _validate_kit(repaired, ["item"], "item")
    assert kit is not None, validation_errors


def test_visual_repair_accepts_partial_item_patch_and_freezes_valid_fields() -> None:
    item = {
        "prompt": "broken prompt",
        "negativePrompt": "placeholder",
        "silhouette": "broad blade",
        "visualIdentity": "carpentry sword",
        "palette": ["brown"],
        "preferredCanvasSize": 32,
        "inventoryScale": 1.0,
        "worldScale": 1.0,
    }
    previous = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": item,
        "entities": [{
            "entityId": "item",
            "assetMode": "baked_sprite",
            "visualProjectRef": "item",
            "prompt": "broken prompt",
            "silhouette": "broad blade",
            "visualIdentity": "carpentry sword",
            "scale": 1.0,
        }],
        "animationPlan": "static inventory sprite",
    }
    errors = [
        {
            "path": "$.item.prompt",
            "code": "schema_min_length",
            "message": "prompt is empty or invalid",
        },
    ]
    scope = _build_visual_repair_scope(previous, errors, ["item"], "item")
    # The model returns ONLY the broken field; everything else stays frozen.
    patch = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": {"prompt": "wooden blade with a literal workbench guard"},
        "entitiesUpsert": [{
            "entityId": "item",
            "assetMode": "baked_sprite",
            "visualProjectRef": "item",
            "prompt": "wooden blade with a literal workbench guard",
            "silhouette": "broad blade",
            "visualIdentity": "carpentry sword",
            "scale": 1.0,
        }],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "animationPlan": None,
        "note": "repair the prompt in both visual project copies",
    }
    repaired, audit = _apply_visual_repair_patch(
        previous,
        patch,
        scope,
        ["item"],
        return_audit=True,
    )
    assert audit["ok"], audit
    assert repaired["item"]["prompt"] == "wooden blade with a literal workbench guard"
    assert repaired["item"]["silhouette"] == item["silhouette"]
    assert repaired["item"]["palette"] == ["brown"]
    kit, validation_errors = _validate_kit(repaired, ["item"], "item")
    assert kit is not None, validation_errors


def test_visual_repair_atomically_replaces_one_unknown_row_with_one_missing_entity() -> None:
    entity_ids = ["item_body", "whip_projectile", "spore_particle"]

    def entity(entity_id: str) -> dict[str, object]:
        is_item = entity_id == "item_body"
        return {
            "entityId": entity_id,
            "assetMode": "baked_sprite",
            "visualProjectRef": "item" if is_item else "entity",
            "prompt": "thorn whip item" if is_item else f"pixel art {entity_id}",
            "silhouette": "coiled thorn whip" if is_item else f"silhouette {entity_id}",
            "visualIdentity": "jungle thorn whip" if is_item else f"identity {entity_id}",
            "scale": 1.0,
        }

    previous = {
        "schema": "infini.visual-kit.runtime-entities.v1",
        "item": {
            "prompt": "thorn whip item",
            "negativePrompt": "text, watermark",
            "silhouette": "coiled thorn whip",
            "visualIdentity": "jungle thorn whip",
            "palette": ["green", "brown"],
            "preferredCanvasSize": 32,
            "inventoryScale": 1.0,
            "worldScale": 1.0,
        },
        "entities": [
            entity("item_handle"),
            entity("whip_projectile"),
            entity("spore_particle"),
        ],
        "animationPlan": "whip attack animation",
    }
    _kit, errors = _validate_kit(previous, entity_ids, "item_body")
    assert _kit is None
    scope = _build_visual_repair_scope(previous, errors, entity_ids, "item_body")
    assert scope["entityReplacementTransactions"] == [
        {"entityId": "item_body", "replaceIndex": 0}
    ]
    patch = {
        "schema": VISUAL_REPAIR_PATCH_SCHEMA,
        "itemPatch": None,
        "entitiesUpsert": [entity("item_body")],
        "entityIdsDelete": [],
        "entityIndicesDelete": [],
        "animationPlan": None,
        "note": "replace the exact invalid row with the missing canonical row",
    }

    repaired, audit = _apply_visual_repair_patch(
        previous,
        patch,
        scope,
        entity_ids,
        return_audit=True,
    )

    assert audit["ok"], audit
    assert [row["entityId"] for row in repaired["entities"]] == [
        "whip_projectile", "spore_particle", "item_body"
    ]
    assert 0 in audit["filteredPatch"]["entityIndicesDelete"]
    kit, validation_errors = _validate_kit(repaired, entity_ids, "item_body")
    assert kit is not None, validation_errors


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


def test_item_asset_mode_fix_requires_complete_visual_design() -> None:
    compiled = compile_runtime_program(build_runtime_fixture("door_on_chain"))
    item_entity = next(
        entity for entity in compiled["runtimeProgram"]["entities"] if entity["kind"] == "item_body"
    )
    for entity in compiled["runtimeProgram"]["entities"]:
        visual = entity.setdefault("visual", {})
        if entity["kind"] == "item_body":
            visual.update({
                "prompt": "complete item prompt",
                "silhouette": "complete silhouette",
                "visualIdentity": "complete identity",
            })
            visual.pop("assetMode", None)
        else:
            visual["assetMode"] = "reuse_item_icon"

    missing_design = copy.deepcopy(compiled)
    missing_item = next(
        entity for entity in missing_design["runtimeProgram"]["entities"] if entity["kind"] == "item_body"
    )
    missing_item["visual"]["prompt"] = ""
    apply_visual_asset_runtime_gates(missing_design, {})
    missing_row = next(row for row in build_visual_asset_plan(missing_design) if row["role"] == "item")
    assert missing_row["assetMode"] == ""
    assert missing_row["runtimeGateReason"] == "invalid_or_missing_authored_asset_mode"
    assert not missing_design.get("debug", {}).get("visualAssetFixes")

    apply_visual_asset_runtime_gates(compiled, {})
    item_row = next(row for row in build_visual_asset_plan(compiled) if row["role"] == "item")
    assert item_entity["visual"]["assetMode"] == "baked_sprite"
    assert item_row["runtimeGateReason"] == "fix:item_body_baked_sprite_from_complete_visual_design"
    assert compiled["debug"]["visualAssetFixes"] == [{
        "entityId": item_entity["id"],
        "field": "assetMode",
        "value": "baked_sprite",
        "reason": "fix:item_body_baked_sprite_from_complete_visual_design",
    }]

    explicit_wrong_mode = copy.deepcopy(compiled)
    explicit_item = next(
        entity for entity in explicit_wrong_mode["runtimeProgram"]["entities"] if entity["kind"] == "item_body"
    )
    explicit_item["visual"]["assetMode"] = "no_asset"
    apply_visual_asset_runtime_gates(explicit_wrong_mode, {})
    assert explicit_item["visual"]["assetMode"] == ""


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
            "layer": "AfterProjectiles",
            "particleSystemId": "none", "scale": 1.0, "density": 0.5, "duration": 20, "alpha": 0.8,
            "spread": 0.2, "jitter": 0.1, "fadeIn": 0.1, "fadeOut": 0.4, "budgetWeight": 1.0,
            "signatureWeight": 0.5, "visualCost": 0.5, "startTick": 0, "repeatEvery": 0,
        }],
    }
    report = validate_vfx_director_output(raw, compiled)
    assert report["ok"] is False
    assert any("absent from runtimeProgram" in row["message"] for row in report["errors"])

    pair = surface["runtimePairs"][0]
    raw["slots"][0].update({"id": " bad ", "entityId": pair["entityId"], "event": pair["event"]})
    exact_id_report = validate_vfx_director_output(raw, compiled)
    assert exact_id_report["ok"] is False
    assert any(row["path"] == "$.slots[0].id" for row in exact_id_report["errors"])
    assert exact_id_report["normalized"]["slots"][0]["id"] == " bad "

    raw["slots"][0]["id"] = "bad"
    raw["motif"]["element"] = "x" * 49
    exact_motif_report = validate_vfx_director_output(raw, compiled)
    assert exact_motif_report["ok"] is False
    assert any(row["path"] == "$.motif.element" for row in exact_motif_report["errors"])
    assert exact_motif_report["normalized"]["motif"]["element"] == "x" * 49

    raw["motif"]["element"] = "glass"
    raw["slots"][0]["inventedStyle"] = "code must not drop me"
    unknown_report = validate_vfx_director_output(raw, compiled)
    assert unknown_report["ok"] is False
    assert any(
        "inventedStyle" in row["path"] or "inventedStyle" in row["message"]
        for row in unknown_report["errors"]
    )


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
            ({
                "entityId": entity_id, "assetMode": "baked_sprite", "visualProjectRef": "item",
                "prompt": "literal lantern pike inventory item",
                "silhouette": "readable pike and lantern",
                "visualIdentity": "lantern pike", "scale": 1.0,
            } if entity_id == item_id else {
                "entityId": entity_id, "assetMode": "reuse_item_icon", "visualProjectRef": "item", "scale": 1.0,
            })
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
            "layer": "AfterProjectiles",
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
            "spritePrompt": "",
            "spriteNegativePrompt": "",
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
    assert slot["layer"] == "AfterProjectiles"
    assert all(field not in slot for field in ("curve", "importance", "variant"))

    impact_raw = copy.deepcopy(raw_vfx)
    impact_slot = impact_raw["slots"][0]
    impact_slot.update({
        "id": "impact_asset_slot",
        "rendererKind": "impactSprite",
        "backend": "Sprite",
        "textureRole": "impact",
        "anchor": "hitPoint",
        "channel": "impactShape",
        "emissionMode": "burst",
        "spritePrompt": "literal authored lantern impact",
        "spriteNegativePrompt": "text, watermark",
    })
    impact_final = attach_hybrid_vfx_manifest(
        compiled,
        "lantern pike impact",
        llm_director=lambda *_args, **_kwargs: copy.deepcopy(impact_raw),
    )
    compiled_slot = impact_final["vfxManifest"]["slots"][0]
    assert "spritePrompt" not in compiled_slot
    assert "spriteNegativePrompt" not in compiled_slot
    entity = next(
        row for row in impact_final["runtimeProgram"]["entities"]
        if row["id"] == pair["entityId"]
    )
    assert entity["visual"]["impactPrompt"] == "literal authored lantern impact"
    assert entity["visual"]["impactNegativePrompt"] == "text, watermark"
