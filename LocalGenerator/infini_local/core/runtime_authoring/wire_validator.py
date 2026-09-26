from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from infini_local.core.runtime_authoring.binding_use_policy import (
    ACTIVE_USE_INPUTS,
    action,
    action_kind,
    contact_damage,
    placeable_input_contract,
    stack_cost,
    target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    ENTITY_KINDS,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
    VISUAL_ROLE_BY_ENTITY_KIND,
)
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import _has_non_neutral_generated_buff

_MAX_MOVEMENT_CODE = 19
_MAX_CONTROLLER_CODE = 3
_MAX_EVENT_ACTION_CODE = 7
_FORBIDDEN_ROUTER_KEYS = {
    "attack",
    "runtimePlan",
    "runtimeFamily",
    "weaponFamily",
    "projectileFamily",
    "delivery",
    "family",
}

_RUNTIME_KEYS = frozenset({"apiVersion", "schema", "itemEntityId", "primaryEntityId", "primaryOwner", "limits", "entities", "bindings", "itemUse", "itemContact"})
_LIMIT_KEYS = frozenset({"maxEntityCount", "maxChildDepth", "maxEventSpawnsPerActivation"})
_ENTITY_KEYS = frozenset({"id", "kind", "visualRole", "visual", "spawn", "damage", "lifetimeTicks", "hitbox", "collision", "movement", "controller", "targeting", "light", "events"})
_VISUAL_KEYS = frozenset({
    "role", "assetMode", "prompt", "silhouette", "visualIdentity", "impactPrompt", "impactNegativePrompt",
    "scale", "spritePath", "spriteUrl", "spriteStatus", "spriteTechnicalScore", "impactSpritePath",
    "impactSpriteUrl", "impactSpriteStatus", "impactSpriteTechnicalScore",
})
_SPAWN_KEYS = frozenset({"enabled", "speedPxPerTick", "count", "spreadRadians", "offsetPx", "aim", "placement", "overTarget"})
_OVER_TARGET_KEYS = frozenset({"heightTiles", "delayTicks"})
_DAMAGE_KEYS = frozenset({"enabled", "damageClass", "damage", "knockback", "ownerHitCheck"})
_HITBOX_KEYS = frozenset({"widthPx", "heightPx", "drawScale", "hitboxScale"})
_COLLISION_KEYS = frozenset({"tileCollide", "ignoreWater", "bounceCount", "pierce", "extraUpdates", "npcImmunityMode", "localNpcHitCooldownTicks"})
_DRIVER_KEYS = frozenset({"name", "code", "params"})
_PARAMS_KEYS = frozenset({
    "rangeTiles", "homingStrength", "gravityPerTick", "velocityRetention", "returnAfterTicks", "returnSpeed",
    "waveAmplitude", "phaseStrength", "acceleration", "maxSpeed", "turnRadiansPerTick", "pullStrength",
    "proximityRadiusPx", "scalePerTick", "maxScale", "segments", "durationTicks", "widthPx", "warmupTicks",
    "chargeTicks", "powerMultiplier", "shotEntity", "intervalTicks", "sameTargetBias",
})
_TARGETING_KEYS = frozenset({"shotEntityId", "intervalTicks", "rangeTiles", "sameTargetBias"})
_LIGHT_KEYS = frozenset({"strength", "color"})
_EVENT_KEYS = frozenset({
    "id", "event", "action", "actionCode", "entityId", "count", "spreadRadians", "damageMultiplier",
    "delayTicks", "periodTicks", "buffId", "durationTicks", "radiusPx", "rangeTiles", "mode", "strength",
    "radiusTiles", "damageFraction", "maxHeal", "cooldownTicks", "safeTileOnly",
})
_BINDING_KEYS = frozenset({"id", "input", "role", "usePolicy"})
_USE_POLICY_KEYS = frozenset({"action", "stackCost", "contactDamage"})
_BINDING_ACTION_KEYS = frozenset({"kind", "targetId", "placement"})
_PLACEMENT_KEYS = frozenset({"tileId", "wallId", "placeStyle"})
_ITEM_USE_KEYS = frozenset({"configured", "useStyle", "hideUseGraphic", "disableMeleeHitbox", "channel", "handPose", "releaseTiming", "holdoutOffsetX", "holdoutOffsetY"})
_ITEM_CONTACT_KEYS = frozenset({"hitboxScale", "contactForgivenessPx"})


