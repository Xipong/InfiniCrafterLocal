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
    stack_chance_error,
    target_id as binding_target_id,
)
from infini_local.core.runtime_authoring.capability_registry import (
    BINDING_ACTION_REGISTRY,
    CAPABILITY_REGISTRY,
    CONTROLLER_OPCODE,
    PROJECTILE_MODIFIER_COMPONENTS,
    ENTITY_KINDS,
    EVENT_ACTION_OPCODE,
    INPUT_KIND_REGISTRY,
    RUNTIME_PROGRAM_API_VERSION,
    RUNTIME_WIRE_SCHEMA,
    VISUAL_ROLE_BY_ENTITY_KIND,
)
from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
from infini_local.core.runtime_authoring.technical_lowering import audit_compiler_receipts
from infini_local.core.runtime_authoring.validator import (
    MAX_CHILD_DEPTH, MAX_EVENT_SPAWNS_PER_ACTIVATION, MAX_RUNTIME_ENTITIES,
    _graph_cycle, _has_non_neutral_generated_buff, _max_depth,
)

_MAX_MOVEMENT_CODE = 19
_MAX_CONTROLLER_CODE = 3
_MAX_EVENT_ACTION_CODE = max(EVENT_ACTION_OPCODE.values())
_TARGET_EMISSION = "select_targets_and_emit_on_event"
_TARGET_EMISSION_FIELDS = frozenset(
    spec.wire_name or name for name, spec in CAPABILITY_REGISTRY[_TARGET_EMISSION].params.items()
)
_TARGET_EMISSION_ONLY_FIELDS = _TARGET_EMISSION_FIELDS - {"event", "entityId", "delayTicks"}
# Existing C# event DTOs serialize these unrelated fields with these exact
# neutral values. They remain readable, but cannot smuggle another operation
# into opcode 8. Fresh Author emits only the registry-owned fields above.
_EMISSION_UNUSED_EVENT_DEFAULTS = {
    "count": 1, "spreadRadians": 0, "damageMultiplier": 1, "periodTicks": 0,
    "buffId": -1, "durationTicks": 0, "radiusPx": 0, "rangeTiles": 0,
    "mode": "", "strength": 0, "radiusTiles": 0, "damageFraction": 0,
    "maxHeal": 0, "cooldownTicks": 0, "safeTileOnly": True,
}
_FORBIDDEN_ROUTER_KEYS = {
    "attack",
    "runtimePlan",
    "runtimeFamily",
    "weaponFamily",
    "projectileFamily",
    "delivery",
    "family",
}

_RUNTIME_KEYS = frozenset({"apiVersion", "schema", "itemEntityId", "primaryEntityId", "primaryOwner", "limits", "entities", "bindings", "itemUse", "itemContact", "effectGroups", "heldEffectGroupId", "weaponAmmo"})
_LIMIT_KEYS = frozenset({"maxEntityCount", "maxChildDepth", "maxEventSpawnsPerActivation"})
_ENTITY_KEYS = frozenset({"id", "kind", "visualRole", "visual", "spawn", "damage", "lifetimeTicks", "hitbox", "hitboxCurve", "collision", "movement", "controller", "targeting", "light", "events", "nativeSentry", "whipUsesOwnerGravity", *PROJECTILE_MODIFIER_COMPONENTS.values()})
_VISUAL_KEYS = frozenset({
    "role", "assetMode", "prompt", "silhouette", "visualIdentity", "impactPrompt", "impactNegativePrompt",
    "scale", "spritePath", "spriteUrl", "spriteStatus", "spriteTechnicalScore", "impactSpritePath",
    "impactSpriteUrl", "impactSpriteStatus", "impactSpriteTechnicalScore",
    "renderSizePx", "preferredCanvasSize", "forwardAngleDegrees",
})
_SPAWN_KEYS = frozenset({"enabled", "speedPxPerTick", "count", "spreadRadians", "offsetPx", "aim", "placement", "overTarget"}) | frozenset(
    spec.wire_name or name for fn in ("set_projectile_concurrency", "set_descendant_concurrency")
    for name, spec in CAPABILITY_REGISTRY[fn].params.items()
)
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
}) | frozenset(CAPABILITY_REGISTRY["channel_beam"].params)
_TARGETING_KEYS = frozenset(spec.wire_name or name for name, spec in CAPABILITY_REGISTRY["target_and_fire"].params.items())
_LIGHT_KEYS = frozenset({"strength", "color"})
_EVENT_KEYS = frozenset({
    "id", "event", "action", "actionCode", "entityId", "count", "spreadRadians", "damageMultiplier",
    "delayTicks", "periodTicks", "buffId", "durationTicks", "radiusPx", "rangeTiles", "mode", "strength",
    "radiusTiles", "damageFraction", "maxHeal", "cooldownTicks", "safeTileOnly",
    "damageBasis", "knockbackBasis",
}) | _TARGET_EMISSION_FIELDS
_BINDING_KEYS = frozenset({"id", "input", "role", "usePolicy"})
_USE_POLICY_KEYS = frozenset({"action", "stackCost", "contactDamage", "stackConsumeChancePercent"})
_BINDING_ACTION_KEYS = frozenset({"kind", "targetId", "placement", "effectGroupId"})
_PLACEMENT_KEYS = frozenset({"tileId", "wallId", "placeStyle", "placedBody"})
_PLACED_BODY_KEYS = frozenset(name for name in CAPABILITY_REGISTRY["present_placed_item_sprite"].params if name != "placementCallId")
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


