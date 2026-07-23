from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from infini_local.core.result_models import RuntimeCompileResult
from infini_local.core.runtime_authoring.common import ENGINE_RUNTIME_API_VERSION, _enum, _norm_name, _num
from infini_local.core.runtime_authoring.compiler import compile_runtime_plan_to_genome_patch
from infini_local.core.runtime_authoring.normalize import normalize_runtime_plan_inplace, runtime_plan
from infini_local.core.runtime_family_policy import (
    CANONICAL_RUNTIME_FAMILIES as RUNTIME_FAMILIES,
    HELD_PROJECTILE_RUNTIME_FAMILIES,
    exclusive_movement_owner,
    runtime_family_accepts_delivery,
    runtime_family_accepts_movement,
    runtime_family_required_params,
    runtime_family_required_movements,
    uses_projectile_only_item_affordance,
)
from infini_local.core.runtime_secondary_policy import normalize_secondary_trigger
from infini_local.core.runtime_authoring.structural import all_calls, find_call
from infini_local.core.runtime_authoring.result_identity import effective_runtime_result_kind
from infini_local.core.runtime_authoring.function_contract_registry import (
    ENGINE_FUNCTION_CATALOG,
    NORMALIZED_ROOT_REQUIRED_PARAM_NAMES,
    compiled_fields_for_authored_path,
    compiled_fields_for_lowered_compatibility_path,
    lowerer_contract,
    lowerer_target_source_map,
)
from infini_local.core.runtime_authoring.schema import (
    COMBAT_EXECUTOR_RESULT_KINDS,
)
from infini_local.core.boundary_models import runtime_plan_boundary_report
from infini_local.core.vfx_composition_primitives import (
    VFX_ITEM_BURST_RENDERERS,
    VFX_ITEM_LIVE_RENDERERS,
)



def _generated_buff_has_executable_effect(buff: dict[str, Any]) -> bool:
    mining = _num(buff.get("miningSpeedMultiplier"), 1.0)
    return bool(
        (mining is not None and abs(mining - 1.0) > 0.001)
        or (_num(buff.get("emitLightStrength"), 0) or 0) > 0
        or (_num(buff.get("oreSenseRadiusTiles"), 0) or 0) > 0
        or abs(_num(buff.get("movementSpeed"), 0) or 0) > 0.001
        or (_num(buff.get("jumpBoost"), 0) or 0) > 0
        or (_num(buff.get("manaRegen"), 0) or 0) > 0
        or (_num(buff.get("lifeRegen"), 0) or 0) > 0
    )


def runtime_plan_quality_report(data: dict[str, Any]) -> dict[str, Any]:
    rp = runtime_plan(data)
    calls = rp.get("engineCalls") if isinstance(rp.get("engineCalls"), list) else []
    fns = [str(c.get("fn")) for c in calls if isinstance(c, dict)]
    counts = {fn: fns.count(fn) for fn in sorted(set(fns))}
    return {
        "hasRuntimePlan": bool(rp),
        "callCount": len(fns),
        "functions": fns,
        "functionCounts": counts,
        "hasStats": "set_item_stats" in fns,
        "hasRootExecutor": "shoot_projectile" in fns,
        "hasPureVfx": "spawn_contact_particles" in fns,
        "hasRealChildren": "spawn_secondary_projectiles" in fns,
        "multiCallAware": True,
    }


def _runtime_validation_error_details(
    errors: list[str],
    calls: list[Any],
) -> list[dict[str, Any]]:
    """Map validator-owned diagnostics back to authored calls without choosing a repair."""
    indexed_calls: list[tuple[int, dict[str, Any]]] = []
    for normalized_index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            continue
        authored_index = raw_call.get("_index")
        index = authored_index if isinstance(authored_index, int) else normalized_index
        indexed_calls.append((index, raw_call))

    details: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for message in errors:
        text = str(message)
        indexed_match = re.search(
            r"engineCalls\.(\d+)(?:\.(params\.)?([A-Za-z0-9_.-]+))?",
            text,
        )
        selected: tuple[int, dict[str, Any]] | None = None
        field = ""
        field_is_param = False
        if indexed_match:
            wanted_index = int(indexed_match.group(1))
            selected = next((row for row in indexed_calls if row[0] == wanted_index), None)
            field_is_param = bool(indexed_match.group(2))
            field = str(indexed_match.group(3) or "")
        if selected is None:
            leading = [
                row
                for row in indexed_calls
                if str(row[1].get("fn") or "").strip()
                and text.startswith(str(row[1].get("fn") or "").strip())
            ]
            if len(leading) == 1:
                selected = leading[0]
        if selected is None:
            named = [
                row
                for row in indexed_calls
                if str(row[1].get("fn") or "").strip()
                and str(row[1].get("fn") or "").strip() in text
            ]
            if len(named) == 1:
                selected = named[0]
        if selected is None:
            family_match = re.search(r"runtimeFamily=([A-Za-z0-9_]+)", text)
            family = _norm_name(family_match.group(1)) if family_match else ""
            family_owned = []
            if family:
                for row in indexed_calls:
                    params_candidate = row[1].get("params")
                    params = params_candidate if isinstance(params_candidate, dict) else {}
                    authored_family = _norm_name(
                        row[1].get("runtimeFamily") or params.get("runtimeFamily")
                    )
                    if authored_family == family:
                        family_owned.append(row)
            if len(family_owned) == 1:
                selected = family_owned[0]
        if selected is None and any(token in text for token in ("root action", "root executor", "root executable")):
            selected = next(
                (row for row in indexed_calls if str(row[1].get("fn") or "") == "shoot_projectile"),
                None,
            )
        if selected is None:
            continue
        if not field:
            explicit_match = re.search(r"requires explicit ([A-Za-z0-9_.]+)", text)
            field = str(explicit_match.group(1) or "") if explicit_match else ""
            field_is_param = bool(field)
        if (
            not field
            and str(selected[1].get("fn") or "").strip() == "shoot_projectile"
            and "runtimefamily" in text.lower()
        ):
            field = "runtimeFamily"
            field_is_param = True
        index, call = selected
        call_id_value = call.get("_callId")
        if call_id_value is None:
            call_id_value = call.get("callId")
        call_id = "" if call_id_value is None else str(call_id_value).strip()
        fn = str(call.get("_rawFn") or call.get("fn") or "").strip()
        path = f"$.runtimePlan.engineCalls[{index}]"
        if field:
            path += f".params.{field}" if field_is_param else f".{field}"
        identity = (call_id, path, text)
        if identity in seen:
            continue
        seen.add(identity)
        detail: dict[str, Any] = {
            "kind": "runtime_validation",
            "path": path,
            "callId": call_id,
            "fn": fn,
            "reason": text,
        }
        if field and field_is_param:
            detail["repairParamNames"] = [field]
        details.append(detail)
    return details


def _plan_has_genuine_normalization_markers(plan: dict[str, Any]) -> bool:
    """True only for plans already shaped by normalize_runtime_plan_inplace.

    A bare user-supplied ``_normalization`` dict is not enough to skip the
    strict raw boundary (anti-spoof).
    """
    norm = plan.get("_normalization")
    if not isinstance(norm, dict):
        return False
    required_keys = (
        "api",
        "inputCallCount",
        "acceptedCallCount",
        "droppedCalls",
        "rejectedEngineCalls",
    )
    if any(key not in norm for key in required_keys):
        return False
    if not isinstance(norm.get("api"), str) or not str(norm.get("api") or "").strip():
        return False
    if not isinstance(norm.get("inputCallCount"), int) or not isinstance(norm.get("acceptedCallCount"), int):
        return False
    if not isinstance(norm.get("droppedCalls"), list) or not isinstance(norm.get("rejectedEngineCalls"), list):
        return False
    calls = plan.get("engineCalls") if isinstance(plan.get("engineCalls"), list) else []
    accepted = [call for call in calls if isinstance(call, dict)]
    if len(accepted) != int(norm["acceptedCallCount"]):
        return False
    for call in accepted:
        if not isinstance(call.get("_index"), int):
            return False
        if not str(call.get("_rawFn") or "").strip():
            return False
    return True


