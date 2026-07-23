from __future__ import annotations

import copy
import json
from typing import Any

from infini_local.core.boundary_models import AttackSpecBoundary
from infini_local.core.json_debug import bounded_json_dumps
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_authoring.reports import compile_runtime_plan_to_genome_result
from infini_local.core.runtime_authoring.result_identity import (
    RuntimeResultIdentityProjection,
    effective_runtime_result_kind,
    project_runtime_result_identity,
)
from infini_local.core.runtime_authoring.structural import all_calls, find_call
from infini_local.core.runtime_contracts import (
    STRUCTURAL_RUNTIME_CONTRACT_SCHEMA,
    authored_param_requires_final_wire_provenance,
)

_RESULT_SCHEMA = "infini.runtime-final-compile-result.v2"
_CACHE_KEY = "_runtimePlanCompileCache"

_GAMEPLAY_PATCH_FIELDS = frozenset({
    "healLife", "healMana", "buffCode", "buffTime", "pickPower", "axePower",
    "hammerPower", "miningSpeedScale", "mobilityMode", "mobilityRangeTiles",
    "mobilityCooldownTicks", "mobilitySafeTileOnly", "altUseMode", "altMobilityMode",
    "altUseCooldownTicks", "altMobilityRangeTiles", "altMobilitySafeTileOnly",
    "holdLightStrength", "holdLightColorName", "itemScale", "holdoutOffsetX",
    "holdoutOffsetY", "autoReuse", "useTurn", "channelUse", "consumeChancePercent",
    "ammoFor", "useConditionMode", "useConditionMinLife", "useConditionMinMana",
    "heldVisibility", "releaseTiming", "handPose", "initialOffsetPx", "createTile",
    "createWall", "placeStyle", "extraBuffs", "generatedBuff", "altGeneratedBuff",
    "holdGeneratedBuff",
})
_ITEM_STAT_FIELDS = (
    "damageClass", "damage", "knockback", "autoReuse", "maxStack", "consumable",
    "rarity", "value", "healLife", "healMana", "buffTime", "pickPower", "axePower",
    "hammerPower", "manaCost", "itemScale", "holdoutOffsetX", "holdoutOffsetY",
    "width", "height", "craftYield", "ammoFor",
)
_ATTACK_FIELDS = frozenset(AttackSpecBoundary.model_fields)
_ATTACK_FLOAT_FIELDS = frozenset({
    "speed", "rangeTiles", "homingStrength", "beamWidthPx", "chargePowerMultiplier",
    "projectileScale", "hitboxScale", "spreadRadians", "pullStrength",
    "secondarySpreadRadians", "secondaryDamageMultiplier", "sameTargetBias",
    "vfxParticleScale", "vfxFieldRadiusTiles", "soundPitch", "soundVolume",
    "soundPitchVariance", "sentryTargetRangeTiles", "runtimeLightStrength",
    "contactForgivenessPx",
})


def _signature(data: dict[str, Any]) -> str:
    return json.dumps(
        runtime_plan(data),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(hi, parsed))


def _num(value: Any, default: float, lo: float, hi: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(hi, parsed))