def _validate_child_combat(
    wire: Mapping[str, Any], capability: str, source_kind: str, active: bool,
    path: str, errors: list[dict[str, Any]],
) -> None:
    """New present leaves are exact; omitted saved-wire leaves retain their old lane."""
    cap = CAPABILITY_REGISTRY[capability]
    names = ("damageBasis", "knockbackBasis", "damageMultiplier") if capability == "target_and_fire" else ("damageBasis", "knockbackBasis")
    for name in names:
        if name not in wire:
            continue
        leaf_path = f"{path}.{name}"
        if not active:
            errors.append({"path": leaf_path, "code": "inactive_child_combat_field",
                           "message": "Child combat choices require this component's exact child-spawn consumer."})
        errors.extend(strict_schema_errors(wire[name], cap.params[name].schema(), path=leaf_path))
    for requirement in cap.requirements:
        if (requirement.kind == "param_requires_target_kind"
                and wire.get(requirement.param) == requirement.equals
                and source_kind not in requirement.any_of):
            errors.append({"path": f"{path}.{requirement.param}",
                           "code": "unsupported_param_target_kind", "message": requirement.message})


def _validate_generated_buff(wire: Mapping[str, Any], errors: list[dict[str, Any]], path: str = "$.gameplay.generatedBuff") -> None:
    """Check every present leaf; absent legacy leaves retain C# DTO defaults."""
    specs = {name: spec for name, spec in CAPABILITY_REGISTRY["apply_generated_buff_on_use"].params.items() if name != "effectGroupId"}
    _reject_unknown(wire, frozenset(spec.wire_name or name for name, spec in specs.items()),
                    path, errors)
    light = wire.get("emitLightStrength", 0)
    no_light = type(light) in (int, float) and light <= 0
    for name, spec in specs.items():
        key = spec.wire_name or name
        # GeneratedBuffSpec defaults color to empty, valid only without light.
        if key not in wire and not (key == "lightColorName" and not no_light):
            continue
        value = wire.get(key, "")
        valid = False
        if spec.wire_boolean_true_value is not None:
            valid = type(value) is int and value in (0, spec.wire_boolean_true_value)
        elif spec.kind == "string":
            valid = isinstance(value, str) and (value in spec.enum or (value == "" and no_light))
        else:
            integer_wire = spec.kind == "integer" or spec.wire_multiplier != 1
            typed = type(value) is int if integer_wire else type(value) in (int, float)
            if typed:
                try:
                    authored = value * spec.wire_divisor / spec.wire_multiplier
                    # Zero duration is the inactive DTO state, not an active
                    # authored buff. Other bounds/conversions are registry-owned.
                    minimum = 0 if key == "durationTicks" else spec.minimum
                    valid = (isfinite(authored)
                             and (minimum is None or authored >= minimum)
                             and (spec.maximum is None or authored <= spec.maximum)
                             and (spec.multiple_of is None or authored % spec.multiple_of == 0)
                             and spec.consumer_value_error(authored) is None)
                except OverflowError:
                    valid = False
        if not valid:
            errors.append({"path": f"{path}.{key}",
                           "code": "invalid_generated_buff_field",
                           "message": "Value must match the declared generated-buff wire type and domain without coercion."})


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