def _runtime_plan_anti_spoof_strict_boundary(data: dict[str, Any]) -> dict[str, Any]:
    """Strict raw boundary unless the plan already carries genuine normalize markers."""
    plan = runtime_plan(data)
    if _plan_has_genuine_normalization_markers(plan):
        return {
            "ok": True,
            "errors": [],
            "unknownParams": [],
            "typedCalls": [],
            "mode": "canonical_already_normalized",
        }
    return runtime_plan_boundary_report(data)


class _RuntimeValidationSink:
    """Lifted rejection sinks: record errors/details without nested closures."""

    __slots__ = ("errors", "warnings", "semantic_error_details", "calls")

    def __init__(
        self,
        errors: list[str],
        warnings: list[str],
        semantic_error_details: list[dict[str, Any]],
        calls: list[Any],
    ) -> None:
        self.errors = errors
        self.warnings = warnings
        self.semantic_error_details = semantic_error_details
        self.calls = calls

    def reject_call_params(
        self,
        message: str,
        fn: str,
        fields: list[str],
        *,
        call_id: str = "",
        add_error: bool = True,
    ) -> None:
        if add_error:
            self.errors.append(message)
        selected: tuple[int, dict[str, Any]] | None = None
        for normalized_index, raw_call in enumerate(self.calls):
            if not isinstance(raw_call, dict):
                continue
            raw_fn = str(raw_call.get("_rawFn") or raw_call.get("fn") or "").strip()
            normalized_fn = str(raw_call.get("fn") or "").strip()
            raw_call_id = str(raw_call.get("_callId") or raw_call.get("callId") or "").strip()
            if (raw_fn == fn or normalized_fn == fn) and (not call_id or raw_call_id == call_id):
                authored_index = raw_call.get("_index")
                selected = (
                    authored_index if isinstance(authored_index, int) else normalized_index,
                    raw_call,
                )
                break
        if selected is None:
            return
        index, raw_call = selected
        resolved_call_id = str(raw_call.get("_callId") or raw_call.get("callId") or "").strip()
        raw_fn = str(raw_call.get("_rawFn") or raw_call.get("fn") or fn).strip()
        for field in fields:
            self.semantic_error_details.append({
                "kind": "runtime_validation",
                "path": f"$.runtimePlan.engineCalls[{index}].params.{field}",
                "callId": resolved_call_id,
                "fn": raw_fn,
                "reason": message,
                "repairParamNames": [field],
            })

    def reject_structural_call(self, message: str, fn: str) -> None:
        self.errors.append(message)
        for normalized_index, raw_call in enumerate(self.calls):
            if not isinstance(raw_call, dict):
                continue
            raw_fn = str(raw_call.get("_rawFn") or raw_call.get("fn") or "").strip()
            normalized_fn = str(raw_call.get("fn") or "").strip()
            if raw_fn != fn and normalized_fn != fn:
                continue
            authored_index = raw_call.get("_index")
            index = authored_index if isinstance(authored_index, int) else normalized_index
            self.semantic_error_details.append({
                "kind": "structural_call_rejected",
                "path": f"$.runtimePlan.engineCalls[{index}]",
                "callId": str(raw_call.get("_callId") or raw_call.get("callId") or "").strip(),
                "fn": raw_fn or fn,
                "reason": message,
            })
            return


def _validate_combat_root_compile(
    data: dict[str, Any],
    rp: dict[str, Any],
    *,
    plan_kind: str,
    fns: list[Any],
    combatish: bool,
    sink: _RuntimeValidationSink,
) -> str:
    """E: combat root compile + combat set_item_stats requirements."""
    compiled_family = ""
    if not combatish:
        return compiled_family
    if "set_item_stats" not in fns:
        sink.errors.append("combat result lacks set_item_stats")
    if "shoot_projectile" not in fns:
        sink.errors.append("combat result lacks a root executable action; visual trail is not executable combat")
    else:
        compiled_patch = compile_runtime_plan_to_genome_patch(data)
        rejected_roots = compiled_patch.get("rejectedRootExecutorCalls")
        if isinstance(rejected_roots, list):
            for rejection in rejected_roots:
                if not isinstance(rejection, dict):
                    continue
                index = rejection.get("index")
                index_text = str(index) if isinstance(index, int) else "?"
                delivery = str(rejection.get("delivery") or "unknown")
                movement = str(rejection.get("movement") or "unknown")
                sink.errors.append(
                    "runtimePlan.engineCalls."
                    + index_text
                    + ": runtime supports one root executor; "
                    + f"extra root uses delivery={delivery}, movement={movement}; encode all root parameters in one call"
                )
        runtime_error_raw = str(compiled_patch.get("runtimeContractError") or "").strip()
        runtime_error = _norm_name(runtime_error_raw)
        if runtime_error_raw:
            sink.errors.append("root executable action did not compile: " + runtime_error_raw)
        if runtime_error == "root_executor_requires_runtimefamily" or not _norm_name(compiled_patch.get("runtimeFamily")) or _norm_name(compiled_patch.get("runtimeFamily")) == "none":
            sink.errors.append("combat root action lacks an executable runtimeFamily")
        for field in NORMALIZED_ROOT_REQUIRED_PARAM_NAMES:
            if field not in compiled_patch:
                sink.errors.append(f"combat root action requires explicit {field}")

        compiled_family = _norm_name(compiled_patch.get("runtimeFamily"))
        for field in runtime_family_required_params(compiled_family):
            if field not in compiled_patch:
                sink.errors.append(f"combat runtimeFamily={compiled_family} requires explicit {field}")
        if compiled_family == "overhead_barrage" and (_num(compiled_patch.get("secondaryDamageMultiplier"), 0) or 0) <= 0:
            sink.errors.append("combat runtimeFamily=overhead_barrage requires secondaryDamageMultiplier > 0")
        if compiled_family == "overhead_barrage":
            base_damage = _num(find_call(rp, "set_item_stats").get("damage"), 0) or 0
            child_multiplier = _num(compiled_patch.get("secondaryDamageMultiplier"), 0) or 0
            if base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
                sink.errors.append("combat runtimeFamily=overhead_barrage rounds to zero damage; increase damage or secondaryDamageMultiplier")
        single_runtime_families = set(HELD_PROJECTILE_RUNTIME_FAMILIES) - {"charge_release"}
        single_runtime_shots = _num(compiled_patch.get("shotCount"), None)
        if compiled_family in single_runtime_families and single_runtime_shots is not None and single_runtime_shots != 1:
            sink.errors.append(f"combat runtimeFamily={compiled_family} requires shotCount=1; its executor owns one runtime root")
        if compiled_family in {"swing", "thrust"}:
            for secondary_call in all_calls(rp, "spawn_secondary_projectiles"):
                if (_num(secondary_call.get("count"), 0) or 0) <= 0:
                    continue
                has_child_body = bool(_norm_name(secondary_call.get("material")) or _norm_name(secondary_call.get("projectileShape")))
                if not has_child_body:
                    sink.errors.append(f"combat runtimeFamily={compiled_family} secondary projectiles require explicit material or projectileShape")
                trigger = normalize_secondary_trigger(secondary_call.get("trigger"))
                if compiled_family == "swing" and trigger == "on_expire":
                    sink.errors.append("combat runtimeFamily=swing cannot execute secondary trigger=on_expire; use on_hit")
    stats_call = find_call(rp, "set_item_stats")
    for field in ("damageClass", "damage", "useTimeTicks"):
        if field not in stats_call:
            sink.errors.append(f"combat set_item_stats requires explicit {field}")
    if compiled_family == "whip" and _norm_name(stats_call.get("damageClass")) != "summon_melee_speed":
        sink.reject_call_params(
            "combat runtimeFamily=whip requires damageClass=summon_melee_speed",
            "set_item_stats",
            ["damageClass"],
        )
    damage = _num(stats_call.get("damage"))
    if damage is not None and damage <= 0:
        sink.reject_call_params(
            "combat set_item_stats requires positive damage; use a non-combat resultKind for pure utility",
            "set_item_stats",
            ["damage"],
        )
    return compiled_family