def _reject_unknown(mapping: Mapping[str, Any], allowed: frozenset[str], path: str, errors: list[dict[str, Any]]) -> None:
    for raw_key in mapping:
        key = str(raw_key)
        if key not in allowed:
            errors.append({
                "path": f"{path}.{key}",
                "code": "unknown_final_wire_field",
                "message": f"Field {key!r} is not declared by the runtime-program v5 C# DTO.",
            })


def _validate_component_shape(value: Any, allowed: frozenset[str], path: str, errors: list[dict[str, Any]]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        errors.append({"path": path, "code": "required_object", "message": "Compiled component must be an object."})
        return None
    _reject_unknown(value, allowed, path, errors)
    return value


def _positive_integer_effect(value: Any, path: str, errors: list[dict[str, Any]]) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append({"path": path, "code": "invalid_integer", "message": "Effect value must be an integer without coercion."})
        return False
    return value > 0


def _generated_buff_has_effect(wire: Mapping[str, Any]) -> bool:
    """Project typed wire stats back to the canonical Author-side effect predicate."""
    params: dict[str, Any] = {}
    for name, spec in CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params.items():
        # Duration and color describe an effect; neither executes one. The
        # registry marks exactly the executable stats with neutral values.
        if spec.neutral is None:
            continue
        value = wire.get(spec.wire_name or name)
        if spec.wire_boolean_true_value is not None:
            if type(value) is int:
                params[name] = value == spec.wire_boolean_true_value
        elif spec.kind in {"integer", "number"}:
            if (spec.kind == "integer" or spec.wire_multiplier != 1) and type(value) is not int:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            try:
                if isfinite(value):
                    authored_value = value * spec.wire_divisor / spec.wire_multiplier
                    if (spec.minimum is not None and authored_value < spec.minimum) or (
                        spec.maximum is not None and authored_value > spec.maximum
                    ):
                        continue
                    params[name] = authored_value
            except OverflowError:
                # An unbounded malformed integer cannot be a valid wire stat.
                continue
    return _has_non_neutral_generated_buff(params)


def _walk_forbidden(value: Any, path: str = "$") -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if key in _FORBIDDEN_ROUTER_KEYS:
                errors.append({
                    "path": child_path,
                    "code": "legacy_semantic_router_field",
                    "message": f"Legacy semantic router field '{key}' is not part of runtime-program v5.",
                })
            errors.extend(_walk_forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk_forbidden(child, f"{path}[{index}]"))
    return errors


def validate_runtime_wire(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the final Python -> C# low-level runtime wire without authoring defaults."""
    errors: list[dict[str, Any]] = []
    runtime_raw = data.get("runtimeProgram")
    runtime = runtime_raw if isinstance(runtime_raw, Mapping) else {}
    if isinstance(runtime_raw, Mapping):
        _reject_unknown(runtime_raw, _RUNTIME_KEYS, "$.runtimeProgram", errors)
    if not isinstance(runtime_raw, Mapping):
        errors.append({"path": "$.runtimeProgram", "code": "required_object", "message": "Compiled runtimeProgram object is required."})
    if runtime.get("apiVersion") != RUNTIME_PROGRAM_API_VERSION:
        errors.append({
            "path": "$.runtimeProgram.apiVersion",
            "code": "unsupported_api_version",
            "message": f"Expected {RUNTIME_PROGRAM_API_VERSION!r}.",
        })
    if runtime.get("schema") != RUNTIME_WIRE_SCHEMA:
        errors.append({
            "path": "$.runtimeProgram.schema",
            "code": "unsupported_wire_schema",
            "message": f"Expected {RUNTIME_WIRE_SCHEMA!r}.",
        })
    if "calls" in runtime:
        errors.append({
            "path": "$.runtimeProgram.calls",
            "code": "author_ir_leaked_to_wire",
            "message": "Author calls must be compiled into typed entity components before C# delivery.",
        })

    limits_raw = runtime.get("limits")
    if isinstance(limits_raw, Mapping):
        _reject_unknown(limits_raw, _LIMIT_KEYS, "$.runtimeProgram.limits", errors)
    elif limits_raw is not None:
        errors.append({"path": "$.runtimeProgram.limits", "code": "required_object", "message": "Runtime limits must be an object."})

    item_use_raw = runtime.get("itemUse")
    if isinstance(item_use_raw, Mapping):
        _reject_unknown(item_use_raw, _ITEM_USE_KEYS, "$.runtimeProgram.itemUse", errors)
    elif item_use_raw is not None:
        errors.append({"path": "$.runtimeProgram.itemUse", "code": "required_object", "message": "itemUse must be an object."})
    item_contact_raw = runtime.get("itemContact")
    if isinstance(item_contact_raw, Mapping):
        _reject_unknown(item_contact_raw, _ITEM_CONTACT_KEYS, "$.runtimeProgram.itemContact", errors)
    elif item_contact_raw is not None:
        errors.append({"path": "$.runtimeProgram.itemContact", "code": "required_object", "message": "itemContact must be an object."})

    entities_raw = runtime.get("entities")
    entities = [row for row in entities_raw if isinstance(row, Mapping)] if isinstance(entities_raw, list) else []
    if not isinstance(entities_raw, list) or not entities:
        errors.append({"path": "$.runtimeProgram.entities", "code": "required_nonempty_array", "message": "At least one compiled entity is required."})
    entity_by_id: dict[str, Mapping[str, Any]] = {}
    for index, entity in enumerate(entities_raw if isinstance(entities_raw, list) else []):
        entity_path = f"$.runtimeProgram.entities[{index}]"
        if not isinstance(entity, Mapping):
            errors.append({"path": entity_path, "code": "required_object", "message": "Entity entry must be an object."})
            continue
        entity_id = str(entity.get("id") or "")
        kind = str(entity.get("kind") or "")
        _reject_unknown(entity, _ENTITY_KEYS, entity_path, errors)
        component_specs = (
            ("visual", _VISUAL_KEYS), ("spawn", _SPAWN_KEYS), ("damage", _DAMAGE_KEYS),
            ("hitbox", _HITBOX_KEYS), ("collision", _COLLISION_KEYS), ("movement", _DRIVER_KEYS),
            ("controller", _DRIVER_KEYS), ("targeting", _TARGETING_KEYS), ("light", _LIGHT_KEYS),
        )
        for component_name, allowed_keys in component_specs:
            if component_name not in entity:
                continue
            component = _validate_component_shape(entity.get(component_name), allowed_keys, f"{entity_path}.{component_name}", errors)
            if component_name == "spawn" and component is not None and "overTarget" in component:
                _validate_component_shape(component.get("overTarget"), _OVER_TARGET_KEYS, f"{entity_path}.spawn.overTarget", errors)
            if component_name in {"movement", "controller"} and component is not None and "params" in component:
                _validate_component_shape(component.get("params"), _PARAMS_KEYS, f"{entity_path}.{component_name}.params", errors)
        if not entity_id:
            errors.append({"path": f"$.runtimeProgram.entities[{index}].id", "code": "required_id", "message": "Entity id is required."})
        elif entity_id in entity_by_id:
            errors.append({"path": f"$.runtimeProgram.entities[{index}].id", "code": "duplicate_id", "message": f"Duplicate entity id {entity_id!r}."})
        else:
            entity_by_id[entity_id] = entity
        if kind not in ENTITY_KINDS:
            errors.append({"path": f"$.runtimeProgram.entities[{index}].kind", "code": "unknown_entity_kind", "message": f"Unknown entity kind {kind!r}."})
        else:
            expected_visual_role = VISUAL_ROLE_BY_ENTITY_KIND[kind]
            if entity.get("visualRole") != expected_visual_role:
                errors.append({
                    "path": f"$.runtimeProgram.entities[{index}].visualRole",
                    "code": "visual_role_mismatch",
                    "message": f"Entity kind {kind!r} requires technical visualRole {expected_visual_role!r}.",
                })
            visual = entity.get("visual")
            if not isinstance(visual, Mapping):
                errors.append({
                    "path": f"$.runtimeProgram.entities[{index}].visual",
                    "code": "required_object",
                    "message": "Compiled entity visual handoff must be an object.",
                })
            elif visual.get("role") != expected_visual_role:
                errors.append({
                    "path": f"$.runtimeProgram.entities[{index}].visual.role",
                    "code": "visual_role_mismatch",
                    "message": f"Entity kind {kind!r} requires technical visual.role {expected_visual_role!r}.",
                })
        if kind != "item_body":
            for required in ("spawn", "lifetimeTicks", "hitbox", "collision"):
                if required not in entity:
                    errors.append({
                        "path": f"$.runtimeProgram.entities[{index}].{required}",
                        "code": "missing_compiled_component",
                        "message": f"Runtime entity {entity_id!r} requires explicit {required}; the wire validator will not invent it.",
                    })
            # Stationary/deployed/field kinds explicitly author the absence of
            # locomotion through their entity kind. Mobile projectiles still
            # require either a movement component or a controller that owns
            # their full position lifecycle.
            controller_code = (entity.get("controller") or {}).get("code") if isinstance(entity.get("controller"), Mapping) else None
            controller_owns_position = (
                isinstance(controller_code, int) and not isinstance(controller_code, bool)
                and controller_code in {1, 2, 3}
            )
            mobile_kind = kind in {"owner_attached_projectile", "free_projectile", "child_projectile"}
            if mobile_kind and "movement" not in entity and not controller_owns_position:
                errors.append({
                    "path": f"$.runtimeProgram.entities[{index}].movement",
                    "code": "missing_compiled_component",
                    "message": f"Mobile runtime entity {entity_id!r} requires explicit movement or a position-owning controller; the wire validator will not invent it.",
                })
        movement = entity.get("movement")
        if isinstance(movement, Mapping):
            code = movement.get("code")
            if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= _MAX_MOVEMENT_CODE:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].movement.code", "code": "unsupported_opcode", "message": f"Movement opcode must be 0..{_MAX_MOVEMENT_CODE}."})
        controller = entity.get("controller")
        if isinstance(controller, Mapping):
            code = controller.get("code")
            name = str(controller.get("name") or "")
            if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= _MAX_CONTROLLER_CODE:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].controller.code", "code": "unsupported_opcode", "message": f"Controller opcode must be 0..{_MAX_CONTROLLER_CODE}."})
            elif code == 0 and name:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].controller", "code": "controller_name_opcode_mismatch", "message": "Neutral controller opcode 0 requires an empty name."})
        targeting = entity.get("targeting")
        if isinstance(targeting, Mapping):
            child = str(targeting.get("shotEntityId") or "")
            if child and child not in entity_by_id and child not in {str(row.get("id") or "") for row in entities}:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].targeting.shotEntityId", "code": "missing_entity_reference", "message": f"Unknown shot entity {child!r}."})
        events_raw = entity.get("events")
        if not isinstance(events_raw, list):
            errors.append({"path": f"$.runtimeProgram.entities[{index}].events", "code": "required_array", "message": "Compiled events must be an array."})
            events_raw = []
        for event_index, event in enumerate(events_raw):
            if not isinstance(event, Mapping):
                errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}]", "code": "required_object", "message": "Event entry must be an object."})
                continue
            _reject_unknown(event, _EVENT_KEYS, f"$.runtimeProgram.entities[{index}].events[{event_index}]", errors)
            action_code = event.get("actionCode")
            if not isinstance(action_code, int) or isinstance(action_code, bool) or not 1 <= action_code <= _MAX_EVENT_ACTION_CODE:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}].actionCode", "code": "unsupported_opcode", "message": f"Event action opcode must be 1..{_MAX_EVENT_ACTION_CODE}."})
            child = str(event.get("entityId") or "")
            if child and child not in {str(row.get("id") or "") for row in entities}:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}].entityId", "code": "missing_entity_reference", "message": f"Unknown event target entity {child!r}."})

    item_bodies = [row for row in entities if row.get("kind") == "item_body"]
    if len(item_bodies) != 1:
        errors.append({"path": "$.runtimeProgram.entities", "code": "item_body_count", "message": f"Exactly one item_body is required; found {len(item_bodies)}."})
    item_id = str(runtime.get("itemEntityId") or "")
    item = next((row for row in entities if str(row.get("id") or "") == item_id), None)
    if item is None or str(item.get("kind") or "") != "item_body":
        errors.append({"path": "$.runtimeProgram.itemEntityId", "code": "invalid_item_entity", "message": "itemEntityId must reference the unique item_body."})

    entity_kind_by_id = {str(row.get("id") or ""): str(row.get("kind") or "") for row in entities}
    primary_entity_id = str(runtime.get("primaryEntityId") or "")
    primary_kind = entity_kind_by_id.get(primary_entity_id)
    primary_owner = str(runtime.get("primaryOwner") or "")
    if primary_kind is None:
        errors.append({"path": "$.runtimeProgram.primaryEntityId", "code": "invalid_primary_entity", "message": "primaryEntityId must reference one compiled runtime entity."})
    else:
        expected_owner = "item_body" if primary_kind == "item_body" else "projectile"
        if primary_owner != expected_owner:
            errors.append({"path": "$.runtimeProgram.primaryOwner", "code": "primary_owner_mismatch", "message": f"Primary entity kind {primary_kind!r} requires primaryOwner {expected_owner!r}."})
    exclusive_inputs: set[str] = set()
    binding_ids: set[str] = set()
    bindings = runtime.get("bindings") or []
    if not isinstance(bindings, list):
        errors.append({"path": "$.runtimeProgram.bindings", "code": "required_array", "message": "Compiled bindings must be an array."})
        bindings = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            errors.append({"path": f"$.runtimeProgram.bindings[{index}]", "code": "required_object", "message": "Binding must be an object."})
            continue
        binding_path = f"$.runtimeProgram.bindings[{index}]"
        binding_id = binding.get("id")
        if not isinstance(binding_id, str) or not binding_id.strip():
            errors.append({"path": f"{binding_path}.id", "code": "required_id", "message": "Binding id must be a nonempty string."})
        elif binding_id in binding_ids:
            errors.append({"path": f"{binding_path}.id", "code": "duplicate_id", "message": f"Duplicate binding id {binding_id!r}."})
        else:
            binding_ids.add(binding_id)
        _reject_unknown(binding, _BINDING_KEYS, binding_path, errors)
        policy = binding.get("usePolicy")
        if not isinstance(policy, Mapping):
            errors.append({"path": f"{binding_path}.usePolicy", "code": "required_object", "message": "Binding usePolicy transaction is required."})
            policy = {}
        else:
            _reject_unknown(policy, _USE_POLICY_KEYS, f"{binding_path}.usePolicy", errors)
        action_row = action(binding)
        if not action_row:
            errors.append({"path": f"{binding_path}.usePolicy.action", "code": "required_object", "message": "Binding action transaction is required."})
        else:
            _reject_unknown(action_row, _BINDING_ACTION_KEYS, f"{binding_path}.usePolicy.action", errors)
        input_name = str(binding.get("input") or "")
        action_name = action_kind(binding)
        role = str(binding.get("role") or "")
        target = binding_target_id(binding)
        input_spec = INPUT_KIND_REGISTRY.get(input_name)
        action_spec = BINDING_ACTION_REGISTRY.get(action_name)
        if input_spec is None:
            errors.append({"path": f"{binding_path}.input", "code": "unknown_runtime_input", "message": f"Unknown runtime input {input_name!r}."})
        elif input_spec.exclusive and input_name in exclusive_inputs:
            errors.append({"path": f"{binding_path}.input", "code": "duplicate_exclusive_input", "message": f"Input {input_name!r} has multiple owners."})
        else:
            if input_spec is not None and input_spec.exclusive:
                exclusive_inputs.add(input_name)
        if action_spec is None:
            errors.append({"path": f"{binding_path}.usePolicy.action.kind", "code": "unknown_binding_action", "message": f"Unknown binding action {action_name!r}."})
        elif input_spec is not None and action_name not in input_spec.allowed_actions:
            errors.append({"path": f"{binding_path}.usePolicy.action.kind", "code": "binding_action_mismatch", "message": f"Action {action_name!r} is not allowed for input {input_name!r}."})
        target_kind = entity_kind_by_id.get(target)
        if target_kind is None:
            errors.append({"path": f"{binding_path}.usePolicy.action.targetId", "code": "missing_entity_reference", "message": f"Unknown binding target {target!r}."})
        elif action_spec is not None and target_kind not in action_spec.target_kinds:
            errors.append({"path": f"{binding_path}.usePolicy.action.targetId", "code": "binding_target_kind", "message": f"Action {action_name!r} cannot target entity kind {target_kind!r}."})
        expected_role = "primary" if target == primary_entity_id else "secondary"
        if role != expected_role:
            errors.append({"path": f"{binding_path}.role", "code": "binding_primary_role_mismatch", "message": f"Binding target {target!r} requires explicit role {expected_role!r}."})
        cost = stack_cost(binding)
        if cost not in {0, 1}:
            errors.append({"path": f"{binding_path}.usePolicy.stackCost", "code": "invalid_stack_cost", "message": "stackCost must be exactly 0 or 1."})
        contact_value = policy.get("contactDamage")
        if not isinstance(contact_value, bool):
            errors.append({"path": f"{binding_path}.usePolicy.contactDamage", "code": "required_boolean", "message": "contactDamage must be a boolean."})
        placement = action_row.get("placement")
        if action_name == "place_item":
            if cost != 1:
                errors.append({"path": f"{binding_path}.usePolicy.stackCost", "code": "place_item_without_stack_cost", "message": "place_item requires stackCost=1."})
            if contact_damage(binding):
                errors.append({"path": f"{binding_path}.usePolicy.contactDamage", "code": "binding_action_mismatch", "message": "place_item cannot deal item-body contact damage."})
            if isinstance(placement, Mapping):
                _reject_unknown(placement, _PLACEMENT_KEYS, f"{binding_path}.usePolicy.action.placement", errors)
                tile_id = placement.get("tileId")
                wall_id = placement.get("wallId")
                if not isinstance(tile_id, int) or isinstance(tile_id, bool) or not isinstance(wall_id, int) or isinstance(wall_id, bool):
                    errors.append({"path": f"{binding_path}.usePolicy.action.placement", "code": "invalid_placement_payload", "message": "Placement requires exact integer tileId and wallId."})
                elif tile_id < 0 and wall_id < 0:
                    errors.append({"path": f"{binding_path}.usePolicy.action.placement", "code": "empty_component", "message": "Placement must enable a tile or wall."})
            else:
                errors.append({"path": f"{binding_path}.usePolicy.action.placement", "code": "required_object", "message": "place_item requires its lowered placement payload."})
        elif placement is not None:
            errors.append({"path": f"{binding_path}.usePolicy.action.placement", "code": "binding_action_mismatch", "message": "Only place_item may carry placement payload."})
        if input_name not in ACTIVE_USE_INPUTS and (cost != 0 or contact_damage(binding)):
            errors.append({"path": f"{binding_path}.usePolicy", "code": "binding_action_mismatch", "message": "Non-use inputs require stackCost=0 and contactDamage=false."})

    active_use = any(isinstance(row, Mapping) and str(row.get("input") or "") in {"primary_use", "alternate_use"} for row in bindings)
    item_use = item_use_raw if isinstance(item_use_raw, Mapping) else {}
    if active_use and item_use.get("configured") is not True:
        errors.append({"path": "$.runtimeProgram.itemUse.configured", "code": "missing_item_use_capability", "message": "Active primary/alternate binding requires explicit configure_item_use."})

    gameplay_raw = data.get("gameplay")
    gameplay: Mapping[str, Any] = gameplay_raw if isinstance(gameplay_raw, Mapping) else {}
    retired_use_policy_fields = {
        "consumable",
        "consumeChancePercent",
        "primaryUseConsumeChancePercent",
        "alternateUseConsumeChancePercent",
        "createTile",
        "createWall",
        "placeStyle",
    }.intersection(gameplay)
    for field in sorted(retired_use_policy_fields):
        errors.append({
            "path": f"$.gameplay.{field}",
            "code": "retired_global_use_policy_field",
            "message": f"Global use-policy field {field!r} is not accepted by wire v3; each binding owns one complete usePolicy transaction.",
        })

    accessory = data.get("accessory") if isinstance(data.get("accessory"), Mapping) else {}
    armor = data.get("armor") if isinstance(data.get("armor"), Mapping) else {}
    generated_buff_raw = gameplay.get("generatedBuff")
    generated_buff = generated_buff_raw if isinstance(generated_buff_raw, Mapping) else {}
    # Validate every field before boolean composition; short-circuiting must not
    # hide malformed values behind an otherwise valid healing effect.
    heals_life = _positive_integer_effect(gameplay.get("healLife", 0), "$.gameplay.healLife", errors)
    heals_mana = _positive_integer_effect(gameplay.get("healMana", 0), "$.gameplay.healMana", errors)
    buff_has_duration = _positive_integer_effect(generated_buff.get("durationTicks", 0), "$.gameplay.generatedBuff.durationTicks", errors)
    has_generated_buff = buff_has_duration and _generated_buff_has_effect(generated_buff)
    has_use_effect = (
        heals_life
        or heals_mana
        or bool(gameplay.get("extraBuffs"))
        or has_generated_buff
        or bool(str(gameplay.get("mobilityMode") or ""))
    )
    has_equipment = accessory.get("enabled") is True or armor.get("enabled") is True
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            continue
        action_name = action_kind(binding)
        if action_name == "apply_item_effects" and not has_use_effect:
            errors.append({"path": f"$.runtimeProgram.bindings[{index}].usePolicy.action", "code": "binding_dependency", "message": "apply_item_effects has no compiled item effect capability."})
        elif action_name == "equip_passive" and not has_equipment:
            errors.append({"path": f"$.runtimeProgram.bindings[{index}].usePolicy.action", "code": "binding_dependency", "message": "equip_passive has no compiled accessory/armor capability."})

    placeable_roles_valid, placeable_role_message = placeable_input_contract(
        row for row in bindings if isinstance(row, Mapping)
    )
    if not placeable_roles_valid:
        errors.append({
            "path": "$.runtimeProgram.bindings",
            "code": "dual_use_placeable_input_contract",
            "message": placeable_role_message,
        })

    errors.extend(_walk_forbidden({"runtimeProgram": runtime}))

    contract_raw = data.get("runtimeContract")
    contract = contract_raw if isinstance(contract_raw, Mapping) else {}
    receipts_raw = contract.get("finalWireReceipts")
    receipts = receipts_raw if isinstance(receipts_raw, list) else []
    # Delivery intentionally strips internal provenance. Audit any present
    # contract (including a broken/empty one), but never demand receipts from
    # a delivery DTO that makes no provenance claim.
    lowering = audit_compiler_receipts(receipts, final_document=data if "runtimeContract" in data else None)
    if not lowering.get("ok"):
        errors.append({
            "path": "$.runtimeContract.finalWireReceipts",
            "code": "undeclared_technical_lowering",
            "message": "Compiler receipt audit found output paths not declared by the capability registry.",
            "details": lowering.get("violations") or [],
        })

    return {
        "schema": "infini.runtime-program-wire-validation.v1",
        "ok": not errors,
        "errors": errors,
        "stats": {
            "entities": len(entities),
            "bindings": len(runtime.get("bindings") or []) if isinstance(runtime.get("bindings"), list) else 0,
            "events": sum(len(row.get("events") or []) for row in entities if isinstance(row.get("events"), list)),
            "receipts": len(receipts),
        },
        "technicalLowering": lowering,
    }


def assert_valid_runtime_wire(data: Mapping[str, Any]) -> dict[str, Any]:
    report = validate_runtime_wire(data)
    if not report["ok"]:
        messages = "; ".join(f"{row.get('path')}: {row.get('message')}" for row in report["errors"][:12])
        raise ValueError("invalid compiled runtime wire: " + messages)
    return report


__all__ = ["assert_valid_runtime_wire", "validate_runtime_wire"]