def _item_effect_group_wire_schema() -> dict[str, Any]:
    """The accepted container surface is a projection of existing registry fields."""
    properties = {"id": CAPABILITY_REGISTRY["restore_resources_on_use"].params["effectGroupId"].schema()}
    for fn in ("restore_resources_on_use", "move_player_on_use"):
        properties.update({spec.wire_name or name: spec.schema() for name, spec in CAPABILITY_REGISTRY[fn].params.items() if name != "effectGroupId"})
    buff_properties = {spec.wire_name or name: spec.schema() for name, spec in CAPABILITY_REGISTRY["apply_vanilla_buff_on_use"].params.items() if name != "effectGroupId"}
    properties["mobilityMode"]["enum"] = ["", *properties["mobilityMode"]["enum"]]
    # A fn-selected exact literal shares the same DTO domain as parameter
    # projections; exposing it on wire does not accept a retired Author token.
    for cap in CAPABILITY_REGISTRY.values():
        if cap.effect_groupable:
            for key, value in cap.fixed_wire_literals.items():
                if key in properties and "enum" in properties[key] and value not in properties[key]["enum"]:
                    properties[key]["enum"].append(value)
    properties["extraBuffs"] = {"type": "array", "maxItems": 48, "items": {
        "type": "object", "additionalProperties": False, "properties": buff_properties, "required": list(buff_properties)}}
    properties["generatedBuff"] = {"type": "object"}
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": ["id"]}