def _validate_economy_and_ammo_identity(
    rp: dict[str, Any],
    *,
    result_kind: str,
    stats: dict[str, Any],
    max_stack: float | int,
    craft_yield: float | int,
    authored_consumable: bool,
    stack_consumption_authored: bool,
    consume_call: dict[str, Any],
    has_root_executor: bool,
    sink: _RuntimeValidationSink,
) -> None:
    """H: stack/yield economy + consumable_weapon markers + ammo identity."""
    if result_kind in {"ammo", "consumable_weapon"}:
        if max_stack <= 0 or craft_yield <= 0:
            stack_message = f"{result_kind} result requires explicit positive maxStack and craftYield"
            stack_fields: list[str] = []
            if max_stack <= 0:
                stack_fields.append("maxStack")
            if craft_yield <= 0:
                stack_fields.append("craftYield")
            sink.reject_call_params(stack_message, "set_item_stats", stack_fields)
        elif max(max_stack, craft_yield) < 25:
            if result_kind == "ammo":
                sink.warnings.append("ammo output has low stack/yield; playable ammo should usually output 25+")
            else:
                sink.warnings.append(
                    f"{result_kind} output has low stack/yield; playable ammo should usually output 25+"
                )
    reusable_gear_kinds = {"weapon", "tool", "armor", "accessory"}
    if result_kind in reusable_gear_kinds and stack_consumption_authored:
        economy_error = (
            f"invalid_result_kind: reusable {result_kind} requires consumable=false, maxStack=1, craftYield=1, and no consumption_behavior"
        )
        economy_fields: list[str] = []
        if authored_consumable:
            economy_fields.append("consumable")
        if max_stack != 1:
            economy_fields.append("maxStack")
        if craft_yield != 1:
            economy_fields.append("craftYield")
        sink.reject_call_params(economy_error, "set_item_stats", economy_fields)
        if (_num(consume_call.get("consumeChancePercent"), 0) or 0) > 0:
            sink.reject_call_params(
                economy_error,
                "consumption_behavior",
                ["consumeChancePercent"],
                add_error=False,
            )
    if result_kind == "consumable_weapon":
        if not authored_consumable:
            sink.reject_call_params(
                "consumable_weapon set_item_stats requires explicit consumable=true",
                "set_item_stats",
                ["consumable"],
            )
        if max_stack <= 1:
            sink.reject_call_params(
                "consumable_weapon set_item_stats requires explicit maxStack > 1",
                "set_item_stats",
                ["maxStack"],
            )
    ammo_behavior = find_call(rp, "ammo_behavior")
    ammo_for = _norm_name(stats.get("ammoFor") or ammo_behavior.get("ammoFor"))
    if result_kind == "ammo":
        if ammo_for not in {"arrow", "bullet"}:
            sink.errors.append("ammo result requires vanilla arrow or bullet identity; custom projectile stacks use consumable_weapon")
        if has_root_executor:
            sink.errors.append("actual ammo cannot author a generated root executor; use consumable_weapon or weapon")
        if "damageClass" not in stats or not str(stats.get("damageClass") or "").strip():
            sink.errors.append("actual ammo requires explicit damageClass")
        if "damage" not in stats or (_num(stats.get("damage"), -1) or 0) < 0:
            sink.errors.append("actual ammo requires explicit non-negative damage")


def _validate_effect_and_alt_calls(
    rp: dict[str, Any],
    *,
    stats: dict[str, Any],
    sink: _RuntimeValidationSink,
) -> None:
    """I+J: every apply_on_hit_effect, apply_player_effect_on_use, set_alt_use_mode."""
    for hit in all_calls(rp, "apply_on_hit_effect"):
        onhit = _norm_name(hit.get("onHit"))
        aoe = _num(hit.get("aoeRadiusTiles"), 0) or 0
        if onhit in {"burst", "starburst", "blackhole", "radial_beams", "mini_missiles", "vortex_spawn"} and aoe > 10:
            sink.warnings.append("impact AoE exceeds executable range; runtime will clamp")
        buff_onhits = {"chain", "burn", "frostburn", "poison", "shadowflame", "bleed", "spore_cloud", "lightning_arc", "slow"}
        if onhit in buff_onhits and (_num(hit.get("debuffTime"), 0) or 0) <= 0:
            sink.errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit debuffTime")
        child_projectile_onhits = {
            "split", "chain", "starburst", "spore_cloud", "mini_missiles",
            "vortex_spawn", "radial_beams", "lightning_arc", "overhead_barrage",
        }
        if onhit in child_projectile_onhits:
            authored_child_count = (
                _num(hit.get("chainCount"), 0) or _num(hit.get("count"), 0) or 0
                if onhit in {"chain", "lightning_arc"}
                else _num(hit.get("count"), 0) or 0
            )
            if authored_child_count <= 0:
                sink.errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit count > 0")
            child_multiplier = _num(hit.get("secondaryDamageMultiplier"), 0) or 0
            if child_multiplier <= 0:
                sink.errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit secondaryDamageMultiplier > 0")
            if (_num(hit.get("secondaryLifetimeTicks"), 0) or 0) <= 0:
                sink.errors.append(f"apply_on_hit_effect onHit={onhit} requires explicit secondaryLifetimeTicks")
            base_damage = _num(stats.get("damage"), 0) or 0
            if base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
                sink.errors.append(f"apply_on_hit_effect onHit={onhit} rounds to zero damage; increase damage or secondaryDamageMultiplier")

    for use_effect in all_calls(rp, "apply_player_effect_on_use"):
        raw_buffs_value = use_effect.get("buffs")
        raw_buffs: list[Any] = raw_buffs_value if isinstance(raw_buffs_value, list) else []
        if use_effect.get("buffType") not in (None, ""):
            raw_buffs = [*raw_buffs, {"buffType": use_effect.get("buffType"), "buffTime": use_effect.get("buffTime")}]
        for buff in raw_buffs:
            if isinstance(buff, dict) and (_num(buff.get("buffType"), 0) or 0) > 0 and (_num(buff.get("buffTime"), 0) or 0) <= 0:
                sink.errors.append("apply_player_effect_on_use buffType requires explicit positive buffTime")
        generated_value = use_effect.get("generatedBuff")
        generated: dict[str, Any] = generated_value if isinstance(generated_value, dict) else {}
        if generated and (_num(generated.get("durationTicks") or use_effect.get("durationTicks"), 0) or 0) <= 0:
            sink.errors.append("apply_player_effect_on_use generatedBuff requires explicit durationTicks")
        if generated and not _generated_buff_has_executable_effect(generated):
            sink.errors.append("apply_player_effect_on_use generatedBuff requires at least one executable effect")
        direct_heal = max(
            _num(use_effect.get("healLife"), 0) or 0,
            _num(use_effect.get("healMana"), 0) or 0,
        ) > 0
        executable_buff = any(
            isinstance(buff, dict)
            and (_num(buff.get("buffType"), 0) or 0) > 0
            and (_num(buff.get("buffTime"), 0) or 0) > 0
            for buff in raw_buffs
        )
        if not (direct_heal or executable_buff or _generated_buff_has_executable_effect(generated)):
            sink.errors.append(
                "apply_player_effect_on_use requires at least one executable heal, buff, or generatedBuff effect"
            )

    for alt in all_calls(rp, "set_alt_use_mode"):
        mode = _norm_name(alt.get("mode"))
        if mode not in {"mobility", "generated_buff", "light"}:
            sink.errors.append("set_alt_use_mode requires executable mode=mobility|generated_buff|light")
        mobility_mode = _norm_name(alt.get("mobilityMode"))
        generated_value = alt.get("generatedBuff")
        generated = generated_value if isinstance(generated_value, dict) else {}
        duration = _num(generated.get("durationTicks") or alt.get("durationTicks"), 0) or 0
        if (generated or mode == "light") and duration <= 0:
            sink.errors.append(f"set_alt_use_mode mode={mode or 'unknown'} requires explicit durationTicks")
        if mode == "generated_buff" and (not generated or not _generated_buff_has_executable_effect(generated)):
            sink.errors.append("set_alt_use_mode mode=generated_buff requires an executable generatedBuff effect")
        if mode == "generated_buff" and (_num(alt.get("cooldownTicks"), 0) or 0) <= 0:
            sink.reject_call_params(
                f"set_alt_use_mode mode={mode} requires explicit positive cooldownTicks",
                "set_alt_use_mode",
                ["cooldownTicks"],
            )
        if mode == "light":
            light_calls = all_calls(rp, "emit_light")
            light_strength = max((_num(call.get("strength"), 0) or 0) for call in light_calls) if light_calls else 0
            if light_strength <= 0:
                sink.errors.append("set_alt_use_mode mode=light requires positive emit_light strength")
        if mode == "mobility" and mobility_mode not in {"recall_home", "blink_to_cursor"}:
            sink.errors.append("set_alt_use_mode mode=mobility requires explicit mobilityMode=recall_home|blink_to_cursor")
        if mode == "mobility" and mobility_mode == "blink_to_cursor" and (_num(alt.get("rangeTiles"), 0) or 0) <= 0:
            sink.errors.append("set_alt_use_mode blink_to_cursor requires explicit positive rangeTiles")