def _matches(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-9
    return left == right


def _project_attack_value(field: str, value: Any) -> Any:
    if field not in _ATTACK_FLOAT_FIELDS:
        return copy.deepcopy(value)
    parsed = float(value)
    digits = 2 if field in {
        "speed", "rangeTiles", "beamWidthPx", "sentryTargetRangeTiles",
        "contactForgivenessPx",
    } else 3
    return round(parsed, digits)


def _project_item_stat_value(
    field: str,
    value: Any,
    *,
    authored_kind: str,
    gameplay_kind: str,
) -> Any:
    noncombat = authored_kind in {"armor", "accessory", "potion", "material", "furniture", "generic"}
    if field == "damageClass":
        return "generic" if noncombat else str(value or "generic")
    if field == "damage":
        return 0 if noncombat else _int(value, 0, 0, 9999)
    if field == "knockback":
        return 0 if noncombat else round(_num(value, 0.0, 0.0, 12.0), 2)
    if field == "maxStack":
        if authored_kind in {"weapon", "tool", "accessory", "armor"}:
            return 1
        if authored_kind in {"consumable_weapon", "potion"}:
            return _int(value, 1, 1, 999)
        return _int(value, 1, 1, 9999)
    if field == "craftYield":
        return _int(value, 1, 1, 999)
    if field == "consumable":
        if authored_kind in {"consumable_weapon", "potion", "ammo"}:
            return True
        if authored_kind in {"weapon", "tool", "accessory", "armor"}:
            return False
        return bool(value)
    if field in {"pickPower", "hammerPower"}:
        return _int(value, 0, 0, 1000)
    if field == "axePower":
        return _int(value, 0, 0, 200)
    if field in {"width", "height"}:
        if authored_kind in {"armor", "accessory", "material", "furniture", "generic"}:
            return 24
        if authored_kind == "tool":
            return 28
        return _int(value, 24, 8 if authored_kind in {"potion", "ammo"} else 10, 96)
    if field in {"rarity"}:
        return _int(value, 0, -1, 12)
    if field in {"value"}:
        return _int(value, 0, 0, 999999999)
    if field in {"healLife", "healMana"}:
        return _int(value, 0, 0, 500)
    if field == "buffTime":
        return _int(value, 0, 0, 60 * 60 * 6)
    if field == "manaCost":
        return _int(value, 0, 0, 80)
    if field in {"holdoutOffsetX", "holdoutOffsetY"}:
        return _int(value, 0, -256, 256)
    if field == "itemScale":
        return round(_num(value, 1.0, 0.55, 1.55), 3)
    if field == "ammoFor":
        return str(value or "")
    return copy.deepcopy(value)


def _project_use_ticks(field: str, value: Any, authored_kind: str) -> int:
    if authored_kind in {"armor", "accessory", "ammo"}:
        return 10
    if authored_kind == "potion":
        return _int(value, 17, 10 if field == "useTimeTicks" else 6, 60)
    if authored_kind == "tool":
        return _int(value, 20, 10 if field == "useTimeTicks" else 6, 150)
    if authored_kind in {"weapon", "consumable_weapon"}:
        return _int(value, 20, 6, 150)
    return _int(value, 20, 1, 600)


def _build_sections_and_destinations(
    data: dict[str, Any],
    patch: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[str]],
    RuntimeResultIdentityProjection,
]:
    sections: dict[str, dict[str, Any]] = {
        "gameplay": {}, "attack": {}, "accessory": {}, "armor": {},
    }
    destinations: dict[str, list[str]] = {}

    def assign(section: str, field: str, value: Any, *compiled_fields: str) -> None:
        sections[section][field] = copy.deepcopy(value)
        final_path = f"{section}.{field}"
        source_fields = compiled_fields or (field,)
        for compiled_field in source_fields:
            paths = destinations.setdefault(compiled_field, [])
            if final_path not in paths:
                paths.append(final_path)
            if isinstance(value, dict):
                def register_nested(prefix: str, target_prefix: str, nested: dict[str, Any]) -> None:
                    for nested_field, nested_value in nested.items():
                        nested_source = f"{prefix}.{nested_field}"
                        nested_target = f"{target_prefix}.{nested_field}"
                        nested_paths = destinations.setdefault(nested_source, [])
                        if nested_target not in nested_paths:
                            nested_paths.append(nested_target)
                        if isinstance(nested_value, dict):
                            register_nested(nested_source, nested_target, nested_value)
                register_nested(compiled_field, final_path, value)

    stats = find_call(data, "set_item_stats")
    has_root_executor = bool(all_calls(data, "shoot_projectile"))
    identity = project_runtime_result_identity(
        effective_runtime_result_kind(data),
        ammo_for=stats.get("ammoFor"),
        has_root_executor=has_root_executor,
    )
    assign("gameplay", "kind", identity.gameplay_kind, "resultKind", "kind")
    if identity.runtime_output_kind:
        assign(
            "gameplay",
            "runtimeOutputKind",
            identity.runtime_output_kind,
            "__derived.runtimeOutputKind",
        )
    if identity.unsupported_ammo_for:
        assign(
            "gameplay",
            "unsupportedAmmoFor",
            identity.unsupported_ammo_for,
            "__derived.unsupportedAmmoFor",
        )

    for field in _ITEM_STAT_FIELDS:
        if field not in stats or stats.get(field) in (None, ""):
            continue
        assign(
            "gameplay",
            field,
            _project_item_stat_value(
                field,
                stats[field],
                authored_kind=identity.authored_kind,
                gameplay_kind=identity.gameplay_kind,
            ),
            field,
        )
    if identity.authored_kind == "consumable_weapon":
        max_stack = _int(sections["gameplay"].get("maxStack"), 1, 1, 999)
        craft_yield = _int(sections["gameplay"].get("craftYield"), 1, 1, max_stack)
        assign("gameplay", "maxStack", max_stack, "maxStack")
        assign("gameplay", "craftYield", craft_yield, "craftYield")
    if stats.get("useTimeTicks") not in (None, ""):
        assign(
            "gameplay", "useTime",
            _project_use_ticks("useTimeTicks", stats["useTimeTicks"], identity.authored_kind),
            "useTimeTicks",
        )
    if stats.get("useAnimationTicks") not in (None, ""):
        assign(
            "gameplay", "useAnimation",
            _project_use_ticks("useAnimationTicks", stats["useAnimationTicks"], identity.authored_kind),
            "useAnimationTicks",
        )
    elif stats.get("useTimeTicks") not in (None, ""):
        assign(
            "gameplay", "useAnimation",
            _project_use_ticks("useAnimationTicks", stats["useTimeTicks"], identity.authored_kind),
            "__derived.useAnimation",
        )

    if stats.get("buffType") not in (None, ""):
        assign("gameplay", "buffCode", stats["buffType"], "buffType")
    if stats.get("buffCode") not in (None, ""):
        assign("gameplay", "buffCode", stats["buffCode"], "buffCode")

    for field in _GAMEPLAY_PATCH_FIELDS:
        if patch.get(field) in (None, ""):
            continue
        assign("gameplay", field, patch[field], field)
    if identity.authored_kind == "tool":
        for field in ("pickPower", "axePower", "hammerPower"):
            if field not in sections["gameplay"]:
                assign("gameplay", field, 0, f"__derived.tool.{field}")
    if patch.get("runtimeLightStrength") not in (None, ""):
        assign("gameplay", "holdLightStrength", patch["runtimeLightStrength"], "runtimeLightStrength")
    if patch.get("runtimeLightColorName") not in (None, ""):
        assign("gameplay", "holdLightColorName", patch["runtimeLightColorName"], "runtimeLightColorName")

    if has_root_executor:
        for field, value in patch.items():
            if field in _ATTACK_FIELDS and value not in (None, ""):
                assign("attack", field, _project_attack_value(field, value), field)
        if stats.get("damageClass") not in (None, ""):
            assign("attack", "damageClass", str(stats["damageClass"]), "damageClass")
        ammo_kind = patch.get("ammoFor") or patch.get("ammoKind")
        if ammo_kind not in (None, ""):
            assign("attack", "ammoKind", str(ammo_kind), "ammoFor", "ammoKind")
        if patch.get("lifetimeTicks") not in (None, ""):
            assign("attack", "lifetime", int(patch["lifetimeTicks"]), "lifetimeTicks")
        if patch.get("projectileHitBudget") not in (None, ""):
            assign("attack", "pierce", int(patch["projectileHitBudget"]), "pierce", "projectileHitBudget")

    for section in ("accessory", "armor"):
        values = patch.get(section)
        if not isinstance(values, dict):
            continue
        for field, value in values.items():
            if value not in (None, ""):
                assign(section, field, value, field, f"{section}.{field}")
    if stats.get("armorSlot") not in (None, ""):
        assign("armor", "slot", str(stats["armorSlot"]), "slot", "armorSlot")
    if stats.get("defense") not in (None, ""):
        assign("armor", "defense", _int(stats["defense"], 0, 0, 80), "defense")
    for section in ("accessory", "armor"):
        if sections[section] and "enabled" not in sections[section]:
            assign(
                section,
                "enabled",
                identity.authored_kind == section,
                f"__derived.{section}.enabled",
            )
    return sections, destinations, identity