def _validate_effect_groups(runtime: Mapping[str, Any], errors: list[dict[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Named containers are literal destinations of the four existing item effects."""
    groups: dict[str, Mapping[str, Any]] = {}
    if "effectGroups" not in runtime:
        return groups
    rows = runtime["effectGroups"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 48:
        errors.append({"path": "$.runtimeProgram.effectGroups", "code": "invalid_effect_groups", "message": "Present effectGroups must contain 1..48 explicit named groups."})
        return groups
    schema = _item_effect_group_wire_schema()
    for index, row in enumerate(rows):
        path = f"$.runtimeProgram.effectGroups[{index}]"
        for issue in strict_schema_errors(row, schema, path=path):
            errors.append({**issue, "code": "invalid_effect_group", "message": "Effect group must match the exact registered item-effect fields and domains."})
        if not isinstance(row, Mapping):
            continue
        group_id = row.get("id")
        if isinstance(group_id, str):
            if group_id in groups:
                errors.append({"path": f"{path}.id", "code": "duplicate_id", "message": "Effect group IDs must be unique."})
            groups[group_id] = row
        generated = row.get("generatedBuff")
        if isinstance(generated, Mapping):
            _validate_generated_buff(generated, errors, f"{path}.generatedBuff")
            if type(generated.get("durationTicks")) is not int or not 1 <= generated["durationTicks"] <= 21600:
                errors.append({"path": f"{path}.generatedBuff.durationTicks", "code": "invalid_effect_group", "message": "Named generated buff requires explicit 1..21600 duration."})
        if not _item_effects_present(row):
            errors.append({"path": path, "code": "empty_effect_group", "message": "Effect group must contain an executable explicit item effect."})
    return groups


def _item_effects_present(effects: Mapping[str, Any]) -> bool:
    generated = effects.get("generatedBuff")
    duration = generated.get("durationTicks") if isinstance(generated, Mapping) else None
    return (any(type(effects.get(key)) is int and effects[key] > 0 for key in ("healLife", "healMana"))
            or isinstance(effects.get("extraBuffs"), list) and bool(effects["extraBuffs"])
            or isinstance(generated, Mapping) and type(duration) is int and duration > 0 and _generated_buff_has_effect(generated)
            or effects.get("mobilityMode") in ("recall_home", "blink_to_cursor"))


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


def _validate_sprite_presentation(visual: Mapping[str, Any], path: str, errors: list[dict[str, Any]], *, entity_kind: str | None = None) -> None:
    """Additive DTO compatibility: omission stays omitted, present choices are strict."""
    from infini_local.pipelines.visual_generation_pipeline import _visual_item_schema
    from infini_local.core.runtime_authoring.program_schema import strict_schema_errors
    fields = ("renderSizePx", "forwardAngleDegrees") if entity_kind is None else ("renderSizePx", "forwardAngleDegrees", "preferredCanvasSize")
    properties = _visual_item_schema()["properties"]
    for field in fields:
        if field not in visual:
            continue
        leaf_path = f"{path}.{field}"
        if entity_kind is not None and (entity_kind == "item_body" or visual.get("assetMode") != "baked_sprite"):
            errors.append({"path": leaf_path, "code": "nonowning_sprite_presentation", "message": "Only a distinct baked entity owns main-sprite presentation; item_body/reuse select the root and non-PNG branches have none."})
        for error in strict_schema_errors(visual[field], properties[field], path=leaf_path):
            errors.append({"path": error["path"], "code": "invalid_sprite_presentation", "message": "Present presentation metadata must have the declared non-null type and finite bounded domain without coercion."})


def _validate_target_emission(event: Mapping[str, Any], entities: list[Mapping[str, Any]],
                              path: str, errors: list[dict[str, Any]]) -> None:
    cap = CAPABILITY_REGISTRY[_TARGET_EMISSION]
    if event.get("actionCode") != EVENT_ACTION_OPCODE[_TARGET_EMISSION]:
        for key in _TARGET_EMISSION_ONLY_FIELDS & event.keys():
            errors.append({"path": f"{path}.{key}", "code": "wrong_event_parameter_owner",
                           "message": "Target-selection emission fields require the exact registered opcode."})
        if event.get("action") == _TARGET_EMISSION:
            errors.append({"path": f"{path}.actionCode", "code": "event_name_opcode_mismatch",
                           "message": "Target-selection emission requires its exact registered opcode."})
        return
    if event.get("action") != cap.name:
        errors.append({"path": f"{path}.action", "code": "event_name_opcode_mismatch",
                       "message": "The target emission name and opcode must agree exactly."})
    schema = {"type": "object", "additionalProperties": False,
              "properties": {spec.wire_name or name: spec.schema() for name, spec in cap.params.items()},
              "required": [spec.wire_name or name for name, spec in cap.params.items() if spec.required]}
    params = {key: event[key] for key in _TARGET_EMISSION_FIELDS if key in event}
    for error in strict_schema_errors(params, schema, path=path):
        errors.append({**error, "code": "invalid_target_emission_parameter"})
    for key, neutral in _EMISSION_UNUSED_EVENT_DEFAULTS.items():
        if key not in event:
            continue
        value = event[key]
        # JSON numbers share one numeric domain; booleans never equal 0/1.
        same_type = type(value) is type(neutral) or type(value) in (int, float) and type(neutral) in (int, float)
        if not same_type or value != neutral:
            errors.append({"path": f"{path}.{key}", "code": "wrong_event_parameter_owner",
                           "message": "This field is not consumed by target emission; only its retained DTO neutral is readable."})
    child = next((row for row in entities if row.get("id") == event.get("entityId")), None)
    if child is None:
        return  # Existing reference validation reports the missing target.
    reference = cap.params["entity"].reference
    spawn = child.get("spawn")
    valid = reference is not None and child.get("kind") in reference.target_kinds and isinstance(spawn, Mapping)
    if valid:
        assert isinstance(spawn, Mapping)
        valid = spawn.get("enabled") is True
        for requirement in cap.requirements:
            if requirement.kind == "referenced_entity_capability_params":
                source = CAPABILITY_REGISTRY[requirement.capability]
                for key, required_value in requirement.equals.items():
                    spec = source.params[key]
                    # Requirements are authored values; compare their canonical
                    # leaf projection, including typed union aliases, to wire.
                    for projected in spec.projected_fields(required_value, key):
                        value: Any = spawn
                        for part in projected.wire_path.split("."):
                            value = value.get(part) if isinstance(value, Mapping) else None
                        same_type = (type(value) is type(projected.value)
                                     or type(value) in (int, float) and type(projected.value) in (int, float))
                        valid = valid and same_type and value == projected.value
            elif requirement.kind == "referenced_entity_without_capability" and requirement.capability == "spawn_over_target":
                over = spawn.get("overTarget", {})
                valid = valid and isinstance(over, Mapping) and all(
                    key not in over or type(over[key]) in (int, float) and over[key] == 0
                    for key in ("heightTiles", "delayTicks"))
    if not valid:
        errors.append({"path": f"{path}.entityId", "code": "reference_requirements_unsatisfied",
                       "message": "Target emission needs the exact independent projectile spawn contract declared by its registry reference requirements."})


def _validate_target_emission_graph(runtime: Mapping[str, Any], entities: list[Mapping[str, Any]],
                                     errors: list[dict[str, Any]]) -> None:
    """Validate new emission graphs without reinterpreting retained old-only wire."""
    actions = [(entity, event) for entity in entities
               for event in (entity.get("events") if isinstance(entity.get("events"), list) else [])
               if isinstance(event, Mapping)]
    if not any(event.get("actionCode") == EVENT_ACTION_OPCODE[_TARGET_EMISSION] for _, event in actions):
        return
    limit_defaults = {"maxEntityCount": MAX_RUNTIME_ENTITIES, "maxChildDepth": MAX_CHILD_DEPTH,
                      "maxEventSpawnsPerActivation": MAX_EVENT_SPAWNS_PER_ACTIVATION}
    raw_limits = runtime.get("limits")
    limits = dict(raw_limits) if isinstance(raw_limits, Mapping) else {}
    for key, ceiling in limit_defaults.items():
        value = limits.get(key, ceiling)
        minimum = 1 if key == "maxEntityCount" else 0
        if type(value) is not int or not minimum <= value <= ceiling:
            errors.append({"path": f"$.runtimeProgram.limits.{key}", "code": "invalid_runtime_limit",
                           "message": "Target emission requires a bounded integer runtime limit without coercion."})
            return
        limits[key] = value
    if len(entities) > limits["maxEntityCount"]:
        errors.append({"path": "$.runtimeProgram.entities", "code": "entity_limit_exceeded",
                       "message": "Target emission graph exceeds the explicit entity limit."})
        return
    graph = {str(entity.get("id") or ""): set() for entity in entities}
    total = 0
    for entity, event in actions:
        opcode = event.get("actionCode")
        if opcode not in (EVENT_ACTION_OPCODE["spawn_entity_on_event"], EVENT_ACTION_OPCODE[_TARGET_EMISSION]):
            continue
        child = event.get("entityId")
        if isinstance(child, str) and child in graph:
            graph[str(entity.get("id") or "")].add(child)
        count = event.get("stepCount") if opcode == EVENT_ACTION_OPCODE[_TARGET_EMISSION] else event.get("count", 1)
        if type(count) is not int or count < 1 or count > CAPABILITY_REGISTRY["spawn_entity_on_event"].params["count"].maximum:
            errors.append({"path": "$.runtimeProgram.entities", "code": "invalid_graph_spawn_count",
                           "message": "Every counted spawn edge needs its declared integer count."})
            return
        total += count
    for entity in entities:
        targeting = entity.get("targeting")
        shot = targeting.get("shotEntityId") if isinstance(targeting, Mapping) else None
        if isinstance(shot, str) and shot in graph:
            graph[str(entity.get("id") or "")].add(shot)
    if total > limits["maxEventSpawnsPerActivation"]:
        errors.append({"path": "$.runtimeProgram.entities", "code": "event_spawn_budget_exceeded",
                       "message": "Aggregate physical event emissions exceed the shared activation limit."})
    cycle = _graph_cycle(graph)
    if cycle:
        errors.append({"path": "$.runtimeProgram.entities", "code": "entity_graph_cycle",
                       "message": "Entity spawn/targeting graph contains a cycle: " + " -> ".join(cycle)})
    elif _max_depth(graph, graph) > limits["maxChildDepth"]:
        errors.append({"path": "$.runtimeProgram.entities", "code": "entity_graph_depth_exceeded",
                       "message": "Entity spawn/targeting graph exceeds the explicit child depth."})


def validate_runtime_wire(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the final Python -> C# low-level runtime wire without authoring defaults."""
    errors: list[dict[str, Any]] = []
    root_visual = data.get("visual")
    if isinstance(root_visual, Mapping):
        _validate_sprite_presentation(root_visual, "$.visual", errors)
    runtime_raw = data.get("runtimeProgram")
    runtime = runtime_raw if isinstance(runtime_raw, Mapping) else {}
    if isinstance(runtime_raw, Mapping):
        _reject_unknown(runtime_raw, _RUNTIME_KEYS, "$.runtimeProgram", errors)
    if not isinstance(runtime_raw, Mapping):
        errors.append({"path": "$.runtimeProgram", "code": "required_object", "message": "Compiled runtimeProgram object is required."})
    if "weaponAmmo" in runtime:
        ammo_cap = CAPABILITY_REGISTRY["configure_weapon_ammo"]
        ammo_schema = {"type": "object", "additionalProperties": False,
                       "properties": {name: spec.schema() for name, spec in ammo_cap.params.items()},
                       "required": list(ammo_cap.params)}
        for issue in strict_schema_errors(runtime["weaponAmmo"], ammo_schema, path="$.runtimeProgram.weaponAmmo"):
            errors.append({**issue, "code": "invalid_weapon_ammo", "message": "weaponAmmo must contain exactly the registered category and explicit speed basis."})
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
        movement = entity.get("movement") if isinstance(entity.get("movement"), Mapping) else {}
        controller = entity.get("controller") if isinstance(entity.get("controller"), Mapping) else {}
        for modifier_fn, member in PROJECTILE_MODIFIER_COMPONENTS.items():
            if member not in entity:
                continue
            modifier_cap = CAPABILITY_REGISTRY[modifier_fn]
            modifier_path = entity_path + "." + member
            shape = strict_schema_errors(entity[member], modifier_cap.provider_variant_schema()["properties"]["params"], path=modifier_path)
            if kind not in modifier_cap.target_kinds or shape:
                errors.append({"path": modifier_path, "code": "invalid_projectile_modifier", "message": "Present modifier requires the exact target kind, all registry choices, finite ranges and no unknown fields."})
                errors.extend(shape)
            if modifier_cap.category == "motion_modifier" and controller.get("code", 0) != 0:
                errors.append({"path": modifier_path, "code": "modifier_driver_conflict", "message": "Velocity modifiers require movement to own motion."})
            if member == "visualScaleCurve" and (movement.get("code") in {15, 18} or controller.get("code") == 1 or isinstance(entity.get("hitboxCurve"), Mapping) and entity["hitboxCurve"].get("mirrorToSprite") is True):
                errors.append({"path": modifier_path, "code": "modifier_driver_conflict", "message": "Dynamic sprite scale has exactly one authored owner and excludes special beam/whip line geometry."})
        if "whipUsesOwnerGravity" in entity:
            path = entity_path + ".whipUsesOwnerGravity"
            if entity["whipUsesOwnerGravity"] is not True or kind != "owner_attached_projectile" or movement.get("code") != 18 or controller.get("code") == 1:
                errors.append({"path": path, "code": "invalid_whip_gravity", "message": "The true marker requires actual owner-attached whip geometry without beam precedence."})
        if "hitboxCurve" in entity:
            curve_cap = CAPABILITY_REGISTRY["set_projectile_hitbox_curve"]
            curve_schema = curve_cap.provider_variant_schema()["properties"]["params"]
            curve = entity["hitboxCurve"]
            curve_path = entity_path + ".hitboxCurve"
            shape = strict_schema_errors(curve, curve_schema, path=curve_path)
            if kind not in curve_cap.target_kinds or shape:
                errors.append({"path": curve_path, "code": "invalid_hitbox_curve", "message": "Present hitboxCurve requires every explicit registry field, exact types, finite bounds and a projectile target."})
                errors.extend(shape)
            else:
                movement = entity.get("movement") if isinstance(entity.get("movement"), Mapping) else {}
                controller = entity.get("controller") if isinstance(entity.get("controller"), Mapping) else {}
                if controller.get("code") == 1 or movement.get("code") == 18 or (curve["mirrorToSprite"] and (movement.get("code") == 15 or "visualScaleCurve" in entity)):
                    errors.append({"path": curve_path, "code": "hitbox_curve_driver_conflict", "message": "Rectangle curves exclude beam/whip collisions; a sprite mirror excludes independent expanding-wave scale."})
        component_specs = (
            ("visual", _VISUAL_KEYS), ("spawn", _SPAWN_KEYS), ("damage", _DAMAGE_KEYS),
            ("hitbox", _HITBOX_KEYS), ("collision", _COLLISION_KEYS), ("movement", _DRIVER_KEYS),
            ("controller", _DRIVER_KEYS), ("targeting", _TARGETING_KEYS), ("light", _LIGHT_KEYS),
        )
        for component_name, allowed_keys in component_specs:
            if component_name not in entity:
                continue
            component = _validate_component_shape(entity.get(component_name), allowed_keys, f"{entity_path}.{component_name}", errors)
            if component_name == "visual" and component is not None:
                _validate_sprite_presentation(component, f"{entity_path}.visual", errors, entity_kind=kind)
            if component_name == "spawn" and component is not None:
                for fn in ("set_projectile_concurrency", "set_descendant_concurrency"):
                    concurrency = CAPABILITY_REGISTRY[fn]
                    for name, spec in concurrency.params.items():
                        key = spec.wire_name or name
                        if key not in component:
                            continue  # Legacy omission adds no admission cap.
                        path = f"{entity_path}.spawn.{key}"
                        if kind not in concurrency.target_kinds or strict_schema_errors(component[key], spec.schema(), path=path):
                            errors.append({"path": path, "code": "invalid_projectile_concurrency",
                                           "message": "Present concurrency must match the registry projectile target, integer type and positive bounds without coercion."})
                if "placement" in component:
                    for issue in strict_schema_errors(component["placement"], CAPABILITY_REGISTRY["configure_spawn"].retained_receipt_params["placement"].schema(), path=f"{entity_path}.spawn.placement"):
                        errors.append(issue)
                if "overTarget" in component:
                    _validate_component_shape(component.get("overTarget"), _OVER_TARGET_KEYS, f"{entity_path}.spawn.overTarget", errors)
            if component_name in {"movement", "controller"} and component is not None and "params" in component:
                params = _validate_component_shape(component.get("params"), _PARAMS_KEYS, f"{entity_path}.{component_name}.params", errors)
                beam = CAPABILITY_REGISTRY["channel_beam"]
                for name, spec in beam.params.items():
                    if spec.default is None or params is None or name not in params:
                        continue  # Retained v5 omission keeps the old neutral behavior.
                    path = f"{entity_path}.{component_name}.params.{name}"
                    selected = (component_name == "controller" and component.get("name") == beam.name
                                and type(component.get("code")) is int and component["code"] == 1
                                and kind in beam.target_kinds)
                    if not selected or strict_schema_errors(params[name], spec.schema(), path=path) or spec.consumer_value_error(params[name]):
                        errors.append({"path": path, "code": "invalid_channel_beam_param",
                                       "message": "Present beam extension must match its exact controller, target, type, bounds and consumer precision without coercion."})
        if "nativeSentry" in entity:
            spec = CAPABILITY_REGISTRY["set_projectile_sentry"]
            path = f"{entity_path}.nativeSentry"
            if kind not in spec.target_kinds or strict_schema_errors(entity["nativeSentry"], spec.params["enabled"].schema(), path=path):
                errors.append({"path": path, "code": "invalid_native_sentry", "message": "Present nativeSentry must be an explicit projectile boolean."})
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
            _validate_child_combat(targeting, "target_and_fire", kind,
                                   isinstance(controller, Mapping) and type(controller.get("code")) is int
                                   and controller["code"] == CONTROLLER_OPCODE["target_and_fire"]
                                   and controller.get("name") == "target_and_fire",
                                   f"$.runtimeProgram.entities[{index}].targeting", errors)
            # New options are absent in retained v5 wire. Any present option is
            # checked by its canonical ParamSpec without supplying a value.
            option_names = ("count", "spreadRadians", "targetPolicy", "requireLineOfSight", "hardRange")
            present_options = set(option_names).intersection(targeting)
            if present_options and (
                kind not in CAPABILITY_REGISTRY["target_and_fire"].target_kinds
                or not isinstance(controller, Mapping)
                or controller.get("name") != "target_and_fire" or type(controller.get("code")) is not int
                or controller.get("code") != CONTROLLER_OPCODE["target_and_fire"]
            ):
                errors.append({"path": f"$.runtimeProgram.entities[{index}].targeting",
                               "code": "targeting_extension_owner",
                               "message": "Explicit targeting options require their registered controller and target kind."})
            contract = data.get("runtimeContract")
            if present_options and isinstance(contract, Mapping):
                receipts = contract.get("finalWireReceipts")
                receipts = receipts if isinstance(receipts, list) else []
                for name in sorted(present_options):
                    final_path = f"runtimeProgram.entities[{index}].targeting.{name}"
                    matching = [row for row in receipts if isinstance(row, Mapping)
                                and row.get("fn") == "target_and_fire" and row.get("finalPath") == final_path]
                    if len(matching) != 1:
                        errors.append({"path": "$." + final_path, "code": "targeting_extension_provenance",
                                       "message": "A present targeting option requires one exact capability receipt."})
            for name in option_names:
                if name in targeting:
                    spec = CAPABILITY_REGISTRY["target_and_fire"].params[name]
                    for error in strict_schema_errors(targeting[name], spec.schema()):
                        errors.append({**error, "path": f"$.runtimeProgram.entities[{index}].targeting.{name}"})
                    consumer_error = spec.consumer_value_error(targeting[name])
                    if consumer_error:
                        errors.append({"code": "consumer_precision_loss", "message": consumer_error,
                                       "path": f"$.runtimeProgram.entities[{index}].targeting.{name}"})
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
            _validate_target_emission(event, entities, f"$.runtimeProgram.entities[{index}].events[{event_index}]", errors)
            if event.get("actionCode") == EVENT_ACTION_OPCODE[_TARGET_EMISSION]:
                damage = entity.get("damage")
                bindings = runtime.get("bindings")
                contact = isinstance(bindings, list) and any(
                    contact_damage(binding) for binding in bindings if isinstance(binding, Mapping))
                if (kind == "item_body" and not contact) or (kind != "item_body" and (
                    not isinstance(damage, Mapping) or damage.get("enabled") is not True
                )):
                    errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}].event",
                                   "code": "event_not_produced", "message": "Target emission requires the actual item-contact or projectile-damage hit producer."})
            action_code = event.get("actionCode")
            _validate_child_combat(event, "spawn_entity_on_event", kind,
                                   type(action_code) is int and action_code == EVENT_ACTION_OPCODE["spawn_entity_on_event"]
                                   and event.get("action") == "spawn_entity_on_event",
                                   f"$.runtimeProgram.entities[{index}].events[{event_index}]", errors)
            if not isinstance(action_code, int) or isinstance(action_code, bool) or not 1 <= action_code <= _MAX_EVENT_ACTION_CODE:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}].actionCode", "code": "unsupported_opcode", "message": f"Event action opcode must be 1..{_MAX_EVENT_ACTION_CODE}."})
            child = str(event.get("entityId") or "")
            if child and child not in {str(row.get("id") or "") for row in entities}:
                errors.append({"path": f"$.runtimeProgram.entities[{index}].events[{event_index}].entityId", "code": "missing_entity_reference", "message": f"Unknown event target entity {child!r}."})

    _validate_target_emission_graph(runtime, entities, errors)
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
    effect_groups = _validate_effect_groups(runtime, errors)
    used_effect_groups: set[str] = set()
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
        if "effectGroupId" in action_row:
            group_id = action_row["effectGroupId"]
            if action_name != "apply_item_effects" or not isinstance(group_id, str) or group_id not in effect_groups:
                errors.append({"path": f"{binding_path}.usePolicy.action.effectGroupId", "code": "invalid_effect_group_reference", "message": "Only apply_item_effects may select an exact declared effect group."})
            elif isinstance(group_id, str):
                used_effect_groups.add(group_id)
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
        if reason := stack_chance_error(binding):
            errors.append({"path": f"{binding_path}.usePolicy.stackConsumeChancePercent", "code": "invalid_stack_chance", "message": reason})
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
                if "placedBody" in placement:
                    specs = CAPABILITY_REGISTRY["present_placed_item_sprite"].params
                    body_schema = {"type": "object", "additionalProperties": False,
                                   "properties": {name: spec.schema() for name, spec in specs.items() if name != "placementCallId"},
                                   "required": [name for name in specs if name != "placementCallId"]}
                    body_path = f"{binding_path}.usePolicy.action.placement.placedBody"
                    for issue in strict_schema_errors(placement["placedBody"], body_schema, path=body_path):
                        errors.append({**issue, "code": "invalid_placed_body", "message": "Placed body must match every required canonical transform leaf."})
                    if type(placement.get("tileId")) is not int or not 0 <= placement["tileId"] <= 65535 or type(placement.get("wallId")) is not int or placement["wallId"] != -1:
                        errors.append({"path": body_path, "code": "placed_body_tile_only", "message": "Placed body requires tile-only placement."})
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
    if "weaponAmmo" in runtime:
        if not any(isinstance(binding, Mapping) and str(binding.get("input") or "") in ACTIVE_USE_INPUTS
                   and action_kind(binding) == "spawn_entity" for binding in bindings):
            errors.append({"path": "$.runtimeProgram.weaponAmmo", "code": "missing_weapon_ammo_consumer", "message": "weaponAmmo requires an active spawn_entity binding."})
        if gameplay.get("ammoCategory"):
            errors.append({"path": "$.runtimeProgram.weaponAmmo", "code": "ammo_role_conflict", "message": "One generated item cannot be both an ammo consumer and a native ammo stack."})
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
    if "generatedBuff" in gameplay and not isinstance(generated_buff_raw, Mapping):
        errors.append({"path": "$.gameplay.generatedBuff", "code": "required_object",
                       "message": "Generated buff must be an object."})
    _validate_generated_buff(generated_buff, errors)
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
    has_placement = any(isinstance(b, Mapping) and action_kind(b) == "place_item" for b in bindings)
    if "heldEffectGroupId" in runtime:
        held_id = runtime["heldEffectGroupId"]
        held_group = effect_groups.get(held_id) if isinstance(held_id, str) else None
        if (held_group is None or not isinstance(held_group.get("generatedBuff"), Mapping)
                or not _generated_buff_has_effect(held_group["generatedBuff"])
                or any(held_group.get(key, 0) != 0 for key in ("healLife", "healMana", "mobilityRangeTiles", "mobilityCooldownTicks"))
                or held_group.get("potion", False) is not False or held_group.get("extraBuffs", []) != []
                or held_group.get("mobilityMode", "") != ""):
            errors.append({"path": "$.runtimeProgram.heldEffectGroupId", "code": "invalid_held_effect_group", "message": "Held refresh must select exactly a generated-buff-only named group."})
        else:
            used_effect_groups.add(held_id)
    for group_id in effect_groups.keys() - used_effect_groups:
        errors.append({"path": "$.runtimeProgram.effectGroups", "code": "orphan_effect_group", "message": f"Effect group {group_id!r} has no exact binding or held consumer."})
    for index, binding in enumerate(bindings):
        if not isinstance(binding, Mapping):
            continue
        action_name = action_kind(binding)
        chance_policy = binding.get("usePolicy")
        chance = chance_policy.get("stackConsumeChancePercent") if isinstance(chance_policy, Mapping) else None
        if (has_placement and action_name in {"spawn_entity", "use_item_body"}
                and type(chance) is int and chance < 100 and gameplay.get("maxStack") != 1):
            errors.append({"path": "$.gameplay.maxStack", "code": "hybrid_placeable_max_stack", "message": "A reusable placement hybrid with own-stack saving requires maxStack=1."})
        group_id = action(binding).get("effectGroupId")
        selected_effects = effect_groups.get(group_id) if isinstance(group_id, str) else None
        selected_has_effect = _item_effects_present(selected_effects) if selected_effects is not None else has_use_effect if group_id is None else False
        if action_name == "apply_item_effects" and not selected_has_effect:
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