def _validate_secondary_particles_and_structural(
    rp: dict[str, Any],
    *,
    combatish: bool,
    fns: list[Any],
    result_kind: str,
    stats: dict[str, Any],
    sink: _RuntimeValidationSink,
) -> tuple[bool, float | int, float | int, bool, bool, dict[str, Any]]:
    """F: secondary/particles + root/family/equipment structural ownership."""
    for secondary in all_calls(rp, "spawn_secondary_projectiles"):
        count = _num(secondary.get("count"), 0) or 0
        trigger = normalize_secondary_trigger(secondary.get("trigger"))
        if count <= 0:
            sink.warnings.append("spawn_secondary_projectiles present with count<=0")
        if count > 8:
            sink.warnings.append("secondary projectile count exceeds executable adapter range; runtime will clamp")
        if not trigger:
            sink.warnings.append("secondary projectile trigger is unsupported; use exact on_hit or on_expire")
        base_damage = _num(find_call(rp, "set_item_stats").get("damage"), 0) or 0
        child_multiplier = _num(secondary.get("damageMultiplier"), 0) or 0
        if combatish and count > 0 and base_damage > 0 and child_multiplier > 0 and int(base_damage * child_multiplier) < 1:
            sink.errors.append("spawn_secondary_projectiles rounds to zero damage; increase damage or damageMultiplier")
    particle_materials = {
        _norm_name(call.get("material"))
        for call in all_calls(rp, "spawn_contact_particles")
        if (_num(call.get("amount"), 0) or 0) > 0 and _norm_name(call.get("material")) not in {"", "none"}
    }
    if len(particle_materials) > 1:
        sink.errors.append("spawn_contact_particles requires one exact material per runtime plan")
    for particle_call in all_calls(rp, "spawn_contact_particles"):
        material = _norm_name(particle_call.get("material"))
        effect_name = _norm_name(particle_call.get("effect"))
        if (_num(particle_call.get("amount"), 0) or 0) > 0 and material not in {"", "none"} and effect_name not in {"", "none", "dust"}:
            sink.reject_call_params(
                "spawn_contact_particles material is executable only with effect=none|dust",
                "spawn_contact_particles",
                ["effect", "material"],
            )
    max_stack = _num(stats.get("maxStack"), 0) or 0
    craft_yield = _num(stats.get("craftYield"), 0) or 0
    consume_call = find_call(rp, "consumption_behavior")
    authored_consumable = stats.get("consumable") is True
    stack_consumption_authored = (
        authored_consumable
        or max_stack > 1
        or craft_yield > 1
        or (_num(consume_call.get("consumeChancePercent"), 0) or 0) > 0
    )
    root_executors = all_calls(rp, "shoot_projectile")
    has_root_executor = bool(root_executors)
    for fn in sorted({str(fn) for fn in fns}):
        spec = ENGINE_FUNCTION_CATALOG.get(fn)
        if (
            isinstance(spec, dict)
            and spec.get("requiresRootExecutor") is True
            and not has_root_executor
        ):
            sink.reject_structural_call(
                f"{fn} requires one executable root executor",
                fn,
            )
    # set_item_stats.defense is armor-only. Positive values on non-armor kinds fail
    # closed; accessory defense lives on accessory_effect.defense. Neutral zero may
    # remain as a dormant required sentinel without enabling armor semantics.
    defense_raw = stats.get("defense")
    if result_kind and result_kind != "armor" and defense_raw not in (None, ""):
        defense_value = _num(defense_raw, 0) or 0
        if defense_value > 0:
            if result_kind == "accessory":
                defense_message = (
                    "set_item_stats.defense is armor-only; use accessory_effect.defense for accessory"
                )
            else:
                defense_message = (
                    f"set_item_stats.defense is armor-only; resultKind={result_kind} "
                    "must not author positive defense"
                )
            sink.reject_call_params(defense_message, "set_item_stats", ["defense"])
    if result_kind in {"weapon", "consumable_weapon"} and not has_root_executor:
        sink.errors.append(f"{result_kind} result requires one root executable action")
    if has_root_executor:
        root = root_executors[0]
        family = _norm_name(root.get("runtimeFamily"))
        delivery = _norm_name(root.get("delivery"))
        movement = _norm_name(root.get("movement"))
        if family in RUNTIME_FAMILIES and not runtime_family_accepts_delivery(family, delivery):
            sink.reject_call_params(
                f"shoot_projectile runtimeFamily={family} rejects delivery={delivery or 'missing'}",
                "shoot_projectile",
                ["runtimeFamily", "delivery"],
            )
        if family in RUNTIME_FAMILIES and not runtime_family_accepts_movement(family, movement):
            required = runtime_family_required_movements(family)
            owner = exclusive_movement_owner(movement)
            if required:
                expected = "|".join(sorted(required))
                reason = f"runtimeFamily={family} requires movement={expected}, got {movement or 'missing'}"
            else:
                reason = f"movement={movement or 'missing'} requires runtimeFamily={owner or 'matching owner'}, got {family or 'missing'}"
            sink.reject_call_params(
                reason,
                "shoot_projectile",
                ["runtimeFamily", "delivery", "movement"],
            )
    if result_kind == "accessory" and not all_calls(rp, "accessory_effect"):
        sink.errors.append("accessory result requires accessory_effect")
    if result_kind == "armor" and not all_calls(rp, "armor_effect"):
        sink.errors.append("armor result requires armor_effect")
    if result_kind == "accessory" and all_calls(rp, "armor_effect"):
        sink.reject_structural_call("accessory result rejects armor_effect; remove the armor call", "armor_effect")
    if result_kind == "armor" and all_calls(rp, "accessory_effect"):
        sink.reject_structural_call("armor result rejects accessory_effect; remove the accessory call", "accessory_effect")
    if result_kind in {"armor", "accessory"} and stats.get("autoReuse") is True:
        sink.reject_call_params(
            f"{result_kind} result requires set_item_stats autoReuse=false",
            "set_item_stats",
            ["autoReuse"],
        )
    if result_kind != "furniture" and all_calls(rp, "placeable_behavior"):
        sink.reject_structural_call(
            f"placeable_behavior requires resultKind=furniture, got {result_kind or 'missing'}",
            "placeable_behavior",
        )
    if result_kind in {"armor", "accessory"} and all_calls(rp, "emit_light"):
        owner = "armor_effect.stats" if result_kind == "armor" else "accessory_effect.stats"
        sink.errors.append(
            f"emit_light is not executable for resultKind={result_kind}; author equipment light in {owner}"
        )
    return (
        has_root_executor,
        max_stack,
        craft_yield,
        authored_consumable,
        stack_consumption_authored,
        consume_call,
    )