def _compiled_value_fallback(
    patch: dict[str, Any],
    compiled_field: str,
    authored_value: Any,
) -> Any:
    if compiled_field == "pierce" and patch.get("projectileHitBudget") not in (None, ""):
        return patch["projectileHitBudget"]
    if compiled_field in patch:
        return copy.deepcopy(patch[compiled_field])
    for section in ("accessory", "armor"):
        nested = patch.get(section)
        if isinstance(nested, dict) and compiled_field in nested:
            return copy.deepcopy(nested[compiled_field])
    return copy.deepcopy(authored_value)


def _final_section_value(
    sections: dict[str, dict[str, Any]],
    final_path: str,
) -> Any:
    parts = final_path.split(".")
    current: Any = sections
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            raise KeyError(final_path)
        current = current[part]
    return current


def _build_receipts(
    provenance: dict[str, Any],
    patch: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    destinations: dict[str, list[str]],
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    rows = provenance.get("authoredParameters")
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        call_id = str(row.get("callId") or "")
        fn = str(row.get("fn") or "")
        authored_param = str(row.get("param") or "")
        if not authored_param_requires_final_wire_provenance(fn, authored_param):
            continue
        authored_value = row.get("authoredValue")
        compiled_fields = row.get("compiledFields")
        compiled_fields = compiled_fields if isinstance(compiled_fields, list) else []
        if not compiled_fields:
            receipts.append({
                "callId": call_id,
                "authoredParam": authored_param,
                "authoredValue": copy.deepcopy(authored_value),
                "compiledField": "unmapped",
                "finalPath": "",
                "compiledValue": None,
                "status": "dropped",
            })
            continue
        for raw_compiled_field in compiled_fields:
            compiled_field = str(raw_compiled_field or "")
            paths = destinations.get(compiled_field, [])
            if not paths:
                receipts.append({
                    "callId": call_id,
                    "authoredParam": authored_param,
                    "authoredValue": copy.deepcopy(authored_value),
                    "compiledField": compiled_field,
                    "finalPath": "",
                    "compiledValue": _compiled_value_fallback(patch, compiled_field, authored_value),
                    "status": "dropped",
                })
                continue

            for final_path in paths:
                compiled_value = _final_section_value(sections, final_path)
                if _matches(compiled_value, authored_value):
                    status = "active"
                elif (
                    isinstance(compiled_value, (int, float))
                    and not isinstance(compiled_value, bool)
                    and isinstance(authored_value, (int, float))
                    and not isinstance(authored_value, bool)
                ):
                    status = "clamped"
                else:
                    status = "normalized"
                receipts.append({
                    "callId": call_id,
                    "authoredParam": authored_param,
                    "authoredValue": copy.deepcopy(authored_value),
                    "compiledField": compiled_field,
                    "finalPath": final_path,
                    "compiledValue": copy.deepcopy(compiled_value),
                    "status": status,
                })
    mapped = {
        (str(row.get("callId") or ""), str(row.get("authoredParam") or ""))
        for row in receipts
        if str(row.get("finalPath") or "")
    }
    return [
        row for row in receipts
        if row.get("status") != "dropped"
        or (str(row.get("callId") or ""), str(row.get("authoredParam") or "")) not in mapped
    ]


def compile_runtime_plan_to_final_result(data: dict[str, Any]) -> dict[str, Any]:
    """Compile one authored plan to a cached final-shaped executable snapshot."""
    normalize_runtime_plan_inplace(data)
    signature = _signature(data)
    cache = data.get(_CACHE_KEY)
    if (
        isinstance(cache, dict)
        and cache.get("signature") == signature
        and isinstance(cache.get("result"), dict)
        and cache["result"].get("schema") == _RESULT_SCHEMA
    ):
        return copy.deepcopy(cache["result"])

    compiler_result = compile_runtime_plan_to_genome_result(data)
    patch = compiler_result.get("patch")
    patch = patch if isinstance(patch, dict) else {}
    projection = _build_sections_and_destinations(data, patch)
    sections = projection[0]
    destinations = projection[1]
    identity = projection[2]
    attack_damage_class = sections.get("attack", {}).get("damageClass")
    if attack_damage_class not in (None, ""):
        patch["damageClass"] = attack_damage_class
    provenance = compiler_result.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    receipts = _build_receipts(provenance, patch, sections, destinations)
    affordance_fields = (
        "itemScale", "holdoutOffsetX", "holdoutOffsetY", "autoReuse", "useTurn",
        "channelUse", "heldVisibility", "releaseTiming", "handPose", "initialOffsetPx",
    )
    runtime_affordance = {
        field: copy.deepcopy(sections["gameplay"][field])
        for field in affordance_fields
        if field in sections["gameplay"]
    }
    if runtime_affordance:
        runtime_affordance["schema"] = "infini.runtime-affordance.v2"
        runtime_affordance["note"] = (
            "Author-provided use/draw feel. It does not change damage, resultKind, "
            "or runtimeFamily by itself."
        )
    result = {
        "schema": _RESULT_SCHEMA,
        "signature": signature,
        "api": ENGINE_RUNTIME_API_VERSION,
        "identity": {
            "authoredKind": identity.authored_kind,
            "gameplayKind": identity.gameplay_kind,
            "runtimeOutputKind": identity.runtime_output_kind,
            "authoredAmmoFor": identity.authored_ammo_for,
            "finalAmmoFor": identity.final_ammo_for,
            "unsupportedAmmoFor": identity.unsupported_ammo_for,
        },
        "patch": copy.deepcopy(patch),
        "finalSections": copy.deepcopy(sections),
        "finalWireReceipts": copy.deepcopy(receipts),
        "provenance": copy.deepcopy(provenance),
        "validation": copy.deepcopy(compiler_result.get("validation") or {}),
        "quality": copy.deepcopy(compiler_result.get("quality") or {}),
        "compiled": copy.deepcopy(compiler_result.get("compiled") or {}),
        "vfxCues": copy.deepcopy(patch.get("vfxCues") or []),
        "runtimeAffordance": runtime_affordance,
        "rejectedEngineCalls": copy.deepcopy(patch.get("rejectedEngineCalls") or []),
    }
    data[_CACHE_KEY] = {"signature": signature, "result": copy.deepcopy(result)}
    debug = data.setdefault("debug", {})
    if isinstance(debug, dict):
        debug["runtimeApiVersion"] = ENGINE_RUNTIME_API_VERSION
        debug["runtimePlanCompiler"] = bounded_json_dumps(result["quality"], max_chars=6000)
        debug["runtimePlanValidation"] = bounded_json_dumps(result["validation"], max_chars=6000)
        debug["runtimePlanProvenance"] = bounded_json_dumps(result["provenance"], max_chars=6000)
        debug["runtimeCompiled"] = bounded_json_dumps(result["compiled"], max_chars=6000)
    data["runtimeCompiled"] = copy.deepcopy(result["compiled"])
    return copy.deepcopy(result)


def runtime_final_patch(data: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(compile_runtime_plan_to_final_result(data)["patch"])


def apply_runtime_final_sections(
    data: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Apply compiler-owned executable overlays once; parent/balance fields survive."""
    if str(result.get("schema") or "") != _RESULT_SCHEMA:
        raise ValueError("invalid runtime final compile result schema")
    sections = result.get("finalSections")
    if not isinstance(sections, dict):
        raise ValueError("runtime final compile result lacks finalSections")
    for section in ("gameplay", "attack", "accessory", "armor"):
        overlay = sections.get(section)
        if not isinstance(overlay, dict):
            raise ValueError(f"runtime final compile result lacks {section} section")
        target = data.setdefault(section, {})
        if not isinstance(target, dict):
            raise ValueError(f"final executable section {section} is not an object")
        target.update(copy.deepcopy(overlay))
    return attach_runtime_final_evidence(data, result)


def attach_runtime_final_evidence(
    data: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Attach immutable compiler evidence without rewriting executable sections."""
    if str(result.get("schema") or "") != _RESULT_SCHEMA:
        raise ValueError("invalid runtime final compile result schema")
    attack = data.get("attack")
    if isinstance(attack, dict):
        attack["runtimeAuthoringProvenance"] = copy.deepcopy(result.get("provenance") or {})
    contract = data.get("runtimeContract")
    contract = dict(contract) if isinstance(contract, dict) else {}
    contract["schema"] = STRUCTURAL_RUNTIME_CONTRACT_SCHEMA
    contract["finalWireReceipts"] = copy.deepcopy(result.get("finalWireReceipts") or [])
    data["runtimeContract"] = contract
    if result.get("vfxCues"):
        data["vfxCues"] = copy.deepcopy(result["vfxCues"])
    if result.get("runtimeAffordance"):
        data["runtimeAffordance"] = copy.deepcopy(result["runtimeAffordance"])
        debug = data.setdefault("debug", {})
        if isinstance(debug, dict):
            debug["runtimeAffordance"] = bounded_json_dumps(result["runtimeAffordance"], max_chars=2000)
    if result.get("rejectedEngineCalls"):
        debug = data.setdefault("debug", {})
        if isinstance(debug, dict):
            debug["rejectedEngineCalls"] = bounded_json_dumps(result["rejectedEngineCalls"], max_chars=6000)
    debug = data.setdefault("debug", {})
    if isinstance(debug, dict):
        debug["compilerFinalWireReceipts"] = copy.deepcopy((result.get("finalWireReceipts") or [])[:192])
    return data


__all__ = [
    "apply_runtime_final_sections",
    "attach_runtime_final_evidence",
    "compile_runtime_plan_to_final_result",
    "runtime_final_patch",
]