def _validate_visual_effect_cues(
    rp: dict[str, Any],
    *,
    result_kind: str,
    sink: _RuntimeValidationSink,
) -> None:
    """G: visual_effect_cue event/renderer ownership (inline-capable block kept private)."""
    item_live_renderers = VFX_ITEM_LIVE_RENDERERS
    item_burst_renderers = VFX_ITEM_BURST_RENDERERS
    for cue in all_calls(rp, "visual_effect_cue"):
        event = str(cue.get("event") or "").strip()
        renderer = str(cue.get("rendererKind") or "").strip()
        cue_call_id = str(cue.get("_callId") or cue.get("callId") or "").strip()
        if event == "while_equipped":
            if result_kind not in {"armor", "accessory"}:
                sink.reject_call_params(
                    "visual_effect_cue event=while_equipped requires resultKind=armor|accessory",
                    "visual_effect_cue",
                    ["event"],
                    call_id=cue_call_id,
                )
            if renderer not in item_live_renderers:
                sink.reject_call_params(
                    f"visual_effect_cue event=while_equipped rejects rendererKind={renderer or 'missing'}",
                    "visual_effect_cue",
                    ["event", "rendererKind", "channel"],
                    call_id=cue_call_id,
                )
        elif event == "while_held":
            if result_kind in {"armor", "accessory", "ammo", "material"}:
                sink.reject_call_params(
                    f"visual_effect_cue event=while_held is not executable for resultKind={result_kind}",
                    "visual_effect_cue",
                    ["event"],
                    call_id=cue_call_id,
                )
            if renderer not in item_live_renderers:
                sink.reject_call_params(
                    f"visual_effect_cue event=while_held rejects rendererKind={renderer or 'missing'}",
                    "visual_effect_cue",
                    ["event", "rendererKind", "channel"],
                    call_id=cue_call_id,
                )
        elif event in {"on_use", "on_alt_use"}:
            if result_kind in {"armor", "accessory", "ammo", "material"}:
                sink.reject_call_params(
                    f"visual_effect_cue event={event} is not executable for resultKind={result_kind}",
                    "visual_effect_cue",
                    ["event"],
                    call_id=cue_call_id,
                )
            if renderer not in item_burst_renderers:
                sink.reject_call_params(
                    f"visual_effect_cue event={event} rejects rendererKind={renderer or 'missing'}",
                    "visual_effect_cue",
                    ["event", "rendererKind", "channel"],
                    call_id=cue_call_id,
                )


def _validate_mobility_hold_and_kind_executors(
    rp: dict[str, Any],
    *,
    result_kind: str,
    stats: dict[str, Any],
    sink: _RuntimeValidationSink,
) -> None:
    """K+L: mobility/hold plus tool/furniture/accessory/armor/potion executability."""
    for mobility in all_calls(rp, "mobility_effect"):
        mode = _norm_name(mobility.get("mode"))
        if mode not in {"recall_home", "blink_to_cursor", "blink_to_projectile_impact"}:
            sink.errors.append("mobility_effect requires an explicit supported mobility mode")
        if mode in {"blink_to_cursor", "blink_to_projectile_impact"} and (_num(mobility.get("rangeTiles"), 0) or 0) <= 0:
            sink.errors.append(f"mobility_effect mode={mode} requires explicit positive rangeTiles")

    for hold in all_calls(rp, "hold_item_effect"):
        generated_raw = hold.get("generatedBuff")
        generated: dict[str, Any] = generated_raw if isinstance(generated_raw, dict) else {}
        if generated:
            hold_duration = _num(generated.get("durationTicks"), 0) or 0
            if hold_duration <= 0:
                sink.errors.append("hold_item_effect generatedBuff requires explicit durationTicks")
            elif hold_duration < 2:
                sink.errors.append("hold_item_effect generatedBuff durationTicks must be at least 2 ticks so the next effect phase can execute it")
            if not _generated_buff_has_executable_effect(generated):
                sink.errors.append("hold_item_effect generatedBuff requires at least one executable effect")

    if result_kind == "tool":
        tool = find_call(rp, "tool_capability")
        if max((_num(tool.get(name), 0) or 0) for name in ("pickPower", "axePower", "hammerPower")) <= 0:
            sink.errors.append("tool result lacks explicit executable tool_capability")
    elif result_kind == "furniture":
        placeable = find_call(rp, "placeable_behavior")
        create_tile = _num(placeable.get("createTile"), -1)
        create_wall = _num(placeable.get("createWall"), -1)
        if (create_tile is None or create_tile < 0) and (create_wall is None or create_wall < 0):
            sink.errors.append("furniture result lacks explicit executable placeable_behavior createTile/createWall")
        stats_call = find_call(rp, "set_item_stats")
        if stats_call.get("consumable") is not True:
            sink.reject_call_params(
                "placeable furniture requires set_item_stats consumable=true",
                "set_item_stats",
                ["consumable"],
            )
        if (_num(stats_call.get("maxStack"), 0) or 0) <= 1:
            sink.reject_call_params(
                "placeable furniture requires set_item_stats maxStack>1",
                "set_item_stats",
                ["maxStack"],
            )
    elif result_kind == "accessory":
        accessory = find_call(rp, "accessory_effect")
        stats_obj_candidate = accessory.get("stats")
        stats_obj: dict[str, Any] = stats_obj_candidate if isinstance(stats_obj_candidate, dict) else {}
        if (_num(stats_obj.get("lightStrength"), 0) or 0) > 0 and not str(stats_obj.get("lightColorName") or "").strip():
            sink.reject_call_params(
                "accessory_effect stats.lightStrength requires explicit lightColorName",
                "accessory_effect",
                ["stats.lightColorName"],
            )
        if not any(value not in (None, "", 0, 0.0, False) for value in stats_obj.values()):
            sink.errors.append("accessory result lacks explicit executable accessory_effect.stats")
    elif result_kind == "armor":
        armor = find_call(rp, "armor_effect")
        slot = _norm_name(armor.get("armorSlot") or stats.get("armorSlot"))
        armor_stats_candidate = armor.get("stats")
        armor_stats: dict[str, Any] = armor_stats_candidate if isinstance(armor_stats_candidate, dict) else {}
        if (_num(armor_stats.get("lightStrength"), 0) or 0) > 0 and not str(armor_stats.get("lightColorName") or "").strip():
            sink.reject_call_params(
                "armor_effect stats.lightStrength requires explicit lightColorName",
                "armor_effect",
                ["stats.lightColorName"],
            )
        set_bonus = armor.get("setBonus") if isinstance(armor.get("setBonus"), dict) else {}
        defense = _num(armor.get("defense", stats.get("defense")), 0) or 0
        if slot not in {"head", "body", "legs"}:
            sink.errors.append("armor result requires explicit armorSlot=head|body|legs")
        if defense <= 0 and not any(value not in (None, "", 0, 0.0, False) for value in [*armor_stats.values(), *set_bonus.values()]):
            sink.errors.append("armor result lacks explicit defense/stat/set-bonus effect")
    elif result_kind == "potion":
        use_calls = all_calls(rp, "apply_player_effect_on_use")
        heal = max((_num(stats.get("healLife"), 0) or 0), (_num(stats.get("healMana"), 0) or 0))
        buff_type = _num(stats.get("buffType"), 0) or 0
        if heal <= 0 and buff_type <= 0 and not use_calls:
            sink.errors.append("potion result lacks an explicit executable use effect")


def _finalize_runtime_validation_report(
    *,
    errors: list[str],
    warnings: list[str],
    semantic_error_details: list[dict[str, Any]],
    calls: list[Any],
    q: dict[str, Any],
    norm: dict[str, Any],
    boundary: dict[str, Any],
) -> dict[str, Any]:
    """Semantic-details-first finalization shared by the public entrypoint."""
    semantic_reasons = {
        str(detail.get("reason") or "")
        for detail in semantic_error_details
    }
    derived_error_details = [
        detail
        for detail in _runtime_validation_error_details(errors, calls)
        if str(detail.get("reason") or "") not in semantic_reasons
    ]
    error_details = semantic_error_details + derived_error_details
    detailed_reasons = {str(detail.get("reason") or "") for detail in error_details}
    for message in errors:
        if message in detailed_reasons:
            continue
        error_details.append({
            "kind": "runtime_validation",
            "path": "$.runtimePlan.engineCalls",
            "reason": message,
        })
    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "ok": not errors,
        "errors": errors,
        "errorDetails": error_details,
        "warnings": warnings,
        "quality": q,
        "normalization": norm,
        "strictBoundary": boundary,
    }


def runtime_plan_validation_report(data: dict[str, Any]) -> dict[str, Any]:
    """Validate authoring plan as an interface contract, not as a game-design judge.

    The strict per-function boundary applies to raw authoring calls.  Semantic
    normalization deliberately lowers high-level calls such as deploy_sentry to
    canonical shoot_projectile rows with compiler-owned fields; those rows must
    not be reinterpreted as raw model output on a second validation pass.

    Ordered rule blocks: E combat root → F structural → G VFX → H economy/ammo →
    I+J effects/alt → K+L mobility/hold/kind. Semantic details finalize first.
    """
    boundary = _runtime_plan_anti_spoof_strict_boundary(data)
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    errors: list[str] = list(boundary.get("errors") or [])
    warnings: list[str] = []
    semantic_error_details: list[dict[str, Any]] = []
    sink = _RuntimeValidationSink(errors, warnings, semantic_error_details, calls)

    fns = q.get("functions") or []
    fn_list: list[Any] = list(fns) if isinstance(fns, list) else []
    counts = q.get("functionCounts") if isinstance(q.get("functionCounts"), dict) else {}
    if counts.get("shoot_projectile", 0) > 1:
        warnings.append(
            "multiple root executor calls supplied; runtime executes the first and rejects every extra root; encode multi-shot in one call"
        )
    if counts.get("set_item_stats", 0) > 1:
        stats_owners = [
            (normalized_index, raw_call)
            for normalized_index, raw_call in enumerate(calls)
            if isinstance(raw_call, dict)
            and str(raw_call.get("fn") or "").strip() == "set_item_stats"
        ]
        for normalized_index, raw_call in stats_owners[1:]:
            authored_index = raw_call.get("_index")
            index = authored_index if isinstance(authored_index, int) else normalized_index
            errors.append(
                f"runtimePlan.engineCalls.{index}: multiple set_item_stats calls supplied; "
                "exactly one item-stat owner is required"
            )
    if not rp:
        errors.append("missing runtimePlan")
    elif not calls:
        errors.append("runtimePlan.engineCalls has no accepted executable calls")
    norm = rp.get("_normalization") if isinstance(rp.get("_normalization"), dict) else {}
    if norm.get("droppedCalls"):
        warnings.append("some engineCalls were dropped as unknown/non-object")
    if norm.get("rejectedEngineCalls"):
        warnings.append("some engineCalls were hard-rejected by safety policy")

    stats_kind = _norm_name(find_call(rp, "set_item_stats").get("resultKind"))
    plan_kind = _norm_name(rp.get("resultKind"))
    authored_category = _norm_name(data.get("category"))
    if plan_kind and stats_kind and plan_kind != stats_kind:
        errors.append(
            f"runtimePlan.resultKind={plan_kind} disagrees with set_item_stats.resultKind={stats_kind}"
        )
    runtime_kind = effective_runtime_result_kind(data)
    projected_category = "weapon" if runtime_kind == "consumable_weapon" else runtime_kind
    if authored_category and projected_category and authored_category != projected_category:
        errors.append(
            f"category={authored_category} disagrees with canonical category={projected_category} "
            f"for authored runtime resultKind={runtime_kind}"
        )
    plan_kind = runtime_kind
    combat_call_functions = sorted({
        str(fn)
        for fn in fn_list
        if str(fn) in {
            "shoot_projectile",
            "apply_on_hit_effect",
            "spawn_secondary_projectiles",
        }
    })
    root_call = find_call(rp, "shoot_projectile")
    root_family = _norm_name(root_call.get("runtimeFamily"))
    root_delivery = _norm_name(root_call.get("delivery"))
    tool_body_executor = bool(
        plan_kind == "tool"
        and "tool_capability" in fn_list
        and root_delivery == "swing"
        and root_family in {"swing", "shoot", "overhead_barrage"}
        and not uses_projectile_only_item_affordance(root_family, root_delivery)
    )
    if (
        plan_kind
        and plan_kind not in COMBAT_EXECUTOR_RESULT_KINDS
        and not tool_body_executor
        and combat_call_functions
    ):
        errors.append(
            "executor_not_representable: "
            + f"resultKind={plan_kind} cannot execute combat engine calls: "
            + ",".join(combat_call_functions)
        )
    combatish = (
        str(data.get("category") or data.get("gameplay", {}).get("kind") or plan_kind or "").lower()
        in {"weapon", "summon"}
        or plan_kind == "consumable_weapon"
        or tool_body_executor
        or bool((data.get("attack") or {}).get("enabled") if isinstance(data.get("attack"), dict) else False)
    )

    # E
    _validate_combat_root_compile(
        data, rp, plan_kind=plan_kind, fns=fn_list, combatish=combatish, sink=sink,
    )
    stats = find_call(rp, "set_item_stats")
    result_kind = effective_runtime_result_kind(data)
    # F
    (
        has_root_executor,
        max_stack,
        craft_yield,
        authored_consumable,
        stack_consumption_authored,
        consume_call,
    ) = _validate_secondary_particles_and_structural(
        rp,
        combatish=combatish,
        fns=fn_list,
        result_kind=result_kind,
        stats=stats,
        sink=sink,
    )
    # G (VFX may stay inline conceptually; private helper preserves order)
    _validate_visual_effect_cues(rp, result_kind=result_kind, sink=sink)
    # H
    _validate_economy_and_ammo_identity(
        rp,
        result_kind=result_kind,
        stats=stats,
        max_stack=max_stack,
        craft_yield=craft_yield,
        authored_consumable=authored_consumable,
        stack_consumption_authored=stack_consumption_authored,
        consume_call=consume_call,
        has_root_executor=has_root_executor,
        sink=sink,
    )
    # I+J
    _validate_effect_and_alt_calls(rp, stats=stats, sink=sink)
    # K+L
    _validate_mobility_hold_and_kind_executors(
        rp, result_kind=result_kind, stats=stats, sink=sink,
    )
    return _finalize_runtime_validation_report(
        errors=errors,
        warnings=warnings,
        semantic_error_details=semantic_error_details,
        calls=calls,
        q=q,
        norm=norm if isinstance(norm, dict) else {},
        boundary=boundary,
    )



def compiled_fields_for_authored_param(fn: str, authored_param: str) -> frozenset[str]:
    """Return compiler fields attributed by the canonical typed contract."""

    return compiled_fields_for_authored_path(fn, authored_param)


def compiled_fields_for_authored_call(
    fn: str,
    params: dict[str, Any],
    authored_param: str,
    *,
    normalized_fn: str = "",
    normalized_params: dict[str, Any] | None = None,
) -> frozenset[str]:
    """Resolve exact per-call ownership from typed lowerer bindings.

    This executes the declared lowerer at most once when a normalized row is not
    already available.  It never mutates values or probes counterfactual calls.
    """

    canonical_fn = _norm_name(fn)
    if lowerer_contract(canonical_fn) is None:
        direct = compiled_fields_for_authored_path(canonical_fn, authored_param)
        if direct:
            return direct
        # Corpus v1 and old accepted dumps sometimes persisted a post-lowering
        # target call with source aliases still present.  Resolve those aliases from
        # the canonical incoming lowerer graph rather than keeping a manual shadow
        # map in provenance.
        return compiled_fields_for_lowered_compatibility_path(
            canonical_fn,
            authored_param,
            normalized_params if isinstance(normalized_params, dict) else params,
        )

    lowered_rows: list[tuple[str, dict[str, Any]]]
    if normalized_fn and isinstance(normalized_params, dict):
        lowered_rows = [(_norm_name(normalized_fn), normalized_params)]
    else:
        from infini_local.core.runtime_authoring.semantics import _lower_typed_engine_call
        lowered_rows = _lower_typed_engine_call(canonical_fn, params)

    resolved: set[str] = set()
    for target_fn, target_params in lowered_rows:
        owners = lowerer_target_source_map(canonical_fn, target_fn, params, target_params)
        for target_path, source_path in owners.items():
            if source_path == authored_param:
                resolved.update(compiled_fields_for_authored_path(target_fn, target_path))
    return frozenset(resolved)


def _iter_authored_param_leaves(params: dict[str, Any]) -> list[tuple[str, Any]]:
    pending: list[tuple[str, Any]] = [(str(key), value) for key, value in params.items()]
    out: list[tuple[str, Any]] = []
    while pending:
        param_path, authored_value = pending.pop(0)
        if str(param_path).startswith("_"):
            continue
        if isinstance(authored_value, dict):
            pending[0:0] = [
                (f"{param_path}.{child_key}", child_value)
                for child_key, child_value in authored_value.items()
            ]
            continue
        if authored_value is None:
            continue
        if isinstance(authored_value, str) and not authored_value.strip():
            continue
        if isinstance(authored_value, list) and not authored_value:
            continue
        if isinstance(authored_value, (str, bool, int, float, list)):
            out.append((param_path, authored_value))
    return out


def _authored_call_identity(raw: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the exact public call before typed lowering, when available."""

    normalized_fn = _norm_name(raw.get("fn"))
    authored_fn = _norm_name(raw.get("_authoredFn") or raw.get("_rawFn") or normalized_fn)
    authored_params_candidate = raw.get("_authoredParams")
    if isinstance(authored_params_candidate, dict):
        authored_params = authored_params_candidate
    else:
        params_candidate = raw.get("params")
        authored_params = params_candidate if isinstance(params_candidate, dict) else {}
    return authored_fn, authored_params


def _authored_field_map(data_or_plan: dict[str, Any]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Map compiled fields to the original typed function and public params."""

    rp = data_or_plan if isinstance(data_or_plan.get("engineCalls"), list) else runtime_plan(data_or_plan)
    authored: dict[str, str] = {}
    authored_by_fn: dict[str, list[str]] = {}
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    for raw in calls:
        if not isinstance(raw, dict):
            continue
        authored_fn, authored_params = _authored_call_identity(raw)
        if not authored_fn:
            continue
        normalized_fn = _norm_name(raw.get("fn"))
        normalized_params_candidate = raw.get("params")
        normalized_params = normalized_params_candidate if isinstance(normalized_params_candidate, dict) else {}
        fields = set(compiled_fields_for_authored_call(
            authored_fn,
            authored_params,
            "$function",
            normalized_fn=normalized_fn,
            normalized_params=normalized_params,
        ))
        for param_path, _ in _iter_authored_param_leaves(authored_params):
            fields.update(compiled_fields_for_authored_call(
                authored_fn,
                authored_params,
                param_path,
                normalized_fn=normalized_fn,
                normalized_params=normalized_params,
            ))
        for compiled_field in fields:
            authored[compiled_field] = authored_fn
            authored_by_fn.setdefault(authored_fn, []).append(compiled_field)
    authored_by_fn = {fn: sorted(set(fields)) for fn, fields in authored_by_fn.items()}
    return authored, authored_by_fn


def runtime_plan_provenance_report(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explain authored-vs-applied runtime fields so VFX is not confused with gameplay."""
    normalize_runtime_plan_inplace(data)
    rp = runtime_plan(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    calls_candidate = rp.get("engineCalls")
    calls: list[Any] = calls_candidate if isinstance(calls_candidate, list) else []
    fns = [str(c.get("fn") or "") for c in calls if isinstance(c, dict)]
    authored_sources, authored_by_fn = _authored_field_map(rp)
    authored_parameters: list[dict[str, Any]] = []
    for call_index, raw_call in enumerate(calls):
        if not isinstance(raw_call, dict):
            continue
        authored_fn, authored_params = _authored_call_identity(raw_call)
        call_id = str(raw_call.get("callId") or f"call_{call_index}")
        for param_path, authored_value in _iter_authored_param_leaves(authored_params):
            normalized_fn = _norm_name(raw_call.get("fn"))
            normalized_params_candidate = raw_call.get("params")
            normalized_params = normalized_params_candidate if isinstance(normalized_params_candidate, dict) else {}
            compiled_fields = sorted(compiled_fields_for_authored_call(
                authored_fn,
                authored_params,
                param_path,
                normalized_fn=normalized_fn,
                normalized_params=normalized_params,
            ))
            authored_parameters.append({
                "callId": call_id,
                "fn": authored_fn,
                "param": param_path,
                "authoredValue": deepcopy(authored_value),
                "compiledFields": compiled_fields,
                "claimableFields": compiled_fields,
            })

    field_sources: dict[str, str] = {}
    authored_fields: dict[str, bool] = {}
    for field in (patch or {}):
        if field in authored_sources:
            field_sources[field] = authored_sources[field]
            authored_fields[field] = True
        else:
            field_sources[field] = "runtime_compiler_default"
            authored_fields[field] = False
    for field, source in authored_sources.items():
        field_sources.setdefault(field, source)
        authored_fields.setdefault(field, True)

    # Alias view requested by the debug contract: both compiled names and compact names
    # point to the same authoring fn when present.
    alias_pairs = {
        "range": "rangeTiles",
        "lifetime": "lifetimeTicks",
        "fieldRadius": "vfxFieldRadiusTiles",
    }
    for alias, compiled_field in alias_pairs.items():
        if compiled_field in field_sources:
            field_sources.setdefault(alias, field_sources[compiled_field])
            authored_fields.setdefault(alias, authored_fields.get(compiled_field, False))

    split = int(_num((patch or {}).get("splitCount"), 0) or 0)
    max_child = int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    burst_cap = int(_num((patch or {}).get("burstDustCap"), 0) or 0)
    secondary_calls = all_calls(rp, "spawn_secondary_projectiles")
    particle_calls = all_calls(rp, "spawn_contact_particles")
    trail_calls = all_calls(rp, "leave_trail_or_field")
    normalized_calls = [
        {"index": c.get("_index"), "fn": c.get("fn"), "authoredFn": c.get("_authoredFn") or c.get("_rawFn"), "paramKeys": sorted(list((c.get("params") or {}).keys())) if isinstance(c.get("params"), dict) else []}
        for c in calls if isinstance(c, dict)
    ]
    child_onhits = {"chain", "lightning_arc", "mini_missiles", "vortex_spawn", "radial_beams", "starburst", "overhead_barrage", "spore_cloud"}
    onhit = _norm_name((patch or {}).get("onHit"))
    runtime_family = _norm_name((patch or {}).get("runtimeFamily"))
    overhead_child_count = int(_num((patch or {}).get("shotCount"), 0) or 0) if runtime_family == "overhead_barrage" else 0
    effect_child_count = 0
    if onhit in {"chain", "lightning_arc"}:
        effect_child_count = int(_num((patch or {}).get("chainCount"), 0) or 0)
    elif onhit in child_onhits:
        effect_child_count = split if split > 0 else int(_num((patch or {}).get("maxChildProjectiles"), 0) or 0)
    norm = rp.get("_normalization", {}) if isinstance(rp.get("_normalization"), dict) else {}
    unsupported: list[Any] = []
    for key in ("rejectedEngineCalls", "rejectedRootExecutorCalls", "rejectedSecondaryCalls", "rejectedTrailCalls"):
        values = norm.get(key) if key in norm else (patch or {}).get(key)
        if isinstance(values, list):
            unsupported.extend(values)

    return {
        "api": ENGINE_RUNTIME_API_VERSION,
        "engineFunctions": fns,
        "normalizedCalls": normalized_calls,
        "authoredFields": authored_fields,
        "authoredParameters": authored_parameters,
        "authoredByFunction": authored_by_fn,
        "gameplayChildren": {
            "enabled": (split > 0 and max_child > 0) or effect_child_count > 0 or overhead_child_count > 0,
            "source": "overhead_barrage" if overhead_child_count > 0 else ("spawn_secondary_projectiles" if split > 0 else ("apply_on_hit_effect" if effect_child_count > 0 else "none")),
            "authoredCallCount": len(secondary_calls),
            "compiledFromCallIndices": (patch or {}).get("secondaryCallIndices", []),
            "splitCount": split,
            "onHit": onhit,
            "onHitChildEstimate": effect_child_count,
            "overheadBarrageChildEstimate": overhead_child_count,
            "maxChildProjectiles": max_child,
            "rejectedSecondaryCalls": (patch or {}).get("rejectedSecondaryCalls", []),
            "note": "Real gameplay child projectiles come from spawn_secondary_projectiles, overhead_barrage, or child-producing apply_on_hit_effect values. VFX motes are separate renderer slots."
        },
        "pureVfx": {
            "enabled": "spawn_contact_particles" in fns or "leave_trail_or_field" in fns or burst_cap > 0,
            "source": "spawn_contact_particles" if "spawn_contact_particles" in fns else ("leave_trail_or_field" if "leave_trail_or_field" in fns else "runtime_compiler_default"),
            "authoredCallCount": len(particle_calls) + len(trail_calls),
            "burstDustCap": burst_cap,
            "trailLength": (patch or {}).get("trailLength", 0),
            "fieldRadius": (patch or {}).get("vfxFieldRadiusTiles", 0),
            "material": (patch or {}).get("vfxMaterial", ""),
            "note": "Pure VFX/dust/trails do not imply damaging child projectiles."
        },
        "unsupported": unsupported[:24],
        "futureDisabled": [],
        "fieldSources": field_sources,
        "normalization": norm,
    }

def compiled_runtime_contract(data: dict[str, Any], patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compact executable output for server/debug: this is what the runtime receives."""
    normalize_runtime_plan_inplace(data)
    patch = patch or compile_runtime_plan_to_genome_patch(data)
    rp = runtime_plan(data)
    q = runtime_plan_quality_report(data)
    out = {
        "api": ENGINE_RUNTIME_API_VERSION,
        "compiler": "runtime_plan_to_attack_spec",
        "executableFields": dict(patch),
        "functionCounts": q.get("functionCounts", {}),
        "primaryCall": (rp.get("engineCalls") or [{}])[0] if isinstance(rp.get("engineCalls"), list) and rp.get("engineCalls") else {},
        "notes": [
            "runtimeFamily is explicit; missing or conflicting primary families fail validation",
            "splitCount/maxChildProjectiles represent gameplay children only, not VFX motes",
            "runtimeContract is model-authored public meaning; unsupported engine calls are rejected before final wire",
        ],
    }
    if isinstance(data.get("runtimeContract"), dict):
        out["runtimeContract"] = data.get("runtimeContract")
    return out


def compile_runtime_plan_to_genome_result(data: dict[str, Any]) -> dict[str, Any]:
    patch = compile_runtime_plan_to_genome_patch(data)
    validation = runtime_plan_validation_report(data)
    provenance = runtime_plan_provenance_report(data, patch)
    model = RuntimeCompileResult(
        patch=patch,
        provenance=provenance,
        clamps=[],
        errors=list(validation.get("errors") or []),
    )
    result = model.to_dict()
    # Backwards-compatible debug payload used by older tests/tools.
    result.update({
        "compiled": compiled_runtime_contract(data, patch),
        "validation": validation,
        "quality": runtime_plan_quality_report(data),
    })
    return result


def infer_attack_pattern_from_runtime(genome: dict[str, Any], damage_class: str = "generic") -> str:
    delivery = _norm_name(genome.get("delivery"))
    runtime_family = _enum(_norm_name(genome.get("runtimeFamily")), RUNTIME_FAMILIES, "none")
    movement = _norm_name(genome.get("movement"))
    onhit = _norm_name(genome.get("onHit"))
    damage_class = _norm_name(damage_class)
    if movement in {"orbit", "vortex_orb", "blackhole_pull"}:
        return "orbiting_projectile"
    if movement == "expanding_wave" or onhit in {"aura_pulse", "spore_cloud", "blackhole"}:
        return "field_trap"
    if movement == "gravity_arc" and runtime_family in {"cast", "summon"}:
        return "falling_projectile"
    if runtime_family == "thrust":
        return "spear_thrust"
    if runtime_family == "flail" or movement == "flail_tether":
        return "flail_tether"
    if runtime_family == "yoyo" or movement == "yoyo_hover":
        return "yoyo_hover"
    if runtime_family == "whip" or movement == "whip_lash":
        return "whip_lash"
    if runtime_family == "swing":
        return "beam_slash" if movement in {"phase", "expanding_wave"} else "slash_holdout"
    if movement in {"phase", "accelerate"} and runtime_family in {"cast", "shoot"}:
        return "laser_beam" if damage_class == "magic" or runtime_family == "cast" else "thrown_simple"
    # Child-producing onHit values are executed by OnHitCode. They must not force the
    # animation archetype to thrown_simple; runtime family/source identity wins.
    if runtime_family == "cast" or damage_class == "magic":
        return "magic_projectile"
    if runtime_family == "summon" or damage_class == "summon":
        return "summon_projectile"
    if runtime_family == "shoot" or damage_class == "ranged":
        return "ranged_projectile"
    if runtime_family in {"throw", "returning"}:
        return "thrown_simple"
    return "thrown_simple"

__all__ = ['runtime_plan_quality_report', 'runtime_plan_validation_report', '_authored_field_map', 'runtime_plan_provenance_report', 'compiled_runtime_contract', 'compile_runtime_plan_to_genome_result', 'infer_attack_pattern_from_runtime']
